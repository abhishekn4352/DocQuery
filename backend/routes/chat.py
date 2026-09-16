from __future__ import annotations

import json
import logging

from fastapi import APIRouter
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from starlette.concurrency import iterate_in_threadpool

from backend import config, database
from backend.models.schemas import AskRequest, AskResponse
from backend.services import rag_service
from backend.utils.errors import not_found

logger = logging.getLogger("docquery")
router = APIRouter(prefix="/api/conversations", tags=["chat"])


def _history_for_llm(conversation_id: str) -> list[dict]:
    turns = database.get_recent_turns(conversation_id, config.MAX_HISTORY_TURNS)
    return [{"role": m["role"], "content": m["content"]} for m in turns]


def _maybe_set_title(conversation_id: str, question: str) -> None:
    conversation = database.get_conversation(conversation_id)
    if conversation and not conversation.get("title"):
        title = question.strip().replace("\n", " ")
        if len(title) > 60:
            title = title[:57].rstrip() + "..."
        with database.get_connection() as conn:
            conn.execute(
                "UPDATE conversations SET title = ? WHERE conversation_id = ?",
                (title, conversation_id),
            )


@router.post("")
async def create_conversation():
    return database.create_conversation()


@router.get("")
async def list_conversations():
    return database.list_conversations()


@router.get("/{conversation_id}")
async def get_conversation_messages(conversation_id: str):
    conversation = database.get_conversation(conversation_id)
    if not conversation:
        raise not_found("Conversation")
    return {"conversation": conversation, "messages": database.get_messages(conversation_id)}


@router.delete("/{conversation_id}")
async def delete_conversation(conversation_id: str):
    if not database.delete_conversation(conversation_id):
        raise not_found("Conversation")
    return {"success": True}


@router.post("/{conversation_id}/ask", response_model=AskResponse)
async def ask(conversation_id: str, payload: AskRequest):
    conversation = database.get_conversation(conversation_id)
    if not conversation:
        raise not_found("Conversation")

    history = _history_for_llm(conversation_id)
    result = await run_in_threadpool(
        rag_service.answer_question,
        payload.question,
        document_id=payload.document_id,
        history=history,
    )

    database.add_message(
        conversation_id=conversation_id, role="user", content=payload.question,
        document_scope=payload.document_id,
    )
    database.add_message(
        conversation_id=conversation_id, role="assistant", content=result["answer"],
        sources=result["sources"], document_scope=payload.document_id,
    )
    _maybe_set_title(conversation_id, payload.question)

    return AskResponse(
        conversation_id=conversation_id,
        answer=result["answer"],
        sources=result["sources"],
        search_query=result["search_query"],
    )


@router.post("/{conversation_id}/ask/stream")
async def ask_stream(conversation_id: str, payload: AskRequest):
    conversation = database.get_conversation(conversation_id)
    if not conversation:
        raise not_found("Conversation")

    history = _history_for_llm(conversation_id)

    async def event_generator():
        collected = {"answer": None, "sources": []}
        generator = rag_service.stream_answer(
            payload.question, document_id=payload.document_id, history=history
        )
        async for event in iterate_in_threadpool(generator):
            if event["type"] == "done":
                collected["answer"] = event["answer"]
                collected["sources"] = event["sources"]
            yield f"data: {json.dumps(event)}\n\n"

        # Always log what the user asked. Only log an assistant turn if one
        # was actually produced -- an "error" event means collected["answer"]
        # is still None, and we don't want a blank reply saved into history.
        database.add_message(
            conversation_id=conversation_id, role="user", content=payload.question,
            document_scope=payload.document_id,
        )
        if collected["answer"] is not None:
            database.add_message(
                conversation_id=conversation_id, role="assistant", content=collected["answer"],
                sources=collected["sources"], document_scope=payload.document_id,
            )
        _maybe_set_title(conversation_id, payload.question)

    return StreamingResponse(event_generator(), media_type="text/event-stream")
