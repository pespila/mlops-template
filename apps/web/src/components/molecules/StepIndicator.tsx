import { Check } from "lucide-react";

import { cn } from "@/lib/cn";

export interface StepIndicatorStep {
  key: string;
  label: string;
  description?: string;
}

interface StepIndicatorProps {
  steps: StepIndicatorStep[];
  currentIndex: number;
  onStepClick?: (index: number) => void;
  className?: string;
}

export function StepIndicator({
  steps,
  currentIndex,
  onStepClick,
  className,
}: StepIndicatorProps) {
  return (
    <ol className={cn("flex flex-col gap-5", className)}>
      {steps.map((step, idx) => {
        const isActive = idx === currentIndex;
        const isComplete = idx < currentIndex;
        const clickable = onStepClick && idx <= currentIndex;
        return (
          <li key={step.key} className="flex items-start gap-3">
            <button
              type="button"
              disabled={!clickable}
              onClick={() => clickable && onStepClick?.(idx)}
              className={cn(
                "relative mt-0.5 inline-flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-pill",
                "border text-[13px] font-semibold transition-colors",
                isActive
                  ? "border-primary bg-bg text-primary shadow-glow"
                  : isComplete
                    ? "border-primary bg-primary text-white"
                    : "border-[color:var(--border)] bg-bg text-fg3",
                clickable && !isActive ? "cursor-pointer hover:border-primary" : "",
              )}
              aria-current={isActive ? "step" : undefined}
            >
              {isActive ? (
                <span
                  aria-hidden="true"
                  className="absolute h-2 w-2 rounded-pill bg-primary animate-pulse-teal"
                />
              ) : null}
              {isComplete ? (
                <Check size={14} strokeWidth={2.5} />
              ) : (
                <span className={isActive ? "opacity-0" : ""}>{idx + 1}</span>
              )}
            </button>
            <div className="flex flex-col">
              <span
                className={cn(
                  "font-sans text-sm font-semibold",
                  isActive ? "text-fg1" : isComplete ? "text-fg1" : "text-fg3",
                )}
              >
                {step.label}
              </span>
              {step.description ? (
                <span className="text-xs text-fg3">{step.description}</span>
              ) : null}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
