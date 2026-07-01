"""
scripts/run_sprint3_demo.py
-------------------------------
End-to-end Sprint 0-3 demo: ingest -> classify -> resolve schema -> tag doc
types -> Gate Check -> (extraction, if an LLM key is configured) ->
evidence verification + confidence rating -> crop generation -> human
review queue.

Run: python3 scripts/run_sprint3_demo.py

To see the full pipeline including extraction and the LLM second-opinion
check, set GROQ_API_KEY or GOOGLE_API_KEY first. Without a key, this demo
manually injects a couple of ExtractedFields (one correct, one with a
deliberately wrong digit) so the verification/rating/review-queue stages
can still be demonstrated end-to-end -- exactly the property this round's
work is supposed to guarantee.
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
from agents.section_extraction_agent import extract_claim
from core.config import OUTPUTS_DIR, SAMPLES_DIR
from core.llm_client import LLMNotConfiguredError, get_llm_client
from core.schema_loader import load_lob_schema
from core.schemas import ClaimState, ExtractedField


def main() -> None:
    claim_folder = SAMPLES_DIR / "example_claim_folder" / "CLM-2026-04821"
    print(f"--- Ingesting claim folder: {claim_folder} ---")
    documents = ingest_claim_folder(str(claim_folder))
    full_text = "\n".join(d.full_text for d in documents)

    lob, confidence = classify_lob(full_text)
    schema = load_lob_schema(lob)
    tag_all_documents(documents)
    claim = ClaimState(claim_id=f"CLM-{uuid.uuid4().hex[:8]}", lob=lob, lob_schema=schema, documents=documents)
    apply_gate_check_to_claim(claim)
    print(f"LOB={lob.value} (confidence {confidence:.2f}), schema resolved, "
          f"{len(documents)} documents tagged, missing mandatory docs: {claim.missing_mandatory_docs}")

    llm_client = get_llm_client("groq") or get_llm_client("gemini")
    if llm_client is not None:
        print("\n--- Real LLM key detected: running real section extraction ---")
        try:
            extract_claim(claim, llm_client=llm_client)
        except LLMNotConfiguredError as exc:
            print(f"  {exc}")
    else:
        print("\n--- No LLM key configured: injecting a demo extraction result instead ---")
        print("    (one correct field, one with a deliberately wrong digit -- proving")
        print("     the verification stage actually catches it, not just trusts it)")
        policy_block = next(
            (b for d in documents for b in d.blocks if "AUTO-2026" in b.text), None
        )
        if policy_block is not None:
            claim.extracted_fields["policy_number"] = ExtractedField(
                field_id="policy_number", value="AUTO-2026-00981", confidence=0.95,
                status="found", evidence_block_ids=[policy_block.block_id],
            )
        estimate_block = next(
            (b for d in documents for b in d.blocks if "4,250" in b.text or "4250" in b.text), None
        )
        if estimate_block is not None:
            # Deliberately wrong: real text says 4,250.00; we claim 4,259.00.
            claim.extracted_fields["repair_estimate_amount"] = ExtractedField(
                field_id="repair_estimate_amount", value="4259.00", confidence=0.93,
                status="found", evidence_block_ids=[estimate_block.block_id],
            )

    print("\n--- Evidence verification + confidence rating ---")
    verifications = rate_all_fields(claim)
    for field_id, v in verifications.items():
        print(f"  {field_id:30s} risk={v.risk_level.value:12s} match={v.match_method.value:14s} "
              f"score={v.match_score:.2f} composite={v.composite_confidence:.2f}")
        for reason in v.reasons:
            print(f"      - {reason}")

    print("\n--- Provenance crop generation ---")
    crop_dir = OUTPUTS_DIR / "crops" / claim.claim_id
    crop_paths = generate_crops_for_claim(claim, crop_dir)
    print(f"  Generated {len(crop_paths)} crop(s) in {crop_dir}")

    print("\n--- Human review queue ---")
    queue = build_review_queue(claim)
    summary = summarize_review_queue(queue)
    print(f"  Summary: {summary}")
    for item in queue:
        print(f"  [{item.risk_level.value.upper()}] {item.field_label} = {item.value!r}")
        for reason in item.reasons:
            print(f"      - {reason}")
        if item.crop_paths:
            print(f"      crop(s): {item.crop_paths}")


if __name__ == "__main__":
    main()
