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

The adjuster must also name which document they actually found the value
in (source_document_id). That's stored on the FieldVerification
(adjuster_source_doc_id) rather than discarded after the request --
comparing it against the model's own evidence_block_ids later is exactly
the kind of signal that shows where extraction is looking in the wrong
place, which is the whole point of collecting it.

Triage is deterministic (agents/triage_agent.py has no LLM calls in its
own logic), so it's cheap to re-run synchronously after every override --
a claim that was HIGH_RISK_INCOMPLETE because of one bad field should
stop being high-risk the moment that field is fixed, not stay stuck at
its pipeline-time verdict for the rest of the review.
"""

from __future__ import annotations

from pydantic import BaseModel

from fastapi import APIRouter, Depends, HTTPException

from agents.human_review_queue import build_review_queue, summarize_review_queue
from agents.triage_agent import apply_triage_to_claim
from app.deps import get_store
from core.schemas import FieldVerification, MatchMethod, RiskLevel
from core.store import AdjusterDecision, ClaimNotFoundError, ClaimStore

router = APIRouter(prefix="/api/claims", tags=["review"])


class FieldOverrideRequest(BaseModel):
    value: str
    source_document_id: str
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

    if not any(d.doc_id == body.source_document_id for d in claim.documents):
        raise HTTPException(
            status_code=422,
            detail=f"source_document_id {body.source_document_id!r} is not one of this claim's documents.",
        )

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
        reasons=[
            f"Adjuster manually reviewed and overrode this field's value, "
            f"citing document {body.source_document_id!r} as the source."
        ],
        crop_paths=existing_crop_paths,
        adjuster_source_doc_id=body.source_document_id,
    )

    # Re-derive the review queue and re-run triage now that this field no
    # longer needs review -- keeps the review page, the Dashboard's tier/
    # score, and the review queue counts all in sync with the override
    # without a full pipeline re-run (triage has no LLM calls, so this is
    # free to do synchronously on every override).
    review_queue = build_review_queue(claim)
    record.review_queue = review_queue
    record.review_queue_counts = summarize_review_queue(review_queue)
    apply_triage_to_claim(claim)

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
