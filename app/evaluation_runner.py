"""Provider-neutral live semantic evaluation construction and execution.

The caller injects a ``SemanticRiskProvider``. This module does not read
credentials, import the IBM SDK, construct Granite, retry requests, or alter
the fixed Task 7C expectations.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType
from typing import Mapping, Sequence

from app.evaluation import (
    ScenarioEvaluationResult,
    SemanticEvaluationScenario,
    SemanticEvaluationSummary,
    evaluate_citation_only_baseline,
    evaluate_semantic_scenario,
    summarize_semantic_evaluation,
)
from app.risk_checker import check_role_risks
from app.role_engine import InsufficientEvidence, RoleOutcome
from app.schemas import (
    EvidenceObject,
    EvidenceReference,
    EvidenceStatus,
    GroundedFinding,
    RoleKey,
    RoleView,
    SemanticReviewDisposition,
    SemanticRiskCode,
    SourceFormat,
    TextSourceLocator,
    _ROLE_EXECUTION_ORDER,
)
from app.semantic_risk_reviewer import (
    SemanticRiskProvider,
    review_semantic_risks,
)


_PENDING_HUMAN_REVIEW = "pending_human_review"
_SAFE_RUN_ID = re.compile(r"^[a-z0-9_-]+$")


class SemanticEvaluationRunnerInputError(ValueError):
    """Raised when scenario selection or runner input is invalid."""


class SemanticEvaluationRunnerExecutionError(RuntimeError):
    """Raised when a scenario cannot complete without exposing raw errors."""


class SemanticEvaluationArtifactError(RuntimeError):
    """Raised when sanitized result artifacts cannot be serialized or written."""


@dataclass(frozen=True)
class LiveScenarioInputs:
    """Synthetic production-contract inputs constructed for one fixture."""

    scenario: SemanticEvaluationScenario
    evidence_object: EvidenceObject
    role_view: RoleView
    role_outcomes: Mapping[RoleKey, RoleOutcome]


@dataclass(frozen=True)
class LiveScenarioEvaluationRecord:
    """Sanitized result record for one live semantic evaluation scenario."""

    scenario_id: str
    reviewer_model: str | None
    detected_codes: tuple[SemanticRiskCode, ...]
    detected_dispositions: tuple[SemanticReviewDisposition, ...]
    candidate_count: int
    passed: bool
    failure_reasons: tuple[str, ...]
    human_review_required: bool
    reviewer_notes: str | None = field(default=None, init=False)
    human_label_status: str = field(
        default=_PENDING_HUMAN_REVIEW,
        init=False,
    )


@dataclass(frozen=True)
class LiveSemanticEvaluationRun:
    """Completed live run with locally derived metadata and summaries."""

    scenario_records: tuple[LiveScenarioEvaluationRecord, ...]
    semantic_summary: SemanticEvaluationSummary
    citation_only_summary: SemanticEvaluationSummary
    started_at_utc: datetime
    completed_at_utc: datetime
    run_id: str
    total_provider_calls: int = field(init=False)
    human_review_status: str = field(
        default=_PENDING_HUMAN_REVIEW,
        init=False,
    )

    def __post_init__(self) -> None:
        """Validate local metadata and derive the successful call count."""
        for name, value in (
            ("started_at_utc", self.started_at_utc),
            ("completed_at_utc", self.completed_at_utc),
        ):
            if value.tzinfo is None or value.utcoffset() is None:
                raise SemanticEvaluationRunnerInputError(
                    f"{name} must be timezone-aware"
                )
            if value.utcoffset() != timezone.utc.utcoffset(value):
                raise SemanticEvaluationRunnerInputError(f"{name} must use UTC")
        if self.completed_at_utc < self.started_at_utc:
            raise SemanticEvaluationRunnerInputError(
                "completed_at_utc must not precede started_at_utc"
            )
        if not _SAFE_RUN_ID.fullmatch(self.run_id):
            raise SemanticEvaluationRunnerInputError(
                "run_id contains unsupported characters"
            )
        object.__setattr__(
            self,
            "total_provider_calls",
            len(self.scenario_records),
        )


def _digest(namespace: str, scenario_id: str) -> str:
    """Return a deterministic SHA-256 digest for synthetic evaluation identity."""
    payload = f"rolelens:task7d:{namespace}:{scenario_id}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def construct_live_scenario_inputs(
    scenario: SemanticEvaluationScenario,
) -> LiveScenarioInputs:
    """Construct one evidence object, one single-claim view, and five outcomes."""
    if not isinstance(scenario, SemanticEvaluationScenario):
        raise SemanticEvaluationRunnerInputError(
            "scenario must be a SemanticEvaluationScenario"
        )

    source_digest = _digest("synthetic-source", scenario.scenario_id)
    evidence_digest = _digest("synthetic-evidence", scenario.scenario_id)
    source_id = f"src-sem_eval-{source_digest[:12]}"
    evidence_id = f"ev-sem_eval-{evidence_digest[:12]}"

    evidence = EvidenceObject.model_validate(
        {
            "evidence_id": evidence_id,
            "identity_digest": evidence_digest,
            "source_id": source_id,
            "source_format": SourceFormat.pasted_text,
            "source_locator": TextSourceLocator(
                heading_path=(
                    "Synthetic Task 7D evaluation fixture / "
                    f"{scenario.scenario_id}"
                )
            ),
            "evidence_type": "semantic_evaluation_fixture",
            "evidence_scope": scenario.evidence_scope,
            "extraction_method": "deterministic",
            "finding": scenario.evidence_finding,
            "supporting_evidence": scenario.evidence_supporting_evidence,
            "confidence": "low",
            "limitations": list(scenario.evidence_limitations),
            "relevant_roles": [scenario.role_key.value],
            "decision_relevance": (
                "Synthetic Task 7D semantic evaluation fixture "
                f"{scenario.scenario_id}."
            ),
            "created_by": "evidence_builder",
            "status": EvidenceStatus.active,
        }
    )
    role_view = RoleView(
        role_key=scenario.role_key,
        role_concern="Review the single synthetic evaluation claim.",
        key_findings=[
            GroundedFinding(
                claim=scenario.claim,
                evidence_references=[
                    EvidenceReference(
                        evidence_id=evidence.evidence_id,
                        relevance_note=(
                            "Citation to the synthetic Task 7D fixture evidence."
                        ),
                    )
                ],
                confidence="low",
            )
        ],
        risks_or_assumptions=[],
        missing_information=[],
        next_action=None,
        dependency=None,
        human_review_required=True,
    )

    outcomes: dict[RoleKey, RoleOutcome] = {}
    for role_key in _ROLE_EXECUTION_ORDER:
        if role_key == scenario.role_key:
            outcomes[role_key] = role_view
        else:
            outcomes[role_key] = InsufficientEvidence(
                role_key=role_key,
                reason=(
                    "Role is absent from this single-role synthetic "
                    "evaluation scenario."
                ),
            )

    return LiveScenarioInputs(
        scenario=scenario,
        evidence_object=evidence,
        role_view=role_view,
        role_outcomes=MappingProxyType(outcomes),
    )


def select_semantic_evaluation_scenarios(
    scenarios: Sequence[SemanticEvaluationScenario],
    selected_scenario_ids: Sequence[str] | None = None,
) -> tuple[SemanticEvaluationScenario, ...]:
    """Validate selection and return scenarios in fixture order."""
    fixture_scenarios = tuple(scenarios)
    if any(
        not isinstance(scenario, SemanticEvaluationScenario)
        for scenario in fixture_scenarios
    ):
        raise SemanticEvaluationRunnerInputError(
            "scenarios must contain only SemanticEvaluationScenario values"
        )

    fixture_ids = [scenario.scenario_id for scenario in fixture_scenarios]
    if len(fixture_ids) != len(set(fixture_ids)):
        raise SemanticEvaluationRunnerInputError(
            "scenarios must not contain duplicate scenario IDs"
        )
    if selected_scenario_ids is None:
        return fixture_scenarios

    selected_ids = tuple(selected_scenario_ids)
    if any(not isinstance(scenario_id, str) for scenario_id in selected_ids):
        raise SemanticEvaluationRunnerInputError(
            "selected scenario IDs must be strings"
        )
    if len(selected_ids) != len(set(selected_ids)):
        raise SemanticEvaluationRunnerInputError(
            "selected scenario IDs must not contain duplicates"
        )
    unknown = sorted(set(selected_ids) - set(fixture_ids))
    if unknown:
        raise SemanticEvaluationRunnerInputError(
            "unknown selected scenario IDs: " + ", ".join(unknown)
        )
    selected = set(selected_ids)
    return tuple(
        scenario
        for scenario in fixture_scenarios
        if scenario.scenario_id in selected
    )


def _run_id(started_at: datetime) -> str:
    """Generate a local opaque run identifier with no provider metadata."""
    timestamp = started_at.strftime("%Y%m%dt%H%M%S%fz")
    return f"sem-{timestamp}-{uuid.uuid4().hex[:12]}"


def _record(
    scenario_result: ScenarioEvaluationResult,
    *,
    reviewer_model: str | None,
    human_review_required: bool,
) -> LiveScenarioEvaluationRecord:
    """Create a sanitized record from validated evaluation output."""
    return LiveScenarioEvaluationRecord(
        scenario_id=scenario_result.scenario_id,
        reviewer_model=reviewer_model,
        detected_codes=scenario_result.detected_codes,
        detected_dispositions=scenario_result.detected_dispositions,
        candidate_count=scenario_result.candidate_count,
        passed=scenario_result.passed,
        failure_reasons=scenario_result.failure_reasons,
        human_review_required=human_review_required,
    )


def run_live_semantic_evaluation(
    provider: SemanticRiskProvider,
    scenarios: Sequence[SemanticEvaluationScenario],
    *,
    selected_scenario_ids: Sequence[str] | None = None,
) -> LiveSemanticEvaluationRun:
    """Run selected fixtures sequentially with exactly one provider call each."""
    selected_scenarios = select_semantic_evaluation_scenarios(
        scenarios,
        selected_scenario_ids,
    )
    started_at = datetime.now(timezone.utc)
    run_id = _run_id(started_at)
    records: list[LiveScenarioEvaluationRecord] = []
    scenario_results: list[ScenarioEvaluationResult] = []

    for scenario in selected_scenarios:
        try:
            inputs = construct_live_scenario_inputs(scenario)
            deterministic_result = check_role_risks(
                inputs.role_outcomes,
                [inputs.evidence_object],
            )
            semantic_result = review_semantic_risks(
                provider,
                inputs.role_outcomes,
                [inputs.evidence_object],
                deterministic_result,
            )
            scenario_result = evaluate_semantic_scenario(
                scenario,
                semantic_result,
            )
        except Exception:
            raise SemanticEvaluationRunnerExecutionError(
                "live semantic evaluation failed for "
                f"scenario_id={scenario.scenario_id!r}"
            ) from None

        scenario_results.append(scenario_result)
        records.append(
            _record(
                scenario_result,
                reviewer_model=semantic_result.reviewer_model,
                human_review_required=semantic_result.human_review_required,
            )
        )

    try:
        semantic_summary = summarize_semantic_evaluation(scenario_results)
        citation_only_results = evaluate_citation_only_baseline(
            selected_scenarios
        )
        citation_only_summary = summarize_semantic_evaluation(
            citation_only_results
        )
    except Exception:
        raise SemanticEvaluationRunnerExecutionError(
            "live semantic evaluation summary construction failed"
        ) from None

    completed_at = datetime.now(timezone.utc)
    return LiveSemanticEvaluationRun(
        scenario_records=tuple(records),
        semantic_summary=semantic_summary,
        citation_only_summary=citation_only_summary,
        started_at_utc=started_at,
        completed_at_utc=completed_at,
        run_id=run_id,
    )


def _summary_payload(summary: SemanticEvaluationSummary) -> dict[str, object]:
    """Return only sanitized aggregate summary values."""
    return {
        "total_scenarios": summary.total_scenarios,
        "passed_scenarios": summary.passed_scenarios,
        "failed_scenarios": summary.failed_scenarios,
        "pass_rate": summary.pass_rate,
        "required_detection_recall": summary.required_detection_recall,
        "false_positive_scenario_count": (
            summary.false_positive_scenario_count
        ),
    }


def _scenario_lookup(
    run: LiveSemanticEvaluationRun,
    scenarios: Sequence[SemanticEvaluationScenario],
) -> dict[str, SemanticEvaluationScenario]:
    """Resolve approved scenario metadata required for sanitized artifacts."""
    lookup = {scenario.scenario_id: scenario for scenario in scenarios}
    if len(lookup) != len(tuple(scenarios)):
        raise SemanticEvaluationArtifactError(
            "artifact scenarios contain duplicate scenario IDs"
        )
    if any(record.scenario_id not in lookup for record in run.scenario_records):
        raise SemanticEvaluationArtifactError(
            "artifact scenarios do not cover every run record"
        )
    return lookup


def serialize_live_semantic_evaluation_json(
    run: LiveSemanticEvaluationRun,
    scenarios: Sequence[SemanticEvaluationScenario],
) -> str:
    """Serialize sanitized run metadata and results as deterministic JSON."""
    try:
        lookup = _scenario_lookup(run, scenarios)
        records = []
        for record in run.scenario_records:
            scenario = lookup[record.scenario_id]
            records.append(
                {
                    "scenario_id": record.scenario_id,
                    "title": scenario.title,
                    "expectation": {
                        "must_detect": [
                            code.value
                            for code in scenario.expected.must_detect
                        ],
                        "acceptable_codes": [
                            code.value
                            for code in scenario.expected.acceptable_codes
                        ],
                        "must_not_detect": [
                            code.value
                            for code in scenario.expected.must_not_detect
                        ],
                        "acceptable_dispositions": [
                            disposition.value
                            for disposition
                            in scenario.expected.acceptable_dispositions
                        ],
                        "minimum_candidate_count": (
                            scenario.expected.minimum_candidate_count
                        ),
                        "maximum_candidate_count": (
                            scenario.expected.maximum_candidate_count
                        ),
                    },
                    "detected_codes": [
                        code.value for code in record.detected_codes
                    ],
                    "detected_dispositions": [
                        disposition.value
                        for disposition in record.detected_dispositions
                    ],
                    "candidate_count": record.candidate_count,
                    "passed": record.passed,
                    "failure_reasons": list(record.failure_reasons),
                    "reviewer_model": record.reviewer_model,
                    "human_review_required": (
                        record.human_review_required
                    ),
                    "human_label_status": record.human_label_status,
                    "reviewer_notes": record.reviewer_notes,
                }
            )
        payload = {
            "run": {
                "run_id": run.run_id,
                "started_at_utc": run.started_at_utc.isoformat(),
                "completed_at_utc": run.completed_at_utc.isoformat(),
                "total_provider_calls": run.total_provider_calls,
                "human_review_status": run.human_review_status,
            },
            "scenario_records": records,
            "semantic_summary": _summary_payload(run.semantic_summary),
            "citation_only_summary": _summary_payload(
                run.citation_only_summary
            ),
        }
        return json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
    except SemanticEvaluationArtifactError:
        raise
    except Exception:
        raise SemanticEvaluationArtifactError(
            "unable to serialize semantic evaluation JSON artifact"
        ) from None


def _markdown_cell(value: object) -> str:
    """Escape one Markdown table cell without exposing additional content."""
    return str(value).replace("|", r"\|").replace("\r", " ").replace("\n", " ")


def _expectation_markdown(scenario: SemanticEvaluationScenario) -> str:
    """Render one complete bounded expectation as concise deterministic text."""
    expectation = scenario.expected
    required = ", ".join(code.value for code in expectation.must_detect) or "none"
    acceptable = (
        ", ".join(code.value for code in expectation.acceptable_codes)
        or "none"
    )
    prohibited = (
        ", ".join(code.value for code in expectation.must_not_detect)
        or "none"
    )
    dispositions = (
        " or ".join(
            disposition.value
            for disposition in expectation.acceptable_dispositions
        )
        or "none"
    )
    minimum = expectation.minimum_candidate_count
    maximum = expectation.maximum_candidate_count
    if maximum == minimum:
        candidate_count = f"exactly {minimum}"
    elif maximum is None:
        candidate_count = f"{minimum}+"
    else:
        candidate_count = f"{minimum}-{maximum}"
    return (
        f"required: {required}; acceptable: {acceptable}; "
        f"prohibited: {prohibited}; candidate count: {candidate_count}; "
        f"disposition: {dispositions}"
    )


def serialize_live_semantic_evaluation_markdown(
    run: LiveSemanticEvaluationRun,
    scenarios: Sequence[SemanticEvaluationScenario],
) -> str:
    """Serialize the sanitized human-review table as Markdown."""
    try:
        lookup = _scenario_lookup(run, scenarios)
        lines = [
            "# RoleLens Live Semantic Evaluation",
            "",
            f"- Run ID: `{_markdown_cell(run.run_id)}`",
            f"- Human review status: `{run.human_review_status}`",
            f"- Provider calls: {run.total_provider_calls}",
            "",
            "| scenario | expected | detected | disposition | pass/fail | human label | reviewer notes |",
            "|---|---|---|---|---|---|---|",
        ]
        for record in run.scenario_records:
            scenario = lookup[record.scenario_id]
            detected = ", ".join(
                code.value for code in record.detected_codes
            ) or "none"
            dispositions = ", ".join(
                disposition.value
                for disposition in record.detected_dispositions
            ) or "none"
            lines.append(
                "| "
                + " | ".join(
                    _markdown_cell(value)
                    for value in (
                        record.scenario_id,
                        _expectation_markdown(scenario),
                        detected,
                        dispositions,
                        "pass" if record.passed else "fail",
                        record.human_label_status,
                        record.reviewer_notes or "",
                    )
                )
                + " |"
            )
        return "\n".join(lines) + "\n"
    except SemanticEvaluationArtifactError:
        raise
    except Exception:
        raise SemanticEvaluationArtifactError(
            "unable to serialize semantic evaluation Markdown artifact"
        ) from None


def write_live_semantic_evaluation_artifacts(
    run: LiveSemanticEvaluationRun,
    scenarios: Sequence[SemanticEvaluationScenario],
    output_dir: Path,
) -> tuple[Path, Path]:
    """Write sanitized JSON and Markdown artifacts without overwriting files."""
    json_text = serialize_live_semantic_evaluation_json(run, scenarios)
    markdown_text = serialize_live_semantic_evaluation_markdown(run, scenarios)
    json_path = output_dir / f"semantic-evaluation-{run.run_id}.json"
    markdown_path = output_dir / f"semantic-evaluation-{run.run_id}.md"
    created_paths: list[Path] = []
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        if json_path.exists() or markdown_path.exists():
            raise SemanticEvaluationArtifactError(
                "semantic evaluation artifact already exists"
            )
        for path, content in (
            (json_path, json_text),
            (markdown_path, markdown_text),
        ):
            with path.open("x", encoding="utf-8", newline="\n") as artifact:
                artifact.write(content)
            created_paths.append(path)
    except SemanticEvaluationArtifactError:
        raise
    except Exception:
        for path in created_paths:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
        raise SemanticEvaluationArtifactError(
            "unable to write semantic evaluation artifacts"
        ) from None
    return json_path, markdown_path
