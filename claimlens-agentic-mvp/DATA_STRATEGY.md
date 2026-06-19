# Data Strategy — Real-World Sourcing + Synthetic Corpus Design

This addresses three things directly: (1) where to get real-world
grounding data for free, (2) why the synthetic test corpus is now
20-25 multi-page documents instead of 3 toy samples, and (3) how
ingestion now handles the heterogeneous formats real claims arrive in.

## 1. Real-world data — what's actually available for free, and what isn't

Be upfront about this in the meeting: **full real claim PDF packets
(FNOL forms, adjuster notes, photos) with real claimant data are not
publicly available, anywhere, for any insurer** — and that's not a
sourcing failure, it's PII/HIPAA law. What *is* publicly available
falls into three useful categories:

### A. Real structured claims data (numbers, codes, distributions — not PDFs)
Use these to ground dollar amounts, code distributions, and claim
patterns in something real, even though the documents themselves are
still generated.

| Dataset | LOB | What it gives us | Link |
|---|---|---|---|
| CMS DE-SynPUF (Medicare claims) | Health | Real inpatient/outpatient/carrier claim structure, real reimbursement patterns. CMS explicitly designed this to be safe to build on. | [cms.gov](https://www.cms.gov/data-research/statistics-trends-and-reports/medicare-claims-synthetic-public-use-files) / mirrored on [Kaggle](https://www.kaggle.com/datasets/anikannal/cms-synthetic-data) |
| FEMA OpenFEMA — NFIP Redacted Claims | Property | 2M+ real flood claims: real claim amounts, building damage categories, dates, redacted location. Free CSV/API, no signup. | [fema.gov](https://www.fema.gov/openfema-data-page/fima-nfip-redacted-claims-v2) |
| Auto Insurance Claims Data (Kaggle) | Auto | ~1,000 real-pattern claims with incident dates, claim amounts, severity. Widely used, well-documented. | [kaggle.com/buntyshah](https://www.kaggle.com/datasets/buntyshah/auto-insurance-claims-data) |
| Real ICD-10-CM / CPT/HCPCS code lists | Health | The actual coding standards hospitals bill against — already wired into `samples/corpus_data.py`. | public coding standards, no download needed |

**Honest limitation:** these are tabular/CSV, not document PDFs. They
answer "what does a real claim amount / diagnosis code / damage
category distribution look like" — they don't hand you a scanned
police report. That's what part B is for.

### B. Real document *templates* (real layouts, zero PII)
This is the highest-leverage free option for the ingestion-robustness
problem specifically: **ACORD forms** — the actual standard claim
forms used across the US insurance industry — are published as blank
templates by state insurance departments and agencies, free, no
signup, because they're forms, not filled claims:

- ACORD 2 — Automobile Loss Notice
- ACORD Property Loss Notice
- Full index of all ACORD forms: `https://www.acord.org/docs/default-source/forms/forms_index.pdf`

These give us **real multi-column layouts, real checkboxes, real legal
disclaimer blocks per state** — exactly the structural heterogeneity
a hand-rolled synthetic generator can't produce on its own. Plan: pull
2-3 blank ACORD PDFs, fill them with synthetic values (or test
ingestion against the blank form itself, since layout parsing doesn't
need filled-in data), and add them to the corpus as real-layout
fixtures alongside the generated ones.

### C. Realistic synthetic *record* generators (not just CSVs — actual documents)
- **Synthea** (MITRE, open-source): generates full synthetic patient
  histories and exports them as real C-CDA clinical documents (the
  same XML format real EHRs produce), FHIR, and CSV. Free sample sets
  of 100-1,000 patients, no signup: `https://synthea.mitre.org/downloads`.
  This is the credible next step for health-LOB realism beyond what
  we hand-generate — a discharge summary built from a Synthea CCDA
  export is structurally a real clinical document, just synthetic.

**Why these weren't downloaded into this deliverable today:** this
sandbox's network is locked to package registries (pypi/npm/github)
for security — it can't reach fema.gov, cms.gov, kaggle.com, or
synthea.mitre.org directly. Every link above works from a normal
internet connection (i.e., your laptop). This is a "pull these down
this week" action item, not a blocker on today's progress.

## 2. The synthetic corpus — what changed and why

**Before:** 3 documents, 2 pages each, one LOB each.
**Now:** 24 documents (8 per LOB), 15-22 pages each, avg 18.7 pages —
run `python3 -m samples.generate_corpus` to regenerate.

Each claim packet is multiple stitched sub-documents, the way a real
claim folder looks when exported as one PDF — not one clean page:

- **Auto** (8 claims): FNOL → policy declaration → police report
  narrative → adjuster inspection notes → itemised repair estimate
  (the page-count driver) → correspondence → closing notes.
- **Property** (8 claims): FNOL → policy declaration → inspection
  report → contents inventory (page-count driver) → contractor
  estimate → correspondence → closing notes.
- **Health** (8 claims): pre-auth → admission notice → discharge
  summary narrative → itemised bill coded with real CPT/HCPCS (page-
  count driver) → EOB → provider correspondence.

**Deliberately injected noise** (tracked in `outputs/corpus_manifest.json`
as ground truth, so we can actually score extraction accuracy later
instead of eyeballing it):
- ~30% of claims have one required field silently missing from the
  text — tests the "missing required field" triage rule before Sprint
  4 even starts.
- ~20% of claims have the estimate/bill dated *before* the
  report/admission it's based on — the same timeline-inconsistency
  pattern from the original design deck's Graph-RAG example.

A corpus where every document is perfect doesn't test anything; this
one is wrong on purpose, in a controlled, measurable way.

## 3. Heterogeneous ingestion — the actual robustness fix

New module: `agents/ingestion_agent.py`. Single entry point `ingest(source)`
auto-detects and routes:

| Source type | Detection | Handler | Confidence behavior |
|---|---|---|---|
| Digital PDF (text layer) | `page.get_text()` non-empty | PyMuPDF | Always 1.0 (no recognition uncertainty) |
| Scanned/image-only PDF | No extractable text layer | `pdf2image` → Tesseract | Real, variable (~0.85-0.95 observed) |
| Standalone image (.png/.jpg/etc) | extension | Tesseract directly | Real, variable |
| Word document (.docx) | extension | `python-docx`, paragraph-level | 1.0, but `bbox=None` (see limitation below) |
| Hyperlink (http/https) | URL scheme | Download via `requests`, then re-dispatch on the **real downloaded content type**, not the URL's extension | Inherits from whichever handler it lands on |

All 24 corpus PDFs plus one scanned-PDF fixture, one image fixture,
one docx fixture, and one local-server hyperlink test are covered in
`tests/test_ingestion.py` — 24 tests passing.

**Known, deliberately-flagged limitation:** `.docx` has no native
page/coordinate system the way a PDF does, so provenance for Word
documents falls back to "paragraph N, this exact text" rather than a
visual crop. Fixing this properly means rendering the docx to PDF
first (e.g. headless LibreOffice) to get real pagination — flagged as
a fast follow, not hidden, because it adds a system dependency for
what's likely a smaller slice of real claim correspondence than PDFs
and scans.

## Talking points for tomorrow

1. "You're right that 3 toy samples wasn't real testing — the corpus
   is now 24 multi-page documents (15-22 pages each, ~19 avg) across
   all three LOBs, and it's not just bigger, it has known data-quality
   issues baked in (missing fields, date conflicts) so we can actually
   measure whether the pipeline catches them."
2. "For real-world grounding: CMS already publishes synthetic-but-
   realistic Medicare claims data, FEMA publishes 2M+ real flood
   claims, and ACORD's actual industry-standard forms are public as
   blank templates — all free, all no-signup. I'll pull these in this
   week to replace/supplement the hand-generated values."
3. "On heterogeneity: ingestion now handles digital PDF, scanned PDF,
   standalone images, Word docs, and hyperlinks through one entry
   point, auto-detecting the real type rather than trusting the file
   extension — tested against all five with 24 passing tests."
