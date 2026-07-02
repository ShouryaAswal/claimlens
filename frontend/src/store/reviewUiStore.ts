import { create } from "zustand";

/**
 * UI-local state for the ClaimReview page ONLY: which field is selected
 * and which evidence block is active in the viewer. Claim data,
 * extracted_fields, verifications, etc. all live in TanStack Query's
 * cache (see hooks/useClaim.ts) -- if you find yourself wanting to put
 * server data in here, stop, that's what the query cache is for.
 */
interface ReviewUiState {
  selectedFieldId: string | null;
  /** Index into the selected field's evidence_block_ids. */
  activeEvidenceIndex: number;
  overrideModalFieldId: string | null;

  selectField: (fieldId: string | null) => void;
  setActiveEvidenceIndex: (index: number) => void;
  nextEvidence: (evidenceCount: number) => void;
  previousEvidence: (evidenceCount: number) => void;
  openOverrideModal: (fieldId: string) => void;
  closeOverrideModal: () => void;
}

export const useReviewUiStore = create<ReviewUiState>((set) => ({
  selectedFieldId: null,
  activeEvidenceIndex: 0,
  overrideModalFieldId: null,

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
}));
