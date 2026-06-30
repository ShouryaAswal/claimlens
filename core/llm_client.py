"""
core/llm_client.py
---------------------
Thin, provider-agnostic LLM client. No LangChain (same reasoning as the
ingestion layer: this is a couple of HTTP calls, not a use case that needs
a framework) -- just the official SDKs, read from environment variables.

Two providers, matching the design doc's model choice:
  - Groq (`GROQ_API_KEY`)   -- fast/cheap, used for LOB classification,
                               doc-type tagging, and the reviewer summary.
  - Gemini (`GOOGLE_API_KEY`) -- large context window, used for section-wise
                               field extraction over the full claim corpus.

IMPORTANT -- this code could not be run against a live API in the sandbox
this was built in (api.groq.com / generativelanguage.googleapis.com are not
on that sandbox's outbound allowlist; only api.anthropic.com is). It is
written correctly against each provider's documented OpenAI-compatible /
native SDK interface and exercised in tests via dependency injection (a
fake `complete_fn`), but the only way to confirm it works against the real
APIs is to run it with real keys in an environment with normal internet
access. See SPRINT_2_NOTES.md for exactly what was and wasn't verified live.

If no key is configured for a given provider, `get_llm_client()` returns
None rather than raising -- callers (lob_classifier_agent.py,
doc_type_tagger_agent.py) use that to fall back to a deterministic,
no-LLM-required mode. section_extraction_agent.py has no sensible
fallback (there's no rule-based substitute for "read this document and
extract this field"), so it raises a clear, actionable error instead.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Optional, Protocol

from core import env  # noqa: F401 -- side effect: loads .env before any os.environ.get() below

logger = logging.getLogger(__name__)

GROQ_DEFAULT_MODEL = os.environ.get("CLAIMLENS_GROQ_MODEL", "openai/gpt-oss-120b")
GEMINI_DEFAULT_MODEL = os.environ.get("CLAIMLENS_GEMINI_MODEL", "gemini-3.1-flash-lite")


class LLMNotConfiguredError(Exception):
    """Raised when an agent that has no offline fallback is asked to run
    without any LLM provider configured."""


class CompleteFn(Protocol):
    def __call__(self, system_prompt: str, user_prompt: str) -> str: ...


@dataclass
class LLMClient:
    provider: str
    model: str
    complete: CompleteFn


def _build_groq_client(model: str) -> Optional[LLMClient]:
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        return None
    try:
        from openai import OpenAI  # Groq exposes an OpenAI-compatible endpoint
    except ImportError:
        logger.warning("GROQ_API_KEY is set but the 'openai' package isn't installed "
                        "(pip install openai). Skipping Groq client.")
        return None

    client = OpenAI(api_key=api_key, base_url="https://api.groq.com/openai/v1")

    def _complete(system_prompt: str, user_prompt: str) -> str:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0,
            response_format={"type": "json_object"},
        )
        return response.choices[0].message.content or ""

    return LLMClient(provider="groq", model=model, complete=_complete)


def _build_gemini_client(model: str) -> Optional[LLMClient]:
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        return None
    try:
        from google import genai
    except ImportError:
        logger.warning("GOOGLE_API_KEY is set but the 'google-genai' package isn't "
                        "installed (pip install google-genai). Skipping Gemini client.")
        return None

    client = genai.Client(api_key=api_key)

    def _complete(system_prompt: str, user_prompt: str) -> str:
        response = client.models.generate_content(
            model=model,
            contents=user_prompt,
            config={
                "system_instruction": system_prompt,
                "response_mime_type": "application/json",
                "temperature": 0,
            },
        )
        return response.text or ""

    return LLMClient(provider="gemini", model=model, complete=_complete)


def get_llm_client(provider: str = "groq") -> Optional[LLMClient]:
    """Returns a configured LLMClient, or None if the relevant API key
    isn't set. `provider` is "groq" or "gemini"."""
    if provider == "groq":
        return _build_groq_client(GROQ_DEFAULT_MODEL)
    elif provider == "gemini":
        return _build_gemini_client(GEMINI_DEFAULT_MODEL)
    raise ValueError(f"Unknown provider {provider!r}; expected 'groq' or 'gemini'")


def parse_json_response(raw: str) -> dict:
    """LLMs occasionally wrap JSON in ```json fences despite being told not
    to -- strip those defensively before parsing, same pattern used
    throughout the Claude-in-artifacts guidance this project already
    follows elsewhere."""
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:]
    cleaned = cleaned.strip()
    return json.loads(cleaned)
