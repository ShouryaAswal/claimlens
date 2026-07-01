# ClaimLens v2 — Design & Implementation Plan
**The missing piece: a Schema Resolution layer, ACORD-mapped per LOB**
Shourya Aswal · Insurance AI Platform Internship MVP · 19 Jun – 5 Jul 2026

---

## 1. What changed and why

The v1 plan (OCR → chunk → LLM extraction → provenance → triage) had no answer to *"extract which fields, exactly?"* That gap is what made "150 fields, one context window" feel like an unsolvable problem — you were trying to solve a search problem before defining the target.

The fix: insert a **deterministic Schema Resolution stage** between classification and extraction. No LLM call needed — just a lookup.

Two corrections to the original framing, both load-bearing for the design below:

- **ACORD fits Auto (ACORD 2 – Automobile Loss Notice) and Property (ACORD 1 – Property Loss Notice) cleanly.** These are real, named, industry-standard FNOL forms. **Health does not use ACORD** for claims — it uses **CMS-1500** (professional/physician) and **UB-04** (institutional/hospital), governed by NUCC/NUBC. So Health gets an *internal* schema inspired by those forms' field concepts, not an ACORD mapping. Keep this distinction explicit in your repo and your final presentation — an evaluator who knows insurance will check for exactly this.
- **Don't reproduce ACORD's actual form template** (layout, numbering, legal boilerplate) — it's copyrighted. Your own JSON schema using plain field names (`policy_number`, `date_of_loss`, …) is fine; a scan/copy of the PDF is not.
- **Groq deprecated `llama-3.1-8b-instant` and `llama-3.3-70b-versatile`** on the free/dev tier (17 Jun 2026 — two days ago). Recommended replacements: `openai/gpt-oss-20b` and `openai/gpt-oss-120b`, both OpenAI-SDK compatible. This also affects your other Groq-pinned projects (SunLeo DJ, the three enterprise HLDs) — worth a quick model-string swap there too, separately from this MVP.

---

## 2. Where ClaimLens sits in the real claims lifecycle

Your 15-step lifecycle is correct for P&C. Refinements:

```
1. Loss happens
2. FNOL submitted                     ←─┐
3. Claim registered                     │  ClaimLens operates here.
4. Basic validation                     │  Reserves are typically set
5. Triage (simple/complex/high-value) ←─┘  immediately after this point.
6. Assigned to adjuster               ←── ClaimLens output feeds this handoff
7. Coverage verification (peril, exclusions, limits, ROR letter if disputed)
8. Investigation (docs, photos, survey, SIU referral if fraud suspected)
9. Damage/liability evaluation
10. Valuation (ACV/RCV, medical necessity/UCR review)
11. Settlement calculation
12. Approval (adjuster authority / manager escalation)
13. Payment / denial / partial settlement
14. Closure
15. Recovery (subrogation, salvage, reinsurance; health: coordination of benefits)
```

**ClaimLens's job is steps 2–5: build the evidence-linked corpus, classify, resolve the required schema, extract with citations, flag gaps, and hand the adjuster a head start at step 6.** It never touches coverage interpretation, valuation, settlement math, or payment — those need licensed judgment and are explicitly out of scope, same as your original call.

One honest caveat: "FNOL" as a term fits Auto/Property well (a claimant or agent reports a loss). Health claims are usually *submitted by the provider* as billing claims, not "first notice of loss" in the same sense. For this MVP it's fine to keep treating Health as a third parallel LOB with its own intake schema — just don't present it as "ACORD for health" in your final deck.

---

## 3. Revised end-to-end architecture

```
Documents (PDF/img/docx, multilingual)
        │
        ▼
[0] Ingestion + OCR Agent ──────► Corpus: {block_id, page, text, bbox, conf, source_file}
        │
        ▼
[1] LOB Classifier  (cheap/fast call) ──► "auto" | "property" | "health"
        │
        ▼
[2] Schema Resolver  (NEW — deterministic, no LLM)
        loads schemas/<lob>.json → sections × fields, + mandatory_doc_types
        │
        ▼
[3] Document-Type Tagger  (per ingested doc: police_report / estimate / discharge_summary / …)
        │
        ▼
[4] Gate Check  (deterministic) ──► list of missing mandatory document types
        │
        ▼
[5] Section-wise Extraction Agents  (one LLM call per section, 5–15 fields each,
        full corpus in context, must cite OCR block_ids or return null)
        │
        ▼
[6] Merge Agent  (deterministic: resolves multi-doc conflicts by label strength /
        OCR confidence / repetition; logs conflicts rather than silently picking)
        │
        ▼
[7] Provenance Linking  (block_id → page, bbox, crop — still deterministic, LLM never touches coordinates)
        │
        ▼
[8] Evidence Verifier  (mostly deterministic: does the cited block's text actually
        support the value? fuzzy/regex sanity check; LLM check only for ambiguous cases)
        │
        ▼
[9] Completion & Gap Report  (X/Y required fields found, confidence breakdown, missing docs)
        │
        ▼
[10] Triage / Risk Score  (rule-based — same scheme as v1)
        │
        ▼
[11] Reviewer Summary Agent  (one LLM call: turns 9+10 into a short adjuster brief)
        │
        ▼
[12] Streamlit Frontend — filled-form view + click-to-evidence + triage report
```

**Why this resolves your three concerns:**

| Concern | v1 problem | v2 fix |
|---|---|---|
| Context window (150 fields) | One call, all fields, whole corpus | Sections cap each call to 5–15 fields. A typical claim's OCR corpus (15–25 short docs) is usually only ~5k–20k tokens — trivially small even without sectioning, but sectioning also bounds *field-list ambiguity*, which is the real bottleneck, not raw token count. |
| Recall (will the answer be found?) | Chunk-then-retrieve risks missing the right chunk | Don't retrieve — pass the **full corpus** to every section call. Gemini 3 Flash's 1M-token window makes "just give it everything" the simplest correct answer for claim-packet-sized inputs. No retrieval index to build under time pressure. |
| Hallucinated coordinates | — | Unchanged from your original (correct) design: LLM cites `block_id`s only; the system maps IDs → bbox deterministically. Never let the model invent a coordinate. |

---

## 4. Field Schema design (the new artifact you need to author first)

Each LOB gets one schema file, structured as **sections → fields**, not a flat 150-item list. This mirrors how the real forms are organized (and is *why* ACORD's section structure is worth borrowing even though you can't copy the form itself).

**`schemas/auto.json`** (ACORD-2-inspired; your own field names, not the form's text):

```json
{
  "lob": "auto",
  "source_concept": "ACORD 2 - Automobile Loss Notice (field concepts only, not reproduced)",
  "mandatory_doc_types": ["police_report", "photos", "repair_estimate", "policy_declaration"],
  "sections": [
    {
      "section_id": "policy_info",
      "fields": [
        {"field_id": "policy_number", "label": "Policy Number", "required": true},
        {"field_id": "carrier_name", "label": "Carrier / NAIC Code", "required": false},
        {"field_id": "policy_effective_dates", "label": "Policy Period", "required": true}
      ]
    },
    {
      "section_id": "loss_details",
      "fields": [
        {"field_id": "date_of_loss", "label": "Date of Loss", "required": true},
        {"field_id": "time_of_loss", "label": "Time of Loss", "required": false},
        {"field_id": "loss_location", "label": "Location of Loss", "required": true},
        {"field_id": "loss_description", "label": "Description of Accident", "required": true}
      ]
    },
    {
      "section_id": "insured_vehicle",
      "fields": [
        {"field_id": "vehicle_vin", "label": "VIN", "required": true},
        {"field_id": "vehicle_make_model_year", "label": "Make/Model/Year", "required": true},
        {"field_id": "damage_location", "label": "Where Damage Can Be Seen", "required": false}
      ]
    },
    {
      "section_id": "parties",
      "fields": [
        {"field_id": "driver_name", "label": "Driver Name", "required": true},
        {"field_id": "other_party_name", "label": "Other Party / Driver Name", "required": false},
        {"field_id": "witness_name", "label": "Witness Name", "required": false}
      ]
    },
    {
      "section_id": "official_records",
      "fields": [
        {"field_id": "police_report_number", "label": "Police Report Number", "required": false},
        {"field_id": "reporting_department", "label": "Reporting Police Department", "required": false}
      ]
    },
    {
      "section_id": "financials",
      "fields": [
        {"field_id": "repair_estimate_amount", "label": "Repair Estimate", "required": true},
        {"field_id": "rental_needed", "label": "Rental Vehicle Needed", "required": false}
      ]
    },
    {
      "section_id": "remarks_overflow",
      "fields": [
        {"field_id": "additional_remarks", "label": "Additional Remarks", "required": false}
      ]
    }
  ]
}
```

This gets you to roughly **35–45 meaningful fields across 7 sections** for Auto — a realistic, demo-able subset of the real form's ~100+ raw checkboxes, mapped to what an adjuster actually needs at intake. Do the same for `property.json` (ACORD-1-inspired: policy info, loss details, property/inventory, official records, financials, remarks) and `health.json` (CMS-1500/UB-04-inspired: patient/member info, provider info, admission/service dates, diagnosis/procedure codes, billed amounts, pre-auth/discharge evidence).

**This schema authoring is now Sprint 0** — everything downstream (prompts, UI form layout, triage rules, Gate Check) depends on it existing first.

---

## 5. Model & tooling decisions (updated for the Groq deprecation)

| Layer | Tool | Why |
|---|---|---|
| LOB classification | Groq `openai/gpt-oss-120b` | Fast, cheap, single short call — speed matters here, not context size |
| Section-wise extraction | **Gemini 3 Flash** (free tier) | 1M-token context fits the entire claim corpus per call; free tier (10 RPM / 250k TPM / 1,500 RPD) easily covers demo + dev volume |
| Evidence verification | Deterministic (fuzzy/regex match of cited block text vs. extracted value) | No LLM call needed for the common case — cheap, fast, and removes one source of hallucination-on-hallucination |
| Reviewer summary / triage report | Groq `openai/gpt-oss-120b` | Fast turnaround keeps the UI feeling responsive after the heavier extraction step |
| Orchestration | Plain Python, manual agent loop | Consistent with your existing no-LangChain stance; same reasoning applies here as in SunLeo DJ |
| Schema validation | Pydantic v2 | Consistent with your existing constraint set |

This is the same dual-provider pattern you already built for SunLeo DJ (Groq primary, Gemini fallback via differing `base_url`/SDK) — here it's not a fallback relationship but a deliberate split by strength: Gemini for the large-context reasoning step, Groq for the fast, small steps.

If you want to reuse one client shim instead of two SDKs: Google has historically exposed an OpenAI-compatible endpoint for Gemini (`.../v1beta/openai/`) — worth a quick check of current docs before relying on it, since I haven't verified it's still current as of this week.

---

## 6. Repository structure (v2)

```
claimlens-agentic-mvp/
  app.py
  requirements.txt
  README.md
  schemas/
    auto.json
    property.json
    health.json
  agents/
    ocr_agent.py
    lob_classifier_agent.py
    schema_resolver.py          # deterministic, not an LLM call
    doc_type_tagger_agent.py
    gate_check.py               # deterministic
    section_extraction_agent.py
    merge_agent.py
    provenance_agent.py
    verifier_agent.py           # mostly deterministic
    triage_agent.py
    summary_agent.py
  core/
    schemas.py        # Pydantic models: OCRBlock, ExtractedField, ClaimState
    state.py
    config.py
    llm_clients.py     # Gemini + Groq clients, isolated behind one interface
  samples/
    auto_claim_01.pdf
    property_claim_01.pdf
    health_claim_01.pdf
  outputs/
    sample_result.json
  tests/
    test_pipeline.py
```

---

## 7. Sprint plan: 19 Jun – 5 Jul (17 days)

| Sprint | Dates | Focus | Exit Criteria |
|---|---|---|---|
| **Sprint 0** | 19 Jun (today) | **Schema authoring** — write `auto.json`, `property.json`, `health.json` with sections + fields + mandatory doc types. Repo restructure. Pydantic models for `ClaimState`/`OCRBlock`/`ExtractedField`/schema. | All 3 schemas exist, validate against Pydantic, reviewed against public ACORD-1/2 and CMS-1500/UB-04 field concepts (no copied form text). |
| **Sprint 1** | 20–21 Jun | OCR/ingestion agent (PaddleOCR + PyMuPDF fallback), block ID assignment, corpus JSON output. | Auto, Property, Health sample docs each produce OCR blocks with page + bbox + source file. |
| **Sprint 2** | 22–24 Jun | LOB classifier agent, doc-type tagger agent, Gate Check, **Section Extraction agent** (Gemini 3 Flash, one call per section, full corpus in context, block-ID citations required). | Each section returns valid JSON; missing fields explicitly listed (not silently dropped); Gate Check correctly flags a missing mandatory doc on a deliberately incomplete sample. |
| **Sprint 3** | 25–27 Jun | Merge agent (multi-doc conflict resolution), Provenance linking (block_id → bbox/crop), Evidence Verifier (fuzzy-match sanity check). | Every accepted field traces to a real crop; a field whose cited block doesn't actually support its value gets flagged, not silently accepted. |
| **Sprint 4** | 28–30 Jun | Triage/risk-scoring agent (rule-based), Reviewer Summary agent (one LLM call → adjuster brief) — **the two deliverables**: filled-schema view + narrative report. | Given a complete sample, get STP verdict + clean report. Given an incomplete sample, get "needs review" + a report naming the missing fields/docs. |
| **Sprint 5** | 1–3 Jul | Streamlit frontend: upload → pipeline run → filled-form view with confidence badges → click-field-to-see-crop → triage report panel. | A non-technical reviewer can upload a sample claim and understand the output without explanation. |
| **Sprint 6** | 4–5 Jul | Testing (pytest for schema validation, gate check, triage thresholds), polish, README, demo script, final presentation. | End-to-end demo works locally on all 3 LOBs; presentation explains the ACORD/CMS-1500 distinction correctly. |

---

## 8. Updated risk register

| Risk | Impact | Mitigation |
|---|---|---|
| Presenting ACORD as covering Health | Embarrassing in front of anyone who knows insurance | Schema doc explicitly labels Health as CMS-1500/UB-04-inspired, not ACORD |
| Reproducing ACORD's actual form | Copyright issue, however minor for a student project | Own field names/JSON only; never embed the ACORD PDF/template |
| Gemini free-tier rate limit hit mid-demo | Demo stalls live | Pre-run and cache results for your 3 demo samples; keep Groq path as backup if you want a live re-run |
| Section extraction misses a field that *is* in the corpus | Lower recall than expected | Full-corpus-per-section (no retrieval gap) + deterministic verifier catches false positives; for false negatives, log every section call's raw output for debugging |
| Conflicting field values across documents | Silent wrong answer if auto-resolved badly | Merge agent logs conflicts and surfaces them in the report rather than picking silently |
| Scope creep (adding the dual-agent critic, VLM verification, retrieval index) | Demo incomplete by 5 Jul | All three are explicitly **stretch goals**, same as your original VLM-verification call — not in the Sprint 0–6 path |

---

## 9. Final success criteria

A successful MVP demonstrates, per LOB (Auto/Property/Health):

1. Documents ingested locally, OCR corpus built with page/bbox/confidence metadata.
2. LOB classified, correct schema resolved from `schemas/<lob>.json`.
3. Gate Check correctly lists any missing mandatory document types.
4. Section-wise extraction returns structured JSON with block-ID citations, full corpus visible per call.
5. Every accepted field is traceable to a real page + bounding box + crop.
6. Completion report states X/Y required fields found, confidence per field.
7. Triage agent produces an explainable STP / Needs-Review / High-Risk verdict.
8. Reviewer Summary agent produces a short adjuster-readable brief.
9. Streamlit UI ties all of the above together for a non-technical reviewer.

## 10. Explicitly out of scope (unchanged from your own call)

Coverage verification, exclusions analysis, investigation, liability determination, valuation (ACV/RCV/depreciation), settlement calculation, payment/denial, subrogation, fraud investigation. ClaimLens accelerates steps 2–5 and hands a structured, evidence-linked work product to the human adjuster at step 6 — it does not replace their judgment past that point.
