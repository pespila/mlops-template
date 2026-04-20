import { Check, Copy, ExternalLink } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

import { RunStatusBadge, type RunStatus } from "@/components/atoms/RunStatusBadge";
import type { DeploymentRead } from "@/lib/api/client";
import { cn } from "@/lib/cn";
import { formatRelative } from "@/lib/format";

interface DeploymentEndpointCardProps {
  deployment: DeploymentRead;
  className?: string;
}

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

export function DeploymentEndpointCard({
  deployment,
  className,
}: DeploymentEndpointCardProps) {
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(deployment.url);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* ignore */
    }
  };

  return (
    <div className={cn("glass-card animate-fade-in", className)}>
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="font-display text-xl font-bold text-fg1">{deployment.name}</h3>
          <p className="mt-1 text-xs text-fg3">
            Last called {formatRelative(deployment.last_called_at)}
          </p>
        </div>
        <RunStatusBadge status={mapStatus(deployment.status)} />
      </div>

      <div className="mt-5 flex items-center gap-2 rounded border border-[color:var(--border)] bg-bg px-3 py-2">
        <code className="flex-1 truncate font-mono text-xs text-teal-900">
          {deployment.url}
        </code>
        <button
          type="button"
          onClick={copy}
          className="inline-flex items-center gap-1 rounded px-2 py-1 text-xs font-semibold text-fg2 hover:bg-bg-muted hover:text-fg1"
        >
          {copied ? <Check size={13} strokeWidth={2} /> : <Copy size={13} strokeWidth={2} />}
          {copied ? "Copied" : "Copy"}
        </button>
      </div>

      <div className="mt-5 flex gap-2">
        <Link
          to={`/deployments/${deployment.id}`}
          className="btn-primary !px-4 !py-2 !text-[13px]"
        >
          Open <ExternalLink size={14} strokeWidth={2} />
        </Link>
      </div>
    </div>
  );
}
