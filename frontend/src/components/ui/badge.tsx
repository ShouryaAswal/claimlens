import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-medium",
  {
    variants: {
      variant: {
        default: "border-transparent bg-ink-900 text-white",
        outline: "border-slate-300 text-slate-600",
        ok: "border-transparent bg-risk-ok-bg text-risk-ok",
        review: "border-transparent bg-risk-review-bg text-risk-review",
        high: "border-transparent bg-risk-high-bg text-risk-high",
        gold: "border-transparent bg-gold-500/15 text-gold-700",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  },
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />;
}

export { Badge, badgeVariants };
