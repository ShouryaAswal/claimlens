"""
agents/merge_agent.py
--------------------------
Sprint 3's multi-document conflict resolution.

Context on why this looks slightly different from the original v1 design
sketch: section_extraction_agent.py (Sprint 2) already runs ONE call per
schema section over the WHOLE claim corpus at once, rather than extracting
per-document and merging afterward -- that design choice (see the design
doc, section 6) already avoids most "document A says X, document B says Y"
conflicts, because the model sees every document simultaneously and is
asked to pick one value.

Two genuine conflict scenarios remain, and this agent handles both:

1. Same-field, multiple citations that disagree. A field can have multiple
   evidence_block_ids (e.g. a policy number appears on both the
   declarations page AND the police report) -- if those cited blocks
   actually contain DIFFERENT values for a critical field type, that's a
   real, dangerous discrepancy that must be surfaced, not silently resolved
   by trusting whichever block happens to be first in the list.

2. Independent re-extraction candidates. If a field is ever extracted more
   than once (a retry, a future per-document pass, a second model run for
   cross-checking), merge_candidates() resolves multiple independent
   ExtractedField proposals into one, by: (a) exact agreement among
   critical-type candidates wins outright; (b) disagreement among
   critical-type candidates is NEVER silently resolved by majority vote or
   highest confidence -- it's marked "conflicting" and routed to a human,
   because picking a winner among two different claim amounts by
   popularity is exactly the kind of silent wrong-number risk this whole
   sprint exists to prevent; (c) for non-critical text fields, the most
   repeated value wins ties broken by combined confidence.
"""

from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass, field as dc_field
from statistics import mean

from agents.evidence_verifier import CRITICAL_FIELD_TYPES, _extract_numeric_candidates
from core.schemas import ClaimState, ExtractedField, FieldDefinition

logger = logging.getLogger(__name__)


@dataclass
class ConflictReport:
    field_id: str
    has_conflict: bool
    distinct_values: list[str] = dc_field(default_factory=list)
    detail: str = ""


def detect_citation_conflicts(
    field: ExtractedField,
    field_def: FieldDefinition,
    claim: ClaimState,
) -> ConflictReport:
    """Checks whether a single field's MULTIPLE cited evidence blocks
    actually agree with each other."""
    if len(field.evidence_block_ids) < 2 or field.value is None:
        return ConflictReport(field_id=field.field_id, has_conflict=False)

    blocks = [b for bid in field.evidence_block_ids if (b := claim.get_block(bid)) is not None]
    if len(blocks) < 2:
        return ConflictReport(field_id=field.field_id, has_conflict=False)

    if field_def.field_type == "number":
        target = _extract_numeric_candidates(field.value)
        per_block_values = set()
        for b in blocks:
            candidates = _extract_numeric_candidates(b.text)
            if target and target[0] in candidates:
                per_block_values.add(str(target[0]))

        conflicting_numbers = {
            str(n) for b in blocks for n in _extract_numeric_candidates(b.text)
        } - per_block_values

        if not per_block_values and conflicting_numbers:
            return ConflictReport(
                field_id=field.field_id, has_conflict=True,
                distinct_values=sorted(conflicting_numbers),
                detail=(
                    f"None of the {len(blocks)} cited blocks contain the claimed value "
                    f"{field.value!r} verbatim, but they do contain other numbers "
                    f"({sorted(conflicting_numbers)}) -- possible citation-value mismatch."
                ),
            )
        return ConflictReport(field_id=field.field_id, has_conflict=False)

    return ConflictReport(field_id=field.field_id, has_conflict=False)


@dataclass
class FieldCandidate:
    """One independent proposal for a field's value -- e.g. from a retry,
    a second extraction pass, or (future) a per-document extraction step."""

    value: str | None
    confidence: float
    evidence_block_ids: list[str]
    source_label: str = "unknown"


def merge_candidates(
    candidates: list[FieldCandidate],
    field_def: FieldDefinition,
    claim: ClaimState,
) -> ExtractedField:
    """Resolves multiple independent candidates for ONE field into a single
    ExtractedField."""
    field_id = field_def.field_id
    real_candidates = [c for c in candidates if c.value is not None]

    if not real_candidates:
        return ExtractedField(field_id=field_id, status="missing",
                               reason="No candidate proposed a value.")

    is_critical = field_def.field_type in CRITICAL_FIELD_TYPES

    if is_critical:
        normalized_groups: dict[str, list[FieldCandidate]] = {}
        for c in real_candidates:
            key = _normalize_for_grouping(field_def.field_type, c.value)
            normalized_groups.setdefault(key, []).append(c)

        if len(normalized_groups) == 1:
            group = next(iter(normalized_groups.values()))
            best = max(group, key=lambda c: c.confidence)
            all_evidence = sorted({bid for c in group for bid in c.evidence_block_ids})
            return ExtractedField(
                field_id=field_id, value=best.value, confidence=max(c.confidence for c in group),
                evidence_block_ids=all_evidence, status="found",
                reason=f"{len(group)} independent candidate(s) agreed on this value.",
            )

        all_evidence = sorted({bid for c in real_candidates for bid in c.evidence_block_ids})
        distinct_values = sorted({c.value for c in real_candidates})
        logger.warning(
            "Field %r: %d independent candidates DISAGREE on value (%s) -- "
            "marking conflicting, routing to human review.",
            field_id, len(normalized_groups), distinct_values,
        )
        return ExtractedField(
            field_id=field_id, value=None, confidence=0.0,
            evidence_block_ids=all_evidence, status="conflicting",
            reason=(
                f"{len(normalized_groups)} independent candidates disagreed: "
                f"{distinct_values}. A critical field type was not auto-resolved "
                f"by vote/confidence -- requires human review."
            ),
        )

    value_counts = Counter(c.value for c in real_candidates)
    top_value, top_count = value_counts.most_common(1)[0]
    tied_top_values = [v for v, n in value_counts.items() if n == top_count]

    if len(tied_top_values) > 1:
        def avg_conf_for(v):
            return mean(c.confidence for c in real_candidates if c.value == v)
        top_value = max(tied_top_values, key=avg_conf_for)

    winning_candidates = [c for c in real_candidates if c.value == top_value]
    all_evidence = sorted({bid for c in winning_candidates for bid in c.evidence_block_ids})
    return ExtractedField(
        field_id=field_id, value=top_value,
        confidence=max(c.confidence for c in winning_candidates),
        evidence_block_ids=all_evidence,
        status="found" if top_count > 1 else "low_confidence",
        reason=f"Value repeated in {top_count}/{len(real_candidates)} independent candidates.",
    )


def _normalize_for_grouping(field_type: str, value: str) -> str:
    if field_type == "number":
        nums = _extract_numeric_candidates(value)
        return str(nums[0]) if nums else value.strip().lower()
    if field_type == "code":
        import re
        return re.sub(r"\s+", "", value).upper()
    return value.strip().lower()
