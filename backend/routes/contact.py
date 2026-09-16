from __future__ import annotations

from fastapi import APIRouter
from fastapi.concurrency import run_in_threadpool

from backend.models.schemas import ContactRequest
from backend.services import email_service

router = APIRouter(prefix="/api", tags=["contact"])


@router.post("/contact")
async def contact(payload: ContactRequest):
    await run_in_threadpool(
        email_service.send_contact_email,
        name=payload.name, email=payload.email, message=payload.message,
    )
    return {"success": True, "message": "Message sent."}
