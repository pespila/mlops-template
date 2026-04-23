import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo } from "react";

import { Button } from "@/components/atoms/Button";
import {
  FeatureProfilePanel,
  type CategoricalEncoder,
} from "@/components/organisms/FeatureProfilePanel";
import { useT } from "@/i18n";
import { api, type FeatureSchema, type TaskFamily } from "@/lib/api/client";
import { useWizardStore, type FeatureTransformKind } from "@/state/wizardStore";

const DEFAULT_TRANSFORM: Record<FeatureSchema["type"], FeatureTransformKind> = {
  numeric: "standardize",
  categorical: "one-hot",
  boolean: "keep",
  // Datetime columns are expanded (year/month/dow/…) by the trainer's
  // smart-default branch when no explicit op is sent. "keep" is the wizard
  // marker for "include but don't prescribe a transform" — the trainer
  // handles the rest via coarse_schema + auto_datefeat_*.
  datetime: "keep",
  text: "drop",
};

const ENCODER_TO_KIND: Record<CategoricalEncoder, FeatureTransformKind> = {
  "one-hot": "one-hot",
  label: "label",
  ordinal: "ordinal",
};
const KIND_TO_ENCODER: Partial<Record<FeatureTransformKind, CategoricalEncoder>> = {
  "one-hot": "one-hot",
  label: "label",
  ordinal: "ordinal",
};

/**
 * Columns whose *type* is fundamentally compatible with the selected task.
 * "Unsuitable" here means "pandas will give the model something it can't
 * learn from well" — text columns in forecasting, datetime-only columns in
 * clustering without extraction, etc. We surface a red "!" but still let
 * the user keep them selected; the trainer either expands them (datetime)
 * or drops them (text) via the smart defaults.
 */
function isColumnSuitable(type: FeatureSchema["type"], family: TaskFamily | null): boolean {
  if (!family) return true;
  if (family === "forecasting") {
    return type === "numeric" || type === "datetime";
  }
  if (family === "clustering") {
    return type === "numeric" || type === "categorical" || type === "boolean";
  }
  if (family === "recommender") {
    // Recommender uses user/item/rating only — feature columns don't feed the model.
    return type === "numeric" || type === "categorical" || type === "boolean";
  }
  // supervised — all types feed into the preprocessor (text→dropped, date→expanded).
  return true;
}

export function StepFeatures() {
  const t = useT();
  const datasetId = useWizardStore((s) => s.datasetId);
  const taskFamily = useWizardStore((s) => s.taskFamily);
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
    () => new Set(transforms.filter((tr) => tr.kind === "drop").map((tr) => tr.feature)),
    [transforms],
  );

  const suitableColumns = useMemo(() => {
    if (!schema.data) return undefined;
    return new Set(
      schema.data
        .filter((c) => isColumnSuitable(c.type, taskFamily))
        .map((c) => c.name),
    );
  }, [schema.data, taskFamily]);

  const encoderChoice = useMemo<Record<string, CategoricalEncoder>>(() => {
    const acc: Record<string, CategoricalEncoder> = {};
    for (const tr of transforms) {
      const mapped = KIND_TO_ENCODER[tr.kind];
      if (mapped) acc[tr.feature] = mapped;
    }
    return acc;
  }, [transforms]);

  // "Overlay" the current (exclusion-aware) column list so bulk actions only
  // touch what's shown. The store is the source of truth; we just rebuild it.
  const applyBulkInclude = (included: boolean) => {
    if (!schema.data) return;
    setTransforms(
      schema.data.map((col) => ({
        feature: col.name,
        kind: included ? DEFAULT_TRANSFORM[col.type] : "drop",
      })),
    );
  };

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h2 className="font-display text-2xl font-bold text-fg1">Choose feature transforms</h2>
        <p className="mt-1 text-sm text-fg2">
          Uncheck any column to skip it. Numeric features standardize, categorical features one-hot
          encode by default; override the type if inference missed. Columns marked with a red
          <span className="mx-1 inline-flex h-3 w-3 items-center justify-center rounded-full bg-[color:var(--danger,#dc2626)] text-[9px] font-bold leading-none text-white">
            !
          </span>
          aren't ideal for the selected task but stay selectable.
        </p>
      </div>

      {schema.data ? (
        <FeatureProfilePanel
          schema={schema.data}
          excluded={excluded}
          suitableColumns={suitableColumns}
          unsuitableHint={t("wizard.notSuitedForTask")}
          onToggleInclude={(name, included) => {
            const col = schema.data?.find((c) => c.name === name);
            const nextKind: FeatureTransformKind = included
              ? (col ? DEFAULT_TRANSFORM[col.type] : "keep")
              : "drop";
            setTransform(name, nextKind);
          }}
          onSelectAll={() => applyBulkInclude(true)}
          onDeselectAll={() => applyBulkInclude(false)}
          onChange={(name) => {
            const col = schema.data?.find((c) => c.name === name);
            if (col) setTransform(name, DEFAULT_TRANSFORM[col.type]);
          }}
          encoderChoice={encoderChoice}
          onEncoderChange={(name, encoder) => {
            setTransform(name, ENCODER_TO_KIND[encoder]);
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
