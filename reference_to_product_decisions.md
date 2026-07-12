# reference_to_product_decisions.md — RoleLens

> 更新日期：2026-07-11  
> 状态：Approved Product Decisions v1  
> 用途：把官方参考仓库笔记转化为 RoleLens 的正式产品决策，避免知识区停留在“资料堆”。

---

# 0. Purpose

This file converts reference research into RoleLens product decisions.

Reference notes are not product requirements by themselves. A reference becomes part of RoleLens only if it is explicitly adopted here.

---

# 1. Adopted Decisions

## D1 — Evidence Objects Are the Core Intermediate Layer

### Decision

RoleLens will use **Evidence Objects** as the core intermediate layer.

Every key role view, risk warning, workflow step, and final memo claim must be grounded in one or more evidence objects.

### Implementation

```text
app/schemas.py
app/evidence_builder.py
app/role_engine.py
app/risk_checker.py
app/memo_generator.py
```

### Rule

```text
No evidence ID, no decision claim.
```

### Status

Approved.

---

## D2 — RoleLens Uses Role Boundaries, Not Superficial Role-Play

### Decision

RoleLens roles must have:

```text
allowed inputs
required outputs
forbidden actions
review responsibilities
dependency rules
```

V1 UI may show business-friendly roles:

```text
Executive
Data Analyst / Data Scientist
Data Engineer
Sales / Marketing
Project Manager
```

Internally, each role must be controlled by a role policy.

### Implementation

```text
config/role_policy.json
app/role_engine.py
app/risk_checker.py
tests/test_role_policy.py
```

### Rule

A role cannot recommend actions outside its responsibility without flagging human review.

Examples:

- Sales cannot recommend broad customer outreach if data quality is not validated.
- Executive cannot approve budget if ROI/cost evidence is missing.
- Data Scientist cannot claim model readiness if target variable or sample quality is weak.
- Data Engineer cannot make strategic business recommendations.

### Status

Approved.

---

## D3 — RoleLens Must Preserve a Decision Trajectory

### Decision

Each RoleLens run should preserve a lightweight decision trajectory.

Minimum trajectory fields:

```json
{
  "run_id": "string",
  "timestamp": "string",
  "business_question": "string",
  "source_manifest": [],
  "data_health_summary": {},
  "evidence_objects": [],
  "role_views": [],
  "risk_results": [],
  "workflow_plan": [],
  "human_review_actions": [],
  "final_memo": "string"
}
```

### Implementation

```text
app/utils.py
app/memo_generator.py
outputs/run_logs/
```

### Status

Approved for v1 as a lightweight JSON export.

---

## D4 — IBM Bob Usage Must Be Evidence-Based

### Decision

RoleLens will maintain a public build log showing how IBM Bob supported:

```text
planning
architecture
implementation
debugging
testing
documentation
```

### Implementation

```text
docs/bob_build_log.md
07_IBM_BOB_USAGE_LOG.md
README.md
```

### Status

Approved.

---

## D5 — RoleLens Will Use Scenario-Based Evaluation

### Decision

RoleLens will include fixed evaluation scenarios.

V1 should include at least 8 scenarios:

```text
1. Missing data risk
2. Outlier distortion
3. Correlation vs causation
4. Weak industry context
5. Role dependency
6. Unsupported recommendation
7. Role overreach
8. Human rejection and regeneration
```

### Implementation

```text
docs/evaluation.md
examples/scenarios/
tests/test_scenarios.py
```

### Status

Approved.

---

## D6 — Human Review Is a Product Mechanism, Not a Disclaimer

### Decision

RoleLens must include visible human review in the UI and final memo.

V1 can simulate review instead of implementing real user accounts.

UI actions:

```text
Approve
Request changes
Add context
Mark not ready
```

Final memo must include:

```text
Human Review Checklist
Final Recommendation Status
```

### Status

Approved.

---

## D7 — RoleLens Will Not Implement MCP or Complex Agent Infrastructure in V1

### Decision

V1 will not implement:

```text
MCP servers
multi-agent frameworks
complex agent runners
vector database
GraphRAG
enterprise workflow permissions
```

Instead, RoleLens will implement the same conceptual boundaries through simple Python modules and Pydantic schemas.

### Status

Approved.

---

## D8 — README Must Include Evaluator Path

### Decision

README must include a short evaluator path:

```text
1. Run app
2. Load sample data
3. Load sample report context
4. Generate evidence objects
5. Inspect role views
6. Inspect risks and workflow plan
7. Export final memo
```

### Status

Approved.

---

# 2. Rejected or Delayed Ideas

## Not Adopted — Generic Multi-Agent Team Platform

Reason:

```text
Too broad
Hard to verify in 3 minutes
Likely to look like generic agent demo
Less aligned with Business Analytics
```

## Not Adopted for V1 — Real Email Sending

Reason:

```text
Adds permissions, privacy, and integration risks.
Not necessary to prove RoleLens value.
```

## Not Adopted for V1 — Real Approval Permissions

Reason:

```text
Would require users/accounts/roles.
Simulated review is enough for MVP.
```

## Not Adopted for V1 — Long-Term Company Memory

Reason:

```text
Difficult to prove.
Risk of false personalization.
Not needed for 3-minute demo.
```

## Delayed — LangGraph / CrewAI

Reason:

```text
Useful later for durable workflow.
Too much framework overhead before MVP value is proven.
```

---

# 3. RoleLens Product Contract

```text
Input:
Mixed business materials and a business question.

Intermediate:
Evidence objects with provenance, confidence, limitations, and role relevance.

Reasoning Layer:
Role-specific views governed by role policies.

Control Layer:
Risk checks, missing information, and human review.

Output:
Approval-ready decision memo and action sequence.
```

If a feature does not support this contract, it should not be built in v1.

---

# 4. Next Development Actions

1. Create `config/role_policy.json`.
2. Create `docs/evaluation.md`.
3. Create `docs/bob_build_log.md`.
4. Add evaluator path to README.
5. Build Streamlit skeleton using IBM Bob.
6. Build first scenario: B2B SaaS churn / retention decision.
7. Use Codex only as secondary reviewer after IBM Bob-generated code exists.
