import { useMutation, useQuery } from "@tanstack/react-query";
import { Sparkles, Zap } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { Button } from "@/components/atoms/Button";
import { IconTile } from "@/components/atoms/IconTile";
import { GlassCard } from "@/components/molecules/GlassCard";
import { useT } from "@/i18n";
import { api, type ModelCatalogEntry } from "@/lib/api/client";
import { cn } from "@/lib/cn";
import { useWizardStore } from "@/state/wizardStore";

type Tab = "builtin" | "custom";

const HIGHLIGHT_FAMILIES = ["logistic", "gradient_boosting", "xgboost", "lightgbm", "autogluon"];

const DISPLAY_NAMES: Record<string, string> = {
  sklearn_logistic: "Logistic Regression",
  sklearn_gradient_boosting: "Gradient Boosting",
  xgboost: "XGBoost",
  lightgbm: "LightGBM",
  autogluon: "AutoGluon",
};

function displayName(entry: ModelCatalogEntry): string {
  const key = (entry.family || entry.name || "").toLowerCase();
  return DISPLAY_NAMES[key] ?? entry.name;
}

function ModelPickerCard({
  entry,
  selected,
  onSelect,
}: {
  entry: ModelCatalogEntry;
  selected: boolean;
  onSelect: () => void;
}) {
  const isAutogluon = (entry.family || "").toLowerCase().includes("autogluon");
  return (
    <button
      type="button"
      onClick={onSelect}
      className={cn(
        "glass-card !p-5 text-left transition-all flex flex-col min-w-0",
        selected && "border-primary ring-2 ring-[color:var(--primary-soft)]",
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <IconTile icon={isAutogluon ? Sparkles : Zap} size={40} />
        {isAutogluon ? (
          <span className="badge-glow whitespace-nowrap text-[10px]">Zero-config</span>
        ) : null}
      </div>
      <h3 className="mt-4 font-display text-base font-bold text-fg1 break-words">
        {displayName(entry)}
      </h3>
      <p className="mt-1 text-xs text-fg2 line-clamp-3">{entry.description}</p>
    </button>
  );
}

export function StepModel() {
  const t = useT();
  const navigate = useNavigate();
  const [tab, setTab] = useState<Tab>("builtin");
  const datasetId = useWizardStore((s) => s.datasetId);
  const transforms = useWizardStore((s) => s.transforms);
  const target = useWizardStore((s) => s.target);
  const split = useWizardStore((s) => s.split);
  const modelCatalogId = useWizardStore((s) => s.modelCatalogId);
  const setModelCatalogId = useWizardStore((s) => s.setModelCatalogId);
  const hyperparams = useWizardStore((s) => s.hyperparams);
  const experimentName = useWizardStore((s) => s.experimentName);
  const setExperimentName = useWizardStore((s) => s.setExperimentName);
  const prev = useWizardStore((s) => s.prev);
  const reset = useWizardStore((s) => s.reset);

  const catalog = useQuery({
    queryKey: ["catalog", "models"],
    queryFn: () => api.catalog.models(),
  });

  const startRun = useMutation({
    mutationFn: async () => {
      if (!datasetId || !target || !modelCatalogId) throw new Error("Wizard incomplete");
      const experiment = await api.experiments.create({
        name: experimentName.trim() || `Run ${new Date().toISOString().slice(0, 16)}`,
      });
      const run = await api.runs.create({
        experiment_id: experiment.id,
        dataset_id: datasetId,
        transform_config: { target, split, features: transforms },
        model_catalog_id: modelCatalogId,
        hyperparams,
      });
      return run;
    },
    onSuccess: (run) => {
      reset();
      navigate(`/experiments/runs/${run.id}`);
    },
  });

  const builtinModels =
    catalog.data?.filter((m) =>
      HIGHLIGHT_FAMILIES.some((f) => m.family.toLowerCase().includes(f)),
    ) ?? [];

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h2 className="font-display text-2xl font-bold text-fg1">Choose a model</h2>
        <p className="mt-1 text-sm text-fg2">
          Start with a built-in model, or bring a custom training package.
        </p>
      </div>

      <div role="tablist" className="inline-flex overflow-hidden rounded-pill border border-[color:var(--border-primary)] self-start">
        {(["builtin", "custom"] as Tab[]).map((k) => (
          <button
            key={k}
            type="button"
            role="tab"
            aria-selected={tab === k}
            onClick={() => setTab(k)}
            className={cn(
              "px-4 py-1.5 text-xs font-semibold uppercase tracking-[0.08em] transition-colors",
              tab === k ? "bg-primary text-white" : "bg-bg text-fg2 hover:text-fg1",
            )}
          >
            {k === "builtin" ? "Built-in" : "Custom package"}
          </button>
        ))}
      </div>

      {tab === "builtin" ? (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
          {catalog.isPending ? (
            <p className="text-sm text-fg3">{t("common.loading")}…</p>
          ) : builtinModels.length === 0 ? (
            <p className="text-sm text-fg3">No built-in models available.</p>
          ) : (
            builtinModels.map((m) => (
              <ModelPickerCard
                key={m.id}
                entry={m}
                selected={modelCatalogId === m.id}
                onSelect={() => setModelCatalogId(m.id)}
              />
            ))
          )}
        </div>
      ) : (
        <GlassCard className="!p-6">
          <span className="badge-glow">Coming in v1</span>
          <h3 className="mt-4 font-display text-xl font-bold text-fg1">
            Custom training packages
          </h3>
          <p className="mt-1 text-sm text-fg2">
            Bring your own trainer image by uploading a signed package. This flow ships in v1.
          </p>
        </GlassCard>
      )}

      <label className="flex flex-col gap-1.5">
        <span className="text-xs font-semibold uppercase tracking-[0.08em] text-fg2">
          Experiment name
        </span>
        <input
          value={experimentName}
          onChange={(ev) => setExperimentName(ev.target.value)}
          placeholder="Churn - baseline gradient boosting"
          className="w-full max-w-md rounded border border-[color:var(--border)] bg-bg px-3 py-2 text-sm focus:border-primary focus:outline-none"
        />
      </label>

      <div className="flex justify-between">
        <Button variant="ghost" onClick={prev}>
          Back
        </Button>
        <Button
          disabled={!modelCatalogId || startRun.isPending}
          onClick={() => startRun.mutate()}
        >
          {t("wizard.finish")}
        </Button>
      </div>
      {startRun.isError ? (
        <p className="text-xs font-semibold text-danger">
          Could not start the run. Check the form and try again.
        </p>
      ) : null}
    </div>
  );
}
