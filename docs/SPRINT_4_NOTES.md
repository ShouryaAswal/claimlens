# Sprint 4 Notes: Triage and the Reviewer Summary

## What got built

```
ClaimState (documents tagged, Gate Check run, fields extracted,
            field_verifications rated -- everything from Sprints 1-3)
        |
        v
[1] triage_agent.compute_triage()
        - +20 per missing mandatory document
        - +40 per HIGH_RISK field, +15/+8 per NEEDS_REVIEW field
          (required fields score higher than optional ones)
        - +15 if the claim's primary amount field exceeds a per-LOB
          high-value threshold
        - score -> stp_candidate (<=25) / needs_review (<=60) /
          high_risk_incomplete (>60)
        - RULE: any HIGH_RISK verification on a REQUIRED field sets
          forced_review=True, which makes stp_candidate impossible for
          that claim no matter how low the score ends up
        |
        v
[2] reviewer_summary_agent.generate_reviewer_summary()
        - rule-based template (default): every sentence is a direct
          readout of an already-computed number -- cannot hallucinate a
          fact about the claim because it never generates a new one
        - LLM-backed (opt-in): same content, smoother prose, explicitly
          told not to invent facts, falls back to the template on any
          failure or empty response
```

## The override rule, restated precisely

This is the same principle from Sprint 3 (`confidence_rating.py`: an LLM
agreeing cannot override a deterministic critical-field exact-match
failure), now enforced one layer further up the pipeline:

**A good composite triage score cannot buy back a straight-through-processing
route past a required field that failed evidence verification.**

Concretely: `compute_triage()` computes the tier from the score as normal,
then has one final check -- if `forced_review` is `True` and the tier the
score alone would produce is `stp_candidate`, it's bumped to
`needs_review` regardless. There is no code path that lets a high score
silence a `forced_review=True`. Proven directly in
`tests/test_triage_agent.py::test_high_risk_required_field_forces_review_even_with_otherwise_low_score`
and `test_forced_review_overrides_what_would_otherwise_be_stp`.

## `.env` support (this round's other change)

Per your note that `.env` + `python-dotenv` is now how you're managing
keys: `core/env.py` calls `load_dotenv(override=False)` and is imported
(for its side effect) at the top of both `core/config.py` (needs
`CLAIMLENS_OCR_ENGINE` at import time) and `core/llm_client.py` (needs
`GROQ_API_KEY`/`GOOGLE_API_KEY`/the model override vars). `override=False`
means a real shell-exported variable always wins over whatever's sitting
in `.env` -- so switching keys for a one-off test (`GROQ_API_KEY=xxx
python3 scripts/...`) still works exactly as you'd expect without editing
the file.

`requirements.txt` now installs `python-dotenv`, `openai`, and
`google-genai` by default (previously commented out as optional) since
your working setup already has the LLM-backed paths running.

## What Sprint 4 deliberately does NOT do

- It doesn't re-run or second-guess Gate Check or evidence verification --
  it trusts their outputs. If those are wrong, fix them upstream; triage
  is a routing decision on top of already-computed facts, not a second
  opinion on them.
- The high-value-claim thresholds (`HIGH_VALUE_THRESHOLD_BY_LOB` in
  `triage_agent.py`) are illustrative placeholders, the same honesty
  caveat as the design doc's original "Premium calculation" discussion --
  a real deployment would tune these against actual loss-cost data per
  LOB, not a guess made while building an internship MVP.
- The reviewer summary's LLM-backed mode, like every other LLM-touching
  agent in this project, is tested via dependency injection (a fake
  `LLMClient`), not confirmed against a live API response from inside the
  build environment. If you've got Sprint 2/3 already running smoothly
  with real keys per your last message, Sprint 4's LLM path uses the exact
  same `core.llm_client.get_llm_client()` you're already using -- nothing
  new to configure.

## Running it

```bash
python3 scripts/run_sprint4_demo.py
```

Without an LLM key, this plants the same deliberate single-digit error as
the Sprint 3 demo and walks it through triage and the reviewer summary --
you'll see `HIGH_RISK_INCOMPLETE`, `forced_review=True`, and the summary's
explicit "cannot be auto-approved... regardless of how clean the rest of
it looks" sentence, all generated from real (synthetic-claim) data, not
hardcoded for the demo.
