"""
agents/ingestion/ocr_utils.py
--------------------------------
Shared OCR logic, used by:
  - pdf_parser.py  (scanned/image-only PDF pages)
  - image_parser.py (standalone PNG/JPG/TIFF/BMP files)

Engine: pytesseract (Tesseract). This is a deliberate sandbox/laptop-friendly
choice over PaddleOCR -- see the design doc's model-choice discussion. The
output contract (list of {text, bbox, confidence} dicts) is engine-agnostic,
so swapping in PaddleOCR later for better multilingual accuracy means
rewriting this one function, not the callers.
"""

from __future__ import annotations

from typing import TypedDict

import pytesseract
from PIL import Image

from core.config import DEFAULT_OCR_LANGUAGE


class OCRLine(TypedDict):
    text: str
    bbox: tuple[float, float, float, float]   # (x0, y0, x1, y1) in pixels
    confidence: float                          # 0.0 - 1.0


def ocr_image_to_lines(
    image: Image.Image,
    lang: str = DEFAULT_OCR_LANGUAGE,
) -> list[OCRLine]:
    """Run Tesseract on a PIL image and group word-level boxes into lines.

    Tesseract's `image_to_data` returns one row per detected word, each
    tagged with (block_num, par_num, line_num). We group consecutive words
    that share all three into a single line-level ContentBlock, which keeps
    block counts sane for dense documents instead of one block per word.
    """
    data = pytesseract.image_to_data(
        image, lang=lang, output_type=pytesseract.Output.DICT
    )

    n = len(data["text"])
    lines: dict[tuple[int, int, int], dict] = {}

    for i in range(n):
        word = data["text"][i].strip()
        if not word:
            continue
        conf_raw = data["conf"][i]
        try:
            conf = float(conf_raw)
        except (TypeError, ValueError):
            conf = -1.0
        if conf < 0:
            # Tesseract uses -1 for non-text regions; skip them.
            continue

        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        x, y, w, h = (
            data["left"][i],
            data["top"][i],
            data["width"][i],
            data["height"][i],
        )

        if key not in lines:
            lines[key] = {
                "words": [],
                "x0": x,
                "y0": y,
                "x1": x + w,
                "y1": y + h,
                "confs": [],
            }
        line = lines[key]
        line["words"].append(word)
        line["x0"] = min(line["x0"], x)
        line["y0"] = min(line["y0"], y)
        line["x1"] = max(line["x1"], x + w)
        line["y1"] = max(line["y1"], y + h)
        line["confs"].append(conf)

    results: list[OCRLine] = []
    # Sort top-to-bottom, then left-to-right, for stable reading order.
    for key in sorted(lines.keys(), key=lambda k: (lines[k]["y0"], lines[k]["x0"])):
        line = lines[key]
        text = " ".join(line["words"]).strip()
        if not text:
            continue
        avg_conf = sum(line["confs"]) / len(line["confs"]) / 100.0
        results.append(
            OCRLine(
                text=text,
                bbox=(float(line["x0"]), float(line["y0"]), float(line["x1"]), float(line["y1"])),
                confidence=round(max(0.0, min(1.0, avg_conf)), 4),
            )
        )
    return results
