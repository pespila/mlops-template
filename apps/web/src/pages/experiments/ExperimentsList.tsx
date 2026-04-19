import { useQuery } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { Button } from "@/components/atoms/Button";
import { GlassCard } from "@/components/molecules/GlassCard";
import { useT } from "@/i18n";
import { api } from "@/lib/api/client";
import { formatRelative } from "@/lib/format";

export function ExperimentsList() {
  const t = useT();
  const navigate = useNavigate();
  const experiments = useQuery({
    queryKey: ["experiments"],
    queryFn: () => api.experiments.list(),
  });

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6">
      <header className="flex items-start justify-between gap-4">
        <div>
          <h1 className="font-display text-display-lg font-extrabold tracking-tight text-fg1">
            {t("experiments.title")}
          </h1>
          <p className="mt-2 max-w-xl text-fg2">{t("experiments.subtitle")}</p>
        </div>
        <Button
          asChild
          as="link"
          to="/experiments/new"
          leftIcon={<Plus size={16} strokeWidth={2} />}
        >
          {t("experiments.newRun")}
        </Button>
      </header>

      <GlassCard className="!p-0 overflow-hidden">
        {experiments.isPending ? (
          <div className="p-6 text-sm text-fg3">{t("common.loading")}…</div>
        ) : experiments.isError ? (
          <div className="p-6 text-sm text-danger">{t("common.error")}</div>
        ) : experiments.data.length === 0 ? (
          <div className="p-8 text-center text-sm text-fg3">{t("experiments.empty")}</div>
        ) : (
          <table className="w-full border-collapse text-sm">
            <thead className="bg-bg-muted text-left">
              <tr>
                <th className="px-6 py-3 text-xs font-semibold uppercase tracking-[0.08em] text-fg2">
                  Name
                </th>
                <th className="px-6 py-3 text-xs font-semibold uppercase tracking-[0.08em] text-fg2">
                  Description
                </th>
                <th className="px-6 py-3 text-right text-xs font-semibold uppercase tracking-[0.08em] text-fg2">
                  Runs
                </th>
                <th className="px-6 py-3 text-xs font-semibold uppercase tracking-[0.08em] text-fg2">
                  Created
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[color:var(--border)]">
              {experiments.data.map((exp) => (
                <tr
                  key={exp.id}
                  className="cursor-pointer hover:bg-bg-muted/60"
                  onClick={() => navigate(`/experiments/${exp.id}`)}
                >
                  <td className="px-6 py-3 font-medium text-fg1">{exp.name}</td>
                  <td className="px-6 py-3 text-fg2">{exp.description ?? "—"}</td>
                  <td className="px-6 py-3 text-right font-mono text-xs text-fg2">
                    {exp.run_count}
                  </td>
                  <td className="px-6 py-3 text-xs text-fg2">{formatRelative(exp.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </GlassCard>
    </div>
  );
}
