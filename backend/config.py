"""
Centralized configuration for DocQuery.

Every tunable value lives here and is read from the environment (with sane
defaults), so nothing important is hardcoded inside route/service files.
See .env.example at the project root for the full list of variables.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# --- Paths -------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent
DOCUMENT_STORE_DIR = Path(os.getenv("DOCUMENT_STORE_DIR", BASE_DIR / "document_store"))
CHROMA_DB_DIR = Path(os.getenv("CHROMA_DB_DIR", BASE_DIR / "chroma_db"))
SQLITE_DB_PATH = Path(os.getenv("SQLITE_DB_PATH", BASE_DIR / "docquery.db"))
FRONTEND_DIR = Path(os.getenv("FRONTEND_DIR", BASE_DIR / "frontend"))

# --- Server --------------------------------------------------------------
HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8080"))
RELOAD = os.getenv("RELOAD", "true").lower() == "true"
# Comma-separated list of origins allowed to call the API with credentials.
# Defaults to common local dev origins instead of "*" (see security notes in README).
_default_origins = "http://127.0.0.1:8080,http://localhost:8080,http://127.0.0.1:5500,http://localhost:5500"
CORS_ALLOWED_ORIGINS = [
    o.strip() for o in os.getenv("CORS_ALLOWED_ORIGINS", _default_origins).split(",") if o.strip()
]

# --- LLM / Groq ----------------------------------------------------------
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
GROQ_TEMPERATURE = float(os.getenv("GROQ_TEMPERATURE", "0.2"))

# --- Embeddings ------------------------------------------------------------
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
HF_TOKEN = os.getenv("HF_TOKEN") or None

# --- Chunking --------------------------------------------------------------
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "500"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "100"))

# --- Document processing ------------------------------------------------
# A document whose extracted text has fewer non-whitespace characters than
# this is treated as "empty" (e.g. a scanned/image-only PDF) rather than
# silently indexed as near-useless vectors.
MIN_MEANINGFUL_CHARS = int(os.getenv("MIN_MEANINGFUL_CHARS", "20"))

# --- Retrieval ---------------------------------------------------------
TOP_K = int(os.getenv("TOP_K", "4"))
# Chroma's distance metric here is cosine *distance* (0 = identical, larger = less similar).
# A retrieved chunk is dropped if its distance exceeds this threshold. Set high/disabled
# by default so behavior doesn't change unless someone deliberately tightens it.
MAX_DISTANCE_THRESHOLD = float(os.getenv("MAX_DISTANCE_THRESHOLD", "2.0"))
MAX_CHUNKS_PER_DOCUMENT = int(os.getenv("MAX_CHUNKS_PER_DOCUMENT", "2"))  # only applied when >1 document is in scope

# --- Conversation memory -----------------------------------------------
MAX_HISTORY_TURNS = int(os.getenv("MAX_HISTORY_TURNS", "5"))  # user+assistant pairs kept for context

# --- Uploads -------------------------------------------------------------
MAX_UPLOAD_SIZE_MB = float(os.getenv("MAX_UPLOAD_SIZE_MB", "10"))
MAX_UPLOAD_SIZE_BYTES = int(MAX_UPLOAD_SIZE_MB * 1024 * 1024)
ALLOWED_EXTENSIONS = {".pdf", ".txt", ".docx"}

# --- Contact form / SMTP (merged from the old app.py) -----------------
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
RECEIVER_EMAIL = os.getenv("RECEIVER_EMAIL")

# --- Derived / validation -------------------------------------------------
def validate() -> list[str]:
    """Return a list of human-readable configuration problems (empty = OK)."""
    problems = []
    if not GROQ_API_KEY:
        problems.append(
            "GROQ_API_KEY is not set. Create a .env file (see .env.example) "
            "with a valid Groq API key before starting the server."
        )
    if CHUNK_OVERLAP >= CHUNK_SIZE:
        problems.append("CHUNK_OVERLAP must be smaller than CHUNK_SIZE.")
    return problems


def ensure_directories() -> None:
    """Create storage directories if missing. NEVER deletes existing data."""
    DOCUMENT_STORE_DIR.mkdir(parents=True, exist_ok=True)
    CHROMA_DB_DIR.mkdir(parents=True, exist_ok=True)
