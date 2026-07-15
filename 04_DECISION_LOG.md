# 04_DECISION_LOG.md — RoleLens 决策记录

> 更新日期：2026-07-14
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

---

## Decision 002

**Date:** 2026-07-12
**Area:** Evidence Identity, Source Provenance, and Minting Boundary

### Decision

Adopt the following approved architecture for source identity, evidence identity, source provenance, and evidence admissibility in RoleLens V1.

### Identity Contract

#### source_id

`source_id` identifies a specific, conservative, order-sensitive version of an uploaded or user-provided source. It does **not** represent semantic equivalence across reordered or reformatted sources.

**Identity inputs (pipe-delimited, hashed with SHA-256):**
```text
id_algo_version | source_format | semantic_context_category | normalized_content
```

**Display format:** `src-{format_abbrev}-{12_hex}`

**Full SHA-256 digest stored separately as `identity_digest`.** If a short ID matches an existing entry but the `identity_digest` differs, raise `IdentityCollisionError`. No in-memory-only collision registry.

**Normalization rules (all source types):** encoding → UTF-8, BOM stripped, Unicode NFC, line endings → LF. No other reordering or deduplication is applied.

**Order preservation:**
- CSV: row order, column order, and duplicate rows preserved.
- Excel: sheet order, row order, and column order preserved.
- Markdown / TXT: section, paragraph, and line order preserved.
- Pasted text: as-entered order preserved.

**Excluded from identity:** filename, upload timestamp, session ID, upload event ID.

**Semantic context isolation:** the same text submitted to two different semantic fields (e.g., `industry_context` vs. `strategy_profile`) produces different `source_id` values because `semantic_context_category` is an identity input.

**Future `equivalence_fingerprint`:** a separate order-insensitive hash may be added later for semantic deduplication without touching the identity contract.

#### evidence_id

`evidence_id` identifies one specific Evidence Object derived from a source.

**Identity inputs (pipe-delimited, hashed with SHA-256):**
```text
id_algo_version | source_id | evidence_type_key | canonical_source_locator | canonical_rule_parameters | normalized_claim_key
```

Free-form `finding` and `explanation` text are **not** identity inputs.

**Display format:** `ev-{evidence_type_abbrev}-{12_hex}`

**Full SHA-256 digest stored separately as `identity_digest`.** Same collision handling as `source_id`.

**Canonical serialization** for locator and rule parameters: explicitly sorted JSON (key-order deterministic). The exact method is an implementation detail resolved in Task 2.

#### Stable abbreviation mapping

The exact `format_abbrev` and `evidence_type_abbrev` values are defined and tested in Task 2 (identity module). They are not hardcoded in the schema task.

### Enum Separation

`SourceFormat` (physical format) and `SemanticContextCategory` (semantic purpose) are separate enums. Industry context and strategy profile are semantic categories, not physical source formats.

**SourceFormat values:** `csv`, `excel`, `pasted_text`, `txt`, `markdown`, `form_input`. PDF text extraction is delayed optional support.

**SemanticContextCategory values:** `data_source`, `internal_report`, `industry_context`, `strategy_profile`, `business_question`, `decision_goal`, `user_assumption`.

### Source and Evidence Scope

`source_scope` and `evidence_scope` carry epistemic metadata on the source record and evidence object respectively. They replace per-role admissibility lists in `SourceManifestEntry`. `role_policy.json` remains the sole runtime authority for role input boundaries.

**SourceScope values and meaning:**

| Value | Meaning |
|---|---|
| `internal_observation` | Company-specific structured data or internal report |
| `external_context` | Industry report, market data, benchmarks |
| `user_assertion` | User-entered unverified claim |
| `decision_context` | Business question or decision goal — context only, produces no EvidenceObject |

**EvidenceScope values and mapping from SourceScope:**

| EvidenceScope | Derived from SourceScope |
|---|---|
| `internal_observation` | `internal_observation` source |
| `external_context` | `external_context` source |
| `assumption` | `user_assertion` source |
| `stated_priority` | strategy goal or profile assertion |

`business_question` and `decision_goal` have `source_scope = decision_context` and do **not** produce EvidenceObjects. Strategy profile goals produce EvidenceObjects with `evidence_scope = stated_priority` and must be labeled as user assertions, not independently verified performance facts.

`risk_checker.py` enforces that `external_context` and `assumption` scoped evidence is not cited as direct company-specific proof.

### Minting Boundary

`data_health.py` produces `HealthFindingCandidate` objects. These are structured finding candidates with no `evidence_id` field.

`app/identity.py` computes deterministic identity values. Only `evidence_builder.py` converts approved candidate objects into `EvidenceObject` records. No other production module may construct Evidence Objects from candidates.

An empty candidate input to `evidence_builder.py` is valid and returns an empty evidence list. It is not automatically a hard failure.

Identity generation belongs in `app/identity.py`, not `app/utils.py`. `app/utils.py` retains shared helpers: timestamp formatting, JSON serialization, run log persistence.

### Evidence Status

`EvidenceStatus` is limited to two values: `active` and `invalidated`.

Duplicate evidence is a deduplication outcome handled during minting — no duplicate `EvidenceObject` is created.

A short-ID match with a different `identity_digest` raises `IdentityCollisionError` and does not create a collision `EvidenceObject`.

### First Five Implementation Tasks

```text
Task 1 — Core identity and provenance schemas
         Files: app/schemas.py, app/__init__.py, tests/test_schemas.py

Task 2 — Deterministic identity and canonicalization
         Files: app/identity.py, tests/test_identity.py

Task 3 — CSV and minimal pasted-text intake / source manifests
         Files: app/file_intake.py, app/text_parser.py (minimal), app/utils.py,
                sample_data/, tests/test_file_intake.py, tests/test_text_parser.py

Task 4 — CSV parsing and deterministic data-health candidates
         Files: app/data_parser.py, app/data_health.py,
                tests/test_data_parser.py, tests/test_data_health.py

Task 5 — Evidence Object builder
         Files: app/evidence_builder.py, tests/test_evidence_builder.py
```

Task 1 must be completed and tests must pass before Task 2 begins. Each subsequent task follows in dependency order.

**Task 1 schema scope:** `SourceFormat`, `SemanticContextCategory`, `SourceScope`, `EvidenceScope`, source-specific locator models, `SourceLocator` union, `SourceManifestEntry`, `EvidenceObject`, `EvidenceReference`, `EvidenceStatus`, `HealthFindingCandidate`.

**Deferred to later schema tasks:** `RoleView`, `RiskResult`, `WorkflowStep`, `HumanReviewAction`, `DecisionMemo`, `DecisionTrajectory`.

### Alternatives Considered and Rejected

| Alternative | Reason Rejected |
|---|---|
| Order-insensitive CSV identity (default deduplication) | Rejected — silently hides reordered time-series or intentional row sequences; conservative order-sensitive rule is simpler and safer |
| User declaration of "time-series" vs "entity" CSV | Rejected — adds UX friction and brittleness; order-sensitive identity for all types eliminates the need |
| Per-role `admissible_for` list in `SourceManifestEntry` | Rejected — duplicates `role_policy.json` authority; `source_scope` / `evidence_scope` metadata is the correct boundary |
| Sequential human-readable IDs | Rejected — session-dependent, fragile across runs, breaks automated tests |
| Full SHA-256 as display ID | Rejected — unreadable in demo and role cards |
| In-memory-only collision registry | Rejected — does not survive session restart; `identity_digest` must be persisted with the short ID |
| `EvidenceStatus.duplicate` and `EvidenceStatus.collision` enum values | Rejected — duplicate is a minting outcome, collision is an error condition; neither warrants a persistent object status |
| `readiness_score` as required `DataHealthSummary` field | Rejected — no defensible scoring method approved yet; deferred until scoring method is reviewed |
| Free-form finding text as evidence identity input | Rejected — unstable; LLM rewording would produce a false new `evidence_id` |

### Risks

1. `IdentityCollisionError` requires a persistent collision registry (not per-session). Must be handled before Task 5 produces stored trajectories.
2. `normalized_claim_key` vocabulary is not yet approved. Must be resolved during Task 4 design review before `data_health.py` produces real output.
3. `app/main.py` (Streamlit UI) is required within the first complete V1 vertical slice and competition demo, but must not be built before the backend evidence pipeline is testable.

### Validation Plan

1. Task 2 tests confirm `generate_source_id` is idempotent across runs, order-sensitive for all source types, and semantic-category-isolated.
2. Task 5 tests confirm `evidence_builder.py` is the only module that produces objects with `evidence_id` fields.
3. Integration test (Task 5 or later): same `HealthFindingCandidate` list always produces the same `evidence_id` values.
4. Edge-case tests: duplicate candidate → deduplication (no second object); collision path → `IdentityCollisionError` raised.


### Post-Implementation Validation Update — 2026-07-14

Tasks 1–5 and the independent identity/provenance repair are complete.

Validated outcomes:

- public identity APIs reject invalid formats and non-canonical identity inputs;
- short-ID collision checks require the same short ID with a different full digest;
- candidate and manifest provenance mismatches fail closed;
- duplicate source manifests cannot silently overwrite each other;
- contract models are frozen to prevent partial invalid mutation;
- canonical locator and rule-parameter JSON is enforced;
- hardcoded golden identity vectors lock the current V1 byte format;
- the full repository suite reports 675 passing tests with zero failures.

The original risk that `normalized_claim_key` vocabulary was unresolved is closed for deterministic data-health outputs. A separate bounded vocabulary is required for Task 5B text/context candidates.

The remaining storage concern is not the collision algorithm itself but persistence of the short-ID → full-digest registry in future decision trajectories.

### Status
Approved and implementation-validated — 2026-07-14

### Revisit Date
After Task 5B integration and saved decision-trajectory persistence.

---

## Decision 003

**Date:** 2026-07-14  
**Area:** Text Evidence Completion and Grounded Role-Engine Sequence

### Decision

Before implementing the production Role Engine, add a bounded deterministic text/context evidence stage and adopt claim-level grounding for role outputs.

The approved implementation order is:

```text
Task 5B — Text and structured-context evidence completion
Task 6A — Grounded role contracts and provider-neutral Role Engine
Task 6B — One live provider adapter and measured runtime behavior
Task 7  — Risk Checker
Task 8  — Workflow Planner
Task 9  — Human review and Decision Memo
Task 10 — Streamlit UI
```

### Context

Two local disposable Codex spikes were used to discover implementation risks. The Task 6 spike showed that the current real sample produces only data-health Evidence Objects relevant mainly to Data Analyst and Data Engineer. Executive and Sales therefore lack admissible evidence, and Project Manager generation cannot safely proceed.

The Task 5B spike compared three candidate-model options and tested deterministic exact-source extraction for industry context, strategy priorities, user assumptions, business questions, and decision goals.

The spike code remains local-only. It is not production code and will not be merged, cherry-picked, copied, or pushed.

### Approved Task 5B Candidate Contract

Add `TextEvidenceCandidate` alongside `HealthFindingCandidate`.

Do not:

- reuse the health-specific type as the permanent text contract;
- replace both types with a generic `EvidenceCandidate`;
- call an LLM;
- summarize or infer business findings.

Allowed evidence-producing categories:

| Category | Extraction granularity | Evidence scope |
|---|---|---|
| `industry_context` | one nonblank normalized paragraph | `external_context` |
| `strategy_profile` | one structured form field | `stated_priority` |
| `user_assumption` | one structured form field | `assumption` |

Context-only categories:

| Category | Behavior |
|---|---|
| `business_question` | source/trajectory context; no candidate and no Evidence Object |
| `decision_goal` | source/trajectory context; no candidate and no Evidence Object |

For Task 5B:

```text
finding = exact normalized excerpt
supporting_evidence = exact normalized excerpt
```

Evidence type, normalized claim key, and extraction-policy version are fixed by the system according to semantic category. They are not free-form caller inputs.

### Provenance Invariants

The production implementation must fail closed unless:

```text
candidate.source_id matches a registered manifest
candidate.source_format == manifest.source_format
candidate.semantic_context_category == manifest.semantic_context_category
structured candidate category == UserContextLocator.context_category
scope is derived from the manifest, never selected by the candidate
```

Text locators must preserve inclusive line and character spans, paragraph index, and excerpt checksum after approved source normalization.

### Role-Relevance Decision

`relevant_roles` uses only canonical machine keys:

```text
executive
data_analyst
data_engineer
sales_marketing
project_manager
```

It is a routing hint, not an admissibility guarantee or proof that a role may use an external source as an internal fact.

### Grounded Role Contract

Task 6A must use claim-level grounding:

```text
GroundedFinding:
  claim
  evidence_references
  confidence
```

A `RoleView` contains a nonempty list of `GroundedFinding` records rather than one free-form key finding with view-level citations.

Required behavior:

- every grounded claim cites at least one unique active Evidence Object;
- every cited ID existed in and was exposed to that provider request;
- the returned role key matches the requested role;
- invalid, fabricated, hidden, or invalidated references fail closed;
- malformed JSON, Markdown-fenced JSON, trailing prose, missing fields, and extra fields do not render;
- no admissible evidence returns typed `InsufficientEvidence`, no role card, and `next_action = None`;
- a next action requires at least one grounded finding;
- natural-language semantic overreach is not falsely presented as fully deterministic enforcement.

### Provider and Call-Graph Decision

Task 6A defines a provider-neutral synchronous protocol and a deterministic, visibly offline test provider.

Task 6B adds one live provider adapter.

A successful conceptual batch may require four independent business-role calls followed by a sequential Project Manager call. This five-call design is **provisional**, not locked. Before final adoption, measure:

- serial and parallel latency;
- prompt and completion cost;
- timeout and retry behavior;
- rate-limit behavior;
- three-minute demo impact.

A mock provider must never silently substitute for a failed live provider.

### Alternatives Considered

| Alternative | Decision | Reason |
|---|---|---|
| Reuse `HealthFindingCandidate` for text | Rejected | Minimal migration but semantically misleading and loses bounded text-specific rules |
| Replace all candidates with generic `EvidenceCandidate` | Rejected for V1 | Broad migration and weaker type-specific safeguards |
| Entire text field as one Evidence Object | Rejected | Locator and citation become too coarse |
| Sentence/LLM claim extraction | Rejected for V1 | Adds inference risk and unnecessary complexity |
| View-level citations only | Rejected | Permits citation laundering across unsupported claims |
| Generate generic role cards without evidence | Rejected | Violates “No evidence ID, no decision claim” |
| Merge or copy Codex spike implementation | Rejected | IBM Bob must independently implement official production code |

### Main Risks

1. Exact-source evidence prevents invented findings but does not prove source truth or semantic entailment.
2. External context can still be mischaracterized as company-specific proof unless Task 7 and human review catch it.
3. Free-text role policies cannot all be deterministically enforced.
4. The five-call model may exceed demo latency or provider budget.
5. The final B2B SaaS demo still needs internal evidence capable of supporting bounded Executive and Sales findings without unsupported ROI or broad-outreach recommendations.

### Validation Method

Task 5B must prove:

- stable source and evidence identities;
- semantic-category isolation;
- precise excerpt locators;
- duplicate handling;
- exact excerpt preservation;
- decision-context exclusion;
- correct evidence-scope derivation;
- category/format/locator/manifest consistency;
- canonical machine role keys;
- no direct EvidenceObject construction outside `evidence_builder.py`;
- all existing production tests remain green.

Task 6A must prove:

- runtime role-policy/schema alignment;
- per-role input isolation;
- claim-level citation integrity;
- strict structured-output parsing;
- typed failure isolation;
- Project Manager sequencing;
- explicit offline-provider metadata;
- no role card when evidence is insufficient.

### Status

Approved for independent IBM Bob implementation.

### Revisit Date

After Task 5B production tests pass and after Task 6B live-provider latency/cost measurements.
