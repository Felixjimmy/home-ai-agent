"""FastAPI entry point for chat, safe tool execution, and event extraction."""

import re
from contextlib import asynccontextmanager
from typing import Literal
from uuid import UUID, uuid4

import psycopg
from fastapi import FastAPI, HTTPException, status, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from httpx import HTTPError
from ollama import ResponseError
from pydantic import BaseModel, Field, model_validator

from app.config import ALLOW_PROMPT_OVERRIDE, ENABLE_GUARD, OLLAMA_MODEL
from app import crud
from app.database import check_database, database_connection, migrate, request_id_context
from app.actions import stage_action
from app.evaluation import trace_context
from app.llm import extract_calendar_event, run_agent
from app.memory import append_message, context_for_session
from app.schemas import (
    ActionDecision,
    EventExtractionRequest,
    EventExtractionResponse,
    PendingActionSummary,
)
from app.tools import ToolInputError, confirmation_description, execute_pending_action, preflight_write_tool

@asynccontextmanager
async def lifespan(_: FastAPI):
    migrate()
    yield


app = FastAPI(title="Home AI Agent", version="0.3.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Accept", "Content-Type"],
)
from app.document_routes import router as document_router
app.include_router(document_router)
from app.memory_routes import router as memory_router
app.include_router(memory_router)


@app.middleware("http")
async def request_identity(request: Request, call_next):
    token=request_id_context.set(str(uuid4()))
    try:
        response=await call_next(request)
        response.headers["X-Request-ID"]=request_id_context.get()
        return response
    finally:
        request_id_context.reset(token)


@app.exception_handler(ValueError)
async def invalid_value(request, error):
    code=409 if isinstance(error,crud.CrudConflict) else 404 if isinstance(error,crud.CrudNotFound) else 422
    message=str(error)
    if "size limit" in message:
        code=413
    if "Unsupported format" in message:
        code=415
    return JSONResponse(status_code=code,content={"detail":message})


@app.exception_handler(psycopg.Error)
async def database_error(request,error):
    return JSONResponse(status_code=503,content={"detail":"PostgreSQL could not complete the request."})


@app.exception_handler(RuntimeError)
@app.exception_handler(HTTPError)
@app.exception_handler(ResponseError)
async def dependency_error(request,error):
    return JSONResponse(status_code=503,content={"detail":"Model service unavailable or incompatible. Check model installation and configuration."})


class CrudWriteRequest(BaseModel):
    data: dict


def _crud_entity(entity: str) -> None:
    if entity not in crud._TABLES:
        raise HTTPException(status_code=404, detail=f"CRUD is not enabled for entity '{entity}'.")


def _stage_crud_action(tool_name: str, arguments: dict, idempotency_key=None) -> dict:
    try:
        validated = crud.validate_action(tool_name, arguments)
        proposal = stage_action(tool_name,validated,idempotency_key)
    except crud.CrudNotFound as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except crud.CrudConflict as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except (crud.CrudError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except psycopg.IntegrityError as error:
        raise HTTPException(status_code=409, detail="The proposed record conflicts with existing data or a database constraint.") from error
    except psycopg.Error as error:
        raise HTTPException(status_code=503, detail="PostgreSQL could not stage the proposed change") from error
    return proposal


@app.get("/data", tags=["Household data"])
def list_crud_entities() -> dict:
    """List user-managed entity types available through CRUD."""
    return {"entities": sorted(crud._TABLES), "internal_entities_excluded": ["pending_actions", "tool_call_logs"]}


@app.get("/data/{entity}", tags=["Household data"])
def list_data(entity: str, limit: int = 100, offset: int = 0) -> dict:
    _crud_entity(entity)
    try:
        with database_connection() as connection:
            return crud.list_records(connection, crud.ListRecordsArgs(entity=entity, limit=limit, offset=offset))
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except psycopg.Error as error:
        raise HTTPException(status_code=503, detail="PostgreSQL could not read household data") from error


@app.get("/data/{entity}/{record_id}", tags=["Household data"])
def get_data(entity: str, record_id: int) -> dict:
    _crud_entity(entity)
    try:
        with database_connection() as connection:
            return crud.get_record(connection, crud.GetRecordArgs(entity=entity, record_id=record_id))
    except crud.CrudNotFound as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except psycopg.Error as error:
        raise HTTPException(status_code=503, detail="PostgreSQL could not read household data") from error


@app.post("/data/{entity}", status_code=status.HTTP_202_ACCEPTED, tags=["Household data"])
def create_data(entity: str, request: CrudWriteRequest, idempotency_key: str | None=Header(None,max_length=200)) -> dict:
    _crud_entity(entity)
    return _stage_crud_action("crud_create_record", {"entity": entity, "data": request.data},idempotency_key)


@app.patch("/data/{entity}/{record_id}", status_code=status.HTTP_202_ACCEPTED, tags=["Household data"])
def update_data(entity: str, record_id: int, request: CrudWriteRequest, idempotency_key: str | None=Header(None,max_length=200)) -> dict:
    _crud_entity(entity)
    return _stage_crud_action("crud_update_record", {"entity": entity, "record_id": record_id, "data": request.data},idempotency_key)


@app.delete("/data/{entity}/{record_id}", status_code=status.HTTP_202_ACCEPTED, tags=["Household data"])
def delete_data(entity: str, record_id: int, idempotency_key: str | None=Header(None,max_length=200)) -> dict:
    _crud_entity(entity)
    return _stage_crud_action("crud_delete_record", {"entity": entity, "record_id": record_id},idempotency_key)

_FALSE_AUTHORITY = re.compile(
    r"\b(?:i am|i'm|this is)\s+(?:the\s+)?(?:developer|system|administrator)\b",
    re.IGNORECASE,
)


def _pre_model_safety_response(message: str) -> str | None:
    """Deterministically reject common user-message authority claims."""
    from app.llm import trusted_question
    if ENABLE_GUARD and _FALSE_AUTHORITY.search(trusted_question(message)):
        return "I can’t accept authority claims made in a user message. I can help with a home-related request."
    return None


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    session_id: UUID | None = None
    agent: Literal["handwritten", "langgraph", "multi_agent"] = "handwritten"
    mode: Literal["assistant","knowledge"] = "assistant"
    document_id: UUID | None = None
    appliance_model: str | None = Field(default=None,max_length=160)
    temperature: float | None = Field(default=None, ge=0, le=1)
    system_prompt: str | None = Field(default=None, min_length=1, max_length=4000)
    response_format: Literal["text", "calendar_event"] = Field(
        default="text",
        description="Use calendar_event to request structured event extraction.",
    )

    @model_validator(mode="after")
    def prevent_prompt_override_for_structured_output(self) -> "ChatRequest":
        if self.mode=="knowledge" and (self.system_prompt is not None or self.response_format!="text" or len(self.message)>2000):
            raise ValueError("Knowledge mode requires text output, no prompt override, and a question of at most 2000 characters.")
        if self.response_format == "calendar_event" and self.system_prompt is not None:
            raise ValueError("system_prompt cannot be combined with calendar_event output")
        return self


class ChatResponse(BaseModel):
    response: str
    model: str
    latency_ms: int
    pending_actions: list[PendingActionSummary] = Field(default_factory=list)
    sources: list[dict] = Field(default_factory=list)
    evidence_status: str = "not_applicable"
    request_id: str | None = None
    session_id: str | None = None
    memory_refs: list[str] = Field(default_factory=list)
    agent: Literal["handwritten", "langgraph", "multi_agent"] = "handwritten"


def _event_response(message: str, temperature: float | None) -> EventExtractionResponse:
    try:
        event, latency_ms = extract_calendar_event(message, temperature=temperature)
    except HTTPError as error:
        raise HTTPException(status_code=503, detail="Ollama is unavailable") from error
    except ResponseError as error:
        raise HTTPException(status_code=502, detail=f"Ollama request failed: {error}") from error
    except RuntimeError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    return EventExtractionResponse(event=event, model=OLLAMA_MODEL, latency_ms=round(latency_ms))


@app.get("/health")
def health() -> dict[str, str]:
    """Check app and PostgreSQL connectivity (Ollama is checked per chat)."""
    if not check_database():
        raise HTTPException(status_code=503, detail="PostgreSQL is unavailable")
    return {"status": "ok", "database": "ok"}


@app.post("/chat", response_model=ChatResponse | EventExtractionResponse)
def chat(request: ChatRequest) -> ChatResponse | EventExtractionResponse:
    """Chat using enabled tools; write proposals are returned pending confirmation."""
    context_messages, memory_refs, _ = context_for_session(str(request.session_id) if request.session_id else None)
    if request.session_id:
        append_message(str(request.session_id), "user", request.message)
    if request.mode=="knowledge":
        from app.knowledge import answer_question
        result=answer_question(request.message,request.temperature,request.document_id,request.appliance_model,trace_context.get())
        if request.session_id:
            append_message(str(request.session_id), "assistant", result["response"], OLLAMA_MODEL)
        return ChatResponse(**result,model=OLLAMA_MODEL,request_id=request_id_context.get(),session_id=str(request.session_id) if request.session_id else None,memory_refs=memory_refs)
    if request.response_format == "calendar_event":
        return _event_response(request.message, request.temperature)
    if request.system_prompt is not None and not ALLOW_PROMPT_OVERRIDE:
        raise HTTPException(
            status_code=403,
            detail="Prompt overrides are disabled; set ALLOW_PROMPT_OVERRIDE=true only for trusted local development.",
        )
    safety_response = _pre_model_safety_response(request.message)
    if safety_response is not None:
        return ChatResponse(response=safety_response, model=OLLAMA_MODEL, latency_ms=0,request_id=request_id_context.get())
    try:
        runner = run_agent
        if request.agent == "langgraph":
            from app.langgraph_agent import run_agent_langgraph
            runner = run_agent_langgraph
        elif request.agent == "multi_agent":
            from app.multi_agent import run_multi_agent
            runner = run_multi_agent
        response, latency_ms, pending_actions = runner(
            request.message,
            temperature=request.temperature,
            system_prompt=request.system_prompt,
            trace=trace_context.get(),
            context_messages=context_messages,
        )
    except HTTPError as error:
        raise HTTPException(status_code=503, detail="Ollama is unavailable") from error
    except ResponseError as error:
        raise HTTPException(status_code=502, detail=f"Ollama request failed: {error}") from error
    except psycopg.Error as error:
        raise HTTPException(status_code=503, detail="PostgreSQL is unavailable") from error
    except RuntimeError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    if request.session_id:
        append_message(str(request.session_id), "assistant", response, OLLAMA_MODEL)
    return ChatResponse(
        response=response,
        model=OLLAMA_MODEL,
        latency_ms=round(latency_ms),
        pending_actions=[PendingActionSummary(**action) for action in pending_actions],
        request_id=request_id_context.get(),
        session_id=str(request.session_id) if request.session_id else None,
        memory_refs=memory_refs,
        agent=request.agent,
    )


@app.post("/actions/{action_id}/decision")
def decide_action(action_id: UUID, decision: ActionDecision) -> dict:
    """Execute or reject one pending write after an explicit confirmation."""
    try:
        result = execute_pending_action(str(action_id), decision.confirm)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except crud.CrudConflict as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except crud.CrudNotFound as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except psycopg.IntegrityError as error:
        raise HTTPException(status_code=409, detail="The change conflicts with existing data or a database constraint.") from error
    except crud.CrudError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except ToolInputError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except psycopg.Error as error:
        raise HTTPException(status_code=503, detail="PostgreSQL could not complete the action") from error
    if result["status"] == "expired":
        raise HTTPException(status_code=410, detail="This pending action expired. Please ask for it again.")
    return result


@app.post("/extract-event", response_model=EventExtractionResponse)
def extract_event(request: EventExtractionRequest) -> EventExtractionResponse:
    """Extract a candidate event without creating a calendar entry."""
    return _event_response(request.message, request.temperature)
