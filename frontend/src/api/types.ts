export type ScenarioStatus =
  | "CLEARS_BREAK_EVEN"
  | "DOES_NOT_CLEAR_BREAK_EVEN"
  | "NOT_EVALUABLE";

export type RoleKey =
  | "executive"
  | "data_analyst"
  | "data_engineer"
  | "sales_marketing"
  | "project_manager";

export type ImpactKind =
  | "current"
  | "unchanged"
  | "recomputed"
  | "changed"
  | "blocked";

export interface DecisionSummary {
  decision_id: string;
  title: string;
  business_question: string;
  source_label: string;
  disclosure: string;
}

export interface RevisionSummary {
  revision_id: "rev-001" | "rev-002";
  label: "Baseline" | "Human revision";
}

export interface EvidenceSummary {
  status: "LOCKED";
  governed_evidence_count: number;
  customer_count: number;
  recorded_churn_rate_pct: number;
  month_to_month_churn_rate_pct: number;
  total_charges_parse_issue_count: number;
  data_health_checked: boolean;
  source_provenance_locked: boolean;
}

export interface RevisionEvidenceSummary extends EvidenceSummary {
  observed_evidence_unchanged: boolean;
  data_health_unchanged: boolean;
  source_provenance_unchanged: boolean;
}

export interface EvidenceDetail {
  evidence_id: string;
  evidence_type: string;
  label: string;
  finding: string;
  confidence: "low" | "medium" | "high";
  extraction_method: "deterministic" | "llm_assisted";
  scope:
    | "internal_observation"
    | "external_context"
    | "stated_priority"
    | "assumption";
  source_label: "IBM Telco public demo";
  limitations: string[];
  relevant_roles: RoleKey[];
}

export interface Assumption {
  assumption_id: string;
  key: string;
  label: string;
  value: number;
  unit: string;
  currency: string | null;
  source_scope: "user_assumption";
}

export interface Scenario {
  scenario_id: string;
  status: ScenarioStatus;
  expected_incremental_retained: number;
  expected_scenario_value: number;
  intervention_cost: number;
  net_scenario_value: number;
  break_even_lift: number;
  currency: string;
}

export interface BaselineRoleState {
  role_key: RoleKey;
  label: string;
  baseline_state: string;
  state_kind: "current" | "foundation";
}

export interface RevisionRoleState {
  role_key: RoleKey;
  label: string;
  state: string;
  impact_kind: ImpactKind;
}

export interface ChangedAssumption {
  assumption_id: string;
  key: string;
  label: string;
  before_value: number;
  after_value: number;
  unit: string;
  currency: string | null;
}

export interface DecisionDiff {
  kind: "decision_posture_changed" | "scenario_changed" | "no_change";
  headline: string;
  changed_assumptions: ChangedAssumption[];
  scenario_status_changed: boolean;
  role_posture_changed: boolean;
  observed_evidence_unchanged: boolean;
}

export interface DemoDecision {
  decision: DecisionSummary;
  revision: RevisionSummary;
  evidence: EvidenceSummary;
  assumptions: Assumption[];
  scenario: Scenario;
  roles: BaselineRoleState[];
  accepted_state_fingerprint: string;
}

export interface RecalculatedDecision {
  decision: DecisionSummary;
  revision: RevisionSummary;
  evidence: RevisionEvidenceSummary;
  assumptions: Assumption[];
  before_scenario: Scenario;
  scenario: Scenario;
  roles: RevisionRoleState[];
  diff: DecisionDiff;
  accepted_state_fingerprint: string;
}

export type ProductDecision = DemoDecision | RecalculatedDecision;

export interface RecalculateDecisionInput {
  pilot_population: number;
  expected_incremental_lift: string;
  cost_per_intervention: string;
  retained_customer_value: string;
  currency: "USD";
}

export type RoleBriefLifecycle = "NOT_GENERATED" | "CURRENT" | "STALE";

export interface RoleImpactBrief {
  role_key: RoleKey;
  why_it_matters: string;
  what_still_holds: string;
  what_to_verify_next: string;
  evidence_refs: string[];
  assumption_refs: string[];
  next_handoff: string;
}

export interface RoleImpactBriefSetResponse {
  accepted_state_fingerprint: string;
  provider: "IBM watsonx.ai";
  model_id: string;
  briefs: RoleImpactBrief[];
}

export function isRecalculatedDecision(
  decision: ProductDecision,
): decision is RecalculatedDecision {
  return "diff" in decision;
}
