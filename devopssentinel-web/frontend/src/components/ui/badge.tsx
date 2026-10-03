import { cva, type VariantProps } from "class-variance-authority";
import type { HTMLAttributes } from "react";

import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-[11px] font-medium leading-4",
  {
    variants: {
      tone: {
        neutral: "border-border text-text-muted bg-panel-2",
        ok: "border-success/40 text-success bg-success/10",
        warning: "border-warning/40 text-warning bg-warning/10",
        critical: "border-critical/40 text-critical bg-critical/10",
        info: "border-info/40 text-info bg-info/10",
        unknown: "border-border-strong text-unknown bg-panel-2",
        kubernetes: "border-kubernetes/40 text-kubernetes bg-kubernetes/10",
        gitops: "border-gitops/40 text-gitops bg-gitops/10",
        pki: "border-pki/40 text-pki bg-pki/10",
        network: "border-network/40 text-network bg-network/10",
        storage: "border-storage/40 text-storage bg-storage/10",
      },
    },
    defaultVariants: { tone: "neutral" },
  },
);

export interface BadgeProps
  extends HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

export function Badge({ className, tone, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ tone }), className)} {...props} />;
}

export { badgeVariants };
