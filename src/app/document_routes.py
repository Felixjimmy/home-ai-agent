"""Document APIs: staging is separate from confirmation and indexing."""
from uuid import UUID
from fastapi import APIRouter,UploadFile,File,Header,Query
from fastapi.responses import FileResponse
from app.documents import (DocumentCreate,DocumentPatch,DocumentReplace,DocumentRevision,store_upload,
    propose_document,list_documents,get_document,get_job,source_file)
from app.retrieval import SearchRequest,search_home_docs

router=APIRouter(prefix="/documents",tags=["Home documents"])

@router.post("/uploads",status_code=201)
def upload(file: UploadFile=File(...)):
    return store_upload(file.file,file.filename or "")

@router.post("/search")
def search(request: SearchRequest):
    return search_home_docs(request)

@router.get("/jobs/{job_id}")
def job(job_id: UUID):
    return get_job(job_id)

@router.get("")
def listing(limit: int=Query(100,ge=1,le=500),offset: int=Query(0,ge=0)):
    return list_documents(limit,offset)

@router.post("",status_code=202)
def create(request: DocumentCreate,idempotency_key: str | None=Header(None,max_length=200)):
    return propose_document("create",request.model_dump(mode="json"),idempotency_key)

@router.get("/{document_id}")
def read(document_id: UUID):
    return get_document(document_id)

@router.get("/{document_id}/versions/{version_id}/source")
def source(document_id: UUID,version_id: UUID):
    path,filename,media_type=source_file(document_id,version_id)
    return FileResponse(path,filename=filename,media_type=media_type)

@router.patch("/{document_id}",status_code=202)
def update(document_id: UUID,request: DocumentPatch,idempotency_key: str | None=Header(None,max_length=200)):
    return propose_document("update",{**request.model_dump(mode="json",exclude_unset=True),"document_id":str(document_id)},idempotency_key)

@router.post("/{document_id}/versions",status_code=202)
def replace(document_id: UUID,request: DocumentReplace,idempotency_key: str | None=Header(None,max_length=200)):
    return propose_document("replace",{**request.model_dump(mode="json"),"document_id":str(document_id)},idempotency_key)

@router.post("/{document_id}/reindex",status_code=202)
def reindex(document_id: UUID,request: DocumentRevision,idempotency_key: str | None=Header(None,max_length=200)):
    return propose_document("reindex",{**request.model_dump(),"document_id":str(document_id)},idempotency_key)

@router.delete("/{document_id}",status_code=202)
def delete(document_id: UUID,expected_revision: int=Query(...,ge=1),idempotency_key: str | None=Header(None,max_length=200)):
    return propose_document("delete",{"expected_revision":expected_revision,"document_id":str(document_id)},idempotency_key)
