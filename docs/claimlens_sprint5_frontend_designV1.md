# ClaimLens Sprint 5 — Final Plan v2

## Decisions confirmed
| Question | Decision |
|---|---|
| Scope | Tier 1 + Tier 2 charts (finance audience needs portfolio numbers) |
| merge_agent | Wire in for real, includes confidence_rating.py fix |
| Persistence | Disk dumps required, after every stage |
| Client portal | Stub only |

## One bug found before we write a line of code

`confidence_rating.py`'s `rate_field()` currently has no branch for
`status == "conflicting"` (what `merge_agent` sets when two documents
disagree on a dollar amount). A conflicting field with `value=None` falls
into the same branch as a simply-missing field — and if that field is
optional, it gets `RiskLevel.OK` and `requires_human_review=False`. A
real conflict silently disappears.

Fix: one new branch at the top of `rate_field()`:
```python
elif field.status == "conflicting":
    # Always HIGH_RISK. A confirmed conflict between two documents on a
    # critical value is worse than a missing field -- it means we have
    # actively contradictory evidence, not an absence of evidence.
    risk = RiskLevel.HIGH_RISK
    composite = 0.0
    requires_human = True
    reasons.append(f"CONFLICTING values detected across cited evidence: {field.reason}")
```

This fix goes on Day 1, before any frontend work, because triage depends
on it downstream (a conflicting required field should trigger
forced_review=True, same as a failed verification on a required field).

---

## Directory structure

```
claimlens-agentic-mvp/                  ← repo root (no Python code lives here)
│
├── README.md                            ← quickstart: how to run both servers
├── start-backend.sh   (+ .ps1)          ← cd backend && uvicorn app.main:app --reload
├── start-frontend.sh  (+ .ps1)          ← cd frontend && npm run dev
├── .gitignore                           ← covers backend/.env AND frontend/.env
│
├── docs/                                ← all design docs consolidated
│   ├── ClaimLens_v2_Design_and_Sprint_Plan.md
│   ├── PADDLEOCR_SETUP.md
│   ├── SPRINT_2_NOTES.md
│   ├── SPRINT_3_NOTES.md
│   ├── SPRINT_4_NOTES.md
│   ├── SPRINT_5_NOTES.md               ← written after 5a/5b are built
│   └── REAL_DATA_SOURCES.md
│
├── backend/                            ← everything Python lives here
│   │
│   ├── agents/                         ← MOVED AS-IS, zero file changes
│   │   ├── ingestion/
│   │   │   ├── dispatcher.py
│   │   │   ├── pdf_parser.py
│   │   │   ├── office_parser.py
│   │   │   ├── image_parser.py
│   │   │   ├── url_parser.py
│   │   │   ├── ocr_utils.py
│   │   │   ├── base.py
│   │   │   └── ocr_engines/
│   │   │       ├── factory.py
│   │   │       ├── tesseract_engine.py
│   │   │       ├── paddleocr_engine.py
│   │   │       └── base.py
│   │   ├── lob_classifier_agent.py
│   │   ├── doc_type_tagger_agent.py
│   │   ├── gate_check.py
│   │   ├── section_extraction_agent.py
│   │   ├── evidence_verifier.py
│   │   ├── confidence_rating.py        ← SMALL FIX: new conflicting branch
│   │   ├── llm_evidence_verifier.py
│   │   ├── provenance_agent.py
│   │   ├── merge_agent.py
│   │   ├── human_review_queue.py
│   │   ├── triage_agent.py
│   │   └── reviewer_summary_agent.py
│   │
│   ├── core/                           ← MOVED AS-IS, PLUS 2 new files
│   │   ├── schemas.py
│   │   ├── schema_loader.py
│   │   ├── config.py
│   │   ├── env.py
│   │   ├── llm_client.py
│   │   ├── pipeline.py                 ← NEW: the orchestrator (12 stages)
│   │   └── store.py                    ← NEW: ClaimStore (memory + disk)
│   │
│   ├── app/                            ← NEW: FastAPI application
│   │   ├── __init__.py
│   │   ├── main.py                     ← FastAPI(), CORS, mounts, router includes
│   │   ├── deps.py                     ← shared deps (get_store)
│   │   ├── sse.py                      ← SSE event types + formatting
│   │   └── routers/
│   │       ├── __init__.py
│   │       ├── claims.py               ← POST/GET /api/claims[/{id}]
│   │       ├── stream.py               ← GET /api/claims/{id}/stream
│   │       ├── documents.py            ← page render endpoint
│   │       └── review.py               ← override / approve / reject
│   │
│   ├── schemas/                        ← MOVED AS-IS (auto.json, property.json, health.json)
│   ├── samples/                        ← MOVED AS-IS
│   ├── scripts/                        ← MOVED AS-IS (kept for manual testing)
│   ├── tests/                          ← MOVED AS-IS (185 passing, zero changes needed)
│   ├── outputs/                        ← MOVED AS-IS, now the real persistence target
│   │   └── {claim_id}/
│   │       ├── claim_state.json        ← written after every pipeline stage
│   │       └── crops/
│   │           └── {block_id}.png
│   ├── conftest.py                     ← NEW (1 line): os.chdir so pytest works from repo root
│   ├── requirements.txt                ← MOVED, add: fastapi uvicorn python-multipart
│   ├── .env.example
│   └── .env                            ← NOT auto-moved: copy this manually (see Day 1 checklist)
│
└── frontend/                           ← NEW: React application
    ├── src/
    │   ├── pages/
    │   │   ├── Landing.tsx             ← two buttons: Adjuster Portal | Client Portal (stub)
    │   │   ├── StartClaim.tsx          ← file drop + LOB optional hint, one screen
    │   │   ├── ProcessingView.tsx      ← full-screen SSE progress, auto-transitions when done
    │   │   ├── Dashboard.tsx           ← KPI cards + risk chart + claims table
    │   │   └── claim/
    │   │       └── ClaimReview.tsx     ← 3-panel adjuster review page
    │   ├── components/
    │   │   ├── review/
    │   │   │   ├── FieldsPanel.tsx     ← left: sections → fields, risk badges
    │   │   │   ├── EvidenceViewer.tsx  ← center: crop img + SVG bbox rect overlay
    │   │   │   ├── TriagePanel.tsx     ← right: verdict, forced_review callout leads
    │   │   │   ├── SummaryPanel.tsx    ← right: reviewer summary prose
    │   │   │   └── OverrideModal.tsx   ← adjuster manual correction
    │   │   ├── dashboard/
    │   │   │   ├── KpiCards.tsx        ← total claims, STP%, avg completion, total value
    │   │   │   ├── RiskDistributionChart.tsx  ← Recharts stacked bar: stp/review/high-risk
    │   │   │   └── ClaimsTable.tsx     ← claim_id, LOB, tier badge, completion%, click-through
    │   │   └── shared/
    │   │       ├── StageProgress.tsx   ← SSE-driven stage list for ProcessingView
    │   │       ├── TierBadge.tsx       ← stp_candidate / needs_review / high_risk_incomplete
    │   │       ├── RiskBadge.tsx       ← ok / needs_review / high_risk (field level)
    │   │       └── ConfidenceBar.tsx   ← per-field composite_confidence bar on review page
    │   ├── hooks/
    │   │   ├── useClaimStream.ts       ← native EventSource wrapper
    │   │   └── useClaim.ts             ← TanStack Query: GET /api/claims/{id}
    │   ├── store/
    │   │   └── reviewUiStore.ts        ← Zustand, UI-local only:
    │   │                                   selectedFieldId, activeEvidenceIndex
    │   │                                   (NOT claim data -- that lives in TanStack Query)
    │   ├── lib/
    │   │   ├── api.ts                  ← fetch wrapper, base URL from VITE_API_BASE_URL
    │   │   └── utils.ts
    │   ├── types/
    │   │   └── claim.ts                ← TypeScript mirrors of core/schemas.py Pydantic models
    │   │                                   hand-verified against the real Python, not the v1 draft
    │   ├── App.tsx
    │   └── main.tsx
    ├── public/
    ├── index.html
    ├── package.json
    ├── vite.config.ts
    ├── tailwind.config.ts
    ├── tsconfig.json
    └── .env.example                    ← VITE_API_BASE_URL=http://localhost:8000
                                           NEVER put GROQ_API_KEY here (Vite bundles
                                           VITE_* vars into browser-readable JS)
```

---

## API surface (complete, finalized)

| Method | Path | Purpose | Notes |
|---|---|---|---|
| POST | /api/claims | Upload files, start pipeline | Multipart, returns `{claim_id}` immediately |
| GET | /api/claims | List all claims (for Dashboard) | Returns summary per claim from store |
| GET | /api/claims/{id} | Full ClaimState JSON | |
| GET | /api/claims/{id}/stream | SSE pipeline progress | See event list below |
| GET | /api/claims/{id}/documents/{doc_id}/page/{n} | Full page render as PNG with bbox in pixel coords | Backend computes transform; frontend only draws an SVG rect |
| POST | /api/claims/{id}/fields/{field_id}/override | Adjuster manual correction | Updates in-memory + redumps JSON |
| POST | /api/claims/{id}/approve | Adjuster approves claim | |
| POST | /api/claims/{id}/reject | Adjuster rejects claim | |
| Static | /crops/{claim_id}/{block_id}.png | Serve crop images | Mounted from outputs/ |

### SSE event list (corrected from v1 draft)

Every event is `data: {stage, status, detail}` JSON.

```
stage=ingest             status=start/complete   detail: {doc_count, total_blocks}
stage=classify           status=start/complete   detail: {lob, lob_confidence}
stage=schema_resolve     status=complete         detail: {schema_name, field_count}
stage=doc_type_tag       status=complete         detail: {doc_types: [{doc_id, doc_type}]}
stage=gate_check         status=complete         detail: {missing_docs: [...]}
stage=extract            status=start
stage=extract_section    status=progress         detail: {section_id, fields_found, fields_total}
stage=extract            status=complete         detail: {total_found, total_fields}
stage=merge              status=complete         detail: {conflicts_detected: N}
stage=verify             status=complete         detail: {ok: N, needs_review: N, high_risk: N}
stage=crops              status=complete         detail: {crops_generated: N}
stage=triage             status=complete         detail: {tier, score, forced_review}
stage=summary            status=complete
stage=pipeline           status=done/error       detail: {claim_id} or {error}
```

The `extract_section` sub-events are the key one for demo feel -- extraction
is 60-80% of total wall-clock time and the UI must not appear frozen during it.

---

## Three-day build schedule

### Day 1 — Backend (all Python, no frontend yet)

**Morning: safe repo restructure (do this before writing any new code)**
1. Create `backend/` and `frontend/` dirs
2. `git mv` (or plain `mv`) everything Python-side into `backend/`
3. Manually copy your working `.env` into `backend/.env`
4. Create `backend/conftest.py` (1 line: `import os; os.chdir(os.path.dirname(__file__))`)
5. From `backend/`: `python3 -m pytest tests/ -q` → must show 185 passed, zero changes
   **If this fails, stop here and fix before writing any new code.**
6. Move docs/*.md into `docs/`
7. Write root `README.md` quickstart + start scripts

**Afternoon: new backend code (in order, each one is short)**
8. `confidence_rating.py`: add the conflicting-status branch + its test
9. `core/pipeline.py`: `run_pipeline()` — 12 stages in order, `on_stage` callback, stage-by-stage disk writes
10. `core/store.py`: `ClaimStore` (in-memory dict + disk persistence + startup rehydration)
11. `app/main.py` + `app/deps.py` + static mount for crops
12. `app/routers/claims.py`: POST/GET endpoints
13. `app/routers/stream.py`: SSE, subscribes to `on_stage` callback
14. `app/routers/documents.py`: page render — reuse `provenance_agent.py`'s exact transform, zero Y-flip, return bbox already in pixel space
15. `app/routers/review.py`: override / approve / reject

**End of Day 1 checkpoint (do this before touching any frontend)**
- `curl -X POST http://localhost:8000/api/claims -F "files=@backend/samples/auto_claim_01.pdf"`
- Watch SSE events arrive in a second terminal with `curl -N http://localhost:8000/api/claims/{id}/stream`
- Confirm `backend/outputs/{claim_id}/claim_state.json` exists and has content after each stage
- Open `http://localhost:8000/api/claims/{id}/documents/{doc_id}/page/1` in a browser tab; manually confirm the `bbox_px` coordinates in the response correspond to where the "AUTOMOBILE LOSS NOTICE" title actually appears in the rendered image (this is the single highest-risk item from v1 — verify it by eye on Day 1, not on the morning of the demo)
- `python3 -m pytest backend/tests/ -q` still 185 passed

### Day 2 — Frontend scaffold + ClaimReview page (the core)

1. Scaffold: `npm create vite@latest frontend -- --template react-ts`
2. Install: Tailwind, shadcn/ui, TanStack Query, Zustand, Recharts, Lucide, Framer Motion, React Router
3. `types/claim.ts` — hand-verify every field against `backend/core/schemas.py` (not the v1 draft description of it)
4. `lib/api.ts` — fetch wrapper, `VITE_API_BASE_URL`
5. `hooks/useClaim.ts` + `hooks/useClaimStream.ts`
6. `store/reviewUiStore.ts` — selectedFieldId, activeEvidenceIndex (UI-local only)
7. `ClaimReview.tsx` 3-panel layout skeleton (CSS grid, empty panels)
8. `FieldsPanel.tsx` — grouped by section from the schema, risk badges per field
9. `EvidenceViewer.tsx`:
   - Shows the crop PNG (`/crops/{claim_id}/{block_id}.png`) when `crop_paths` is non-empty
   - SVG `<rect>` overlay using backend-provided pixel coords (no transform in JS)
   - **Explicit "no visual evidence" state** (DOCX/PPTX/HTML sourced fields): styled quote block showing the cited block's raw text. This is a real expected case from Sprint 1, not an edge case.
   - "Evidence N of M" navigator when a field has multiple evidence blocks
10. `TriagePanel.tsx` — forced_review banner leads when true (the Sprint 4 payoff)
11. `SummaryPanel.tsx` — reviewer summary prose
12. `OverrideModal.tsx` — wired to the override endpoint
13. `ConfidenceBar.tsx` — shows composite_confidence per field

**End of Day 2 checkpoint**
- Open a browser to the review page for yesterday's processed claim (hardcode the ID in the URL for now)
- Click through 3-4 fields and confirm: crop images load, SVG bbox visually aligns with the correct text in the image, the triage panel shows forced_review reasoning, the summary reads correctly

### Day 3 — Processing view, Dashboard, routing, polish

1. `StartClaim.tsx` — file drop zone (native HTML input, no extra library needed), POST to `/api/claims`, redirect to ProcessingView on success
2. `ProcessingView.tsx` — SSE-driven stage list, `extract_section` sub-events update a section-level sub-progress within the extraction stage, Framer Motion fade-out transition to the review page on `pipeline.done`
3. `Landing.tsx` — two buttons, client portal is "Coming Soon"
4. `Dashboard.tsx` + `KpiCards.tsx` + `RiskDistributionChart.tsx` + `ClaimsTable.tsx`:
   - KPI cards: total claims, STP rate (%), average required-field completion, total claim value (sum of primary amount fields across all processed claims — this is the finance-facing number)
   - Risk chart: Recharts stacked bar, one bar per LOB showing count of stp/needs_review/high_risk_incomplete claims
   - Claims table: click-through to review page
5. React Router: wire all routes (`/`, `/start`, `/processing/:claimId`, `/claims`, `/claims/:claimId`)
6. Loading states everywhere (skeleton screens, not raw spinners)
7. Error states (failed upload, SSE disconnected, field with no extraction result)
8. Empty states (no claims yet, no fields found in a section)
9. Responsive check at 1280px width (typical demo laptop resolution)

**Full dry run (do this as a block, not incrementally)**
- Cold server start (kill and restart `uvicorn`)
- Upload 3 sample claims one after the other: auto PDF, health DOCX, the 22-page stress-test PDF
- Verify: SSE stages arrive in order, extraction sub-events update the progress UI, each claim ends up on the Dashboard with correct tier badges and numbers, KPI cards update, risk chart reflects all 3 claims
- Open each claim's review page; verify the triage verdict and summary are claim-appropriate

**If this finishes early (realistic if Days 1-2 go cleanly):** keyboard navigation (Tab between fields, arrow keys through evidence), export-as-PDF button wired to a simple `window.print()` with a print stylesheet (faster than jsPDF for a demo, looks just as professional).

---

## Key design decisions written down so they don't get re-litigated during the build

**No Y-flip in the frontend, ever.** The backend returns bbox already in
image pixel space. The frontend draws an SVG rect. If a bbox looks wrong
visually, the bug is in `app/routers/documents.py`'s pixel math (which
should be a verbatim copy of `provenance_agent.py`'s verified logic),
not in the frontend. Look there first.

**Crops are keyed by `block_id`, not `field_id`.** A field with two evidence
blocks has two crops. Multiple fields citing the same block share a crop file.
The evidence navigator shows "Evidence N of M" where M is `field.evidence_block_ids.length`.

**`react-pdf` is not in this project.** The backend serves PNGs; the
frontend shows `<img>` tags. If someone suggests adding `react-pdf` or
`pdf.js` worker configuration during the build, say no — it adds a
complex Vite worker setup and a whole parallel rendering pipeline for zero
benefit over what we already have.

**Zustand holds UI state only.** Specifically: which field is selected,
which evidence index is active on the EvidenceViewer. If you find yourself
putting `claim` data or `extracted_fields` into the Zustand store,
stop — that's what TanStack Query's cache is for.

**The `merge_agent` is now a real pipeline stage.** If a claim's SSE stream
shows `stage=merge, detail={conflicts_detected: 0}`, that's correct — it ran
and found nothing. If it shows `conflicts_detected: 2`, the Demo has a
genuinely interesting thing to show: the system detected that two documents
disagreed on a field value and refused to silently pick a winner.

---

## Frontend tech stack (final, locked)

| Library | Purpose | Why kept/dropped vs v1 draft |
|---|---|---|
| React 18 + Vite + TypeScript | Core | Kept as drafted |
| Tailwind CSS + shadcn/ui | Styling | Kept as drafted |
| TanStack Query | Server state | Kept as drafted |
| Zustand | UI-local state only | Kept, but scope tightened -- no server data |
| React Router v6 | Routing | Kept as drafted |
| Recharts | Charts | Kept, but 2 chart instances max across the whole app |
| Lucide React | Icons | Kept |
| Framer Motion | Transition off ProcessingView only | Kept for that one transition, dropped elsewhere |
| ~~react-pdf~~ | ~~Document previews~~ | **Dropped** -- backend serves PNGs, no PDF.js worker needed |
| ~~jsPDF~~ | ~~Client-side PDF export~~ | **Dropped** -- Tier 3 (use `window.print()` if pressed) |
| ~~Multi-step wizard library~~ | ~~Upload wizard~~ | **Dropped** -- submit screen is one page, not a wizard |