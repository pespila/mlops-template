import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";

import { CodeSnippetTabs } from "@/components/molecules/CodeSnippetTabs";
import { GlassCard } from "@/components/molecules/GlassCard";
import { api, type DeploymentRead, type JsonSchema } from "@/lib/api/client";
import { buildSnippets } from "@/lib/codegen/snippets";
import { formatRelative } from "@/lib/format";

interface OverviewTabProps {
  deployment: DeploymentRead;
}

function sampleValueForProp(spec: JsonSchema | undefined): unknown {
  if (!spec || typeof spec !== "object") return 0;
  if (Array.isArray(spec.enum) && spec.enum.length > 0) return spec.enum[0];
  const t = Array.isArray(spec.type) ? spec.type.find((x) => x !== "null") : spec.type;
  if (t === "integer") return 0;
  if (t === "number") return 0.0;
  if (t === "boolean") return false;
  return "";
}

function buildSampleBody(schema: JsonSchema | undefined): Record<string, unknown> {
  if (!schema || !schema.properties) return { feature_a: 1.23, feature_b: "value" };
  const out: Record<string, unknown> = {};
  for (const [name, spec] of Object.entries(schema.properties)) {
    out[name] = sampleValueForProp(spec);
  }
  return out;
}

export function OverviewTab({ deployment }: OverviewTabProps) {
  const schema = useQuery({
    queryKey: ["deployments", deployment.id, "schema"],
    queryFn: () => api.deployments.schema(deployment.id),
    enabled: Boolean(deployment.id),
  });

  const body = useMemo(() => buildSampleBody(schema.data), [schema.data]);

  // Build an absolute URL so curl / Python / JS snippets are copy-paste-ready.
  // Falls back to a relative path during SSR / tests where `window` is absent.
  const absoluteUrl = useMemo(() => {
    const origin = typeof window !== "undefined" ? window.location.origin : "";
    return origin ? `${origin}${deployment.url}` : deployment.url;
  }, [deployment.url]);

  const snippets = useMemo(
    () =>
      buildSnippets({
        url: absoluteUrl,
        method: "POST",
        body,
      }),
    [absoluteUrl, body],
  );

  return (
    <div className="flex flex-col gap-6">
      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <div className="rounded-md border border-[color:var(--border)] bg-bg p-4">
          <div className="text-xs uppercase tracking-[0.08em] text-fg3">Status</div>
          <div className="mt-1 text-sm font-semibold text-fg1">{deployment.status}</div>
        </div>
        <div className="rounded-md border border-[color:var(--border)] bg-bg p-4">
          <div className="text-xs uppercase tracking-[0.08em] text-fg3">Created</div>
          <div className="mt-1 text-sm text-fg1">{formatRelative(deployment.created_at)}</div>
        </div>
        <div className="rounded-md border border-[color:var(--border)] bg-bg p-4">
          <div className="text-xs uppercase tracking-[0.08em] text-fg3">Last called</div>
          <div className="mt-1 text-sm text-fg1">{formatRelative(deployment.last_called_at)}</div>
        </div>
      </div>

      <GlassCard>
        <h2 className="font-display text-xl font-bold text-fg1">Endpoint URL</h2>
        <p className="mt-1 text-sm text-fg2">POST predictions to this address.</p>
        <div className="mt-3 rounded border border-[color:var(--border)] bg-teal-50 px-3 py-2 font-mono text-xs text-teal-900">
          {absoluteUrl}
        </div>
      </GlassCard>

      <GlassCard>
        <h2 className="font-display text-xl font-bold text-fg1">Call from your code</h2>
        <p className="mt-1 text-sm text-fg2">
          {schema.data
            ? "Body is prefilled with one entry per feature from your model's input schema."
            : schema.isPending
              ? "Loading schema…"
              : "Using a generic example body."}
        </p>
        <div className="mt-3">
          <CodeSnippetTabs snippets={snippets} />
        </div>
      </GlassCard>
    </div>
  );
}
