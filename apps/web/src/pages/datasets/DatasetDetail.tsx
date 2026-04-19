import { useQuery } from "@tanstack/react-query";
import { ArrowRight } from "lucide-react";
import { useParams } from "react-router-dom";

import { Button } from "@/components/atoms/Button";
import { GlassCard } from "@/components/molecules/GlassCard";
import { FeatureProfilePanel } from "@/components/organisms/FeatureProfilePanel";
import { api } from "@/lib/api/client";
import { formatBytes, formatRelative } from "@/lib/format";

export function DatasetDetail() {
  const { id = "" } = useParams<{ id: string }>();

  const dataset = useQuery({
    queryKey: ["datasets", id],
    queryFn: () => api.datasets.get(id),
    enabled: Boolean(id),
  });

  const schema = useQuery({
    queryKey: ["datasets", id, "schema"],
    queryFn: () => api.datasets.schema(id),
    enabled: Boolean(id),
  });

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6">
      <header className="flex items-start justify-between gap-4">
        <div>
          <h1 className="font-display text-display-lg font-extrabold tracking-tight text-fg1">
            {dataset.data?.name ?? "Dataset"}
          </h1>
          <p className="mt-2 text-sm text-fg2">
            {dataset.data
              ? `${dataset.data.row_count ?? 0} rows · ${dataset.data.column_count ?? 0} columns · ${formatBytes(dataset.data.size_bytes)} · created ${formatRelative(dataset.data.created_at)}`
              : "Loading…"}
          </p>
        </div>
        <Button
          asChild
          as="link"
          to={`/experiments/new?dataset=${id}`}
          rightIcon={<ArrowRight size={14} strokeWidth={2} />}
        >
          Use in new run
        </Button>
      </header>

      <GlassCard>
        <h2 className="font-display text-xl font-bold text-fg1">Columns</h2>
        <p className="mt-1 text-sm text-fg2">
          Inferred feature types, missing-value summary, and unique cardinality.
        </p>
        <div className="mt-5">
          {schema.isPending ? (
            <div className="text-sm text-fg3">Loading…</div>
          ) : schema.isError ? (
            <div className="text-sm text-danger">Could not load schema.</div>
          ) : (
            <FeatureProfilePanel schema={schema.data} readOnly />
          )}
        </div>
      </GlassCard>
    </div>
  );
}
