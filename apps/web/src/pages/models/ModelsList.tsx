import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import { GlassCard } from "@/components/molecules/GlassCard";
import { useT } from "@/i18n";
import { api } from "@/lib/api/client";
import { formatRelative } from "@/lib/format";

export function ModelsList() {
  const t = useT();
  const navigate = useNavigate();
  const models = useQuery({ queryKey: ["models"], queryFn: () => api.models.list() });

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6">
      <header>
        <h1 className="font-display text-display-lg font-extrabold tracking-tight text-fg1">
          {t("models.title")}
        </h1>
        <p className="mt-2 max-w-xl text-fg2">{t("models.subtitle")}</p>
      </header>

      <GlassCard className="!p-0 overflow-hidden">
        {models.isPending ? (
          <div className="p-6 text-sm text-fg3">{t("common.loading")}…</div>
        ) : models.isError ? (
          <div className="p-6 text-sm text-danger">{t("common.error")}</div>
        ) : models.data.length === 0 ? (
          <div className="p-8 text-center text-sm text-fg3">{t("models.empty")}</div>
        ) : (
          <table className="w-full border-collapse text-sm">
            <thead className="bg-bg-muted text-left">
              <tr>
                <th className="px-6 py-3 text-xs font-semibold uppercase tracking-[0.08em] text-fg2">
                  {t("models.columns.name")}
                </th>
                <th className="px-6 py-3 text-xs font-semibold uppercase tracking-[0.08em] text-fg2">
                  {t("models.columns.description")}
                </th>
                <th className="px-6 py-3 text-xs font-semibold uppercase tracking-[0.08em] text-fg2">
                  {t("models.columns.registered")}
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[color:var(--border)]">
              {models.data.map((m) => {
                const desc = (m as { description?: string | null }).description;
                const created = (m as { created_at?: string }).created_at;
                return (
                  <tr
                    key={m.id}
                    className="cursor-pointer hover:bg-bg-muted/60"
                    onClick={() => navigate(`/models/${m.id}`)}
                  >
                    <td className="px-6 py-3 font-medium text-fg1">{m.name}</td>
                    <td className="px-6 py-3 text-sm text-fg2">
                      {desc ? (
                        <span className="line-clamp-1">{desc}</span>
                      ) : (
                        <span className="text-fg3">—</span>
                      )}
                    </td>
                    <td className="px-6 py-3 text-xs text-fg2">
                      {created ? formatRelative(created) : "—"}
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
