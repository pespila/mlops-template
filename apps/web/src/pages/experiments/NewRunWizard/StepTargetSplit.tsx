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

  const schema = useQuery({
    queryKey: ["datasets", datasetId, "schema"],
    queryFn: () => api.datasets.schema(datasetId!),
    enabled: Boolean(datasetId),
  });

  const totalOk = split.train + split.val + split.test === 100;

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h2 className="font-display text-2xl font-bold text-fg1">Target column and data split</h2>
        <p className="mt-1 text-sm text-fg2">
          Pick the column to predict, then set train / validation / test percentages.
        </p>
      </div>

      <label className="flex flex-col gap-1.5">
        <span className="text-xs font-semibold uppercase tracking-[0.08em] text-fg2">
          Target column
        </span>
        <select
          value={target ?? ""}
          onChange={(ev) => setTarget(ev.target.value || null)}
          className="w-full max-w-sm rounded border border-[color:var(--border)] bg-bg px-3 py-2 text-sm focus:border-primary focus:outline-none"
        >
          <option value="">Select a column…</option>
          {(schema.data ?? []).map((c) => (
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
          {(schema.data ?? [])
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

      <div className="flex justify-between">
        <Button variant="ghost" onClick={prev}>
          Back
        </Button>
        <Button disabled={!target || !totalOk} onClick={next}>
          Continue →
        </Button>
      </div>
    </div>
  );
}
