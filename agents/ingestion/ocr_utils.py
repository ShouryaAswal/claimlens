"""
agents/ingestion/ocr_utils.py
--------------------------------
Backward-compatible shim. Sprint 1's pdf_parser.py and image_parser.py (and
their tests) call `ocr_utils.ocr_image_to_lines(...)`. As of Sprint 1
completion, the real implementation lives in `ocr_engines/` (Tesseract +
PaddleOCR + the engine-selection factory) -- this module just forwards to
the factory so none of the existing call sites had to change.

If you're looking for the actual OCR logic, see:
  - agents/ingestion/ocr_engines/factory.py        (engine selection)
  - agents/ingestion/ocr_engines/tesseract_engine.py
  - agents/ingestion/ocr_engines/paddleocr_engine.py
"""

from __future__ import annotations

from core.config import DEFAULT_OCR_LANGUAGE
from agents.ingestion.ocr_engines.base import OCRLine
from agents.ingestion.ocr_engines.factory import (
    active_engine_name,
    ocr_image_to_lines,
    reset_engine_cache,
)

__all__ = [
    "OCRLine",
    "ocr_image_to_lines",
    "active_engine_name",
    "reset_engine_cache",
    "DEFAULT_OCR_LANGUAGE",
]
