"""
agents/ingestion/ocr_engines/paddleocr_engine.py
------------------------------------------------------
The PaddleOCR-backed OCR engine (PaddleOCR v3 / PP-OCRv6 pipeline).

This is the "special feature" engine -- the same family of engine used in
the Fullerton Health architecture (arXiv:2601.01897) ClaimLens's design doc
cites, and the one named in the original Sprint 1 plan ("PaddleOCR +
PyMuPDF"). It generally out-performs Tesseract on multilingual text, messy
real-world scans, and dense small text, at the cost of a much heavier
install (a real deep-learning runtime, not just a CLI binary) and a
mandatory one-time model download on first use.

Result schema (verified directly against the installed paddlex source,
paddlex/inference/pipelines/ocr/pipeline.py, since PaddleOCR's public API
has changed shape across versions and guessing from memory would be
unreliable): `ocr.predict(...)` returns a list of dict-like OCRResult
objects, one per input image, each exposing:
    result["rec_texts"]   -> list[str]                      recognized text per line
    result["rec_scores"]  -> list[float]                    confidence 0.0-1.0 per line
    result["rec_boxes"]   -> list[(x0, y0, x1, y1)]          axis-aligned box per line
      (rec_boxes is already an axis-aligned rectangle, derived internally
      from the raw detection polygon -- no manual polygon math needed here.)

IMPORTANT -- network dependency: instantiating PaddleOCR triggers a
one-time download of detection/recognition model weights from one of
HuggingFace, ModelScope, AIStudio, or Baidu BOS. This requires outbound
network access to one of those hosts. See PADDLEOCR_SETUP.md for exact
install + first-run instructions and what to do if your network blocks all
four (e.g. a locked-down corporate or sandboxed environment).
"""

from __future__ import annotations

import logging
import tempfile
from functools import lru_cache
from pathlib import Path

from PIL import Image

from core.config import DEFAULT_OCR_LANGUAGE
from agents.ingestion.ocr_engines.base import OCREngineError, OCRLine

logger = logging.getLogger(__name__)


@lru_cache(maxsize=4)
def _get_paddleocr_instance(lang: str):
    """Lazily construct (and cache) a PaddleOCR pipeline instance.

    Model loading is expensive (model download on first use + neural net
    init), so this is built once per language and reused -- never
    re-instantiate PaddleOCR per page/image.
    """
    try:
        from paddleocr import PaddleOCR  # noqa: PLC0415 - intentionally lazy/optional import
    except ImportError as exc:
        raise OCREngineError(
            "paddleocr is not installed. Run: pip install paddlepaddle paddleocr "
            "(see PADDLEOCR_SETUP.md for the full guide)."
        ) from exc

    try:
        return PaddleOCR(
            lang=_to_paddle_lang_code(lang),
            use_doc_orientation_classify=False,  # off by default: faster, fewer models to
            use_doc_unwarping=False,              # download; flip on for crumpled/rotated
            use_textline_orientation=False,       # real-world photos if you need it.
        )
    except Exception as exc:  # noqa: BLE001 - PaddleOCR/PaddleX raise plain Exception
        raise OCREngineError(
            "PaddleOCR failed to initialize. This almost always means the "
            "one-time model download couldn't reach any of its hosts "
            "(huggingface.co, modelscope.cn, aistudio.baidu.com, or Baidu BOS). "
            "Check outbound network access to one of those domains, or set "
            "PADDLE_PDX_MODEL_SOURCE to a reachable mirror. "
            f"Original error: {exc}"
        ) from exc


def _to_paddle_lang_code(lang: str) -> str:
    """Map our Tesseract-style language codes (e.g. 'eng', 'eng+vie') to
    PaddleOCR's codes (e.g. 'en', 'vi'). Only the first language is used --
    PaddleOCR (unlike Tesseract) takes a single model language, not a
    combined pack."""
    primary = lang.split("+")[0].strip().lower()
    return {
        "eng": "en",
        "vie": "vi",
        "deu": "de",
        "fra": "fr",
        "chi_sim": "ch",
        "chi_tra": "chinese_cht",
        "jpn": "japan",
        "kor": "korean",
    }.get(primary, primary if len(primary) == 2 else "en")


def ocr_image_to_lines(
    image: Image.Image,
    lang: str = DEFAULT_OCR_LANGUAGE,
) -> list[OCRLine]:
    """Run PaddleOCR on a PIL image. Raises OCREngineError on any failure
    (missing install, failed model download, inference error) so the
    factory can decide whether to fall back to Tesseract."""
    ocr = _get_paddleocr_instance(lang)

    # predict() accepts a file path most reliably across PaddleOCR versions
    # (vs. raw numpy arrays, where RGB/BGR channel-order conventions have
    # shifted between releases) -- write to a temp PNG rather than guess.
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        image.convert("RGB").save(tmp, format="PNG")
        tmp_path = tmp.name

    try:
        results = ocr.predict(tmp_path)
    except Exception as exc:  # noqa: BLE001
        raise OCREngineError(f"PaddleOCR inference failed: {exc}") from exc
    finally:
        try:
            Path(tmp_path).unlink()
        except OSError:
            logger.warning("Could not remove temp file %s", tmp_path)

    if not results:
        return []

    result = results[0]
    texts = result.get("rec_texts", [])
    scores = result.get("rec_scores", [])
    boxes = result.get("rec_boxes", [])

    lines: list[OCRLine] = []
    for text, score, box in zip(texts, scores, boxes):
        text = (text or "").strip()
        if not text:
            continue
        x0, y0, x1, y1 = (float(v) for v in box)
        lines.append(
            OCRLine(
                text=text,
                bbox=(x0, y0, x1, y1),
                confidence=round(float(max(0.0, min(1.0, score))), 4),
            )
        )
    return lines
