"""
scripts/generate_realistic_scans.py
---------------------------------------
Takes the clean, "born-digital" synthetic claim documents from Sprint 1
(samples/*.pdf, samples/*.png) and produces realistically degraded scan
versions using Augraphy (https://github.com/sparkfish/augraphy) -- the same
library used to build the ShabbyPages document-denoising benchmark.

This directly addresses "the current ones are too clean and dummy-like":
these outputs have genuine paper texture, scan noise, ink bleed, page
rotation/skew, JPEG recompression artifacts, lighting gradients (uneven
photocopier/scanner lighting), and -- at the "heavy" tier -- the kind of
shadowy, low-contrast mess a real bad photocopy of a faxed form looks like.

Three severity tiers, because real claim packets aren't uniformly bad:
  - light:  mild noise + slight rotation + light JPEG recompression
            (a decent flatbed scan)
  - medium: + ink bleed + paper texture noise + heavier JPEG compression
            (an office scanner that's overdue for a clean)
  - heavy:  + page folding + bad-photocopy noise + lighting gradient/shadow
            (a faxed-then-photocopied document, several generations removed
            from the original)

Run: python3 scripts/generate_realistic_scans.py
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import fitz  # PyMuPDF
import numpy as np
from augraphy import (
    AugraphyPipeline,
    BadPhotoCopy,
    Folding,
    Geometric,
    InkBleed,
    Jpeg,
    LightingGradient,
    NoiseTexturize,
)
from PIL import Image

from core.config import SAMPLES_DIR

OUT_DIR = SAMPLES_DIR / "synthetic_realistic"

SOURCE_FILES = [
    SAMPLES_DIR / "auto_claim_01.pdf",
    SAMPLES_DIR / "health_claim_01.docx",  # rendered via a quick text->image stand-in below is skipped; PDFs/images only
]


def _build_pipelines() -> dict[str, AugraphyPipeline]:
    return {
        "light": AugraphyPipeline(
            post_phase=[
                Geometric(rotate_range=(-2, 2), p=1),
                NoiseTexturize(sigma_range=(2, 4), p=0.7),
                Jpeg(quality_range=(60, 85), p=1),
            ],
        ),
        "medium": AugraphyPipeline(
            ink_phase=[InkBleed(intensity_range=(0.1, 0.2), severity=(0.1, 0.2), p=0.6)],
            paper_phase=[LightingGradient(p=0.5)],
            post_phase=[
                Geometric(rotate_range=(-4, 4), p=1),
                NoiseTexturize(sigma_range=(3, 6), p=0.8),
                Jpeg(quality_range=(35, 60), p=1),
            ],
        ),
        "heavy": AugraphyPipeline(
            ink_phase=[InkBleed(intensity_range=(0.3, 0.5), severity=(0.2, 0.35), p=0.8)],
            paper_phase=[
                Folding(fold_count=2, fold_noise=0.05, p=0.7),
                LightingGradient(p=0.6),
            ],
            post_phase=[
                BadPhotoCopy(noise_iteration=(1, 2), p=0.5),
                Geometric(rotate_range=(-6, 6), p=1),
                Jpeg(quality_range=(20, 40), p=1),
            ],
        ),
    }


def _pdf_pages_to_arrays(pdf_path: Path, zoom: float = 2.0) -> list[np.ndarray]:
    doc = fitz.open(str(pdf_path))
    arrays = []
    for page in doc:
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        arrays.append(np.array(img))
    doc.close()
    return arrays


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    pipelines = _build_pipelines()

    pdf_sources = [
        SAMPLES_DIR / "auto_claim_01.pdf",
        SAMPLES_DIR / "real_world" / "fnol_specimens" / "fema_proof_of_loss_specimen.pdf",
        SAMPLES_DIR / "real_world" / "fnol_specimens" / "ny_dmv_mv104_specimen.pdf",
    ]

    generated = []
    for pdf_path in pdf_sources:
        if not pdf_path.exists():
            print(f"  (skipping, not found: {pdf_path})")
            continue
        stem = pdf_path.stem
        for page_idx, arr in enumerate(_pdf_pages_to_arrays(pdf_path), start=1):
            for tier_name, pipeline in pipelines.items():
                out_arr = pipeline(arr.copy())
                out_path = OUT_DIR / f"{stem}_p{page_idx}_{tier_name}.png"
                Image.fromarray(out_arr).save(out_path)
                generated.append(out_path)

    print(f"Generated {len(generated)} realistically-degraded scan images in: {OUT_DIR}")
    for p in generated:
        print(f"  - {p.name}")


if __name__ == "__main__":
    main()
