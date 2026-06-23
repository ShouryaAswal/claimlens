"""
tests/test_confidence_rating.py
-------------------------------------
Tests the full rating pipeline: deterministic match + OCR confidence + LLM
confidence + optional LLM second opinion -> one FieldVerification.

The single most important test in this file is
`test_llm_agreement_cannot_override_critical_field_failure` -- it proves
that even if an LLM second opinion is fooled/wrong and claims a numerically
incorrect value is "supported", the deterministic exact-match failure on a
critical field still wins. This is the literal code-level guarantee behind
"even a single digit error must be fatal" -- it must hold regardless of
what any LLM says, not just regardless of fuzzy string similarity.
"""

from __future__ import annotations

from agents.confidence_rating import (
    LOW_OCR_CONFIDENCE_THRESHOLD,
    rate_all_fields,
    rate_field,
)
from core.llm_client import LLMClient
from core.schema_loader import load_lob_schema
from core.schemas import (
    ClaimState,
    ContentBlock,
    DocumentRecord,
    ExtractedField,
    LOB,
    RiskLevel,
    SourceFormat,
)


def _make_claim(block_text: str, block_confidence: float = 0.95, block_id: str = "p1_b001") -> ClaimState:
    schema = load_lob_schema(LOB.AUTO)
    block = ContentBlock(
        block_id=block_id, source_file="d.pdf", source_format=SourceFormat.PDF,
        page=1, locator="l", text=block_text, bbox=(1, 1, 2, 2),
        confidence=block_confidence, extraction_method="pymupdf_text",
    )
    doc = DocumentRecord(doc_id="d1", source_file="d.pdf", source_format=SourceFormat.PDF,
                          page_count=1, blocks=[block])
    return ClaimState(claim_id="CLM-TEST", lob=LOB.AUTO, lob_schema=schema, documents=[doc])


def _numeric_field_def(claim):
    return claim.lob_schema.get_section("financials").fields[0]  # repair_estimate_amount


def _fake_llm(response_text: str) -> LLMClient:
    return LLMClient(provider="fake", model="fake", complete=lambda s, u: response_text)


# ---------------------------------------------------------------------------
# Deterministic-only rating (no LLM client)
# ---------------------------------------------------------------------------

def test_correct_critical_value_with_high_ocr_confidence_rates_ok():
    claim = _make_claim("Repair Estimate: $4,250.00", block_confidence=0.95)
    field_def = _numeric_field_def(claim)
    field = ExtractedField(field_id=field_def.field_id, value="4250.00", confidence=0.9,
                            status="found", evidence_block_ids=["p1_b001"])
    result = rate_field(field, field_def, claim)
    assert result.risk_level == RiskLevel.OK
    assert result.requires_human_review is False


def test_wrong_critical_value_always_rates_high_risk_regardless_of_self_reported_confidence():
    """The model claiming 99% confidence in a wrong number must not matter."""
    claim = _make_claim("Repair Estimate: $4,250.00", block_confidence=0.95)
    field_def = _numeric_field_def(claim)
    field = ExtractedField(field_id=field_def.field_id, value="4259.00", confidence=0.99,
                            status="found", evidence_block_ids=["p1_b001"])
    result = rate_field(field, field_def, claim)
    assert result.risk_level == RiskLevel.HIGH_RISK
    assert result.requires_human_review is True
    assert result.composite_confidence == 0.0


def test_correct_critical_value_with_low_ocr_confidence_rates_needs_review():
    """Even an exact match deserves a second look if the underlying OCR
    that produced the evidence text was itself unreliable."""
    claim = _make_claim("Repair Estimate: $4,250.00", block_confidence=0.3)
    field_def = _numeric_field_def(claim)
    field = ExtractedField(field_id=field_def.field_id, value="4250.00", confidence=0.9,
                            status="found", evidence_block_ids=["p1_b001"])
    result = rate_field(field, field_def, claim)
    assert result.risk_level == RiskLevel.NEEDS_REVIEW
    assert result.requires_human_review is True
    assert "OCR confidence" in " ".join(result.reasons)


def test_ocr_confidence_at_exact_threshold_boundary():
    claim = _make_claim("Repair Estimate: $4,250.00", block_confidence=LOW_OCR_CONFIDENCE_THRESHOLD)
    field_def = _numeric_field_def(claim)
    field = ExtractedField(field_id=field_def.field_id, value="4250.00", confidence=0.9,
                            status="found", evidence_block_ids=["p1_b001"])
    result = rate_field(field, field_def, claim)
    assert result.risk_level == RiskLevel.OK  # at-threshold is acceptable, only BELOW flags


def test_missing_required_field_rates_needs_review_not_high_risk():
    """A missing field is a different problem than a WRONG field -- it's
    absent, not actively incorrect. Gate Check / completion stats already
    surface 'missing'; this shouldn't double-alarm as high_risk."""
    claim = _make_claim("Some unrelated text with no estimate at all.")
    field_def = _numeric_field_def(claim)
    assert field_def.required is True
    field = ExtractedField(field_id=field_def.field_id, status="missing", value=None)
    result = rate_field(field, field_def, claim)
    assert result.risk_level == RiskLevel.NEEDS_REVIEW
    assert result.requires_human_review is True


def test_missing_optional_field_rates_ok():
    claim = _make_claim("Some text.")
    field_def = claim.lob_schema.get_section("remarks_overflow").fields[0]  # additional_remarks, optional
    assert field_def.required is False
    field = ExtractedField(field_id=field_def.field_id, status="missing", value=None)
    result = rate_field(field, field_def, claim)
    assert result.risk_level == RiskLevel.OK
    assert result.requires_human_review is False


def test_field_with_value_but_no_evidence_citations_is_high_risk():
    claim = _make_claim("Repair Estimate: $4,250.00")
    field_def = _numeric_field_def(claim)
    field = ExtractedField(field_id=field_def.field_id, value="4250.00", confidence=0.9,
                            status="found", evidence_block_ids=[])
    result = rate_field(field, field_def, claim)
    assert result.risk_level == RiskLevel.HIGH_RISK


def test_text_field_low_composite_confidence_rates_needs_review():
    claim = _make_claim("Driver Name: Someone Else Entirely", block_confidence=0.4)
    field_def = claim.lob_schema.get_section("parties").fields[0]  # driver_name, text type
    field = ExtractedField(field_id=field_def.field_id, value="Priya Nair", confidence=0.5,
                            status="found", evidence_block_ids=["p1_b001"])
    result = rate_field(field, field_def, claim)
    assert result.risk_level == RiskLevel.NEEDS_REVIEW


# ---------------------------------------------------------------------------
# THE critical safety property: LLM agreement cannot override a
# deterministic critical-field exact-match failure.
# ---------------------------------------------------------------------------

def test_llm_agreement_cannot_override_critical_field_failure():
    """Even if the LLM second opinion is fooled and says the wrong number
    IS supported, with high confidence, the field must remain high_risk.
    This is the core guarantee behind 'a single digit error is fatal'."""
    claim = _make_claim("Repair Estimate: $4,250.00", block_confidence=0.95)
    field_def = _numeric_field_def(claim)
    field = ExtractedField(field_id=field_def.field_id, value="4259.00", confidence=0.9,
                            status="found", evidence_block_ids=["p1_b001"])

    # A deliberately "wrong" LLM that incorrectly agrees the bad value is fine.
    fooled_llm = _fake_llm('{"supported": true, "confidence": 0.95, "explanation": "looks consistent"}')

    result = rate_field(field, field_def, claim, llm_client=fooled_llm, force_llm_check=True)
    assert result.risk_level == RiskLevel.HIGH_RISK
    assert result.requires_human_review is True
    assert result.llm_verification is not None
    assert result.llm_verification.supported is True  # the LLM's (wrong) opinion is recorded...
    assert "not overridden" in " ".join(result.reasons)  # ...but explicitly did not win


def test_llm_disagreement_escalates_a_deterministically_ok_text_field():
    """The other direction: the LLM CAN catch something string-matching
    missed and escalate a field that looked fine. 'AM' vs 'PM' differs by
    one character and passes fuzzy string matching easily (0.71 similarity)
    -- but it is a completely different time of day. This is exactly the
    blind spot the LLM second opinion exists to cover."""
    claim = _make_claim("Time of Loss: 5:45 PM", block_confidence=0.95)
    field_def = claim.lob_schema.get_section("loss_details").fields[1]  # time_of_loss, text
    field = ExtractedField(field_id=field_def.field_id, value="5:45 AM", confidence=0.9,
                            status="found", evidence_block_ids=["p1_b001"])

    # Confirm the premise: the deterministic check alone would pass this.
    from agents.evidence_verifier import verify_text
    assert verify_text("5:45 AM", "Time of Loss: 5:45 PM").matched is True

    disagreeing_llm = _fake_llm(
        '{"supported": false, "confidence": 0.9, "explanation": "5:45 AM and 5:45 PM are different times of day"}'
    )
    result = rate_field(field, field_def, claim, llm_client=disagreeing_llm, force_llm_check=True)
    assert result.risk_level == RiskLevel.NEEDS_REVIEW
    assert result.requires_human_review is True
    assert "disagreed" in " ".join(result.reasons)


def test_llm_check_skipped_when_not_requested():
    claim = _make_claim("Repair Estimate: $4,250.00")
    field_def = _numeric_field_def(claim)
    field = ExtractedField(field_id=field_def.field_id, value="4250.00", confidence=0.9,
                            status="found", evidence_block_ids=["p1_b001"])
    llm = _fake_llm('{"supported": false, "confidence": 0.9, "explanation": "should not be called"}')
    # force_llm_check=False (default) and the deterministic result is already OK
    # -> the LLM should not even be consulted.
    result = rate_field(field, field_def, claim, llm_client=llm, force_llm_check=False)
    assert result.llm_verification is None
    assert result.risk_level == RiskLevel.OK


def test_llm_check_failure_does_not_crash_pipeline():
    claim = _make_claim("Repair Estimate: $4,250.00")
    field_def = _numeric_field_def(claim)
    field = ExtractedField(field_id=field_def.field_id, value="9999.00", confidence=0.9,
                            status="found", evidence_block_ids=["p1_b001"])
    broken_llm = LLMClient(provider="fake", model="fake", complete=lambda s, u: "not valid json")
    result = rate_field(field, field_def, claim, llm_client=broken_llm, force_llm_check=True)
    assert result.risk_level == RiskLevel.HIGH_RISK  # deterministic failure still stands
    assert result.llm_verification is not None
    assert result.llm_verification.supported is False


# ---------------------------------------------------------------------------
# rate_all_fields(): full-claim integration
# ---------------------------------------------------------------------------

def test_rate_all_fields_writes_back_to_claim_state():
    claim = _make_claim("Repair Estimate: $4,250.00")
    field_def = _numeric_field_def(claim)
    claim.extracted_fields[field_def.field_id] = ExtractedField(
        field_id=field_def.field_id, value="4250.00", confidence=0.9,
        status="found", evidence_block_ids=["p1_b001"],
    )
    results = rate_all_fields(claim)
    assert claim.field_verifications == results
    assert field_def.field_id in claim.field_verifications


def test_rate_all_fields_without_schema_raises():
    claim = _make_claim("text")
    claim.lob_schema = None
    import pytest
    with pytest.raises(ValueError):
        rate_all_fields(claim)
