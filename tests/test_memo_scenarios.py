"""Offline tests for the fixed Task 9C memo evaluation pack."""

from __future__ import annotations

import builtins
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from app.human_review import review_workflow_plan, workflow_plan_digest
from app.memo_evaluation import (
    DEFAULT_MEMO_SCENARIO_PATH,
    MemoEvaluationInputError,
    MemoEvaluationScenario,
    MemoScenarioEvaluationResult,
    build_memo_scenario_inputs,
    evaluate_memo_scenario,
    evaluate_polished_action_summary_baseline,
    load_memo_scenarios,
    run_memo_evaluation,
)
from app.memo_generator import DecisionMemoInputError, compose_decision_memo
from app.schemas import (
    DecisionMemoActionOrigin,
    DecisionMemoStatus,
    EvidenceScope,
    EvidenceStatus,
    HumanReviewDecision,
    HumanReviewSessionStatus,
    HumanReviewStepInput,
    RiskCode,
    RoleKey,
    SemanticRiskCode,
    WorkflowPlan,
    WorkflowStepStatus,
)


_EXPECTED_IDS = (
    "M1_complete_all_accept",
    "M2_rejected_action_auditable",
    "M3_human_revision_requires_revalidation",
    "M4_blocker_persists_after_review",
    "M5_semantic_gate_non_authoritative",
    "M6_missing_information_survives_rejection",
    "M7_incomplete_review_fails_closed",
    "M8_empty_plan_acknowledged",
)


def _scenario(
    scenarios: tuple[MemoEvaluationScenario, ...],
    scenario_id: str,
) -> MemoEvaluationScenario:
    """Return one scenario by fixed ID."""
    return next(
        scenario
        for scenario in scenarios
        if scenario.scenario_id == scenario_id
    )


def _write_fixture(path: Path, payload: object) -> Path:
    """Write one JSON fixture mutation."""
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _memo(scenario: MemoEvaluationScenario):
    """Compose one production memo from fixed scenario inputs."""
    inputs = build_memo_scenario_inputs(scenario)
    session = review_workflow_plan(
        inputs.workflow_plan,
        inputs.decisions,
        no_action_acknowledged=inputs.no_action_acknowledged,
        overall_note=inputs.overall_note,
    )
    return inputs, session, compose_decision_memo(
        inputs.workflow_plan,
        session,
        inputs.evidence_objects,
    )


def _evaluate_tampered_memo(
    scenario: MemoEvaluationScenario,
    memo: object,
) -> MemoScenarioEvaluationResult:
    """Evaluate one patched composer result through the production harness."""
    with patch(
        "app.memo_evaluation.compose_decision_memo",
        return_value=memo,
    ):
        return evaluate_memo_scenario(scenario)


def test_fixture_loads_exactly_eight_unique_ids_in_approved_order() -> None:
    """The fixed pack contains exactly M1-M8 in approved order."""
    scenarios = load_memo_scenarios()

    assert len(scenarios) == 8
    assert tuple(scenario.scenario_id for scenario in scenarios) == _EXPECTED_IDS
    assert len({scenario.scenario_id for scenario in scenarios}) == 8


def test_malformed_fixture_inputs_and_expectations_fail_closed(
    tmp_path: Path,
) -> None:
    """Syntax, IDs, templates, decisions, text, and expectations are strict."""
    raw = json.loads(DEFAULT_MEMO_SCENARIO_PATH.read_text(encoding="utf-8"))
    cases: list[object] = []

    duplicate_id = json.loads(json.dumps(raw))
    duplicate_id[1]["scenario_id"] = duplicate_id[0]["scenario_id"]
    cases.append(duplicate_id)
    cases.append(raw[:-1])

    reordered = json.loads(json.dumps(raw))
    reordered[0], reordered[1] = reordered[1], reordered[0]
    cases.append(reordered)

    extra_scenario_field = json.loads(json.dumps(raw))
    extra_scenario_field[0]["unexpected"] = True
    cases.append(extra_scenario_field)

    extra_expectation_field = json.loads(json.dumps(raw))
    extra_expectation_field[0]["expected"]["unexpected"] = True
    cases.append(extra_expectation_field)

    invalid_template = json.loads(json.dumps(raw))
    invalid_template[0]["plan_template"] = "unknown"
    cases.append(invalid_template)

    invalid_decision_id = json.loads(json.dumps(raw))
    invalid_decision_id[0]["decisions"]["wf-999"] = (
        invalid_decision_id[0]["decisions"].pop("wf-001")
    )
    cases.append(invalid_decision_id)

    semantic_revision = json.loads(json.dumps(raw))
    semantic_revision[1]["decisions"]["wf-002"] = {
        "decision": "revise",
        "reviewer_note": "Invalid gate revision.",
        "revised_action": "Rewrite a probabilistic gate.",
    }
    cases.append(semantic_revision)

    unchanged_revision = json.loads(json.dumps(raw))
    unchanged_revision[2]["decisions"]["wf-003"]["revised_action"] = (
        "Review the bounded retention priority."
    )
    unchanged_revision[2]["expected"]["revised_actions"]["wf-003"] = (
        "Review the bounded retention priority."
    )
    cases.append(unchanged_revision)

    nonempty_acknowledgment = json.loads(json.dumps(raw))
    nonempty_acknowledgment[0]["no_action_acknowledged"] = True
    cases.append(nonempty_acknowledgment)

    empty_without_acknowledgment = json.loads(json.dumps(raw))
    empty_without_acknowledgment[7]["no_action_acknowledged"] = False
    cases.append(empty_without_acknowledgment)

    malformed_expectation = json.loads(json.dumps(raw))
    malformed_expectation[0]["expected"]["memo_status"] = None
    cases.append(malformed_expectation)

    nonempty_error_sections = json.loads(json.dumps(raw))
    nonempty_error_sections[6]["expected"]["evidence_ids"] = [
        "ev-memo_eval-000000000001"
    ]
    cases.append(nonempty_error_sections)

    blank_text = json.loads(json.dumps(raw))
    blank_text[0]["title"] = " "
    cases.append(blank_text)

    invalid_enum = json.loads(json.dumps(raw))
    invalid_enum[0]["expected"]["memo_status"] = "complete"
    cases.append(invalid_enum)

    duplicate_tuple_value = json.loads(json.dumps(raw))
    duplicate_tuple_value[0]["expected"]["evidence_ids"].append(
        "ev-memo_eval-000000000001"
    )
    cases.append(duplicate_tuple_value)

    overlong_evidence_abbreviation = json.loads(json.dumps(raw))
    overlong_evidence_abbreviation[0]["expected"]["evidence_ids"][0] = (
        "ev-memo_evaluation-000000000001"
    )
    cases.append(overlong_evidence_abbreviation)

    for index, payload in enumerate(cases):
        path = _write_fixture(tmp_path / f"invalid-{index}.json", payload)
        with pytest.raises(MemoEvaluationInputError):
            load_memo_scenarios(path)

    invalid_json = tmp_path / "invalid-json.json"
    invalid_json.write_text("{not valid JSON", encoding="utf-8")
    with pytest.raises(MemoEvaluationInputError):
        load_memo_scenarios(invalid_json)

    top_level_object = _write_fixture(
        tmp_path / "top-level.json",
        {"scenarios": raw},
    )
    with pytest.raises(MemoEvaluationInputError):
        load_memo_scenarios(top_level_object)

    duplicate_decision_key = tmp_path / "duplicate-key.json"
    original_text = DEFAULT_MEMO_SCENARIO_PATH.read_text(encoding="utf-8")
    duplicate_decision_key.write_text(
        original_text.replace(
            '"decisions": {',
            (
                '"decisions": {'
                '"wf-999": {"decision": "accept", '
                '"reviewer_note": null, "revised_action": null},'
                '"wf-999": {"decision": "accept", '
                '"reviewer_note": null, "revised_action": null},'
            ),
            1,
        ),
        encoding="utf-8",
    )
    with pytest.raises(MemoEvaluationInputError):
        load_memo_scenarios(duplicate_decision_key)

    with pytest.raises(MemoEvaluationInputError):
        load_memo_scenarios(tmp_path / "missing.json")


def test_input_construction_is_stable_validated_and_text_exact() -> None:
    """Fixed templates create stable production plans, Evidence, and decisions."""
    scenario = _scenario(
        load_memo_scenarios(),
        "M3_human_revision_requires_revalidation",
    )

    first = build_memo_scenario_inputs(scenario)
    second = build_memo_scenario_inputs(scenario)

    assert first == second
    assert WorkflowPlan.model_validate(first.workflow_plan.model_dump()) == (
        first.workflow_plan
    )
    assert tuple(
        evidence.evidence_id for evidence in first.evidence_objects
    ) == tuple(
        f"ev-memo_eval-{index:012d}" for index in range(1, 5)
    )
    assert tuple(
        evidence.source_id for evidence in first.evidence_objects
    ) == tuple(
        f"src-memo_eval-{index:012d}" for index in range(1, 5)
    )
    assert all(
        evidence.status is EvidenceStatus.active
        and evidence.evidence_scope is EvidenceScope.internal_observation
        and evidence.extraction_method == "deterministic"
        and "Synthetic" in evidence.finding
        for evidence in first.evidence_objects
    )
    assert first.decisions == scenario.decisions
    assert first.decisions["wf-002"].reviewer_note == (
        "Probabilistic concern reviewed before revision."
    )
    assert first.decisions["wf-003"].revised_action == (
        "Draft a conditional retention priority for revalidation."
    )


def test_m1_all_accept_preserves_exact_actions_evidence_and_digest() -> None:
    """M1 produces exact accepted originals and a reviewed, bound memo."""
    scenario = load_memo_scenarios()[0]
    inputs, session, memo = _memo(scenario)
    result = evaluate_memo_scenario(scenario)

    assert result.passed is True
    assert result.failure_reasons == ()
    assert memo.memo_status is DecisionMemoStatus.reviewed
    assert memo.plan_digest == workflow_plan_digest(inputs.workflow_plan)
    assert memo.plan_step_ids == ["wf-001", "wf-002"]
    assert [action.action for action in memo.retained_actions] == [
        step.action for step in inputs.workflow_plan.steps
    ]
    assert all(
        action.action_origin is DecisionMemoActionOrigin.accepted_original
        for action in memo.retained_actions
    )
    assert [item.evidence_id for item in memo.evidence_items] == [
        "ev-memo_eval-000000000001",
        "ev-memo_eval-000000000002",
    ]
    assert [item.finding for item in memo.evidence_items] == [
        evidence.finding for evidence in inputs.evidence_objects
    ]
    assert memo.control_notices == [
        "Simulated human review does not authorize execution."
    ]
    assert session.human_review_complete is True


def test_m2_rejection_is_auditable_and_m6_gap_survives_rejection() -> None:
    """Rejected work stays out of actions while its audit and gaps remain."""
    scenarios = load_memo_scenarios()
    m2 = _scenario(scenarios, "M2_rejected_action_auditable")
    m6 = _scenario(
        scenarios,
        "M6_missing_information_survives_rejection",
    )
    m2_inputs, _, m2_memo = _memo(m2)
    _, _, m6_memo = _memo(m6)

    assert evaluate_memo_scenario(m2).passed is True
    assert evaluate_memo_scenario(m6).passed is True
    assert [action.step_id for action in m2_memo.retained_actions] == [
        "wf-001",
        "wf-003",
    ]
    assert [step.step_id for step in m2_memo.rejected_steps] == ["wf-004"]
    assert m2_memo.rejected_steps[0].original_action == (
        m2_inputs.workflow_plan.steps[3].action
    )
    assert m2_memo.rejected_steps[0].reviewer_note == (
        "Exclude project coordination until ownership is confirmed."
    )
    assert [action.step_id for action in m6_memo.retained_actions] == [
        "wf-001",
        "wf-004",
    ]
    assert [step.step_id for step in m6_memo.rejected_steps] == ["wf-003"]
    assert m6_memo.missing_information[0].step_id == "wf-003"
    assert m6_memo.missing_information[0].items == [
        "Validated customer-identifier coverage."
    ]

    changed_note = m2_memo.rejected_steps[0].model_copy(
        update={"reviewer_note": "Changed reviewer note."}
    )
    changed_evidence = m2_memo.rejected_steps[0].model_copy(
        update={
            "supporting_evidence_ids": [
                "ev-memo_eval-000000000003"
            ]
        }
    )
    lost_risk = m6_memo.rejected_steps[0].model_copy(
        update={"semantic_risk_codes": []}
    )
    wrong_section = m2_memo.model_copy(
        update={
            "retained_actions": [
                *m2_memo.retained_actions,
                m2_memo.rejected_steps[0],
            ],
            "rejected_steps": [],
        }
    )
    tampered_memos = (
        m2_memo.model_copy(update={"rejected_steps": [changed_note]}),
        m2_memo.model_copy(update={"rejected_steps": [changed_evidence]}),
        m6_memo.model_copy(update={"rejected_steps": [lost_risk]}),
        wrong_section,
    )
    tampered_scenarios = (m2, m2, m6, m2)
    for tampered_scenario, tampered_memo in zip(
        tampered_scenarios,
        tampered_memos,
        strict=True,
    ):
        tampered_result = _evaluate_tampered_memo(
            tampered_scenario,
            tampered_memo,
        )
        assert tampered_result.passed is False
        assert any(
            "rejected step audit snapshot mismatch" in reason
            or "primary record decision category mismatch" in reason
            or "invalid record type" in reason
            for reason in tampered_result.failure_reasons
        )


def test_m3_revision_requires_revalidation_and_m4_remains_blocked() -> None:
    """Human revisions retain original lineage and cannot clear blockers."""
    scenarios = load_memo_scenarios()
    m3 = _scenario(
        scenarios,
        "M3_human_revision_requires_revalidation",
    )
    m4 = _scenario(scenarios, "M4_blocker_persists_after_review")
    m3_inputs, _, m3_memo = _memo(m3)
    _, _, m4_memo = _memo(m4)
    revised = next(
        action
        for action in m3_memo.retained_actions
        if action.step_id == "wf-003"
    )

    assert evaluate_memo_scenario(m3).passed is True
    assert evaluate_memo_scenario(m4).passed is True
    assert m3_memo.memo_status is DecisionMemoStatus.requires_revalidation
    assert revised.original_action == m3_inputs.workflow_plan.steps[2].action
    assert revised.action == (
        "Draft a conditional retention priority for revalidation."
    )
    assert revised.revision_requires_revalidation is True
    assert revised.supporting_evidence_ids == [
        "ev-memo_eval-000000000003"
    ]
    assert m4_memo.memo_status is DecisionMemoStatus.blocked
    assert m4_memo.unresolved_blocking_step_ids == ["wf-001"]
    assert m4_memo.human_revision_step_ids == ["wf-001"]

    first_action = next(
        action
        for action in m3_memo.retained_actions
        if action.step_id == "wf-001"
    )
    revised_action = next(
        action
        for action in m3_memo.retained_actions
        if action.step_id == "wf-003"
    )
    altered_actions = (
        first_action.model_copy(
            update={"owner_role": RoleKey.project_manager}
        ),
        revised_action.model_copy(
            update={"original_status": WorkflowStepStatus.ready}
        ),
        first_action.model_copy(
            update={"deterministic_risk_codes": []}
        ),
    )
    for altered in altered_actions:
        tampered_actions = [
            altered if action.step_id == altered.step_id else action
            for action in m3_memo.retained_actions
        ]
        tampered_memo = m3_memo.model_copy(
            update={"retained_actions": tampered_actions}
        )
        tampered_result = _evaluate_tampered_memo(m3, tampered_memo)
        assert tampered_result.passed is False
        assert "retained action snapshot mismatch" in (
            tampered_result.failure_reasons
        )


def test_m5_semantic_gate_is_only_a_non_authoritative_review_record() -> None:
    """M5 preserves the rejected gate note and probabilistic lineage only."""
    scenario = _scenario(
        load_memo_scenarios(),
        "M5_semantic_gate_non_authoritative",
    )
    _, _, memo = _memo(scenario)
    result = evaluate_memo_scenario(scenario)
    gate = memo.review_gates[0]

    assert result.passed is True
    assert [item.step_id for item in memo.review_gates] == ["wf-002"]
    assert "wf-002" not in {
        action.step_id for action in memo.retained_actions
    }
    assert "wf-002" not in {
        rejected.step_id for rejected in memo.rejected_steps
    }
    assert gate.decision is HumanReviewDecision.reject
    assert gate.reviewer_note == (
        "Do not treat the probabilistic concern as factual verification."
    )
    assert gate.semantic_risk_codes == [
        SemanticRiskCode.citation_claim_mismatch
    ]
    assert gate.blocks_downstream is False
    assert (
        "Semantic review decisions remain probabilistic and "
        "non-authoritative."
        in memo.control_notices
    )

    tampered_gates = (
        gate.model_copy(update={"reviewer_note": "Changed gate note."}),
        gate.model_copy(
            update={
                "supporting_evidence_ids": [
                    "ev-memo_eval-000000000003"
                ]
            }
        ),
        gate.model_copy(
            update={"original_status": WorkflowStepStatus.ready}
        ),
    )
    for tampered_gate in tampered_gates:
        tampered_memo = memo.model_copy(
            update={"review_gates": [tampered_gate]}
        )
        tampered_result = _evaluate_tampered_memo(
            scenario,
            tampered_memo,
        )
        assert tampered_result.passed is False
        assert "review gate snapshot mismatch" in (
            tampered_result.failure_reasons
        )


def test_m7_pending_review_and_tampered_bindings_fail_closed() -> None:
    """Incomplete, stale-digest, and tampered-snapshot inputs produce no memo."""
    scenario = _scenario(
        load_memo_scenarios(),
        "M7_incomplete_review_fails_closed",
    )
    inputs = build_memo_scenario_inputs(scenario)
    pending = review_workflow_plan(
        inputs.workflow_plan,
        inputs.decisions,
    )
    result = evaluate_memo_scenario(scenario)

    assert pending.session_status is HumanReviewSessionStatus.pending
    assert pending.human_review_complete is False
    assert result.passed is True
    assert result.actual_outcome == "decision_memo_input_error"
    with pytest.raises(DecisionMemoInputError):
        compose_decision_memo(
            inputs.workflow_plan,
            pending,
            inputs.evidence_objects,
        )

    complete_decisions = {
        step.step_id: HumanReviewStepInput(
            decision=HumanReviewDecision.accept,
            reviewer_note=(
                "Probabilistic concern reviewed."
                if step.step_id == "wf-002"
                else None
            ),
        )
        for step in inputs.workflow_plan.steps
    }
    complete = review_workflow_plan(
        inputs.workflow_plan,
        complete_decisions,
    )
    stale_digest = complete.model_copy(
        update={"plan_digest": "f" * 64}
    )
    tampered_step = complete.reviewed_steps[0].model_copy(
        update={"original_action": "Tampered synthetic action."}
    )
    tampered_snapshot = complete.model_copy(
        update={
            "reviewed_steps": [
                tampered_step,
                *complete.reviewed_steps[1:],
            ]
        }
    )
    for session in (stale_digest, tampered_snapshot):
        with pytest.raises(DecisionMemoInputError):
            compose_decision_memo(
                inputs.workflow_plan,
                session,
                inputs.evidence_objects,
            )


def test_m8_acknowledgment_and_full_pack_are_exact_and_repeatable() -> None:
    """M8 is explicit and all eight production scenarios pass twice."""
    scenarios = load_memo_scenarios()
    m8 = _scenario(scenarios, "M8_empty_plan_acknowledged")
    inputs, session, memo = _memo(m8)
    first = run_memo_evaluation(scenarios)
    second = run_memo_evaluation(scenarios)

    assert inputs.workflow_plan.steps == []
    assert session.no_action_acknowledged is True
    assert memo.memo_status is DecisionMemoStatus.no_action_acknowledged
    assert memo.plan_step_ids == []
    assert memo.retained_actions == []
    assert memo.review_gates == []
    assert memo.rejected_steps == []
    assert memo.evidence_items == []
    assert memo.deterministic_risk_codes == []
    assert memo.semantic_risk_codes == []
    assert memo.overall_review_note == (
        "Reviewed and acknowledged that no workflow action was proposed."
    )
    assert first == second
    assert first.total_scenarios == 8
    assert first.passed_scenarios == 8
    assert first.failed_scenarios == 0
    assert first.pass_rate == 1.0


def test_polished_action_summary_baseline_passes_zero_without_external_behavior() -> None:
    """The final-action-only baseline cannot satisfy any audit expectation."""
    scenarios = load_memo_scenarios()
    original_import = builtins.__import__

    def guarded_import(
        name: str,
        globals: object = None,
        locals: object = None,
        fromlist: tuple[str, ...] = (),
        level: int = 0,
    ):
        if (
            name == "app.granite_semantic_risk_provider"
            or name == "ibm_watsonx_ai"
            or name.startswith("ibm_watsonx_ai.")
        ):
            raise AssertionError("baseline must not import a provider or SDK")
        return original_import(name, globals, locals, fromlist, level)

    with patch(
        "app.memo_evaluation.compose_decision_memo",
        side_effect=AssertionError("baseline must not compose a memo"),
    ), patch(
        "socket.create_connection",
        side_effect=AssertionError("baseline must not use the network"),
    ), patch(
        "os.getenv",
        side_effect=AssertionError("baseline must not read environment"),
    ), patch(
        "random.random",
        side_effect=AssertionError("baseline must not use randomness"),
    ), patch(
        "time.time",
        side_effect=AssertionError("baseline must not use timestamps"),
    ), patch(
        "builtins.__import__",
        side_effect=guarded_import,
    ):
        first = evaluate_polished_action_summary_baseline(scenarios)
        second = evaluate_polished_action_summary_baseline(scenarios)

    assert first == second
    assert first.total_scenarios == 8
    assert first.passed_scenarios == 0
    assert first.failed_scenarios == 8
    assert first.pass_rate == 0.0
    assert all(not result.passed for result in first.scenario_results)
    assert all(
        result.failure_reasons
        and result.passed is (not result.failure_reasons)
        for result in first.scenario_results
    )
    reasons_by_id = {
        result.scenario_id: " | ".join(result.failure_reasons).lower()
        for result in first.scenario_results
    }
    assert len(
        {
            result.failure_reasons
            for result in first.scenario_results
        }
    ) > 1
    assert (
        "rejected-step audit"
        in reasons_by_id["M2_rejected_action_auditable"]
        or "review-gate"
        in reasons_by_id["M2_rejected_action_auditable"]
    )
    assert "blocker" in reasons_by_id["M4_blocker_persists_after_review"]
    assert (
        "missing information"
        in reasons_by_id["M6_missing_information_survives_rejection"]
    )
    assert (
        "pending" in reasons_by_id["M7_incomplete_review_fails_closed"]
        or "incomplete" in reasons_by_id["M7_incomplete_review_fails_closed"]
    )
    assert (
        "no-action acknowledgment"
        in reasons_by_id["M8_empty_plan_acknowledged"]
    )
