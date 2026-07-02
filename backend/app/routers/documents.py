"""
app/routers/documents.py
----------------------------
GET /api/claims/{claim_id}/documents/{doc_id}/page/{page_number}

Renders one page of a source document as a raw PNG (so this URL can be
opened directly in a browser tab -- exactly what the Sprint 5 plan's end-
of-Day-1 checkpoint asks for: "open .../page/1 in a browser tab; manually
confirm the bbox_px coordinates in the response correspond to where the
title actually appears in the rendered image").

The per-block pixel-space bounding boxes travel alongside the image in an
`X-Blocks` response header (JSON: `[{"block_id": ..., "bbox_px": [x0,y0,x1,y1]}, ...]`),
rather than wrapping the image in a JSON/base64 envelope -- that keeps the
image byte-for-byte a real PNG (viewable directly, cacheable, no base64
inflation) while still letting the frontend's `fetch()` read the bbox data
from the same response via `response.headers.get("X-Blocks")` before
drawing its SVG overlay. (See app/main.py's CORS config -- `X-Blocks` is
in `expose_headers`, or the browser JS can't read it cross-origin.)

Uses the EXACT SAME render DPI and coordinate transform as
agents/provenance_agent.py's `_crop_from_pdf` (the render-DPI constant is
imported from there, not re-derived), so a crop generated for evidence
review and a full page rendered here are always pixel-consistent.

Per the Sprint 5 plan's "no Y-flip in the frontend, ever" rule: bbox_px is
already in the SAME top-left-origin pixel space as the rendered PNG. If a
box looks wrong, the bug is in the transform below, not in the frontend.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import fitz  # PyMuPDF
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from PIL import Image

from agents.provenance_agent import PDF_CROP_RENDER_DPI
from app.deps import get_store
from core.schemas import SourceFormat
from core.store import ClaimNotFoundError, ClaimStore

router = APIRouter(prefix="/api/claims", tags=["documents"])


@router.get("/{claim_id}/documents/{doc_id}/page/{page_number}")
def get_document_page(
    claim_id: str,
    doc_id: str,
    page_number: int,
    store: ClaimStore = Depends(get_store),
) -> Response:
    try:
        record = store.get(claim_id)
    except ClaimNotFoundError:
        raise HTTPException(status_code=404, detail=f"No claim found with id {claim_id!r}")

    document = next((d for d in record.claim.documents if d.doc_id == doc_id), None)
    if document is None:
        raise HTTPException(status_code=404, detail=f"No document {doc_id!r} on claim {claim_id!r}")

    if document.source_format == SourceFormat.PDF:
        png_bytes = _render_pdf_page(document.source_file, page_number)
        zoom = PDF_CROP_RENDER_DPI / 72.0
    elif document.source_format == SourceFormat.IMAGE:
        png_bytes = _render_image_page(document.source_file)
        zoom = 1.0  # image blocks' bbox is already in pixel space -- no scaling
    else:
        raise HTTPException(
            status_code=422,
            detail=f"No page renderer for source_format={document.source_format.value!r} "
                   f"(only pdf/image documents have a fixed-page pixel space to render).",
        )

    blocks_on_page = [
        b for b in document.blocks
        if b.bbox is not None
        and (b.page == page_number or (document.source_format == SourceFormat.IMAGE and b.page is None))
    ]
    blocks_payload = [
        {
            "block_id": b.block_id,
            # Verbatim: same scaling agents/provenance_agent.py's
            # _crop_from_pdf applies before cropping -- zero Y-flip.
            "bbox_px": [b.bbox[0] * zoom, b.bbox[1] * zoom, b.bbox[2] * zoom, b.bbox[3] * zoom],
        }
        for b in blocks_on_page
    ]

    return Response(
        content=png_bytes,
        media_type="image/png",
        headers={"X-Blocks": json.dumps(blocks_payload)},
    )


def _render_pdf_page(source_file: str, page_number: int) -> bytes:
    if not Path(source_file).exists():
        raise HTTPException(status_code=410, detail=f"Source PDF no longer exists on disk: {source_file}")

    doc = fitz.open(source_file)
    try:
        if page_number < 1 or page_number > doc.page_count:
            raise HTTPException(status_code=404, detail=f"Page {page_number} out of range (1-{doc.page_count}).")
        page = doc[page_number - 1]
        zoom = PDF_CROP_RENDER_DPI / 72.0
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
        image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        return buf.getvalue()
    finally:
        doc.close()


def _render_image_page(source_file: str) -> bytes:
    if not Path(source_file).exists():
        raise HTTPException(status_code=410, detail=f"Source image no longer exists on disk: {source_file}")

    image = Image.open(source_file).convert("RGB")
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()
