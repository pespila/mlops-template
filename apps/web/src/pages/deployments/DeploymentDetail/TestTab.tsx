import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { GlassCard } from "@/components/molecules/GlassCard";
import { SchemaDrivenForm } from "@/components/organisms/SchemaDrivenForm";
import { api, type PredictionResponse } from "@/lib/api/client";

interface TestTabProps {
  deploymentId: string;
}

export function TestTab({ deploymentId }: TestTabProps) {
  const [response, setResponse] = useState<PredictionResponse | null>(null);
  const [errorText, setErrorText] = useState<string | null>(null);

  const schema = useQuery({
    queryKey: ["deployments", deploymentId, "schema"],
    queryFn: () => api.deployments.schema(deploymentId),
    enabled: Boolean(deploymentId),
  });

  const predict = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      api.deployments.predict(deploymentId, body),
    onSuccess: (data) => {
      setResponse(data);
      setErrorText(null);
    },
    onError: (err) => {
      setResponse(null);
      setErrorText(err instanceof Error ? err.message : "Request failed");
    },
  });

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
      <GlassCard>
        <h2 className="font-display text-xl font-bold text-fg1">Input</h2>
        <p className="mt-1 text-sm text-fg2">
          Fields are generated from the deployment&apos;s input schema.
        </p>
        <div className="mt-4">
          {schema.isPending ? (
            <p className="text-sm text-fg3">Loading schema…</p>
          ) : schema.isError ? (
            <p className="text-sm text-danger">Could not load schema.</p>
          ) : (
            <SchemaDrivenForm
              schema={schema.data}
              onSubmit={(values) => predict.mutateAsync(values)}
              submitLabel="Send request →"
              busy={predict.isPending}
            />
          )}
        </div>
      </GlassCard>

      <GlassCard>
        <h2 className="font-display text-xl font-bold text-fg1">Response</h2>
        {errorText ? (
          <p className="mt-3 rounded border border-[color:var(--border)] bg-teal-50 px-3 py-2 text-xs font-semibold text-danger">
            {errorText}
          </p>
        ) : null}
        {response ? (
          <div className="mt-3 flex flex-col gap-3">
            {response.prediction_label ? (
              <div className="rounded border border-primary bg-[color:var(--primary-soft)] px-4 py-3">
                <div className="text-xs font-semibold uppercase tracking-[0.08em] text-fg2">
                  Predicted label
                </div>
                <div className="mt-1 font-display text-2xl font-bold text-primary">
                  {response.prediction_label}
                </div>
                <div className="mt-1 font-mono text-[11px] text-fg3">
                  raw output: {String(response.prediction)}
                </div>
              </div>
            ) : null}
            {response.target_classes && response.target_classes.length > 0 ? (
              <div className="text-xs text-fg3">
                <span className="font-semibold uppercase tracking-[0.08em]">Classes:</span>{" "}
                {response.target_classes.join(" · ")}
              </div>
            ) : null}
            <div className="overflow-hidden rounded border border-[color:var(--border)] bg-teal-50">
              <pre className="m-0 overflow-x-auto p-4 font-mono text-xs text-teal-900">
                {JSON.stringify(response, null, 2)}
              </pre>
            </div>
          </div>
        ) : !errorText ? (
          <p className="mt-3 text-sm text-fg3">No response yet. Submit the form to test.</p>
        ) : null}
      </GlassCard>
    </div>
  );
}
