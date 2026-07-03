import { Link, useParams } from "react-router-dom";
import { AlertCircle, ArrowLeft, CheckCircle2, FileStack, ListChecks, Loader2, PencilLine, Plus, XCircle } from "lucide-react";

import { Button } from "@/components/ui/button";
import { DocumentViewerModal } from "@/components/review/DocumentViewerModal";
import { DocumentsPanel } from "@/components/review/DocumentsPanel";
import { EvidenceViewer } from "@/components/review/EvidenceViewer";
import { FieldsPanel } from "@/components/review/FieldsPanel";
import { OverrideModal } from "@/components/review/OverrideModal";
import { SummaryPanel } from "@/components/review/SummaryPanel";
import { TriagePanel } from "@/components/review/TriagePanel";
import { TierBadge } from "@/components/shared/TierBadge";
import { useAdjusterDecision, useClaim } from "@/hooks/useClaim";
import { cn } from "@/lib/utils";
import { useReviewUiStore } from "@/store/reviewUiStore";

export default function ClaimReview() {
  const { claimId } = useParams<{ claimId: string }>();
  const { data: record, isLoading, isError, error } = useClaim(claimId);
  const { mutate: decide, isPending: decisionPending } = useAdjusterDecision(claimId ?? "");

  const selectedFieldId = useReviewUiStore((s) => s.selectedFieldId);
  const openOverrideModal = useReviewUiStore((s) => s.openOverrideModal);
  const activeTab = useReviewUiStore((s) => s.activeTab);
  const setActiveTab = useReviewUiStore((s) => s.setActiveTab);

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
        <Link to="/claims" className="mt-2 text-sm font-medium text-ink-800 underline underline-offset-4">
          Back to dashboard
        </Link>
      </div>
    );
  }

  const { claim } = record;
  const selectedField = selectedFieldId ? claim.extracted_fields[selectedFieldId] : undefined;
  const selectedVerification = selectedFieldId
    ? claim.field_verifications[selectedFieldId]
    : undefined;
  const isDecided = record.adjuster_decision !== "pending";

  return (
    <div className="flex h-screen flex-col bg-slate-50">
      <header className="flex shrink-0 flex-col gap-2 border-b border-slate-200 bg-white px-6 py-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Link
              to="/claims"
              className="flex items-center gap-1 text-xs text-slate-500 hover:text-ink-900"
            >
              <ArrowLeft className="h-3.5 w-3.5" />
              Dashboard
            </Link>
            <span className="h-4 w-px bg-slate-200" />
            <h1 className="font-data text-base font-semibold text-ink-950">{claim.claim_id}</h1>
            {claim.lob && (
              <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium uppercase text-slate-600">
                {claim.lob}
              </span>
            )}
            {claim.triage && <TierBadge tier={claim.triage.tier} />}
            {record.adjuster_decision === "approved" && (
              <span className="flex items-center gap-1 rounded-full bg-risk-ok-bg px-2 py-0.5 text-xs font-medium text-risk-ok">
                <CheckCircle2 className="h-3 w-3" /> Approved
              </span>
            )}
            {record.adjuster_decision === "rejected" && (
              <span className="flex items-center gap-1 rounded-full bg-risk-high-bg px-2 py-0.5 text-xs font-medium text-risk-high">
                <XCircle className="h-3 w-3" /> Rejected
              </span>
            )}
          </div>

          <div className="flex items-center gap-2">
            {selectedFieldId && (
              <Button size="sm" variant="outline" onClick={() => openOverrideModal(selectedFieldId)}>
                <PencilLine className="h-3.5 w-3.5" />
                Override field
              </Button>
            )}
            <Button size="sm" variant="outline" onClick={() => decide("reject")} disabled={decisionPending || isDecided}>
              <XCircle className="h-3.5 w-3.5" />
              Reject
            </Button>
            <Button size="sm" variant="gold" onClick={() => decide("approve")} disabled={decisionPending || isDecided}>
              <CheckCircle2 className="h-3.5 w-3.5" />
              Approve
            </Button>
            <Button asChild size="sm" variant="ghost">
              <Link to="/start">
                <Plus className="h-3.5 w-3.5" />
                New claim
              </Link>
            </Button>
          </div>
        </div>

        <div className="flex gap-1">
          <TabButton active={activeTab === "fields"} onClick={() => setActiveTab("fields")} icon={ListChecks}>
            Fields
          </TabButton>
          <TabButton active={activeTab === "documents"} onClick={() => setActiveTab("documents")} icon={FileStack}>
            Documents ({claim.documents.length})
          </TabButton>
        </div>
      </header>

      <div className="grid min-h-0 flex-1 grid-cols-[320px_1fr_360px]">
        <section className="min-h-0 border-r border-slate-200 bg-white">
          {activeTab === "fields" ? <FieldsPanel claim={claim} /> : <DocumentsPanel claim={claim} />}
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
      <DocumentViewerModal claim={claim} />
    </div>
  );
}

function TabButton({
  active,
  onClick,
  icon: Icon,
  children,
}: {
  active: boolean;
  onClick: () => void;
  icon: typeof ListChecks;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "flex items-center gap-1.5 rounded-t-md border-b-2 px-3 py-1.5 text-xs font-medium transition-colors",
        active
          ? "border-gold-500 text-ink-950"
          : "border-transparent text-slate-500 hover:text-ink-900",
      )}
    >
      <Icon className="h-3.5 w-3.5" />
      {children}
    </button>
  );
}
