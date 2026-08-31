# docs/bob_build_log.md — RoleLens

> 更新日期：2026-08-30
> 状态：Active Build Log
> 用途：公开记录 IBM Bob 如何作为主要开发工具参与 RoleLens 的规划、实现、测试和文档。

# IBM Bob Build Log

This log records preserved Bob evidence and the July production history whose Bob provenance is confirmed by the human author and supported by Git. It distinguishes exact prompts from timeline entries reconstructed from commits.

The verified entries cover:

```text
foundation planning and architecture
Tasks 1–5 implementation
test-driven debugging and testing
Evidence, role, Granite, risk, evaluation, workflow, review, and memo layers
first complete Streamlit prototype
```

---

# Entry 001 — Repository Foundation and Evidence Identity Architecture Planning

**Date:** 2026-07-12

**Project Area:** Planning / Architecture / Evidence Schema / Identity Contract

**Type:** Planning only — no source code or tests created

**Prompt Given to IBM Bob:**

**Prompt preservation:** Exact historical prompt not preserved. The planning summary below is preserved.

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

# Original Planned Bob Tasks (Approved Sequence)

This is the original July plan. The timeline below records the later Bob-assisted production outcomes.

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

---

# Entry 002 — First Vertical Slice Implementation (Tasks 1–5)

**Date:** 2026-07-13

**Project Area:** Implementation / Testing / Backend Pipeline

**Type:** Full implementation — source code, tests, sample data

**Prompt Given to IBM Bob:**

**Prompt preservation:** Exact preserved Bob prompt.

```text
Agent Mode. Continue. Execute the approved five-task implementation sequence.
Tasks 1–5, no Streamlit, no LLM integration. Commit each task when tests pass.
```

**Bob Output Summary:**

```text
Task 1 (29104c2) — app/schemas.py: 13 Pydantic v2 models (ContractModel base,
  5 enums, 3 locators, SourceLocator union, SourceManifestEntry, EvidenceObject,
  EvidenceReference, HealthFindingCandidate). tests/test_schemas.py: 234 tests.

Task 2 (9ff0040) — app/identity.py: generate_source_id(), generate_evidence_id(),
  normalize_source_content(), canonicalize_locator(), canonicalize_rule_parameters(),
  IdentityCollisionError, _FORMAT_ABBREV stable mapping.
  tests/test_identity.py: 137 tests covering idempotency, ordering sensitivity,
  semantic isolation, collision detection, all SourceFormat and
  SemanticContextCategory combinations.

Task 3 (13ffafe) — app/file_intake.py: ingest_csv(), ingest_source() dispatcher,
  EmptySourceError, UnsupportedSourceFormatError.
  app/text_parser.py: parse_pasted_text() for pasted_text / txt / markdown.
  app/utils.py: utc_now(), to_json_str(), save_run_log().
  sample_data/regional_sales_q1_q4.csv: 13 rows, 9 columns, deliberate missing
  values and 1 duplicate row for demo scenario.
  tests: 3 test files, 121 tests.

Task 4 (d6785a1) — app/data_parser.py: parse_csv() → validated pandas DataFrame.
  app/data_health.py: analyze_data_health() → DataHealthSummary +
  list[HealthFindingCandidate] with 6 rule types (duplicate_row,
  missing_value_rate, mixed_type_column, constant_column, all_null_column,
  unnamed_column). No evidence_id minted.
  DataHealthSummary added to app/schemas.py (deferred model, now implemented).
  normalized_claim_key vocabulary approved and implemented.
  tests: 2 test files, 88 tests.

Task 5 (0a91464) — app/evidence_builder.py: build_evidence() is the sole
  evidence_id minting function. Derives evidence_scope from source provenance.
  Handles duplicates (deduplication by identity), collisions (IdentityCollisionError).
  Raises EvidenceScopeError for decision_context sources.
  Raises MissingSourceManifestError for unregistered source_id.
  tests/test_evidence_builder.py: 47 tests including mock-based collision test,
  minting boundary enforcement, full pipeline integration test.
```

**Human Review:**

```text
All five tasks reviewed and approved as committed.
No architecture deviations. All invariants from Decision 002 are enforced by tests.
```

**Manual Changes:**

```text
- Task 4: Fixed EmptyDataFrameError condition for header-only CSV (zero-row DF).
- Task 4: Fixed all-null column detection for zero-row DF (vacuously all-null).
- Task 4: Corrected sample CSV row count assertion (13, not 12).
- These were caught by the tests and fixed before commit.
```

**Resulting Files:**

```text
app/__init__.py                     — empty package init
app/schemas.py                      — 13 models + DataHealthSummary (Task 4 addition)
app/identity.py                     — deterministic ID generation
app/file_intake.py                  — CSV intake
app/text_parser.py                  — pasted text adapter
app/utils.py                        — shared helpers
app/data_parser.py                  — CSV → DataFrame
app/data_health.py                  — DataFrame → health findings
app/evidence_builder.py             — sole evidence_id minting boundary
tests/__init__.py                   — empty test package init
tests/test_schemas.py               — 234 tests
tests/test_identity.py              — 137 tests
tests/test_file_intake.py           — ~60 tests
tests/test_text_parser.py           — ~44 tests
tests/test_utils.py                 — ~37 tests
tests/test_data_parser.py           — 31 tests
tests/test_data_health.py           — 57 tests
tests/test_evidence_builder.py      — 47 tests
sample_data/regional_sales_q1_q4.csv — demo sample data
requirements.txt                    — pydantic>=2,<3; pandas>=2,<3; pytest>=8,<9
```

**Test / Verification:**

```text
627 / 627 tests passing. 0 failures. 0 warnings.
python -m pytest -q → 627 passed in ~1.2s
git diff --check → clean (no trailing whitespace)
git status → working tree clean after all commits
```

**Related Commits:**

```text
29104c2  feat(schemas): core identity and provenance contract — Task 1
9ff0040  feat(identity): deterministic source and evidence ID generation — Task 2
13ffafe  feat(intake): CSV and pasted-text source intake, utils, sample data — Task 3
d6785a1  feat(data-health): CSV parsing, deterministic health analysis, DataHealthSummary — Task 4
0a91464  feat(evidence-builder): Evidence Object minting, scope derivation, deduplication — Task 5
```

**Evidence Saved:** Yes

---

## July Bob-Built Prototype Timeline

The human author confirms that IBM Bob was the primary development tool for these July production milestones. Git supplies the dates, commit messages, changed files, and resulting implementations. Except for the preserved Tasks 1–5 prompt above, exact historical prompts for these grouped milestones were not preserved.

| Date | Area | Bob-assisted outcome | Representative commit | Verification |
|---|---|---|---|---|
| July 12–13 | Architecture, identity, provenance, intake, and Evidence foundation | Human-reviewed architecture plus production schemas, deterministic source/Evidence IDs, source intake, data health, and the sole Evidence Object minting boundary | `29104c2`, `9ff0040`, `13ffafe`, `d6785a1`, `0a91464`, `6b8a6a9` | Preserved Tasks 1–5 record: 627 passed; provenance-hardening commit includes updated tests |
| July 18–20 | Structured-context Evidence | Text/form candidates, deterministic context extraction, and Evidence minting for text and structured context | `de8be17`, `e5a3ef2`, `794533a` | Schema, intake, parser, context-evidence, and Evidence-builder tests committed |
| July 20–24 | Governed roles and IBM Granite | Five role contracts and policy, provider-neutral grounded Role Engine, and watsonx Granite role adapter | `6a15296`, `f9385df`, `d3d02a9` | Dedicated role-schema, Role Engine, and Granite-provider tests committed |
| July 25 | Risk controls | Deterministic epistemic Risk Checker, provider-neutral semantic review, and Granite semantic-risk provider | `cf5248b`, `2c33433`, `3b09688` | Dedicated deterministic and provider tests committed |
| July 26–27 | Semantic evaluation | Fixed evaluation pack and live runner, frozen holdout infrastructure, calibrated taxonomy, and reviewed calibration/holdout records | `afb6f38`, `f7dc2d8`, `03637e9`, `272002a`, `8f1a2b2` | Scenario/runner tests and human-reviewed run records committed |
| July 27–28 | Workflow, review, and memo | Deterministic Workflow Planner, workflow scenarios, simulated human-review ledger, fail-closed Decision Memo, and audit scenarios | `6ed0455`, `f28b6d3`, `da3046e`, `7bc9d4a`, `a82b822` | Dedicated workflow, review, memo, and audit-scenario tests committed |
| July 29–31 | First complete working prototype | End-to-end Streamlit vertical slice, deterministic Telco business Evidence, Granite dataset orientation, and product-first governed Streamlit UI | `e782e87`, `fd4339f`, `fb9e86e`, `0178306` | Demo-pipeline, profile, orientation, and product-UI tests committed |

For the rows reconstructed from Git, **exact historical prompt not preserved**. No task-specific human correction is claimed unless it appears in the detailed preserved entries or commit record. Test files are evidence of implemented verification coverage; only the Tasks 1–5 row carries a preserved numerical test result.

---

## Tool Usage Boundary

**Date:** 2026-08-30

IBM Bob was the primary development tool for the foundational July build and first complete working prototype. The August product retained and extended those Evidence, provenance, role-policy, Granite, risk, workflow, review, memo, and evaluation foundations.

August Decision Diff and React/FastAPI product redesign were developed later with Codex and are not represented here as IBM Bob outputs.

