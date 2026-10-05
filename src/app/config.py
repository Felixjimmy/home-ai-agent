"""Environment-backed configuration for the local development app."""

import os

from dotenv import load_dotenv

load_dotenv()

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:8b")
ENABLE_GUARD = os.getenv("ENABLE_GUARD", "true").strip().casefold() in {"1", "true", "yes", "on"}
ALLOW_PROMPT_OVERRIDE = os.getenv("ALLOW_PROMPT_OVERRIDE", "false").strip().casefold() in {"1", "true", "yes", "on"}
EVENT_TIMEZONE = os.getenv("EVENT_TIMEZONE", "Europe/London")
OLLAMA_THINK = os.getenv("OLLAMA_THINK", "false").strip().casefold() in {"1", "true", "yes", "on"}

DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_NAME = os.getenv("POSTGRES_DB", "home_ai")
DB_USER = os.getenv("POSTGRES_USER", "home_ai")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", "")

from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DOCUMENT_STORAGE_DIR = Path(os.getenv("DOCUMENT_STORAGE_DIR", str(PROJECT_ROOT / "storage" / "documents"))).resolve()
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "embeddinggemma")
EMBEDDING_DIMENSION = int(os.getenv("EMBEDDING_DIMENSION", "768"))
DOCUMENT_MAX_BYTES = int(os.getenv("DOCUMENT_MAX_BYTES", str(10 * 1024 * 1024)))
DOCUMENT_MAX_PAGES = int(os.getenv("DOCUMENT_MAX_PAGES", "200"))
DOCUMENT_MAX_CHARS = int(os.getenv("DOCUMENT_MAX_CHARS", "1000000"))
RAG_MAX_DISTANCE = float(os.getenv("RAG_MAX_DISTANCE", "0.65"))
RAG_CONTEXT_CHARS = int(os.getenv("RAG_CONTEXT_CHARS", "12000"))
