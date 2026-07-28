"""Offline tests for the fixed Task 8B workflow evaluation pack."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from app.role_engine import InsufficientEvidence, RoleGenerationFailure
from app.schemas import (
    EvidenceStatus,
    RoleKey,
    RoleView,
    SemanticRiskCode,
    WorkflowPlan,
    WorkflowPlanStatus,
    WorkflowStep,
    WorkflowStepKind,
    WorkflowStepStatus,
)
from app.workflow_evaluation import (
    DEFAULT_WORKFLOW_SCENARIO_PATH,
    WorkflowEvaluationInputError,
    WorkflowEvaluationScenario,
    build_workflow_scenario_inputs,
    evaluate_flat_action_list_baseline,
    evaluate_workflow_scenario,
    load_workflow_scenarios,
    run_workflow_evaluation,
)
from app.workflow_planner import plan_workflow


_EXPECTED_IDS = (
    "W1_healthy_full_sequence",
    "W2_data_engineer_blocker",
    "W3_semantic_review_gate",
    "W4_nonblocking_deterministic_review",
    "W5_failed_roles_no_fabricated_actions",
    "W6_duplicate_resolution_grouping",
    "W7_dependency_note_is_non_executable",
    "W8_no_actionable_steps",
)


def _scenario(
    scenarios: tuple[WorkflowEvaluationScenario, ...],
    scenario_id: str,
) -> WorkflowEvaluationScenario:
    """Return one scenario by its fixed identifier."""
    return next(
        scenario
        for scenario in scenarios
        if scenario.scenario_id == scenario_id
    )


def _plan(scenario: WorkflowEvaluationScenario):
    """Build the production deterministic plan for one scenario."""
    inputs = build_workflow_scenario_inputs(scenario)
    return plan_workflow(
        inputs.role_outcomes,
        inputs.evidence_objects,
        inputs.deterministic_risk_result,
        inputs.semantic_risk_result,
    )


def _write_fixture(
    path: Path,
    payload: object,
) -> Path:
    """Write one JSON fixture mutation for fail-closed loading tests."""
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _mutate_step(
    plan: WorkflowPlan,
    sequence: int,
    **updates: object,
) -> WorkflowPlan:
    """Rebuild one step and its plan through full schema validation."""
    steps = list(plan.steps)
    original = steps[sequence - 1]
    step_payload = original.model_dump()
    step_payload.update(updates)
    steps[sequence - 1] = WorkflowStep.model_validate(step_payload)
    plan_payload = plan.model_dump(exclude={"steps"})
    plan_payload["steps"] = [step.model_dump() for step in steps]
    return WorkflowPlan.model_validate(plan_payload)


def test_fixture_loads_exactly_eight_unique_ids_in_approved_order() -> None:
    """The fixed pack contains exactly W1-W8 in approved order."""
    scenarios = load_workflow_scenarios()

    assert len(scenarios) == 8
    assert tuple(scenario.scenario_id for scenario in scenarios) == _EXPECTED_IDS
    assert len({scenario.scenario_id for scenario in scenarios}) == 8


def test_invalid_fixture_shapes_and_role_relationships_fail_closed(
    tmp_path: Path,
) -> None:
    """Malformed syntax, expectations, IDs, and role links are rejected."""
    raw = json.loads(
        DEFAULT_WORKFLOW_SCENARIO_PATH.read_text(encoding="utf-8")
    )
    cases: list[object] = []

    duplicate = json.loads(json.dumps(raw))
    duplicate[1]["scenario_id"] = duplicate[0]["scenario_id"]
    cases.append(duplicate)

    cases.append(raw[:-1])

    reordered = json.loads(json.dumps(raw))
    reordered[0], reordered[1] = reordered[1], reordered[0]
    cases.append(reordered)

    extra_field = json.loads(json.dumps(raw))
    extra_field[0]["unexpected"] = True
    cases.append(extra_field)

    malformed_signature = json.loads(json.dumps(raw))
    malformed_signature[0]["expected"]["step_signatures"][0] = (
        "role_action-data_engineer"
    )
    cases.append(malformed_signature)

    invalid_dependency = json.loads(json.dumps(raw))
    invalid_dependency[0]["expected"]["dependency_sequences"][1] = [2]
    cases.append(invalid_dependency)

    overlap = json.loads(json.dumps(raw))
    overlap[4]["generation_failure_roles"].append("data_engineer")
    cases.append(overlap)

    unsuccessful_mapping = json.loads(json.dumps(raw))
    unsuccessful_mapping[4]["role_actions"]["executive"] = "Invalid action."
    cases.append(unsuccessful_mapping)

    invalid_claim_role = json.loads(json.dumps(raw))
    invalid_claim_role[4]["deterministic_findings"][0]["claim_index"] = 0
    cases.append(invalid_claim_role)

    invalid_semantic_role = json.loads(json.dumps(raw))
    invalid_semantic_role[4]["semantic_candidates"].append(
        {
            "role_key": "project_manager",
            "risk_code": "citation_claim_mismatch",
            "disposition": "needs_human_review",
            "review_question": "Review this invalid relationship.",
            "claim_index": 0,
        }
    )
    cases.append(invalid_semantic_role)

    blank_text = json.loads(json.dumps(raw))
    blank_text[0]["title"] = " "
    cases.append(blank_text)

    duplicate_role = json.loads(json.dumps(raw))
    duplicate_role[0]["successful_roles"].append("executive")
    cases.append(duplicate_role)

    for index, payload in enumerate(cases):
        path = _write_fixture(tmp_path / f"invalid-{index}.json", payload)
        with pytest.raises(WorkflowEvaluationInputError):
            load_workflow_scenarios(path)

    invalid_json = tmp_path / "invalid-json.json"
    invalid_json.write_text("{not valid JSON", encoding="utf-8")
    with pytest.raises(WorkflowEvaluationInputError):
        load_workflow_scenarios(invalid_json)

    top_level_object = _write_fixture(
        tmp_path / "top-level-object.json",
        {"scenarios": raw},
    )
    with pytest.raises(WorkflowEvaluationInputError):
        load_workflow_scenarios(top_level_object)


def test_input_construction_is_stable_and_preserves_fixture_text() -> None:
    """Construction creates five outcomes, five stable evidence records, and exact text."""
    scenarios = load_workflow_scenarios()
    scenario = _scenario(
        scenarios,
        "W5_failed_roles_no_fabricated_actions",
    )

    first = build_workflow_scenario_inputs(scenario)
    second = build_workflow_scenario_inputs(scenario)

    assert first == second
    assert set(first.role_outcomes) == set(RoleKey)
    assert len(first.evidence_objects) == 5
    assert len(
        {evidence.evidence_id for evidence in first.evidence_objects}
    ) == 5
    assert all(
        evidence.status is EvidenceStatus.active
        for evidence in first.evidence_objects
    )
    assert isinstance(
        first.role_outcomes[RoleKey.data_engineer],
        RoleView,
    )
    assert (
        first.role_outcomes[RoleKey.data_engineer].next_action
        == "Validate the available event data."
    )
    assert isinstance(
        first.role_outcomes[RoleKey.sales_marketing],
        RoleGenerationFailure,
    )
    assert isinstance(
        first.role_outcomes[RoleKey.executive],
        InsufficientEvidence,
    )
    assert [
        finding.required_action
        for finding in first.deterministic_risk_result.findings
    ] == [
        "Acquire executive decision evidence.",
        "Resolve the Sales and Marketing generation failure.",
    ]


def test_w1_healthy_sequence_passes_with_exact_fixed_dag() -> None:
    """W1 produces the five governed actions and exact prerequisite edges."""
    scenario = load_workflow_scenarios()[0]
    plan = _plan(scenario)
    result = evaluate_workflow_scenario(scenario, plan)

    assert result.passed is True
    assert result.failure_reasons == ()
    assert result.actual_plan_status is WorkflowPlanStatus.ready_for_human_review
    assert result.actual_step_signatures == scenario.expected.step_signatures
    assert result.actual_dependency_sequences == (
        (),
        (1,),
        (1, 2),
        (1, 2, 3),
        (1, 2, 3, 4),
    )

    missing_evidence = _mutate_step(
        plan,
        1,
        supporting_evidence_ids=[],
    )
    missing_evidence_result = evaluate_workflow_scenario(
        scenario,
        missing_evidence,
    )
    assert missing_evidence_result.passed is False
    assert any(
        "role action evidence lineage mismatch" in reason
        for reason in missing_evidence_result.failure_reasons
    )


def test_w2_blocker_and_w4_review_have_distinct_propagation() -> None:
    """Hard blockers and nonblocking human-review requirements remain distinct."""
    scenarios = load_workflow_scenarios()
    blocker = _scenario(scenarios, "W2_data_engineer_blocker")
    review = _scenario(
        scenarios,
        "W4_nonblocking_deterministic_review",
    )
    blocker_plan = _plan(blocker)
    review_plan = _plan(review)

    assert evaluate_workflow_scenario(blocker, blocker_plan).passed is True
    assert evaluate_workflow_scenario(review, review_plan).passed is True
    assert blocker_plan.plan_status is WorkflowPlanStatus.blocked
    assert blocker_plan.blocking_step_ids == ["wf-001"]
    assert all(
        step.status is WorkflowStepStatus.blocked
        for step in blocker_plan.steps
        if step.step_kind is WorkflowStepKind.role_action
    )
    assert review_plan.plan_status is WorkflowPlanStatus.ready_for_human_review
    assert review_plan.blocking_step_ids == []
    review_actions = {
        step.owner_role: step.status
        for step in review_plan.steps
        if step.step_kind is WorkflowStepKind.role_action
    }
    assert review_actions[RoleKey.data_engineer] is WorkflowStepStatus.ready
    assert (
        review_actions[RoleKey.data_analyst]
        is WorkflowStepStatus.pending_human_review
    )

    ready_resolution = _mutate_step(
        blocker_plan,
        1,
        status=WorkflowStepStatus.ready,
    )
    no_review_resolution = _mutate_step(
        blocker_plan,
        1,
        human_review_required=False,
    )
    missing_action_risk = _mutate_step(
        blocker_plan,
        2,
        deterministic_risk_codes=[],
    )
    ready_result = evaluate_workflow_scenario(
        blocker,
        ready_resolution,
    )
    no_review_result = evaluate_workflow_scenario(
        blocker,
        no_review_resolution,
    )
    missing_action_risk_result = evaluate_workflow_scenario(
        blocker,
        missing_action_risk,
    )
    assert ready_result.passed is False
    assert any(
        "deterministic step status mismatch" in reason
        for reason in ready_result.failure_reasons
    )
    assert no_review_result.passed is False
    assert any(
        "deterministic human-review state mismatch" in reason
        for reason in no_review_result.failure_reasons
    )
    assert missing_action_risk_result.passed is False
    assert any(
        "role action deterministic risk lineage mismatch" in reason
        for reason in missing_action_risk_result.failure_reasons
    )


def test_w3_consolidates_nonblocking_gate_and_excludes_likely_supported() -> None:
    """W3 creates one Executive gate from only qualifying candidates."""
    scenario = _scenario(
        load_workflow_scenarios(),
        "W3_semantic_review_gate",
    )
    plan = _plan(scenario)
    result = evaluate_workflow_scenario(scenario, plan)
    gates = [
        step
        for step in plan.steps
        if step.step_kind is WorkflowStepKind.semantic_review_gate
    ]

    assert result.passed is True
    assert len(gates) == 1
    assert gates[0].owner_role is RoleKey.executive
    assert gates[0].semantic_risk_codes == [
        SemanticRiskCode.unsupported_company_specific_claim,
        SemanticRiskCode.citation_claim_mismatch,
    ]
    assert SemanticRiskCode.role_boundary_violation not in (
        gates[0].semantic_risk_codes
    )
    assert gates[0].blocks_downstream is False
    assert plan.blocking_step_ids == []

    inputs = build_workflow_scenario_inputs(scenario)
    executive_view = inputs.role_outcomes[RoleKey.executive]
    assert isinstance(executive_view, RoleView)
    expected_evidence_id = (
        executive_view.key_findings[0].evidence_references[0].evidence_id
    )
    executive_action = next(
        step
        for step in plan.steps
        if step.step_kind is WorkflowStepKind.role_action
        and step.owner_role is RoleKey.executive
    )
    assert gates[0].supporting_evidence_ids == [expected_evidence_id]
    assert executive_action.semantic_risk_codes == [
        SemanticRiskCode.unsupported_company_specific_claim,
        SemanticRiskCode.citation_claim_mismatch,
    ]
    assert (
        SemanticRiskCode.role_boundary_violation
        not in executive_action.semantic_risk_codes
    )

    missing_gate_evidence = _mutate_step(
        plan,
        gates[0].sequence,
        supporting_evidence_ids=[],
    )
    missing_action_semantic = _mutate_step(
        plan,
        executive_action.sequence,
        semantic_risk_codes=[],
    )
    missing_gate_result = evaluate_workflow_scenario(
        scenario,
        missing_gate_evidence,
    )
    missing_action_semantic_result = evaluate_workflow_scenario(
        scenario,
        missing_action_semantic,
    )
    assert missing_gate_result.passed is False
    assert any(
        "semantic gate evidence lineage mismatch" in reason
        for reason in missing_gate_result.failure_reasons
    )
    assert missing_action_semantic_result.passed is False
    assert any(
        "role action semantic risk lineage mismatch" in reason
        for reason in missing_action_semantic_result.failure_reasons
    )


def test_w5_omits_failed_role_actions_and_w6_groups_exact_actions() -> None:
    """Unsuccessful roles get no actions and equal resolutions group exactly."""
    scenarios = load_workflow_scenarios()
    failed = _scenario(
        scenarios,
        "W5_failed_roles_no_fabricated_actions",
    )
    grouped = _scenario(
        scenarios,
        "W6_duplicate_resolution_grouping",
    )
    failed_plan = _plan(failed)
    grouped_plan = _plan(grouped)

    assert evaluate_workflow_scenario(failed, failed_plan).passed is True
    assert evaluate_workflow_scenario(grouped, grouped_plan).passed is True
    failed_action_roles = {
        step.owner_role
        for step in failed_plan.steps
        if step.step_kind is WorkflowStepKind.role_action
    }
    assert failed_action_roles == {
        RoleKey.data_engineer,
        RoleKey.data_analyst,
    }
    resolutions = [
        step
        for step in grouped_plan.steps
        if step.step_kind
        is WorkflowStepKind.deterministic_risk_resolution
    ]
    assert len(resolutions) == 1
    assert resolutions[0].deterministic_risk_codes == [
        item.risk_code for item in grouped.deterministic_findings
    ]
    assert resolutions[0].dependency_notes == [
        item.message for item in grouped.deterministic_findings
    ]


def test_w7_dependency_text_is_only_a_note_and_never_changes_dag() -> None:
    """Adversarial dependency prose stays visible and non-executable."""
    scenario = _scenario(
        load_workflow_scenarios(),
        "W7_dependency_note_is_non_executable",
    )
    plan = _plan(scenario)
    result = evaluate_workflow_scenario(scenario, plan)
    sales_step = next(
        step
        for step in plan.steps
        if step.step_kind is WorkflowStepKind.role_action
        and step.owner_role is RoleKey.sales_marketing
    )
    dependency_text = scenario.role_dependencies[RoleKey.sales_marketing]

    assert result.passed is True
    assert sales_step.dependency_notes == [dependency_text]
    assert sales_step.dependency_step_ids == [
        "wf-001",
        "wf-002",
        "wf-003",
    ]
    assert all(step.action != dependency_text for step in plan.steps)
    assert result.actual_dependency_sequences == (
        (),
        (1,),
        (1, 2),
        (1, 2, 3),
        (1, 2, 3, 4),
    )


def test_w8_and_full_rolelens_pack_pass_and_are_repeatable() -> None:
    """W8 is explicitly empty and all eight governed scenarios pass twice."""
    scenarios = load_workflow_scenarios()
    no_action = _scenario(scenarios, "W8_no_actionable_steps")
    no_action_plan = _plan(no_action)
    no_action_result = evaluate_workflow_scenario(
        no_action,
        no_action_plan,
    )
    first = run_workflow_evaluation(scenarios)
    second = run_workflow_evaluation(scenarios)

    assert no_action_result.passed is True
    assert no_action_plan.steps == []
    assert (
        no_action_plan.plan_status
        is WorkflowPlanStatus.no_actionable_steps
    )
    assert no_action_plan.human_review_required is True
    assert first == second
    assert first.total_scenarios == 8
    assert first.passed_scenarios == 8
    assert first.failed_scenarios == 0
    assert first.pass_rate == 1.0


def test_flat_action_baseline_passes_only_w8_without_provider_or_model_call() -> None:
    """The transparent flat list cannot satisfy governed workflow expectations."""
    scenarios = load_workflow_scenarios()

    with patch(
        "app.workflow_evaluation.plan_workflow",
        side_effect=AssertionError("baseline must not call the planner"),
    ), patch(
        "socket.create_connection",
        side_effect=AssertionError("baseline must not use the network"),
    ):
        first = evaluate_flat_action_list_baseline(scenarios)
        second = evaluate_flat_action_list_baseline(scenarios)

    assert first == second
    assert first.total_scenarios == 8
    assert first.passed_scenarios == 1
    assert first.failed_scenarios == 7
    assert tuple(
        result.scenario_id
        for result in first.scenario_results
        if result.passed
    ) == ("W8_no_actionable_steps",)
