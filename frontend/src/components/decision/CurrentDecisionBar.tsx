import { AlertTriangle, CheckCircle2 } from "lucide-react";
import { fractionToPercentDisplay } from "../../api/decimal";
import {
  formatSignedCurrency,
  scenarioStatusShortLabel,
  scenarioStatusTone,
  type ScenarioTone,
} from "../../api/presentation";
import type { Scenario } from "../../api/types";

interface CurrentDecisionBarProps {
  scenario: Scenario;
}

export function CurrentDecisionBar({ scenario }: CurrentDecisionBarProps) {
  const tone = scenarioStatusTone(scenario.status);
  const toneClasses: Record<
    ScenarioTone,
    { container: string; eyebrow: string; status: string }
  > = {
    positive: {
      container: "border-emerald-400/20 bg-emerald-400/[0.06]",
      eyebrow: "text-emerald-300",
      status:
        "border-emerald-400/30 bg-emerald-400/10 text-emerald-200",
    },
    blocked: {
      container: "border-red-400/20 bg-red-400/[0.06]",
      eyebrow: "text-red-300",
      status: "border-red-400/30 bg-red-400/10 text-red-200",
    },
    neutral: {
      container: "border-amber-400/20 bg-amber-400/[0.05]",
      eyebrow: "text-amber-300",
      status: "border-amber-400/30 bg-amber-400/10 text-amber-200",
    },
  };
  const classes = toneClasses[tone];
  const StatusIcon = tone === "positive" ? CheckCircle2 : AlertTriangle;
  return (
    <section className={`flex min-h-[68px] items-center rounded-xl border px-5 ${classes.container}`}>
      <div className="mr-6 border-r border-slate-700 pr-6">
        <p className={`eyebrow ${classes.eyebrow}`}>Current Decision</p>
      </div>
      <p className="text-base font-semibold text-white">
        {formatSignedCurrency(scenario.net_scenario_value, scenario.currency)}
        <span className="ml-1 font-normal text-slate-400">net scenario value</span>
      </p>
      <p className="ml-auto text-sm text-slate-300">
        {fractionToPercentDisplay(scenario.break_even_lift).replace(/\.0$/, "")}% modeled break-even lift
      </p>
      <span className={`ml-5 inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-semibold tracking-wide ${classes.status}`}>
        <StatusIcon size={14} aria-hidden="true" />
        {scenarioStatusShortLabel(scenario.status)}
      </span>
    </section>
  );
}
