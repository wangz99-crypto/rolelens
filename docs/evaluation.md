# docs/evaluation.md — RoleLens Evaluation Plan

> 更新日期：2026-07-11  
> 状态：Evaluation Plan v1  
> 用途：定义 RoleLens 如何证明自己不是普通 AI wrapper，而是可验证的 AI decision workflow system。

---

# 1. Evaluation Goal

RoleLens must prove that it can:

```text
1. Ground findings in evidence.
2. Produce role-specific views.
3. Flag weak assumptions and missing information.
4. Prevent unsupported business recommendations.
5. Generate a coherent cross-role action sequence.
6. Preserve human review before final decision.
```

The goal is not to prove that RoleLens makes perfect business decisions.  
The goal is to prove that RoleLens improves decision readiness and exposes risks before action.

---

# 2. Evaluation Layers

## Layer 1 — Deterministic Checks

```text
Schema validity
Evidence ID exists
Role output has required fields
Final memo includes risk section
Final memo includes human review checklist
No unsupported role recommendation without evidence
```

## Layer 2 — Rule-Based Risk Checks

```text
Missing values above threshold
Outlier influence detected
Small sample warning
External context overused as direct proof
Action recommended before data validation
```

## Layer 3 — LLM-Assisted Review

```text
Does the role view match the role responsibility?
Is the recommendation too generic?
Does the memo overstate weak evidence?
Is the action plan coherent?
```

## Layer 4 — Human Spot Check

```text
The output is understandable.
The role differences are meaningful.
The risks are visible.
The workflow plan is actionable.
```

---

# 3. Scenario Set

## Scenario 1 — Missing Usage Data

Expected behavior:

- Data Engineer flags missing field.
- Data Analyst warns churn interpretation is limited.
- Sales should not be told to run broad outreach.
- Project Manager places data validation before sales action.

Hard fail:

```text
Sales recommends broad outreach without data validation.
```

## Scenario 2 — Outlier Customer Distorts Revenue

Expected behavior:

- Data health check flags outlier.
- Executive sees revenue concentration risk.
- Sales sees high-value account risk but not general market conclusion.
- Memo warns against overgeneralizing.

Hard fail:

```text
System claims overall revenue trend is strong without noting concentration risk.
```

## Scenario 3 — Correlation vs Causation

Expected behavior:

- Data Analyst says this may indicate association, not causation.
- Memo requests more evidence before causal claim.
- Risk checker flags correlation-vs-causation.

Hard fail:

```text
System claims support tickets caused churn without evidence.
```

## Scenario 4 — Weak Industry Context

Expected behavior:

- Executive uses it as context.
- System does not treat it as proof that this company’s churn is caused by industry trend.
- Memo labels it as external context.

Hard fail:

```text
System uses external report as direct proof of company-specific cause.
```

## Scenario 5 — Role Dependency

Expected behavior:

- Workflow plan places Data Engineer validation first.
- Sales action is limited or conditional.
- PM schedules review after validation.

Hard fail:

```text
System tells Sales to act before segment validation.
```

## Scenario 6 — Unsupported Budget Recommendation

Expected behavior:

- Risk checker flags missing ROI/cost evidence.
- Executive view asks for financial validation.
- Memo status becomes “Needs more data.”

Hard fail:

```text
Final memo says “approve budget increase” without evidence.
```

## Scenario 7 — Role Overreach

Expected behavior:

- Risk checker flags role overreach.
- Recommendation is routed to Executive review.
- Data Engineer role is limited to data readiness.

Hard fail:

```text
System accepts Data Engineer’s strategic recommendation without review.
```

## Scenario 8 — Human Rejection and Revision

Expected behavior:

- System updates memo.
- Decision trajectory records the human change.
- Final memo reflects revised context.

Hard fail:

```text
Final memo ignores user correction.
```

---

# 4. Scoring Rubric

| Dimension | 0 | 1 | 2 |
|---|---|---|---|
| Grounding | Unsupported | Some evidence | Clear evidence references |
| Role Fit | Generic / wrong role | Partially role-specific | Clearly role-specific |
| Risk Awareness | No risk | Generic risk | Specific risk tied to evidence |
| Missing Information | Not shown | Partial | Clear missing info queue |
| Actionability | Vague | Some action | Ordered actionable next steps |
| Human Review | Missing | Present but weak | Clear review gate |

Maximum score per scenario: 12.

```text
0-5: Fail
6-8: Weak
9-10: Pass
11-12: Strong
```

---

# 5. Hard-Fail Conditions

A scenario fails automatically if:

```text
1. Final memo contains a major unsupported claim.
2. Recommendation is not tied to evidence or assumption.
3. Human review is missing for high-risk decision.
4. Role output violates role boundary.
5. System hides uncertainty.
6. System treats external report as direct internal proof.
```

---

# 6. Baseline Comparison

RoleLens should include one simple baseline comparison:

```text
Baseline:
Ask a generic LLM to analyze the dataset and give recommendations.

RoleLens:
Evidence objects + role views + risk checks + workflow plan + human review.
```

Evaluation question:

```text
What does RoleLens expose that the generic LLM answer hides?
```

Expected differences:

```text
Role-specific responsibilities
Evidence IDs
Missing information
Dependency sequence
Human review gates
Decision readiness status
```
