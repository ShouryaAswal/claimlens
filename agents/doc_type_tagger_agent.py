"""
agents/doc_type_tagger_agent.py
------------------------------------
Stage 1b of Sprint 2: tag each individual ingested document (not the whole
claim -- a single document) with a doc_type, so Gate Check can compare
"what mandatory document types does this LOB's schema require" against
"what doc types did we actually see" and name exactly what's missing.

Same two-mode shape as the LOB classifier: rule-based keyword scoring by
default (no API key required), LLM-backed when a client is supplied.

The doc_type vocabulary here is the union of every schema's
`mandatory_doc_types`, plus a handful of common non-mandatory types that
show up in real claim packets (correspondence, witness statements) so they
don't all get dumped into "unknown".
"""

from __future__ import annotations

import logging

from core.llm_client import LLMClient, parse_json_response
from core.schemas import DocumentRecord, SourceFormat

logger = logging.getLogger(__name__)

# Keyword phrases are hand-curated per doc type (these aren't already
# sitting in schemas/*.json the way LOB vocab is, since mandatory_doc_types
# there are just type NAMES, not keyword sets).
DOC_TYPE_KEYWORDS: dict[str, list[str]] = {
    "police_report": [
        "police department", "police report", "case number", "officer",
        "incident report number", "crash records center",
        "report of motor vehicle crash", "reporting police department",
        "motor vehicle crash", "crash operator report", "operator report",
    ],
    "repair_estimate": [
        "repair estimate", "total estimate", "body shop", "paint and labor",
        "rental vehicle needed",
    ],
    "policy_declaration": [
        "declarations page", "policy declaration", "named insured",
        "policy period", "coverage limits", "deductible schedule",
    ],
    "inspection_report": [
        "inspection report", "adjuster inspection", "inspected by", "site visit",
    ],
    "inventory_list": [
        "inventory", "itemized list", "damaged items", "schedule of contents",
    ],
    "receipts": [
        "receipt", "purchase date", "subtotal", "total due", "amount paid",
    ],
    "pre_authorization": [
        "pre-authorization", "pre-auth", "prior authorization", "authorization number",
    ],
    "discharge_summary": [
        "discharge summary", "discharge date", "admission date",
        "attending physician", "hospital course",
    ],
    "itemized_bill": [
        "itemized bill", "billed amount", "icd-10", "cpt", "charge description",
        "statement of charges", "total billed",
    ],
    "witness_statement": [
        "witness statement", "witness name", "i witnessed", "statement of witness",
    ],
    "correspondence": [
        "dear", "sincerely", "re: claim", "adjuster note", "claim update",
    ],
}

# A keyword phrase that appears within the document's opening "title zone"
# is far more informative than the same phrase buried in body text -- real
# documents announce their type in the heading ("ADJUSTER NOTE", "REPAIR
# ESTIMATE"), not in a passing mention three paragraphs in. This is what
# separates "this document IS a police report" from "this document
# mentions a police report in passing".
_HEADING_ZONE_CHARS = 80
_HEADING_BONUS_MULTIPLIER = 3.0
_MIN_EVIDENCE_SCORE = 2.0

# A pure evidentiary photo (vehicle damage, property damage) typically has
# little to no recognizable text -- this threshold is intentionally lenient
# (a label sticker or a faint watermark shouldn't flip the classification).
_PHOTO_TEXT_DENSITY_THRESHOLD = 40  # total characters across all OCR blocks


def tag_doc_type_rule_based(document: DocumentRecord) -> tuple[str, float]:
    # Normalize newlines, tabs, and multiple spaces into a single space
    text = " ".join(document.full_text.lower().split())
    heading_zone = text[:_HEADING_ZONE_CHARS]

    if document.source_format == SourceFormat.IMAGE and len(text.strip()) < _PHOTO_TEXT_DENSITY_THRESHOLD:
        return "photos", 0.7  # heuristic, not keyword-matched -- deliberately moderate confidence

    scores: dict[str, float] = {}
    for doc_type, keywords in DOC_TYPE_KEYWORDS.items():
        score = 0.0
        for kw in keywords:
            if kw in heading_zone:
                score += _HEADING_BONUS_MULTIPLIER
            elif kw in text:
                score += 1.0
        scores[doc_type] = score

    total = sum(scores.values())
    if total == 0:
        return "unknown", 0.0

    best_type, best_score = max(scores.items(), key=lambda kv: kv[1])
    # A single incidental keyword mention (e.g. a property-loss form that
    # happens to mention "repair estimates" once in a sentence) isn't
    # enough evidence to commit to a specific type -- that's a guess
    # dressed up as a classification. Below this floor, admit "unknown"
    # rather than confidently mislabeling.
    if best_score < _MIN_EVIDENCE_SCORE:
        return "unknown", 0.0
    confidence = best_score / total
    return best_type, round(confidence, 4)


_LLM_SYSTEM_PROMPT = """You are an insurance claims document classifier.
Given the raw text extracted from ONE document (not a full claim, just one
file), classify its document type. Respond with ONLY a JSON object, no
other text, in exactly this shape:
{"doc_type": "<type>", "confidence": <float 0.0-1.0>}
Valid types: police_report, repair_estimate, policy_declaration,
inspection_report, inventory_list, receipts, pre_authorization,
discharge_summary, itemized_bill, witness_statement, correspondence,
photos, unknown.
"""


def tag_doc_type_with_llm(document: DocumentRecord, llm_client: LLMClient, max_chars: int = 4000) -> tuple[str, float]:
    excerpt = document.full_text[:max_chars]
    raw = llm_client.complete(_LLM_SYSTEM_PROMPT, excerpt)
    try:
        parsed = parse_json_response(raw)
        doc_type = str(parsed.get("doc_type", "unknown"))
        confidence = float(parsed.get("confidence", 0.0))
        if doc_type not in DOC_TYPE_KEYWORDS and doc_type not in ("photos", "unknown"):
            logger.warning("LLM returned unrecognized doc_type %r; treating as unknown.", doc_type)
            doc_type = "unknown"
        return doc_type, round(max(0.0, min(1.0, confidence)), 4)
    except (ValueError, KeyError, TypeError) as exc:
        logger.warning("Could not parse LLM doc-type response (%s): %r", exc, raw)
        return "unknown", 0.0


def tag_doc_type(document: DocumentRecord, llm_client: LLMClient | None = None) -> tuple[str, float]:
    """The function the rest of the pipeline calls."""
    if llm_client is not None:
        try:
            return tag_doc_type_with_llm(document, llm_client)
        except Exception as exc:  # noqa: BLE001
            logger.warning("LLM-backed doc-type tagging failed (%s); falling back to rule-based.", exc)
    return tag_doc_type_rule_based(document)


def tag_all_documents(documents: list[DocumentRecord], llm_client: LLMClient | None = None) -> None:
    """Mutates each DocumentRecord's `doc_type` in place (the field already
    exists on the schema, scaffolded in Sprint 0 for exactly this)."""
    for doc in documents:
        doc_type, confidence = tag_doc_type(doc, llm_client)
        doc.doc_type = doc_type
        logger.debug("Tagged %s as %s (confidence %.2f)", doc.source_file, doc_type, confidence)
