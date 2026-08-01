# RoleLens product-first UI

Task 10C-2B makes the business decision summary primary and moves dense
governance detail to a secondary Audit Trail. The backend pipeline is
unchanged: Evidence, role outcomes, risk results, WorkflowPlan, simulated
human review, and DecisionMemo remain the authoritative typed records.

## Information architecture

The six primary tabs, in order, are:

1. **Decision Brief** — dataset identity, business question, decision posture,
   four profile metrics, three evidence-cited patterns, and four guardrails.
2. **Data Explained** — deterministic Dataset Primer, fixed glossary, profile
   aggregates, and the optional Granite orientation.
3. **Role Comparison** — a five-row comparison showing why each function asks
   a different question, plus one selected concise role detail.
4. **Action Plan** — WorkflowPlan status and a bounded view of the first three
   blockers and first five role-owned actions.
5. **Review & Memo** — compact workflow counts, unchanged simulated-review
   inputs, and a summary of the composed DecisionMemo.
6. **Audit Trail** — full Data Health, Evidence, roles and risks, WorkflowPlan,
   and DecisionMemo lineage.

This hierarchy lets an evaluator understand the decision in the first screen
without deleting any inspectable provenance.

## Explicit source modes

`demo_source_mode` is exactly one of `none`, `ibm_telco`, `custom`, or
`synthetic_fixture`.

- **IBM Telco public demo** is the primary quick start. It uses only the frozen
  public CSV and context sidecar and explicitly activates
  `ibm_telco_churn_v1` during preparation.
- **Custom** uses the uploaded object's stable `getvalue()` bytes and never
  activates a business playbook. No playbook is inferred from a filename,
  columns, or file hash. When a custom upload replaces either predefined
  sample, all five predefined context fields are cleared so sample context
  cannot silently carry into custom Evidence.
- **Synthetic fixture** is available only under Advanced / QA and never
  activates a business profile.
- **None** produces a controlled source-selection error.

The single resolver returns the CSV bytes, filename, business-profile ID, and
human-readable label together. The displayed and prepared source therefore
share one selection boundary. Loading a source does not prepare Evidence or
call a provider.

The Advanced / QA synthetic loader is constructed before the custom uploader.
This lets either predefined loader clear prior uploader state before Streamlit
instantiates the uploader widget, preserving Streamlit widget-state safety.

## Deterministic and Granite explanations

Before live analysis, the IBM Decision Brief uses deterministic
BusinessDatasetProfile values and matching business Evidence IDs. If Granite
orientation succeeds, only the three presentation pattern cards are replaced
by its validated text and exact citations and are labeled **IBM Granite
orientation**. If orientation fails, a controlled notice is shown and the
deterministic patterns remain visible. The failure is never mislabeled as
Granite output.

The Dataset Primer remains deterministic. Its 10-field glossary, fictional
sample disclosure, currency status, four guardrails, and TotalCharges quality
note are shown before any model explanation. Charts use existing profile
aggregates; the UI does not reread or recompute the CSV. Contract churn rate,
median tenure, and median MonthlyCharges use three separate charts because
tenure and MonthlyCharges are different measures. No currency is inferred.

## Comparison, coordination, and review

Role Comparison exposes five fixed primary questions and only the first
grounded claim in its main table. Full RoleViews and typed failures remain in
Audit Trail. Raw provider failure reasons are never rendered.

Action Plan compresses presentation only. It neither groups nor rewrites
WorkflowSteps; step IDs, owners, statuses, and Evidence IDs are retained, and
the complete unchanged plan remains in Audit Trail.

Review & Memo keeps the exact HumanReviewStepInput rules. **Load editable demo
review** populates controls only; it does not record review, clear blockers,
compose a memo, or call a provider. Recording remains explicit. MemoSummary
counts and references existing DecisionMemo records without changing them.
Unresolved blockers, revisions requiring revalidation, and the lack of
execution authority remain visible.

## Safety boundaries

Only **Run with IBM Granite** invokes live analysis. Streamlit reruns, source
loading, preparation, tab changes, expanders, role selection, review controls,
review recording, and memo composition do not call a provider. The UI shows
only a boolean watsonx.ai configuration status and never displays secrets.

The product makes no customer prediction, targeting or outreach
recommendation, causal inference, ROI or financial-return claim, or execution
authorization. Descriptive evidence supports a limited validation posture for
human review only.

## Three-minute evaluator path

| Time | Evaluator action |
|---|---|
| 0:00–0:20 | Load **IBM Telco public demo** and prepare deterministic Evidence. |
| 0:20–0:45 | Decision Brief: 7,043 customers, 26.54% recorded churn, controlled posture. |
| 0:45–1:10 | Data Explained: glossary, contract pattern, tenure and charge medians. |
| 1:10–1:40 | Role Comparison: show how five functions ask different questions. |
| 1:40–2:05 | Action Plan: blockers and role-owned actions. |
| 2:05–2:35 | Review & Memo: load editable demo review, record, and compose. |
| 2:35–2:55 | Audit Trail: inspect Evidence IDs and preserved governance. |
| 2:55–3:00 | Close on Future of Work value: shared, reviewable human decisions. |
