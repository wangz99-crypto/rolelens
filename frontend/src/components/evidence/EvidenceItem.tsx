import { useId, useState } from "react";
import { ChevronDown } from "lucide-react";
import type { EvidenceDetail } from "../../api/types";

interface EvidenceItemProps {
  evidence: EvidenceDetail;
}

const scopeLabels: Record<EvidenceDetail["scope"], string> = {
  internal_observation: "Observed evidence",
  external_context: "External context",
  stated_priority: "Stated priority",
  assumption: "Assumption",
};

export function EvidenceItem({ evidence }: EvidenceItemProps) {
  const [expanded, setExpanded] = useState(false);
  const detailId = useId();

  return (
    <article className="rounded-xl border border-cyan-400/15 bg-cyan-400/[0.035]">
      <button
        type="button"
        aria-expanded={expanded}
        aria-controls={detailId}
        onClick={() => setExpanded((current) => !current)}
        className="block w-full px-4 py-3 text-left outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-cyan-300/70"
      >
        <span className="flex items-start justify-between gap-3">
          <span>
            <span className="block text-sm font-semibold text-slate-100">
              {evidence.label}
            </span>
            <span className="mt-1.5 block text-[11px] leading-4 text-slate-400">
              {evidence.finding}
            </span>
          </span>
          <ChevronDown
            size={15}
            aria-hidden="true"
            className={`mt-0.5 shrink-0 text-cyan-300 transition-transform ${expanded ? "rotate-180" : ""}`}
          />
        </span>
        <span className="mt-2 inline-flex rounded bg-cyan-400/10 px-2 py-1 text-[9px] font-bold uppercase tracking-[0.12em] text-cyan-200">
          {scopeLabels[evidence.scope]}
        </span>
      </button>
      {expanded && (
        <div id={detailId} className="border-t border-cyan-400/10 px-4 py-3">
          <dl className="grid grid-cols-[88px_1fr] gap-x-3 gap-y-2 text-[11px]">
            <EvidenceField label="Source" value={evidence.source_label} />
            <EvidenceField label="Method" value={capitalize(evidence.extraction_method)} />
            <EvidenceField label="Scope" value={scopeLabels[evidence.scope]} />
            <EvidenceField label="Confidence" value={capitalize(evidence.confidence)} />
            <dt className="text-slate-500">Limitations</dt>
            <dd className="text-slate-300">
              {evidence.limitations.length > 0 ? (
                <ul className="space-y-1">
                  {evidence.limitations.map((limitation) => (
                    <li key={limitation}>• {limitation}</li>
                  ))}
                </ul>
              ) : (
                "None recorded"
              )}
            </dd>
            <EvidenceField label="Evidence ID" value={evidence.evidence_id} mono />
          </dl>
        </div>
      )}
    </article>
  );
}

function capitalize(value: string): string {
  return `${value.charAt(0).toUpperCase()}${value.slice(1).replace("_", " ")}`;
}

function EvidenceField({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <>
      <dt className="text-slate-500">{label}</dt>
      <dd className={mono ? "font-mono text-[10px] text-cyan-200" : "text-slate-300"}>
        {value}
      </dd>
    </>
  );
}
