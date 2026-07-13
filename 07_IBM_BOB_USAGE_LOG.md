# 07_IBM_BOB_USAGE_LOG.md — RoleLens

> 更新日期：2026-07-12
> 用途：记录 IBM Bob 在 RoleLens 项目中的实际使用。
> 重要：IBM Bob 是本比赛要求的 primary development tool。

# IBM Bob Usage Summary
RoleLens will use IBM Bob across the software development lifecycle:

```text
planning
architecture
code generation
debugging
refactoring
testing
documentation
README preparation
```

# Usage Log

## Entry 001 — Repository Foundation and Evidence Identity Architecture

**Date:** 2026-07-12

**Task:** Plan Mode — architecture review and Evidence Identity design for RoleLens V1 foundation

**Project Area:** Architecture / Evidence Schema / Identity Contract / Source Provenance

**Prompt Used in IBM Bob:**

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

# Planned IBM Bob Tasks

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

# README Usage Section Draft
```text
## How IBM Bob Was Used

IBM Bob was used as the primary development assistant throughout the RoleLens development process. It supported architecture planning, identity and provenance contract design, schema definition, data parsing modules, evidence object builder, role engine, risk checker, workflow planner, memo generator, unit tests, debugging, refactoring, and README documentation.

The development process followed a human-in-the-loop workflow: IBM Bob generated initial plans and code, I reviewed and corrected the outputs, and all changes were documented in the IBM Bob usage log and Bob build log.
```
