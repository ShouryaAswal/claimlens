import type { LucideIcon } from "lucide-react";

import { cn } from "@/lib/utils";

interface KpiCardProps {
  label: string;
  value: string;
  subtext?: string;
  icon: LucideIcon;
  tone?: "default" | "gold";
}

/** One stat tile for the Dashboard's KPI row. Deliberately plain -- the
 * gold accent is reserved for "needs a human" moments elsewhere in the
 * app, so it's used sparingly here too (only `tone="gold"`, for whichever
 * single KPI most needs attention, e.g. claims awaiting review). */
export function KpiCard({ label, value, subtext, icon: Icon, tone = "default" }: KpiCardProps) {
  return (
    <div className="flex flex-col gap-2 rounded-lg border border-slate-200 bg-white p-4 shadow-panel">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</span>
        <Icon className={cn("h-4 w-4", tone === "gold" ? "text-gold-600" : "text-slate-400")} />
      </div>
      <span className="font-data text-2xl font-semibold text-ink-950">{value}</span>
      {subtext && <span className="text-xs text-slate-500">{subtext}</span>}
    </div>
  );
}
