import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { TriageTier } from "@/types/claim";

const TIER_CONFIG: Record<TriageTier, { label: string; variant: "ok" | "review" | "high" }> = {
  stp_candidate: { label: "STP Candidate", variant: "ok" },
  needs_review: { label: "Needs Review", variant: "review" },
  high_risk_incomplete: { label: "High Risk / Incomplete", variant: "high" },
};

interface TierBadgeProps {
  tier: TriageTier;
  className?: string;
}

export function TierBadge({ tier, className }: TierBadgeProps) {
  const config = TIER_CONFIG[tier];
  return (
    <Badge variant={config.variant} className={cn("font-semibold", className)}>
      {config.label}
    </Badge>
  );
}
