from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.memory import create_session, get_session, list_memory, save_summary, stage_memory_action

router = APIRouter(tags=["Memory"])


class SummaryRequest(BaseModel):
    summary: str = Field(min_length=1, max_length=8000)
    covered_through: int = Field(ge=1)


class MemorySaveRequest(BaseModel):
    key: str = Field(min_length=1, max_length=160)
    value: object
    display_text: str = Field(min_length=1, max_length=1000)
    scope: str = Field(default="household", min_length=1, max_length=160)
    session_id: UUID | None = None


class MemoryUpdateRequest(MemorySaveRequest):
    expected_revision: int = Field(ge=1)


class MemoryForgetRequest(BaseModel):
    memory_id: UUID
    expected_revision: int = Field(ge=1)


@router.post("/sessions", status_code=201)
def create() -> dict:
    return create_session()


@router.get("/sessions/{session_id}")
def read_session(session_id: UUID) -> dict:
    try:
        return get_session(str(session_id))
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post("/sessions/{session_id}/summaries")
def summary(session_id: UUID, request: SummaryRequest) -> dict:
    try:
        return save_summary(str(session_id), request.summary, request.covered_through)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get("/memory")
def memories(scope: str = "household", key: str | None = None) -> dict:
    return {"memories": list_memory(scope, key)}


@router.post("/memory", status_code=202)
def save_memory(request: MemorySaveRequest) -> dict:
    return stage_memory_action("save", request.model_dump(mode="json"), str(request.session_id) if request.session_id else None)


@router.patch("/memory/{memory_id}", status_code=202)
def update_memory(memory_id: UUID, request: MemoryUpdateRequest) -> dict:
    args = request.model_dump(mode="json")
    args["memory_id"] = str(memory_id)
    return stage_memory_action("update", args, str(request.session_id) if request.session_id else None)


@router.post("/memory/forget", status_code=202)
def forget_memory(request: MemoryForgetRequest) -> dict:
    return stage_memory_action("forget", request.model_dump(mode="json"))
