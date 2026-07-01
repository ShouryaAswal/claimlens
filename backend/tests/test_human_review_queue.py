"""
tests/test_human_review_queue.py
--------------------------------------
Sets up and verifies the human-in-the-loop basis: a flat, sorted,
self-contained queue a future reviewer UI reads directly.
"""

from __future__ import annotations

from agents.human_review_queue import build_review_queue, summarize_review_queue
from core.schema_loader import load_lob_schema
from core.schemas import (
    ClaimState,
    ExtractedField,
    FieldVerification,
    LOB,
    MatchMethod,
    RiskLevel,
)


def _make_claim() -> ClaimState:
    schema = load_lob_schema(LOB.AUTO)
    return ClaimState(claim_id="CLM-TEST", lob=LOB.AUTO, lob_schema=schema)


def test_empty_verifications_returns_empty_queue():
    claim = _make_claim()
    assert build_review_queue(claim) == []


def test_only_fields_requiring_review_are_included_by_default():
    claim = _make_claim()
    claim.extracted_fields["policy_number"] = ExtractedField(
        field_id="policy_number", value="AUTO-2026-00981", status="found", evidence_block_ids=["b1"],
    )
    claim.extracted_fields["repair_estimate_amount"] = ExtractedField(
        field_id="repair_estimate_amount", value="9999.00", status="found", evidence_block_ids=["b2"],
    )
    claim.field_verifications["policy_number"] = FieldVerification(
        field_id="policy_number", match_method=MatchMethod.EXACT_CODE, match_score=1.0,
        ocr_confidence_avg=0.95, llm_confidence=0.9, composite_confidence=0.9,
        risk_level=RiskLevel.OK, requires_human_review=False,
    )
    claim.field_verifications["repair_estimate_amount"] = FieldVerification(
        field_id="repair_estimate_amount", match_method=MatchMethod.EXACT_NUMERIC, match_score=0.0,
        ocr_confidence_avg=0.95, llm_confidence=0.9, composite_confidence=0.0,
        risk_level=RiskLevel.HIGH_RISK, requires_human_review=True,
        reasons=["NO EXACT MATCH for 9999.00"],
    )

    queue = build_review_queue(claim)
    assert len(queue) == 1
    assert queue[0].field_id == "repair_estimate_amount"
    assert queue[0].risk_level == RiskLevel.HIGH_RISK


def test_include_ok_returns_everything():
    claim = _make_claim()
    claim.extracted_fields["policy_number"] = ExtractedField(
        field_id="policy_number", value="X", status="found", evidence_block_ids=["b1"],
    )
    claim.field_verifications["policy_number"] = FieldVerification(
        field_id="policy_number", match_method=MatchMethod.EXACT_CODE, match_score=1.0,
        ocr_confidence_avg=0.95, llm_confidence=0.9, composite_confidence=0.9,
        risk_level=RiskLevel.OK, requires_human_review=False,
    )
    assert build_review_queue(claim, include_ok=False) == []
    assert len(build_review_queue(claim, include_ok=True)) == 1


def test_high_risk_sorted_before_needs_review():
    claim = _make_claim()
    for fid, risk in [("a_field", RiskLevel.NEEDS_REVIEW), ("b_field", RiskLevel.HIGH_RISK)]:
        claim.extracted_fields[fid] = ExtractedField(field_id=fid, value="x", status="found", evidence_block_ids=["b"])
        claim.field_verifications[fid] = FieldVerification(
            field_id=fid, match_method=MatchMethod.FUZZY_TEXT, match_score=0.3,
            ocr_confidence_avg=0.9, llm_confidence=0.9, composite_confidence=0.2,
            risk_level=risk, requires_human_review=True,
        )
    queue = build_review_queue(claim)
    assert queue[0].risk_level == RiskLevel.HIGH_RISK
    assert queue[1].risk_level == RiskLevel.NEEDS_REVIEW


def test_field_label_resolved_from_schema_not_just_field_id():
    claim = _make_claim()
    claim.extracted_fields["policy_number"] = ExtractedField(
        field_id="policy_number", value=None, status="missing",
    )
    claim.field_verifications["policy_number"] = FieldVerification(
        field_id="policy_number", match_method=MatchMethod.NO_EVIDENCE, match_score=0.0,
        ocr_confidence_avg=0.0, llm_confidence=0.0, composite_confidence=0.0,
        risk_level=RiskLevel.NEEDS_REVIEW, requires_human_review=True,
    )
    queue = build_review_queue(claim)
    assert queue[0].field_label == "Policy Number"  # the schema's human label, not the raw field_id


def test_summarize_review_queue_counts_correctly():
    claim = _make_claim()
    configs = [
        ("a", RiskLevel.HIGH_RISK, []),
        ("b", RiskLevel.HIGH_RISK, []),
        ("c", RiskLevel.NEEDS_REVIEW, ["/tmp/crop.png"]),
    ]
    for fid, risk, crops in configs:
        claim.extracted_fields[fid] = ExtractedField(field_id=fid, value="x", status="found", evidence_block_ids=["b"])
        claim.field_verifications[fid] = FieldVerification(
            field_id=fid, match_method=MatchMethod.EXACT_NUMERIC, match_score=0.0,
            ocr_confidence_avg=0.9, llm_confidence=0.9, composite_confidence=0.0,
            risk_level=risk, requires_human_review=True, crop_paths=crops,
        )
    queue = build_review_queue(claim)
    summary = summarize_review_queue(queue)
    assert summary["total"] == 3
    assert summary["high_risk"] == 2
    assert summary["needs_review"] == 1
    assert summary["no_visual_evidence"] == 2
