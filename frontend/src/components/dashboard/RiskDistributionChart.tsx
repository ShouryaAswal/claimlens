import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import type { ClaimSummary, TriageTier } from "@/types/claim";

const TIER_LABEL: Record<TriageTier, string> = {
  stp_candidate: "STP Candidate",
  needs_review: "Needs Review",
  high_risk_incomplete: "High Risk",
};

const TIER_COLOR: Record<TriageTier, string> = {
  stp_candidate: "#0E9F6E",
  needs_review: "#C77C0E",
  high_risk_incomplete: "#D23B3B",
};

interface RiskDistributionChartProps {
  claims: ClaimSummary[];
}

/** Counts completed claims by triage tier. Claims still processing or
 * without a tier yet (triage hasn't run) are excluded -- a bar chart
 * mixing "not yet triaged" in with the three real verdicts would blur
 * the one thing this chart needs to say clearly. */
export function RiskDistributionChart({ claims }: RiskDistributionChartProps) {
  const tiers: TriageTier[] = ["stp_candidate", "needs_review", "high_risk_incomplete"];
  const data = tiers.map((tier) => ({
    tier,
    label: TIER_LABEL[tier],
    count: claims.filter((c) => c.tier === tier).length,
    fill: TIER_COLOR[tier],
  }));

  const hasAnyTriaged = data.some((d) => d.count > 0);

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-panel">
      <h2 className="mb-3 text-sm font-semibold text-ink-950">Risk Distribution</h2>
      {hasAnyTriaged ? (
        <ResponsiveContainer width="100%" height={200}>
          <BarChart data={data} margin={{ top: 4, right: 8, left: -16, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#EEF1F5" vertical={false} />
            <XAxis
              dataKey="label"
              tick={{ fontSize: 12, fill: "#6B7A94" }}
              axisLine={{ stroke: "#DFE4EB" }}
              tickLine={false}
            />
            <YAxis
              allowDecimals={false}
              tick={{ fontSize: 12, fill: "#6B7A94" }}
              axisLine={false}
              tickLine={false}
              width={28}
            />
            <Tooltip
              cursor={{ fill: "#F7F8FA" }}
              contentStyle={{ borderRadius: 8, borderColor: "#DFE4EB", fontSize: 12 }}
            />
            <Bar dataKey="count" radius={[4, 4, 0, 0]} maxBarSize={64}>
              {data.map((d) => (
                <Cell key={d.tier} fill={d.fill} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      ) : (
        <div className="flex h-[200px] items-center justify-center text-sm text-slate-400">
          No triaged claims yet.
        </div>
      )}
    </div>
  );
}
