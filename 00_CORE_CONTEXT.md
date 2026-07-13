# 00_CORE_CONTEXT.md — RoleLens

> Updated: 2026-07-13
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

**Phase 2 — MVP Build: First Vertical Slice Complete**

The five-task backend pipeline is implemented, tested, and committed. 627 tests pass (0 failures). No LLM, no Streamlit yet. The evidence provenance chain is fully functional end-to-end from CSV bytes to minted EvidenceObject records.

**Completed commits (branch: chore/project-foundation):**

| Commit | Task | Tests Added |
|---|---|---|
| 0a91464 | Task 5 — Evidence Object builder | 47 |
| d6785a1 | Task 4 — CSV parsing and data health | 88 |
| 13ffafe | Task 3 — CSV and pasted-text intake | 121 |
| 9ff0040 | Task 2 — Deterministic identity | 137 |
| 29104c2 | Task 1 — Core schemas | 234 |

## Current Top Risks

1. The output may still look like a generic CSV chatbot unless the demo exposes evidence IDs, role boundaries, and dependencies.
2. Role engine, risk checker, workflow planner, memo generator, and Streamlit UI are not yet implemented — competition deadline pressure.
3. IBM Bob usage must be demonstrated with actual build artifacts, prompts, changes, and verification — not only a statement in the README.

## Locked Decisions

1. RoleLens is the main project direction.
2. V1 uses the five user-visible roles listed above.
3. Evidence Objects are the shared intermediate contract.
4. Human review and revision are product mechanisms.
5. V1 excludes real email, real approvals, enterprise integrations, long-term memory, and complex multi-agent infrastructure.
6. The existing **69/80 is a pre-prototype idea-selection prior**, not a product-completion score or a claim of first-place readiness.
7. Evidence identity and source-span provenance design is approved (Decision 002 in `04_DECISION_LOG.md`). `source_id` uses conservative order-sensitive identity. `evidence_id` uses a hybrid deterministic prefix + 12-hex format. `SourceFormat` and `SemanticContextCategory` are separate enums. `source_scope` and `evidence_scope` replace per-role admissibility lists. Only `evidence_builder.py` mints `evidence_id` values.

## Open Questions

1. Runtime LLM / IBM model choice (blocks role engine AI output)
2. How much human editing V1 supports
3. First 48-hour prototype pass/fail criteria
4. Role engine design: how RoleView citations are structured for the demo

**Resolved open questions:**
- `normalized_claim_key` vocabulary — approved and implemented in `app/data_health.py` (Task 4)
- Sample dataset schema — `sample_data/regional_sales_q1_q4.csv` (13 rows, 9 columns, deliberate quality issues)

## Next Deliverable

**Phase 2 continuation — role engine and Streamlit demo pipeline:**

```text
Task 6  — RoleView schemas + role_engine.py (loads role_policy.json, emits RoleView citing evidence_id)
Task 7  — RiskResult schema + risk_checker.py
Task 8  — WorkflowStep schema + workflow_planner.py
Task 9  — HumanReviewAction + DecisionMemo schemas + memo_generator.py
Task 10 — app/main.py (Streamlit UI — 6 tabs, demo scenario with sample_data)
```

Minimum demo scenario:
```text
regional_sales_q1_q4.csv + pasted industry context
→ EvidenceObject records (already working)
→ five role cards with evidence citations
→ risk flags for missing Q3/Q4 revenue and external context scope
→ human-reviewed decision memo
```

## Non-Negotiable Competition Rules

- IBM Bob is the primary development tool and its use is evidenced.
- AI is a core functional component.
- The prototype runs from documented setup instructions.
- The GitHub repository and demo video are public.
- The demo or presentation video is no longer than three minutes.
- Required IBM SkillsBuild learning activity is completed.
- Only one project is submitted for the month.

See `01_RULES_SCORECARD.md` for current status and evidence links.
