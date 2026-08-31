# README Outline — RoleLens

> 更新日期：2026-07-11  
> 状态：README Outline v2  
> 主要更新：加入 evaluator path、evaluation、Bob build evidence、reference-derived product decisions。

# RoleLens

**AI Decision Team for Business Data**

RoleLens converts mixed business materials — structured data, reports, and strategy context — into role-specific insights, risks, missing information, and an approval-ready decision workflow.

## Selected Challenge Theme

**Wildcard Challenge — Build Intelligent Systems for the Future of Work**

## Problem Statement

Business teams often make decisions from mixed materials: spreadsheets, reports, dashboards, industry context, and incomplete assumptions. Different roles need different views of the same evidence, but existing AI tools often produce one generic answer.

RoleLens helps teams move from data and reports to coordinated, evidence-backed decisions.

## Why RoleLens Is Different

Most AI tools return one generic answer.

RoleLens instead creates a structured decision workflow:

```text
materials → evidence objects → role-specific views → risk checks → action sequence → human-reviewed memo
```

RoleLens is not a generic chatbot, not a dashboard clone, and not a full enterprise workflow platform.

## Target Users

- Junior business analysts
- Business Analytics students
- Small teams
- Student consulting teams
- Startup / small business operators

## 5-Minute Evaluator Path

```text
1. Install dependencies.
2. Run the Streamlit app.
3. Load the sample B2B SaaS churn dataset.
4. Paste the sample industry context.
5. Enter the strategy goal: reduce churn among high-value customers.
6. Generate evidence objects.
7. Review role-specific views.
8. Inspect risk flags and missing information.
9. Generate workflow plan.
10. Export decision memo.
```

Expected outcome:

```text
The app should show why Sales should not act broadly before Data Engineer / Data Analyst validation, and why Executive review is needed before retention budget decisions.
```

## Solution Overview

RoleLens processes business materials and generates:

- evidence objects
- data health warnings
- role-specific decision views
- risks and assumptions
- missing information
- cross-role action sequence
- decision memo
- human review checklist

## Core Workflow

```text
Upload data and context
↓
Build evidence objects
↓
Generate role-specific views
↓
Check risks and assumptions
↓
Plan cross-role action sequence
↓
Generate decision memo
↓
Human review
```

## AI Approach

RoleLens uses AI to:

1. Extract evidence from business materials.
2. Generate role-specific perspectives.
3. Identify missing information and weak assumptions.
4. Draft a decision memo.
5. Help humans review decision readiness.

Structured schemas and rule-based checks are used to reduce unsupported outputs.

## Architecture

```text
Streamlit UI
↓
File Intake
↓
Data Parser / Text Parser
↓
Evidence Object Builder
↓
RoleLens Decision Engine
↓
Risk Checker
↓
Workflow Planner
↓
Decision Memo Generator
↓
Human Review
```

## Evidence Object Contract

Every key finding should be represented as an evidence object.

Rule:

```text
No evidence ID, no decision claim.
```

## Evaluation

RoleLens includes fixed evaluation scenarios:

- missing data risk
- outlier distortion
- correlation vs causation
- weak industry context
- role dependency
- unsupported budget recommendation
- role overreach
- human rejection and revision

## How IBM Bob Was Used

IBM Bob was used as the primary development assistant for:

- architecture planning
- Streamlit app skeleton
- CSV / Excel parser
- Pydantic schema design
- data health checker
- role engine
- risk checker
- decision memo generator
- tests
- debugging
- README drafting

See:

```text
docs/bob_build_log.md
07_IBM_BOB_USAGE_LOG.md
```

## Features

- CSV / Excel upload
- business context input
- evidence cards
- role-specific views
- risk detection
- action sequence generation
- decision memo output
- human review checklist

## Demo Scenario

A B2B SaaS team receives customer churn data and an industry report excerpt. RoleLens helps the team identify revenue risk, data quality issues, sales action constraints, and the correct decision workflow.

## Installation

```bash
git clone [repo-url]
cd rolelens
pip install -r requirements.txt
streamlit run app/main.py
```

## Tech Stack

- Python
- Streamlit
- pandas
- openpyxl
- Pydantic
- PyMuPDF / pdfplumber
- IBM Bob for development assistance

## Limitations

- Does not connect to live BI tools in v1.
- Does not perform real email sending or enterprise approval.
- Does not replace human decision-makers.
- Does not treat external industry reports as direct proof of company-specific outcomes.
- Requires human review before action.

## Future Improvements

- PDF parsing improvements
- richer document ingestion
- optional LangGraph-based human-in-the-loop workflow
- role customization
- export to Markdown / PDF
- integration with project management tools

## Team

Zhe Wang — Solo participant  
University of Dayton  
M.S. Business Analytics
