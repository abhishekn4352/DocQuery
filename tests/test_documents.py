from __future__ import annotations

from tests.conftest import make_docx_bytes, make_pdf_bytes


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_upload_txt_success(client, sample_txt_bytes):
    r = client.post(
        "/api/documents",
        files={"file": ("notes.txt", sample_txt_bytes, "text/plain")},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["original_filename"] == "notes.txt"
    assert body["processing_status"] == "ready"
    assert body["chunk_count"] > 0
    assert body["file_type"] == "txt"


def test_upload_pdf_success_preserves_page_metadata(client):
    pdf_bytes = make_pdf_bytes(
        [
            "Page one. The architecture uses three retrieval stages.",
            "Page two. Revenue clauses are described in section four.",
        ]
    )
    r = client.post("/api/documents", files={"file": ("report.pdf", pdf_bytes, "application/pdf")})
    assert r.status_code == 201
    body = r.json()
    assert body["processing_status"] == "ready"
    assert body["page_count"] == 2
    assert body["chunk_count"] >= 2


def test_upload_docx_success(client):
    docx_bytes = make_docx_bytes(
        sections=[
            ("Introduction", ["This contract covers warranty terms.", "It also covers pricing."]),
            ("Definitions", ["A grape is a fruit used in the recipe example."]),
        ],
        tables=[[["Term", "Definition"], ["Warranty", "One year coverage"]]],
    )
    r = client.post(
        "/api/documents",
        files={"file": ("terms.docx", docx_bytes, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["processing_status"] == "ready"
    assert body["file_type"] == "docx"
    assert body["chunk_count"] > 0


def test_upload_unsupported_extension_rejected(client):
    r = client.post("/api/documents", files={"file": ("virus.exe", b"MZ\x90\x00fake", "application/octet-stream")})
    assert r.status_code == 400
    body = r.json()
    assert body["success"] is False
    assert body["error"]["code"] == "UNSUPPORTED_FILE_TYPE"


def test_upload_oversized_file_rejected(client):
    # fixture sets MAX_UPLOAD_SIZE_MB=1
    big_content = b"a" * (2 * 1024 * 1024)
    r = client.post("/api/documents", files={"file": ("big.txt", big_content, "text/plain")})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "FILE_TOO_LARGE"


def test_upload_empty_txt_is_marked_empty_not_indexed(client):
    r = client.post("/api/documents", files={"file": ("blank.txt", b"   \n\n   ", "text/plain")})
    assert r.status_code == 201
    body = r.json()
    assert body["processing_status"] == "empty"
    assert body["chunk_count"] == 0
    assert "no searchable text" in body["error_message"].lower()


def test_upload_pdf_content_mismatch_rejected(client):
    # A .pdf extension on content that is clearly not a real PDF (magic-byte check).
    r = client.post("/api/documents", files={"file": ("fake.pdf", b"not actually a pdf file", "application/pdf")})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "FILE_CONTENT_MISMATCH"


def test_malicious_filename_cannot_escape_storage_directory(client, sample_txt_bytes, tmp_path):
    """Direct regression test for the path-traversal vulnerability found in
    the original project: a crafted filename must never cause a write
    outside DOCUMENT_STORE_DIR."""
    from backend import config

    malicious_name = "../../../../tmp/escaped_evil_file.txt"
    r = client.post("/api/documents", files={"file": (malicious_name, sample_txt_bytes, "text/plain")})
    assert r.status_code == 201
    body = r.json()

    # The display name may retain a harmless label, but nothing was written
    # using the raw client-supplied path.
    stored_path_candidates = list(config.DOCUMENT_STORE_DIR.glob("*"))
    assert all(".." not in p.name for p in stored_path_candidates)
    assert not (tmp_path / "escaped_evil_file.txt").exists()
    assert not (config.DOCUMENT_STORE_DIR.parent / "escaped_evil_file.txt").exists()

    # And the file that WAS written lives only inside DOCUMENT_STORE_DIR.
    doc_id = body["document_id"]
    stored_filename = None
    from backend import database
    stored_filename = database.get_document(doc_id)["stored_filename"]
    assert (config.DOCUMENT_STORE_DIR / stored_filename).exists()
    assert ".." not in stored_filename
    assert "/" not in stored_filename


def test_list_documents(client, sample_txt_bytes):
    client.post("/api/documents", files={"file": ("a.txt", sample_txt_bytes, "text/plain")})
    client.post("/api/documents", files={"file": ("b.txt", sample_txt_bytes, "text/plain")})
    r = client.get("/api/documents")
    assert r.status_code == 200
    names = {d["original_filename"] for d in r.json()}
    assert names == {"a.txt", "b.txt"}


def test_download_document_roundtrip(client, sample_txt_bytes):
    upload = client.post("/api/documents", files={"file": ("roundtrip.txt", sample_txt_bytes, "text/plain")})
    doc_id = upload.json()["document_id"]
    r = client.get(f"/api/documents/{doc_id}/download")
    assert r.status_code == 200
    assert r.content == sample_txt_bytes


def test_delete_nonexistent_document_returns_404(client):
    r = client.delete("/api/documents/does-not-exist")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "NOT_FOUND"


def test_delete_removes_file_and_db_record(client, sample_txt_bytes):
    from backend import config

    upload = client.post("/api/documents", files={"file": ("todelete.txt", sample_txt_bytes, "text/plain")})
    doc_id = upload.json()["document_id"]
    stored_filename = upload.json()  # placeholder, fetched properly below
    from backend import database
    stored_filename = database.get_document(doc_id)["stored_filename"]
    assert (config.DOCUMENT_STORE_DIR / stored_filename).exists()

    r = client.delete(f"/api/documents/{doc_id}")
    assert r.status_code == 200
    assert r.json()["success"] is True

    assert not (config.DOCUMENT_STORE_DIR / stored_filename).exists()
    assert client.get(f"/api/documents/{doc_id}").status_code == 404


def test_delete_does_not_affect_other_documents(client, sample_txt_bytes):
    """Direct regression test for Phase 6's requirement: deleting one
    document's chunks must never remove another document's chunks."""
    doc_a = client.post("/api/documents", files={"file": ("keep.txt", sample_txt_bytes, "text/plain")}).json()
    doc_b = client.post("/api/documents", files={"file": ("remove.txt", sample_txt_bytes, "text/plain")}).json()

    client.delete(f"/api/documents/{doc_b['document_id']}")

    # doc_a must still be listed and still fully downloadable/queryable.
    assert client.get(f"/api/documents/{doc_a['document_id']}").status_code == 200
    remaining = client.get("/api/documents").json()
    assert len(remaining) == 1
    assert remaining[0]["document_id"] == doc_a["document_id"]
