"""Tests for deterministic, fail-closed workflow planning."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest
from pydantic import ValidationError

from app.risk_checker import RiskReviewResult
from app.role_engine import InsufficientEvidence, RoleGenerationFailure, RoleOutcome
from app.schemas import (
    EvidenceObject,
    EvidenceReference,
    EvidenceScope,
    EvidenceStatus,
    GroundedFinding,
    RiskCode,
    RiskFinding,
    RiskSeverity,
    RoleKey,
    RoleView,
    SemanticReviewDisposition,
    SemanticRiskCandidate,
    SemanticRiskCode,
    SemanticRiskReviewResult,
    SourceFormat,
    TabularSourceLocator,
    WorkflowPlan,
    WorkflowPlanStatus,
    WorkflowStep,
    WorkflowStepKind,
    WorkflowStepStatus,
)
from app.workflow_planner import WorkflowPlanningInputError, plan_workflow


_CANONICAL_ROLES = (
    RoleKey.executive,
    RoleKey.data_analyst,
    RoleKey.data_engineer,
    RoleKey.sales_marketing,
    RoleKey.project_manager,
)
_WORKFLOW_ROLES = (
    RoleKey.data_engineer,
    RoleKey.data_analyst,
    RoleKey.executive,
    RoleKey.sales_marketing,
    RoleKey.project_manager,
)
_ROLE_NUMBER = {role: index for index, role in enumerate(_CANONICAL_ROLES, 1)}


def _evidence_id(role_key: RoleKey) -> str:
    """Return a stable evidence ID for one role."""
    abbreviations = {
        RoleKey.executive: "wfexec",
        RoleKey.data_analyst: "wfanalyst",
        RoleKey.data_engineer: "wfengineer",
        RoleKey.sales_marketing: "wfsales",
        RoleKey.project_manager: "wfpm",
    }
    return f"ev-{abbreviations[role_key]}-{_ROLE_NUMBER[role_key]:012x}"


def _evidence(
    role_key: RoleKey,
    *,
    evidence_id: str | None = None,
    status: EvidenceStatus = EvidenceStatus.active,
) -> EvidenceObject:
    """Build one valid EvidenceObject."""
    number = _ROLE_NUMBER[role_key]
    return EvidenceObject(
        evidence_id=evidence_id or _evidence_id(role_key),
        source_id=f"src-workflow-{number:012x}",
        source_format=SourceFormat.csv,
        source_locator=TabularSourceLocator(
            sheet_name=None,
            columns=["metric"],
            row_range=(number, number),
        ),
        evidence_type="workflow_test_observation",
        evidence_scope=EvidenceScope.internal_observation,
        extraction_method="deterministic",
        finding=f"Finding for {role_key.value}.",
        supporting_evidence=f"Metric value {number}.",
        confidence="high",
        limitations=["Synthetic workflow test evidence."],
        relevant_roles=[role_key.value],
        decision_relevance=f"Supports {role_key.value} workflow testing.",
        created_by="evidence_builder",
        status=status,
        invalidated_reason=(
            "Superseded test evidence."
            if status is EvidenceStatus.invalidated
            else None
        ),
        identity_digest=f"{number:x}" * 64,
    )


def _view(
    role_key: RoleKey,
    *,
    next_action: str | None = None,
    dependency: str | None = None,
    human_review_required: bool = False,
) -> RoleView:
    """Build one successful role view."""
    return RoleView(
        role_key=role_key,
        role_concern=f"Concern for {role_key.value}.",
        key_findings=[
            GroundedFinding(
                claim=f"Grounded claim for {role_key.value}.",
                evidence_references=[
                    EvidenceReference(evidence_id=_evidence_id(role_key))
                ],
                confidence="high",
            )
        ],
        risks_or_assumptions=[],
        next_action=next_action,
        dependency=dependency,
        missing_information=[f"Missing input for {role_key.value}."],
        human_review_required=human_review_required,
    )


def _outcomes(
    successful_views: Mapping[RoleKey, RoleView],
) -> dict[RoleKey, RoleOutcome]:
    """Fill the canonical five-role mapping around successful views."""
    return {
        role_key: successful_views.get(
            role_key,
            InsufficientEvidence(
                role_key=role_key,
                reason=f"No evidence for {role_key.value}.",
            ),
        )
        for role_key in _CANONICAL_ROLES
    }


def _risk_result(findings: list[RiskFinding] | None = None) -> RiskReviewResult:
    """Build a valid deterministic risk result."""
    approved = findings or []
    return RiskReviewResult(
        reviewed_role_keys=list(_CANONICAL_ROLES),
        findings=approved,
        has_blocking_risks=any(item.blocks_downstream for item in approved),
        human_review_required=any(
            item.requires_human_review for item in approved
        ),
    )


def _semantic_result(
    role_outcomes: Mapping[RoleKey, RoleOutcome],
    candidates: list[SemanticRiskCandidate] | None = None,
) -> SemanticRiskReviewResult:
    """Build a valid semantic review over successful views only."""
    approved = candidates or []
    reviewed_roles = [
        role_key
        for role_key in _CANONICAL_ROLES
        if isinstance(role_outcomes[role_key], RoleView)
    ]
    return SemanticRiskReviewResult(
        reviewed_role_keys=reviewed_roles,
        candidates=approved,
        human_review_required=any(
            item.disposition
            in {
            SemanticReviewDisposition.needs_human_review,
            SemanticReviewDisposition.reviewer_uncertain,
            }
            for item in approved
        ),
        reviewer_model=None,
    )


def _finding(
    role_key: RoleKey,
    *,
    risk_code: RiskCode = RiskCode.assumption_not_declared,
    required_action: str = "Resolve the deterministic risk.",
    blocks_downstream: bool = False,
    requires_human_review: bool = True,
    claim_index: int | None = 0,
) -> RiskFinding:
    """Build one deterministic risk finding."""
    return RiskFinding(
        risk_code=risk_code,
        severity=RiskSeverity.high,
        role_key=role_key,
        claim_index=claim_index,
        evidence_ids=[_evidence_id(role_key)],
        message=f"Risk message for {role_key.value}.",
        required_action=required_action,
        blocks_downstream=blocks_downstream,
        requires_human_review=requires_human_review,
    )


def _candidate(
    role_key: RoleKey,
    *,
    risk_code: SemanticRiskCode,
    disposition: SemanticReviewDisposition,
    review_question: str,
    claim_index: int = 0,
) -> SemanticRiskCandidate:
    """Build one semantic risk candidate."""
    return SemanticRiskCandidate(
        risk_code=risk_code,
        role_key=role_key,
        claim_index=claim_index,
        evidence_ids=[_evidence_id(role_key)],
        explanation=f"Semantic concern for {role_key.value}.",
        review_question=review_question,
        confidence="medium",
        disposition=disposition,
    )


def _healthy_inputs() -> tuple[
    dict[RoleKey, RoleOutcome],
    list[EvidenceObject],
    RiskReviewResult,
    SemanticRiskReviewResult,
]:
    """Build five successful views and their empty risk reviews."""
    views = {
        role_key: _view(
            role_key,
            next_action=f"Perform the {role_key.value} action.",
            dependency=f"Dependency note for {role_key.value}.",
        )
        for role_key in _CANONICAL_ROLES
    }
    outcomes = _outcomes(views)
    evidence = [_evidence(role_key) for role_key in _CANONICAL_ROLES]
    return outcomes, evidence, _risk_result(), _semantic_result(outcomes)


def _step_payload(**overrides: Any) -> dict[str, Any]:
    """Return a minimal valid workflow-step payload."""
    payload: dict[str, Any] = {
        "step_id": "wf-001",
        "sequence": 1,
        "step_kind": WorkflowStepKind.role_action,
        "owner_role": RoleKey.executive,
        "action": "Take the executive action.",
        "supporting_evidence_ids": [_evidence_id(RoleKey.executive)],
        "dependency_step_ids": [],
        "dependency_notes": [],
        "missing_information": [],
        "deterministic_risk_codes": [],
        "semantic_risk_codes": [],
        "review_questions": [],
        "status": WorkflowStepStatus.ready,
        "blocks_downstream": False,
        "human_review_required": False,
    }
    payload.update(overrides)
    return payload


def test_workflow_schemas_reject_malformed_steps_and_plans() -> None:
    """Workflow schemas reject malformed IDs, duplicates, and derived state."""
    malformed_steps = [
        _step_payload(step_id="step-001"),
        _step_payload(supporting_evidence_ids=["bad-evidence-id"]),
        _step_payload(
            supporting_evidence_ids=[
                _evidence_id(RoleKey.executive),
                _evidence_id(RoleKey.executive),
            ]
        ),
        _step_payload(dependency_step_ids=["wf-001"]),
        _step_payload(
            step_kind=WorkflowStepKind.semantic_review_gate,
            status=WorkflowStepStatus.pending_human_review,
            human_review_required=True,
            semantic_risk_codes=[],
            review_questions=["Review the claim."],
        ),
        _step_payload(
            step_kind=WorkflowStepKind.deterministic_risk_resolution,
            deterministic_risk_codes=[],
        ),
        _step_payload(dependency_notes=["Repeated.", "Repeated."]),
    ]
    for payload in malformed_steps:
        with pytest.raises(ValidationError):
            WorkflowStep(**payload)

    valid_step = WorkflowStep(**_step_payload())
    malformed_plans: list[dict[str, Any]] = [
        {
            "steps": [
                WorkflowStep(
                    **_step_payload(step_id="wf-002", sequence=2)
                )
            ],
            "included_role_keys": [RoleKey.executive],
            "blocking_step_ids": [],
            "plan_status": WorkflowPlanStatus.ready_for_human_review,
        },
        {
            "steps": [
                WorkflowStep(
                    **_step_payload(dependency_step_ids=["wf-002"])
                ),
                WorkflowStep(
                    **_step_payload(
                        step_id="wf-002",
                        sequence=2,
                        owner_role=RoleKey.data_analyst,
                        supporting_evidence_ids=[
                            _evidence_id(RoleKey.data_analyst)
                        ],
                    )
                ),
            ],
            "included_role_keys": [
                RoleKey.executive,
                RoleKey.data_analyst,
            ],
            "blocking_step_ids": [],
            "plan_status": WorkflowPlanStatus.ready_for_human_review,
        },
        {
            "steps": [valid_step],
            "included_role_keys": [RoleKey.executive],
            "blocking_step_ids": ["wf-001"],
            "plan_status": WorkflowPlanStatus.blocked,
        },
        {
            "steps": [valid_step],
            "included_role_keys": [RoleKey.executive],
            "blocking_step_ids": [],
            "plan_status": WorkflowPlanStatus.no_actionable_steps,
        },
        {
            "steps": [],
            "included_role_keys": [
                RoleKey.data_engineer,
                RoleKey.executive,
            ],
            "blocking_step_ids": [],
            "plan_status": WorkflowPlanStatus.no_actionable_steps,
        },
    ]
    for payload in malformed_plans:
        with pytest.raises(ValidationError):
            WorkflowPlan(
                **payload,
                human_review_required=True,
            planning_method="deterministic_v1",
            )


def test_healthy_five_role_plan_uses_fixed_workflow_order() -> None:
    """Five healthy views become role actions in the fixed workflow order."""
    outcomes, evidence, deterministic, semantic = _healthy_inputs()

    plan = plan_workflow(outcomes, evidence, deterministic, semantic)

    assert [step.owner_role for step in plan.steps] == list(_WORKFLOW_ROLES)
    assert [step.step_id for step in plan.steps] == [
        "wf-001",
        "wf-002",
        "wf-003",
        "wf-004",
        "wf-005",
    ]
    assert all(
        step.step_kind is WorkflowStepKind.role_action for step in plan.steps
    )
    assert all(step.status is WorkflowStepStatus.ready for step in plan.steps)
    assert plan.included_role_keys == list(_CANONICAL_ROLES)
    assert plan.plan_status is WorkflowPlanStatus.ready_for_human_review
    assert plan.human_review_required is True


def test_cross_role_dependencies_follow_all_prior_workflow_roles() -> None:
    """Each role action depends on every earlier included workflow role."""
    outcomes, evidence, deterministic, semantic = _healthy_inputs()

    plan = plan_workflow(outcomes, evidence, deterministic, semantic)

    assert [step.dependency_step_ids for step in plan.steps] == [
        [],
        ["wf-001"],
        ["wf-001", "wf-002"],
        ["wf-001", "wf-002", "wf-003"],
        ["wf-001", "wf-002", "wf-003", "wf-004"],
    ]
    assert [
        step.dependency_notes for step in plan.steps
    ] == [
        [f"Dependency note for {role_key.value}."]
        for role_key in _WORKFLOW_ROLES
    ]


def test_blocking_deterministic_risk_propagates_to_downstream_actions() -> None:
    """A blocking resolution step blocks its role action and all later roles."""
    outcomes, evidence, _, semantic = _healthy_inputs()
    deterministic = _risk_result(
        [
            _finding(
                RoleKey.data_engineer,
                required_action="Validate the source before proceeding.",
                blocks_downstream=True,
            )
        ]
    )

    plan = plan_workflow(outcomes, evidence, deterministic, semantic)

    assert plan.steps[0].step_kind is WorkflowStepKind.deterministic_risk_resolution
    assert plan.steps[0].blocks_downstream is True
    assert plan.blocking_step_ids == ["wf-001"]
    assert [
        step.status
        for step in plan.steps
        if step.step_kind is WorkflowStepKind.role_action
    ] == [WorkflowStepStatus.blocked] * 5
    assert plan.plan_status is WorkflowPlanStatus.blocked


def test_nonblocking_deterministic_review_propagates_pending_status() -> None:
    """A nonblocking human review makes dependent role actions pending."""
    outcomes, evidence, _, semantic = _healthy_inputs()
    deterministic = _risk_result(
        [
            _finding(
                RoleKey.data_analyst,
                required_action="Confirm the disclosed limitation.",
                blocks_downstream=False,
                requires_human_review=True,
            )
        ]
    )

    plan = plan_workflow(outcomes, evidence, deterministic, semantic)
    resolution = next(
        step
        for step in plan.steps
        if step.step_kind is WorkflowStepKind.deterministic_risk_resolution
    )

    assert resolution.status is WorkflowStepStatus.pending_human_review
    assert resolution.blocks_downstream is False
    analyst_index = next(
        index
        for index, step in enumerate(plan.steps)
        if step.owner_role is RoleKey.data_analyst
        and step.step_kind is WorkflowStepKind.role_action
    )
    assert all(
        step.status is WorkflowStepStatus.pending_human_review
        for step in plan.steps[analyst_index:]
        if step.step_kind is WorkflowStepKind.role_action
    )
    assert plan.blocking_step_ids == []
    assert plan.plan_status is WorkflowPlanStatus.ready_for_human_review


def test_semantic_candidates_form_one_nonblocking_gate_per_role() -> None:
    """Only review-required semantic candidates form a consolidated gate."""
    executive = _view(
        RoleKey.executive,
        next_action="Approve the bounded executive action.",
    )
    outcomes = _outcomes({RoleKey.executive: executive})
    evidence = [_evidence(RoleKey.executive)]
    candidates = [
        _candidate(
            RoleKey.executive,
            risk_code=SemanticRiskCode.unsupported_company_specific_claim,
            disposition=SemanticReviewDisposition.needs_human_review,
            review_question="Does the evidence support the company claim?",
        ),
        _candidate(
            RoleKey.executive,
            risk_code=SemanticRiskCode.citation_claim_mismatch,
            disposition=SemanticReviewDisposition.reviewer_uncertain,
            review_question="Is the citation aligned with the claim?",
        ),
        _candidate(
            RoleKey.executive,
            risk_code=SemanticRiskCode.role_boundary_violation,
            disposition=SemanticReviewDisposition.likely_supported,
            review_question="Is the recommendation appropriately bounded?",
        ),
    ]

    plan = plan_workflow(
        outcomes,
        evidence,
        _risk_result(),
        _semantic_result(outcomes, candidates),
    )

    gates = [
        step
        for step in plan.steps
        if step.step_kind is WorkflowStepKind.semantic_review_gate
    ]
    assert len(gates) == 1
    gate = gates[0]
    assert gate.semantic_risk_codes == [
        SemanticRiskCode.unsupported_company_specific_claim,
        SemanticRiskCode.citation_claim_mismatch,
    ]
    assert gate.review_questions == [
        "Does the evidence support the company claim?",
        "Is the citation aligned with the claim?",
    ]
    assert gate.status is WorkflowStepStatus.pending_human_review
    assert gate.blocks_downstream is False
    assert plan.steps[-1].dependency_step_ids == [gate.step_id]
    assert plan.steps[-1].status is WorkflowStepStatus.pending_human_review


def test_unsuccessful_roles_receive_only_applicable_risk_resolution_steps() -> None:
    """Failed roles have no role action but may retain deterministic risk work."""
    outcomes: dict[RoleKey, RoleOutcome] = {
        role_key: InsufficientEvidence(
            role_key=role_key,
            reason=f"Missing {role_key.value} evidence.",
        )
        for role_key in _CANONICAL_ROLES
    }
    outcomes[RoleKey.project_manager] = RoleGenerationFailure(
        role_key=RoleKey.project_manager,
        failure_code="provider_error",
        reason="Provider output was unavailable.",
    )
    evidence = [
        _evidence(RoleKey.data_engineer),
        _evidence(RoleKey.project_manager),
    ]
    findings = [
        _finding(
            RoleKey.data_engineer,
            required_action="Acquire engineering evidence.",
            claim_index=None,
        ),
        _finding(
            RoleKey.project_manager,
            required_action="Resolve the project-manager risk.",
            claim_index=None,
        ),
    ]

    plan = plan_workflow(
        outcomes,
        evidence,
        _risk_result(findings),
        _semantic_result(outcomes),
    )

    assert [step.step_kind for step in plan.steps] == [
        WorkflowStepKind.deterministic_risk_resolution,
        WorkflowStepKind.deterministic_risk_resolution,
    ]
    assert [step.owner_role for step in plan.steps] == [
        RoleKey.data_engineer,
        RoleKey.project_manager,
    ]
    assert [step.action for step in plan.steps] == [
        "Acquire engineering evidence.",
        "Resolve the project-manager risk.",
    ]
    assert plan.included_role_keys == []


def test_planner_fails_closed_on_corrupted_inputs_before_planning() -> None:
    """Malformed outcomes, evidence, and risk references all fail closed."""
    executive = _view(RoleKey.executive, next_action="Act.")
    outcomes = _outcomes({RoleKey.executive: executive})
    evidence = [_evidence(RoleKey.executive)]
    deterministic = _risk_result()
    semantic = _semantic_result(outcomes)

    malformed_outcomes: list[Mapping[Any, Any]] = [
        {key: value for key, value in outcomes.items() if key is not RoleKey.executive},
        {**outcomes, "not_a_role": executive},
        {**outcomes, RoleKey.executive: object()},
        {
            **outcomes,
            RoleKey.executive: InsufficientEvidence(
                role_key=RoleKey.data_engineer,
                reason="Missing evidence.",
            ),
        },
    ]
    for malformed in malformed_outcomes:
        with pytest.raises(WorkflowPlanningInputError):
            plan_workflow(malformed, evidence, deterministic, semantic)

    conflicting = _evidence(RoleKey.executive)
    conflicting = conflicting.model_copy(
        update={"identity_digest": "f" * 64}
    )
    with pytest.raises(WorkflowPlanningInputError):
        plan_workflow(
            outcomes,
            [evidence[0], conflicting],
            deterministic,
            semantic,
        )

    with pytest.raises(WorkflowPlanningInputError):
        plan_workflow(
            outcomes,
            [_evidence(RoleKey.executive, status=EvidenceStatus.invalidated)],
            deterministic,
            semantic,
        )

    with pytest.raises(WorkflowPlanningInputError):
        plan_workflow(
            outcomes,
            [_evidence(RoleKey.data_engineer)],
            deterministic,
            semantic,
        )

    invalid_deterministic = _risk_result(
        [_finding(RoleKey.executive, claim_index=1)]
    )
    with pytest.raises(WorkflowPlanningInputError):
        plan_workflow(
            outcomes,
            evidence,
            invalid_deterministic,
            semantic,
        )

    invalid_semantic = _semantic_result(
        outcomes,
        [
            _candidate(
                RoleKey.executive,
                risk_code=SemanticRiskCode.citation_claim_mismatch,
                disposition=SemanticReviewDisposition.needs_human_review,
                review_question="Review this claim.",
                claim_index=1,
            )
        ],
    )
    with pytest.raises(WorkflowPlanningInputError):
        plan_workflow(
            outcomes,
            evidence,
            deterministic,
            invalid_semantic,
        )

    mismatched_review = SemanticRiskReviewResult(
        reviewed_role_keys=[],
        candidates=[],
        human_review_required=False,
        reviewer_model=None,
    )
    with pytest.raises(WorkflowPlanningInputError):
        plan_workflow(
            outcomes,
            evidence,
            deterministic,
            mismatched_review,
        )

    malformed_deterministic = RiskReviewResult.model_construct(
        reviewed_role_keys=[RoleKey.executive],
        findings=[],
        has_blocking_risks=False,
        human_review_required=False,
    )
    with pytest.raises(WorkflowPlanningInputError):
        plan_workflow(
            outcomes,
            evidence,
            malformed_deterministic,
            semantic,
        )


def test_no_next_actions_produces_no_actionable_steps() -> None:
    """Successful views without next actions produce the explicit empty plan."""
    outcomes = _outcomes(
        {
            RoleKey.executive: _view(RoleKey.executive),
            RoleKey.data_analyst: _view(RoleKey.data_analyst),
        }
    )
    evidence = [
        _evidence(RoleKey.executive),
        _evidence(RoleKey.data_analyst),
    ]

    plan = plan_workflow(
        outcomes,
        evidence,
        _risk_result(),
        _semantic_result(outcomes),
    )

    assert plan.steps == []
    assert plan.plan_status is WorkflowPlanStatus.no_actionable_steps
    assert plan.included_role_keys == [
        RoleKey.executive,
        RoleKey.data_analyst,
    ]
    assert plan.blocking_step_ids == []
    assert plan.human_review_required is True


def test_complex_b2b_saas_plan_is_repeatable_and_sequences_validation_first() -> None:
    """A representative B2B SaaS plan is stable and validation-led."""
    views = {
        RoleKey.data_engineer: _view(
            RoleKey.data_engineer,
            next_action="Validate customer-event joins and freshness.",
        ),
        RoleKey.data_analyst: _view(
            RoleKey.data_analyst,
            next_action="Analyze bounded churn patterns.",
        ),
        RoleKey.executive: _view(
            RoleKey.executive,
            next_action="Select the reviewed retention priority.",
        ),
        RoleKey.sales_marketing: _view(
            RoleKey.sales_marketing,
            next_action="Draft a reviewed retention experiment.",
        ),
        RoleKey.project_manager: _view(
            RoleKey.project_manager,
            next_action="Sequence owners, checkpoints, and approvals.",
        ),
    }
    outcomes = _outcomes(views)
    evidence = [_evidence(role_key) for role_key in _CANONICAL_ROLES]
    deterministic = _risk_result(
        [
            _finding(
                RoleKey.data_engineer,
                risk_code=RiskCode.action_without_internal_evidence,
                required_action="Validate the join limitations.",
                blocks_downstream=True,
            )
        ]
    )
    semantic = _semantic_result(
        outcomes,
        [
            _candidate(
                RoleKey.executive,
                risk_code=SemanticRiskCode.unsupported_company_specific_claim,
                disposition=SemanticReviewDisposition.reviewer_uncertain,
                review_question="Is the retention priority company-supported?",
            )
        ],
    )

    first = plan_workflow(outcomes, evidence, deterministic, semantic)
    second = plan_workflow(outcomes, evidence, deterministic, semantic)

    assert first == second
    assert [
        (step.step_kind, step.owner_role, step.action) for step in first.steps
    ] == [
        (
            WorkflowStepKind.deterministic_risk_resolution,
            RoleKey.data_engineer,
            "Validate the join limitations.",
        ),
        (
            WorkflowStepKind.role_action,
            RoleKey.data_engineer,
            "Validate customer-event joins and freshness.",
        ),
        (
            WorkflowStepKind.role_action,
            RoleKey.data_analyst,
            "Analyze bounded churn patterns.",
        ),
        (
            WorkflowStepKind.semantic_review_gate,
            RoleKey.executive,
            "Review semantic risk candidates for executive before downstream action.",
        ),
        (
            WorkflowStepKind.role_action,
            RoleKey.executive,
            "Select the reviewed retention priority.",
        ),
        (
            WorkflowStepKind.role_action,
            RoleKey.sales_marketing,
            "Draft a reviewed retention experiment.",
        ),
        (
            WorkflowStepKind.role_action,
            RoleKey.project_manager,
            "Sequence owners, checkpoints, and approvals.",
        ),
    ]
    assert first.steps[-1].dependency_step_ids == [
        "wf-001",
        "wf-002",
        "wf-003",
        "wf-004",
        "wf-005",
        "wf-006",
    ]
    assert first.plan_status is WorkflowPlanStatus.blocked
