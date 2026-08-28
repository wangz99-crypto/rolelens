import type {
  DemoDecision,
  EvidenceDetail,
  RecalculatedDecision,
} from "../api/types";

export const evidenceDetailFixture: EvidenceDetail[] = [
  {
    evidence_id: "ev-business_ove-2a4fdf4a1858",
    evidence_type: "business_overall_churn",
    label: "Overall recorded churn",
    finding: "1,869 of 7,043 customers are marked as churned (26.54%). This descriptive result is an association, not a causal conclusion.",
    confidence: "high",
    extraction_method: "deterministic",
    scope: "internal_observation",
    source_label: "IBM Telco public demo",
    limitations: [
      "This is a descriptive association and does not establish causation.",
      "Aggregate differences do not authorize individual customer targeting or outreach.",
      "The sample describes a fictional IBM telco dataset.",
    ],
    relevant_roles: ["executive", "data_analyst", "sales_marketing", "project_manager"],
  },
  {
    evidence_id: "ev-business_con-6a24581b8b1d",
    evidence_type: "business_contract_churn",
    label: "Recorded churn by contract",
    finding: "Month-to-month: 1,655 of 3,875 churned (42.71%); One year: 166 of 1,473 churned (11.27%); Two year: 48 of 1,695 churned (2.83%). This descriptive result is an association, not a causal conclusion.",
    confidence: "high",
    extraction_method: "deterministic",
    scope: "internal_observation",
    source_label: "IBM Telco public demo",
    limitations: ["Contract groups may differ on other observed or unobserved factors."],
    relevant_roles: ["executive", "data_analyst", "sales_marketing", "project_manager"],
  },
  {
    evidence_id: "ev-business_sup-2b8f9e6d7223",
    evidence_type: "business_support_churn",
    label: "Recorded churn by tech support",
    finding: "TechSupport No: 1,446 of 3,473 churned (41.64%); Yes: 310 of 2,044 churned (15.17%); No internet service: 113 of 1,526 churned (7.40%). This descriptive result is an association, not a causal conclusion.",
    confidence: "high",
    extraction_method: "deterministic",
    scope: "internal_observation",
    source_label: "IBM Telco public demo",
    limitations: ["TechSupport status is not evidence of service-effect direction."],
    relevant_roles: ["data_analyst", "sales_marketing", "executive"],
  },
  {
    evidence_id: "ev-business_int-75e7bf0d54db",
    evidence_type: "business_internet_churn",
    label: "Recorded churn by internet service",
    finding: "Fiber optic: 1,297 of 3,096 churned (41.89%); DSL: 459 of 2,421 churned (18.96%); No internet service: 113 of 1,526 churned (7.40%). This descriptive result is an association, not a causal conclusion.",
    confidence: "high",
    extraction_method: "deterministic",
    scope: "internal_observation",
    source_label: "IBM Telco public demo",
    limitations: ["Service categories may reflect different customer contexts."],
    relevant_roles: ["data_analyst", "sales_marketing", "executive"],
  },
  {
    evidence_id: "ev-business_pay-dd2d3cfffadc",
    evidence_type: "business_payment_churn",
    label: "Recorded churn by payment method",
    finding: "Electronic check: 1,071 of 2,365 churned (45.29%); Mailed check: 308 of 1,612 churned (19.11%); Bank transfer (automatic): 258 of 1,544 churned (16.71%); Credit card (automatic): 232 of 1,522 churned (15.24%). This descriptive result is an association, not a causal conclusion.",
    confidence: "high",
    extraction_method: "deterministic",
    scope: "internal_observation",
    source_label: "IBM Telco public demo",
    limitations: ["Payment methods may correlate with other account characteristics."],
    relevant_roles: ["data_analyst", "sales_marketing", "executive"],
  },
  {
    evidence_id: "ev-business_chu-2fea03c8df5e",
    evidence_type: "business_churn_medians",
    label: "Churn-status medians",
    finding: "Churned customers have median tenure 10.0 versus 38.0 for retained customers, and median MonthlyCharges 79.65 versus 64.43.",
    confidence: "high",
    extraction_method: "deterministic",
    scope: "internal_observation",
    source_label: "IBM Telco public demo",
    limitations: ["Medians summarize groups and do not describe every customer."],
    relevant_roles: ["executive", "data_analyst", "sales_marketing"],
  },
  {
    evidence_id: "ev-business_par-5024e8abf481",
    evidence_type: "business_parseability",
    label: "TotalCharges parseability",
    finding: "11 of 7,043 TotalCharges values are blank or nonnumeric (0.16%); the original column is stored as text.",
    confidence: "high",
    extraction_method: "deterministic",
    scope: "internal_observation",
    source_label: "IBM Telco public demo",
    limitations: ["TotalCharges medians exclude the 11 unparseable values."],
    relevant_roles: ["data_engineer", "data_analyst", "project_manager"],
  },
];

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
