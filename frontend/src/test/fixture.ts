import type { DemoDecision, RecalculatedDecision } from "../api/types";

export const demoDecisionFixture: DemoDecision = {
  decision: {
    decision_id: "dec-001",
    title: "Customer Retention Pilot",
    business_question: "Is the current evidence sufficient to approve a limited customer-retention pilot, and what must each function validate before any outreach begins?",
    source_label: "IBM Telco",
    disclosure: "This is a fictional IBM sample dataset, not real customer production data.",
  },
  revision: { revision_id: "rev-001", label: "Baseline" },
  evidence: {
    status: "LOCKED",
    governed_evidence_count: 7,
    customer_count: 7043,
    recorded_churn_rate_pct: 26.54,
    month_to_month_churn_rate_pct: 42.71,
    total_charges_parse_issue_count: 11,
    data_health_checked: true,
    source_provenance_locked: true,
  },
  assumptions: [
    { assumption_id: "asm-001", key: "pilot_population", label: "Pilot population", value: 500, unit: "customers", currency: null, source_scope: "user_assumption" },
    { assumption_id: "asm-002", key: "expected_incremental_lift", label: "Expected lift", value: 0.08, unit: "fraction", currency: null, source_scope: "user_assumption" },
    { assumption_id: "asm-003", key: "cost_per_intervention", label: "Cost / intervention", value: 30, unit: "currency_per_customer", currency: "USD", source_scope: "user_assumption" },
    { assumption_id: "asm-004", key: "retained_customer_value", label: "Retained value", value: 500, unit: "currency_per_customer", currency: "USD", source_scope: "user_assumption" },
  ],
  scenario: {
    scenario_id: "scn-001",
    status: "CLEARS_BREAK_EVEN",
    expected_incremental_retained: 40,
    expected_scenario_value: 20000,
    intervention_cost: 15000,
    net_scenario_value: 5000,
    break_even_lift: 0.06,
    currency: "USD",
  },
  roles: [
    { role_key: "executive", label: "Executive", baseline_state: "Pilot review candidate", state_kind: "current" },
    { role_key: "data_analyst", label: "Data Analyst", baseline_state: "Evidence basis valid", state_kind: "foundation" },
    { role_key: "data_engineer", label: "Data Engineer", baseline_state: "Data foundation valid", state_kind: "foundation" },
    { role_key: "sales_marketing", label: "Sales / Marketing", baseline_state: "Eligible for pilot review", state_kind: "current" },
    { role_key: "project_manager", label: "Project Manager", baseline_state: "Prepare limited pilot review", state_kind: "current" },
  ],
};

const unchangedEvidence = {
  ...demoDecisionFixture.evidence,
  observed_evidence_unchanged: true,
  data_health_unchanged: true,
  source_provenance_unchanged: true,
};

export const heroRevisionFixture: RecalculatedDecision = {
  ...demoDecisionFixture,
  revision: { revision_id: "rev-002", label: "Human revision" },
  evidence: unchangedEvidence,
  assumptions: demoDecisionFixture.assumptions.map((assumption) =>
    assumption.key === "expected_incremental_lift"
      ? { ...assumption, value: 0.03 }
      : assumption,
  ),
  before_scenario: demoDecisionFixture.scenario,
  scenario: {
    ...demoDecisionFixture.scenario,
    status: "DOES_NOT_CLEAR_BREAK_EVEN",
    expected_incremental_retained: 15,
    expected_scenario_value: 7500,
    net_scenario_value: -7500,
  },
  roles: [
    { role_key: "executive", label: "Executive", state: "Validate assumptions first", impact_kind: "changed" },
    { role_key: "data_analyst", label: "Data Analyst", state: "Evidence basis remains valid", impact_kind: "unchanged" },
    { role_key: "data_engineer", label: "Data Engineer", state: "Data foundation remains valid", impact_kind: "unchanged" },
    { role_key: "sales_marketing", label: "Sales / Marketing", state: "Blocked by scenario", impact_kind: "blocked" },
    { role_key: "project_manager", label: "Project Manager", state: "Reopen scenario validation", impact_kind: "changed" },
  ],
  diff: {
    kind: "decision_posture_changed",
    headline: "Decision posture changed",
    changed_assumptions: [
      {
        assumption_id: "asm-002",
        key: "expected_incremental_lift",
        label: "Expected lift",
        before_value: 0.08,
        after_value: 0.03,
        unit: "fraction",
        currency: null,
      },
    ],
    scenario_status_changed: true,
    role_posture_changed: true,
    observed_evidence_unchanged: true,
  },
};

export const sevenPercentRevisionFixture: RecalculatedDecision = {
  ...heroRevisionFixture,
  assumptions: demoDecisionFixture.assumptions.map((assumption) =>
    assumption.key === "expected_incremental_lift"
      ? { ...assumption, value: 0.07 }
      : assumption,
  ),
  scenario: {
    ...demoDecisionFixture.scenario,
    expected_incremental_retained: 35,
    expected_scenario_value: 17500,
    net_scenario_value: 2500,
  },
  roles: [
    { role_key: "executive", label: "Executive", state: "Pilot review candidate", impact_kind: "recomputed" },
    { role_key: "data_analyst", label: "Data Analyst", state: "Evidence basis remains valid", impact_kind: "unchanged" },
    { role_key: "data_engineer", label: "Data Engineer", state: "Data foundation remains valid", impact_kind: "unchanged" },
    { role_key: "sales_marketing", label: "Sales / Marketing", state: "Eligible for pilot review", impact_kind: "recomputed" },
    { role_key: "project_manager", label: "Project Manager", state: "Prepare limited pilot review", impact_kind: "recomputed" },
  ],
  diff: {
    kind: "scenario_changed",
    headline: "Scenario changed; decision posture remains the same",
    changed_assumptions: [
      {
        assumption_id: "asm-002",
        key: "expected_incremental_lift",
        label: "Expected lift",
        before_value: 0.08,
        after_value: 0.07,
        unit: "fraction",
        currency: null,
      },
    ],
    scenario_status_changed: false,
    role_posture_changed: false,
    observed_evidence_unchanged: true,
  },
};
