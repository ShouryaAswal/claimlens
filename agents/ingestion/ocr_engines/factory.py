"""
agents/ingestion/ocr_engines/factory.py
-------------------------------------------
Engine selection. `OCR_ENGINE` in core/config.py picks the preferred engine;
if it fails to initialize (not installed, or PaddleOCR's model download
can't reach a host), we log a clear warning and fall back to Tesseract --
once per process, not once per page, so a broken PaddleOCR install doesn't
silently retry-and-fail on every single page of a 25-page claim.
"""

from __future__ import annotations

import logging
from functools import lru_cache

from PIL import Image

from core.config import DEFAULT_OCR_LANGUAGE, OCR_ENGINE
from agents.ingestion.ocr_engines import paddleocr_engine, tesseract_engine
from agents.ingestion.ocr_engines.base import OCREngineError, OCRLine

logger = logging.getLogger(__name__)

_ENGINES = {
    "tesseract": tesseract_engine.ocr_image_to_lines,
    "paddleocr": paddleocr_engine.ocr_image_to_lines,
}


@lru_cache(maxsize=1)
def _resolve_active_engine_name() -> str:
    """Decide, once per process, which engine name to actually use.
    Cached so we only attempt (and potentially fail) PaddleOCR
    initialization a single time, not on every page."""
    preferred = OCR_ENGINE
    if preferred not in _ENGINES:
        logger.warning(
            "Unknown OCR_ENGINE=%r in config; falling back to 'tesseract'. "
            "Valid options: %s", preferred, list(_ENGINES),
        )
        return "tesseract"

    if preferred == "tesseract":
        return "tesseract"

    # preferred == "paddleocr": probe it once with a trivial blank image so
    # we surface install/model-download failures immediately and clearly,
    # rather than on whatever random page happens to need OCR first.
    try:
        paddleocr_engine.ocr_image_to_lines(Image.new("RGB", (32, 32), "white"))
        logger.info("OCR engine: PaddleOCR (model loaded successfully)")
        return "paddleocr"
    except OCREngineError as exc:
        logger.warning(
            "PaddleOCR requested but unavailable (%s). "
            "Falling back to Tesseract for this run. "
            "See PADDLEOCR_SETUP.md to fix this.", exc,
        )
        return "tesseract"


def ocr_image_to_lines(image: Image.Image, lang: str = DEFAULT_OCR_LANGUAGE) -> list[OCRLine]:
    """The single function the rest of the ingestion pipeline calls.
    Engine-agnostic by design -- callers never know or care which engine
    actually ran."""
    engine_name = _resolve_active_engine_name()
    engine_fn = _ENGINES[engine_name]
    try:
        return engine_fn(image, lang)
    except OCREngineError as exc:
        if engine_name != "tesseract":
            logger.warning(
                "%s failed mid-run (%s); falling back to Tesseract for this image.",
                engine_name, exc,
            )
            return tesseract_engine.ocr_image_to_lines(image, lang)
        raise


def active_engine_name() -> str:
    """For logging/diagnostics/tests: which engine is actually active."""
    return _resolve_active_engine_name()


def reset_engine_cache() -> None:
    """Test/debug helper -- clears the cached engine decision so a changed
    OCR_ENGINE config or a freshly-fixed install is picked up without
    restarting the process."""
    if hasattr(_resolve_active_engine_name, "cache_clear"):
        _resolve_active_engine_name.cache_clear()
