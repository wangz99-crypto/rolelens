"""Offline construction and execution tests for the Task 7D live runner."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any, Mapping

import pytest

from app.evaluation import (
    SemanticEvaluationScenario,
    load_semantic_scenarios,
)
from app.evaluation_runner import (
    SemanticEvaluationRunnerExecutionError,
    SemanticEvaluationRunnerInputError,
    construct_live_scenario_inputs,
    run_live_semantic_evaluation,
    serialize_live_semantic_evaluation_json,
    serialize_live_semantic_evaluation_markdown,
)
from app.risk_checker import check_role_risks
from app.role_engine import InsufficientEvidence
from app.schemas import (
    EvidenceScope,
    EvidenceStatus,
    RoleKey,
    RoleView,
    SemanticReviewDisposition,
    SemanticRiskCode,
)
from app.semantic_risk_reviewer import SemanticRiskRequest


_SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "run_live_semantic_evaluation.py"
)
_REVIEWER_MODEL = "fake/granite-semantic-evaluation"
_UNKNOWN_EVIDENCE_ID = "ev-sem_eval-ffffffffffff"


@dataclass(frozen=True)
class _ResponseSpec:
    """One offline provider response instruction."""

    codes: tuple[SemanticRiskCode, ...] = ()
    disposition: SemanticReviewDisposition = (
        SemanticReviewDisposition.needs_human_review
    )
    claim_index: int = 0
    evidence_id_override: str | None = None


class _FakeSemanticRiskProvider:
    """Sequential injected provider with no environment or network access."""

    def __init__(self, specs: list[_ResponseSpec]) -> None:
        self.specs = specs
        self.calls: list[SemanticRiskRequest] = []

    def review_semantic_risks(
        self,
        request: SemanticRiskRequest,
    ) -> Mapping[str, Any]:
        call_index = len(self.calls)
        self.calls.append(request)
        spec = self.specs[call_index]
        evidence_id = (
            spec.evidence_id_override
            or request.evidence_objects[0].evidence_id
        )
        candidates = [
            {
                "risk_code": code.value,
                "role_key": request.role_views[0].role_key.value,
                "claim_index": spec.claim_index,
                "evidence_ids": [evidence_id],
                "explanation": "Synthetic offline evaluation response.",
                "review_question": "Should a human review this candidate?",
                "confidence": "medium",
                "disposition": spec.disposition.value,
            }
            for code in spec.codes
        ]
        return {
            "candidates": candidates,
            "reviewed_role_keys": [
                role_view.role_key.value
                for role_view in request.role_views
            ],
            "reviewer_model": _REVIEWER_MODEL,
            "human_review_required": bool(candidates)
            and spec.disposition
            != SemanticReviewDisposition.likely_supported,
        }


def _passing_spec(scenario: SemanticEvaluationScenario) -> _ResponseSpec:
    """Return one human-review-safe response that satisfies the fixture."""
    if scenario.expected.must_detect:
        return _ResponseSpec(codes=(scenario.expected.must_detect[0],))
    if scenario.scenario_id == "S8_ambiguous_partial_support":
        return _ResponseSpec(
            codes=(SemanticRiskCode.citation_claim_mismatch,),
            disposition=SemanticReviewDisposition.reviewer_uncertain,
        )
    return _ResponseSpec()


def _passing_specs(
    scenarios: tuple[SemanticEvaluationScenario, ...],
) -> list[_ResponseSpec]:
    """Build passing response specs in fixture order."""
    return [_passing_spec(scenario) for scenario in scenarios]


def _load_cli_module() -> ModuleType:
    """Import the CLI as a module without executing its direct-run branch."""
    spec = importlib.util.spec_from_file_location(
        "rolelens_test_live_semantic_cli",
        _SCRIPT_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_importing_runner_modules_requires_no_credentials_sdk_or_network() -> None:
    repository_root = Path(__file__).resolve().parents[1]
    probe = """
import builtins
import runpy
import sys
from types import ModuleType

sys.modules["app.granite_semantic_risk_provider"] = ModuleType(
    "app.granite_semantic_risk_provider"
)
sys.modules["ibm_watsonx_ai"] = ModuleType("ibm_watsonx_ai")
sys.modules["ibm_watsonx_ai.foundation_models"] = ModuleType(
    "ibm_watsonx_ai.foundation_models"
)
real_import = builtins.__import__

def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
    if name == "app.granite_semantic_risk_provider":
        raise AssertionError("Granite provider import attempted")
    if name == "ibm_watsonx_ai" or name.startswith("ibm_watsonx_ai."):
        raise AssertionError("IBM SDK import attempted")
    return real_import(name, globals, locals, fromlist, level)

def audit_network(event, args):
    if event in {"socket.connect", "socket.getaddrinfo"}:
        raise AssertionError("network connection attempted")

builtins.__import__ = guarded_import
sys.addaudithook(audit_network)
import app.evaluation_runner
runpy.run_path(
    "scripts/run_live_semantic_evaluation.py",
    run_name="rolelens_import_safety_probe",
)
"""
    environment = os.environ.copy()
    for name in ("WATSONX_APIKEY", "WATSONX_URL", "WATSONX_PROJECT_ID"):
        environment.pop(name, None)

    completed = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=repository_root,
        env=environment,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr


def test_each_fixture_constructs_one_evidence_view_claim_and_five_outcomes() -> None:
    scenarios = load_semantic_scenarios()

    for scenario in scenarios:
        inputs = construct_live_scenario_inputs(scenario)

        assert inputs.evidence_object.status == EvidenceStatus.active
        assert isinstance(inputs.role_view, RoleView)
        assert inputs.role_view.role_key == scenario.role_key
        assert len(inputs.role_view.key_findings) == 1
        claim_at_index_zero = inputs.role_view.key_findings[0]
        assert len(claim_at_index_zero.evidence_references) == 1
        assert (
            claim_at_index_zero.evidence_references[0].evidence_id
            == inputs.evidence_object.evidence_id
        )
        assert set(inputs.role_outcomes) == set(RoleKey)
        assert inputs.role_outcomes[scenario.role_key] is inputs.role_view
        absent = [
            outcome
            for role_key, outcome in inputs.role_outcomes.items()
            if role_key != scenario.role_key
        ]
        assert len(absent) == 4
        assert all(isinstance(item, InsufficientEvidence) for item in absent)
        check_role_risks(
            inputs.role_outcomes,
            [inputs.evidence_object],
        )


def test_fixture_text_scope_and_synthetic_identity_are_copied_exactly() -> None:
    for scenario in load_semantic_scenarios():
        first = construct_live_scenario_inputs(scenario)
        second = construct_live_scenario_inputs(scenario)
        evidence = first.evidence_object

        assert evidence.evidence_scope == scenario.evidence_scope
        assert evidence.finding == scenario.evidence_finding
        assert (
            evidence.supporting_evidence
            == scenario.evidence_supporting_evidence
        )
        assert evidence.limitations == list(scenario.evidence_limitations)
        assert first.role_view.key_findings[0].claim == scenario.claim
        assert evidence.evidence_id == second.evidence_object.evidence_id
        assert evidence.source_id == second.evidence_object.source_id
        assert "Synthetic Task 7D" in evidence.decision_relevance
        assert evidence.source_id.startswith("src-sem_eval-")


def test_all_eight_run_preserves_order_and_makes_eight_provider_calls() -> None:
    scenarios = load_semantic_scenarios()
    provider = _FakeSemanticRiskProvider(_passing_specs(scenarios))

    run = run_live_semantic_evaluation(provider, scenarios)

    assert [record.scenario_id for record in run.scenario_records] == [
        scenario.scenario_id for scenario in scenarios
    ]
    assert len(provider.calls) == 8
    assert run.total_provider_calls == 8
    assert run.semantic_summary.total_scenarios == 8
    assert run.semantic_summary.passed_scenarios == 8


def test_selected_scenarios_preserve_fixture_order_and_call_once_each() -> None:
    scenarios = load_semantic_scenarios()
    selected = (scenarios[1], scenarios[6])
    provider = _FakeSemanticRiskProvider(_passing_specs(selected))

    run = run_live_semantic_evaluation(
        provider,
        scenarios,
        selected_scenario_ids=[
            "S7_citation_claim_mismatch",
            "S2_unsupported_roi_budget",
        ],
    )

    assert [record.scenario_id for record in run.scenario_records] == [
        "S2_unsupported_roi_budget",
        "S7_citation_claim_mismatch",
    ]
    assert len(provider.calls) == 2
    assert run.total_provider_calls == 2


def test_duplicate_and_unknown_selected_ids_fail_before_provider_calls() -> None:
    scenarios = load_semantic_scenarios()
    provider = _FakeSemanticRiskProvider([])

    with pytest.raises(SemanticEvaluationRunnerInputError, match="duplicates"):
        run_live_semantic_evaluation(
            provider,
            scenarios,
            selected_scenario_ids=[
                scenarios[0].scenario_id,
                scenarios[0].scenario_id,
            ],
        )
    with pytest.raises(SemanticEvaluationRunnerInputError, match="unknown"):
        run_live_semantic_evaluation(
            provider,
            scenarios,
            selected_scenario_ids=["S99_not_approved"],
        )

    assert provider.calls == []


def test_provider_neutral_review_and_task7c_evaluator_are_applied() -> None:
    scenario = load_semantic_scenarios()[1]
    evaluator_provider = _FakeSemanticRiskProvider(
        [
            _ResponseSpec(
                codes=(SemanticRiskCode.citation_claim_mismatch,)
            )
        ]
    )

    evaluated_run = run_live_semantic_evaluation(
        evaluator_provider,
        [scenario],
    )

    assert evaluated_run.scenario_records[0].passed is False
    assert any(
        "missing required codes" in reason
        for reason in evaluated_run.scenario_records[0].failure_reasons
    )

    invalid_provider = _FakeSemanticRiskProvider(
        [
            _ResponseSpec(
                codes=(SemanticRiskCode.unsupported_roi_or_budget,),
                evidence_id_override=_UNKNOWN_EVIDENCE_ID,
            )
        ]
    )
    with pytest.raises(SemanticEvaluationRunnerExecutionError):
        run_live_semantic_evaluation(invalid_provider, [scenario])
    assert len(invalid_provider.calls) == 1


def test_run_metadata_summaries_and_human_review_state_are_locally_derived() -> None:
    scenario = load_semantic_scenarios()[1]
    provider = _FakeSemanticRiskProvider([_passing_spec(scenario)])

    run = run_live_semantic_evaluation(provider, [scenario])
    record = run.scenario_records[0]

    assert run.started_at_utc.utcoffset().total_seconds() == 0
    assert run.completed_at_utc.utcoffset().total_seconds() == 0
    assert run.completed_at_utc >= run.started_at_utc
    assert run.run_id.startswith("sem-")
    assert run.total_provider_calls == len(provider.calls) == 1
    assert run.human_review_status == "pending_human_review"
    assert record.reviewer_model == _REVIEWER_MODEL
    assert record.human_label_status == "pending_human_review"
    assert record.reviewer_notes is None
    assert run.semantic_summary.passed_scenarios == 1
    assert run.citation_only_summary.failed_scenarios == 1


def test_json_and_markdown_serialization_are_sanitized() -> None:
    all_scenarios = load_semantic_scenarios()
    scenarios = (all_scenarios[0], all_scenarios[7])
    provider = _FakeSemanticRiskProvider(_passing_specs(scenarios))
    run = run_live_semantic_evaluation(provider, scenarios)

    json_text = serialize_live_semantic_evaluation_json(run, scenarios)
    markdown_text = serialize_live_semantic_evaluation_markdown(
        run,
        scenarios,
    )
    payload = json.loads(json_text)
    combined = json_text + markdown_text
    records = {
        record["scenario_id"]: record
        for record in payload["scenario_records"]
    }
    s1 = records["S1_supported_cautious_claim"]
    s8 = records["S8_ambiguous_partial_support"]

    assert payload["run"]["human_review_status"] == "pending_human_review"
    assert s1["title"] == scenarios[0].title
    assert s8["title"] == scenarios[1].title
    assert (
        s1["human_label_status"]
        == "pending_human_review"
    )
    assert set(s1["expectation"]) == {
        "must_detect",
        "acceptable_codes",
        "must_not_detect",
        "acceptable_dispositions",
        "minimum_candidate_count",
        "maximum_candidate_count",
    }
    assert s1["expectation"]["must_detect"] == []
    assert s1["expectation"]["acceptable_codes"] == []
    assert s1["expectation"]["minimum_candidate_count"] == 0
    assert s1["expectation"]["maximum_candidate_count"] == 0
    assert s1["candidate_count"] == 0
    assert s8["expectation"]["must_detect"] == []
    assert s8["expectation"]["acceptable_codes"] == [
        "citation_claim_mismatch",
        "unsupported_company_specific_claim",
    ]
    assert s8["expectation"]["minimum_candidate_count"] == 1
    assert s8["expectation"]["maximum_candidate_count"] == 2
    assert s8["expectation"] != s1["expectation"]
    assert "expected_codes" not in s1
    assert "expected_codes" not in s8
    assert "| scenario | expected | detected | disposition | pass/fail | human label | reviewer notes |" in markdown_text
    assert "required: none; acceptable: none;" in markdown_text
    assert "candidate count: exactly 0" in markdown_text
    assert (
        "acceptable: citation_claim_mismatch, "
        "unsupported_company_specific_claim;" in markdown_text
    )
    assert "candidate count: 1-2" in markdown_text
    assert "disposition: reviewer_uncertain or needs_human_review" in markdown_text
    for scenario in scenarios:
        assert scenario.claim not in combined
        assert scenario.evidence_finding not in combined
        assert scenario.evidence_supporting_evidence not in combined
        assert all(
            limitation not in combined
            for limitation in scenario.evidence_limitations
        )
    for forbidden in (
        "WATSONX_APIKEY",
        "WATSONX_URL",
        "WATSONX_PROJECT_ID",
        "raw_prompt",
        "full_watsonx_response",
        "request_id",
        "chain_of_thought",
    ):
        assert forbidden not in combined


def test_cli_without_confirmation_exits_nonzero_and_constructs_no_provider(
    capsys: pytest.CaptureFixture[str],
) -> None:
    cli_module = _load_cli_module()
    factory_calls = 0

    def provider_factory() -> _FakeSemanticRiskProvider:
        nonlocal factory_calls
        factory_calls += 1
        return _FakeSemanticRiskProvider([])

    status = cli_module.main(
        ["--scenario", "S1_supported_cautious_claim"],
        provider_factory=provider_factory,
    )
    captured = capsys.readouterr()

    assert status != 0
    assert factory_calls == 0
    assert "zero provider calls were made" in captured.err
