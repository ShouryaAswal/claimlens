"""
core/config.py
----------------
Shared constants. Centralized so Sprint 1's ingestion code and later sprints'
extraction/triage code don't each hardcode their own copies.
"""

from pathlib import Path

# --- Paths -------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCHEMAS_DIR = PROJECT_ROOT / "schemas"
SAMPLES_DIR = PROJECT_ROOT / "samples"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"

# --- Ingestion -----------------------------------------------------------
SUPPORTED_FILE_EXTENSIONS = {
    ".pdf": "pdf",
    ".docx": "docx",
    ".pptx": "pptx",
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".tif": "image",
    ".tiff": "image",
    ".bmp": "image",
}

# Content-Type -> file extension, used when ingesting a hyperlink so we know
# which parser to route the downloaded bytes to.
CONTENT_TYPE_TO_EXTENSION = {
    "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/tiff": ".tiff",
    "image/bmp": ".bmp",
}

# A PDF page is treated as "scanned" (and routed to OCR) if PyMuPDF's native
# text layer yields fewer than this many non-whitespace characters.
PDF_PAGE_OCR_FALLBACK_CHAR_THRESHOLD = 15

# DPI used when rasterizing a scanned PDF page for OCR. Higher = more
# accurate OCR, slower processing. 200-300 is the usual production sweet spot.
PDF_OCR_RENDER_DPI = 250

# Tesseract language code(s). Swap/extend for multilingual claims
# (e.g. "eng+vie" for English + Vietnamese) once language packs are
# installed (`apt-get install tesseract-ocr-<lang>`).
DEFAULT_OCR_LANGUAGE = "eng"

# Long-document guardrail: log a warning (not an error) above this page count
# so processing time is visible rather than silent. The manager's "20-25
# pages" requirement is the expected case, not the ceiling.
LONG_DOCUMENT_PAGE_WARNING_THRESHOLD = 20

# HTTP request timeout (seconds) for hyperlink ingestion.
URL_FETCH_TIMEOUT_SECONDS = 20

# Max bytes to download for a single hyperlink target (10 MB) — a sane guard
# against accidentally trying to OCR a 2 GB video someone linked by mistake.
URL_FETCH_MAX_BYTES = 10 * 1024 * 1024
