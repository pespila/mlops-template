import { useQuery } from "@tanstack/react-query";
import { ChevronDown, ChevronRight, Download } from "lucide-react";
import { useMemo, useState } from "react";
import { useParams } from "react-router-dom";

import { RunStatusBadge } from "@/components/atoms/RunStatusBadge";
import { GlassCard } from "@/components/molecules/GlassCard";
import { LineageChip } from "@/components/molecules/LineageChip";
import { MetricCard } from "@/components/molecules/MetricCard";
import { BiasGroupTable } from "@/components/organisms/BiasGroupTable";
import { RunMetricsChart } from "@/components/organisms/RunMetricsChart";
import { SHAPGlobalBars } from "@/components/organisms/SHAPGlobalBars";
import { TrainingLogStream } from "@/components/organisms/TrainingLogStream";
import { api } from "@/lib/api/client";
import { formatNumber, formatRelative } from "@/lib/format";

export function RunDetail() {
  const { id = "" } = useParams<{ id: string }>();
  const [logsOpen, setLogsOpen] = useState(true);

  const run = useQuery({
    queryKey: ["runs", id],
    queryFn: () => api.runs.get(id),
    enabled: Boolean(id),
    refetchInterval: 5_000,
  });

  const metrics = useQuery({
    queryKey: ["runs", id, "metrics"],
    queryFn: () => api.runs.metrics(id),
    enabled: Boolean(id),
    refetchInterval: 5_000,
  });

  const artifacts = useQuery({
    queryKey: ["runs", id, "artifacts"],
    queryFn: () => api.runs.artifacts(id),
    enabled: Boolean(id),
  });

  const finalMetrics = useMemo(() => {
    if (!metrics.data) return [];
    const byName = new Map<string, number>();
    for (const m of metrics.data) {
      byName.set(m.name, m.value);
    }
    return Array.from(byName.entries()).slice(0, 4);
  }, [metrics.data]);

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6">
      <header className="flex flex-col gap-3">
        <div className="flex items-center gap-3">
          <RunStatusBadge status={run.data?.status ?? "queued"} />
          <h1 className="font-display text-display-lg font-extrabold tracking-tight text-fg1">
            Run {id.slice(0, 8)}
          </h1>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-xs text-fg2">
          {run.data ? (
            <>
              <LineageChip
                kind="dataset"
                id={run.data.dataset_id}
                to={`/datasets/${run.data.dataset_id}`}
                label="dataset"
              />
              <span>Started {formatRelative(run.data.started_at)}</span>
              {run.data.finished_at ? (
                <span>· Finished {formatRelative(run.data.finished_at)}</span>
              ) : null}
            </>
          ) : null}
        </div>
      </header>

      <section className="grid grid-cols-1 gap-4 md:grid-cols-4">
        {finalMetrics.length === 0 ? (
          <GlassCard className="md:col-span-4">
            <p className="text-sm text-fg3">No metrics recorded yet.</p>
          </GlassCard>
        ) : (
          finalMetrics.map(([name, value]) => (
            <MetricCard key={name} eyebrow={name} value={formatNumber(value, 3)} />
          ))
        )}
      </section>

      <GlassCard>
        <h2 className="font-display text-xl font-bold text-fg1">Metrics over time</h2>
        <p className="mt-1 text-sm text-fg2">Per-step loss and evaluation metrics.</p>
        <div className="mt-4">
          <RunMetricsChart metrics={metrics.data ?? []} />
        </div>
      </GlassCard>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <GlassCard>
          <h2 className="font-display text-xl font-bold text-fg1">Global feature importance</h2>
          <p className="mt-1 text-sm text-fg2">SHAP-derived, averaged across the validation split.</p>
          <div className="mt-4">
            <SHAPGlobalBars data={[]} />
          </div>
        </GlassCard>
        <GlassCard>
          <h2 className="font-display text-xl font-bold text-fg1">Bias analysis</h2>
          <p className="mt-1 text-sm text-fg2">Per-group metric deltas vs. the baseline.</p>
          <div className="mt-4">
            <BiasGroupTable rows={[]} />
          </div>
        </GlassCard>
      </div>

      <GlassCard className="!p-0 overflow-hidden">
        <div className="border-b border-[color:var(--border)] px-6 py-4">
          <h2 className="font-display text-xl font-bold text-fg1">Artifacts</h2>
        </div>
        {artifacts.data && artifacts.data.length > 0 ? (
          <ul className="divide-y divide-[color:var(--border)]">
            {artifacts.data.map((a) => (
              <li key={a.id} className="flex items-center justify-between px-6 py-3 text-sm">
                <div>
                  <div className="font-medium text-fg1">{a.name}</div>
                  <div className="text-xs text-fg3">{a.kind}</div>
                </div>
                <a
                  href={a.download_url}
                  className="inline-flex items-center gap-1.5 text-xs font-semibold text-primary hover:underline"
                >
                  <Download size={14} strokeWidth={2} /> Download
                </a>
              </li>
            ))}
          </ul>
        ) : (
          <p className="px-6 py-4 text-sm text-fg3">No artifacts yet.</p>
        )}
      </GlassCard>

      <GlassCard className="!p-0 overflow-hidden">
        <button
          type="button"
          onClick={() => setLogsOpen((v) => !v)}
          className="flex w-full items-center justify-between border-b border-[color:var(--border)] px-6 py-4 text-left hover:bg-bg-muted/60"
        >
          <h2 className="font-display text-xl font-bold text-fg1">Training logs</h2>
          {logsOpen ? (
            <ChevronDown size={18} strokeWidth={2} />
          ) : (
            <ChevronRight size={18} strokeWidth={2} />
          )}
        </button>
        {logsOpen ? (
          <div className="p-4">
            <TrainingLogStream url={`/sse/runs/${id}/logs`} enabled />
          </div>
        ) : null}
      </GlassCard>
    </div>
  );
}
