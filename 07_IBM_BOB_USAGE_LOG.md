# 07_IBM_BOB_USAGE_LOG.md — RoleLens Template

> 更新日期：2026-07-08  
> 用途：记录 IBM Bob 在 RoleLens 项目中的实际使用。  
> 重要：IBM Bob 是本比赛要求的 primary development tool。

# IBM Bob Usage Summary
RoleLens will use IBM Bob across the software development lifecycle:

```text
planning
architecture
code generation
debugging
refactoring
testing
documentation
README preparation
```

# Usage Log Template

## Entry 001

**Date:**  
2026-__-__

**Task:**  
[What was IBM Bob used for?]

**Project Area:**  
Architecture / Streamlit UI / Parser / Evidence Schema / Role Engine / Risk Checker / Memo Generator / Tests / README

**Prompt Used in IBM Bob:**
```text
[paste prompt here]
```

**Bob Output Summary:**
```text
[summary of what Bob generated or suggested]
```

**How I Used It:**
```text
[accepted / modified / rejected / used as reference]
```

**Manual Changes I Made:**
```text
[what I changed after Bob's output]
```

**Result:**
```text
[working module / bug fixed / draft improved / test added]
```

**Evidence Saved:**  
Yes / No

**Screenshot / Commit / File Reference:**  
[link or local note]

# Recommended IBM Bob Tasks

## Task 1 — Streamlit Skeleton
```text
Create a Streamlit app skeleton for RoleLens, an AI decision workflow system. The app should include tabs for Intake, Data Health, Evidence Board, Role Views, Workflow Plan, and Decision Memo. Keep the code simple and modular.
```

## Task 2 — CSV / Excel Parser
```text
Create a Python module that loads CSV and Excel files into pandas DataFrames, handles basic errors, detects empty files, and returns clear error messages for unsupported formats.
```

## Task 3 — Data Health Check
```text
Create a data health check module that identifies missing values, numeric outliers, data types, sample size, and potential decision risks in a pandas DataFrame.
```

## Task 4 — Evidence Object Schema
```text
Create Pydantic models for EvidenceObject, RoleView, and DecisionMemo for a role-based AI decision workflow system.
```

## Task 5 — Role Engine
```text
Create a Python module that takes evidence objects and generates role-specific decision views for Executive, Data Analyst, Data Engineer, Sales/Marketing, and Project Manager. Use structured output and validation.
```

## Task 6 — Risk Checker
```text
Create a risk checker module that flags unsupported claims, missing context, correlation-vs-causation risk, small sample size, outlier influence, and recommendations without evidence.
```

## Task 7 — Decision Memo Generator
```text
Create a decision memo generator that converts evidence objects, role views, risks, assumptions, and workflow plan into a structured Markdown memo.
```

## Task 8 — Tests
```text
Generate pytest test cases for the data parser, data health checker, evidence object validation, and risk checker modules.
```

# README Usage Section Draft
```text
## How IBM Bob Was Used

IBM Bob was used as the primary development assistant throughout the RoleLens development process. It supported architecture planning, Streamlit UI creation, data parsing modules, evidence schema design, risk checker implementation, unit test generation, debugging, refactoring, and README documentation.

The development process followed a human-in-the-loop workflow: IBM Bob generated initial code or suggestions, I reviewed and modified the outputs, tested the modules, and documented the changes in the IBM Bob usage log.
```
