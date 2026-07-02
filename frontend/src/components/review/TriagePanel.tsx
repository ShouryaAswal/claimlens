import { AlertTriangle, ShieldCheck } from "lucide-react";

import { TierBadge } from "@/components/shared/TierBadge";
import { cn } from "@/lib/utils";
import { useReviewUiStore } from "@/store/reviewUiStore";
import type { ClaimState } from "@/types/claim";

interface TriagePanelProps {
  claim: ClaimState;
}

export function TriagePanel({ claim }: TriagePanelProps) {
  const selectField = useReviewUiStore((s) => s.selectField);
  const { triage } = claim;

  if (!triage) {
    return (
      <div className="p-4 text-sm text-slate-500">Triage has not run for this claim yet.</div>
    );
  }

  return (
    <div className="flex flex-col gap-4 p-4">
      {triage.forced_review && (
        <div className="rounded-md border border-gold-500/40 bg-gold-500/10 p-3">
          <div className="flex items-center gap-2 text-gold-700">
            <AlertTriangle className="h-4 w-4 shrink-0" />
            <span className="text-sm font-semibold">Forced review required</span>
          </div>
          <p className="mt-1 text-xs text-ink-900">
            A required field landed on high risk during verification, so this claim cannot be
            an STP candidate regardless of its overall score.
          </p>
        </div>
      )}

      <div className="flex items-center justify-between">
        <span className="text-xs font-medium uppercase tracking-wide text-slate-500">Verdict</span>
        <TierBadge tier={triage.tier} />
      </div>

      <div>
        <div className="mb-1 flex items-center justify-between text-xs text-slate-500">
          <span>Composite score</span>
          <span className="font-data">{triage.score}</span>
        </div>
        <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-200">
          <div
            className={cn(
              "h-full rounded-full",
              triage.tier === "stp_candidate"
                ? "bg-risk-ok"
                : triage.tier === "needs_review"
                  ? "bg-risk-review"
                  : "bg-risk-high",
            )}
            style={{ width: `${Math.max(0, Math.min(100, triage.score))}%` }}
          />
        </div>
      </div>

      {triage.reasons.length > 0 && (
        <div>
          <h3 className="mb-1.5 text-xs font-medium uppercase tracking-wide text-slate-500">
            Reasons
          </h3>
          <ul className="flex flex-col gap-1.5">
            {triage.reasons.map((reason, i) => (
              <li key={i} className="flex gap-2 text-sm text-ink-900">
                <span className="mt-1 h-1 w-1 shrink-0 rounded-full bg-slate-400" />
                {reason}
              </li>
            ))}
          </ul>
        </div>
      )}

      {triage.high_risk_field_ids.length > 0 && (
        <div>
          <h3 className="mb-1.5 text-xs font-medium uppercase tracking-wide text-slate-500">
            High-risk fields ({triage.high_risk_field_ids.length})
          </h3>
          <ul className="flex flex-col gap-1">
            {triage.high_risk_field_ids.map((fieldId) => (
              <li key={fieldId}>
                <button
                  type="button"
                  onClick={() => selectField(fieldId)}
                  className="w-full rounded-md border border-slate-200 px-2.5 py-1.5 text-left font-data text-xs text-ink-900 hover:border-risk-high hover:bg-risk-high-bg"
                >
                  {fieldId}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      {!triage.forced_review && triage.tier === "stp_candidate" && (
        <div className="flex items-center gap-2 rounded-md border border-risk-ok/30 bg-risk-ok-bg p-3 text-sm text-risk-ok">
          <ShieldCheck className="h-4 w-4 shrink-0" />
          Clean pass -- straight-through processing candidate.
        </div>
      )}
    </div>
  );
}
