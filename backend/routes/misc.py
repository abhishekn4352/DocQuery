from __future__ import annotations

from fastapi import APIRouter

from backend import config
from backend.models.schemas import SettingsOut

router = APIRouter(tags=["misc"])


@router.get("/api/health")
async def health():
    return {"status": "ok"}


@router.get("/api/settings", response_model=SettingsOut)
async def settings():
    # Read-only: reflects the model/config actually in use. The old project's
    # /settings/models/ listed model names that could never actually be
    # switched to; we don't ship a cosmetic selector for something that
    # doesn't work. Change GROQ_MODEL in .env and restart to use a different model.
    return SettingsOut(
        groq_model=config.GROQ_MODEL,
        groq_configured=bool(config.GROQ_API_KEY),
        embedding_model=config.EMBEDDING_MODEL,
        chunk_size=config.CHUNK_SIZE,
        chunk_overlap=config.CHUNK_OVERLAP,
        top_k=config.TOP_K,
        max_upload_size_mb=config.MAX_UPLOAD_SIZE_MB,
        allowed_extensions=sorted(config.ALLOWED_EXTENSIONS),
    )
