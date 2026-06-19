"""
Sprint 1 tests for the OCR Bounding Box Agent.

Covers the exit criteria from the sprint plan:
  - At least one Auto, Property, and Health sample emits OCR blocks.
  - Each block has source file, page, text, and bbox.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from agents.ocr_agent import run_ocr
from core.schemas import OCRBlock

SAMPLES = {
    "auto": "samples/auto_claim_01.pdf",
    "property": "samples/property_claim_01.pdf",
    "health": "samples/health_claim_01.pdf",
}


@pytest.mark.parametrize("claim_type,path", SAMPLES.items())
def test_sample_emits_blocks(claim_type, path):
    blocks = run_ocr(path)
    assert len(blocks) > 0, f"{claim_type} sample produced zero OCR blocks"


@pytest.mark.parametrize("claim_type,path", SAMPLES.items())
def test_blocks_validate_against_schema(claim_type, path):
    blocks = run_ocr(path)
    for b in blocks:
        # Will raise if any block violates the Pydantic schema.
        OCRBlock.model_validate(b.model_dump())
        assert b.source_file
        assert b.page >= 1
        assert b.text.strip() != ""
        x1, y1, x2, y2 = b.bbox
        assert x2 >= x1 and y2 >= y1


def test_block_ids_are_unique_per_claim():
    blocks = run_ocr(SAMPLES["auto"])
    ids = [b.block_id for b in blocks]
    assert len(ids) == len(set(ids)), "Duplicate block_id detected"


def test_multi_page_documents_cover_all_pages():
    # Our synthetic samples are 2 pages each.
    blocks = run_ocr(SAMPLES["property"])
    pages_seen = {b.page for b in blocks}
    assert pages_seen == {1, 2}
