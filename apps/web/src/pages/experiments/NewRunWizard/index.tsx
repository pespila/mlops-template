import { RotateCcw } from "lucide-react";

import { Button } from "@/components/atoms/Button";
import { GlassCard } from "@/components/molecules/GlassCard";
import { StepIndicator, type StepIndicatorStep } from "@/components/molecules/StepIndicator";
import { useT } from "@/i18n";
import { useWizardStore, type WizardStep } from "@/state/wizardStore";

import { StepFeatures } from "./StepFeatures";
import { StepHyperparameters } from "./StepHyperparameters";
import { StepModel } from "./StepModel";
import { StepProblemType } from "./StepProblemType";
import { StepProfile } from "./StepProfile";
import { StepTargetSplit } from "./StepTargetSplit";
import { StepUpload } from "./StepUpload";

export function NewRunWizard() {
  const t = useT();
  const currentStep = useWizardStore((s) => s.currentStep);
  const setStep = useWizardStore((s) => s.setStep);
  const reset = useWizardStore((s) => s.reset);

  const steps: StepIndicatorStep[] = [
    { key: "upload", label: t("wizard.step1") },
    { key: "profile", label: t("wizard.step2") },
    { key: "problemType", label: t("wizard.step3") },
    { key: "features", label: t("wizard.step4") },
    { key: "target", label: t("wizard.step5") },
    { key: "model", label: t("wizard.step6") },
    { key: "hyperparameters", label: t("wizard.step7") },
  ];

  const handleClear = () => {
    if (window.confirm(t("wizard.clearConfirm"))) {
      reset();
    }
  };

  return (
    <div className="mx-auto grid max-w-6xl grid-cols-1 gap-8 lg:grid-cols-[220px_1fr]">
      <aside className="flex flex-col gap-3">
        <StepIndicator
          steps={steps}
          currentIndex={currentStep - 1}
          onStepClick={(idx) => setStep(((idx + 1) as WizardStep))}
        />
        <Button
          variant="ghost"
          size="sm"
          onClick={handleClear}
          leftIcon={<RotateCcw size={12} strokeWidth={2} />}
        >
          {t("wizard.clear")}
        </Button>
      </aside>

      <GlassCard className="animate-fade-in">
        {currentStep === 1 ? <StepUpload /> : null}
        {currentStep === 2 ? <StepProfile /> : null}
        {currentStep === 3 ? <StepProblemType /> : null}
        {currentStep === 4 ? <StepFeatures /> : null}
        {currentStep === 5 ? <StepTargetSplit /> : null}
        {currentStep === 6 ? <StepModel /> : null}
        {currentStep === 7 ? <StepHyperparameters /> : null}
      </GlassCard>
    </div>
  );
}
