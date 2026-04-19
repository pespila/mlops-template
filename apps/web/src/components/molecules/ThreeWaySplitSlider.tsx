import { useMemo } from "react";

import { cn } from "@/lib/cn";

export interface ThreeWaySplitValue {
  train: number;
  val: number;
  test: number;
}

interface ThreeWaySplitSliderProps {
  value: ThreeWaySplitValue;
  onChange: (value: ThreeWaySplitValue) => void;
  className?: string;
}

type SplitKey = keyof ThreeWaySplitValue;

const ROWS: Array<{ key: SplitKey; label: string; color: string }> = [
  { key: "train", label: "Train", color: "bg-primary" },
  { key: "val", label: "Validation", color: "bg-teal-400" },
  { key: "test", label: "Test", color: "bg-teal-200" },
];

function reconcile(
  prev: ThreeWaySplitValue,
  changed: SplitKey,
  nextValue: number,
): ThreeWaySplitValue {
  const clampedNext = Math.min(100, Math.max(0, Math.round(nextValue)));
  const others: SplitKey[] = (Object.keys(prev) as SplitKey[]).filter((k) => k !== changed);
  const remaining = 100 - clampedNext;
  const prevOthersSum = others.reduce((acc, k) => acc + prev[k], 0);
  const result: ThreeWaySplitValue = { ...prev, [changed]: clampedNext };

  if (prevOthersSum === 0) {
    const even = Math.floor(remaining / others.length);
    others.forEach((k, idx) => {
      result[k] = idx === others.length - 1 ? remaining - even * (others.length - 1) : even;
    });
    return result;
  }

  let allocated = 0;
  others.forEach((k, idx) => {
    if (idx === others.length - 1) {
      result[k] = Math.max(0, remaining - allocated);
    } else {
      const share = Math.round((prev[k] / prevOthersSum) * remaining);
      result[k] = Math.max(0, share);
      allocated += share;
    }
  });
  return result;
}

export function ThreeWaySplitSlider({ value, onChange, className }: ThreeWaySplitSliderProps) {
  const total = useMemo(() => value.train + value.val + value.test, [value]);

  return (
    <div className={cn("flex flex-col gap-4", className)}>
      <div className="flex h-3 overflow-hidden rounded-pill border border-[color:var(--border)] bg-bg-muted">
        <div className="bg-primary" style={{ width: `${value.train}%` }} />
        <div className="bg-teal-400" style={{ width: `${value.val}%` }} />
        <div className="bg-teal-200" style={{ width: `${value.test}%` }} />
      </div>
      <div className="flex flex-col gap-3">
        {ROWS.map((row) => (
          <label key={row.key} className="flex items-center gap-3 text-sm">
            <span className="flex w-28 items-center gap-2 font-medium text-fg1">
              <span aria-hidden="true" className={cn("h-2.5 w-2.5 rounded-pill", row.color)} />
              {row.label}
            </span>
            <input
              type="range"
              min={0}
              max={100}
              step={1}
              value={value[row.key]}
              onChange={(ev) =>
                onChange(reconcile(value, row.key, Number(ev.target.value)))
              }
              className="flex-1 accent-[color:var(--primary)]"
            />
            <span className="w-10 text-right font-mono text-xs text-fg2">{value[row.key]}%</span>
          </label>
        ))}
      </div>
      {total !== 100 ? (
        <p className="text-xs text-warning">
          Sum is {total}% - splits must total exactly 100%.
        </p>
      ) : null}
    </div>
  );
}
