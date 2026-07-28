"""Deterministic, fail-closed cross-role Workflow Planner (Task 8A).

The planner validates already-produced RoleLens pipeline outputs and converts
only approved upstream action fields into an inspectable coordination plan.
It performs no provider calls, natural-language dependency parsing, execution,
or automatic approval.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from app.role_engine import (
    InsufficientEvidence,
    RoleGenerationFailure,
    RoleOutcome,
)
from app.schemas import (
    EvidenceObject,
    EvidenceStatus,
    RiskCode,
    RiskFinding,
    RiskReviewResult,
    RoleKey,
    RoleView,
    SemanticReviewDisposition,
    SemanticRiskCandidate,
    SemanticRiskCode,
    SemanticRiskReviewResult,
    WorkflowPlan,
    WorkflowPlanStatus,
    WorkflowStep,
    WorkflowStepKind,
    WorkflowStepStatus,
    _ROLE_EXECUTION_ORDER,
)


_WORKFLOW_ROLE_ORDER: tuple[RoleKey, ...] = (
    RoleKey.data_engineer,
    RoleKey.data_analyst,
    RoleKey.executive,
    RoleKey.sales_marketing,
    RoleKey.project_manager,
)
_APPROVED_OUTCOME_TYPES = (
    RoleView,
    InsufficientEvidence,
    RoleGenerationFailure,
)


class WorkflowPlanningInputError(ValueError):
    """Raised when validated upstream objects are mutually inconsistent."""


@dataclass(frozen=True)
class _DraftStep:
    """Internal step representation before stable IDs are assigned."""

    step_kind: WorkflowStepKind
    owner_role: RoleKey
    action: str
    supporting_evidence_ids: tuple[str, ...]
    dependency_indexes: tuple[int, ...]
    dependency_notes: tuple[str, ...]
    missing_information: tuple[str, ...]
    deterministic_risk_codes: tuple[RiskCode, ...]
    semantic_risk_codes: tuple[SemanticRiskCode, ...]
    review_questions: tuple[str, ...]
    status: WorkflowStepStatus
    blocks_downstream: bool
    human_review_required: bool


def _unique(values: Sequence[Any]) -> tuple[Any, ...]:
    """Return hashable values in first-seen order."""
    return tuple(dict.fromkeys(values))


def _successful_roles(
    role_outcomes: Mapping[RoleKey, RoleOutcome],
) -> tuple[RoleKey, ...]:
    """Return successful roles in canonical execution order."""
    return tuple(
        role_key
        for role_key in _ROLE_EXECUTION_ORDER
        if type(role_outcomes[role_key]) is RoleView
    )


def _validate_role_outcomes(
    role_outcomes: Mapping[RoleKey, RoleOutcome],
) -> None:
    """Validate exact keys, exact approved types, and role identity."""
    for mapping_key in role_outcomes:
        if not isinstance(mapping_key, RoleKey):
            raise WorkflowPlanningInputError(
                "role_outcomes contains a non-RoleKey mapping key "
                f"of type {type(mapping_key).__name__}"
            )
    required = set(_ROLE_EXECUTION_ORDER)
    if set(role_outcomes) != required:
        raise WorkflowPlanningInputError(
            "role_outcomes must contain exactly the five RoleKey values"
        )
    for role_key in _ROLE_EXECUTION_ORDER:
        outcome = role_outcomes[role_key]
        if type(outcome) not in _APPROVED_OUTCOME_TYPES:
            raise WorkflowPlanningInputError(
                f"role_outcomes for {role_key.value} has unsupported "
                f"type {type(outcome).__name__}"
            )
        if outcome.role_key != role_key:
            raise WorkflowPlanningInputError(
                f"role outcome identity mismatch for {role_key.value}"
            )


def _build_evidence_registry(
    evidence_objects: Sequence[EvidenceObject],
) -> dict[str, EvidenceObject]:
    """Build a registry, tolerating exact duplicates and rejecting conflicts."""
    if not isinstance(evidence_objects, Sequence) or isinstance(
        evidence_objects,
        (str, bytes),
    ):
        raise WorkflowPlanningInputError(
            "evidence_objects must be a sequence of EvidenceObject values"
        )
    registry: dict[str, EvidenceObject] = {}
    for evidence in evidence_objects:
        if type(evidence) is not EvidenceObject:
            raise WorkflowPlanningInputError(
                "evidence_objects contains an unsupported value type"
            )
        existing = registry.get(evidence.evidence_id)
        if existing is None:
            registry[evidence.evidence_id] = evidence
        elif existing != evidence:
            raise WorkflowPlanningInputError(
                "conflicting EvidenceObject records share an evidence_id"
            )
    return registry


def _active_evidence(
    evidence_id: str,
    registry: Mapping[str, EvidenceObject],
) -> EvidenceObject:
    """Resolve one active evidence ID with sanitized failures."""
    evidence = registry.get(evidence_id)
    if evidence is None:
        raise WorkflowPlanningInputError(
            "an upstream object references unknown evidence"
        )
    if evidence.status != EvidenceStatus.active:
        raise WorkflowPlanningInputError(
            "an upstream object references inactive evidence"
        )
    return evidence


def _claim_evidence_ids(view: RoleView, claim_index: int) -> set[str]:
    """Return evidence IDs cited by one existing claim."""
    if claim_index < 0 or claim_index >= len(view.key_findings):
        raise WorkflowPlanningInputError(
            "claim_index does not identify an existing GroundedFinding"
        )
    return {
        reference.evidence_id
        for reference in view.key_findings[claim_index].evidence_references
    }


def _validate_role_view_evidence(
    role_outcomes: Mapping[RoleKey, RoleOutcome],
    registry: Mapping[str, EvidenceObject],
) -> None:
    """Validate every successful view citation before planning."""
    for role_key in _ROLE_EXECUTION_ORDER:
        outcome = role_outcomes[role_key]
        if type(outcome) is not RoleView:
            continue
        for finding in outcome.key_findings:
            for reference in finding.evidence_references:
                _active_evidence(reference.evidence_id, registry)


def _validate_deterministic_result(
    result: RiskReviewResult,
    role_outcomes: Mapping[RoleKey, RoleOutcome],
    registry: Mapping[str, EvidenceObject],
) -> None:
    """Validate deterministic findings against exact roles, claims, and evidence."""
    if type(result) is not RiskReviewResult:
        raise WorkflowPlanningInputError(
            "deterministic_risk_result must be a RiskReviewResult"
        )
    if result.reviewed_role_keys != _ROLE_EXECUTION_ORDER:
        raise WorkflowPlanningInputError(
            "deterministic reviewed_role_keys must contain all five roles "
            "in canonical order"
        )
    if type(result.findings) is not list:
        raise WorkflowPlanningInputError(
            "deterministic findings must be a list"
        )
    for finding in result.findings:
        if type(finding) is not RiskFinding:
            raise WorkflowPlanningInputError(
                "deterministic result contains an unsupported finding type"
            )
        if (
            type(finding.role_key) is not RoleKey
            or finding.role_key not in role_outcomes
        ):
            raise WorkflowPlanningInputError(
                "deterministic finding references an unknown role"
            )
    if result.has_blocking_risks != any(
        finding.blocks_downstream for finding in result.findings
    ):
        raise WorkflowPlanningInputError(
            "deterministic blocking aggregate is inconsistent"
        )
    if result.human_review_required != any(
        finding.requires_human_review for finding in result.findings
    ):
        raise WorkflowPlanningInputError(
            "deterministic human-review aggregate is inconsistent"
        )

    for finding in result.findings:
        outcome = role_outcomes[finding.role_key]
        cited_ids: set[str] | None = None
        if finding.claim_index is not None:
            if type(finding.claim_index) is not int:
                raise WorkflowPlanningInputError(
                    "deterministic claim_index must be an integer or None"
                )
            if type(outcome) is not RoleView:
                raise WorkflowPlanningInputError(
                    "claim-level deterministic finding targets an "
                    "unsuccessful role"
                )
            cited_ids = _claim_evidence_ids(outcome, finding.claim_index)
        for evidence_id in finding.evidence_ids:
            _active_evidence(evidence_id, registry)
            if cited_ids is not None and evidence_id not in cited_ids:
                raise WorkflowPlanningInputError(
                    "claim-level deterministic finding references evidence "
                    "not cited by that claim"
                )


def _validate_semantic_result(
    result: SemanticRiskReviewResult,
    role_outcomes: Mapping[RoleKey, RoleOutcome],
    registry: Mapping[str, EvidenceObject],
) -> None:
    """Validate semantic candidates without treating model metadata as authority."""
    if type(result) is not SemanticRiskReviewResult:
        raise WorkflowPlanningInputError(
            "semantic_risk_result must be a SemanticRiskReviewResult"
        )
    successful_roles = list(_successful_roles(role_outcomes))
    if result.reviewed_role_keys != successful_roles:
        raise WorkflowPlanningInputError(
            "semantic reviewed_role_keys must exactly match successful "
            "RoleViews in canonical order"
        )
    if type(result.candidates) is not list:
        raise WorkflowPlanningInputError(
            "semantic candidates must be a list"
        )
    for candidate in result.candidates:
        if type(candidate) is not SemanticRiskCandidate:
            raise WorkflowPlanningInputError(
                "semantic result contains an unsupported candidate type"
            )
        if (
            type(candidate.role_key) is not RoleKey
            or candidate.role_key not in role_outcomes
        ):
            raise WorkflowPlanningInputError(
                "semantic candidate references an unknown role"
            )
    expected_review = any(
        candidate.disposition
        != SemanticReviewDisposition.likely_supported
        for candidate in result.candidates
    )
    if result.human_review_required != expected_review:
        raise WorkflowPlanningInputError(
            "semantic human-review aggregate is inconsistent"
        )

    for candidate in result.candidates:
        outcome = role_outcomes[candidate.role_key]
        if type(outcome) is not RoleView:
            raise WorkflowPlanningInputError(
                "semantic candidate targets an unsuccessful role"
            )
        if type(candidate.claim_index) is not int:
            raise WorkflowPlanningInputError(
                "semantic claim_index must be an integer"
            )
        cited_ids = _claim_evidence_ids(outcome, candidate.claim_index)
        for evidence_id in candidate.evidence_ids:
            _active_evidence(evidence_id, registry)
            if evidence_id not in cited_ids:
                raise WorkflowPlanningInputError(
                    "semantic candidate references evidence not cited by "
                    "the exact claim"
                )


def _validate_inputs(
    role_outcomes: Mapping[RoleKey, RoleOutcome],
    evidence_objects: Sequence[EvidenceObject],
    deterministic_risk_result: RiskReviewResult,
    semantic_risk_result: SemanticRiskReviewResult,
) -> dict[str, EvidenceObject]:
    """Complete all fail-closed validation before constructing any step."""
    if not isinstance(role_outcomes, Mapping):
        raise WorkflowPlanningInputError("role_outcomes must be a mapping")
    _validate_role_outcomes(role_outcomes)
    registry = _build_evidence_registry(evidence_objects)
    _validate_role_view_evidence(role_outcomes, registry)
    _validate_deterministic_result(
        deterministic_risk_result,
        role_outcomes,
        registry,
    )
    _validate_semantic_result(
        semantic_risk_result,
        role_outcomes,
        registry,
    )
    return registry


def _findings_by_role(
    result: RiskReviewResult,
) -> dict[RoleKey, list[RiskFinding]]:
    """Collect deterministic findings in their existing result order."""
    grouped = {role_key: [] for role_key in RoleKey}
    for finding in result.findings:
        grouped[finding.role_key].append(finding)
    return grouped


def _semantic_by_role(
    result: SemanticRiskReviewResult,
) -> dict[RoleKey, list[SemanticRiskCandidate]]:
    """Collect only semantic candidates that require a review gate."""
    grouped = {role_key: [] for role_key in RoleKey}
    for candidate in result.candidates:
        if candidate.disposition in (
            SemanticReviewDisposition.needs_human_review,
            SemanticReviewDisposition.reviewer_uncertain,
        ):
            grouped[candidate.role_key].append(candidate)
    return grouped


def _role_view_evidence_ids(view: RoleView) -> tuple[str, ...]:
    """Collect every cited view evidence ID in first-seen order."""
    return _unique(
        [
            reference.evidence_id
            for finding in view.key_findings
            for reference in finding.evidence_references
        ]
    )


def _materialize_steps(drafts: Sequence[_DraftStep]) -> list[WorkflowStep]:
    """Assign stable IDs after ordering and construct validated public steps."""
    step_ids = [
        f"wf-{sequence:03d}" for sequence in range(1, len(drafts) + 1)
    ]
    return [
        WorkflowStep(
            step_id=step_ids[index],
            sequence=index + 1,
            step_kind=draft.step_kind,
            owner_role=draft.owner_role,
            action=draft.action,
            supporting_evidence_ids=list(draft.supporting_evidence_ids),
            dependency_step_ids=[
                step_ids[dependency_index]
                for dependency_index in draft.dependency_indexes
            ],
            dependency_notes=list(draft.dependency_notes),
            missing_information=list(draft.missing_information),
            deterministic_risk_codes=list(
                draft.deterministic_risk_codes
            ),
            semantic_risk_codes=list(draft.semantic_risk_codes),
            review_questions=list(draft.review_questions),
            status=draft.status,
            blocks_downstream=draft.blocks_downstream,
            human_review_required=draft.human_review_required,
        )
        for index, draft in enumerate(drafts)
    ]


def plan_workflow(
    role_outcomes: Mapping[RoleKey, RoleOutcome],
    evidence_objects: Sequence[EvidenceObject],
    deterministic_risk_result: RiskReviewResult,
    semantic_risk_result: SemanticRiskReviewResult,
) -> WorkflowPlan:
    """Build a deterministic workflow plan from validated upstream outputs."""
    _validate_inputs(
        role_outcomes,
        evidence_objects,
        deterministic_risk_result,
        semantic_risk_result,
    )
    findings_by_role = _findings_by_role(deterministic_risk_result)
    semantic_by_role = _semantic_by_role(semantic_risk_result)
    drafts: list[_DraftStep] = []
    indexes_by_role: dict[RoleKey, list[int]] = {
        role_key: [] for role_key in RoleKey
    }

    for role_key in _WORKFLOW_ROLE_ORDER:
        prior_indexes = tuple(
            index
            for prior_role in _WORKFLOW_ROLE_ORDER
            if _WORKFLOW_ROLE_ORDER.index(prior_role)
            < _WORKFLOW_ROLE_ORDER.index(role_key)
            for index in indexes_by_role[prior_role]
        )
        role_findings = findings_by_role[role_key]
        grouped_findings: dict[str, list[RiskFinding]] = {}
        for finding in role_findings:
            grouped_findings.setdefault(
                finding.required_action,
                [],
            ).append(finding)

        deterministic_indexes: list[int] = []
        for action, grouped in grouped_findings.items():
            human_review_required = any(
                finding.requires_human_review for finding in grouped
            )
            draft = _DraftStep(
                step_kind=WorkflowStepKind.deterministic_risk_resolution,
                owner_role=role_key,
                action=action,
                supporting_evidence_ids=_unique(
                    [
                        evidence_id
                        for finding in grouped
                        for evidence_id in finding.evidence_ids
                    ]
                ),
                dependency_indexes=prior_indexes,
                dependency_notes=_unique(
                    [finding.message for finding in grouped]
                ),
                missing_information=(),
                deterministic_risk_codes=_unique(
                    [finding.risk_code for finding in grouped]
                ),
                semantic_risk_codes=(),
                review_questions=(),
                status=(
                    WorkflowStepStatus.pending_human_review
                    if human_review_required
                    else WorkflowStepStatus.ready
                ),
                blocks_downstream=any(
                    finding.blocks_downstream for finding in grouped
                ),
                human_review_required=human_review_required,
            )
            drafts.append(draft)
            index = len(drafts) - 1
            deterministic_indexes.append(index)
            indexes_by_role[role_key].append(index)

        qualifying_candidates = semantic_by_role[role_key]
        semantic_gate_index: int | None = None
        if qualifying_candidates:
            drafts.append(
                _DraftStep(
                    step_kind=WorkflowStepKind.semantic_review_gate,
                    owner_role=role_key,
                    action=(
                        "Review semantic risk candidates for "
                        f"{role_key.value} before downstream action."
                    ),
                    supporting_evidence_ids=_unique(
                        [
                            evidence_id
                            for candidate in qualifying_candidates
                            for evidence_id in candidate.evidence_ids
                        ]
                    ),
                    dependency_indexes=_unique(
                        [*prior_indexes, *deterministic_indexes]
                    ),
                    dependency_notes=(),
                    missing_information=(),
                    deterministic_risk_codes=(),
                    semantic_risk_codes=_unique(
                        [
                            candidate.risk_code
                            for candidate in qualifying_candidates
                        ]
                    ),
                    review_questions=_unique(
                        [
                            candidate.review_question
                            for candidate in qualifying_candidates
                        ]
                    ),
                    status=WorkflowStepStatus.pending_human_review,
                    blocks_downstream=False,
                    human_review_required=True,
                )
            )
            semantic_gate_index = len(drafts) - 1
            indexes_by_role[role_key].append(semantic_gate_index)

        outcome = role_outcomes[role_key]
        if type(outcome) is RoleView and outcome.next_action is not None:
            dependencies = _unique(
                [
                    *prior_indexes,
                    *deterministic_indexes,
                    *(
                        [semantic_gate_index]
                        if semantic_gate_index is not None
                        else []
                    ),
                ]
            )
            if any(drafts[index].blocks_downstream for index in dependencies):
                status = WorkflowStepStatus.blocked
            elif outcome.human_review_required or any(
                drafts[index].status
                == WorkflowStepStatus.pending_human_review
                for index in dependencies
            ):
                status = WorkflowStepStatus.pending_human_review
            else:
                status = WorkflowStepStatus.ready
            drafts.append(
                _DraftStep(
                    step_kind=WorkflowStepKind.role_action,
                    owner_role=role_key,
                    action=outcome.next_action,
                    supporting_evidence_ids=_role_view_evidence_ids(outcome),
                    dependency_indexes=dependencies,
                    dependency_notes=(
                        (outcome.dependency,)
                        if outcome.dependency is not None
                        else ()
                    ),
                    missing_information=tuple(
                        outcome.missing_information
                    ),
                    deterministic_risk_codes=_unique(
                        [
                            finding.risk_code
                            for finding in role_findings
                        ]
                    ),
                    semantic_risk_codes=_unique(
                        [
                            candidate.risk_code
                            for candidate in qualifying_candidates
                        ]
                    ),
                    review_questions=(),
                    status=status,
                    blocks_downstream=False,
                    human_review_required=(
                        status
                        in (
                            WorkflowStepStatus.pending_human_review,
                            WorkflowStepStatus.blocked,
                        )
                        or outcome.human_review_required
                    ),
                )
            )
            indexes_by_role[role_key].append(len(drafts) - 1)

    steps = _materialize_steps(drafts)
    blocking_step_ids = [
        step.step_id for step in steps if step.blocks_downstream
    ]
    if not steps:
        plan_status = WorkflowPlanStatus.no_actionable_steps
    elif blocking_step_ids:
        plan_status = WorkflowPlanStatus.blocked
    else:
        plan_status = WorkflowPlanStatus.ready_for_human_review
    return WorkflowPlan(
        steps=steps,
        plan_status=plan_status,
        included_role_keys=list(_successful_roles(role_outcomes)),
        blocking_step_ids=blocking_step_ids,
        human_review_required=True,
        planning_method="deterministic_v1",
    )
