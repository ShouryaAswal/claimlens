"""
tests/test_evidence_verifier.py
-------------------------------------
Sprint 3's most important test file. The central requirement from this
round's brief: "if the scanned image was so bad... numeric claims values
aren't hallucinated, even a single digit error, must be fatal." Every test
in the numeric/date/code sections exists to prove that property, not just
to pad coverage.
"""

from __future__ import annotations

from agents.evidence_verifier import (
    CRITICAL_FIELD_TYPES,
    verify_code,
    verify_date,
    verify_field,
    verify_numeric,
    verify_text,
)
from core.schemas import (
    ClaimState,
    ContentBlock,
    ExtractedField,
    FieldDefinition,
    LOB,
    SourceFormat,
)


# ---------------------------------------------------------------------------
# THE core safety property: single-digit/single-character errors are fatal
# ---------------------------------------------------------------------------

def test_single_digit_numeric_error_is_a_hard_fail():
    r = verify_numeric("4259.00", "Total Estimate: $4,250.00")
    assert r.matched is False
    assert r.score == 0.0


def test_single_digit_numeric_error_fails_even_with_high_string_similarity():
    """The whole point: '4259.00' and '4250.00' are ~85% similar as raw
    strings (a fuzzy matcher would likely pass this), but they are
    DIFFERENT NUMBERS. This must fail regardless of string similarity."""
    import difflib
    raw_similarity = difflib.SequenceMatcher(a="4259.00", b="4250.00").ratio()
    assert raw_similarity > 0.7  # confirms this WOULD pass a naive fuzzy threshold
    r = verify_numeric("4259.00", "Total Estimate: $4,250.00")
    assert r.matched is False  # ...but our verifier does not use fuzzy matching for numbers


def test_transposed_date_digits_is_a_hard_fail():
    r = verify_date("2026-06-21", "Date of Loss: 2026-06-12")  # day digits transposed
    assert r.matched is False


def test_single_character_vin_substitution_is_a_hard_fail():
    r = verify_code("1HGCM82633A004353", "VIN: 1HGCM82633A004352")  # last digit differs
    assert r.matched is False


def test_exact_numeric_match_passes():
    r = verify_numeric("4250.00", "Total Estimate: $4,250.00")
    assert r.matched is True
    assert r.score == 1.0


def test_numeric_match_tolerates_currency_formatting_not_digits():
    """Formatting differences (currency symbol, commas, decimal precision)
    are fine -- those aren't claims about the VALUE. Digit differences are
    never fine."""
    r = verify_numeric("4250", "Total Estimate: $4,250.00")
    assert r.matched is True

    r2 = verify_numeric("4,250.00", "estimate 4250.00")
    assert r2.matched is True


def test_numeric_match_finds_target_among_multiple_numbers_in_block():
    r = verify_numeric("4250.00", "Subtotal: $3,900.00 Tax: $350.00 Total: $4,250.00")
    assert r.matched is True


def test_negative_numeric_match():
    r = verify_numeric("-500.00", "Adjustment: -500.00 applied")
    assert r.matched is True


def test_date_match_across_different_formats():
    assert verify_date("2026-06-12", "Date of Loss: June 12, 2026").matched is True
    assert verify_date("06/12/2026", "Loss occurred on 2026-06-12.").matched is True


def test_code_match_is_case_and_whitespace_insensitive_only():
    r = verify_code("1hgcm82633a004352", "VIN:1HGCM82633A004352")
    assert r.matched is True  # case + whitespace differences are fine


def test_unparseable_numeric_value_does_not_crash():
    r = verify_numeric("not a number", "Total: $4,250.00")
    assert r.matched is False
    assert "does not parse" in r.reason


def test_unparseable_date_value_does_not_crash():
    r = verify_date("sometime in the spring", "Date of Loss: 2026-06-12")
    assert r.matched is False


# ---------------------------------------------------------------------------
# Text fields: fuzzy matching IS appropriate here (different risk profile)
# ---------------------------------------------------------------------------

def test_text_field_tolerates_minor_ocr_noise():
    r = verify_text("Priya Nair", "Driver Name: Prya Nair")  # one letter dropped
    assert r.matched is True


def test_text_field_rejects_unrelated_text():
    r = verify_text("Priya Nair", "Vehicle damage to rear bumper")
    assert r.matched is False


def test_short_value_inside_long_block_is_not_unfairly_penalized():
    long_block = "This is a long paragraph of context text. " * 5 + "Driver Name: Priya Nair. " + "More context follows. " * 5
    r = verify_text("Priya Nair", long_block)
    assert r.matched is True


# ---------------------------------------------------------------------------
# verify_field(): the full integration with ClaimState/ExtractedField
# ---------------------------------------------------------------------------

def _make_claim_with_block(text: str) -> ClaimState:
    from core.schema_loader import load_lob_schema
    from core.schemas import DocumentRecord

    schema = load_lob_schema(LOB.AUTO)
    block = ContentBlock(
        block_id="p1_b001", source_file="doc.pdf", source_format=SourceFormat.PDF,
        page=1, locator="page_1_block_1", text=text,
        bbox=(10, 10, 200, 30), confidence=0.95, extraction_method="pymupdf_text",
    )
    doc = DocumentRecord(doc_id="d1", source_file="doc.pdf", source_format=SourceFormat.PDF,
                          page_count=1, blocks=[block])
    return ClaimState(claim_id="CLM-TEST", lob=LOB.AUTO, lob_schema=schema, documents=[doc])


def test_verify_field_missing_status_returns_no_evidence():
    claim = _make_claim_with_block("Repair Estimate: $4,250.00")
    field = ExtractedField(field_id="repair_estimate_amount", status="missing", value=None)
    field_def = FieldDefinition(field_id="repair_estimate_amount", label="Repair Estimate", field_type="number")
    result = verify_field(field, field_def, claim)
    assert result.matched is False
    assert result.method.value == "no_evidence"


def test_verify_field_no_evidence_block_ids_returns_no_evidence():
    claim = _make_claim_with_block("Repair Estimate: $4,250.00")
    field = ExtractedField(field_id="repair_estimate_amount", status="found", value="4250.00", evidence_block_ids=[])
    field_def = FieldDefinition(field_id="repair_estimate_amount", label="Repair Estimate", field_type="number")
    result = verify_field(field, field_def, claim)
    assert result.matched is False
    assert result.method.value == "no_evidence"


def test_verify_field_dangling_block_id_returns_no_evidence():
    """Defensive depth: even if Sprint 2's citation-existence filter is
    somehow bypassed, this layer must not crash or false-pass."""
    claim = _make_claim_with_block("Repair Estimate: $4,250.00")
    field = ExtractedField(field_id="x", status="found", value="4250.00",
                            evidence_block_ids=["does_not_exist"])
    field_def = FieldDefinition(field_id="x", label="X", field_type="number")
    result = verify_field(field, field_def, claim)
    assert result.matched is False


def test_verify_field_routes_by_field_type_correctly():
    claim = _make_claim_with_block("Repair Estimate: $4,250.00")
    correct_field = ExtractedField(field_id="x", status="found", value="4250.00",
                                    evidence_block_ids=["p1_b001"])
    wrong_field = ExtractedField(field_id="x", status="found", value="9999.00",
                                  evidence_block_ids=["p1_b001"])
    field_def = FieldDefinition(field_id="x", label="X", field_type="number")

    assert verify_field(correct_field, field_def, claim).matched is True
    assert verify_field(wrong_field, field_def, claim).matched is False


def test_critical_field_types_constant_matches_expected_set():
    assert CRITICAL_FIELD_TYPES == {"number", "date", "code"}
    assert "text" not in CRITICAL_FIELD_TYPES
