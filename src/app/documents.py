"""Confirmed document lifecycle and confined persistent source storage."""
import hashlib
import json
from pathlib import Path
from uuid import UUID, uuid4
from datetime import date
from pydantic import BaseModel, ConfigDict, Field, model_validator
from psycopg.types.json import Jsonb
from app.config import DOCUMENT_STORAGE_DIR, DOCUMENT_MAX_BYTES
from app.database import database_connection,json_safe,request_id_context
from app.crud import CrudConflict,CrudNotFound


class DocumentCreate(BaseModel):
    model_config=ConfigDict(extra="forbid",str_strip_whitespace=True)
    upload_id: UUID
    title: str=Field(min_length=1,max_length=200)
    category: str=Field(default="household",min_length=1,max_length=80)
    appliance_model: str | None=Field(default=None,max_length=160)
    effective_date: date | None=None


class DocumentPatch(BaseModel):
    model_config=ConfigDict(extra="forbid",str_strip_whitespace=True)
    expected_revision: int=Field(ge=1)
    title: str | None=Field(default=None,min_length=1,max_length=200)
    category: str | None=Field(default=None,min_length=1,max_length=80)
    appliance_model: str | None=Field(default=None,max_length=160)
    effective_date: date | None=None

    @model_validator(mode="after")
    def nonempty(self):
        if not self.model_fields_set-{"expected_revision"}:
            raise ValueError("Supply at least one metadata field.")
        for key in ("title","category"):
            if key in self.model_fields_set and getattr(self,key) is None:
                raise ValueError(f"{key} cannot be null")
        return self


class DocumentRevision(BaseModel):
    model_config=ConfigDict(extra="forbid")
    expected_revision: int=Field(ge=1)


class DocumentReplace(DocumentRevision):
    upload_id: UUID


def storage_path(key):
    root=DOCUMENT_STORAGE_DIR.resolve()
    path=(root/key).resolve()
    if not path.is_relative_to(root) or path==root:
        raise ValueError("Invalid storage key.")
    return path


def store_upload(file, filename):
    filename=Path(filename.replace("\\","/")).name
    suffix=Path(filename).suffix.lower()
    types={".pdf":"application/pdf",".txt":"text/plain",".md":"text/markdown"}
    if suffix not in types:
        raise ValueError("Unsupported format. Upload .txt, .md, or a text-based .pdf.")
    upload_id=str(uuid4())
    key=f"staging/{upload_id}{suffix}"
    path=storage_path(key)
    path.parent.mkdir(parents=True,exist_ok=True)
    digest=hashlib.sha256()
    size=0
    try:
        with path.open("xb") as out:
            while data:=file.read(65536):
                size+=len(data)
                if size>DOCUMENT_MAX_BYTES:
                    raise ValueError("Upload exceeds the configured size limit.")
                digest.update(data)
                out.write(data)
        if not size:
            raise ValueError("Empty upload.")
        if suffix==".pdf":
            with path.open("rb") as handle:
                if not handle.read(1024).lstrip().startswith(b"%PDF-"):
                    raise ValueError("The file does not contain a PDF header.")
        else:
            text=path.read_text(encoding="utf-8-sig")
            if not text.strip() or "\x00" in text:
                raise ValueError("Upload must contain UTF-8 text.")
        with database_connection() as conn:
            row=conn.execute("INSERT INTO document_uploads(id,storage_key,filename,sha256,byte_size,media_type) VALUES (%s,%s,%s,%s,%s,%s) RETURNING id,filename,sha256,byte_size,media_type,expires_at",(upload_id,key,filename,digest.hexdigest(),size,types[suffix])).fetchone()
        return json_safe(row)
    except Exception:
        path.unlink(missing_ok=True)
        raise


def get_document(document_id, conn=None):
    if conn is None:
        with database_connection() as conn:
            return get_document(document_id,conn)
    row=conn.execute("SELECT * FROM home_documents WHERE id=%s AND deleted_at IS NULL",(document_id,)).fetchone()
    if not row:
        raise CrudNotFound("Document not found.")
    versions=conn.execute("SELECT id,source_hash,filename,status,error,config,created_at FROM home_document_versions WHERE document_id=%s ORDER BY created_at DESC",(document_id,)).fetchall()
    return {**json_safe(row),"versions":json_safe(versions)}


def list_documents(limit=100,offset=0):
    with database_connection() as conn:
        rows=conn.execute("SELECT d.*,v.status index_status FROM home_documents d LEFT JOIN home_document_versions v ON v.id=d.active_version_id WHERE d.deleted_at IS NULL ORDER BY d.created_at DESC LIMIT %s OFFSET %s",(limit,offset)).fetchall()
    return {"items":json_safe(rows)}


def _upload(conn,upload_id):
    row=conn.execute("SELECT *,expires_at>NOW() valid FROM document_uploads WHERE id=%s FOR SHARE",(upload_id,)).fetchone()
    if not row or not row["valid"]:
        raise ValueError("Upload missing or expired. Upload the file again.")
    if not storage_path(row["storage_key"]).is_file():
        raise ValueError("Upload bytes are missing.")
    return row


def propose_document(operation,arguments,idempotency_key=None):
    arguments=json_safe(arguments)
    # Validate even when called through an assistant tool rather than REST.
    schemas={"create":DocumentCreate,"update":DocumentPatch,"replace":DocumentReplace,"reindex":DocumentRevision,"delete":DocumentRevision}
    supplied={k:v for k,v in arguments.items() if k!="document_id"}
    args=schemas[operation].model_validate(supplied).model_dump(mode="json",exclude_unset=True)
    if operation!="create":
        args["document_id"]=str(UUID(arguments["document_id"]))
    index_config = None
    if operation in ("create","replace","reindex"):
        from app.retrieval import embedding_config
        index_config=embedding_config()
    with database_connection() as conn:
        if idempotency_key:
            conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",(idempotency_key,))
            old=conn.execute("SELECT * FROM pending_actions WHERE idempotency_key=%s",(idempotency_key,)).fetchone()
            if old:
                if old["tool_name"]!="document_"+operation or old["arguments"]["input"]!=args:
                    raise CrudConflict("Idempotency key belongs to a different request.")
                return _summary(old)
        payload={"input":args}
        if index_config:
            payload.update(index_config=index_config[0],index_config_hash=index_config[1])
        if "upload_id" in args:
            upload=_upload(conn,args["upload_id"])
            payload["sha256"]=upload["sha256"]
        if operation!="create":
            doc=get_document(args["document_id"],conn)
            if doc["revision"]!=args["expected_revision"]:
                raise CrudConflict("Document revision changed. Read it again before proposing.")
        payload["description"]=f"{operation.capitalize()} document: "+args.get("title",args.get("document_id",""))
        if payload.get("sha256"):
            payload["description"]+="; source SHA-256 "+payload["sha256"]
        if index_config:
            payload["description"]+="; embedding "+index_config[0]["model"]
        row=conn.execute("INSERT INTO pending_actions(id,tool_name,arguments,payload_version,request_id,idempotency_key) VALUES (%s,%s,%s,2,%s,%s) RETURNING *",(str(uuid4()),"document_"+operation,Jsonb(payload),request_id_context.get(),idempotency_key)).fetchone()
    return _summary(row)


def _summary(row):
    return {"id":str(row["id"]),"tool_name":row["tool_name"],"description":row["arguments"]["description"],"status":row["status"],"expires_at":str(row["expires_at"])}


def apply_document_action(conn,action):
    op=action["tool_name"].removeprefix("document_")
    payload=action["arguments"]
    args=payload["input"]
    upload=None
    if "upload_id" in args:
        upload=_upload(conn,args["upload_id"])
        if upload["sha256"]!=payload["sha256"]:
            raise CrudConflict("Upload content changed.")
    if op=="create":
        document_id=str(uuid4())
        conn.execute("INSERT INTO home_documents(id,title,category,appliance_model,effective_date) VALUES (%s,%s,%s,%s,%s)",(document_id,args["title"],args.get("category","household"),args.get("appliance_model"),args.get("effective_date")))
        revision=1
    else:
        document_id=args["document_id"]
        doc=conn.execute("SELECT * FROM home_documents WHERE id=%s AND deleted_at IS NULL FOR UPDATE",(document_id,)).fetchone()
        if not doc:
            raise CrudNotFound("Document not found.")
        if doc["revision"]!=args["expected_revision"]:
            raise CrudConflict("Document changed since the proposal. Request a new proposal.")
        revision=doc["revision"]+1
        conn.execute("UPDATE home_documents SET revision=%s,updated_at=NOW() WHERE id=%s",(revision,document_id))
        if op=="update":
            from psycopg import sql
            fields={k:v for k,v in args.items() if k not in ("document_id","expected_revision")}
            assignments=sql.SQL(',').join(sql.SQL('{}=%s').format(sql.Identifier(k)) for k in fields)
            conn.execute(sql.SQL("UPDATE home_documents SET {} WHERE id=%s").format(assignments),[*fields.values(),document_id])
            # Metadata changes do not invalidate the already-authorized source.
            conn.execute("UPDATE home_document_versions SET expected_revision=%s WHERE document_id=%s AND status IN ('queued','processing')",(revision,document_id))
            return {"document_id":document_id,"revision":revision,"status":"updated"}
        if op=="delete":
            conn.execute("UPDATE home_documents SET deleted_at=NOW(),active_version_id=NULL WHERE id=%s",(document_id,))
            conn.execute("UPDATE document_ingestion_jobs SET state='cancelled',lease_token=NULL WHERE document_id=%s AND state IN ('queued','processing')",(document_id,))
            conn.execute("DELETE FROM home_document_chunks WHERE version_id IN (SELECT id FROM home_document_versions WHERE document_id=%s)",(document_id,))
            conn.execute("UPDATE home_document_versions SET status='deleted' WHERE document_id=%s",(document_id,))
            job_id=str(uuid4())
            conn.execute("INSERT INTO document_ingestion_jobs(id,document_id,action_id,kind) VALUES (%s,%s,%s,'delete')",(job_id,document_id,action["id"]))
            return {"document_id":document_id,"status":"deleted","cleanup_status":"queued","job_id":job_id}
        if op=="reindex":
            previous=conn.execute("SELECT * FROM home_document_versions WHERE document_id=%s ORDER BY created_at DESC LIMIT 1",(document_id,)).fetchone()
            if not previous:
                raise CrudConflict("No source to reindex.")
            upload={"id":previous["upload_id"],"sha256":previous["source_hash"],"filename":previous["filename"],"media_type":previous["media_type"],"storage_key":previous["storage_key"],"byte_size":previous["byte_size"]}
    # Config was frozen at proposal time, outside the database transaction.
    config=payload.get("index_config")
    config_hash=payload.get("index_config_hash")
    if not config or not config_hash:
        raise ValueError("Index configuration missing.")
    existing=conn.execute("SELECT * FROM home_document_versions WHERE document_id=%s AND source_hash=%s AND config_hash=%s",(document_id,upload["sha256"],config_hash)).fetchone()
    if existing and existing["status"]=="ready":
        conn.execute("UPDATE home_documents SET active_version_id=%s WHERE id=%s",(existing["id"],document_id))
        return {"document_id":document_id,"version_id":str(existing["id"]),"status":"ready","reused":True}
    if existing and existing["status"] in ("queued","processing"):
        conn.execute("UPDATE home_document_versions SET expected_revision=%s WHERE id=%s",(revision,existing["id"]))
        job=conn.execute("SELECT id FROM document_ingestion_jobs WHERE version_id=%s AND state IN ('queued','processing')",(existing["id"],)).fetchone()
        return {"document_id":document_id,"version_id":str(existing["id"]),"status":"queued","job_id":str(job["id"])}
    version_id=str(existing["id"]) if existing else str(uuid4())
    if existing:
        conn.execute("UPDATE home_document_versions SET status='queued',error=NULL,expected_revision=%s WHERE id=%s",(revision,version_id))
    else:
        conn.execute("INSERT INTO home_document_versions(id,document_id,upload_id,source_hash,filename,media_type,storage_key,byte_size,config,config_hash,expected_revision) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",(version_id,document_id,upload["id"],upload["sha256"],upload["filename"],upload["media_type"],upload["storage_key"],upload["byte_size"],Jsonb(config),config_hash,revision))
    job_id=str(uuid4())
    conn.execute("INSERT INTO document_ingestion_jobs(id,document_id,version_id,action_id) VALUES (%s,%s,%s,%s)",(job_id,document_id,version_id,action["id"]))
    return {"document_id":document_id,"version_id":version_id,"job_id":job_id,"status":"queued"}


def get_job(job_id):
    with database_connection() as conn:
        row=conn.execute("SELECT id,document_id,version_id,kind,state,attempts,error,created_at,completed_at FROM document_ingestion_jobs WHERE id=%s",(job_id,)).fetchone()
    if not row:
        raise CrudNotFound("Job not found.")
    return json_safe(row)


def source_file(document_id,version_id):
    with database_connection() as conn:
        row=conn.execute("SELECT v.* FROM home_document_versions v JOIN home_documents d ON d.id=v.document_id WHERE d.id=%s AND v.id=%s AND d.deleted_at IS NULL",(document_id,version_id)).fetchone()
    if not row:
        raise CrudNotFound("Source not found.")
    path=storage_path(row["storage_key"])
    if not path.is_file():
        raise CrudNotFound("Source bytes are unavailable.")
    return path,row["filename"],row["media_type"]
