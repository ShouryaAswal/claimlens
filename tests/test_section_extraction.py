"""
tests/test_section_extraction.py
--------------------------------------
Sprint 2 exit criterion: "Each section returns valid JSON; missing fields
explicitly listed (not silently dropped)."

No live Groq/Gemini call is reachable from this sandbox (see
core/llm_client.py's module docstring), so these tests exercise the
surrounding logic -- prompt construction, JSON parsing, block_id
verification, missing-field handling -- via a fake LLMClient with a
controllable `complete` function. This is exactly what's NOT covered by
just trusting an LLM to behave: a real model occasionally omits fields,
hallucinates citations, or returns malformed JSON, and this is the code
that has to catch all three without crashing the pipeline.
"""

from __future__ import annotations

import json

import pytest

from agents.gate_check import run_gate_check
from agents.section_extraction_agent import build_corpus_text, extract_claim, extract_section
from core.llm_client import LLMClient, LLMNotConfiguredError
from core.schema_loader import load_lob_schema
from core.schemas import ClaimState, ContentBlock, DocumentRecord, LOB, SourceFormat


def _fake_client(response_text: str) -> LLMClient:
    return LLMClient(provider="fake", model="fake-model", complete=lambda s, u: response_text)


def _make_auto_claim() -> ClaimState:
    schema = load_lob_schema(LOB.AUTO)
    blocks = [
        ContentBlock(
            block_id="p1_b001", source_file="auto_claim.pdf", source_format=SourceFormat.PDF,
            page=1, locator="page_1_block_1", text="Policy Number: AUTO-2026-00981",
            bbox=(10, 10, 200, 30), confidence=1.0, extraction_method="pymupdf_text",
        ),
        ContentBlock(
            block_id="p1_b002", source_file="auto_claim.pdf", source_format=SourceFormat.PDF,
            page=1, locator="page_1_block_2", text="Date of Loss: 2026-06-12",
            bbox=(10, 40, 200, 60), confidence=1.0, extraction_method="pymupdf_text",
        ),
    ]
    doc = DocumentRecord(
        doc_id="doc1", source_file="auto_claim.pdf", source_format=SourceFormat.PDF,
        page_count=1, blocks=blocks, doc_type="policy_declaration",
    )
    return ClaimState(claim_id="CLM-TEST", lob=LOB.AUTO, lob_schema=schema, documents=[doc])


def test_build_corpus_text_includes_block_ids_and_doc_headers():
    claim = _make_auto_claim()
    corpus = build_corpus_text(claim)
    assert "[p1_b001]" in corpus
    assert "AUTO-2026-00981" in corpus
    assert "auto_claim.pdf" in corpus


def test_extract_section_happy_path_returns_found_field_with_evidence():
    claim = _make_auto_claim()
    section = claim.lob_schema.get_section("policy_info")

    response = json.dumps({
        "fields": {
            "policy_number": {
                "value": "AUTO-2026-00981", "confidence": 0.97,
                "evidence_block_ids": ["p1_b001"], "status": "found", "reason": "Explicit label.",
            },
            "carrier_name": {
                "value": None, "confidence": 0.0,
                "evidence_block_ids": [], "status": "missing", "reason": "Not mentioned anywhere.",
            },
            "policy_effective_dates": {
                "value": None, "confidence": 0.0,
                "evidence_block_ids": [], "status": "missing", "reason": "Not mentioned anywhere.",
            },
        }
    })
    results = extract_section(section, claim, _fake_client(response))

    assert results["policy_number"].status == "found"
    assert results["policy_number"].value == "AUTO-2026-00981"
    assert results["policy_number"].evidence_block_ids == ["p1_b001"]
    assert results["carrier_name"].status == "missing"
    # every field in the section schema has an entry, regardless of LLM output
    assert set(results.keys()) == {f.field_id for f in section.fields}


def test_extract_section_explicitly_lists_field_llm_completely_omitted():
    """The literal exit criterion: an LLM that just... doesn't mention a
    field in its JSON must still produce an explicit 'missing' entry for
    it, not a silently absent key."""
    claim = _make_auto_claim()
    section = claim.lob_schema.get_section("policy_info")

    # Deliberately omits "carrier_name" and "policy_effective_dates" entirely.
    response = json.dumps({
        "fields": {
            "policy_number": {
                "value": "AUTO-2026-00981", "confidence": 0.9,
                "evidence_block_ids": ["p1_b001"], "status": "found",
            },
        }
    })
    results = extract_section(section, claim, _fake_client(response))

    assert set(results.keys()) == {f.field_id for f in section.fields}
    assert results["carrier_name"].status == "missing"
    assert results["carrier_name"].value is None
    assert "not returned" in results["carrier_name"].reason.lower()
    assert results["policy_effective_dates"].status == "missing"


def test_extract_section_drops_hallucinated_block_id_citation():
    """The core anti-hallucination guard: a citation pointing at a
    block_id that doesn't exist in this claim's corpus must not be trusted,
    and a field with ONLY fake citations must be demoted to missing."""
    claim = _make_auto_claim()
    section = claim.lob_schema.get_section("policy_info")

    response = json.dumps({
        "fields": {
            "policy_number": {
                "value": "AUTO-2026-00981", "confidence": 0.95,
                "evidence_block_ids": ["p1_b001", "p9_b999_DOES_NOT_EXIST"],
                "status": "found",
            },
            "carrier_name": {
                "value": "Some Invented Insurer", "confidence": 0.8,
                "evidence_block_ids": ["p4_bFAKE"],  # entirely fabricated citation
                "status": "found",
            },
            "policy_effective_dates": {
                "value": None, "confidence": 0.0, "evidence_block_ids": [], "status": "missing",
            },
        }
    })
    results = extract_section(section, claim, _fake_client(response))

    # Partially real citation -- the real one survives, the fake one is dropped.
    assert results["policy_number"].evidence_block_ids == ["p1_b001"]
    assert results["policy_number"].status == "found"

    # ENTIRELY fake citation -- demoted to missing, value discarded.
    assert results["carrier_name"].status == "missing"
    assert results["carrier_name"].value is None
    assert "demoted" in results["carrier_name"].reason.lower()


def test_extract_section_handles_malformed_json_without_crashing():
    claim = _make_auto_claim()
    section = claim.lob_schema.get_section("policy_info")
    results = extract_section(section, claim, _fake_client("this is not json at all {{{"))

    # Every field still gets an explicit entry, all "missing" -- a broken
    # response degrades to "we found nothing" rather than crashing the run.
    assert set(results.keys()) == {f.field_id for f in section.fields}
    assert all(f.status == "missing" for f in results.values())


def test_extract_section_handles_markdown_fenced_json():
    claim = _make_auto_claim()
    section = claim.lob_schema.get_section("policy_info")
    response = "```json\n" + json.dumps({
        "fields": {
            "policy_number": {"value": "AUTO-2026-00981", "confidence": 0.9,
                               "evidence_block_ids": ["p1_b001"], "status": "found"},
            "carrier_name": {"value": None, "confidence": 0.0, "evidence_block_ids": [], "status": "missing"},
            "policy_effective_dates": {"value": None, "confidence": 0.0, "evidence_block_ids": [], "status": "missing"},
        }
    }) + "\n```"
    results = extract_section(section, claim, _fake_client(response))
    assert results["policy_number"].status == "found"


def test_extract_section_clamps_out_of_range_confidence():
    claim = _make_auto_claim()
    section = claim.lob_schema.get_section("policy_info")
    response = json.dumps({
        "fields": {
            "policy_number": {"value": "X", "confidence": 5.0,  # way out of range
                               "evidence_block_ids": ["p1_b001"], "status": "found"},
            "carrier_name": {"value": None, "confidence": -3.0,  # negative
                              "evidence_block_ids": [], "status": "missing"},
            "policy_effective_dates": {"value": None, "confidence": 0.0, "evidence_block_ids": [], "status": "missing"},
        }
    })
    results = extract_section(section, claim, _fake_client(response))
    assert results["policy_number"].confidence == 1.0
    assert results["carrier_name"].confidence == 0.0


def test_extract_claim_without_llm_client_raises_clear_error():
    claim = _make_auto_claim()
    with pytest.raises(LLMNotConfiguredError, match="GROQ_API_KEY|GOOGLE_API_KEY"):
        extract_claim(claim, llm_client=None)


def test_extract_claim_without_resolved_schema_raises():
    claim = _make_auto_claim()
    claim.lob_schema = None
    with pytest.raises(ValueError):
        extract_claim(claim, llm_client=_fake_client('{"fields": {}}'))


def test_extract_claim_runs_every_section_and_populates_claim_state():
    claim = _make_auto_claim()

    def _complete(system_prompt: str, user_prompt: str) -> str:
        # Echo back "found" for whatever fields were asked, generically --
        # this proves extract_claim iterates every section, not just one.
        import re
        field_ids = re.findall(r"^- (\w+) \[", user_prompt, flags=re.MULTILINE)
        return json.dumps({
            "fields": {
                fid: {"value": "stub", "confidence": 0.5, "evidence_block_ids": [], "status": "low_confidence"}
                for fid in field_ids
            }
        })

    fake_client = LLMClient(provider="fake", model="fake-model", complete=_complete)
    extract_claim(claim, llm_client=fake_client)

    all_schema_field_ids = {f.field_id for f in claim.lob_schema.all_fields}
    assert set(claim.extracted_fields.keys()) == all_schema_field_ids
