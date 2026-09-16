"""
Lightweight SQLite persistence for document metadata and chat conversations.

Why SQLite: the project explicitly should not gain a heavyweight database
dependency (Postgres/Redis/etc. are out of scope for a project this size).
SQLite is a single file, ships with Python, and is more than enough to give
documents a real identity and conversations a real, persistent home.

IMPORTANT: init_db() only ever CREATEs tables if they don't exist. It never
drops or truncates anything, so restarting the server never destroys data.
"""
from __future__ import annotations

import contextlib
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Iterator, Optional

from backend import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    document_id       TEXT PRIMARY KEY,
    original_filename  TEXT NOT NULL,
    stored_filename    TEXT NOT NULL UNIQUE,
    file_type          TEXT NOT NULL,
    file_size          INTEGER NOT NULL,
    upload_timestamp   TEXT NOT NULL,
    page_count         INTEGER,
    chunk_count        INTEGER DEFAULT 0,
    processing_status  TEXT NOT NULL DEFAULT 'processing',
    error_message      TEXT
);

CREATE TABLE IF NOT EXISTS conversations (
    conversation_id TEXT PRIMARY KEY,
    title           TEXT,
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id  TEXT NOT NULL,
    role             TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content          TEXT NOT NULL,
    sources_json     TEXT,
    document_scope   TEXT,
    created_at       TEXT NOT NULL,
    FOREIGN KEY (conversation_id) REFERENCES conversations(conversation_id)
);

CREATE INDEX IF NOT EXISTS idx_messages_conversation
    ON messages(conversation_id, id);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id() -> str:
    return uuid.uuid4().hex


@contextlib.contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(config.SQLITE_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    """Safe to call on every startup. Creates tables only if missing."""
    with get_connection() as conn:
        conn.executescript(SCHEMA)


# --------------------------------------------------------------------------
# Documents
# --------------------------------------------------------------------------

def create_document(
    *,
    document_id: Optional[str] = None,
    original_filename: str,
    stored_filename: str,
    file_type: str,
    file_size: int,
) -> dict:
    document_id = document_id or new_id()
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO documents
               (document_id, original_filename, stored_filename, file_type,
                file_size, upload_timestamp, processing_status)
               VALUES (?, ?, ?, ?, ?, ?, 'processing')""",
            (document_id, original_filename, stored_filename, file_type, file_size, _now()),
        )
    return get_document(document_id)


def update_document(document_id: str, **fields: Any) -> Optional[dict]:
    if not fields:
        return get_document(document_id)
    columns = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [document_id]
    with get_connection() as conn:
        conn.execute(f"UPDATE documents SET {columns} WHERE document_id = ?", values)
    return get_document(document_id)


def get_document(document_id: str) -> Optional[dict]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM documents WHERE document_id = ?", (document_id,)
        ).fetchone()
    return dict(row) if row else None


def get_document_by_stored_filename(stored_filename: str) -> Optional[dict]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM documents WHERE stored_filename = ?", (stored_filename,)
        ).fetchone()
    return dict(row) if row else None


def list_documents() -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM documents ORDER BY upload_timestamp DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def delete_document(document_id: str) -> bool:
    with get_connection() as conn:
        cur = conn.execute("DELETE FROM documents WHERE document_id = ?", (document_id,))
        return cur.rowcount > 0


# --------------------------------------------------------------------------
# Conversations & messages
# --------------------------------------------------------------------------

def create_conversation(title: Optional[str] = None) -> dict:
    conversation_id = new_id()
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO conversations (conversation_id, title, created_at) VALUES (?, ?, ?)",
            (conversation_id, title, _now()),
        )
    return get_conversation(conversation_id)


def get_conversation(conversation_id: str) -> Optional[dict]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM conversations WHERE conversation_id = ?", (conversation_id,)
        ).fetchone()
    return dict(row) if row else None


def list_conversations() -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM conversations ORDER BY created_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def delete_conversation(conversation_id: str) -> bool:
    with get_connection() as conn:
        conn.execute("DELETE FROM messages WHERE conversation_id = ?", (conversation_id,))
        cur = conn.execute(
            "DELETE FROM conversations WHERE conversation_id = ?", (conversation_id,)
        )
        return cur.rowcount > 0


def add_message(
    *,
    conversation_id: str,
    role: str,
    content: str,
    sources: Optional[list[dict]] = None,
    document_scope: Optional[str] = None,
) -> dict:
    with get_connection() as conn:
        cur = conn.execute(
            """INSERT INTO messages
               (conversation_id, role, content, sources_json, document_scope, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                conversation_id,
                role,
                content,
                json.dumps(sources) if sources is not None else None,
                document_scope,
                _now(),
            ),
        )
        message_id = cur.lastrowid
        row = conn.execute("SELECT * FROM messages WHERE id = ?", (message_id,)).fetchone()
    return _message_row_to_dict(row)


def get_messages(conversation_id: str, limit: Optional[int] = None) -> list[dict]:
    query = "SELECT * FROM messages WHERE conversation_id = ? ORDER BY id ASC"
    with get_connection() as conn:
        rows = conn.execute(query, (conversation_id,)).fetchall()
    messages = [_message_row_to_dict(r) for r in rows]
    if limit is not None and limit > 0:
        return messages[-limit:]
    return messages


def get_recent_turns(conversation_id: str, max_turns: int) -> list[dict]:
    """Return at most `max_turns` user+assistant pairs (i.e. up to 2*max_turns
    messages), most recent last -- used to build bounded conversational memory."""
    return get_messages(conversation_id, limit=max_turns * 2)


def _message_row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["sources"] = json.loads(d.pop("sources_json")) if d.get("sources_json") else []
    return d
