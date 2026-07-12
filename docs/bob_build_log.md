# docs/bob_build_log.md — RoleLens

> 更新日期：2026-07-11  
> 状态：Build Log Template  
> 用途：公开记录 IBM Bob 如何作为主要开发工具参与 RoleLens 的规划、实现、测试和文档。

# IBM Bob Build Log

IBM Bob is used as the primary development assistant for RoleLens.

This log records how Bob supported the project across:

```text
planning
architecture
implementation
debugging
testing
documentation
```

---

# Entry Template

## Entry 001 — [Task Name]

**Date:**  
2026-__-__

**Project Area:**  
Planning / Architecture / UI / Parser / Schema / Role Engine / Risk Checker / Workflow Planner / Memo Generator / Tests / README

**Prompt Given to IBM Bob:**

```text
[prompt]
```

**Bob Output Summary:**

```text
[what Bob generated or suggested]
```

**Human Review:**

```text
[accepted / changed / rejected]
```

**Manual Changes:**

```text
[what I changed and why]
```

**Resulting Files:**

```text
[file paths]
```

**Test / Verification:**

```text
[how I verified it works]
```

**Related Commit:**

```text
[commit hash or link]
```

**Evidence Saved:**  
Yes / No

---

# Planned Bob Tasks

## Task 1 — Streamlit Skeleton

Create the app shell with tabs:

```text
Intake
Data Health
Evidence Board
Role Views
Workflow Plan
Decision Memo
```

## Task 2 — Data Parser

Load CSV / Excel into pandas DataFrame with clear errors for unsupported or empty files.

## Task 3 — Pydantic Schemas

Define:

```text
EvidenceObject
RoleView
DecisionMemo
RiskFinding
WorkflowStep
```

## Task 4 — Data Health Checker

Detect:

```text
missing values
outliers
sample size issues
suspicious columns
decision-readiness warnings
```

## Task 5 — Evidence Builder

Convert data summaries and report context into structured evidence objects.

## Task 6 — Role Engine

Generate role-specific views using evidence objects and role policy.

## Task 7 — Risk Checker

Flag:

```text
unsupported claims
correlation-vs-causation
missing context
overused external context
action before validation
```

## Task 8 — Workflow Planner

Generate cross-role action sequence with dependencies and human review gates.

## Task 9 — Decision Memo Generator

Create an approval-ready memo with evidence, risks, assumptions, action sequence, and review checklist.

## Task 10 — Tests

Generate pytest tests for parser, schema validation, data health checks, and risk checker.
