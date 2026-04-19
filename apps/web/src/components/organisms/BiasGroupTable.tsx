import { cn } from "@/lib/cn";
import { formatNumber } from "@/lib/format";

export interface BiasGroupRow {
  group: string;
  support: number;
  metric: number;
  baseline: number;
}

interface BiasGroupTableProps {
  rows: BiasGroupRow[];
  metricLabel?: string;
  className?: string;
}

export function BiasGroupTable({
  rows,
  metricLabel = "Accuracy",
  className,
}: BiasGroupTableProps) {
  if (rows.length === 0) {
    return (
      <div className="rounded-md border border-dashed border-[color:var(--border)] p-6 text-center text-sm text-fg3">
        No bias-analysis groups recorded for this run.
      </div>
    );
  }
  const max = Math.max(...rows.map((r) => r.metric), 0.0001);
  return (
    <div className={cn("overflow-hidden rounded-md border border-[color:var(--border)]", className)}>
      <table className="w-full border-collapse text-sm">
        <thead className="bg-bg-muted">
          <tr>
            <th className="px-4 py-2 text-left text-xs font-semibold uppercase tracking-[0.08em] text-fg2">
              Group
            </th>
            <th className="px-4 py-2 text-right text-xs font-semibold uppercase tracking-[0.08em] text-fg2">
              Support
            </th>
            <th className="px-4 py-2 text-right text-xs font-semibold uppercase tracking-[0.08em] text-fg2">
              {metricLabel}
            </th>
            <th className="w-60 px-4 py-2 text-left text-xs font-semibold uppercase tracking-[0.08em] text-fg2">
              vs. baseline
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-[color:var(--border)]">
          {rows.map((row) => {
            const pct = (row.metric / max) * 100;
            const delta = row.metric - row.baseline;
            const deltaColor =
              Math.abs(delta) < 0.005 ? "text-fg3" : delta > 0 ? "text-success" : "text-danger";
            return (
              <tr key={row.group}>
                <td className="px-4 py-2 text-fg1">{row.group}</td>
                <td className="px-4 py-2 text-right font-mono text-xs text-fg2">
                  {formatNumber(row.support)}
                </td>
                <td className="px-4 py-2 text-right font-mono text-xs text-fg1">
                  {formatNumber(row.metric, 3)}
                </td>
                <td className="px-4 py-2">
                  <div className="flex items-center gap-3">
                    <div className="h-1.5 flex-1 rounded-pill bg-bg-muted">
                      <div
                        className="h-full rounded-pill bg-primary"
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                    <span className={cn("font-mono text-[11px]", deltaColor)}>
                      {delta >= 0 ? "+" : ""}
                      {formatNumber(delta, 3)}
                    </span>
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
