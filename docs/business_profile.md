# IBM Telco Churn Business Profile

RoleLens uses explicit decision playbooks instead of treating an arbitrary CSV
as a generic chat prompt. A playbook fixes the accepted source shape, approved
calculations, evidence language, role relevance, and decision boundaries before
Granite interprets anything. Task 10C-1 introduces one playbook:
`ibm_telco_churn_v1`.

## Provenance and selection boundary

The playbook accepts the frozen IBM Telco Customer Churn CSV in
`sample_data/public`. IBM describes this as a fictional telecommunications
customer sample; it is not real production customer data. The profile must be
selected explicitly by ID. RoleLens does not infer it from the filename or
column names, and the profiler does not perform online research.

The existing synthetic B2B SaaS fixture remains separate and continues to
support deterministic failure-path testing. It is not reinterpreted as the IBM
Telco profile.

## Deterministic frozen metrics

The approved local CSV produces these exact aggregate facts:

- 7,043 rows and 7,043 unique fictional customers
- 1,869 churned and 5,174 retained customers; overall churn rate 26.54%
- Contract: Month-to-month 1,655/3,875 (42.71%), One year 166/1,473
  (11.27%), Two year 48/1,695 (2.83%)
- TechSupport: No 1,446/3,473 (41.64%), Yes 310/2,044 (15.17%), No
  internet service 113/1,526 (7.40%)
- InternetService: Fiber optic 1,297/3,096 (41.89%), DSL 459/2,421
  (18.96%), No 113/1,526 (7.40%)
- PaymentMethod: Electronic check 1,071/2,365 (45.29%), Mailed check
  308/1,612 (19.11%), Bank transfer (automatic) 258/1,544 (16.71%), and
  Credit card (automatic) 232/1,522 (15.24%)
- Retained medians: tenure 38.0, MonthlyCharges 64.43, TotalCharges 1,683.60
- Churned medians: tenure 10.0, MonthlyCharges 79.65, TotalCharges 703.55
- 11 blank or nonnumeric `TotalCharges` values

`TotalCharges` is stored as text in the original CSV. Its 11 unparseable values
are excluded from `TotalCharges` median calculations. This limitation affects
calculations that use that column; it does not invalidate the other approved
profile metrics.

## Seven business Evidence types

The profiler emits candidates in this fixed order. Evidence IDs are minted only
after the candidates pass through `app/evidence_builder.py`.

| Evidence type | Aggregate fact | Relevant roles |
|---|---|---|
| `business_overall_churn` | Dataset-wide churn baseline | Executive, Data Analyst, Sales/Marketing, Project Manager |
| `business_contract_churn` | Churn by contract | Executive, Data Analyst, Sales/Marketing, Project Manager |
| `business_support_churn` | Churn by TechSupport status | Data Analyst, Sales/Marketing, Executive |
| `business_internet_churn` | Churn by InternetService | Data Analyst, Sales/Marketing, Executive |
| `business_payment_churn` | Churn by PaymentMethod | Data Analyst, Sales/Marketing, Executive |
| `business_churn_medians` | Tenure and charge medians by churn status | Executive, Data Analyst, Sales/Marketing |
| `business_parseability` | `TotalCharges` parsing limitation | Data Engineer, Data Analyst, Project Manager |

The Evidence Objects remain active, deterministic, internal observations that
point to the original CSV manifest and tabular source locators. The typed
`BusinessDatasetProfile` is not added as a new role-policy input; roles receive
approved business findings only through Evidence Objects.

## Interpretation and action boundary

All comparisons are descriptive associations. They do not establish causation,
individual churn probability, or financial return. Aggregate differences do
not authorize customer scoring, customer-level recommendations, targeting,
automated outreach, real approval, or execution. They can orient the dataset,
support role-specific interpretation, and inform the design of a limited
validation pilot subject to the existing governed workflow and human review.

## Future of Work value

Business users receive one shared set of deterministic facts, while each
function sees only the implications relevant to its responsibility. Granite
may interpret the resulting Evidence Objects in a later stage, but it does not
invent the underlying business metrics.

The Granite Dataset Orientation Brief and the Streamlit redesign are deferred
to Task 10C-2.
