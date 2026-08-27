import { GitBranch } from "lucide-react";
import { scenarioStatusBadgeLabel } from "../api/presentation";
import type { DemoDecision } from "../api/types";
import { AppSidebar } from "../components/AppSidebar";
import { StatusBadge } from "../components/StatusBadge";
import { AssumptionCard } from "../components/decision/AssumptionCard";
import { CurrentDecisionBar } from "../components/decision/CurrentDecisionBar";
import { EvidenceFoundationCard } from "../components/decision/EvidenceFoundationCard";
import { ImpactMap } from "../components/impact-map/ImpactMap";

interface DecisionRoomPageProps {
  data: DemoDecision;
}

export function DecisionRoomPage({ data }: DecisionRoomPageProps) {
  return (
    <div className="flex h-screen overflow-hidden bg-graphite">
      <AppSidebar activeLabel="Decisions" />
      <main className="grid min-w-0 flex-1 grid-rows-[auto_minmax(0,1fr)_auto] gap-4 overflow-hidden px-6 py-5">
        <header className="flex items-start justify-between gap-8">
          <div className="min-w-0">
            <p className="eyebrow text-cyan-300">Decision Room</p>
            <h1 className="mt-1.5 text-2xl font-semibold tracking-tight text-white">{data.decision.title}</h1>
            <p className="mt-1 max-w-[760px] truncate text-sm text-slate-400" title={data.decision.business_question}>
              {data.decision.business_question}
            </p>
            <div className="mt-3 flex gap-2">
              <StatusBadge tone="evidence">Evidence locked</StatusBadge>
              <StatusBadge tone="positive">{scenarioStatusBadgeLabel(data.scenario.status)}</StatusBadge>
              <StatusBadge tone="neutral">AI Brief not generated</StatusBadge>
            </div>
          </div>
          <div className="mt-1 flex shrink-0 items-center gap-2 rounded-lg border border-slate-700 bg-slate-900/60 px-3 py-2 text-xs font-semibold tracking-[0.08em] text-slate-300">
            <GitBranch size={15} className="text-slate-500" aria-hidden="true" />
            {data.revision.revision_id.toUpperCase()} · {data.revision.label.toUpperCase()}
          </div>
        </header>
        <div className="grid min-h-0 grid-cols-[minmax(0,1fr)_304px] gap-4">
          <ImpactMap data={data} />
          <aside className="flex min-h-0 flex-col gap-3 overflow-hidden">
            <AssumptionCard assumptions={data.assumptions} />
            <EvidenceFoundationCard evidence={data.evidence} />
          </aside>
        </div>
        <CurrentDecisionBar scenario={data.scenario} />
      </main>
    </div>
  );
}
