import { useQuery } from "@tanstack/react-query";
import { ArrowRight, Plus } from "lucide-react";
import { useNavigate, useParams } from "react-router-dom";

import { Button } from "@/components/atoms/Button";
import { RunStatusBadge } from "@/components/atoms/RunStatusBadge";
import { GlassCard } from "@/components/molecules/GlassCard";
import { api } from "@/lib/api/client";
import { formatRelative } from "@/lib/format";

export function ExperimentDetail() {
  const { id = "" } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const experiment = useQuery({
    queryKey: ["experiments", id],
    queryFn: () => api.experiments.get(id),
    enabled: Boolean(id),
  });

  const runs = useQuery({
    queryKey: ["runs", { experimentId: id }],
    queryFn: () => api.runs.list(id),
    enabled: Boolean(id),
    refetchInterval: 3000,
  });

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6">
      <header className="flex items-start justify-between gap-4">
        <div>
          <h1 className="font-display text-display-lg font-extrabold tracking-tight text-fg1">
            {experiment.data?.name ?? "Experiment"}
          </h1>
          <p className="mt-2 max-w-xl text-fg2">
            {experiment.data?.description ?? "A grouping of training runs."}
          </p>
        </div>
        <Button
          asChild
          as="link"
          to={`/experiments/new?experiment=${encodeURIComponent(id)}`}
          leftIcon={<Plus size={16} strokeWidth={2} />}
        >
          New run →
        </Button>
      </header>

      <GlassCard className="!p-0 overflow-hidden">
        {runs.isPending ? (
          <div className="p-6 text-sm text-fg3">Loading…</div>
        ) : runs.isError ? (
          <div className="p-6 text-sm text-danger">Could not load runs.</div>
        ) : runs.data.length === 0 ? (
          <div className="p-8 text-center text-sm text-fg3">
            No runs in this experiment yet.
          </div>
        ) : (
          <table className="w-full border-collapse text-sm">
            <thead className="bg-bg-muted text-left">
              <tr>
                <th className="px-6 py-3 text-xs font-semibold uppercase tracking-[0.08em] text-fg2">
                  Run
                </th>
                <th className="px-6 py-3 text-xs font-semibold uppercase tracking-[0.08em] text-fg2">
                  Status
                </th>
                <th className="px-6 py-3 text-xs font-semibold uppercase tracking-[0.08em] text-fg2">
                  Started
                </th>
                <th className="px-6 py-3 text-xs font-semibold uppercase tracking-[0.08em] text-fg2">
                  {" "}
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[color:var(--border)]">
              {runs.data.map((r) => (
                <tr
                  key={r.id}
                  className="cursor-pointer hover:bg-bg-muted/60"
                  onClick={() => navigate(`/experiments/runs/${r.id}`)}
                >
                  <td className="px-6 py-3 font-mono text-xs text-fg1">
                    {r.id.slice(0, 8)}…
                  </td>
                  <td className="px-6 py-3">
                    <RunStatusBadge status={r.status} />
                  </td>
                  <td className="px-6 py-3 text-xs text-fg2">
                    {r.started_at ? formatRelative(r.started_at) : "queued"}
                  </td>
                  <td className="px-6 py-3 text-right">
                    <ArrowRight size={14} strokeWidth={2} className="inline text-fg3" />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </GlassCard>
    </div>
  );
}
