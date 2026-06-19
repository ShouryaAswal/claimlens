# ClaimLens — Agentic OCR + LLM Claims Extraction MVP

Internship MVP demonstrating: OCR bounding-box extraction → LLM field
extraction → provenance linking → verification → triage. See the
project deck for full architecture and sprint plan.

## Status

- [x] **Sprint 0** (17 Jun) — repo skeleton, schemas, sample claim docs
- [x] **Sprint 1** (18–20 Jun) — OCR Bounding Box Agent
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

## Generate sample claim documents

Already generated and committed under `samples/`, but to regenerate:

```bash
python3 samples/generate_samples.py
```

## Run the OCR agent

```bash
python3 -m agents.ocr_agent
```

This processes all 3 sample claims (auto/property/health) and writes
`outputs/<name>_ocr_blocks.json` for each, with one entry per detected
text block: `block_id`, `page`, `text`, `bbox`, `ocr_confidence`,
`source_file`.

## Run tests

```bash
python3 -m pytest tests/ -v
```

## Design note: who owns coordinates?

The OCR agent (`agents/ocr_agent.py`) is the **only** place in the
pipeline allowed to produce a bounding box. From Sprint 2 onward, the
LLM only ever cites an existing `block_id` as evidence — it never
outputs coordinates itself. This is what makes the provenance layer
trustworthy: every field's bbox is deterministic, not LLM-generated.

Today's OCR path handles **digital (text-layer) PDFs** via PyMuPDF,
which is exact and free. Scanned/image-only documents would route to
PaddleOCR (`agents/ocr_agent.py::run_paddle_ocr`, currently a stub) —
deferred until the digital path is fully validated, since PaddleOCR
needs a model download and isn't needed for this week's sample set.

## Repo structure

```
claimlens-agentic-mvp/
├── app.py                      # Streamlit demo (Sprint 4)
├── requirements.txt
├── README.md
├── agents/
│   ├── ocr_agent.py             # Sprint 1 — DONE
│   ├── chunking_agent.py        # Sprint 2
│   ├── llm_extraction_agent.py  # Sprint 2
│   ├── provenance_agent.py      # Sprint 3
│   ├── verifier_agent.py        # Sprint 3
│   ├── triage_agent.py          # Sprint 4
│   └── summary_agent.py         # Sprint 4
├── core/
│   ├── schemas.py               # ClaimState, OCRBlock, ExtractedField...
│   └── config.py                # field schemas, thresholds
├── samples/
│   ├── generate_samples.py
│   ├── auto_claim_01.pdf
│   ├── property_claim_01.pdf
│   └── health_claim_01.pdf
├── outputs/                     # OCR blocks JSON, per claim
└── tests/
    └── test_pipeline.py
```
