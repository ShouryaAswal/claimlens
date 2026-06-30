"""
tests/test_triage_agent.py
--------------------------------
Sprint 4: triage agent. The most important test here,
test_high_risk_required_field_forces_review_even_with_otherwise_low_score,
proves the rule carried over from Sprint 3: a single high-risk REQUIRED
field forces human review regardless of how low the rest of the composite
score is. A good score cannot buy back an STP route past a wrong dollar
amount.
"""

from __future__ import annotations

from agents.triage_agent import (
    HIGH_VALUE_THRESHOLD_BY_LOB,
    PRIMARY_AMOUNT_FIELD_BY_LOB,
    apply_triage_to_claim,
    compute_triage,
)
from core.schema_loader import load_lob_schema
from core.schemas import (
    ClaimState,
    ExtractedField,
    FieldVerification,
    LOB,
    MatchMethod,
    RiskLevel,
    TriageTier,
)


def _make_claim(lob: LOB = LOB.AUTO) -> ClaimState:
    schema = load_lob_schema(lob)
    return ClaimState(claim_id="CLM-TEST", lob=lob, lob_schema=schema)


def _verification(risk: RiskLevel, reasons=None) -> FieldVerification:
    return FieldVerification(
        field_id="x", match_method=MatchMethod.EXACT_NUMERIC, match_score=0.0,
        ocr_confidence_avg=0.9, llm_confidence=0.9, composite_confidence=0.0,
        risk_level=risk, requires_human_review=(risk != RiskLevel.OK),
        reasons=reasons or [],
    )


def test_clean_claim_is_stp_candidate():
    claim = _make_claim()
    verdict = compute_triage(claim)
    assert verdict.tier == TriageTier.STP_CANDIDATE
    assert verdict.score == 0
    assert verdict.forced_review is False


def test_missing_mandatory_doc_adds_score():
    claim = _make_claim()
    claim.missing_mandatory_docs = ["police_report"]
    verdict = compute_triage(claim)
    assert verdict.score == 20
    assert any("police_report" in r for r in verdict.reasons)


def test_multiple_missing_docs_accumulate():
    claim = _make_claim()
    claim.missing_mandatory_docs = ["police_report", "photos", "policy_declaration"]
    verdict = compute_triage(claim)
    assert verdict.score == 60
    assert verdict.tier == TriageTier.NEEDS_REVIEW  # at the boundary, not over


def test_needs_review_field_on_optional_field_scores_less_than_required():
    claim_required = _make_claim()
    claim_required.field_verifications["repair_estimate_amount"] = _verification(RiskLevel.NEEDS_REVIEW)
    verdict_required = compute_triage(claim_required)

    claim_optional = _make_claim()
    claim_optional.field_verifications["additional_remarks"] = _verification(RiskLevel.NEEDS_REVIEW)
    verdict_optional = compute_triage(claim_optional)

    assert verdict_required.score > verdict_optional.score


def test_high_risk_required_field_forces_review_even_with_otherwise_low_score():
    claim = _make_claim()
    claim.field_verifications["repair_estimate_amount"] = _verification(
        RiskLevel.HIGH_RISK, reasons=["NO EXACT MATCH for 4259.00"]
    )
    verdict = compute_triage(claim)
    assert verdict.forced_review is True
    assert verdict.tier != TriageTier.STP_CANDIDATE
    assert "repair_estimate_amount" in verdict.high_risk_field_ids


def test_high_risk_optional_field_does_not_force_review():
    claim = _make_claim()
    claim.field_verifications["additional_remarks"] = _verification(RiskLevel.HIGH_RISK)
    verdict = compute_triage(claim)
    assert verdict.forced_review is False


def test_forced_review_overrides_what_would_otherwise_be_stp():
    claim = _make_claim()
    claim.field_verifications["repair_estimate_amount"] = _verification(RiskLevel.HIGH_RISK)
    verdict = compute_triage(claim)
    assert verdict.tier != TriageTier.STP_CANDIDATE
    assert verdict.forced_review is True


def test_high_value_auto_claim_adds_escalation_points():
    claim = _make_claim(LOB.AUTO)
    threshold = HIGH_VALUE_THRESHOLD_BY_LOB[LOB.AUTO]
    field_id = PRIMARY_AMOUNT_FIELD_BY_LOB[LOB.AUTO]
    claim.extracted_fields[field_id] = ExtractedField(
        field_id=field_id, value=str(threshold + 1), status="found", confidence=0.9,
    )
    verdict = compute_triage(claim)
    assert verdict.score >= 15
    assert any("high-value" in r for r in verdict.reasons)


def test_below_threshold_claim_amount_does_not_escalate():
    claim = _make_claim(LOB.AUTO)
    field_id = PRIMARY_AMOUNT_FIELD_BY_LOB[LOB.AUTO]
    claim.extracted_fields[field_id] = ExtractedField(
        field_id=field_id, value="500.00", status="found", confidence=0.9,
    )
    verdict = compute_triage(claim)
    assert verdict.score == 0


def test_high_value_threshold_differs_by_lob():
    claim_health = _make_claim(LOB.HEALTH)
    field_id = PRIMARY_AMOUNT_FIELD_BY_LOB[LOB.HEALTH]
    threshold = HIGH_VALUE_THRESHOLD_BY_LOB[LOB.HEALTH]
    claim_health.extracted_fields[field_id] = ExtractedField(
        field_id=field_id, value=str(threshold + 1), status="found", confidence=0.9,
    )
    verdict = compute_triage(claim_health)
    assert verdict.score >= 15


def test_missing_amount_field_does_not_crash():
    claim = _make_claim()
    verdict = compute_triage(claim)
    assert verdict.score == 0


def test_apply_triage_writes_back_to_claim_state():
    claim = _make_claim()
    assert claim.triage is None
    verdict = apply_triage_to_claim(claim)
    assert claim.triage is verdict
    assert claim.triage.tier == TriageTier.STP_CANDIDATE


def test_default_reason_given_when_nothing_flagged():
    claim = _make_claim()
    verdict = compute_triage(claim)
    assert len(verdict.reasons) == 1
    assert "no issues" in verdict.reasons[0].lower()
