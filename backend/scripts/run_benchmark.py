"""
scripts/run_benchmark.py
---------------------------
Runs the full ClaimLens pipeline end to end against every claim folder
under samples/claim_folders/, measuring (not estimating) wall-clock
time, LLM token usage + cost, and every pipeline-internal metric that's
actually observable from the code (Gate Check completeness, forced
review, field risk distribution, citation-hallucination catches,
ingestion resilience). It then combines those measured numbers with the
sourced constants in scripts/benchmark/pricing.py to produce the
business-facing metrics (cost per claim, time saved, etc.), and writes
everything to a single JSON file.

WHAT THIS DOES NOT DO: it does not claim your 12 synthetic sample
claims represent real production claim volume or a real STP rate. Every
number computed from the sample set is labeled `"sample_size": 12` (or
however many folders you have) in the output JSON precisely so nobody
downstream mistakes a demo-set average for a population statistic. See
docs/BENCHMARK_METHODOLOGY.md.

Requires: GROQ_API_KEY and GOOGLE_API_KEY set in backend/.env (or your
shell environment) -- section extraction (agents/section_extraction_agent.py)
has no offline fallback, so a real end-to-end run needs both. Without
them this script prints what's missing and exits rather than silently
producing partial garbage.

Run from anywhere:
    python3 backend/scripts/run_benchmark.py
    python3 backend/scripts/run_benchmark.py --claims-dir samples/claim_folders --limit 3
    python3 backend/scripts/run_benchmark.py --output-json outputs/benchmark/results.json
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from dataclasses import asdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent  # backend/
sys.path.insert(0, str(PROJECT_ROOT))

from agents.ingestion.dispatcher import discover_files  # noqa: E402
from core.llm_client import get_llm_client  # noqa: E402
from core.pipeline import run_pipeline  # noqa: E402
from core.schemas import RiskLevel, TriageTier  # noqa: E402
from core.store import ClaimStore, PipelineStatus  # noqa: E402

from scripts.benchmark import pricing  # noqa: E402
from scripts.benchmark.log_capture import HallucinationTracker  # noqa: E402
from scripts.benchmark.token_tracker import tracker as llm_tracker  # noqa: E402


# --------------------------------------------------------------------------
# Preflight
# --------------------------------------------------------------------------

def preflight_check() -> None:
    groq = get_llm_client("groq")
    gemini = get_llm_client("gemini")
    missing = []
    if groq is None:
        missing.append("GROQ_API_KEY")
    if gemini is None:
        missing.append("GOOGLE_API_KEY")
    if missing:
        print(
            "Missing: " + ", ".join(missing) + "\n"
            "\nThis benchmark needs real LLM calls to measure real numbers --\n"
            "section extraction (agents/section_extraction_agent.py) has no\n"
            "offline fallback, so a partial run without these keys would\n"
            "produce misleading timing/cost data, not a smaller-but-valid\n"
            "sample.\n"
            "\nSet these in backend/.env (see backend/.env.example) and re-run:\n"
            "  GROQ_API_KEY=...    (https://console.groq.com)\n"
            "  GOOGLE_API_KEY=...  (https://aistudio.google.com/apikey)\n"
        )
        sys.exit(1)


# --------------------------------------------------------------------------
# Per-claim run
# --------------------------------------------------------------------------

def discover_claim_folders(claims_dir: Path) -> list[Path]:
    folders = sorted(
        p for p in claims_dir.iterdir()
        if p.is_dir() and not p.name.startswith(".")
    )
    return folders


def run_one_claim(store: ClaimStore, folder: Path) -> dict:
    claim_id = folder.name
    print(f"--- {claim_id} " + "-" * max(1, 60 - len(claim_id)))

    sources = discover_files(str(folder))
    print(f"  discovered {len(sources)} source file(s)/link(s)")

    stage_events: list[dict] = []

    def on_stage(event: dict) -> None:
        event = dict(event)
        event["t"] = time.time()
        stage_events.append(event)
        llm_tracker.set_stage(event["stage"])

    llm_tracker.reset()
    hallucination = HallucinationTracker()

    wall_start = time.time()
    with hallucination:
        llm_tracker.patch()
        try:
            record = run_pipeline(store, sources, claim_id=claim_id, on_stage=on_stage)
        finally:
            llm_tracker.unpatch()
    wall_end = time.time()
    total_seconds = wall_end - wall_start

    pipeline_error = record.status == PipelineStatus.ERROR
    if pipeline_error:
        print(f"  !! pipeline error: {record.error}")

    # -- stage durations, from consecutive on_stage timestamps ------------
    stage_durations: dict[str, float] = {}
    stage_start_t: dict[str, float] = {}
    for ev in stage_events:
        if ev["status"] == "start":
            stage_start_t[ev["stage"]] = ev["t"]
        elif ev["status"] in ("complete", "error") and ev["stage"] in stage_start_t:
            stage_durations[ev["stage"]] = round(ev["t"] - stage_start_t[ev["stage"]], 3)

    # -- LLM usage + cost ----------------------------------------------------
    calls = llm_tracker.records_for_current_claim()
    llm_cost_total = 0.0
    llm_cost_is_estimate = False
    calls_out = []
    tokens_by_provider: dict[str, dict[str, int]] = {}
    for c in calls:
        cost, is_estimate = pricing.cost_usd(c.input_tokens, c.output_tokens, c.model)
        llm_cost_total += cost
        llm_cost_is_estimate = llm_cost_is_estimate or is_estimate
        calls_out.append({
            "provider": c.provider, "model": c.model, "stage": c.stage,
            "input_tokens": c.input_tokens, "output_tokens": c.output_tokens,
            "latency_seconds": round(c.latency_seconds, 3),
            "cost_usd": round(cost, 6), "pricing_is_estimate": is_estimate,
        })
        bucket = tokens_by_provider.setdefault(c.provider, {"input_tokens": 0, "output_tokens": 0, "calls": 0})
        bucket["input_tokens"] += c.input_tokens
        bucket["output_tokens"] += c.output_tokens
        bucket["calls"] += 1

    # -- ingestion / document metrics -------------------------------------
    documents = record.claim.documents
    failed_docs = [d for d in documents if any("INGESTION FAILED" in w for w in d.warnings)]
    total_pages = sum(d.page_count or 0 for d in documents)
    source_formats = sorted({d.source_format.value for d in documents})

    # -- gate check / triage / verification --------------------------------
    missing_mandatory_docs = record.claim.missing_mandatory_docs
    triage = record.claim.triage
    verification_counts = {"ok": 0, "needs_review": 0, "high_risk": 0}
    for v in record.claim.field_verifications.values():
        if v.risk_level == RiskLevel.OK:
            verification_counts["ok"] += 1
        elif v.risk_level == RiskLevel.NEEDS_REVIEW:
            verification_counts["needs_review"] += 1
        else:
            verification_counts["high_risk"] += 1

    conflicting_fields = [
        f for f in record.claim.extracted_fields.values() if f.status == "conflicting"
    ]
    found_fields = [f for f in record.claim.extracted_fields.values() if f.status == "found"]

    result = {
        "claim_id": claim_id,
        "claim_folder": folder.name,
        "expected_lob_from_folder_name": folder.name.split("_")[0],
        "pipeline_error": pipeline_error,
        "pipeline_error_detail": record.error,

        "timing": {
            "total_wall_seconds": round(total_seconds, 3),
            "stage_seconds": stage_durations,
            "total_pages": total_pages,
            "seconds_per_page": round(total_seconds / total_pages, 3) if total_pages else None,
        },

        "documents": {
            "sources_discovered": len(sources),
            "documents_ingested": len(documents),
            "documents_failed": len(failed_docs),
            "ingestion_success_rate": round(1 - (len(failed_docs) / len(sources)), 4) if sources else None,
            "source_formats_present": source_formats,
            "total_pages": total_pages,
        },

        "lob_classification": {
            "predicted_lob": record.claim.lob.value if record.claim.lob else None,
            "confidence": record.claim.lob_confidence,
        },

        "gate_check": {
            "missing_mandatory_docs": missing_mandatory_docs,
            "documentation_complete": len(missing_mandatory_docs) == 0,
        },

        "extraction": {
            "total_fields_in_schema": len(record.claim.extracted_fields),
            "fields_found": len(found_fields),
            "fields_conflicting": len(conflicting_fields),
        },

        "citation_integrity": {
            "hallucinated_citations_caught": hallucination.hallucinated_citation_count,
            "fields_with_hallucinated_citation": hallucination.affected_field_count,
        },

        "field_verification": verification_counts,

        "triage": {
            "tier": triage.tier.value if triage else None,
            "score": triage.score if triage else None,
            "forced_review": triage.forced_review if triage else None,
            "high_risk_field_count": len(triage.high_risk_field_ids) if triage else None,
        },

        "review_queue_counts": record.review_queue_counts,

        "llm_usage": {
            "total_calls": len(calls),
            "tokens_by_provider": tokens_by_provider,
            "total_cost_usd": round(llm_cost_total, 6),
            "cost_is_estimate": llm_cost_is_estimate,
            "calls": calls_out,
        },
    }
    print(
        f"  done in {total_seconds:.1f}s | LOB={result['lob_classification']['predicted_lob']} | "
        f"triage={result['triage']['tier']} (forced_review={result['triage']['forced_review']}) | "
        f"LLM cost=${llm_cost_total:.4f} ({len(calls)} calls)"
    )
    return result


# --------------------------------------------------------------------------
# Aggregation
# --------------------------------------------------------------------------

def aggregate(per_claim: list[dict]) -> dict:
    ok_claims = [c for c in per_claim if not c["pipeline_error"]]
    n = len(ok_claims)
    n_all = len(per_claim)

    def mean(xs: list[float]) -> float | None:
        return round(statistics.mean(xs), 3) if xs else None

    def median(xs: list[float]) -> float | None:
        return round(statistics.median(xs), 3) if xs else None

    wall_times = [c["timing"]["total_wall_seconds"] for c in ok_claims]
    secs_per_page = [c["timing"]["seconds_per_page"] for c in ok_claims if c["timing"]["seconds_per_page"]]
    costs = [c["llm_usage"]["total_cost_usd"] for c in ok_claims]
    any_cost_is_estimate = any(c["llm_usage"]["cost_is_estimate"] for c in ok_claims)

    doc_complete_count = sum(1 for c in ok_claims if c["gate_check"]["documentation_complete"])
    forced_review_count = sum(1 for c in ok_claims if c["triage"]["forced_review"])

    total_hallucinated = sum(c["citation_integrity"]["hallucinated_citations_caught"] for c in ok_claims)

    tier_counts: dict[str, int] = {}
    for c in ok_claims:
        tier = c["triage"]["tier"]
        if tier:
            tier_counts[tier] = tier_counts.get(tier, 0) + 1

    field_totals = {"ok": 0, "needs_review": 0, "high_risk": 0}
    for c in ok_claims:
        for k in field_totals:
            field_totals[k] += c["field_verification"][k]
    total_fields_verified = sum(field_totals.values())

    ingestion_success_rates = [
        c["documents"]["ingestion_success_rate"] for c in ok_claims
        if c["documents"]["ingestion_success_rate"] is not None
    ]

    avg_wall_seconds = mean(wall_times)
    avg_cost_usd = mean(costs)

    # -- business metrics: cost & time comparison against sourced constants --
    business = None
    if avg_wall_seconds is not None and avg_cost_usd is not None:
        pipeline_minutes = avg_wall_seconds / 60
        pipeline_labor_cost = 0.0  # unattended run -- no adjuster time consumed while it runs
        claimlens_total_cost = pipeline_labor_cost + avg_cost_usd

        manual_low, manual_high = pricing.MANUAL_COST_PER_CLAIM_LOW_USD, pricing.MANUAL_COST_PER_CLAIM_HIGH_USD
        derived_manual_min_low, derived_manual_min_high = pricing.derived_manual_minutes_range()

        business = {
            "measured_avg_pipeline_minutes": round(pipeline_minutes, 3),
            "measured_avg_llm_cost_usd": avg_cost_usd,
            "llm_cost_is_estimate": any_cost_is_estimate,
            "claimlens_cost_per_claim_usd": round(claimlens_total_cost, 4),
            "claimlens_cost_note": (
                "LLM inference cost only -- the pipeline runs unattended, "
                "so no adjuster-hour cost is incurred while it processes. "
                "Compare against manual_cost_per_claim_usd_range below, "
                "which DOES include labor."
            ),
            "manual_cost_per_claim_usd_range": [manual_low, manual_high],
            "manual_cost_source": pricing.MANUAL_COST_SOURCE,
            "derived_manual_minutes_range": [derived_manual_min_low, derived_manual_min_high],
            "derived_manual_minutes_note": pricing.PRICING_METADATA["derived_manual_minutes_note"],
            "time_saved_minutes_range": [
                round(derived_manual_min_low - pipeline_minutes, 1),
                round(derived_manual_min_high - pipeline_minutes, 1),
            ],
            "adjuster_fully_loaded_hourly_usd": pricing.ADJUSTER_FULLY_LOADED_HOURLY_USD,
            "cost_avoided_per_claim_usd_range": [
                round(manual_low - claimlens_total_cost, 2),
                round(manual_high - claimlens_total_cost, 2),
            ],
        }

    return {
        "sample_size": n_all,
        "sample_size_successful": n,
        "sample_size_caveat": (
            f"All figures below are computed from {n_all} synthetic test claim "
            "folders generated for this project's own testing. This is a "
            "functional/engineering benchmark of the pipeline, NOT a "
            "statistically valid production sample -- do not present "
            "distributions (e.g. triage tier %) as real-world rates. "
            "Timing and cost are real measurements of real work the "
            "pipeline did; only the *sample* is synthetic, not the "
            "measurement."
        ),

        "timing": {
            "avg_wall_seconds": avg_wall_seconds,
            "median_wall_seconds": median(wall_times),
            "min_wall_seconds": round(min(wall_times), 3) if wall_times else None,
            "max_wall_seconds": round(max(wall_times), 3) if wall_times else None,
            "avg_seconds_per_page": mean(secs_per_page),
        },

        "llm_cost": {
            "avg_cost_per_claim_usd": avg_cost_usd,
            "total_cost_all_claims_usd": round(sum(costs), 6) if costs else None,
            "any_pricing_is_estimate": any_cost_is_estimate,
        },

        "documentation_completeness": {
            "claims_fully_documented": doc_complete_count,
            "rate": round(doc_complete_count / n, 4) if n else None,
        },

        "forced_review_override": {
            "claims_forced_to_review": forced_review_count,
            "rate": round(forced_review_count / n, 4) if n else None,
            "note": "Claims where a good composite triage score was overridden "
                    "because at least one critical field failed verification -- "
                    "the 'we don't let a good average hide one bad field' metric.",
        },

        "citation_integrity": {
            "total_hallucinated_citations_caught": total_hallucinated,
            "note": "Count of LLM-cited evidence block_ids that did not exist in "
                    "the claim's actual documents and were dropped before reaching "
                    "a human reviewer. Raw count, not a rate (see "
                    "docs/BENCHMARK_METHODOLOGY.md for why a rate isn't computable "
                    "here).",
        },

        "triage_tier_distribution": {
            "counts": tier_counts,
            "note": f"Distribution across n={n} synthetic test claims. NOT a "
                    "production STP rate -- see sample_size_caveat above and "
                    "docs/BENCHMARK_METHODOLOGY.md.",
        },

        "field_verification_distribution": {
            "counts": field_totals,
            "rates": {
                k: round(v / total_fields_verified, 4) for k, v in field_totals.items()
            } if total_fields_verified else {},
        },

        "ingestion_resilience": {
            "avg_success_rate": mean(ingestion_success_rates),
        },

        "business_metrics": business,
        "pricing_metadata": pricing.PRICING_METADATA,
    }


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--claims-dir", type=str, default=None,
                         help="Directory containing claim folders "
                              "(default: samples/claim_folders)")
    parser.add_argument("--outputs-dir", type=str, default=None,
                         help="Where ClaimStore checkpoints go "
                              "(default: outputs/_benchmark_run)")
    parser.add_argument("--output-json", type=str, default=None,
                         help="Where to write the metrics JSON "
                              "(default: outputs/benchmark_results.json)")
    parser.add_argument("--limit", type=int, default=None,
                         help="Only run the first N claim folders (for a quick smoke test)")
    args = parser.parse_args()

    preflight_check()

    claims_dir = Path(args.claims_dir) if args.claims_dir else PROJECT_ROOT / "samples" / "claim_folders"
    outputs_dir = Path(args.outputs_dir) if args.outputs_dir else PROJECT_ROOT / "outputs" / "_benchmark_run"
    output_json = Path(args.output_json) if args.output_json else PROJECT_ROOT / "outputs" / "benchmark_results.json"
    output_json.parent.mkdir(parents=True, exist_ok=True)

    folders = discover_claim_folders(claims_dir)
    if args.limit:
        folders = folders[: args.limit]
    if not folders:
        print(f"No claim folders found under {claims_dir}")
        sys.exit(1)

    print(f"ClaimLens benchmark -- {len(folders)} claim folder(s) from {claims_dir}\n")

    store = ClaimStore(outputs_dir)
    per_claim = []
    run_started = time.time()
    for folder in folders:
        try:
            per_claim.append(run_one_claim(store, folder))
        except Exception as exc:  # noqa: BLE001 - one bad folder shouldn't kill the whole run
            print(f"  !! unhandled exception on {folder.name}: {exc}")
            per_claim.append({
                "claim_id": folder.name, "claim_folder": folder.name,
                "pipeline_error": True, "pipeline_error_detail": str(exc),
                "timing": {"total_wall_seconds": None, "stage_seconds": {}, "total_pages": None, "seconds_per_page": None},
                "documents": {}, "lob_classification": {}, "gate_check": {},
                "extraction": {}, "citation_integrity": {"hallucinated_citations_caught": 0, "fields_with_hallucinated_citation": 0},
                "field_verification": {"ok": 0, "needs_review": 0, "high_risk": 0},
                "triage": {"tier": None, "score": None, "forced_review": None, "high_risk_field_count": None},
                "review_queue_counts": {}, "llm_usage": {"total_calls": 0, "tokens_by_provider": {}, "total_cost_usd": 0, "cost_is_estimate": False, "calls": []},
            })
    run_ended = time.time()

    summary = aggregate(per_claim)
    output = {
        "generated_by": "scripts/run_benchmark.py",
        "run_wall_seconds": round(run_ended - run_started, 2),
        "claims_dir": str(claims_dir),
        "summary": summary,
        "per_claim": per_claim,
    }

    output_json.write_text(json.dumps(output, indent=2, default=str))

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(json.dumps(summary, indent=2, default=str))
    print(f"\nFull results written to: {output_json}")


if __name__ == "__main__":
    main()
