import { GlassCard } from "@/components/molecules/GlassCard";
import { StepIndicator, type StepIndicatorStep } from "@/components/molecules/StepIndicator";
import { useT } from "@/i18n";
import { useWizardStore, type WizardStep } from "@/state/wizardStore";

import { StepFeatures } from "./StepFeatures";
import { StepHyperparameters } from "./StepHyperparameters";
import { StepModel } from "./StepModel";
import { StepProfile } from "./StepProfile";
import { StepTargetSplit } from "./StepTargetSplit";
import { StepUpload } from "./StepUpload";

export function NewRunWizard() {
  const t = useT();
  const currentStep = useWizardStore((s) => s.currentStep);
  const setStep = useWizardStore((s) => s.setStep);

  const steps: StepIndicatorStep[] = [
    { key: "upload", label: t("wizard.step1") },
    { key: "profile", label: t("wizard.step2") },
    { key: "features", label: t("wizard.step3") },
    { key: "target", label: t("wizard.step4") },
    { key: "model", label: t("wizard.step5") },
    { key: "hyperparameters", label: t("wizard.step6") },
  ];

  return (
    <div className="mx-auto grid max-w-6xl grid-cols-1 gap-8 lg:grid-cols-[220px_1fr]">
      <aside>
        <StepIndicator
          steps={steps}
          currentIndex={currentStep - 1}
          onStepClick={(idx) => setStep(((idx + 1) as WizardStep))}
        />
      </aside>

      <GlassCard className="animate-fade-in">
        {currentStep === 1 ? <StepUpload /> : null}
        {currentStep === 2 ? <StepProfile /> : null}
        {currentStep === 3 ? <StepFeatures /> : null}
        {currentStep === 4 ? <StepTargetSplit /> : null}
        {currentStep === 5 ? <StepModel /> : null}
        {currentStep === 6 ? <StepHyperparameters /> : null}
      </GlassCard>
    </div>
  );
}
