import { useParams } from "react-router-dom";
import { AlertCircle, Loader2, PencilLine } from "lucide-react";

import { Button } from "@/components/ui/button";
import { EvidenceViewer } from "@/components/review/EvidenceViewer";
import { FieldsPanel } from "@/components/review/FieldsPanel";
import { OverrideModal } from "@/components/review/OverrideModal";
import { SummaryPanel } from "@/components/review/SummaryPanel";
import { TriagePanel } from "@/components/review/TriagePanel";
import { TierBadge } from "@/components/shared/TierBadge";
import { useClaim } from "@/hooks/useClaim";
import { useReviewUiStore } from "@/store/reviewUiStore";

export default function ClaimReview() {
  const { claimId } = useParams<{ claimId: string }>();
  const { data: record, isLoading, isError, error } = useClaim(claimId);

  const selectedFieldId = useReviewUiStore((s) => s.selectedFieldId);
  const openOverrideModal = useReviewUiStore((s) => s.openOverrideModal);

  if (isLoading) {
    return (
      <div className="flex h-screen items-center justify-center gap-2 text-slate-500">
        <Loader2 className="h-5 w-5 animate-spin" />
        Loading claim…
      </div>
    );
  }

  if (isError || !record) {
    return (
      <div className="flex h-screen flex-col items-center justify-center gap-2 text-center">
        <AlertCircle className="h-6 w-6 text-risk-high" />
        <p className="text-sm text-ink-950">Couldn't load this claim.</p>
        <p className="text-xs text-slate-500">
          {error instanceof Error ? error.message : "Unknown error."}
        </p>
      </div>
    );
  }

  const { claim } = record;
  const selectedField = selectedFieldId ? claim.extracted_fields[selectedFieldId] : undefined;
  const selectedVerification = selectedFieldId
    ? claim.field_verifications[selectedFieldId]
    : undefined;

  return (
    <div className="flex h-screen flex-col bg-slate-50">
      <header className="flex shrink-0 items-center justify-between border-b border-slate-200 bg-white px-6 py-3">
        <div className="flex items-center gap-3">
          <h1 className="font-data text-base font-semibold text-ink-950">{claim.claim_id}</h1>
          {claim.lob && (
            <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium uppercase text-slate-600">
              {claim.lob}
            </span>
          )}
          {claim.triage && <TierBadge tier={claim.triage.tier} />}
        </div>
        {selectedFieldId && (
          <Button
            size="sm"
            variant="outline"
            onClick={() => openOverrideModal(selectedFieldId)}
          >
            <PencilLine className="h-3.5 w-3.5" />
            Override field
          </Button>
        )}
      </header>

      <div className="grid min-h-0 flex-1 grid-cols-[320px_1fr_360px]">
        <section className="min-h-0 border-r border-slate-200 bg-white">
          <FieldsPanel claim={claim} />
        </section>

        <section className="min-h-0 bg-white">
          <EvidenceViewer claim={claim} field={selectedField} verification={selectedVerification} />
        </section>

        <section className="scrollbar-thin min-h-0 overflow-y-auto border-l border-slate-200 bg-white">
          <TriagePanel claim={claim} />
          <SummaryPanel record={record} />
        </section>
      </div>

      <OverrideModal claim={claim} />
    </div>
  );
}
