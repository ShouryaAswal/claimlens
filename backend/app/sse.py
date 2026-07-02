"""
app/sse.py
-----------
SSE event formatting, plus a tiny in-process pub/sub broker.

Why a broker is needed at all: core/pipeline.py runs as a FastAPI
BackgroundTask, which Starlette executes in a worker thread (since
run_pipeline is a plain sync function, not a coroutine) -- so its
`on_stage` callback fires from a different thread than the one running
the async SSE generator in app/routers/stream.py. A plain thread-safe
`queue.Queue` per claim_id bridges the two: pipeline.py's worker thread
calls `publish()` (a simple, non-blocking put), and the SSE endpoint's
async generator offloads the blocking `queue.get()` to the thread pool via
Starlette's `run_in_threadpool` so it never blocks the event loop for
other concurrently-connected clients.

Known limitation (fine for an MVP demo, worth knowing about): if a client
opens the SSE stream a moment after POST /api/claims returns, any events
published before it subscribed are missed (dropped, not buffered) --
GET /api/claims/{id} always returns the full current state as a fallback,
so nothing is unrecoverable, but a client that wants a gapless progress
bar should open the stream immediately after the POST response arrives.
"""

from __future__ import annotations

import json
import queue
import threading
from typing import Any

# Sentinel put on a claim's queue to signal "pipeline finished" so the SSE
# generator knows to close the stream instead of polling forever.
_SENTINEL = object()

_lock = threading.Lock()
_subscribers: dict[str, list[queue.Queue]] = {}


def format_sse(event: dict) -> str:
    """Formats one stage event as a single SSE `data:` line. Every event
    emitted by core/pipeline.py already has the shape
    {"stage": ..., "status": ..., "detail": {...}} -- see the SSE event
    list in docs/SPRINT_5_NOTES.md / the Sprint 5 plan."""
    return f"data: {json.dumps(event)}\n\n"


def subscribe(claim_id: str) -> queue.Queue:
    """Registers a new listener queue for a claim_id. Call once per SSE
    client connection; always pair with unsubscribe() in a `finally`
    block so a disconnected client doesn't leak a queue forever."""
    q: queue.Queue = queue.Queue()
    with _lock:
        _subscribers.setdefault(claim_id, []).append(q)
    return q


def unsubscribe(claim_id: str, q: queue.Queue) -> None:
    with _lock:
        listeners = _subscribers.get(claim_id, [])
        if q in listeners:
            listeners.remove(q)
        if not listeners:
            _subscribers.pop(claim_id, None)


def publish(claim_id: str, event: dict) -> None:
    """Called from core/pipeline.py's on_stage callback. Fans the event
    out to every currently-connected SSE client for this claim_id. If
    nobody is listening yet, the event is simply dropped (see the module
    docstring's known limitation)."""
    with _lock:
        listeners = list(_subscribers.get(claim_id, []))
    for q in listeners:
        q.put(event)
    if event.get("stage") == "pipeline" and event.get("status") in ("done", "error"):
        for q in listeners:
            q.put(_SENTINEL)


def is_sentinel(item: Any) -> bool:
    return item is _SENTINEL
