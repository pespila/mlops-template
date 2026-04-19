import { cn } from "@/lib/cn";

export type RunStatus =
  | "queued"
  | "building"
  | "running"
  | "succeeded"
  | "failed"
  | "cancelled";

const LABEL: Record<RunStatus, string> = {
  queued: "Queued",
  building: "Building",
  running: "Running",
  succeeded: "Succeeded",
  failed: "Failed",
  cancelled: "Cancelled",
};

const DOT_COLOR: Record<RunStatus, string> = {
  queued: "bg-fg3",
  building: "bg-warning",
  running: "bg-primary animate-pulse-teal",
  succeeded: "bg-success",
  failed: "bg-danger",
  cancelled: "bg-fg3",
};

interface RunStatusBadgeProps {
  status: RunStatus;
  className?: string;
}

export function RunStatusBadge({ status, className }: RunStatusBadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-2 rounded-pill border border-[color:var(--border-primary)]",
        "bg-bg px-3.5 py-1.5 text-[11px] font-semibold uppercase tracking-[0.1em] text-fg1",
        "shadow-glow",
        className,
      )}
    >
      <span aria-hidden="true" className={cn("h-1.5 w-1.5 rounded-pill", DOT_COLOR[status])} />
      {LABEL[status]}
    </span>
  );
}
