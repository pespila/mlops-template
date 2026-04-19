import { useMemo } from "react";

import { CodeSnippetTabs } from "@/components/molecules/CodeSnippetTabs";
import { GlassCard } from "@/components/molecules/GlassCard";
import type { DeploymentRead } from "@/lib/api/client";
import { buildSnippets } from "@/lib/codegen/snippets";
import { formatRelative } from "@/lib/format";

interface OverviewTabProps {
  deployment: DeploymentRead;
}

export function OverviewTab({ deployment }: OverviewTabProps) {
  const snippets = useMemo(
    () =>
      buildSnippets({
        url: deployment.url,
        method: "POST",
        body: { feature_a: 1.23, feature_b: "value" },
      }),
    [deployment.url],
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
          {deployment.url}
        </div>
      </GlassCard>

      <GlassCard>
        <h2 className="font-display text-xl font-bold text-fg1">Call from your code</h2>
        <div className="mt-3">
          <CodeSnippetTabs snippets={snippets} />
        </div>
      </GlassCard>
    </div>
  );
}
