"""
app/routers/review.py
-------------------------
POST /api/claims/{claim_id}/fields/{field_id}/override -- adjuster manual
    correction. Updates the field's value in-memory and redumps
    claim_state.json, per the Sprint 5 API surface table.
POST /api/claims/{claim_id}/approve  -- adjuster approves the claim.
POST /api/claims/{claim_id}/reject   -- adjuster rejects the claim.

An override is recorded as a human decision, not re-run through
confidence_rating.py -- an adjuster looking at the actual evidence and
typing the correct value IS the verification; there's nothing left for
the deterministic/LLM checks to re-adjudicate. The field's
FieldVerification is updated directly to reflect that a human resolved
it (risk_level -> OK, requires_human_review -> False), which is what lets
it drop off a re-rendered review queue instead of staying flagged forever.
"""

from __future__ import annotations

from pydantic import BaseModel

from fastapi import APIRouter, Depends, HTTPException

from agents.human_review_queue import build_review_queue, summarize_review_queue
from app.deps import get_store
from core.schemas import FieldVerification, MatchMethod, RiskLevel
from core.store import AdjusterDecision, ClaimNotFoundError, ClaimStore

router = APIRouter(prefix="/api/claims", tags=["review"])


class FieldOverrideRequest(BaseModel):
    value: str
    note: str | None = None


def _get_record_or_404(store: ClaimStore, claim_id: str):
    try:
        return store.get(claim_id)
    except ClaimNotFoundError:
        raise HTTPException(status_code=404, detail=f"No claim found with id {claim_id!r}")


@router.post("/{claim_id}/fields/{field_id}/override")
def override_field(
    claim_id: str,
    field_id: str,
    body: FieldOverrideRequest,
    store: ClaimStore = Depends(get_store),
) -> dict:
    record = _get_record_or_404(store, claim_id)
    claim = record.claim

    field = claim.extracted_fields.get(field_id)
    if field is None:
        raise HTTPException(status_code=404, detail=f"No extracted field {field_id!r} on claim {claim_id!r}")

    existing_crop_paths = (
        claim.field_verifications[field_id].crop_paths if field_id in claim.field_verifications else []
    )
    field.value = body.value
    field.status = "found"
    field.reason = "Manually overridden by adjuster." + (f" Note: {body.note}" if body.note else "")

    # No match_method fits "a human typed this after looking at the
    # evidence themselves" -- FUZZY_TEXT is the closest existing label
    # (not a numeric/date/code exactness claim); what actually matters is
    # risk_level=OK / requires_human_review=False, which is what lets this
    # field drop off a re-rendered review queue.
    claim.field_verifications[field_id] = FieldVerification(
        field_id=field_id,
        match_method=MatchMethod.FUZZY_TEXT,
        match_score=1.0,
        ocr_confidence_avg=1.0,
        llm_confidence=1.0,
        composite_confidence=1.0,
        risk_level=RiskLevel.OK,
        requires_human_review=False,
        reasons=["Adjuster manually reviewed and overrode this field's value."],
        crop_paths=existing_crop_paths,
    )

    # Re-derive the review queue and its counts now that this field no
    # longer needs review -- keeps the review page and Dashboard counts
    # in sync with the override without a full pipeline re-run.
    review_queue = build_review_queue(claim)
    record.review_queue = review_queue
    record.review_queue_counts = summarize_review_queue(review_queue)

    store.save(record)
    return record.model_dump(mode="json")


@router.post("/{claim_id}/approve")
def approve_claim(claim_id: str, store: ClaimStore = Depends(get_store)) -> dict:
    record = _get_record_or_404(store, claim_id)
    record.adjuster_decision = AdjusterDecision.APPROVED
    store.save(record)
    return record.model_dump(mode="json")


@router.post("/{claim_id}/reject")
def reject_claim(claim_id: str, store: ClaimStore = Depends(get_store)) -> dict:
    record = _get_record_or_404(store, claim_id)
    record.adjuster_decision = AdjusterDecision.REJECTED
    store.save(record)
    return record.model_dump(mode="json")
