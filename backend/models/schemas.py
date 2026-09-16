from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class DocumentOut(BaseModel):
    document_id: str
    original_filename: str
    file_type: str
    file_size: int
    upload_timestamp: str
    page_count: Optional[int] = None
    chunk_count: int = 0
    processing_status: str
    error_message: Optional[str] = None


class ContactRequest(BaseModel):
    name: str
    email: str
    message: str


class ConversationOut(BaseModel):
    conversation_id: str
    title: Optional[str] = None
    created_at: str


class CitationOut(BaseModel):
    filename: str
    document_id: Optional[str] = None
    chunk_id: Optional[str] = None
    page: Optional[str] = None
    section: Optional[str] = None
    excerpt: str
    distance: float


class MessageOut(BaseModel):
    id: int
    role: str
    content: str
    sources: list[CitationOut] = Field(default_factory=list)
    document_scope: Optional[str] = None
    created_at: str


class AskRequest(BaseModel):
    question: str
    document_id: Optional[str] = None


class AskResponse(BaseModel):
    conversation_id: str
    answer: str
    sources: list[CitationOut]
    search_query: str


class SettingsOut(BaseModel):
    groq_model: str
    groq_configured: bool
    embedding_model: str
    chunk_size: int
    chunk_overlap: int
    top_k: int
    max_upload_size_mb: float
    allowed_extensions: list[str]
