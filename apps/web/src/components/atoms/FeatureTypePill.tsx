import { cn } from "@/lib/cn";

export type FeatureType = "numeric" | "categorical" | "datetime" | "boolean" | "text";

const LABELS: Record<FeatureType, string> = {
  numeric: "Numeric",
  categorical: "Categorical",
  datetime: "Datetime",
  boolean: "Boolean",
  text: "Text",
};

interface FeatureTypePillProps {
  type: FeatureType;
  className?: string;
}

export function FeatureTypePill({ type, className }: FeatureTypePillProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-pill border border-[color:var(--border-primary)]",
        "bg-teal-50 px-2.5 py-0.5 text-[11px] font-semibold uppercase tracking-[0.08em]",
        "text-teal-900",
        className,
      )}
    >
      {LABELS[type]}
    </span>
  );
}
