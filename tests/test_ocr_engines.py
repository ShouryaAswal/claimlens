"""
tests/test_ocr_engines.py
----------------------------
Tests for the engine-selection factory. Notably, `test_paddleocr_falls_back_to_tesseract_when_unavailable`
is NOT mocked -- it exercises the real PaddleOCR initialization path. In any
environment where PaddleOCR's model download genuinely cannot reach a host
(as documented in PADDLEOCR_SETUP.md), this test proves the fallback
actually engages rather than crashing the pipeline. In an environment where
PaddleOCR *can* download its models, this test still passes -- it just
means real PaddleOCR output gets used and is checked for the same OCRLine
shape contract instead.
"""

from __future__ import annotations

import logging

import pytest
from PIL import Image, ImageDraw, ImageFont

from agents.ingestion.ocr_engines import factory


@pytest.fixture(autouse=True)
def _reset_engine_state(monkeypatch):
    """Every test gets a clean slate: no leftover cached engine decision
    from a previous test, and OCR_ENGINE reset to the tesseract default.

    Note: factory.py does `from core.config import OCR_ENGINE`, a name
    binding copied at import time -- patching core.config.OCR_ENGINE
    afterward would NOT affect factory's already-bound copy. We patch
    `factory.OCR_ENGINE` directly, where it's actually read.
    """
    monkeypatch.setattr(factory, "OCR_ENGINE", "tesseract", raising=False)
    factory.reset_engine_cache()
    yield
    factory.reset_engine_cache()


def _sample_text_image() -> Image.Image:
    img = Image.new("RGB", (600, 150), color="white")
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 28)
    except OSError:
        font = ImageFont.load_default()
    draw.text((20, 40), "Policy Number: TEST-001", fill="black", font=font)
    return img


def test_default_engine_is_tesseract():
    assert factory.active_engine_name() == "tesseract"


def test_unknown_engine_name_falls_back_to_tesseract(monkeypatch, caplog):
    monkeypatch.setattr(factory, "OCR_ENGINE", "not_a_real_engine", raising=False)
    factory.reset_engine_cache()
    assert factory.active_engine_name() == "tesseract"


def test_tesseract_engine_runs_via_factory():
    lines = factory.ocr_image_to_lines(_sample_text_image())
    assert len(lines) > 0
    assert all(0.0 <= line["confidence"] <= 1.0 for line in lines)
    full_text = " ".join(l["text"] for l in lines)
    assert "TEST-001" in full_text or "Policy" in full_text


def test_paddleocr_falls_back_to_tesseract_when_unavailable(monkeypatch, caplog):
    """Real (unmocked) test of the resilience behavior this task asked for:
    requesting paddleocr in an environment where its model download cannot
    reach a host must not crash the pipeline -- it must fall back to
    Tesseract and still return usable OCRLines."""
    monkeypatch.setattr(factory, "OCR_ENGINE", "paddleocr", raising=False)
    factory.reset_engine_cache()

    import logging
    caplog.set_level(logging.WARNING)

    lines = factory.ocr_image_to_lines(_sample_text_image())

    # Whichever engine actually ran, the OUTPUT CONTRACT must hold.
    assert len(lines) > 0
    assert all(set(line.keys()) == {"text", "bbox", "confidence"} for line in lines)

    engine_used = factory.active_engine_name()
    assert engine_used in ("tesseract", "paddleocr")
    if engine_used == "tesseract":
        # We fell back -- there must be a clear log explaining why, not a
        # silent swap that would confuse someone debugging output quality.
        assert any("PaddleOCR" in r.message for r in caplog.records)


def test_mid_run_failure_falls_back_without_crashing(monkeypatch):
    """Simulates a PaddleOCR engine that initializes fine but blows up on a
    specific image (e.g. a corrupt page) -- the per-call fallback in
    factory.ocr_image_to_lines must still recover."""
    from agents.ingestion.ocr_engines.base import OCREngineError

    monkeypatch.setattr(factory, "OCR_ENGINE", "paddleocr", raising=False)
    factory.reset_engine_cache()

    # Force the resolver to believe paddleocr is the active engine, without
    # actually depending on whether real init succeeded in this environment.
    factory._resolve_active_engine_name.cache_clear()
    monkeypatch.setattr(factory, "_resolve_active_engine_name", lambda: "paddleocr")

    def _boom(image, lang):
        raise OCREngineError("simulated mid-run failure")

    monkeypatch.setitem(factory._ENGINES, "paddleocr", _boom)

    lines = factory.ocr_image_to_lines(_sample_text_image())
    assert len(lines) > 0  # tesseract fallback produced real output
