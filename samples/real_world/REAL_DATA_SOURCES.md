# Real-World & Realistic Test Data: Sources, Process, and Honest Limitations

This documents the research behind `samples/real_world/` and
`samples/synthetic_realistic/`, and is deliberately specific about what's
**genuinely real**, what's **authentic-content-recreated**, and what's
**realistically synthetic** -- those are three different things, and
conflating them would undermine the point of testing against real data.

## The core constraint, confirmed

Actual, proprietary insurer claim files are not publicly available, for
exactly the reason anticipated: they contain real people's PII, medical
information, and financial details, and no insurer publishes them. This is
true industry-wide, not a gap in searching. Litigation exhibits (via
PACER/CourtListener) are the closest thing to real claim files in the wild,
but are gated behind per-document fees and account requirements that
weren't practical to clear for this round. So the approach below combines
three legitimately-public alternatives instead of one perfect source.

## 1. Genuinely real, noisy scanned documents: FUNSD

`samples/real_world/funsd_scans/` -- **10 real scanned document images**,
pulled from the FUNSD dataset (Jaume, Ekenel & Thiran, 2019,
arXiv:1905.13538), via a GitHub mirror that bundles a sample subset
(`github.com/errajibadr/ocr_benchmarking`, `dataset/sample/images/`).

These are **not insurance documents** -- FUNSD is a general business-form
dataset (memos, requests, reports) sourced from the Truth Tobacco Industry
Documents archive, scanned at ~100 DPI in the 1980s-90s with real
photocopier/fax noise, skew, and degradation. What makes them valuable here
isn't domain match, it's that they are **real scans with real noise**,
which is exactly the "too clean" problem being fixed. `funsd_ground_truth.json`
(also copied in) has the original human-verified text/layout annotations,
useful as ground truth if you want to measure OCR accuracy quantitatively
rather than just "did it crash."

**License:** FUNSD is distributed for non-commercial research and
educational use. Fine for internship/testing use; don't redistribute these
specific files as part of a commercial product without checking the
license terms at https://guillaumejaume.github.io/FUNSD/ first.

## 2. Authentic-content FNOL specimens: real government forms, faithfully recreated

`samples/real_world/fnol_specimens/` -- 3 PDFs whose **field labels,
section structure, and certification language are reproduced from real,
currently-live government insurance/crash-report forms**, fetched directly
on 2026-06-21:

| File | Real source | Status |
|---|---|---|
| `fema_proof_of_loss_specimen.pdf` | FEMA Form 086-0-09, NFIP Proof of Loss (`fema.gov`) | U.S. federal government work -- public domain (17 U.S.C. §105) |
| `ny_dmv_mv104_specimen.pdf` | NY DMV Form MV-104, Report of Motor Vehicle Crash (`dmv.ny.gov`) | NY State government form, distributed for public filing use |
| `ma_crash_operator_report_specimen.pdf` | MA Motor Vehicle Crash Operator Report (`mass.gov`) | MA state government form, distributed for public filing use |

**Why "specimen," not "the real PDF":** the tooling available in this
environment could fetch and read the *text content* of these forms directly
from the live government sites, but could not retrieve their *raw original
PDF bytes* (the fetch tool auto-extracts PDF text rather than returning a
file). Rather than either (a) silently treating extracted text as good
enough and never producing a realistic file, or (b) inventing field names
from scratch, `scripts/generate_fnol_specimens.py` lays out the **authentic
field structure** (verified against the live source, with the exact source
URL cited in the script's docstring) as a fresh PDF. The data values filled
into the fields (names, dates, policy numbers) are fictional test data --
the *form structure itself* is real.

If you want the literal original PDFs for a closer visual match, the URLs
above are directly downloadable on any machine with normal internet access
-- they're blocked specifically from this sandbox's network policy, not
from the public internet.

## 3. Realistically degraded synthetic scans: Augraphy

`samples/synthetic_realistic/` -- the clean, "too dummy-like" Sprint-1
synthetic documents (and the FNOL specimens above) run through
[Augraphy](https://github.com/sparkfish/augraphy), the same open-source
document-degradation library used to build the ShabbyPages OCR benchmark.
Three severity tiers per source page:

| Tier | Effects | Looks like |
|---|---|---|
| `light` | slight rotation, paper noise texture, mild JPEG recompression | A decent flatbed scan |
| `medium` | + ink bleed, heavier paper noise, stronger JPEG compression | An office scanner overdue for cleaning |
| `heavy` | + page folding, bad-photocopy noise, uneven lighting gradient | A faxed document, photocopied several generations removed from the original |

This is **synthetic**, not real -- but it's a legitimate, well-established
way to stress-test OCR robustness when real noisy domain data isn't
available, and it's exactly the fallback path planned for if real data
couldn't be found. `tests/test_real_world_data.py::test_augraphy_degraded_scan_survives_ocr`
confirms the pipeline produces output even at the `heavy` tier rather than
silently failing.

## 4. A realistic nested claim-folder layout

`samples/example_claim_folder/CLM-2026-04821/` demonstrates the directory
structure a real claim packet plausibly arrives in -- not one flat folder,
but `fnol/`, `evidence/`, `correspondence/` subdirectories with mixed
formats (PDF, PNG, HTML), plus a `claim_links.txt` manifest showing how a
claim folder might reference documents that live elsewhere (a portal, cloud
storage) instead of being attached directly.

`agents.ingestion.dispatcher.discover_files()` / `ingest_claim_folder()`
(new this round) recursively walk this kind of structure and feed
everything found -- local files and manifest URLs alike -- into the same
`ingest_many()` batch path used everywhere else.

## What this does and doesn't prove

This data proves the ingestion pipeline survives **real scan noise**
(FUNSD), **authentic real-world form structure** (FNOL specimens), and
**controllable synthetic degradation** (Augraphy) without crashing, and that
it correctly discovers files across a **realistic nested directory layout**.
It does not prove field-extraction accuracy on real insurance content,
since no real, domain-matched claim documents could legitimately be
obtained -- that's a real limitation, not a hidden one, and worth knowing
before reporting any extraction-accuracy numbers in a presentation.
