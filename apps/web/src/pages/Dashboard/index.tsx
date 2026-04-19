import { ArrowRight } from "lucide-react";
import { Link } from "react-router-dom";

import { BadgeGlow } from "@/components/atoms/BadgeGlow";
import { Eyebrow } from "@/components/atoms/Eyebrow";
import { GlassCard } from "@/components/molecules/GlassCard";
import { useT } from "@/i18n";

export function Dashboard() {
  const t = useT();
  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-8 animate-fade-in">
      <header className="flex flex-col gap-4">
        <BadgeGlow>{t("dashboard.eyebrow")}</BadgeGlow>
        <h1 className="font-display text-display-xl font-extrabold tracking-tight text-fg1">
          {t("dashboard.headline")}
        </h1>
        <p className="max-w-2xl text-lg text-fg2">{t("dashboard.subhead")}</p>
        <div className="flex gap-3">
          <Link to="/experiments/new" className="btn-primary">
            {t("dashboard.ctaPrimary")}
            <ArrowRight size={16} strokeWidth={2} />
          </Link>
          <Link to="/datasets" className="btn-ghost">
            {t("dashboard.ctaGhost")}
          </Link>
        </div>
      </header>

      <section className="grid grid-cols-1 gap-6 md:grid-cols-3">
        <GlassCard>
          <Eyebrow>01 · Upload</Eyebrow>
          <h3 className="mt-3 font-display text-2xl font-bold">{t("dashboard.stepUpload")}</h3>
          <p className="mt-2 text-fg2">
            CSV, Excel, Parquet. The platform profiles every column and infers types automatically.
          </p>
        </GlassCard>
        <GlassCard>
          <Eyebrow>02 · Train</Eyebrow>
          <h3 className="mt-3 font-display text-2xl font-bold">{t("dashboard.stepTrain")}</h3>
          <p className="mt-2 text-fg2">
            Built-in sklearn, gradient boosting, and AutoGluon. Bias and SHAP run automatically.
          </p>
        </GlassCard>
        <GlassCard>
          <Eyebrow>03 · Deploy</Eyebrow>
          <h3 className="mt-3 font-display text-2xl font-bold">{t("dashboard.stepDeploy")}</h3>
          <p className="mt-2 text-fg2">
            Every deployment is a Docker container with auto-generated docs and prediction logs.
          </p>
        </GlassCard>
      </section>
    </div>
  );
}
