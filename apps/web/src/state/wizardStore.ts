import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";

import type { TaskKind } from "@/lib/api/client";

export type FeatureTransformKind =
  | "keep"
  | "drop"
  | "standardize"
  | "one-hot"
  | "impute-mean"
  | "impute-median"
  | "impute-mode";

export interface FeatureTransform {
  feature: string;
  kind: FeatureTransformKind;
}

export interface TrainValTestSplit {
  train: number;
  val: number;
  test: number;
}

export type WizardStep = 1 | 2 | 3 | 4 | 5 | 6;

/**
 * HPO range entry shape (mirrors backend `HpoSearchRangeInt / Float /
 * Categorical`). The wizard stores these by hyperparameter name and the
 * submit path forwards them to the backend under `hpo.search_space` when
 * `hpoEnabled` is true.
 */
export type HpoSearchEntry =
  | { type: "int"; low: number; high: number; log?: boolean }
  | { type: "float"; low: number; high: number; log?: boolean }
  | { type: "categorical"; choices: Array<string | number | boolean> };

export interface WizardState {
  datasetId: string | null;
  transforms: FeatureTransform[];
  target: string | null;
  sensitiveFeatures: string[];
  split: TrainValTestSplit;
  modelCatalogId: string | null;
  /** User-picked fixed hyperparameters (HPO off path). */
  hyperparams: Record<string, unknown>;
  /** HPO search-space entries keyed by hyperparameter name (HPO on path). */
  hpoSearchSpace: Record<string, HpoSearchEntry>;
  /** User-selected task override; null → backend infers from target. */
  task: TaskKind | null;
  /** True when the user has enabled HPO; strictly either/or with `hyperparams`. */
  hpoEnabled: boolean;
  /** Optuna trial budget — propagated into the HpoConfig on submit. */
  hpoTrials: number;
  /** Optuna timeout — propagated into the HpoConfig on submit. */
  hpoTimeoutSec: number;
  /** Optional metric to optimize during HPO; null -> backend picks sensible default per task. */
  hpoMetric: string | null;
  /**
   * Per-hyperparameter mode: "fixed" | "range" | "default". "default" excludes
   * the hyperparameter from both `hyperparams` and `search_space` so the
   * library default wins — the user opts out of tuning without having to
   * know the default value themselves.
   */
  hpModes: Record<string, "fixed" | "range" | "default">;
  currentStep: WizardStep;
  experimentName: string;
  experimentId: string | null;

  setDatasetId: (id: string | null) => void;
  setTransforms: (t: FeatureTransform[]) => void;
  setTransform: (feature: string, kind: FeatureTransformKind) => void;
  setTarget: (t: string | null) => void;
  setSensitiveFeatures: (cols: string[]) => void;
  toggleSensitiveFeature: (col: string) => void;
  setSplit: (s: TrainValTestSplit) => void;
  setModelCatalogId: (id: string | null) => void;
  setHyperparams: (h: Record<string, unknown>) => void;
  setHpoSearchSpace: (s: Record<string, HpoSearchEntry>) => void;
  setTask: (t: TaskKind | null) => void;
  setHpoEnabled: (v: boolean) => void;
  setHpoTrials: (n: number) => void;
  setHpoTimeoutSec: (n: number) => void;
  setHpoMetric: (v: string | null) => void;
  setHpMode: (name: string, mode: "fixed" | "range" | "default") => void;
  setHpModes: (modes: Record<string, "fixed" | "range" | "default">) => void;
  setStep: (step: WizardStep) => void;
  setExperimentName: (name: string) => void;
  setExperimentId: (id: string | null) => void;
  next: () => void;
  prev: () => void;
  reset: () => void;
}

const DEFAULT_SPLIT: TrainValTestSplit = { train: 70, val: 15, test: 15 };

const INITIAL: Omit<
  WizardState,
  | "setDatasetId"
  | "setTransforms"
  | "setTransform"
  | "setTarget"
  | "setSensitiveFeatures"
  | "toggleSensitiveFeature"
  | "setSplit"
  | "setModelCatalogId"
  | "setHyperparams"
  | "setHpoSearchSpace"
  | "setTask"
  | "setHpoEnabled"
  | "setHpoTrials"
  | "setHpoTimeoutSec"
  | "setHpoMetric"
  | "setHpMode"
  | "setHpModes"
  | "setStep"
  | "setExperimentName"
  | "setExperimentId"
  | "next"
  | "prev"
  | "reset"
> = {
  datasetId: null,
  transforms: [],
  target: null,
  sensitiveFeatures: [],
  split: DEFAULT_SPLIT,
  modelCatalogId: null,
  hyperparams: {},
  hpoSearchSpace: {},
  task: null,
  hpoEnabled: false,
  hpoTrials: 30,
  hpoTimeoutSec: 1800,
  hpoMetric: null,
  hpModes: {},
  currentStep: 1,
  experimentName: "",
  experimentId: null,
};

const MAX_STEP: WizardStep = 6;

export const useWizardStore = create<WizardState>()(
  persist(
    (set) => ({
      ...INITIAL,
      setDatasetId: (datasetId) => set({ datasetId }),
      setTransforms: (transforms) => set({ transforms }),
      setTransform: (feature, kind) =>
        set((state) => {
          const next = state.transforms.filter((t) => t.feature !== feature);
          next.push({ feature, kind });
          return { transforms: next };
        }),
      setTarget: (target) => set({ target }),
      setSensitiveFeatures: (sensitiveFeatures) => set({ sensitiveFeatures }),
      toggleSensitiveFeature: (col) =>
        set((state) => ({
          sensitiveFeatures: state.sensitiveFeatures.includes(col)
            ? state.sensitiveFeatures.filter((c) => c !== col)
            : [...state.sensitiveFeatures, col],
        })),
      setSplit: (split) => set({ split }),
      setModelCatalogId: (modelCatalogId) => set({ modelCatalogId }),
      setHyperparams: (hyperparams) => set({ hyperparams }),
      setHpoSearchSpace: (hpoSearchSpace) => set({ hpoSearchSpace }),
      setTask: (task) => set({ task }),
      setHpoEnabled: (hpoEnabled) => set({ hpoEnabled }),
      setHpoTrials: (hpoTrials) => set({ hpoTrials }),
      setHpoTimeoutSec: (hpoTimeoutSec) => set({ hpoTimeoutSec }),
      setHpoMetric: (hpoMetric) => set({ hpoMetric }),
      setHpMode: (name, mode) =>
        set((state) => ({ hpModes: { ...state.hpModes, [name]: mode } })),
      setHpModes: (hpModes) => set({ hpModes }),
      setStep: (currentStep) => set({ currentStep }),
      setExperimentName: (experimentName) => set({ experimentName }),
      setExperimentId: (experimentId) => set({ experimentId }),
      next: () =>
        set((state) => ({
          currentStep: Math.min(MAX_STEP, state.currentStep + 1) as WizardStep,
        })),
      prev: () =>
        set((state) => ({
          currentStep: Math.max(1, state.currentStep - 1) as WizardStep,
        })),
      reset: () => set({ ...INITIAL }),
    }),
    {
      name: "aipacken.wizard",
      version: 3,
      storage: createJSONStorage(() => localStorage),
      migrate: (_persisted, _version) => {
        // Shape changed between v1 and v2 (new fields + WizardStep widened
        // to 6). Easier to wipe stale state than migrate field-by-field —
        // users rarely mid-flight a wizard across deploys.
        return { ...INITIAL };
      },
    },
  ),
);
