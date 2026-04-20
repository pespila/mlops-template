import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { Button } from "@/components/atoms/Button";
import { useT } from "@/i18n";
import { api, type ModelCatalogEntry } from "@/lib/api/client";
import { cn } from "@/lib/cn";
import { useWizardStore, type HpoSearchEntry } from "@/state/wizardStore";

/**
 * Catalog hyperparameter spec shape (mirrors backend
 * `signature_json.hyperparams[name]`). Kept permissive here because several
 * optional fields (min/max/log/choices) only apply to a subset of types.
 */
interface HyperparamSpec {
  type: "int" | "float" | "bool" | "enum";
  default: number | boolean | string;
  min?: number;
  max?: number;
  log?: boolean;
  choices?: Array<string | number | boolean>;
}

function specsFromEntry(entry: ModelCatalogEntry | null): Record<string, HyperparamSpec> {
  if (!entry) return {};
  const raw = (entry.hyperparam_schema as Record<string, unknown>)?.hyperparams;
  if (!raw || typeof raw !== "object") return {};
  return raw as Record<string, HyperparamSpec>;
}

function PointField({
  name,
  spec,
  value,
  onChange,
}: {
  name: string;
  spec: HyperparamSpec;
  value: number | string | boolean;
  onChange: (v: number | string | boolean) => void;
}) {
  const inputCls =
    "w-full rounded border border-[color:var(--border)] bg-bg px-3 py-2 text-sm text-fg1 focus:border-primary focus:outline-none";

  if (spec.type === "bool") {
    return (
      <input
        type="checkbox"
        className="h-5 w-5 accent-[color:var(--primary)]"
        checked={Boolean(value)}
        onChange={(ev) => onChange(ev.target.checked)}
      />
    );
  }
  if (spec.type === "enum" && spec.choices) {
    return (
      <select
        className={inputCls}
        value={String(value)}
        onChange={(ev) => onChange(ev.target.value)}
      >
        {spec.choices.map((c) => (
          <option key={String(c)} value={String(c)}>
            {String(c)}
          </option>
        ))}
      </select>
    );
  }
  const isInt = spec.type === "int";
  return (
    <input
      type="number"
      step={isInt ? 1 : "any"}
      min={spec.min}
      max={spec.max}
      value={value === "" ? "" : Number(value)}
      onChange={(ev) => {
        const raw = ev.target.value;
        if (raw === "") return onChange("");
        onChange(isInt ? parseInt(raw, 10) : parseFloat(raw));
      }}
      className={inputCls}
    />
  );
}

function RangeField({
  name,
  spec,
  entry,
  onChange,
}: {
  name: string;
  spec: HyperparamSpec;
  entry: HpoSearchEntry | undefined;
  onChange: (e: HpoSearchEntry) => void;
}) {
  const inputCls =
    "w-full rounded border border-[color:var(--border)] bg-bg px-2 py-1.5 text-sm text-fg1 focus:border-primary focus:outline-none";

  if (spec.type === "bool") {
    // Tri-state: search {True, False} together → categorical over two choices.
    const current = entry && entry.type === "categorical" ? entry.choices : [true, false];
    return (
      <div className="flex flex-wrap gap-3 text-xs">
        {[true, false].map((c) => (
          <label key={String(c)} className="inline-flex items-center gap-1.5">
            <input
              type="checkbox"
              className="h-4 w-4 accent-[color:var(--primary)]"
              checked={current.includes(c)}
              onChange={(ev) => {
                const nextChoices = ev.target.checked
                  ? Array.from(new Set([...current, c]))
                  : current.filter((x) => x !== c);
                onChange({ type: "categorical", choices: nextChoices });
              }}
            />
            <span className="font-mono text-fg1">{String(c)}</span>
          </label>
        ))}
      </div>
    );
  }
  if (spec.type === "enum" && spec.choices) {
    const current =
      entry && entry.type === "categorical" ? entry.choices : [...spec.choices];
    return (
      <div className="flex flex-wrap gap-2 text-xs">
        {spec.choices.map((c) => {
          const on = current.includes(c);
          return (
            <button
              key={String(c)}
              type="button"
              onClick={() => {
                const nextChoices = on
                  ? current.filter((x) => x !== c)
                  : Array.from(new Set([...current, c]));
                onChange({ type: "categorical", choices: nextChoices });
              }}
              className={cn(
                "rounded-pill border px-2.5 py-0.5 font-mono",
                on
                  ? "border-primary bg-[color:var(--primary-soft)] text-fg1"
                  : "border-[color:var(--border)] text-fg2",
              )}
            >
              {String(c)}
            </button>
          );
        })}
      </div>
    );
  }
  const typeTag = spec.type === "int" ? "int" : "float";
  const current =
    entry && (entry.type === "int" || entry.type === "float")
      ? entry
      : {
          type: typeTag,
          low: spec.min ?? (typeTag === "int" ? 1 : 0),
          high: spec.max ?? (typeTag === "int" ? 100 : 1),
          log: Boolean(spec.log),
        } as HpoSearchEntry;
  const isInt = typeTag === "int";
  return (
    <div className="grid grid-cols-3 items-center gap-2">
      <input
        type="number"
        step={isInt ? 1 : "any"}
        value={current.type !== "categorical" ? current.low : ""}
        onChange={(ev) => {
          const v = isInt ? parseInt(ev.target.value, 10) : parseFloat(ev.target.value);
          onChange({ ...current, low: v } as HpoSearchEntry);
        }}
        placeholder="min"
        className={inputCls}
      />
      <input
        type="number"
        step={isInt ? 1 : "any"}
        value={current.type !== "categorical" ? current.high : ""}
        onChange={(ev) => {
          const v = isInt ? parseInt(ev.target.value, 10) : parseFloat(ev.target.value);
          onChange({ ...current, high: v } as HpoSearchEntry);
        }}
        placeholder="max"
        className={inputCls}
      />
      <label className="inline-flex items-center gap-1.5 text-xs text-fg2">
        <input
          type="checkbox"
          className="h-4 w-4 accent-[color:var(--primary)]"
          checked={Boolean(current.type !== "categorical" && current.log)}
          onChange={(ev) =>
            onChange({ ...current, log: ev.target.checked } as HpoSearchEntry)
          }
        />
        log
      </label>
    </div>
  );
}

export function StepHyperparameters() {
  const t = useT();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [experimentMode, setExperimentMode] = useState<"existing" | "new">("existing");

  const datasetId = useWizardStore((s) => s.datasetId);
  const transforms = useWizardStore((s) => s.transforms);
  const target = useWizardStore((s) => s.target);
  const sensitiveFeatures = useWizardStore((s) => s.sensitiveFeatures);
  const split = useWizardStore((s) => s.split);
  const modelCatalogId = useWizardStore((s) => s.modelCatalogId);
  const hyperparams = useWizardStore((s) => s.hyperparams);
  const setHyperparams = useWizardStore((s) => s.setHyperparams);
  const hpoEnabled = useWizardStore((s) => s.hpoEnabled);
  const hpoSearchSpace = useWizardStore((s) => s.hpoSearchSpace);
  const setHpoSearchSpace = useWizardStore((s) => s.setHpoSearchSpace);
  const hpoTrials = useWizardStore((s) => s.hpoTrials);
  const setHpoTrials = useWizardStore((s) => s.setHpoTrials);
  const hpoTimeoutSec = useWizardStore((s) => s.hpoTimeoutSec);
  const setHpoTimeoutSec = useWizardStore((s) => s.setHpoTimeoutSec);
  const task = useWizardStore((s) => s.task);
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

  const selectedEntry = useMemo(
    () => (catalog.data ?? []).find((m) => m.id === modelCatalogId) ?? null,
    [catalog.data, modelCatalogId],
  );

  const specs = useMemo(() => specsFromEntry(selectedEntry), [selectedEntry]);

  // Initialise `hyperparams` with the catalog defaults the first time this
  // model's schema is seen. If the user had already set some, keep them.
  useEffect(() => {
    if (!selectedEntry || Object.keys(specs).length === 0) return;
    const needsInit = Object.keys(specs).some((k) => hyperparams[k] === undefined);
    if (!needsInit) return;
    const merged: Record<string, unknown> = { ...hyperparams };
    for (const [k, spec] of Object.entries(specs)) {
      if (merged[k] === undefined) merged[k] = spec.default;
    }
    setHyperparams(merged);
  }, [selectedEntry, specs, hyperparams, setHyperparams]);

  const startRun = useMutation({
    mutationFn: async () => {
      if (!datasetId || !target || !modelCatalogId) {
        throw new Error("Wizard incomplete");
      }
      let expId = experimentMode === "existing" ? experimentId : null;
      if (!expId) {
        const exp = await api.experiments.create({
          name: experimentName.trim() || `Experiment ${new Date().toISOString().slice(0, 16)}`,
        });
        expId = exp.id;
      }

      const kindToOp: Record<string, string> = {
        drop: "drop",
        standardize: "standard_scale",
        "one-hot": "one_hot",
        "impute-mean": "impute_mean",
        "impute-median": "impute_median",
        "impute-mode": "impute_mode",
      };
      const transformList = transforms
        .filter((tr) => tr.feature !== target && kindToOp[tr.kind])
        .map((tr) => ({ column: tr.feature, op: kindToOp[tr.kind] }));

      const splitFractions = {
        train: split.train / 100,
        val: split.val / 100,
        test: split.test / 100,
      };

      const payload: Record<string, unknown> = {
        experiment_id: expId,
        dataset_id: datasetId,
        transform_config: {
          target,
          transforms: transformList,
          split: splitFractions,
          sensitive_features: sensitiveFeatures,
        },
        model_catalog_id: modelCatalogId,
        task,
      };

      if (hpoEnabled) {
        payload.hpo = {
          enabled: true,
          n_trials: hpoTrials,
          timeout_sec: hpoTimeoutSec,
          search_space: hpoSearchSpace,
        };
        // HPO path: fixed hyperparameters are empty by contract (either/or).
        payload.hyperparams = {};
      } else {
        payload.hyperparams = hyperparams;
      }

      const run = await api.runs.create(payload);
      return { run, experimentId: expId };
    },
    onSuccess: ({ run }) => {
      reset();
      navigate(`/experiments/runs/${run.id}`);
    },
  });

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h2 className="font-display text-2xl font-bold text-fg1">Hyperparameters</h2>
        <p className="mt-1 text-sm text-fg2">
          {hpoEnabled
            ? "Set a search range per tunable hyperparameter. The trainer will run an Optuna search and return the best model."
            : "Defaults come from the library; override any field you want to tune."}
        </p>
      </div>

      {!selectedEntry ? (
        <p className="text-sm text-fg3">No model selected. Go back to the previous step.</p>
      ) : Object.keys(specs).length === 0 ? (
        <p className="text-sm text-fg3">This model has no declared hyperparameters.</p>
      ) : (
        <div className="flex flex-col gap-4">
          {Object.entries(specs).map(([name, spec]) => (
            <div
              key={name}
              className="grid grid-cols-[minmax(180px,220px)_1fr] items-center gap-4"
            >
              <div>
                <div className="text-xs font-semibold uppercase tracking-[0.08em] text-fg2">
                  {name}
                </div>
                <div className="text-[10px] font-mono text-fg3">
                  {spec.type}
                  {spec.min !== undefined ? ` · ≥${spec.min}` : ""}
                  {spec.max !== undefined ? ` · ≤${spec.max}` : ""}
                  {spec.log ? " · log" : ""}
                </div>
              </div>
              {hpoEnabled ? (
                <RangeField
                  name={name}
                  spec={spec}
                  entry={hpoSearchSpace[name]}
                  onChange={(entry) =>
                    setHpoSearchSpace({ ...hpoSearchSpace, [name]: entry })
                  }
                />
              ) : (
                <PointField
                  name={name}
                  spec={spec}
                  value={
                    (hyperparams[name] as number | string | boolean | undefined) ??
                    (spec.default as number | string | boolean)
                  }
                  onChange={(v) => setHyperparams({ ...hyperparams, [name]: v })}
                />
              )}
            </div>
          ))}

          {hpoEnabled ? (
            <div className="mt-2 grid grid-cols-1 gap-3 rounded-lg border border-[color:var(--border)] bg-bg-muted/40 p-4 md:grid-cols-2">
              <label className="flex flex-col gap-1 text-xs">
                <span className="font-semibold uppercase tracking-[0.08em] text-fg2">
                  Trials
                </span>
                <input
                  type="number"
                  min={2}
                  max={500}
                  value={hpoTrials}
                  onChange={(ev) =>
                    setHpoTrials(Math.max(2, parseInt(ev.target.value, 10) || 0))
                  }
                  className="rounded border border-[color:var(--border)] bg-bg px-2 py-1.5 text-sm focus:border-primary focus:outline-none"
                />
              </label>
              <label className="flex flex-col gap-1 text-xs">
                <span className="font-semibold uppercase tracking-[0.08em] text-fg2">
                  Timeout (seconds)
                </span>
                <input
                  type="number"
                  min={60}
                  max={7200}
                  value={hpoTimeoutSec}
                  onChange={(ev) =>
                    setHpoTimeoutSec(Math.max(60, parseInt(ev.target.value, 10) || 0))
                  }
                  className="rounded border border-[color:var(--border)] bg-bg px-2 py-1.5 text-sm focus:border-primary focus:outline-none"
                />
              </label>
            </div>
          ) : null}
        </div>
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
