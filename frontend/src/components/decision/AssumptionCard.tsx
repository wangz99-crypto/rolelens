import { LockKeyhole } from "lucide-react";
import type { Assumption } from "../../api/types";

interface AssumptionCardProps {
  assumptions: Assumption[];
}

function displayValue(assumption: Assumption): string {
  if (assumption.key === "expected_incremental_lift") {
    return `${(assumption.value * 100).toFixed(1)}%`;
  }
  if (assumption.currency) {
    return `${assumption.value.toLocaleString("en-US")} ${assumption.currency}`;
  }
  return `${assumption.value.toLocaleString("en-US")} ${assumption.unit}`;
}

export function AssumptionCard({ assumptions }: AssumptionCardProps) {
  return (
    <section className="rail-card" aria-labelledby="assumptions-title">
      <div className="flex items-center justify-between">
        <div>
          <p className="eyebrow text-amber-300">Human input</p>
          <h2 id="assumptions-title" className="mt-1 text-sm font-semibold text-slate-100">
            Decision Assumptions
          </h2>
        </div>
        <LockKeyhole size={16} className="text-amber-300/80" aria-hidden="true" />
      </div>
      <dl className="mt-3 divide-y divide-slate-800">
        {assumptions.map((assumption) => (
          <div key={assumption.assumption_id} className="flex items-center justify-between gap-4 py-2.5">
            <dt className="text-xs text-slate-400">{assumption.label}</dt>
            <dd className="text-sm font-semibold text-amber-100">
              {displayValue(assumption)}
            </dd>
          </div>
        ))}
      </dl>
      <p className="mt-2 border-t border-amber-400/15 pt-3 text-[11px] text-amber-200/65">
        Human-supplied assumptions
      </p>
    </section>
  );
}
