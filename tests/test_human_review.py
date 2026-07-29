"""Offline tests for the deterministic simulated Human Review Ledger."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from app.human_review import (
    HumanReviewInputError,
    review_workflow_plan,
    workflow_plan_digest,
)
from app.schemas import (
    HumanReviewedStep,
    HumanReviewDecision,
    HumanReviewSession,
    HumanReviewSessionStatus,
    HumanReviewStepInput,
    RiskCode,
    RoleKey,
    SemanticRiskCode,
    WorkflowPlan,
    WorkflowPlanStatus,
    WorkflowStep,
    WorkflowStepKind,
    WorkflowStepStatus,
)


_EVIDENCE_ONE = "ev-review-000000000001"
_EVIDENCE_TWO = "ev-review-000000000002"
_EVIDENCE_THREE = "ev-review-000000000003"


class _HumanReviewStepInputSubclass(HumanReviewStepInput):
    """Unsupported subclass used to prove exact-type enforcement."""


def _review_plan() -> WorkflowPlan:
    """Build a three-step plan with blocker, semantic gate, and role action."""
    steps = [
        WorkflowStep(
            step_id="wf-001",
            sequence=1,
            step_kind=WorkflowStepKind.deterministic_risk_resolution,
            owner_role=RoleKey.data_engineer,
            action="Validate customer identifiers.",
            supporting_evidence_ids=[_EVIDENCE_ONE],
            dependency_step_ids=[],
            dependency_notes=["Customer identifiers are not validated."],
            missing_information=[],
            deterministic_risk_codes=[
                RiskCode.action_without_internal_evidence
            ],
            semantic_risk_codes=[],
            review_questions=[],
            status=WorkflowStepStatus.pending_human_review,
            blocks_downstream=True,
            human_review_required=True,
        ),
        WorkflowStep(
            step_id="wf-002",
            sequence=2,
            step_kind=WorkflowStepKind.semantic_review_gate,
            owner_role=RoleKey.executive,
            action=(
                "Review semantic risk candidates for executive before "
                "downstream action."
            ),
            supporting_evidence_ids=[_EVIDENCE_TWO],
            dependency_step_ids=["wf-001"],
            dependency_notes=[],
            missing_information=[],
            deterministic_risk_codes=[],
            semantic_risk_codes=[
                SemanticRiskCode.citation_claim_mismatch
            ],
            review_questions=[
                "Does the evidence support the executive conclusion?"
            ],
            status=WorkflowStepStatus.pending_human_review,
            blocks_downstream=False,
            human_review_required=True,
        ),
        WorkflowStep(
            step_id="wf-003",
            sequence=3,
            step_kind=WorkflowStepKind.role_action,
            owner_role=RoleKey.executive,
            action="Approve the bounded retention priority.",
            supporting_evidence_ids=[_EVIDENCE_THREE],
            dependency_step_ids=["wf-001", "wf-002"],
            dependency_notes=[],
            missing_information=["Validated customer identifiers."],
            deterministic_risk_codes=[
                RiskCode.action_without_internal_evidence
            ],
            semantic_risk_codes=[
                SemanticRiskCode.citation_claim_mismatch
            ],
            review_questions=[],
            status=WorkflowStepStatus.blocked,
            blocks_downstream=False,
            human_review_required=True,
        ),
    ]
    return WorkflowPlan(
        steps=steps,
        plan_status=WorkflowPlanStatus.blocked,
        included_role_keys=[
            RoleKey.executive,
            RoleKey.data_engineer,
        ],
        blocking_step_ids=["wf-001"],
        human_review_required=True,
        planning_method="deterministic_v1",
    )


def _empty_plan() -> WorkflowPlan:
    """Build an explicit no-action plan."""
    return WorkflowPlan(
        steps=[],
        plan_status=WorkflowPlanStatus.no_actionable_steps,
        included_role_keys=[RoleKey.executive],
        blocking_step_ids=[],
        human_review_required=True,
        planning_method="deterministic_v1",
    )


def _mutate_plan(
    plan: WorkflowPlan,
    sequence: int,
    *,
    plan_updates: dict[str, Any] | None = None,
    **step_updates: Any,
) -> WorkflowPlan:
    """Rebuild a changed plan through full schema validation."""
    steps = list(plan.steps)
    payload = steps[sequence - 1].model_dump()
    payload.update(step_updates)
    steps[sequence - 1] = WorkflowStep.model_validate(payload)
    plan_payload = plan.model_dump(exclude={"steps"})
    plan_payload["steps"] = [step.model_dump() for step in steps]
    if plan_updates:
        plan_payload.update(plan_updates)
    return WorkflowPlan.model_validate(plan_payload)


def _reviewed_step_payload(**updates: Any) -> dict[str, Any]:
    """Return one valid accepted reviewed-step payload."""
    payload: dict[str, Any] = {
        "step_id": "wf-001",
        "sequence": 1,
        "step_kind": WorkflowStepKind.role_action,
        "owner_role": RoleKey.executive,
        "original_action": "Review the bounded decision.",
        "final_action": "Review the bounded decision.",
        "decision": HumanReviewDecision.accept,
        "reviewer_note": None,
        "supporting_evidence_ids": [_EVIDENCE_ONE],
        "deterministic_risk_codes": [],
        "semantic_risk_codes": [],
        "original_status": WorkflowStepStatus.ready,
        "blocks_downstream": False,
        "revision_requires_revalidation": False,
    }
    payload.update(updates)
    return payload


def test_review_schemas_reject_invalid_combinations_and_derived_state() -> None:
    """All three review schemas reject malformed or inconsistent records."""
    invalid_inputs = [
        {
            "decision": HumanReviewDecision.accept,
            "revised_action": "Unexpected revision.",
        },
        {"decision": HumanReviewDecision.reject},
        {
            "decision": HumanReviewDecision.reject,
            "reviewer_note": " ",
        },
        {
            "decision": HumanReviewDecision.revise,
            "reviewer_note": "Explain revision.",
        },
        {
            "decision": HumanReviewDecision.accept,
            "unexpected": True,
        },
    ]
    for payload in invalid_inputs:
        with pytest.raises(ValidationError):
            HumanReviewStepInput.model_validate(payload)

    invalid_reviewed_steps = [
        _reviewed_step_payload(step_id="step-001"),
        _reviewed_step_payload(
            decision=HumanReviewDecision.reject,
            final_action=None,
            reviewer_note=None,
        ),
        _reviewed_step_payload(
            decision=HumanReviewDecision.revise,
            final_action="Review the bounded decision.",
            reviewer_note="Revision note.",
            revision_requires_revalidation=True,
        ),
        _reviewed_step_payload(
            step_kind=WorkflowStepKind.semantic_review_gate,
            reviewer_note=None,
        ),
        _reviewed_step_payload(
            supporting_evidence_ids=[_EVIDENCE_ONE, _EVIDENCE_ONE]
        ),
    ]
    for payload in invalid_reviewed_steps:
        with pytest.raises(ValidationError):
            HumanReviewedStep.model_validate(payload)

    plan = _review_plan()
    pending = review_workflow_plan(
        plan,
        {"wf-001": HumanReviewStepInput(decision="accept")},
    )
    invalid_sessions = [
        {**pending.model_dump(), "plan_digest": "not-a-digest"},
        {**pending.model_dump(), "accepted_step_ids": []},
        {
            **pending.model_dump(),
            "session_status": HumanReviewSessionStatus.complete,
            "human_review_complete": True,
        },
        {
            **pending.model_dump(),
            "plan_step_ids": ["wf-001", "wf-001", "wf-003"],
        },
        {**pending.model_dump(), "unexpected": True},
    ]
    for payload in invalid_sessions:
        with pytest.raises(ValidationError):
            HumanReviewSession.model_validate(payload)


def test_plan_digest_is_stable_and_changes_for_meaningful_plan_changes() -> None:
    """Canonical digests cover action, DAG, evidence, risks, status, and blockers."""
    plan = _review_plan()
    equal_plan = WorkflowPlan.model_validate(plan.model_dump())
    baseline = workflow_plan_digest(plan)
    changed_plans = [
        _mutate_plan(
            plan,
            3,
            action="Approve a different bounded priority.",
        ),
        _mutate_plan(
            plan,
            3,
            dependency_step_ids=["wf-001"],
        ),
        _mutate_plan(
            plan,
            3,
            supporting_evidence_ids=[_EVIDENCE_ONE],
        ),
        _mutate_plan(
            plan,
            3,
            deterministic_risk_codes=[RiskCode.assumption_not_declared],
        ),
        _mutate_plan(
            plan,
            3,
            status=WorkflowStepStatus.pending_human_review,
        ),
        _mutate_plan(
            plan,
            1,
            blocks_downstream=False,
            plan_updates={
                "blocking_step_ids": [],
                "plan_status": WorkflowPlanStatus.ready_for_human_review,
            },
        ),
    ]

    assert workflow_plan_digest(equal_plan) == baseline
    assert len(baseline) == 64
    assert all(
        workflow_plan_digest(changed) != baseline
        for changed in changed_plans
    )


def test_partial_review_preserves_plan_order_and_pending_partition() -> None:
    """Reviewed and pending records follow plan order, not mapping order."""
    plan = _review_plan()
    decisions = {
        "wf-003": HumanReviewStepInput(
            decision="reject",
            reviewer_note="Exclude the downstream action.",
        ),
        "wf-001": HumanReviewStepInput(decision="accept"),
    }

    session = review_workflow_plan(plan, decisions)

    assert [step.step_id for step in session.reviewed_steps] == [
        "wf-001",
        "wf-003",
    ]
    assert session.pending_step_ids == ["wf-002"]
    assert session.accepted_step_ids == ["wf-001"]
    assert session.rejected_step_ids == ["wf-003"]
    assert session.revised_step_ids == []
    assert session.session_status is HumanReviewSessionStatus.pending
    assert session.human_review_complete is False


def test_complete_all_accept_review_preserves_original_actions() -> None:
    """Explicit acceptance of every step creates a complete bound session."""
    plan = _review_plan()
    decisions = {
        "wf-001": HumanReviewStepInput(decision="accept"),
        "wf-002": HumanReviewStepInput(
            decision="accept",
            reviewer_note="Semantic concern reviewed and retained.",
        ),
        "wf-003": HumanReviewStepInput(decision="accept"),
    }

    session = review_workflow_plan(plan, decisions)

    assert session.session_status is HumanReviewSessionStatus.complete
    assert session.human_review_complete is True
    assert session.pending_step_ids == []
    assert session.accepted_step_ids == [
        "wf-001",
        "wf-002",
        "wf-003",
    ]
    assert all(
        reviewed.final_action == plan.steps[index].action
        for index, reviewed in enumerate(session.reviewed_steps)
    )
    assert all(
        not reviewed.revision_requires_revalidation
        for reviewed in session.reviewed_steps
    )
    assert session.plan_digest == workflow_plan_digest(plan)


def test_reject_requires_note_and_preserves_evidence_and_risk_lineage() -> None:
    """Reject excludes the action while retaining its exact source snapshot."""
    with pytest.raises(ValidationError):
        HumanReviewStepInput(decision="reject")
    plan = _review_plan()

    session = review_workflow_plan(
        plan,
        {
            "wf-003": HumanReviewStepInput(
                decision="reject",
                reviewer_note="Exclude this action from the later memo.",
            )
        },
    )
    reviewed = session.reviewed_steps[0]

    assert reviewed.final_action is None
    assert reviewed.supporting_evidence_ids == [_EVIDENCE_THREE]
    assert reviewed.deterministic_risk_codes == [
        RiskCode.action_without_internal_evidence
    ]
    assert reviewed.semantic_risk_codes == [
        SemanticRiskCode.citation_claim_mismatch
    ]
    assert session.rejected_step_ids == ["wf-003"]


def test_revise_requires_new_text_and_marks_unvalidated_provenance() -> None:
    """Human revisions remain explicit and require later revalidation."""
    with pytest.raises(ValidationError):
        HumanReviewStepInput(
            decision="revise",
            reviewer_note="Revise it.",
            revised_action=" ",
        )
    plan = _review_plan()
    with pytest.raises(HumanReviewInputError):
        review_workflow_plan(
            plan,
            {
                "wf-003": HumanReviewStepInput(
                    decision="revise",
                    reviewer_note="No actual change.",
                    revised_action=plan.steps[2].action,
                )
            },
        )

    session = review_workflow_plan(
        plan,
        {
            "wf-001": HumanReviewStepInput(
                decision="revise",
                reviewer_note="Use a narrower validation action.",
                revised_action="Validate the bounded identifier subset.",
            ),
            "wf-003": HumanReviewStepInput(
                decision="revise",
                reviewer_note="Keep the proposed action conditional.",
                revised_action="Draft a conditional retention priority.",
            ),
        },
    )

    assert session.revised_step_ids == ["wf-001", "wf-003"]
    assert all(
        step.revision_requires_revalidation
        for step in session.reviewed_steps
    )
    assert session.reviewed_steps[0].final_action == (
        "Validate the bounded identifier subset."
    )
    with pytest.raises(HumanReviewInputError):
        review_workflow_plan(
            plan,
            {
                "wf-002": HumanReviewStepInput(
                    decision="revise",
                    reviewer_note="A gate cannot be rewritten.",
                    revised_action="Rewrite the semantic gate.",
                )
            },
        )


def test_semantic_gate_requires_note_and_allows_explicit_accept_or_reject() -> None:
    """A documented gate decision stays nonblocking and cannot imply execution."""
    plan = _review_plan()
    with pytest.raises(HumanReviewInputError):
        review_workflow_plan(
            plan,
            {"wf-002": HumanReviewStepInput(decision="accept")},
        )

    accepted = review_workflow_plan(
        plan,
        {
            "wf-002": HumanReviewStepInput(
                decision="accept",
                reviewer_note="Reviewed the probabilistic concern.",
            )
        },
    )
    rejected = review_workflow_plan(
        plan,
        {
            "wf-002": HumanReviewStepInput(
                decision="reject",
                reviewer_note="Exclude the gated proposal.",
            )
        },
    )

    assert accepted.reviewed_steps[0].decision is HumanReviewDecision.accept
    assert accepted.reviewed_steps[0].blocks_downstream is False
    assert rejected.reviewed_steps[0].decision is HumanReviewDecision.reject
    assert rejected.reviewed_steps[0].final_action is None
    assert rejected.reviewed_steps[0].blocks_downstream is False


def test_accepting_blocked_work_does_not_clear_blocker_or_original_status() -> None:
    """Acceptance snapshots blocker facts without resolving or rewriting them."""
    plan = _review_plan()

    session = review_workflow_plan(
        plan,
        {
            "wf-001": HumanReviewStepInput(decision="accept"),
            "wf-003": HumanReviewStepInput(decision="accept"),
        },
    )
    resolution, role_action = session.reviewed_steps

    assert resolution.blocks_downstream is True
    assert (
        resolution.original_status
        is WorkflowStepStatus.pending_human_review
    )
    assert role_action.blocks_downstream is False
    assert role_action.original_status is WorkflowStepStatus.blocked
    assert plan.blocking_step_ids == ["wf-001"]
    assert plan.plan_status is WorkflowPlanStatus.blocked


def test_empty_plan_requires_explicit_acknowledgment_and_overall_note() -> None:
    """No-action plans remain pending until a human explicitly acknowledges them."""
    plan = _empty_plan()

    pending = review_workflow_plan(plan, {})
    assert pending.session_status is HumanReviewSessionStatus.pending
    assert pending.human_review_complete is False
    assert pending.no_action_acknowledged is False
    assert pending.plan_step_ids == []

    with pytest.raises(HumanReviewInputError):
        review_workflow_plan(
            plan,
            {},
            no_action_acknowledged=True,
        )
    complete = review_workflow_plan(
        plan,
        {},
        no_action_acknowledged=True,
        overall_note="Reviewed and acknowledged that no action is proposed.",
    )
    assert complete.session_status is HumanReviewSessionStatus.complete
    assert complete.human_review_complete is True
    assert complete.no_action_acknowledged is True
    assert complete.reviewed_steps == []


def test_fail_closed_inputs_are_deterministic_and_never_mutate_plan() -> None:
    """Invalid mappings fail safely; equal valid calls are stable and immutable."""
    plan = _review_plan()
    original = plan.model_dump()
    valid_decisions = {
        "wf-001": HumanReviewStepInput(decision="accept"),
    }
    invalid_calls = [
        lambda: review_workflow_plan(
            plan,
            {"wf-999": HumanReviewStepInput(decision="accept")},
        ),
        lambda: review_workflow_plan(plan, {"wf-001": object()}),
        lambda: review_workflow_plan(
            plan,
            {1: HumanReviewStepInput(decision="accept")},
        ),
        lambda: review_workflow_plan(plan, []),
        lambda: review_workflow_plan(
            plan,
            {
                "wf-001": _HumanReviewStepInputSubclass(
                    decision="accept"
                )
            },
        ),
        lambda: review_workflow_plan(
            plan,
            {},
            no_action_acknowledged=1,
        ),
        lambda: review_workflow_plan(plan, {}, overall_note=" "),
    ]
    for call in invalid_calls:
        with pytest.raises(HumanReviewInputError):
            call()

    first = review_workflow_plan(plan, valid_decisions)
    second = review_workflow_plan(plan, dict(valid_decisions))

    assert first == second
    assert plan.model_dump() == original
    with pytest.raises(HumanReviewInputError):
        workflow_plan_digest(object())
