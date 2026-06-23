# Sprint 3 Notes: Verification, Confidence Rating, and the Human-in-the-Loop Basis

## The brief, restated precisely

"Even a single digit error must be fatal" for numeric claim values, with
the same standard extended to dates and identifiers (VIN, codes) -- and a
verification step intelligent enough to also account for the possibility
that the OCR itself was unreliable, not just that the extraction model
hallucinated. Plus: a basis for human-in-the-loop review, and an optional
LLM-based check alongside the deterministic fuzzy/exact matching.

## What got built, and how the safety property is actually enforced

```
extracted field + its cited evidence block(s)
        |
        v
[1] evidence_verifier.py  -- does the cited TEXT contain this value?
        - number/date/code -> EXACT match only (zero tolerance)
        - text/boolean     -> fuzzy match (OCR noise is forgivable here)
        |
        v
[2] confidence_rating.py  -- combines match result + OCR confidence of the
    cited block(s) + the extraction agent's own confidence + (optional)
    an LLM second opinion -> one risk_level: ok / needs_review / high_risk
        - RULE: a critical-type exact-match FAILURE is high_risk, full
          stop. No LLM agreement, no confidence score, nothing overrides
          this.
        - RULE: even an exact match gets flagged needs_review if the
          cited evidence's OWN OCR confidence is low -- text matching only
          proves consistency with what OCR produced, not that OCR read
          the real document correctly in the first place.
        |
        v
[3] provenance_agent.py   -- renders an actual crop image of the cited
    bbox region, so a human can look at the real source pixels, not just
    trust the text pipeline
        |
        v
[4] human_review_queue.py -- flattens every needs_review/high_risk field
    into a sorted, self-contained queue (value, reasons, crop paths) --
    the literal handoff point for Sprint 5's reviewer UI
```

Plus `merge_agent.py`, which handles the case where a field's evidence
citations or independent extraction candidates actively DISAGREE with each
other -- and, same rule, never resolves a critical-field disagreement by
majority vote or confidence. Two different claim amounts don't get
averaged or "the more confident one wins" -- they become
`status: "conflicting"`, value `None`, and a human decides.

## A real bug this round's testing caught (worth knowing about)

While building the end-to-end Sprint 3 demo against the real example claim
folder, the verification pipeline initially reported a single-digit
mismatch using the WRONG evidence -- the cited block_id resolved to a
different photo's text than the one actually cited. Root cause:
`image_parser.py` numbers blocks `img_b001`, `img_b002`, ... starting from
1 independently for every image, so two photos in the same claim folder
produced colliding block_ids, and `ClaimState.get_block()` (which searches
across every document in a claim) silently returned whichever document's
block it found first.

This is now fixed at the one place every `DocumentRecord` is created
(`agents/ingestion/dispatcher.py`'s `_namespace_block_ids()`, prefixing
every block_id with its doc_id) and locked in with a regression test
(`tests/test_directory_discovery.py::test_block_ids_are_globally_unique_across_multiple_images_in_one_claim`).
It's flagged here explicitly rather than quietly fixed, because it's a
useful demonstration of exactly the failure mode this sprint's tests are
designed to surface: an invisible wrong-evidence bug that produces a
plausible-looking but incorrect result if nothing is actually checking.

## The LLM second-opinion layer: what it's for and what it explicitly cannot do

`llm_evidence_verifier.py` asks an LLM "does this evidence actually
support this value?" -- a semantic check on top of the deterministic
string/exact match, useful for catching things like "5:45 AM" vs "5:45 PM"
(high string similarity, completely different fact) that a fuzzy/exact
matcher alone might miss.

It is deliberately NOT given override authority over a critical-field
exact-match failure (`confidence_rating.py`'s `rate_field()`): if the
deterministic check says a number doesn't match, that finding stands even
if the LLM second opinion claims it's fine. `tests/test_confidence_rating.py`
proves this with a deliberately "fooled" fake LLM client that incorrectly
agrees a wrong number is correct -- the field stays `high_risk` regardless.
This is a deliberate, load-bearing design choice, not an oversight: an LLM
being wrong about whether a number matches is exactly the failure mode this
whole sprint exists to defend against, so it cannot be the final word on a
critical field.

Same sandbox network caveat as Sprints 1-2: no live Groq/Gemini call was
reachable to test `llm_evidence_verifier.py` against a real API response --
it's tested via a fake `LLMClient` covering the agreement, disagreement,
and malformed-response cases. See `SPRINT_2_NOTES.md` for how to wire up
real keys; the same client works here unchanged.

## What's still NOT covered (honest gaps for Sprint 4+)

- `merge_agent.detect_citation_conflicts()` only checks numeric fields for
  cross-citation disagreement right now -- date/code cross-citation
  conflict detection follows the same pattern but isn't wired up yet.
- Crop generation works for PDF and image blocks (anything with a real
  bbox + a renderable source). PPTX blocks have a real bbox but no
  slide-to-image renderer is wired up; DOCX/HTML blocks have no bbox at
  all by design (flowing documents). Both degrade to "no crop" rather than
  a fake one -- not silently wrong, just not yet built.
- The triage agent (Sprint 4) is the natural consumer of
  `field_verifications`/the review queue's `high_risk` count -- that
  wiring (e.g. "any high_risk field on a required field forces Needs
  Review, full stop, regardless of the composite risk score") doesn't
  exist yet, since Sprint 4 hasn't started.

## Running the demo

```bash
python3 scripts/run_sprint3_demo.py
```

Without an LLM key configured, this injects one correct field and one
field with a deliberately wrong digit, so you can see the full
verification -> rating -> crop -> review-queue pipeline catch the planted
error end-to-end, crop image included.
