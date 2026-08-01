# RoleLens Streamlit demo

Run locally with:

```bash
streamlit run app/main.py
```

RoleLens turns validated business inputs into Evidence Objects, five
policy-constrained role views, risk review, a deterministic WorkflowPlan,
explicit simulated human review, and a deterministic DecisionMemo. Roles are
views over shared Evidence, not autonomous agents.

## Product-first navigation

The six primary tabs are **Decision Brief**, **Data Explained**, **Role
Comparison**, **Action Plan**, **Review & Memo**, and **Audit Trail**. Business
meaning is primary; dense implementation and provenance detail is secondary.
Audit Trail retains the full Data Health record, every EvidenceObject field,
full RoleViews and typed failures, deterministic and semantic risks, every
WorkflowStep field, and the complete DecisionMemo with Evidence lineage.

## Demo setup and source selection

All setup is in the sidebar. **Load IBM Telco public demo** is the primary
quick start. It loads the frozen public context and selects the frozen public
CSV but does not prepare Evidence or call Granite. Preparing this mode
explicitly passes `ibm_telco_churn_v1` to the existing deterministic pipeline.

A custom CSV always runs in generic Evidence mode. It never activates the IBM
playbook automatically, even if its filename or columns resemble the public
sample. Custom upload bytes come from `getvalue()`, never a consumed cursor.
The existing synthetic B2B SaaS fixture is available under **Advanced / QA**
and is profile-free. Switching from either predefined sample to a custom
upload clears all five predefined context fields; manually entered custom
context may persist when one custom file replaces another.

The Advanced / QA synthetic loader is rendered before the custom uploader is
constructed. Both predefined loaders can therefore clear prior uploader state
without mutating an already-instantiated Streamlit widget.

The single `demo_source_mode` value is `none`, `ibm_telco`, `custom`, or
`synthetic_fixture`. Source selection returns bytes, filename, profile ID, and
display label as one deterministic result. Changing the source or any context
field invalidates prepared Evidence and downstream analysis, review, and memo.
Unrelated session state is preserved. Reset clears the RoleLens source label
and RoleLens-owned state.

## Deterministic preparation and live execution

**Prepare evidence** performs intake, parsing, Data Health, optional approved
business profiling, and Evidence minting without constructing a provider.
Preparation is transactional: state changes only after success.

**Run with IBM Granite** is the only control that calls
`run_live_demo_analysis()`. It remains disabled until preparation succeeds.
Live state replacement is also transactional. Streamlit reruns, tab changes,
expanders, role selection, review controls, and memo composition never repeat
a provider call. There is no retry, cache, parallelism, or silent fallback.

The header displays only whether `WATSONX_APIKEY`, `WATSONX_URL`, and
`WATSONX_PROJECT_ID` are configured. Secret values are never displayed.

## IBM Telco presentation

The Decision Brief leads with the fictional-sample disclosure, business
question, controlled decision posture, four frozen metrics, three cited
patterns, and four Dataset Primer guardrails. Before live analysis, patterns
come from the deterministic business profile. A successful validated Granite
orientation replaces only those three presentation patterns and preserves its
Evidence IDs. A typed orientation failure keeps the deterministic version and
shows a controlled notice.

Data Explained shows the deterministic 10-field glossary, the fact that
currency is unspecified, the 11 TotalCharges parse issues, and three native
charts built only from BusinessDatasetProfile values. Contract churn
rate, median tenure, and median MonthlyCharges are displayed in three separate
charts because tenure and MonthlyCharges are different measures; no currency
is inferred. It then shows a
successful orientation under **Explained by IBM Granite**, or a controlled
warning if orientation was unavailable.

## Roles, workflow, review, and memo

Role Comparison makes the five functional questions visible in one table and
allows inspection of one concise role detail. Full outputs remain in Audit
Trail.

Action Plan shows exact counts and only the first three blockers and first five
role-owned actions. This is presentation compression, not work-package
grouping: WorkflowPlan and every WorkflowStep remain unchanged.

Review & Memo preserves all human-review rules. **Load editable demo review**
only populates editable fields. **Record simulated human review** remains an
explicit action, and a complete HumanReviewSession is still required before
memo composition. MemoSummary is a view over the existing DecisionMemo. It
does not clear blockers or revision warnings. Simulated review never
authorizes execution.

## Safety and evaluator path

The demo makes no customer-level prediction, targeting or outreach
recommendation, causal inference, ROI claim, or execution claim. The IBM data
is a fictional sample, not production customer data.

For a three-minute walkthrough: load and prepare IBM Telco (0:00–0:20), scan
Decision Brief (0:20–0:45), inspect Data Explained (0:45–1:10), compare roles
(1:10–1:40), review Action Plan (1:40–2:05), record the editable demo review
and compose the memo (2:05–2:35), inspect Evidence IDs in Audit Trail
(2:35–2:55), and close on shared, reviewable Future of Work decisions
(2:55–3:00).
