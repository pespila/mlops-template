import { useQuery } from "@tanstack/react-query";

import { Button } from "@/components/atoms/Button";
import { FeatureProfilePanel } from "@/components/organisms/FeatureProfilePanel";
import { api } from "@/lib/api/client";
import { useWizardStore } from "@/state/wizardStore";

export function StepProfile() {
  const datasetId = useWizardStore((s) => s.datasetId);
  const prev = useWizardStore((s) => s.prev);
  const next = useWizardStore((s) => s.next);

  const profile = useQuery({
    queryKey: ["datasets", datasetId, "profile"],
    queryFn: () => api.datasets.profile(datasetId!),
    enabled: Boolean(datasetId),
  });

  const schema = useQuery({
    queryKey: ["datasets", datasetId, "schema"],
    queryFn: () => api.datasets.schema(datasetId!),
    enabled: Boolean(datasetId),
  });

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h2 className="font-display text-2xl font-bold text-fg1">Review the data profile</h2>
        <p className="mt-1 text-sm text-fg2">
          Quick sanity check on row counts, missing cells, and inferred types.
        </p>
      </div>

      <dl className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <div className="rounded-md border border-[color:var(--border)] bg-bg p-4">
          <dt className="text-xs text-fg3">Rows</dt>
          <dd className="mt-1 font-mono text-xl font-bold text-fg1">
            {profile.data?.row_count ?? "—"}
          </dd>
        </div>
        <div className="rounded-md border border-[color:var(--border)] bg-bg p-4">
          <dt className="text-xs text-fg3">Columns</dt>
          <dd className="mt-1 font-mono text-xl font-bold text-fg1">
            {profile.data?.column_count ?? "—"}
          </dd>
        </div>
        <div className="rounded-md border border-[color:var(--border)] bg-bg p-4">
          <dt className="text-xs text-fg3">Missing cells</dt>
          <dd className="mt-1 font-mono text-xl font-bold text-fg1">
            {profile.data?.missing_cells ?? "—"}
          </dd>
        </div>
        <div className="rounded-md border border-[color:var(--border)] bg-bg p-4">
          <dt className="text-xs text-fg3">Duplicate rows</dt>
          <dd className="mt-1 font-mono text-xl font-bold text-fg1">
            {profile.data?.duplicate_rows ?? "—"}
          </dd>
        </div>
      </dl>

      {schema.data ? <FeatureProfilePanel schema={schema.data} readOnly /> : null}

      <div className="flex justify-between">
        <Button variant="ghost" onClick={prev}>
          Back
        </Button>
        <Button onClick={next}>Continue →</Button>
      </div>
    </div>
  );
}
