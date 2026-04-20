import { FeatureTypePill } from "@/components/atoms/FeatureTypePill";
import type { FeatureSchema, FeatureType } from "@/lib/api/client";
import { cn } from "@/lib/cn";

interface FeatureProfilePanelProps {
  schema: FeatureSchema[];
  onChange?: (featureName: string, nextType: FeatureType) => void;
  /**
   * Columns the user has chosen to exclude from training. Rendered as an
   * "Include" checkbox in the first column; when empty the control is hidden
   * so other contexts (dataset detail page) keep their read-only shape.
   */
  excluded?: Set<string>;
  onToggleInclude?: (featureName: string, included: boolean) => void;
  readOnly?: boolean;
  className?: string;
}

const TYPES: FeatureType[] = ["numeric", "categorical", "datetime", "boolean", "text"];

function MiniBar({ value }: { value: number }) {
  const pct = Math.max(2, Math.min(100, value * 100));
  return (
    <div className="h-1.5 w-24 rounded-pill bg-bg-muted">
      <div className="h-full rounded-pill bg-primary" style={{ width: `${pct}%` }} />
    </div>
  );
}

export function FeatureProfilePanel({
  schema,
  onChange,
  excluded,
  onToggleInclude,
  readOnly,
  className,
}: FeatureProfilePanelProps) {
  const showInclude = Boolean(onToggleInclude);
  return (
    <div className={cn("overflow-hidden rounded-md border border-[color:var(--border)]", className)}>
      <table className="w-full border-collapse text-sm">
        <thead className="bg-bg-muted">
          <tr>
            {showInclude ? (
              <th className="w-10 px-4 py-2 text-left text-xs font-semibold uppercase tracking-[0.08em] text-fg2">
                Use
              </th>
            ) : null}
            <th className="px-4 py-2 text-left text-xs font-semibold uppercase tracking-[0.08em] text-fg2">
              Feature
            </th>
            <th className="px-4 py-2 text-left text-xs font-semibold uppercase tracking-[0.08em] text-fg2">
              Type
            </th>
            <th className="px-4 py-2 text-right text-xs font-semibold uppercase tracking-[0.08em] text-fg2">
              Null %
            </th>
            <th className="px-4 py-2 text-right text-xs font-semibold uppercase tracking-[0.08em] text-fg2">
              Unique
            </th>
            <th className="px-4 py-2 text-left text-xs font-semibold uppercase tracking-[0.08em] text-fg2">
              Distribution
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-[color:var(--border)]">
          {schema.map((col) => {
            const isExcluded = excluded?.has(col.name) ?? false;
            return (
              <tr
                key={col.name}
                className={cn(
                  "hover:bg-bg-muted/60",
                  isExcluded && "opacity-50",
                )}
              >
                {showInclude ? (
                  <td className="px-4 py-2">
                    <input
                      type="checkbox"
                      aria-label={`Include ${col.name} in training`}
                      checked={!isExcluded}
                      onChange={(ev) => onToggleInclude?.(col.name, ev.target.checked)}
                      className="h-4 w-4 accent-primary"
                    />
                  </td>
                ) : null}
                <td className="px-4 py-2 font-mono text-xs text-fg1">{col.name}</td>
                <td className="px-4 py-2">
                  {readOnly || !onChange ? (
                    <FeatureTypePill type={col.type} />
                  ) : (
                    <select
                      value={col.type}
                      onChange={(ev) => onChange(col.name, ev.target.value as FeatureType)}
                      className="rounded border border-[color:var(--border)] bg-bg px-2 py-1 text-xs"
                      disabled={isExcluded}
                    >
                      {TYPES.map((t) => (
                        <option key={t} value={t}>
                          {t}
                        </option>
                      ))}
                    </select>
                  )}
                </td>
                <td className="px-4 py-2 text-right font-mono text-xs text-fg2">
                  {(col.null_fraction * 100).toFixed(1)}
                </td>
                <td className="px-4 py-2 text-right font-mono text-xs text-fg2">
                  {col.unique_count}
                </td>
                <td className="px-4 py-2">
                  <MiniBar value={1 - col.null_fraction} />
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
