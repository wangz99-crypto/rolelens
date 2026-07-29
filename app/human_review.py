"""Deterministic simulated human review of an immutable WorkflowPlan.

Task 9A records caller-supplied memo-review decisions. It does not execute
workflow steps, clear blockers, grant approval authority, or validate
human-authored revision text.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping

from app.schemas import (
    HumanReviewedStep,
    HumanReviewDecision,
    HumanReviewSession,
    HumanReviewSessionStatus,
    HumanReviewStepInput,
    WorkflowPlan,
    WorkflowStepKind,
)


class HumanReviewInputError(ValueError):
    """Raised when simulated human-review input is invalid."""


def workflow_plan_digest(workflow_plan: WorkflowPlan) -> str:
    """Return the canonical SHA-256 digest of an exact WorkflowPlan."""
    if type(workflow_plan) is not WorkflowPlan:
        raise HumanReviewInputError(
            "workflow_plan must be exactly a WorkflowPlan"
        )
    try:
        canonical_json = json.dumps(
            workflow_plan.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            allow_nan=False,
            separators=(",", ":"),
        )
    except (TypeError, ValueError):
        raise HumanReviewInputError(
            "workflow_plan could not be serialized canonically"
        ) from None
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


def _validate_review_inputs(
    workflow_plan: WorkflowPlan,
    decisions: Mapping[str, HumanReviewStepInput],
    *,
    no_action_acknowledged: bool,
    overall_note: str | None,
) -> dict[str, HumanReviewStepInput]:
    """Validate and normalize caller decisions without inventing any."""
    if type(workflow_plan) is not WorkflowPlan:
        raise HumanReviewInputError(
            "workflow_plan must be exactly a WorkflowPlan"
        )
    if not isinstance(decisions, Mapping):
        raise HumanReviewInputError("decisions must be a mapping")
    if type(no_action_acknowledged) is not bool:
        raise HumanReviewInputError(
            "no_action_acknowledged must be a bool"
        )
    if overall_note is not None and (
        not isinstance(overall_note, str)
        or not overall_note
        or not overall_note.strip()
    ):
        raise HumanReviewInputError(
            "overall_note must be non-blank when supplied"
        )

    known_steps = {step.step_id: step for step in workflow_plan.steps}
    normalized: dict[str, HumanReviewStepInput] = {}
    for step_id, decision in decisions.items():
        if type(step_id) is not str:
            raise HumanReviewInputError(
                "decision mapping keys must be strings"
            )
        if step_id not in known_steps:
            raise HumanReviewInputError(
                "decision mapping contains an unknown WorkflowStep ID"
            )
        if type(decision) is not HumanReviewStepInput:
            raise HumanReviewInputError(
                "decision mapping values must be exactly "
                "HumanReviewStepInput"
            )
        step = known_steps[step_id]
        if step.step_kind == WorkflowStepKind.semantic_review_gate:
            if decision.decision == HumanReviewDecision.revise:
                raise HumanReviewInputError(
                    "semantic review gates cannot be revised"
                )
            if decision.reviewer_note is None:
                raise HumanReviewInputError(
                    "semantic review gate decisions require a reviewer note"
                )
        if (
            decision.decision == HumanReviewDecision.revise
            and decision.revised_action == step.action
        ):
            raise HumanReviewInputError(
                "a revised action must differ from the original action"
            )
        normalized[step_id] = decision

    if workflow_plan.steps:
        if no_action_acknowledged:
            raise HumanReviewInputError(
                "no-action acknowledgment is valid only for an empty plan"
            )
    elif no_action_acknowledged and overall_note is None:
        raise HumanReviewInputError(
            "acknowledging an empty plan requires an overall note"
        )
    return normalized


def review_workflow_plan(
    workflow_plan: WorkflowPlan,
    decisions: Mapping[str, HumanReviewStepInput],
    *,
    no_action_acknowledged: bool = False,
    overall_note: str | None = None,
) -> HumanReviewSession:
    """Record explicit simulated human decisions in WorkflowPlan order."""
    normalized = _validate_review_inputs(
        workflow_plan,
        decisions,
        no_action_acknowledged=no_action_acknowledged,
        overall_note=overall_note,
    )

    reviewed_steps: list[HumanReviewedStep] = []
    pending_step_ids: list[str] = []
    for step in workflow_plan.steps:
        decision = normalized.get(step.step_id)
        if decision is None:
            pending_step_ids.append(step.step_id)
            continue

        if decision.decision == HumanReviewDecision.accept:
            final_action = step.action
            revision_requires_revalidation = False
        elif decision.decision == HumanReviewDecision.reject:
            final_action = None
            revision_requires_revalidation = False
        else:
            final_action = decision.revised_action
            revision_requires_revalidation = True

        reviewed_steps.append(
            HumanReviewedStep(
                step_id=step.step_id,
                sequence=step.sequence,
                step_kind=step.step_kind,
                owner_role=step.owner_role,
                original_action=step.action,
                final_action=final_action,
                decision=decision.decision,
                reviewer_note=decision.reviewer_note,
                supporting_evidence_ids=list(
                    step.supporting_evidence_ids
                ),
                deterministic_risk_codes=list(
                    step.deterministic_risk_codes
                ),
                semantic_risk_codes=list(step.semantic_risk_codes),
                original_status=step.status,
                blocks_downstream=step.blocks_downstream,
                revision_requires_revalidation=(
                    revision_requires_revalidation
                ),
            )
        )

    accepted_step_ids = [
        step.step_id
        for step in reviewed_steps
        if step.decision == HumanReviewDecision.accept
    ]
    rejected_step_ids = [
        step.step_id
        for step in reviewed_steps
        if step.decision == HumanReviewDecision.reject
    ]
    revised_step_ids = [
        step.step_id
        for step in reviewed_steps
        if step.decision == HumanReviewDecision.revise
    ]

    if workflow_plan.steps:
        session_status = (
            HumanReviewSessionStatus.pending
            if pending_step_ids
            else HumanReviewSessionStatus.complete
        )
    else:
        session_status = (
            HumanReviewSessionStatus.complete
            if no_action_acknowledged
            else HumanReviewSessionStatus.pending
        )

    return HumanReviewSession(
        plan_digest=workflow_plan_digest(workflow_plan),
        plan_step_ids=[step.step_id for step in workflow_plan.steps],
        reviewed_steps=reviewed_steps,
        pending_step_ids=pending_step_ids,
        accepted_step_ids=accepted_step_ids,
        rejected_step_ids=rejected_step_ids,
        revised_step_ids=revised_step_ids,
        session_status=session_status,
        no_action_acknowledged=no_action_acknowledged,
        overall_note=overall_note,
        human_review_complete=(
            session_status == HumanReviewSessionStatus.complete
        ),
        review_method="simulated_human_review_v1",
    )
