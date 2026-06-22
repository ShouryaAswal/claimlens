"""
agents/section_extraction_agent.py
----------------------------------------
Sprint 2's centerpiece: section-wise field extraction. One LLM call per
schema section (5-15 fields, not 150 at once), with the FULL claim corpus
in context every time rather than a pre-retrieved subset -- see the design
doc's section 6 for why that combination resolves the context-window and
recall problems without needing a retrieval index.

Anti-hallucination guards (the "LLM extracts meaning, OCR owns coordinates"
principle, now enforced in code, not just policy):
  1. The LLM is given block_ids and asked to CITE them -- never asked for
     or allowed to state a page number or bounding box itself.
  2. Every cited block_id is checked against the claim's actual block_id
     set. A citation pointing at a block_id that doesn't exist is dropped,
     and if a field has zero surviving real citations, it's demoted to
     "missing" rather than trusted at face value -- an LLM that invents a
     citation gets caught here, not silently believed.
  3. Every field_id the schema asks for gets an entry in the result, even
     if the LLM's JSON omitted it entirely -- "missing fields explicitly
     listed, not silently dropped" is enforced by the code, not just
     requested in the prompt.

This agent has NO rule-based fallback (unlike the LOB classifier / doc-type
tagger) -- there's no sensible non-LLM substitute for "read this document
and tell me what the claimant's VIN is". Without a configured LLM client,
it raises LLMNotConfiguredError with the exact env var to set, rather than
either crashing confusingly or silently returning empty data.
"""

from __future__ import annotations

import logging

from core.llm_client import LLMClient, LLMNotConfiguredError, parse_json_response
from core.schemas import ClaimState, ExtractedField, FieldDefinition, SectionDefinition

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are an insurance claims field-extraction agent.

You will be given (1) a list of fields to extract and (2) a corpus of text
blocks from a claim's documents, each tagged with a unique block_id.

RULES -- follow these exactly:
1. Only use information that is actually present in the corpus. Never guess
   or infer a value that isn't stated.
2. For every field you find, cite the exact block_id(s) that support your
   answer. NEVER invent a block_id that doesn't appear in the corpus
   exactly as given.
3. If a field cannot be found anywhere in the corpus, set "status" to
   "missing", "value" to null, and explain briefly in "reason".
4. You MUST include an entry for EVERY field listed, even if missing. Do
   not omit a field just because you couldn't find it.
5. Return ONLY a valid JSON object, no other text, no markdown fences, in
   exactly this shape:

{
  "fields": {
    "<field_id>": {
      "value": "<string, or null if missing>",
      "confidence": <float 0.0-1.0>,
      "evidence_block_ids": ["<block_id>", ...],
      "status": "found" | "missing" | "low_confidence",
      "reason": "<short reason, especially if missing or low_confidence>"
    }
  }
}
"""


def _format_field_list(fields: list[FieldDefinition]) -> str:
    lines = []
    for f in fields:
        line = f"- {f.field_id} [{f.field_type}{', REQUIRED' if f.required else ''}]: {f.label}"
        if f.synonyms:
            line += f" (also called: {', '.join(f.synonyms)})"
        if f.description:
            line += f" -- {f.description}"
        lines.append(line)
    return "\n".join(lines)


def build_corpus_text(claim: ClaimState) -> str:
    """Renders the full claim corpus as plain text with block_id tags --
    this is what goes in the prompt. Grouped by document so the model has
    some structural context (which file each block came from), not just a
    flat soup of lines."""
    sections = []
    for doc in claim.documents:
        header = f"=== Document: {doc.source_file} (type: {doc.doc_type or 'unclassified'}) ==="
        lines = [header]
        for block in doc.blocks:
            lines.append(f"[{block.block_id}] {block.text}")
        sections.append("\n".join(lines))
    return "\n\n".join(sections)


def extract_section(
    section: SectionDefinition,
    claim: ClaimState,
    llm_client: LLMClient,
) -> dict[str, ExtractedField]:
    """Runs one extraction call for one schema section. Returns a dict
    keyed by field_id -- always containing every field the section asks
    for, regardless of what the LLM actually returned."""
    field_list_text = _format_field_list(section.fields)
    corpus_text = build_corpus_text(claim)
    user_prompt = (
        f"FIELDS TO EXTRACT (section: {section.section_id}):\n{field_list_text}\n\n"
        f"CLAIM CORPUS:\n{corpus_text}"
    )

    raw_response = llm_client.complete(_SYSTEM_PROMPT, user_prompt)

    try:
        parsed = parse_json_response(raw_response)
        returned_fields = parsed.get("fields", {})
        if not isinstance(returned_fields, dict):
            raise ValueError(f"'fields' was {type(returned_fields).__name__}, expected dict")
    except (ValueError, KeyError, TypeError) as exc:
        logger.warning(
            "Section %r: could not parse LLM response (%s). Raw response: %r",
            section.section_id, exc, raw_response[:500],
        )
        returned_fields = {}

    valid_block_ids = {b.block_id for b in claim.all_blocks}
    results: dict[str, ExtractedField] = {}

    for field in section.fields:
        field_id = field.field_id
        raw_field = returned_fields.get(field_id)

        if raw_field is None:
            # Exit criterion: missing fields are explicit, not dropped.
            results[field_id] = ExtractedField(
                field_id=field_id,
                status="missing",
                reason="Not returned by extraction model for this section call.",
            )
            continue

        cited_ids = raw_field.get("evidence_block_ids", []) or []
        if not isinstance(cited_ids, list):
            cited_ids = []
        verified_ids = [bid for bid in cited_ids if bid in valid_block_ids]
        hallucinated_ids = [bid for bid in cited_ids if bid not in valid_block_ids]

        if hallucinated_ids:
            logger.warning(
                "Section %r, field %r: model cited %d block_id(s) not present in "
                "the corpus (%s) -- dropped from evidence.",
                section.section_id, field_id, len(hallucinated_ids), hallucinated_ids,
            )

        status = raw_field.get("status", "missing")
        value = raw_field.get("value")
        reason = raw_field.get("reason")

        # A field claimed "found" with zero surviving real citations is not
        # trustworthy -- demote it rather than passing the claim through.
        if status == "found" and not verified_ids:
            status = "missing"
            value = None
            reason = (reason or "") + " [demoted: no verifiable evidence citation]"

        try:
            confidence = float(raw_field.get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0
        confidence = max(0.0, min(1.0, confidence))

        results[field_id] = ExtractedField(
            field_id=field_id,
            value=value,
            confidence=confidence,
            evidence_block_ids=verified_ids,
            status=status if status in ("found", "missing", "low_confidence", "conflicting") else "missing",
            reason=reason,
        )

    return results


def extract_claim(claim: ClaimState, llm_client: LLMClient | None = None) -> ClaimState:
    """Runs extraction for every section of the claim's resolved schema and
    writes results onto claim.extracted_fields. No rule-based fallback --
    raises LLMNotConfiguredError if llm_client is None."""
    if llm_client is None:
        raise LLMNotConfiguredError(
            "Section extraction requires a configured LLM client -- there is no "
            "sensible offline substitute for reading documents and extracting "
            "field values. Set GROQ_API_KEY or GOOGLE_API_KEY and call "
            "core.llm_client.get_llm_client(), or pass a client explicitly "
            "(e.g. a fake one in tests)."
        )
    if claim.lob_schema is None:
        raise ValueError(
            f"ClaimState {claim.claim_id!r} has no lob_schema resolved -- "
            f"run LOB classification + schema_loader.load_lob_schema() first."
        )

    for section in claim.lob_schema.sections:
        section_results = extract_section(section, claim, llm_client)
        claim.extracted_fields.update(section_results)
        found = sum(1 for f in section_results.values() if f.status == "found")
        logger.info(
            "Section %r: %d/%d fields found.",
            section.section_id, found, len(section_results),
        )

    return claim
