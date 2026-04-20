import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/atoms/Button";
import { GlassCard } from "@/components/molecules/GlassCard";
import { Modal } from "@/components/molecules/Modal";
import { DeploymentEndpointCard } from "@/components/organisms/DeploymentEndpointCard";
import { useT } from "@/i18n";
import { api } from "@/lib/api/client";

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

      {deployments.isPending ? (
        <GlassCard>
          <p className="text-sm text-fg3">{t("common.loading")}…</p>
        </GlassCard>
      ) : deployments.isError ? (
        <GlassCard>
          <p className="text-sm text-danger">{t("common.error")}</p>
        </GlassCard>
      ) : deployments.data.length === 0 ? (
        <GlassCard>
          <p className="text-center text-sm text-fg3">{t("deployments.empty")}</p>
        </GlassCard>
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          {deployments.data.map((d) => (
            <DeploymentEndpointCard key={d.id} deployment={d} />
          ))}
        </div>
      )}

      <Modal open={newOpen} onClose={() => setNewOpen(false)} title={t("deployments.newCta")}>
        <NewDeploymentForm onClose={() => setNewOpen(false)} />
      </Modal>
    </div>
  );
}
