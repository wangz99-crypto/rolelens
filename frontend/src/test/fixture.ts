import type { DemoDecision } from "../api/types";

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
