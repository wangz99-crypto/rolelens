# Human Review and Decision Memo Evaluation

Task 9C evaluates the deterministic simulated Human Review Ledger and
post-review Decision Memo Composer together. Task 9B unit tests establish
individual contract behavior, but they do not by themselves prove that a
fixed scenario trajectory preserves review completion, the exact source
plan, rejected work, blockers, Evidence lineage, information gaps, and
control notices through the final record.

The evaluation pack is fully synthetic and offline. It makes no provider,
model, credential, environment, timestamp, randomness, or network call.
Every plan and Evidence record is constructed through the production
Pydantic contracts, reviewed with `review_workflow_plan()`, and composed with
`compose_decision_memo()`. Comparisons are exact; there is no fuzzy matching,
keyword scoring, or semantic heuristic.

## Fixed scenarios

| Scenario | Invariant |
|---|---|
| `M1_complete_all_accept` | A complete healthy review retains accepted original action text, exact Evidence snapshots, the plan digest, reviewed status, and execution notice. |
| `M2_rejected_action_auditable` | A rejected role action is excluded from retained actions while its original text, note, risk lineage, and Evidence lineage remain auditable. |
| `M3_human_revision_requires_revalidation` | A human revision preserves original action and Evidence lineage, carries the exact revised text, and remains explicitly subject to revalidation. |
| `M4_blocker_persists_after_review` | An original blocking flag remains unresolved after review; blocked status takes precedence over revision revalidation. |
| `M5_semantic_gate_non_authoritative` | A semantic gate appears only as a probabilistic, non-authoritative review record with its exact decision, note, and semantic risk lineage. |
| `M6_missing_information_survives_rejection` | Missing information remains visible even when the associated role action is rejected. |
| `M7_incomplete_review_fails_closed` | A partial review session stays pending and `compose_decision_memo()` raises `DecisionMemoInputError` instead of returning a partial record. |
| `M8_empty_plan_acknowledged` | An empty plan produces a memo only after explicit written no-action acknowledgment. |

For every successful scenario the evaluator checks the memo status; exact
plan digest and step IDs; ordered retained, gate, rejected, blocker, and
revision IDs; review-gate decisions; revised action text; active Evidence
snapshot fields; missing-information mapping; deterministic and semantic
risk-code order; control notices; acknowledgment state; review completion;
and the fixed review and memo method identifiers. It also verifies that
accepted text is unchanged, revisions retain only original lineage, rejected
steps never re-enter retained actions, semantic gates never become actions
or factual verification, blockers derive from the original flags, and source
plans and review sessions remain unchanged.

Primary memo sections are checked field by field against both their source
`WorkflowStep` and matching `HumanReviewedStep`. Retained actions, rejected
steps, and semantic review gates must preserve their own owner, sequence,
status, blocker flag, Evidence IDs, risk codes, reviewer note, and applicable
decision fields. Aggregate Evidence IDs and risk-code unions are additional
checks, not substitutes for section-level snapshots; moving lineage from one
step to another therefore fails evaluation even when an aggregate is
unchanged.

The expected RoleLens result is **8/8**.

## Evaluation boundaries

These evaluation layers answer different questions:

- Semantic-risk model evaluation measures probabilistic candidate review
  behavior from a model provider.
- Deterministic Workflow Planner evaluation measures the fixed transformation
  of validated role and risk inputs into an evidence-linked plan.
- Deterministic Human Review and Memo evaluation measures whether explicit
  simulated judgments and the final structured record preserve the exact
  governed trajectory.

Task 9C covers only the third layer. It does not rerun semantic-risk model
evaluation or change Workflow Planner behavior.

## Polished action-summary baseline

The transparent baseline is a deterministic, non-LLM final-action summary.
It may record the supplied simulated decisions and list only accepted or
revised non-gate action text in plan order, omitting rejected actions from
that visible list. It intentionally has no plan digest, Evidence IDs,
risk-code lineage, semantic-gate section, rejected-step audit, unresolved
blocker state, missing-information section, revision revalidation metadata,
control notices, or explicit empty-plan acknowledgment record.

Evaluated against the same audit expectations, its expected result is
**0/8**. That score is not hardcoded. A private deterministic evaluator
derives each result from the exact audit properties absent from the baseline,
and sets success only when no failure reason remains. Different scenarios
therefore fail for different omissions: rejected-step or semantic-gate
history, blocker state, information gaps, revision revalidation metadata, or
explicit no-action acknowledgment. It is not a generic LLM baseline: no model
generates it, and it is designed only to isolate what is lost when a polished
final-action summary discards governance. A fluent answer without rejected
work, blockers, Evidence, or review history is not an auditable decision
record.

## Future of Work value

RoleLens keeps AI-assisted analysis, workflow coordination, human judgment,
and final reporting connected through inspectable provenance instead of
discarding governance at the final-summary stage.

## Limitations

- Eight fixtures validate approved V1 contracts, not arbitrary
  organizations.
- Scenario pass rate is not statistical proof.
- Plan templates are synthetic.
- Simulated review is not legal or operational approval.
- Fixtures must not be edited merely to hide failures.
- Markdown/PDF export and UI remain outside Task 9C.
