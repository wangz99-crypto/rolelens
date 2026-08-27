import { ArrowRight, Bot, FileCheck2, GitBranch, Target } from "lucide-react";
import { scenarioStatusLabel } from "../../api/presentation";
import type { DemoDecision } from "../../api/types";

interface DecisionCardProps {
  data: DemoDecision;
  onOpen: () => void;
}

export function DecisionCard({ data, onOpen }: DecisionCardProps) {
  return (
    <article
      data-testid="decision-card"
      className="max-w-[880px] rounded-2xl border border-slate-800 bg-[#111925] p-6 shadow-2xl shadow-black/10"
    >
      <div className="flex items-start justify-between gap-8">
        <div>
          <div className="mb-4 inline-flex size-10 items-center justify-center rounded-xl border border-cyan-400/25 bg-cyan-400/10 text-cyan-300">
            <Target size={20} aria-hidden="true" />
          </div>
          <h2 className="text-xl font-semibold text-white">
            {data.decision.title}
          </h2>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-400">
            {data.decision.business_question}
          </p>
        </div>
        <button
          type="button"
          onClick={onOpen}
          className="inline-flex shrink-0 items-center gap-2 rounded-lg bg-cyan-300 px-4 py-2.5 text-sm font-semibold text-slate-950 transition hover:bg-cyan-200"
        >
          Open Decision
          <ArrowRight size={16} aria-hidden="true" />
        </button>
      </div>
      <div className="mt-7 grid grid-cols-4 divide-x divide-slate-800 border-t border-slate-800 pt-5">
        <Metric icon={<FileCheck2 size={15} />} label="Evidence" value={`${data.evidence.governed_evidence_count} governed findings`} />
        <Metric icon={<Target size={15} />} label="Scenario" value={scenarioStatusLabel(data.scenario.status)} />
        <Metric icon={<GitBranch size={15} />} label="Revision" value="REV-001" />
        <Metric icon={<Bot size={15} />} label="AI Brief" value="Not generated" />
      </div>
    </article>
  );
}

function Metric({
  icon,
  label,
  value,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
}) {
  return (
    <div className="px-5 first:pl-0">
      <div className="flex items-center gap-2 text-xs text-slate-500">
        {icon}
        {label}
      </div>
      <p className="mt-1.5 text-sm font-medium text-slate-200">{value}</p>
    </div>
  );
}
