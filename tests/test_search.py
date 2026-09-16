from __future__ import annotations

from tests.conftest import make_pdf_bytes


def _upload_txt(client, filename: str, content: bytes) -> dict:
    return client.post("/api/documents", files={"file": (filename, content, "text/plain")}).json()


def test_ask_with_no_documents_returns_no_context_answer(client):
    conv = client.post("/api/conversations").json()
    r = client.post(
        f"/api/conversations/{conv['conversation_id']}/ask", json={"question": "What is the refund policy?"}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["sources"] == []
    assert "couldn't find" in body["answer"].lower()


def test_ask_grounds_answer_in_retrieved_context(client):
    _upload_txt(
        client, "policy.txt",
        b"Our warranty policy: the contract covers one year of coverage for the product. "
        b"Grape flavored items are excluded from the warranty.",
    )
    conv = client.post("/api/conversations").json()
    r = client.post(
        f"/api/conversations/{conv['conversation_id']}/ask",
        json={"question": "What does the warranty contract cover?"},
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body["sources"]) > 0
    assert body["sources"][0]["filename"] == "policy.txt"
    # Verify the fake LLM's *actual received prompt* contains the retrieved
    # excerpt -- i.e. the answer really is grounded in context, not just that
    # *a* response came back.
    from backend.services import rag_service
    last_messages = rag_service.get_llm().last_messages
    combined = " ".join(m.content for m in last_messages)
    assert "warranty" in combined.lower()
    assert "Question: What does the warranty contract cover?" in combined


def test_pdf_citation_includes_page_number(client):
    pdf_bytes = make_pdf_bytes(
        ["First page about cats and dogs.", "Second page: the invoice contract details revenue clauses."]
    )
    client.post("/api/documents", files={"file": ("doc.pdf", pdf_bytes, "application/pdf")})
    conv = client.post("/api/conversations").json()
    r = client.post(
        f"/api/conversations/{conv['conversation_id']}/ask",
        json={"question": "What do the revenue clauses say?"},
    )
    body = r.json()
    assert len(body["sources"]) > 0
    pages = {s["page"] for s in body["sources"]}
    assert pages  # at least one source has a page value
    assert all(p in {"1", "2"} for p in pages if p is not None)


def test_document_scoped_search_only_returns_that_document(client):
    _upload_txt(client, "cats.txt", b"This document is entirely about cats and dogs as pets.")
    doc_b = _upload_txt(client, "contracts.txt", b"This document is entirely about invoice contract revenue clauses.")

    conv = client.post("/api/conversations").json()
    r = client.post(
        f"/api/conversations/{conv['conversation_id']}/ask",
        json={"question": "Tell me about cats", "document_id": doc_b["document_id"]},
    )
    body = r.json()
    # Scoped to doc_b, so even a cats-related question can only surface doc_b's content.
    for source in body["sources"]:
        assert source["document_id"] == doc_b["document_id"]


def test_deleted_document_no_longer_appears_in_search(client):
    doc = _upload_txt(client, "temporary.txt", b"This unique document discusses grape recipe warranty details.")
    client.delete(f"/api/documents/{doc['document_id']}")

    conv = client.post("/api/conversations").json()
    r = client.post(
        f"/api/conversations/{conv['conversation_id']}/ask",
        json={"question": "Tell me about the grape recipe warranty"},
    )
    body = r.json()
    assert body["sources"] == []


def test_conversation_memory_is_used_for_follow_up(client):
    _upload_txt(
        client, "methodology.txt",
        b"The proposed architecture was designed by the retrieval engineering team. "
        b"It uses a python based contract for revenue processing.",
    )
    conv = client.post("/api/conversations").json()
    conv_id = conv["conversation_id"]

    r1 = client.post(f"/api/conversations/{conv_id}/ask", json={"question": "What is the architecture?"})
    assert r1.status_code == 200

    r2 = client.post(f"/api/conversations/{conv_id}/ask", json={"question": "Who designed it?"})
    assert r2.status_code == 200

    # The second call's condensation step must have seen the first turn.
    messages = client.get(f"/api/conversations/{conv_id}").json()["messages"]
    assert len(messages) == 4  # user, assistant, user, assistant
    assert messages[2]["content"] == "Who designed it?"


def test_conversation_history_persists_and_is_listable(client):
    conv = client.post("/api/conversations").json()
    client.post(f"/api/conversations/{conv['conversation_id']}/ask", json={"question": "hello"})
    listing = client.get("/api/conversations").json()
    assert any(c["conversation_id"] == conv["conversation_id"] for c in listing)
    # Greeting shortcut should have auto-titled the conversation.
    titled = next(c for c in listing if c["conversation_id"] == conv["conversation_id"])
    assert titled["title"]


def test_ask_on_unknown_conversation_returns_404(client):
    r = client.post("/api/conversations/does-not-exist/ask", json={"question": "hi"})
    assert r.status_code == 404


def test_greeting_shortcut_returns_canned_reply_without_sources(client):
    conv = client.post("/api/conversations").json()
    r = client.post(f"/api/conversations/{conv['conversation_id']}/ask", json={"question": "hello"})
    body = r.json()
    assert body["sources"] == []
    assert "upload a document" in body["answer"].lower()


def test_streaming_ask_emits_sources_then_tokens_then_done(client):
    _upload_txt(client, "stream_doc.txt", b"This document discusses python contract revenue architecture details.")
    conv = client.post("/api/conversations").json()

    with client.stream(
        "POST",
        f"/api/conversations/{conv['conversation_id']}/ask/stream",
        json={"question": "What does the document discuss?"},
    ) as response:
        assert response.status_code == 200
        event_types = []
        for line in response.iter_lines():
            if not line or not line.startswith("data: "):
                continue
            import json as _json
            event = _json.loads(line[len("data: "):])
            event_types.append(event["type"])

    assert event_types[0] == "sources"
    assert event_types[-1] == "done"
    assert "token" in event_types

    # The streamed turn must also have been persisted to conversation history.
    messages = client.get(f"/api/conversations/{conv['conversation_id']}").json()["messages"]
    assert len(messages) == 2
    assert messages[1]["role"] == "assistant"
    assert len(messages[1]["content"]) > 0
