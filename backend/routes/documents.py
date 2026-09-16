from __future__ import annotations

import logging

from fastapi import APIRouter, File, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse

from backend import config, database
from backend.services import document_service, vector_store
from backend.utils import file_utils
from backend.utils.errors import AppError, not_found

logger = logging.getLogger("docquery")
router = APIRouter(prefix="/api/documents", tags=["documents"])


@router.post("", status_code=201)
async def upload_document(file: UploadFile = File(...)):
    display_filename = file_utils.get_display_filename(file.filename or "")
    extension = file_utils.validate_extension(display_filename)

    contents = await file.read()
    file_utils.validate_size(len(contents))
    file_utils.validate_magic_bytes(extension, contents[:8])

    document_id = database.new_id()
    stored_filename = file_utils.generate_stored_filename(document_id, extension)
    file_path = config.DOCUMENT_STORE_DIR / stored_filename
    config.ensure_directories()
    file_path.write_bytes(contents)

    doc = database.create_document(
        document_id=document_id,
        original_filename=display_filename,
        stored_filename=stored_filename,
        file_type=extension.lstrip("."),
        file_size=len(contents),
    )

    try:
        # Embedding + PDF/DOCX parsing are CPU/IO-bound and synchronous; run them
        # off the event loop so one big upload doesn't stall other requests.
        processed = await run_in_threadpool(
            document_service.process_file,
            file_path=file_path,
            extension=extension,
            document_id=document_id,
            original_filename=display_filename,
        )
    except AppError:
        raise
    except Exception as exc:  # a genuinely unexpected parsing failure
        logger.exception("Failed to process document %s", document_id)
        doc = database.update_document(
            document_id, processing_status="failed", error_message=str(exc)
        )
        return doc

    if processed.is_empty:
        doc = database.update_document(
            document_id,
            processing_status="empty",
            page_count=processed.page_count,
            chunk_count=0,
            error_message="No searchable text could be extracted from this file.",
        )
        return doc

    await run_in_threadpool(vector_store.add_chunks, processed.chunks)
    doc = database.update_document(
        document_id,
        processing_status="ready",
        page_count=processed.page_count,
        chunk_count=len(processed.chunks),
    )
    return doc


@router.get("")
async def list_documents():
    return database.list_documents()


@router.get("/{document_id}")
async def get_document(document_id: str):
    doc = database.get_document(document_id)
    if not doc:
        raise not_found("Document")
    return doc


@router.get("/{document_id}/download")
async def download_document(document_id: str):
    doc = database.get_document(document_id)
    if not doc:
        raise not_found("Document")
    file_path = config.DOCUMENT_STORE_DIR / doc["stored_filename"]
    if not file_path.exists():
        raise AppError(404, "FILE_MISSING", "The stored file could not be found on disk.")
    return FileResponse(path=file_path, filename=doc["original_filename"])


@router.delete("/{document_id}")
async def delete_document(document_id: str):
    doc = database.get_document(document_id)
    if not doc:
        raise not_found("Document")

    file_path = config.DOCUMENT_STORE_DIR / doc["stored_filename"]
    if file_path.exists():
        file_path.unlink()

    await run_in_threadpool(vector_store.delete_document_chunks, document_id)
    database.delete_document(document_id)
    return {"success": True, "document_id": document_id}
