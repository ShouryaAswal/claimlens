# ClaimLens v2

Agentic OCR/document-understanding + LLM claims-intake MVP.
Insurance AI Platform Internship · Sprints 0–4 complete (19 Jun – 1 Jul 2026).

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
| **1** | Multi-format ingestion: PDF (digital + scanned/OCR), DOCX, PPTX, images, hyperlinks, nested claim folders; long-document handling; dual OCR engines (Tesseract + PaddleOCR) | ✅ Done |
| **2** | LOB classification, doc-type tagging, Gate Check, section-wise extraction | ✅ Done |
| **3** | Merge agent, provenance crop rendering, evidence verifier (exact/fuzzy matching), confidence rating, optional LLM second opinion, human review queue | ✅ Done |
| **4** | Triage agent (forced-review override rule), reviewer summary agent | ✅ Done |
| 5 | Streamlit frontend | Not started |
| 6 | Testing, polish, demo | Not started |

**185 tests passing.** `.env` is loaded automatically (`core/env.py`) — see
`.env.example`. See `SPRINT_4_NOTES.md` for the triage/summary architecture.

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate   # Python 3.11 recommended
pip install -r requirements.txt

# System dependency (not pip-installable):
sudo apt-get install tesseract-ocr      # Ubuntu/Debian
# brew install tesseract                # macOS
```

Optional, for the PaddleOCR engine (see `PADDLEOCR_SETUP.md`) and the
LLM-backed agents (see `SPRINT_2_NOTES.md`):
```bash
pip install paddlepaddle paddleocr   # PaddleOCR engine
```

Copy `.env.example` to `.env` and fill in your keys to enable real LLM
calls (Groq + Gemini are installed by default now — `requirements.txt`
includes `openai`, `google-genai`, and `python-dotenv`):
```bash
cp .env.example .env   # then edit .env with your real GROQ_API_KEY / GOOGLE_API_KEY
```
`.env` is gitignored and loaded automatically (`core/env.py`) — nothing
else to wire up. Without it, every agent still runs in rule-based/demo
mode (see each sprint's NOTES.md for exactly what that means per agent).

Generate synthetic sample claim documents (one per supported format, plus a
22-page stress test):

```bash
python3 scripts/generate_samples.py
python3 scripts/generate_fnol_specimens.py     # authentic real-government-form specimens
python3 scripts/generate_realistic_scans.py    # Augraphy-degraded realistic scans
```

Run the ingestion demo over all samples (writes `outputs/ingestion_demo_result.json`):

```bash
python3 scripts/run_ingestion_demo.py
```

Run the Sprint 2 pipeline demo (ingest → classify LOB → resolve schema →
tag doc types → Gate Check → extraction if an LLM key is configured):

```bash
python3 scripts/run_sprint2_demo.py
```

Run the Sprint 3 pipeline demo (adds evidence verification, confidence
rating, crop generation, and the human review queue on top of Sprint 2 —
without an LLM key, it plants a deliberate single-digit error to prove the
verifier actually catches it):

```bash
python3 scripts/run_sprint3_demo.py
```

Run the Sprint 4 pipeline demo (adds triage and the reviewer summary on
top of Sprint 3 — the full pipeline, end to end):

```bash
python3 scripts/run_sprint4_demo.py
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
- **OCR engine is selectable: Tesseract (default) or PaddleOCR**, via
  `agents/ingestion/ocr_engines/` (a `factory.py` that auto-falls-back to
  Tesseract if PaddleOCR isn't installed or its model download can't reach
  a host — see `PADDLEOCR_SETUP.md`). The output contract
  (`{text, bbox, confidence}`) is identical regardless of engine, so
  `pdf_parser.py`/`image_parser.py` never need to know which one ran.
- **Real-world and realistically-degraded test data** lives in
  `samples/real_world/` (genuinely real noisy scans + authentic
  government-form content) and `samples/synthetic_realistic/`
  (Augraphy-degraded scans, three severity tiers) — see
  `samples/real_world/REAL_DATA_SOURCES.md` for exactly what's real vs.
  recreated vs. synthetic, and why.
- **Nested claim folders** are supported via
  `dispatcher.discover_files()` / `ingest_claim_folder()` — recursively
  walks a directory (`fnol/`, `evidence/`, `correspondence/` subfolders,
  mixed formats) and also reads a `claim_links.txt` manifest for documents
  that live elsewhere (a portal, cloud storage) instead of being attached
  directly. See `samples/example_claim_folder/`.
- **No LangChain.** Evaluated and declined for this layer: LangChain's
  document loaders wrap the same libraries used here directly
  (`python-docx`, OCR, etc.), so adopting it wouldn't reduce real code, just
  add `langchain-core`/`langchain-community`'s dependency tree on top of an
  already-pinned `pydantic>=2,<3` — the exact category of conflict that
  caused issues in SunLeo DJ. Worth revisiting per-feature later (e.g. if a
  retrieval layer is added) rather than as a blanket policy.

## What Sprint 2 built: classification, Gate Check, and section extraction

Four agents, two of them with a no-API-key-required default mode (see
`SPRINT_2_NOTES.md` for exactly what was/wasn't tested against a live LLM):

| Agent | Mode | Behavior |
|---|---|---|
| `lob_classifier_agent.py` | Rule-based (default) | IDF-weighted keyword scoring against each schema's own vocabulary (field labels + synonyms + mandatory_doc_types — no separate keyword list to maintain) |
| | LLM-backed (opt-in) | Single cheap/fast Groq call |
| `doc_type_tagger_agent.py` | Rule-based (default) | Keyword scoring with a heading-position bonus (a document's title is much stronger evidence of its type than an incidental mid-text mention) and a minimum-evidence floor below which it honestly returns `unknown` rather than guessing |
| | LLM-backed (opt-in) | Single cheap/fast Groq call |
| `gate_check.py` | Deterministic, always | Set-difference between tagged doc types present and the resolved schema's `mandatory_doc_types` — no LLM involved, by design |
| `section_extraction_agent.py` | LLM-backed, no fallback exists | One call per schema section (5–15 fields, full claim corpus in context), `block_id`-only citations |

**The anti-hallucination guard that matters most:** every `block_id` an
extraction response cites is checked against the claim's actual block set.
A citation pointing at a `block_id` that doesn't exist is dropped; a field
with zero surviving real citations is demoted from `"found"` to
`"missing"` rather than trusted. This is enforced in code
(`extract_section()`), not just requested in the prompt — see
`tests/test_section_extraction.py::test_extract_section_drops_hallucinated_block_id_citation`.

**Missing fields are explicit, never silently dropped:** every field a
schema section asks for gets an entry in the result, even if the LLM's JSON
omitted it entirely — `tests/test_section_extraction.py::test_extract_section_explicitly_lists_field_llm_completely_omitted`
is the literal Sprint 2 exit criterion as a test.

Three real classification bugs were caught and fixed while testing against
the real-world/realistic data added this round (not hypothetical edge
cases — see the regression tests in `test_lob_classifier.py` and
`test_doc_type_tagger.py` for what actually broke and why):
1. Generic shared terms (e.g. "policy number") outweighing distinctive ones
   in LOB scoring → fixed with IDF-style term weighting.
2. A 3-letter code (`RCV`) filtered out by an overly aggressive minimum
   term length → fixed by lowering the floor.
3. An incidental mid-sentence mention ("...awaiting police report
   confirmation") outscoring a document's actual title ("Adjuster Note") →
   fixed with a heading-position bonus.

## Why no LangChain here either

Same reasoning as Sprint 1: `core/llm_client.py` is two HTTP-calling
functions (Groq via its OpenAI-compatible endpoint, Gemini via
`google-genai`), not a chain, agent graph, or retriever — there's nothing
here LangChain would meaningfully simplify, and it would reintroduce the
same dependency-pinning risk flagged before. If Sprint 3+ ever needs actual
retrieval (a vector store, a multi-step agent loop with tool-calling),
that's a genuine case to re-evaluate, not before.

## What Sprint 3 built: verification that a single digit error can't slip through

The safety-critical round. Five new modules, all built around one
non-negotiable rule, stated in full in `SPRINT_3_NOTES.md` and enforced in
code, not just policy: **for numeric/date/code fields, an exact-match
failure is final — no LLM agreement, no confidence score, nothing
overrides it.**

| Module | Job |
|---|---|
| `evidence_verifier.py` | Does the cited evidence TEXT actually contain this value? Numbers/dates/codes get exact matching (zero tolerance — `$4,250` vs `$4,259` fails even though it's 85% similar as a string); text/boolean get fuzzy matching (OCR noise on a name is forgivable) |
| `confidence_rating.py` | Combines the match result + the cited evidence's own OCR confidence + the extraction agent's confidence + an optional LLM second opinion → one `risk_level`: `ok` / `needs_review` / `high_risk` |
| `llm_evidence_verifier.py` | Optional semantic second opinion (catches things string-matching can't, e.g. "5:45 AM" vs "5:45 PM" — high similarity, different fact) — can *escalate* a field, can never *downgrade* a critical-field failure |
| `provenance_agent.py` | Renders an actual crop image from a block's bbox — "every accepted field traces to a real crop," not just a citation |
| `merge_agent.py` | When a field's multiple evidence citations (or independent extraction candidates) disagree on a critical-type value, it becomes `status: "conflicting"` — never silently resolved by majority vote or confidence |
| `human_review_queue.py` | Flattens every flagged field into a sorted, self-contained queue (value, reasons, crop paths) — the literal handoff point for Sprint 5's reviewer UI |

**A real bug this caught, not a hypothetical one:** building the Sprint 3
demo against the actual example claim folder surfaced a genuine collision
— two photos in the same claim both produced a block called `img_b006`
(each format parser numbers its own blocks from 1, independently), so
`claim.get_block()` was silently returning the wrong photo's text as
"evidence." Fixed at the one place every `DocumentRecord` is created
(`dispatcher.py`'s `_namespace_block_ids()`) and locked in with a
regression test. Full writeup in `SPRINT_3_NOTES.md` — kept visible
deliberately, since it's a good demonstration of exactly the failure mode
this sprint's tests exist to surface.

## What Sprint 4 built: triage and the reviewer summary

Two agents, closing the loop from "here's what we found" to "here's what
you should do about it":

| Module | Job |
|---|---|
| `triage_agent.py` | Rule-based composite score (missing mandatory docs, needs_review/high_risk fields, high-value-claim escalation) → `stp_candidate` / `needs_review` / `high_risk_incomplete` |
| `reviewer_summary_agent.py` | Turns completion stats + the triage verdict + the human review queue into a short adjuster-readable brief — rule-based template by default (never invents a fact), LLM-backed prose when a key is configured |

**The rule that carries through from Sprint 3, one layer up:** a
`HIGH_RISK` verification result on a **required** field sets
`forced_review=True` on the `TriageVerdict`, which makes `stp_candidate`
impossible for that claim regardless of how low the rest of the composite
score is. A claim can't be auto-approved for straight-through processing
because nine fields are perfect if the tenth is a wrong dollar amount —
same non-negotiable principle as "an LLM agreeing cannot override a
deterministic critical-field failure," now enforced one level up the
pipeline instead of just at the field level.
(`tests/test_triage_agent.py::test_high_risk_required_field_forces_review_even_with_otherwise_low_score`)

`reviewer_summary_agent.py`'s rule-based mode is deliberately built so
every sentence is a direct readout of an already-computed number or reason
string — it cannot hallucinate a fact about the claim, because it never
generates one; it only assembles ones that already exist elsewhere in
`ClaimState`. The LLM-backed mode is explicitly instructed not to invent
facts either, and falls back to the rule-based template if the call fails
or returns something empty/unusable — same resilience pattern as every
other LLM-touching agent in this project.

## `.env` support

`core/env.py` loads a `.env` file (via `python-dotenv`) before any agent
reads `GROQ_API_KEY`, `GOOGLE_API_KEY`, or `CLAIMLENS_OCR_ENGINE` — see
`.env.example` for the template. A real `export`/`set` environment variable
always takes priority over a value sitting in `.env` (`override=False`).
If `python-dotenv` isn't installed, this degrades to "environment
variables still work if exported the normal way" rather than crashing.

## Repository structure

```
claimlens-agentic-mvp/
  README.md
  PADDLEOCR_SETUP.md      # PaddleOCR install/setup/troubleshooting guide
  SPRINT_2_NOTES.md         # LLM client setup, what was/wasn't live-tested
  ClaimLens_v2_Design_and_Sprint_Plan.md
  requirements.txt
  schemas/
    auto.json          # ACORD-2-inspired field concepts
    property.json       # ACORD-1-inspired field concepts
    health.json          # CMS-1500/UB-04-inspired field concepts (NOT ACORD)
  core/
    schemas.py           # Pydantic models: ContentBlock, DocumentRecord,
                          # FieldDefinition, SectionDefinition, LOBSchema,
                          # ExtractedField, ClaimState, FieldVerification,
                          # ReviewQueueItem, TriageVerdict
    schema_loader.py      # deterministic LOB -> LOBSchema lookup
    config.py             # shared constants (incl. OCR_ENGINE selection)
    llm_client.py          # Groq + Gemini client wrappers, env-var configured
    env.py                  # loads .env (see .env.example) before config/llm_client read env vars
  agents/
    lob_classifier_agent.py        # Sprint 2
    doc_type_tagger_agent.py        # Sprint 2
    gate_check.py                    # Sprint 2 (deterministic)
    section_extraction_agent.py       # Sprint 2 (LLM-backed, no fallback)
    evidence_verifier.py               # Sprint 3 (exact match for number/date/code, fuzzy for text)
    confidence_rating.py                # Sprint 3 (composite risk_level, LLM-cannot-override rule)
    llm_evidence_verifier.py             # Sprint 3 (optional semantic second opinion)
    provenance_agent.py                   # Sprint 3 (block_id -> crop image)
    merge_agent.py                         # Sprint 3 (multi-citation/candidate conflict resolution)
    human_review_queue.py                   # Sprint 3 (basis for Sprint 5's reviewer UI)
    triage_agent.py                          # Sprint 4 (forced-review override rule)
    reviewer_summary_agent.py                 # Sprint 4 (rule-based template + optional LLM prose)
    ingestion/
      base.py             # shared exceptions
      ocr_utils.py         # backward-compat shim -> ocr_engines/factory.py
      ocr_engines/
        base.py             # OCRLine/OCREngine contract
        tesseract_engine.py  # default engine
        paddleocr_engine.py   # optional "special feature" engine
        factory.py             # engine selection + auto-fallback
      pdf_parser.py         # digital + OCR-fallback PDF parsing
      office_parser.py      # DOCX + PPTX parsing
      image_parser.py        # standalone image OCR
      url_parser.py           # hyperlink fetch + content-type routing + local/fetched HTML
      dispatcher.py            # ingest() / ingest_many() / discover_files() / ingest_claim_folder()
                                 # + _namespace_block_ids() (global block_id uniqueness, Sprint 3 fix)
  samples/                # sample claim docs -- several tiers, see below
    *.pdf, *.docx, *.pptx, *.png   # Sprint 1: clean synthetic ("born-digital")
    real_world/
      REAL_DATA_SOURCES.md          # what's real vs. recreated vs. synthetic, and why
      funsd_scans/                   # genuinely real noisy scanned forms (FUNSD)
      fnol_specimens/                  # authentic real-government-form content
    synthetic_realistic/              # Augraphy-degraded scans, 3 severity tiers
    example_claim_folder/               # realistic nested claim-folder layout demo
  scripts/
    generate_samples.py          # Sprint 1 clean synthetic fixtures
    generate_fnol_specimens.py    # authentic FNOL form specimens
    generate_realistic_scans.py    # Augraphy degradation pipeline
    run_ingestion_demo.py            # ingests all flat samples
    run_sprint2_demo.py               # full Sprint 0-2 pipeline on the example claim folder
    run_sprint3_demo.py                # adds verification/rating/crops/review-queue on top
  outputs/                # generated JSON results + crops/ (gitignored except .gitkeep)
  tests/
    test_schemas.py              # Sprint 0
    test_ingestion.py             # Sprint 1
    test_ocr_engines.py            # Sprint 1 (PaddleOCR/Tesseract factory + fallback)
    test_directory_discovery.py     # Sprint 1 (nested claim folders, link manifests, block_id uniqueness)
    test_real_world_data.py          # Sprint 1 (regression tests against real/realistic data)
    test_lob_classifier.py            # Sprint 2
    test_doc_type_tagger.py            # Sprint 2
    test_gate_check.py                  # Sprint 2
    test_section_extraction.py           # Sprint 2
    test_evidence_verifier.py             # Sprint 3 (the zero-tolerance critical-field tests)
    test_confidence_rating.py              # Sprint 3 (incl. LLM-cannot-override-failure test)
    test_provenance_agent.py                # Sprint 3
    test_merge_agent.py                      # Sprint 3 (incl. never-silently-resolve-conflict tests)
    test_human_review_queue.py                # Sprint 3
    test_triage_agent.py                        # Sprint 4 (incl. forced-review override tests)
    test_reviewer_summary_agent.py               # Sprint 4
```

## Next up: Sprint 5

Streamlit frontend: upload a claim folder (or individual files), run the
full Sprint 0-4 pipeline, and show the filled-schema view with
click-field-to-see-crop, the triage verdict banner, and the reviewer
summary — the actual demo-able UI an adjuster would look at. Every backend
piece it needs (`ingest_claim_folder`, `rate_all_fields`,
`generate_crops_for_claim`, `apply_triage_to_claim`,
`generate_reviewer_summary`) already exists and is tested; Sprint 5 is
wiring, not new agent logic.
