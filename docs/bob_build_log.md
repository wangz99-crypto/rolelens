# docs/bob_build_log.md — RoleLens

> 更新日期：2026-07-12
> 状态：Active Build Log
> 用途：公开记录 IBM Bob 如何作为主要开发工具参与 RoleLens 的规划、实现、测试和文档。

# IBM Bob Build Log

IBM Bob is used as the primary development assistant for RoleLens.

This log records how Bob supported the project across:

```text
planning
architecture
implementation
debugging
testing
documentation
```

---

# Entry 001 — Repository Foundation and Evidence Identity Architecture Planning

**Date:** 2026-07-12

**Project Area:** Planning / Architecture / Evidence Schema / Identity Contract

**Type:** Planning only — no source code or tests created

**Prompt Given to IBM Bob:**

```text
Plan Mode. Architecture review and Evidence Identity design for RoleLens V1.

Covered: minimum repository foundation, evidence identity and provenance design
(source_id, evidence_id, source_locator), identity strategy comparison,
Pydantic schema impact, failure and edge-case analysis, first five
implementation tasks, conflict and scope review.

Second pass: applied 3 human decisions and 10 corrections.
```

**Bob Output Summary:**

```text
Pass 1 — Full architecture plan (13 sections):
- Module foundation tiers and file responsibilities
- Hybrid deterministic ID design (prefix + truncated SHA-256)
- Discriminated SourceLocator union design
- Proposed Pydantic model set with EvidenceObject field gap analysis
- 20-case failure and edge-case matrix
- First five implementation tasks in dependency order
- Conflict and scope review; acceptance checklist

Pass 2 — Revised plan applying human decisions:
- Conservative order-sensitive identity for all source types
- identity_digest (renamed from full_digest); persistent storage required
- source_scope / evidence_scope replacing per-role admissibility lists
- SourceFormat separated from SemanticContextCategory
- EvidenceStatus limited to active | invalidated
- HealthFindingCandidate introduced (no evidence_id); minting boundary enforced
- app/identity.py approved as the correct module for ID generation
- readiness_score deferred; Task 1 scope narrowed; deferred model list
```

**Human Review:**

```text
Modified — three explicit human decisions applied; ten additional corrections
applied in a second plan pass. Final plan is the human-approved result of
Bob's proposal plus all corrections.
```

**Manual Changes:**

```text
- EvidenceScope internal_fact renamed to internal_observation
- EvidenceStatus.duplicate and EvidenceStatus.collision removed
- full_digest renamed to identity_digest throughout
- admissible_for lists removed from SourceManifestEntry
- HealthFindingCandidate introduced as a new schema type
- Identity generation module renamed from utils.py to identity.py
- readiness_score removed from required DataHealthSummary contract
- Task 1 test scope limited to implemented behavior only
```

**Resulting Files (documentation only):**

```text
00_CORE_CONTEXT.md    — Open question 3 resolved; locked decision 7 added;
                        next deliverable updated to five-task sequence
04_DECISION_LOG.md    — Decision 002 added with full identity contract
05_PRODUCT_SPEC.md    — Evidence Object contract updated; scope metadata added;
                        IBM Bob usage plan updated to match approved tasks
06_ARCHITECTURE_CODE_MAP.md — v2: app/identity.py added; all schemas updated;
                        HealthFindingCandidate → evidence_builder minting boundary shown;
                        deferred models clearly labeled; module map updated
07_IBM_BOB_USAGE_LOG.md — Entry 001 added (this planning task)
docs/bob_build_log.md — Entry 001 added (this entry)
```

**Test / Verification:**

```text
Planning task only. No code run.
Verification: all six documentation files updated consistently.
No conflicts detected between canonical files after update.
Architecture consistent across 00_CORE_CONTEXT.md, 04_DECISION_LOG.md,
05_PRODUCT_SPEC.md, and 06_ARCHITECTURE_CODE_MAP.md.
```

**Related Commit:**

```text
Not yet committed. Pending human review of documentation updates.
```

**Evidence Saved:** Yes

---

# Planned Bob Tasks (Approved Sequence)

## Task 1 — Core Identity and Provenance Schemas

Implement `app/schemas.py` and `tests/test_schemas.py`.

Models: `SourceFormat`, `SemanticContextCategory`, `SourceScope`, `EvidenceScope`, `EvidenceStatus`, `TabularSourceLocator`, `TextSourceLocator`, `UserContextLocator`, `SourceLocator` (discriminated union), `SourceManifestEntry`, `EvidenceObject`, `EvidenceReference`, `HealthFindingCandidate`.

No LLM, no Streamlit, no file I/O. Tests cover all model validation rules.

## Task 2 — Deterministic Identity and Canonicalization

Implement `app/identity.py` and `tests/test_identity.py`.

Functions: `generate_source_id()`, `generate_evidence_id()`, content normalization, `canonical_locator_string()`, `IdentityCollisionError`.

## Task 3 — CSV and Pasted-Text Intake

Implement `app/file_intake.py`, `app/text_parser.py` (minimal), `app/utils.py`.
Create `sample_data/` with one sample CSV.
Include `tests/test_file_intake.py` and `tests/test_text_parser.py`.

## Task 4 — CSV Parsing and Data-Health Candidates

Implement `app/data_parser.py` and `app/data_health.py`.
`data_health.py` produces `DataHealthSummary` and `list[HealthFindingCandidate]` — no `evidence_id`.
Include `tests/test_data_parser.py` and `tests/test_data_health.py`.

## Task 5 — Evidence Object Builder

Implement `app/evidence_builder.py` and `tests/test_evidence_builder.py`.
`evidence_builder.py` is the only module that mints `evidence_id`.
Handles duplicates (no second object) and collisions (`IdentityCollisionError`).

## Later Tasks (after vertical slice)

```text
Task 6  — Role engine (policy-constrained role views)
Task 7  — Risk checker (evidence-cited risk results)
Task 8  — Workflow planner (ordered workflow steps)
Task 9  — Memo generator (post-human-review decision memo)
Task 10 — Streamlit UI shell (app/main.py)
Task 11 — Integration tests and evaluation scenarios
Task 12 — README, demo preparation, final documentation
```
