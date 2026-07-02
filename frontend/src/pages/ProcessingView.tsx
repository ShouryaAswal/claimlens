import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams, Link } from "react-router-dom";
import { AlertTriangle, CheckCircle2, CircleDashed, Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { useClaimStream } from "@/hooks/useClaimStream";
import type { StageName } from "@/types/claim";

interface Milestone {
  stage: StageName;
  label: string;
}

// Mirrors the exact stage order core/pipeline.py emits in -- see its
// `_emit(...)` calls. `extract_section` is deliberately NOT its own row;
// it's a sub-progress event folded into the "extract" row below.
const MILESTONES: Milestone[] = [
  { stage: "ingest", label: "Ingesting documents" },
  { stage: "classify", label: "Classifying line of business" },
  { stage: "schema_resolve", label: "Resolving field schema" },
  { stage: "doc_type_tag", label: "Tagging document types" },
  { stage: "gate_check", label: "Checking mandatory documents" },
  { stage: "extract", label: "Extracting fields" },
  { stage: "merge", label: "Detecting citation conflicts" },
  { stage: "verify", label: "Verifying evidence & rating confidence" },
  { stage: "crops", label: "Generating evidence crops" },
  { stage: "triage", label: "Triaging claim" },
  { stage: "summary", label: "Writing reviewer summary" },
];

type RowStatus = "pending" | "active" | "complete" | "error";

export default function ProcessingView() {
  const { claimId } = useParams<{ claimId: string }>();
  const navigate = useNavigate();
  const [pipelineError, setPipelineError] = useState<string | null>(null);

  const { events, connected } = useClaimStream(claimId, {
    onDone: () => {
      // Small delay so the final row visibly flips to "complete" before
      // the page changes out from under the adjuster.
      setTimeout(() => navigate(`/claims/${claimId}`), 500);
    },
    onError: (detail) => {
      setPipelineError((detail?.error as string) ?? "The pipeline failed for an unknown reason.");
    },
  });

  // Redundant safety net: if this view is mounted on a claim whose
  // pipeline already finished before the SSE connection was opened (the
  // documented "late subscriber" gap in app/sse.py), the stream will sit
  // open with no events. This alone can't detect that -- see the
  // "already finished?" note below the stage list.
  useEffect(() => {
    if (!claimId) navigate("/start");
  }, [claimId, navigate]);

  const lastCompletedIndex = useMemo(() => {
    let idx = -1;
    MILESTONES.forEach((m, i) => {
      if (events.some((e) => e.stage === m.stage && e.status === "complete")) idx = i;
    });
    return idx;
  }, [events]);

  const extractProgress = useMemo(() => {
    const last = [...events].reverse().find((e) => e.stage === "extract_section");
    if (!last?.detail) return null;
    const { section_id, fields_found, fields_total } = last.detail as Record<string, unknown>;
    return `${section_id}: ${fields_found}/${fields_total} fields found`;
  }, [events]);

  function rowStatus(index: number): RowStatus {
    if (index <= lastCompletedIndex) return "complete";
    if (index === lastCompletedIndex + 1) return pipelineError ? "error" : "active";
    return "pending";
  }

  return (
    <div className="flex h-screen flex-col items-center justify-center bg-slate-50 px-4">
      <div className="w-full max-w-md rounded-lg border border-slate-200 bg-white p-6 shadow-panel">
        <div className="mb-5">
          <h1 className="font-data text-sm font-semibold text-ink-950">{claimId}</h1>
          <p className="text-xs text-slate-500">
            {pipelineError ? "Processing failed" : connected ? "Processing…" : "Connecting…"}
          </p>
        </div>

        <ul className="flex flex-col gap-3">
          {MILESTONES.map((m, i) => {
            const status = rowStatus(i);
            return (
              <li key={m.stage} className="flex items-center gap-3">
                <StatusIcon status={status} />
                <div className="min-w-0 flex-1">
                  <span
                    className={cn(
                      "text-sm",
                      status === "pending" ? "text-slate-400" : "text-ink-900",
                      status === "complete" && "text-slate-500 line-through decoration-slate-300",
                    )}
                  >
                    {m.label}
                  </span>
                  {m.stage === "extract" && status === "active" && extractProgress && (
                    <p className="font-data mt-0.5 truncate text-xs text-slate-400">{extractProgress}</p>
                  )}
                </div>
              </li>
            );
          })}
        </ul>

        {pipelineError && (
          <div className="mt-5 rounded-md border border-risk-high/30 bg-risk-high-bg p-3">
            <div className="flex items-center gap-2 text-risk-high">
              <AlertTriangle className="h-4 w-4 shrink-0" />
              <span className="text-sm font-semibold">Pipeline error</span>
            </div>
            <p className="mt-1 text-xs text-ink-900">{pipelineError}</p>
            <div className="mt-3 flex gap-2">
              <Button asChild size="sm" variant="outline">
                <Link to="/start">Start a new claim</Link>
              </Button>
              <Button asChild size="sm" variant="ghost">
                <Link to="/claims">Back to dashboard</Link>
              </Button>
            </div>
          </div>
        )}

        {!pipelineError && !connected && events.length === 0 && (
          <p className="mt-5 text-center text-xs text-slate-400">
            No progress yet. If this claim already finished processing before this page opened,{" "}
            <Link to={`/claims/${claimId}`} className="underline underline-offset-2">
              open it directly
            </Link>
            .
          </p>
        )}
      </div>
    </div>
  );
}

function StatusIcon({ status }: { status: RowStatus }) {
  if (status === "complete") return <CheckCircle2 className="h-4 w-4 shrink-0 text-risk-ok" />;
  if (status === "error") return <AlertTriangle className="h-4 w-4 shrink-0 text-risk-high" />;
  if (status === "active") return <Loader2 className="h-4 w-4 shrink-0 animate-spin text-gold-600" />;
  return <CircleDashed className="h-4 w-4 shrink-0 text-slate-300" />;
}
