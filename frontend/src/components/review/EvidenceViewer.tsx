import { useEffect } from "react";
import { ChevronLeft, ChevronRight, FileImage, Maximize2, Quote } from "lucide-react";

import { resolveAssetUrl } from "@/lib/api";
import { findContentBlock, findCropForBlock, findDocumentForBlock } from "@/lib/claimHelpers";
import { useReviewUiStore } from "@/store/reviewUiStore";
import type { ClaimState, ExtractedField, FieldVerification } from "@/types/claim";

interface EvidenceViewerProps {
  claim: ClaimState;
  field: ExtractedField | undefined;
  verification: FieldVerification | undefined;
}

export function EvidenceViewer({ claim, field, verification }: EvidenceViewerProps) {
  const activeEvidenceIndex = useReviewUiStore((s) => s.activeEvidenceIndex);
  const nextEvidence = useReviewUiStore((s) => s.nextEvidence);
  const previousEvidence = useReviewUiStore((s) => s.previousEvidence);
  const openDocumentViewer = useReviewUiStore((s) => s.openDocumentViewer);
  const setActiveEvidenceIndex = useReviewUiStore((s) => s.setActiveEvidenceIndex);

  const evidenceBlockIds = field?.evidence_block_ids ?? [];
  const evidenceCount = evidenceBlockIds.length;
  const activeBlockId = evidenceBlockIds[activeEvidenceIndex];

  // Selecting a new field always starts at its first piece of evidence.
  useEffect(() => {
    setActiveEvidenceIndex(0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [field?.field_id]);

  if (!field) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-2 p-8 text-center text-slate-400">
        <FileImage className="h-8 w-8" />
        <p className="text-sm">Select a field to review its evidence.</p>
      </div>
    );
  }

  if (evidenceCount === 0) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-2 p-8 text-center text-slate-400">
        <Quote className="h-8 w-8" />
        <p className="text-sm">
          {field.status === "missing"
            ? "No evidence was cited -- this field was not found in any document."
            : "No evidence blocks are linked to this field."}
        </p>
      </div>
    );
  }

  const block = activeBlockId ? findContentBlock(claim, activeBlockId) : null;
  const document = activeBlockId ? findDocumentForBlock(claim, activeBlockId) : null;
  const cropUrl =
    activeBlockId && verification
      ? findCropForBlock(verification.crop_paths, activeBlockId)
      : null;

  const canShowFullPage = Boolean(
    document && block?.page && (document.source_format === "pdf" || document.source_format === "image"),
  );

  function handleShowFullPage() {
    if (!document || !block?.page || !activeBlockId) return;
    openDocumentViewer(document.doc_id, block.page, activeBlockId);
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b border-slate-200 px-4 py-3">
        <div className="min-w-0">
          <h2 className="truncate text-sm font-semibold text-ink-950">Evidence</h2>
          <p className="truncate text-xs text-slate-500">{document?.source_file ?? block?.locator}</p>
        </div>
        {evidenceCount > 1 && (
          <div className="flex items-center gap-1 text-xs text-slate-500">
            <button
              type="button"
              className="flex h-7 w-7 items-center justify-center rounded-md text-slate-500 hover:bg-slate-100"
              onClick={() => previousEvidence(evidenceCount)}
              aria-label="Previous evidence"
            >
              <ChevronLeft className="h-4 w-4" />
            </button>
            <span className="font-data">
              {activeEvidenceIndex + 1} of {evidenceCount}
            </span>
            <button
              type="button"
              className="flex h-7 w-7 items-center justify-center rounded-md text-slate-500 hover:bg-slate-100"
              onClick={() => nextEvidence(evidenceCount)}
              aria-label="Next evidence"
            >
              <ChevronRight className="h-4 w-4" />
            </button>
          </div>
        )}
      </div>

      <div className="scrollbar-thin flex-1 overflow-auto p-4">
        {cropUrl ? (
          <div className="flex flex-col gap-3">
            <button
              type="button"
              onClick={canShowFullPage ? handleShowFullPage : undefined}
              className="group relative overflow-hidden rounded-md border border-slate-200 bg-slate-100 text-left disabled:cursor-default"
              disabled={!canShowFullPage}
              title={canShowFullPage ? "Click to view in the original document" : undefined}
            >
              <img
                src={resolveAssetUrl(cropUrl)}
                alt={`Evidence for ${field.field_id}`}
                className="w-full object-contain"
              />
              {canShowFullPage && (
                <span className="absolute inset-0 flex items-center justify-center bg-ink-950/0 opacity-0 transition-all group-hover:bg-ink-950/40 group-hover:opacity-100">
                  <span className="flex items-center gap-1.5 rounded-md bg-white px-3 py-1.5 text-xs font-medium text-ink-950 shadow-panel">
                    <Maximize2 className="h-3.5 w-3.5" />
                    View in document
                  </span>
                </span>
              )}
            </button>
          </div>
        ) : block ? (
          <NoVisualEvidence
            block={block}
            onOpenSourceDocument={canShowFullPage ? handleShowFullPage : undefined}
          />
        ) : (
          <p className="text-sm text-slate-400">Evidence block not found.</p>
        )}
      </div>
    </div>
  );
}

/**
 * DOCX/PPTX/HTML-sourced fields have no fixed (x, y) bbox -- provenance
 * degrades gracefully to a locator string + the cited block's raw text
 * rather than inventing a coordinate. This is an expected, real case
 * (Sprint 1), not a fallback for a bug.
 */
function NoVisualEvidence({
  block,
  onOpenSourceDocument,
}: {
  block: { locator: string; text: string; source_format: string };
  onOpenSourceDocument?: () => void;
}) {
  return (
    <div className="rounded-md border border-slate-200 bg-slate-50 p-4">
      <p className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-400">
        No visual evidence available &middot; {block.source_format.toUpperCase()} &middot; {block.locator}
      </p>
      <blockquote className="border-l-2 border-gold-500 pl-3 text-sm italic text-ink-900">
        "{block.text}"
      </blockquote>
      {onOpenSourceDocument && (
        <button
          type="button"
          onClick={onOpenSourceDocument}
          className="mt-3 text-xs font-medium text-ink-800 underline underline-offset-2"
        >
          View source document
        </button>
      )}
    </div>
  );
}
