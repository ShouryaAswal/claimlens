import { cn } from "@/lib/utils";
import type { RiskLevel } from "@/types/claim";

const FILL_BY_RISK: Record<RiskLevel, string> = {
  ok: "bg-risk-ok",
  needs_review: "bg-risk-review",
  high_risk: "bg-risk-high",
};

interface ConfidenceBarProps {
  /** 0-1, matches FieldVerification.composite_confidence */
  confidence: number;
  risk: RiskLevel;
  className?: string;
}

export function ConfidenceBar({ confidence, risk, className }: ConfidenceBarProps) {
  const pct = Math.round(Math.max(0, Math.min(1, confidence)) * 100);
  return (
    <div className={cn("flex items-center gap-2", className)}>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-200">
        <div
          className={cn("h-full rounded-full transition-all", FILL_BY_RISK[risk])}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="font-data w-9 shrink-0 text-right text-xs text-slate-500">{pct}%</span>
    </div>
  );
}
