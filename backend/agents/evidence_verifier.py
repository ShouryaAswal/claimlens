"""
agents/evidence_verifier.py
--------------------------------
Sprint 3's safety-critical component: does the text a field's cited
evidence actually SUPPORT the value the extraction agent claimed?

Sprint 2 already checks that a cited block_id *exists* in the corpus
(catches an invented citation). This agent checks something stricter and
more important: that the cited block's *text* actually contains the
claimed value -- catches a real citation pointing at real text that simply
doesn't say what the model claimed it says.

THE CENTRAL DESIGN DECISION, and why it matters:

Fuzzy/approximate text matching is fine for a name or an address -- OCR
noise on natural language is forgivable, and "Priya Nair" vs "Priya Nalr"
is obviously the same claim with a minor scan artifact. It is NOT
acceptable for a dollar amount, a date, or a code (VIN, ICD-10, CPT, policy
number): "$4,250.00" vs "$4,259.00" is a HIGH fuzzy-similarity score and a
COMPLETELY DIFFERENT, WRONG number. A single transposed digit in a claim
amount is not a 95%-correct answer -- it's wrong, full stop, and treating
it as "close enough" is exactly the kind of error that costs real money or
creates a real discrepancy in a legal record.

So field_type drives the verification strategy, not a single similarity
threshold for everything:

  - "number" -> exact numeric match (after stripping currency symbols/
    commas/whitespace). Every digit must match. No tolerance.
  - "date"   -> exact match after date normalization (dateutil parses
    "2026-06-12", "June 12, 2026", "06/12/2026" to the same date object).
    No tolerance -- a transposed day/month is a different date.
  - "code"   -> exact match after normalizing case/whitespace/punctuation
    only (VIN, ICD-10, CPT, policy numbers). No character-substitution
    tolerance -- a one-character-off VIN is a different vehicle.
  - "text"/"boolean" -> fuzzy match (difflib) with a real but forgiving
    threshold. Natural language OCR noise is tolerated; a low score still
    gets flagged for review, never silently passed.

A field with NO cited evidence at all is "no_evidence" and always
high-risk -- there's nothing to verify a number against.
"""

from __future__ import annotations

import difflib
import logging
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from dateutil import parser as dateutil_parser

from core.schemas import ClaimState, ContentBlock, ExtractedField, FieldDefinition, MatchMethod

logger = logging.getLogger(__name__)

# Below this fuzzy-text similarity, a text field is NOT considered verified
# (it still gets a score and a reason -- callers decide what to do with it,
# typically flag for review rather than discard).
FUZZY_TEXT_MATCH_THRESHOLD = 0.6

_NUMERIC_RE = re.compile(r"-?\$?\d[\d,]*\.?\d*")


@dataclass
class MatchResult:
    matched: bool
    method: MatchMethod
    score: float  # 0.0 - 1.0
    reason: str


def _extract_numeric_candidates(text: str) -> list[Decimal]:
    """Pulls every number-looking substring out of a text blob (a block of
    OCR'd text often contains several numbers -- line item amounts, dates,
    counts -- and the one we want could be any of them)."""
    candidates: list[Decimal] = []
    for raw in _NUMERIC_RE.findall(text):
        cleaned = raw.replace("$", "").replace(",", "").strip()
        if not cleaned or cleaned in ("-", "."):
            continue
        try:
            candidates.append(Decimal(cleaned))
        except InvalidOperation:
            continue
    return candidates


def verify_numeric(value: str, evidence_text: str) -> MatchResult:
    target_candidates = _extract_numeric_candidates(value)
    if not target_candidates:
        return MatchResult(
            False, MatchMethod.UNPARSEABLE, 0.0,
            f"Extracted value {value!r} does not parse as a number -- cannot verify.",
        )
    target = target_candidates[0]

    evidence_candidates = _extract_numeric_candidates(evidence_text)
    if target in evidence_candidates:
        return MatchResult(
            True, MatchMethod.EXACT_NUMERIC, 1.0,
            f"Exact numeric match: {target} found verbatim in cited evidence.",
        )
    return MatchResult(
        False, MatchMethod.EXACT_NUMERIC, 0.0,
        f"NO EXACT MATCH for {target} in cited evidence "
        f"(numbers found there: {evidence_candidates or 'none'}). "
        f"Even a single-digit discrepancy on a claim amount is treated as a hard failure, not a near-miss.",
    )


def _try_parse_date(text: str):
    try:
        return dateutil_parser.parse(text, fuzzy=True).date()
    except (ValueError, OverflowError):
        return None


def verify_date(value: str, evidence_text: str) -> MatchResult:
    target_date = _try_parse_date(value)
    if target_date is None:
        return MatchResult(
            False, MatchMethod.UNPARSEABLE, 0.0,
            f"Extracted value {value!r} does not parse as a date -- cannot verify.",
        )

    # dateutil's fuzzy mode on a whole block of prose can lock onto the
    # wrong number sequence -- scan plausible date-shaped substrings
    # individually rather than fuzzy-parsing the entire block at once.
    date_like = re.findall(
        r"\b\d{1,4}[-/]\d{1,2}[-/]\d{1,4}\b|\b[A-Za-z]+\.?\s+\d{1,2},?\s+\d{4}\b",
        evidence_text,
    )
    for candidate_str in date_like:
        candidate_date = _try_parse_date(candidate_str)
        if candidate_date == target_date:
            return MatchResult(
                True, MatchMethod.EXACT_DATE, 1.0,
                f"Exact date match: {target_date.isoformat()} found in cited evidence.",
            )
    return MatchResult(
        False, MatchMethod.EXACT_DATE, 0.0,
        f"NO EXACT MATCH for date {target_date.isoformat()} in cited evidence "
        f"(date-like substrings found: {date_like or 'none'}). "
        f"A transposed day/month is a different date, not a close one.",
    )


def verify_code(value: str, evidence_text: str) -> MatchResult:
    """VIN, ICD-10, CPT, policy/case numbers, etc. Normalize ONLY case and
    incidental whitespace -- never tolerate a substituted character."""
    normalize = lambda s: re.sub(r"\s+", "", s).upper()
    target = normalize(value)
    if not target:
        return MatchResult(
            False, MatchMethod.UNPARSEABLE, 0.0,
            "Extracted value is empty after normalization -- cannot verify.",
        )
    if target in normalize(evidence_text):
        return MatchResult(
            True, MatchMethod.EXACT_CODE, 1.0,
            f"Exact code match: {value!r} found verbatim (case/whitespace-insensitive) in cited evidence.",
        )
    return MatchResult(
        False, MatchMethod.EXACT_CODE, 0.0,
        f"NO EXACT MATCH for code {value!r} in cited evidence. "
        f"A single substituted character makes this a different identifier, not a typo.",
    )


def verify_text(value: str, evidence_text: str) -> MatchResult:
    ratio = difflib.SequenceMatcher(a=value.lower(), b=evidence_text.lower()).ratio()
    # SequenceMatcher penalizes length mismatch heavily (comparing a short
    # value against a long block of surrounding text) -- also check the
    # best-aligned substring window so a short, exact value inside a long
    # block doesn't get unfairly punished.
    best_substring_ratio = _best_substring_ratio(value.lower(), evidence_text.lower())
    score = max(ratio, best_substring_ratio)
    matched = score >= FUZZY_TEXT_MATCH_THRESHOLD
    reason = (
        f"Fuzzy text similarity {score:.2f} ({'meets' if matched else 'below'} "
        f"threshold {FUZZY_TEXT_MATCH_THRESHOLD})."
    )
    return MatchResult(matched, MatchMethod.FUZZY_TEXT, score, reason)


def _best_substring_ratio(value: str, evidence_text: str) -> float:
    if not value:
        return 0.0
    window = max(len(value), 1)
    best = 0.0
    step = max(1, window // 2)
    for start in range(0, max(len(evidence_text) - window + 1, 1), step):
        chunk = evidence_text[start:start + window]
        ratio = difflib.SequenceMatcher(a=value, b=chunk).ratio()
        best = max(best, ratio)
    return best


_VERIFIERS = {
    "number": verify_numeric,
    "date": verify_date,
    "code": verify_code,
    "text": verify_text,
    "boolean": verify_text,
}

# Field types where "close" is meaningless -- a match is exact or it's wrong.
CRITICAL_FIELD_TYPES = {"number", "date", "code"}


def verify_field(
    field: ExtractedField,
    field_def: FieldDefinition,
    claim: ClaimState,
) -> MatchResult:
    """The single entry point: verify one extracted field against its own
    cited evidence blocks. Returns a MatchResult; callers (confidence_rating.py)
    decide what risk_level/human-review consequence follows."""
    if field.status == "missing" or field.value is None:
        return MatchResult(False, MatchMethod.NO_EVIDENCE, 0.0, "Field has no value to verify.")

    if not field.evidence_block_ids:
        return MatchResult(
            False, MatchMethod.NO_EVIDENCE, 0.0,
            "Field has a value but no evidence_block_ids -- nothing to verify it against.",
        )

    blocks: list[ContentBlock] = [
        b for bid in field.evidence_block_ids if (b := claim.get_block(bid)) is not None
    ]
    if not blocks:
        # Shouldn't happen if Sprint 2's citation filtering ran first, but
        # never assume an upstream invariant -- verify it here too.
        return MatchResult(
            False, MatchMethod.NO_EVIDENCE, 0.0,
            "None of the cited block_ids resolve to real blocks in this claim.",
        )

    combined_evidence_text = "\n".join(b.text for b in blocks)
    verifier = _VERIFIERS.get(field_def.field_type, verify_text)
    result = verifier(field.value, combined_evidence_text)

    if field_def.field_type in CRITICAL_FIELD_TYPES and not result.matched:
        logger.warning(
            "CRITICAL FIELD MISMATCH: field_id=%r type=%r value=%r -- %s",
            field.field_id, field_def.field_type, field.value, result.reason,
        )

    return result
