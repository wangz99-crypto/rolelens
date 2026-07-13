# 00_CORE_CONTEXT.md — RoleLens

> Updated: 2026-07-12
> Status: Canonical project context
> Purpose: Shared source of truth for IBM Bob, Codex, and human review.

## Project

IBM AI Builders Challenge — July 2026

Participant: Zhe Wang — University of Dayton — M.S. Business Analytics — solo participant

Challenge track: Wild Card Challenge — Build Intelligent Systems for the Future of Work

## Selected Direction

**RoleLens: AI Decision Team for Business Data**

RoleLens converts mixed business materials—structured data, business reports, and strategy context—into evidence-backed role views, risks, missing information, an ordered workflow, and a human-reviewed decision memo.

## Product Boundary

RoleLens is a decision-support workflow, not a generic chatbot and not a simulated team of five AI coworkers.

### User-visible business roles

1. Executive
2. Data Analyst / Data Scientist
3. Data Engineer
4. Sales / Marketing
5. Project Manager

These are views over shared evidence. Their permissions and required warnings are defined in `role_policy.json`.

### Internal system components

1. Evidence Builder
2. Risk Reviewer
3. Workflow Planner
4. Decision Memo Composer

The internal components perform bounded processing steps. Reference-derived labels such as Evidence Curator, Finance Reviewer, and Operations Reviewer are design inspiration only and are not additional user-facing roles.

## Core Workflow

```text
Mixed business materials
→ Evidence objects with source references
→ Five role-specific decision views
→ Risk and assumption checks
→ Cross-role action sequence
→ Human review and revision
→ Decision memo
```

## Current Phase

**Phase 2 — MVP Build and Architecture Validation**

Direction selection, the five-role policy, and the first evaluation plan are complete. The next proof point is a working, testable prototype.

## Current Top Risks

1. The output may still look like a generic CSV chatbot unless the demo exposes evidence IDs, role boundaries, and dependencies.
2. Source-span traceability and evidence identity contracts are approved but not yet implemented in code.
3. IBM Bob usage must be demonstrated with actual build artifacts, prompts, changes, and verification—not only a statement in the README.

## Locked Decisions

1. RoleLens is the main project direction.
2. V1 uses the five user-visible roles listed above.
3. Evidence Objects are the shared intermediate contract.
4. Human review and revision are product mechanisms.
5. V1 excludes real email, real approvals, enterprise integrations, long-term memory, and complex multi-agent infrastructure.
6. The existing **69/80 is a pre-prototype idea-selection prior**, not a product-completion score or a claim of first-place readiness.
7. Evidence identity and source-span provenance design is approved (Decision 002 in `04_DECISION_LOG.md`). `source_id` uses conservative order-sensitive identity. `evidence_id` uses a hybrid deterministic prefix + 12-hex format. `SourceFormat` and `SemanticContextCategory` are separate enums. `source_scope` and `evidence_scope` replace per-role admissibility lists. Only `evidence_builder.py` mints `evidence_id` values.

## Open Questions

1. Runtime LLM / IBM model choice
2. Exact sample dataset schema
3. How much human editing V1 supports
4. First 48-hour prototype pass/fail criteria
5. `normalized_claim_key` vocabulary — to be approved during Task 4 design review

## Next Deliverable

First five implementation tasks (approved sequence):

```text
Task 1 — Core identity and provenance schemas (app/schemas.py, app/identity.py stubs)
Task 2 — Deterministic identity and canonicalization (app/identity.py)
Task 3 — CSV and minimal pasted-text intake / source manifests (app/file_intake.py, app/text_parser.py)
Task 4 — CSV parsing and deterministic data-health candidates (app/data_parser.py, app/data_health.py)
Task 5 — Evidence Object builder (app/evidence_builder.py)
```

After Task 5, the first executable vertical slice produces:

```text
CSV upload + pasted business context
→ SourceManifestEntry records with stable source_id values
→ DataHealthSummary and HealthFindingCandidate objects
→ EvidenceObject records with stable evidence_id values
→ (subsequent tasks) five policy-constrained role cards, risk checks, reviewed decision memo
```

The vertical slice must include at least one evaluation scenario and one real IBM Bob build-log entry.

## Non-Negotiable Competition Rules

- IBM Bob is the primary development tool and its use is evidenced.
- AI is a core functional component.
- The prototype runs from documented setup instructions.
- The GitHub repository and demo video are public.
- The demo or presentation video is no longer than three minutes.
- Required IBM SkillsBuild learning activity is completed.
- Only one project is submitted for the month.

See `01_RULES_SCORECARD.md` for current status and evidence links.
