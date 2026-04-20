import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { GlassCard } from "@/components/molecules/GlassCard";
import { Modal } from "@/components/molecules/Modal";
import { api, type PredictionLogEntry } from "@/lib/api/client";
import { formatRelative } from "@/lib/format";

interface PredictionsTabProps {
  deploymentId: string;
}

export function PredictionsTab({ deploymentId }: PredictionsTabProps) {
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<PredictionLogEntry | null>(null);

  const predictions = useQuery({
    queryKey: ["deployments", deploymentId, "predictions", page],
    queryFn: () => api.deployments.predictions(deploymentId, page),
    enabled: Boolean(deploymentId),
  });

  return (
    <div className="flex flex-col gap-4">
      <GlassCard className="!p-0 overflow-hidden">
        {predictions.isPending ? (
          <p className="p-6 text-sm text-fg3">Loading…</p>
        ) : predictions.isError ? (
          <p className="p-6 text-sm text-danger">Could not load predictions.</p>
        ) : predictions.data.items.length === 0 ? (
          <p className="p-6 text-center text-sm text-fg3">No predictions logged yet.</p>
        ) : (
          <table className="w-full border-collapse text-sm">
            <thead className="bg-bg-muted text-left">
              <tr>
                <th className="px-6 py-3 text-xs font-semibold uppercase tracking-[0.08em] text-fg2">
                  When
                </th>
                <th className="px-6 py-3 text-xs font-semibold uppercase tracking-[0.08em] text-fg2">
                  Trace
                </th>
                <th className="px-6 py-3 text-xs font-semibold uppercase tracking-[0.08em] text-fg2">
                  Prediction
                </th>
                <th className="px-6 py-3 text-right text-xs font-semibold uppercase tracking-[0.08em] text-fg2">
                  Latency
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[color:var(--border)]">
              {predictions.data.items.map((row) => (
                <tr
                  key={row.id}
                  className="cursor-pointer hover:bg-bg-muted/60"
                  onClick={() => setSelected(row)}
                >
                  <td className="px-6 py-3 text-xs text-fg2">{formatRelative(row.ts)}</td>
                  <td className="px-6 py-3 font-mono text-xs text-fg2">
                    {row.trace_id ? row.trace_id.slice(0, 8) : "—"}
                  </td>
                  <td className="px-6 py-3 font-mono text-xs text-fg1">
                    {typeof row.output === "string" || typeof row.output === "number"
                      ? String(row.output)
                      : JSON.stringify(row.output).slice(0, 40)}
                  </td>
                  <td className="px-6 py-3 text-right font-mono text-xs text-fg2">
                    {row.latency_ms}ms
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </GlassCard>

      {predictions.data && predictions.data.total > predictions.data.page_size ? (
        <div className="flex items-center justify-between text-xs text-fg3">
          <span>
            Page {predictions.data.page} of{" "}
            {Math.ceil(predictions.data.total / predictions.data.page_size)}
          </span>
          <div className="flex gap-2">
            <button
              type="button"
              className="btn-ghost !px-3 !py-1 !text-xs"
              disabled={page === 1}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
            >
              Prev
            </button>
            <button
              type="button"
              className="btn-ghost !px-3 !py-1 !text-xs"
              disabled={page * predictions.data.page_size >= predictions.data.total}
              onClick={() => setPage((p) => p + 1)}
            >
              Next
            </button>
          </div>
        </div>
      ) : null}

      <Modal
        open={Boolean(selected)}
        onClose={() => setSelected(null)}
        title={
          selected
            ? `Prediction ${selected.trace_id ? selected.trace_id.slice(0, 8) : selected.id.slice(0, 8)}`
            : "Prediction"
        }
      >
        {selected ? (
          <div className="flex flex-col gap-4">
            <div>
              <h3 className="text-xs font-semibold uppercase tracking-[0.08em] text-fg2">Input</h3>
              <pre className="mt-2 overflow-x-auto rounded border border-[color:var(--border)] bg-teal-50 p-3 font-mono text-xs text-teal-900">
                {JSON.stringify(selected.input, null, 2)}
              </pre>
            </div>
            <div>
              <h3 className="text-xs font-semibold uppercase tracking-[0.08em] text-fg2">
                Output
              </h3>
              <pre className="mt-2 overflow-x-auto rounded border border-[color:var(--border)] bg-teal-50 p-3 font-mono text-xs text-teal-900">
                {JSON.stringify(selected.output, null, 2)}
              </pre>
            </div>
            <div className="rounded-md border border-[color:var(--border)] bg-bg-muted p-4 text-sm text-fg2">
              SHAP waterfall - Coming in v1
            </div>
          </div>
        ) : null}
      </Modal>
    </div>
  );
}
