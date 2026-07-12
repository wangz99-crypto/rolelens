# 06_ARCHITECTURE_CODE_MAP.md — RoleLens

> 更新日期：2026-07-08  
> 状态：Architecture Draft v1

# 1. Architecture Overview

```text
User Inputs
CSV / Excel + Report Text + Strategy Profile
        ↓
Source Classifier
        ↓
┌───────────────────────┬────────────────────────┐
│ Structured Data Parser│ Text / Report Parser   │
└───────────────────────┴────────────────────────┘
        ↓                         ↓
Data Health Check          Claim / Context Extraction
        ↓                         ↓
        └────── Evidence Object Builder ──────┘
                         ↓
                 Evidence Store
                         ↓
              RoleLens Decision Engine
                         ↓
 Executive | Data Analyst | Data Engineer | Sales/Marketing | PM
                         ↓
              Risk & Assumption Checker
                         ↓
               Workflow Sequence Planner
                         ↓
              Decision Memo Generator
                         ↓
               Human Review Interface
```

# 2. Recommended Project Structure

## User roles versus internal components

The architecture has two distinct layers:

- **User-visible views:** Executive, Data Analyst / Data Scientist, Data Engineer, Sales / Marketing, and Project Manager.
- **Internal bounded components:** Evidence Builder, Risk Reviewer, Workflow Planner, and Decision Memo Composer.

The user-visible views apply policy to shared Evidence Objects. Internal components perform processing steps and must not be presented as extra AI coworkers. `role_policy.json` is the machine-readable authority for the five business-role boundaries.

```text
rolelens/
├── app/
│   ├── main.py
│   ├── config.py
│   ├── schemas.py
│   ├── file_intake.py
│   ├── data_parser.py
│   ├── text_parser.py
│   ├── data_health.py
│   ├── evidence_builder.py
│   ├── role_engine.py
│   ├── risk_checker.py
│   ├── workflow_planner.py
│   ├── memo_generator.py
│   └── utils.py
├── prompts/
├── sample_data/
├── tests/
├── docs/
├── README.md
└── requirements.txt
```

# 3. Core Schemas

## Evidence Object
```python
class EvidenceObject(BaseModel):
    source_id: str
    source_type: Literal["structured_data", "business_report", "industry_context", "user_context"]
    finding: str
    supporting_evidence: str
    confidence: Literal["low", "medium", "high"]
    limitations: list[str]
    relevant_roles: list[str]
    decision_relevance: str
```

## Role View
```python
class RoleView(BaseModel):
    role_name: str
    role_concern: str
    key_finding: str
    supporting_evidence: list[str]
    risks_or_assumptions: list[str]
    missing_information: list[str]
    next_action: str
    dependency: str | None
    human_review_required: bool
```

## Decision Memo
```python
class DecisionMemo(BaseModel):
    executive_summary: str
    key_evidence: list[str]
    role_views: list[RoleView]
    risks: list[str]
    assumptions: list[str]
    missing_information: list[str]
    recommended_action_sequence: list[str]
    human_review_checklist: list[str]
```

# 4. Module Map

## main.py
Purpose: Streamlit app entry point.  
Input: uploaded files and user context.  
Output: rendered UI with data health, role views, workflow plan, decision memo.  
Failure cases: missing file, invalid file type, invalid LLM response.

## file_intake.py
Purpose: classify uploaded input source.  
Output: source metadata.  
Failure cases: unsupported extension, empty file, encoding issue.

## data_parser.py
Purpose: parse CSV / Excel into pandas DataFrame.  
Dependencies: pandas, openpyxl.  
Failure cases: empty sheet, non-tabular Excel, multiple sheets.

## text_parser.py
Purpose: parse pasted report or industry context text.  
Output: cleaned text chunks.  
Failure cases: very long text, irrelevant text, text contains tables not parsed.

## data_health.py
Purpose: run basic data quality and decision readiness checks.  
Checks: missing values, outliers, data types, sample size, warnings.

## evidence_builder.py
Purpose: convert structured and text findings into Evidence Objects.  
Failure cases: unsupported claim, invalid schema, weak source evidence.

## role_engine.py
Purpose: generate role-specific decision views.  
Failure cases: role output generic, role ignores evidence, role recommends action without support.

## risk_checker.py
Purpose: identify weak assumptions, unsupported claims, and interpretation risks.  
Risks: missing context, unsupported claim, correlation vs causation, small sample, outlier influence, unclear metric, recommendation without evidence.

## workflow_planner.py
Purpose: generate cross-role action sequence.  
Failure cases: illogical order, ignored dependency, vague action.

## memo_generator.py
Purpose: generate final decision memo in Markdown.  
Failure cases: missing evidence, missing risk, missing action sequence.

# 5. Suggested UI Tabs
1. Intake
2. Data Health
3. Evidence Board
4. RoleLens Views
5. Workflow Plan
6. Decision Memo

# 6. Technical Guardrails
- Use Pydantic for structured outputs.
- Do not rely on free-form LLM text only.
- Every role view must include evidence.
- Every recommendation must include risk or assumption.
- LLM output must be validated before rendering.
- If confidence is low, system must say so.
- Do not over-automate; keep human review visible.
