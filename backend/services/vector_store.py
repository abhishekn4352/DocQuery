"""
Chroma vector store access.

All calls here go through one cached Chroma client (get_store()) so the
connection is opened once per process rather than re-opened on every
request. Every write/read is scoped by the `document_id` metadata field
that document_service.py attaches to every chunk, which is what makes
per-document deletion and per-document search both safe and precise
(verified in isolation: deleting one document's chunks by
`where={"document_id": ...}` does not touch any other document's chunks --
see the project's test suite / analysis notes for the reproduction).
"""
from __future__ import annotations

from functools import lru_cache
from typing import Optional

from langchain_chroma import Chroma
from langchain_core.documents import Document

from backend import config
from backend.services import embedding_service


@lru_cache(maxsize=1)
def get_store() -> Chroma:
    config.ensure_directories()
    return Chroma(
        persist_directory=str(config.CHROMA_DB_DIR),
        embedding_function=embedding_service.get_embeddings(),
        collection_name="docquery",
    )


def add_chunks(chunks: list[Document]) -> None:
    if not chunks:
        return
    ids = [c.metadata["chunk_id"] for c in chunks]
    get_store().add_documents(chunks, ids=ids)


def delete_document_chunks(document_id: str) -> None:
    """Remove every chunk belonging to one document. Chunks of every other
    document are left untouched (scoped by metadata filter, not by a range
    or a naive 'delete everything and re-add' approach)."""
    get_store().delete(where={"document_id": document_id})


def search_with_scores(
    query: str,
    *,
    top_k: int,
    document_id: Optional[str] = None,
) -> list[tuple[Document, float]]:
    """Lower score = more similar (Chroma returns a distance, not a
    similarity, for this metric -- verified empirically)."""
    filter_ = {"document_id": document_id} if document_id else None
    # Over-fetch a little so the diversity/threshold pass in rag_service has
    # room to drop weak or over-represented results and still return top_k.
    fetch_k = max(top_k * 3, top_k + 4)
    return get_store().similarity_search_with_score(query, k=fetch_k, filter=filter_)
