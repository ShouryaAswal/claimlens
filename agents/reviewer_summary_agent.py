"""
agents/reviewer_summary_agent.py
--------------------------------------
Sprint 4's second agent, and the second of ClaimLens's two original
deliverables (design doc, section "What's Special"): a short,
adjuster-readable brief, on top of the filled-schema/completion-stats view
the rest of the pipeline already produces.

Two modes, same pattern as every other LLM-touching agent in this project:
  - Rule-based (default, always available): a template that turns
    completion stats + the triage verdict + the human review queue into
    plain-text sentences. No API key needed, fully deterministic, and
    NEVER invents a fact -- every sentence is a direct readout of numbers
    already computed elsewhere.
  - LLM-backed (opt-in): asks an LLM to write the same content in smoother
    prose. Explicitly instructed not to invent facts beyond what's given,
    and -- same resilience pattern as every other LLM call in this
    project -- falls back to the rule-based template if the call fails or
    returns something unusable, rather than producing no summary at all.
"""

from __future__ import annotations

import logging

from core.llm_client import LLMClient
from core.schemas import ClaimState, ReviewQueueItem, TriageVerdict

logger = logging.getLogger(__name__)


def build_completion_stats(claim: ClaimState) -> dict:
    """A small, self-contained dict -- used by both summary modes and
    available independently for a UI to render as a progress bar/stat
    card without needing to recompute anything."""
    if claim.lob_schema is None:
        return {
            "total_fields": 0, "fields_found": 0,
            "required_fields": 0, "required_fields_found": 0,
        }

    all_fields = claim.lob_schema.all_fields
    required_fields = claim.lob_schema.required_fields
    found_ids = {fid for fid, f in claim.extracted_fields.items() if f.status == "found"}

    return {
        "total_fields": len(all_fields),
        "fields_found": len(found_ids),
        "required_fields": len(required_fields),
        "required_fields_found": sum(1 for f in required_fields if f.field_id in found_ids),
    }


def generate_summary_rule_based(
    claim: ClaimState,
    completion_stats: dict,
    triage_verdict: TriageVerdict,
    review_queue: list[ReviewQueueItem],
) -> str:
    """Deterministic template. Every line is a direct readout of an
    already-computed number or reason string -- nothing here is invented,
    which is exactly why this mode never needs a disclaimer about
    hallucination the way the LLM mode does."""
    lines: list[str] = []

    lob_label = claim.lob.value.upper() if claim.lob else "UNKNOWN"
    lines.append(
        f"Claim {claim.claim_id} ({lob_label}): "
        f"{completion_stats['fields_found']}/{completion_stats['total_fields']} fields extracted "
        f"({completion_stats['required_fields_found']}/{completion_stats['required_fields']} required fields found)."
    )

    if claim.missing_mandatory_docs:
        lines.append(f"Missing mandatory documents: {', '.join(claim.missing_mandatory_docs)}.")
    else:
        lines.append("All mandatory document types are present.")

    tier_label = triage_verdict.tier.value.replace("_", " ").upper()
    lines.append(f"Triage verdict: {tier_label} (composite score {triage_verdict.score}).")

    if triage_verdict.forced_review:
        lines.append(
            "NOTE: Routed to human review because a REQUIRED field failed evidence "
            "verification (exact-match failure on a critical value) -- this overrides "
            "the composite score; the claim cannot be auto-approved for straight-through "
            "processing regardless of how clean the rest of it looks."
        )

    if review_queue:
        lines.append(f"{len(review_queue)} field(s) flagged for review, highest priority first:")
        for item in review_queue[:5]:
            reason = item.reasons[0] if item.reasons else "flagged for review"
            lines.append(f"  - [{item.risk_level.value.upper()}] {item.field_label} = {item.value!r}: {reason}")
        if len(review_queue) > 5:
            lines.append(f"  ... and {len(review_queue) - 5} more (see the full review queue).")
    else:
        lines.append("No fields flagged for review.")

    return "\n".join(lines)


_LLM_SYSTEM_PROMPT = """You are an insurance claims intake assistant writing
a short brief for a human adjuster who is about to review this claim.

You will be given: completion statistics, a triage verdict with its
composite score and reasons, and a list of flagged fields needing review
(each with its value, risk level, and reason).

Write a clear, professional brief in 4-8 sentences of plain prose (no
markdown headers, a short bulleted list of flagged fields is fine if there
are several). Do NOT invent any fact, number, or field that isn't
explicitly given to you below -- if something isn't in the data, don't
mention it. If the triage verdict shows forced_review=true, make sure your
very first or second sentence calls that out clearly, since it means this
claim cannot go straight-through no matter how clean the rest looks.
"""


def _format_llm_prompt(
    claim: ClaimState,
    completion_stats: dict,
    triage_verdict: TriageVerdict,
    review_queue: list[ReviewQueueItem],
) -> str:
    lines = [
        f"Claim ID: {claim.claim_id}",
        f"Line of Business: {claim.lob.value if claim.lob else 'unknown'}",
        f"Completion: {completion_stats['fields_found']}/{completion_stats['total_fields']} fields found "
        f"({completion_stats['required_fields_found']}/{completion_stats['required_fields']} required).",
        f"Missing mandatory documents: {claim.missing_mandatory_docs or 'none'}",
        f"Triage tier: {triage_verdict.tier.value}",
        f"Triage score: {triage_verdict.score}",
        f"Forced review (required field failed verification): {triage_verdict.forced_review}",
        f"Triage reasons: {triage_verdict.reasons}",
        "Flagged fields for review:",
    ]
    if not review_queue:
        lines.append("  (none)")
    for item in review_queue:
        lines.append(
            f"  - field={item.field_label!r} value={item.value!r} "
            f"risk={item.risk_level.value} reasons={item.reasons}"
        )
    return "\n".join(lines)


def generate_summary_with_llm(
    claim: ClaimState,
    completion_stats: dict,
    triage_verdict: TriageVerdict,
    review_queue: list[ReviewQueueItem],
    llm_client: LLMClient,
) -> str:
    prompt = _format_llm_prompt(claim, completion_stats, triage_verdict, review_queue)
    # The reviewer summary is free-text prose, not JSON -- complete()
    # returns it as-is, no parse_json_response() step needed here.
    summary = llm_client.complete(_LLM_SYSTEM_PROMPT, prompt)
    if not summary or not summary.strip():
        raise ValueError("LLM returned an empty summary.")
    return summary.strip()


def generate_reviewer_summary(
    claim: ClaimState,
    review_queue: list[ReviewQueueItem],
    llm_client: LLMClient | None = None,
) -> str:
    """The main entry point. Requires claim.triage to already be set
    (agents.triage_agent.apply_triage_to_claim()) -- raises a clear error
    rather than silently summarizing an unrouted claim."""
    if claim.triage is None:
        raise ValueError(
            f"ClaimState {claim.claim_id!r} has no triage verdict yet -- "
            f"run agents.triage_agent.apply_triage_to_claim() first."
        )

    completion_stats = build_completion_stats(claim)

    if llm_client is not None:
        try:
            return generate_summary_with_llm(claim, completion_stats, claim.triage, review_queue, llm_client)
        except Exception as exc:  # noqa: BLE001 - a flaky/empty LLM response must not leave the adjuster with nothing
            logger.warning(
                "LLM-backed reviewer summary failed (%s); falling back to the rule-based template.", exc,
            )

    return generate_summary_rule_based(claim, completion_stats, claim.triage, review_queue)
