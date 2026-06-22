"""
tests/test_lob_classifier.py
--------------------------------
Sprint 2: LOB classifier agent tests. Covers the rule-based default (no API
key required, runs in any environment) against both clean synthetic samples
and the real-world/realistic data added this round -- the rule-based path
is the one actually exercised end-to-end here, since no live LLM API is
reachable from this sandbox (see core/llm_client.py's module docstring).
The LLM-backed path is covered separately via dependency injection with a
fake client, proving the parsing/validation logic around it is correct.
"""

from __future__ import annotations

from agents.ingestion.dispatcher import ingest
from agents.lob_classifier_agent import (
    classify_lob,
    classify_lob_rule_based,
    classify_lob_with_llm,
)
from core.llm_client import LLMClient
from core.schemas import LOB


def test_auto_claim_classified_correctly():
    rec = ingest("samples/auto_claim_01.pdf")
    lob, confidence = classify_lob_rule_based(rec.full_text)
    assert lob == LOB.AUTO
    assert confidence > 0.5


def test_health_claim_classified_correctly():
    rec = ingest("samples/health_claim_01.docx")
    lob, confidence = classify_lob_rule_based(rec.full_text)
    assert lob == LOB.HEALTH
    assert confidence > 0.5


def test_property_claim_classified_correctly():
    rec = ingest("samples/property_claim_01_scanned.pdf")
    lob, confidence = classify_lob_rule_based(rec.full_text)
    assert lob == LOB.PROPERTY
    assert confidence > 0.5


def test_real_fema_property_form_classified_correctly():
    """The case that caught a real bug in the first version of the
    rule-based scorer (generic shared terms outweighing distinctive ones)
    -- kept as a regression test."""
    rec = ingest("samples/real_world/fnol_specimens/fema_proof_of_loss_specimen.pdf")
    lob, confidence = classify_lob_rule_based(rec.full_text)
    assert lob == LOB.PROPERTY


def test_ny_dmv_crash_form_classified_correctly():
    rec = ingest("samples/real_world/fnol_specimens/ny_dmv_mv104_specimen.pdf")
    lob, confidence = classify_lob_rule_based(rec.full_text)
    assert lob == LOB.AUTO


def test_empty_text_returns_unknown():
    lob, confidence = classify_lob_rule_based("   ")
    assert lob == LOB.UNKNOWN
    assert confidence == 0.0


def test_irrelevant_text_returns_unknown_or_low_confidence():
    lob, confidence = classify_lob_rule_based("The quick brown fox jumps over the lazy dog.")
    assert lob == LOB.UNKNOWN


def test_classify_lob_falls_back_to_rule_based_without_client():
    rec = ingest("samples/auto_claim_01.pdf")
    lob, confidence = classify_lob(rec.full_text, llm_client=None)
    assert lob == LOB.AUTO


def test_classify_lob_with_llm_parses_valid_response():
    fake_client = LLMClient(
        provider="fake",
        model="fake-model",
        complete=lambda system_prompt, user_prompt: '{"lob": "auto", "confidence": 0.92, "reason": "mentions VIN and police report"}',
    )
    lob, confidence = classify_lob_with_llm("some claim text", fake_client)
    assert lob == LOB.AUTO
    assert confidence == 0.92


def test_classify_lob_with_llm_handles_malformed_json_gracefully():
    fake_client = LLMClient(
        provider="fake",
        model="fake-model",
        complete=lambda system_prompt, user_prompt: "not valid json at all",
    )
    lob, confidence = classify_lob_with_llm("some claim text", fake_client)
    assert lob == LOB.UNKNOWN
    assert confidence == 0.0


def test_classify_lob_with_llm_handles_unknown_lob_value():
    fake_client = LLMClient(
        provider="fake",
        model="fake-model",
        complete=lambda system_prompt, user_prompt: '{"lob": "marine_cargo", "confidence": 0.5}',
    )
    lob, confidence = classify_lob_with_llm("some claim text", fake_client)
    assert lob == LOB.UNKNOWN  # invalid enum value caught, not propagated as a crash


def test_classify_lob_prefers_llm_but_falls_back_on_exception():
    def _boom(system_prompt, user_prompt):
        raise RuntimeError("simulated network failure")

    fake_client = LLMClient(provider="fake", model="fake-model", complete=_boom)
    rec = ingest("samples/auto_claim_01.pdf")
    lob, confidence = classify_lob(rec.full_text, llm_client=fake_client)
    assert lob == LOB.AUTO  # recovered via rule-based fallback, didn't crash
