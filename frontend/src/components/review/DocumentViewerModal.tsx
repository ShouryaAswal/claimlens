import { useEffect, useState } from "react";
import { ChevronLeft, ChevronRight, FileText, Loader2 } from "lucide-react";

import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { getDocumentPage, type DocumentPageResult } from "@/lib/api";
import { getDocumentById } from "@/lib/claimHelpers";
import { titleCase } from "@/lib/utils";
import { useReviewUiStore } from "@/store/reviewUiStore";
import type { ClaimState } from "@/types/claim";

interface DocumentViewerModalProps {
  claim: ClaimState;
}

/**
 * Renders whichever document is named in reviewUiStore's `documentViewer`
 * state -- opened either from a crop click in EvidenceViewer (with a
 * block to highlight) or from the Documents pane (page 1, no highlight).
 * One shared modal for both entry points on purpose: an adjuster
 * shouldn't get a different viewing experience depending on which button
 * they clicked to get here.
 */
export function DocumentViewerModal({ claim }: DocumentViewerModalProps) {
  const documentViewer = useReviewUiStore((s) => s.documentViewer);
  const closeDocumentViewer = useReviewUiStore((s) => s.closeDocumentViewer);
  const setDocumentViewerPage = useReviewUiStore((s) => s.setDocumentViewerPage);

  const [page, setPage] = useState<DocumentPageResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  const doc = documentViewer ? getDocumentById(claim, documentViewer.docId) : null;
  const canPaginate = doc?.source_format === "pdf" && Boolean(doc.page_count);
  const isRenderable = doc?.source_format === "pdf" || doc?.source_format === "image";

  useEffect(() => {
    if (!documentViewer || !doc || !isRenderable) return;
    let cancelled = false;
    setLoading(true);
    setLoadError(null);
    getDocumentPage(claim.claim_id, documentViewer.docId, documentViewer.page)
      .then((result) => {
        if (cancelled) return;
        setPage((prev) => {
          if (prev) URL.revokeObjectURL(prev.imageUrl);
          return result;
        });
      })
      .catch((err) => {
        if (!cancelled) setLoadError(err instanceof Error ? err.message : "Failed to load page.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [documentViewer?.docId, documentViewer?.page]);

  useEffect(() => {
    return () => {
      if (page) URL.revokeObjectURL(page.imageUrl);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function handleOpenChange(open: boolean) {
    if (!open) {
      closeDocumentViewer();
      setPage(null);
    }
  }

  return (
    <Dialog open={Boolean(documentViewer)} onOpenChange={handleOpenChange}>
      <DialogContent className="max-w-3xl">
        {doc && documentViewer && (
          <>
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <FileText className="h-4 w-4 shrink-0 text-slate-400" />
                <span className="truncate">{doc.source_file.split("/").pop()}</span>
              </DialogTitle>
              <p className="text-xs text-slate-500">
                {doc.doc_type ? titleCase(doc.doc_type) : "Unclassified"} ·{" "}
                {doc.source_format.toUpperCase()}
                {canPaginate && ` · Page ${documentViewer.page} of ${doc.page_count}`}
              </p>
            </DialogHeader>

            {isRenderable ? (
              <div className="flex flex-col gap-3">
                <div className="scrollbar-thin max-h-[65vh] overflow-auto rounded-md border border-slate-200 bg-slate-900/5">
                  {loading && (
                    <div className="flex h-64 items-center justify-center text-slate-400">
                      <Loader2 className="h-5 w-5 animate-spin" />
                    </div>
                  )}
                  {loadError && (
                    <p className="p-6 text-center text-sm text-risk-high">{loadError}</p>
                  )}
                  {!loading && !loadError && page && (
                    <PageImageWithOverlay page={page} highlightBlockId={documentViewer.highlightBlockId} />
                  )}
                </div>

                {canPaginate && (
                  <div className="flex items-center justify-center gap-3">
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={documentViewer.page <= 1}
                      onClick={() => setDocumentViewerPage(documentViewer.page - 1)}
                    >
                      <ChevronLeft className="h-3.5 w-3.5" />
                      Previous
                    </Button>
                    <span className="font-data text-xs text-slate-500">
                      {documentViewer.page} / {doc.page_count}
                    </span>
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={documentViewer.page >= (doc.page_count ?? 1)}
                      onClick={() => setDocumentViewerPage(documentViewer.page + 1)}
                    >
                      Next
                      <ChevronRight className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                )}
              </div>
            ) : (
              <TextBlockList blocks={doc.blocks} highlightBlockId={documentViewer.highlightBlockId} />
            )}

            {doc.warnings.length > 0 && (
              <p className="mt-3 text-xs text-slate-400">{doc.warnings.join(" ")}</p>
            )}
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}

/** No Y-flip, no transform -- bbox_px from the API is already in the
 * same top-left-origin pixel space as the rendered PNG. */
function PageImageWithOverlay({
  page,
  highlightBlockId,
}: {
  page: DocumentPageResult;
  highlightBlockId: string | undefined;
}) {
  const [naturalSize, setNaturalSize] = useState<{ width: number; height: number } | null>(null);

  return (
    <div className="relative inline-block">
      <img
        src={page.imageUrl}
        alt="Document page"
        onLoad={(e) =>
          setNaturalSize({ width: e.currentTarget.naturalWidth, height: e.currentTarget.naturalHeight })
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
  );
}

/** Fallback for DOCX/PPTX/HTML docs, which have no fixed page to render --
 * the highlighted block gets a gold outline so a crop click still lands
 * somewhere meaningful even without a pixel-space overlay. */
function TextBlockList({
  blocks,
  highlightBlockId,
}: {
  blocks: ClaimState["documents"][number]["blocks"];
  highlightBlockId: string | undefined;
}) {
  return (
    <div className="scrollbar-thin flex max-h-[60vh] flex-col gap-2 overflow-y-auto rounded-md border border-slate-200 bg-slate-50 p-3">
      {blocks.length === 0 && (
        <p className="p-4 text-center text-sm text-slate-400">
          No extractable text blocks in this document.
        </p>
      )}
      {blocks.map((block) => (
        <p
          key={block.block_id}
          className={
            block.block_id === highlightBlockId
              ? "rounded-md border-l-2 border-gold-500 bg-gold-500/10 px-3 py-2 text-sm text-ink-950"
              : "px-3 py-2 text-sm text-slate-600"
          }
        >
          {block.text}
        </p>
      ))}
    </div>
  );
}
