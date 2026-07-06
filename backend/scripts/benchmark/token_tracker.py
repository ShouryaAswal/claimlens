"""
scripts/benchmark/token_tracker.py
------------------------------------
Records real token usage (input/output counts, latency, which pipeline
stage was active) for every LLM call made anywhere in the pipeline --
without editing core/llm_client.py or any agent file.

How: core/llm_client.py builds its Groq client on top of the official
`openai` SDK, and its Gemini client on top of the official `google-genai`
SDK (see core/llm_client.py's own docstring). Both SDKs expose a single
class method that every completion call ultimately goes through:

  - openai.resources.chat.completions.completions.Completions.create
  - google.genai.models.Models.generate_content

This module monkeypatches those two class methods for the duration of a
benchmark run, wraps each real call to capture `response.usage` (OpenAI/
Groq) or `response.usage_metadata` (Gemini), and restores the originals
on unpatch(). It never touches request/response content, only reads the
usage counters the SDKs already return.

Usage:
    from scripts.benchmark.token_tracker import tracker

    tracker.patch()
    try:
        tracker.set_stage("extract")
        ... call the pipeline ...
    finally:
        tracker.unpatch()

    calls = tracker.records_for_current_claim()
    tracker.reset()  # before the next claim
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field


@dataclass
class LLMCallRecord:
    provider: str          # "groq" or "gemini"
    model: str
    stage: str              # pipeline stage active when the call was made
    input_tokens: int
    output_tokens: int
    latency_seconds: float


class TokenTracker:
    def __init__(self) -> None:
        self._records: list[LLMCallRecord] = []
        self._lock = threading.Lock()
        self.current_stage = "unknown"
        self._patched = False
        self._orig_openai_create = None
        self._orig_genai_generate = None

    # -- stage bookkeeping ------------------------------------------------

    def set_stage(self, stage: str) -> None:
        self.current_stage = stage

    # -- recording ----------------------------------------------------------

    def _record(self, rec: LLMCallRecord) -> None:
        with self._lock:
            self._records.append(rec)

    def records_for_current_claim(self) -> list[LLMCallRecord]:
        with self._lock:
            return list(self._records)

    def reset(self) -> None:
        with self._lock:
            self._records = []
        self.current_stage = "unknown"

    # -- patch / unpatch ------------------------------------------------------

    def patch(self) -> None:
        if self._patched:
            return
        self._patch_openai()
        self._patch_genai()
        self._patched = True

    def unpatch(self) -> None:
        if not self._patched:
            return
        if self._orig_openai_create is not None:
            try:
                from openai.resources.chat.completions.completions import Completions
                Completions.create = self._orig_openai_create
            except ImportError:
                pass
        if self._orig_genai_generate is not None:
            try:
                from google.genai.models import Models
                Models.generate_content = self._orig_genai_generate
            except ImportError:
                pass
        self._patched = False

    def __enter__(self) -> "TokenTracker":
        self.patch()
        return self

    def __exit__(self, *exc_info) -> None:
        self.unpatch()

    # -- the actual patches ------------------------------------------------

    def _patch_openai(self) -> None:
        try:
            from openai.resources.chat.completions.completions import Completions
        except ImportError:
            # openai isn't installed -- Groq-backed stages simply won't be
            # tracked (they'll also fail at runtime with a clear import
            # error from core/llm_client.py itself, so this is safe).
            return

        original_create = Completions.create
        self._orig_openai_create = original_create
        tracker = self

        def patched_create(self_completions, *args, **kwargs):
            start = time.time()
            response = original_create(self_completions, *args, **kwargs)
            latency = time.time() - start
            model = kwargs.get("model", "unknown")
            input_tokens = output_tokens = 0
            try:
                usage = response.usage
                if usage is not None:
                    input_tokens = getattr(usage, "prompt_tokens", 0) or 0
                    output_tokens = getattr(usage, "completion_tokens", 0) or 0
            except Exception:
                pass  # never let usage-extraction break the actual call
            tracker._record(LLMCallRecord(
                provider="groq", model=model, stage=tracker.current_stage,
                input_tokens=input_tokens, output_tokens=output_tokens,
                latency_seconds=latency,
            ))
            return response

        Completions.create = patched_create

    def _patch_genai(self) -> None:
        try:
            from google.genai.models import Models
        except ImportError:
            return

        original_generate = Models.generate_content
        self._orig_genai_generate = original_generate
        tracker = self

        def patched_generate(self_models, *args, **kwargs):
            start = time.time()
            response = original_generate(self_models, *args, **kwargs)
            latency = time.time() - start
            model = kwargs.get("model", "unknown")
            input_tokens = output_tokens = 0
            try:
                usage = response.usage_metadata
                if usage is not None:
                    input_tokens = getattr(usage, "prompt_token_count", 0) or 0
                    output_tokens = getattr(usage, "candidates_token_count", 0) or 0
            except Exception:
                pass
            tracker._record(LLMCallRecord(
                provider="gemini", model=model, stage=tracker.current_stage,
                input_tokens=input_tokens, output_tokens=output_tokens,
                latency_seconds=latency,
            ))
            return response

        Models.generate_content = patched_generate


# Module-level singleton -- one tracker for the whole benchmark process.
tracker = TokenTracker()
