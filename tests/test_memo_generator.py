"""Offline tests for deterministic post-review Decision Memo composition."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from app.human_review import review_workflow_plan
from app.memo_generator import DecisionMemoInputError, compose_decision_memo
from app.schemas import (
    DecisionMemo,
    DecisionMemoAction,
    DecisionMemoActionOrigin,
    DecisionMemoMissingInformation,
    DecisionMemoRejectedStep,
    DecisionMemoReviewGate,
    DecisionMemoStatus,
    EvidenceObject,
    EvidenceScope,
    EvidenceStatus,
    HumanReviewDecision,
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


_EVIDENCE_IDS = (
    "ev-memo-000000000001",
    "ev-memo-000000000002",
    "ev-memo-000000000003",
)


def _evidence(
    index: int,
    *,
    status: EvidenceStatus = EvidenceStatus.active,
) -> EvidenceObject:
    """Build one active synthetic EvidenceObject via validated mapping."""
    return EvidenceObject.model_validate(
        {
            "evidence_id": _EVIDENCE_IDS[index - 1],
            "identity_digest": f"{index:x}" * 64,
            "source_id": f"src-memo-{index:012x}",
            "source_format": SourceFormat.csv,
            "source_locator": TabularSourceLocator(
                columns=["synthetic_metric"],
                row_range=(index, index),
            ),
            "evidence_type": "memo_test_observation",
            "evidence_scope": EvidenceScope.internal_observation,
            "extraction_method": "deterministic",
            "finding": f"Synthetic memo finding {index}.",
            "supporting_evidence": f"Synthetic supporting value {index}.",
            "confidence": "high",
            "limitations": ["Synthetic test evidence."],
            "relevant_roles": ["executive", "data_analyst"],
            "decision_relevance": f"Supports memo test step {index}.",
            "created_by": "evidence_builder",
            "status": status,
            "invalidated_reason": (
                "Superseded test evidence."
                if status is EvidenceStatus.invalidated
                else None
            ),
        }
    )


def _evidence_registry() -> list[EvidenceObject]:
    """Return all EvidenceObjects referenced by the healthy plan."""
    return [_evidence(1), _evidence(2), _evidence(3)]


def _healthy_plan() -> WorkflowPlan:
    """Build a reviewed, nonblocking plan with all three primary step kinds."""
    steps = [
        WorkflowStep(
            step_id="wf-001",
            sequence=1,
            step_kind=WorkflowStepKind.deterministic_risk_resolution,
            owner_role=RoleKey.data_analyst,
            action="Confirm the analytical limitation.",
            supporting_evidence_ids=[_EVIDENCE_IDS[0]],
            dependency_step_ids=[],
            dependency_notes=["An assumption requires confirmation."],
            missing_information=[],
            deterministic_risk_codes=[RiskCode.assumption_not_declared],
            semantic_risk_codes=[],
            review_questions=[],
            status=WorkflowStepStatus.ready,
            blocks_downstream=False,
            human_review_required=False,
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
            supporting_evidence_ids=[_EVIDENCE_IDS[1]],
            dependency_step_ids=["wf-001"],
            dependency_notes=[],
            missing_information=[],
            deterministic_risk_codes=[],
            semantic_risk_codes=[
                SemanticRiskCode.citation_claim_mismatch
            ],
            review_questions=["Does the citation support the conclusion?"],
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
            supporting_evidence_ids=[_EVIDENCE_IDS[2]],
            dependency_step_ids=["wf-001", "wf-002"],
            dependency_notes=[],
            missing_information=[
                "Validated customer-identifier coverage."
            ],
            deterministic_risk_codes=[
                RiskCode.action_without_internal_evidence
            ],
            semantic_risk_codes=[
                SemanticRiskCode.unsupported_company_specific_claim
            ],
            review_questions=[],
            status=WorkflowStepStatus.pending_human_review,
            blocks_downstream=False,
            human_review_required=True,
        ),
    ]
    return WorkflowPlan(
        steps=steps,
        plan_status=WorkflowPlanStatus.ready_for_human_review,
        included_role_keys=[RoleKey.executive, RoleKey.data_analyst],
        blocking_step_ids=[],
        human_review_required=True,
        planning_method="deterministic_v1",
    )


def _blocking_plan() -> WorkflowPlan:
    """Derive a schema-valid plan whose first step remains a blocker."""
    plan = _healthy_plan()
    steps = list(plan.steps)
    first_payload = steps[0].model_dump()
    first_payload.update(
        {
            "status": WorkflowStepStatus.pending_human_review,
            "blocks_downstream": True,
            "human_review_required": True,
        }
    )
    steps[0] = WorkflowStep.model_validate(first_payload)
    third_payload = steps[2].model_dump()
    third_payload["status"] = WorkflowStepStatus.blocked
    steps[2] = WorkflowStep.model_validate(third_payload)
    return WorkflowPlan(
        steps=steps,
        plan_status=WorkflowPlanStatus.blocked,
        included_role_keys=list(plan.included_role_keys),
        blocking_step_ids=["wf-001"],
        human_review_required=True,
        planning_method="deterministic_v1",
    )


def _mutate_plan_step(
    plan: WorkflowPlan,
    sequence: int,
    **updates: Any,
) -> WorkflowPlan:
    """Rebuild a changed workflow step and plan through schema validation."""
    steps = list(plan.steps)
    step_payload = steps[sequence - 1].model_dump()
    step_payload.update(updates)
    steps[sequence - 1] = WorkflowStep.model_validate(step_payload)
    plan_payload = plan.model_dump(exclude={"steps"})
    plan_payload["steps"] = [step.model_dump() for step in steps]
    return WorkflowPlan.model_validate(plan_payload)


def _complete_session(
    plan: WorkflowPlan,
    overrides: dict[str, HumanReviewStepInput] | None = None,
):
    """Return a complete session, accepting every step by default."""
    decisions = {
        step.step_id: HumanReviewStepInput(
            decision=HumanReviewDecision.accept,
            reviewer_note=(
                "Probabilistic concern reviewed."
                if step.step_kind is WorkflowStepKind.semantic_review_gate
                else None
            ),
        )
        for step in plan.steps
    }
    decisions.update(overrides or {})
    return review_workflow_plan(plan, decisions)


def _empty_plan() -> WorkflowPlan:
    """Build an explicit no-action plan."""
    return WorkflowPlan(
        steps=[],
        plan_status=WorkflowPlanStatus.no_actionable_steps,
        included_role_keys=[RoleKey.executive],
        blocking_step_ids=[],
        human_review_required=True,
        planning_method="deterministic_v1",
    )


def test_decision_memo_schemas_reject_malformed_and_inconsistent_records() -> None:
    """Subcontracts and aggregate memo validation fail closed."""
    plan = _healthy_plan()
    session = _complete_session(plan)
    memo = compose_decision_memo(plan, session, _evidence_registry())
    action_payload = memo.retained_actions[-1].model_dump()
    invalid_actions = [
        {**action_payload, "step_id": "step-003"},
        {**action_payload, "action": " "},
        {
            **action_payload,
            "supporting_evidence_ids": [
                _EVIDENCE_IDS[2],
                _EVIDENCE_IDS[2],
            ],
        },
        {
            **action_payload,
            "action_origin": DecisionMemoActionOrigin.human_revision,
            "revision_requires_revalidation": False,
        },
        {
            **action_payload,
            "step_kind": WorkflowStepKind.semantic_review_gate,
        },
        {**action_payload, "unexpected": True},
    ]
    for payload in invalid_actions:
        with pytest.raises(ValidationError):
            DecisionMemoAction.model_validate(payload)

    gate_payload = memo.review_gates[0].model_dump()
    for payload in (
        {**gate_payload, "reviewer_note": " "},
        {**gate_payload, "decision": HumanReviewDecision.revise},
        {**gate_payload, "supporting_evidence_ids": []},
        {**gate_payload, "semantic_risk_codes": []},
        {**gate_payload, "blocks_downstream": True},
    ):
        with pytest.raises(ValidationError):
            DecisionMemoReviewGate.model_validate(payload)

    rejected_payload = {
        **action_payload,
        "reviewer_note": "Reject it.",
    }
    rejected_payload.pop("action")
    rejected_payload.pop("action_origin")
    rejected_payload.pop("revision_requires_revalidation")
    with pytest.raises(ValidationError):
        DecisionMemoRejectedStep.model_validate(
            {
                **rejected_payload,
                "step_kind": WorkflowStepKind.semantic_review_gate,
            }
        )
    with pytest.raises(ValidationError):
        DecisionMemoMissingInformation(
            step_id="wf-003",
            owner_role=RoleKey.executive,
            items=[],
        )

    memo_payload = memo.model_dump()
    invalid_memos = [
        {**memo_payload, "plan_step_ids": memo.plan_step_ids[:-1]},
        {**memo_payload, "deterministic_risk_codes": []},
        {**memo_payload, "evidence_items": memo.evidence_items[:-1]},
        {**memo_payload, "memo_status": DecisionMemoStatus.blocked},
        {**memo_payload, "human_review_complete": False},
        {
            **memo_payload,
            "control_notices": [
                memo.control_notices[0],
                memo.control_notices[0],
            ],
        },
        {**memo_payload, "unexpected": True},
    ]
    for payload in invalid_memos:
        with pytest.raises(ValidationError):
            DecisionMemo.model_validate(payload)


def test_incomplete_stale_and_tampered_review_sessions_fail_closed() -> None:
    """Completion, digest, step coverage, and exact snapshots are mandatory."""
    plan = _healthy_plan()
    complete = _complete_session(plan)
    pending = review_workflow_plan(
        plan,
        {"wf-001": HumanReviewStepInput(decision="accept")},
    )
    digest_mismatch = complete.model_copy(
        update={"plan_digest": "f" * 64}
    )
    step_mismatch = complete.model_copy(
        update={"plan_step_ids": ["wf-001", "wf-002", "wf-999"]}
    )
    missing_review = complete.model_copy(
        update={"reviewed_steps": complete.reviewed_steps[:-1]}
    )
    tampered_step = complete.reviewed_steps[0].model_copy(
        update={"original_action": "Tampered action."}
    )
    tampered_session = complete.model_copy(
        update={
            "reviewed_steps": [
                tampered_step,
                *complete.reviewed_steps[1:],
            ]
        }
    )

    for session in (
        pending,
        digest_mismatch,
        step_mismatch,
        missing_review,
        tampered_session,
    ):
        with pytest.raises(DecisionMemoInputError):
            compose_decision_memo(plan, session, _evidence_registry())

    role_action_without_evidence = _mutate_plan_step(
        plan,
        3,
        supporting_evidence_ids=[],
    )
    role_action_session = _complete_session(
        role_action_without_evidence
    )
    with pytest.raises(DecisionMemoInputError) as role_action_error:
        compose_decision_memo(
            role_action_without_evidence,
            role_action_session,
            _evidence_registry(),
        )
    assert "errors.pydantic.dev" not in str(role_action_error.value)
    assert plan.steps[2].action not in str(role_action_error.value)

    gate_without_evidence = _mutate_plan_step(
        plan,
        2,
        supporting_evidence_ids=[],
    )
    gate_session = _complete_session(gate_without_evidence)
    with pytest.raises(DecisionMemoInputError) as gate_error:
        compose_decision_memo(
            gate_without_evidence,
            gate_session,
            _evidence_registry(),
        )
    assert "errors.pydantic.dev" not in str(gate_error.value)
    assert plan.steps[1].action not in str(gate_error.value)


def test_evidence_registry_fails_closed_and_tolerates_exact_duplicates() -> None:
    """Referenced Evidence must exist, remain active, and have no conflict."""
    plan = _healthy_plan()
    session = _complete_session(plan)
    evidence = _evidence_registry()

    with pytest.raises(DecisionMemoInputError):
        compose_decision_memo(plan, session, evidence[:-1])

    inactive = [evidence[0], evidence[1], _evidence(3, status=EvidenceStatus.invalidated)]
    with pytest.raises(DecisionMemoInputError):
        compose_decision_memo(plan, session, inactive)

    conflicting = evidence[0].model_copy(
        update={"identity_digest": "f" * 64}
    )
    with pytest.raises(DecisionMemoInputError):
        compose_decision_memo(
            plan,
            session,
            [*evidence, conflicting],
        )

    internally_invalid = evidence[0].model_copy(
        update={"finding": " "}
    )
    with pytest.raises(DecisionMemoInputError) as invalid_error:
        compose_decision_memo(
            plan,
            session,
            [internally_invalid, *evidence[1:]],
        )
    error_text = str(invalid_error.value)
    assert error_text == (
        "evidence_objects contains an internally invalid EvidenceObject"
    )
    assert "errors.pydantic.dev" not in error_text
    assert evidence[0].finding not in error_text
    assert repr(internally_invalid) not in error_text
    assert plan.steps[0].action not in error_text

    duplicate_memo = compose_decision_memo(
        plan,
        session,
        [*evidence, evidence[0]],
    )
    assert duplicate_memo.evidence_items == compose_decision_memo(
        plan,
        session,
        evidence,
    ).evidence_items


def test_all_accept_healthy_plan_composes_exact_reviewed_memo() -> None:
    """Accepted actions, gate, Evidence, and risk aggregates preserve plan order."""
    plan = _healthy_plan()
    session = _complete_session(plan)

    memo = compose_decision_memo(plan, session, _evidence_registry())

    assert memo.memo_status is DecisionMemoStatus.reviewed
    assert [action.step_id for action in memo.retained_actions] == [
        "wf-001",
        "wf-003",
    ]
    assert [gate.step_id for gate in memo.review_gates] == ["wf-002"]
    assert memo.rejected_steps == []
    assert [item.evidence_id for item in memo.evidence_items] == list(
        _EVIDENCE_IDS
    )
    assert [item.finding for item in memo.evidence_items] == [
        "Synthetic memo finding 1.",
        "Synthetic memo finding 2.",
        "Synthetic memo finding 3.",
    ]
    assert memo.deterministic_risk_codes == [
        RiskCode.assumption_not_declared,
        RiskCode.action_without_internal_evidence,
    ]
    assert memo.semantic_risk_codes == [
        SemanticRiskCode.citation_claim_mismatch,
        SemanticRiskCode.unsupported_company_specific_claim,
    ]
    assert memo.unresolved_blocking_step_ids == []
    assert memo.human_revision_step_ids == []


def test_rejected_role_action_is_auditable_and_not_retained() -> None:
    """Rejected role actions preserve lineage while leaving retained actions."""
    plan = _healthy_plan()
    session = _complete_session(
        plan,
        {
            "wf-003": HumanReviewStepInput(
                decision="reject",
                reviewer_note="Exclude the role action from the memo.",
            )
        },
    )

    memo = compose_decision_memo(plan, session, _evidence_registry())
    rejected = memo.rejected_steps[0]

    assert [action.step_id for action in memo.retained_actions] == ["wf-001"]
    assert rejected.step_id == "wf-003"
    assert rejected.reviewer_note == (
        "Exclude the role action from the memo."
    )
    assert rejected.supporting_evidence_ids == [_EVIDENCE_IDS[2]]
    assert rejected.deterministic_risk_codes == [
        RiskCode.action_without_internal_evidence
    ]
    assert rejected.semantic_risk_codes == [
        SemanticRiskCode.unsupported_company_specific_claim
    ]
    assert rejected.original_status is WorkflowStepStatus.pending_human_review


def test_human_revision_is_visible_and_requires_revalidation() -> None:
    """A retained human revision preserves original text and warning lineage."""
    plan = _healthy_plan()
    session = _complete_session(
        plan,
        {
            "wf-003": HumanReviewStepInput(
                decision="revise",
                reviewer_note="Keep this action explicitly conditional.",
                revised_action="Draft a conditional retention priority.",
            )
        },
    )

    memo = compose_decision_memo(plan, session, _evidence_registry())
    revised = next(
        action
        for action in memo.retained_actions
        if action.step_id == "wf-003"
    )

    assert memo.memo_status is DecisionMemoStatus.requires_revalidation
    assert revised.original_action == plan.steps[2].action
    assert revised.action == "Draft a conditional retention priority."
    assert revised.action_origin is DecisionMemoActionOrigin.human_revision
    assert revised.revision_requires_revalidation is True
    assert revised.supporting_evidence_ids == [_EVIDENCE_IDS[2]]
    assert memo.human_revision_step_ids == ["wf-003"]
    assert (
        "Human-authored revisions require evidence and semantic revalidation."
        in memo.control_notices
    )


@pytest.mark.parametrize(
    ("decision", "note", "revision"),
    [
        (HumanReviewDecision.accept, None, None),
        (
            HumanReviewDecision.reject,
            "Reject the proposed remediation.",
            None,
        ),
        (
            HumanReviewDecision.revise,
            "Narrow the proposed remediation.",
            "Validate only the bounded identifier subset.",
        ),
    ],
)
def test_blocking_plan_remains_blocked_for_every_review_decision(
    decision: HumanReviewDecision,
    note: str | None,
    revision: str | None,
) -> None:
    """Accept, reject, or revise never clears an original blocker."""
    plan = _blocking_plan()
    session = _complete_session(
        plan,
        {
            "wf-001": HumanReviewStepInput(
                decision=decision,
                reviewer_note=note,
                revised_action=revision,
            )
        },
    )

    memo = compose_decision_memo(plan, session, _evidence_registry())

    assert memo.memo_status is DecisionMemoStatus.blocked
    assert memo.unresolved_blocking_step_ids == ["wf-001"]
    assert (
        "Blocking prerequisites remain unresolved; accepting remediation "
        "does not mark them complete."
        in memo.control_notices
    )


def test_semantic_gates_are_non_authoritative_review_records_only() -> None:
    """Accepted and rejected gates remain documented non-action records."""
    plan = _healthy_plan()
    for decision in (
        HumanReviewDecision.accept,
        HumanReviewDecision.reject,
    ):
        session = _complete_session(
            plan,
            {
                "wf-002": HumanReviewStepInput(
                    decision=decision,
                    reviewer_note="Documented probabilistic gate handling.",
                )
            },
        )
        memo = compose_decision_memo(
            plan,
            session,
            _evidence_registry(),
        )

        assert len(memo.review_gates) == 1
        assert memo.review_gates[0].decision is decision
        assert memo.review_gates[0].reviewer_note == (
            "Documented probabilistic gate handling."
        )
        assert memo.review_gates[0].semantic_risk_codes == [
            SemanticRiskCode.citation_claim_mismatch
        ]
        assert "wf-002" not in {
            action.step_id for action in memo.retained_actions
        }
        assert "wf-002" not in {
            step.step_id for step in memo.rejected_steps
        }
        assert (
            "Semantic review decisions remain probabilistic and "
            "non-authoritative."
            in memo.control_notices
        )


def test_missing_information_and_empty_acknowledged_memo_are_preserved() -> None:
    """Information gaps survive rejection and empty acknowledged plans stay explicit."""
    plan = _healthy_plan()
    accepted = compose_decision_memo(
        plan,
        _complete_session(plan),
        _evidence_registry(),
    )
    rejected = compose_decision_memo(
        plan,
        _complete_session(
            plan,
            {
                "wf-003": HumanReviewStepInput(
                    decision="reject",
                    reviewer_note="Reject while retaining the information gap.",
                )
            },
        ),
        _evidence_registry(),
    )
    expected_items = ["Validated customer-identifier coverage."]

    assert accepted.missing_information[0].items == expected_items
    assert rejected.missing_information[0].items == expected_items
    assert accepted.missing_information[0].step_id == "wf-003"
    assert rejected.missing_information[0].step_id == "wf-003"

    empty_plan = _empty_plan()
    empty_session = review_workflow_plan(
        empty_plan,
        {},
        no_action_acknowledged=True,
        overall_note="Reviewed and acknowledged the empty workflow.",
    )
    empty_memo = compose_decision_memo(empty_plan, empty_session, [])

    assert empty_memo.memo_status is DecisionMemoStatus.no_action_acknowledged
    assert empty_memo.plan_step_ids == []
    assert empty_memo.retained_actions == []
    assert empty_memo.review_gates == []
    assert empty_memo.rejected_steps == []
    assert empty_memo.evidence_items == []
    assert empty_memo.overall_review_note == (
        "Reviewed and acknowledged the empty workflow."
    )
    assert "No actionable workflow step was proposed." in (
        empty_memo.control_notices
    )


def test_composition_is_deterministic_immutable_and_entirely_offline() -> None:
    """Equal inputs yield equal memos without mutation or external behavior."""
    plan = _healthy_plan()
    session = _complete_session(plan)
    evidence = _evidence_registry()
    plan_before = plan.model_dump()
    session_before = session.model_dump()

    with patch(
        "socket.create_connection",
        side_effect=AssertionError("memo composition must not use network"),
    ), patch(
        "os.getenv",
        side_effect=AssertionError("memo composition must not read environment"),
    ):
        first = compose_decision_memo(plan, session, evidence)
        second = compose_decision_memo(
            WorkflowPlan.model_validate(plan.model_dump()),
            session,
            list(evidence),
        )

    assert first == second
    assert plan.model_dump() == plan_before
    assert session.model_dump() == session_before
    assert first.memo_method == "deterministic_post_review_v1"
