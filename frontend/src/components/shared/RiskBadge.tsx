import { AlertTriangle, CheckCircle2, HelpCircle } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { RiskLevel } from "@/types/claim";

const RISK_CONFIG: Record<
  RiskLevel,
  { label: string; variant: "ok" | "review" | "high"; icon: typeof CheckCircle2 }
> = {
  ok: { label: "OK", variant: "ok", icon: CheckCircle2 },
  needs_review: { label: "Needs Review", variant: "review", icon: HelpCircle },
  high_risk: { label: "High Risk", variant: "high", icon: AlertTriangle },
};

interface RiskBadgeProps {
  risk: RiskLevel;
  className?: string;
  /** Icon-only, no label -- for dense lists like FieldsPanel rows. */
  compact?: boolean;
}

export function RiskBadge({ risk, className, compact = false }: RiskBadgeProps) {
  const config = RISK_CONFIG[risk];
  const Icon = config.icon;
  return (
    <Badge variant={config.variant} className={cn(className)}>
      <Icon className="h-3 w-3" />
      {!compact && config.label}
    </Badge>
  );
}
