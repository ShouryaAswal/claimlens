import { useEffect, useState } from "react";
import { ChevronLeft, ChevronRight, FileImage, Maximize2, Quote } from "lucide-react";

import { Button } from "@/components/ui/button";
import { getDocumentPage, resolveAssetUrl, type DocumentPageResult } from "@/lib/api";
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

  const [fullPage, setFullPage] = useState<DocumentPageResult | null>(null);
  const [fullPageLoading, setFullPageLoading] = useState(false);

  const evidenceBlockIds = field?.evidence_block_ids ?? [];
  const evidenceCount = evidenceBlockIds.length;
  const activeBlockId = evidenceBlockIds[activeEvidenceIndex];

  // Reset the full-page view whenever the selected field/evidence changes,
  // revoking the previous object URL so blob URLs don't accumulate.
  useEffect(() => {
    return () => {
      if (fullPage) URL.revokeObjectURL(fullPage.imageUrl);
    };
  }, [fullPage]);

  useEffect(() => {
    setFullPage(null);
  }, [field?.field_id, activeEvidenceIndex]);

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

  async function handleShowFullPage() {
    if (!document || !block?.page) return;
    setFullPageLoading(true);
    try {
      const result = await getDocumentPage(claim.claim_id, document.doc_id, block.page);
      setFullPage(result);
    } finally {
      setFullPageLoading(false);
    }
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
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7"
              onClick={() => previousEvidence(evidenceCount)}
              aria-label="Previous evidence"
            >
              <ChevronLeft className="h-4 w-4" />
            </Button>
            <span className="font-data">
              {activeEvidenceIndex + 1} of {evidenceCount}
            </span>
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7"
              onClick={() => nextEvidence(evidenceCount)}
              aria-label="Next evidence"
            >
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        )}
      </div>

      <div className="scrollbar-thin flex-1 overflow-auto p-4">
        {fullPage ? (
          <FullPageWithOverlay page={fullPage} highlightBlockId={activeBlockId} />
        ) : cropUrl ? (
          <div className="flex flex-col gap-3">
            <div className="overflow-hidden rounded-md border border-slate-200 bg-slate-100">
              <img
                src={resolveAssetUrl(cropUrl)}
                alt={`Evidence for ${field.field_id}`}
                className="w-full object-contain"
              />
            </div>
            {canShowFullPage && (
              <Button
                variant="outline"
                size="sm"
                onClick={handleShowFullPage}
                disabled={fullPageLoading}
                className="w-fit"
              >
                <Maximize2 className="h-3.5 w-3.5" />
                {fullPageLoading ? "Loading page…" : "View in full page context"}
              </Button>
            )}
          </div>
        ) : block ? (
          <NoVisualEvidence block={block} />
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
function NoVisualEvidence({ block }: { block: { locator: string; text: string; source_format: string } }) {
  return (
    <div className="rounded-md border border-slate-200 bg-slate-50 p-4">
      <p className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-400">
        No visual evidence available &middot; {block.source_format.toUpperCase()} &middot; {block.locator}
      </p>
      <blockquote className="border-l-2 border-gold-500 pl-3 text-sm italic text-ink-900">
        "{block.text}"
      </blockquote>
    </div>
  );
}

/**
 * Draws the backend-provided pixel bbox directly onto the rendered page
 * image. Per the locked design decision, there is NO Y-flip or transform
 * here -- bbox_px is already in the same top-left-origin pixel space as
 * the PNG. If a box looks wrong, the bug is in
 * app/routers/documents.py's pixel math, not in this component.
 */
function FullPageWithOverlay({
  page,
  highlightBlockId,
}: {
  page: DocumentPageResult;
  highlightBlockId: string | undefined;
}) {
  const [naturalSize, setNaturalSize] = useState<{ width: number; height: number } | null>(null);

  return (
    <div className="overflow-auto rounded-md border border-slate-200 bg-slate-900/5">
      <div className="relative inline-block">
        <img
          src={page.imageUrl}
          alt="Full page"
          onLoad={(e) =>
            setNaturalSize({
              width: e.currentTarget.naturalWidth,
              height: e.currentTarget.naturalHeight,
            })
          }
          className="block max-w-none"
        />
        {naturalSize && (
          <svg
            viewBox={`0 0 ${naturalSize.width} ${naturalSize.height}`}
            className="pointer-events-none absolute inset-0 h-full w-full"
          >
            {page.blocks.map((b) => {
              const [x0, y0, x1, y1] = b.bbox_px;
              const isActive = b.block_id === highlightBlockId;
              return (
                <rect
                  key={b.block_id}
                  x={x0}
                  y={y0}
                  width={x1 - x0}
                  height={y1 - y0}
                  fill={isActive ? "rgba(201, 154, 62, 0.18)" : "transparent"}
                  stroke={isActive ? "#C99A3E" : "rgba(107, 122, 148, 0.35)"}
                  strokeWidth={isActive ? 3 : 1}
                />
              );
            })}
          </svg>
        )}
      </div>
    </div>
  );
}
