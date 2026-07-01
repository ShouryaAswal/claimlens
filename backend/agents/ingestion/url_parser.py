"""
agents/ingestion/url_parser.py
----------------------------------
Hyperlink ingestion. A claim packet increasingly arrives as links rather
than attachments (a portal link to a PDF, a cloud-storage link to photos,
a link to a webpage with claim details).

Strategy:
  1. Fetch the URL.
  2. Sniff Content-Type. If it maps to a known file format (PDF/DOCX/PPTX/
     image), download to a temp file and hand off to the matching parser --
     so a hyperlink to a PDF is treated identically to an uploaded PDF.
  3. Otherwise, treat the response as HTML and extract visible text per
     block-level element (paragraphs, list items, headings, table cells).
     There's no fixed visual page for arbitrary HTML in this MVP, so
     `bbox` stays None -- same graceful degradation as DOCX.
"""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from core.config import (
    CONTENT_TYPE_TO_EXTENSION,
    URL_FETCH_MAX_BYTES,
    URL_FETCH_TIMEOUT_SECONDS,
)
from core.schemas import ContentBlock, SourceFormat
from agents.ingestion import image_parser, office_parser, pdf_parser
from agents.ingestion.base import FetchError, next_block_id

logger = logging.getLogger(__name__)

_HTML_TEXT_TAGS = ["p", "li", "h1", "h2", "h3", "h4", "h5", "td", "blockquote"]
_STRIP_TAGS = ["script", "style", "nav", "footer", "header", "noscript"]


def ingest_url(url: str) -> tuple[list[ContentBlock], int | None, list[str]]:
    warnings: list[str] = []
    try:
        resp = requests.get(url, timeout=URL_FETCH_TIMEOUT_SECONDS, stream=True)
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise FetchError(f"Could not fetch {url!r}: {exc}") from exc

    content_length = resp.headers.get("Content-Length")
    if content_length and int(content_length) > URL_FETCH_MAX_BYTES:
        raise FetchError(
            f"{url!r} reports {content_length} bytes, "
            f"exceeding the {URL_FETCH_MAX_BYTES}-byte ingestion limit."
        )

    content = resp.content
    if len(content) > URL_FETCH_MAX_BYTES:
        raise FetchError(
            f"{url!r} body is {len(content)} bytes, "
            f"exceeding the {URL_FETCH_MAX_BYTES}-byte ingestion limit."
        )

    content_type = resp.headers.get("Content-Type", "").split(";")[0].strip().lower()

    suffix = CONTENT_TYPE_TO_EXTENSION.get(content_type)
    if suffix is None:
        # Fall back to sniffing the URL path itself (some servers mislabel
        # Content-Type, e.g. serving a PDF as application/octet-stream).
        lowered = url.lower()
        for ext in (".pdf", ".docx", ".pptx", ".png", ".jpg", ".jpeg", ".tiff", ".bmp"):
            if lowered.endswith(ext):
                suffix = ext
                break

    if suffix is not None:
        blocks, page_count, parser_warnings = _ingest_downloaded_file(content, suffix, url)
        return blocks, page_count, warnings + parser_warnings

    # Default: treat as HTML.
    blocks = _parse_html(resp.text, source_file=url)
    if not blocks:
        warnings.append(f"No extractable text found at {url!r} (HTML, but no matching elements).")
    return blocks, None, warnings


def parse_html_file(path: str, source_file: str | None = None) -> tuple[list[ContentBlock], None, list[str]]:
    """Local .html/.htm file -- e.g. a saved email or web page printout
    dropped into a claim folder. Reuses the same extraction logic as
    fetched-URL HTML, since the provenance story is identical (no fixed
    visual page, locator-only)."""
    source_file = source_file or str(path)
    html = Path(path).read_text(encoding="utf-8", errors="replace")
    blocks = _parse_html(html, source_file=source_file)
    warnings: list[str] = []
    if not blocks:
        warnings.append(f"No extractable text found in {source_file!r} (HTML, but no matching elements).")
    return blocks, None, warnings


def _ingest_downloaded_file(
    content: bytes, suffix: str, source_url: str
) -> tuple[list[ContentBlock], int | None, list[str]]:
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name
    try:
        if suffix == ".pdf":
            return pdf_parser.parse_pdf(tmp_path, source_file=source_url)
        elif suffix == ".docx":
            return office_parser.parse_docx(tmp_path, source_file=source_url)
        elif suffix == ".pptx":
            return office_parser.parse_pptx(tmp_path, source_file=source_url)
        else:
            return image_parser.parse_image(tmp_path, source_file=source_url)
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            logger.warning("Could not remove temp file %s", tmp_path)


def _parse_html(html: str, source_file: str) -> list[ContentBlock]:
    soup = BeautifulSoup(html, "lxml")
    for tag_name in _STRIP_TAGS:
        for tag in soup.find_all(tag_name):
            tag.decompose()

    blocks: list[ContentBlock] = []
    counter = 0
    for el in soup.find_all(_HTML_TEXT_TAGS):
        text = el.get_text(separator=" ", strip=True)
        if not text or len(text) < 2:
            continue
        counter += 1
        blocks.append(
            ContentBlock(
                block_id=next_block_id("html", counter),
                source_file=source_file,
                source_format=SourceFormat.HTML,
                page=None,
                locator=f"{el.name}_{counter}",
                text=text,
                bbox=None,
                confidence=1.0,
                extraction_method="html_text_element",
            )
        )
    return blocks
