import { ArrowDownRight, ArrowUpRight, Minus } from "lucide-react";

import { cn } from "@/lib/cn";

interface MetricDeltaProps {
  /** Delta expressed as a ratio, e.g. 0.04 = +4%. */
  value: number;
  /** If true, a positive delta is rendered in red (e.g. error rate). */
  invert?: boolean;
  className?: string;
}

function formatPct(value: number): string {
  const abs = Math.abs(value);
  const fractionDigits = abs >= 0.1 ? 1 : 2;
  return `${(value * 100).toFixed(fractionDigits)}%`;
}

export function MetricDelta({ value, invert = false, className }: MetricDeltaProps) {
  const epsilon = 1e-4;
  const isFlat = Math.abs(value) < epsilon;
  const isPositive = value > 0;
  const good = isFlat ? null : invert ? !isPositive : isPositive;
  const color = good === null ? "text-fg3" : good ? "text-success" : "text-danger";
  const Icon = isFlat ? Minus : isPositive ? ArrowUpRight : ArrowDownRight;
  const sign = isFlat ? "" : isPositive ? "+" : "";

  return (
    <span className={cn("inline-flex items-center gap-1 text-xs font-semibold", color, className)}>
      <Icon size={14} strokeWidth={2} aria-hidden="true" />
      <span>
        {sign}
        {formatPct(value)}
      </span>
    </span>
  );
}
