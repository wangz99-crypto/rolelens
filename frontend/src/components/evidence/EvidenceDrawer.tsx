import { DatabaseZap, LockKeyhole, ShieldCheck } from "lucide-react";
import type { EvidenceDetail } from "../../api/types";
import { Drawer } from "../drawer/Drawer";
import { EvidenceItem } from "./EvidenceItem";

interface EvidenceDrawerProps {
  status: "loading" | "loaded" | "error";
  evidence: EvidenceDetail[];
  onClose: () => void;
}

export function EvidenceDrawer({
  status,
  evidence,
  onClose,
}: EvidenceDrawerProps) {
  return (
    <Drawer labelledBy="evidence-drawer-title" onClose={onClose}>
      <header className="pr-12">
        <p className="eyebrow text-cyan-300">Observed evidence</p>
        <h2 id="evidence-drawer-title" className="mt-1 text-xl font-semibold text-white">
          Evidence Foundation
        </h2>
        <div className="mt-4 flex flex-wrap gap-2 text-[10px] font-semibold text-cyan-100">
          <Summary icon={<ShieldCheck size={13} />} label="7 observed findings" />
          <Summary icon={<DatabaseZap size={13} />} label="Data Health checked" />
          <Summary icon={<LockKeyhole size={13} />} label="Source locked" />
        </div>
        <p className="mt-4 text-xs leading-5 text-slate-400">
          Observed Evidence provides the factual business context. Scenario assumptions do not rewrite these findings.
        </p>
      </header>

      <div className="mt-6 space-y-3">
        {status === "loading" && (
          <p role="status" className="rounded-xl border border-slate-700 bg-slate-900/60 px-4 py-5 text-sm text-slate-400">
            Loading observed Evidence…
          </p>
        )}
        {status === "error" && (
          <p role="alert" className="rounded-xl border border-red-400/25 bg-red-400/[0.06] px-4 py-5 text-sm text-red-200">
            Evidence details could not be loaded safely.
          </p>
        )}
        {status === "loaded" && evidence.map((item) => (
          <EvidenceItem key={item.evidence_id} evidence={item} />
        ))}
      </div>
    </Drawer>
  );
}

function Summary({ icon, label }: { icon: React.ReactNode; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border border-cyan-400/15 bg-cyan-400/[0.06] px-2.5 py-1.5">
      {icon}
      {label}
    </span>
  );
}
