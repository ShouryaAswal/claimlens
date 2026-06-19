"""
Sprint 1: OCR Bounding Box Agent.

Turns a claim document (PDF or image) into a flat list of OCRBlock
objects: page, text, bbox, confidence, source_file. This is the ONLY
agent in the whole pipeline allowed to assign coordinates -- every
later agent must reference an existing block_id rather than invent one.

Two paths, matching the design-doc's "Hybrid OCR" idea:
  1. Digital PDF path (PRIMARY for this MVP): PyMuPDF reads the text
     layer directly. Fast, free, perfectly accurate coordinates,
     confidence = 1.0 since there's no recognition uncertainty.
  2. Scanned image / image-only PDF path (PaddleOCR): stubbed out for
     now (see run_paddle_ocr) and wired up once the digital path is
     proven -- this keeps Sprint 1 unblocked without a heavy model
     download today.
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
                    )
                )
    return blocks


def run_paddle_ocr(file_path: str) -> List[OCRBlock]:
    """Scanned image / image-only PDF path. Wired up in a follow-up
    sprint once the digital-PDF path is validated end-to-end -- the
    architecture (see docstring above) is identical, only the source
    of bbox + confidence changes (PaddleOCR detection instead of the
    PDF text layer).
    """
    raise NotImplementedError(
        "PaddleOCR path not yet implemented. This MVP currently supports "
        "digital (text-layer) PDFs via run_pymupdf_ocr(). Add this once "
        "Sprint 1's digital path is validated."
    )


def is_digital_pdf(file_path: str) -> bool:
    """Heuristic: a PDF is 'digital' if at least one page has an
    extractable text layer. Image-only / scanned PDFs return empty
    text and should fall back to run_paddle_ocr."""
    with fitz.open(file_path) as doc:
        for page in doc:
            if page.get_text("text").strip():
                return True
    return False


def run_ocr(file_path: str) -> List[OCRBlock]:
    """Entry point used by the rest of the pipeline. Routes to the
    digital-PDF path or the (future) PaddleOCR path."""
    if file_path.lower().endswith(".pdf") and is_digital_pdf(file_path):
        return run_pymupdf_ocr(file_path)
    return run_paddle_ocr(file_path)


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
