import { useQuery } from "@tanstack/react-query";

import { GlassCard } from "@/components/molecules/GlassCard";
import { useT } from "@/i18n";
import { api } from "@/lib/api/client";
import { useUiStore, type Language } from "@/state/uiStore";

export function Settings() {
  const t = useT();
  const language = useUiStore((s) => s.language);
  const setLanguage = useUiStore((s) => s.setLanguage);

  const health = useQuery({ queryKey: ["health"], queryFn: () => api.health() });

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6">
      <header>
        <h1 className="font-display text-display-lg font-extrabold tracking-tight text-fg1">
          {t("settings.title")}
        </h1>
        <p className="mt-2 text-fg2">{t("settings.subtitle")}</p>
      </header>

      <GlassCard>
        <dl className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <div>
            <dt className="text-xs font-semibold uppercase tracking-[0.08em] text-fg2">
              {t("settings.version")}
            </dt>
            <dd className="mt-1 font-mono text-sm text-fg1">
              {health.data?.version ?? "—"}
            </dd>
          </div>
          <div>
            <dt className="text-xs font-semibold uppercase tracking-[0.08em] text-fg2">
              {t("settings.disk")}
            </dt>
            <dd className="mt-1 text-sm text-fg2">Coming in v1</dd>
          </div>
        </dl>
      </GlassCard>

      <GlassCard>
        <h2 className="font-display text-lg font-bold text-fg1">{t("settings.language")}</h2>
        <div className="mt-3 inline-flex overflow-hidden rounded-pill border border-[color:var(--border-primary)]">
          {(["en", "de"] as Language[]).map((lng) => (
            <button
              key={lng}
              type="button"
              onClick={() => setLanguage(lng)}
              className={`px-4 py-1.5 text-xs font-semibold uppercase tracking-[0.08em] transition-colors ${
                language === lng ? "bg-primary text-white" : "bg-bg text-fg2 hover:text-fg1"
              }`}
            >
              {lng}
            </button>
          ))}
        </div>
      </GlassCard>
    </div>
  );
}
