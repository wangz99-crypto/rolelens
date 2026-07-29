"""Deterministic post-review Decision Memo composition (Task 9B).

The composer projects an immutable WorkflowPlan and its complete simulated
HumanReviewSession into a structured, provenance-preserving DecisionMemo. It
does not call a model, authorize execution, clear blockers, or revalidate
human-authored revision text.
"""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import ValidationError

from app.human_review import workflow_plan_digest
from app.schemas import (
    DecisionMemo,
    DecisionMemoAction,
    DecisionMemoActionOrigin,
    DecisionMemoEvidenceItem,
    DecisionMemoMissingInformation,
    DecisionMemoRejectedStep,
    DecisionMemoReviewGate,
    DecisionMemoStatus,
    EvidenceObject,
    EvidenceStatus,
    HumanReviewedStep,
    HumanReviewDecision,
    HumanReviewSession,
    HumanReviewSessionStatus,
    WorkflowPlan,
    WorkflowStepKind,
)


class DecisionMemoInputError(ValueError):
    """Raised when post-review memo input is incomplete or inconsistent."""


def _build_evidence_registry(
    evidence_objects: Sequence[EvidenceObject],
) -> dict[str, EvidenceObject]:
    """Build an exact registry, tolerating duplicates and rejecting conflicts."""
    if not isinstance(evidence_objects, Sequence) or isinstance(
        evidence_objects,
        (str, bytes),
    ):
        raise DecisionMemoInputError(
            "evidence_objects must be a sequence of EvidenceObject values"
        )
    registry: dict[str, EvidenceObject] = {}
    for evidence in evidence_objects:
        if type(evidence) is not EvidenceObject:
            raise DecisionMemoInputError(
                "evidence_objects contains an unsupported value type"
            )
        try:
            validated_evidence = EvidenceObject.model_validate(
                evidence.model_dump()
            )
        except (ValidationError, TypeError, ValueError):
            raise DecisionMemoInputError(
                "evidence_objects contains an internally invalid "
                "EvidenceObject"
            ) from None
        existing = registry.get(validated_evidence.evidence_id)
        if existing is None:
            registry[validated_evidence.evidence_id] = validated_evidence
        elif existing != validated_evidence:
            raise DecisionMemoInputError(
                "conflicting EvidenceObject records share an evidence_id"
            )
    return registry


def _validate_review_binding(
    workflow_plan: WorkflowPlan,
    human_review_session: HumanReviewSession,
    registry: dict[str, EvidenceObject],
) -> dict[str, HumanReviewedStep]:
    """Validate complete review, exact plan snapshot, and active Evidence."""
    if (
        human_review_session.session_status
        != HumanReviewSessionStatus.complete
        or not human_review_session.human_review_complete
        or human_review_session.pending_step_ids
    ):
        raise DecisionMemoInputError(
            "human review must be complete with no pending steps"
        )
    if human_review_session.plan_digest != workflow_plan_digest(workflow_plan):
        raise DecisionMemoInputError(
            "human review plan digest does not match workflow_plan"
        )

    plan_step_ids = [step.step_id for step in workflow_plan.steps]
    if human_review_session.plan_step_ids != plan_step_ids:
        raise DecisionMemoInputError(
            "human review plan_step_ids do not match workflow_plan"
        )
    if len(human_review_session.reviewed_steps) != len(workflow_plan.steps):
        raise DecisionMemoInputError(
            "human review must cover every workflow step"
        )

    reviewed_by_id: dict[str, HumanReviewedStep] = {}
    for reviewed in human_review_session.reviewed_steps:
        if type(reviewed) is not HumanReviewedStep:
            raise DecisionMemoInputError(
                "human review contains an unsupported reviewed-step type"
            )
        reviewed_by_id[reviewed.step_id] = reviewed

    if set(reviewed_by_id) != set(plan_step_ids):
        raise DecisionMemoInputError(
            "human review records do not match workflow_plan steps"
        )

    snapshot_fields = (
        ("step_id", "step_id"),
        ("sequence", "sequence"),
        ("step_kind", "step_kind"),
        ("owner_role", "owner_role"),
        ("original_action", "action"),
        ("supporting_evidence_ids", "supporting_evidence_ids"),
        ("deterministic_risk_codes", "deterministic_risk_codes"),
        ("semantic_risk_codes", "semantic_risk_codes"),
        ("original_status", "status"),
        ("blocks_downstream", "blocks_downstream"),
    )
    referenced_evidence_ids: list[str] = []
    for step in workflow_plan.steps:
        reviewed = reviewed_by_id[step.step_id]
        for reviewed_field, plan_field in snapshot_fields:
            if getattr(reviewed, reviewed_field) != getattr(step, plan_field):
                raise DecisionMemoInputError(
                    "human review step snapshot does not match workflow_plan"
                )
        for evidence_id in reviewed.supporting_evidence_ids:
            if evidence_id not in referenced_evidence_ids:
                referenced_evidence_ids.append(evidence_id)

    for evidence_id in referenced_evidence_ids:
        evidence = registry.get(evidence_id)
        if evidence is None:
            raise DecisionMemoInputError(
                "a reviewed step references unknown evidence"
            )
        if evidence.status != EvidenceStatus.active:
            raise DecisionMemoInputError(
                "a reviewed step references inactive evidence"
            )

    if not workflow_plan.steps:
        if (
            not human_review_session.no_action_acknowledged
            or human_review_session.overall_note is None
        ):
            raise DecisionMemoInputError(
                "empty plans require acknowledged complete human review"
            )
    elif human_review_session.no_action_acknowledged:
        raise DecisionMemoInputError(
            "non-empty plans cannot use no-action acknowledgment"
        )
    return reviewed_by_id


def _validate_memo_compatibility(workflow_plan: WorkflowPlan) -> None:
    """Reject valid workflow steps that cannot satisfy memo provenance."""
    for step in workflow_plan.steps:
        if (
            step.step_kind == WorkflowStepKind.role_action
            and not step.supporting_evidence_ids
        ):
            raise DecisionMemoInputError(
                "workflow_plan contains a role_action without supporting "
                "evidence"
            )
        if step.step_kind == WorkflowStepKind.semantic_review_gate:
            if not step.supporting_evidence_ids:
                raise DecisionMemoInputError(
                    "workflow_plan contains a semantic_review_gate without "
                    "supporting evidence"
                )
            if not step.semantic_risk_codes:
                raise DecisionMemoInputError(
                    "workflow_plan contains a semantic_review_gate without "
                    "semantic risk codes"
                )


def _unique_in_order(values: Sequence[object]) -> list[object]:
    """Return distinct hashable values in first-seen order."""
    return list(dict.fromkeys(values))


def _review_summary(
    *,
    retained_count: int,
    rejected_count: int,
    revised_count: int,
    gate_count: int,
    blocker_count: int,
) -> str:
    """Return deterministic process-only review summary text."""
    return (
        f"Human review retained {retained_count} workflow items, rejected "
        f"{rejected_count}, revised {revised_count}, and documented "
        f"{gate_count} semantic review gates. {blocker_count} blocking "
        "prerequisites remain unresolved."
    )


def _compose_decision_memo(
    workflow_plan: WorkflowPlan,
    human_review_session: HumanReviewSession,
    evidence_objects: Sequence[EvidenceObject],
) -> DecisionMemo:
    """Validate inputs and compose one deterministic DecisionMemo."""
    if type(workflow_plan) is not WorkflowPlan:
        raise DecisionMemoInputError(
            "workflow_plan must be exactly a WorkflowPlan"
        )
    if type(human_review_session) is not HumanReviewSession:
        raise DecisionMemoInputError(
            "human_review_session must be exactly a HumanReviewSession"
        )
    try:
        WorkflowPlan.model_validate(workflow_plan.model_dump())
        HumanReviewSession.model_validate(
            human_review_session.model_dump()
        )
    except (ValidationError, TypeError, ValueError):
        raise DecisionMemoInputError(
            "workflow plan or human review session is internally invalid"
        ) from None
    registry = _build_evidence_registry(evidence_objects)
    reviewed_by_id = _validate_review_binding(
        workflow_plan,
        human_review_session,
        registry,
    )
    _validate_memo_compatibility(workflow_plan)

    retained_actions: list[DecisionMemoAction] = []
    review_gates: list[DecisionMemoReviewGate] = []
    rejected_steps: list[DecisionMemoRejectedStep] = []
    missing_information: list[DecisionMemoMissingInformation] = []
    evidence_ids: list[str] = []
    deterministic_codes: list[object] = []
    semantic_codes: list[object] = []
    unresolved_blocker_ids: list[str] = []

    for step in workflow_plan.steps:
        reviewed = reviewed_by_id[step.step_id]
        for evidence_id in step.supporting_evidence_ids:
            if evidence_id not in evidence_ids:
                evidence_ids.append(evidence_id)
        deterministic_codes.extend(step.deterministic_risk_codes)
        semantic_codes.extend(step.semantic_risk_codes)
        if step.blocks_downstream:
            unresolved_blocker_ids.append(step.step_id)

        if step.step_kind == WorkflowStepKind.semantic_review_gate:
            review_gates.append(
                DecisionMemoReviewGate(
                    step_id=step.step_id,
                    sequence=step.sequence,
                    owner_role=step.owner_role,
                    decision=reviewed.decision,
                    reviewer_note=reviewed.reviewer_note,
                    supporting_evidence_ids=list(
                        step.supporting_evidence_ids
                    ),
                    semantic_risk_codes=list(step.semantic_risk_codes),
                    original_status=step.status,
                    blocks_downstream=step.blocks_downstream,
                )
            )
        elif reviewed.decision == HumanReviewDecision.reject:
            rejected_steps.append(
                DecisionMemoRejectedStep(
                    step_id=step.step_id,
                    sequence=step.sequence,
                    step_kind=step.step_kind,
                    owner_role=step.owner_role,
                    original_action=step.action,
                    reviewer_note=reviewed.reviewer_note,
                    supporting_evidence_ids=list(
                        step.supporting_evidence_ids
                    ),
                    deterministic_risk_codes=list(
                        step.deterministic_risk_codes
                    ),
                    semantic_risk_codes=list(step.semantic_risk_codes),
                    original_status=step.status,
                    blocks_downstream=step.blocks_downstream,
                )
            )
        else:
            is_revision = (
                reviewed.decision == HumanReviewDecision.revise
            )
            retained_actions.append(
                DecisionMemoAction(
                    step_id=step.step_id,
                    sequence=step.sequence,
                    step_kind=step.step_kind,
                    owner_role=step.owner_role,
                    original_action=step.action,
                    action=reviewed.final_action,
                    action_origin=(
                        DecisionMemoActionOrigin.human_revision
                        if is_revision
                        else DecisionMemoActionOrigin.accepted_original
                    ),
                    reviewer_note=reviewed.reviewer_note,
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
                        reviewed.revision_requires_revalidation
                    ),
                )
            )

        if (
            step.step_kind == WorkflowStepKind.role_action
            and step.missing_information
        ):
            missing_information.append(
                DecisionMemoMissingInformation(
                    step_id=step.step_id,
                    owner_role=step.owner_role,
                    items=list(step.missing_information),
                )
            )

    evidence_items = [
        DecisionMemoEvidenceItem(
            evidence_id=registry[evidence_id].evidence_id,
            source_id=registry[evidence_id].source_id,
            evidence_scope=registry[evidence_id].evidence_scope,
            finding=registry[evidence_id].finding,
            confidence=registry[evidence_id].confidence,
            limitations=list(registry[evidence_id].limitations),
            decision_relevance=registry[evidence_id].decision_relevance,
        )
        for evidence_id in evidence_ids
    ]
    human_revision_ids = [
        action.step_id
        for action in retained_actions
        if action.action_origin == DecisionMemoActionOrigin.human_revision
    ]

    if not workflow_plan.steps:
        memo_status = DecisionMemoStatus.no_action_acknowledged
    elif unresolved_blocker_ids:
        memo_status = DecisionMemoStatus.blocked
    elif human_revision_ids:
        memo_status = DecisionMemoStatus.requires_revalidation
    else:
        memo_status = DecisionMemoStatus.reviewed

    control_notices = [
        "Simulated human review does not authorize execution."
    ]
    if unresolved_blocker_ids:
        control_notices.append(
            "Blocking prerequisites remain unresolved; accepting remediation "
            "does not mark them complete."
        )
    if human_revision_ids:
        control_notices.append(
            "Human-authored revisions require evidence and semantic "
            "revalidation."
        )
    if review_gates:
        control_notices.append(
            "Semantic review decisions remain probabilistic and "
            "non-authoritative."
        )
    if not workflow_plan.steps:
        control_notices.append(
            "No actionable workflow step was proposed."
        )

    return DecisionMemo(
        plan_digest=human_review_session.plan_digest,
        plan_step_ids=[step.step_id for step in workflow_plan.steps],
        memo_status=memo_status,
        review_summary=_review_summary(
            retained_count=len(retained_actions),
            rejected_count=len(rejected_steps),
            revised_count=len(human_revision_ids),
            gate_count=len(review_gates),
            blocker_count=len(unresolved_blocker_ids),
        ),
        evidence_items=evidence_items,
        retained_actions=retained_actions,
        review_gates=review_gates,
        rejected_steps=rejected_steps,
        missing_information=missing_information,
        deterministic_risk_codes=_unique_in_order(deterministic_codes),
        semantic_risk_codes=_unique_in_order(semantic_codes),
        unresolved_blocking_step_ids=unresolved_blocker_ids,
        human_revision_step_ids=human_revision_ids,
        overall_review_note=human_review_session.overall_note,
        no_action_acknowledged=(
            human_review_session.no_action_acknowledged
        ),
        human_review_complete=True,
        control_notices=control_notices,
        review_method="simulated_human_review_v1",
        memo_method="deterministic_post_review_v1",
    )


def compose_decision_memo(
    workflow_plan: WorkflowPlan,
    human_review_session: HumanReviewSession,
    evidence_objects: Sequence[EvidenceObject],
) -> DecisionMemo:
    """Compose a memo while normalizing all projection validation failures."""
    try:
        return _compose_decision_memo(
            workflow_plan,
            human_review_session,
            evidence_objects,
        )
    except DecisionMemoInputError:
        raise
    except (ValidationError, TypeError, ValueError):
        raise DecisionMemoInputError(
            "validated inputs could not be composed into a DecisionMemo"
        ) from None
