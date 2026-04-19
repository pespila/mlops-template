import { useQuery } from "@tanstack/react-query";
import { useParams } from "react-router-dom";

import { GlassCard } from "@/components/molecules/GlassCard";
import { api } from "@/lib/api/client";
import { formatNumber, formatRelative } from "@/lib/format";

export function ModelDetail() {
  const { id = "" } = useParams<{ id: string }>();
  const model = useQuery({
    queryKey: ["models", id],
    queryFn: () => api.models.get(id),
    enabled: Boolean(id),
  });

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6">
      <header>
        <h1 className="font-display text-display-lg font-extrabold tracking-tight text-fg1">
          {model.data?.name ?? "Model"}
        </h1>
      </header>

      <GlassCard className="!p-0 overflow-hidden">
        {model.isPending ? (
          <div className="p-6 text-sm text-fg3">Loading…</div>
        ) : model.isError ? (
          <div className="p-6 text-sm text-danger">Could not load model.</div>
        ) : (
          <table className="w-full border-collapse text-sm">
            <thead className="bg-bg-muted text-left">
              <tr>
                <th className="px-6 py-3 text-xs font-semibold uppercase tracking-[0.08em] text-fg2">
                  Version
                </th>
                <th className="px-6 py-3 text-xs font-semibold uppercase tracking-[0.08em] text-fg2">
                  Run
                </th>
                <th className="px-6 py-3 text-xs font-semibold uppercase tracking-[0.08em] text-fg2">
                  Metrics
                </th>
                <th className="px-6 py-3 text-xs font-semibold uppercase tracking-[0.08em] text-fg2">
                  Created
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[color:var(--border)]">
              {(model.data?.versions ?? []).map((v) => {
                const version = (v as { mlflow_version?: string | null; version?: number }).mlflow_version
                  ?? (v as { version?: number }).version
                  ?? "1";
                const metrics =
                  ((v as { metrics?: Record<string, number> }).metrics) ?? {};
                return (
                  <tr key={v.id} className="hover:bg-bg-muted/60">
                    <td className="px-6 py-3 font-mono text-xs text-fg1">v{version}</td>
                    <td className="px-6 py-3 font-mono text-xs text-fg2">
                      {v.run_id.slice(0, 8)}
                    </td>
                    <td className="px-6 py-3 text-xs text-fg2">
                      {Object.entries(metrics)
                        .map(([k, val]) => `${k}: ${formatNumber(val, 3)}`)
                        .join(" · ") || "—"}
                    </td>
                    <td className="px-6 py-3 text-xs text-fg2">
                      {formatRelative(v.created_at)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </GlassCard>
    </div>
  );
}
