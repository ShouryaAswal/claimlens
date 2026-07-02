import { Link } from "react-router-dom";
import { AlertCircle, CircleDollarSign, FileStack, Loader2, Plus, ShieldCheck } from "lucide-react";

import { Button } from "@/components/ui/button";
import { KpiCard } from "@/components/dashboard/KpiCard";
import { RiskDistributionChart } from "@/components/dashboard/RiskDistributionChart";
import { ClaimsTable } from "@/components/dashboard/ClaimsTable";
import { useClaimsList } from "@/hooks/useClaim";
import { formatCurrency, formatPercent } from "@/lib/utils";

/**
 * The adjuster's landing view once claims exist. Everything here is
 * derived from GET /api/claims (app/routers/claims.py::list_claims()) --
 * no per-claim re-fetching, the summary endpoint already has what every
 * KPI needs.
 */
export default function Dashboard() {
  const { data: claims, isLoading, isError, refetch } = useClaimsList();

  if (isLoading) {
    return (
      <div className="flex h-screen items-center justify-center gap-2 text-slate-500">
        <Loader2 className="h-5 w-5 animate-spin" />
        Loading claims…
      </div>
    );
  }

  if (isError || !claims) {
    return (
      <div className="flex h-screen flex-col items-center justify-center gap-3 text-center">
        <AlertCircle className="h-6 w-6 text-risk-high" />
        <p className="text-sm text-ink-950">Couldn't load claims.</p>
        <Button size="sm" variant="outline" onClick={() => refetch()}>
          Retry
        </Button>
      </div>
    );
  }

  const completeClaims = claims.filter((c) => c.status === "complete");
  const stpCount = completeClaims.filter((c) => c.tier === "stp_candidate").length;
  const needsHumanCount = claims.filter(
    (c) => c.status === "complete" && (c.forced_review || c.tier === "high_risk_incomplete"),
  ).length;
  const totalAmount = claims.reduce((sum, c) => sum + (c.primary_amount ?? 0), 0);
  const avgCompletion =
    completeClaims.length === 0
      ? 0
      : completeClaims.reduce(
          (sum, c) =>
            sum + (c.completion.required_fields === 0 ? 1 : c.completion.required_fields_found / c.completion.required_fields),
          0,
        ) / completeClaims.length;

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="flex items-center justify-between border-b border-slate-200 bg-white px-6 py-4">
        <div>
          <h1 className="text-lg font-semibold text-ink-950">Claims Dashboard</h1>
          <p className="text-xs text-slate-500">{claims.length} claim{claims.length === 1 ? "" : "s"} total</p>
        </div>
        <Button asChild size="sm" variant="gold">
          <Link to="/start">
            <Plus className="h-3.5 w-3.5" />
            New claim
          </Link>
        </Button>
      </header>

      <main className="mx-auto flex max-w-6xl flex-col gap-4 p-6">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <KpiCard label="Total claims" value={String(claims.length)} icon={FileStack} />
          <KpiCard
            label="STP rate"
            value={completeClaims.length === 0 ? "—" : formatPercent(stpCount, completeClaims.length)}
            subtext={`${stpCount} of ${completeClaims.length} completed`}
            icon={ShieldCheck}
          />
          <KpiCard
            label="Needs a human"
            value={String(needsHumanCount)}
            subtext="Forced review or high risk"
            icon={AlertCircle}
            tone={needsHumanCount > 0 ? "gold" : "default"}
          />
          <KpiCard
            label="Total claim value"
            value={formatCurrency(totalAmount)}
            subtext={`Avg. completion ${Math.round(avgCompletion * 100)}%`}
            icon={CircleDollarSign}
          />
        </div>

        <RiskDistributionChart claims={claims} />

        <ClaimsTable claims={claims} />
      </main>
    </div>
  );
}
