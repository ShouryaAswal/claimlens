"""
Ingestion Agent -- responds directly to the manager's feedback that
real claim packets arrive as PDFs, scanned images, photographed
documents, Word docs, and emailed links, not just clean digital PDFs.

This module is the single entry point (`ingest(source)`) the rest of
the pipeline calls. Everything downstream of this file only ever sees
a List[OCRBlock] -- it doesn't know or care whether that came from a
text layer, Tesseract, or a .docx paragraph.

Supported source types today:
  - digital_pdf : has an extractable text layer       -> PyMuPDF
  - scanned_pdf : image-only PDF (no text layer)        -> pdf2image + Tesseract
  - image       : .png/.jpg/.jpeg/.tiff/.bmp             -> Tesseract
  - docx        : Word document                         -> python-docx
  - url         : http(s):// link                       -> download, then
                                                            re-dispatch on
                                                            the downloaded
                                                            file's real type

Known limitation (called out deliberately, not hidden): .docx has no
native page/coordinate concept the way a PDF does. We extract at
paragraph granularity with bbox=None; provenance for those fields
falls back to "paragraph N, this exact snippet" rather than a visual
crop. Reconstructing true pagination would mean rendering the docx to
PDF first (e.g. via headless LibreOffice) -- flagged as a fast follow,
not done today because it adds a system dependency for a relatively
rare source type in this dataset.
"""

from __future__ import annotations

import mimetypes
import os
import tempfile
from pathlib import Path
from typing import List
from urllib.parse import urlparse

import docx
import fitz  # PyMuPDF
import requests
from pdf2image import convert_from_path
from PIL import Image
import pytesseract

from agents.ocr_agent import is_digital_pdf, run_pymupdf_ocr
from core.schemas import OCRBlock

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tiff", ".bmp", ".webp"}
TESSERACT_MIN_WORD_CONF = 0  # pytesseract returns -1 for non-text regions


def detect_source_type(source: str) -> str:
    """Classify a source path or URL into one of:
    'url' | 'digital_pdf' | 'scanned_pdf' | 'image' | 'docx'"""
    parsed = urlparse(source)
    if parsed.scheme in ("http", "https"):
        return "url"

    ext = Path(source).suffix.lower()
    if ext == ".pdf":
        return "digital_pdf" if is_digital_pdf(source) else "scanned_pdf"
    if ext in IMAGE_EXTENSIONS:
        return "image"
    if ext == ".docx":
        return "docx"
    raise ValueError(f"Unsupported file type: {source!r} (ext={ext!r})")


def _tesseract_image_to_blocks(
    image: Image.Image, page: int, source_file: str, source_type: str
) -> List[OCRBlock]:
    """Runs Tesseract on a single page/image and groups word-level
    output into line-level OCRBlocks (line granularity matches what
    the digital-PDF path already produces, keeping downstream agents
    format-agnostic)."""
    data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
    n = len(data["text"])

    # Group words by (block_num, par_num, line_num) -> one OCRBlock per line.
    lines: dict[tuple, dict] = {}
    for i in range(n):
        word = data["text"][i].strip()
        conf = int(data["conf"][i])
        if not word or conf < TESSERACT_MIN_WORD_CONF:
            continue
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        x, y, w, h = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
        if key not in lines:
            lines[key] = {"words": [], "confs": [], "x1": x, "y1": y, "x2": x + w, "y2": y + h}
        line = lines[key]
        line["words"].append(word)
        line["confs"].append(conf)
        line["x1"] = min(line["x1"], x)
        line["y1"] = min(line["y1"], y)
        line["x2"] = max(line["x2"], x + w)
        line["y2"] = max(line["y2"], y + h)

    blocks = []
    for idx, (_, line) in enumerate(sorted(lines.items()), start=1):
        text = " ".join(line["words"]).strip()
        if not text:
            continue
        avg_conf = sum(line["confs"]) / len(line["confs"]) / 100.0
        blocks.append(
            OCRBlock(
                block_id=f"p{page}_b{idx:03d}",
                page=page,
                text=text,
                bbox=(float(line["x1"]), float(line["y1"]), float(line["x2"]), float(line["y2"])),
                ocr_confidence=round(avg_conf, 3),
                source_file=source_file,
                source_type=source_type,
            )
        )
    return blocks


def ingest_scanned_pdf(file_path: str) -> List[OCRBlock]:
    """Image-only PDF: rasterize each page, then Tesseract OCR it."""
    source_file = os.path.basename(file_path)
    pages = convert_from_path(file_path, dpi=200)
    blocks: List[OCRBlock] = []
    for page_index, page_image in enumerate(pages, start=1):
        blocks.extend(
            _tesseract_image_to_blocks(page_image, page_index, source_file, "scanned_pdf")
        )
    return blocks


def ingest_image(file_path: str) -> List[OCRBlock]:
    """Standalone photographed/scanned image (e.g. a damage photo with
    a caption, or a phone-photographed receipt)."""
    source_file = os.path.basename(file_path)
    image = Image.open(file_path)
    return _tesseract_image_to_blocks(image, page=1, source_file=source_file, source_type="image")


def ingest_docx(file_path: str) -> List[OCRBlock]:
    """Word document. See module docstring for the bbox=None trade-off."""
    source_file = os.path.basename(file_path)
    document = docx.Document(file_path)
    blocks: List[OCRBlock] = []
    idx = 0
    for para in document.paragraphs:
        text = para.text.strip()
        if not text:
            continue
        idx += 1
        blocks.append(
            OCRBlock(
                block_id=f"p1_b{idx:03d}",
                page=1,  # docx has no native page concept; see module docstring
                text=text,
                bbox=None,
                ocr_confidence=1.0,  # digital text, no recognition uncertainty
                source_file=source_file,
                source_type="docx",
            )
        )
    return blocks


def ingest_url(url: str, download_dir: str | None = None) -> List[OCRBlock]:
    """Fetches a remote document and re-dispatches based on its real
    content type (a hyperlink to a .pdf is still a PDF once downloaded;
    we don't trust the URL's extension alone since claims systems often
    serve documents from extensionless endpoints)."""
    response = requests.get(url, timeout=30)
    response.raise_for_status()

    content_type = response.headers.get("Content-Type", "").split(";")[0].strip()
    ext = mimetypes.guess_extension(content_type) or Path(urlparse(url).path).suffix or ".bin"
    # mimetypes sometimes returns ".jpe" for jpeg -- normalise common cases.
    ext = {".jpe": ".jpg", ".htm": ".html"}.get(ext, ext)

    download_dir = download_dir or tempfile.mkdtemp(prefix="claimlens_url_")
    local_path = os.path.join(download_dir, "downloaded" + ext)
    with open(local_path, "wb") as f:
        f.write(response.content)

    source_type = detect_source_type(local_path)
    return _dispatch(local_path, source_type)


def _dispatch(source: str, source_type: str) -> List[OCRBlock]:
    if source_type == "digital_pdf":
        return run_pymupdf_ocr(source)
    if source_type == "scanned_pdf":
        return ingest_scanned_pdf(source)
    if source_type == "image":
        return ingest_image(source)
    if source_type == "docx":
        return ingest_docx(source)
    raise ValueError(f"No handler registered for source_type={source_type!r}")


def ingest(source: str) -> List[OCRBlock]:
    """Single entry point for the whole pipeline. Detects the source
    type and routes to the right extractor."""
    source_type = detect_source_type(source)
    if source_type == "url":
        return ingest_url(source)
    return _dispatch(source, source_type)


if __name__ == "__main__":
    import json
    import sys

    targets = sys.argv[1:] or ["samples/auto_claim_01.pdf"]
    for t in targets:
        blocks = ingest(t)
        print(f"{t} [{detect_source_type(t) if not t.startswith('http') else 'url'}]: {len(blocks)} blocks")
        for b in blocks[:2]:
            print(f"    {b.block_id} conf={b.ocr_confidence} bbox={b.bbox} text={b.text!r}")
