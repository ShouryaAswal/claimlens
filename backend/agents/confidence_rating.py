"""
agents/confidence_rating.py
---------------------------------
Combines evidence_verifier.py's match result, the cited evidence's own OCR
confidence, the extraction agent's self-reported confidence, and (optionally)
llm_evidence_verifier.py's semantic second opinion into one final
FieldVerification: a risk_level and a requires_human_review flag a future
reviewer UI (and, before that, the triage agent) can act on directly.

THE NON-NEGOTIABLE SAFETY RULE, stated once here and enforced in code below:

For critical field types (number/date/code), a deterministic exact-match
FAILURE is final. An LLM second opinion can ESCALATE a field that the
deterministic check passed (catches semantic issues the exact-match
check can't see), but it can NEVER downgrade/override a deterministic
critical-field failure back to "fine". If the cited evidence does not
contain the exact number/date/code, the field is high_risk, period --
no amount of LLM-reported confidence changes that. This is the literal
implementation of "even a single digit error must be fatal."

Why OCR confidence is checked even when the text matches: an exact text
match only proves consistency with whatever OCR produced -- if OCR itself
misread the source page with low confidence, the underlying real document
could say something different from what OCR (and therefore our match
check) saw. Low OCR confidence on a critical field's evidence is grounds
for human review even when everything else lines up.
"""

from __future__ import annotations

import logging
from statistics import mean

from agents.evidence_verifier import CRITICAL_FIELD_TYPES, verify_field
from agents.llm_evidence_verifier import llm_verify_field
from core.llm_client import LLMClient
from core.schemas import (
    ClaimState,
    ExtractedField,
    FieldDefinition,
    FieldVerification,
    MatchMethod,
    RiskLevel,
)

logger = logging.getLogger(__name__)

# Below this OCR confidence, even an exact-matching critical field gets
# flagged for review -- the source scan itself may be unreliable in ways
# that happen to still produce a matching string.
LOW_OCR_CONFIDENCE_THRESHOLD = 0.6

# Below this composite score, a text/boolean field is flagged for review.
TEXT_COMPOSITE_REVIEW_THRESHOLD = 0.5


def rate_field(
    field: ExtractedField,
    field_def: FieldDefinition,
    claim: ClaimState,
    llm_client: LLMClient | None = None,
    force_llm_check: bool = False,
) -> FieldVerification:
    """The main entry point. `llm_client`/`force_llm_check` are optional --
    without them this runs purely deterministically. With them, the LLM
    second-opinion runs on any field the deterministic check didn't fully
    clear (or on every field, if force_llm_check=True), and can escalate
    risk but never silences a critical-field exact-match failure."""
    match_result = verify_field(field, field_def, claim)
    blocks = [b for bid in field.evidence_block_ids if (b := claim.get_block(bid)) is not None]
    ocr_confidence_avg = round(mean(b.confidence for b in blocks), 4) if blocks else 0.0
    llm_confidence = round(field.confidence, 4)
    is_critical = field_def.field_type in CRITICAL_FIELD_TYPES
    reasons: list[str] = []
    llm_verification = None

    if field.status == "conflicting":
        # Always HIGH_RISK. A confirmed conflict between two documents on a
        # critical value is worse than a missing field -- it means we have
        # actively contradictory evidence, not an absence of evidence. Must
        # be checked BEFORE the missing/value-is-None branch below, since
        # merge_agent.merge_candidates() sets value=None on a conflicting
        # field -- without this branch first, a conflicting optional field
        # would silently fall into the "missing" branch and come out OK.
        risk = RiskLevel.HIGH_RISK
        composite = 0.0
        requires_human = True
        reasons.append(f"CONFLICTING values detected across cited evidence: {field.reason}")

    elif field.status == "missing" or field.value is None:
        risk = RiskLevel.NEEDS_REVIEW if field_def.required else RiskLevel.OK
        composite = 0.0
        requires_human = field_def.required
        reasons.append(
            "Field was not found in the claim corpus."
            + (" This is a REQUIRED field." if field_def.required else " This is an optional field.")
        )

    elif match_result.method == MatchMethod.NO_EVIDENCE:
        risk = RiskLevel.HIGH_RISK
        composite = 0.0
        requires_human = True
        reasons.append(match_result.reason)

    elif is_critical and not match_result.matched:
        # THE rule: exact-match failure on a critical field is final.
        risk = RiskLevel.HIGH_RISK
        composite = 0.0
        requires_human = True
        reasons.append(match_result.reason)

    elif is_critical:  # matched
        if ocr_confidence_avg < LOW_OCR_CONFIDENCE_THRESHOLD:
            risk = RiskLevel.NEEDS_REVIEW
            composite = round(ocr_confidence_avg * llm_confidence, 4)
            requires_human = True
            reasons.append(
                f"Value matches cited evidence exactly, but that evidence's OCR "
                f"confidence is low ({ocr_confidence_avg:.2f}) -- the source scan "
                f"itself may be unreliable. Recommend visual confirmation."
            )
        else:
            risk = RiskLevel.OK
            composite = round(min(ocr_confidence_avg, llm_confidence, 1.0), 4)
            requires_human = False
            reasons.append(match_result.reason)

    else:  # text / boolean
        composite = round(llm_confidence * ocr_confidence_avg * match_result.score, 4)
        if not match_result.matched or composite < TEXT_COMPOSITE_REVIEW_THRESHOLD:
            risk = RiskLevel.NEEDS_REVIEW
            requires_human = True
        else:
            risk = RiskLevel.OK
            requires_human = False
        reasons.append(match_result.reason)

    # Optional LLM second opinion: runs when explicitly forced, or
    # automatically on anything the deterministic pass didn't fully clear.
    # Never invoked for fields with no value/no evidence -- nothing to ask.
    if llm_client is not None and blocks and field.value is not None and (force_llm_check or risk != RiskLevel.OK):
        llm_result = llm_verify_field(field, field_def, blocks, llm_client)
        llm_verification = llm_result

        if not llm_result.supported and risk == RiskLevel.OK:
            # LLM caught something the string-level check couldn't --
            # escalate, never silently ignore a dissenting second opinion.
            risk = RiskLevel.NEEDS_REVIEW
            requires_human = True
            reasons.append(f"LLM second-opinion check disagreed: {llm_result.explanation}")
        elif llm_result.supported and risk == RiskLevel.HIGH_RISK and is_critical:
            # Explicitly NOT overriding -- logged so it's visible in review,
            # but the deterministic failure stands.
            reasons.append(
                f"Note: LLM second opinion suggested support ({llm_result.explanation}), "
                f"but an exact-match failure on a critical field type is not "
                f"overridden by an LLM opinion. Remains high_risk."
            )
        elif llm_result.supported and risk == RiskLevel.NEEDS_REVIEW and not is_critical:
            reasons.append(f"LLM second-opinion check confirmed support: {llm_result.explanation}")

    return FieldVerification(
        field_id=field.field_id,
        match_method=match_result.method,
        match_score=match_result.score,
        ocr_confidence_avg=ocr_confidence_avg,
        llm_confidence=llm_confidence,
        composite_confidence=composite,
        risk_level=risk,
        requires_human_review=requires_human,
        reasons=reasons,
        llm_verification=llm_verification,
    )


def rate_all_fields(
    claim: ClaimState,
    llm_client: LLMClient | None = None,
    force_llm_check: bool = False,
) -> dict[str, FieldVerification]:
    """Rates every extracted field on the claim and writes the results onto
    claim.field_verifications (the field scaffolded for exactly this)."""
    if claim.lob_schema is None:
        raise ValueError(f"ClaimState {claim.claim_id!r} has no lob_schema resolved.")

    field_defs = {f.field_id: f for f in claim.lob_schema.all_fields}
    results: dict[str, FieldVerification] = {}

    for field_id, field in claim.extracted_fields.items():
        field_def = field_defs.get(field_id)
        if field_def is None:
            logger.warning("Extracted field %r has no matching schema definition; skipping rating.", field_id)
            continue
        results[field_id] = rate_field(field, field_def, claim, llm_client=llm_client, force_llm_check=force_llm_check)

    claim.field_verifications = results
    high_risk_count = sum(1 for r in results.values() if r.risk_level == RiskLevel.HIGH_RISK)
    if high_risk_count:
        logger.warning("Claim %r: %d field(s) rated HIGH_RISK after verification.", claim.claim_id, high_risk_count)
    return results
