import { DatabaseZap, LockKeyhole, ShieldCheck } from "lucide-react";
import type { EvidenceSummary } from "../../api/types";

interface EvidenceFoundationCardProps {
  evidence: EvidenceSummary;
}

export function EvidenceFoundationCard({ evidence }: EvidenceFoundationCardProps) {
  return (
    <section className="rail-card" aria-labelledby="evidence-title">
      <div className="flex items-center justify-between">
        <div>
          <p className="eyebrow text-cyan-300">Observed evidence</p>
          <h2 id="evidence-title" className="mt-1 text-sm font-semibold text-slate-100">
            Evidence Foundation
          </h2>
        </div>
        <ShieldCheck size={17} className="text-cyan-300" aria-hidden="true" />
      </div>
      <p className="mt-4 text-2xl font-semibold text-white">
        {evidence.governed_evidence_count}
        <span className="ml-2 text-sm font-normal text-slate-400">governed findings</span>
      </p>
      <div className="mt-4 grid grid-cols-2 gap-2">
        <EvidenceCheck icon={<DatabaseZap size={14} />} label="Data Health checked" />
        <EvidenceCheck icon={<LockKeyhole size={14} />} label="Source locked" />
      </div>
      <button
        type="button"
        disabled
        className="mt-4 w-full cursor-not-allowed rounded-lg border border-slate-700 bg-slate-900/70 px-3 py-2 text-left text-[11px] text-slate-500"
      >
        Evidence details available in a later slice
      </button>
    </section>
  );
}

function EvidenceCheck({ icon, label }: { icon: React.ReactNode; label: string }) {
  return (
    <div className="flex items-center gap-2 rounded-lg border border-cyan-400/10 bg-cyan-400/[0.05] px-2.5 py-2 text-[11px] text-cyan-100/80">
      <span className="text-cyan-300">{icon}</span>
      {label}
    </div>
  );
}
