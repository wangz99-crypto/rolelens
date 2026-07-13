# 06_ARCHITECTURE_CODE_MAP.md — RoleLens

> 更新日期：2026-07-12
> 状态：Architecture Draft v2 — Identity and Provenance Contract Approved

# 1. Architecture Overview

```text
User Inputs
CSV / Excel + Pasted Text + Strategy Profile + Business Question
        ↓
file_intake.py  +  text_parser.py (minimal pasted-text adapter)
        ↓
SourceManifestEntry records  (source_id, identity_digest, source_scope)
        ↓
┌────────────────────────┬──────────────────────────────┐
│ data_parser.py         │ text_parser.py               │
│ (CSV → DataFrame)      │ (pasted text → TextChunk)    │
└────────────────────────┴──────────────────────────────┘
        ↓                            ↓
data_health.py               (future text evidence extraction)
HealthFindingCandidate list  (no evidence_id)
        ↓
        └──────── evidence_builder.py ────────┘
                          ↓
              EvidenceObject records (evidence_id minted here only)
                          ↓
              RoleLens Decision Engine  (role_engine.py)
              Loads role_policy.json at runtime
                          ↓
 Executive | Data Analyst | Data Engineer | Sales/Marketing | PM
 Each RoleView cites evidence_id values; forbidden inputs enforced
                          ↓
              risk_checker.py
              Enforces: external_context ≠ direct company proof
              Critical risks block or qualify affected execution actions
                          ↓
               workflow_planner.py
               WorkflowStep records cite evidence_id values
                          ↓
              Decision draft state → Human Review Interface
                          ↓
              memo_generator.py  (post human review)
              Final DecisionMemo cites evidence_id values
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
│   ├── __init__.py
│   ├── schemas.py          ← Task 1: all provenance/identity Pydantic models
│   ├── identity.py         ← Task 2: deterministic ID generation (not utils.py)
│   ├── file_intake.py      ← Task 3: source intake → SourceManifestEntry
│   ├── text_parser.py      ← Task 3: minimal pasted-text adapter
│   ├── utils.py            ← Task 3: shared helpers (timestamps, JSON, log save)
│   ├── data_parser.py      ← Task 4: CSV → DataFrame
│   ├── data_health.py      ← Task 4: DataFrame → HealthFindingCandidate list
│   ├── evidence_builder.py ← Task 5: candidates → EvidenceObject (minting only here)
│   ├── role_engine.py      ← later: policy-constrained role views
│   ├── risk_checker.py     ← later: risk flags citing evidence_id
│   ├── workflow_planner.py ← later: WorkflowStep records
│   ├── memo_generator.py   ← later: post-human-review DecisionMemo
│   └── main.py             ← later: Streamlit UI (after backend is testable)
├── config/
│   └── role_policy.json    ← runtime role boundary authority (exists)
├── prompts/                ← later: LLM prompt templates
├── sample_data/            ← Task 3: sample CSV for reproducible demo
├── outputs/
│   └── run_logs/           ← JSON decision trajectories
├── tests/
│   ├── __init__.py
│   ├── test_schemas.py     ← Task 1
│   ├── test_identity.py    ← Task 2
│   ├── test_file_intake.py ← Task 3
│   ├── test_text_parser.py ← Task 3
│   ├── test_data_parser.py ← Task 4
│   ├── test_data_health.py ← Task 4
│   └── test_evidence_builder.py ← Task 5
├── docs/
├── README.md
└── requirements.txt
```

`app/config.py` is deferred — no config needs beyond `role_policy.json` exist yet.

# 3. Core Schemas

*All schemas defined in `app/schemas.py`. Schema models are grouped by implementation task.*

## Task 1 — Core Identity and Provenance Schemas

### Enums

```text
SourceFormat:           csv | excel | pasted_text | txt | markdown | form_input
                        (pdf_text: delayed optional support)

SemanticContextCategory: data_source | internal_report | industry_context |
                          strategy_profile | business_question | decision_goal |
                          user_assumption

SourceScope:            internal_observation | external_context |
                        user_assertion | decision_context

EvidenceScope:          internal_observation | external_context |
                        assumption | stated_priority

EvidenceStatus:         active | invalidated
```

### Source Locator Models (discriminated union, discriminator = locator_type)

```text
TabularSourceLocator    locator_type="tabular"
  columns: list[str]                    required
  row_range: tuple[int,int] | None      optional
  sheet_name: str | None                optional  (Excel only)
  cell_range: str | None                optional  (Excel only)
  metric: str | None                    optional
  aggregation: str | None               optional

TextSourceLocator       locator_type="text"
  line_start: int | None                optional
  line_end: int | None                  optional
  char_start: int | None                optional
  char_end: int | None                  optional
  heading_path: str | None              optional
  paragraph_index: int | None           optional
  chunk_index: int | None               optional
  excerpt_checksum: str | None          optional

UserContextLocator      locator_type="user_context"
  field_name: str                       required
  form_section: str | None              optional
  context_category: SemanticContextCategory  required
  user_entered_version: str | None      optional

SourceLocator = Annotated[Union[Tabular, Text, UserContext], discriminator="locator_type"]
```

### SourceManifestEntry

```text
source_id: str                          required  src-{format_abbrev}-{12_hex}
identity_digest: str                    required  full SHA-256 hex (64 chars)
source_format: SourceFormat             required
semantic_context_category: SemanticContextCategory  required
source_scope: SourceScope               required
filename: str | None                    optional  excluded from identity
upload_event_id: str | None             optional  excluded from identity
id_algo_version: str                    required  default "v1"
created_at: datetime                    required
```

### EvidenceObject

```text
evidence_id: str                        required  ev-{type_abbrev}-{12_hex}
identity_digest: str                    required  full SHA-256 hex (64 chars)
source_id: str                          required
source_format: SourceFormat             required
source_locator: SourceLocator           required  typed discriminated union
evidence_type: str                      required  rule key e.g. "missing_value_rate"
evidence_scope: EvidenceScope           required
extraction_method: "deterministic"|"llm_assisted"  required
finding: str                            required  human-readable; NOT an identity input
supporting_evidence: str                required
confidence: "low"|"medium"|"high"       required
limitations: list[str]                  required  empty list allowed
relevant_roles: list[str]               required  must be non-empty
decision_relevance: str                 required
id_algo_version: str                    required  default "v1"
created_by: "data_health"|"evidence_builder"|"llm_pipeline"  required
status: EvidenceStatus                  required  default "active"
invalidated_reason: str | None          optional  required when status=="invalidated"
```

### EvidenceReference

```text
evidence_id: str                        required  format validated; existence not validated at schema level
relevance_note: str | None              optional
```

Cross-object referential integrity (does this `evidence_id` exist in the current trajectory?) is handled by a separate registry or trajectory validation function — not by the Pydantic model alone.

### HealthFindingCandidate

```text
source_id: str                          required
source_format: SourceFormat             required
source_locator: SourceLocator           required
evidence_type: str                      required  rule key
canonical_rule_parameters: dict         required  deterministic rule inputs
normalized_claim_key: str               required  short stable key, not free-form text
finding: str                            required
supporting_evidence: str                required
confidence: "low"|"medium"|"high"       required
limitations: list[str]                  required
relevant_roles: list[str]               required  non-empty
decision_relevance: str                 required
```

**No `evidence_id` field.** This type enforces the minting boundary: `data_health.py` produces `HealthFindingCandidate`; only `evidence_builder.py` produces `EvidenceObject`.

## Deferred Schema Models (later tasks — not yet implemented)

```text
DataHealthSummary     Task 4
RoleView              Role engine task
RiskResult            Risk checker task
WorkflowStep          Workflow planner task
HumanReviewAction     Human review task
DecisionMemo          Memo generator task
DecisionTrajectory    Integration task
```

These models are not yet defined. They will be added to `app/schemas.py` in their respective tasks.

# 4. Module Map

## schemas.py *(Task 1)*
Purpose: all Pydantic models for identity, provenance, and evidence contracts.
Input: none (pure definition).
Output: importable models — `SourceFormat`, `SemanticContextCategory`, `SourceScope`, `EvidenceScope`, `EvidenceStatus`, locator models, `SourceLocator` union, `SourceManifestEntry`, `EvidenceObject`, `EvidenceReference`, `HealthFindingCandidate`.
Failure cases: missing required field raises `ValidationError`; invalid `evidence_id` format rejected.

## identity.py *(Task 2)*
Purpose: deterministic `source_id` and `evidence_id` generation, content normalization, canonical locator serialization, and `IdentityCollisionError`.
Input: `source_format`, `semantic_context_category`, normalized content → `(source_id, identity_digest)`. `source_id`, `evidence_type_key`, locator, rule params, claim key → `(evidence_id, identity_digest)`.
Output: short hybrid ID + full SHA-256 `identity_digest`.
Failure cases: short ID match with different `identity_digest` → `IdentityCollisionError`. `identity_digest` must be persisted alongside the short ID — not in-memory only.
Note: identity generation belongs here, not in `utils.py`.

## file_intake.py *(Task 3)*
Purpose: accept a CSV file or pasted text; normalize content; call `identity.py`; emit `SourceManifestEntry` records.
Input: raw bytes + `SourceFormat` declaration + `SemanticContextCategory`.
Output: `list[SourceManifestEntry]` with stable `source_id` and `identity_digest`.
Failure cases: empty file, unsupported format, encoding failure, missing `semantic_context_category`.

## text_parser.py *(Task 3 — minimal adapter)*
Purpose: accept pasted text; normalize; produce a `SourceManifestEntry` and a `TextSourceLocator` for use by `evidence_builder.py`. No chunking, no section splitting, no PDF handling in V1 first slice.
Input: raw pasted string + `SemanticContextCategory`.
Output: `SourceManifestEntry`.
Later extensions: TXT / Markdown section splitting, heading extraction. PDF text extraction is delayed optional support.

## utils.py *(Task 3)*
Purpose: shared helpers only — timestamp formatting, JSON serialization, run log persistence (`outputs/run_logs/`). No identity generation, no business logic.

## data_parser.py *(Task 4)*
Purpose: parse CSV bytes from a `SourceManifestEntry` into a validated pandas DataFrame.
Input: `SourceManifestEntry` + raw CSV bytes.
Output: `DataFrame`.
Failure cases: malformed CSV, wrong encoding, empty DataFrame.

## data_health.py *(Task 4)*
Purpose: compute deterministic health metrics from a `DataFrame`; emit `DataHealthSummary` and `list[HealthFindingCandidate]`. Does **not** mint `evidence_id`.
Input: `SourceManifestEntry` + `DataFrame`.
Output: `DataHealthSummary` + `list[HealthFindingCandidate]`.
Key fields computed: `row_count`, `column_count`, `missing_value_rates`, `duplicate_row_count`, `outlier_flags`, `schema_issues`. `readiness_score` is deferred until a defensible scoring method is approved.
Failure cases: all-null DataFrame raises structured error; empty input is valid (returns empty candidate list).
Note: `HealthFindingCandidate` objects carry no `evidence_id`. Minting is solely `evidence_builder.py`'s responsibility.

## evidence_builder.py *(Task 5)*
Purpose: convert validated `HealthFindingCandidate` objects into `EvidenceObject` records; mint all `evidence_id` values; detect and handle duplicates and collisions. **The only module that mints `evidence_id`.**
Input: `list[HealthFindingCandidate]` + `list[SourceManifestEntry]`.
Output: `list[EvidenceObject]`.
Duplicate handling: same identity inputs → existing `evidence_id` returned; no second object created.
Collision handling: short ID match with different `identity_digest` → `IdentityCollisionError`.
Empty input: valid; returns empty list.

## role_engine.py *(later)*
Purpose: load `role_policy.json` at runtime; filter admissible evidence per role; generate `RoleView` records citing `evidence_id` values. Enforces forbidden inputs and required warnings.
Failure cases: role receives no admissible evidence (must flag `missing_information`); forbidden input consumed by role.

## risk_checker.py *(later)*
Purpose: identify weak assumptions, unsupported claims, and interpretation risks; produce `RiskResult` records citing `evidence_id` values. Must run before `workflow_planner.py`. Enforces that `external_context` evidence is not cited as direct company-specific proof.
Critical risks and unmet prerequisites block or qualify affected execution actions; planner receives structured risk output, not a global stop.

## workflow_planner.py *(later)*
Purpose: generate cross-role action sequence as `WorkflowStep` records citing `evidence_id` values. Downstream of `risk_checker.py`.
Failure cases: blocked prerequisites, circular dependency.

## memo_generator.py *(later)*
Purpose: post-human-review; generate final `DecisionMemo` citing `evidence_id` values. Runs after human review actions are recorded.
Failure cases: no human review action recorded; missing evidence references.

## main.py *(later — after backend pipeline is testable)*
Purpose: Streamlit app entry point. Renders all six UI tabs: Intake, Data Health, Evidence Board, RoleLens Views, Workflow Plan, Decision Memo.
Input: uploaded files and user context.
Output: rendered UI.
Failure cases: missing file, invalid file type, invalid LLM response.
Note: `app/main.py` is required within the first complete V1 vertical slice and competition demo. It must not be built before the backend evidence pipeline is independently testable.

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
