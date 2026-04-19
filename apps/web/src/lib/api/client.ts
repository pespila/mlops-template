/**
 * Typed API client.
 *
 * Once the OpenAPI spec lands at packages/api-spec/openapi.json, `pnpm gen:api`
 * generates `./schema.d.ts` and we replace the untyped fetch wrapper below
 * with `createClient<paths>()` from openapi-fetch.
 */

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "/api";

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    ...init,
  });
  if (!res.ok) {
    throw new Error(`API ${res.status} ${res.statusText}: ${await res.text()}`);
  }
  return (await res.json()) as T;
}

export interface HealthResponse {
  status: "ok";
  version: string;
}

export const api = {
  health: () => apiFetch<HealthResponse>("/healthz"),
};
