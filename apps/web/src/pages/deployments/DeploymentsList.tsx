import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Copy, Plus } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { RunStatusBadge, type RunStatus } from "@/components/atoms/RunStatusBadge";
import { Button } from "@/components/atoms/Button";
import { GlassCard } from "@/components/molecules/GlassCard";
import { Modal } from "@/components/molecules/Modal";
import { useT } from "@/i18n";
import { api, type DeploymentRead } from "@/lib/api/client";
import { formatRelative } from "@/lib/format";

function mapStatus(status: DeploymentRead["status"]): RunStatus {
  switch (status) {
    case "provisioning":
    case "deploying":
      return "building";
    case "ready":
    case "active":
      return "running";
    case "failed":
    case "unhealthy":
      return "failed";
    case "stopping":
    case "stopped":
    case "tearing_down":
      return "cancelled";
    default:
      return "queued";
  }
}

function EndpointCell({ url }: { url: string }) {
  const [copied, setCopied] = useState(false);
  const copy = async (ev: React.MouseEvent) => {
    ev.stopPropagation();
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* ignore */
    }
  };
  return (
    <div className="flex items-center gap-2">
      <code className="max-w-[24rem] truncate font-mono text-xs text-teal-900">
        {url}
      </code>
      <button
        type="button"
        onClick={copy}
        className="inline-flex items-center gap-1 rounded px-2 py-1 text-xs font-semibold text-fg2 hover:bg-bg-muted hover:text-fg1"
      >
        {copied ? <Check size={12} strokeWidth={2} /> : <Copy size={12} strokeWidth={2} />}
      </button>
    </div>
  );
}

function NewDeploymentForm({ onClose }: { onClose: () => void }) {
  const t = useT();
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [modelId, setModelId] = useState("");
  const [modelVersionId, setModelVersionId] = useState("");

  const models = useQuery({ queryKey: ["models"], queryFn: () => api.models.list() });
  const model = useQuery({
    queryKey: ["models", modelId],
    queryFn: () => api.models.get(modelId),
    enabled: Boolean(modelId),
  });

  const create = useMutation({
    mutationFn: () =>
      api.deployments.create({ model_version_id: modelVersionId, name: name.trim() }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["deployments"] });
      onClose();
    },
  });

  return (
    <form
      className="flex flex-col gap-4"
      onSubmit={(ev) => {
        ev.preventDefault();
        if (modelVersionId && name.trim()) create.mutate();
      }}
    >
      <label className="flex flex-col gap-1.5">
        <span className="text-xs font-semibold uppercase tracking-[0.08em] text-fg2">
          Deployment name
        </span>
        <input
          value={name}
          onChange={(ev) => setName(ev.target.value)}
          placeholder="churn-prod"
          className="rounded border border-[color:var(--border)] bg-bg px-3 py-2 text-sm focus:border-primary focus:outline-none"
        />
      </label>
      <label className="flex flex-col gap-1.5">
        <span className="text-xs font-semibold uppercase tracking-[0.08em] text-fg2">
          Model
        </span>
        <select
          value={modelId}
          onChange={(ev) => {
            setModelId(ev.target.value);
            setModelVersionId("");
          }}
          className="rounded border border-[color:var(--border)] bg-bg px-3 py-2 text-sm focus:border-primary focus:outline-none"
        >
          <option value="">Select a model…</option>
          {(models.data ?? []).map((m) => (
            <option key={m.id} value={m.id}>
              {m.name}
            </option>
          ))}
        </select>
      </label>
      <label className="flex flex-col gap-1.5">
        <span className="text-xs font-semibold uppercase tracking-[0.08em] text-fg2">
          Version
        </span>
        <select
          value={modelVersionId}
          onChange={(ev) => setModelVersionId(ev.target.value)}
          disabled={!modelId || !model.data}
          className="rounded border border-[color:var(--border)] bg-bg px-3 py-2 text-sm focus:border-primary focus:outline-none disabled:opacity-50"
        >
          <option value="">Select a version…</option>
          {(model.data?.versions ?? []).map((v) => (
            <option key={v.id} value={v.id}>
              v{v.version} · {v.model_kind}
            </option>
          ))}
        </select>
      </label>
      <div className="flex justify-end gap-2">
        <Button variant="ghost" onClick={onClose} type="button">
          {t("common.cancel")}
        </Button>
        <Button type="submit" disabled={create.isPending || !modelVersionId || !name.trim()}>
          Deploy →
        </Button>
      </div>
    </form>
  );
}

export function DeploymentsList() {
  const t = useT();
  const navigate = useNavigate();
  const [newOpen, setNewOpen] = useState(false);
  const deployments = useQuery({
    queryKey: ["deployments"],
    queryFn: () => api.deployments.list(),
  });

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6">
      <header className="flex items-start justify-between gap-4">
        <div>
          <h1 className="font-display text-display-lg font-extrabold tracking-tight text-fg1">
            {t("deployments.title")}
          </h1>
          <p className="mt-2 max-w-xl text-fg2">{t("deployments.subtitle")}</p>
        </div>
        <Button leftIcon={<Plus size={16} strokeWidth={2} />} onClick={() => setNewOpen(true)}>
          {t("deployments.newCta")}
        </Button>
      </header>

      <GlassCard className="!p-0 overflow-hidden">
        {deployments.isPending ? (
          <div className="p-6 text-sm text-fg3">{t("common.loading")}…</div>
        ) : deployments.isError ? (
          <div className="p-6 text-sm text-danger">{t("common.error")}</div>
        ) : deployments.data.length === 0 ? (
          <div className="p-8 text-center text-sm text-fg3">{t("deployments.empty")}</div>
        ) : (
          <table className="w-full border-collapse text-sm">
            <thead className="bg-bg-muted text-left">
              <tr>
                <th className="px-6 py-3 text-xs font-semibold uppercase tracking-[0.08em] text-fg2">
                  {t("deployments.columns.name")}
                </th>
                <th className="px-6 py-3 text-xs font-semibold uppercase tracking-[0.08em] text-fg2">
                  {t("deployments.columns.status")}
                </th>
                <th className="px-6 py-3 text-xs font-semibold uppercase tracking-[0.08em] text-fg2">
                  {t("deployments.columns.endpoint")}
                </th>
                <th className="px-6 py-3 text-xs font-semibold uppercase tracking-[0.08em] text-fg2">
                  {t("deployments.columns.lastCalled")}
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[color:var(--border)]">
              {deployments.data.map((d) => (
                <tr
                  key={d.id}
                  className="cursor-pointer hover:bg-bg-muted/60"
                  onClick={() => navigate(`/deployments/${d.id}`)}
                >
                  <td className="px-6 py-3 font-medium text-fg1">{d.name}</td>
                  <td className="px-6 py-3">
                    <RunStatusBadge status={mapStatus(d.status)} />
                  </td>
                  <td className="px-6 py-3">
                    <EndpointCell url={d.url} />
                  </td>
                  <td className="px-6 py-3 text-xs text-fg2">
                    {formatRelative(d.last_called_at)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </GlassCard>

      <Modal open={newOpen} onClose={() => setNewOpen(false)} title={t("deployments.newCta")}>
        <NewDeploymentForm onClose={() => setNewOpen(false)} />
      </Modal>
    </div>
  );
}
