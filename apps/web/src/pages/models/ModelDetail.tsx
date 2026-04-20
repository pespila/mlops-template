import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router-dom";

import { EditableHeading } from "@/components/molecules/EditableHeading";
import { GlassCard } from "@/components/molecules/GlassCard";
import { api, errorMessage } from "@/lib/api/client";
import { formatNumber, formatRelative } from "@/lib/format";

export function ModelDetail() {
  const { id = "" } = useParams<{ id: string }>();
  const qc = useQueryClient();
  const navigate = useNavigate();

  const model = useQuery({
    queryKey: ["models", id],
    queryFn: () => api.models.get(id),
    enabled: Boolean(id),
  });

  const rename = useMutation({
    mutationFn: (name: string) => api.models.update(id, { name }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["models", id] });
      qc.invalidateQueries({ queryKey: ["models"] });
    },
  });

  const remove = useMutation({
    mutationFn: () => api.models.remove(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["models"] });
      navigate("/models");
    },
  });

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6">
      <header className="flex flex-col gap-2">
        <EditableHeading
          value={model.data?.name ?? "Model"}
          onSave={(next) => rename.mutateAsync(next)}
          onDelete={() => remove.mutateAsync()}
          deleteConfirm="Delete this model and every version under it? This cannot be undone."
          saving={rename.isPending}
          deleting={remove.isPending}
        />
        {model.data?.description ? (
          <p className="max-w-xl text-sm text-fg2">{model.data.description}</p>
        ) : null}
        {remove.isError ? (
          <p className="max-w-xl text-sm text-danger">{errorMessage(remove.error)}</p>
        ) : null}
      </header>

      <GlassCard className="!p-0 overflow-hidden">
        {model.isPending ? (
          <div className="p-6 text-sm text-fg3">Loading…</div>
        ) : model.isError ? (
          <div className="p-6 text-sm text-danger">Could not load model.</div>
        ) : (model.data?.versions ?? []).length === 0 ? (
          <div className="p-8 text-center text-sm text-fg3">
            No versions — the run that produced this model may have been deleted.
          </div>
        ) : (
          <table className="w-full border-collapse text-sm">
            <thead className="bg-bg-muted text-left">
              <tr>
                <th className="px-6 py-3 text-xs font-semibold uppercase tracking-[0.08em] text-fg2">
                  Version
                </th>
                <th className="px-6 py-3 text-xs font-semibold uppercase tracking-[0.08em] text-fg2">
                  Kind
                </th>
                <th className="px-6 py-3 text-xs font-semibold uppercase tracking-[0.08em] text-fg2">
                  Run
                </th>
                <th className="px-6 py-3 text-xs font-semibold uppercase tracking-[0.08em] text-fg2">
                  Dataset
                </th>
                <th className="px-6 py-3 text-xs font-semibold uppercase tracking-[0.08em] text-fg2">
                  Metrics
                </th>
                <th className="px-6 py-3 text-xs font-semibold uppercase tracking-[0.08em] text-fg2">
                  Created
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[color:var(--border)]">
              {(model.data?.versions ?? []).map((v) => (
                <tr key={v.id} className="hover:bg-bg-muted/60">
                  <td className="px-6 py-3 font-mono text-xs text-fg1">v{v.version}</td>
                  <td className="px-6 py-3 text-xs text-fg2">
                    {v.model_catalog_name ?? v.model_kind}
                  </td>
                  <td className="px-6 py-3 font-mono text-xs">
                    <Link
                      to={`/experiments/runs/${v.run_id}`}
                      className="text-primary hover:underline"
                    >
                      {v.run_id.slice(0, 8)}…
                    </Link>
                  </td>
                  <td className="px-6 py-3 text-xs text-fg2">
                    {v.dataset_id ? (
                      <Link
                        to={`/datasets/${v.dataset_id}`}
                        className="hover:text-fg1 hover:underline"
                      >
                        {v.dataset_name ?? v.dataset_id.slice(0, 8)}
                      </Link>
                    ) : (
                      "—"
                    )}
                  </td>
                  <td className="px-6 py-3 text-xs text-fg2">
                    {Object.keys(v.metrics ?? {}).length === 0 ? (
                      <span className="text-fg3">—</span>
                    ) : (
                      <div className="flex flex-wrap gap-1.5">
                        {Object.entries(v.metrics ?? {}).map(([name, val]) => (
                          <span
                            key={name}
                            className="inline-flex items-center gap-1 rounded-pill bg-bg-muted px-2 py-0.5 font-mono text-[10px] text-fg1"
                            title={String(val)}
                          >
                            <span className="text-fg3">{name}</span>
                            <span>{formatNumber(val, 3)}</span>
                          </span>
                        ))}
                      </div>
                    )}
                  </td>
                  <td className="px-6 py-3 text-xs text-fg2">
                    {formatRelative(v.created_at)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </GlassCard>
    </div>
  );
}
