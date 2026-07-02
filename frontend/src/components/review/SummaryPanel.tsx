import { FileText } from "lucide-react";

import type { ClaimRecord } from "@/types/claim";

interface SummaryPanelProps {
  record: ClaimRecord;
}

export function SummaryPanel({ record }: SummaryPanelProps) {
  const { summary, review_queue_counts: counts } = record;

  return (
    <div className="flex flex-col gap-4 border-t border-slate-200 p-4">
      <div className="flex items-center gap-2">
        <FileText className="h-4 w-4 text-slate-400" />
        <h2 className="text-sm font-semibold text-ink-950">Reviewer Summary</h2>
      </div>

      {summary ? (
        <p className="whitespace-pre-line text-sm leading-relaxed text-ink-900">{summary}</p>
      ) : (
        <p className="text-sm text-slate-400">No summary has been generated for this claim yet.</p>
      )}

      {counts.total > 0 && (
        <div className="grid grid-cols-3 gap-2 border-t border-slate-100 pt-3 text-center">
          <SummaryStat label="Needs review" value={counts.needs_review} />
          <SummaryStat label="High risk" value={counts.high_risk} tone="high" />
          <SummaryStat label="No evidence" value={counts.no_visual_evidence} />
        </div>
      )}
    </div>
  );
}

function SummaryStat({
  label,
  value,
  tone = "default",
}: {
  label: string;
  value: number;
  tone?: "default" | "high";
}) {
  return (
    <div>
      <div className={tone === "high" && value > 0 ? "text-risk-high" : "text-ink-950"}>
        <span className="font-data text-lg font-semibold">{value}</span>
      </div>
      <div className="text-[11px] text-slate-500">{label}</div>
    </div>
  );
}
