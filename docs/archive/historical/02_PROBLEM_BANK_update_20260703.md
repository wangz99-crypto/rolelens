# 02_PROBLEM_BANK_update_20260703

> 文件用途：根据 Future of Work 工作流痛点证据包更新候选项目方向。  
> 状态：Problem Bank Draft  
> 更新日期：2026-07-03  
> 使用方式：复制到 `02_PROBLEM_BANK.md`。  
> 注意：本文件不是最终选题结论。当前优先级只是基于第一轮证据的临时排序。

---

# 候选方向评分总览

| 排名 | 候选方向 | 当前判断 | 继续研究优先级 |
|---:|---|---|---|
| 1 | AI Data-to-Recommendation / Dashboard-to-Decision Assistant | 最强候选 | High |
| 2 | AI Report / Decision Memo Quality Auditor | 很强，可独立或并入 1 | High |
| 3 | Meeting Notes-to-Execution Auditor | 可行，但赛道拥挤 | Medium |
| 4 | AI Project Status Risk Auditor | 可行，但容易像任务管理插件 | Medium |
| 5 | AI Automation Readiness Mapper | 概念高级，但易变咨询报告 | Medium |
| 6 | AI Workslop Detector for Teams | 痛点强，但产品边界易泛 | Revisit |
| 7 | Client Intake-to-Proposal Assistant | Demo 强，但与背景匹配稍弱 | Revisit |
| 8 | Small-Team Knowledge Context Auditor | 有价值，但范围易膨胀 | Revisit |

---

# Candidate A — AI Data-to-Recommendation / Dashboard-to-Decision Assistant

## Problem Name

AI Data-to-Recommendation / Dashboard-to-Decision Assistant

## Target User

- Junior business analysts
- Business Analytics students
- Small business analysts
- Non-technical business users who need to interpret dashboards
- Teams that need to turn charts into business recommendations

## Current Workflow

```text
CSV / dashboard / metrics
↓
Analyst creates charts or reads dashboard
↓
Analyst manually writes insights
↓
Analyst tries to infer business meaning
↓
Analyst writes recommendation
↓
Manager or professor reviews
```

## Pain Point

Many users can create charts or dashboards, but struggle to answer:

```text
So what?
What does this mean?
Is this insight supported by the data?
What business action should be taken?
What assumptions or risks exist?
```

## Why It Matters

The value of analytics is not just visualization, but decision support. If the interpretation is weak, misleading, or unsupported, the final business recommendation may be wrong.

## Existing Alternatives

- ChatGPT
- Power BI Copilot
- Tableau Pulse
- Excel Copilot
- Generic dashboard tools
- Manual analyst review

## Why Existing Alternatives Are Insufficient

- Generic AI tools can generate plausible but unsupported recommendations.
- BI copilots can generate insights, but official documentation acknowledges potential generic / inaccurate / misleading outputs.
- Dashboard tools show metrics, but may not ensure recommendations are evidence-backed.
- Junior analysts often need guidance on interpretation, not just chart creation.

## AI Opportunity

AI can help:

1. Summarize dataset structure.
2. Identify trends, anomalies, and comparisons.
3. Generate candidate insights.
4. Check whether each insight is supported by data.
5. Flag risks such as:
   - correlation vs causation
   - small sample size
   - missing time frame
   - outliers
   - unclear metric definition
   - unsupported recommendation
6. Generate a structured decision memo.
7. Provide a human review checklist.

## Workflow Automation Component

```text
Input data
↓
Data summary
↓
Insight extraction
↓
Evidence check
↓
Risk detection
↓
Recommendation generation
↓
Human review
↓
Decision memo
```

## Decision Support Component

The system does not simply generate advice. It evaluates whether a recommendation is sufficiently supported by data and flags assumptions, missing evidence, and possible misinterpretations.

## Demo Possibility

Very strong.

Demo can show:

```text
Before:
A CSV/dashboard with confusing charts and weak “so what.”

During:
The system identifies insights, checks evidence, flags risks, and generates a decision memo.

After:
The user receives a clearer, evidence-backed, reviewable business recommendation.
```

## Technical Difficulty

Medium.

Feasible MVP:

- CSV upload
- Data profiling
- Rule-based risk checks
- LLM-generated structured insight
- Evidence / risk / recommendation panel
- Streamlit UI

Avoid for MVP:

- Real Power BI integration
- Complex dashboard image recognition
- Full BI platform features

## Business Value

High for junior analysts, students, small business teams, and analytics learners.

## Risk

- Could look like a generic CSV chatbot.
- AI may fabricate business reasoning.
- If no evidence/risk layer exists, differentiation is weak.
- Needs a strong demo dataset.

## Current Score

| Dimension | Score / 10 | Notes |
|---|---:|---|
| Problem Strength | 9 | Supported by research, BI limitations, user pain |
| Commercial Value | 8 | Strong for analysts / small teams |
| AI Core Depth | 8 | AI interprets, checks, structures |
| Workflow Fit | 9 | Clear decision intelligence workflow |
| Technical Feasibility | 8 | Feasible with CSV + Streamlit |
| Differentiation | 7 | Must avoid CSV chatbot |
| Trust / Verification | 9 | Can build evidence/risk layer |
| Demo Clarity | 9 | Strong Before → After |
| **Total** | **67 / 80** | Strong candidate |

## Decision

Keep / Deep Research Next

---

# Candidate B — AI Report / Decision Memo Quality Auditor

## Problem Name

AI Report / Decision Memo Quality Auditor

## Target User

- Students
- Junior analysts
- Managers
- Knowledge workers
- Teams using AI-generated reports

## Current Workflow

```text
User or AI writes report / memo
↓
Output looks polished
↓
Reader must manually check if it is useful, accurate, evidence-backed, and actionable
```

## Pain Point

AI-generated work can appear complete while lacking:

- evidence
- context
- actionability
- clear recommendation
- risk discussion
- ownership
- decision relevance

This can create “workslop” and cause rework.

## Why It Matters

As AI content becomes more common, teams need quality gates before using AI-generated outputs in real work.

## Existing Alternatives

- ChatGPT self-review
- Grammarly
- Notion AI
- Manual review
- Generic rubric checkers

## Why Existing Alternatives Are Insufficient

Most tools focus on writing quality, not business decision quality. They may improve grammar but fail to check whether a recommendation is supported, actionable, or risky.

## AI Opportunity

AI can audit:

- unsupported claims
- missing evidence
- vague recommendations
- unclear decision owner
- missing next steps
- weak business logic
- missing risks
- inconsistent assumptions

## Workflow Automation Component

```text
Input report / memo
↓
Claim extraction
↓
Evidence check
↓
Actionability check
↓
Risk check
↓
Quality score
↓
Revision suggestions
```

## Decision Support Component

The system helps users judge whether an AI-generated or human-written memo is decision-ready.

## Demo Possibility

Strong.

Before: polished but weak AI memo.  
After: system marks unsupported claims, missing actions, and risky assumptions.

## Technical Difficulty

Low-Medium.

Feasible with structured text input, rubric scoring, LLM critique, and checklist output.

## Business Value

Medium-High.

Strong if tied to business decision memo or analytics report. Weak if positioned as generic writing checker.

## Risk

- Could look like another writing assistant.
- Needs a narrow target document type.
- Needs clear rubric and examples.

## Current Score

| Dimension | Score / 10 | Notes |
|---|---:|---|
| Problem Strength | 8 | Workslop evidence supports it |
| Commercial Value | 8 | Useful for AI-heavy workflows |
| AI Core Depth | 8 | AI audits quality and risk |
| Workflow Fit | 8 | Future of work trust layer |
| Technical Feasibility | 9 | Easy MVP |
| Differentiation | 7 | Must avoid grammar checker |
| Trust / Verification | 9 | Core value is verification |
| Demo Clarity | 8 | Good demo if examples strong |
| **Total** | **65 / 80** | Strong, possibly merge into A |

## Decision

Keep / Consider as validation layer for Candidate A

---

# Candidate C — Meeting Notes-to-Execution Auditor

## Problem Name

Meeting Notes-to-Execution Auditor

## Target User

- Student teams
- Small teams
- Project managers
- Team leads

## Current Workflow

```text
Meeting happens
↓
Someone writes summary
↓
Action items are vague
↓
Owner / deadline / blocker missing
↓
Follow-up fails
```

## Pain Point

Meeting summaries do not guarantee execution. Action items often lack owner, deadline, priority, blocker, or next step.

## Why It Matters

Teams waste time in meetings if outputs do not become clear executable tasks.

## Existing Alternatives

- ClickUp Brain
- monday AI
- Notion AI
- Otter.ai
- Microsoft Copilot
- Generic meeting summary tools

## Why Existing Alternatives Are Insufficient

Many tools summarize meetings or extract action items, but do not always judge whether those action items are executable.

## AI Opportunity

AI can:

- extract action items
- check owner
- check deadline
- check blocker
- identify ambiguous tasks
- generate follow-up plan
- flag execution risks

## Workflow Automation Component

```text
Meeting notes
↓
Action item extraction
↓
Completeness audit
↓
Execution risk detection
↓
Follow-up plan
```

## Decision Support Component

The system helps a team decide which tasks are unclear, blocked, or at risk.

## Demo Possibility

High.

Before: messy notes.  
After: clear action table + missing owner/deadline/blocker warnings.

## Technical Difficulty

Low-Medium.

Feasible with text input and structured extraction.

## Business Value

Medium-High.

Useful but crowded.

## Risk

- Meeting assistant market is crowded.
- If only summary/action extraction, it is not differentiated.
- Needs execution-audit positioning.

## Current Score

| Dimension | Score / 10 | Notes |
|---|---:|---|
| Problem Strength | 8 | Real and common |
| Commercial Value | 7 | Useful for teams |
| AI Core Depth | 7 | Extraction + audit |
| Workflow Fit | 9 | Strong Future of Work fit |
| Technical Feasibility | 9 | Easy MVP |
| Differentiation | 6 | Crowded market |
| Trust / Verification | 8 | Can check missing fields |
| Demo Clarity | 9 | Very demoable |
| **Total** | **63 / 80** | Good backup direction |

## Decision

Revisit / Backup

---

# Candidate D — AI Project Status Risk Auditor

## Problem Name

AI Project Status Risk Auditor

## Target User

- Small teams
- Student project groups
- Project coordinators
- Startup operators

## Current Workflow

```text
Task board / status updates
↓
Team manually checks progress
↓
Risks hide in vague updates
↓
Deadlines slip
```

## Pain Point

Tasks may exist, but teams often miss stale tasks, missing owners, blockers, repeated tasks, or deadline drift.

## Why It Matters

Execution failure often comes from small tracking failures, not lack of strategy.

## Existing Alternatives

- Asana AI
- ClickUp Brain
- monday AI
- Notion AI
- Jira AI

## Why Existing Alternatives Are Insufficient

Large project tools provide summaries, but small teams may need a lightweight risk audit layer rather than a full platform.

## AI Opportunity

AI can detect:

- stale tasks
- vague updates
- missing owner
- missing due date
- blockers
- repeated tasks
- dependency risks

## Workflow Automation Component

```text
Task table / updates
↓
Risk detection
↓
Priority ranking
↓
Suggested next actions
```

## Decision Support Component

The system tells the team what needs attention now.

## Demo Possibility

High with sample task board.

## Technical Difficulty

Medium.

Needs structured task input.

## Business Value

Medium.

Useful but close to project management tools.

## Risk

Can look like a task manager plugin. Needs a sharper use case.

## Current Score

| Dimension | Score / 10 | Notes |
|---|---:|---|
| Problem Strength | 7 | Real but common |
| Commercial Value | 7 | Useful for teams |
| AI Core Depth | 7 | Risk detection |
| Workflow Fit | 9 | Strong |
| Technical Feasibility | 8 | Feasible |
| Differentiation | 6 | Crowded |
| Trust / Verification | 8 | Can use rules |
| Demo Clarity | 8 | Good |
| **Total** | **60 / 80** | Revisit |

## Decision

Revisit

---

# Candidate E — AI Automation Readiness Mapper

## Problem Name

AI Automation Readiness Mapper

## Target User

- Small business owners
- Operations teams
- Student startup teams
- Agency operators
- Freelancers

## Current Workflow

```text
User describes a manual process
↓
User wants to automate
↓
User does not know what should be AI, what should be rules, what needs human review
```

## Pain Point

People know some workflows are repetitive, but struggle to identify which steps are suitable for AI automation versus deterministic automation.

## Why It Matters

Poorly designed automation can amplify bad workflows or create risk.

## Existing Alternatives

- Zapier
- Make
- Microsoft Power Automate
- ChatGPT consulting-style answers
- Workflow consultants

## Why Existing Alternatives Are Insufficient

Automation platforms execute workflows, but users still need to design safe, appropriate workflows.

## AI Opportunity

AI can:

- break workflow into steps
- classify each step as deterministic / AI-suitable / human-review-required
- identify risk
- recommend automation plan
- generate implementation checklist

## Workflow Automation Component

```text
Manual process description
↓
Step decomposition
↓
Automation suitability classification
↓
Risk and human-review mapping
↓
Implementation plan
```

## Decision Support Component

Helps users decide how to automate safely.

## Demo Possibility

Medium-High.

Could show messy process → automation map.

## Technical Difficulty

Medium.

Needs good prompt pipeline and visual output.

## Business Value

Medium-High.

Conceptually strong but less concrete.

## Risk

- Could become consulting report generator.
- Harder to show direct measurable output.
- Less aligned with user's analytics background.

## Current Score

| Dimension | Score / 10 | Notes |
|---|---:|---|
| Problem Strength | 7 | Real but broad |
| Commercial Value | 8 | Strong if narrowed |
| AI Core Depth | 8 | AI classifies workflow |
| Workflow Fit | 10 | Excellent theme fit |
| Technical Feasibility | 7 | Feasible but needs design |
| Differentiation | 7 | Interesting if visual |
| Trust / Verification | 8 | Can use human-in-loop logic |
| Demo Clarity | 7 | Needs strong scenario |
| **Total** | **62 / 80** | Revisit |

## Decision

Revisit / Possible module, not main project

---

# Current Recommendation

Current highest-priority direction:

```text
Candidate A — AI Data-to-Recommendation / Dashboard-to-Decision Assistant
```

Most useful combination:

```text
Candidate A as main product
+
Candidate B as quality / verification layer
```

Possible product framing:

```text
A trusted AI workflow that helps junior analysts turn data insights into evidence-backed business recommendations, while flagging weak assumptions, missing evidence, misleading charts, and risky conclusions.
```

