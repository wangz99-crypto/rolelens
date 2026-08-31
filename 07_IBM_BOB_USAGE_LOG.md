# 07_IBM_BOB_USAGE_LOG.md — RoleLens

> 更新日期：2026-08-30
> 用途：记录 IBM Bob 在 RoleLens 项目中的实际使用。
> 重要：IBM Bob 是 2026 年 7 月基础构建和首个完整原型的主要开发工具；2026 年 8 月最终产品重设计主要使用 Codex。

# IBM Bob Usage Summary

This log combines preserved Bob records with a Git-evidenced July timeline whose tool provenance is confirmed by the human author. IBM Bob was the primary development tool for the foundational July build and first complete working prototype. Exact prompts are quoted only where preserved; later July milestones reconstructed from Git are labeled accordingly.

```text
verified planning and architecture
verified Tasks 1–5 implementation
human-confirmed July Bob development beyond Tasks 1–5
Git-evidenced Evidence, role, Granite, risk, evaluation, workflow, review,
memo, and Streamlit prototype outcomes
explicit August Codex boundary
```

# Usage Log

## Entry 001 — Repository Foundation and Evidence Identity Architecture

**Date:** 2026-07-12

**Task:** Plan Mode — architecture review and Evidence Identity design for RoleLens V1 foundation

**Project Area:** Architecture / Evidence Schema / Identity Contract / Source Provenance

**Prompt Used in IBM Bob:**

**Prompt preservation:** Exact historical prompt not preserved. The planning summary below is preserved.

```text
Planning and architecture analysis for RoleLens V1.

Produce a reviewed architecture plan covering:
A. Minimum repository foundation
B. Evidence identity and provenance design
C. First implementation sequence

(Full prompt included PART A through PART G covering repository foundation,
evidence identity and provenance design, identity strategy comparison, schema
impact, failure and edge-case analysis, first five implementation tasks, and
conflict/scope review. Plan Mode — no code created.)
```

**Bob Initial Output Summary:**

```text
Bob produced a full architecture plan across 13 sections covering:
- Module foundation tiers (required now / later / out of scope)
- Evidence identity contract: source_id and evidence_id hybrid prefix + truncated hash design
- Source locator discriminated union design
- Identity strategy comparison (sequential vs content-hash vs hybrid)
- Proposed Pydantic model set including EvidenceObject field gap analysis
- 20-case failure and edge-case matrix
- First five implementation tasks in dependency order
- Conflict and scope review
- Acceptance checklist

Original proposal included:
- order-insensitive CSV identity as default
- admissible_for lists on SourceManifestEntry
- EvidenceStatus.duplicate and EvidenceStatus.collision enum values
- readiness_score as a required DataHealthSummary field
- identity generation in app/utils.py
- in-memory-only collision registry
- EvidenceObject as the output of data_health.py
```

**Human Corrections Applied:**

```text
Human Decision 1: Reject order-insensitive CSV identity.
  Adopt conservative order-sensitive identity for all source types.
  Remove user declaration of time-series vs entity CSV.

Human Decision 2: Approve hybrid ID format with modifications.
  Rename full_digest to identity_digest.
  Require persistent storage of identity_digest, not in-memory registry only.
  Abbreviation mapping deferred to Task 2 implementation.

Human Decision 3: Reject admissible_for lists in SourceManifestEntry.
  Replace with source_scope and evidence_scope metadata.
  role_policy.json remains sole runtime authority for role boundaries.

Additional corrections (10 items):
  - Separate SourceFormat (physical) from SemanticContextCategory (semantic)
  - Remove industry_context and strategy_profile as SourceFormat values
  - Add form_input as a SourceFormat value
  - Revise EvidenceStatus to active | invalidated only
  - data_health.py produces HealthFindingCandidate (no evidence_id); only
    evidence_builder.py mints evidence_id
  - evidence_id identity inputs must include normalized_claim_key; exclude
    free-form finding text
  - app/identity.py replaces app/utils.py for ID generation
  - Canonical serialization uses explicitly sorted JSON (implementation detail
    deferred to Task 2)
  - app/main.py is delayed but required within first complete vertical slice,
    not post-V1
  - minimal text_parser.py included in vertical slice (Task 3)
  - Empty HealthFindingCandidate input is valid; returns empty list
  - Task 1 narrowed to core identity and provenance schemas only
  - Deferred: RoleView, RiskResult, WorkflowStep, HumanReviewAction,
    DecisionMemo, DecisionTrajectory
  - readiness_score removed from required DataHealthSummary contract
  - Task 1 test scope limited to behavior actually implemented in Task 1
  - Cross-object referential integrity deferred to registry / trajectory
    validation function
```

**How I Used It:**
```text
Used as primary architecture design tool in Plan Mode.
Bob's output was reviewed, corrected, and refined through two passes.
Final architecture is the human-approved result of Bob's proposal plus
explicit human decisions and corrections.
```

**Manual Changes Made:**

```text
All 3 human decisions and 10 corrections applied in a second Plan Mode pass.
EvidenceScope internal_fact renamed to internal_observation for consistency
with SourceScope.
EvidenceStatus simplified to two values (active | invalidated).
HealthFindingCandidate introduced as a new model type with no evidence_id.
identity_digest field name approved (replacing full_digest).
app/identity.py approved as the correct module for ID generation.
```

**Result:**

```text
Architecture plan approved. Six canonical documentation files updated:
00_CORE_CONTEXT.md, 04_DECISION_LOG.md, 05_PRODUCT_SPEC.md,
06_ARCHITECTURE_CODE_MAP.md, 07_IBM_BOB_USAGE_LOG.md,
docs/bob_build_log.md.

Decision 002 added to 04_DECISION_LOG.md with full identity contract,
alternatives rejected, risks, and validation plan.

No source code or tests created. Plan Mode only.
Ready to begin Task 1 implementation after human approval.
```

**Evidence Saved:** Yes

**Screenshot / Commit / File Reference:**
```text
Planning session — no commit yet.
Evidence: this log entry + docs/bob_build_log.md Entry 001 +
04_DECISION_LOG.md Decision 002 + 06_ARCHITECTURE_CODE_MAP.md v2.
Verification: canonical files updated; architecture plan consistent across
all six updated files; no conflicts introduced.
```

# Original Planned IBM Bob Tasks

This is the July planning sequence. The production timeline below records which later tasks were subsequently implemented with Bob assistance.

## Task 1 — Core Identity and Provenance Schemas
```text
Implement app/schemas.py with the approved Pydantic models:
SourceFormat, SemanticContextCategory, SourceScope, EvidenceScope,
EvidenceStatus, TabularSourceLocator, TextSourceLocator,
UserContextLocator, SourceLocator (discriminated union),
SourceManifestEntry, EvidenceObject, EvidenceReference,
HealthFindingCandidate.
Include tests/test_schemas.py.
No LLM, no Streamlit, no file I/O.
```

## Task 2 — Deterministic Identity and Canonicalization
```text
Implement app/identity.py with generate_source_id(), generate_evidence_id(),
content normalization per source type, canonical_locator_string(),
and IdentityCollisionError.
Full SHA-256 digest stored as identity_digest alongside short display ID.
Include tests/test_identity.py.
```

## Task 3 — CSV and Pasted-Text Intake
```text
Implement app/file_intake.py to accept CSV files and produce
SourceManifestEntry records using identity.py.
Implement app/text_parser.py as a minimal pasted-text adapter.
Implement app/utils.py for shared helpers.
Create sample_data/ with one sample CSV.
Include tests/test_file_intake.py and tests/test_text_parser.py.
```

## Task 4 — CSV Parsing and Data-Health Candidates
```text
Implement app/data_parser.py (CSV → DataFrame).
Implement app/data_health.py (DataFrame → DataHealthSummary +
list[HealthFindingCandidate]).
HealthFindingCandidate must have no evidence_id field.
Include tests/test_data_parser.py and tests/test_data_health.py.
```

## Task 5 — Evidence Object Builder
```text
Implement app/evidence_builder.py to convert HealthFindingCandidate
objects into EvidenceObject records and mint evidence_id values.
evidence_builder.py is the only module that mints evidence_id.
Empty input is valid; returns empty list.
Duplicate: no second object created.
Collision: IdentityCollisionError raised.
Include tests/test_evidence_builder.py.
```

# Historical README Usage Section Draft — Superseded

The July draft proposed broad lifecycle wording before the July/August tool boundary was documented. It is superseded because it did not distinguish the later Codex product redesign. The current README and Tool Usage Boundary below are authoritative.

```text
Historical draft superseded. See the current README and the dated tool-usage
boundary in this log for the supported provenance statement.
```

---

# Entry 002 — First Vertical Slice Implementation (Tasks 1–5)

**Date:** 2026-07-13

**Task:** Implement the approved Tasks 1–5 sequence in IBM Bob Agent Mode.

**Prompt preservation:** Exact preserved Bob prompt.

**Actual Bob role:** Bob generated the first production implementations and tests for core schemas, deterministic identity, source intake, CSV parsing/data health, and the Evidence Object builder from the previously reviewed architecture.

**Output summary:**

- Added the Pydantic identity/provenance contracts and their tests.
- Added deterministic source and Evidence identity generation.
- Added CSV/pasted-text intake and shared utilities.
- Added deterministic CSV parsing and data-health candidates.
- Added the sole Evidence Object minting boundary with duplicate/collision handling.

**Human changes:**

- Corrected header-only CSV empty-data behavior.
- Corrected all-null handling for zero-row dataframes.
- Corrected the sample CSV row-count assertion.

**Historical verification:**

- The contemporaneous public build log records `627 / 627` tests passing, zero failures, zero warnings, and a clean `git diff --check` after Tasks 1–5.
- This is a dated July verification record, not the current repository test total.

**Commit references:**

```text
29104c2  Task 1 — core identity and provenance schemas
9ff0040  Task 2 — deterministic identity and canonicalization
13ffafe  Task 3 — CSV and pasted-text intake
d6785a1  Task 4 — CSV parsing and deterministic data health
0a91464  Task 5 — Evidence Object builder
```

**Evidence source:** `docs/bob_build_log.md`, Entry 002.

---

# July Bob-Assisted Production Timeline

The entries below are **historical tasks reconstructed from Git evidence and human-confirmed tool provenance**. Unless an entry says otherwise, the exact historical Bob prompt was not preserved. Commit dates, messages, changed files, and resulting capabilities are directly supported by repository history; no unrecorded test totals or task-specific human corrections are inferred.

## Entry 003 — Provenance Hardening and Structured Context Evidence

- **Date range:** 2026-07-13–2026-07-20
- **Development task:** Harden deterministic provenance and extend the Evidence pipeline to text, form input, and structured context.
- **IBM Bob's role:** Primary development tool for this July implementation.
- **Prompt preservation:** Exact historical prompt not preserved.
- **Resulting implementation:** Strengthened identity/provenance integrity; added `TextEvidenceCandidate`, form intake, deterministic context extraction, and Evidence Object minting for text/context candidates.
- **Representative commits:** `6b8a6a9`, `de8be17`, `e5a3ef2`, `794533a`.
- **Human review / corrections:** No task-specific correction transcript was found in the preserved Bob logs.
- **Verification / tests:** The commits include updated schema, intake, parser, context-evidence, identity, and Evidence-builder test modules; no historical aggregate pass count is claimed.
- **Evidence source:** Git commit history and the files changed by the representative commits.

## Entry 004 — Grounded Roles and watsonx Granite Adapter

- **Date range:** 2026-07-20–2026-07-24
- **Development task:** Implement grounded role contracts, role-policy enforcement, the provider-neutral Role Engine, and the first watsonx Granite role adapter.
- **IBM Bob's role:** Primary development tool for this July implementation.
- **Prompt preservation:** Exact historical prompt not preserved.
- **Resulting implementation:** Added five-role schemas and `config/role_policy.json`, grounded provider-neutral role execution, evidence-reference validation, and `app/granite_provider.py`.
- **Representative commits:** `6a15296`, `f9385df`, `d3d02a9`.
- **Human review / corrections:** No task-specific correction transcript was found in the preserved Bob logs.
- **Verification / tests:** Each capability was committed with its corresponding role-schema, Role Engine, or Granite-provider test module; no historical aggregate pass count is claimed.
- **Evidence source:** Git commit history and committed production/test files.

## Entry 005 — Deterministic and Semantic Risk Controls

- **Date range:** 2026-07-25
- **Development task:** Add deterministic epistemic checks, a provider-neutral semantic-review boundary, and a Granite semantic-risk provider.
- **IBM Bob's role:** Primary development tool for this July implementation.
- **Prompt preservation:** Exact historical prompt not preserved.
- **Resulting implementation:** Added `risk_checker.py`, `semantic_risk_reviewer.py`, `granite_semantic_risk_provider.py`, related schemas, and fail-closed tests.
- **Representative commits:** `cf5248b`, `2c33433`, `3b09688`.
- **Human review / corrections:** No task-specific correction transcript was found in the preserved Bob logs.
- **Verification / tests:** The three commits include dedicated deterministic, provider-neutral, and Granite-provider risk test modules; no historical aggregate pass count is claimed.
- **Evidence source:** Git commit history and committed production/test files.

## Entry 006 — Semantic Evaluation, Calibration, and Frozen Holdout

- **Date range:** 2026-07-26–2026-07-27
- **Development task:** Build the deterministic semantic evaluation pack and runner, freeze a holdout, calibrate the Granite taxonomy, and record reviewed runs.
- **IBM Bob's role:** Primary development tool for the July evaluation infrastructure.
- **Prompt preservation:** Exact historical prompt not preserved.
- **Resulting implementation:** Added fixed scenario packs, deterministic scoring, a fail-safe live runner, frozen calibration/holdout records, and supporting tests.
- **Representative commits:** `afb6f38`, `f7dc2d8`, `03637e9`, `272002a`, `8f1a2b2`.
- **Human review / corrections:** The committed evaluation-run review files document human review; no separate Bob correction transcript was found.
- **Verification / tests:** Evaluation-runner and scenario tests were committed. Reviewed artifacts record calibration v2 and frozen holdout outcomes; they are evaluation evidence, not a general reliability claim.
- **Evidence source:** Git history, `docs/evaluation.md`, scenario fixtures, and `docs/evaluation_runs/` reviewed records.

## Entry 007 — Workflow, Human Review, and Decision Memo

- **Date range:** 2026-07-27–2026-07-28
- **Development task:** Implement deterministic workflow planning, a simulated human-review ledger, fail-closed Decision Memo composition, and audit scenarios.
- **IBM Bob's role:** Primary development tool for this July implementation.
- **Prompt preservation:** Exact historical prompt not preserved.
- **Resulting implementation:** Added `workflow_planner.py`, workflow evaluation scenarios, `human_review.py`, `memo_generator.py`, and memo audit evaluation.
- **Representative commits:** `6ed0455`, `f28b6d3`, `da3046e`, `7bc9d4a`, `a82b822`.
- **Human review / corrections:** The memo commit records fail-closed error normalization; no preserved prompt or separate task-specific human-correction transcript was found.
- **Verification / tests:** Each layer was committed with dedicated workflow, human-review, memo, or audit-scenario tests; no historical aggregate pass count is claimed.
- **Evidence source:** Git commit history and committed implementation, documentation, and test files.

## Entry 008 — First Complete Streamlit Prototype

- **Date range:** 2026-07-29–2026-07-31
- **Development task:** Assemble the first end-to-end working prototype, then add deterministic Telco business Evidence, a grounded Granite dataset-orientation brief, and a product-first governed Streamlit experience.
- **IBM Bob's role:** Primary development tool for the July prototype.
- **Prompt preservation:** Exact historical prompt not preserved.
- **Resulting implementation:** Added the demo pipeline and `app/main.py` Streamlit vertical slice, business profiling, dataset orientation, `product_view.py`, sample data, and product UI documentation.
- **Representative commits:** `e782e87`, `fd4339f`, `fb9e86e`, `0178306`.
- **Human review / corrections:** No task-specific correction transcript was found in the preserved Bob logs.
- **Verification / tests:** The commits include demo-pipeline, business-profile, dataset-orientation, and product-UI tests; no historical aggregate pass count is claimed.
- **Evidence source:** Git commit history and committed prototype, documentation, sample-data, and test files.

---

## Tool Usage Boundary

**Date:** 2026-08-30

- IBM Bob was the primary development tool for the foundational July build and first complete RoleLens prototype.
- Starting in August, product development shifted primarily to Codex. This includes the deterministic break-even redesign, Decision Diff engine and RoleLens bridge, human decision-revision experience, React/FastAPI Decision Room, trusted impact propagation, reproducibility work, and governed Granite Role Impact Brief integration.
- The August product retained and extended the Bob-built Evidence, provenance, role-policy, Granite, risk, workflow, human-review, memo, and evaluation foundations.
- This log intentionally does not attribute August Codex work to IBM Bob.

Representative August Codex commits include `9d400bc`, `f02b62d`, `ddc680b`, `c798107`, `79f8959`, `b74b953`, `689e96a`, `1d8c863`, and `ca6191a`. They are listed only to make the boundary auditable, not as Bob outputs.
