"""
core/store.py
----------------
Sprint 5's persistence layer.

``ClaimRecord`` wraps a Sprint 0-4 ``ClaimState`` with everything the new
API/UI layer needs that no earlier sprint needed: whether the pipeline is
still running or finished (and with what error, if any), the reviewer
summary prose, the human review queue, and the adjuster's approve/reject
decision. This is deliberately a wrapper, NOT new fields bolted onto
``ClaimState`` -- core/schemas.py is Sprint 0-4's contract, moved into
backend/ as-is per the Sprint 5 plan, and every agent from Sprints 0-4
still returns/consumes a plain ``ClaimState`` unmodified.

``ClaimStore`` is the single object the FastAPI app holds onto (see
app/deps.py) -- an in-memory dict for fast reads during a claim's
lifecycle, backed by a JSON dump on disk after every pipeline stage so a
server restart doesn't lose in-flight or completed claims.

Design notes:
- One file per claim: ``outputs/{claim_id}/claim_state.json`` (holds the
  full ClaimRecord, not just the bare ClaimState -- the filename is kept
  as `claim_state.json` per the Sprint 5 plan's directory layout, but the
  content is the full record so a restart recovers status/summary/review
  queue too, not just the underlying claim).
- ``save()`` writes atomically (write to a temp file, then os.replace) so a
  crash mid-write never leaves a half-written, unparseable claim_state.json
  behind -- important because this file is rewritten after EVERY pipeline
  stage, not just once at the end.
- ``rehydrate()`` is called once at FastAPI startup (see app/main.py) and
  walks outputs/*/claim_state.json, loading each back into
  ClaimRecord.model_validate(). A claim that was mid-pipeline when the
  server died comes back exactly as it last checkpointed -- status stays
  "processing", so the claims list can show it as such rather than losing
  track of it entirely.
- Deliberately NOT async / NOT a real database. For an MVP demo with a
  single adjuster hitting a handful of claims, an in-memory dict guarded
  by a single lock ("FastAPI is single-process") is the right amount of
  infrastructure. A real multi-adjuster deployment would swap this for
  Postgres + a real object store for crops -- noted here so it isn't
  mistaken for an oversight.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field

from core.schemas import ClaimState, ReviewQueueItem

logger = logging.getLogger(__name__)

CLAIM_STATE_FILENAME = "claim_state.json"


class ClaimNotFoundError(Exception):
    pass


class PipelineStatus(str, Enum):
    PROCESSING = "processing"
    COMPLETE = "complete"
    ERROR = "error"


class AdjusterDecision(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ClaimRecord(BaseModel):
    """The full Sprint 5 record for one claim: the Sprint 0-4 ClaimState
    plus everything the review UI and Dashboard need on top of it."""

    claim: ClaimState
    status: PipelineStatus = PipelineStatus.PROCESSING
    error: str | None = None
    summary: str | None = None
    review_queue: list[ReviewQueueItem] = Field(default_factory=list)
    review_queue_counts: dict[str, int] = Field(default_factory=dict)
    adjuster_decision: AdjusterDecision = AdjusterDecision.PENDING
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def claim_id(self) -> str:
        return self.claim.claim_id


class ClaimStore:
    """In-memory ClaimRecord registry, mirrored to disk under
    ``{outputs_dir}/{claim_id}/claim_state.json`` after every write."""

    def __init__(self, outputs_dir: Path) -> None:
        self.outputs_dir = Path(outputs_dir)
        self.outputs_dir.mkdir(parents=True, exist_ok=True)
        self._records: dict[str, ClaimRecord] = {}
        self._lock = threading.Lock()

    # -- paths ---------------------------------------------------------

    def claim_dir(self, claim_id: str) -> Path:
        return self.outputs_dir / claim_id

    def crops_dir(self, claim_id: str) -> Path:
        return self.claim_dir(claim_id) / "crops"

    def _state_path(self, claim_id: str) -> Path:
        return self.claim_dir(claim_id) / CLAIM_STATE_FILENAME

    # -- core operations -------------------------------------------------

    def save(self, record: ClaimRecord) -> None:
        """Writes the record to memory AND disk. Called after every
        pipeline stage (see core/pipeline.py) so
        outputs/{claim_id}/claim_state.json always reflects the most
        recently completed stage, and after any adjuster
        override/approve/reject in app/routers/review.py."""
        record.updated_at = datetime.now(timezone.utc)
        with self._lock:
            self._records[record.claim_id] = record
            claim_dir = self.claim_dir(record.claim_id)
            claim_dir.mkdir(parents=True, exist_ok=True)
            final_path = self._state_path(record.claim_id)
            tmp_path = final_path.with_suffix(".json.tmp")
            tmp_path.write_text(record.model_dump_json(indent=2), encoding="utf-8")
            os.replace(tmp_path, final_path)  # atomic on POSIX and Windows

    def get(self, claim_id: str) -> ClaimRecord:
        with self._lock:
            record = self._records.get(claim_id)
        if record is None:
            raise ClaimNotFoundError(f"No claim found with id {claim_id!r}")
        return record

    def get_or_none(self, claim_id: str) -> ClaimRecord | None:
        with self._lock:
            return self._records.get(claim_id)

    def list_all(self) -> list[ClaimRecord]:
        with self._lock:
            # Newest first -- most relevant to an adjuster/dashboard view.
            return sorted(self._records.values(), key=lambda r: r.claim.created_at, reverse=True)

    def exists(self, claim_id: str) -> bool:
        with self._lock:
            return claim_id in self._records

    # -- startup rehydration -----------------------------------------------

    def rehydrate(self) -> int:
        """Scans outputs_dir for every claim_state.json and loads it back
        into memory. Returns the number of claims recovered. Call once at
        FastAPI startup (see app/main.py's lifespan handler)."""
        recovered = 0
        if not self.outputs_dir.exists():
            return recovered

        for claim_dir in sorted(self.outputs_dir.iterdir()):
            if not claim_dir.is_dir():
                continue
            state_path = claim_dir / CLAIM_STATE_FILENAME
            if not state_path.exists():
                continue
            try:
                raw = json.loads(state_path.read_text(encoding="utf-8"))
                record = ClaimRecord.model_validate(raw)
            except Exception as exc:  # noqa: BLE001 - one bad file must not block the rest
                logger.error("Failed to rehydrate claim from %s: %s", state_path, exc)
                continue
            with self._lock:
                self._records[record.claim_id] = record
            recovered += 1

        if recovered:
            logger.info("Rehydrated %d claim(s) from %s", recovered, self.outputs_dir)
        return recovered
