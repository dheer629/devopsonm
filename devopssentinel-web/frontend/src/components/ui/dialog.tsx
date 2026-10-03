import * as DialogPrimitive from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import { forwardRef, type ReactNode } from "react";

import { cn } from "@/lib/utils";

export const Dialog = DialogPrimitive.Root;
export const DialogTrigger = DialogPrimitive.Trigger;
export const DialogClose = DialogPrimitive.Close;

export const DialogContent = forwardRef<
  React.ComponentRef<typeof DialogPrimitive.Content>,
  React.ComponentPropsWithoutRef<typeof DialogPrimitive.Content>
>(({ className, children, ...props }, ref) => (
  <DialogPrimitive.Portal>
    <DialogPrimitive.Overlay className="fixed inset-0 z-40 bg-black/50" />
    <DialogPrimitive.Content
      ref={ref}
      className={cn(
        "fixed left-1/2 top-1/2 z-50 w-full max-w-lg -translate-x-1/2 -translate-y-1/2 rounded-lg border border-border bg-panel shadow-2xl",
        className,
      )}
      {...props}
    >
      {children}
      <DialogPrimitive.Close
        aria-label="Close dialog"
        className="absolute right-2 top-2 rounded p-1 text-text-muted hover:bg-panel-2 hover:text-text"
      >
        <X className="h-4 w-4" />
      </DialogPrimitive.Close>
    </DialogPrimitive.Content>
  </DialogPrimitive.Portal>
));
DialogContent.displayName = "DialogContent";

/** Right-hand drawer used for the resource inspector (spec section 10). */
export function Sheet({
  open,
  onOpenChange,
  title,
  children,
  width = 520,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  title: ReactNode;
  children: ReactNode;
  width?: number;
}) {
  return (
    <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-40 bg-black/40" />
        <DialogPrimitive.Content
          style={{ width }}
          className="fixed right-0 top-0 z-50 h-full max-w-[92vw] overflow-y-auto scroll-thin border-l border-border bg-panel shadow-2xl"
        >
          <div className="sticky top-0 z-10 flex items-center justify-between gap-2 border-b border-border bg-panel px-3 py-2">
            <DialogPrimitive.Title className="text-[13px] font-semibold text-text">
              {title}
            </DialogPrimitive.Title>
            <DialogPrimitive.Close
              aria-label="Close panel"
              className="rounded p-1 text-text-muted hover:bg-panel-2 hover:text-text"
            >
              <X className="h-4 w-4" />
            </DialogPrimitive.Close>
          </div>
          <div className="p-3">{children}</div>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}
