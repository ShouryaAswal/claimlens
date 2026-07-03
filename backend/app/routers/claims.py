"""
app/routers/claims.py
------------------------
POST /api/claims          -- upload files, kick off the pipeline, return
                              {claim_id} immediately (Sprint 5 plan: "Returns
                              claim_id immediately", not once processing
                              finishes).
GET  /api/claims           -- list every claim, summarized for the
                              Dashboard (KPI cards, risk chart, claims table).
GET  /api/claims/{claim_id} -- the full ClaimRecord for the review page.
"""

from __future__ import annotations

import logging
import shutil
import tempfile
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile

from agents.evidence_verifier import _extract_numeric_candidates
from agents.reviewer_summary_agent import build_completion_stats
from agents.triage_agent import PRIMARY_AMOUNT_FIELD_BY_LOB
from app.deps import get_store
from app.sse import publish
from core.pipeline import run_pipeline
from core.store import ClaimNotFoundError, ClaimStore, PipelineStatus

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/claims", tags=["claims"])

# OS/filesystem noise that folder uploads commonly drag in -- not a real
# claim document, so it's dropped before it ever reaches the pipeline
# rather than showing up as a confusing "INGESTION FAILED" entry.
_JUNK_FILENAMES = {".ds_store", "thumbs.db", "desktop.ini"}


def _is_junk_upload(filename: str) -> bool:
    name = Path(filename).name.lower()
    return name in _JUNK_FILENAMES or name.startswith("._")


def _save_uploads_to_temp(claim_id: str, files: list[UploadFile]) -> list[str]:
    """agents.ingestion.dispatcher.ingest() takes local file paths (or
    URLs), not in-memory bytes -- so uploaded files are written to a temp
    directory first, then handed off to the pipeline as a list of paths.
    The temp dir is namespaced by claim_id and left in place (not cleaned
    up) since agents/provenance_agent.py re-opens the ORIGINAL source file
    to render crops later in the pipeline -- deleting it after ingestion
    would break crop generation for every PDF/image block.

    Folder uploads (frontend sends each file's name as its
    webkitRelativePath, e.g. "evidence/photo1.jpg") are preserved as
    nested directories under upload_root rather than flattened to a bare
    filename. Flattening would silently overwrite one file with another
    of the same name from a different subfolder -- a real, likely case
    for a claim packet with fnol/, evidence/, correspondence/ each
    containing their own "notes.docx" or "photo1.jpg".
    """
    upload_root = Path(tempfile.gettempdir()) / "claimlens_uploads" / claim_id
    upload_root.mkdir(parents=True, exist_ok=True)
    saved_paths: list[str] = []
    for f in files:
        # An uploaded filename (which may carry a relative path for
        # folder uploads) is untrusted input -- strip any ".."/absolute
        # components before joining it onto upload_root, then recreate
        # only the remaining subdirectory structure.
        raw_name = f.filename or "upload"
        rel_parts = [
            part for part in Path(raw_name).parts
            if part not in ("", ".", "..") and not Path(part).is_absolute()
        ]
        safe_rel_path = Path(*rel_parts) if rel_parts else Path("upload")
        dest = upload_root / safe_rel_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        # Two different claims' folders can legitimately both contain
        # e.g. "evidence/photo1.jpg" flattened from unrelated top-level
        # folder names the browser doesn't expose -- so still guard
        # against a same-claim, same-relative-path collision explicitly
        # rather than silently overwriting.
        if dest.exists():
            dest = dest.with_name(f"{uuid.uuid4().hex[:6]}_{dest.name}")
        with dest.open("wb") as out:
            shutil.copyfileobj(f.file, out)
        saved_paths.append(str(dest))
    return saved_paths


def _run_pipeline_and_publish(store: ClaimStore, sources: list[str], claim_id: str) -> None:
    """The BackgroundTasks target. `on_stage` publishes each event to any
    connected SSE client (app/sse.py) as the pipeline runs."""
    def on_stage(event: dict) -> None:
        publish(claim_id, event)

    run_pipeline(store, sources, claim_id=claim_id, on_stage=on_stage)


@router.post("")
async def create_claim(
    background_tasks: BackgroundTasks,
    files: list[UploadFile],
    store: ClaimStore = Depends(get_store),
) -> dict:
    files = [f for f in files if not _is_junk_upload(f.filename or "")]
    if not files:
        raise HTTPException(status_code=400, detail="At least one file is required.")

    claim_id = f"CLM-{uuid.uuid4().hex[:8]}"
    sources = _save_uploads_to_temp(claim_id, files)

    background_tasks.add_task(_run_pipeline_and_publish, store, sources, claim_id)
    return {"claim_id": claim_id}


@router.get("")
def list_claims(store: ClaimStore = Depends(get_store)) -> list[dict]:
    """Dashboard-facing summary -- one row per claim, everything
    KpiCards/RiskDistributionChart/ClaimsTable need without each having to
    fetch and re-derive it from the full record."""
    summaries = []
    for record in store.list_all():
        claim = record.claim
        completion = build_completion_stats(claim)
        amount_field_id = PRIMARY_AMOUNT_FIELD_BY_LOB.get(claim.lob) if claim.lob else None
        amount_field = claim.extracted_fields.get(amount_field_id) if amount_field_id else None
        primary_amount = None
        if amount_field is not None and amount_field.value is not None:
            candidates = _extract_numeric_candidates(amount_field.value)
            if candidates:
                primary_amount = float(candidates[0])

        summaries.append({
            "claim_id": claim.claim_id,
            "lob": claim.lob.value if claim.lob else None,
            "status": record.status.value,
            "adjuster_decision": record.adjuster_decision.value,
            "tier": claim.triage.tier.value if claim.triage else None,
            "score": claim.triage.score if claim.triage else None,
            "forced_review": claim.triage.forced_review if claim.triage else None,
            "completion": completion,
            "primary_amount": primary_amount,
            "doc_count": len(claim.documents),
            "created_at": claim.created_at.isoformat(),
            "updated_at": record.updated_at.isoformat(),
        })
    return summaries


@router.get("/{claim_id}")
def get_claim(claim_id: str, store: ClaimStore = Depends(get_store)) -> dict:
    try:
        record = store.get(claim_id)
    except ClaimNotFoundError:
        raise HTTPException(status_code=404, detail=f"No claim found with id {claim_id!r}")
    return record.model_dump(mode="json")
