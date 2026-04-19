import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";

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

export type WizardStep = 1 | 2 | 3 | 4 | 5;

export interface WizardState {
  datasetId: string | null;
  transforms: FeatureTransform[];
  target: string | null;
  split: TrainValTestSplit;
  modelCatalogId: string | null;
  hyperparams: Record<string, unknown>;
  currentStep: WizardStep;
  experimentName: string;

  setDatasetId: (id: string | null) => void;
  setTransforms: (t: FeatureTransform[]) => void;
  setTransform: (feature: string, kind: FeatureTransformKind) => void;
  setTarget: (t: string | null) => void;
  setSplit: (s: TrainValTestSplit) => void;
  setModelCatalogId: (id: string | null) => void;
  setHyperparams: (h: Record<string, unknown>) => void;
  setStep: (step: WizardStep) => void;
  setExperimentName: (name: string) => void;
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
  | "setSplit"
  | "setModelCatalogId"
  | "setHyperparams"
  | "setStep"
  | "setExperimentName"
  | "next"
  | "prev"
  | "reset"
> = {
  datasetId: null,
  transforms: [],
  target: null,
  split: DEFAULT_SPLIT,
  modelCatalogId: null,
  hyperparams: {},
  currentStep: 1,
  experimentName: "",
};

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
      setSplit: (split) => set({ split }),
      setModelCatalogId: (modelCatalogId) => set({ modelCatalogId }),
      setHyperparams: (hyperparams) => set({ hyperparams }),
      setStep: (currentStep) => set({ currentStep }),
      setExperimentName: (experimentName) => set({ experimentName }),
      next: () =>
        set((state) => ({
          currentStep: Math.min(5, state.currentStep + 1) as WizardStep,
        })),
      prev: () =>
        set((state) => ({
          currentStep: Math.max(1, state.currentStep - 1) as WizardStep,
        })),
      reset: () => set({ ...INITIAL }),
    }),
    {
      name: "aipacken.wizard",
      version: 1,
      storage: createJSONStorage(() => localStorage),
      migrate: (_persisted, version) => {
        if (version !== 1) return { ...INITIAL };
        return _persisted as WizardState;
      },
    },
  ),
);
