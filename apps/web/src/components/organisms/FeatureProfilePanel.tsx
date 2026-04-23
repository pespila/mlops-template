import { FeatureTypePill } from "@/components/atoms/FeatureTypePill";
import type { FeatureSchema, FeatureType } from "@/lib/api/client";
import { cn } from "@/lib/cn";

export type CategoricalEncoder = "one-hot" | "label" | "ordinal";

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
  /**
   * Columns the current task can actually consume. Columns NOT in this set
   * stay selectable but are flagged with a red "!" + tooltip. When undefined,
   * no suitability rendering kicks in (all columns treated as suitable).
   */
  suitableColumns?: Set<string>;
  /** i18n-ready tooltip for the red "!" badge. */
  unsuitableHint?: string;
  /** Select-all / deselect-all handlers for the header bar. */
  onSelectAll?: () => void;
  onDeselectAll?: () => void;
  /** Per-column categorical encoder selection (wizard only). */
  encoderChoice?: Record<string, CategoricalEncoder>;
  onEncoderChange?: (featureName: string, encoder: CategoricalEncoder) => void;
  readOnly?: boolean;
  className?: string;
}

const TYPES: FeatureType[] = ["numeric", "categorical", "datetime", "boolean", "text"];
const ENCODERS: CategoricalEncoder[] = ["one-hot", "label", "ordinal"];

function MiniBar({ value }: { value: number }) {
  const pct = Math.max(2, Math.min(100, value * 100));
  return (
    <div className="h-1.5 w-24 rounded-pill bg-bg-muted">
      <div className="h-full rounded-pill bg-primary" style={{ width: `${pct}%` }} />
    </div>
  );
}

function UnsuitableBadge({ hint }: { hint: string }) {
  return (
    <span
      title={hint}
      aria-label={hint}
      className="ml-2 inline-flex h-4 w-4 items-center justify-center rounded-full bg-[color:var(--danger,#dc2626)] text-[10px] font-bold leading-none text-white"
    >
      !
    </span>
  );
}

export function FeatureProfilePanel({
  schema,
  onChange,
  excluded,
  onToggleInclude,
  suitableColumns,
  unsuitableHint = "This column isn't suited to the selected task.",
  onSelectAll,
  onDeselectAll,
  encoderChoice,
  onEncoderChange,
  readOnly,
  className,
}: FeatureProfilePanelProps) {
  const showInclude = Boolean(onToggleInclude);
  const showBulk = Boolean(onSelectAll || onDeselectAll);
  const showEncoder = Boolean(onEncoderChange);
  return (
    <div className={cn("overflow-hidden rounded-md border border-[color:var(--border)]", className)}>
      {showBulk ? (
        <div className="flex items-center justify-end gap-2 border-b border-[color:var(--border)] bg-bg-muted/60 px-4 py-1.5 text-xs">
          {onSelectAll ? (
            <button
              type="button"
              onClick={onSelectAll}
              className="rounded-md border border-[color:var(--border)] bg-bg px-2 py-1 font-medium text-fg1 hover:bg-bg-muted"
            >
              Select all
            </button>
          ) : null}
          {onDeselectAll ? (
            <button
              type="button"
              onClick={onDeselectAll}
              className="rounded-md border border-[color:var(--border)] bg-bg px-2 py-1 font-medium text-fg1 hover:bg-bg-muted"
            >
              Deselect all
            </button>
          ) : null}
        </div>
      ) : null}
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
            {showEncoder ? (
              <th className="px-4 py-2 text-left text-xs font-semibold uppercase tracking-[0.08em] text-fg2">
                Encoder
              </th>
            ) : null}
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
            const isUnsuitable =
              suitableColumns !== undefined && !suitableColumns.has(col.name);
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
                <td className="px-4 py-2 font-mono text-xs text-fg1">
                  <span className="inline-flex items-center">
                    {col.name}
                    {isUnsuitable ? <UnsuitableBadge hint={unsuitableHint} /> : null}
                  </span>
                </td>
                <td className="px-4 py-2">
                  {readOnly || !onChange ? (
                    <FeatureTypePill type={col.type} />
                  ) : (
                    <select
                      value={col.type}
                      onChange={(ev) => onChange(col.name, ev.target.value as FeatureType)}
                      className="rounded border border-[color:var(--border)] bg-bg px-2 py-1 text-xs"
                    >
                      {TYPES.map((t) => (
                        <option key={t} value={t}>
                          {t}
                        </option>
                      ))}
                    </select>
                  )}
                </td>
                {showEncoder ? (
                  <td className="px-4 py-2">
                    {col.type === "categorical" ? (
                      <select
                        value={encoderChoice?.[col.name] ?? "one-hot"}
                        onChange={(ev) =>
                          onEncoderChange?.(
                            col.name,
                            ev.target.value as CategoricalEncoder,
                          )
                        }
                        className="rounded border border-[color:var(--border)] bg-bg px-2 py-1 text-xs"
                      >
                        {ENCODERS.map((e) => (
                          <option key={e} value={e}>
                            {e}
                          </option>
                        ))}
                      </select>
                    ) : (
                      <span className="text-xs text-fg2">—</span>
                    )}
                  </td>
                ) : null}
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
