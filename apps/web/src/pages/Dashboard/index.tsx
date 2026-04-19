import { ArrowRight } from "lucide-react";

import { BadgeGlow } from "@/components/atoms/BadgeGlow";
import { Eyebrow } from "@/components/atoms/Eyebrow";
import { GlassCard } from "@/components/molecules/GlassCard";

export function Dashboard() {
  return (
    <div className="max-w-6xl mx-auto flex flex-col gap-8">
      <header className="flex flex-col gap-4">
        <BadgeGlow>Platform · v0</BadgeGlow>
        <h1 className="font-display text-display-xl font-extrabold tracking-tight text-fg1">
          Train, deploy, and query ML models — all on your own machine.
        </h1>
        <p className="text-lg text-fg2 max-w-2xl">
          Upload a dataset, pick a model (including AutoGluon, zero-config), and deploy to a live
          API. No cloud dependencies. Your data never leaves the host.
        </p>
        <div className="flex gap-3">
          <a href="/experiments" className="btn-primary">
            Start a new run
            <ArrowRight size={16} strokeWidth={2} />
          </a>
          <a href="/datasets" className="btn-ghost">
            Browse datasets →
          </a>
        </div>
      </header>

      <section className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <GlassCard>
          <Eyebrow>01 · Upload</Eyebrow>
          <h3 className="mt-3 font-display text-2xl font-bold">Bring your own data</h3>
          <p className="mt-2 text-fg2">
            CSV, Excel, Parquet. The platform profiles every column and infers types automatically.
          </p>
        </GlassCard>
        <GlassCard>
          <Eyebrow>02 · Train</Eyebrow>
          <h3 className="mt-3 font-display text-2xl font-bold">Pick a model — or let AutoGluon</h3>
          <p className="mt-2 text-fg2">
            Built-in sklearn, gradient boosting, and AutoGluon. Bias + SHAP run automatically.
          </p>
        </GlassCard>
        <GlassCard>
          <Eyebrow>03 · Deploy</Eyebrow>
          <h3 className="mt-3 font-display text-2xl font-bold">One click to a live API</h3>
          <p className="mt-2 text-fg2">
            Every deployment is a Docker container with auto-generated docs and prediction logs.
          </p>
        </GlassCard>
      </section>
    </div>
  );
}
