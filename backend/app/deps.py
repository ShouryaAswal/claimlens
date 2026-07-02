"""
app/deps.py
-------------
Shared FastAPI dependencies. Just one for now: `get_store`, which reads
the single `ClaimStore` instance off `app.state` (created once at startup
in app/main.py's lifespan handler, rehydrated from disk there too) --
every router depends on this rather than constructing its own store, so
there's exactly one in-memory claim registry for the whole process.
"""

from __future__ import annotations

from fastapi import Request

from core.store import ClaimStore


def get_store(request: Request) -> ClaimStore:
    return request.app.state.store
