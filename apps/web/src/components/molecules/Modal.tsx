import { X } from "lucide-react";
import { useEffect, type ReactNode } from "react";

import { cn } from "@/lib/cn";

interface ModalProps {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  className?: string;
}

export function Modal({ open, onClose, title, children, className }: ModalProps) {
  useEffect(() => {
    if (!open) return;
    function onKey(ev: KeyboardEvent) {
      if (ev.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={title}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4 animate-fade-in"
      onClick={onClose}
    >
      <div
        className={cn("glass-card !p-0 w-full max-w-lg", className)}
        onClick={(ev) => ev.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-[color:var(--border)] px-6 py-4">
          <h2 className="font-display text-lg font-bold text-fg1">{title}</h2>
          <button
            type="button"
            onClick={onClose}
            className="inline-flex h-8 w-8 items-center justify-center rounded-md text-fg2 hover:bg-bg-muted hover:text-fg1"
            aria-label="Close"
          >
            <X size={16} strokeWidth={2} />
          </button>
        </div>
        <div className="p-6">{children}</div>
      </div>
    </div>
  );
}
