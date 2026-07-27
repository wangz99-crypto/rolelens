"""Offline integrity tests for the frozen semantic-risk holdout pack."""

from __future__ import annotations

import json
from difflib import SequenceMatcher
from unittest.mock import Mock, patch

import pytest

from app.evaluation import (
    DEFAULT_SEMANTIC_HOLDOUT_PATH,
    DEFAULT_SEMANTIC_SCENARIO_PATH,
    SemanticEvaluationInputError,
    load_semantic_holdout_scenarios,
    load_semantic_scenarios,
)
from app.schemas import SemanticReviewDisposition, SemanticRiskCode


_HOLDOUT_IDS = (
    "H1_supported_exact_metric",
    "H2_supported_data_quality_limitation",
    "H3_unsupported_payback_staffing",
    "H4_observational_causation",
    "H5_external_benchmark_as_internal_demand",
    "H6_data_engineer_action_authorization",
    "H7_planned_test_as_completed",
    "H8_unrelated_contract_claim",
)
_PRIMARY_CODES = {
    "H3_unsupported_payback_staffing": (
        SemanticRiskCode.unsupported_roi_or_budget
    ),
    "H4_observational_causation": SemanticRiskCode.causation_overreach,
    "H5_external_benchmark_as_internal_demand": (
        SemanticRiskCode.unsupported_company_specific_claim
    ),
    "H6_data_engineer_action_authorization": (
        SemanticRiskCode.role_boundary_violation
    ),
    "H7_planned_test_as_completed": (
        SemanticRiskCode.unsupported_completion_or_validation_claim
    ),
    "H8_unrelated_contract_claim": SemanticRiskCode.citation_claim_mismatch,
}


def test_holdout_loads_exactly_eight_unique_ids_in_approved_order() -> None:
    scenarios = load_semantic_holdout_scenarios()

    assert len(scenarios) == 8
    assert tuple(scenario.scenario_id for scenario in scenarios) == _HOLDOUT_IDS
    assert len({scenario.scenario_id for scenario in scenarios}) == 8


def test_holdout_ids_do_not_overlap_calibration_ids() -> None:
    holdout_ids = {
        scenario.scenario_id
        for scenario in load_semantic_holdout_scenarios()
    }
    calibration_ids = {
        scenario.scenario_id for scenario in load_semantic_scenarios()
    }

    assert holdout_ids.isdisjoint(calibration_ids)


def test_h1_and_h2_are_strict_zero_candidate_safe_controls() -> None:
    scenarios = load_semantic_holdout_scenarios()
    all_codes = set(SemanticRiskCode)

    for scenario in scenarios[:2]:
        expectation = scenario.expected
        assert expectation.must_detect == ()
        assert expectation.acceptable_codes == ()
        assert set(expectation.must_not_detect) == all_codes
        assert set(expectation.acceptable_dispositions) == set(
            SemanticReviewDisposition
        )
        assert expectation.minimum_candidate_count == 0
        assert expectation.maximum_candidate_count == 0


def test_h3_through_h8_have_intended_required_primary_codes() -> None:
    by_id = {
        scenario.scenario_id: scenario
        for scenario in load_semantic_holdout_scenarios()
    }

    for scenario_id, primary_code in _PRIMARY_CODES.items():
        assert by_id[scenario_id].expected.must_detect == (primary_code,)


def test_holdout_examples_are_synthetic_and_claims_are_unseen() -> None:
    holdout = load_semantic_holdout_scenarios()
    calibration = load_semantic_scenarios()
    calibration_claims = {scenario.claim for scenario in calibration}

    for scenario in holdout:
        combined = " ".join(
            (
                scenario.title,
                scenario.purpose,
                scenario.evidence_finding,
                scenario.evidence_supporting_evidence,
                *scenario.evidence_limitations,
                scenario.claim,
                scenario.rationale,
            )
        ).lower()
        assert "synthetic" in combined
        assert scenario.claim not in calibration_claims
        assert max(
            SequenceMatcher(
                None,
                scenario.claim.lower(),
                calibration_scenario.claim.lower(),
            ).ratio()
            for calibration_scenario in calibration
        ) < 0.75


def test_invalid_holdout_inputs_fail_closed() -> None:
    raw = json.loads(DEFAULT_SEMANTIC_HOLDOUT_PATH.read_text(encoding="utf-8"))
    invalid_values: list[object] = []

    duplicate = json.loads(json.dumps(raw))
    duplicate[1]["scenario_id"] = duplicate[0]["scenario_id"]
    invalid_values.append(duplicate)

    invalid_values.append(json.loads(json.dumps(raw[:-1])))

    extra_id = json.loads(json.dumps(raw))
    extra_scenario = json.loads(json.dumps(raw[-1]))
    extra_scenario["scenario_id"] = "H9_unapproved_extra"
    extra_id.append(extra_scenario)
    invalid_values.append(extra_id)

    extra_field = json.loads(json.dumps(raw))
    extra_field[0]["unapproved_field"] = True
    invalid_values.append(extra_field)

    invalid_relationship = json.loads(json.dumps(raw))
    invalid_relationship[2]["expected"]["must_not_detect"].append(
        "unsupported_roi_or_budget"
    )
    invalid_values.append(invalid_relationship)

    invalid_enum = json.loads(json.dumps(raw))
    invalid_enum[2]["expected"]["must_detect"] = ["unknown_risk_code"]
    invalid_values.append(invalid_enum)

    for value in invalid_values:
        with patch("app.evaluation._load_json", return_value=value):
            with pytest.raises(SemanticEvaluationInputError):
                load_semantic_holdout_scenarios()

    invalid_json_path = Mock()
    invalid_json_path.read_text.return_value = "{not valid JSON"
    with pytest.raises(SemanticEvaluationInputError):
        load_semantic_holdout_scenarios(invalid_json_path)


def test_holdout_loader_does_not_weaken_calibration_loader() -> None:
    calibration = load_semantic_scenarios()
    holdout = load_semantic_holdout_scenarios()
    calibration_raw = json.loads(
        DEFAULT_SEMANTIC_SCENARIO_PATH.read_text(encoding="utf-8")
    )
    holdout_raw = json.loads(
        DEFAULT_SEMANTIC_HOLDOUT_PATH.read_text(encoding="utf-8")
    )

    assert len(calibration) == len(holdout) == 8
    with patch("app.evaluation._load_json", return_value=holdout_raw):
        with pytest.raises(SemanticEvaluationInputError):
            load_semantic_scenarios()
    with patch("app.evaluation._load_json", return_value=calibration_raw):
        with pytest.raises(SemanticEvaluationInputError):
            load_semantic_holdout_scenarios()


def test_holdout_contains_no_credentials_cloud_ids_or_real_company_data() -> None:
    raw_text = DEFAULT_SEMANTIC_HOLDOUT_PATH.read_text(
        encoding="utf-8"
    ).lower()
    forbidden = (
        "watsonx",
        "api_key",
        "apikey",
        "project_id",
        "cloud.ibm",
        "http://",
        "https://",
        "openai",
        "microsoft",
        "salesforce",
    )

    assert all(value not in raw_text for value in forbidden)
    assert raw_text.count("synthetic") >= 8
