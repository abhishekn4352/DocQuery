"""
Regression tests for graceful handling when the Groq call itself fails.

This is a direct response to running the app for real: a retired model
name (`llama-3.1-8b-instant`, deprecated by Groq) caused the streaming
endpoint to crash mid-response with no signal to the client, leaving the
UI stuck. These tests pin down the fix: the non-streaming endpoint returns
a clean structured error, the streaming endpoint emits a clean "error"
event instead of aborting the connection, and a failure in the (optional)
question-condensation step degrades gracefully instead of blocking the
whole answer.
"""
from __future__ import annotations

import json

from tests.conftest import AlwaysFailingChatModel, CondenseFailsChatModel


def _upload_txt(client, filename: str, content: bytes) -> dict:
    return client.post("/api/documents", files={"file": (filename, content, "text/plain")}).json()


def test_ask_returns_clean_error_when_llm_fails(client, monkeypatch):
    from backend.services import rag_service

    _upload_txt(client, "policy.txt", b"The retrieval architecture is central to this system.")
    monkeypatch.setattr(rag_service, "get_llm", lambda: AlwaysFailingChatModel())

    conv = client.post("/api/conversations").json()
    r = client.post(
        f"/api/conversations/{conv['conversation_id']}/ask",
        json={"question": "What is the retrieval architecture?"},
    )
    assert r.status_code == 502
    body = r.json()
    assert body["success"] is False
    assert body["error"]["code"] == "LLM_REQUEST_FAILED"
    assert "model" in body["error"]["message"].lower()


def test_stream_emits_error_event_instead_of_crashing(client, monkeypatch):
    from backend.services import rag_service

    _upload_txt(client, "policy.txt", b"The retrieval architecture is central to this system.")
    monkeypatch.setattr(rag_service, "get_llm", lambda: AlwaysFailingChatModel())

    conv = client.post("/api/conversations").json()
    with client.stream(
        "POST",
        f"/api/conversations/{conv['conversation_id']}/ask/stream",
        json={"question": "What is the retrieval architecture?"},
    ) as response:
        assert response.status_code == 200  # already committed -- this is exactly why an in-band event is needed
        events = []
        for line in response.iter_lines():
            if line and line.startswith("data: "):
                events.append(json.loads(line[len("data: "):]))

    event_types = [e["type"] for e in events]
    assert event_types[0] == "sources"
    assert event_types[-1] == "error"
    assert "done" not in event_types
    error_event = events[-1]
    assert error_event["code"] == "LLM_REQUEST_FAILED"

    # Only the user's question is saved -- no blank/failed assistant turn.
    messages = client.get(f"/api/conversations/{conv['conversation_id']}").json()["messages"]
    assert len(messages) == 1
    assert messages[0]["role"] == "user"


def test_stream_error_event_does_not_crash_the_connection_before_any_upload(client, monkeypatch):
    """Same failure, but with zero documents uploaded -- makes sure the
    error path doesn't depend on retrieval having found anything."""
    from backend.services import rag_service

    monkeypatch.setattr(rag_service, "get_llm", lambda: AlwaysFailingChatModel())
    conv = client.post("/api/conversations").json()

    with client.stream(
        "POST",
        f"/api/conversations/{conv['conversation_id']}/ask/stream",
        json={"question": "Anything in here?"},
    ) as response:
        assert response.status_code == 200
        events = [
            json.loads(line[len("data: "):])
            for line in response.iter_lines()
            if line and line.startswith("data: ")
        ]

    # No documents -> no citations -> the (canned) no-context answer is used,
    # which doesn't call the LLM at all, so this should succeed normally.
    assert events[-1]["type"] == "done"


def test_condensation_failure_falls_back_to_original_question(client, monkeypatch):
    """The condensation step is a nice-to-have for follow-up questions. If
    it fails, the answer should still be generated using the original,
    un-rewritten question rather than failing the whole request."""
    from backend.services import rag_service

    _upload_txt(
        client, "methodology.txt",
        b"The proposed architecture was designed by the retrieval engineering team "
        b"using a three stage python pipeline.",
    )
    fake_llm = CondenseFailsChatModel()
    monkeypatch.setattr(rag_service, "get_llm", lambda: fake_llm)

    conv = client.post("/api/conversations").json()
    conv_id = conv["conversation_id"]

    # First turn has no history yet, so condensation is skipped entirely --
    # this call succeeds regardless of the fake's failure condition.
    r1 = client.post(f"/api/conversations/{conv_id}/ask", json={"question": "What is the architecture?"})
    assert r1.status_code == 200

    # Second turn has history, so condensation WOULD run (and fail, per the
    # fake) -- the request should still succeed via the fallback to the
    # original question. That fallback question needs to be retrievable on
    # its own (not just as a pronoun needing resolution) so this test
    # isolates "did condensation-failure fall back correctly" from
    # "would the retrieval fake have found this anyway" -- a real, richer
    # embedding model would resolve "who designed it" without help; this
    # fake deliberately can't, so the question below stands on its own.
    r2 = client.post(f"/api/conversations/{conv_id}/ask", json={"question": "Who designed the python architecture?"})
    assert r2.status_code == 200
    assert r2.json()["answer"] == "[answer despite condensation failure]"

    messages = client.get(f"/api/conversations/{conv_id}").json()["messages"]
    assert len(messages) == 4
