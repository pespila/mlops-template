import { Button } from "@/components/atoms/Button";
import { useT } from "@/i18n";
import type { TaskFamily } from "@/lib/api/client";
import { useWizardStore } from "@/state/wizardStore";

const FAMILIES: TaskFamily[] = ["supervised", "forecasting", "recommender", "clustering"];

export function StepProblemType() {
  const t = useT();
  const taskFamily = useWizardStore((s) => s.taskFamily);
  const setTaskFamily = useWizardStore((s) => s.setTaskFamily);
  const prev = useWizardStore((s) => s.prev);
  const next = useWizardStore((s) => s.next);

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h2 className="font-display text-2xl font-bold text-fg1">
          {t("wizard.problemTypeHeading")}
        </h2>
        <p className="mt-1 text-sm text-fg2">{t("wizard.problemTypeSubtitle")}</p>
      </div>

      <fieldset>
        <legend className="sr-only">{t("wizard.problemTypeHeading")}</legend>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2" role="radiogroup">
          {FAMILIES.map((value) => {
            const selected = taskFamily === value;
            return (
              <button
                key={value}
                type="button"
                role="radio"
                aria-checked={selected}
                onClick={() => setTaskFamily(value)}
                className={
                  "flex flex-col gap-2 rounded border px-4 py-3 text-left transition-colors " +
                  (selected
                    ? "border-primary bg-[color:var(--primary-soft)]"
                    : "border-[color:var(--border)] bg-bg hover:border-primary")
                }
              >
                <span className="font-semibold text-fg1">
                  {t(`wizard.families.${value}.title`)}
                </span>
                <span className="text-xs text-fg2">{t(`wizard.families.${value}.blurb`)}</span>
                <ul className="mt-1 list-disc pl-4 text-[11px] text-fg3" aria-hidden="true">
                  {(["bullet1", "bullet2", "bullet3"] as const).map((b) => (
                    <li key={b}>{t(`wizard.families.${value}.${b}`)}</li>
                  ))}
                </ul>
              </button>
            );
          })}
        </div>
      </fieldset>

      <div className="flex justify-between">
        <Button variant="ghost" onClick={prev}>
          {t("common.back")}
        </Button>
        <Button disabled={!taskFamily} onClick={next}>
          {t("common.next")} →
        </Button>
      </div>
    </div>
  );
}
