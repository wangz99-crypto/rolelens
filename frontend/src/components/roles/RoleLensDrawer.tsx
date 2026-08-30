import type {
  Assumption,
  EvidenceDetail,
  ImpactKind,
  ProductDecision,
  RoleBriefLifecycle,
  RoleImpactBrief,
  RoleImpactBriefSetResponse,
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
  briefSet: RoleImpactBriefSetResponse | null;
  briefLifecycle: RoleBriefLifecycle;
  isGeneratingBrief: boolean;
  briefError: string | null;
  onGenerateBrief: () => void;
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
  briefSet,
  briefLifecycle,
  isGeneratingBrief,
  briefError,
  onGenerateBrief,
  onClose,
}: RoleLensDrawerProps) {
  const role = currentRole(data, roleKey);
  const relevantEvidence = evidence.filter((item) =>
    item.relevant_roles.includes(roleKey),
  );
  const brief = briefSet?.briefs.find((item) => item.role_key === roleKey);

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

      <GraniteBrief
        lifecycle={briefLifecycle}
        brief={brief}
        data={data}
        evidence={evidence}
        dirty={dirty}
        isGenerating={isGeneratingBrief}
        error={briefError}
        onGenerate={onGenerateBrief}
      />

      <EvidenceContext
        status={evidenceStatus}
        evidence={relevantEvidence}
      />
    </Drawer>
  );
}

function GraniteBrief({
  lifecycle,
  brief,
  data,
  evidence,
  dirty,
  isGenerating,
  error,
  onGenerate,
}: {
  lifecycle: RoleBriefLifecycle;
  brief: RoleImpactBrief | undefined;
  data: ProductDecision;
  evidence: EvidenceDetail[];
  dirty: boolean;
  isGenerating: boolean;
  error: string | null;
  onGenerate: () => void;
}) {
  const hasBrief = lifecycle !== "NOT_GENERATED" && brief !== undefined;
  const evidenceLabels = brief?.evidence_refs.map(
    (reference) =>
      evidence.find((item) => item.evidence_id === reference)?.label ?? reference,
  );
  const assumptionLabels = brief?.assumption_refs.map(
    (reference) =>
      data.assumptions.find((item) => item.assumption_id === reference)?.label ??
      reference,
  );
  return (
    <RoleSection title="IBM Granite Brief">
      <div
        className={`rounded-xl border p-4 ${
          lifecycle === "STALE"
            ? "border-amber-400/25 bg-amber-400/[0.05]"
            : hasBrief
              ? "border-violet-400/25 bg-violet-400/[0.06]"
              : "border-slate-700 bg-slate-900/50"
        }`}
      >
        <p
          className={`text-xs font-bold tracking-[0.14em] ${
            lifecycle === "STALE"
              ? "text-amber-200"
              : hasBrief
                ? "text-violet-200"
                : "text-slate-300"
          }`}
        >
          {lifecycle.replace("_", " ")}
        </p>
        {lifecycle === "NOT_GENERATED" && (
          <p className="mt-2 text-xs leading-5 text-slate-500">
            Role-aware interpretation has not been generated yet.
          </p>
        )}
        {lifecycle === "STALE" && (
          <p className="mt-2 text-xs leading-5 text-amber-100/80">
            This brief was generated for the previous accepted decision state.
          </p>
        )}
        {hasBrief && brief && (
          <div className="mt-4 space-y-4">
            <p className="text-[10px] font-semibold tracking-[0.1em] text-violet-300">
              IBM Granite · watsonx.ai
            </p>
            <BriefField title="Why it matters" text={brief.why_it_matters} />
            <BriefField title="What still holds" text={brief.what_still_holds} />
            <BriefField
              title="What to verify next"
              text={brief.what_to_verify_next}
            />
            <BriefField title="Next handoff" text={brief.next_handoff} />
            <div>
              <h4 className="text-[10px] font-bold uppercase tracking-[0.12em] text-slate-500">
                Grounding
              </h4>
              <p className="mt-1.5 text-xs leading-5 text-slate-300">
                Evidence: {evidenceLabels?.join(", ")}
              </p>
              <p className="text-xs leading-5 text-slate-300">
                Assumptions: {assumptionLabels?.join(", ") || "None"}
              </p>
            </div>
          </div>
        )}
        {dirty && (
          <p className="mt-4 text-xs leading-5 text-amber-200">
            Recalculate or revert the unsaved assumption edit before generating a new brief.
          </p>
        )}
        {error && (
          <p role="alert" className="mt-4 text-xs leading-5 text-red-200">
            {error}
          </p>
        )}
        {lifecycle !== "CURRENT" && (
          <button
            type="button"
            disabled={dirty || isGenerating}
            onClick={onGenerate}
            className="mt-4 rounded-lg border border-violet-400/30 bg-violet-400/10 px-3 py-2 text-xs font-semibold text-violet-100 transition hover:bg-violet-400/15 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {isGenerating
              ? "Generating…"
              : lifecycle === "STALE"
                ? "Refresh Role Brief"
                : "Generate Role Brief"}
          </button>
        )}
      </div>
    </RoleSection>
  );
}

function BriefField({ title, text }: { title: string; text: string }) {
  return (
    <div>
      <h4 className="text-[10px] font-bold uppercase tracking-[0.12em] text-slate-500">
        {title}
      </h4>
      <p className="mt-1.5 text-xs leading-5 text-slate-200">{text}</p>
    </div>
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
