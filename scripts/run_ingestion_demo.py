"""
scripts/run_ingestion_demo.py
---------------------------------
Sprint 1 exit-criteria demo: ingest every sample document (across every
supported format) and write a consolidated JSON to outputs/, plus print a
human-readable summary table to the terminal.

Run: python3 scripts/run_ingestion_demo.py
(Run scripts/generate_samples.py first if samples/ is empty.)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from agents.ingestion.dispatcher import ingest_many
from core.config import OUTPUTS_DIR, SAMPLES_DIR


def main() -> None:
    sample_files = sorted(
        str(p) for p in SAMPLES_DIR.iterdir()
        if p.suffix.lower() in {".pdf", ".docx", ".pptx", ".png", ".jpg", ".jpeg"}
    )
    if not sample_files:
        print(f"No sample files found in {SAMPLES_DIR}. Run scripts/generate_samples.py first.")
        return

    records = ingest_many(sample_files)

    print(f"{'FILE':<38} {'FORMAT':<7} {'PAGES':<6} {'BLOCKS':<7} WARNINGS")
    print("-" * 100)
    for rec in records:
        name = Path(rec.source_file).name
        pages = rec.page_count if rec.page_count is not None else "-"
        warn = "; ".join(rec.warnings) if rec.warnings else ""
        print(f"{name:<38} {rec.source_format.value:<7} {str(pages):<6} {rec.block_count:<7} {warn}")

    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUTS_DIR / "ingestion_demo_result.json"
    out_path.write_text(
        json.dumps([r.model_dump(mode="json") for r in records], indent=2),
        encoding="utf-8",
    )
    print(f"\nFull structured output written to: {out_path}")


if __name__ == "__main__":
    main()
