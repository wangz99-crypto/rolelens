"""Deterministic scenario evaluation for the Task 8A Workflow Planner.

This module loads a fixed synthetic fixture pack, constructs exact upstream
pipeline inputs, evaluates planner output with strict comparisons, and
provides a transparent flat-action-list baseline. It performs no provider,
network, fuzzy-matching, or natural-language dependency work.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from app.role_engine import (
    InsufficientEvidence,
    RoleGenerationFailure,
    RoleOutcome,
)
from app.schemas import (
    EvidenceObject,
    EvidenceReference,
    EvidenceScope,
    EvidenceStatus,
    GroundedFinding,
    RiskCode,
    RiskFinding,
    RiskReviewResult,
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
    _ROLE_EXECUTION_ORDER,
)
from app.workflow_planner import plan_workflow


DEFAULT_WORKFLOW_SCENARIO_PATH = (
    Path(__file__).resolve().parents[1]
    / "examples"
    / "scenarios"
    / "workflow_v1.json"
)

_REQUIRED_SCENARIO_IDS = (
    "W1_healthy_full_sequence",
    "W2_data_engineer_blocker",
    "W3_semantic_review_gate",
    "W4_nonblocking_deterministic_review",
    "W5_failed_roles_no_fabricated_actions",
    "W6_duplicate_resolution_grouping",
    "W7_dependency_note_is_non_executable",
    "W8_no_actionable_steps",
)
_WORKFLOW_ROLE_ORDER = (
    RoleKey.data_engineer,
    RoleKey.data_analyst,
    RoleKey.executive,
    RoleKey.sales_marketing,
    RoleKey.project_manager,
)
_QUALIFYING_DISPOSITIONS = (
    SemanticReviewDisposition.needs_human_review,
    SemanticReviewDisposition.reviewer_uncertain,
)


class WorkflowEvaluationInputError(ValueError):
    """Raised when workflow evaluation input is malformed or ambiguous."""


class _FrozenEvaluationModel(BaseModel):
    """Shared immutable, extra-forbidding evaluation model."""

    model_config = ConfigDict(extra="forbid", frozen=True)


def _non_blank(value: str, *, field_name: str) -> str:
    """Return non-blank text or raise a validation error."""
    if not value or not value.strip():
        raise ValueError(f"{field_name} must not be blank")
    return value


def _unique(values: Sequence[Any]) -> tuple[Any, ...]:
    """Return distinct hashable values in first-seen order."""
    return tuple(dict.fromkeys(values))


class WorkflowScenarioFinding(_FrozenEvaluationModel):
    """Fixture representation of one deterministic risk finding."""

    role_key: RoleKey
    risk_code: RiskCode
    message: str
    required_action: str
    blocks_downstream: bool
    requires_human_review: bool
    claim_index: int | None

    @field_validator("message", "required_action")
    @classmethod
    def text_is_non_blank(cls, value: str, info: Any) -> str:
        """Reject blank finding text."""
        return _non_blank(value, field_name=info.field_name)

    @field_validator("claim_index")
    @classmethod
    def claim_index_is_valid(cls, value: int | None) -> int | None:
        """Require a non-negative claim index when one is supplied."""
        if value is not None and value < 0:
            raise ValueError("claim_index must be >= 0 when supplied")
        return value


class WorkflowScenarioSemanticCandidate(_FrozenEvaluationModel):
    """Fixture representation of one single-claim semantic candidate."""

    role_key: RoleKey
    risk_code: SemanticRiskCode
    disposition: SemanticReviewDisposition
    review_question: str
    claim_index: int = 0

    @field_validator("review_question")
    @classmethod
    def question_is_non_blank(cls, value: str) -> str:
        """Reject a blank review question."""
        return _non_blank(value, field_name="review_question")

    @field_validator("claim_index")
    @classmethod
    def claim_index_is_zero(cls, value: int) -> int:
        """This fixed fixture pack contains exactly one claim per view."""
        if value != 0:
            raise ValueError("claim_index must be exactly 0")
        return value


class WorkflowScenarioExpectation(_FrozenEvaluationModel):
    """Exact expected workflow shape and status for one scenario."""

    plan_status: WorkflowPlanStatus
    step_signatures: tuple[str, ...]
    dependency_sequences: tuple[tuple[int, ...], ...]
    blocking_sequences: tuple[int, ...]
    included_role_keys: tuple[RoleKey, ...]
    role_action_statuses: dict[RoleKey, WorkflowStepStatus]
    semantic_gate_roles: tuple[RoleKey, ...]
    absent_role_actions: tuple[RoleKey, ...]

    @field_validator("step_signatures")
    @classmethod
    def signatures_are_valid_unique_shape(
        cls,
        values: tuple[str, ...],
    ) -> tuple[str, ...]:
        """Require exact ``step_kind:role_key`` signatures."""
        valid_kinds = {kind.value for kind in WorkflowStepKind}
        valid_roles = {role.value for role in RoleKey}
        for value in values:
            if not value or not value.strip():
                raise ValueError("step_signatures must not contain blanks")
            parts = value.split(":")
            if (
                len(parts) != 2
                or parts[0] not in valid_kinds
                or parts[1] not in valid_roles
                or value != f"{parts[0]}:{parts[1]}"
            ):
                raise ValueError(
                    "step signatures must use exactly <step_kind>:<role_key>"
                )
        return values

    @field_validator("dependency_sequences")
    @classmethod
    def dependencies_are_unique_positive_and_earlier(
        cls,
        values: tuple[tuple[int, ...], ...],
    ) -> tuple[tuple[int, ...], ...]:
        """Reject duplicate, non-positive, or non-earlier dependencies."""
        for step_sequence, dependencies in enumerate(values, start=1):
            if len(dependencies) != len(set(dependencies)):
                raise ValueError(
                    "dependency sequences must not contain duplicates"
                )
            if any(
                type(dependency) is not int or dependency < 1
                for dependency in dependencies
            ):
                raise ValueError(
                    "dependency sequences must contain positive integers"
                )
            if any(dependency >= step_sequence for dependency in dependencies):
                raise ValueError(
                    "dependencies must reference an earlier step sequence"
                )
        return values

    @field_validator("included_role_keys")
    @classmethod
    def included_roles_are_fixed_order_subsequence(
        cls,
        values: tuple[RoleKey, ...],
    ) -> tuple[RoleKey, ...]:
        """Require unique roles in canonical schema order."""
        if len(values) != len(set(values)):
            raise ValueError("included_role_keys must not contain duplicates")
        expected = tuple(
            role_key
            for role_key in _ROLE_EXECUTION_ORDER
            if role_key in set(values)
        )
        if values != expected:
            raise ValueError(
                "included_role_keys must preserve canonical role order"
            )
        return values

    @field_validator("semantic_gate_roles", "absent_role_actions")
    @classmethod
    def role_lists_are_unique(
        cls,
        values: tuple[RoleKey, ...],
        info: Any,
    ) -> tuple[RoleKey, ...]:
        """Reject duplicate role values in expectation lists."""
        if len(values) != len(set(values)):
            raise ValueError(f"{info.field_name} must not contain duplicates")
        return values

    @model_validator(mode="after")
    def expectation_shape_is_consistent(self) -> "WorkflowScenarioExpectation":
        """Validate expectation lengths and blocker references."""
        step_count = len(self.step_signatures)
        if len(self.dependency_sequences) != step_count:
            raise ValueError(
                "step_signatures and dependency_sequences must have equal length"
            )
        if len(self.blocking_sequences) != len(set(self.blocking_sequences)):
            raise ValueError("blocking_sequences must not contain duplicates")
        if any(
            type(sequence) is not int
            or sequence < 1
            or sequence > step_count
            for sequence in self.blocking_sequences
        ):
            raise ValueError(
                "blocking_sequences must reference existing step sequences"
            )
        return self


class WorkflowEvaluationScenario(_FrozenEvaluationModel):
    """One synthetic scenario for deterministic workflow evaluation."""

    scenario_id: str
    title: str
    purpose: str
    successful_roles: tuple[RoleKey, ...]
    generation_failure_roles: tuple[RoleKey, ...]
    role_actions: dict[RoleKey, str]
    role_dependencies: dict[RoleKey, str]
    role_missing_information: dict[RoleKey, tuple[str, ...]]
    role_human_review_required: tuple[RoleKey, ...]
    deterministic_findings: tuple[WorkflowScenarioFinding, ...]
    semantic_candidates: tuple[WorkflowScenarioSemanticCandidate, ...]
    expected: WorkflowScenarioExpectation
    rationale: str
    demo_priority: bool = Field(strict=True)

    @field_validator("scenario_id", "title", "purpose", "rationale")
    @classmethod
    def text_fields_are_non_blank(cls, value: str, info: Any) -> str:
        """Reject blank fixture identifiers and prose."""
        return _non_blank(value, field_name=info.field_name)

    @field_validator(
        "successful_roles",
        "generation_failure_roles",
        "role_human_review_required",
    )
    @classmethod
    def role_lists_are_unique(
        cls,
        values: tuple[RoleKey, ...],
        info: Any,
    ) -> tuple[RoleKey, ...]:
        """Reject duplicate role values."""
        if len(values) != len(set(values)):
            raise ValueError(f"{info.field_name} must not contain duplicates")
        return values

    @field_validator("role_actions", "role_dependencies")
    @classmethod
    def role_text_mappings_are_non_blank(
        cls,
        values: dict[RoleKey, str],
        info: Any,
    ) -> dict[RoleKey, str]:
        """Reject blank mapped action or dependency text."""
        for value in values.values():
            _non_blank(value, field_name=info.field_name)
        return values

    @field_validator("role_missing_information")
    @classmethod
    def missing_information_is_clean(
        cls,
        values: dict[RoleKey, tuple[str, ...]],
    ) -> dict[RoleKey, tuple[str, ...]]:
        """Reject blank or duplicate missing-information values."""
        for items in values.values():
            if any(not item or not item.strip() for item in items):
                raise ValueError(
                    "role_missing_information must not contain blank values"
                )
            if len(items) != len(set(items)):
                raise ValueError(
                    "role_missing_information must not contain duplicates"
                )
        return values

    @model_validator(mode="after")
    def role_relationships_are_valid(self) -> "WorkflowEvaluationScenario":
        """Restrict fixture mappings and claim-level records to valid roles."""
        successful = set(self.successful_roles)
        failures = set(self.generation_failure_roles)
        overlap = successful & failures
        if overlap:
            raise ValueError(
                "successful_roles and generation_failure_roles must be disjoint"
            )

        mapped_roles = (
            set(self.role_actions)
            | set(self.role_dependencies)
            | set(self.role_missing_information)
            | set(self.role_human_review_required)
        )
        if not mapped_roles <= successful:
            raise ValueError(
                "role mappings and human-review roles may reference only "
                "successful roles"
            )
        if any(
            candidate.role_key not in successful
            for candidate in self.semantic_candidates
        ):
            raise ValueError(
                "semantic candidates may reference only successful roles"
            )
        if any(
            finding.claim_index is not None
            and finding.role_key not in successful
            for finding in self.deterministic_findings
        ):
            raise ValueError(
                "claim-level deterministic findings may reference only "
                "successful roles"
            )
        return self


class WorkflowScenarioEvaluationResult(_FrozenEvaluationModel):
    """Exact comparison result for one workflow scenario."""

    scenario_id: str
    passed: bool
    actual_plan_status: WorkflowPlanStatus
    actual_step_signatures: tuple[str, ...]
    actual_dependency_sequences: tuple[tuple[int, ...], ...]
    actual_blocking_sequences: tuple[int, ...]
    actual_included_role_keys: tuple[RoleKey, ...]
    failure_reasons: tuple[str, ...]


@dataclass(frozen=True)
class WorkflowEvaluationSummary:
    """Derived aggregate results for a workflow scenario sequence."""

    scenario_results: tuple[WorkflowScenarioEvaluationResult, ...]
    total_scenarios: int = field(init=False)
    passed_scenarios: int = field(init=False)
    failed_scenarios: int = field(init=False)
    pass_rate: float = field(init=False)

    def __post_init__(self) -> None:
        """Derive aggregate fields and reject duplicate scenario IDs."""
        scenario_ids = [
            result.scenario_id for result in self.scenario_results
        ]
        if len(scenario_ids) != len(set(scenario_ids)):
            raise WorkflowEvaluationInputError(
                "scenario_results must not contain duplicate scenario IDs"
            )
        total = len(self.scenario_results)
        passed = sum(result.passed for result in self.scenario_results)
        object.__setattr__(self, "total_scenarios", total)
        object.__setattr__(self, "passed_scenarios", passed)
        object.__setattr__(self, "failed_scenarios", total - passed)
        object.__setattr__(
            self,
            "pass_rate",
            passed / total if total else 0.0,
        )


@dataclass(frozen=True)
class WorkflowScenarioInputs:
    """Exact upstream inputs constructed for one workflow scenario."""

    role_outcomes: dict[RoleKey, RoleOutcome]
    evidence_objects: tuple[EvidenceObject, ...]
    deterministic_risk_result: RiskReviewResult
    semantic_risk_result: SemanticRiskReviewResult


def _load_json(path: Path) -> Any:
    """Read and decode JSON while normalizing fixture failures."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise WorkflowEvaluationInputError(
            f"unable to load workflow evaluation fixture {path}: {exc}"
        ) from exc


def load_workflow_scenarios(
    path: Path = DEFAULT_WORKFLOW_SCENARIO_PATH,
) -> tuple[WorkflowEvaluationScenario, ...]:
    """Load the exact W1-W8 workflow evaluation pack in approved order."""
    raw_scenarios = _load_json(path)
    if not isinstance(raw_scenarios, list):
        raise WorkflowEvaluationInputError(
            "workflow evaluation fixture top-level value must be a list"
        )

    scenarios: list[WorkflowEvaluationScenario] = []
    for index, raw_scenario in enumerate(raw_scenarios):
        if not isinstance(raw_scenario, Mapping):
            raise WorkflowEvaluationInputError(
                f"workflow scenario at index {index} must be a JSON object"
            )
        try:
            scenarios.append(
                WorkflowEvaluationScenario.model_validate(raw_scenario)
            )
        except ValidationError as exc:
            raise WorkflowEvaluationInputError(
                f"invalid workflow evaluation scenario at index {index}: {exc}"
            ) from exc

    scenario_ids = tuple(scenario.scenario_id for scenario in scenarios)
    if len(scenario_ids) != len(set(scenario_ids)):
        raise WorkflowEvaluationInputError(
            "workflow evaluation fixture contains duplicate scenario IDs"
        )
    missing = tuple(
        scenario_id
        for scenario_id in _REQUIRED_SCENARIO_IDS
        if scenario_id not in scenario_ids
    )
    if missing:
        raise WorkflowEvaluationInputError(
            "workflow evaluation fixture is missing required scenario IDs: "
            + ", ".join(missing)
        )
    extras = tuple(
        scenario_id
        for scenario_id in scenario_ids
        if scenario_id not in set(_REQUIRED_SCENARIO_IDS)
    )
    if extras:
        raise WorkflowEvaluationInputError(
            "workflow evaluation fixture contains unapproved scenario IDs: "
            + ", ".join(extras)
        )
    if scenario_ids != _REQUIRED_SCENARIO_IDS:
        raise WorkflowEvaluationInputError(
            "workflow evaluation scenario IDs must appear in approved W1-W8 order"
        )
    return tuple(scenarios)


def _identity_material(scenario_id: str, role_key: RoleKey) -> str:
    """Return stable fixture identity material."""
    return f"workflow-evaluation-v1|{scenario_id}|{role_key.value}"


def _build_evidence(
    scenario_id: str,
    role_key: RoleKey,
) -> EvidenceObject:
    """Build one stable active synthetic EvidenceObject without minting logic."""
    digest = hashlib.sha256(
        _identity_material(scenario_id, role_key).encode("utf-8")
    ).hexdigest()
    role_abbreviations = {
        RoleKey.executive: "wf_exec",
        RoleKey.data_analyst: "wf_analyst",
        RoleKey.data_engineer: "wf_engineer",
        RoleKey.sales_marketing: "wf_sales",
        RoleKey.project_manager: "wf_pm",
    }
    return EvidenceObject.model_validate(
        {
            "evidence_id": (
                f"ev-{role_abbreviations[role_key]}-{digest[:12]}"
            ),
            "identity_digest": digest,
            "source_id": f"src-wf_eval-{digest[12:24]}",
            "source_format": SourceFormat.csv,
            "source_locator": TabularSourceLocator(
                columns=["synthetic_metric"],
                row_range=(0, 0),
            ),
            "evidence_type": "workflow_evaluation_observation",
            "evidence_scope": EvidenceScope.internal_observation,
            "extraction_method": "deterministic",
            "finding": (
                f"Synthetic observation for {role_key.value} in "
                f"{scenario_id}."
            ),
            "supporting_evidence": (
                "Synthetic fixture value used only for offline workflow "
                "evaluation."
            ),
            "confidence": "high",
            "limitations": [
                "Synthetic evaluation evidence; not company-specific."
            ],
            "relevant_roles": [role_key.value],
            "decision_relevance": (
                f"Grounds the synthetic {role_key.value} fixture claim."
            ),
            "created_by": "evidence_builder",
            "status": EvidenceStatus.active,
            "invalidated_reason": None,
        }
    )


def build_workflow_scenario_inputs(
    scenario: WorkflowEvaluationScenario,
) -> WorkflowScenarioInputs:
    """Construct deterministic five-role planner inputs for one scenario."""
    if type(scenario) is not WorkflowEvaluationScenario:
        raise WorkflowEvaluationInputError(
            "scenario must be a WorkflowEvaluationScenario"
        )

    evidence_objects = tuple(
        _build_evidence(scenario.scenario_id, role_key)
        for role_key in _ROLE_EXECUTION_ORDER
    )
    evidence_by_role = dict(zip(_ROLE_EXECUTION_ORDER, evidence_objects))
    successful = set(scenario.successful_roles)
    failures = set(scenario.generation_failure_roles)

    role_outcomes: dict[RoleKey, RoleOutcome] = {}
    for role_key in _ROLE_EXECUTION_ORDER:
        if role_key in successful:
            evidence_id = evidence_by_role[role_key].evidence_id
            role_outcomes[role_key] = RoleView(
                role_key=role_key,
                role_concern=(
                    f"Synthetic workflow concern for {role_key.value}."
                ),
                key_findings=[
                    GroundedFinding(
                        claim=(
                            f"Synthetic grounded claim for {role_key.value}."
                        ),
                        evidence_references=[
                            EvidenceReference(evidence_id=evidence_id)
                        ],
                        confidence="high",
                    )
                ],
                risks_or_assumptions=[],
                missing_information=list(
                    scenario.role_missing_information.get(role_key, ())
                ),
                next_action=scenario.role_actions.get(role_key),
                dependency=scenario.role_dependencies.get(role_key),
                human_review_required=(
                    role_key in set(scenario.role_human_review_required)
                ),
            )
        elif role_key in failures:
            role_outcomes[role_key] = RoleGenerationFailure(
                role_key=role_key,
                failure_code="provider_error",
                reason=(
                    f"Synthetic generation failure for {role_key.value}."
                ),
            )
        else:
            role_outcomes[role_key] = InsufficientEvidence(
                role_key=role_key,
                reason=(
                    f"Synthetic fixture has insufficient evidence for "
                    f"{role_key.value}."
                ),
            )

    findings = [
        RiskFinding(
            risk_code=item.risk_code,
            severity=RiskSeverity.high,
            role_key=item.role_key,
            claim_index=item.claim_index,
            evidence_ids=[evidence_by_role[item.role_key].evidence_id],
            message=item.message,
            required_action=item.required_action,
            blocks_downstream=item.blocks_downstream,
            requires_human_review=item.requires_human_review,
        )
        for item in scenario.deterministic_findings
    ]
    deterministic_result = RiskReviewResult(
        findings=findings,
        reviewed_role_keys=list(_ROLE_EXECUTION_ORDER),
        has_blocking_risks=any(
            finding.blocks_downstream for finding in findings
        ),
        human_review_required=any(
            finding.requires_human_review for finding in findings
        ),
    )

    candidates = [
        SemanticRiskCandidate(
            risk_code=item.risk_code,
            role_key=item.role_key,
            claim_index=item.claim_index,
            evidence_ids=[evidence_by_role[item.role_key].evidence_id],
            explanation=(
                "Deterministic synthetic evaluation candidate; no model "
                "reasoning was used."
            ),
            review_question=item.review_question,
            confidence="medium",
            disposition=item.disposition,
        )
        for item in scenario.semantic_candidates
    ]
    successful_in_canonical_order = [
        role_key
        for role_key in _ROLE_EXECUTION_ORDER
        if role_key in successful
    ]
    semantic_result = SemanticRiskReviewResult(
        candidates=candidates,
        reviewed_role_keys=successful_in_canonical_order,
        reviewer_model=None,
        human_review_required=any(
            candidate.disposition in _QUALIFYING_DISPOSITIONS
            for candidate in candidates
        ),
    )
    return WorkflowScenarioInputs(
        role_outcomes=role_outcomes,
        evidence_objects=evidence_objects,
        deterministic_risk_result=deterministic_result,
        semantic_risk_result=semantic_result,
    )


def _step_signatures(plan: WorkflowPlan) -> tuple[str, ...]:
    """Return exact ordered ``kind:role`` signatures."""
    return tuple(
        f"{step.step_kind.value}:{step.owner_role.value}"
        for step in plan.steps
    )


def _step_sequence(step_id: str) -> int:
    """Convert a validated ``wf-NNN`` ID to its integer sequence."""
    return int(step_id.removeprefix("wf-"))


def _dependency_sequences(
    plan: WorkflowPlan,
) -> tuple[tuple[int, ...], ...]:
    """Convert every dependency ID list to integer sequences."""
    return tuple(
        tuple(
            _step_sequence(dependency_id)
            for dependency_id in step.dependency_step_ids
        )
        for step in plan.steps
    )


def _append_mismatch(
    failure_reasons: list[str],
    label: str,
    actual: Any,
    expected: Any,
) -> None:
    """Append one concise exact-comparison failure."""
    if actual != expected:
        failure_reasons.append(
            f"{label} mismatch: expected {expected!r}, got {actual!r}"
        )


def evaluate_workflow_scenario(
    scenario: WorkflowEvaluationScenario,
    plan: WorkflowPlan,
) -> WorkflowScenarioEvaluationResult:
    """Evaluate one plan with exact structural and source-preservation checks."""
    if type(scenario) is not WorkflowEvaluationScenario:
        raise WorkflowEvaluationInputError(
            "scenario must be a WorkflowEvaluationScenario"
        )
    if type(plan) is not WorkflowPlan:
        raise WorkflowEvaluationInputError("plan must be a WorkflowPlan")

    approved_inputs = build_workflow_scenario_inputs(scenario)
    actual_signatures = _step_signatures(plan)
    actual_dependencies = _dependency_sequences(plan)
    actual_blockers = tuple(
        _step_sequence(step_id) for step_id in plan.blocking_step_ids
    )
    actual_included = tuple(plan.included_role_keys)
    actual_action_statuses = {
        step.owner_role: step.status
        for step in plan.steps
        if step.step_kind is WorkflowStepKind.role_action
    }
    actual_gate_roles = tuple(
        step.owner_role
        for step in plan.steps
        if step.step_kind is WorkflowStepKind.semantic_review_gate
    )
    actual_action_roles = {
        step.owner_role
        for step in plan.steps
        if step.step_kind is WorkflowStepKind.role_action
    }

    expected = scenario.expected
    failure_reasons: list[str] = []
    _append_mismatch(
        failure_reasons,
        "plan_status",
        plan.plan_status,
        expected.plan_status,
    )
    _append_mismatch(
        failure_reasons,
        "step_signatures",
        actual_signatures,
        expected.step_signatures,
    )
    _append_mismatch(
        failure_reasons,
        "dependency_sequences",
        actual_dependencies,
        expected.dependency_sequences,
    )
    _append_mismatch(
        failure_reasons,
        "blocking_sequences",
        actual_blockers,
        expected.blocking_sequences,
    )
    _append_mismatch(
        failure_reasons,
        "included_role_keys",
        actual_included,
        expected.included_role_keys,
    )
    _append_mismatch(
        failure_reasons,
        "role_action_statuses",
        actual_action_statuses,
        expected.role_action_statuses,
    )
    _append_mismatch(
        failure_reasons,
        "semantic_gate_roles",
        actual_gate_roles,
        expected.semantic_gate_roles,
    )
    unexpected_present_actions = tuple(
        role_key
        for role_key in expected.absent_role_actions
        if role_key in actual_action_roles
    )
    if unexpected_present_actions:
        failure_reasons.append(
            "required absent role actions were present: "
            + ", ".join(role.value for role in unexpected_present_actions)
        )

    for step in plan.steps:
        if step.step_kind is WorkflowStepKind.role_action:
            approved_outcome = approved_inputs.role_outcomes[step.owner_role]
            expected_action = scenario.role_actions.get(step.owner_role)
            if expected_action is None or step.action != expected_action:
                failure_reasons.append(
                    f"role action source mismatch for {step.owner_role.value}"
                )
            if type(approved_outcome) is not RoleView:
                failure_reasons.append(
                    f"role action has no approved RoleView for "
                    f"{step.owner_role.value}"
                )
                continue
            expected_evidence_ids = list(
                _unique(
                    [
                        reference.evidence_id
                        for finding in approved_outcome.key_findings
                        for reference in finding.evidence_references
                    ]
                )
            )
            if step.supporting_evidence_ids != expected_evidence_ids:
                failure_reasons.append(
                    f"role action evidence lineage mismatch for "
                    f"{step.owner_role.value}"
                )
            expected_note = scenario.role_dependencies.get(step.owner_role)
            expected_notes = [expected_note] if expected_note is not None else []
            if step.dependency_notes != expected_notes:
                failure_reasons.append(
                    f"dependency note mismatch for {step.owner_role.value}"
                )
            expected_missing = list(
                scenario.role_missing_information.get(step.owner_role, ())
            )
            if step.missing_information != expected_missing:
                failure_reasons.append(
                    f"missing information mismatch for {step.owner_role.value}"
                )
            expected_deterministic_codes = list(
                _unique(
                    [
                        finding.risk_code
                        for finding in (
                            approved_inputs.deterministic_risk_result.findings
                        )
                        if finding.role_key is step.owner_role
                    ]
                )
            )
            if (
                step.deterministic_risk_codes
                != expected_deterministic_codes
            ):
                failure_reasons.append(
                    f"role action deterministic risk lineage mismatch for "
                    f"{step.owner_role.value}"
                )
            expected_semantic_codes = list(
                _unique(
                    [
                        candidate.risk_code
                        for candidate in (
                            approved_inputs.semantic_risk_result.candidates
                        )
                        if candidate.role_key is step.owner_role
                        and candidate.disposition
                        in _QUALIFYING_DISPOSITIONS
                    ]
                )
            )
            if step.semantic_risk_codes != expected_semantic_codes:
                failure_reasons.append(
                    f"role action semantic risk lineage mismatch for "
                    f"{step.owner_role.value}"
                )
            expected_human_review = (
                True
                if step.status
                in {
                    WorkflowStepStatus.blocked,
                    WorkflowStepStatus.pending_human_review,
                }
                else approved_outcome.human_review_required
            )
            if step.human_review_required != expected_human_review:
                failure_reasons.append(
                    f"role action human-review state mismatch for "
                    f"{step.owner_role.value}"
                )

    dependency_texts = set(scenario.role_dependencies.values())
    if any(step.action in dependency_texts for step in plan.steps):
        failure_reasons.append(
            "fixture dependency text became executable action text"
        )
    for role_key, dependency_text in scenario.role_dependencies.items():
        if any(
            dependency_text in step.dependency_notes
            and not (
                step.step_kind is WorkflowStepKind.role_action
                and step.owner_role is role_key
            )
            for step in plan.steps
        ):
            failure_reasons.append(
                f"dependency text for {role_key.value} appeared outside its "
                "role action note"
            )

    grouped_findings: dict[
        tuple[RoleKey, str],
        list[RiskFinding],
    ] = {}
    for finding in approved_inputs.deterministic_risk_result.findings:
        grouped_findings.setdefault(
            (finding.role_key, finding.required_action),
            [],
        ).append(finding)
    actual_resolution_steps = [
        step
        for step in plan.steps
        if step.step_kind
        is WorkflowStepKind.deterministic_risk_resolution
    ]
    for (role_key, action), findings in grouped_findings.items():
        matching = [
            step
            for step in actual_resolution_steps
            if step.owner_role is role_key and step.action == action
        ]
        if len(matching) != 1:
            failure_reasons.append(
                "deterministic findings sharing exact required_action did "
                f"not form one step for {role_key.value}"
            )
            continue
        step = matching[0]
        expected_codes = list(
            _unique([finding.risk_code for finding in findings])
        )
        expected_messages = list(
            _unique([finding.message for finding in findings])
        )
        expected_evidence_ids = list(
            _unique(
                [
                    evidence_id
                    for finding in findings
                    for evidence_id in finding.evidence_ids
                ]
            )
        )
        expected_blocks_downstream = any(
            finding.blocks_downstream for finding in findings
        )
        expected_human_review = any(
            finding.requires_human_review for finding in findings
        )
        expected_status = (
            WorkflowStepStatus.pending_human_review
            if expected_human_review
            else WorkflowStepStatus.ready
        )
        if step.deterministic_risk_codes != expected_codes:
            failure_reasons.append(
                f"deterministic risk-code order mismatch for {role_key.value}"
            )
        if step.dependency_notes != expected_messages:
            failure_reasons.append(
                f"deterministic messages were not preserved for "
                f"{role_key.value}"
            )
        if step.supporting_evidence_ids != expected_evidence_ids:
            failure_reasons.append(
                f"deterministic evidence lineage mismatch for "
                f"{role_key.value}"
            )
        if step.blocks_downstream != expected_blocks_downstream:
            failure_reasons.append(
                f"deterministic blocker state mismatch for {role_key.value}"
            )
        if step.human_review_required != expected_human_review:
            failure_reasons.append(
                f"deterministic human-review state mismatch for "
                f"{role_key.value}"
            )
        if step.status is not expected_status:
            failure_reasons.append(
                f"deterministic step status mismatch for {role_key.value}"
            )
    approved_resolution_keys = set(grouped_findings)
    if any(
        (step.owner_role, step.action) not in approved_resolution_keys
        for step in actual_resolution_steps
    ):
        failure_reasons.append(
            "plan contains a deterministic resolution action not present "
            "in the fixture"
        )

    qualifying_by_role: dict[
        RoleKey,
        list[SemanticRiskCandidate],
    ] = {}
    for candidate in approved_inputs.semantic_risk_result.candidates:
        if candidate.disposition in _QUALIFYING_DISPOSITIONS:
            qualifying_by_role.setdefault(
                candidate.role_key,
                [],
            ).append(candidate)
    actual_gates = [
        step
        for step in plan.steps
        if step.step_kind is WorkflowStepKind.semantic_review_gate
    ]
    for role_key, candidates in qualifying_by_role.items():
        matching = [
            step for step in actual_gates if step.owner_role is role_key
        ]
        if len(matching) != 1:
            failure_reasons.append(
                f"qualifying semantic candidates did not form one gate for "
                f"{role_key.value}"
            )
            continue
        gate = matching[0]
        expected_codes = list(
            _unique([candidate.risk_code for candidate in candidates])
        )
        expected_questions = list(
            _unique([candidate.review_question for candidate in candidates])
        )
        expected_evidence_ids = list(
            _unique(
                [
                    evidence_id
                    for candidate in candidates
                    for evidence_id in candidate.evidence_ids
                ]
            )
        )
        if gate.semantic_risk_codes != expected_codes:
            failure_reasons.append(
                f"semantic gate codes mismatch for {role_key.value}"
            )
        if gate.review_questions != expected_questions:
            failure_reasons.append(
                f"semantic gate question order mismatch for {role_key.value}"
            )
        if gate.supporting_evidence_ids != expected_evidence_ids:
            failure_reasons.append(
                f"semantic gate evidence lineage mismatch for "
                f"{role_key.value}"
            )
        if gate.blocks_downstream:
            failure_reasons.append(
                f"semantic gate incorrectly blocks for {role_key.value}"
            )
    if any(
        gate.owner_role not in qualifying_by_role for gate in actual_gates
    ):
        failure_reasons.append(
            "plan contains a semantic gate without a qualifying candidate"
        )

    if not plan.human_review_required:
        failure_reasons.append(
            "WorkflowPlan.human_review_required must remain true"
        )

    return WorkflowScenarioEvaluationResult(
        scenario_id=scenario.scenario_id,
        passed=not failure_reasons,
        actual_plan_status=plan.plan_status,
        actual_step_signatures=actual_signatures,
        actual_dependency_sequences=actual_dependencies,
        actual_blocking_sequences=actual_blockers,
        actual_included_role_keys=actual_included,
        failure_reasons=tuple(failure_reasons),
    )


def _validate_scenario_sequence(
    scenarios: Sequence[WorkflowEvaluationScenario],
) -> tuple[WorkflowEvaluationScenario, ...]:
    """Freeze and validate a caller-supplied scenario sequence."""
    if not isinstance(scenarios, Sequence) or isinstance(
        scenarios,
        (str, bytes),
    ):
        raise WorkflowEvaluationInputError(
            "scenarios must be a sequence of WorkflowEvaluationScenario values"
        )
    frozen = tuple(scenarios)
    if any(type(scenario) is not WorkflowEvaluationScenario for scenario in frozen):
        raise WorkflowEvaluationInputError(
            "scenarios contains an unsupported value type"
        )
    scenario_ids = [scenario.scenario_id for scenario in frozen]
    if len(scenario_ids) != len(set(scenario_ids)):
        raise WorkflowEvaluationInputError(
            "scenarios must not contain duplicate scenario IDs"
        )
    return frozen


def run_workflow_evaluation(
    scenarios: Sequence[WorkflowEvaluationScenario],
) -> WorkflowEvaluationSummary:
    """Build, plan, and evaluate every scenario in caller-provided order."""
    frozen = _validate_scenario_sequence(scenarios)
    results: list[WorkflowScenarioEvaluationResult] = []
    for scenario in frozen:
        inputs = build_workflow_scenario_inputs(scenario)
        plan = plan_workflow(
            inputs.role_outcomes,
            inputs.evidence_objects,
            inputs.deterministic_risk_result,
            inputs.semantic_risk_result,
        )
        results.append(evaluate_workflow_scenario(scenario, plan))
    return WorkflowEvaluationSummary(scenario_results=tuple(results))


def _build_flat_action_plan(
    scenario: WorkflowEvaluationScenario,
) -> WorkflowPlan:
    """Build the transparent non-LLM flat action-list baseline."""
    action_roles = [
        role_key
        for role_key in _WORKFLOW_ROLE_ORDER
        if role_key in set(scenario.successful_roles)
        and role_key in scenario.role_actions
    ]
    steps = [
        WorkflowStep(
            step_id=f"wf-{sequence:03d}",
            sequence=sequence,
            step_kind=WorkflowStepKind.role_action,
            owner_role=role_key,
            action=scenario.role_actions[role_key],
            supporting_evidence_ids=[],
            dependency_step_ids=[],
            dependency_notes=[],
            missing_information=[],
            deterministic_risk_codes=[],
            semantic_risk_codes=[],
            review_questions=[],
            status=WorkflowStepStatus.ready,
            blocks_downstream=False,
            human_review_required=False,
        )
        for sequence, role_key in enumerate(action_roles, start=1)
    ]
    included_roles = [
        role_key
        for role_key in _ROLE_EXECUTION_ORDER
        if role_key in set(scenario.successful_roles)
    ]
    return WorkflowPlan(
        steps=steps,
        plan_status=(
            WorkflowPlanStatus.ready_for_human_review
            if steps
            else WorkflowPlanStatus.no_actionable_steps
        ),
        included_role_keys=included_roles,
        blocking_step_ids=[],
        human_review_required=True,
        planning_method="deterministic_v1",
    )


def evaluate_flat_action_list_baseline(
    scenarios: Sequence[WorkflowEvaluationScenario],
) -> WorkflowEvaluationSummary:
    """Evaluate a naive flat action list against governed expectations."""
    frozen = _validate_scenario_sequence(scenarios)
    return WorkflowEvaluationSummary(
        scenario_results=tuple(
            evaluate_workflow_scenario(
                scenario,
                _build_flat_action_plan(scenario),
            )
            for scenario in frozen
        )
    )
