"""Opt-in in-process evaluation traces; never enabled by an HTTP request field."""
from contextvars import ContextVar
trace_context: ContextVar[list | None] = ContextVar("evaluation_trace",default=None)
