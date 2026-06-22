"""
agents/gate_check.py
------------------------
Stage 1c of Sprint 2: Gate Check. Compares the doc_types actually tagged
across a claim's documents against the resolved LOBSchema's
`mandatory_doc_types`, and reports exactly what's missing.

Deliberately NOT an LLM call -- this is a set-difference, and the whole
point of the Schema Resolution design (see design doc, section 2) was that
once you know the LOB, you already know what's required. There's nothing
for a model to decide here.

Must run AFTER agents.doc_type_tagger_agent.tag_all_documents() has set
`doc_type` on each DocumentRecord -- an untagged document (doc_type is
None) is treated as not satisfying any mandatory type, same as "unknown".
"""

from __future__ import annotations

from dataclasses import dataclass, field

from core.schemas import ClaimState, DocumentRecord, LOBSchema


@dataclass
class GateCheckResult:
    is_complete: bool
    present_doc_types: set[str]
    missing_doc_types: list[str]
    mandatory_doc_types: list[str]
    unmatched_documents: list[str] = field(default_factory=list)  # source_files tagged "unknown"/None


def run_gate_check(documents: list[DocumentRecord], schema: LOBSchema) -> GateCheckResult:
    present = {d.doc_type for d in documents if d.doc_type and d.doc_type != "unknown"}
    missing = [dt for dt in schema.mandatory_doc_types if dt not in present]
    unmatched = [d.source_file for d in documents if not d.doc_type or d.doc_type == "unknown"]

    return GateCheckResult(
        is_complete=(len(missing) == 0),
        present_doc_types=present,
        missing_doc_types=missing,
        mandatory_doc_types=list(schema.mandatory_doc_types),
        unmatched_documents=unmatched,
    )


def apply_gate_check_to_claim(claim: ClaimState) -> GateCheckResult:
    """Convenience wrapper that also writes the result back onto
    ClaimState.missing_mandatory_docs, matching the field already
    scaffolded there in Sprint 0."""
    if claim.lob_schema is None:
        raise ValueError(
            f"ClaimState {claim.claim_id!r} has no lob_schema resolved yet -- "
            f"run LOB classification + core.schema_loader.load_lob_schema() first."
        )
    result = run_gate_check(claim.documents, claim.lob_schema)
    claim.missing_mandatory_docs = result.missing_doc_types
    return result
