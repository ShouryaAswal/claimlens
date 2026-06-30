"""
scripts/run_sprint4_demo.py
-------------------------------
The full Sprint 0-4 pipeline, end to end: ingest -> classify -> resolve
schema -> tag doc types -> Gate Check -> (extraction) -> evidence
verification + confidence rating -> crop generation -> triage ->
human review queue -> reviewer summary.

Run: python3 scripts/run_sprint4_demo.py

Loads .env automatically (core/env.py) -- if GROQ_API_KEY/GOOGLE_API_KEY
are set there or in your shell, real extraction and an LLM-written summary
run for real. Without any key, this demo plants the same deliberate
single-digit error as the Sprint 3 demo, so you can watch the triage
agent's forced_review override and the reviewer summary's explicit callout
of it, end to end, without needing an API key at all.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from agents.confidence_rating import rate_all_fields
from agents.doc_type_tagger_agent import tag_all_documents
from agents.gate_check import apply_gate_check_to_claim
from agents.human_review_queue import build_review_queue, summarize_review_queue
from agents.ingestion.dispatcher import ingest_claim_folder
from agents.lob_classifier_agent import classify_lob
from agents.provenance_agent import generate_crops_for_claim
from agents.reviewer_summary_agent import generate_reviewer_summary
from agents.section_extraction_agent import extract_claim
from agents.triage_agent import apply_triage_to_claim
from core.config import OUTPUTS_DIR, SAMPLES_DIR
from core.llm_client import LLMNotConfiguredError, get_llm_client
from core.schema_loader import load_lob_schema
from core.schemas import ClaimState, ExtractedField


def main() -> None:
    claim_folder = SAMPLES_DIR / "example_claim_folder" / "CLM-2026-04821"
    print(f"=== ClaimLens Sprint 0-4 pipeline ===\nClaim folder: {claim_folder}\n")

    documents = ingest_claim_folder(str(claim_folder))
    full_text = "\n".join(d.full_text for d in documents)

    groq_client = get_llm_client("groq")
    gemini_client = get_llm_client("gemini")
    llm_client = groq_client or gemini_client
    print(f"[1] Ingestion: {len(documents)} documents. LLM configured: "
          f"{'yes (' + llm_client.provider + ')' if llm_client else 'no -- rule-based/demo mode'}")

    lob, lob_confidence = classify_lob(full_text, llm_client=groq_client)
    schema = load_lob_schema(lob)
    tag_all_documents(documents, llm_client=groq_client)
    claim = ClaimState(claim_id=f"CLM-{uuid.uuid4().hex[:8]}", lob=lob, lob_schema=schema, documents=documents)
    apply_gate_check_to_claim(claim)
    print(f"[2] LOB={lob.value} (confidence {lob_confidence:.2f}); "
          f"missing mandatory docs: {claim.missing_mandatory_docs or 'none'}")

    if gemini_client is not None:
        try:
            extract_claim(claim, llm_client=gemini_client)
            print("[3] Real section extraction completed via Gemini.")
        except LLMNotConfiguredError as exc:
            print(f"[3] {exc}")
    else:
        print("[3] No GOOGLE_API_KEY configured -- injecting a demo extraction result instead")
        print("    (one correct field, one with a deliberately wrong digit).")
        policy_block = next((b for d in documents for b in d.blocks if "AUTO-2026" in b.text), None)
        if policy_block is not None:
            claim.extracted_fields["policy_number"] = ExtractedField(
                field_id="policy_number", value="AUTO-2026-00981", confidence=0.95,
                status="found", evidence_block_ids=[policy_block.block_id],
            )
        estimate_block = next((b for d in documents for b in d.blocks if "4,250" in b.text or "4250" in b.text), None)
        if estimate_block is not None:
            claim.extracted_fields["repair_estimate_amount"] = ExtractedField(
                field_id="repair_estimate_amount", value="4259.00", confidence=0.93,  # deliberately wrong
                status="found", evidence_block_ids=[estimate_block.block_id],
            )

    rate_all_fields(claim, llm_client=groq_client)
    crop_dir = OUTPUTS_DIR / "crops" / claim.claim_id
    generate_crops_for_claim(claim, crop_dir)
    print(f"[4] Evidence verification complete. Crops in {crop_dir}")

    triage_verdict = apply_triage_to_claim(claim)
    print(f"\n[5] TRIAGE VERDICT: {triage_verdict.tier.value.upper()} "
          f"(score={triage_verdict.score}, forced_review={triage_verdict.forced_review})")
    for reason in triage_verdict.reasons:
        print(f"      - {reason}")

    review_queue = build_review_queue(claim)
    summary_counts = summarize_review_queue(review_queue)
    print(f"\n[6] Human review queue: {summary_counts}")
    for item in review_queue:
        print(f"      [{item.risk_level.value.upper()}] {item.field_label} = {item.value!r}")
        if item.crop_paths:
            print(f"          crop: {item.crop_paths[0]}")

    summary = generate_reviewer_summary(claim, review_queue, llm_client=groq_client)
    print("\n[7] REVIEWER SUMMARY")
    print("-" * 60)
    print(summary)
    print("-" * 60)


if __name__ == "__main__":
    main()
