# ClaimLens Benchmark — Methodology

This explains what `scripts/run_benchmark.py` measures, how, and — just
as importantly — what it does **not** let you claim. Read this before
you put any number from `outputs/benchmark_results.json` on a slide.

## What it does

Runs `core.pipeline.run_pipeline()` — the exact same end-to-end pipeline
the API/UI uses — once per folder under `samples/claim_folders/`, and
instruments it non-invasively (no edits to any agent or core file) to
measure:

1. **Wall-clock time**, overall and per stage, from the pipeline's own
   `on_stage` event callback.
2. **Real LLM token usage and cost**, by monkeypatching the two SDK
   methods every LLM call in this codebase goes through
   (`openai...Completions.create` for Groq, `google.genai...Models.
   generate_content` for Gemini) — see `scripts/benchmark/token_tracker.py`.
   This reads `response.usage` / `response.usage_metadata`, fields the
   SDKs already return; it doesn't estimate anything.
3. **Citation-hallucination catches**, by attaching a log handler to
   `agents.section_extraction_agent`'s existing warning log (see
   `scripts/benchmark/log_capture.py`) and reading the exact count that
   agent already computes when the extraction model cites a block_id
   that doesn't exist in the claim's real documents.
4. Everything else observable directly off the final `ClaimRecord`:
   Gate Check completeness, forced-review overrides, field-level risk
   distribution, triage tier, ingestion success/failure, document
   format mix.

Then it combines the **measured** numbers with a small set of **sourced
external constants** (`scripts/benchmark/pricing.py`) to produce the
business-facing comparisons (cost per claim, time saved).

## Why this design, specifically

**Non-invasive.** Nothing in `agents/` or `core/` is modified. The
tracker patches SDK *classes*, not your code, and un-patches when done.
You can delete `scripts/benchmark/` and `scripts/run_benchmark.py`
entirely and the rest of the repo is untouched.

**Reads real usage counters, not estimates.** Every previous
conversation about "how many tokens does a 30-page claim use" was a
guess. This reads the actual `prompt_tokens`/`completion_tokens`
(Groq/OpenAI-compatible) or `prompt_token_count`/`candidates_token_count`
(Gemini) that the provider returns with every real response.

**Catches hallucinated citations without editing the agent.**
`agents/section_extraction_agent.py` already detects and drops citations
pointing at block_ids that don't exist — it just doesn't return the
count anywhere. Rather than changing a tested Sprint 0-4 file to add a
return value, the benchmark reads the exact same integer off the
warning log line that logs it.

## The one rule this benchmark enforces on itself

**A number computed from your 12 synthetic claim folders is a
measurement of your pipeline's behavior, not a claim about the real
world.** The output JSON labels this explicitly:

- `summary.sample_size` — literally how many folders were run. Every
  rate/percentage in the summary is only valid against this n. Do not
  say "our STP rate is X%" to your boss — say "on our N test claims, X
  were flagged straight-through-eligible," and if pressed, be upfront
  that N is too small to be a real rate.
- `summary.sample_size_caveat` — the same point, spelled out, sitting
  right next to the numbers so nobody downstream forgets it.
- `summary.triage_tier_distribution.note` — repeats the caveat
  specifically for the metric most likely to get mis-quoted as an
  industry-style STP rate.

**Timing and cost are the exception** — those are real, measured
seconds and real, measured tokens for real work the pipeline actually
did. The *test data* is synthetic; the *measurement of how the code
behaved on it* is not. It's legitimate to say "our pipeline processed a
30-page synthetic claim packet in N seconds" — just don't imply that
packet represents the average real-world claim.

## What's measured vs. cited vs. derived vs. assumed

| Category | Meaning | Example in this benchmark |
|---|---|---|
| **Measured** | Read directly off a real pipeline run | Wall-clock seconds, token counts, hallucinated-citation count |
| **Cited** | A number from an external source, with the source given | BLS adjuster wage, Deloitte-attributed manual cost range |
| **Derived** | Computed by us from cited numbers, not itself a citation | The "50–80 minutes manual equivalent" estimate (cited cost ÷ cited hourly rate) |
| **Assumption** | A stated guess, not backed by any source, meant to be replaced | The 1.3x fully-loaded labor multiplier |

Every constant in `scripts/benchmark/pricing.py` is commented with which
of these four buckets it's in. `PRICING_METADATA` in the output JSON
repeats this so it travels with the results.

## The business metrics, explained

`summary.business_metrics` in the output JSON:

- **`claimlens_cost_per_claim_usd`** — LLM inference cost only. The
  pipeline runs unattended, so (unlike a human adjuster) no per-minute
  labor cost accrues while it runs. This is the fairest, most defensible
  number to show — it isn't inflated by pretending automation has zero
  marginal cost, but it also isn't diluted by counting labor that
  didn't happen.
- **`manual_cost_per_claim_usd_range`** — the Deloitte-attributed $40–60
  figure, cited, not measured. This is the number to be ready to defend
  with "I found this cited across multiple secondary sources but
  couldn't verify Deloitte's original report directly" if asked.
- **`derived_manual_minutes_range`** — OUR back-calculation (manual cost
  ÷ fully-loaded hourly wage), shown so it's fully reproducible. This is
  the honest answer to "how long does manual processing take" — there is
  no clean published industry figure for this specific sub-task (see the
  chat discussion that led to this benchmark), so this is a transparent
  derivation, not a citation. If you can get even one real practitioner
  data point, replace this constant and say so on the slide.
- **`time_saved_minutes_range`** / **`cost_avoided_per_claim_usd_range`**
  — the derived manual estimate minus your pipeline's *measured* time/cost.

## Before you present this

1. **Run it for real.** This ships without live numbers — the sandbox
   this was built in cannot reach `api.groq.com` or
   `generativelanguage.googleapis.com`, only a fixed allowlist. Every
   piece of the harness was tested with fake-but-correctly-shaped SDK
   responses to confirm the instrumentation mechanics work; it has not
   been run against the real APIs. Set `GROQ_API_KEY` and
   `GOOGLE_API_KEY` in `backend/.env` and run:
   ```
   python3 backend/scripts/run_benchmark.py
   ```
2. **Re-check pricing.** LLM prices move. `scripts/benchmark/pricing.py`
   has direct links to both providers' pricing pages — check them
   before trusting `outputs/benchmark_results.json`'s cost figures.
3. **Don't quote a rate off 12 claims.** Use the raw counts and the
   timing/cost numbers; skip percentages that imply a production sample.
4. **Say what's cited vs. derived out loud.** The "$40–60/claim" number
   is citable as-is. The "50–80 minutes" number is your own math from
   that citation — good practice is saying so, not presenting it as if
   you found it published somewhere.
