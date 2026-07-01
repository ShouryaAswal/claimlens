"""
tests/test_reviewer_summary_agent.py
------------------------------------------
Sprint 4: reviewer summary agent. The rule-based template is the one
actually exercised end-to-end (no live Groq/Gemini call reachable from this
sandbox, same caveat as every other LLM-backed agent in this project -- see
SPRINT_2_NOTES.md). The LLM-backed path is tested via a fake LLMClient,
covering the happy path, the empty-response failure mode, and the
fallback-on-exception behavior.
"""

from __future__ import annotations

import pytest

from agents.human_review_queue import build_review_queue
from agents.reviewer_summary_agent import (
    build_completion_stats,
    generate_reviewer_summary,
    generate_summary_rule_based,
    generate_summary_with_llm,
)
from agents.triage_agent import apply_triage_to_claim
from core.llm_client import LLMClient
from core.schema_loader import load_lob_schema
from core.schemas import (
    ClaimState,
    ExtractedField,
    FieldVerification,
    LOB,
    MatchMethod,
    RiskLevel,
)


def _clean_claim() -> ClaimState:
    schema = load_lob_schema(LOB.AUTO)
    claim = ClaimState(claim_id="CLM-TEST", lob=LOB.AUTO, lob_schema=schema)
    apply_triage_to_claim(claim)
    return claim


def _claim_with_high_risk_field() -> ClaimState:
    schema = load_lob_schema(LOB.AUTO)
    claim = ClaimState(claim_id="CLM-TEST", lob=LOB.AUTO, lob_schema=schema)
    claim.extracted_fields["repair_estimate_amount"] = ExtractedField(
        field_id="repair_estimate_amount", value="4259.00", status="found",
        confidence=0.9, evidence_block_ids=["b1"],
    )
    claim.field_verifications["repair_estimate_amount"] = FieldVerification(
        field_id="repair_estimate_amount", match_method=MatchMethod.EXACT_NUMERIC, match_score=0.0,
        ocr_confidence_avg=0.9, llm_confidence=0.9, composite_confidence=0.0,
        risk_level=RiskLevel.HIGH_RISK, requires_human_review=True,
        reasons=["NO EXACT MATCH for 4259.00"],
    )
    apply_triage_to_claim(claim)
    return claim


def test_completion_stats_on_empty_claim():
    schema = load_lob_schema(LOB.AUTO)
    claim = ClaimState(claim_id="C1", lob=LOB.AUTO, lob_schema=schema)
    stats = build_completion_stats(claim)
    assert stats["total_fields"] == len(schema.all_fields)
    assert stats["fields_found"] == 0
    assert stats["required_fields"] == len(schema.required_fields)
    assert stats["required_fields_found"] == 0


def test_completion_stats_counts_only_found_status():
    schema = load_lob_schema(LOB.AUTO)
    claim = ClaimState(claim_id="C1", lob=LOB.AUTO, lob_schema=schema)
    claim.extracted_fields["policy_number"] = ExtractedField(field_id="policy_number", value="X", status="found")
    claim.extracted_fields["carrier_name"] = ExtractedField(field_id="carrier_name", value=None, status="missing")
    stats = build_completion_stats(claim)
    assert stats["fields_found"] == 1


def test_completion_stats_without_schema_does_not_crash():
    claim = ClaimState(claim_id="C1", lob=None, lob_schema=None)
    stats = build_completion_stats(claim)
    assert stats["total_fields"] == 0


def test_rule_based_summary_on_clean_claim_mentions_stp():
    claim = _clean_claim()
    queue = build_review_queue(claim)
    summary = generate_summary_rule_based(claim, build_completion_stats(claim), claim.triage, queue)
    assert "STP CANDIDATE" in summary
    assert "No fields flagged" in summary


def test_rule_based_summary_calls_out_forced_review_explicitly():
    claim = _claim_with_high_risk_field()
    assert claim.triage.forced_review is True
    queue = build_review_queue(claim)
    summary = generate_summary_rule_based(claim, build_completion_stats(claim), claim.triage, queue)
    assert "NOTE" in summary
    assert "cannot be auto-approved" in summary


def test_rule_based_summary_lists_flagged_fields_with_reasons():
    claim = _claim_with_high_risk_field()
    queue = build_review_queue(claim)
    summary = generate_summary_rule_based(claim, build_completion_stats(claim), claim.triage, queue)
    assert "repair_estimate_amount" in summary or "Repair Estimate" in summary
    assert "HIGH_RISK" in summary


def test_rule_based_summary_truncates_long_review_queue_with_count():
    schema = load_lob_schema(LOB.AUTO)
    claim = ClaimState(claim_id="C1", lob=LOB.AUTO, lob_schema=schema)
    for i in range(8):
        fid = f"field_{i}"
        claim.field_verifications[fid] = FieldVerification(
            field_id=fid, match_method=MatchMethod.FUZZY_TEXT, match_score=0.3,
            ocr_confidence_avg=0.9, llm_confidence=0.9, composite_confidence=0.2,
            risk_level=RiskLevel.NEEDS_REVIEW, requires_human_review=True, reasons=["low confidence"],
        )
    apply_triage_to_claim(claim)
    queue = build_review_queue(claim)
    summary = generate_summary_rule_based(claim, build_completion_stats(claim), claim.triage, queue)
    assert "3 more" in summary


def test_rule_based_summary_missing_mandatory_docs_listed():
    claim = _clean_claim()
    claim.missing_mandatory_docs = ["photos", "police_report"]
    apply_triage_to_claim(claim)  # recompute with the missing docs now set
    summary = generate_summary_rule_based(claim, build_completion_stats(claim), claim.triage, [])
    assert "photos" in summary and "police_report" in summary


def test_llm_backed_summary_returns_llm_text_verbatim():
    claim = _clean_claim()
    queue = build_review_queue(claim)
    fake_client = LLMClient(provider="fake", model="fake",
                             complete=lambda s, u: "This claim looks clean and ready for STP.")
    summary = generate_summary_with_llm(claim, build_completion_stats(claim), claim.triage, queue, fake_client)
    assert summary == "This claim looks clean and ready for STP."


def test_llm_backed_summary_raises_on_empty_response():
    claim = _clean_claim()
    queue = build_review_queue(claim)
    fake_client = LLMClient(provider="fake", model="fake", complete=lambda s, u: "   ")
    with pytest.raises(ValueError):
        generate_summary_with_llm(claim, build_completion_stats(claim), claim.triage, queue, fake_client)


def test_generate_reviewer_summary_falls_back_to_rule_based_on_llm_failure():
    claim = _clean_claim()
    queue = build_review_queue(claim)

    def _boom(s, u):
        raise RuntimeError("network down")

    broken_client = LLMClient(provider="fake", model="fake", complete=_boom)
    summary = generate_reviewer_summary(claim, queue, llm_client=broken_client)
    assert "STP CANDIDATE" in summary  # the rule-based template's output, not a crash


def test_generate_reviewer_summary_uses_llm_when_it_works():
    claim = _clean_claim()
    queue = build_review_queue(claim)
    fake_client = LLMClient(provider="fake", model="fake",
                             complete=lambda s, u: "Custom LLM-written summary text.")
    summary = generate_reviewer_summary(claim, queue, llm_client=fake_client)
    assert summary == "Custom LLM-written summary text."


def test_generate_reviewer_summary_without_triage_raises():
    schema = load_lob_schema(LOB.AUTO)
    claim = ClaimState(claim_id="C1", lob=LOB.AUTO, lob_schema=schema)
    with pytest.raises(ValueError):
        generate_reviewer_summary(claim, [])


def test_generate_reviewer_summary_default_mode_is_rule_based():
    claim = _clean_claim()
    queue = build_review_queue(claim)
    summary = generate_reviewer_summary(claim, queue)  # no llm_client passed
    assert "STP CANDIDATE" in summary
