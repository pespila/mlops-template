import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { GlassCard } from "@/components/molecules/GlassCard";
import { useT } from "@/i18n";
import { api } from "@/lib/api/client";
import { formatRelative } from "@/lib/format";

export function ModelsList() {
  const t = useT();
  const models = useQuery({ queryKey: ["models"], queryFn: () => api.models.list() });

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6">
      <header>
        <h1 className="font-display text-display-lg font-extrabold tracking-tight text-fg1">
          {t("models.title")}
        </h1>
        <p className="mt-2 max-w-xl text-fg2">{t("models.subtitle")}</p>
      </header>

      {models.isPending ? (
        <GlassCard>
          <p className="text-sm text-fg3">{t("common.loading")}…</p>
        </GlassCard>
      ) : models.isError ? (
        <GlassCard>
          <p className="text-sm text-danger">{t("common.error")}</p>
        </GlassCard>
      ) : models.data.length === 0 ? (
        <GlassCard>
          <p className="text-center text-sm text-fg3">{t("models.empty")}</p>
        </GlassCard>
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
          {models.data.map((m) => (
            <Link key={m.id} to={`/models/${m.id}`}>
              <GlassCard className="!p-6">
                <h3 className="font-display text-xl font-bold text-fg1">{m.name}</h3>
                {(m as { description?: string | null }).description ? (
                  <p className="mt-2 text-sm text-fg2 line-clamp-2">
                    {(m as { description?: string | null }).description}
                  </p>
                ) : null}
                <p className="mt-3 text-xs text-fg3">
                  {(m as { created_at?: string }).created_at
                    ? `Registered ${formatRelative((m as { created_at: string }).created_at)}`
                    : ""}
                </p>
              </GlassCard>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
