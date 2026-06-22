# Sprint 2 Notes: LLM Setup & What Was/Wasn't Live-Tested

Sprint 2 added the LOB classifier, doc-type tagger, Gate Check, and section
extraction agent. Be precise about what's actually been run end-to-end vs.
what's correct-but-unverified-live, since that distinction matters before
you demo this:

| Component | Mode | Live-tested in this round? |
|---|---|---|
| LOB classifier | Rule-based (default) | **Yes** -- against clean synthetic, real FUNSD-adjacent, and real-government-form-content samples |
| LOB classifier | LLM-backed | Logic tested via fake client; not run against a real Groq/Gemini API |
| Doc-type tagger | Rule-based (default) | **Yes** -- same data, including several real bugs caught and fixed (see `samples/real_world/REAL_DATA_SOURCES.md` test history) |
| Doc-type tagger | LLM-backed | Logic tested via fake client; not run against a real API |
| Gate Check | Deterministic | **Yes** -- including the deliberately-incomplete-sample exit criterion |
| Section extraction | LLM-backed (no fallback exists) | Logic tested via fake client (10 tests covering hallucinated citations, omitted fields, malformed JSON); **not run against a real Groq/Gemini API** |

## Why no live LLM test

`api.groq.com` and `generativelanguage.googleapis.com` are not on the
outbound allowlist of the sandbox this was built in (only
`api.anthropic.com` and package registries are). This is a tooling
constraint of that specific build environment, not a defect in the code --
`core/llm_client.py` is written directly against each provider's documented
API shape (Groq's OpenAI-compatible endpoint, Gemini's `google-genai` SDK),
the same level of care as the PaddleOCR integration's source-verified result
schema. The only way to close the gap between "correct by inspection and
thoroughly tested in isolation" and "confirmed against the real API" is to
run it with real keys on a machine with normal internet access -- which is
exactly what the next section walks through.

## Enabling real LLM calls

### 1. Get API keys

- **Groq** (used for LOB classification, doc-type tagging, and -- in later
  sprints -- the reviewer summary): https://console.groq.com -- free tier
  available. Note the June 17, 2026 deprecation of
  `llama-3.3-70b-versatile`/`llama-3.1-8b-instant` mentioned in earlier
  planning -- `core/llm_client.py` defaults to `openai/gpt-oss-120b`, Groq's
  recommended replacement.
- **Gemini** (used for section extraction, where the large context window
  matters): https://aistudio.google.com/apikey -- free tier available
  (Gemini 3 Flash: 1M token context, 1,500 requests/day at last check).

### 2. Install the SDKs

```bash
pip install openai google-genai
```

(`openai` is correct even for Groq -- Groq exposes an OpenAI-compatible
endpoint, same pattern already used in SunLeo DJ.)

### 3. Set environment variables

```bash
export GROQ_API_KEY="your-groq-key-here"
export GOOGLE_API_KEY="your-google-key-here"
```

### 4. Run the demo

```bash
python3 scripts/run_sprint2_demo.py
```

With at least one key set, it will run real section extraction in addition
to the (already-working-without-any-key) classification and Gate Check
stages, and print every extracted field with its status.

### 5. Smoke-test each client in isolation

```bash
python3 -c "
from core.llm_client import get_llm_client
client = get_llm_client('groq')
print(client.complete('Reply with only the word OK.', 'Test.'))
"
```

If that prints `OK` (or close to it), the Groq client is wired correctly.
Swap `'groq'` for `'gemini'` to test the other.

## What to do if a live call doesn't match the expected JSON shape

`core/llm_client.parse_json_response()` strips ` ```json ` fences
defensively, but if a real model's output drifts from the exact schema in
`section_extraction_agent.py`'s system prompt in some other way, the
section extraction tests in `tests/test_section_extraction.py` show exactly
which malformed-response shapes are already handled (missing fields,
hallucinated citations, non-JSON garbage, markdown fences, out-of-range
confidence) -- if you hit a new failure mode, it likely needs one more
case added to that test file and a corresponding guard in
`extract_section()`, following the same pattern.

## Next up: Sprint 3

Merge agent (multi-document conflict resolution when two documents both
claim a value for the same field), provenance linking (block_id -> bbox/crop
already exists in `ContentBlock`, so this is mostly about the
reviewer-facing crop rendering), and the evidence verifier (a deterministic
fuzzy-text check that the cited block's text plausibly supports the
extracted value, on top of the existing "does this block_id exist at all"
check already built in Sprint 2).
