import { useQuery } from "@tanstack/react-query";
import { Sparkles, Zap } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { Button } from "@/components/atoms/Button";
import { IconTile } from "@/components/atoms/IconTile";
import { GlassCard } from "@/components/molecules/GlassCard";
import { useT } from "@/i18n";
import { api, type ModelCatalogEntry, type TaskKind } from "@/lib/api/client";
import { cn } from "@/lib/cn";
import { useWizardStore } from "@/state/wizardStore";

type Tab = "builtin" | "custom";

const DISPLAY_NAMES: Record<string, string> = {
  sklearn_linear: "Linear Regression",
  sklearn_ridge: "Ridge",
  sklearn_lasso: "Lasso",
  sklearn_elasticnet: "ElasticNet",
  sklearn_logistic: "Logistic Regression",
  sklearn_svm: "Support Vector Machine",
  sklearn_knn: "K-Nearest Neighbors",
  sklearn_decision_tree: "Decision Tree",
  sklearn_random_forest: "Random Forest",
  sklearn_extra_trees: "Extra Trees",
  sklearn_gradient_boosting: "Gradient Boosting",
  sklearn_hist_gbm: "HistGradientBoosting",
  sklearn_ada_boost: "AdaBoost",
  sklearn_mlp: "MLP (Neural Net)",
  sklearn_naive_bayes: "Naive Bayes",
  xgboost: "XGBoost",
  lightgbm: "LightGBM",
  autogluon: "AutoGluon",
};

const TASK_LABELS: Record<TaskKind, string> = {
  regression: "Regression",
  binary_classification: "Binary classification",
  multiclass_classification: "Multiclass classification",
};

function displayName(entry: ModelCatalogEntry): string {
  const key = (entry.family || entry.name || "").toLowerCase();
  return DISPLAY_NAMES[key] ?? entry.name;
}

function inferTaskFromTarget(
  schema: Array<{ name: string; type: string; unique_count: number }> | undefined,
  target: string | null,
): TaskKind | null {
  if (!schema || !target) return null;
  const col = schema.find((c) => c.name === target);
  if (!col) return null;
  if (col.type === "numeric" && col.unique_count > 20) return "regression";
  if (col.type === "boolean") return "binary_classification";
  if (col.type === "categorical" || col.type === "boolean") {
    return col.unique_count <= 2 ? "binary_classification" : "multiclass_classification";
  }
  // Fallback for text / datetime: assume multiclass (rare). Backend will
  // validate.
  return "multiclass_classification";
}

function ModelPickerCard({
  entry,
  selected,
  recommended,
  compatible,
  onSelect,
}: {
  entry: ModelCatalogEntry;
  selected: boolean;
  recommended: boolean;
  compatible: boolean;
  onSelect: () => void;
}) {
  const isAutogluon = (entry.family || "").toLowerCase().includes("autogluon");
  return (
    <button
      type="button"
      onClick={onSelect}
      disabled={!compatible}
      className={cn(
        "glass-card !p-5 text-left transition-all flex flex-col min-w-0",
        selected && "border-primary ring-2 ring-[color:var(--primary-soft)]",
        !compatible && "opacity-40 cursor-not-allowed",
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <IconTile icon={isAutogluon ? Sparkles : Zap} size={40} />
        <div className="flex flex-col items-end gap-1">
          {recommended ? (
            <span className="badge-glow whitespace-nowrap text-[10px]">Recommended</span>
          ) : null}
          {isAutogluon ? (
            <span className="badge-glow whitespace-nowrap text-[10px]">Zero-config</span>
          ) : null}
        </div>
      </div>
      <h3 className="mt-4 font-display text-base font-bold text-fg1 break-words">
        {displayName(entry)}
      </h3>
      <p className="mt-1 text-xs text-fg2 line-clamp-3">{entry.description}</p>
      <div className="mt-2 text-[10px] font-mono text-fg3">{entry.framework ?? "—"}</div>
    </button>
  );
}

export function StepModel() {
  const t = useT();
  const [tab, setTab] = useState<Tab>("builtin");
  const [frameworkFilter, setFrameworkFilter] = useState<string>("all");
  const datasetId = useWizardStore((s) => s.datasetId);
  const target = useWizardStore((s) => s.target);
  const modelCatalogId = useWizardStore((s) => s.modelCatalogId);
  const setModelCatalogId = useWizardStore((s) => s.setModelCatalogId);
  const task = useWizardStore((s) => s.task);
  const setTask = useWizardStore((s) => s.setTask);
  const hpoEnabled = useWizardStore((s) => s.hpoEnabled);
  const setHpoEnabled = useWizardStore((s) => s.setHpoEnabled);
  const next = useWizardStore((s) => s.next);
  const prev = useWizardStore((s) => s.prev);

  const catalog = useQuery({
    queryKey: ["catalog", "models"],
    queryFn: () => api.catalog.models(),
  });

  const schema = useQuery({
    queryKey: ["datasets", datasetId, "schema"],
    queryFn: () => api.datasets.schema(datasetId!),
    enabled: Boolean(datasetId),
  });

  // Pre-select the inferred task from the target column so the Recommended
  // badges show even before the user touches the pill.
  useEffect(() => {
    if (task != null) return;
    const inferred = inferTaskFromTarget(schema.data, target);
    if (inferred) setTask(inferred);
  }, [schema.data, target, task, setTask]);

  const effectiveTask = task ?? inferTaskFromTarget(schema.data, target);

  const frameworks = useMemo(() => {
    const set = new Set<string>();
    for (const m of catalog.data ?? []) {
      if (m.framework) set.add(m.framework);
    }
    return Array.from(set).sort();
  }, [catalog.data]);

  const visibleModels = useMemo(() => {
    const all = catalog.data ?? [];
    let filtered = all;
    if (frameworkFilter !== "all") {
      filtered = filtered.filter((m) => m.framework === frameworkFilter);
    }
    // Sort: recommended (supports effectiveTask) first, alphabetical within.
    const isRecommended = (m: ModelCatalogEntry) =>
      Boolean(effectiveTask && (m.supported_tasks ?? []).includes(effectiveTask));
    return [...filtered].sort((a, b) => {
      const ar = isRecommended(a);
      const br = isRecommended(b);
      if (ar !== br) return ar ? -1 : 1;
      return displayName(a).localeCompare(displayName(b));
    });
  }, [catalog.data, effectiveTask, frameworkFilter]);

  const selectedEntry = (catalog.data ?? []).find((m) => m.id === modelCatalogId) ?? null;
  const selectedSupportsTask = Boolean(
    selectedEntry &&
      effectiveTask &&
      (selectedEntry.supported_tasks ?? []).includes(effectiveTask),
  );
  const selectedIsAutogluon = (selectedEntry?.framework ?? "").toLowerCase() === "autogluon";

  // AutoGluon runs its own internal HPO via presets — hide the toggle and
  // surface a hint instead.
  useEffect(() => {
    if (selectedIsAutogluon && hpoEnabled) setHpoEnabled(false);
  }, [selectedIsAutogluon, hpoEnabled, setHpoEnabled]);

  const canContinue = Boolean(
    modelCatalogId && effectiveTask && selectedSupportsTask,
  );

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
        <>
          <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
            <div className="flex flex-col gap-2">
              <span className="text-xs font-semibold uppercase tracking-[0.08em] text-fg2">
                Task
              </span>
              <div role="tablist" className="inline-flex overflow-hidden rounded-pill border border-[color:var(--border-primary)] text-[11px]">
                {(Object.keys(TASK_LABELS) as TaskKind[]).map((k) => (
                  <button
                    key={k}
                    type="button"
                    onClick={() => setTask(k)}
                    className={cn(
                      "px-3 py-1.5 font-semibold uppercase tracking-[0.08em] transition-colors",
                      effectiveTask === k
                        ? "bg-primary text-white"
                        : "bg-bg text-fg2 hover:text-fg1",
                    )}
                  >
                    {TASK_LABELS[k]}
                  </button>
                ))}
              </div>
              <span className="text-xs text-fg3">
                {effectiveTask
                  ? `Inferred from target "${target ?? "—"}" — override if needed.`
                  : "Pick a target column in the previous step to get a recommendation."}
              </span>
            </div>

            <div className="flex flex-col gap-2">
              <span className="text-xs font-semibold uppercase tracking-[0.08em] text-fg2">
                Framework
              </span>
              <select
                value={frameworkFilter}
                onChange={(ev) => setFrameworkFilter(ev.target.value)}
                className="rounded border border-[color:var(--border)] bg-bg px-3 py-1.5 text-sm focus:border-primary focus:outline-none"
              >
                <option value="all">All frameworks</option>
                {frameworks.map((f) => (
                  <option key={f} value={f}>
                    {f}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
            {catalog.isPending ? (
              <p className="text-sm text-fg3">{t("common.loading")}…</p>
            ) : visibleModels.length === 0 ? (
              <p className="text-sm text-fg3">No models match the filters.</p>
            ) : (
              visibleModels.map((m) => {
                const compatible = Boolean(
                  effectiveTask && (m.supported_tasks ?? []).includes(effectiveTask),
                );
                return (
                  <ModelPickerCard
                    key={m.id}
                    entry={m}
                    selected={modelCatalogId === m.id}
                    recommended={compatible}
                    compatible={compatible}
                    onSelect={() => setModelCatalogId(m.id)}
                  />
                );
              })
            )}
          </div>

          {selectedEntry && !selectedSupportsTask ? (
            <p className="text-xs font-semibold text-danger">
              {displayName(selectedEntry)} does not support{" "}
              {effectiveTask ? TASK_LABELS[effectiveTask] : "the selected task"}. Pick a
              different model or switch the task.
            </p>
          ) : null}

          <div className="rounded-lg border border-[color:var(--border)] bg-bg-muted/40 p-4">
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="text-sm font-semibold text-fg1">Hyperparameter optimization</div>
                <div className="mt-1 text-xs text-fg2">
                  {selectedIsAutogluon
                    ? "AutoGluon runs its own internal HPO — choose a preset and time limit on the next step."
                    : "When enabled, you'll set min/max ranges per hyperparameter and the trainer runs an Optuna search. Either/or with fixed hyperparameters."}
                </div>
              </div>
              {!selectedIsAutogluon ? (
                <label className="inline-flex cursor-pointer items-center gap-2">
                  <input
                    type="checkbox"
                    className="h-4 w-4 accent-[color:var(--primary)]"
                    checked={hpoEnabled}
                    onChange={(ev) => setHpoEnabled(ev.target.checked)}
                  />
                  <span className="text-xs font-semibold text-fg1">HPO</span>
                </label>
              ) : null}
            </div>
          </div>
        </>
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

      <div className="flex justify-between">
        <Button variant="ghost" onClick={prev}>
          Back
        </Button>
        <Button disabled={!canContinue} onClick={next}>
          Continue →
        </Button>
      </div>
    </div>
  );
}
