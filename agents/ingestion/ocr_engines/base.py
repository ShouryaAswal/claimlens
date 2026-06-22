"""
agents/ingestion/ocr_engines/base.py
---------------------------------------
The contract every OCR engine must satisfy. ContentBlock-producing code
(pdf_parser.py, image_parser.py) depends only on this shape -- never on
Tesseract or PaddleOCR specifics -- so engines are swappable.
"""

from __future__ import annotations

from typing import Protocol, TypedDict

from PIL import Image


class OCRLine(TypedDict):
    text: str
    bbox: tuple[float, float, float, float]   # (x0, y0, x1, y1) in pixels
    confidence: float                          # 0.0 - 1.0


class OCREngine(Protocol):
    """Anything with this call signature is a valid OCR engine."""

    def __call__(self, image: Image.Image, lang: str) -> list[OCRLine]: ...


class OCREngineError(Exception):
    """Raised when an engine fails to initialize or run, so the factory can
    decide whether to fall back to another engine."""
