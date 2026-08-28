import { fractionToPercentDisplay } from "../../api/decimal";
import {
  formatSignedCurrency,
  scenarioStatusCompactLabel,
  scenarioStatusLabel,
} from "../../api/presentation";
import {
  isRecalculatedDecision,
  type Assumption,
  type DemoDecision,
  type ProductDecision,
} from "../../api/types";
import { Drawer } from "../drawer/Drawer";

interface RevisionHistoryDrawerProps {
  baseline: DemoDecision;
  current: ProductDecision;
  dirty: boolean;
  onClose: () => void;
}

export function RevisionHistoryDrawer({
  baseline,
  current,
  dirty,
  onClose,
}: RevisionHistoryDrawerProps) {
  const hasRevision =
    isRecalculatedDecision(current) && current.diff.kind !== "no_change";

  return (
    <Drawer labelledBy="revision-history-drawer-title" onClose={onClose}>
      <header className="pr-12">
        <p className="eyebrow text-orange-300">Accepted state</p>
        <h2 id="revision-history-drawer-title" className="mt-1 text-xl font-semibold text-white">
          Revision History
        </h2>
        <p className="mt-4 text-xs leading-5 text-slate-400">
          This prototype shows the baseline and latest accepted revision in the current browser session.
        </p>
        {dirty && (
          <p className="mt-4 rounded-lg border border-amber-400/20 bg-amber-400/[0.06] px-3 py-2 text-[11px] text-amber-200">
            An unsaved assumption edit is not reflected in this view.
          </p>
        )}
      </header>

      <div className="mt-6 space-y-4">
        {hasRevision && isRecalculatedDecision(current) && (
          <LatestRevision data={current} />
        )}
        <BaselineRevision baseline={baseline} current={!hasRevision} />
        {!hasRevision && (
          <p className="rounded-xl border border-slate-700 bg-slate-900/50 px-4 py-3 text-xs text-slate-400">
            No human revision has been calculated in this session.
          </p>
        )}
      </div>
    </Drawer>
  );
}

function LatestRevision({
  data,
}: {
  data: Extract<ProductDecision, { diff: unknown }>;
}) {
  const affected = data.roles.filter(
    (role) =>
      !["data_analyst", "data_engineer"].includes(role.role_key) &&
      role.impact_kind !== "unchanged",
  );
  const foundations = data.roles.filter((role) =>
    ["data_analyst", "data_engineer"].includes(role.role_key),
  );
  const statusText =
    data.before_scenario.status === data.scenario.status &&
    data.scenario.status === "CLEARS_BREAK_EVEN"
      ? "Still clears"
      : `${scenarioStatusCompactLabel(data.before_scenario.status)} → ${scenarioStatusCompactLabel(data.scenario.status)}`;

  return (
    <article data-testid="revision-rev-002" className="rounded-xl border border-orange-400/25 bg-orange-400/[0.05] p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-sm font-bold text-white">REV-002</p>
          <p className="mt-1 text-[10px] font-semibold tracking-[0.14em] text-orange-200">
            HUMAN REVISION
          </p>
        </div>
        <span className="rounded-full border border-orange-400/25 bg-orange-400/10 px-2 py-1 text-[9px] font-bold tracking-[0.12em] text-orange-200">
          CURRENT
        </span>
      </div>
      <p className="mt-3 text-xs font-semibold text-slate-200">{data.diff.headline}</p>

      <RevisionSection title="Changed Assumptions">
        {data.diff.changed_assumptions.map((change) => {
          const assumption = data.assumptions.find(
            (item) => item.assumption_id === change.assumption_id,
          )!;
          return (
            <RevisionRow
              key={change.assumption_id}
              label={change.label}
              value={`${formatAssumption(change.before_value, assumption)} → ${formatAssumption(change.after_value, assumption)}`}
            />
          );
        })}
      </RevisionSection>

      <RevisionSection title="Scenario">
        <RevisionRow
          label="Net scenario value"
          value={`${formatSignedCurrency(data.before_scenario.net_scenario_value, data.before_scenario.currency)} → ${formatSignedCurrency(data.scenario.net_scenario_value, data.scenario.currency)}`}
        />
        <RevisionRow label="Break-even" value={statusText} />
      </RevisionSection>

      <RevisionSection title="Affected">
        {affected.map((role) => (
          <RevisionRow
            key={role.role_key}
            label={role.label}
            value={role.impact_kind.toUpperCase()}
          />
        ))}
      </RevisionSection>

      <RevisionSection title="Unchanged Foundations">
        {foundations.map((role) => (
          <RevisionRow key={role.role_key} label={role.label} value="UNCHANGED" />
        ))}
        <RevisionRow label="7 Evidence Objects" value="UNCHANGED" />
        <RevisionRow label="Data Health" value="UNCHANGED" />
        <RevisionRow label="Source provenance" value="UNCHANGED" />
      </RevisionSection>

      <details className="mt-4 border-t border-slate-800 pt-3 text-[11px] text-slate-400">
        <summary className="cursor-pointer font-semibold text-slate-300">Technical details</summary>
        <dl className="mt-3 grid grid-cols-[120px_1fr] gap-2">
          <dt>Revision ID</dt><dd className="font-mono">{data.revision.revision_id}</dd>
          <dt>Scenario ID</dt><dd className="font-mono">{data.scenario.scenario_id}</dd>
          <dt>Changed IDs</dt>
          <dd className="font-mono">
            {data.diff.changed_assumptions.map((item) => item.assumption_id).join(", ")}
          </dd>
        </dl>
      </details>
    </article>
  );
}

function BaselineRevision({
  baseline,
  current,
}: {
  baseline: DemoDecision;
  current: boolean;
}) {
  const lift = baseline.assumptions.find(
    (item) => item.key === "expected_incremental_lift",
  )!;
  return (
    <article data-testid="revision-rev-001" className="rounded-xl border border-slate-700 bg-slate-900/55 p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-sm font-bold text-white">REV-001</p>
          <p className="mt-1 text-[10px] font-semibold tracking-[0.14em] text-slate-400">BASELINE</p>
        </div>
        {current && (
          <span className="rounded-full border border-cyan-400/20 bg-cyan-400/10 px-2 py-1 text-[9px] font-bold tracking-[0.12em] text-cyan-200">
            CURRENT
          </span>
        )}
      </div>
      <dl className="mt-4 space-y-2.5">
        <RevisionRow label="Expected lift" value={formatAssumption(lift.value, lift)} />
        <RevisionRow
          label="Net scenario value"
          value={formatSignedCurrency(
            baseline.scenario.net_scenario_value,
            baseline.scenario.currency,
          )}
        />
        <RevisionRow
          label="Break-even"
          value={scenarioStatusLabel(baseline.scenario.status)}
        />
        <RevisionRow
          label="Evidence Foundation"
          value={`${baseline.evidence.governed_evidence_count} governed findings`}
        />
      </dl>
    </article>
  );
}

function formatAssumption(value: number, assumption: Assumption): string {
  if (assumption.unit === "fraction") {
    return `${fractionToPercentDisplay(value).replace(/\.0$/, "")}%`;
  }
  if (assumption.currency) {
    return `${value.toLocaleString("en-US")} ${assumption.currency}`;
  }
  return `${value.toLocaleString("en-US")} ${assumption.unit}`;
}

function RevisionSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mt-4 border-t border-slate-800 pt-3">
      <h3 className="mb-2 text-[9px] font-bold uppercase tracking-[0.14em] text-slate-500">
        {title}
      </h3>
      <dl className="space-y-2">{children}</dl>
    </section>
  );
}

function RevisionRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start justify-between gap-4 text-xs">
      <dt className="text-slate-500">{label}</dt>
      <dd className="text-right font-semibold text-slate-200">{value}</dd>
    </div>
  );
}
