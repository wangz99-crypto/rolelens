import type { DemoDecision } from "../api/types";
import { AppSidebar } from "../components/AppSidebar";
import { DecisionCard } from "../components/decision/DecisionCard";

interface DecisionHomePageProps {
  data: DemoDecision;
  onOpenDecision: () => void;
}

export function DecisionHomePage({ data, onOpenDecision }: DecisionHomePageProps) {
  return (
    <div className="flex h-screen overflow-hidden bg-graphite">
      <AppSidebar activeLabel="Decisions" />
      <main className="min-w-0 flex-1 overflow-auto px-10 py-9">
        <p className="eyebrow text-slate-500">Demo workspace</p>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight text-white">Decisions</h1>
        <p className="mt-2 text-sm text-slate-500">One governed decision is ready for review.</p>
        <div className="mt-9">
          <DecisionCard data={data} onOpen={onOpenDecision} />
        </div>
      </main>
    </div>
  );
}
