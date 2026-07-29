# Simulated Human Review Ledger

Task 9A records simulated human decisions about an immutable WorkflowPlan. It
is not real approval authority and it does not execute workflow actions,
complete blockers, grant permissions, or establish that an action is legally
or operationally safe.

## Exact plan binding

Every `HumanReviewSession` carries a deterministic SHA-256 digest of the exact
reviewed WorkflowPlan. The digest uses the complete canonical JSON
representation of the plan, including actions, dependencies, Evidence IDs,
risk-code lineage, statuses, and blocker flags. Equal plans produce equal
digests; a meaningful plan change produces a different digest.

The WorkflowPlan remains immutable. Review records snapshot each step's
original action, owner, evidence lineage, risk codes, status, and
`blocks_downstream` flag. The ledger never rewrites those source facts.

## Explicit decisions and completion

Each workflow step requires an explicit human decision:

- **Accept** retains the original action for the later memo.
- **Reject** excludes the action and requires a written reviewer note.
- **Revise** stores a different human-authored action and a written note.

Partial review is allowed. Reviewed steps and pending step IDs remain in
WorkflowPlan order, and the session stays `pending` until every step has an
explicit decision. The API never invents a decision or automatically accepts
a pending step.

Semantic review gates may be accepted or rejected, but either decision
requires a written note explaining how the probabilistic concern was handled.
They cannot be revised into a different action.

Revisions are not evidence- or semantically revalidated by RoleLens. Every
revised record sets `revision_requires_revalidation=true` and must be visibly
labeled:

> Human revision — evidence support not revalidated

Accepting a proposed blocker-remediation step does not mean that the
underlying blocker was completed. The reviewed record retains the original
blocker flag and status, and Task 9A provides no blocker completion tracking
or automatic resolution.

An empty `no_actionable_steps` plan also requires human judgment. It remains
pending until the caller explicitly sets `no_action_acknowledged=true` and
supplies a non-blank overall note.

## Intended review interface

A later interface should show, for every workflow step:

- original action;
- owner role;
- supporting Evidence IDs;
- deterministic and semantic risk codes;
- original `ready`, `blocked`, or `pending_human_review` status; and
- explicit Accept, Reject, and—where permitted—Revise controls.

The interface must present revisions with the warning above and must not imply
that these simulated decisions are real permissions or completed work.

## Scope and next stage

Decision Memo generation and Markdown export are deferred to Task 9B. The
memo composer will require a complete `HumanReviewSession`; a partial or
unacknowledged session is not sufficient.

V1 deliberately includes no timestamps, authentication, reviewer accounts,
email identity, multi-user permissions, or real approval integration.

This ledger supports the Future of Work theme by creating an inspectable
handoff between AI-generated coordination and accountable human judgment,
instead of silently converting AI recommendations into execution.

The core limitation remains explicit: this ledger records a simulated review
decision. It does not prove that an action was completed, authorized, legally
approved, evidence-validated after revision, or operationally safe.
