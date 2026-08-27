export type ScenarioStatus =
  | "CLEARS_BREAK_EVEN"
  | "DOES_NOT_CLEAR_BREAK_EVEN"
  | "NOT_EVALUABLE";

export interface DecisionSummary {
  decision_id: string;
  title: string;
  business_question: string;
  source_label: string;
  disclosure: string;
}

export interface RevisionSummary {
  revision_id: "rev-001";
  label: "Baseline";
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

export interface RoleState {
  role_key:
    | "executive"
    | "data_analyst"
    | "data_engineer"
    | "sales_marketing"
    | "project_manager";
  label: string;
  baseline_state: string;
  state_kind: "current" | "foundation";
}

export interface DemoDecision {
  decision: DecisionSummary;
  revision: RevisionSummary;
  evidence: EvidenceSummary;
  assumptions: Assumption[];
  scenario: Scenario;
  roles: RoleState[];
}
