# 02_PROBLEM_BANK.md — RoleLens 最终候选方向更新

> 更新日期：2026-07-08  
> 状态：RoleLens selected as main direction

# Selected Direction

## Problem Name
**RoleLens: AI Decision Team for Business Data**

## Target User
Primary:
- Junior business analysts
- Business Analytics students
- Small teams
- Student consulting teams
- Startup / small business operators

Secondary:
- Business users who need to interpret data and reports before making decisions

## Current Workflow
Teams often receive mixed business materials:

```text
CSV / Excel data
+
business reports
+
industry report excerpts
+
meeting notes
+
strategy goals
```

Different team members interpret the same material manually:
- Executive looks for strategic risk.
- Data scientist looks for modeling feasibility.
- Data engineer looks for data quality.
- Sales looks for customer action.
- Project manager looks for task sequence.

## Pain Point
The same business material means different things to different roles. Common failure points:
1. One generic AI answer does not fit every role.
2. Analysts may generate insights but fail to turn them into actions.
3. Recommendations may lack supporting evidence.
4. Data gaps and assumptions are not clearly exposed.
5. Teams do not know who should act first.
6. Business reports and dashboards may not produce decision-ready outcomes.
7. AI-generated content may look polished but still be weak or unsupported.

## Why It Matters
Business decisions are made from mixed evidence, reports, assumptions, and stakeholder concerns. RoleLens helps teams convert messy decision materials into structured role-specific outputs.

## Existing Alternatives
- ChatGPT / Claude
- Microsoft Copilot
- Power BI Copilot
- Tableau Pulse
- Notion AI
- Asana AI
- monday AI
- ClickUp Brain
- Meeting summary tools
- Manual analyst review

## Why Existing Alternatives Are Insufficient
Existing tools usually focus on generic answer generation, dashboard insights, meeting summarization, task generation, or project updates. RoleLens focuses on a narrower workflow:

```text
mixed business materials
→ role-specific decision evidence
→ risk and assumption checks
→ coordinated action plan
```

## AI Opportunity
AI can:
1. Classify input materials.
2. Extract evidence objects.
3. Identify role-relevant insights.
4. Flag unsupported claims and missing context.
5. Detect data quality and interpretation risks.
6. Generate role-specific next actions.
7. Suggest cross-role dependencies.
8. Produce a decision memo.
9. Create a human review checklist.

## Demo Possibility
Strong.

Demo scenario:
A B2B SaaS team receives customer churn data and an industry report excerpt. The team needs to decide how to respond to churn risk. RoleLens turns the material into five role views and a coordinated action plan.

## Technical Difficulty
Medium-High but feasible if scoped strictly.

Recommended MVP stack:
```text
Streamlit
pandas
openpyxl
PyMuPDF / pdfplumber
Pydantic
LLM structured output
IBM Bob-assisted development
```

Avoid in v1:
```text
real email sending
real approval permissions
long-term memory
Power BI / Tableau API
full multi-agent system
vector database
complex LangGraph orchestration
```

## Idea-Selection Prior (2026-07-08)

This score was used to select a direction before implementation. It is **not** a product-completion score, a judge score, or evidence that RoleLens is already first-place ready. Re-scoring is blocked until a working prototype produces reproducible evaluation and demo evidence; see `01_RULES_SCORECARD.md`.

| Dimension | Score / 10 | Notes |
|---|---:|---|
| Problem Strength | 9 | Strong evidence from data-to-decision and AI verification pain |
| Commercial Value | 8 | Useful for analysts, students, small teams |
| AI Core Depth | 9 | AI interprets, checks, structures, and coordinates |
| Workflow Fit | 10 | Strong Wildcard fit |
| Technical Feasibility | 7 | Feasible if scoped tightly |
| Differentiation | 9 | More unique than CSV chatbot |
| Trust / Verification | 9 | Evidence and risk layers are central |
| Demo Clarity | 8 | Strong if sample scenario is controlled |
| **Total** | **69 / 80** | Pre-prototype idea-selection prior; frozen until prototype evidence exists |

## Decision
**Keep — Main project direction selected.**

# Backup Direction 1 — SheetGuard AI
Status: Backup / possible future module  
Core value: Spreadsheet decision risk auditing before teams use Excel/CSV for decisions.

# Backup Direction 2 — Workslop Firewall
Status: Module inside RoleLens  
Core value: Check whether RoleLens-generated decision memo has evidence, actionability, risks, and review points.

# Final Direction Statement
RoleLens is selected because it combines data-to-decision, AI coworker, decision intelligence, and workflow orchestration into a focused MVP that fits the participant's Business Analytics background and the IBM AI Builders Challenge Wildcard theme.
