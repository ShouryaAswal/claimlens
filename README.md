# ClaimLens v2

Agentic OCR/document-understanding + LLM claims-intake MVP.
Insurance AI Platform Internship · Sprints 0 & 1 complete (19–21 Jun 2026).

This repo accelerates **steps 2–5 of the claims lifecycle** (FNOL intake →
basic validation → triage) and hands a structured, evidence-linked work
product to the human adjuster. It does **not** do coverage verification,
investigation, valuation, settlement, or payment — those stay with licensed
humans. See `ClaimLens_v2_Design_and_Sprint_Plan.md` for the full
architecture and sprint plan.

## Status

| Sprint | Scope | Status |
|---|---|---|
| **0** | Schema authoring (Auto/Property/Health field schemas), repo skeleton, Pydantic models | ✅ Done |
| **1** | Multi-format ingestion: PDF (digital + scanned/OCR), DOCX, PPTX, images, hyperlinks; long-document handling | ✅ Done |
| 2 | LOB classification, doc-type tagging, Gate Check, section-wise extraction | Not started |
| 3 | Merge agent, provenance linking, evidence verifier | Not started |
| 4 | Triage agent, reviewer summary agent | Not started |
| 5 | Streamlit frontend | Not started |
| 6 | Testing, polish, demo | Not started |

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate   # Python 3.11 recommended
pip install -r requirements.txt

# System dependency (not pip-installable):
sudo apt-get install tesseract-ocr      # Ubuntu/Debian
# brew install tesseract                # macOS
```

Generate synthetic sample claim documents (one per supported format, plus a
22-page stress test):

```bash
python3 scripts/generate_samples.py
```

Run the ingestion demo over all samples (writes `outputs/ingestion_demo_result.json`):

```bash
python3 scripts/run_ingestion_demo.py
```

Run the test suite:

```bash
python3 -m pytest tests/ -v
```

## What Sprint 0 built: Schema Resolution

`schemas/auto.json`, `schemas/property.json`, `schemas/health.json` — each
maps a Line of Business to **sections → fields**, mirroring how the real
forms are organized. This is a deterministic lookup, not an LLM call: once a
claim is classified, the field list to extract is already known.

- **Auto** and **Property** are inspired by ACORD 2 (Automobile Loss Notice)
  and ACORD 1 (Property Loss Notice) — the real P&C industry-standard FNOL
  forms. We use our own field names/JSON, never the ACORD form template
  itself (copyrighted).
- **Health** is explicitly *not* ACORD — standard health claims use
  CMS-1500 (professional) / UB-04 (institutional), governed by NUCC/NUBC.
  `schemas/health.json` says this directly in `source_concept`, and
  `tests/test_schemas.py::test_health_schema_explicitly_disclaims_acord`
  guards against that distinction quietly disappearing later.

`core/schema_loader.py` loads and validates these against the
`LOBSchema` Pydantic model (cached — LOBs don't change at runtime).

## What Sprint 1 built: Multi-format ingestion

Single entry point: `agents.ingestion.dispatcher.ingest(source)`, where
`source` is a local file path **or** an `http(s)://` URL. Returns a
`DocumentRecord` full of `ContentBlock`s — the universal evidence unit every
later agent will cite by `block_id`, never by inventing a coordinate.

| Format | Parser | Provenance |
|---|---|---|
| PDF (digital) | PyMuPDF (`fitz`) layout analysis | Real bbox, page, 1.0 confidence |
| PDF (scanned / image-only page) | PyMuPDF rasterize → Tesseract OCR | Real bbox (mapped back to PDF point space), OCR confidence |
| DOCX | `python-docx` (paragraphs + tables) | `locator` only — flowing doc, no fixed bbox |
| PPTX | `python-pptx` (text-frame shapes) | Real bbox (slides are a fixed canvas — shape geometry converted from EMU to points) |
| PNG/JPG/TIFF/BMP | Tesseract OCR | Real bbox, OCR confidence |
| Hyperlink (`http://`/`https://`) | Content-Type sniffed → routed to the matching parser above, or HTML text extraction | Inherits the matched parser's provenance, or `locator`-only for HTML |

Design choices worth knowing about:

- **A PDF page is judged independently** for digital-vs-scanned. A real
  claim packet routinely mixes a digitally-generated estimate with a scanned
  signed police report in the same file — both are handled correctly.
- **Long documents (20–25+ pages)** are not a special code path, just
  page-by-page processing with a logged warning above
  `LONG_DOCUMENT_PAGE_WARNING_THRESHOLD` (20) so processing time is visible.
  Validated against a 22-page synthetic PDF in both `scripts/generate_samples.py`
  and `tests/test_ingestion.py::test_long_document_22_pages`.
- **Hyperlink ingestion** downloads and routes through the same parsers as
  local uploads — a link to a PDF is treated identically to an uploaded PDF.
  Tested against a real local HTTP server (`tests/test_ingestion.py`'s
  `local_http_server` fixture), not the live internet, so the test suite
  doesn't depend on external network access.
- **`ingest_many()` never lets one bad file abort a whole claim** — a
  corrupted attachment is logged and recorded with an `INGESTION FAILED`
  warning on its own `DocumentRecord`, while the rest of the bundle still
  processes.
- **OCR engine is Tesseract, not PaddleOCR**, for sandbox/laptop-friendly
  installs. The output contract (`ocr_utils.ocr_image_to_lines` → list of
  `{text, bbox, confidence}`) is engine-agnostic — swapping in PaddleOCR
  later for better multilingual accuracy is a rewrite of one function, not
  the callers.
- **No LangChain.** Evaluated and declined for this layer: LangChain's
  document loaders wrap the same libraries used here directly
  (`python-docx`, OCR, etc.), so adopting it wouldn't reduce real code, just
  add `langchain-core`/`langchain-community`'s dependency tree on top of an
  already-pinned `pydantic>=2,<3` — the exact category of conflict that
  caused issues in SunLeo DJ. Worth revisiting per-feature later (e.g. if a
  retrieval layer is added) rather than as a blanket policy.

## Repository structure

```
claimlens-agentic-mvp/
  README.md
  requirements.txt
  schemas/
    auto.json          # ACORD-2-inspired field concepts
    property.json       # ACORD-1-inspired field concepts
    health.json          # CMS-1500/UB-04-inspired field concepts (NOT ACORD)
  core/
    schemas.py           # Pydantic models: ContentBlock, DocumentRecord,
                          # FieldDefinition, SectionDefinition, LOBSchema,
                          # ExtractedField, ClaimState
    schema_loader.py      # deterministic LOB -> LOBSchema lookup
    config.py             # shared constants
  agents/
    ingestion/
      base.py             # shared exceptions
      ocr_utils.py         # Tesseract wrapper, word->line grouping
      pdf_parser.py         # digital + OCR-fallback PDF parsing
      office_parser.py      # DOCX + PPTX parsing
      image_parser.py        # standalone image OCR
      url_parser.py           # hyperlink fetch + content-type routing + HTML extraction
      dispatcher.py            # single public entry point: ingest() / ingest_many()
  samples/                # synthetic sample claim docs (generated, not real claims)
  scripts/
    generate_samples.py    # creates samples/ fixtures
    run_ingestion_demo.py    # ingests all samples, writes outputs/ingestion_demo_result.json
  outputs/                # generated JSON results (gitignored except .gitkeep)
  tests/
    test_schemas.py         # Sprint 0
    test_ingestion.py        # Sprint 1
```

## Next up: Sprint 2

LOB classifier (fast/cheap call), document-type tagger, Gate Check
(deterministic — compares ingested doc types against each schema's
`mandatory_doc_types`), and the section-wise extraction agent (Gemini 3
Flash, full corpus per section call, `block_id`-only citations — see the
design doc for why this resolves the "150 fields / one context window"
problem without a retrieval index).
