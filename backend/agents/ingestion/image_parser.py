"""
agents/ingestion/image_parser.py
------------------------------------
Standalone image ingestion (PNG/JPG/TIFF/BMP) -- e.g. a photo of damage with
a handwritten note, or a phone photo of a single-page document. Always goes
through OCR (there's no "digital text layer" possibility for a raw image).
"""

from __future__ import annotations

from PIL import Image

from core.config import DEFAULT_OCR_LANGUAGE
from core.schemas import ContentBlock, SourceFormat
from agents.ingestion import ocr_utils
from agents.ingestion.base import next_block_id


def parse_image(
    path: str,
    source_file: str | None = None,
    ocr_lang: str = DEFAULT_OCR_LANGUAGE,
) -> tuple[list[ContentBlock], int, list[str]]:
    source_file = source_file or str(path)
    warnings: list[str] = []

    image = Image.open(path).convert("RGB")
    lines = ocr_utils.ocr_image_to_lines(image, lang=ocr_lang)

    blocks: list[ContentBlock] = []
    for i, line in enumerate(lines, start=1):
        blocks.append(
            ContentBlock(
                block_id=next_block_id("img", i),
                source_file=source_file,
                source_format=SourceFormat.IMAGE,
                page=1,
                locator=f"ocr_line_{i}",
                text=line["text"],
                bbox=line["bbox"],
                confidence=line["confidence"],
                extraction_method="pytesseract_ocr",
            )
        )

    if not blocks:
        warnings.append(
            "OCR found no text in this image. It may be a pure photo "
            "(e.g. vehicle damage) with no document text -- this is expected "
            "for evidentiary photos, not necessarily an error."
        )

    return blocks, 1, warnings
