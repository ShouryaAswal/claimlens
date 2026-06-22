"""
tests/test_real_world_data.py
---------------------------------
Regression tests against the real-world / realistic data added this round
(see samples/real_world/REAL_DATA_SOURCES.md for what's genuinely real vs.
recreated-from-real-content vs. synthetically degraded, and why).

These intentionally do NOT assert exact OCR text matches -- real and
realistically-degraded scans are noisy by design, and a brittle exact-match
assertion here would defeat the purpose of testing against messy data.
What's asserted is robustness: the pipeline must not crash, must produce at
least some blocks, and every block must carry valid provenance.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agents.ingestion.dispatcher import ingest
from core.config import SAMPLES_DIR

FUNSD_DIR = SAMPLES_DIR / "real_world" / "funsd_scans"
FNOL_SPECIMEN_DIR = SAMPLES_DIR / "real_world" / "fnol_specimens"
REALISTIC_DIR = SAMPLES_DIR / "synthetic_realistic"

pytestmark = pytest.mark.skipif(
    not FUNSD_DIR.exists() or not any(FUNSD_DIR.glob("*.png")),
    reason="real-world sample data not present in this checkout",
)


def _all_funsd_images() -> list[Path]:
    return sorted(FUNSD_DIR.glob("*.png"))


@pytest.mark.parametrize("image_path", _all_funsd_images())
def test_real_funsd_scan_does_not_crash_and_yields_blocks(image_path):
    record = ingest(str(image_path))
    assert record.page_count == 1
    # Real noisy scans should still yield SOME text -- if this starts
    # failing across the board, OCR quality has regressed badly.
    assert record.block_count > 0
    for block in record.blocks:
        assert block.bbox is not None
        assert 0.0 <= block.confidence <= 1.0
        assert block.source_file == str(image_path)


def test_real_funsd_ground_truth_file_is_valid_json():
    import json
    gt_path = FUNSD_DIR / "funsd_ground_truth.json"
    assert gt_path.exists()
    data = json.loads(gt_path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)


@pytest.mark.skipif(not FNOL_SPECIMEN_DIR.exists(), reason="FNOL specimens not present")
@pytest.mark.parametrize("pdf_path", sorted(FNOL_SPECIMEN_DIR.glob("*.pdf")) if FNOL_SPECIMEN_DIR.exists() else [])
def test_fnol_specimen_pdf_ingests_cleanly(pdf_path):
    record = ingest(str(pdf_path))
    assert record.page_count == 1
    assert record.block_count > 0
    assert all(b.extraction_method == "pymupdf_text" for b in record.blocks)


@pytest.mark.skipif(not REALISTIC_DIR.exists(), reason="realistic degraded scans not present")
@pytest.mark.parametrize("image_path", sorted(REALISTIC_DIR.glob("*.png")) if REALISTIC_DIR.exists() else [])
def test_augraphy_degraded_scan_survives_ocr(image_path):
    """Even at 'heavy' degradation (folding, bad-photocopy noise, lighting
    gradient, JPEG recompression), the pipeline must produce output rather
    than silently returning nothing."""
    record = ingest(str(image_path))
    assert record.page_count == 1
    assert record.block_count > 0, f"{image_path.name} produced zero OCR blocks"
