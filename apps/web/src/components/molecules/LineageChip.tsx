import { Database, FlaskConical, type LucideIcon } from "lucide-react";
import { Link } from "react-router-dom";

import { cn } from "@/lib/cn";

type LineageKind = "dataset" | "run";

const ICON: Record<LineageKind, LucideIcon> = {
  dataset: Database,
  run: FlaskConical,
};

interface LineageChipProps {
  kind: LineageKind;
  id: string;
  label?: string;
  to: string;
  className?: string;
}

function shortHash(id: string): string {
  if (id.length <= 8) return id;
  return id.slice(0, 8);
}

export function LineageChip({ kind, id, label, to, className }: LineageChipProps) {
  const Icon = ICON[kind];
  return (
    <Link
      to={to}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-pill border border-[color:var(--border-primary)]",
        "bg-bg px-2.5 py-1 text-xs font-semibold text-fg1 hover:bg-bg-muted",
        "transition-colors",
        className,
      )}
    >
      <Icon size={12} strokeWidth={2} className="text-primary" aria-hidden="true" />
      <span className="max-w-[140px] truncate">{label ?? kind}</span>
      <span className="font-mono text-[11px] text-fg3">{shortHash(id)}</span>
    </Link>
  );
}
