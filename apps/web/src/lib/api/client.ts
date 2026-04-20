/**
 * Typed API client for the AIpacken backend.
 *
 * All endpoints live on the same origin behind Traefik, so we use relative
 * paths and `credentials: "include"` for cookie-based auth.
 *
 * The fetcher throws a typed `ApiError` on non-2xx responses; callers (mostly
 * TanStack Query) can inspect `.status` to drive 401 redirects.
 */

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "/api";

export class ApiError extends Error {
  readonly status: number;
  readonly statusText: string;
  readonly body: unknown;

  constructor(status: number, statusText: string, body: unknown) {
    super(`API ${status} ${statusText}`);
    this.name = "ApiError";
    this.status = status;
    this.statusText = statusText;
    this.body = body;
  }
}

async function parseBody(res: Response): Promise<unknown> {
  const contentType = res.headers.get("content-type") ?? "";
  if (contentType.includes("application/json")) {
    try {
      return await res.json();
    } catch {
      return null;
    }
  }
  try {
    return await res.text();
  } catch {
    return null;
  }
}

interface ApiFetchInit extends Omit<RequestInit, "body"> {
  body?: BodyInit | Record<string, unknown> | Array<unknown> | null;
  /** If false, skip the default JSON content-type header. */
  json?: boolean;
}

export async function apiFetch<T>(path: string, init: ApiFetchInit = {}): Promise<T> {
  const { body, json = true, headers, ...rest } = init;
  const finalHeaders: Record<string, string> = { ...(headers as Record<string, string> | undefined) };

  let finalBody: BodyInit | null | undefined;
  if (body === undefined || body === null) {
    finalBody = body ?? undefined;
  } else if (body instanceof FormData || body instanceof Blob || typeof body === "string") {
    finalBody = body;
  } else {
    finalBody = JSON.stringify(body);
    if (json && !finalHeaders["Content-Type"]) {
      finalHeaders["Content-Type"] = "application/json";
    }
  }

  const res = await fetch(`${BASE_URL}${path}`, {
    credentials: "include",
    headers: finalHeaders,
    body: finalBody,
    ...rest,
  });

  if (!res.ok) {
    throw new ApiError(res.status, res.statusText, await parseBody(res));
  }

  if (res.status === 204) {
    return undefined as T;
  }

  const contentType = res.headers.get("content-type") ?? "";
  if (contentType.includes("application/json")) {
    return (await res.json()) as T;
  }
  return (await res.text()) as unknown as T;
}

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface CurrentUser {
  id: string;
  email: string;
  role: "admin" | "member";
}

export interface HealthResponse {
  status: "ok";
  version: string;
}

export type DatasetStatus = "uploading" | "profiling" | "ready" | "failed";

export interface DatasetRead {
  id: string;
  name: string;
  status: DatasetStatus;
  row_count: number | null;
  column_count: number | null;
  size_bytes: number | null;
  created_at: string;
  updated_at: string;
}

export interface DatasetProfile {
  row_count: number;
  column_count: number;
  missing_cells: number;
  duplicate_rows: number;
  columns: DatasetProfileColumn[];
}

export interface DatasetProfileColumn {
  name: string;
  type: FeatureType;
  null_fraction: number;
  unique_count: number;
  histogram?: Array<{ bucket: string; count: number }>;
}

export type FeatureType = "numeric" | "categorical" | "datetime" | "boolean" | "text";

export interface FeatureSchema {
  name: string;
  type: FeatureType;
  nullable: boolean;
  unique_count: number;
  null_fraction: number;
  sample: Array<string | number | boolean | null>;
}

export interface ModelCatalogEntry {
  id: string;
  name: string;
  family: string;
  description: string;
  hyperparam_schema: JsonSchema;
  tags: string[];
}

export interface ExperimentRead {
  id: string;
  name: string;
  description: string | null;
  created_at: string;
  run_count?: number;
}

export type RunStatusValue =
  | "queued"
  | "building"
  | "running"
  | "succeeded"
  | "failed"
  | "cancelled";

export interface RunRead {
  id: string;
  experiment_id: string;
  dataset_id: string;
  model_catalog_id: string;
  display_name: string | null;
  status: RunStatusValue;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  transform_config?: Record<string, unknown>;
  hyperparams?: Record<string, unknown>;
  primary_metric?: { name: string; value: number } | null;
}

export interface RunMetric {
  name: string;
  step: number;
  value: number;
  ts: string;
}

export interface RunArtifact {
  id: string;
  name: string;
  kind: string;
  size_bytes: number;
  download_url: string;
}

export interface ModelVersionRead {
  id: string;
  registered_model_id: string;
  version: number;
  run_id: string;
  stage: string;
  model_kind: string;
  storage_path: string | null;
  created_at: string;
  metrics?: Record<string, number>;
  dataset_id?: string | null;
  dataset_name?: string | null;
  experiment_id?: string | null;
  model_catalog_name?: string | null;
}

export type DeploymentStatus =
  | "provisioning"
  | "ready"
  | "failed"
  | "stopping"
  | "stopped";

export interface DeploymentRead {
  id: string;
  name: string;
  slug: string;
  model_version_id: string;
  status: DeploymentStatus;
  /** Public-facing URL the external caller POSTs predictions to. */
  url: string;
  endpoint_url: string | null;
  internal_url: string | null;
  created_at: string;
  last_called_at: string | null;
}

export interface PredictionResponse {
  prediction: unknown;
  prediction_label?: string | null;
  target_classes?: string[] | null;
  model_version: string;
  trace_id: string;
}

export interface PredictionLogEntry {
  id: string;
  ts: string;
  input: Record<string, unknown>;
  output: unknown;
  latency_ms: number;
  trace_id: string;
}

export interface Page<T> {
  items: T[];
  page: number;
  page_size: number;
  total: number;
}

export interface JsonSchema {
  type?: string | string[];
  title?: string;
  description?: string;
  properties?: Record<string, JsonSchema>;
  required?: string[];
  enum?: Array<string | number | boolean>;
  default?: unknown;
  minimum?: number;
  maximum?: number;
  minLength?: number;
  maxLength?: number;
  items?: JsonSchema;
  format?: string;
}

// ---------------------------------------------------------------------------
// Endpoint bindings
// ---------------------------------------------------------------------------

export interface CreateRunInput {
  experiment_id: string;
  dataset_id: string;
  transform_config: Record<string, unknown>;
  model_catalog_id: string;
  hyperparams: Record<string, unknown>;
}

export interface CreateExperimentInput {
  name: string;
  description?: string;
}

export interface CreateDeploymentInput {
  model_version_id: string;
  name: string;
}

export const api = {
  health: () => apiFetch<HealthResponse>("/healthz"),

  auth: {
    login: (input: { email: string; password: string }) =>
      apiFetch<CurrentUser>("/auth/login", { method: "POST", body: input }),
    logout: () => apiFetch<void>("/auth/logout", { method: "POST" }),
    me: () => apiFetch<CurrentUser>("/auth/me"),
  },

  datasets: {
    list: () =>
      apiFetch<{ items: DatasetRead[] }>("/datasets").then((r) => r.items ?? []),
    get: (id: string) => apiFetch<DatasetRead>(`/datasets/${encodeURIComponent(id)}`),
    profile: (id: string) =>
      apiFetch<DatasetProfile>(`/datasets/${encodeURIComponent(id)}/profile`),
    schema: (id: string) =>
      apiFetch<FeatureSchema[]>(`/datasets/${encodeURIComponent(id)}/schema`),
    upload: (file: File, onProgress?: (pct: number) => void): Promise<DatasetRead> =>
      new Promise((resolve, reject) => {
        const form = new FormData();
        form.append("file", file);
        const xhr = new XMLHttpRequest();
        xhr.open("POST", `${BASE_URL}/datasets`);
        xhr.withCredentials = true;
        if (onProgress) {
          xhr.upload.onprogress = (ev) => {
            if (ev.lengthComputable) {
              onProgress(ev.loaded / ev.total);
            }
          };
        }
        xhr.onload = () => {
          if (xhr.status >= 200 && xhr.status < 300) {
            try {
              resolve(JSON.parse(xhr.responseText) as DatasetRead);
            } catch (err) {
              reject(err as Error);
            }
          } else {
            reject(new ApiError(xhr.status, xhr.statusText, xhr.responseText));
          }
        };
        xhr.onerror = () => reject(new ApiError(0, "network error", null));
        xhr.send(form);
      }),
  },

  catalog: {
    models: () =>
      apiFetch<{ items: ModelCatalogEntry[] } | ModelCatalogEntry[]>("/catalog/models").then(
        (r) => (Array.isArray(r) ? r : (r.items ?? [])),
      ),
  },

  experiments: {
    list: () =>
      apiFetch<{ items: ExperimentRead[] }>("/experiments").then((r) => r.items ?? []),
    get: (id: string) => apiFetch<ExperimentRead>(`/experiments/${encodeURIComponent(id)}`),
    create: (input: CreateExperimentInput) =>
      apiFetch<ExperimentRead>("/experiments", { method: "POST", body: input }),
    update: (id: string, input: { name?: string; description?: string | null }) =>
      apiFetch<ExperimentRead>(`/experiments/${encodeURIComponent(id)}`, {
        method: "PATCH",
        body: input,
      }),
    remove: (id: string) =>
      apiFetch<void>(`/experiments/${encodeURIComponent(id)}`, { method: "DELETE" }),
  },

  runs: {
    list: (experimentId?: string) =>
      apiFetch<{ items: RunRead[] }>(
        experimentId ? `/runs?experiment_id=${encodeURIComponent(experimentId)}` : "/runs",
      ).then((r) => r.items ?? []),
    create: (input: CreateRunInput) =>
      apiFetch<RunRead>("/runs", { method: "POST", body: input }),
    get: (id: string) => apiFetch<RunRead>(`/runs/${encodeURIComponent(id)}`),
    update: (id: string, input: { display_name?: string | null }) =>
      apiFetch<RunRead>(`/runs/${encodeURIComponent(id)}`, { method: "PATCH", body: input }),
    remove: (id: string) =>
      apiFetch<void>(`/runs/${encodeURIComponent(id)}`, { method: "DELETE" }),
    metrics: (id: string) => apiFetch<RunMetric[]>(`/runs/${encodeURIComponent(id)}/metrics`),
    artifacts: (id: string) =>
      apiFetch<RunArtifact[]>(`/runs/${encodeURIComponent(id)}/artifacts`),
    logs: (id: string) =>
      apiFetch<Array<{ ts: string; level: string; message: string }>>(
        `/runs/${encodeURIComponent(id)}/logs`,
      ),
    explanations: (id: string) =>
      apiFetch<
        Array<{
          id: string;
          kind: string;
          feature_importance: Record<string, number>;
          artifact_path: string | null;
        }>
      >(`/runs/${encodeURIComponent(id)}/explanations`),
    bias: (id: string) =>
      apiFetch<
        Array<{
          id: string;
          sensitive_feature: string;
          metric_name: string;
          overall_value: number | null;
          group_values: {
            groups?: Record<string, number | Record<string, number>>;
            deltas?: Record<string, number>;
            overall?: number | Record<string, number>;
          };
        }>
      >(`/runs/${encodeURIComponent(id)}/bias`),
  },

  models: {
    list: () =>
      apiFetch<{
        items: Array<{ id: string; name: string; description: string | null; created_at: string }>;
      }>("/models").then((r) => r.items ?? []),
    get: (id: string) =>
      apiFetch<{
        id: string;
        name: string;
        description: string | null;
        versions: ModelVersionRead[];
      }>(`/models/${encodeURIComponent(id)}`),
    update: (id: string, input: { name?: string; description?: string | null }) =>
      apiFetch<{ id: string; name: string; description: string | null }>(
        `/models/${encodeURIComponent(id)}`,
        { method: "PATCH", body: input },
      ),
  },

  deployments: {
    list: () =>
      apiFetch<{ items: DeploymentRead[] }>("/deployments").then((r) => r.items ?? []),
    get: (id: string) => apiFetch<DeploymentRead>(`/deployments/${encodeURIComponent(id)}`),
    create: (input: CreateDeploymentInput) =>
      apiFetch<DeploymentRead>("/deployments", { method: "POST", body: input }),
    update: (id: string, input: { name?: string; audit_payloads?: boolean }) =>
      apiFetch<DeploymentRead>(`/deployments/${encodeURIComponent(id)}`, {
        method: "PATCH",
        body: input,
      }),
    remove: (id: string) =>
      apiFetch<void>(`/deployments/${encodeURIComponent(id)}`, { method: "DELETE" }),
    schema: (id: string) =>
      apiFetch<JsonSchema>(`/deployments/${encodeURIComponent(id)}/schema`),
    logs: (id: string, tail: number = 500) =>
      apiFetch<Array<{ ts: string; level: string; message: string }>>(
        `/deployments/${encodeURIComponent(id)}/logs?tail=${tail}`,
      ),
    predict: (id: string, body: Record<string, unknown>) =>
      apiFetch<PredictionResponse>(`/deployments/${encodeURIComponent(id)}/predict`, {
        method: "POST",
        body,
      }),
    predictions: (id: string, page: number = 1, pageSize: number = 20) =>
      apiFetch<Page<PredictionLogEntry>>(
        `/deployments/${encodeURIComponent(id)}/predictions?page=${page}&page_size=${pageSize}`,
      ),
  },
};

export type Api = typeof api;
