"""Deterministic evaluation of semantic-risk reviewer outputs.

This module scores an already-produced :class:`SemanticRiskReviewResult`
against human-reviewed, fixed scenario expectations. It never calls Granite
or any other model. A passing score therefore describes deterministic
agreement with this evaluation pack; it does not prove that a probabilistic
reviewer is generally reliable or that any claim is true.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PrivateAttr,
    ValidationError,
    field_validator,
    model_validator,
)

from app.schemas import (
    EvidenceScope,
    RoleKey,
    SemanticReviewDisposition,
    SemanticRiskCode,
    SemanticRiskReviewResult,
)


DEFAULT_SEMANTIC_SCENARIO_PATH = (
    Path(__file__).resolve().parents[1]
    / "examples"
    / "scenarios"
    / "semantic_risk_v1.json"
)

_REQUIRED_SCENARIO_IDS = (
    "S1_supported_cautious_claim",
    "S2_unsupported_roi_budget",
    "S3_causation_overreach",
    "S4_external_context_as_company_fact",
    "S5_role_boundary_violation",
    "S6_unsupported_completion_validation",
    "S7_citation_claim_mismatch",
    "S8_ambiguous_partial_support",
)


class SemanticEvaluationInputError(ValueError):
    """Raised when an evaluation fixture or result sequence is invalid."""


class _FrozenEvaluationModel(BaseModel):
    """Shared immutable, extra-forbidding evaluation model configuration."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class SemanticScenarioExpectation(_FrozenEvaluationModel):
    """Approved deterministic expectations for one semantic-risk scenario."""

    must_detect: tuple[SemanticRiskCode, ...]
    acceptable_codes: tuple[SemanticRiskCode, ...]
    must_not_detect: tuple[SemanticRiskCode, ...]
    acceptable_dispositions: tuple[SemanticReviewDisposition, ...]
    minimum_candidate_count: int = Field(ge=0, strict=True)
    maximum_candidate_count: int | None = Field(default=None, ge=0, strict=True)

    @field_validator(
        "must_detect",
        "acceptable_codes",
        "must_not_detect",
        "acceptable_dispositions",
    )
    @classmethod
    def expectation_values_are_unique(cls, values: tuple[Any, ...]) -> tuple[Any, ...]:
        """Reject duplicate expectation values that could distort scoring."""
        if len(values) != len(set(values)):
            raise ValueError("expectation lists must not contain duplicate values")
        return values

    @model_validator(mode="after")
    def expectation_relationships_are_valid(self) -> "SemanticScenarioExpectation":
        """Validate count bounds and required/prohibited code relationships."""
        if (
            self.maximum_candidate_count is not None
            and self.maximum_candidate_count < self.minimum_candidate_count
        ):
            raise ValueError(
                "maximum_candidate_count must be greater than or equal to "
                "minimum_candidate_count"
            )

        required = set(self.must_detect)
        prohibited = set(self.must_not_detect)
        acceptable = set(self.acceptable_codes)
        overlap = required & prohibited
        if overlap:
            codes = ", ".join(sorted(code.value for code in overlap))
            raise ValueError(
                f"must_detect must not overlap must_not_detect: {codes}"
            )
        if not required <= acceptable:
            missing = ", ".join(
                sorted(code.value for code in required - acceptable)
            )
            raise ValueError(
                "must_detect must be a subset of acceptable_codes; "
                f"missing: {missing}"
            )
        return self


class SemanticEvaluationScenario(_FrozenEvaluationModel):
    """One synthetic, human-reviewed semantic-risk evaluation scenario."""

    scenario_id: str
    title: str
    purpose: str
    role_key: RoleKey
    evidence_scope: EvidenceScope
    evidence_finding: str
    evidence_supporting_evidence: str
    evidence_limitations: tuple[str, ...]
    claim: str
    expected: SemanticScenarioExpectation
    rationale: str
    demo_priority: bool = Field(strict=True)

    @field_validator(
        "scenario_id",
        "title",
        "purpose",
        "evidence_finding",
        "evidence_supporting_evidence",
        "claim",
        "rationale",
    )
    @classmethod
    def text_fields_are_non_blank(cls, value: str) -> str:
        """Require concise but non-empty fixture text."""
        if not value or not value.strip():
            raise ValueError("scenario text fields must not be blank")
        return value

    @field_validator("evidence_limitations")
    @classmethod
    def limitations_are_non_blank_unique(
        cls,
        values: tuple[str, ...],
    ) -> tuple[str, ...]:
        """Require at least one distinct, non-blank evidence limitation."""
        if not values:
            raise ValueError("evidence_limitations must not be empty")
        if any(not value or not value.strip() for value in values):
            raise ValueError("evidence_limitations must not contain blank values")
        if len(values) != len(set(values)):
            raise ValueError("evidence_limitations must not contain duplicates")
        return values


class ScenarioEvaluationResult(_FrozenEvaluationModel):
    """Deterministic result of evaluating one reviewer output."""

    scenario_id: str
    passed: bool
    detected_codes: tuple[SemanticRiskCode, ...]
    detected_dispositions: tuple[SemanticReviewDisposition, ...]
    missing_required_codes: tuple[SemanticRiskCode, ...]
    forbidden_detected_codes: tuple[SemanticRiskCode, ...]
    unexpected_codes: tuple[SemanticRiskCode, ...]
    candidate_count: int = Field(ge=0, strict=True)
    failure_reasons: tuple[str, ...]

    _required_code_count: int | None = PrivateAttr(default=None)
    _detected_required_code_count: int | None = PrivateAttr(default=None)
    _false_positive_failure: bool | None = PrivateAttr(default=None)


@dataclass(frozen=True)
class SemanticEvaluationSummary:
    """Derived aggregate metrics for a sequence of scenario results."""

    scenario_results: tuple[ScenarioEvaluationResult, ...]
    total_scenarios: int = field(init=False)
    passed_scenarios: int = field(init=False)
    failed_scenarios: int = field(init=False)
    pass_rate: float = field(init=False)
    required_detection_recall: float = field(init=False)
    false_positive_scenario_count: int = field(init=False)

    def __post_init__(self) -> None:
        """Derive every aggregate value; callers cannot supply aggregates."""
        scenario_ids = [result.scenario_id for result in self.scenario_results]
        if len(scenario_ids) != len(set(scenario_ids)):
            raise SemanticEvaluationInputError(
                "scenario_results must not contain duplicate scenario IDs"
            )

        missing_metadata = [
            result.scenario_id
            for result in self.scenario_results
            if result._required_code_count is None
            or result._detected_required_code_count is None
            or result._false_positive_failure is None
        ]
        if missing_metadata:
            raise SemanticEvaluationInputError(
                "scenario results must be produced by "
                "evaluate_semantic_scenario; missing evaluation metadata for: "
                + ", ".join(missing_metadata)
            )

        total = len(self.scenario_results)
        passed = sum(result.passed for result in self.scenario_results)
        required_total = sum(
            result._required_code_count or 0 for result in self.scenario_results
        )
        required_detected = sum(
            result._detected_required_code_count or 0
            for result in self.scenario_results
        )

        object.__setattr__(self, "total_scenarios", total)
        object.__setattr__(self, "passed_scenarios", passed)
        object.__setattr__(self, "failed_scenarios", total - passed)
        object.__setattr__(self, "pass_rate", passed / total if total else 0.0)
        object.__setattr__(
            self,
            "required_detection_recall",
            required_detected / required_total if required_total else 0.0,
        )
        object.__setattr__(
            self,
            "false_positive_scenario_count",
            sum(
                bool(result._false_positive_failure)
                for result in self.scenario_results
            ),
        )


def _load_json(path: Path) -> Any:
    """Read and decode JSON, normalizing all input failures."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SemanticEvaluationInputError(
            f"unable to load semantic evaluation fixture {path}: {exc}"
        ) from exc


def load_semantic_scenarios(
    path: Path = DEFAULT_SEMANTIC_SCENARIO_PATH,
) -> tuple[SemanticEvaluationScenario, ...]:
    """Load and strictly validate the fixed eight-scenario evaluation pack."""
    raw_scenarios = _load_json(path)
    if not isinstance(raw_scenarios, list):
        raise SemanticEvaluationInputError(
            "semantic evaluation fixture top-level value must be a list"
        )

    scenarios: list[SemanticEvaluationScenario] = []
    for index, raw_scenario in enumerate(raw_scenarios):
        if not isinstance(raw_scenario, Mapping):
            raise SemanticEvaluationInputError(
                f"scenario at index {index} must be a JSON object"
            )
        try:
            scenarios.append(SemanticEvaluationScenario.model_validate(raw_scenario))
        except ValidationError as exc:
            raise SemanticEvaluationInputError(
                f"invalid semantic evaluation scenario at index {index}: {exc}"
            ) from exc

    scenario_ids = [scenario.scenario_id for scenario in scenarios]
    if len(scenario_ids) != len(set(scenario_ids)):
        raise SemanticEvaluationInputError(
            "semantic evaluation fixture contains duplicate scenario IDs"
        )

    missing_ids = [
        scenario_id
        for scenario_id in _REQUIRED_SCENARIO_IDS
        if scenario_id not in scenario_ids
    ]
    if missing_ids:
        raise SemanticEvaluationInputError(
            "semantic evaluation fixture is missing required scenario IDs: "
            + ", ".join(missing_ids)
        )
    if len(scenarios) != len(_REQUIRED_SCENARIO_IDS):
        raise SemanticEvaluationInputError(
            "semantic evaluation fixture must contain exactly eight scenarios"
        )

    return tuple(scenarios)


def _unique_in_order(values: Sequence[Any]) -> tuple[Any, ...]:
    """Return distinct hashable values in first-seen order."""
    return tuple(dict.fromkeys(values))


def evaluate_semantic_scenario(
    scenario: SemanticEvaluationScenario,
    review_result: SemanticRiskReviewResult,
) -> ScenarioEvaluationResult:
    """Evaluate one reviewer result using exact enum and count comparisons only."""
    candidates = tuple(
        candidate
        for candidate in review_result.candidates
        if candidate.role_key == scenario.role_key
    )
    detected_codes = _unique_in_order(
        [candidate.risk_code for candidate in candidates]
    )
    detected_dispositions = _unique_in_order(
        [candidate.disposition for candidate in candidates]
    )
    valid_claim_candidates = tuple(
        candidate for candidate in candidates if candidate.claim_index == 0
    )
    valid_claim_detected_set = {
        candidate.risk_code for candidate in valid_claim_candidates
    }
    invalid_claim_indexes = tuple(
        sorted(
            {
                candidate.claim_index
                for candidate in candidates
                if candidate.claim_index != 0
            }
        )
    )
    role_was_reviewed = scenario.role_key in review_result.reviewed_role_keys

    expected = scenario.expected
    detected_set = set(detected_codes)
    acceptable_set = set(expected.acceptable_codes)
    missing_required = tuple(
        code
        for code in expected.must_detect
        if code not in valid_claim_detected_set
    )
    forbidden_detected = tuple(
        code for code in expected.must_not_detect if code in detected_set
    )
    unexpected = tuple(
        code for code in detected_codes if code not in acceptable_set
    )
    invalid_dispositions = tuple(
        disposition
        for disposition in detected_dispositions
        if disposition not in set(expected.acceptable_dispositions)
    )
    candidate_count = len(candidates)

    failure_reasons: list[str] = []
    if not role_was_reviewed:
        failure_reasons.append(
            f"scenario role {scenario.role_key.value!r} was not reviewed"
        )
    if invalid_claim_indexes:
        failure_reasons.append(
            "candidates reference unsupported claim indexes: "
            + ", ".join(str(index) for index in invalid_claim_indexes)
            + "; the single-claim fixture contract requires claim_index=0"
        )
    if missing_required:
        failure_reasons.append(
            "missing required codes: "
            + ", ".join(code.value for code in missing_required)
        )
    if forbidden_detected:
        failure_reasons.append(
            "detected prohibited codes: "
            + ", ".join(code.value for code in forbidden_detected)
        )
    if unexpected:
        failure_reasons.append(
            "detected unexpected codes: "
            + ", ".join(code.value for code in unexpected)
        )
    if candidate_count < expected.minimum_candidate_count:
        failure_reasons.append(
            f"candidate count {candidate_count} is below minimum "
            f"{expected.minimum_candidate_count}"
        )
    if (
        expected.maximum_candidate_count is not None
        and candidate_count > expected.maximum_candidate_count
    ):
        failure_reasons.append(
            f"candidate count {candidate_count} exceeds maximum "
            f"{expected.maximum_candidate_count}"
        )
    if invalid_dispositions:
        failure_reasons.append(
            "detected unacceptable dispositions: "
            + ", ".join(disposition.value for disposition in invalid_dispositions)
        )

    result = ScenarioEvaluationResult(
        scenario_id=scenario.scenario_id,
        passed=not failure_reasons,
        detected_codes=detected_codes,
        detected_dispositions=detected_dispositions,
        missing_required_codes=missing_required,
        forbidden_detected_codes=forbidden_detected,
        unexpected_codes=unexpected,
        candidate_count=candidate_count,
        failure_reasons=tuple(failure_reasons),
    )
    result._required_code_count = len(expected.must_detect)
    result._detected_required_code_count = (
        len(expected.must_detect) - len(missing_required)
    )
    result._false_positive_failure = (
        not expected.must_detect
        and bool(candidates)
        and (bool(forbidden_detected) or bool(unexpected))
    )
    return result


def summarize_semantic_evaluation(
    scenario_results: Sequence[ScenarioEvaluationResult],
) -> SemanticEvaluationSummary:
    """Build a summary whose aggregate metrics are entirely derived."""
    results = tuple(scenario_results)
    if any(not isinstance(result, ScenarioEvaluationResult) for result in results):
        raise SemanticEvaluationInputError(
            "scenario_results must contain only ScenarioEvaluationResult values"
        )
    return SemanticEvaluationSummary(scenario_results=results)


def evaluate_citation_only_baseline(
    scenarios: Sequence[SemanticEvaluationScenario],
) -> tuple[ScenarioEvaluationResult, ...]:
    """Evaluate the citation-only baseline without fabricating semantic output.

    Every fixed scenario states that a syntactically valid citation is present,
    so this baseline returns no semantic-risk candidates. It demonstrates that
    ``valid citation != semantically supported claim``: S1 passes, while the
    semantic-risk expectations in S2-S8 fail.
    """
    return tuple(
        evaluate_semantic_scenario(
            scenario,
            SemanticRiskReviewResult(
                candidates=[],
                reviewed_role_keys=[scenario.role_key],
                reviewer_model=None,
                human_review_required=False,
            ),
        )
        for scenario in scenarios
    )
