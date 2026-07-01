"""
agents/human_review_queue.py
----------------------------------
The basis for human-in-the-loop review (Sprint 5's reviewer UI consumes
this directly). Turns a claim's field_verifications into a flat,
self-contained list of ReviewQueueItem -- everything a human needs to make
a call on one flagged field without digging back through raw claim state.

Sort order is deliberate, not incidental: high_risk fields (wrong/
unverifiable critical values) come before needs_review fields (uncertain
but not actively contradicted), and within each tier, fields with NO
evidence at all come before fields that at least have a crop to look at --
a reviewer's limited attention should land on "this might be a hallucinated
number" before "this is probably fine but the scan was a bit blurry".
"""

from __future__ import annotations

from core.schemas import ClaimState, MatchMethod, ReviewQueueItem, RiskLevel

_RISK_SORT_ORDER = {RiskLevel.HIGH_RISK: 0, RiskLevel.NEEDS_REVIEW: 1, RiskLevel.OK: 2}
_NO_EVIDENCE_METHODS = {MatchMethod.NO_EVIDENCE}


def build_review_queue(claim: ClaimState, include_ok: bool = False) -> list[ReviewQueueItem]:
    """Builds the queue from claim.field_verifications (must already be
    populated by agents.confidence_rating.rate_all_fields()). By default
    only includes fields that actually need a human look -- pass
    include_ok=True to get a complete audit list instead."""
    if not claim.field_verifications:
        return []

    field_defs = {f.field_id: f for f in claim.lob_schema.all_fields} if claim.lob_schema else {}
    items: list[ReviewQueueItem] = []

    for field_id, verification in claim.field_verifications.items():
        if not include_ok and not verification.requires_human_review:
            continue

        field = claim.extracted_fields.get(field_id)
        field_def = field_defs.get(field_id)
        label = field_def.label if field_def else field_id

        items.append(
            ReviewQueueItem(
                claim_id=claim.claim_id,
                field_id=field_id,
                field_label=label,
                value=field.value if field else None,
                risk_level=verification.risk_level,
                reasons=verification.reasons,
                evidence_block_ids=field.evidence_block_ids if field else [],
                crop_paths=verification.crop_paths,
            )
        )

    items.sort(key=lambda item: (
        _RISK_SORT_ORDER.get(item.risk_level, 99),
        0 if not item.crop_paths else 1,
        item.field_id,
    ))
    return items


def summarize_review_queue(items: list[ReviewQueueItem]) -> dict[str, int]:
    """A quick rollup for a triage banner / report header -- "3 fields need
    review, 1 of them high-risk" rather than a human having to count."""
    return {
        "total": len(items),
        "high_risk": sum(1 for i in items if i.risk_level == RiskLevel.HIGH_RISK),
        "needs_review": sum(1 for i in items if i.risk_level == RiskLevel.NEEDS_REVIEW),
        "no_visual_evidence": sum(1 for i in items if not i.crop_paths),
    }
