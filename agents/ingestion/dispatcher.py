"""
agents/ingestion/dispatcher.py
----------------------------------
The single public entry point for Sprint 1: `ingest()`.

Everything upstream (Streamlit upload handler, batch CLI, tests) calls this
one function with either a local file path or a URL, and gets back a
`DocumentRecord` -- it never needs to know whether that meant PyMuPDF,
python-docx, python-pptx, Tesseract, or requests+BeautifulSoup under the hood.
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path

from core.config import SUPPORTED_FILE_EXTENSIONS
from core.schemas import DocumentRecord, SourceFormat
from agents.ingestion import image_parser, office_parser, pdf_parser, url_parser
from agents.ingestion.base import UnsupportedFormatError

logger = logging.getLogger(__name__)

_FORMAT_ENUM_BY_KEY = {
    "pdf": SourceFormat.PDF,
    "docx": SourceFormat.DOCX,
    "pptx": SourceFormat.PPTX,
    "image": SourceFormat.IMAGE,
    "html": SourceFormat.HTML,
}


def ingest(source: str, doc_id: str | None = None) -> DocumentRecord:
    """Ingest one document, from a local file path OR an http(s) URL.

    Returns a DocumentRecord with `blocks` populated (empty list is valid --
    e.g. a pure evidentiary photo with no text -- and is recorded as a
    warning, not an exception). Raises UnsupportedFormatError / FetchError
    for genuine failures.
    """
    doc_id = doc_id or f"doc_{uuid.uuid4().hex[:8]}"

    if source.lower().startswith(("http://", "https://")):
        blocks, page_count, warnings = url_parser.ingest_url(source)
        # Best-effort format label for a URL: infer from what the URL parser
        # actually routed to, via the blocks it produced (or default HTML).
        fmt = blocks[0].source_format if blocks else SourceFormat.HTML
        return DocumentRecord(
            doc_id=doc_id,
            source_file=source,
            source_format=fmt,
            page_count=page_count,
            blocks=blocks,
            warnings=warnings,
        )

    path = Path(source)
    if not path.exists():
        raise FileNotFoundError(f"No such file: {source}")

    suffix = path.suffix.lower()
    format_key = SUPPORTED_FILE_EXTENSIONS.get(suffix)
    if format_key is None:
        raise UnsupportedFormatError(
            f"Unsupported file extension {suffix!r} for {source!r}. "
            f"Supported: {sorted(SUPPORTED_FILE_EXTENSIONS)}"
        )

    if format_key == "pdf":
        blocks, page_count, warnings = pdf_parser.parse_pdf(str(path), source_file=str(path))
    elif format_key == "docx":
        blocks, page_count, warnings = office_parser.parse_docx(str(path), source_file=str(path))
    elif format_key == "pptx":
        blocks, page_count, warnings = office_parser.parse_pptx(str(path), source_file=str(path))
    elif format_key == "image":
        blocks, page_count, warnings = image_parser.parse_image(str(path), source_file=str(path))
    elif format_key == "html":
        blocks, page_count, warnings = url_parser.parse_html_file(str(path), source_file=str(path))
    else:  # pragma: no cover - guarded by SUPPORTED_FILE_EXTENSIONS above
        raise UnsupportedFormatError(f"No parser registered for format key {format_key!r}")

    return DocumentRecord(
        doc_id=doc_id,
        source_file=str(path),
        source_format=_FORMAT_ENUM_BY_KEY[format_key],
        page_count=page_count,
        blocks=blocks,
        warnings=warnings,
    )


def discover_files(directory: str, link_manifest_name: str = "claim_links.txt") -> list[str]:
    """Recursively walk a directory (a real claim packet rarely arrives as
    one flat folder -- expect fnol/, evidence/, correspondence/
    subdirectories, mixed formats throughout) and return every file path
    with a supported extension, plus any URLs listed in a manifest file
    (default name 'claim_links.txt', one URL per line, '#' for comments) --
    so a claim folder can reference documents that live elsewhere (a
    carrier portal, cloud storage) without downloading them ahead of time.

    Returns a flat list of strings ready to pass straight to ingest_many():
    local paths and/or http(s):// URLs, in deterministic (sorted) order.
    """
    root = Path(directory)
    if not root.exists():
        raise FileNotFoundError(f"No such directory: {directory}")
    if not root.is_dir():
        raise NotADirectoryError(f"Not a directory: {directory}")

    sources: list[str] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.name == link_manifest_name:
            sources.extend(_read_link_manifest(path))
            continue
        if path.suffix.lower() in SUPPORTED_FILE_EXTENSIONS:
            sources.append(str(path))
        else:
            logger.debug("Skipping unsupported file during discovery: %s", path)
    return sources


def _read_link_manifest(path: Path) -> list[str]:
    urls: list[str] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.lower().startswith(("http://", "https://")):
            urls.append(line)
        else:
            logger.warning("Ignoring non-URL line in link manifest %s: %r", path, line)
    return urls


def ingest_claim_folder(directory: str) -> list[DocumentRecord]:
    """Convenience wrapper: discover every supported file/link under a claim
    folder and ingest all of them in one batch. This is the function a
    Streamlit upload handler or batch CLI should call for 'process this
    whole claim' rather than assembling the file list manually."""
    sources = discover_files(directory)
    if not sources:
        logger.warning("No ingestible files or links found under %s", directory)
    return ingest_many(sources)


def ingest_many(sources: list[str]) -> list[DocumentRecord]:
    """Ingest a batch of files/URLs (one claim's full document bundle).
    A single bad document logs and is skipped rather than aborting the
    whole claim -- one corrupted attachment shouldn't block the other 14.
    """
    records: list[DocumentRecord] = []
    for source in sources:
        try:
            records.append(ingest(source))
        except Exception as exc:  # noqa: BLE001 - intentionally broad at batch boundary
            logger.error("Failed to ingest %r: %s", source, exc)
            records.append(
                DocumentRecord(
                    doc_id=f"doc_{uuid.uuid4().hex[:8]}",
                    source_file=source,
                    source_format=SourceFormat.HTML,  # placeholder; ingestion failed
                    page_count=None,
                    blocks=[],
                    warnings=[f"INGESTION FAILED: {exc}"],
                )
            )
    return records
