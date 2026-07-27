"""Offline tests for the fixed semantic-risk evaluation pack."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import Mock, patch

import pytest

from app.evaluation import (
    DEFAULT_SEMANTIC_SCENARIO_PATH,
    SemanticEvaluationInputError,
    SemanticEvaluationScenario,
    evaluate_citation_only_baseline,
    evaluate_semantic_scenario,
    load_semantic_scenarios,
    summarize_semantic_evaluation,
)
from app.schemas import (
    SemanticReviewDisposition,
    SemanticRiskCandidate,
    SemanticRiskCode,
    SemanticRiskReviewResult,
)


_EXPECTED_IDS = (
    "S1_supported_cautious_claim",
    "S2_unsupported_roi_budget",
    "S3_causation_overreach",
    "S4_external_context_as_company_fact",
    "S5_role_boundary_violation",
    "S6_unsupported_completion_validation",
    "S7_citation_claim_mismatch",
    "S8_ambiguous_partial_support",
)
_PRIMARY_CODES = {
    "S2_unsupported_roi_budget": SemanticRiskCode.unsupported_roi_or_budget,
    "S3_causation_overreach": SemanticRiskCode.causation_overreach,
    "S4_external_context_as_company_fact": (
        SemanticRiskCode.unsupported_company_specific_claim
    ),
    "S5_role_boundary_violation": SemanticRiskCode.role_boundary_violation,
    "S6_unsupported_completion_validation": (
        SemanticRiskCode.unsupported_completion_or_validation_claim
    ),
    "S7_citation_claim_mismatch": SemanticRiskCode.citation_claim_mismatch,
}
_EVIDENCE_ID = "ev-eval_case_00-000000000001"


def _scenario(
    scenarios: tuple[SemanticEvaluationScenario, ...],
    scenario_id: str,
) -> SemanticEvaluationScenario:
    """Return one named scenario from the fixed pack."""
    return next(item for item in scenarios if item.scenario_id == scenario_id)


def _candidate(
    scenario: SemanticEvaluationScenario,
    risk_code: SemanticRiskCode,
    disposition: SemanticReviewDisposition = (
        SemanticReviewDisposition.needs_human_review
    ),
    claim_index: int = 0,
) -> SemanticRiskCandidate:
    """Build one valid synthetic semantic candidate."""
    return SemanticRiskCandidate(
        risk_code=risk_code,
        role_key=scenario.role_key,
        claim_index=claim_index,
        evidence_ids=[_EVIDENCE_ID],
        explanation="Synthetic evaluation candidate.",
        review_question="Should a human reviewer inspect this claim?",
        confidence="medium",
        disposition=disposition,
    )


def _review(
    scenario: SemanticEvaluationScenario,
    candidates: list[SemanticRiskCandidate],
) -> SemanticRiskReviewResult:
    """Build a schema-valid review result for one scenario role."""
    human_review_required = any(
        candidate.disposition != SemanticReviewDisposition.likely_supported
        for candidate in candidates
    )
    return SemanticRiskReviewResult(
        candidates=candidates,
        reviewed_role_keys=[scenario.role_key],
        reviewer_model=None,
        human_review_required=human_review_required,
    )


def test_fixture_loads_exactly_eight_unique_scenarios_in_expected_order() -> None:
    scenarios = load_semantic_scenarios()

    assert len(scenarios) == 8
    assert tuple(scenario.scenario_id for scenario in scenarios) == _EXPECTED_IDS
    assert len({scenario.scenario_id for scenario in scenarios}) == 8


def test_required_scenario_ids_and_primary_codes_are_present() -> None:
    scenarios = load_semantic_scenarios()
    by_id = {scenario.scenario_id: scenario for scenario in scenarios}

    assert set(by_id) == set(_EXPECTED_IDS)
    assert by_id["S1_supported_cautious_claim"].expected.must_detect == ()
    for scenario_id, primary_code in _PRIMARY_CODES.items():
        assert primary_code in by_id[scenario_id].expected.must_detect
    s8 = by_id["S8_ambiguous_partial_support"].expected
    assert len(s8.acceptable_codes) > 1
    assert set(s8.acceptable_dispositions) == {
        SemanticReviewDisposition.reviewer_uncertain,
        SemanticReviewDisposition.needs_human_review,
    }
    assert set(s8.acceptable_codes) == {
        SemanticRiskCode.citation_claim_mismatch,
        SemanticRiskCode.unsupported_company_specific_claim,
    }
    assert SemanticRiskCode.causation_overreach in s8.must_not_detect
    assert by_id["S8_ambiguous_partial_support"].claim == (
        "Low-usage accounts are likely a high-churn segment and should be "
        "prioritized for the retention pilot."
    )

    s4 = by_id["S4_external_context_as_company_fact"].expected
    assert SemanticRiskCode.causation_overreach in s4.acceptable_codes
    assert SemanticRiskCode.causation_overreach not in s4.must_not_detect
    assert s4.maximum_candidate_count == 3


def test_invalid_fixtures_fail_closed() -> None:
    raw = json.loads(DEFAULT_SEMANTIC_SCENARIO_PATH.read_text(encoding="utf-8"))
    cases: list[Any] = []

    extra = json.loads(json.dumps(raw))
    extra[0]["unexpected_field"] = True
    cases.append(extra)

    duplicate = json.loads(json.dumps(raw))
    duplicate[1]["scenario_id"] = duplicate[0]["scenario_id"]
    cases.append(duplicate)

    missing = json.loads(json.dumps(raw[:-1]))
    cases.append(missing)

    wrong_required_id = json.loads(json.dumps(raw))
    wrong_required_id[-1]["scenario_id"] = "S8_unapproved_replacement"
    cases.append(wrong_required_id)

    negative_minimum = json.loads(json.dumps(raw))
    negative_minimum[0]["expected"]["minimum_candidate_count"] = -1
    cases.append(negative_minimum)

    reversed_bounds = json.loads(json.dumps(raw))
    reversed_bounds[1]["expected"]["maximum_candidate_count"] = 0
    cases.append(reversed_bounds)

    overlap = json.loads(json.dumps(raw))
    overlap[1]["expected"]["must_not_detect"].append(
        "unsupported_roi_or_budget"
    )
    cases.append(overlap)

    missing_acceptable = json.loads(json.dumps(raw))
    missing_acceptable[1]["expected"]["acceptable_codes"] = [
        "citation_claim_mismatch"
    ]
    cases.append(missing_acceptable)

    invalid_enum = json.loads(json.dumps(raw))
    invalid_enum[1]["expected"]["must_detect"] = ["not_a_semantic_risk_code"]
    cases.append(invalid_enum)
    cases.append({"scenarios": raw})

    for value in cases:
        with patch("app.evaluation._load_json", return_value=value):
            with pytest.raises(SemanticEvaluationInputError):
                load_semantic_scenarios()

    invalid_json_path = Mock()
    invalid_json_path.read_text.return_value = "{not valid JSON"
    with pytest.raises(SemanticEvaluationInputError):
        load_semantic_scenarios(invalid_json_path)


def test_supported_scenario_passes_empty_and_fails_prohibited_false_positive() -> None:
    scenario = load_semantic_scenarios()[0]

    unreviewed = SemanticRiskReviewResult(
        candidates=[],
        reviewed_role_keys=[],
        reviewer_model=None,
        human_review_required=False,
    )
    unreviewed_result = evaluate_semantic_scenario(scenario, unreviewed)
    reviewed_empty_result = evaluate_semantic_scenario(
        scenario,
        _review(scenario, []),
    )
    false_positive = _candidate(
        scenario,
        SemanticRiskCode.citation_claim_mismatch,
    )
    false_positive_result = evaluate_semantic_scenario(
        scenario,
        _review(scenario, [false_positive]),
    )

    assert unreviewed_result.passed is False
    assert any(
        "scenario role 'data_analyst' was not reviewed" == reason
        for reason in unreviewed_result.failure_reasons
    )
    assert reviewed_empty_result.passed is True
    assert reviewed_empty_result.candidate_count == 0
    assert false_positive_result.passed is False
    assert false_positive_result.forbidden_detected_codes == (
        SemanticRiskCode.citation_claim_mismatch,
    )


@pytest.mark.parametrize(
    ("scenario_id", "risk_code"),
    tuple(_PRIMARY_CODES.items()),
)
def test_required_semantic_risk_detection_passes(
    scenario_id: str,
    risk_code: SemanticRiskCode,
) -> None:
    scenario = _scenario(load_semantic_scenarios(), scenario_id)
    candidates = [_candidate(scenario, risk_code)]
    expected_codes = (risk_code,)
    if scenario_id == "S4_external_context_as_company_fact":
        candidates.extend(
            [
                _candidate(
                    scenario,
                    SemanticRiskCode.causation_overreach,
                ),
                _candidate(
                    scenario,
                    SemanticRiskCode.citation_claim_mismatch,
                ),
            ]
        )
        expected_codes = (
            SemanticRiskCode.unsupported_company_specific_claim,
            SemanticRiskCode.causation_overreach,
            SemanticRiskCode.citation_claim_mismatch,
        )

    result = evaluate_semantic_scenario(
        scenario,
        _review(scenario, candidates),
    )

    assert result.passed is True
    assert result.detected_codes == expected_codes
    assert result.missing_required_codes == ()
    if scenario_id == "S4_external_context_as_company_fact":
        assert result.candidate_count == 3


def test_missing_required_code_fails() -> None:
    scenario = _scenario(
        load_semantic_scenarios(),
        "S2_unsupported_roi_budget",
    )

    result = evaluate_semantic_scenario(scenario, _review(scenario, []))
    wrong_claim_candidate = _candidate(
        scenario,
        SemanticRiskCode.unsupported_roi_or_budget,
        claim_index=1,
    )
    wrong_claim_result = evaluate_semantic_scenario(
        scenario,
        _review(scenario, [wrong_claim_candidate]),
    )

    assert result.passed is False
    assert result.missing_required_codes == (
        SemanticRiskCode.unsupported_roi_or_budget,
    )
    assert result.detected_codes == ()
    assert wrong_claim_result.passed is False
    assert wrong_claim_result.candidate_count == 1
    assert wrong_claim_result.detected_codes == (
        SemanticRiskCode.unsupported_roi_or_budget,
    )
    assert wrong_claim_result.missing_required_codes == (
        SemanticRiskCode.unsupported_roi_or_budget,
    )
    assert any(
        "single-claim fixture contract requires claim_index=0" in reason
        for reason in wrong_claim_result.failure_reasons
    )


def test_unexpected_prohibited_disposition_and_count_failures() -> None:
    scenario = _scenario(
        load_semantic_scenarios(),
        "S2_unsupported_roi_budget",
    )
    primary = SemanticRiskCode.unsupported_roi_or_budget

    unexpected_candidate = _candidate(
        scenario,
        SemanticRiskCode.role_boundary_violation,
    )
    unexpected = evaluate_semantic_scenario(
        scenario,
        _review(scenario, [unexpected_candidate]),
    )

    prohibited_candidate = _candidate(
        scenario,
        SemanticRiskCode.causation_overreach,
    )
    prohibited = evaluate_semantic_scenario(
        scenario,
        _review(scenario, [prohibited_candidate]),
    )

    invalid_disposition_candidate = _candidate(
        scenario,
        primary,
        SemanticReviewDisposition.likely_supported,
    )
    invalid_disposition = evaluate_semantic_scenario(
        scenario,
        _review(scenario, [invalid_disposition_candidate]),
    )

    too_many_candidates = [
        _candidate(scenario, primary, claim_index=index) for index in range(3)
    ]
    invalid_count = evaluate_semantic_scenario(
        scenario,
        _review(scenario, too_many_candidates),
    )

    assert unexpected.passed is False
    assert unexpected.unexpected_codes == (
        SemanticRiskCode.role_boundary_violation,
    )
    assert prohibited.passed is False
    assert prohibited.forbidden_detected_codes == (
        SemanticRiskCode.causation_overreach,
    )
    assert invalid_disposition.passed is False
    assert any("unacceptable dispositions" in reason for reason in invalid_disposition.failure_reasons)
    assert invalid_count.passed is False
    assert invalid_count.candidate_count == 3
    assert any("exceeds maximum" in reason for reason in invalid_count.failure_reasons)


def test_summary_metrics_are_derived() -> None:
    scenarios = load_semantic_scenarios()
    supported = scenarios[0]
    roi = _scenario(scenarios, "S2_unsupported_roi_budget")
    causation = _scenario(scenarios, "S3_causation_overreach")

    false_positive = evaluate_semantic_scenario(
        supported,
        _review(
            supported,
            [_candidate(supported, SemanticRiskCode.citation_claim_mismatch)],
        ),
    )
    detected = evaluate_semantic_scenario(
        roi,
        _review(
            roi,
            [_candidate(roi, SemanticRiskCode.unsupported_roi_or_budget)],
        ),
    )
    missed = evaluate_semantic_scenario(causation, _review(causation, []))

    summary = summarize_semantic_evaluation([false_positive, detected, missed])

    assert summary.total_scenarios == 3
    assert summary.passed_scenarios == 1
    assert summary.failed_scenarios == 2
    assert summary.pass_rate == pytest.approx(1 / 3)
    assert summary.required_detection_recall == 0.5
    assert summary.false_positive_scenario_count == 1


def test_duplicate_result_ids_fail_summary_construction() -> None:
    scenario = load_semantic_scenarios()[0]
    result = evaluate_semantic_scenario(scenario, _review(scenario, []))

    with pytest.raises(SemanticEvaluationInputError, match="duplicate"):
        summarize_semantic_evaluation([result, result])


def test_citation_only_baseline_passes_only_supported_scenario() -> None:
    scenarios = load_semantic_scenarios()

    results = evaluate_citation_only_baseline(scenarios)

    assert tuple(result.scenario_id for result in results) == _EXPECTED_IDS
    assert [result.scenario_id for result in results if result.passed] == [
        "S1_supported_cautious_claim"
    ]
    assert all(result.passed is False for result in results[1:])
    assert all(result.detected_codes == () for result in results)
    assert all(result.candidate_count == 0 for result in results)
