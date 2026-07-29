# Deterministic Post-Review Decision Memo

Task 9B composes a structured `DecisionMemo` only after a simulated human
review is complete. It is deterministic: the same immutable WorkflowPlan,
complete HumanReviewSession, and active EvidenceObject registry produce
exactly the same memo.

A free-form LLM memo would undo the controls established upstream. It could
smooth over rejected work, omit blockers, rewrite accepted action text,
present probabilistic review as fact, or detach claims from Evidence IDs.
Task 9B therefore uses exact source fields and deterministic process
templates. It makes no model, provider, network, environment, timestamp, or
randomness call.

## Required inputs and fail-closed binding

Composition requires:

1. one exact immutable `WorkflowPlan`;
2. one complete `HumanReviewSession` with no pending steps; and
3. the current `EvidenceObject` registry.

The session digest must match the canonical SHA-256 digest of the plan, and
its ordered step IDs must match exactly. The composer also compares every
reviewed-step snapshot against its WorkflowStep: identity, sequence, kind,
owner, original action, Evidence IDs, deterministic and semantic risk codes,
original status, and blocker flag. The digest is not trusted by itself.

Conflicting Evidence records fail closed. Every cited Evidence ID must exist
and remain active. Unrelated registry records are not copied into the memo.
The source plan, review session, and Evidence records remain unchanged.

Exact Pydantic object type is not treated as sufficient proof of internal
validity at the public composer boundary. Every EvidenceObject is revalidated
from its serialized payload before composition. Likewise, a schema-valid
workflow object that cannot satisfy the memo's stricter provenance
requirements—such as a role action or semantic gate without supporting
Evidence IDs—fails with a sanitized `DecisionMemoInputError` before any memo
section is created. Internal validation traces, supplied source text, and raw
Pydantic error output are never exposed to the UI.

## Memo sections

The memo preserves the full reviewed trajectory:

- **Retained action sequence** contains accepted original actions and
  explicitly marked human revisions.
- **Semantic review decisions** document accepted or rejected probabilistic
  gates without turning them into executable actions or factual verification.
- **Rejected steps** remain visible for audit but are excluded from retained
  actions.
- **Unresolved blockers** include every original step whose
  `blocks_downstream` flag remains true.
- **Missing information** remains attached to role actions whether they were
  retained, revised, or rejected.
- **Evidence cited** snapshots only active EvidenceObjects referenced by the
  primary memo sections, in first-seen plan order.
- **Control notices** state the non-execution, blocker, revision, semantic, and
  empty-plan boundaries that apply.

Deterministic risk-remediation records may sometimes contain no Evidence IDs.
This is allowed when the control issue is precisely insufficient evidence or
a role-generation failure. Such records are control actions, not
evidence-backed business claims. A retained `role_action`, by contrast, must
retain at least one supporting Evidence ID.

## Revisions, blockers, and semantic gates

Accepted action text is copied exactly and never rewritten. A human revision
stores both the original and replacement text, carries
`action_origin=human_revision`, and sets
`revision_requires_revalidation=true`. Copied Evidence IDs describe the
original lineage only; RoleLens does not claim that they support the revised
wording.

When no blocker exists, a retained human revision produces
`requires_revalidation`. When any original step blocks downstream, `blocked`
takes precedence. Accepting, rejecting, or revising a blocker-remediation step
does not complete or clear the blocker.

Semantic gates appear only in the review-gate section. Their accept/reject
decision and written note show how the human handled a probabilistic concern;
they do not verify the underlying claim and do not authorize an action.

An explicitly acknowledged empty plan produces
`no_action_acknowledged`, empty action and Evidence sections, the human's
overall note, and a notice that no actionable workflow step was proposed.

## Intended interface

The intended UI presents these sections in order:

1. Review state
2. Retained action sequence
3. Semantic review decisions
4. Rejected steps
5. Unresolved blockers
6. Missing information
7. Evidence cited
8. Control notices

The interface must visibly warn that human revisions require Evidence and
semantic revalidation. It must not imply real approval or execution.

## Future of Work value and limits

The memo preserves the chain from AI-assisted analysis to human judgment,
including what was rejected, revised, blocked, or left uncertain. It avoids a
polished answer with hidden provenance.

A `DecisionMemo` is a deterministic reviewed record. It does not prove
execution, authorization, legal approval, blocker completion, operational
safety, or the validity of human-authored revisions. Markdown and PDF download
remain deferred.
