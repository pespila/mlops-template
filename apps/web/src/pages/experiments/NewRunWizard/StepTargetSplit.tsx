import { useQuery } from "@tanstack/react-query";

import { Button } from "@/components/atoms/Button";
import { ThreeWaySplitSlider } from "@/components/molecules/ThreeWaySplitSlider";
import { api } from "@/lib/api/client";
import { useWizardStore } from "@/state/wizardStore";

export function StepTargetSplit() {
  const datasetId = useWizardStore((s) => s.datasetId);
  const target = useWizardStore((s) => s.target);
  const setTarget = useWizardStore((s) => s.setTarget);
  const sensitiveFeatures = useWizardStore((s) => s.sensitiveFeatures);
  const toggleSensitive = useWizardStore((s) => s.toggleSensitiveFeature);
  const split = useWizardStore((s) => s.split);
  const setSplit = useWizardStore((s) => s.setSplit);
  const prev = useWizardStore((s) => s.prev);
  const next = useWizardStore((s) => s.next);
  const taskFamily = useWizardStore((s) => s.taskFamily);
  const timeColumn = useWizardStore((s) => s.timeColumn);
  const setTimeColumn = useWizardStore((s) => s.setTimeColumn);
  const forecastHorizon = useWizardStore((s) => s.forecastHorizon);
  const setForecastHorizon = useWizardStore((s) => s.setForecastHorizon);
  const userColumn = useWizardStore((s) => s.userColumn);
  const setUserColumn = useWizardStore((s) => s.setUserColumn);
  const itemColumn = useWizardStore((s) => s.itemColumn);
  const setItemColumn = useWizardStore((s) => s.setItemColumn);
  const ratingColumn = useWizardStore((s) => s.ratingColumn);
  const setRatingColumn = useWizardStore((s) => s.setRatingColumn);
  const feedbackType = useWizardStore((s) => s.feedbackType);
  const setFeedbackType = useWizardStore((s) => s.setFeedbackType);

  const schema = useQuery({
    queryKey: ["datasets", datasetId, "schema"],
    queryFn: () => api.datasets.schema(datasetId!),
    enabled: Boolean(datasetId),
  });

  const columns = schema.data ?? [];
  const totalOk = split.train + split.val + split.test === 100;
  const family = taskFamily ?? "supervised";

  // Validation by family --------------------------------------------------
  const canContinue =
    family === "supervised"
      ? Boolean(target) && totalOk
      : family === "forecasting"
        ? Boolean(timeColumn) && Boolean(target) && forecastHorizon > 0
        : family === "recommender"
          ? Boolean(userColumn) && Boolean(itemColumn) && Boolean(ratingColumn)
          : true; // clustering — nothing required here

  const selectCls =
    "w-full max-w-sm rounded border border-[color:var(--border)] bg-bg px-3 py-2 text-sm " +
    "focus:border-primary focus:outline-none";

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h2 className="font-display text-2xl font-bold text-fg1">Roles and split</h2>
        <p className="mt-1 text-sm text-fg2">
          {family === "clustering"
            ? "No target needed — clustering groups rows by their feature columns."
            : family === "forecasting"
              ? "Pick the time axis, the value to forecast, and the horizon."
              : family === "recommender"
                ? "Pick the user, item, and rating columns. Choose explicit or implicit feedback."
                : "Pick the column to predict, then set train / validation / test percentages."}
        </p>
      </div>

      {family === "supervised" ? (
        <>
          <label className="flex flex-col gap-1.5">
            <span className="text-xs font-semibold uppercase tracking-[0.08em] text-fg2">
              Target column
            </span>
            <select
              value={target ?? ""}
              onChange={(ev) => setTarget(ev.target.value || null)}
              className={selectCls}
            >
              <option value="">Select a column…</option>
              {columns.map((c) => (
                <option key={c.name} value={c.name}>
                  {c.name} · {c.type}
                </option>
              ))}
            </select>
          </label>

          <div className="flex flex-col gap-2">
            <span className="text-xs font-semibold uppercase tracking-[0.08em] text-fg2">
              Sensitive features (optional)
            </span>
            <p className="text-xs text-fg3">
              Pick columns to compute a per-group bias report against. Leave empty to skip.
            </p>
            <div className="flex flex-wrap gap-2">
              {columns
                .filter((c) => c.name !== target)
                .map((c) => {
                  const on = sensitiveFeatures.includes(c.name);
                  return (
                    <button
                      key={c.name}
                      type="button"
                      onClick={() => toggleSensitive(c.name)}
                      className={
                        "rounded-pill border px-3 py-1 text-xs transition-colors " +
                        (on
                          ? "border-primary bg-[color:var(--primary-soft)] text-primary"
                          : "border-[color:var(--border)] bg-bg text-fg2 hover:text-fg1")
                      }
                    >
                      {c.name}
                      <span className="ml-1 text-[10px] text-fg3">· {c.type}</span>
                    </button>
                  );
                })}
            </div>
          </div>

          <div>
            <span className="text-xs font-semibold uppercase tracking-[0.08em] text-fg2">
              Train / Validation / Test
            </span>
            <div className="mt-3">
              <ThreeWaySplitSlider value={split} onChange={setSplit} />
            </div>
          </div>
        </>
      ) : null}

      {family === "forecasting" ? (
        <>
          <label className="flex flex-col gap-1.5">
            <span className="text-xs font-semibold uppercase tracking-[0.08em] text-fg2">
              Time column
            </span>
            <select
              value={timeColumn ?? ""}
              onChange={(ev) => setTimeColumn(ev.target.value || null)}
              className={selectCls}
            >
              <option value="">Select a column…</option>
              {columns.map((c) => (
                <option key={c.name} value={c.name}>
                  {c.name} · {c.type}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1.5">
            <span className="text-xs font-semibold uppercase tracking-[0.08em] text-fg2">
              Value column (what to forecast)
            </span>
            <select
              value={target ?? ""}
              onChange={(ev) => setTarget(ev.target.value || null)}
              className={selectCls}
            >
              <option value="">Select a column…</option>
              {columns
                .filter((c) => c.name !== timeColumn)
                .map((c) => (
                  <option key={c.name} value={c.name}>
                    {c.name} · {c.type}
                  </option>
                ))}
            </select>
          </label>
          <label className="flex flex-col gap-1.5">
            <span className="text-xs font-semibold uppercase tracking-[0.08em] text-fg2">
              Forecast horizon (steps ahead)
            </span>
            <input
              type="number"
              min={1}
              max={1000}
              value={forecastHorizon}
              onChange={(ev) => setForecastHorizon(Number(ev.target.value) || 1)}
              className={selectCls}
            />
          </label>
        </>
      ) : null}

      {family === "recommender" ? (
        <>
          <label className="flex flex-col gap-1.5">
            <span className="text-xs font-semibold uppercase tracking-[0.08em] text-fg2">
              User column
            </span>
            <select
              value={userColumn ?? ""}
              onChange={(ev) => setUserColumn(ev.target.value || null)}
              className={selectCls}
            >
              <option value="">Select a column…</option>
              {columns.map((c) => (
                <option key={c.name} value={c.name}>
                  {c.name} · {c.type}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1.5">
            <span className="text-xs font-semibold uppercase tracking-[0.08em] text-fg2">
              Item column
            </span>
            <select
              value={itemColumn ?? ""}
              onChange={(ev) => setItemColumn(ev.target.value || null)}
              className={selectCls}
            >
              <option value="">Select a column…</option>
              {columns
                .filter((c) => c.name !== userColumn)
                .map((c) => (
                  <option key={c.name} value={c.name}>
                    {c.name} · {c.type}
                  </option>
                ))}
            </select>
          </label>
          <label className="flex flex-col gap-1.5">
            <span className="text-xs font-semibold uppercase tracking-[0.08em] text-fg2">
              Rating / interaction column
            </span>
            <select
              value={ratingColumn ?? ""}
              onChange={(ev) => setRatingColumn(ev.target.value || null)}
              className={selectCls}
            >
              <option value="">Select a column…</option>
              {columns
                .filter((c) => c.name !== userColumn && c.name !== itemColumn)
                .map((c) => (
                  <option key={c.name} value={c.name}>
                    {c.name} · {c.type}
                  </option>
                ))}
            </select>
          </label>
          <label className="flex flex-col gap-1.5">
            <span className="text-xs font-semibold uppercase tracking-[0.08em] text-fg2">
              Feedback type
            </span>
            <div className="flex gap-2">
              {(["explicit", "implicit"] as const).map((f) => (
                <button
                  key={f}
                  type="button"
                  onClick={() => setFeedbackType(f)}
                  className={
                    "rounded-pill border px-3 py-1 text-xs transition-colors " +
                    (feedbackType === f
                      ? "border-primary bg-[color:var(--primary-soft)] text-primary"
                      : "border-[color:var(--border)] bg-bg text-fg2 hover:text-fg1")
                  }
                >
                  {f === "explicit" ? "Explicit (ratings)" : "Implicit (interactions)"}
                </button>
              ))}
            </div>
          </label>
        </>
      ) : null}

      {family === "clustering" ? (
        <div className="rounded border border-[color:var(--border)] bg-bg/60 p-4 text-sm text-fg2">
          Clustering uses the feature columns you configured on the previous step. New points at
          serving time are assigned to the nearest cluster.
        </div>
      ) : null}

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
