import { useQuery } from "@tanstack/react-query";
import {
  ArrowRight,
  Database,
  FlaskConical,
  type LucideIcon,
  Package,
  Rocket,
} from "lucide-react";
import { Link } from "react-router-dom";

import { GlassCard } from "@/components/molecules/GlassCard";
import { RunStatusBadge } from "@/components/atoms/RunStatusBadge";
import { useT } from "@/i18n";
import { api, type DeploymentStatus, type RunStatusValue } from "@/lib/api/client";
import { cn } from "@/lib/cn";
import { formatRelative } from "@/lib/format";

interface StatTileProps {
  icon: LucideIcon;
  label: string;
  value: number | string;
  to: string;
  accent?: "primary" | "success" | "warning" | "neutral";
}

const ACCENT_BG: Record<NonNullable<StatTileProps["accent"]>, string> = {
  primary: "bg-primary/15 text-primary",
  success: "bg-success/15 text-success",
  warning: "bg-warning/15 text-warning",
  neutral: "bg-bg-muted text-fg2",
};

function StatTile({ icon: Icon, label, value, to, accent = "primary" }: StatTileProps) {
  return (
    <Link
      to={to}
      className="group flex items-center gap-4 rounded-lg border border-[color:var(--border)] bg-bg p-4 transition hover:border-primary hover:bg-bg-muted/40"
    >
      <div className={cn("rounded-md p-2.5", ACCENT_BG[accent])}>
        <Icon size={20} strokeWidth={2} />
      </div>
      <div className="flex flex-col">
        <span className="text-[10px] font-semibold uppercase tracking-[0.08em] text-fg3">
          {label}
        </span>
        <span className="font-display text-xl font-bold text-fg1">{value}</span>
      </div>
      <ArrowRight
        size={16}
        strokeWidth={2}
        className="ml-auto text-fg3 transition group-hover:translate-x-0.5 group-hover:text-primary"
      />
    </Link>
  );
}

const DEPLOYMENT_TONE: Record<DeploymentStatus, string> = {
  pending: "bg-bg-muted text-fg2",
  provisioning: "bg-primary/15 text-primary",
  deploying: "bg-primary/15 text-primary",
  ready: "bg-success/15 text-success",
  active: "bg-success/15 text-success",
  unhealthy: "bg-warning/15 text-warning",
  failed: "bg-danger/15 text-danger",
  stopping: "bg-warning/15 text-warning",
  tearing_down: "bg-warning/15 text-warning",
  stopped: "bg-bg-muted text-fg3",
};

function DeploymentStatusPill({ status }: { status: DeploymentStatus }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.08em]",
        DEPLOYMENT_TONE[status],
      )}
    >
      {status}
    </span>
  );
}

export function Dashboard() {
  const t = useT();

  const datasets = useQuery({
    queryKey: ["datasets"],
    queryFn: () => api.datasets.list(),
  });
  const runs = useQuery({
    queryKey: ["runs"],
    queryFn: () => api.runs.list(),
  });
  const models = useQuery({
    queryKey: ["models"],
    queryFn: () => api.models.list(),
  });
  const deployments = useQuery({
    queryKey: ["deployments"],
    queryFn: () => api.deployments.list(),
  });

  const activeRuns = (runs.data ?? []).filter((r) =>
    (["queued", "building", "running"] as RunStatusValue[]).includes(r.status),
  ).length;
  const readyDeployments = (deployments.data ?? []).filter((d) => d.status === "ready").length;

  const recentRuns = (runs.data ?? [])
    .slice()
    .sort((a, b) => (a.created_at < b.created_at ? 1 : -1))
    .slice(0, 5);
  const recentModels = (models.data ?? []).slice(0, 5);
  const recentDeployments = (deployments.data ?? [])
    .slice()
    .sort((a, b) => (a.created_at < b.created_at ? 1 : -1))
    .slice(0, 5);

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-8 animate-fade-in">
      <header className="flex flex-col gap-3">
        <h1 className="font-display text-display-lg font-extrabold tracking-tight text-fg1">
          {t("dashboard.headline")}
        </h1>
        <p className="max-w-2xl text-base text-fg2">{t("dashboard.subhead")}</p>
        <div className="flex gap-3 pt-2">
          <Link to="/experiments/new" className="btn-primary">
            {t("dashboard.ctaPrimary")}
            <ArrowRight size={16} strokeWidth={2} />
          </Link>
          <Link to="/datasets" className="btn-ghost">
            {t("dashboard.ctaGhost")}
          </Link>
        </div>
      </header>

      <section className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <StatTile
          icon={Database}
          label="Datasets"
          value={datasets.data?.length ?? "—"}
          to="/datasets"
          accent="primary"
        />
        <StatTile
          icon={FlaskConical}
          label={activeRuns > 0 ? `${activeRuns} running` : "Runs"}
          value={runs.data?.length ?? "—"}
          to="/experiments"
          accent={activeRuns > 0 ? "warning" : "primary"}
        />
        <StatTile
          icon={Package}
          label="Registered models"
          value={models.data?.length ?? "—"}
          to="/models"
          accent="primary"
        />
        <StatTile
          icon={Rocket}
          label={`${readyDeployments} live`}
          value={deployments.data?.length ?? "—"}
          to="/deployments"
          accent={readyDeployments > 0 ? "success" : "primary"}
        />
      </section>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <GlassCard className="!p-0 overflow-hidden">
          <div className="flex items-center justify-between border-b border-[color:var(--border)] px-6 py-4">
            <h2 className="font-display text-lg font-bold text-fg1">Latest runs</h2>
            <Link to="/experiments" className="text-xs font-semibold text-primary hover:underline">
              View all →
            </Link>
          </div>
          {runs.isPending ? (
            <p className="px-6 py-4 text-sm text-fg3">Loading…</p>
          ) : recentRuns.length === 0 ? (
            <div className="px-6 py-8 text-center">
              <p className="text-sm text-fg3">No runs yet.</p>
              <Link to="/experiments/new" className="mt-2 inline-block text-xs font-semibold text-primary hover:underline">
                Start your first →
              </Link>
            </div>
          ) : (
            <ul className="divide-y divide-[color:var(--border)]">
              {recentRuns.map((r) => (
                <li key={r.id}>
                  <Link
                    to={`/experiments/runs/${r.id}`}
                    className="flex items-center justify-between gap-3 px-6 py-3 transition hover:bg-bg-muted/60"
                  >
                    <div className="flex min-w-0 flex-col">
                      <span className="truncate text-sm font-medium text-fg1">
                        {r.display_name || `Run ${r.id.slice(0, 8)}`}
                      </span>
                      <span className="text-[11px] text-fg3">
                        {formatRelative(r.created_at)}
                      </span>
                    </div>
                    <RunStatusBadge status={r.status} />
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </GlassCard>

        <GlassCard className="!p-0 overflow-hidden">
          <div className="flex items-center justify-between border-b border-[color:var(--border)] px-6 py-4">
            <h2 className="font-display text-lg font-bold text-fg1">Latest models</h2>
            <Link to="/models" className="text-xs font-semibold text-primary hover:underline">
              View all →
            </Link>
          </div>
          {models.isPending ? (
            <p className="px-6 py-4 text-sm text-fg3">Loading…</p>
          ) : recentModels.length === 0 ? (
            <div className="px-6 py-8 text-center">
              <p className="text-sm text-fg3">No models registered yet.</p>
              <p className="mt-1 text-xs text-fg3">
                Models appear here after a run succeeds.
              </p>
            </div>
          ) : (
            <ul className="divide-y divide-[color:var(--border)]">
              {recentModels.map((m) => (
                <li key={m.id}>
                  <Link
                    to={`/models/${m.id}`}
                    className="flex items-center justify-between gap-3 px-6 py-3 transition hover:bg-bg-muted/60"
                  >
                    <div className="flex min-w-0 flex-col">
                      <span className="truncate text-sm font-medium text-fg1">{m.name}</span>
                      {m.description ? (
                        <span className="truncate text-[11px] text-fg3">{m.description}</span>
                      ) : (
                        <span className="text-[11px] text-fg3">
                          {formatRelative(m.created_at)}
                        </span>
                      )}
                    </div>
                    <ArrowRight size={14} strokeWidth={2} className="text-fg3" />
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </GlassCard>

        <GlassCard className="!p-0 overflow-hidden lg:col-span-2">
          <div className="flex items-center justify-between border-b border-[color:var(--border)] px-6 py-4">
            <h2 className="font-display text-lg font-bold text-fg1">Latest deployments</h2>
            <Link to="/deployments" className="text-xs font-semibold text-primary hover:underline">
              View all →
            </Link>
          </div>
          {deployments.isPending ? (
            <p className="px-6 py-4 text-sm text-fg3">Loading…</p>
          ) : recentDeployments.length === 0 ? (
            <div className="px-6 py-8 text-center">
              <p className="text-sm text-fg3">No deployments yet.</p>
              <p className="mt-1 text-xs text-fg3">
                Promote a trained model from the Models page.
              </p>
            </div>
          ) : (
            <ul className="divide-y divide-[color:var(--border)]">
              {recentDeployments.map((d) => (
                <li key={d.id}>
                  <Link
                    to={`/deployments/${d.id}`}
                    className="flex items-center justify-between gap-3 px-6 py-3 transition hover:bg-bg-muted/60"
                  >
                    <div className="flex min-w-0 flex-col">
                      <span className="truncate text-sm font-medium text-fg1">{d.name}</span>
                      <span className="truncate text-[11px] font-mono text-fg3">
                        {d.endpoint_url ?? d.url ?? "—"}
                      </span>
                    </div>
                    <DeploymentStatusPill status={d.status} />
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </GlassCard>
      </div>

      {(datasets.data?.length ?? 0) === 0 &&
      (runs.data?.length ?? 0) === 0 &&
      (models.data?.length ?? 0) === 0 ? (
        <GlassCard className="flex flex-col gap-2 border-primary/40 bg-primary/5">
          <h3 className="font-display text-lg font-bold text-fg1">
            Let's get you started
          </h3>
          <p className="text-sm text-fg2">
            Upload a dataset, pick a model (or let AutoGluon decide), and deploy
            to a live API — all on your own machine. No cloud dependencies.
          </p>
          <div className="flex gap-2 pt-1">
            <Link to="/experiments/new" className="btn-primary">
              Start a new run →
            </Link>
            <Link to="/datasets" className="btn-ghost">
              Upload a dataset →
            </Link>
          </div>
        </GlassCard>
      ) : null}
    </div>
  );
}
