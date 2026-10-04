import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { forwardRef, type ButtonHTMLAttributes } from "react";

import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-1.5 whitespace-nowrap rounded-full text-[12.5px] font-medium transition-all duration-150 disabled:pointer-events-none disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent active:translate-y-[0.5px]",
  {
    variants: {
      variant: {
        default:
          "border border-border bg-panel-2 text-text hover:border-border-strong hover:bg-panel",
        primary:
          "border border-transparent bg-accent text-white shadow-[0_2px_10px_var(--accent-soft)] hover:brightness-110",
        ghost: "border border-transparent text-text-muted hover:bg-panel-2 hover:text-text",
        outline: "border border-border-strong text-text hover:bg-panel-2",
        danger: "border border-critical/45 text-critical hover:bg-critical/10",
        soft: "border border-transparent bg-accent-soft text-accent hover:brightness-110",
      },
      size: {
        sm: "h-7 px-3",
        md: "h-8 px-3.5",
        lg: "h-9 px-4",
        icon: "h-8 w-8",
        "icon-sm": "h-6 w-6",
      },
    },
    defaultVariants: { variant: "default", size: "md" },
  },
);

export interface ButtonProps
  extends ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return (
      <Comp ref={ref} className={cn(buttonVariants({ variant, size }), className)} {...props} />
    );
  },
);
Button.displayName = "Button";

export { buttonVariants };

