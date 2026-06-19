# ClaimLens — Agentic OCR + LLM Claims Extraction MVP

Internship MVP demonstrating: OCR bounding-box extraction → LLM field
extraction → provenance linking → verification → triage. See the
project deck for full architecture and sprint plan.

## Status

- [x] **Sprint 0** (17 Jun) — repo skeleton, schemas, sample claim docs
- [x] **Sprint 1** (18–20 Jun) — OCR Bounding Box Agent
- [x] **Sprint 1.5** (added in response to manager feedback) — multi-format
      ingestion agent (digital PDF, scanned PDF, image, docx, hyperlink) +
      24-document synthetic corpus, 15-22 pages each, across all 3 LOBs.
      See `DATA_STRATEGY.md` for the real-world data sourcing plan.
- [ ] Sprint 2 (21–24 Jun) — Chunking + LLM Extraction Agent
- [ ] Sprint 3 (25–27 Jun) — Provenance + Evidence Verifier
- [ ] Sprint 4 (28 Jun–1 Jul) — Triage + Streamlit demo
- [ ] Sprint 5 (2–4 Jul) — Testing, polish, handover

## Setup

```bash
python3 -m venv venv
source venv/bin/activate          # venv\Scripts\activate on Windows
pip install -r requirements.txt
```

You also need two system packages for the scanned-PDF/image OCR path
(Tesseract itself + the PDF-to-image renderer it relies on):

```bash
# Ubuntu/Debian/WSL
sudo apt-get install tesseract-ocr poppler-utils

# Mac (Homebrew)
brew install tesseract poppler

# Windows: install Tesseract from
# https://github.com/UB-Mannheim/tesseract/wiki and add it to PATH;
# install poppler from https://github.com/oschwartz10612/poppler-windows
# and add its bin/ folder to PATH.
```

## Generate the synthetic test corpus

```bash
# 3 toy 2-page samples (Sprint 0 originals, still useful for quick smoke tests)
python3 samples/generate_samples.py

# 24 realistic multi-document claim packets, 15-22 pages each, all 3 LOBs
python3 -m samples.generate_corpus

# Word doc / standalone image / true scanned-PDF fixtures
python3 -m samples.generate_other_formats
```

This writes `outputs/corpus_manifest.json` — the ground-truth record
for all 24 claims, including which field (if any) was deliberately
left out of each document and whether its dates are internally
consistent. Use this to actually score extraction accuracy in Sprint 2
instead of eyeballing it.

## Run ingestion across everything

```bash
python3 -m agents.ocr_agent          # original Sprint 1 digital-PDF-only path
python3 -m agents.ingestion_agent samples/corpus/auto/AUTO-001.pdf
python3 -m agents.ingestion_agent samples/other_formats/AUTO-002_scanned.pdf
python3 -m agents.ingestion_agent samples/other_formats/repair_receipt_photo.png
python3 -m agents.ingestion_agent samples/other_formats/claimant_followup_letter.docx
```

## Run tests

```bash
python3 -m pytest tests/ -v
```

24 tests across `test_pipeline.py` (Sprint 1 exit criteria) and
`test_ingestion.py` (every format type, the local-server hyperlink
path, and corpus-level checks: 20-25 docs, 15-22 pages each, all 3
LOBs present, noise actually injected).

## Design note: who owns coordinates?

The ingestion agent (`agents/ingestion_agent.py`) is the **only** place
in the pipeline allowed to produce a bounding box. From Sprint 2
onward, the LLM only ever cites an existing `block_id` as evidence —
it never outputs coordinates itself. This is what makes the provenance
layer trustworthy: every field's bbox is deterministic, not
LLM-generated.

| Source type | Who assigns the bbox | Confidence meaning |
|---|---|---|
| Digital PDF | PyMuPDF text layer | Always 1.0 — there's no recognition step |
| Scanned PDF / image | Tesseract | Real OCR confidence, varies per line |
| .docx | N/A — `bbox=None` | Provenance falls back to paragraph index + snippet |

## Repo structure

```
claimlens-agentic-mvp/
├── DATA_STRATEGY.md             # real-data sourcing plan + corpus design rationale
├── app.py                       # Streamlit demo (Sprint 4)
├── requirements.txt
├── README.md
├── agents/
│   ├── ocr_agent.py              # Sprint 1 — digital-PDF-only path (DONE)
│   ├── ingestion_agent.py        # Sprint 1.5 — multi-format router (DONE)
│   ├── chunking_agent.py         # Sprint 2
│   ├── llm_extraction_agent.py   # Sprint 2
│   ├── provenance_agent.py       # Sprint 3
│   ├── verifier_agent.py         # Sprint 3
│   ├── triage_agent.py           # Sprint 4
│   └── summary_agent.py          # Sprint 4
├── core/
│   ├── schemas.py                # ClaimState, OCRBlock, ExtractedField...
│   ├── state.py                  # load/save ClaimState helpers
│   └── config.py                 # field schemas, thresholds
├── samples/
│   ├── generate_samples.py       # 3 toy 2-page samples (Sprint 0)
│   ├── generate_corpus.py        # 24 multi-page claim packets (Sprint 1.5)
│   ├── generate_other_formats.py # docx / image / scanned-PDF fixtures
│   ├── corpus_data.py            # value pools (real ICD-10/CPT codes, etc.)
│   ├── pdf_writer.py             # reusable multi-page PDF writer
│   ├── auto_claim_01.pdf / property_claim_01.pdf / health_claim_01.pdf
│   ├── corpus/{auto,property,health}/*.pdf   # the 24-doc corpus
│   └── other_formats/            # docx, image, scanned-PDF fixtures
├── outputs/
│   └── corpus_manifest.json      # ground truth + injected noise per claim
└── tests/
    ├── test_pipeline.py          # Sprint 1 exit criteria
    └── test_ingestion.py         # multi-format + corpus-level checks
```

