from __future__ import annotations


def test_settings_never_exposes_the_api_key(client):
    r = client.get("/api/settings")
    body = r.json()
    serialized = str(body)
    assert "test-fake-key" not in serialized
    assert "GROQ_API_KEY" not in serialized


def test_contact_requires_all_fields(client):
    r = client.post("/api/contact", json={"name": "", "email": "", "message": ""})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "MISSING_FIELDS"


def test_contact_rejects_invalid_email(client):
    r = client.post("/api/contact", json={"name": "A", "email": "not-an-email", "message": "hi"})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "INVALID_EMAIL"


def test_contact_reports_when_smtp_not_configured(client):
    # The test fixture never sets SMTP_USERNAME/PASSWORD/RECEIVER_EMAIL, so this
    # should fail clearly and safely rather than raising an unhandled exception.
    r = client.post("/api/contact", json={"name": "A", "email": "a@example.com", "message": "hi"})
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "CONTACT_NOT_CONFIGURED"


def test_every_error_response_has_the_same_structured_shape(client):
    responses = [
        client.get("/api/documents/does-not-exist"),
        client.delete("/api/documents/does-not-exist"),
        client.post("/api/conversations/does-not-exist/ask", json={"question": "hi"}),
        client.post("/api/documents", files={"file": ("bad.exe", b"x", "application/octet-stream")}),
        client.post("/api/contact", json={"name": "", "email": "", "message": ""}),
    ]
    for r in responses:
        body = r.json()
        assert body["success"] is False
        assert "code" in body["error"]
        assert "message" in body["error"]


def test_validation_error_is_structured_not_raw_pydantic_dump(client):
    # Missing the required "question" field entirely.
    conv = client.post("/api/conversations").json()
    r = client.post(f"/api/conversations/{conv['conversation_id']}/ask", json={})
    assert r.status_code == 422
    body = r.json()
    assert body["success"] is False
    assert body["error"]["code"] == "VALIDATION_ERROR"


def test_cors_headers_present_for_allowed_origin(client):
    r = client.options(
        "/api/documents",
        headers={
            "Origin": "http://127.0.0.1:8080",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert r.status_code in (200, 204)
    assert r.headers.get("access-control-allow-origin") == "http://127.0.0.1:8080"


def test_cors_does_not_reflect_arbitrary_untrusted_origins(client):
    r = client.options(
        "/api/documents",
        headers={
            "Origin": "http://evil.example.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    # Starlette still returns 200 to the preflight itself, but it must NOT
    # grant the untrusted origin access via the allow-origin header.
    assert r.headers.get("access-control-allow-origin") != "http://evil.example.com"
