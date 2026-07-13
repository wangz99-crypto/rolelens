# 05_PRODUCT_SPEC.md — RoleLens

> 更新日期：2026-07-12
> 状态：Product Spec v1
> 项目名称：RoleLens  
> 参赛方向：IBM AI Builders Challenge Wildcard Challenge — Build Intelligent Systems for the Future of Work

# 1. Product Name
**RoleLens**

Full name:
```text
RoleLens: AI Decision Team for Business Data
```

# 2. One-Sentence Value Proposition
```text
RoleLens converts mixed business materials into role-specific insights, risks, missing information, and an approval-ready decision plan.
```

中文：
```text
RoleLens 把数据、报告和业务背景转化为不同企业角色可审核的洞察、风险、缺失信息和行动计划。
```

# 3. Problem Statement
Business decisions are rarely made from clean data alone. Teams often work with spreadsheets, reports, dashboard summaries, industry context, and incomplete assumptions. Different roles need different views of the same evidence, but existing AI tools usually produce one generic answer.

RoleLens helps teams move from data and reports to coordinated, evidence-backed decisions.

# 4. Target User
Primary:
- Junior business analysts
- Business Analytics students
- Small business teams
- Startup / small team operators
- Student consulting teams

Secondary:
- Non-technical business users who need help interpreting data before making decisions

# 5. Core User Story
```text
As a junior analyst or small team member,
I want to upload a dataset and business context,
so that I can understand what different business roles should care about,
what evidence supports each insight,
what risks or missing information exist,
and what action sequence the team should follow.
```

# 6. MVP Inputs
Required:
1. CSV / Excel data file
2. Business report or industry context text
3. Company strategy profile
4. Business question / decision goal

Example business question:
```text
Should we prioritize retention efforts for high-value customers in Q3?
```

# 7. MVP Outputs
RoleLens outputs:
1. Data health check
2. Evidence cards
3. Role-specific decision views
4. Risks and assumptions
5. Missing information queue
6. Cross-role action sequence
7. Decision memo
8. Human review checklist

# 8. Core Workflow
```text
Step 1: User uploads data and context
Step 2: System classifies source types
Step 3: System profiles structured data
Step 4: System extracts evidence from text
Step 5: System builds evidence objects
Step 6: System generates role-specific views
Step 7: System checks evidence, assumptions, and risks
Step 8: System suggests action sequence
Step 9: User reviews and edits
Step 10: System generates final decision memo
```

# 9. Role Framework

## Executive
Focus: strategy, ROI, business risk, decision options, resource allocation.

## Data Analyst / Data Scientist
Focus: metric validity, analysis feasibility, modeling potential, bias, target variable, feature quality.

## Data Engineer
Focus: data quality, schema, missing values, source reliability, pipeline readiness.

## Sales / Marketing
Focus: customer segment, revenue opportunity, campaign action, market context, customer risk.

## Project Manager
Focus: task sequence, dependencies, owners, deadlines, meeting needs, approval points.

### Role boundary

The five entries above are user-visible business perspectives over shared evidence, not five independent AI coworkers. Their allowed inputs, required outputs, forbidden actions, and mandatory warnings are governed by `role_policy.json`.

Internal implementation components are **Evidence Builder**, **Risk Reviewer**, **Workflow Planner**, and **Decision Memo Composer**. Reference-note labels such as Evidence Curator, Finance Reviewer, and Operations Reviewer are not additional product roles.

# 10. Evidence Object Contract

Every Evidence Object must carry a stable `evidence_id` and a `source_locator` linking it to a specific span of the originating source. Role views, risk warnings, workflow steps, and memo claims must each cite at least one `evidence_id`. **No evidence ID, no decision claim.**

```text
evidence_id:        ev-{evidence_type_abbrev}-{12_hex}
source_id:          src-{format_abbrev}-{12_hex}
source_format:      csv | excel | pasted_text | txt | markdown | form_input
semantic_category:  data_source | internal_report | industry_context |
                    strategy_profile | business_question | decision_goal | user_assumption
source_scope:       internal_observation | external_context | user_assertion | decision_context
evidence_scope:     internal_observation | external_context | assumption | stated_priority
evidence_type:      rule key (e.g. "missing_value_rate", "outlier_flag")
extraction_method:  deterministic | llm_assisted
finding:            string (human-readable; not an identity input)
supporting_evidence: string
confidence:         low | medium | high
limitations:        [string]
relevant_roles:     [non-empty list]
decision_relevance: string
identity_digest:    full SHA-256 hex (stored separately from the display ID)
```

**Source and evidence scope rules:**
- `internal_observation` source → `internal_observation` evidence: may be cited as company-specific fact.
- `external_context` source → `external_context` evidence: informs but must not be treated as direct company proof.
- `user_assertion` source → `assumption` evidence: must be labeled as assumption, not verified fact.
- Strategy goal or profile assertion → `stated_priority` evidence: represents intent, not performance.
- `decision_context` source (business question, decision goal) → produces no EvidenceObject.

**Minting boundary:** `data_health.py` produces `HealthFindingCandidate` objects without `evidence_id`. Only `evidence_builder.py` converts candidates into `EvidenceObject` records and mints `evidence_id` values.

# 11. Must-Have Features
1. File intake: CSV / Excel / pasted report text / strategy profile
2. Data health check: missing values, outliers, sample size, unclear columns
3. Evidence object builder
4. Role-based insight generator
5. Risk and assumption checker
6. Workflow planner
7. Decision memo generator
8. Simulated human review

# 12. Nice-to-Have Features
1. Markdown export
2. Simple chart preview
3. Decision readiness score
4. Evidence strength score
5. Workslop Firewall memo quality check
6. Downloadable decision memo

# 13. Out of Scope for V1
1. Real email sending
2. Real approval permissions
3. Multi-user authentication
4. Long-term company memory
5. Automatic online industry research
6. Power BI / Tableau integration
7. Dashboard screenshot recognition
8. OCR for scanned PDFs
9. Full multi-agent infrastructure
10. Vector database / GraphRAG
11. Enterprise deployment

# 14. Demo Scenario
A B2B SaaS company wants to reduce churn among high-value customers. The team has customer data, an industry report excerpt, and a strategy goal.

Before: mixed materials but no clear decision workflow.  
During: RoleLens generates evidence cards, role views, risk flags, and missing information.  
After: the team receives an executive decision brief, data validation tasks, sales action cautions, project workflow sequence, and a decision memo.

# 15. Success Criteria
- The system clearly differs from a CSV chatbot.
- Each role output is grounded in evidence.
- Recommendations include risks and assumptions.
- The workflow planner identifies dependencies.
- The final memo is structured and reviewable.
- Demo can be completed in under 3 minutes.
- MVP is technically feasible in one month.
- IBM Bob usage can be documented across development.

# 16. Technical Stack
Recommended:
```text
Frontend: Streamlit
Data processing: pandas, openpyxl
Schema validation: Pydantic
AI logic: prompt pipeline + structured output
Testing: pytest
Development assistant: IBM Bob
```

Optional later (post-core-pipeline stability):
```text
PyMuPDF / pdfplumber — digitally generated PDF text extraction only
LangGraph — human-in-the-loop workflow (V1 excluded)
Unstructured — richer document parsing (V1 excluded)
LlamaIndex — if document volume grows (V1 excluded)
```

# 17. IBM Bob Usage Plan
IBM Bob should be used for:
1. Core identity and provenance schemas (`app/schemas.py`)
2. Deterministic identity module (`app/identity.py`)
3. CSV and pasted-text intake / source manifest (`app/file_intake.py`, `app/text_parser.py`)
4. CSV parser and data-health candidates (`app/data_parser.py`, `app/data_health.py`)
5. Evidence Object builder (`app/evidence_builder.py`)
6. Role engine and policy enforcement (`app/role_engine.py`)
7. Risk checker module (`app/risk_checker.py`)
8. Workflow planner and memo generator (`app/workflow_planner.py`, `app/memo_generator.py`)
9. Streamlit app shell (`app/main.py`) — after backend pipeline is testable
10. Unit tests, README draft, debugging and refactoring
