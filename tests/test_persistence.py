"""
Direct regression test for the original project's most severe bug: all
uploaded documents and embeddings were wiped on every restart. This test
does NOT use the `client` fixture (which intentionally gives every test a
fresh temp directory) -- instead it points two SEPARATE app instances at the
SAME directories to simulate a real stop/start of the server, and asserts
the second instance sees everything the first one created.
"""
from __future__ import annotations

import importlib

from fastapi.testclient import TestClient

from tests.conftest import FakeChatModel, FakeEmbeddings


def _build_app(tmp_path, monkeypatch):
    from backend import config

    monkeypatch.setattr(config, "DOCUMENT_STORE_DIR", tmp_path / "document_store")
    monkeypatch.setattr(config, "CHROMA_DB_DIR", tmp_path / "chroma_db")
    monkeypatch.setattr(config, "SQLITE_DB_PATH", tmp_path / "persistent.db")
    monkeypatch.setattr(config, "FRONTEND_DIR", tmp_path / "no_frontend_here")
    monkeypatch.setattr(config, "GROQ_API_KEY", "test-fake-key")

    from backend.services import embedding_service, vector_store, rag_service

    getattr(embedding_service.get_embeddings, "cache_clear", lambda: None)()
    getattr(vector_store.get_store, "cache_clear", lambda: None)()
    getattr(rag_service.get_llm, "cache_clear", lambda: None)()
    monkeypatch.setattr(embedding_service, "get_embeddings", lambda: FakeEmbeddings())
    fake_llm = FakeChatModel()
    monkeypatch.setattr(rag_service, "get_llm", lambda: fake_llm)

    from backend import main as main_module
    importlib.reload(main_module)  # rebuild the FastAPI app fresh, as a real restart would
    return main_module.app


def test_documents_and_search_survive_a_restart(tmp_path, monkeypatch):
    # --- "First run" of the server -----------------------------------
    app_first_run = _build_app(tmp_path, monkeypatch)
    with TestClient(app_first_run) as client:
        upload = client.post(
            "/api/documents",
            files={"file": ("survives.txt", b"This unique warranty contract discusses grape recipe details.", "text/plain")},
        )
        assert upload.status_code == 201
        doc_id = upload.json()["document_id"]
        assert upload.json()["processing_status"] == "ready"

        conv = client.post("/api/conversations").json()
        client.post(f"/api/conversations/{conv['conversation_id']}/ask", json={"question": "What does it discuss?"})

    # --- Simulate a full restart: brand-new app instance, SAME directories ---
    app_second_run = _build_app(tmp_path, monkeypatch)
    with TestClient(app_second_run) as client:
        # The document metadata (SQLite) survived.
        docs = client.get("/api/documents").json()
        assert any(d["document_id"] == doc_id for d in docs)

        # The uploaded file on disk survived.
        downloaded = client.get(f"/api/documents/{doc_id}/download")
        assert downloaded.status_code == 200
        assert b"grape recipe" in downloaded.content

        # The vector embeddings survived (Chroma still finds the chunk).
        conv2 = client.post("/api/conversations").json()
        r = client.post(
            f"/api/conversations/{conv2['conversation_id']}/ask",
            json={"question": "Tell me about the grape recipe warranty"},
        )
        assert len(r.json()["sources"]) > 0
        assert r.json()["sources"][0]["filename"] == "survives.txt"

        # The conversation history from the first run also survived.
        conversations = client.get("/api/conversations").json()
        assert any(c["conversation_id"] == conv["conversation_id"] for c in conversations)
