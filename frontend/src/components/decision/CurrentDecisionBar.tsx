import { CheckCircle2 } from "lucide-react";
import { scenarioStatusShortLabel } from "../../api/presentation";
import type { Scenario } from "../../api/types";

interface CurrentDecisionBarProps {
  scenario: Scenario;
}

export function CurrentDecisionBar({ scenario }: CurrentDecisionBarProps) {
  return (
    <section className="flex min-h-[68px] items-center rounded-xl border border-emerald-400/20 bg-emerald-400/[0.06] px-5">
      <div className="mr-6 border-r border-slate-700 pr-6">
        <p className="eyebrow text-emerald-300">Current Decision</p>
      </div>
      <p className="text-base font-semibold text-white">
        +{scenario.net_scenario_value.toLocaleString("en-US")} {scenario.currency}
        <span className="ml-1 font-normal text-slate-400">net scenario value</span>
      </p>
      <p className="ml-auto text-sm text-slate-300">
        {(scenario.break_even_lift * 100).toFixed(0)}% modeled break-even lift
      </p>
      <span className="ml-5 inline-flex items-center gap-2 rounded-full border border-emerald-400/30 bg-emerald-400/10 px-3 py-1.5 text-xs font-semibold tracking-wide text-emerald-200">
        <CheckCircle2 size={14} aria-hidden="true" />
        {scenarioStatusShortLabel(scenario.status)}
      </span>
    </section>
  );
}
