# RoleLens Streamlit Demo — Task 10A

> **Run command:** `streamlit run app/main.py`

---

## Overview

RoleLens is an evidence-grounded AI decision workflow for business teams.
It makes the following transformation visible through a six-tab Streamlit UI:

```
mixed business materials
  → typed sources
  → Evidence Objects
  → five policy-constrained role views
  → deterministic and probabilistic risk review
  → governed workflow
  → explicit simulated human review
  → deterministic Decision Memo
```

The five roles are **policy-constrained views over shared Evidence**.
They are not autonomous AI employees.

---

## Six-Tab Information Architecture

| Tab | Name | What It Shows |
|-----|------|---------------|
| 1 | **Intake** | CSV upload, context fields, sample loader, data preview, Prepare and Run buttons |
| 2 | **Data Health** | Row count, duplicate rows, missing-value rates, mixed-type columns, schema issues |
| 3 | **Evidence Board** | One card per EvidenceObject: evidence_id, scope, finding, limitations, source locator |
| 4 | **RoleLens Views** | Five role views with claims and citations, deterministic risks, semantic candidates |
| 5 | **Workflow Plan** | Ordered steps, blockers, review gates, human review controls, synthetic preset |
| 6 | **Decision Memo** | Post-review memo: retained actions, rejected steps, blockers, evidence, control notices |

---

## Synthetic B2B SaaS Demo Scenario

**File:** `sample_data/b2b_saas_retention_demo.csv`

A synthetic B2B SaaS customer/account dataset with 17–18 rows and these fields:

- `account_id`, `customer_segment`, `arr_band`, `renewal_status`
- `support_ticket_count`, `last_login_days`, `product_usage_score`, `contract_value`

**Deliberate quality problems:**
- One exact duplicate row (ACC-004 repeated)
- Missing values in `product_usage_score` (2 rows)
- Missing values in `contract_value` (2 rows)
- No real company or customer names; no personal data; no credentials

**File:** `sample_data/b2b_saas_retention_demo.json`

Sidecar context with these exact keys:
- `industry_context` — external industry observation, explicitly not company evidence
- `strategy_profile` — stated strategic priority, not verified performance data
- `business_question` — decision context only, produces no EvidenceObject
- `decision_goal` — decision context only, produces no EvidenceObject
- `user_assumption` — unverified assumption, visibly flagged in risk review

---

## Deterministic vs. Live Granite Boundaries

### Deterministic (no provider call, no env var reads):
- Clicking **Prepare evidence**
- Viewing Data Health, Evidence Board tabs
- Loading the synthetic review preset
- Recording simulated human review
- Composing the Decision Memo

### Live IBM Granite / watsonx.ai (requires env vars):
- Clicking **Run RoleLens with IBM Granite** — the only button that calls the model

---

## Required Environment Variables

```
WATSONX_APIKEY       — IBM watsonx.ai API key
WATSONX_URL          — watsonx.ai service URL (e.g. https://us-south.ml.cloud.ibm.com)
WATSONX_PROJECT_ID   — watsonx.ai project ID
WATSONX_MODEL_ID     — optional; defaults to ibm/granite-4-h-small
```

The UI displays `watsonx.ai configured` or `watsonx.ai not configured` as a boolean
flag. **Secret values are never displayed.**

---

## Sample Loading

Click **Load synthetic B2B SaaS demo** to populate all context fields and mark the
demo CSV for use. This button does not call Granite. Users may also upload their own
CSV and edit any text field. The loader writes directly to the actual
`field_*` widget-state keys, so all five editable values are visible on the
next rendered state. It also removes any currently uploaded custom CSV before
the uploader widget is reconstructed. Selecting or clearing a custom upload
disables sample-CSV mode. Exactly one CSV source mode is therefore active, so
the displayed context and prepared Evidence cannot accidentally refer to
different CSV source selections.

The loader does not prepare Evidence automatically. Uploaded files are
prepared from stable full bytes (`getvalue()`), not from a consumed read
cursor, so repeated preparation of the same upload is cursor-independent.

**CSV only is supported in Task 10A.** Excel, PDF, and image parsing are not available.

---

## Session-State Behavior

All pipeline results are stored in `st.session_state` under RoleLens-specific keys:

| Key | Content |
|-----|---------|
| `rolelens_prepared_inputs` | PreparedDemoInputs |
| `rolelens_analysis_result` | DemoAnalysisResult |
| `rolelens_review_session` | HumanReviewSession |
| `rolelens_decision_memo` | DecisionMemo |

**A Streamlit widget rerun (tab change, expander, review selector) never repeats a
Granite call.** Only the explicit **Run RoleLens with IBM Granite** button triggers
`run_live_demo_analysis()`.

Changing the uploaded CSV or any decision-context input immediately invalidates
prepared Evidence and all downstream results. Live execution remains disabled
until **Prepare evidence** succeeds again. Editable context values, the upload
widget state during text edits, and unrelated application state are preserved.

The **Reset demo** button clears only RoleLens results and demo-owned sample,
context, and review widget state. A successful re-prepare or live rerun clears
stale downstream review decisions, notes, revisions, preset state, review
sessions, and memos. State replacement is transactional: a preparation or
provider failure during an intentional rerun does not destroy the last
successful analysis, review session, memo, or editable review controls when
those values were not already invalidated by an input change. Unrelated
Streamlit application state is not cleared.

---

## No Silent Fallback

There is no mock mode, offline fallback, or silent retry. If watsonx.ai is not
configured or the provider fails, the UI displays a clear error and preserves any
previously completed state (unless Reset is clicked).

---

## Human Review Behavior

1. After a live run, go to **Tab 5 — Workflow Plan**.
2. Each workflow step displays a decision selector: `select / accept / reject / revise`.
3. Semantic review gates do not offer `revise`.
4. Click **Synthetic review preset — review before recording** to populate the
   editable synthetic preset.
   - The preset is labeled **"Synthetic review preset — review before recording"**.
   - It changes editable decision, note, and revision widget values only.
   - It does not record review, call `review_workflow_plan()`, compose a memo,
     or clear blockers.
5. Click **Record simulated human review** to call `review_workflow_plan()` and
   produce a `HumanReviewSession`.
6. A pending session (some steps not reviewed) is displayed but does not enable
   the memo.

Semantic-gate accept and reject decisions both require a written reviewer
note, and that note is preserved in the typed `HumanReviewStepInput`. Semantic
gates cannot be revised.

An empty `no_actionable_steps` workflow does not fabricate a step. It requires
the reviewer to enter a non-blank **No-action review note** and click
**Acknowledge no actionable workflow**. That explicit written acknowledgment
completes the empty-plan review and enables composition of the deterministic
`no_action_acknowledged` Decision Memo.

**Warning always shown:** "Simulated review does not authorize execution."

---

## Safe Failure Display

Role-generation failures retain their typed role and `failure_code`, but use
deterministic sanitized display reasons. Raw provider exceptions, payload
content, secret values, and Pydantic validation URLs are not retained in demo
analysis results or rendered in the UI. Preparation and unexpected
review-validation errors likewise use concise controlled messages.

---

## Decision Memo Behavior

1. Go to **Tab 6 — Decision Memo**.
2. The **Compose reviewed Decision Memo** button is enabled only when the
   `HumanReviewSession` is complete.
3. The memo is composed by `compose_decision_memo()` — deterministic, no Granite call.
4. Sections displayed in order:
   - Review state
   - Retained action sequence
   - Semantic review decisions
   - Rejected steps
   - Unresolved blockers
   - Missing information
   - Evidence cited
   - Control notices
5. Human revisions always show:
   **"Human revision — evidence support not revalidated"**
6. Download buttons are not available in Task 10A.

---

## Three-Minute Evaluator Path

| Time | Action |
|------|--------|
| 0:00–0:20 | Read the positioning text and process ribbon: Evidence → Roles → Risks → Workflow → Human Review → Memo |
| 0:20–0:40 | Click **Load synthetic B2B SaaS demo**, observe fields populated. Click **Prepare evidence**. Note: no Granite call yet. |
| 0:40–1:15 | Go to **Evidence Board** — note evidence_id on every card, scope labels, limitations. Check **Data Health** for duplicates and missing values. |
| 1:15–1:45 | Click **Run RoleLens with IBM Granite**. When complete, go to **RoleLens Views** — observe role concerns, citations, typed failures. Check deterministic risks and semantic candidates. |
| 1:45–2:15 | Go to **Workflow Plan** — observe step IDs, blockers (🔴), review gates (🟡). Click **Synthetic review preset — review before recording**, review the values, then click **Record simulated human review**. |
| 2:15–2:40 | Go to **Decision Memo** — click **Compose reviewed Decision Memo**. Observe retained actions, human revision warning, control notices. |
| 2:40–3:00 | Return to Intake — explain IBM Granite role, Bob-assisted development, and Future of Work value: human-in-the-loop AI decisions with full evidence lineage. |

---

## Known Limitations

- **Live output latency:** Role view generation takes 30–90 seconds depending on
  evidence size and model load.
- **Semantic review is probabilistic:** Candidates are non-authoritative. Dispositions
  are not verified facts.
- **The sample is synthetic:** No real companies, customers, or credentials.
- **Simulated review is not real approval:** No execution authority is granted.
- **Blocker acceptance is not blocker completion:** Accepting a remediation step does
  not mark the underlying blocker as resolved.
- **Human revisions require revalidation:** Evidence-level support is not rechecked
  automatically.
- **No production deployment claim:** This is a prototype demonstration for the IBM AI
  Builders Challenge.
- **Task 10A scope:** No Markdown/PDF export, no authentication, no database storage,
  no LangGraph/CrewAI/vector DB, no automatic human-review decisions, no Excel or PDF
  parsing.
