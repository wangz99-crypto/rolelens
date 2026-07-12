# 04_DECISION_LOG.md — RoleLens 决策记录

> 更新日期：2026-07-08  
> 状态：Active

## Decision 001

### Decision
Select **RoleLens: AI Decision Team for Business Data** as the main IBM AI Builders Challenge Wildcard project direction.

### Context
The project compared several candidate directions:

1. RoleLens / Multi-source Role-based Data-to-Decision Workflow
2. SheetGuard AI / Spreadsheet Decision Risk Auditor
3. Workslop Firewall / Decision Memo Quality Gate
4. Meeting-to-Execution Auditor
5. Automation Readiness Mapper
6. Generic AI coworker / Synapse Team style multi-agent workspace

### Why RoleLens Was Chosen
RoleLens combines the strongest elements of several candidate directions:

```text
Data-to-Decision
+
Role-based AI collaboration
+
Evidence checking
+
Risk detection
+
Human review
+
Workflow orchestration
```

It is more differentiated than a generic CSV chatbot and more feasible than a full enterprise AI team platform.

### Alternatives Considered

#### SheetGuard AI
Strengths: clear pain point, feasible, strong demo, strong risk-adjusted option.  
Why not selected as main direction: narrower and less ambitious than RoleLens. Can become a future module for data quality and spreadsheet decision risk.

#### Workslop Firewall
Strengths: timely AI-era pain point, easy MVP, strong quality-control framing.  
Why not selected as main direction: may look like a writing quality checker. Better as a memo quality gate inside RoleLens.

#### Synapse Team / Generic AI Team Workspace
Strengths: high conceptual ambition and strong future-of-work narrative.  
Why not selected: too broad, likely to become a generic multi-agent demo, hard to verify output quality in 3 minutes, and less tied to the user’s Business Analytics background.

#### Meeting-to-Execution Auditor
Strengths: clear workflow pain and easy demo.  
Why not selected: crowded market; many tools already summarize meetings and extract action items.

### Main Risk
RoleLens may become too large if it tries to support all file formats, real enterprise workflows, email sending, long-term memory, live BI integrations, or complex multi-agent orchestration.

### Scope Control Decision
V1 scope:

```text
CSV / Excel
+
business report text
+
strategy profile
+
evidence objects
+
role-based views
+
risk / missing information checks
+
action sequence
+
decision memo
+
simulated review
```

### Validation Method
RoleLens must pass:

1. Generic wrapper test: Can a judge clearly see how RoleLens differs from ChatGPT analyzing a CSV?
2. 3-minute demo test: Can the full value be shown in under 3 minutes?
3. Feasibility test: Can the MVP be built with Streamlit, pandas, openpyxl, Pydantic, and IBM Bob-assisted development within one month?

### Status
Active

### Revisit Date
After first 48-hour prototype test.
