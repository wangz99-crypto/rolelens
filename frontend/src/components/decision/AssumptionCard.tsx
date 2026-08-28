import { AlertTriangle, RotateCw } from "lucide-react";

export interface AssumptionDraft {
  pilot_population: string;
  expected_incremental_lift_pct: string;
  cost_per_intervention: string;
  retained_customer_value: string;
}

interface AssumptionCardProps {
  draft: AssumptionDraft;
  dirty: boolean;
  isRecalculating: boolean;
  error: string | null;
  onChange: (key: keyof AssumptionDraft, value: string) => void;
  onRecalculate: () => void;
}

export function AssumptionCard({
  draft,
  dirty,
  isRecalculating,
  error,
  onChange,
  onRecalculate,
}: AssumptionCardProps) {
  return (
    <section className="rail-card" aria-labelledby="assumptions-title">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="eyebrow text-amber-300">Human input</p>
          <h2 id="assumptions-title" className="mt-1 text-sm font-semibold text-slate-100">Decision Assumptions</h2>
        </div>
        {dirty && (
          <span className="rounded-full border border-amber-400/30 bg-amber-400/10 px-2 py-1 text-[9px] font-semibold tracking-[0.12em] text-amber-200">UNSAVED REVISION</span>
        )}
      </div>
      <div className="mt-3 grid grid-cols-2 gap-2.5">
        <AssumptionInput label="Pilot population" value={draft.pilot_population} suffix="customers" min="1" step="1" disabled={isRecalculating} onChange={(value) => onChange("pilot_population", value)} />
        <AssumptionInput label="Expected lift (%)" value={draft.expected_incremental_lift_pct} suffix="%" min="0" max="100" step="0.1" preserveDecimalDisplay disabled={isRecalculating} onChange={(value) => onChange("expected_incremental_lift_pct", value)} />
        <AssumptionInput label="Cost / intervention" value={draft.cost_per_intervention} suffix="USD" min="0" step="0.01" disabled={isRecalculating} onChange={(value) => onChange("cost_per_intervention", value)} />
        <AssumptionInput label="Retained value" value={draft.retained_customer_value} suffix="USD" min="0.01" step="0.01" disabled={isRecalculating} onChange={(value) => onChange("retained_customer_value", value)} />
      </div>
      {dirty && <p className="mt-2.5 text-[10px] leading-4 text-amber-200/75">Impact Map still reflects the last calculated decision.</p>}
      {error && (
        <p role="alert" className="mt-2.5 flex items-start gap-2 text-[10px] leading-4 text-red-300">
          <AlertTriangle size={13} className="mt-0.5 shrink-0" aria-hidden="true" />
          {error}
        </p>
      )}
      <button
        type="button"
        disabled={!dirty || isRecalculating}
        onClick={onRecalculate}
        className="mt-3 inline-flex w-full items-center justify-center gap-2 rounded-lg bg-amber-300 px-3 py-2.5 text-xs font-semibold text-slate-950 transition hover:bg-amber-200 disabled:cursor-not-allowed disabled:bg-slate-800 disabled:text-slate-500"
      >
        <RotateCw size={14} className={isRecalculating ? "animate-spin" : ""} aria-hidden="true" />
        {isRecalculating ? "Recalculating..." : "Recalculate Impact"}
      </button>
      <p className="mt-2.5 border-t border-amber-400/15 pt-2.5 text-[10px] text-amber-200/65">Human-supplied assumptions</p>
    </section>
  );
}

function AssumptionInput({
  label,
  value,
  suffix,
  min,
  max,
  step,
  preserveDecimalDisplay = false,
  disabled,
  onChange,
}: {
  label: string;
  value: string;
  suffix: string;
  min: string;
  max?: string;
  step: string;
  preserveDecimalDisplay?: boolean;
  disabled: boolean;
  onChange: (value: string) => void;
}) {
  return (
    <label className="block rounded-lg border border-amber-400/15 bg-amber-400/[0.04] px-2.5 py-2">
      <span className="block text-[10px] text-slate-400">{label}</span>
      <span className="mt-1 flex items-center gap-1.5">
        <input
          aria-label={label}
          type={preserveDecimalDisplay ? "text" : "number"}
          inputMode={preserveDecimalDisplay ? "decimal" : undefined}
          value={value}
          min={min}
          max={max}
          step={step}
          disabled={disabled}
          onChange={(event) => onChange(event.target.value)}
          className="min-w-0 flex-1 bg-transparent text-sm font-semibold tabular-nums text-amber-100 outline-none"
        />
        <span className="text-[9px] font-medium text-amber-300/60">{suffix}</span>
      </span>
    </label>
  );
}
