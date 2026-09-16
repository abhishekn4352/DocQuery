"""
Document loading, structure-aware extraction, and chunking.

Design goals (per the upgrade brief):
  - No if/elif monster: adding a new format means writing one _load_xxx()
    function and registering it in _LOADERS.
  - Never discard useful metadata the loader already computed (page numbers,
    section headings, etc.) -- this is what makes real citations possible.
  - Detect genuinely empty/unextractable documents (e.g. scanned PDFs)
    instead of silently indexing near-empty vectors.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from backend import config
from backend.utils.errors import AppError


@dataclass
class ProcessedDocument:
    chunks: list[Document]
    page_count: Optional[int]
    total_chars: int
    is_empty: bool
    warnings: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------
# Per-format loaders. Each returns a list of "raw" (pre-chunking) Documents
# with whatever structural metadata is available for that format.
# --------------------------------------------------------------------------

def _load_pdf(file_path: Path) -> list[Document]:
    # Uses pypdf directly (actively maintained) instead of LangChain's
    # PyPDFLoader, which pulls in the now-deprecated `langchain-community`
    # package for exactly this one loader -- see the project's dependency
    # notes. Behavior is equivalent: one Document per page, carrying the
    # same 'page' / 'page_label' / 'total_pages' metadata.
    from pypdf import PdfReader

    reader = PdfReader(str(file_path))
    total_pages = len(reader.pages)
    try:
        page_labels = reader.page_labels
    except Exception:
        page_labels = None

    docs: list[Document] = []
    for index, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        label = page_labels[index] if page_labels and index < len(page_labels) else str(index + 1)
        docs.append(
            Document(
                page_content=text,
                metadata={"page": index, "page_label": label, "total_pages": total_pages},
            )
        )
    return docs


def _load_txt(file_path: Path) -> list[Document]:
    raw_bytes = file_path.read_bytes()

    # Try the common, correct case first.
    for encoding in ("utf-8", "utf-8-sig"):
        try:
            text = raw_bytes.decode(encoding)
            return [Document(page_content=text, metadata={"encoding": encoding})]
        except UnicodeDecodeError:
            continue

    # Fall back to detecting the encoding instead of crashing (this is the
    # direct fix for the old project's "non-UTF-8 .txt upload -> 500" bug).
    try:
        import chardet

        detected = chardet.detect(raw_bytes)
        encoding = detected.get("encoding")
        if not encoding:
            raise ValueError("no encoding detected")
        text = raw_bytes.decode(encoding, errors="strict")
        return [Document(page_content=text, metadata={"encoding": encoding})]
    except Exception as exc:
        raise AppError(
            400,
            "UNREADABLE_TEXT_ENCODING",
            "This .txt file's text encoding could not be detected or decoded. "
            "Please re-save it as UTF-8 and try uploading again.",
        ) from exc


def _load_docx(file_path: Path) -> list[Document]:
    try:
        from docx import Document as DocxFile
    except ImportError as exc:  # pragma: no cover - dependency should always be installed
        raise AppError(
            500, "MISSING_DEPENDENCY", "DOCX support requires the 'python-docx' package."
        ) from exc

    docx_file = DocxFile(str(file_path))
    raw_docs: list[Document] = []
    current_section: Optional[str] = None
    buffer: list[str] = []

    def flush() -> None:
        text = "\n\n".join(buffer).strip()
        if text:
            raw_docs.append(
                Document(page_content=text, metadata={"section": current_section, "element_type": "text"})
            )
        buffer.clear()

    for para in docx_file.paragraphs:
        text = para.text.strip()
        if not text:
            continue
        style_name = (para.style.name if para.style is not None else "") or ""
        if style_name.lower().startswith("heading"):
            flush()
            current_section = text
            buffer.append(text)  # the heading itself is searchable content too
        else:
            buffer.append(text)
    flush()

    # Tables are appended after paragraph text and tagged with the most
    # recent heading seen. python-docx does not expose true document order
    # across paragraphs+tables without walking the raw XML body, so this is
    # a reasonable approximation, not exact positional order.
    for idx, table in enumerate(docx_file.tables):
        rows = []
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells]
            if any(cells):
                rows.append(" | ".join(cells))
        table_text = "\n".join(rows).strip()
        if table_text:
            raw_docs.append(
                Document(
                    page_content=table_text,
                    metadata={"section": current_section, "element_type": "table", "table_index": idx},
                )
            )

    return raw_docs


_LOADERS: dict[str, Callable[[Path], list[Document]]] = {
    ".pdf": _load_pdf,
    ".txt": _load_txt,
    ".docx": _load_docx,
}


def _load_raw(file_path: Path, extension: str) -> list[Document]:
    loader_fn = _LOADERS.get(extension)
    if loader_fn is None:
        raise AppError(400, "UNSUPPORTED_FILE_TYPE", f"No loader is registered for '{extension}' files.")
    return loader_fn(file_path)


def _infer_page_count(raw_docs: list[Document], extension: str) -> Optional[int]:
    if extension == ".pdf":
        pages = [d.metadata.get("page") for d in raw_docs if d.metadata.get("page") is not None]
        total = raw_docs[0].metadata.get("total_pages") if raw_docs else None
        if total is not None:
            try:
                return int(total)
            except (TypeError, ValueError):
                pass
        if pages:
            return max(int(p) for p in pages) + 1
    return None  # not a meaningful concept for .txt, and python-docx has no reliable page count


_METADATA_SCALAR_TYPES = (str, int, float, bool)


def _clean_metadata(metadata: dict) -> dict:
    """Chroma requires metadata values to be str/int/float/bool -- no None,
    no nested structures. Drop anything else instead of letting the whole
    add_documents() call fail on one odd field."""
    cleaned = {}
    for key, value in metadata.items():
        if value is None:
            continue
        if isinstance(value, _METADATA_SCALAR_TYPES):
            cleaned[key] = value
        else:
            cleaned[key] = str(value)
    return cleaned


def process_file(
    *, file_path: Path, extension: str, document_id: str, original_filename: str
) -> ProcessedDocument:
    """Load, (maybe) detect emptiness, and chunk a single uploaded file."""
    raw_docs = _load_raw(file_path, extension)
    total_chars = sum(len(d.page_content.strip()) for d in raw_docs)
    page_count = _infer_page_count(raw_docs, extension)

    if total_chars < config.MIN_MEANINGFUL_CHARS:
        return ProcessedDocument(chunks=[], page_count=page_count, total_chars=total_chars, is_empty=True)

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=config.CHUNK_SIZE, chunk_overlap=config.CHUNK_OVERLAP
    )
    split_docs = splitter.split_documents(raw_docs)

    chunks: list[Document] = []
    for idx, doc in enumerate(split_docs):
        chunk_id = f"{document_id}_{idx}"
        metadata = dict(doc.metadata)
        metadata.update(
            {
                "document_id": document_id,
                "filename": original_filename,
                "file_type": extension.lstrip("."),
                "chunk_id": chunk_id,
                "chunk_index": idx,
            }
        )
        chunks.append(Document(page_content=doc.page_content, metadata=_clean_metadata(metadata)))

    return ProcessedDocument(chunks=chunks, page_count=page_count, total_chars=total_chars, is_empty=False)
