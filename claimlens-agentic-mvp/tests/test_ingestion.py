"""
Tests for the ingestion agent (multi-format) and the synthetic corpus
generator. Run alongside tests/test_pipeline.py:

    python3 -m pytest tests/ -v
"""

import http.server
import json
import socketserver
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from agents.ingestion_agent import detect_source_type, ingest
from core.schemas import OCRBlock

FIXTURES = {
    "digital_pdf": "samples/corpus/auto/AUTO-002.pdf",
    "scanned_pdf": "samples/other_formats/AUTO-002_scanned.pdf",
    "image": "samples/other_formats/repair_receipt_photo.png",
    "docx": "samples/other_formats/claimant_followup_letter.docx",
}


@pytest.mark.parametrize("expected_type,path", FIXTURES.items())
def test_detect_source_type(expected_type, path):
    assert detect_source_type(path) == expected_type


@pytest.mark.parametrize("expected_type,path", FIXTURES.items())
def test_ingest_each_format_produces_valid_blocks(expected_type, path):
    blocks = ingest(path)
    assert len(blocks) > 0, f"{path} produced zero blocks"
    for b in blocks:
        OCRBlock.model_validate(b.model_dump())
        assert b.source_type == expected_type
        assert b.text.strip() != ""


def test_scanned_pdf_has_realistic_confidence_spread():
    """The scanned path should show real OCR uncertainty -- unlike the
    digital path, which is always 1.0. If this is ever exactly 1.0
    across the board, something is silently falling back to the
    digital path instead of actually running Tesseract."""
    blocks = ingest(FIXTURES["scanned_pdf"])
    confidences = {round(b.ocr_confidence, 2) for b in blocks}
    assert len(confidences) > 3, "Expected varied confidence scores from real OCR"
    assert min(confidences) < 1.0


def test_docx_blocks_have_no_bbox_but_valid_text():
    blocks = ingest(FIXTURES["docx"])
    assert all(b.bbox is None for b in blocks)
    assert all(b.page == 1 for b in blocks)


def test_hyperlink_ingestion_via_local_server(tmp_path):
    """We can't reach arbitrary external URLs from this sandbox, so we
    validate the fetch-then-redispatch logic against a local HTTP
    server instead. Behaviour against a real internet URL is
    identical -- only the network path differs."""
    serve_dir = Path("samples/corpus/auto").resolve()
    handler_cls = type(
        "Handler",
        (http.server.SimpleHTTPRequestHandler,),
        {"directory": str(serve_dir)},
    )

    def handler_factory(*args, **kwargs):
        return http.server.SimpleHTTPRequestHandler(*args, directory=str(serve_dir), **kwargs)

    httpd = socketserver.TCPServer(("localhost", 0), handler_factory)
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.3)

    try:
        url = f"http://localhost:{port}/AUTO-003.pdf"
        assert detect_source_type(url) == "url"
        blocks = ingest(url)
        assert len(blocks) > 0
        assert blocks[0].source_type == "digital_pdf"
    finally:
        httpd.shutdown()


# --- Corpus-level checks (the manager's "20-25 docs of ~20 pages" ask) ---

MANIFEST_PATH = Path("outputs/corpus_manifest.json")


@pytest.fixture(scope="module")
def manifest():
    assert MANIFEST_PATH.exists(), "Run `python3 -m samples.generate_corpus` first"
    return json.loads(MANIFEST_PATH.read_text())


def test_corpus_has_20_to_25_documents(manifest):
    assert 20 <= len(manifest) <= 25


def test_corpus_covers_all_three_lobs(manifest):
    lobs = {m["claim_type"] for m in manifest}
    assert lobs == {"auto", "property", "health"}


def test_corpus_page_counts_are_realistic_length(manifest):
    for entry in manifest:
        assert 15 <= entry["page_count"] <= 22, entry["claim_id"]


def test_corpus_includes_injected_noise(manifest):
    """A corpus where every document is perfect doesn't test anything.
    Confirm both noise types actually occur somewhere in the set."""
    any_missing_field = any(entry["missing_fields"] for entry in manifest)
    any_date_issue = any(entry["date_inconsistency"] for entry in manifest)
    assert any_missing_field, "No claim had a missing-field injected"
    assert any_date_issue, "No claim had a date inconsistency injected"


def test_every_corpus_pdf_is_ingestible(manifest):
    for entry in manifest:
        blocks = ingest(entry["file"])
        assert len(blocks) > 0, entry["file"]
