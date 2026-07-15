# 05_PRODUCT_SPEC.md — RoleLens

> 更新日期：2026-07-14
> 状态：Product Spec v1.1 — Task 5B and grounded role contracts approved
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
what evidence supports each claim,
what risks or missing information exist,
and what action sequence the team should follow.
```

# 6. MVP Inputs

Required evaluator path:

1. CSV business data
2. Pasted business report or industry-context text
3. Structured company strategy profile
4. Business question
5. Decision goal

Optional but supported in the evidence contract:

6. Explicit user assumption

Planned input extensions that must not block the first stable demo:

- Excel
- TXT
- Markdown

Example business question:
```text
Which high-value customer segments, if any, should receive a limited retention pilot?
```

Example decision goal:
```text
Determine whether the available evidence is sufficient to design a limited retention pilot for human review.
```

# 7. MVP Outputs
RoleLens outputs:
1. Data health check
2. Evidence cards with stable IDs, scope, limitations, and exact source locators
3. Role-specific decision views with claim-level citations
4. Risks and assumptions
5. Missing information queue
6. Cross-role action sequence
7. Decision memo
8. Human review checklist and recommendation status

# 8. Core Workflow
```text
Step 1: User uploads data and enters decision context
Step 2: System registers source manifests and semantic categories
Step 3: System profiles structured data
Step 4: System extracts bounded exact-source text/context candidates
Step 5: Evidence Builder creates Evidence Objects with stable IDs
Step 6: Role Engine generates policy-constrained, claim-level grounded views
Step 7: Risk Checker checks unsupported claims, scope misuse, assumptions, and role overreach
Step 8: Workflow Planner suggests an ordered action sequence
Step 9: User reviews, rejects, or requests changes
Step 10: System generates the reviewed decision memo
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

The five entries above are user-visible business perspectives over shared evidence, not five independent AI coworkers. Their allowed inputs, required outputs, forbidden actions, and mandatory warnings are governed by `config/role_policy.json`.

Canonical machine role keys:

```text
executive
data_analyst
data_engineer
sales_marketing
project_manager
```

`relevant_roles` is a routing hint. It is not proof that an evidence item is admissible for a claim and does not override `role_policy.json`.

Internal implementation components are **Evidence Builder**, **Role Engine**, **Risk Reviewer**, **Workflow Planner**, and **Decision Memo Composer**. Reference-note labels such as Evidence Curator, Finance Reviewer, and Operations Reviewer are not additional product roles.

## 9.1 Grounded Role Output Contract

View-level citations are insufficient. RoleLens uses claim-level grounding:

```text
GroundedFinding
- claim
- evidence_references: one or more EvidenceReference records
- confidence: low | medium | high
```

A successful `RoleView` contains:

```text
role_key
role_concern
key_findings: nonempty list[GroundedFinding]
risks_or_assumptions
missing_information
next_action: str | None
dependency: str | None
human_review_required
```

Required behavior:

- every `GroundedFinding` cites at least one unique, active Evidence Object;
- every citation existed in and was exposed to the role request;
- returned `role_key` must equal the requested role;
- invalid provider output never renders as a role card;
- fabricated, hidden, malformed, or invalidated references fail closed;
- no admissible evidence returns typed `InsufficientEvidence`, no role card, and `next_action = None`;
- a non-null next action requires at least one valid grounded finding;
- a valid citation does not by itself prove that the claim semantically follows from the evidence—Task 7 and human review remain required.

# 10. Evidence Object Contract

Every Evidence Object must carry a stable `evidence_id` and a `source_locator` linking it to a specific span of the originating source. Every decision claim must be grounded at claim level.

```text
No evidence ID, no decision claim.
```

```text
evidence_id:        ev-{evidence_type_abbrev}-{12_hex}
source_id:          src-{format_abbrev}-{12_hex}
source_format:      csv | excel | pasted_text | txt | markdown | form_input
semantic_category:  data_source | internal_report | industry_context |
                    strategy_profile | business_question | decision_goal | user_assumption
source_scope:       internal_observation | external_context | user_assertion | decision_context
evidence_scope:     internal_observation | external_context | assumption | stated_priority
evidence_type:      controlled rule/evidence key
extraction_method:  deterministic | llm_assisted
finding:            string (human-readable; not an identity input)
supporting_evidence: string
confidence:         low | medium | high
limitations:        [string]
relevant_roles:     canonical machine role keys
decision_relevance: string
identity_digest:    full SHA-256 hex (stored separately from the display ID)
```

**Confidence meaning:** confidence represents the evidence item's decision reliability in its declared scope, not whether deterministic extraction copied the text correctly.

**Source and evidence scope rules:**
- `internal_observation` source → `internal_observation` evidence: may be cited as company-specific observation.
- `external_context` source → `external_context` evidence: informs but must not be treated as direct company proof.
- `user_assertion` source → `assumption` evidence: must be labeled as assumption, not verified fact.
- Strategy goal or profile assertion → `stated_priority` evidence: represents confirmed user intent, not measured performance.
- `decision_context` source (business question, decision goal) → produces no EvidenceObject.

**Identity boundary:** `app/identity.py` computes deterministic identity values.

**Construction boundary:** only `app/evidence_builder.py` converts approved candidates into `EvidenceObject` records.

## 10.1 Pre-Minting Candidate Contracts

### HealthFindingCandidate

Produced by deterministic tabular data-health checks. It has no `evidence_id`.

### TextEvidenceCandidate — Task 5B

Added alongside, not instead of, `HealthFindingCandidate`.

Allowed evidence-producing categories:

| Category | Candidate granularity | Evidence scope |
|---|---|---|
| `industry_context` | one nonblank normalized paragraph | `external_context` |
| `strategy_profile` | one structured form field | `stated_priority` |
| `user_assumption` | one structured form field | `assumption` |

Context-only categories:

```text
business_question
decision_goal
```

These categories register source/trajectory context but produce no candidate and no Evidence Object.

Task 5B rules:

- preserve the exact normalized excerpt;
- set `finding` and `supporting_evidence` to that excerpt during minting;
- do not summarize, infer, or author a separate free-form finding;
- use precise typed locators;
- derive scope from the registered manifest;
- require candidate, manifest, locator, category, format, and algorithm-version consistency;
- use controlled evidence type, claim key, and extraction-policy values;
- use only canonical machine role keys;
- treat role relevance as routing, not admissibility.

# 11. Must-Have Features
1. Source intake for the first evaluator path: CSV, pasted industry context, strategy profile, business question, decision goal, and optional assumption
2. Data health check: missing values, duplicates, mixed types, constant columns, and schema issues
3. Bounded candidate generation for tabular health and exact-source text/context evidence
4. Evidence Object builder with deterministic identity and provenance checks
5. Claim-level grounded role views with typed abstention/failure behavior
6. Risk and assumption checker
7. Workflow planner
8. Decision memo generator
9. Simulated human review and revision
10. Streamlit evaluator path

# 12. Nice-to-Have Features
1. Excel / TXT / Markdown input extensions
2. Markdown export
3. Simple chart preview
4. Decision readiness score
5. Evidence strength score
6. Workslop Firewall memo quality check
7. Downloadable decision memo

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
12. LLM-based text evidence extraction in Task 5B
13. Silent mock substitution for live-provider failure

# 14. Demo Scenario
A B2B SaaS company wants to reduce churn among high-value customers. The team has customer data, a sourced industry-context excerpt, a strategy priority, an explicit assumption, a business question, and a decision goal.

Before: mixed materials but no clear evidence boundary or decision workflow.  
During: RoleLens creates scoped Evidence Objects, claim-level grounded role views, risk flags, missing information, and dependencies.  
After: the team receives an executive decision brief, data-validation tasks, sales-action cautions, a coordinated workflow sequence, and a human-reviewed decision memo.

The demo must visibly distinguish:

- internal observations;
- external context;
- stated priorities;
- assumptions;
- decision context that does not count as evidence.

# 15. Success Criteria
- The system clearly differs from a CSV chatbot.
- Every displayed decision claim has claim-level evidence references.
- Unsupported roles abstain rather than fabricate a generic card.
- External context is not presented as direct company proof.
- Assumptions and stated priorities remain visibly distinct from internal observations.
- Recommendations include visible limitations, missing information, and review needs.
- The workflow planner identifies dependencies.
- The final memo is structured and reviewable.
- Mock/offline output is visibly labeled and never silently replaces a failed live provider.
- Demo can be completed in under three minutes.
- MVP is technically feasible within the competition window.
- IBM Bob usage is documented across production development.

# 16. Technical Stack
Recommended:
```text
Frontend: Streamlit
Data processing: pandas, openpyxl
Schema validation: Pydantic
AI logic: provider-neutral structured-output pipeline
Testing: pytest
Development assistant: IBM Bob
```

Optional later:
```text
PyMuPDF / pdfplumber — digitally generated PDF text extraction only
LangGraph — human-in-the-loop workflow (V1 excluded)
Unstructured — richer document parsing (V1 excluded)
LlamaIndex — if document volume grows (V1 excluded)
```

# 17. IBM Bob Usage Plan
IBM Bob should be used for:
1. Core identity and provenance schemas
2. Deterministic identity and canonicalization
3. CSV and pasted-text source intake
4. CSV parser and deterministic data-health candidates
5. Evidence Object builder and provenance integrity repairs
6. Task 5B — independent production implementation of `TextEvidenceCandidate`, context evidence extraction, form-input manifests, and candidate-union minting
7. Task 6A — grounded role schemas, policy validation, strict parsing, provider-neutral Role Engine, and deterministic visibly-offline test provider
8. Task 6B — one live provider adapter, timeout/retry behavior, credential handling, and latency/cost measurement
9. Risk Checker
10. Workflow Planner and Decision Memo generator
11. Streamlit app shell
12. Unit tests, debugging, refactoring, README support, and demo preparation

Local Codex spikes are used only to discover failure cases and acceptance criteria. Their implementation code is not merged or reused.
