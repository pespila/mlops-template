import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { RunStatusBadge, type RunStatus } from "@/components/atoms/RunStatusBadge";
import { EditableHeading } from "@/components/molecules/EditableHeading";
import { GlassCard } from "@/components/molecules/GlassCard";
import { useT } from "@/i18n";
import { api, type DeploymentRead } from "@/lib/api/client";
import { cn } from "@/lib/cn";

import { LogsTab } from "./LogsTab";
import { OverviewTab } from "./OverviewTab";
import { PredictionsTab } from "./PredictionsTab";
import { TestTab } from "./TestTab";

type Tab = "overview" | "test" | "predictions" | "logs";

function mapStatus(status: DeploymentRead["status"]): RunStatus {
  switch (status) {
    case "provisioning":
      return "building";
    case "ready":
      return "running";
    case "failed":
      return "failed";
    case "stopping":
    case "stopped":
      return "cancelled";
    default:
      return "queued";
  }
}

export function DeploymentDetail() {
  const { id = "" } = useParams<{ id: string }>();
  const t = useT();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [tab, setTab] = useState<Tab>("overview");

  const deployment = useQuery({
    queryKey: ["deployments", id],
    queryFn: () => api.deployments.get(id),
    enabled: Boolean(id),
    refetchInterval: 10_000,
  });

  const rename = useMutation({
    mutationFn: (name: string) => api.deployments.update(id, { name }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["deployments", id] });
      qc.invalidateQueries({ queryKey: ["deployments"] });
    },
  });

  const remove = useMutation({
    mutationFn: () => api.deployments.remove(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["deployments"] });
      navigate("/deployments");
    },
  });

  const tabs: Array<{ key: Tab; label: string }> = [
    { key: "overview", label: t("deployments.tabs.overview") },
    { key: "test", label: t("deployments.tabs.test") },
    { key: "predictions", label: t("deployments.tabs.predictions") },
    { key: "logs", label: t("deployments.tabs.logs") },
  ];

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6">
      <header className="flex flex-col gap-3">
        <div className="flex items-center gap-3">
          {deployment.data ? (
            <RunStatusBadge status={mapStatus(deployment.data.status)} />
          ) : null}
          <EditableHeading
            className="flex-1"
            value={deployment.data?.name ?? "Deployment"}
            onSave={(next) => rename.mutateAsync(next)}
            onDelete={() => remove.mutateAsync()}
            deleteConfirm="Delete this deployment? The serving container will be stopped immediately."
            saving={rename.isPending}
            deleting={remove.isPending}
          />
        </div>
      </header>

      <div
        role="tablist"
        className="flex gap-1 overflow-x-auto border-b border-[color:var(--border)]"
      >
        {tabs.map((tabDef) => (
          <button
            key={tabDef.key}
            type="button"
            role="tab"
            aria-selected={tab === tabDef.key}
            onClick={() => setTab(tabDef.key)}
            className={cn(
              "border-b-2 px-4 py-2 text-sm font-semibold transition-colors",
              tab === tabDef.key
                ? "border-primary text-primary"
                : "border-transparent text-fg2 hover:text-fg1",
            )}
          >
            {tabDef.label}
          </button>
        ))}
      </div>

      {deployment.isPending || !deployment.data ? (
        <GlassCard>
          <p className="text-sm text-fg3">{t("common.loading")}…</p>
        </GlassCard>
      ) : tab === "overview" ? (
        <OverviewTab deployment={deployment.data} />
      ) : tab === "test" ? (
        <TestTab deploymentId={id} />
      ) : tab === "predictions" ? (
        <PredictionsTab deploymentId={id} />
      ) : (
        <LogsTab deploymentId={id} />
      )}
    </div>
  );
}
