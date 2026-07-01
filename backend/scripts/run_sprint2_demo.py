"""
scripts/run_sprint2_demo.py
-------------------------------
End-to-end Sprint 2 demo: ingest -> classify LOB -> resolve schema ->
tag doc types -> Gate Check -> (extraction, if an LLM key is configured).

Run: python3 scripts/run_sprint2_demo.py
Optional: set GROQ_API_KEY or GOOGLE_API_KEY first to also run real
section extraction; without a key, the demo stops after Gate Check and
explains why.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from agents.doc_type_tagger_agent import tag_all_documents
from agents.gate_check import apply_gate_check_to_claim
from agents.ingestion.dispatcher import ingest_claim_folder
from agents.lob_classifier_agent import classify_lob
from agents.section_extraction_agent import extract_claim
from core.config import SAMPLES_DIR
from core.llm_client import LLMNotConfiguredError, get_llm_client
from core.schema_loader import load_lob_schema
from core.schemas import ClaimState


def main() -> None:
    claim_folder = SAMPLES_DIR / "example_claim_folder" / "CLM-2026-04821"
    print(f"--- Ingesting claim folder: {claim_folder} ---")
    documents = ingest_claim_folder(str(claim_folder))
    for d in documents:
        print(f"  {Path(d.source_file).name:35s} format={d.source_format.value:6s} blocks={d.block_count}")

    full_text = "\n".join(d.full_text for d in documents)
    print("\n--- Stage 1: LOB classification (rule-based, no API key needed) ---")
    lob, confidence = classify_lob(full_text)
    print(f"  LOB = {lob.value}  (confidence {confidence:.2f})")

    print("\n--- Stage 2: Schema resolution (deterministic lookup) ---")
    schema = load_lob_schema(lob) if lob.value != "unknown" else None
    if schema is None:
        print("  Could not resolve a schema (LOB unknown). Stopping here.")
        return
    print(f"  Resolved schema: {schema.source_concept[:70]}...")
    print(f"  {len(schema.sections)} sections, {len(schema.all_fields)} total fields, "
          f"{len(schema.mandatory_doc_types)} mandatory doc types: {schema.mandatory_doc_types}")

    print("\n--- Stage 3: Document-type tagging (rule-based) ---")
    tag_all_documents(documents)
    for d in documents:
        print(f"  {Path(d.source_file).name:35s} -> {d.doc_type}")

    print("\n--- Stage 4: Gate Check (deterministic) ---")
    claim = ClaimState(claim_id=f"CLM-{uuid.uuid4().hex[:8]}", lob=lob, lob_schema=schema, documents=documents)
    gate_result = apply_gate_check_to_claim(claim)
    print(f"  Complete: {gate_result.is_complete}")
    print(f"  Present doc types: {sorted(gate_result.present_doc_types)}")
    print(f"  Missing mandatory doc types: {gate_result.missing_doc_types}")

    print("\n--- Stage 5: Section extraction ---")
    llm_client = get_llm_client("groq") or get_llm_client("gemini")
    if llm_client is None:
        print("  No GROQ_API_KEY or GOOGLE_API_KEY configured in this environment.")
        print("  This is expected in a sandbox with no outbound access to those APIs.")
        print("  Set one of those env vars on a machine with normal internet access")
        print("  to run real extraction -- see SPRINT_2_NOTES.md for exact steps.")
        return

    try:
        extract_claim(claim, llm_client=llm_client)
    except LLMNotConfiguredError as exc:
        print(f"  {exc}")
        return

    for field_id, extracted in claim.extracted_fields.items():
        print(f"  {field_id:30s} status={extracted.status:14s} value={extracted.value}")


if __name__ == "__main__":
    main()
