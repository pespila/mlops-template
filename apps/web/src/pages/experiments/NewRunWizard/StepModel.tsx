import { useMutation, useQuery } from "@tanstack/react-query";
import { Sparkles, Zap } from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

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
  const [searchParams] = useSearchParams();
  const [tab, setTab] = useState<Tab>("builtin");
  const [experimentMode, setExperimentMode] = useState<"existing" | "new">("existing");
  const datasetId = useWizardStore((s) => s.datasetId);
  const transforms = useWizardStore((s) => s.transforms);
  const target = useWizardStore((s) => s.target);
  const sensitiveFeatures = useWizardStore((s) => s.sensitiveFeatures);
  const split = useWizardStore((s) => s.split);
  const modelCatalogId = useWizardStore((s) => s.modelCatalogId);
  const setModelCatalogId = useWizardStore((s) => s.setModelCatalogId);
  const hyperparams = useWizardStore((s) => s.hyperparams);
  const experimentName = useWizardStore((s) => s.experimentName);
  const setExperimentName = useWizardStore((s) => s.setExperimentName);
  const experimentId = useWizardStore((s) => s.experimentId);
  const setExperimentId = useWizardStore((s) => s.setExperimentId);
  const prev = useWizardStore((s) => s.prev);
  const reset = useWizardStore((s) => s.reset);

  const catalog = useQuery({
    queryKey: ["catalog", "models"],
    queryFn: () => api.catalog.models(),
  });

  const experiments = useQuery({
    queryKey: ["experiments"],
    queryFn: () => api.experiments.list(),
  });

  // URL ?experiment=<id> preselects an existing experiment (from ExperimentDetail
  // "New run →"); otherwise pick the most recent one by default.
  useEffect(() => {
    const preset = searchParams.get("experiment");
    if (preset) {
      setExperimentId(preset);
      setExperimentMode("existing");
      return;
    }
    if (!experimentId && experiments.data && experiments.data.length > 0) {
      setExperimentId(experiments.data[0].id);
    }
    if (experiments.data && experiments.data.length === 0) {
      setExperimentMode("new");
    }
  }, [experiments.data, experimentId, searchParams, setExperimentId]);

  const startRun = useMutation({
    mutationFn: async () => {
      if (!datasetId || !target || !modelCatalogId) throw new Error("Wizard incomplete");
      let expId = experimentMode === "existing" ? experimentId : null;
      if (!expId) {
        const exp = await api.experiments.create({
          name: experimentName.trim() || `Experiment ${new Date().toISOString().slice(0, 16)}`,
        });
        expId = exp.id;
      }

      // UI kind → backend op. The backend's build_column_transformer applies
      // sensible defaults for columns it doesn't see here, so we only send
      // entries that deviate from the default ("keep" is a no-op).
      const kindToOp: Record<string, string> = {
        drop: "drop",
        standardize: "standard_scale",
        "one-hot": "one_hot",
        "impute-mean": "impute_mean",
        "impute-median": "impute_median",
        "impute-mode": "impute_mode",
      };
      const transformList = transforms
        .filter((t) => t.feature !== target && kindToOp[t.kind])
        .map((t) => ({ column: t.feature, op: kindToOp[t.kind] }));

      // Split slider stores 0–100 ints; the trainer normalizes but fractions
      // are the on-wire convention we want to settle on.
      const splitFractions = {
        train: split.train / 100,
        val: split.val / 100,
        test: split.test / 100,
      };

      const run = await api.runs.create({
        experiment_id: expId,
        dataset_id: datasetId,
        transform_config: {
          target,
          transforms: transformList,
          split: splitFractions,
          sensitive_features: sensitiveFeatures,
        },
        model_catalog_id: modelCatalogId,
        hyperparams,
      });
      return { run, experimentId: expId };
    },
    onSuccess: ({ run }) => {
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

      <div className="flex flex-col gap-3">
        <span className="text-xs font-semibold uppercase tracking-[0.08em] text-fg2">
          Experiment
        </span>
        <div role="tablist" className="inline-flex overflow-hidden rounded-pill border border-[color:var(--border-primary)] self-start text-[11px]">
          {(["existing", "new"] as const).map((m) => (
            <button
              key={m}
              type="button"
              onClick={() => setExperimentMode(m)}
              disabled={m === "existing" && (experiments.data?.length ?? 0) === 0}
              className={cn(
                "px-3 py-1.5 font-semibold uppercase tracking-[0.08em] transition-colors disabled:opacity-40 disabled:cursor-not-allowed",
                experimentMode === m
                  ? "bg-primary text-white"
                  : "bg-bg text-fg2 hover:text-fg1",
              )}
            >
              {m === "existing" ? "Add to existing" : "Create new"}
            </button>
          ))}
        </div>

        {experimentMode === "existing" ? (
          <select
            value={experimentId ?? ""}
            onChange={(ev) => setExperimentId(ev.target.value || null)}
            className="w-full max-w-md rounded border border-[color:var(--border)] bg-bg px-3 py-2 text-sm focus:border-primary focus:outline-none"
          >
            {(experiments.data ?? []).map((exp) => (
              <option key={exp.id} value={exp.id}>
                {exp.name}
                {exp.run_count ? ` · ${exp.run_count} run${exp.run_count > 1 ? "s" : ""}` : ""}
              </option>
            ))}
          </select>
        ) : (
          <input
            value={experimentName}
            onChange={(ev) => setExperimentName(ev.target.value)}
            placeholder="Churn - baseline gradient boosting"
            className="w-full max-w-md rounded border border-[color:var(--border)] bg-bg px-3 py-2 text-sm focus:border-primary focus:outline-none"
          />
        )}
      </div>

      <div className="flex justify-between">
        <Button variant="ghost" onClick={prev}>
          Back
        </Button>
        <Button
          disabled={
            !modelCatalogId ||
            startRun.isPending ||
            (experimentMode === "existing" && !experimentId)
          }
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
