"""
Sprint 1: OCR Bounding Box Agent (digital-PDF path).

Turns a digital (text-layer) claim PDF into a flat list of OCRBlock
objects: page, text, bbox, confidence, source_file. This is the
original Sprint 1 scope and still works standalone for quick smoke
tests against digital PDFs.

NOTE: scanned PDFs, standalone images, .docx, and hyperlinks are now
handled by agents/ingestion_agent.py, which imports run_pymupdf_ocr()
and is_digital_pdf() from this module for the digital-PDF case and
adds Tesseract/python-docx/requests paths for everything else. Use
ingestion_agent.ingest() as the actual pipeline entry point; this
module is kept focused and importable on its own.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import List

import fitz  # PyMuPDF

from core.schemas import OCRBlock

MIN_BLOCK_TEXT_LEN = 1  # drop fully-empty blocks


def run_pymupdf_ocr(file_path: str) -> List[OCRBlock]:
    """Extract OCRBlocks from a digital (text-layer) PDF using PyMuPDF.

    Uses page.get_text("blocks") which returns (x0, y0, x1, y1, text,
    block_no, block_type) tuples -- exactly the page-coordinate
    granularity the Provenance Agent (Sprint 3) will need later.
    """
    source_file = os.path.basename(file_path)
    blocks: List[OCRBlock] = []

    with fitz.open(file_path) as doc:
        for page_index, page in enumerate(doc, start=1):
            raw_blocks = page.get_text("blocks")
            block_counter = 0
            for b in raw_blocks:
                x0, y0, x1, y1, text = b[0], b[1], b[2], b[3], b[4]
                text = text.strip()
                if len(text) < MIN_BLOCK_TEXT_LEN:
                    continue
                block_counter += 1
                block_id = f"p{page_index}_b{block_counter:03d}"
                blocks.append(
                    OCRBlock(
                        block_id=block_id,
                        page=page_index,
                        text=text,
                        bbox=(round(x0, 1), round(y0, 1), round(x1, 1), round(y1, 1)),
                        # Digital text layer -> no recognition uncertainty.
                        ocr_confidence=1.0,
                        source_file=source_file,
                        source_type="digital_pdf",
                    )
                )
    return blocks


def is_digital_pdf(file_path: str) -> bool:
    """Heuristic: a PDF is 'digital' if at least one page has an
    extractable text layer. Image-only / scanned PDFs return empty
    text and route through agents.ingestion_agent's Tesseract path."""
    with fitz.open(file_path) as doc:
        for page in doc:
            if page.get_text("text").strip():
                return True
    return False


def run_ocr(file_path: str) -> List[OCRBlock]:
    """Digital-PDF-only entry point, kept for Sprint-1-era smoke tests.
    For real pipeline use (handles scanned PDFs, images, docx, URLs
    too), use agents.ingestion_agent.ingest() instead."""
    if not file_path.lower().endswith(".pdf"):
        raise ValueError(
            f"{file_path}: run_ocr() only handles PDFs. Use "
            "agents.ingestion_agent.ingest() for images/docx/scanned PDFs/URLs."
        )
    if not is_digital_pdf(file_path):
        raise ValueError(
            f"{file_path}: no extractable text layer (this is a scanned PDF). "
            "Use agents.ingestion_agent.ingest() instead, which routes this "
            "case through Tesseract."
        )
    return run_pymupdf_ocr(file_path)


def save_blocks(blocks: List[OCRBlock], out_path: str) -> None:
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump([b.model_dump() for b in blocks], f, indent=2)


if __name__ == "__main__":
    # Quick manual run across all 3 sample claim types.
    samples = [
        "samples/auto_claim_01.pdf",
        "samples/property_claim_01.pdf",
        "samples/health_claim_01.pdf",
    ]
    for sample_path in samples:
        blocks = run_ocr(sample_path)
        out_name = Path(sample_path).stem + "_ocr_blocks.json"
        save_blocks(blocks, f"outputs/{out_name}")
        print(f"{sample_path}: {len(blocks)} blocks -> outputs/{out_name}")
        for b in blocks[:3]:
            print(f"    {b.block_id} (page {b.page}): {b.text!r} bbox={b.bbox}")
