"""
agents/provenance_agent.py
-------------------------------
Sprint 3's "every accepted field traces to a real crop" requirement. Given
a block_id, regenerates a cropped image of exactly the region that block's
bbox covers -- this is what a reviewer actually looks at to confirm a field
with their own eyes, on top of (not instead of) the text-level evidence
checks in evidence_verifier.py.

Crop generation is possible wherever a block has BOTH a real bbox AND a
renderable source page:
  - PDF blocks: re-render the source PDF page at a fixed DPI (PyMuPDF),
    crop to bbox (scaled from PDF points to the render's pixel space), save
    as PNG.
  - Image blocks: open the original image directly, crop to bbox in pixel
    space, save as PNG.
  - PPTX blocks: have a real bbox (slide shape geometry, in points) but no
    pure-Python slide-to-image renderer is wired up -- crop generation is
    honestly unavailable here, not silently faked. (Would need a LibreOffice
    headless conversion step; flagged as future work, same as the DOCX/PPTX
    page-count gap from Sprint 1.)
  - DOCX/HTML blocks: no bbox exists at all (flowing documents) -- nothing
    to crop, by design since Sprint 1.

Crops are generated on demand for blocks actually cited as evidence (not
proactively for the entire corpus) -- most blocks in a 25-page claim are
never cited by anything, and rendering every page as an image upfront would
be wasted work.
"""

from __future__ import annotations

import logging
from pathlib import Path

import fitz  # PyMuPDF
from PIL import Image

from core.schemas import ClaimState, ContentBlock, SourceFormat

logger = logging.getLogger(__name__)

CROP_PADDING_PX = 8       # small margin around the bbox so text isn't clipped at the edge
PDF_CROP_RENDER_DPI = 250  # match the OCR fallback render DPI from Sprint 1 for consistency


class CropUnavailableError(Exception):
    """Raised (and caught internally, never propagated to callers) when a
    block's source format has no renderable crop path."""


def generate_crop(block: ContentBlock, output_dir: Path) -> Path | None:
    """Returns the path to a generated crop PNG, or None if this block's
    format doesn't support crop generation (logged, not raised -- a
    missing crop for one block must never halt verification for the rest
    of the claim)."""
    if block.bbox is None:
        logger.debug("Block %r has no bbox -- no crop possible (format: %s).",
                      block.block_id, block.source_format.value)
        return None

    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"{block.block_id}.png"

    try:
        if block.source_format == SourceFormat.PDF:
            _crop_from_pdf(block, out_path)
        elif block.source_format == SourceFormat.IMAGE:
            _crop_from_image(block, out_path)
        else:
            raise CropUnavailableError(
                f"No crop renderer available for source_format={block.source_format.value!r} "
                f"(block {block.block_id!r})."
            )
    except CropUnavailableError as exc:
        logger.info(str(exc))
        return None
    except Exception as exc:  # noqa: BLE001 - a corrupt/missing source file must not crash the run
        logger.warning("Failed to generate crop for block %r: %s", block.block_id, exc)
        return None

    return out_path


def _crop_from_pdf(block: ContentBlock, out_path: Path) -> None:
    source_path = Path(block.source_file)
    if not source_path.exists():
        raise CropUnavailableError(f"Source PDF no longer exists: {block.source_file}")

    doc = fitz.open(str(source_path))
    try:
        if block.page is None or block.page < 1 or block.page > doc.page_count:
            raise CropUnavailableError(f"Block {block.block_id!r} has invalid page {block.page!r}.")
        page = doc[block.page - 1]
        zoom = PDF_CROP_RENDER_DPI / 72.0
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
        full_image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)

        x0, y0, x1, y1 = block.bbox
        crop_box = (
            max(0, int(x0 * zoom) - CROP_PADDING_PX),
            max(0, int(y0 * zoom) - CROP_PADDING_PX),
            min(full_image.width, int(x1 * zoom) + CROP_PADDING_PX),
            min(full_image.height, int(y1 * zoom) + CROP_PADDING_PX),
        )
        full_image.crop(crop_box).save(out_path)
    finally:
        doc.close()


def _crop_from_image(block: ContentBlock, out_path: Path) -> None:
    source_path = Path(block.source_file)
    if not source_path.exists():
        raise CropUnavailableError(f"Source image no longer exists: {block.source_file}")

    full_image = Image.open(source_path).convert("RGB")
    x0, y0, x1, y1 = block.bbox
    crop_box = (
        max(0, int(x0) - CROP_PADDING_PX),
        max(0, int(y0) - CROP_PADDING_PX),
        min(full_image.width, int(x1) + CROP_PADDING_PX),
        min(full_image.height, int(y1) + CROP_PADDING_PX),
    )
    full_image.crop(crop_box).save(out_path)


def generate_crops_for_claim(claim: ClaimState, output_dir: Path) -> dict[str, str]:
    """Generates crops only for block_ids actually cited as evidence
    somewhere in claim.extracted_fields -- returns {block_id: crop_path}.
    Also writes the resulting paths back onto each FieldVerification's
    crop_paths, if verification has already run."""
    cited_block_ids: set[str] = set()
    for field in claim.extracted_fields.values():
        cited_block_ids.update(field.evidence_block_ids)

    crop_paths: dict[str, str] = {}
    for block_id in cited_block_ids:
        block = claim.get_block(block_id)
        if block is None:
            continue
        path = generate_crop(block, output_dir)
        if path is not None:
            crop_paths[block_id] = str(path)

    for field_id, field in claim.extracted_fields.items():
        verification = claim.field_verifications.get(field_id)
        if verification is None:
            continue
        verification.crop_paths = [
            crop_paths[bid] for bid in field.evidence_block_ids if bid in crop_paths
        ]

    unavailable = len(cited_block_ids) - len(crop_paths)
    if unavailable:
        logger.info(
            "%d of %d cited block(s) could not be cropped (format without a "
            "renderable source, or source file unavailable) -- this is expected "
            "for DOCX/PPTX/HTML evidence, not necessarily an error.",
            unavailable, len(cited_block_ids),
        )

    return crop_paths
