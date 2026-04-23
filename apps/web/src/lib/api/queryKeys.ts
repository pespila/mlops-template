/**
 * Centralized query key factory.
 *
 * Keeping keys here (instead of inline string arrays) gives:
 *  - Single point of truth — rename a key once, not across 20 files.
 *  - Prefix-based invalidation: `qc.invalidateQueries({ queryKey: keys.runs.all })`
 *    will cancel every sub-key that starts with ["runs"].
 *  - IDE autocomplete for every key segment.
 */
export const queryKeys = {
  auth: {
    me: ["auth", "me"] as const,
  },
  datasets: {
    all: ["datasets"] as const,
    list: () => [...queryKeys.datasets.all, "list"] as const,
    detail: (id: string) => [...queryKeys.datasets.all, id] as const,
    schema: (id: string) => [...queryKeys.datasets.all, id, "schema"] as const,
    profile: (id: string) => [...queryKeys.datasets.all, id, "profile"] as const,
  },
  experiments: {
    all: ["experiments"] as const,
    list: () => [...queryKeys.experiments.all, "list"] as const,
    detail: (id: string) => [...queryKeys.experiments.all, id] as const,
  },
  runs: {
    all: ["runs"] as const,
    list: () => [...queryKeys.runs.all, "list"] as const,
    detail: (id: string) => [...queryKeys.runs.all, id] as const,
    metrics: (id: string) => [...queryKeys.runs.all, id, "metrics"] as const,
    artifacts: (id: string) => [...queryKeys.runs.all, id, "artifacts"] as const,
    explanations: (id: string) => [...queryKeys.runs.all, id, "explanations"] as const,
    bias: (id: string) => [...queryKeys.runs.all, id, "bias"] as const,
    selectedHyperparams: (id: string) =>
      [...queryKeys.runs.all, id, "selected_hyperparams"] as const,
    logs: (id: string) => [...queryKeys.runs.all, id, "logs"] as const,
  },
  models: {
    all: ["models"] as const,
    list: () => [...queryKeys.models.all, "list"] as const,
    detail: (id: string) => [...queryKeys.models.all, id] as const,
    catalog: () => [...queryKeys.models.all, "catalog"] as const,
    catalogDetail: (id: string) => [...queryKeys.models.all, "catalog", id] as const,
  },
  deployments: {
    all: ["deployments"] as const,
    list: () => [...queryKeys.deployments.all, "list"] as const,
    detail: (id: string) => [...queryKeys.deployments.all, id] as const,
    predictions: (id: string) => [...queryKeys.deployments.all, id, "predictions"] as const,
    logs: (id: string) => [...queryKeys.deployments.all, id, "logs"] as const,
  },
} as const;
