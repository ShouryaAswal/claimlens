import { create } from "zustand";

/**
 * UI-local state for the ClaimReview page ONLY: which field is selected
 * and which evidence block is active in the viewer. Claim data,
 * extracted_fields, verifications, etc. all live in TanStack Query's
 * cache (see hooks/useClaim.ts) -- if you find yourself wanting to put
 * server data in here, stop, that's what the query cache is for.
 */
interface DocumentViewerState {
  docId: string;
  page: number;
  /** Block to highlight in gold when the page renders -- set when opened
   * from a crop click; absent when opened from the Documents pane. */
  highlightBlockId?: string;
}

interface ReviewUiState {
  selectedFieldId: string | null;
  /** Index into the selected field's evidence_block_ids. */
  activeEvidenceIndex: number;
  overrideModalFieldId: string | null;
  documentViewer: DocumentViewerState | null;
  activeTab: "fields" | "documents";

  selectField: (fieldId: string | null) => void;
  setActiveEvidenceIndex: (index: number) => void;
  nextEvidence: (evidenceCount: number) => void;
  previousEvidence: (evidenceCount: number) => void;
  openOverrideModal: (fieldId: string) => void;
  closeOverrideModal: () => void;
  openDocumentViewer: (docId: string, page: number, highlightBlockId?: string) => void;
  setDocumentViewerPage: (page: number) => void;
  closeDocumentViewer: () => void;
  setActiveTab: (tab: "fields" | "documents") => void;
}

export const useReviewUiStore = create<ReviewUiState>((set) => ({
  selectedFieldId: null,
  activeEvidenceIndex: 0,
  overrideModalFieldId: null,
  documentViewer: null,
  activeTab: "fields",

  selectField: (fieldId) => set({ selectedFieldId: fieldId, activeEvidenceIndex: 0 }),

  setActiveEvidenceIndex: (index) => set({ activeEvidenceIndex: index }),

  nextEvidence: (evidenceCount) =>
    set((state) => ({
      activeEvidenceIndex:
        evidenceCount === 0 ? 0 : (state.activeEvidenceIndex + 1) % evidenceCount,
    })),

  previousEvidence: (evidenceCount) =>
    set((state) => ({
      activeEvidenceIndex:
        evidenceCount === 0
          ? 0
          : (state.activeEvidenceIndex - 1 + evidenceCount) % evidenceCount,
    })),

  openOverrideModal: (fieldId) => set({ overrideModalFieldId: fieldId }),
  closeOverrideModal: () => set({ overrideModalFieldId: null }),

  openDocumentViewer: (docId, page, highlightBlockId) =>
    set({ documentViewer: { docId, page, highlightBlockId } }),
  setDocumentViewerPage: (page) =>
    set((state) =>
      state.documentViewer ? { documentViewer: { ...state.documentViewer, page } } : {},
    ),
  closeDocumentViewer: () => set({ documentViewer: null }),

  setActiveTab: (tab) => set({ activeTab: tab }),
}));
