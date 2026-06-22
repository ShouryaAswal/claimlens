"""
tests/test_doc_type_tagger.py
----------------------------------
Sprint 2: doc-type tagger tests. Several of these are regression tests for
real bugs caught while building this against actual sample/real-world
data (a generic keyword causing false positives, a tie between two
plausible types, a form type with no clean bucket) -- kept here rather
than silently fixed, since they're the most informative tests in this file.
"""

from __future__ import annotations

from agents.doc_type_tagger_agent import (
    tag_all_documents,
    tag_doc_type,
    tag_doc_type_rule_based,
    tag_doc_type_with_llm,
)
from agents.ingestion.dispatcher import ingest
from core.llm_client import LLMClient


def test_police_report_form_tagged_correctly():
    rec = ingest("samples/real_world/fnol_specimens/ny_dmv_mv104_specimen.pdf")
    doc_type, confidence = tag_doc_type_rule_based(rec)
    assert doc_type == "police_report"
    assert confidence > 0.5


def test_self_filed_crash_report_also_tagged_as_police_report():
    """Regression test: a driver-filed crash report (no literal 'police'
    in its title) must still land in the same bucket as a police-filed one
    -- they're the same functional document type for Gate Check purposes."""
    rec = ingest("samples/real_world/fnol_specimens/ma_crash_operator_report_specimen.pdf")
    doc_type, confidence = tag_doc_type_rule_based(rec)
    assert doc_type == "police_report"


def test_repair_estimate_image_tagged_correctly():
    rec = ingest("samples/damage_photo_01.png")
    doc_type, confidence = tag_doc_type_rule_based(rec)
    assert doc_type == "repair_estimate"


def test_correspondence_not_misclassified_by_incidental_mention():
    """Regression test: the note's text incidentally mentions 'police
    report' in passing ('awaiting police report confirmation'), but its
    actual heading is 'Adjuster Note' -- the heading-position bonus must
    win, not the raw keyword count."""
    rec = ingest("samples/example_claim_folder/CLM-2026-04821/correspondence/adjuster_note.html")
    doc_type, confidence = tag_doc_type_rule_based(rec)
    assert doc_type == "correspondence"


def test_unrecognized_form_type_honestly_returns_unknown():
    """Regression test: a single incidental keyword hit (one passing
    mention of 'repair estimates' in a flood Proof-of-Loss form, which has
    no matching bucket at all) must not be over-trusted into a confident
    wrong answer."""
    rec = ingest("samples/real_world/fnol_specimens/fema_proof_of_loss_specimen.pdf")
    doc_type, confidence = tag_doc_type_rule_based(rec)
    assert doc_type == "unknown"
    assert confidence == 0.0


def test_pure_photo_with_no_text_tagged_as_photos(tmp_path):
    from PIL import Image
    blank = tmp_path / "blank_damage_photo.png"
    Image.new("RGB", (400, 300), color="gray").save(blank)
    rec = ingest(str(blank))
    doc_type, confidence = tag_doc_type_rule_based(rec)
    assert doc_type == "photos"


def test_tag_all_documents_mutates_doc_type_in_place():
    rec = ingest("samples/real_world/fnol_specimens/ny_dmv_mv104_specimen.pdf")
    assert rec.doc_type is None
    tag_all_documents([rec])
    assert rec.doc_type == "police_report"


def test_llm_backed_tagging_parses_valid_response():
    fake_client = LLMClient(
        provider="fake", model="fake-model",
        complete=lambda s, u: '{"doc_type": "discharge_summary", "confidence": 0.88}',
    )
    rec = ingest("samples/health_claim_01.docx")
    doc_type, confidence = tag_doc_type_with_llm(rec, fake_client)
    assert doc_type == "discharge_summary"
    assert confidence == 0.88


def test_llm_backed_tagging_rejects_unrecognized_type():
    fake_client = LLMClient(
        provider="fake", model="fake-model",
        complete=lambda s, u: '{"doc_type": "ransom_note", "confidence": 0.9}',
    )
    rec = ingest("samples/health_claim_01.docx")
    doc_type, confidence = tag_doc_type_with_llm(rec, fake_client)
    assert doc_type == "unknown"


def test_tag_doc_type_falls_back_on_llm_exception():
    def _boom(s, u):
        raise RuntimeError("simulated failure")
    fake_client = LLMClient(provider="fake", model="fake-model", complete=_boom)
    rec = ingest("samples/real_world/fnol_specimens/ny_dmv_mv104_specimen.pdf")
    doc_type, confidence = tag_doc_type(rec, llm_client=fake_client)
    assert doc_type == "police_report"  # recovered via rule-based fallback
