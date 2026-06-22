"""
tests/test_gate_check.py
----------------------------
Sprint 2 exit criterion: "Gate Check correctly flags a missing mandatory
doc on a deliberately incomplete sample."
"""

from __future__ import annotations

import pytest

from agents.doc_type_tagger_agent import tag_all_documents
from agents.gate_check import apply_gate_check_to_claim, run_gate_check
from core.schema_loader import load_lob_schema
from core.schemas import ClaimState, LOB


def _make_document(tmp_path, name: str, text: str, fmt_suffix: str = ".pdf"):
    import fitz
    path = tmp_path / name
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 50), text, fontsize=11)
    doc.save(str(path))
    doc.close()
    from agents.ingestion.dispatcher import ingest
    return ingest(str(path))


def test_complete_auto_claim_passes_gate_check(tmp_path):
    schema = load_lob_schema(LOB.AUTO)
    docs = [
        _make_document(tmp_path, "d1.pdf", "Police Department report number SPD-44210, officer on scene."),
        _make_document(tmp_path, "d2.pdf", "Repair Estimate total estimate $4,250.00 from City Body Shop."),
        _make_document(tmp_path, "d3.pdf", "Policy Declaration named insured policy period 2026."),
    ]
    tag_all_documents(docs)
    # photos requirement satisfied by a low-text image, simulate directly:
    from core.schemas import ContentBlock, DocumentRecord, SourceFormat
    photo_doc = DocumentRecord(
        doc_id="photo1", source_file="damage.png", source_format=SourceFormat.IMAGE,
        page_count=1, blocks=[], doc_type="photos",
    )
    docs.append(photo_doc)

    result = run_gate_check(docs, schema)
    assert result.is_complete is True
    assert result.missing_doc_types == []


def test_deliberately_incomplete_auto_claim_flags_missing_docs(tmp_path):
    """The exact Sprint 2 exit criterion: missing a mandatory doc must be
    caught, not silently passed."""
    schema = load_lob_schema(LOB.AUTO)
    docs = [
        _make_document(tmp_path, "d1.pdf", "Police Department report number SPD-44210, officer on scene."),
        # Deliberately missing: repair_estimate, photos, policy_declaration
    ]
    tag_all_documents(docs)

    result = run_gate_check(docs, schema)
    assert result.is_complete is False
    assert "repair_estimate" in result.missing_doc_types
    assert "photos" in result.missing_doc_types
    assert "policy_declaration" in result.missing_doc_types
    assert "police_report" not in result.missing_doc_types  # this one WAS present


def test_unmatched_documents_listed_separately_from_missing_types(tmp_path):
    schema = load_lob_schema(LOB.AUTO)
    docs = [
        _make_document(tmp_path, "mystery.pdf", "The quick brown fox jumps over the lazy dog."),
    ]
    tag_all_documents(docs)
    result = run_gate_check(docs, schema)
    assert len(result.unmatched_documents) == 1
    assert "mystery.pdf" in result.unmatched_documents[0]
    # an unmatched doc doesn't satisfy ANY mandatory type
    assert set(result.missing_doc_types) == set(schema.mandatory_doc_types)


def test_apply_gate_check_to_claim_writes_back_to_claim_state(tmp_path):
    schema = load_lob_schema(LOB.AUTO)
    docs = [_make_document(tmp_path, "d1.pdf", "Police report number SPD-1, police department.")]
    tag_all_documents(docs)

    claim = ClaimState(claim_id="CLM-TEST-001", lob=LOB.AUTO, lob_schema=schema, documents=docs)
    assert claim.missing_mandatory_docs == []  # not yet computed

    result = apply_gate_check_to_claim(claim)
    assert claim.missing_mandatory_docs == result.missing_doc_types
    assert "repair_estimate" in claim.missing_mandatory_docs


def test_apply_gate_check_without_resolved_schema_raises():
    claim = ClaimState(claim_id="CLM-TEST-002", lob=LOB.AUTO, lob_schema=None)
    with pytest.raises(ValueError):
        apply_gate_check_to_claim(claim)


def test_property_claim_gate_check_uses_property_mandatory_docs(tmp_path):
    schema = load_lob_schema(LOB.PROPERTY)
    docs = [
        _make_document(tmp_path, "d1.pdf", "Inspection Report inspected by adjuster, site visit notes."),
    ]
    tag_all_documents(docs)
    result = run_gate_check(docs, schema)
    assert "inventory_list" in result.missing_doc_types
    assert "receipts" in result.missing_doc_types
    assert "inspection_report" not in result.missing_doc_types
