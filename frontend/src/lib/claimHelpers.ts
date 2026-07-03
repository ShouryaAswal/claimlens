import type { ClaimState, ContentBlock, DocumentRecord } from "@/types/claim";

export function getDocumentById(claim: ClaimState, docId: string): DocumentRecord | null {
  return claim.documents.find((doc) => doc.doc_id === docId) ?? null;
}

export function findContentBlock(claim: ClaimState, blockId: string): ContentBlock | null {
  for (const doc of claim.documents) {
    const block = doc.blocks.find((b) => b.block_id === blockId);
    if (block) return block;
  }
  return null;
}

export function findDocumentForBlock(claim: ClaimState, blockId: string): DocumentRecord | null {
  return claim.documents.find((doc) => doc.blocks.some((b) => b.block_id === blockId)) ?? null;
}

/**
 * crop_paths are server-rewritten URLs shaped like
 * `/crops/{claim_id}/{block_id}.png` (see core/pipeline.py's
 * _rewrite_crop_paths_to_urls). Matching by filename rather than by
 * array index is deliberate: a field's evidence_block_ids can outnumber
 * its crop_paths whenever some cited blocks have no pixel-space bbox
 * (DOCX/PPTX/HTML paragraphs), so index-aligning the two lists would
 * silently pair the wrong crop with the wrong block.
 */
export function findCropForBlock(cropPaths: string[], blockId: string): string | null {
  return cropPaths.find((path) => path.endsWith(`/${blockId}.png`)) ?? null;
}
