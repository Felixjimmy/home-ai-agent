"""One restart-safe database-backed indexing worker. Run: python -m app.document_worker."""
import argparse
import hashlib
import os
import shutil
import time
from pathlib import Path
from uuid import uuid4
from psycopg.types.json import Jsonb
from app.database import database_connection,migrate
from app.documents import storage_path
from app.document_processing import bounded_extract,chunk_blocks
from app.retrieval import embed


def lease_job():
    with database_connection() as conn:
        # A crashed final attempt must become a visible failure, not disappear.
        failed=conn.execute("UPDATE document_ingestion_jobs SET state='failed',error='Worker lease expired after final attempt',lease_token=NULL WHERE state='processing' AND lease_until<NOW() AND attempts>=3 RETURNING version_id").fetchall()
        for row in failed:
            if row["version_id"]:
                conn.execute("UPDATE home_document_versions SET status='failed',error='Worker lease expired after final attempt' WHERE id=%s AND status='processing'",(row["version_id"],))
        job=conn.execute("SELECT * FROM document_ingestion_jobs WHERE (state='queued' OR (state='processing' AND lease_until<NOW())) AND attempts<3 ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1").fetchone()
        if not job:
            return None
        token=str(uuid4())
        conn.execute("UPDATE document_ingestion_jobs SET state='processing',attempts=attempts+1,lease_token=%s,lease_until=NOW()+interval '5 minutes' WHERE id=%s",(token,job["id"]))
        job["lease_token"]=token
        job["attempts"]+=1
        if job["version_id"]:
            conn.execute("UPDATE home_document_versions SET status='processing',error=NULL WHERE id=%s AND status<>'deleted'",(job["version_id"],))
        return job


def heartbeat(job):
    with database_connection() as conn:
        row=conn.execute("UPDATE document_ingestion_jobs SET lease_until=NOW()+interval '5 minutes' WHERE id=%s AND state='processing' AND lease_token=%s RETURNING id",(job["id"],job["lease_token"])).fetchone()
    if not row:
        raise ValueError("Job cancelled or lease replaced.")


def index_job(job):
    with database_connection() as conn:
        version=conn.execute("SELECT * FROM home_document_versions WHERE id=%s",(job["version_id"],)).fetchone()
    source=storage_path(version["storage_key"])
    if hashlib.sha256(source.read_bytes()).hexdigest()!=version["source_hash"]:
        raise ValueError("Source hash mismatch")
    suffix=Path(version["filename"]).suffix.lower()
    key=f"sources/{job['document_id']}/{version['id']}/original{suffix}"
    target=storage_path(key)
    # File copying is serialized with deletion so a cancelled worker cannot resurrect files.
    with database_connection() as conn:
        doc=conn.execute("SELECT * FROM home_documents WHERE id=%s FOR UPDATE",(job["document_id"],)).fetchone()
        if doc["deleted_at"]:
            raise ValueError("Document deleted")
        target.parent.mkdir(parents=True,exist_ok=True)
        if source!=target:
            temp=target.with_suffix(target.suffix+".tmp")
            shutil.copyfile(source,temp)
            os.replace(temp,target)
        conn.execute("UPDATE home_document_versions SET storage_key=%s WHERE id=%s",(key,version["id"]))
    blocks=bounded_extract(target,suffix)
    chunks=chunk_blocks(blocks)
    vectors=[]
    for start in range(0,len(chunks),16):
        heartbeat(job)
        vectors.extend(embed([c["text"] for c in chunks[start:start+16]],version["config"]))
    with database_connection() as conn:
        doc=conn.execute("SELECT * FROM home_documents WHERE id=%s FOR UPDATE",(job["document_id"],)).fetchone()
        current=conn.execute("SELECT * FROM document_ingestion_jobs WHERE id=%s FOR UPDATE",(job["id"],)).fetchone()
        version=conn.execute("SELECT * FROM home_document_versions WHERE id=%s FOR UPDATE",(job["version_id"],)).fetchone()
        if doc["deleted_at"] or doc["revision"]!=version["expected_revision"] or current["state"]!="processing" or str(current["lease_token"])!=job["lease_token"]:
            if current["state"]=="processing" and str(current["lease_token"])==job["lease_token"]:
                conn.execute("UPDATE document_ingestion_jobs SET state='cancelled',error='Superseded source',lease_token=NULL WHERE id=%s",(job["id"],))
                conn.execute("UPDATE home_document_versions SET status='failed',error='Superseded source' WHERE id=%s AND status<>'deleted'",(version["id"],))
            return
        conn.execute("DELETE FROM home_document_chunks WHERE version_id=%s",(version["id"],))
        for chunk,vector in zip(chunks,vectors,strict=True):
            conn.execute("INSERT INTO home_document_chunks(id,version_id,ordinal,text,section,page_start,page_end,char_count,text_hash,embedding) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::vector)",(str(uuid4()),version["id"],chunk["ordinal"],chunk["text"],chunk["section"],chunk["page_start"],chunk["page_end"],chunk["char_count"],chunk["text_hash"],str(vector)))
        conn.execute("UPDATE home_document_versions SET status='ready',error=NULL WHERE id=%s",(version["id"],))
        conn.execute("UPDATE home_documents SET active_version_id=%s WHERE id=%s",(version["id"],doc["id"]))
        conn.execute("UPDATE document_ingestion_jobs SET state='completed',completed_at=NOW(),lease_token=NULL WHERE id=%s",(job["id"],))


def delete_job(job):
    with database_connection() as conn:
        doc=conn.execute("SELECT * FROM home_documents WHERE id=%s FOR UPDATE",(job["document_id"],)).fetchone()
        if not doc["deleted_at"]:
            raise ValueError("Deletion is not authorized")
        versions=conn.execute("SELECT * FROM home_document_versions WHERE document_id=%s",(doc["id"],)).fetchall()
        for version in versions:
            # Delete originals only from this document's private version directory.
            key=f"sources/{doc['id']}/{version['id']}"
            directory=storage_path(key)
            if directory.is_dir():
                for path in directory.iterdir():
                    if path.is_file():
                        storage_path(str(path.relative_to(storage_path("sources").parent))).unlink(missing_ok=True)
                directory.rmdir()
            conn.execute("UPDATE home_document_versions SET storage_key='' WHERE id=%s",(version["id"],))
            if version["upload_id"]:
                other=conn.execute("SELECT 1 FROM home_document_versions WHERE upload_id=%s AND document_id<>%s AND status<>'deleted'",(version["upload_id"],doc["id"])).fetchone()
                pending=conn.execute("SELECT 1 FROM pending_actions WHERE status='pending' AND expires_at>NOW() AND arguments->'input'->>'upload_id'=%s",(str(version["upload_id"]),)).fetchone()
                if not other and not pending:
                    upload=conn.execute("SELECT * FROM document_uploads WHERE id=%s FOR UPDATE",(version["upload_id"],)).fetchone()
                    if upload:
                        storage_path(upload["storage_key"]).unlink(missing_ok=True)
                        conn.execute("UPDATE home_document_versions SET upload_id=NULL WHERE upload_id=%s",(upload["id"],))
                        conn.execute("DELETE FROM document_uploads WHERE id=%s",(upload["id"],))
        conn.execute("UPDATE document_ingestion_jobs SET state='completed',completed_at=NOW(),lease_token=NULL WHERE id=%s AND lease_token=%s",(job["id"],job["lease_token"]))


def cleanup_uploads():
    with database_connection() as conn:
        rows=conn.execute("""SELECT u.* FROM document_uploads u WHERE u.expires_at<NOW()
          AND NOT EXISTS(SELECT 1 FROM home_document_versions v WHERE v.upload_id=u.id AND v.status<>'deleted')
          AND NOT EXISTS(SELECT 1 FROM pending_actions a WHERE a.status='pending' AND a.expires_at>NOW() AND a.arguments->'input'->>'upload_id'=u.id::text)
          FOR UPDATE SKIP LOCKED LIMIT 100""").fetchall()
        for row in rows:
            storage_path(row["storage_key"]).unlink(missing_ok=True)
            conn.execute("UPDATE home_document_versions SET upload_id=NULL WHERE upload_id=%s",(row["id"],))
            conn.execute("DELETE FROM document_uploads WHERE id=%s",(row["id"],))


def run_once():
    job=lease_job()
    if not job:
        cleanup_uploads()
        return False
    try:
        if job["kind"]=="delete":
            delete_job(job)
        else:
            index_job(job)
    except Exception as error:
        with database_connection() as conn:
            state="failed" if job["attempts"]>=3 or isinstance(error,(ValueError,FileNotFoundError)) else "queued"
            row=conn.execute("UPDATE document_ingestion_jobs SET state=%s,error=%s,lease_token=NULL WHERE id=%s AND state='processing' AND lease_token=%s RETURNING version_id",(state,str(error)[:600],job["id"],job["lease_token"])).fetchone()
            if row and row["version_id"]:
                conn.execute("UPDATE home_document_versions SET status=%s,error=%s WHERE id=%s AND status<>'deleted'",("failed" if state=="failed" else "queued",str(error)[:600],row["version_id"]))
    return True


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--once",action="store_true")
    args=parser.parse_args()
    migrate()
    while True:
        worked=run_once()
        if args.once:
            return
        if not worked:
            time.sleep(2)


if __name__=="__main__":
    main()
