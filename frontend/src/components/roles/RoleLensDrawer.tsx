import type {
  Assumption,
  EvidenceDetail,
  ImpactKind,
  ProductDecision,
  RoleKey,
} from "../../api/types";
import { isRecalculatedDecision } from "../../api/types";
import { fractionToPercentDisplay } from "../../api/decimal";
import {
  formatSignedCurrency,
  scenarioStatusLabel,
} from "../../api/presentation";
import { Drawer } from "../drawer/Drawer";
import { EvidenceItem } from "../evidence/EvidenceItem";

interface RoleLensDrawerProps {
  data: ProductDecision;
  roleKey: RoleKey;
  evidenceStatus: "loading" | "loaded" | "error";
  evidence: EvidenceDetail[];
  dirty: boolean;
  onClose: () => void;
}

const scenarioRoles = new Set<RoleKey>([
  "executive",
  "sales_marketing",
  "project_manager",
]);

export function RoleLensDrawer({
  data,
  roleKey,
  evidenceStatus,
  evidence,
  dirty,
  onClose,
}: RoleLensDrawerProps) {
  const role = currentRole(data, roleKey);
  const relevantEvidence = evidence.filter((item) =>
    item.relevant_roles.includes(roleKey),
  );

  return (
    <Drawer labelledBy="role-lens-drawer-title" onClose={onClose}>
      <header className="pr-12">
        <p className="eyebrow text-cyan-300">Role Lens</p>
        <h2 id="role-lens-drawer-title" className="mt-1 text-xl font-semibold uppercase text-white">
          {role.label}
        </h2>
        <p className="mt-2 text-sm font-semibold uppercase tracking-[0.08em] text-slate-300">
          {role.state}
        </p>
        <ImpactBadge impact={role.impactKind} />
        {dirty && (
          <p className="mt-4 rounded-lg border border-amber-400/20 bg-amber-400/[0.06] px-3 py-2 text-[11px] text-amber-200">
            An unsaved assumption edit is not reflected in this view.
          </p>
        )}
      </header>

      <RoleSection title="System State">
        <p className="text-sm font-semibold text-white">{role.state}</p>
      </RoleSection>

      {scenarioRoles.has(roleKey) && (
        <ScenarioContext data={data} />
      )}

      {roleKey === "data_analyst" && (
        <EvidenceContext
          status={evidenceStatus}
          evidence={relevantEvidence}
        />
      )}

      {roleKey === "data_analyst" && (
        <RoleSection title="Foundation Status">
          <p className="text-sm font-semibold text-cyan-100">
            {isRecalculatedDecision(data)
              ? "Observed Evidence unchanged"
              : "Observed Evidence locked"}
          </p>
          <p className="mt-2 text-xs leading-5 text-slate-400">
            Scenario revisions do not rewrite observed Evidence.
          </p>
        </RoleSection>
      )}

      {roleKey === "data_engineer" && (
        <RoleSection title="Data Foundation">
          <ul className="space-y-2 text-sm text-cyan-100">
            <li>
              {isRecalculatedDecision(data)
                ? "Data Health unchanged"
                : "Data Health checked"}
            </li>
            <li>
              {isRecalculatedDecision(data)
                ? "Source provenance unchanged"
                : "Source provenance locked"}
            </li>
          </ul>
          <p className="mt-3 text-xs leading-5 text-slate-400">
            Scenario revisions do not alter the prepared data foundation.
          </p>
        </RoleSection>
      )}

      {roleKey !== "data_analyst" && (
        <EvidenceContext
          status={evidenceStatus}
          evidence={relevantEvidence}
        />
      )}

      <RoleSection title="IBM Granite Brief">
        <p className="text-xs font-bold tracking-[0.14em] text-slate-300">
          NOT GENERATED
        </p>
        <p className="mt-2 text-xs leading-5 text-slate-500">
          Role-aware interpretation has not been generated yet.
        </p>
      </RoleSection>
    </Drawer>
  );
}

function currentRole(data: ProductDecision, roleKey: RoleKey): {
  label: string;
  state: string;
  impactKind: ImpactKind;
} {
  if (isRecalculatedDecision(data)) {
    const role = data.roles.find((item) => item.role_key === roleKey);
    if (!role) {
      throw new Error("Trusted role state is unavailable.");
    }
    return { label: role.label, state: role.state, impactKind: role.impact_kind };
  }
  const role = data.roles.find((item) => item.role_key === roleKey);
  if (!role) {
    throw new Error("Trusted role state is unavailable.");
  }
  return {
    label: role.label,
    state: role.baseline_state,
    impactKind: "current",
  };
}

function ScenarioContext({ data }: { data: ProductDecision }) {
  return (
    <RoleSection title="Current Scenario">
      <dl className="space-y-3">
        <ScenarioRow
          label="Net scenario value"
          value={formatSignedCurrency(
            data.scenario.net_scenario_value,
            data.scenario.currency,
          )}
        />
        <ScenarioRow
          label="Modeled break-even"
          value={scenarioStatusLabel(data.scenario.status)}
        />
        {data.assumptions.map((assumption) => {
          const change = isRecalculatedDecision(data)
            ? data.diff.changed_assumptions.find(
                (item) => item.assumption_id === assumption.assumption_id,
              )
            : undefined;
          return (
            <ScenarioRow
              key={assumption.assumption_id}
              label={assumption.label}
              value={
                change
                  ? `${formatAssumption(change.before_value, assumption)} → ${formatAssumption(change.after_value, assumption)}`
                  : formatAssumption(assumption.value, assumption)
              }
              changed={Boolean(change)}
            />
          );
        })}
      </dl>
    </RoleSection>
  );
}

function EvidenceContext({
  status,
  evidence,
}: {
  status: "loading" | "loaded" | "error";
  evidence: EvidenceDetail[];
}) {
  return (
    <RoleSection title="Evidence Context">
      {status === "loading" && (
        <p role="status" className="text-sm text-slate-400">Loading relevant observed Evidence…</p>
      )}
      {status === "error" && (
        <p role="alert" className="text-sm text-red-200">Evidence context could not be loaded safely.</p>
      )}
      {status === "loaded" && (
        <div className="space-y-2">
          {evidence.map((item) => (
            <EvidenceItem key={item.evidence_id} evidence={item} />
          ))}
        </div>
      )}
    </RoleSection>
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

function ScenarioRow({
  label,
  value,
  changed = false,
}: {
  label: string;
  value: string;
  changed?: boolean;
}) {
  return (
    <div className="flex items-start justify-between gap-4 border-b border-slate-800 pb-2.5 last:border-0 last:pb-0">
      <dt className="text-xs text-slate-500">{label}</dt>
      <dd className="text-right text-xs font-semibold text-slate-200">
        {value}
        {changed && (
          <span className="ml-2 rounded bg-orange-400/10 px-1.5 py-0.5 text-[8px] tracking-[0.1em] text-orange-200">
            CHANGED
          </span>
        )}
      </dd>
    </div>
  );
}

function ImpactBadge({ impact }: { impact: ImpactKind }) {
  const tones: Record<ImpactKind, string> = {
    current: "border-slate-600 bg-slate-800 text-slate-300",
    unchanged: "border-cyan-400/25 bg-cyan-400/10 text-cyan-200",
    recomputed: "border-amber-400/25 bg-amber-400/10 text-amber-200",
    changed: "border-orange-400/25 bg-orange-400/10 text-orange-200",
    blocked: "border-red-400/25 bg-red-400/10 text-red-200",
  };
  return (
    <span className={`mt-3 inline-flex rounded-full border px-2.5 py-1 text-[9px] font-bold tracking-[0.13em] ${tones[impact]}`}>
      {impact.toUpperCase()}
    </span>
  );
}

function RoleSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mt-6 border-t border-slate-800 pt-5">
      <h3 className="mb-3 text-[10px] font-bold uppercase tracking-[0.16em] text-slate-500">
        {title}
      </h3>
      {children}
    </section>
  );
}
