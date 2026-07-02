import { Link } from "react-router-dom";
import { FileQuestion } from "lucide-react";

import { RiskBadge } from "@/components/shared/RiskBadge";
import { TierBadge } from "@/components/shared/TierBadge";
import { formatCurrency, formatDateTime, formatPercent } from "@/lib/utils";
import type { ClaimSummary } from "@/types/claim";

const STATUS_LABEL: Record<ClaimSummary["status"], { label: string; className: string }> = {
  processing: { label: "Processing", className: "text-slate-500" },
  complete: { label: "Complete", className: "text-risk-ok" },
  error: { label: "Error", className: "text-risk-high" },
};

interface ClaimsTableProps {
  claims: ClaimSummary[];
}

export function ClaimsTable({ claims }: ClaimsTableProps) {
  if (claims.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-slate-300 bg-white py-16 text-center">
        <FileQuestion className="h-6 w-6 text-slate-300" />
        <p className="text-sm text-slate-500">No claims yet.</p>
        <Link to="/start" className="text-sm font-medium text-ink-800 underline underline-offset-4">
          Submit the first one
        </Link>
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-panel">
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="border-b border-slate-200 text-xs font-medium uppercase tracking-wide text-slate-500">
            <th className="px-4 py-2.5">Claim</th>
            <th className="px-4 py-2.5">LOB</th>
            <th className="px-4 py-2.5">Status</th>
            <th className="px-4 py-2.5">Verdict</th>
            <th className="px-4 py-2.5">Completion</th>
            <th className="px-4 py-2.5">Amount</th>
            <th className="px-4 py-2.5">Updated</th>
          </tr>
        </thead>
        <tbody>
          {claims.map((claim) => {
            const status = STATUS_LABEL[claim.status];
            const linkTo = claim.status === "processing" ? `/processing/${claim.claim_id}` : `/claims/${claim.claim_id}`;
            return (
              <tr key={claim.claim_id} className="border-b border-slate-100 last:border-0 hover:bg-slate-50">
                <td className="px-4 py-2.5">
                  <Link to={linkTo} className="font-data font-medium text-ink-950 hover:underline">
                    {claim.claim_id}
                  </Link>
                </td>
                <td className="px-4 py-2.5 uppercase text-slate-600">{claim.lob ?? "—"}</td>
                <td className={`px-4 py-2.5 font-medium ${status.className}`}>{status.label}</td>
                <td className="px-4 py-2.5">
                  {claim.tier ? (
                    <TierBadge tier={claim.tier} />
                  ) : claim.status === "error" ? (
                    <RiskBadge risk="high_risk" />
                  ) : (
                    <span className="text-slate-400">—</span>
                  )}
                </td>
                <td className="px-4 py-2.5 font-data text-slate-700">
                  {formatPercent(claim.completion.required_fields_found, claim.completion.required_fields)}
                </td>
                <td className="px-4 py-2.5 font-data text-slate-700">
                  {formatCurrency(claim.primary_amount)}
                </td>
                <td className="px-4 py-2.5 text-slate-500">{formatDateTime(claim.updated_at)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
