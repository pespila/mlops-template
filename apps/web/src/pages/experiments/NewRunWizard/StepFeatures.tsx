import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo } from "react";

import { Button } from "@/components/atoms/Button";
import { FeatureProfilePanel } from "@/components/organisms/FeatureProfilePanel";
import { api, type FeatureSchema } from "@/lib/api/client";
import { useWizardStore, type FeatureTransformKind } from "@/state/wizardStore";

const DEFAULT_TRANSFORM: Record<FeatureSchema["type"], FeatureTransformKind> = {
  numeric: "standardize",
  categorical: "one-hot",
  boolean: "keep",
  datetime: "keep",
  text: "drop",
};

export function StepFeatures() {
  const datasetId = useWizardStore((s) => s.datasetId);
  const transforms = useWizardStore((s) => s.transforms);
  const setTransforms = useWizardStore((s) => s.setTransforms);
  const setTransform = useWizardStore((s) => s.setTransform);
  const prev = useWizardStore((s) => s.prev);
  const next = useWizardStore((s) => s.next);

  const schema = useQuery({
    queryKey: ["datasets", datasetId, "schema"],
    queryFn: () => api.datasets.schema(datasetId!),
    enabled: Boolean(datasetId),
  });

  useEffect(() => {
    if (!schema.data || transforms.length > 0) return;
    setTransforms(
      schema.data.map((col) => ({ feature: col.name, kind: DEFAULT_TRANSFORM[col.type] })),
    );
  }, [schema.data, transforms.length, setTransforms]);

  const excluded = useMemo(
    () => new Set(transforms.filter((t) => t.kind === "drop").map((t) => t.feature)),
    [transforms],
  );

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h2 className="font-display text-2xl font-bold text-fg1">Choose feature transforms</h2>
        <p className="mt-1 text-sm text-fg2">
          Uncheck any column to skip it. Numeric features standardize, categorical features one-hot
          encode by default; override the type if inference missed.
        </p>
      </div>

      {schema.data ? (
        <FeatureProfilePanel
          schema={schema.data}
          excluded={excluded}
          onToggleInclude={(name, included) => {
            const col = schema.data?.find((c) => c.name === name);
            const nextKind: FeatureTransformKind = included
              ? (col ? DEFAULT_TRANSFORM[col.type] : "keep")
              : "drop";
            setTransform(name, nextKind);
          }}
          onChange={(name) => {
            const col = schema.data?.find((c) => c.name === name);
            if (col) setTransform(name, DEFAULT_TRANSFORM[col.type]);
          }}
        />
      ) : (
        <p className="text-sm text-fg3">Loading…</p>
      )}

      <div className="flex justify-between">
        <Button variant="ghost" onClick={prev}>
          Back
        </Button>
        <Button onClick={next}>Continue →</Button>
      </div>
    </div>
  );
}
