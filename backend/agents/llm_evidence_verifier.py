"""
agents/llm_evidence_verifier.py
-------------------------------------
The optional, semantic second-opinion layer on top of evidence_verifier.py's
deterministic matching. Two genuinely different jobs, not redundant:

  - evidence_verifier.py asks: "does this exact value appear in this exact
    text?" -- precise, cheap, zero false-pass risk for numbers/dates/codes,
    but blind to anything that isn't a literal string match (it can't tell
    you "5:45 PM" and "17:45" mean the same time, or that a value is
    technically present but contradicted by context two sentences later).
  - This module asks an LLM: "given this evidence text, does it actually
    SUPPORT this claimed value?" -- catches semantic mismatches the
    deterministic check can't see, at the cost of needing a real API call.

Use this selectively, not on every field: it's the second-opinion step for
fields the deterministic check already flagged as uncertain (or for
critical fields you want extra scrutiny on, given that the brief's framing
is "a single digit error must be fatal" -- belt-and-suspenders is the right
instinct for claim amounts specifically). Running it on every field in
every claim is unnecessary cost for fields the cheap check already
confirmed cleanly.

Same dependency-injection-tested pattern as Sprint 2's LLM-backed agents:
no live Groq/Gemini call was reachable from the sandbox this was built in
(see core/llm_client.py's module docstring), so this is tested via a fake
LLMClient and is correct-by-construction against the documented API shape,
not confirmed against a real response yet.
"""

from __future__ import annotations

import logging

from core.llm_client import LLMClient, parse_json_response
from core.schemas import ContentBlock, ExtractedField, FieldDefinition, LLMVerificationResult

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are a careful insurance claims auditor double-checking
a single extracted field against its cited source text.

You will be given the field's label/description, the value that was
extracted, and the exact text of the document block(s) cited as evidence.

Decide: does the cited text actually SUPPORT this value? Be skeptical and
precise, especially for numbers, dates, and identifiers (VIN, policy
number, codes) -- a value that is merely "similar" to what's written is
NOT supported; it must be the same fact, allowing only for formatting
differences (currency symbols, date format, capitalization) and equivalent
phrasing for non-numeric values (e.g. "5:45 PM" and "17:45" are the same
time).

Respond with ONLY a JSON object, no other text:
{"supported": true|false, "confidence": <float 0.0-1.0>, "explanation": "<one short sentence>"}
"""


def _format_prompt(field: ExtractedField, field_def: FieldDefinition, evidence_blocks: list[ContentBlock]) -> str:
    evidence_text = "\n".join(f"[{b.block_id}] {b.text}" for b in evidence_blocks)
    return (
        f"FIELD: {field_def.label} ({field_def.field_type})\n"
        f"EXTRACTED VALUE: {field.value!r}\n\n"
        f"CITED EVIDENCE TEXT:\n{evidence_text}\n\n"
        f"Does the cited evidence actually support this value?"
    )


def llm_verify_field(
    field: ExtractedField,
    field_def: FieldDefinition,
    evidence_blocks: list[ContentBlock],
    llm_client: LLMClient,
) -> LLMVerificationResult:
    """Runs the LLM second-opinion check for one field. Always returns a
    valid LLMVerificationResult -- a malformed/failed LLM response degrades
    to `supported=False, confidence=0.0` (treated as "could not confirm",
    which is the safe direction to fail in) rather than raising and halting
    the pipeline."""
    if not evidence_blocks:
        return LLMVerificationResult(
            supported=False, confidence=0.0,
            explanation="No evidence blocks available to check against.",
        )

    prompt = _format_prompt(field, field_def, evidence_blocks)
    try:
        raw = llm_client.complete(_SYSTEM_PROMPT, prompt)
        parsed = parse_json_response(raw)
        return LLMVerificationResult(
            supported=bool(parsed.get("supported", False)),
            confidence=max(0.0, min(1.0, float(parsed.get("confidence", 0.0)))),
            explanation=str(parsed.get("explanation", "")),
        )
    except Exception as exc:  # noqa: BLE001 - a flaky/malformed LLM response must not crash the run
        logger.warning(
            "LLM evidence verification failed for field %r (%s); treating as unsupported.",
            field.field_id, exc,
        )
        return LLMVerificationResult(
            supported=False, confidence=0.0,
            explanation=f"LLM verification call failed or returned an unparseable response: {exc}",
        )
