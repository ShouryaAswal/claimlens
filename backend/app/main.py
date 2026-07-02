"""
app/main.py
-------------
FastAPI application entry point for ClaimLens. Run with:

    cd backend && uvicorn app.main:app --reload

(see start-backend.sh / start-backend.ps1 at the repo root).

Wires together:
- CORS, open to the Vite dev server (and configurable via
  CLAIMLENS_CORS_ORIGINS for anything else).
- A single `ClaimStore` on `app.state.store`, rehydrated from
  `backend/outputs/` at startup so a server restart doesn't lose claims
  that were already processed (or mid-pipeline) before it went down.
- The four routers: claims, stream, documents, review.
- A dedicated `/crops/{claim_id}/{filename}` route serving crop PNGs.
  Deliberately NOT a blanket `StaticFiles` mount over the whole
  `outputs/` directory -- that would also serve claim_state.json (and any
  future per-claim file) as a static download, which isn't intended to be
  public. This route only ever serves `outputs/{claim_id}/crops/*.png`.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from core.config import OUTPUTS_DIR
from core.store import ClaimStore

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    store = ClaimStore(OUTPUTS_DIR)
    recovered = store.rehydrate()
    app.state.store = store
    logger.info("ClaimLens API starting up. %d claim(s) rehydrated from %s.", recovered, OUTPUTS_DIR)
    yield
    logger.info("ClaimLens API shutting down.")


app = FastAPI(title="ClaimLens API", version="0.5.0", lifespan=lifespan)

_default_origins = "http://localhost:5173,http://127.0.0.1:5173"
_cors_origins = [
    o.strip() for o in os.environ.get("CLAIMLENS_CORS_ORIGINS", _default_origins).split(",") if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Blocks"],  # so app/routers/documents.py's bbox header is readable by fetch()
)


@app.get("/crops/{claim_id}/{filename}")
def get_crop(claim_id: str, filename: str) -> FileResponse:
    """Serves one crop PNG. `filename` is taken from
    FieldVerification.crop_paths, which core/pipeline.py already rewrites
    to exactly this URL shape after crop generation -- see
    core/pipeline.py's `_rewrite_crop_paths_to_urls`."""
    # Reject path traversal / anything that isn't a bare filename -- this
    # endpoint takes untrusted path segments directly from the URL.
    if "/" in filename or "\\" in filename or filename in (".", ".."):
        raise HTTPException(status_code=400, detail="Invalid filename.")
    if "/" in claim_id or "\\" in claim_id or claim_id in (".", ".."):
        raise HTTPException(status_code=400, detail="Invalid claim_id.")

    path = (OUTPUTS_DIR / claim_id / "crops" / filename).resolve()
    if OUTPUTS_DIR.resolve() not in path.parents or not path.exists():
        raise HTTPException(status_code=404, detail="Crop not found.")
    return FileResponse(path, media_type="image/png")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


from app.routers import claims, documents, review, stream  # noqa: E402 - after app is defined

app.include_router(claims.router)
app.include_router(stream.router)
app.include_router(documents.router)
app.include_router(review.router)
