# 00_CORE_CONTEXT.md — RoleLens

> Updated: 2026-08-30
> Status: Canonical project context
> Purpose: Shared source of truth for IBM Bob, Codex, and human review.

## Project

IBM AI Builders Challenge — August 2026

Participant: Zhe Wang — University of Dayton — M.S. Business Analytics — solo participant

Challenge track: Wildcard Challenge — Build Intelligent Systems for the Future of Work

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

These are policy-constrained views over shared evidence. Their allowed inputs, required outputs, forbidden actions, and mandatory warnings are defined in `config/role_policy.json`.

### Internal system components

1. Evidence Builder
2. Role Engine
3. Risk Reviewer
4. Workflow Planner
5. Decision Memo Composer

The internal components perform bounded processing steps. Reference-derived labels such as Evidence Curator, Finance Reviewer, and Operations Reviewer are design inspiration only and are not additional user-facing roles.

## Core Workflow

```text
Mixed business materials
→ Source manifests and bounded evidence candidates
→ Evidence Objects with stable IDs and exact source locators
→ Five policy-constrained role views with claim-level citations
→ Risk and assumption checks
→ Cross-role action sequence
→ Human review and revision
→ Decision memo
```

## Current Phase

**Slice 5 — Competition Finish**

RoleLens now has a working product prototype with a FastAPI backend, React decision workspace, deterministic scenario and role-impact logic, governed Evidence, and explicit IBM Granite role-brief generation. The current Slice 5 task is submission completion and reconciliation of active competition-facing documentation with the implemented product.

Historical July research, architecture decisions, Bob work, evaluations, and dated project records remain historically accurate; they do not define the active August submission identity.

## Current Top Risks

1. The current real sample evidence primarily grounds Data Analyst and Data Engineer views. Without Task 5B, Executive and Sales must abstain and Project Manager generation is blocked; generic role cards would violate the evidence contract.
2. The provider-neutral Role Engine, live provider adapter, Risk Checker, Workflow Planner, Decision Memo, human-review flow, and Streamlit UI are not yet implemented.
3. A five-call role-generation design is only provisional. Live-provider latency, cost, rate limits, and four-role parallelism plus sequential Project Manager behavior must be measured against the three-minute demo budget.
4. IBM Bob must remain the primary production development tool, but Bob tasks must be narrow enough to avoid quota waste, scope overruns, and self-validating implementation errors.

## Locked Decisions

1. RoleLens is the main project direction.
2. V1 uses the five user-visible roles listed above.
3. Evidence Objects are the shared intermediate contract.
4. Human review and revision are product mechanisms.
5. V1 excludes real email, real approvals, enterprise integrations, long-term memory, and complex multi-agent infrastructure.
6. The existing **69/80 is a pre-prototype idea-selection prior**, not a product-completion score or a claim of first-place readiness.
7. Evidence identity and source-span provenance design is approved. `source_id` uses conservative order-sensitive identity. `evidence_id` uses a deterministic prefix plus 12-hex display suffix with a full digest stored separately. `SourceFormat` and `SemanticContextCategory` remain separate. `source_scope` and `evidence_scope` carry epistemic status.
8. `app/identity.py` computes deterministic identity values. `app/evidence_builder.py` is the only production module that converts approved candidates into `EvidenceObject` records.
9. Task 5B adds a bounded `TextEvidenceCandidate` alongside `HealthFindingCandidate`; it does not replace the health candidate with a generic abstraction.
10. Task 5B performs deterministic exact-source extraction only:
    - industry context → one candidate per nonblank normalized paragraph;
    - strategy profile → one candidate per structured field;
    - user assumption → one candidate per structured field;
    - business question and decision goal → source/trajectory context only, no Evidence Object.
11. Task 5B cannot author inferred business findings. `finding` and `supporting_evidence` both preserve the exact normalized excerpt. Evidence type, normalized claim key, and extraction-policy version are system-controlled identity inputs.
12. Role outputs require claim-level grounding through `GroundedFinding`. View-level citations alone are insufficient.
13. No admissible evidence produces typed `InsufficientEvidence`, no generic role card, and no unsupported next action.
14. The approved production sequence is:
    ```text
    Task 5B → Task 6A → Task 6B → Task 7 → Task 8 → Task 9 → Task 10
    ```
15. Task 6A defines grounded role contracts and a provider-neutral engine. Task 6B adds one live provider adapter. The exact five-call runtime design remains provisional until latency and cost are measured.
16. Local Codex spike implementations are disposable research artifacts. IBM Bob must independently implement approved production contracts.

## Open Questions

1. Which live runtime model/provider will be used for Task 6B, and how will IBM technology be made visible in the demo?
2. Is five-call generation demo-safe after measuring latency, cost, retries, and rate limits?
3. How much human editing and rejection/revision history will V1 preserve?
4. What exact B2B SaaS churn dataset and internal business evidence will support Executive and Sales without unsupported ROI or broad-outreach claims?
5. How should natural-language role-policy rules be divided between Task 6 prompt constraints, Task 7 deterministic checks, and mandatory human review?

### Resolved questions

- Data-health `normalized_claim_key` values are implemented and tested.
- Claim-level citations are required.
- `TextEvidenceCandidate` coexists with `HealthFindingCandidate`.
- Business question and decision goal do not produce evidence.
- The current `regional_sales_q1_q4.csv` remains a backend test fixture; it is not yet approved as the final competition demo dataset.

## Next Deliverable

**Task 5B — Deterministic text and structured-context evidence completion**

Minimum production scope:

```text
pasted industry context
→ exact normalized paragraph candidates
→ external_context Evidence Objects

strategy profile form field
→ exact structured candidate
→ stated_priority Evidence Object

user assumption form field
→ exact structured candidate
→ assumption Evidence Object

business question / decision goal
→ decision_context source records only
→ no Evidence Object
```

Required implementation boundary:

- add `TextEvidenceCandidate` without replacing `HealthFindingCandidate`;
- add one bounded context-evidence extractor;
- support `form_input` source manifests for approved structured fields;
- extend `evidence_builder.py` to accept the explicit candidate union;
- enforce candidate ↔ manifest ↔ locator category and format consistency;
- use canonical machine role keys as routing hints only;
- keep every existing production test green;
- use IBM Bob for the independent production implementation and log prompt → output → human changes → verification.

After Task 5B passes:

```text
Task 6A — RoleKey, GroundedFinding, RoleView, typed failures,
          policy validation, strict parsing, provider-neutral engine,
          deterministic visibly-offline test provider

Task 6B — one live provider adapter, credential handling, timeout/retry policy,
          latency and cost measurement
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
