"""Deterministic evaluation for Human Review and Decision Memo composition.

The fixed Task 9C pack constructs synthetic production WorkflowPlan and
EvidenceObject values, records caller-supplied simulated review decisions,
and evaluates the resulting DecisionMemo through exact structural
comparisons. It performs no provider, model, network, environment, timestamp,
randomness, or fuzzy-matching work.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from app.human_review import review_workflow_plan, workflow_plan_digest
from app.memo_generator import DecisionMemoInputError, compose_decision_memo
from app.schemas import (
    DecisionMemo,
    DecisionMemoAction,
    DecisionMemoActionOrigin,
    DecisionMemoRejectedStep,
    DecisionMemoReviewGate,
    DecisionMemoStatus,
    EvidenceObject,
    EvidenceScope,
    EvidenceStatus,
    HumanReviewDecision,
    HumanReviewSession,
    HumanReviewSessionStatus,
    HumanReviewStepInput,
    RiskCode,
    RoleKey,
    SemanticRiskCode,
    SourceFormat,
    TabularSourceLocator,
    WorkflowPlan,
    WorkflowPlanStatus,
    WorkflowStep,
    WorkflowStepKind,
    WorkflowStepStatus,
)


DEFAULT_MEMO_SCENARIO_PATH = (
    Path(__file__).resolve().parents[1]
    / "examples"
    / "scenarios"
    / "memo_v1.json"
)

_REQUIRED_SCENARIO_IDS = (
    "M1_complete_all_accept",
    "M2_rejected_action_auditable",
    "M3_human_revision_requires_revalidation",
    "M4_blocker_persists_after_review",
    "M5_semantic_gate_non_authoritative",
    "M6_missing_information_survives_rejection",
    "M7_incomplete_review_fails_closed",
    "M8_empty_plan_acknowledged",
)
_PLAN_TEMPLATE_KEYS = (
    "healthy",
    "governed",
    "governed_missing_information",
    "blocking",
    "empty",
)
_TEMPLATE_STEP_IDS = {
    "healthy": ("wf-001", "wf-002"),
    "governed": ("wf-001", "wf-002", "wf-003", "wf-004"),
    "governed_missing_information": (
        "wf-001",
        "wf-002",
        "wf-003",
        "wf-004",
    ),
    "blocking": ("wf-001", "wf-002", "wf-003", "wf-004"),
    "empty": (),
}
_TEMPLATE_ORIGINAL_ACTIONS = {
    "healthy": {
        "wf-001": "Review the evidence-backed retention priority.",
        "wf-002": "Coordinate the reviewed action sequence.",
    },
    "governed": {
        "wf-001": "Confirm and disclose the analytical limitation.",
        "wf-002": (
            "Review semantic risk candidates for executive before "
            "downstream action."
        ),
        "wf-003": "Review the bounded retention priority.",
        "wf-004": "Coordinate owners and review checkpoints.",
    },
    "governed_missing_information": {
        "wf-001": "Confirm and disclose the analytical limitation.",
        "wf-002": (
            "Review semantic risk candidates for executive before "
            "downstream action."
        ),
        "wf-003": "Review the bounded retention priority.",
        "wf-004": "Coordinate owners and review checkpoints.",
    },
    "blocking": {
        "wf-001": "Confirm and disclose the analytical limitation.",
        "wf-002": (
            "Review semantic risk candidates for executive before "
            "downstream action."
        ),
        "wf-003": "Review the bounded retention priority.",
        "wf-004": "Coordinate owners and review checkpoints.",
    },
    "empty": {},
}
_GOVERNED_TEMPLATE_KEYS = {
    "governed",
    "governed_missing_information",
    "blocking",
}
_STEP_ID_RE = re.compile(r"^wf-[0-9]{3}$")
_EVIDENCE_ID_RE = re.compile(
    r"^ev-[a-z0-9_]{1,12}-[0-9a-f]{12}$"
)


class MemoEvaluationInputError(ValueError):
    """Raised when memo evaluation input is malformed or ambiguous."""


class _FrozenEvaluationModel(BaseModel):
    """Shared immutable, extra-forbidding evaluation model."""

    model_config = ConfigDict(extra="forbid", frozen=True)


def _non_blank(value: str, *, field_name: str) -> str:
    """Return non-blank text or raise a validation error."""
    if not value or not value.strip():
        raise ValueError(f"{field_name} must not be blank")
    return value


def _validate_step_ids(
    values: Sequence[str],
    *,
    field_name: str,
) -> None:
    """Require valid, duplicate-free workflow step IDs."""
    if any(not _STEP_ID_RE.fullmatch(value) for value in values):
        raise ValueError(f"{field_name} values must match wf-[0-9]{{3}}")
    if len(values) != len(set(values)):
        raise ValueError(f"{field_name} must not contain duplicates")


class MemoScenarioExpectation(_FrozenEvaluationModel):
    """Exact expected Decision Memo outcome for one fixed scenario."""

    expected_outcome: Literal["memo", "decision_memo_input_error"]
    memo_status: DecisionMemoStatus | None
    retained_step_ids: tuple[str, ...]
    review_gate_step_ids: tuple[str, ...]
    review_gate_decisions: dict[str, HumanReviewDecision]
    rejected_step_ids: tuple[str, ...]
    unresolved_blocking_step_ids: tuple[str, ...]
    human_revision_step_ids: tuple[str, ...]
    revised_actions: dict[str, str]
    evidence_ids: tuple[str, ...]
    missing_information: dict[str, tuple[str, ...]]
    deterministic_risk_codes: tuple[RiskCode, ...]
    semantic_risk_codes: tuple[SemanticRiskCode, ...]
    control_notices: tuple[str, ...]
    no_action_acknowledged: bool = Field(strict=True)

    @field_validator(
        "retained_step_ids",
        "review_gate_step_ids",
        "rejected_step_ids",
        "unresolved_blocking_step_ids",
        "human_revision_step_ids",
    )
    @classmethod
    def step_id_tuples_are_valid_unique(
        cls,
        values: tuple[str, ...],
        info: Any,
    ) -> tuple[str, ...]:
        """Reject malformed or repeated step IDs."""
        _validate_step_ids(values, field_name=info.field_name)
        if values != tuple(
            sorted(values, key=lambda value: int(value.removeprefix("wf-")))
        ):
            raise ValueError(f"{info.field_name} must preserve plan order")
        return values

    @field_validator("evidence_ids")
    @classmethod
    def evidence_ids_are_unique(
        cls,
        values: tuple[str, ...],
    ) -> tuple[str, ...]:
        """Reject repeated Evidence IDs."""
        if any(not _EVIDENCE_ID_RE.fullmatch(value) for value in values):
            raise ValueError("evidence_ids contains an invalid Evidence ID")
        if len(values) != len(set(values)):
            raise ValueError("evidence_ids must not contain duplicates")
        return values

    @field_validator(
        "deterministic_risk_codes",
        "semantic_risk_codes",
    )
    @classmethod
    def risk_codes_are_unique(
        cls,
        values: tuple[Any, ...],
        info: Any,
    ) -> tuple[Any, ...]:
        """Reject repeated aggregate risk codes."""
        if len(values) != len(set(values)):
            raise ValueError(f"{info.field_name} must not contain duplicates")
        return values

    @field_validator("control_notices")
    @classmethod
    def control_notices_are_unique_non_blank(
        cls,
        values: tuple[str, ...],
    ) -> tuple[str, ...]:
        """Reject blank or repeated control notices."""
        if any(not value or not value.strip() for value in values):
            raise ValueError("control_notices must not contain blank values")
        if len(values) != len(set(values)):
            raise ValueError("control_notices must not contain duplicates")
        return values

    @field_validator(
        "review_gate_decisions",
        "revised_actions",
        "missing_information",
    )
    @classmethod
    def mapping_keys_are_step_ids(
        cls,
        values: dict[str, Any],
        info: Any,
    ) -> dict[str, Any]:
        """Require valid workflow IDs for every expectation mapping."""
        _validate_step_ids(
            tuple(values),
            field_name=f"{info.field_name} keys",
        )
        return values

    @field_validator("revised_actions")
    @classmethod
    def revised_action_text_is_non_blank(
        cls,
        values: dict[str, str],
    ) -> dict[str, str]:
        """Reject blank expected revision text."""
        for value in values.values():
            _non_blank(value, field_name="revised_actions")
        return values

    @field_validator("missing_information")
    @classmethod
    def missing_information_is_clean(
        cls,
        values: dict[str, tuple[str, ...]],
    ) -> dict[str, tuple[str, ...]]:
        """Reject blank or repeated expected information gaps."""
        for items in values.values():
            if not items:
                raise ValueError(
                    "missing_information values must not be empty"
                )
            if any(not item or not item.strip() for item in items):
                raise ValueError(
                    "missing_information must not contain blank values"
                )
            if len(items) != len(set(items)):
                raise ValueError(
                    "missing_information must not contain duplicates"
                )
        return values

    @model_validator(mode="after")
    def expectation_is_consistent(self) -> "MemoScenarioExpectation":
        """Enforce successful-memo and expected-error field boundaries."""
        if tuple(self.revised_actions) != self.human_revision_step_ids:
            raise ValueError(
                "human_revision_step_ids must exactly equal revised_actions "
                "keys in plan order"
            )
        if tuple(self.review_gate_decisions) != self.review_gate_step_ids:
            raise ValueError(
                "review_gate_decisions keys must exactly equal "
                "review_gate_step_ids"
            )

        if self.expected_outcome == "memo":
            if self.memo_status is None:
                raise ValueError("memo outcome requires memo_status")
            if not self.control_notices:
                raise ValueError(
                    "memo outcome requires at least one control notice"
                )
        else:
            memo_sections = (
                self.retained_step_ids,
                self.review_gate_step_ids,
                self.review_gate_decisions,
                self.rejected_step_ids,
                self.unresolved_blocking_step_ids,
                self.human_revision_step_ids,
                self.revised_actions,
                self.evidence_ids,
                self.missing_information,
                self.deterministic_risk_codes,
                self.semantic_risk_codes,
                self.control_notices,
            )
            if self.memo_status is not None or any(memo_sections):
                raise ValueError(
                    "error outcome requires empty memo-section expectations"
                )
            if self.no_action_acknowledged:
                raise ValueError(
                    "error outcome cannot expect no-action acknowledgment"
                )

        if self.no_action_acknowledged != (
            self.memo_status is DecisionMemoStatus.no_action_acknowledged
        ):
            raise ValueError(
                "no_action_acknowledged must match no-action memo status"
            )
        return self


class MemoEvaluationScenario(_FrozenEvaluationModel):
    """One synthetic Human Review and Decision Memo scenario."""

    scenario_id: str
    title: str
    purpose: str
    plan_template: Literal[
        "healthy",
        "governed",
        "governed_missing_information",
        "blocking",
        "empty",
    ]
    decisions: dict[str, HumanReviewStepInput]
    no_action_acknowledged: bool = Field(strict=True)
    overall_note: str | None
    expected: MemoScenarioExpectation
    rationale: str
    demo_priority: bool = Field(strict=True)

    @field_validator("scenario_id", "title", "purpose", "rationale")
    @classmethod
    def required_text_is_non_blank(
        cls,
        value: str,
        info: Any,
    ) -> str:
        """Reject blank identifiers and prose."""
        return _non_blank(value, field_name=info.field_name)

    @field_validator("overall_note")
    @classmethod
    def overall_note_is_non_blank(
        cls,
        value: str | None,
    ) -> str | None:
        """Reject a blank optional overall note."""
        if value is not None:
            _non_blank(value, field_name="overall_note")
        return value

    @field_validator("decisions")
    @classmethod
    def decision_keys_are_valid(
        cls,
        values: dict[str, HumanReviewStepInput],
    ) -> dict[str, HumanReviewStepInput]:
        """Require valid, unique workflow IDs for decisions."""
        _validate_step_ids(tuple(values), field_name="decision keys")
        return values

    @model_validator(mode="after")
    def scenario_relationships_are_valid(self) -> "MemoEvaluationScenario":
        """Bind decisions and expectations to the selected fixed template."""
        step_ids = _TEMPLATE_STEP_IDS[self.plan_template]
        step_set = set(step_ids)
        decision_ids = tuple(self.decisions)
        if any(step_id not in step_set for step_id in decision_ids):
            raise ValueError(
                "decision keys must reference the selected plan template"
            )
        if self.plan_template == "empty":
            if decision_ids:
                raise ValueError("empty template permits no step decisions")
        elif self.no_action_acknowledged:
            raise ValueError(
                "non-empty templates reject no_action_acknowledged=true"
            )

        if (
            self.plan_template in _GOVERNED_TEMPLATE_KEYS
            and self.decisions.get("wf-002") is not None
            and self.decisions["wf-002"].decision
            is HumanReviewDecision.revise
        ):
            raise ValueError("semantic gate wf-002 cannot be revised")

        original_actions = _TEMPLATE_ORIGINAL_ACTIONS[self.plan_template]
        for step_id, decision in self.decisions.items():
            if (
                decision.decision is HumanReviewDecision.revise
                and decision.revised_action == original_actions[step_id]
            ):
                raise ValueError(
                    "revised action must differ from template original action"
                )

        expected_step_ids = (
            self.expected.retained_step_ids
            + self.expected.review_gate_step_ids
            + self.expected.rejected_step_ids
        )
        expected_mapping_ids = (
            tuple(self.expected.revised_actions)
            + tuple(self.expected.missing_information)
            + tuple(self.expected.review_gate_decisions)
            + self.expected.unresolved_blocking_step_ids
        )
        if any(
            step_id not in step_set
            for step_id in expected_step_ids + expected_mapping_ids
        ):
            raise ValueError(
                "memo expectations must reference the selected plan template"
            )

        if self.expected.expected_outcome == "memo":
            if set(decision_ids) != step_set:
                raise ValueError(
                    "memo expectation requires a decision for every plan step"
                )
            if (
                len(expected_step_ids) != len(step_ids)
                or set(expected_step_ids) != step_set
                or len(expected_step_ids) != len(set(expected_step_ids))
            ):
                raise ValueError(
                    "memo primary sections must partition template steps"
                )
            if self.plan_template == "empty":
                if (
                    not self.no_action_acknowledged
                    or not self.expected.no_action_acknowledged
                ):
                    raise ValueError(
                        "successful empty template must expect acknowledgment"
                    )
            elif self.expected.no_action_acknowledged:
                raise ValueError(
                    "non-empty memo cannot expect no-action acknowledgment"
                )

            revised_ids = tuple(
                step_id
                for step_id in step_ids
                if self.decisions[step_id].decision
                is HumanReviewDecision.revise
            )
            if revised_ids != self.expected.human_revision_step_ids:
                raise ValueError(
                    "expected revisions must match fixture decisions"
                )
            for step_id, revised_action in (
                self.expected.revised_actions.items()
            ):
                if (
                    self.decisions[step_id].revised_action
                    != revised_action
                ):
                    raise ValueError(
                        "expected revised action must match fixture decision"
                    )

            gate_ids = tuple(
                step_id
                for step_id in step_ids
                if (
                    self.plan_template in _GOVERNED_TEMPLATE_KEYS
                    and step_id == "wf-002"
                )
            )
            if self.expected.review_gate_step_ids != gate_ids:
                raise ValueError(
                    "expected review gates must match template gate steps"
                )
            for step_id in gate_ids:
                if (
                    self.expected.review_gate_decisions[step_id]
                    is not self.decisions[step_id].decision
                ):
                    raise ValueError(
                        "expected gate decisions must match fixture decisions"
                    )

            retained_ids = tuple(
                step_id
                for step_id in step_ids
                if (
                    step_id not in set(gate_ids)
                    and self.decisions[step_id].decision
                    is not HumanReviewDecision.reject
                )
            )
            rejected_ids = tuple(
                step_id
                for step_id in step_ids
                if (
                    step_id not in set(gate_ids)
                    and self.decisions[step_id].decision
                    is HumanReviewDecision.reject
                )
            )
            if self.expected.retained_step_ids != retained_ids:
                raise ValueError(
                    "expected retained steps must match fixture decisions"
                )
            if self.expected.rejected_step_ids != rejected_ids:
                raise ValueError(
                    "expected rejected steps must match fixture decisions"
                )
        return self


class MemoScenarioEvaluationResult(_FrozenEvaluationModel):
    """Exact comparison result for one memo evaluation scenario."""

    scenario_id: str
    passed: bool
    expected_outcome: Literal["memo", "decision_memo_input_error"]
    actual_outcome: Literal[
        "memo",
        "decision_memo_input_error",
        "unexpected_error",
    ]
    actual_memo_status: DecisionMemoStatus | None
    actual_retained_step_ids: tuple[str, ...]
    actual_review_gate_step_ids: tuple[str, ...]
    actual_rejected_step_ids: tuple[str, ...]
    actual_unresolved_blocking_step_ids: tuple[str, ...]
    actual_human_revision_step_ids: tuple[str, ...]
    actual_evidence_ids: tuple[str, ...]
    failure_reasons: tuple[str, ...]


@dataclass(frozen=True)
class MemoEvaluationSummary:
    """Derived aggregate results for a memo scenario sequence."""

    scenario_results: tuple[MemoScenarioEvaluationResult, ...]
    total_scenarios: int = field(init=False)
    passed_scenarios: int = field(init=False)
    failed_scenarios: int = field(init=False)
    pass_rate: float = field(init=False)

    def __post_init__(self) -> None:
        """Derive counts and reject duplicate or unsupported results."""
        if any(
            type(result) is not MemoScenarioEvaluationResult
            for result in self.scenario_results
        ):
            raise MemoEvaluationInputError(
                "scenario_results must contain only "
                "MemoScenarioEvaluationResult values"
            )
        scenario_ids = [
            result.scenario_id for result in self.scenario_results
        ]
        if len(scenario_ids) != len(set(scenario_ids)):
            raise MemoEvaluationInputError(
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
class MemoScenarioInputs:
    """Exact production inputs constructed for one memo scenario."""

    workflow_plan: WorkflowPlan
    evidence_objects: tuple[EvidenceObject, ...]
    decisions: dict[str, HumanReviewStepInput]
    no_action_acknowledged: bool
    overall_note: str | None


@dataclass(frozen=True)
class _PolishedActionSummary:
    """Minimal deterministic action summary used by the audit baseline."""

    visible_step_ids: tuple[str, ...]
    visible_actions: tuple[str, ...]
    action_count_summary: str
    review_session_status: HumanReviewSessionStatus
    human_review_complete: bool


def _reject_duplicate_json_keys(
    pairs: list[tuple[str, Any]],
) -> dict[str, Any]:
    """Reject duplicate keys at every JSON object level."""
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object key")
        result[key] = value
    return result


def _load_json(path: Path) -> Any:
    """Read JSON without exposing fixture contents in normalized errors."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        raise MemoEvaluationInputError(
            "unable to read memo evaluation fixture"
        ) from None
    try:
        return json.loads(
            text,
            object_pairs_hook=_reject_duplicate_json_keys,
        )
    except (json.JSONDecodeError, ValueError):
        raise MemoEvaluationInputError(
            "memo evaluation fixture contains invalid JSON"
        ) from None


def load_memo_scenarios(
    path: Path = DEFAULT_MEMO_SCENARIO_PATH,
) -> tuple[MemoEvaluationScenario, ...]:
    """Load the exact M1-M8 memo evaluation pack in approved order."""
    raw_scenarios = _load_json(path)
    if not isinstance(raw_scenarios, list):
        raise MemoEvaluationInputError(
            "memo evaluation fixture top-level value must be a list"
        )

    scenarios: list[MemoEvaluationScenario] = []
    for index, raw_scenario in enumerate(raw_scenarios):
        if not isinstance(raw_scenario, Mapping):
            raise MemoEvaluationInputError(
                f"memo scenario at index {index} must be a JSON object"
            )
        try:
            scenarios.append(
                MemoEvaluationScenario.model_validate(raw_scenario)
            )
        except (ValidationError, TypeError, ValueError):
            raise MemoEvaluationInputError(
                f"invalid memo evaluation scenario at index {index}"
            ) from None

    scenario_ids = tuple(scenario.scenario_id for scenario in scenarios)
    if len(scenario_ids) != len(set(scenario_ids)):
        raise MemoEvaluationInputError(
            "memo evaluation fixture contains duplicate scenario IDs"
        )
    missing = tuple(
        scenario_id
        for scenario_id in _REQUIRED_SCENARIO_IDS
        if scenario_id not in scenario_ids
    )
    if missing:
        raise MemoEvaluationInputError(
            "memo evaluation fixture is missing required scenario IDs"
        )
    extras = tuple(
        scenario_id
        for scenario_id in scenario_ids
        if scenario_id not in set(_REQUIRED_SCENARIO_IDS)
    )
    if extras:
        raise MemoEvaluationInputError(
            "memo evaluation fixture contains unapproved scenario IDs"
        )
    if scenario_ids != _REQUIRED_SCENARIO_IDS:
        raise MemoEvaluationInputError(
            "memo evaluation scenario IDs must appear in approved M1-M8 order"
        )
    return tuple(scenarios)


def _build_evidence(index: int, role_key: RoleKey) -> EvidenceObject:
    """Build one fixed active synthetic internal observation."""
    return EvidenceObject.model_validate(
        {
            "evidence_id": f"ev-memo_eval-{index:012d}",
            "identity_digest": f"{index:x}" * 64,
            "source_id": f"src-memo_eval-{index:012d}",
            "source_format": SourceFormat.csv,
            "source_locator": TabularSourceLocator(
                columns=["synthetic_metric"],
                row_range=(index, index),
            ),
            "evidence_type": "memo_evaluation_observation",
            "evidence_scope": EvidenceScope.internal_observation,
            "extraction_method": "deterministic",
            "finding": (
                f"Synthetic internal observation {index} for memo evaluation."
            ),
            "supporting_evidence": (
                f"Synthetic deterministic fixture value {index}."
            ),
            "confidence": "high",
            "limitations": [
                "Synthetic evaluation evidence; not company-specific."
            ],
            "relevant_roles": [role_key.value],
            "decision_relevance": (
                f"Grounds synthetic memo evaluation step {index}."
            ),
            "created_by": "evidence_builder",
            "status": EvidenceStatus.active,
            "invalidated_reason": None,
        }
    )


def _healthy_plan() -> WorkflowPlan:
    """Build the fixed two-action healthy plan."""
    evidence_ids = (
        "ev-memo_eval-000000000001",
        "ev-memo_eval-000000000002",
    )
    return WorkflowPlan(
        steps=[
            WorkflowStep(
                step_id="wf-001",
                sequence=1,
                step_kind=WorkflowStepKind.role_action,
                owner_role=RoleKey.executive,
                action="Review the evidence-backed retention priority.",
                supporting_evidence_ids=[evidence_ids[0]],
                dependency_step_ids=[],
                dependency_notes=[],
                missing_information=[],
                deterministic_risk_codes=[],
                semantic_risk_codes=[],
                review_questions=[],
                status=WorkflowStepStatus.ready,
                blocks_downstream=False,
                human_review_required=False,
            ),
            WorkflowStep(
                step_id="wf-002",
                sequence=2,
                step_kind=WorkflowStepKind.role_action,
                owner_role=RoleKey.project_manager,
                action="Coordinate the reviewed action sequence.",
                supporting_evidence_ids=[evidence_ids[1]],
                dependency_step_ids=["wf-001"],
                dependency_notes=[],
                missing_information=[],
                deterministic_risk_codes=[],
                semantic_risk_codes=[],
                review_questions=[],
                status=WorkflowStepStatus.ready,
                blocks_downstream=False,
                human_review_required=False,
            ),
        ],
        plan_status=WorkflowPlanStatus.ready_for_human_review,
        included_role_keys=[
            RoleKey.executive,
            RoleKey.project_manager,
        ],
        blocking_step_ids=[],
        human_review_required=True,
        planning_method="deterministic_v1",
    )


def _governed_plan(
    *,
    missing_information: bool,
    blocking: bool,
) -> WorkflowPlan:
    """Build one governed four-step plan variant."""
    evidence_ids = tuple(
        f"ev-memo_eval-{index:012d}" for index in range(1, 5)
    )
    return WorkflowPlan(
        steps=[
            WorkflowStep(
                step_id="wf-001",
                sequence=1,
                step_kind=(
                    WorkflowStepKind.deterministic_risk_resolution
                ),
                owner_role=RoleKey.data_analyst,
                action="Confirm and disclose the analytical limitation.",
                supporting_evidence_ids=[evidence_ids[0]],
                dependency_step_ids=[],
                dependency_notes=[],
                missing_information=[],
                deterministic_risk_codes=[
                    RiskCode.assumption_not_declared
                ],
                semantic_risk_codes=[],
                review_questions=[],
                status=(
                    WorkflowStepStatus.pending_human_review
                    if blocking
                    else WorkflowStepStatus.ready
                ),
                blocks_downstream=blocking,
                human_review_required=blocking,
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
                supporting_evidence_ids=[evidence_ids[1]],
                dependency_step_ids=["wf-001"],
                dependency_notes=[],
                missing_information=[],
                deterministic_risk_codes=[],
                semantic_risk_codes=[
                    SemanticRiskCode.citation_claim_mismatch
                ],
                review_questions=[
                    "Does the citation support the executive conclusion?"
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
                action="Review the bounded retention priority.",
                supporting_evidence_ids=[evidence_ids[2]],
                dependency_step_ids=["wf-001", "wf-002"],
                dependency_notes=[],
                missing_information=(
                    ["Validated customer-identifier coverage."]
                    if missing_information
                    else []
                ),
                deterministic_risk_codes=[],
                semantic_risk_codes=[
                    SemanticRiskCode.unsupported_company_specific_claim
                ],
                review_questions=[],
                status=(
                    WorkflowStepStatus.blocked
                    if blocking
                    else WorkflowStepStatus.pending_human_review
                ),
                blocks_downstream=False,
                human_review_required=True,
            ),
            WorkflowStep(
                step_id="wf-004",
                sequence=4,
                step_kind=WorkflowStepKind.role_action,
                owner_role=RoleKey.project_manager,
                action="Coordinate owners and review checkpoints.",
                supporting_evidence_ids=[evidence_ids[3]],
                dependency_step_ids=[
                    "wf-001",
                    "wf-002",
                    "wf-003",
                ],
                dependency_notes=[],
                missing_information=[],
                deterministic_risk_codes=[],
                semantic_risk_codes=[],
                review_questions=[],
                status=(
                    WorkflowStepStatus.blocked
                    if blocking
                    else WorkflowStepStatus.pending_human_review
                ),
                blocks_downstream=False,
                human_review_required=True,
            ),
        ],
        plan_status=(
            WorkflowPlanStatus.blocked
            if blocking
            else WorkflowPlanStatus.ready_for_human_review
        ),
        included_role_keys=[
            RoleKey.executive,
            RoleKey.data_analyst,
            RoleKey.project_manager,
        ],
        blocking_step_ids=["wf-001"] if blocking else [],
        human_review_required=True,
        planning_method="deterministic_v1",
    )


def _empty_plan() -> WorkflowPlan:
    """Build the fixed explicitly reviewable empty plan."""
    return WorkflowPlan(
        steps=[],
        plan_status=WorkflowPlanStatus.no_actionable_steps,
        included_role_keys=[RoleKey.executive],
        blocking_step_ids=[],
        human_review_required=True,
        planning_method="deterministic_v1",
    )


def _build_plan(plan_template: str) -> WorkflowPlan:
    """Build one selected fixed production WorkflowPlan."""
    if plan_template == "healthy":
        return _healthy_plan()
    if plan_template == "governed":
        return _governed_plan(
            missing_information=False,
            blocking=False,
        )
    if plan_template == "governed_missing_information":
        return _governed_plan(
            missing_information=True,
            blocking=False,
        )
    if plan_template == "blocking":
        return _governed_plan(
            missing_information=False,
            blocking=True,
        )
    if plan_template == "empty":
        return _empty_plan()
    raise MemoEvaluationInputError("unsupported memo plan template")


def build_memo_scenario_inputs(
    scenario: MemoEvaluationScenario,
) -> MemoScenarioInputs:
    """Build stable production inputs for one validated memo scenario."""
    if type(scenario) is not MemoEvaluationScenario:
        raise MemoEvaluationInputError(
            "scenario must be exactly a MemoEvaluationScenario"
        )
    workflow_plan = _build_plan(scenario.plan_template)
    evidence_roles = (
        (RoleKey.executive, RoleKey.project_manager)
        if scenario.plan_template == "healthy"
        else (
            (
                RoleKey.data_analyst,
                RoleKey.executive,
                RoleKey.executive,
                RoleKey.project_manager,
            )
            if scenario.plan_template != "empty"
            else ()
        )
    )
    evidence_objects = tuple(
        _build_evidence(index, role_key)
        for index, role_key in enumerate(evidence_roles, start=1)
    )
    decisions = {
        step_id: HumanReviewStepInput.model_validate(
            decision.model_dump()
        )
        for step_id, decision in scenario.decisions.items()
    }
    return MemoScenarioInputs(
        workflow_plan=workflow_plan,
        evidence_objects=evidence_objects,
        decisions=decisions,
        no_action_acknowledged=scenario.no_action_acknowledged,
        overall_note=scenario.overall_note,
    )


def _append_mismatch(
    failure_reasons: list[str],
    label: str,
    actual: Any,
    expected: Any,
) -> None:
    """Append one concise exact-comparison failure."""
    if actual != expected:
        failure_reasons.append(f"{label} mismatch")


def _expected_evidence_snapshots(
    inputs: MemoScenarioInputs,
    evidence_ids: tuple[str, ...],
) -> tuple[dict[str, Any], ...]:
    """Return exact memo snapshot fields for expected Evidence IDs."""
    registry = {
        evidence.evidence_id: evidence
        for evidence in inputs.evidence_objects
    }
    return tuple(
        {
            "evidence_id": registry[evidence_id].evidence_id,
            "source_id": registry[evidence_id].source_id,
            "evidence_scope": registry[evidence_id].evidence_scope,
            "finding": registry[evidence_id].finding,
            "confidence": registry[evidence_id].confidence,
            "limitations": list(registry[evidence_id].limitations),
            "decision_relevance": registry[evidence_id].decision_relevance,
        }
        for evidence_id in evidence_ids
    )


def _memo_result(
    scenario: MemoEvaluationScenario,
    memo: DecisionMemo,
    failure_reasons: list[str],
) -> MemoScenarioEvaluationResult:
    """Create the public evaluation result from one composed memo."""
    return MemoScenarioEvaluationResult(
        scenario_id=scenario.scenario_id,
        passed=not failure_reasons,
        expected_outcome=scenario.expected.expected_outcome,
        actual_outcome="memo",
        actual_memo_status=memo.memo_status,
        actual_retained_step_ids=tuple(
            action.step_id for action in memo.retained_actions
        ),
        actual_review_gate_step_ids=tuple(
            gate.step_id for gate in memo.review_gates
        ),
        actual_rejected_step_ids=tuple(
            step.step_id for step in memo.rejected_steps
        ),
        actual_unresolved_blocking_step_ids=tuple(
            memo.unresolved_blocking_step_ids
        ),
        actual_human_revision_step_ids=tuple(
            memo.human_revision_step_ids
        ),
        actual_evidence_ids=tuple(
            item.evidence_id for item in memo.evidence_items
        ),
        failure_reasons=tuple(failure_reasons),
    )


def _non_memo_result(
    scenario: MemoEvaluationScenario,
    *,
    actual_outcome: Literal[
        "decision_memo_input_error",
        "unexpected_error",
    ],
    failure_reasons: Sequence[str],
) -> MemoScenarioEvaluationResult:
    """Create a result for a normalized composition error."""
    return MemoScenarioEvaluationResult(
        scenario_id=scenario.scenario_id,
        passed=not failure_reasons,
        expected_outcome=scenario.expected.expected_outcome,
        actual_outcome=actual_outcome,
        actual_memo_status=None,
        actual_retained_step_ids=(),
        actual_review_gate_step_ids=(),
        actual_rejected_step_ids=(),
        actual_unresolved_blocking_step_ids=(),
        actual_human_revision_step_ids=(),
        actual_evidence_ids=(),
        failure_reasons=tuple(failure_reasons),
    )


def _evaluate_successful_memo(
    scenario: MemoEvaluationScenario,
    inputs: MemoScenarioInputs,
    human_review_session: HumanReviewSession,
    memo: DecisionMemo,
    plan_before: dict[str, Any],
    session_before: dict[str, Any],
    session_after: dict[str, Any],
) -> MemoScenarioEvaluationResult:
    """Compare every approved memo and source-preservation invariant."""
    expected = scenario.expected
    plan = inputs.workflow_plan
    plan_by_id = {step.step_id: step for step in plan.steps}
    reviewed_by_id = {
        reviewed.step_id: reviewed
        for reviewed in human_review_session.reviewed_steps
    }
    failure_reasons: list[str] = []

    _append_mismatch(
        failure_reasons,
        "expected_outcome",
        "memo",
        expected.expected_outcome,
    )
    _append_mismatch(
        failure_reasons,
        "memo_status",
        memo.memo_status,
        expected.memo_status,
    )
    _append_mismatch(
        failure_reasons,
        "plan_digest",
        memo.plan_digest,
        workflow_plan_digest(plan),
    )
    _append_mismatch(
        failure_reasons,
        "plan_step_ids",
        tuple(memo.plan_step_ids),
        tuple(step.step_id for step in plan.steps),
    )

    retained_ids = tuple(
        action.step_id for action in memo.retained_actions
    )
    gate_ids = tuple(gate.step_id for gate in memo.review_gates)
    rejected_ids = tuple(
        step.step_id for step in memo.rejected_steps
    )
    revision_ids = tuple(memo.human_revision_step_ids)
    evidence_ids = tuple(
        item.evidence_id for item in memo.evidence_items
    )
    _append_mismatch(
        failure_reasons,
        "retained_step_ids",
        retained_ids,
        expected.retained_step_ids,
    )
    _append_mismatch(
        failure_reasons,
        "review_gate_step_ids",
        gate_ids,
        expected.review_gate_step_ids,
    )
    _append_mismatch(
        failure_reasons,
        "review_gate_decisions",
        {gate.step_id: gate.decision for gate in memo.review_gates},
        expected.review_gate_decisions,
    )
    _append_mismatch(
        failure_reasons,
        "rejected_step_ids",
        rejected_ids,
        expected.rejected_step_ids,
    )
    _append_mismatch(
        failure_reasons,
        "unresolved_blocking_step_ids",
        tuple(memo.unresolved_blocking_step_ids),
        expected.unresolved_blocking_step_ids,
    )
    _append_mismatch(
        failure_reasons,
        "human_revision_step_ids",
        revision_ids,
        expected.human_revision_step_ids,
    )
    actual_revised_actions = {
        action.step_id: action.action
        for action in memo.retained_actions
        if (
            type(action) is DecisionMemoAction
            and action.action_origin
            is DecisionMemoActionOrigin.human_revision
        )
    }
    _append_mismatch(
        failure_reasons,
        "revised_actions",
        actual_revised_actions,
        expected.revised_actions,
    )
    _append_mismatch(
        failure_reasons,
        "evidence_ids",
        evidence_ids,
        expected.evidence_ids,
    )
    _append_mismatch(
        failure_reasons,
        "evidence_snapshots",
        tuple(item.model_dump() for item in memo.evidence_items),
        _expected_evidence_snapshots(inputs, expected.evidence_ids),
    )
    actual_missing = {
        record.step_id: tuple(record.items)
        for record in memo.missing_information
    }
    _append_mismatch(
        failure_reasons,
        "missing_information",
        actual_missing,
        expected.missing_information,
    )
    _append_mismatch(
        failure_reasons,
        "deterministic_risk_codes",
        tuple(memo.deterministic_risk_codes),
        expected.deterministic_risk_codes,
    )
    _append_mismatch(
        failure_reasons,
        "semantic_risk_codes",
        tuple(memo.semantic_risk_codes),
        expected.semantic_risk_codes,
    )
    _append_mismatch(
        failure_reasons,
        "control_notices",
        tuple(memo.control_notices),
        expected.control_notices,
    )
    _append_mismatch(
        failure_reasons,
        "no_action_acknowledged",
        memo.no_action_acknowledged,
        expected.no_action_acknowledged,
    )
    _append_mismatch(
        failure_reasons,
        "overall_review_note",
        memo.overall_review_note,
        scenario.overall_note,
    )
    _append_mismatch(
        failure_reasons,
        "human_review_complete",
        memo.human_review_complete,
        True,
    )
    _append_mismatch(
        failure_reasons,
        "review_method",
        memo.review_method,
        "simulated_human_review_v1",
    )
    _append_mismatch(
        failure_reasons,
        "memo_method",
        memo.memo_method,
        "deterministic_post_review_v1",
    )

    retained_set = set(retained_ids)
    rejected_set = set(rejected_ids)
    gate_set = set(gate_ids)
    primary_ids = retained_ids + gate_ids + rejected_ids
    plan_ids = tuple(step.step_id for step in plan.steps)
    if (
        len(primary_ids) != len(plan_ids)
        or set(primary_ids) != set(plan_ids)
        or len(primary_ids) != len(set(primary_ids))
    ):
        failure_reasons.append(
            "primary records do not cover each plan step exactly once"
        )

    for step in plan.steps:
        reviewed = reviewed_by_id.get(step.step_id)
        if reviewed is None:
            failure_reasons.append(
                "primary record has no matching reviewed-step snapshot"
            )
            continue
        if step.step_kind is WorkflowStepKind.semantic_review_gate:
            expected_section = "gate"
        elif reviewed.decision is HumanReviewDecision.reject:
            expected_section = "rejected"
        else:
            expected_section = "retained"
        memberships = {
            "retained": step.step_id in retained_set,
            "gate": step.step_id in gate_set,
            "rejected": step.step_id in rejected_set,
        }
        if (
            not memberships[expected_section]
            or sum(memberships.values()) != 1
        ):
            failure_reasons.append(
                "primary record decision category mismatch"
            )

    for action in memo.retained_actions:
        if type(action) is not DecisionMemoAction:
            failure_reasons.append(
                "retained-action section contains an invalid record type"
            )
            continue
        source_step = plan_by_id.get(action.step_id)
        reviewed = reviewed_by_id.get(action.step_id)
        if source_step is None or reviewed is None:
            failure_reasons.append(
                "retained action has no matching source snapshot"
            )
            continue
        expected_snapshot = (
            source_step.step_id,
            source_step.sequence,
            source_step.step_kind,
            source_step.owner_role,
            source_step.action,
            source_step.supporting_evidence_ids,
            source_step.deterministic_risk_codes,
            source_step.semantic_risk_codes,
            source_step.status,
            source_step.blocks_downstream,
        )
        actual_snapshot = (
            action.step_id,
            action.sequence,
            action.step_kind,
            action.owner_role,
            action.original_action,
            action.supporting_evidence_ids,
            action.deterministic_risk_codes,
            action.semantic_risk_codes,
            action.original_status,
            action.blocks_downstream,
        )
        if actual_snapshot != expected_snapshot:
            failure_reasons.append(
                "retained action snapshot mismatch"
            )
        if reviewed.decision is HumanReviewDecision.accept:
            accepted_fields = (
                action.action == source_step.action,
                action.action_origin
                is DecisionMemoActionOrigin.accepted_original,
                action.reviewer_note == reviewed.reviewer_note,
                not action.revision_requires_revalidation,
            )
            if not all(accepted_fields):
                failure_reasons.append(
                    "accepted retained-action review fields mismatch"
                )
        elif reviewed.decision is HumanReviewDecision.revise:
            revision_fields = (
                action.action == reviewed.final_action,
                action.action_origin
                is DecisionMemoActionOrigin.human_revision,
                action.reviewer_note == reviewed.reviewer_note,
                action.revision_requires_revalidation,
                action.supporting_evidence_ids
                == source_step.supporting_evidence_ids,
            )
            if not all(revision_fields):
                failure_reasons.append(
                    "human-revision fields or original Evidence "
                    "lineage mismatch"
                )
        else:
            failure_reasons.append(
                "retained action decision category mismatch"
            )

    for rejected in memo.rejected_steps:
        if type(rejected) is not DecisionMemoRejectedStep:
            failure_reasons.append(
                "rejected-step section contains an invalid record type"
            )
            continue
        source_step = plan_by_id.get(rejected.step_id)
        reviewed = reviewed_by_id.get(rejected.step_id)
        if source_step is None or reviewed is None:
            failure_reasons.append(
                "rejected step has no matching source snapshot"
            )
            continue
        expected_snapshot = (
            source_step.step_id,
            source_step.sequence,
            source_step.step_kind,
            source_step.owner_role,
            source_step.action,
            reviewed.reviewer_note,
            source_step.supporting_evidence_ids,
            source_step.deterministic_risk_codes,
            source_step.semantic_risk_codes,
            source_step.status,
            source_step.blocks_downstream,
        )
        actual_snapshot = (
            rejected.step_id,
            rejected.sequence,
            rejected.step_kind,
            rejected.owner_role,
            rejected.original_action,
            rejected.reviewer_note,
            rejected.supporting_evidence_ids,
            rejected.deterministic_risk_codes,
            rejected.semantic_risk_codes,
            rejected.original_status,
            rejected.blocks_downstream,
        )
        if actual_snapshot != expected_snapshot:
            failure_reasons.append(
                "rejected step audit snapshot mismatch"
            )
        if reviewed.decision is not HumanReviewDecision.reject:
            failure_reasons.append(
                "rejected step decision category mismatch"
            )

    for gate in memo.review_gates:
        if type(gate) is not DecisionMemoReviewGate:
            failure_reasons.append(
                "review-gate section contains an invalid record type"
            )
            continue
        source_step = plan_by_id.get(gate.step_id)
        reviewed = reviewed_by_id.get(gate.step_id)
        if source_step is None or reviewed is None:
            failure_reasons.append(
                "review gate has no matching source snapshot"
            )
            continue
        expected_snapshot = (
            source_step.step_id,
            source_step.sequence,
            source_step.owner_role,
            reviewed.decision,
            reviewed.reviewer_note,
            source_step.supporting_evidence_ids,
            source_step.semantic_risk_codes,
            source_step.status,
            source_step.blocks_downstream,
        )
        actual_snapshot = (
            gate.step_id,
            gate.sequence,
            gate.owner_role,
            gate.decision,
            gate.reviewer_note,
            gate.supporting_evidence_ids,
            gate.semantic_risk_codes,
            gate.original_status,
            gate.blocks_downstream,
        )
        if (
            source_step.step_kind
            is not WorkflowStepKind.semantic_review_gate
            or actual_snapshot != expected_snapshot
        ):
            failure_reasons.append(
                "review gate snapshot mismatch"
            )
        if (
            reviewed.decision
            not in {
                HumanReviewDecision.accept,
                HumanReviewDecision.reject,
            }
            or gate.step_id in retained_set
            or gate.step_id in rejected_set
        ):
            failure_reasons.append(
                "semantic gate decision category mismatch"
            )

    expected_gate_set = {
        step.step_id
        for step in plan.steps
        if step.step_kind is WorkflowStepKind.semantic_review_gate
    }
    if gate_set != expected_gate_set:
        failure_reasons.append(
            "semantic gates did not enter only the review-gate section"
        )

    expected_blockers = tuple(
        step.step_id for step in plan.steps if step.blocks_downstream
    )
    if tuple(memo.unresolved_blocking_step_ids) != expected_blockers:
        failure_reasons.append(
            "blocker IDs did not preserve original blocking flags"
        )
    expected_missing = {
        step.step_id: tuple(step.missing_information)
        for step in plan.steps
        if (
            step.step_kind is WorkflowStepKind.role_action
            and step.missing_information
        )
    }
    if actual_missing != expected_missing:
        failure_reasons.append(
            "role-action missing information was not source-preserved"
        )
    if plan.model_dump() != plan_before:
        failure_reasons.append("source WorkflowPlan was mutated")
    if session_before != session_after:
        failure_reasons.append("source HumanReviewSession was mutated")

    return _memo_result(scenario, memo, failure_reasons)


def evaluate_memo_scenario(
    scenario: MemoEvaluationScenario,
) -> MemoScenarioEvaluationResult:
    """Review, compose, and exactly evaluate one fixed memo scenario."""
    if type(scenario) is not MemoEvaluationScenario:
        raise MemoEvaluationInputError(
            "scenario must be exactly a MemoEvaluationScenario"
        )
    try:
        inputs = build_memo_scenario_inputs(scenario)
        plan_before = inputs.workflow_plan.model_dump()
        session = review_workflow_plan(
            inputs.workflow_plan,
            inputs.decisions,
            no_action_acknowledged=inputs.no_action_acknowledged,
            overall_note=inputs.overall_note,
        )
        session_before = session.model_dump()
    except Exception:
        return _non_memo_result(
            scenario,
            actual_outcome="unexpected_error",
            failure_reasons=(
                "unexpected error while constructing review inputs",
            ),
        )

    if scenario.expected.expected_outcome == "decision_memo_input_error":
        failure_reasons: list[str] = []
        if (
            session.session_status is not HumanReviewSessionStatus.pending
            or session.human_review_complete
        ):
            failure_reasons.append(
                "expected incomplete review session did not remain pending"
            )
        try:
            memo = compose_decision_memo(
                inputs.workflow_plan,
                session,
                inputs.evidence_objects,
            )
        except DecisionMemoInputError:
            if inputs.workflow_plan.model_dump() != plan_before:
                failure_reasons.append("source WorkflowPlan was mutated")
            if session.model_dump() != session_before:
                failure_reasons.append(
                    "source HumanReviewSession was mutated"
                )
            return _non_memo_result(
                scenario,
                actual_outcome="decision_memo_input_error",
                failure_reasons=failure_reasons,
            )
        except Exception:
            return _non_memo_result(
                scenario,
                actual_outcome="unexpected_error",
                failure_reasons=(
                    "unexpected exception type during memo composition",
                ),
            )
        return _memo_result(
            scenario,
            memo,
            ["incomplete review unexpectedly produced a memo"],
        )

    if (
        session.session_status is not HumanReviewSessionStatus.complete
        or not session.human_review_complete
    ):
        return _non_memo_result(
            scenario,
            actual_outcome="decision_memo_input_error",
            failure_reasons=(
                "expected memo scenario did not complete human review",
            ),
        )
    try:
        memo = compose_decision_memo(
            inputs.workflow_plan,
            session,
            inputs.evidence_objects,
        )
    except DecisionMemoInputError:
        return _non_memo_result(
            scenario,
            actual_outcome="decision_memo_input_error",
            failure_reasons=(
                "expected memo scenario failed composition",
            ),
        )
    except Exception:
        return _non_memo_result(
            scenario,
            actual_outcome="unexpected_error",
            failure_reasons=(
                "unexpected exception type during memo composition",
            ),
        )
    return _evaluate_successful_memo(
        scenario,
        inputs,
        session,
        memo,
        plan_before,
        session_before,
        session.model_dump(),
    )


def _validate_scenario_sequence(
    scenarios: Sequence[MemoEvaluationScenario],
) -> tuple[MemoEvaluationScenario, ...]:
    """Freeze and validate a caller-supplied scenario sequence."""
    if not isinstance(scenarios, Sequence) or isinstance(
        scenarios,
        (str, bytes),
    ):
        raise MemoEvaluationInputError(
            "scenarios must be a sequence of MemoEvaluationScenario values"
        )
    frozen = tuple(scenarios)
    if any(
        type(scenario) is not MemoEvaluationScenario
        for scenario in frozen
    ):
        raise MemoEvaluationInputError(
            "scenarios contains an unsupported value type"
        )
    scenario_ids = [scenario.scenario_id for scenario in frozen]
    if len(scenario_ids) != len(set(scenario_ids)):
        raise MemoEvaluationInputError(
            "scenarios must not contain duplicate scenario IDs"
        )
    return frozen


def run_memo_evaluation(
    scenarios: Sequence[MemoEvaluationScenario],
) -> MemoEvaluationSummary:
    """Evaluate every supplied scenario in caller-provided order."""
    frozen = _validate_scenario_sequence(scenarios)
    return MemoEvaluationSummary(
        scenario_results=tuple(
            evaluate_memo_scenario(scenario)
            for scenario in frozen
        )
    )


def _build_polished_action_summary(
    inputs: MemoScenarioInputs,
    human_review_session: HumanReviewSession,
) -> _PolishedActionSummary:
    """Build only the visible final-action list and count summary."""
    reviewed_by_id = {
        reviewed.step_id: reviewed
        for reviewed in human_review_session.reviewed_steps
    }
    visible_step_ids = tuple(
        step.step_id
        for step in inputs.workflow_plan.steps
        if (
            step.step_kind is not WorkflowStepKind.semantic_review_gate
            and reviewed_by_id.get(step.step_id) is not None
            and reviewed_by_id[step.step_id].decision
            is not HumanReviewDecision.reject
        )
    )
    visible_actions: list[str] = []
    for step_id in visible_step_ids:
        final_action = reviewed_by_id[step_id].final_action
        if final_action is None:
            raise MemoEvaluationInputError(
                "visible baseline action unexpectedly has no final text"
            )
        visible_actions.append(final_action)
    return _PolishedActionSummary(
        visible_step_ids=visible_step_ids,
        visible_actions=tuple(visible_actions),
        action_count_summary=(
            f"{len(visible_actions)} final actions listed."
        ),
        review_session_status=human_review_session.session_status,
        human_review_complete=human_review_session.human_review_complete,
    )


def _evaluate_polished_action_summary(
    scenario: MemoEvaluationScenario,
    summary: _PolishedActionSummary,
) -> MemoScenarioEvaluationResult:
    """Derive baseline failures from exact absent or inconsistent properties."""
    expected = scenario.expected
    failure_reasons: list[str] = []
    expected_actions = tuple(
        expected.revised_actions.get(
            step_id,
            _TEMPLATE_ORIGINAL_ACTIONS[scenario.plan_template][step_id],
        )
        for step_id in expected.retained_step_ids
    )
    if summary.visible_step_ids != expected.retained_step_ids:
        failure_reasons.append("visible action step order mismatch")
    if summary.visible_actions != expected_actions:
        failure_reasons.append("visible final action text mismatch")
    if summary.action_count_summary != (
        f"{len(summary.visible_actions)} final actions listed."
    ):
        failure_reasons.append("action count summary mismatch")

    if expected.expected_outcome == "decision_memo_input_error":
        if (
            summary.review_session_status
            is HumanReviewSessionStatus.pending
            and not summary.human_review_complete
        ):
            failure_reasons.append(
                "baseline produced a polished summary despite pending "
                "incomplete review"
            )
        else:
            failure_reasons.append(
                "baseline did not preserve the expected input-error outcome"
            )
    else:
        if (
            summary.review_session_status
            is not HumanReviewSessionStatus.complete
            or not summary.human_review_complete
        ):
            failure_reasons.append(
                "baseline review completion state mismatch"
            )
        failure_reasons.append("missing plan digest")
        failure_reasons.append("missing memo status")
        if expected.evidence_ids:
            failure_reasons.append("missing Evidence lineage")
        if (
            expected.deterministic_risk_codes
            or expected.semantic_risk_codes
        ):
            failure_reasons.append("missing risk-code lineage")
        if expected.review_gate_step_ids:
            failure_reasons.append(
                "missing non-authoritative semantic review-gate record"
            )
        if expected.rejected_step_ids:
            failure_reasons.append("missing rejected-step audit")
        if expected.unresolved_blocking_step_ids:
            failure_reasons.append("missing unresolved blocker state")
        if expected.missing_information:
            failure_reasons.append("missing information gap")
        if expected.human_revision_step_ids:
            failure_reasons.append(
                "missing human-revision revalidation metadata"
            )
        if expected.control_notices:
            failure_reasons.append("missing control notices")
        if expected.no_action_acknowledged:
            failure_reasons.append(
                "missing explicit no-action acknowledgment record"
            )

    return MemoScenarioEvaluationResult(
        scenario_id=scenario.scenario_id,
        passed=not failure_reasons,
        expected_outcome=expected.expected_outcome,
        actual_outcome="memo",
        actual_memo_status=None,
        actual_retained_step_ids=summary.visible_step_ids,
        actual_review_gate_step_ids=(),
        actual_rejected_step_ids=(),
        actual_unresolved_blocking_step_ids=(),
        actual_human_revision_step_ids=(),
        actual_evidence_ids=(),
        failure_reasons=tuple(failure_reasons),
    )


def evaluate_polished_action_summary_baseline(
    scenarios: Sequence[MemoEvaluationScenario],
) -> MemoEvaluationSummary:
    """Evaluate deterministic action summaries against memo audit needs."""
    frozen = _validate_scenario_sequence(scenarios)
    results: list[MemoScenarioEvaluationResult] = []
    for scenario in frozen:
        inputs = build_memo_scenario_inputs(scenario)
        session = review_workflow_plan(
            inputs.workflow_plan,
            inputs.decisions,
            no_action_acknowledged=inputs.no_action_acknowledged,
            overall_note=inputs.overall_note,
        )
        summary = _build_polished_action_summary(inputs, session)
        results.append(
            _evaluate_polished_action_summary(scenario, summary)
        )
    return MemoEvaluationSummary(scenario_results=tuple(results))
