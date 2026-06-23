"""
tests/test_merge_agent.py
-------------------------------
Sprint 3: multi-document/multi-citation conflict resolution. The critical
property under test: disagreement on a critical field type (number/date/
code) is NEVER silently resolved by majority vote or confidence -- it must
become an explicit "conflicting" status routed to a human. Silently picking
a winner among two different claim amounts is exactly the kind of error
this sprint exists to prevent.
"""

from __future__ import annotations

from agents.merge_agent import (
    FieldCandidate,
    detect_citation_conflicts,
    merge_candidates,
)
from core.schema_loader import load_lob_schema
from core.schemas import ClaimState, ContentBlock, DocumentRecord, ExtractedField, FieldDefinition, LOB, SourceFormat


_NUMERIC_FIELD = FieldDefinition(field_id="repair_estimate_amount", label="Repair Estimate", field_type="number")
_DATE_FIELD = FieldDefinition(field_id="date_of_loss", label="Date of Loss", field_type="date")
_CODE_FIELD = FieldDefinition(field_id="vehicle_vin", label="VIN", field_type="code")
_TEXT_FIELD = FieldDefinition(field_id="driver_name", label="Driver Name", field_type="text")


# ---------------------------------------------------------------------------
# merge_candidates(): the critical safety property
# ---------------------------------------------------------------------------

def test_agreeing_numeric_candidates_merge_safely():
    candidates = [
        FieldCandidate(value="4250.00", confidence=0.9, evidence_block_ids=["b1"]),
        FieldCandidate(value="$4,250.00", confidence=0.85, evidence_block_ids=["b2"]),
    ]
    result = merge_candidates(candidates, _NUMERIC_FIELD, claim=None)
    assert result.status == "found"
    assert "4250.00" in result.value
    assert set(result.evidence_block_ids) == {"b1", "b2"}


def test_disagreeing_numeric_candidates_never_silently_resolved():
    """THE test. Two different claim amounts must never produce a
    confident 'found' status by majority/confidence vote."""
    candidates = [
        FieldCandidate(value="4250.00", confidence=0.95, evidence_block_ids=["b1"]),
        FieldCandidate(value="4500.00", confidence=0.80, evidence_block_ids=["b2"]),
    ]
    result = merge_candidates(candidates, _NUMERIC_FIELD, claim=None)
    assert result.status == "conflicting"
    assert result.value is None
    assert result.confidence == 0.0
    assert "4250.00" in result.reason and "4500.00" in result.reason


def test_disagreeing_numeric_candidates_not_resolved_even_with_lopsided_confidence():
    """Even if one candidate is reported at 0.99 confidence and the other
    at 0.10, disagreement on a critical field still doesn't get silently
    resolved by trusting the more confident one -- confidence is
    self-reported by an LLM and is exactly the kind of signal that
    shouldn't be allowed to paper over a real numeric discrepancy."""
    candidates = [
        FieldCandidate(value="4250.00", confidence=0.99, evidence_block_ids=["b1"]),
        FieldCandidate(value="4500.00", confidence=0.10, evidence_block_ids=["b2"]),
    ]
    result = merge_candidates(candidates, _NUMERIC_FIELD, claim=None)
    assert result.status == "conflicting"


def test_disagreeing_date_candidates_never_silently_resolved():
    candidates = [
        FieldCandidate(value="2026-06-12", confidence=0.9, evidence_block_ids=["b1"]),
        FieldCandidate(value="2026-06-21", confidence=0.9, evidence_block_ids=["b2"]),
    ]
    result = merge_candidates(candidates, _DATE_FIELD, claim=None)
    assert result.status == "conflicting"


def test_disagreeing_code_candidates_never_silently_resolved():
    candidates = [
        FieldCandidate(value="1HGCM82633A004352", confidence=0.9, evidence_block_ids=["b1"]),
        FieldCandidate(value="1HGCM82633A004353", confidence=0.9, evidence_block_ids=["b2"]),
    ]
    result = merge_candidates(candidates, _CODE_FIELD, claim=None)
    assert result.status == "conflicting"


def test_three_way_split_on_critical_field_is_conflicting_not_majority():
    """No majority exists among 3 different values -- must not arbitrarily
    pick one."""
    candidates = [
        FieldCandidate(value="100.00", confidence=0.5, evidence_block_ids=["b1"]),
        FieldCandidate(value="200.00", confidence=0.5, evidence_block_ids=["b2"]),
        FieldCandidate(value="300.00", confidence=0.9, evidence_block_ids=["b3"]),
    ]
    result = merge_candidates(candidates, _NUMERIC_FIELD, claim=None)
    assert result.status == "conflicting"


# ---------------------------------------------------------------------------
# merge_candidates(): text/boolean fields -- lower stakes, voting IS okay
# ---------------------------------------------------------------------------

def test_text_field_majority_value_wins():
    candidates = [
        FieldCandidate(value="Priya Nair", confidence=0.9, evidence_block_ids=["b1"]),
        FieldCandidate(value="Priya Nair", confidence=0.85, evidence_block_ids=["b2"]),
        FieldCandidate(value="Prya Nair", confidence=0.5, evidence_block_ids=["b3"]),
    ]
    result = merge_candidates(candidates, _TEXT_FIELD, claim=None)
    assert result.value == "Priya Nair"
    assert result.status == "found"


def test_text_field_tie_broken_by_confidence():
    candidates = [
        FieldCandidate(value="Priya Nair", confidence=0.95, evidence_block_ids=["b1"]),
        FieldCandidate(value="P. Nair", confidence=0.4, evidence_block_ids=["b2"]),
    ]
    result = merge_candidates(candidates, _TEXT_FIELD, claim=None)
    assert result.value == "Priya Nair"  # 1-1 tie, higher confidence wins
    assert result.status == "low_confidence"  # not repeated, so flagged as such


def test_no_candidates_with_values_returns_missing():
    candidates = [FieldCandidate(value=None, confidence=0.0, evidence_block_ids=[])]
    result = merge_candidates(candidates, _NUMERIC_FIELD, claim=None)
    assert result.status == "missing"


def test_single_candidate_passes_through():
    candidates = [FieldCandidate(value="4250.00", confidence=0.9, evidence_block_ids=["b1"])]
    result = merge_candidates(candidates, _NUMERIC_FIELD, claim=None)
    assert result.status == "found"
    assert result.value == "4250.00"


# ---------------------------------------------------------------------------
# detect_citation_conflicts(): same-field, multiple citations disagree
# ---------------------------------------------------------------------------

def _make_claim_with_blocks(texts: dict[str, str]) -> ClaimState:
    schema = load_lob_schema(LOB.AUTO)
    blocks = [
        ContentBlock(block_id=bid, source_file="d.pdf", source_format=SourceFormat.PDF,
                     page=1, locator="l", text=text, bbox=(1, 1, 2, 2),
                     confidence=0.9, extraction_method="pymupdf_text")
        for bid, text in texts.items()
    ]
    doc = DocumentRecord(doc_id="d1", source_file="d.pdf", source_format=SourceFormat.PDF,
                          page_count=1, blocks=blocks)
    return ClaimState(claim_id="CLM-TEST", lob=LOB.AUTO, lob_schema=schema, documents=[doc])


def test_citation_conflict_detected_when_cited_blocks_disagree():
    claim = _make_claim_with_blocks({
        "b1": "Repair Estimate: $4,500.00",
        "b2": "Repair Estimate: $4,900.00",
    })
    field = ExtractedField(field_id="repair_estimate_amount", value="4250.00", status="found",
                            evidence_block_ids=["b1", "b2"])
    report = detect_citation_conflicts(field, _NUMERIC_FIELD, claim)
    assert report.has_conflict is True


def test_no_conflict_when_cited_blocks_agree():
    claim = _make_claim_with_blocks({
        "b1": "Repair Estimate: $4,250.00 per the body shop quote.",
        "b2": "Total Estimate: $4,250.00 confirmed by adjuster.",
    })
    field = ExtractedField(field_id="repair_estimate_amount", value="4250.00", status="found",
                            evidence_block_ids=["b1", "b2"])
    report = detect_citation_conflicts(field, _NUMERIC_FIELD, claim)
    assert report.has_conflict is False


def test_single_citation_cannot_conflict_with_itself():
    claim = _make_claim_with_blocks({"b1": "Repair Estimate: $4,250.00"})
    field = ExtractedField(field_id="repair_estimate_amount", value="4250.00", status="found",
                            evidence_block_ids=["b1"])
    report = detect_citation_conflicts(field, _NUMERIC_FIELD, claim)
    assert report.has_conflict is False
