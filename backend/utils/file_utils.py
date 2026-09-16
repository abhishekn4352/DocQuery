"""
Secure file-handling utilities.

The core security principle here: the client-supplied filename is NEVER used
to build a filesystem path. It is kept only as a display label. Every file
that touches disk gets a name derived from a server-generated document_id,
so there is no path-traversal surface at all -- not "sanitized", eliminated.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass

from backend import config


class UploadValidationError(Exception):
    """Raised for any problem with an incoming upload. Carries a machine
    readable `code` plus a human-readable `message` for structured error responses."""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


# Magic-byte signatures for a lightweight sanity check that the file's
# *content* roughly matches what its extension claims. This is not a
# security boundary by itself (nothing here is), it just catches obviously
# mislabeled files before they reach a parser.
_MAGIC_BYTES = {
    ".pdf": (b"%PDF-",),
    ".docx": (b"PK\x03\x04",),  # DOCX is a zip container
}


@dataclass
class ValidatedUpload:
    display_filename: str  # safe-to-show original name (no path components)
    extension: str  # e.g. ".pdf" (lowercased, validated against the allow-list)


def get_display_filename(raw_filename: str) -> str:
    """Strip any path components / control characters from a client-supplied
    filename so it is safe to store as a *label* (never as a path)."""
    name = (raw_filename or "").strip()
    # Keep only the final path segment, whatever separator style is used.
    name = name.replace("\\", "/").split("/")[-1]
    # Strip characters that have no business in a filename users will read.
    name = re.sub(r"[\x00-\x1f]", "", name)
    name = name.strip(". ")
    return name or "untitled"


def validate_extension(raw_filename: str) -> str:
    display_name = get_display_filename(raw_filename)
    _, ext = os.path.splitext(display_name)
    ext = ext.lower()
    if ext not in config.ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(config.ALLOWED_EXTENSIONS))
        raise UploadValidationError(
            "UNSUPPORTED_FILE_TYPE",
            f"'{ext or 'unknown'}' files are not supported. Supported types: {allowed}.",
        )
    return ext


def validate_size(size_bytes: int) -> None:
    if size_bytes <= 0:
        raise UploadValidationError("EMPTY_FILE", "The uploaded file is empty.")
    if size_bytes > config.MAX_UPLOAD_SIZE_BYTES:
        raise UploadValidationError(
            "FILE_TOO_LARGE",
            f"File is {human_size(size_bytes)}, which exceeds the "
            f"{config.MAX_UPLOAD_SIZE_MB:.0f} MB limit.",
        )


def validate_magic_bytes(extension: str, head: bytes) -> None:
    signatures = _MAGIC_BYTES.get(extension)
    if not signatures:
        return  # no reliable signature for this type (e.g. .txt) -- skip
    if not any(head.startswith(sig) for sig in signatures):
        raise UploadValidationError(
            "FILE_CONTENT_MISMATCH",
            f"This file's content doesn't look like a valid {extension} file.",
        )


def generate_stored_filename(document_id: str, extension: str) -> str:
    """The ONLY filename ever used to build a real filesystem path. Derived
    entirely from a server-generated id, so it can never contain '..', an
    absolute path, or any character the client controls."""
    return f"{document_id}{extension}"


def human_size(num_bytes: int) -> str:
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"
