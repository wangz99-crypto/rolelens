# 06_ARCHITECTURE_CODE_MAP.md — RoleLens

> 更新日期：2026-07-14
> 状态：Architecture v3 — Task 5B and grounded Role Engine sequence approved

# 1. Architecture Overview

```text
User Inputs
CSV + Pasted Industry Context + Strategy Profile + User Assumption
+ Business Question + Decision Goal
        ↓
┌──────────────────────────┬────────────────────────────────────┐
│ file_intake.py           │ text_parser.py / form-input intake │
│ CSV source registration  │ context source registration        │
└──────────────────────────┴────────────────────────────────────┘
        ↓
SourceManifestEntry records
(source_id, identity_digest, semantic category, source_scope)
        ↓
┌──────────────────────────────────┬─────────────────────────────────────┐
│ data_parser.py                   │ context_evidence.py — Task 5B      │
│ CSV → validated DataFrame        │ deterministic exact-source extract │
│        ↓                         │                                     │
│ data_health.py                   │ industry paragraph / form field     │
│ DataHealthSummary                │        ↓                            │
│ HealthFindingCandidate list      │ TextEvidenceCandidate list          │
└──────────────────────────────────┴─────────────────────────────────────┘
                         ↓
              evidence_builder.py
      explicit approved candidate union → EvidenceObject
      identity.py computes IDs; builder constructs records
                         ↓
             EvidenceObject registry
(active status, scope, exact locator, full digest)
                         ↓
              Task 6A — Role Engine
- loads and validates role_policy.json
- deterministic per-role input projection
- strict structured-output parsing
- claim-level GroundedFinding validation
- typed failures / InsufficientEvidence
- deterministic visibly-offline provider for tests
                         ↓
       Executive | Analyst | Engineer | Sales
          independent conceptual role calls
                         ↓
            Project Manager generated last
        only after all required upstream success
                         ↓
              Task 6B — Live Provider Adapter
- one provider
- credentials / timeout / retry controls
- latency and cost measurement
- no silent mock fallback
                         ↓
              Task 7 — risk_checker.py
- unsupported claims
- external context used as internal proof
- assumptions represented as facts
- role overreach and missing prerequisites
                         ↓
              Task 8 — workflow_planner.py
- ordered cross-role actions
- dependencies and blocked steps
                         ↓
       Task 9 — Human Review + memo_generator.py
                         ↓
              Task 10 — Streamlit UI
```

Business question and decision goal produce `decision_context` source records but no Evidence Objects.

The conceptual five-call role design is provisional. Four non-PM roles may later run in parallel; Project Manager remains sequential. Final adoption depends on measured live-provider latency and cost.

# 2. Recommended Project Structure

## User roles versus internal components

The architecture has two distinct layers:

- **User-visible views:** Executive, Data Analyst / Data Scientist, Data Engineer, Sales / Marketing, and Project Manager.
- **Internal bounded components:** Evidence Builder, Role Engine, Risk Reviewer, Workflow Planner, and Decision Memo Composer.

The user-visible views apply policy to shared Evidence Objects. Internal components perform bounded processing steps and must not be presented as extra AI coworkers. `config/role_policy.json` is the machine-readable authority for the five business-role boundaries.

```text
rolelens/
├── app/
│   ├── __init__.py
│   ├── schemas.py          ← implemented + Task 5B/6A schema extensions
│   ├── identity.py         ← implemented: deterministic ID generation
│   ├── file_intake.py      ← implemented: CSV source intake
│   ├── text_parser.py      ← implemented: pasted-text source manifest
│   ├── utils.py            ← implemented: timestamps and shared helpers
│   ├── data_parser.py      ← implemented: CSV → DataFrame
│   ├── data_health.py      ← implemented: deterministic tabular candidates
│   ├── context_evidence.py ← Task 5B: exact text/form evidence candidates
│   ├── evidence_builder.py ← implemented; Task 5B candidate-union extension
│   ├── role_engine.py      ← Task 6A: grounded provider-neutral role engine
│   ├── risk_checker.py     ← Task 7
│   ├── workflow_planner.py ← Task 8
│   ├── memo_generator.py   ← Task 9
│   └── main.py             ← Task 10: Streamlit UI
├── config/
│   └── role_policy.json    ← runtime role boundary authority
├── prompts/                ← Task 6B provider prompt templates
├── sample_data/            ← reproducible backend and final demo fixtures
├── outputs/
│   └── run_logs/           ← future JSON decision trajectories
├── tests/
│   ├── test_schemas.py
│   ├── test_identity.py
│   ├── test_file_intake.py
│   ├── test_text_parser.py
│   ├── test_data_parser.py
│   ├── test_data_health.py
│   ├── test_context_evidence.py   ← Task 5B
│   ├── test_evidence_builder.py
│   └── test_role_engine.py        ← Task 6A
├── docs/
├── README.md
└── requirements.txt
```

A live-provider adapter filename is not locked until Task 6B provider selection. Do not add `app/config.py`, agent frameworks, vector storage, or provider abstractions beyond the minimum accepted protocol.

# 3. Core Schemas

*All production schema models are defined in `app/schemas.py` and added only in their approved task.*

## Implemented — Identity, Provenance, and Data Health

### Enums

```text
SourceFormat:            csv | excel | pasted_text | txt | markdown | form_input
                         (pdf_text delayed)

SemanticContextCategory: data_source | internal_report | industry_context |
                         strategy_profile | business_question | decision_goal |
                         user_assumption

SourceScope:             internal_observation | external_context |
                         user_assertion | decision_context

EvidenceScope:           internal_observation | external_context |
                         assumption | stated_priority

EvidenceStatus:          active | invalidated
```

### Source Locator Union

```text
TabularSourceLocator
TextSourceLocator
UserContextLocator
```

Each locator is a frozen, extra-forbidden Pydantic model. `SourceLocator` is a discriminated union using `locator_type`.

### SourceManifestEntry

```text
source_id
identity_digest
source_format
semantic_context_category
source_scope
filename
upload_event_id
id_algo_version
created_at
```

### DataHealthSummary

Implemented deterministic summary:

```text
source_id
row_count
column_count
duplicate_row_count
missing_value_rates
columns_with_mixed_types
constant_columns
schema_issues
```

No readiness score exists because no defensible scoring method has been approved.

### HealthFindingCandidate

Deterministic tabular pre-minting candidate. It contains identity inputs and human-readable evidence fields but no `evidence_id`.

### EvidenceObject

```text
evidence_id
identity_digest
source_id
source_format
source_locator
evidence_type
evidence_scope
extraction_method
finding
supporting_evidence
confidence
limitations
relevant_roles
decision_relevance
id_algo_version
created_by
status
invalidated_reason
```

### EvidenceReference

Validates reference syntax only. Runtime existence, active status, exposure to a provider request, and semantic use are checked downstream.

## Task 5B — TextEvidenceCandidate

`TextEvidenceCandidate` coexists with `HealthFindingCandidate`.

Minimum contract:

```text
source_id
source_format
source_locator
semantic_context_category
exact_excerpt
confidence
limitations
relevant_roles
decision_relevance
```

Identity-bearing evidence type, normalized claim key, and extraction-policy version are system-controlled according to semantic category. They must not be arbitrary caller-authored values.

Allowed evidence-producing categories:

```text
industry_context
strategy_profile
user_assumption
```

Context-only categories:

```text
business_question
decision_goal
```

Required invariants:

```text
candidate category == manifest category
candidate format == manifest format
structured candidate category == UserContextLocator category
scope comes from manifest
finding == exact normalized excerpt
supporting_evidence == exact normalized excerpt
```

## Task 6A — Grounded Role Schemas

### RoleKey

```text
executive
data_analyst
data_engineer
sales_marketing
project_manager
```

### GroundedFinding

```text
claim: nonblank string
evidence_references: nonempty unique list[EvidenceReference]
confidence: low | medium | high
```

### RoleView

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

### Typed Role-Generation Failures

At minimum, distinguish:

```text
ProviderFailure
ParseFailure
SchemaFailure
EvidenceReferenceFailure
InsufficientEvidence
RoleMismatchFailure
PolicyConfigurationFailure
UpstreamRoleFailure
```

These may be typed result records or exceptions according to the approved Task 6A design, but invalid outputs must never render as role cards.

## Deferred Schemas

```text
RiskResult            Task 7
WorkflowStep          Task 8
HumanReviewAction     Task 9
DecisionMemo          Task 9
DecisionTrajectory    Integration / run-log task
```

# 4. Module Map

## schemas.py
Purpose: frozen Pydantic contracts for identity, provenance, candidates, evidence, data health, and later grounded role results.
Failure cases: missing/extra fields, invalid identity syntax, incompatible format/locator/category combinations, invalid status transitions.

## identity.py
Purpose: deterministic `source_id` and `evidence_id` computation, source normalization, canonical serialization, and collision checking.
Important boundary: identity.py computes IDs; it does not construct EvidenceObject records.
Failure cases: invalid identity inputs, non-canonical JSON, same short ID with a different full digest.

## file_intake.py
Purpose: accept CSV bytes, normalize content, register a `SourceManifestEntry`, and optionally validate against a short-ID → digest registry.
Input: raw CSV bytes + semantic category.
Output: one `SourceManifestEntry`.
Failure cases: empty source, unsupported format, encoding failure, identity collision.

## text_parser.py
Purpose: normalize pasted text and register a text `SourceManifestEntry`.
Input: pasted text + semantic category.
Output: one `SourceManifestEntry`.
It does not yet derive text Evidence Objects.

## context_evidence.py *(Task 5B)*
Purpose: deterministically convert approved text/form context into bounded `TextEvidenceCandidate` records.

Input contract:

```text
raw_text
semantic_context_category
field_name
timezone-aware created_at
```

Behavior:

- industry context → one candidate per nonblank normalized paragraph;
- strategy profile → one candidate per structured field;
- user assumption → one candidate per structured field;
- business question / decision goal → manifest/context result with zero candidates;
- no LLM, summarization, or inferred business finding.

Failure cases:

- blank text or field name;
- unsupported category;
- category/format/locator mismatch;
- imprecise locator;
- uncontrolled identity key;
- missing limitation or invalid canonical role key.

## data_parser.py
Purpose: parse validated CSV bytes into a pandas DataFrame.
Failure cases: malformed CSV, wrong encoding, empty/all-null conditions according to approved parser behavior.

## data_health.py
Purpose: compute deterministic data-health metrics and emit `DataHealthSummary` plus `HealthFindingCandidate` records.
Does not compute IDs or construct Evidence Objects.

## evidence_builder.py
Purpose: convert an explicit union of approved candidate types into `EvidenceObject` records.

Task 5B accepted input:

```text
HealthFindingCandidate | TextEvidenceCandidate
```

Responsibilities:

- validate candidate ↔ manifest provenance;
- derive EvidenceScope from manifest provenance;
- canonicalize identity inputs;
- call identity.py for deterministic ID computation;
- deduplicate exact identities;
- reject short-ID collisions;
- construct EvidenceObject records.

No other module constructs EvidenceObject records from candidates.

## role_engine.py *(Task 6A)*
Purpose:

- load and validate exactly five roles from `config/role_policy.json`;
- project only allowed inputs to each role;
- expose only active, relevant evidence;
- call a provider-neutral `RoleViewProvider`;
- accept only a mapping or plain JSON object string;
- perform strict Pydantic validation;
- validate role key and claim-level evidence references;
- return valid RoleView records or typed failures.

No regex recovery, Markdown-fence stripping, trailing-prose repair, or silent mock substitution.

Project Manager behavior:

- generated after required non-PM role views;
- may cite only the exact union of upstream cited evidence IDs;
- any required upstream role failure returns `UpstreamRoleFailure` for PM.

The five-call design remains provisional pending Task 6B measurements.

## Live Provider Adapter *(Task 6B)*
Purpose: implement one runtime provider behind the provider-neutral interface.

Required decisions:

- provider/model;
- credentials;
- timeouts and retry count;
- token/output limits;
- temperature;
- sanitized metadata logging;
- live latency and cost;
- rate-limit behavior;
- explicit live failure versus visibly labeled offline mode.

The adapter must not contain role-policy, citation-validation, or EvidenceObject construction logic.

## risk_checker.py *(Task 7)*
Purpose: identify unsupported claims, scope misuse, assumptions represented as facts, correlation/causation errors, role overreach, and missing prerequisites.

A valid evidence reference does not prove semantic entailment. Task 7 and human review remain responsible for semantic misuse.

## workflow_planner.py *(Task 8)*
Purpose: produce ordered, evidence-citing `WorkflowStep` records after structured risk output exists.
Failure cases: blocked prerequisites, unresolved dependencies, circular sequence.

## memo_generator.py *(Task 9)*
Purpose: generate a post-review DecisionMemo from validated evidence, role views, risks, workflow steps, and recorded human actions.
Failure cases: missing review state, invalid references, unsupported final recommendation.

## main.py *(Task 10)*
Purpose: Streamlit evaluator path.

Suggested tabs:

1. Intake
2. Data Health
3. Evidence Board
4. RoleLens Views
5. Workflow Plan
6. Decision Memo

The UI must visibly distinguish internal observations, external context, stated priorities, assumptions, and decision context.

# 5. Technical Guardrails

- Use frozen, extra-forbidden Pydantic models for production contracts.
- Do not rely on free-form LLM text.
- Every `GroundedFinding` cites one or more unique, active, exposed Evidence Objects.
- View-level citations alone are insufficient.
- No admissible evidence returns typed `InsufficientEvidence`, not a generic role card.
- A non-null next action requires at least one grounded finding; it does not automatically require a risk or assumption.
- External context is never direct company proof.
- Stated priorities are intent, not performance.
- Assumptions remain unverified.
- `relevant_roles` is a routing hint, not an admissibility grant.
- Invalid provider output never renders.
- Mock/offline mode is visibly labeled and never silently replaces live failure.
- Do not overstate deterministic enforcement of natural-language role-policy rules.
- Do not introduce LangGraph, CrewAI, MCP, vector storage, or complex agent infrastructure in V1.
- Keep human review visible and required before the final memo.
