"""
core/pipeline.py
------------------
Sprint 5's orchestrator. Runs the full Sprint 0-4 agent chain end to end
for one claim, in the same order as scripts/run_sprint4_demo.py, plus two
things that script never did:

1. Actually wires agents/merge_agent.py in (see `_run_merge_stage` below)
   -- Sprint 0-4's demo scripts built merge_agent.py but never called it
   from the main pipeline. This is Day 1's "merge_agent is now a real
   pipeline stage" requirement.
2. Emits an `on_stage(stage, status, detail)` event after every step and
   checkpoints the claim to disk (via ClaimStore.save) after every step,
   so a client watching the SSE stream (app/routers/stream.py) sees live
   progress and a server crash mid-pipeline never loses more than the
   current stage's work.

No agent module is modified to support this (other than the Day 1 morning
confidence_rating.py fix) -- this file only calls the existing, tested
Sprint 0-4 functions in order.
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Callable, Optional

from agents.confidence_rating import rate_all_fields
from agents.doc_type_tagger_agent import tag_all_documents
from agents.gate_check import apply_gate_check_to_claim
from agents.human_review_queue import build_review_queue, summarize_review_queue
from agents.ingestion.dispatcher import ingest_many
from agents.lob_classifier_agent import classify_lob
from agents.merge_agent import detect_citation_conflicts
from agents.provenance_agent import generate_crops_for_claim
from agents.reviewer_summary_agent import generate_reviewer_summary
from agents.section_extraction_agent import extract_section
from agents.triage_agent import apply_triage_to_claim
from core.llm_client import LLMNotConfiguredError, get_llm_client
from core.schema_loader import load_lob_schema
from core.schemas import ClaimState, RiskLevel
from core.store import ClaimRecord, ClaimStore, PipelineStatus

logger = logging.getLogger(__name__)

# `on_stage` gets one dict per event: {"stage": str, "status": str, "detail": dict}
# -- this is exactly the shape app/routers/stream.py formats into an SSE `data:` line.
StageCallback = Callable[[dict], None]


def _emit(on_stage: Optional[StageCallback], stage: str, status: str, detail: Optional[dict] = None) -> None:
    if on_stage is None:
        return
    try:
        on_stage({"stage": stage, "status": status, "detail": detail or {}})
    except Exception:  # noqa: BLE001 - a broken listener must never abort the pipeline
        logger.exception("on_stage callback raised for stage=%s status=%s", stage, status)


def _run_merge_stage(claim: ClaimState) -> int:
    """Wires agents/merge_agent.py's `detect_citation_conflicts` into the
    pipeline as a real stage: for every extracted field, checks whether
    its cited evidence blocks actually agree with each other. A detected
    conflict marks the field status="conflicting" (value cleared to None,
    same convention merge_agent.merge_candidates() already uses) --
    confidence_rating.rate_field()'s new conflicting-status branch (Day 1
    morning fix) then always rates that HIGH_RISK and forces human review,
    regardless of whether the field happens to be optional.

    Returns the number of conflicts detected, for the `stage=merge`
    SSE event's `conflicts_detected` count.
    """
    if claim.lob_schema is None:
        return 0
    field_defs = {f.field_id: f for f in claim.lob_schema.all_fields}
    conflicts_detected = 0

    for field_id, field in claim.extracted_fields.items():
        field_def = field_defs.get(field_id)
        if field_def is None:
            continue
        report = detect_citation_conflicts(field, field_def, claim)
        if report.has_conflict:
            conflicts_detected += 1
            field.status = "conflicting"
            field.value = None
            field.reason = report.detail
            logger.warning(
                "Claim %r, field %r: citation conflict detected -- %s",
                claim.claim_id, field_id, report.detail,
            )

    return conflicts_detected


def _rewrite_crop_paths_to_urls(claim: ClaimState, claim_id: str) -> None:
    """generate_crops_for_claim() (agents/provenance_agent.py) writes real
    filesystem paths onto FieldVerification.crop_paths -- correct for a
    Python caller, useless to a browser. Rewrites them in place to the
    public URL the crop-serving route in app/main.py actually exposes:
    /crops/{claim_id}/{filename}.png. Must run AFTER crop generation and
    BEFORE agents.human_review_queue.build_review_queue(), since that
    function copies crop_paths verbatim from FieldVerification onto each
    ReviewQueueItem it builds."""
    for verification in claim.field_verifications.values():
        verification.crop_paths = [
            f"/crops/{claim_id}/{Path(p).name}" for p in verification.crop_paths
        ]


def run_pipeline(
    store: ClaimStore,
    sources: list[str],
    claim_id: Optional[str] = None,
    on_stage: Optional[StageCallback] = None,
) -> ClaimRecord:
    """Runs ingest -> classify -> resolve schema -> tag doc types ->
    gate check -> extract -> merge -> verify -> crops -> triage ->
    review queue -> summary, checkpointing to `store` after every stage.

    `sources` is a list of local file paths (already saved to disk by the
    caller -- see app/routers/claims.py, which writes uploaded files to a
    temp directory before calling this) and/or http(s) URLs.

    Returns the final ClaimRecord (also already saved in `store`). Raises
    nothing -- pipeline failures are caught, checkpointed as
    status=PipelineStatus.ERROR with the error message, and an
    `on_stage("pipeline", "error", {...})` event is emitted, matching the
    SSE contract in the Sprint 5 plan. This is deliberate: a background
    task with an uncaught exception just silently dies with no trace for
    a client watching the stream, which is worse than a clean error event.
    """
    claim_id = claim_id or f"CLM-{uuid.uuid4().hex[:8]}"
    record = ClaimRecord(claim=ClaimState(claim_id=claim_id))
    store.save(record)

    try:
        # -- 1. Ingest ---------------------------------------------------
        _emit(on_stage, "ingest", "start")
        documents = ingest_many(sources)
        record.claim.documents = documents
        total_blocks = sum(d.block_count for d in documents)
        store.save(record)
        _emit(on_stage, "ingest", "complete", {"doc_count": len(documents), "total_blocks": total_blocks})

        # -- 2. Classify LOB ----------------------------------------------
        _emit(on_stage, "classify", "start")
        groq_client = get_llm_client("groq")
        gemini_client = get_llm_client("gemini")
        full_text = "\n".join(d.full_text for d in documents)
        lob, lob_confidence = classify_lob(full_text, llm_client=groq_client)
        record.claim.lob = lob
        record.claim.lob_confidence = lob_confidence
        store.save(record)
        _emit(on_stage, "classify", "complete", {"lob": lob.value, "lob_confidence": lob_confidence})

        # -- 3. Schema resolution ------------------------------------------
        schema = load_lob_schema(lob)
        record.claim.lob_schema = schema
        store.save(record)
        _emit(on_stage, "schema_resolve", "complete",
              {"schema_name": schema.source_concept, "field_count": len(schema.all_fields)})

        # -- 4. Doc-type tagging -------------------------------------------
        tag_all_documents(documents, llm_client=groq_client)
        store.save(record)
        _emit(on_stage, "doc_type_tag", "complete",
              {"doc_types": [{"doc_id": d.doc_id, "doc_type": d.doc_type} for d in documents]})

        # -- 5. Gate Check ---------------------------------------------------
        gate_result = apply_gate_check_to_claim(record.claim)
        store.save(record)
        _emit(on_stage, "gate_check", "complete", {"missing_docs": gate_result.missing_doc_types})

        # -- 6. Section-wise extraction --------------------------------------
        _emit(on_stage, "extract", "start")
        if gemini_client is None:
            raise LLMNotConfiguredError(
                "Section extraction requires GOOGLE_API_KEY to be set (see backend/.env) -- "
                "there is no offline fallback for reading documents and extracting field values."
            )
        total_found = 0
        total_fields = 0
        for section in schema.sections:
            section_results = extract_section(section, record.claim, gemini_client)
            record.claim.extracted_fields.update(section_results)
            found = sum(1 for f in section_results.values() if f.status == "found")
            total_found += found
            total_fields += len(section_results)
            _emit(on_stage, "extract_section", "progress", {
                "section_id": section.section_id, "fields_found": found, "fields_total": len(section_results),
            })
        store.save(record)
        _emit(on_stage, "extract", "complete", {"total_found": total_found, "total_fields": total_fields})

        # -- 7. Merge / conflict detection -----------------------------------
        conflicts_detected = _run_merge_stage(record.claim)
        store.save(record)
        _emit(on_stage, "merge", "complete", {"conflicts_detected": conflicts_detected})

        # -- 8. Evidence verification + confidence rating ----------------------
        verifications = rate_all_fields(record.claim, llm_client=groq_client)
        verify_counts = {"ok": 0, "needs_review": 0, "high_risk": 0}
        for v in verifications.values():
            if v.risk_level == RiskLevel.OK:
                verify_counts["ok"] += 1
            elif v.risk_level == RiskLevel.NEEDS_REVIEW:
                verify_counts["needs_review"] += 1
            else:
                verify_counts["high_risk"] += 1
        store.save(record)
        _emit(on_stage, "verify", "complete", verify_counts)

        # -- 9. Crop generation ----------------------------------------------
        crop_paths = generate_crops_for_claim(record.claim, store.crops_dir(claim_id))
        _rewrite_crop_paths_to_urls(record.claim, claim_id)
        store.save(record)
        _emit(on_stage, "crops", "complete", {"crops_generated": len(crop_paths)})

        # -- 10. Triage --------------------------------------------------------
        triage_verdict = apply_triage_to_claim(record.claim)
        store.save(record)
        _emit(on_stage, "triage", "complete", {
            "tier": triage_verdict.tier.value, "score": triage_verdict.score,
            "forced_review": triage_verdict.forced_review,
        })

        # -- 11. Human review queue ----------------------------------------------
        review_queue = build_review_queue(record.claim)
        record.review_queue = review_queue
        record.review_queue_counts = summarize_review_queue(review_queue)

        # -- 12. Reviewer summary --------------------------------------------------
        record.summary = generate_reviewer_summary(record.claim, review_queue, llm_client=groq_client)
        record.status = PipelineStatus.COMPLETE
        store.save(record)
        _emit(on_stage, "summary", "complete")

        _emit(on_stage, "pipeline", "done", {"claim_id": claim_id})

    except Exception as exc:  # noqa: BLE001 - top-level pipeline boundary; must never crash silently
        logger.exception("Pipeline failed for claim %r", claim_id)
        record.status = PipelineStatus.ERROR
        record.error = str(exc)
        store.save(record)
        _emit(on_stage, "pipeline", "error", {"error": str(exc)})

    return record
