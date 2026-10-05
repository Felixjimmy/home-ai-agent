"""Ollama embedding adapter and exact pgvector retrieval."""
import hashlib
import json
import math
from ollama import Client
from pydantic import BaseModel, ConfigDict, Field
from uuid import UUID
from app.config import OLLAMA_HOST, EMBEDDING_MODEL, EMBEDDING_DIMENSION, RAG_MAX_DISTANCE, RAG_CONTEXT_CHARS
from app.database import database_connection, json_safe

class SearchRequest(BaseModel):
    model_config=ConfigDict(extra="forbid",str_strip_whitespace=True)
    query: str=Field(min_length=1,max_length=2000)
    limit: int=Field(default=4,ge=1,le=8)
    document_id: UUID | None=None
    appliance_model: str | None=Field(default=None,max_length=160)


def embedding_config():
    client=Client(host=OLLAMA_HOST,timeout=60)
    models=client.list().models
    wanted=EMBEDDING_MODEL if ":" in EMBEDDING_MODEL else EMBEDDING_MODEL+":latest"
    digest=next((m.digest for m in models if m.model in (EMBEDDING_MODEL,wanted)),None)
    if not digest:
        raise RuntimeError(f"Embedding model {EMBEDDING_MODEL} is not installed.")
    if EMBEDDING_DIMENSION!=768:
        raise ValueError("This schema uses 768 dimensions. Migrate the vector column before changing dimensions.")
    config={"model":EMBEDDING_MODEL,"digest":digest,"dimension":EMBEDDING_DIMENSION,"chunk_chars":1600,"overlap_chars":240,"extractor":"v1"}
    return config,hashlib.sha256(json.dumps(config,sort_keys=True).encode()).hexdigest()


def embed(texts, config):
    if not texts or any(not t.strip() for t in texts):
        raise ValueError("Embedding input must not be empty.")
    client=Client(host=OLLAMA_HOST,timeout=120)
    current,_=embedding_config()
    if current!=config:
        raise ValueError("Embedding configuration changed; explicitly reindex the documents.")
    result=client.embed(model=config["model"],input=texts,truncate=False)
    vectors=result.embeddings
    if len(vectors)!=len(texts) or any(len(v)!=config["dimension"] or not all(math.isfinite(x) for x in v) or not any(v) for v in vectors):
        raise ValueError("Invalid embedding output or dimension mismatch.")
    return vectors


def search_home_docs(request: SearchRequest | dict):
    request=SearchRequest.model_validate(request)
    config,config_hash=embedding_config()
    vector=embed([request.query],config)[0]
    with database_connection() as conn:
        count=conn.execute("SELECT count(*) n FROM home_documents d JOIN home_document_versions v ON v.id=d.active_version_id WHERE d.deleted_at IS NULL AND v.status='ready' AND (%s::uuid IS NULL OR d.id=%s) AND (%s::text IS NULL OR d.appliance_model=%s) AND v.config_hash<>%s",(request.document_id,request.document_id,request.appliance_model,request.appliance_model,config_hash)).fetchone()["n"]
        rows=conn.execute("""SELECT d.id document_id,d.title,d.appliance_model,d.effective_date,v.id version_id,
          c.id chunk_id,c.text excerpt,c.section,c.page_start,c.page_end,c.embedding <=> %s::vector distance
          FROM home_documents d JOIN home_document_versions v ON v.id=d.active_version_id
          JOIN home_document_chunks c ON c.version_id=v.id
          WHERE d.deleted_at IS NULL AND v.status='ready' AND v.config_hash=%s
          AND (%s::uuid IS NULL OR d.id=%s) AND (%s::text IS NULL OR d.appliance_model=%s)
          ORDER BY distance,c.id LIMIT %s""",(str(vector),config_hash,request.document_id,request.document_id,request.appliance_model,request.appliance_model,request.limit*3)).fetchall()
    results=[]
    seen=set()
    budget=RAG_CONTEXT_CHARS
    for row in rows:
        row=json_safe(row)
        if row["distance"]>RAG_MAX_DISTANCE or row["excerpt"] in seen:
            continue
        if len(row["excerpt"])>budget:
            continue
        seen.add(row["excerpt"])
        budget-=len(row["excerpt"])
        row["citation_id"]=f"S{len(results)+1}"
        results.append(row)
        if len(results)>=request.limit:
            break
    return {"results":results,"evidence_status":"available" if results else "insufficient","incompatible_documents":count,"config_hash":config_hash}
