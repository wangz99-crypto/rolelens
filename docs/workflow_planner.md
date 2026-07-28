# Deterministic Workflow Planner

Task 8A converts validated RoleLens outputs into an inspectable coordination
sequence. It is deterministic by design: it has no model or provider, and it
uses only approved upstream action fields, evidence IDs, typed risk codes, and
fixed ordering rules. Equal valid inputs therefore produce exactly equal
plans.

This design supports the Future of Work theme by turning AI-assisted analysis
into a transparent, human-reviewed coordination sequence rather than another
free-form answer.

## Step types

The planner produces exactly three kinds of steps:

- `deterministic_risk_resolution` copies an exact
  `RiskFinding.required_action`.
- `semantic_review_gate` asks a human to resolve qualifying probabilistic
  candidates.
- `role_action` copies an exact successful `RoleView.next_action`.

The planner does not invent business recommendations. It groups deterministic
findings only when their required-action text is exactly equal. Semantic
candidate explanations are never converted into executable actions.

## Fixed dependency order

V1 uses this conservative role order:

1. Data Engineer
2. Data Analyst
3. Executive
4. Sales / Marketing
5. Project Manager

Every generated step for a role is a prerequisite for all generated steps of
later roles. Within a role, its semantic gate follows its deterministic
risk-resolution steps, and its role action follows both.

The expected B2B SaaS demonstration sequence is:

> Data Engineer validation → Data Analyst analysis → Executive review →
> Sales action → Project Manager coordination

`RoleView.dependency` remains visible as an exact free-text dependency note,
but it does not create or alter graph edges. The same is true of missing
information: it remains visible on the role action without controlling the
DAG. The planner does not parse either field for keywords or inferred
dependencies.

## Blockers and semantic review

A deterministic risk-resolution step carries the upstream
`blocks_downstream` value. A blocking step appears in
`blocking_step_ids`; role actions that depend on it become `blocked`, and the
plan becomes `blocked`. Nonblocking deterministic findings that require human
review remain `pending_human_review` and make dependent role actions pending
without being mislabeled as blockers.

Semantic candidates are non-authoritative. Candidates marked
`needs_human_review` or `reviewer_uncertain` are consolidated into one
nonblocking review gate per role. `likely_supported` candidates do not create
a gate. A semantic gate is always pending human review and can never approve,
reject, or block an action automatically.

If there are no deterministic resolution steps, qualifying semantic gates, or
role next actions, the planner returns an explicit `no_actionable_steps` plan.
Human review remains required because RoleLens V1 never auto-executes a plan.

## Integrity and execution boundary

Planning fails closed before step construction when role identities, evidence
records, citations, claim indexes, reviewed-role sets, or aggregate risk flags
are inconsistent. Evidence referenced by role views or risk records must
exist, remain active, and—at claim level—be cited by that exact grounded
finding.

Task 8A provides no auto-execution, completion mutation, live provider calls,
or real approval permissions. It is an inspectable proposal for simulated
human review. The fixed V1 ordering is intentionally conservative and is not a
general-purpose enterprise workflow engine.
