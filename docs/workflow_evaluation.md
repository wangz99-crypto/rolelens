# Workflow Planner Evaluation

Task 8B evaluates the deterministic Task 8A Workflow Planner as a business
coordination system. Unit tests remain necessary for schema and function-level
behavior, but they do not by themselves show that blockers, review gates,
failed roles, and handoffs work together across a complete scenario. This
fixed pack evaluates those interactions end to end with exact comparisons.

The harness is fully offline and deterministic. It loads synthetic fixtures,
constructs typed upstream pipeline outputs, calls the existing planner, and
compares the resulting plan with an approved bounded expectation. It makes no
provider, model, credential, or network call.

## Scenario pack

| ID | Scenario | Business invariant |
| --- | --- | --- |
| W1 | Healthy full sequence | Every successful role action follows the fixed Data Engineer → Data Analyst → Executive → Sales / Marketing → Project Manager prerequisite chain. |
| W2 | Data Engineer blocker | Unvalidated data creates an explicit blocking resolution step and prevents every dependent role action from bypassing it. |
| W3 | Semantic review gate | Review-required and uncertain candidates consolidate into one nonblocking gate; `likely_supported` creates no gate. |
| W4 | Nonblocking deterministic review | Required human review propagates a pending status without being mislabeled as a blocker. |
| W5 | Failed roles | `InsufficientEvidence` and `RoleGenerationFailure` receive no fabricated role actions; only exact risk-required actions remain. |
| W6 | Duplicate resolution grouping | Findings with exactly equal required actions form one step while preserving first-seen codes and messages. |
| W7 | Dependency note | Free-text dependency prose remains visible only as a note and cannot alter, remove, or reorder DAG edges. |
| W8 | No actionable steps | Grounded views without next actions produce an explicit `no_actionable_steps` plan with human review still required. |

The evaluator checks exact plan status, ordered `step_kind:role_key`
signatures, dependency and blocker sequences, included roles, action statuses,
semantic-gate roles, and required action absence. It also checks source
preservation:

- role actions exactly equal fixture `RoleView.next_action` values;
- supporting Evidence IDs exactly preserve their source lineage across role
  actions, grouped deterministic resolutions, and semantic review gates;
- deterministic actions exactly equal fixture
  `RiskFinding.required_action` values;
- exact duplicate required actions group once, preserving first-seen risk
  codes and messages;
- deterministic resolution status, blocker state, and human-review state are
  derived exactly from their grouped source findings;
- downstream role actions preserve first-seen deterministic and qualifying
  semantic risk-code lineage;
- semantic gates contain only qualifying codes and questions in first-seen
  order;
- `likely_supported` semantic evidence and codes remain excluded from gates
  and downstream role-action risk lineage;
- semantic gates never block;
- dependency text remains only on its role action as a note and never becomes
  executable text;
- missing information is copied exactly; and
- every plan retains the V1 human-review requirement.

No fuzzy matching, keyword heuristic, natural-language dependency parsing, or
automatic remediation is used.

## Deterministic workflow evaluation versus semantic-risk evaluation

This pack evaluates deterministic coordination rules after semantic review
has already produced typed candidates. It can prove that a qualifying
candidate becomes the correct nonblocking gate and that a `likely_supported`
candidate does not. It does not measure whether a probabilistic semantic
reviewer detected the right concern; that is covered by the separate
semantic-risk evaluation and its live evaluation protocol.

The expected RoleLens result is eight of eight scenarios passing.

## Flat action-list baseline

The comparison baseline is explicitly non-LLM. It lists only successful
`RoleView.next_action` values in workflow role order. It creates no
risk-resolution steps, semantic gates, dependency edges, or blocker
propagation, and it marks every listed action `ready`.

The baseline is evaluated against the same approved expectations and is
expected to pass only W8. Its deliberate simplicity makes the comparison
transparent:

> An ordered action list is not a governed workflow.

It must not be described as a generic LLM baseline and it fabricates no risk
detections or model output.

## Future of Work value

RoleLens turns role outputs into inspectable coordination: evidence-bound
actions, explicit blockers, human-review gates, and visible handoffs. The
evaluation demonstrates the difference between that governed sequence and an
ungoverned list of recommendations.

## Limitations and fixture discipline

- These fixtures validate approved V1 rules, not arbitrary enterprise
  workflows.
- Fixed role ordering is intentionally conservative.
- An eight-scenario pass rate is not statistical proof of general reliability.
- Exact fixtures must not be edited merely to hide planner failures. A planner
  mismatch should be investigated and independently reviewed before any
  expectation change.
