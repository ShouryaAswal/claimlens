"""
tests/test_provenance_agent.py
------------------------------------
Sprint 3: "every accepted field traces to a real crop."
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from agents.ingestion.dispatcher import ingest
from agents.provenance_agent import generate_crop, generate_crops_for_claim
from core.schema_loader import load_lob_schema
from core.schemas import ClaimState, ContentBlock, DocumentRecord, ExtractedField, LOB, SourceFormat


def test_crop_generated_from_real_pdf_block(tmp_path):
    record = ingest("samples/auto_claim_01.pdf")
    block = record.blocks[0]
    crop_path = generate_crop(block, tmp_path)

    assert crop_path is not None
    assert crop_path.exists()
    img = Image.open(crop_path)
    assert img.width > 0 and img.height > 0
    # crop should be roughly the bbox size (scaled by render DPI) plus
    # padding, not accidentally the whole page.
    from agents.provenance_agent import PDF_CROP_RENDER_DPI
    zoom = PDF_CROP_RENDER_DPI / 72.0
    expected_width = (block.bbox[2] - block.bbox[0]) * zoom
    assert img.width < expected_width * 1.5


def test_crop_generated_from_real_image_block(tmp_path):
    record = ingest("samples/damage_photo_01.png")
    block = record.blocks[0]
    crop_path = generate_crop(block, tmp_path)
    assert crop_path is not None
    assert crop_path.exists()


def test_crop_returns_none_for_block_without_bbox(tmp_path):
    block = ContentBlock(
        block_id="para_001", source_file="doc.docx", source_format=SourceFormat.DOCX,
        page=None, locator="paragraph_0", text="Some flowing text.",
        bbox=None, confidence=1.0, extraction_method="docx_paragraph",
    )
    assert generate_crop(block, tmp_path) is None


def test_crop_returns_none_for_unsupported_format_with_bbox(tmp_path):
    """PPTX has a real bbox but no renderer wired up -- must degrade
    gracefully (None, logged) rather than crash or fake a crop."""
    block = ContentBlock(
        block_id="slide1_b001", source_file="deck.pptx", source_format=SourceFormat.PPTX,
        page=1, locator="slide_1_shape_0", text="Some slide text.",
        bbox=(10.0, 10.0, 100.0, 30.0), confidence=1.0, extraction_method="pptx_shape_text",
    )
    assert generate_crop(block, tmp_path) is None


def test_crop_returns_none_for_missing_source_file(tmp_path):
    block = ContentBlock(
        block_id="p1_b001", source_file="/nonexistent/path/doc.pdf", source_format=SourceFormat.PDF,
        page=1, locator="page_1_block_1", text="text",
        bbox=(10.0, 10.0, 100.0, 30.0), confidence=1.0, extraction_method="pymupdf_text",
    )
    assert generate_crop(block, tmp_path) is None  # logged, not raised


def test_generate_crops_for_claim_only_crops_cited_blocks(tmp_path):
    record = ingest("samples/auto_claim_01.pdf")
    schema = load_lob_schema(LOB.AUTO)
    claim = ClaimState(claim_id="CLM-TEST", lob=LOB.AUTO, lob_schema=schema, documents=[record])

    cited_block_id = record.blocks[0].block_id
    claim.extracted_fields["policy_number"] = ExtractedField(
        field_id="policy_number", value="X", status="found",
        evidence_block_ids=[cited_block_id],
    )

    crop_paths = generate_crops_for_claim(claim, tmp_path)
    assert cited_block_id in crop_paths
    # only ONE block was cited -- only one crop should have been generated,
    # not one per block in the whole document.
    assert len(crop_paths) == 1


def test_generate_crops_for_claim_writes_back_to_field_verifications(tmp_path):
    from agents.confidence_rating import rate_all_fields

    record = ingest("samples/auto_claim_01.pdf")
    schema = load_lob_schema(LOB.AUTO)
    claim = ClaimState(claim_id="CLM-TEST", lob=LOB.AUTO, lob_schema=schema, documents=[record])

    cited_block_id = record.blocks[0].block_id  # "AUTOMOBILE LOSS NOTICE" text
    claim.extracted_fields["policy_number"] = ExtractedField(
        field_id="policy_number", value="AUTOMOBILE LOSS NOTICE", status="found",
        confidence=0.9, evidence_block_ids=[cited_block_id],
    )
    rate_all_fields(claim)
    generate_crops_for_claim(claim, tmp_path)

    verification = claim.field_verifications["policy_number"]
    assert len(verification.crop_paths) == 1
    assert Path(verification.crop_paths[0]).exists()
