"""
agents/ingestion/pdf_parser.py
---------------------------------
PDF ingestion. Handles both:
  - "Digital" PDFs (text was typed/generated, e.g. an exported form) -- text
    and bounding boxes come straight from PyMuPDF's layout analysis, which is
    exact, free, and instant (no model inference).
  - "Scanned" PDFs (the page is effectively a photograph with no real text
    layer, e.g. a faxed or phone-photographed police report) -- the page is
    rasterized to an image and routed through Tesseract OCR.

A single PDF can mix both kinds of pages (common in real claim packets: a
digitally-generated estimate followed by a scanned, signed police report) --
each page is judged independently.
"""

from __future__ import annotations

import logging

import fitz  # PyMuPDF
from PIL import Image

from core.config import (
    LONG_DOCUMENT_PAGE_WARNING_THRESHOLD,
    PDF_OCR_RENDER_DPI,
    PDF_PAGE_OCR_FALLBACK_CHAR_THRESHOLD,
)
from core.schemas import ContentBlock, SourceFormat
from agents.ingestion import ocr_utils
from agents.ingestion.base import next_block_id

logger = logging.getLogger(__name__)


def parse_pdf(
    path: str,
    source_file: str | None = None,
    ocr_lang: str = "eng",
) -> tuple[list[ContentBlock], int, list[str]]:
    """Returns (blocks, page_count, warnings)."""
    source_file = source_file or str(path)
    warnings: list[str] = []
    blocks: list[ContentBlock] = []
    block_counter = 0

    doc = fitz.open(path)
    page_count = doc.page_count

    if page_count > LONG_DOCUMENT_PAGE_WARNING_THRESHOLD:
        warnings.append(
            f"Long document: {page_count} pages "
            f"(threshold {LONG_DOCUMENT_PAGE_WARNING_THRESHOLD}). "
            f"Processing page-by-page; this is expected to take longer for "
            f"scanned pages than for digital ones."
        )

    for page_index in range(page_count):
        page = doc[page_index]
        page_blocks, used_ocr = _parse_page(
            page, page_index, source_file, block_counter, ocr_lang
        )
        block_counter += len(page_blocks)
        blocks.extend(page_blocks)
        if used_ocr:
            logger.info(
                "page %d/%d of %s: digital text layer below threshold, used OCR fallback",
                page_index + 1, page_count, source_file,
            )

    doc.close()

    if not blocks:
        warnings.append(
            "No extractable text found on any page (digital or OCR). "
            "The PDF may be blank, corrupted, or contain only non-text imagery."
        )

    return blocks, page_count, warnings


def _parse_page(
    page: fitz.Page,
    page_index: int,
    source_file: str,
    block_counter_start: int,
    ocr_lang: str,
) -> tuple[list[ContentBlock], bool]:
    page_number = page_index + 1
    blocks: list[ContentBlock] = []
    counter = block_counter_start

    page_dict = page.get_text("dict")
    text_blocks = [b for b in page_dict.get("blocks", []) if b.get("type") == 0]

    total_chars = sum(
        len(span["text"])
        for b in text_blocks
        for line in b.get("lines", [])
        for span in line.get("spans", [])
    )

    if total_chars >= PDF_PAGE_OCR_FALLBACK_CHAR_THRESHOLD:
        # --- Digital text path -------------------------------------------
        for b in text_blocks:
            text = "".join(
                span["text"] for line in b.get("lines", []) for span in line.get("spans", [])
            ).strip()
            if not text:
                continue
            counter += 1
            blocks.append(
                ContentBlock(
                    block_id=next_block_id(f"p{page_number}", counter),
                    source_file=source_file,
                    source_format=SourceFormat.PDF,
                    page=page_number,
                    locator=f"page_{page_number}_block_{counter}",
                    text=text,
                    bbox=tuple(b["bbox"]),
                    confidence=1.0,
                    extraction_method="pymupdf_text",
                )
            )
        return blocks, False

    # --- OCR fallback path (scanned / image-only page) -------------------
    zoom = PDF_OCR_RENDER_DPI / 72.0  # PDF default is 72 DPI
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
    image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)

    lines = ocr_utils.ocr_image_to_lines(image, lang=ocr_lang)
    for line in lines:
        counter += 1
        x0, y0, x1, y1 = line["bbox"]
        # Map pixel coords (at render zoom) back to PDF point space.
        pdf_bbox = (x0 / zoom, y0 / zoom, x1 / zoom, y1 / zoom)
        blocks.append(
            ContentBlock(
                block_id=next_block_id(f"p{page_number}", counter),
                source_file=source_file,
                source_format=SourceFormat.PDF,
                page=page_number,
                locator=f"page_{page_number}_ocr_line_{counter}",
                text=line["text"],
                bbox=pdf_bbox,
                confidence=line["confidence"],
                extraction_method="pytesseract_ocr",
            )
        )
    return blocks, True
