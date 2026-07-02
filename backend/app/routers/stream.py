"""
app/routers/stream.py
-------------------------
GET /api/claims/{claim_id}/stream -- Server-Sent Events pipeline progress.

Each event is a `data: {...}` line, `{stage, status, detail}` -- see
core/pipeline.py's `_emit` calls for the full stage list (ingest, classify,
schema_resolve, doc_type_tag, gate_check, extract / extract_section,
merge, verify, crops, triage, summary, pipeline).

Subscribes to app/sse.py's broker for this claim_id, and blocks (off the
event loop, via run_in_threadpool) waiting for the next event until the
pipeline sends its terminal `stage=pipeline, status=done|error` event.
"""

from __future__ import annotations

import queue
from typing import AsyncIterator

from fastapi import APIRouter
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse

from app.sse import format_sse, is_sentinel, subscribe, unsubscribe

router = APIRouter(prefix="/api/claims", tags=["stream"])

# How long to block on queue.get() per poll -- short enough that the
# generator notices client disconnects promptly, long enough to not spin.
_POLL_TIMEOUT_SECONDS = 15.0


async def _event_generator(claim_id: str) -> AsyncIterator[str]:
    q = subscribe(claim_id)
    try:
        while True:
            try:
                item = await run_in_threadpool(q.get, True, _POLL_TIMEOUT_SECONDS)
            except queue.Empty:
                # Heartbeat -- keeps the connection alive through proxies/
                # load balancers that time out idle SSE connections, and
                # gives the generator a chance to notice a disconnect.
                yield ": keep-alive\n\n"
                continue
            if is_sentinel(item):
                break
            yield format_sse(item)
    finally:
        unsubscribe(claim_id, q)


@router.get("/{claim_id}/stream")
async def stream_claim_progress(claim_id: str) -> StreamingResponse:
    return StreamingResponse(
        _event_generator(claim_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # disable nginx buffering, if ever deployed behind one
        },
    )
