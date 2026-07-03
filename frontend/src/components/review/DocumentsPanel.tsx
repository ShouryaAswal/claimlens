import { AlertTriangle, File, FileImage, FileText, Layers } from "lucide-react";

import { titleCase } from "@/lib/utils";
import { useReviewUiStore } from "@/store/reviewUiStore";
import type { ClaimState, DocumentRecord, SourceFormat } from "@/types/claim";

interface DocumentsPanelProps {
  claim: ClaimState;
}

const FORMAT_ICON: Record<SourceFormat, typeof FileText> = {
  pdf: FileText,
  image: FileImage,
  docx: FileText,
  pptx: Layers,
  html: FileText,
};

/**
 * Every document ClaimLens ingested for this claim, alongside what the
 * classifier tagged it as (doc_type_tagger_agent.py's output, or
 * "Unclassified" for the DocType.UNKNOWN case). Deliberately shows
 * EVERY document, including ones that failed to ingest (warnings
 * non-empty, doc_type null) -- an adjuster needs to see that a file was
 * uploaded but rejected, not have it silently vanish.
 */
export function DocumentsPanel({ claim }: DocumentsPanelProps) {
  const openDocumentViewer = useReviewUiStore((s) => s.openDocumentViewer);

  if (claim.documents.length === 0) {
    return (
      <div className="flex h-full items-center justify-center p-6 text-center text-sm text-slate-500">
        No documents on this claim.
      </div>
    );
  }

  const isMandatory = (doc: DocumentRecord) =>
    Boolean(doc.doc_type && claim.lob_schema?.mandatory_doc_types.includes(doc.doc_type));

  return (
    <div className="scrollbar-thin flex h-full flex-col overflow-y-auto">
      <div className="border-b border-slate-200 px-4 py-3">
        <h2 className="text-sm font-semibold text-ink-950">Documents</h2>
        <p className="text-xs text-slate-500">
          {claim.documents.length} file{claim.documents.length === 1 ? "" : "s"} uploaded
        </p>
      </div>

      {claim.missing_mandatory_docs.length > 0 && (
        <div className="mx-4 mt-3 flex items-start gap-2 rounded-md border border-gold-500/40 bg-gold-500/10 p-3 text-xs text-ink-900">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-gold-600" />
          <span>
            Missing mandatory document{claim.missing_mandatory_docs.length === 1 ? "" : "s"}:{" "}
            {claim.missing_mandatory_docs.map(titleCase).join(", ")}
          </span>
        </div>
      )}

      <ul className="flex flex-col gap-1.5 p-4">
        {claim.documents.map((doc) => {
          const failed = doc.warnings.some((w) => w.startsWith("INGESTION FAILED"));
          const Icon = failed ? File : FORMAT_ICON[doc.source_format] ?? File;
          const canOpen = doc.source_format === "pdf" || doc.source_format === "image";

          return (
            <li key={doc.doc_id}>
              <button
                type="button"
                onClick={() => openDocumentViewer(doc.doc_id, 1)}
                className="flex w-full items-start gap-3 rounded-md border border-slate-200 px-3 py-2.5 text-left transition-colors hover:border-ink-700 hover:bg-slate-50"
              >
                <Icon
                  className={
                    failed ? "mt-0.5 h-4 w-4 shrink-0 text-risk-high" : "mt-0.5 h-4 w-4 shrink-0 text-slate-400"
                  }
                />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-ink-950">
                    {doc.source_file.split("/").pop()}
                  </p>
                  <div className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-slate-500">
                    <span
                      className={
                        isMandatory(doc)
                          ? "rounded-full bg-gold-500/15 px-1.5 py-0.5 font-medium text-gold-700"
                          : "rounded-full bg-slate-100 px-1.5 py-0.5"
                      }
                    >
                      {doc.doc_type ? titleCase(doc.doc_type) : "Unclassified"}
                    </span>
                    <span className="uppercase">{doc.source_format}</span>
                    {doc.page_count && <span>{doc.page_count} pages</span>}
                    {!canOpen && <span className="italic">Text view only</span>}
                  </div>
                  {failed && (
                    <p className="mt-1 text-xs text-risk-high">{doc.warnings.join(" ")}</p>
                  )}
                </div>
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
