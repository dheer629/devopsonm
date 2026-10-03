import { forwardRef, type InputHTMLAttributes } from "react";

import { cn } from "@/lib/utils";

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(
  ({ className, ...props }, ref) => (
    <input
      ref={ref}
      className={cn(
        "h-8 w-full rounded-md border border-border bg-bg-elevated px-2 text-[12.5px] text-text placeholder:text-text-faint focus-visible:border-accent",
        className,
      )}
      {...props}
    />
  ),
);
Input.displayName = "Input";
