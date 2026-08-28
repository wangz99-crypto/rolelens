import { ArrowRight, GitCompareArrows } from "lucide-react";
import { fractionToPercentDisplay } from "../../api/decimal";
import {
  formatSignedCurrency,
  scenarioStatusCompactLabel,
} from "../../api/presentation";
import type {
  ChangedAssumption,
  RecalculatedDecision,
  RevisionRoleState,
} from "../../api/types";

interface DecisionDiffPanelProps {
  data: RecalculatedDecision;
}

const roleOrder: RevisionRoleState["role_key"][] = [
  "executive",
  "sales_marketing",
  "project_manager",
  "data_analyst",
  "data_engineer",
];

const compactRoleLabels: Record<RevisionRoleState["role_key"], string> = {
  executive: "Executive",
  sales_marketing: "Sales",
  project_manager: "Project Manager",
  data_analyst: "Data Analyst",
  data_engineer: "Data Engineer",
};

function changedValue(change: ChangedAssumption, value: number): string {
  if (change.unit === "fraction") {
    return `${fractionToPercentDisplay(value)}%`;
  }
  if (change.currency) {
    return `${value.toLocaleString("en-US")} ${change.currency}`;
  }
  return `${value.toLocaleString("en-US")} ${change.unit}`;
}

export function DecisionDiffPanel({ data }: DecisionDiffPanelProps) {
  const changedLabel = data.diff.kind === "decision_posture_changed"
    ? "DECISION CHANGED"
    : "SCENARIO CHANGED";
  return (
    <section className="decision-diff-enter rounded-xl border border-orange-400/25 bg-orange-400/[0.055] px-4 py-3" aria-labelledby="decision-diff-title">
      <div className="grid grid-cols-[175px_minmax(180px,0.8fr)_minmax(250px,1.1fr)_minmax(330px,1.5fr)] items-center gap-4">
        <div>
          <div className="flex items-center gap-2 text-orange-300">
            <GitCompareArrows size={15} aria-hidden="true" />
            <p className="eyebrow">{data.revision.revision_id.toUpperCase()} · {changedLabel}</p>
          </div>
          <h2 id="decision-diff-title" className="mt-1 text-xs font-semibold text-white">{data.diff.headline}</h2>
        </div>
        <div className="border-l border-slate-700 pl-4">
          <p className="text-[9px] uppercase tracking-[0.14em] text-slate-500">Changed assumption</p>
          <div className="mt-1 space-y-1">
            {data.diff.changed_assumptions.map((change) => (
              <p key={change.assumption_id} className="text-[11px] text-slate-300">
                <span className="font-medium text-white">{change.label}</span>{" "}
                {changedValue(change, change.before_value)} <ArrowRight size={10} className="inline" /> {changedValue(change, change.after_value)}
              </p>
            ))}
          </div>
        </div>
        <div className="grid grid-cols-2 gap-3 border-l border-slate-700 pl-4">
          <DiffMetric
            label="Net scenario value"
            before={formatSignedCurrency(data.before_scenario.net_scenario_value, data.before_scenario.currency)}
            after={formatSignedCurrency(data.scenario.net_scenario_value, data.scenario.currency)}
          />
          <DiffMetric
            label="Break-even"
            before={scenarioStatusCompactLabel(data.before_scenario.status)}
            after={scenarioStatusCompactLabel(data.scenario.status)}
          />
        </div>
        <div className="border-l border-slate-700 pl-4">
          <p className="text-[9px] uppercase tracking-[0.14em] text-slate-500">Organizational impact</p>
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            {roleOrder.map((roleKey) => {
              const role = data.roles.find((item) => item.role_key === roleKey)!;
              return (
                <span key={roleKey} className="rounded-md border border-slate-700 bg-slate-900/60 px-2 py-1 text-[9px] text-slate-400">
                  {compactRoleLabels[roleKey]} <strong className="ml-1 text-slate-200">{role.impact_kind.toUpperCase()}</strong>
                </span>
              );
            })}
          </div>
          <p className="mt-2 text-[11px] font-semibold text-cyan-100">
            {data.diff.kind === "decision_posture_changed"
              ? "The decision changed. The observed evidence did not."
              : "The scenario changed. The observed evidence did not."}
          </p>
        </div>
      </div>
    </section>
  );
}

function DiffMetric({ label, before, after }: { label: string; before: string; after: string }) {
  return (
    <div>
      <p className="text-[9px] uppercase tracking-[0.12em] text-slate-500">{label}</p>
      <p className="mt-1 text-[11px] text-slate-300">{before} <ArrowRight size={10} className="inline text-orange-300" /> <strong className="text-white">{after}</strong></p>
    </div>
  );
}
