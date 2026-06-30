"""
agents/triage_agent.py
---------------------------
Sprint 4's first agent. Combines everything Sprints 1-3 produced into one
routing decision: straight-through processing (STP) candidate, needs human
review, or high-risk/incomplete.

THE RULE THAT MATTERS MOST: a HIGH_RISK verification result on a REQUIRED
field forces human review outright, regardless of how good the rest of the
composite score looks. `forced_review=True` makes this explicit -- it is
the literal continuation of Sprint 3's "an LLM agreeing cannot override a
deterministic critical-field failure" rule, one layer up: now a good
triage SCORE cannot override it either. A claim cannot be auto-approved
for STP because nine fields are perfect if the tenth is a wrong dollar
amount.

Deterministic, rule-based -- once the inputs (Gate Check results,
field_verifications, the extracted amount field) already exist, there's
nothing here that genuinely needs an LLM call. The reviewer summary agent
(also Sprint 4) elaborates these reasons into prose, and DOES use an LLM.
"""

from __future__ import annotations

import logging
from decimal import Decimal

from agents.evidence_verifier import _extract_numeric_candidates
from core.schemas import ClaimState, LOB, RiskLevel, TriageTier, TriageVerdict

logger = logging.getLogger(__name__)

POINTS_MISSING_MANDATORY_DOC = 20
POINTS_HIGH_RISK_FIELD = 40
POINTS_NEEDS_REVIEW_REQUIRED_FIELD = 15
POINTS_NEEDS_REVIEW_OPTIONAL_FIELD = 8
POINTS_HIGH_VALUE_CLAIM = 15

STP_MAX_SCORE = 25
NEEDS_REVIEW_MAX_SCORE = 60

# Which schema field represents "the claim amount" differs per LOB -- an
# explicit lookup, not a guess based on field-name pattern matching.
PRIMARY_AMOUNT_FIELD_BY_LOB: dict[LOB, str] = {
    LOB.AUTO: "repair_estimate_amount",
    LOB.PROPERTY: "probable_amount_of_loss",
    LOB.HEALTH: "billed_amount",
}

# Illustrative thresholds -- a real deployment would tune these against
# actual loss-cost data per LOB, not a guess.
HIGH_VALUE_THRESHOLD_BY_LOB: dict[LOB, Decimal] = {
    LOB.AUTO: Decimal("10000"),
    LOB.PROPERTY: Decimal("25000"),
    LOB.HEALTH: Decimal("15000"),
}


def _tier_for_score(score: int) -> TriageTier:
    if score <= STP_MAX_SCORE:
        return TriageTier.STP_CANDIDATE
    if score <= NEEDS_REVIEW_MAX_SCORE:
        return TriageTier.NEEDS_REVIEW
    return TriageTier.HIGH_RISK_INCOMPLETE


def _check_high_value_claim(claim: ClaimState) -> tuple[int, list[str]]:
    if claim.lob is None:
        return 0, []
    amount_field_id = PRIMARY_AMOUNT_FIELD_BY_LOB.get(claim.lob)
    threshold = HIGH_VALUE_THRESHOLD_BY_LOB.get(claim.lob)
    if amount_field_id is None or threshold is None:
        return 0, []

    extracted = claim.extracted_fields.get(amount_field_id)
    if extracted is None or extracted.value is None:
        return 0, []

    candidates = _extract_numeric_candidates(extracted.value)
    if not candidates:
        return 0, []
    amount = candidates[0]

    if amount >= threshold:
        return POINTS_HIGH_VALUE_CLAIM, [
            f"Claim amount {amount} meets or exceeds the {claim.lob.value} "
            f"high-value threshold ({threshold}) -- recommend senior/extra review."
        ]
    return 0, []


def compute_triage(claim: ClaimState) -> TriageVerdict:
    """Requires Gate Check (Sprint 2) and confidence_rating.rate_all_fields()
    (Sprint 3) to have already run -- this agent consumes their results,
    it doesn't recompute either."""
    score = 0
    reasons: list[str] = []
    forced_review = False
    high_risk_field_ids: list[str] = []

    field_defs = {f.field_id: f for f in claim.lob_schema.all_fields} if claim.lob_schema else {}

    for doc_type in claim.missing_mandatory_docs:
        score += POINTS_MISSING_MANDATORY_DOC
        reasons.append(f"Missing mandatory document type: {doc_type!r}.")

    for field_id, verification in claim.field_verifications.items():
        field_def = field_defs.get(field_id)
        label = field_def.label if field_def else field_id
        is_required = bool(field_def and field_def.required)

        if verification.risk_level == RiskLevel.HIGH_RISK:
            score += POINTS_HIGH_RISK_FIELD
            high_risk_field_ids.append(field_id)
            reason_detail = verification.reasons[0] if verification.reasons else "flagged high-risk."
            reasons.append(f"{label}: HIGH RISK -- {reason_detail}")
            if is_required:
                forced_review = True
                reasons.append(
                    f"{label} is a REQUIRED field and failed verification -- "
                    f"forcing human review regardless of composite score."
                )
        elif verification.risk_level == RiskLevel.NEEDS_REVIEW:
            score += POINTS_NEEDS_REVIEW_REQUIRED_FIELD if is_required else POINTS_NEEDS_REVIEW_OPTIONAL_FIELD
            reason_detail = verification.reasons[0] if verification.reasons else "needs review."
            reasons.append(f"{label}: needs review -- {reason_detail}")

    value_points, value_reasons = _check_high_value_claim(claim)
    score += value_points
    reasons.extend(value_reasons)

    tier = _tier_for_score(score)
    if forced_review and tier == TriageTier.STP_CANDIDATE:
        tier = TriageTier.NEEDS_REVIEW

    if not reasons:
        reasons.append("No issues detected: all required fields verified, no missing mandatory documents.")

    logger.info(
        "Triage for claim %r: tier=%s score=%d forced_review=%s (%d high-risk field(s))",
        claim.claim_id, tier.value, score, forced_review, len(high_risk_field_ids),
    )

    return TriageVerdict(
        tier=tier, score=score, forced_review=forced_review,
        reasons=reasons, high_risk_field_ids=high_risk_field_ids,
    )


def apply_triage_to_claim(claim: ClaimState) -> TriageVerdict:
    """Convenience wrapper, same pattern as Gate Check's
    apply_gate_check_to_claim() -- computes and writes back onto
    claim.triage in one call."""
    verdict = compute_triage(claim)
    claim.triage = verdict
    return verdict
