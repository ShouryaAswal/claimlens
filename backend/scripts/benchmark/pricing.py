"""
scripts/benchmark/pricing.py
-----------------------------
Every dollar figure the benchmark reports comes from one of two places:
  (a) a token count *measured* from a real pipeline run (see token_tracker.py), or
  (b) a constant defined here, with its source in a comment next to it.

Nothing in this file is invented. Where I could not find a trustworthy
published number (e.g. "average minutes an adjuster spends reviewing a
claim packet"), the constant is clearly marked DERIVED (computed from
other cited numbers, not itself a citation) or ASSUMPTION (a stated
guess you should replace with your own data if you get it) -- see
docs/BENCHMARK_METHODOLOGY.md for the full writeup of why each number
looks the way it does.

*** UPDATE THESE BEFORE TRUSTING THE OUTPUT ***
LLM prices change constantly and the two providers ClaimLens uses
(Groq, Gemini) both ship new/cheaper model tiers often. The numbers
below were current as of July 2026. Before you present these results,
re-check:
  - https://groq.com/pricing
  - https://ai.google.dev/gemini-api/docs/pricing
and update PROVIDER_PRICING to match.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelPrice:
    input_per_million: float   # USD per 1,000,000 input tokens
    output_per_million: float  # USD per 1,000,000 output tokens
    source: str


# Keyed by the exact model string ClaimLens's core/llm_client.py requests
# (CLAIMLENS_GROQ_MODEL / CLAIMLENS_GEMINI_MODEL, or their defaults).
# If your .env overrides the model, add a matching entry here -- the
# benchmark will otherwise fall back to FALLBACK_PRICE_PER_MILLION and
# flag every claim's cost as an estimate in the output JSON.
PROVIDER_PRICING: dict[str, ModelPrice] = {
    # Groq-hosted openai/gpt-oss-120b -- ClaimLens's default for
    # classification, doc-type tagging, evidence verification support,
    # and the reviewer summary (core/llm_client.py GROQ_DEFAULT_MODEL).
    "openai/gpt-oss-120b": ModelPrice(
        input_per_million=0.15,
        output_per_million=0.75,
        source="Groq, 'Day Zero Support for OpenAI Open Models' "
               "(groq.com/blog/day-zero-support-for-openai-open-models), "
               "checked July 2026. Groq's main pricing page (groq.com/pricing) "
               "is the canonical source -- re-check there, some third-party "
               "trackers list $0.60/M output instead of $0.75/M.",
    ),
    # Gemini -- ClaimLens's default for section extraction
    # (CLAIMLENS_GEMINI_MODEL default in core/llm_client.py).
    "gemini-3.1-flash-lite": ModelPrice(
        input_per_million=0.25,
        output_per_million=1.50,
        source="Google AI for Developers pricing page "
               "(ai.google.dev/gemini-api/docs/pricing), checked July 2026.",
    ),
    # Older/alternate Gemini tier some setups may still point at.
    "gemini-2.5-flash-lite": ModelPrice(
        input_per_million=0.10,
        output_per_million=0.40,
        source="Google AI for Developers pricing page "
               "(ai.google.dev/gemini-api/docs/pricing), checked July 2026.",
    ),
    "gemini-3-flash": ModelPrice(
        input_per_million=0.50,
        output_per_million=3.00,
        source="Google AI for Developers pricing page "
               "(ai.google.dev/gemini-api/docs/pricing), checked July 2026.",
    ),
}

# Used only if a model string shows up that isn't in PROVIDER_PRICING above
# (e.g. you changed CLAIMLENS_GEMINI_MODEL and forgot to add a pricing
# row). Keeps the script from crashing, but every affected claim's cost
# is flagged "pricing_is_estimate": true in the JSON so you don't
# accidentally present a made-up number as a real one.
FALLBACK_PRICE_PER_MILLION = ModelPrice(
    input_per_million=0.50,
    output_per_million=2.00,
    source="FALLBACK -- no pricing entry found for this model string. "
           "This is a placeholder, not a citation. Add a real entry to "
           "PROVIDER_PRICING in this file.",
)


def price_for_model(model: str) -> tuple[ModelPrice, bool]:
    """Returns (price, is_estimate). is_estimate=True means the fallback
    price was used because `model` wasn't found in PROVIDER_PRICING."""
    price = PROVIDER_PRICING.get(model)
    if price is not None:
        return price, False
    return FALLBACK_PRICE_PER_MILLION, True


def cost_usd(input_tokens: int, output_tokens: int, model: str) -> tuple[float, bool]:
    price, is_estimate = price_for_model(model)
    cost = (
        input_tokens / 1_000_000 * price.input_per_million
        + output_tokens / 1_000_000 * price.output_per_million
    )
    return cost, is_estimate


# ---------------------------------------------------------------------
# Labor-cost constants, for the "$ saved" business metric.
# ---------------------------------------------------------------------

# U.S. Bureau of Labor Statistics, Occupational Outlook Handbook,
# "Claims Adjusters, Appraisers, Examiners, and Investigators", May 2024
# data (bls.gov/ooh/business-and-financial/claims-adjusters-appraisers-
# examiners-and-investigators.htm). Median annual wage for claims
# adjusters/examiners/investigators: $76,790/year.
# CITED, government source.
BLS_MEDIAN_ANNUAL_WAGE_USD = 76_790
BLS_ANNUAL_WORK_HOURS = 2_080  # standard full-time hours/year (40hrs x 52wks)
ADJUSTER_HOURLY_WAGE_USD = round(BLS_MEDIAN_ANNUAL_WAGE_USD / BLS_ANNUAL_WORK_HOURS, 2)

# Fully-loaded labor cost multiplier (benefits, overhead, facilities) --
# a commonly used range in cost-per-claim/HR modeling is 1.25x-1.4x base
# wage. This multiplier itself is an ASSUMPTION, not a specific citation
# -- flagged as such in every output that uses it.
FULLY_LOADED_MULTIPLIER = 1.3
ADJUSTER_FULLY_LOADED_HOURLY_USD = round(ADJUSTER_HOURLY_WAGE_USD * FULLY_LOADED_MULTIPLIER, 2)

# Manual claims-processing cost per claim, a figure attributed to a 2022
# Deloitte report and repeated across many secondary/aggregator sources
# (could not locate Deloitte's original report directly -- present this
# as "industry-cited," not independently verified).
MANUAL_COST_PER_CLAIM_LOW_USD = 40.0
MANUAL_COST_PER_CLAIM_HIGH_USD = 60.0
MANUAL_COST_SOURCE = (
    "Figure attributed to Deloitte (2022) in multiple secondary sources "
    "(e.g. numberanalytics.com/blog/modern-insurance-claims-automation). "
    "Could not locate Deloitte's original report to verify directly -- "
    "present as 'industry-cited estimate,' not a confirmed primary figure."
)

# DERIVED (not a citation): implied minutes of labor-equivalent time per
# claim, back-calculated from the manual cost range above divided by the
# fully-loaded hourly rate. This is OUR derivation, shown so it's
# reproducible -- not a number we found published anywhere. Use it as a
# reference point, not as ground truth, and say so out loud if asked.
def derived_manual_minutes_range() -> tuple[float, float]:
    low_hours = MANUAL_COST_PER_CLAIM_LOW_USD / ADJUSTER_FULLY_LOADED_HOURLY_USD
    high_hours = MANUAL_COST_PER_CLAIM_HIGH_USD / ADJUSTER_FULLY_LOADED_HOURLY_USD
    return round(low_hours * 60, 1), round(high_hours * 60, 1)


PRICING_METADATA = {
    "adjuster_hourly_wage_usd": ADJUSTER_HOURLY_WAGE_USD,
    "adjuster_hourly_wage_source": (
        "U.S. Bureau of Labor Statistics, Occupational Outlook Handbook, "
        "May 2024 data: median annual wage for claims adjusters, examiners, "
        "and investigators = $76,790/year. "
        "bls.gov/ooh/business-and-financial/claims-adjusters-appraisers-"
        "examiners-and-investigators.htm"
    ),
    "adjuster_fully_loaded_hourly_usd": ADJUSTER_FULLY_LOADED_HOURLY_USD,
    "fully_loaded_multiplier": FULLY_LOADED_MULTIPLIER,
    "fully_loaded_multiplier_note": "ASSUMPTION, not a citation -- a commonly "
                                     "used 1.25x-1.4x overhead range in "
                                     "cost-per-claim modeling.",
    "manual_cost_per_claim_low_usd": MANUAL_COST_PER_CLAIM_LOW_USD,
    "manual_cost_per_claim_high_usd": MANUAL_COST_PER_CLAIM_HIGH_USD,
    "manual_cost_source": MANUAL_COST_SOURCE,
    "derived_manual_minutes_range": derived_manual_minutes_range(),
    "derived_manual_minutes_note": (
        "DERIVED, not cited -- manual cost range divided by fully-loaded "
        "hourly rate. This is our own back-calculation, shown for "
        "transparency. Replace with a real practitioner data point if you "
        "can get one; label it clearly as a derivation either way."
    ),
}
