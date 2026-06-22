"""
agents/lob_classifier_agent.py
----------------------------------
Stage 1 of Sprint 2: figure out which Line of Business a claim belongs to,
so core/schema_loader.py knows which schema to resolve.

Two modes:
  - Rule-based (default, no API key needed): scores the claim's full text
    against each LOB schema's own vocabulary (field labels + synonyms +
    mandatory_doc_types, already sitting right there in schemas/*.json --
    no separate keyword list to maintain). Fully deterministic and testable
    without any network access.
  - LLM-backed (opt-in, requires GROQ_API_KEY): a single cheap/fast call,
    matching the design doc's "Stage 1: LOB classification (cheap/fast
    call)". Used when an LLMClient is passed in.

Both modes return the same shape: (LOB, confidence). The rule-based mode is
not a placeholder to be deleted later -- it's a legitimate, free, instant
fallback for when no LLM is configured or the API is down, the same
"graceful degradation" pattern as the OCR engine factory.
"""

from __future__ import annotations

import logging
import re
from collections import Counter

from core.llm_client import LLMClient, parse_json_response
from core.schema_loader import load_all_schemas
from core.schemas import LOB

logger = logging.getLogger(__name__)

_WORD_RE = re.compile(r"[a-z0-9]+")


def _normalize(text: str) -> str:
    return text.lower()


def _build_vocabulary(lob: LOB) -> set[str]:
    schema = load_all_schemas()[lob]
    vocab: set[str] = set()
    for section in schema.sections:
        for field in section.fields:
            vocab.add(field.label.lower())
            vocab.update(s.lower() for s in field.synonyms)
    vocab.update(d.replace("_", " ") for d in schema.mandatory_doc_types)
    # Drop very short/generic terms that would match almost anything and
    # add noise rather than signal -- but keep 3-letter terms, since
    # several legitimately distinctive insurance codes are exactly that
    # length (RCV, ACV, ICD, CPT).
    return {v for v in vocab if len(v) >= 3}


def classify_lob_rule_based(corpus_text: str) -> tuple[LOB, float]:
    text = _normalize(corpus_text)
    all_lobs = (LOB.AUTO, LOB.PROPERTY, LOB.HEALTH)
    vocabs = {lob: _build_vocabulary(lob) for lob in all_lobs}

    # IDF-style weighting: a term that appears in every LOB's vocabulary
    # (e.g. "policy number") is shared boilerplate with near-zero
    # discriminative power; a term unique to one LOB (e.g. "rcv", "icd-10")
    # is a strong signal. Weight = 1 / (number of LOB vocabularies
    # containing this term), same idea as TF-IDF's rationale, applied to a
    # 3-bucket vocabulary instead of a full corpus.
    term_lob_counts: Counter[str] = Counter()
    for lob, vocab in vocabs.items():
        for term in vocab:
            term_lob_counts[term] += 1

    scores: dict[LOB, float] = {lob: 0.0 for lob in all_lobs}
    for lob in all_lobs:
        for term in vocabs[lob]:
            if term in text:
                scores[lob] += 1.0 / term_lob_counts[term]

    total = sum(scores.values())
    if total == 0:
        return LOB.UNKNOWN, 0.0

    best_lob, best_score = max(scores.items(), key=lambda kv: kv[1])
    confidence = best_score / total
    logger.debug("LOB rule-based weighted scores: %s -> %s (confidence %.2f)", scores, best_lob, confidence)
    return best_lob, round(confidence, 4)


_LLM_SYSTEM_PROMPT = """You are an insurance claims intake classifier.
Given the raw text extracted from a claim's documents, classify which Line
of Business (LOB) it belongs to. Respond with ONLY a JSON object, no other
text, in exactly this shape:
{"lob": "auto" | "property" | "health" | "unknown", "confidence": <float 0.0-1.0>, "reason": "<one short sentence>"}
"""


def classify_lob_with_llm(corpus_text: str, llm_client: LLMClient, max_chars: int = 6000) -> tuple[LOB, float]:
    """LLM-backed classification. Truncates the corpus to a representative
    excerpt -- classification doesn't need the whole packet, just enough
    signal, and keeping this call cheap is the whole point of using it at
    Stage 1 rather than the larger extraction-stage model."""
    excerpt = corpus_text[:max_chars]
    raw = llm_client.complete(_LLM_SYSTEM_PROMPT, excerpt)
    try:
        parsed = parse_json_response(raw)
        lob = LOB(parsed.get("lob", "unknown"))
        confidence = float(parsed.get("confidence", 0.0))
        return lob, round(max(0.0, min(1.0, confidence)), 4)
    except (ValueError, KeyError, TypeError) as exc:
        logger.warning("Could not parse LLM LOB classification response (%s): %r", exc, raw)
        return LOB.UNKNOWN, 0.0


def classify_lob(corpus_text: str, llm_client: LLMClient | None = None) -> tuple[LOB, float]:
    """The function the rest of the pipeline calls. Falls back to
    rule-based automatically if no LLM client is supplied or configured."""
    if llm_client is not None:
        try:
            return classify_lob_with_llm(corpus_text, llm_client)
        except Exception as exc:  # noqa: BLE001 - never let a flaky LLM call kill the pipeline
            logger.warning("LLM-backed LOB classification failed (%s); falling back to rule-based.", exc)
    return classify_lob_rule_based(corpus_text)
