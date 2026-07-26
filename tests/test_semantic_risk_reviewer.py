"""Offline tests for the Task 7B-1 semantic risk review contract."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest

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
    RiskFinding,
    RiskReviewResult,
    RoleKey,
    RoleView,
    SemanticReviewDisposition,
    SemanticRiskCandidate,
    SemanticRiskCode,
    SourceFormat,
    TabularSourceLocator,
    _ROLE_EXECUTION_ORDER,
)
from app.semantic_risk_reviewer import (
    SemanticRiskInputError,
    SemanticRiskProviderError,
    SemanticRiskRequest,
    SemanticRiskResponseError,
    review_semantic_risks,
)

_EV_EXEC = "ev-sem_exec_00-000000000001"
_EV_ANALYST = "ev-sem_da_0000-000000000002"
_EV_UNRELATED = "ev-sem_other_0-000000000003"
_EV_INACTIVE = "ev-sem_dead_00-000000000004"
_EV_UNKNOWN = "ev-sem_ghost_0-0000000000ff"
_SOURCE_ID = "src-csv-000000000001"


class _FakeProvider:
    """Offline semantic provider with exact request capture."""

    def __init__(self, response: Mapping[str, Any] | Exception) -> None:
        self.response = response
        self.calls: list[SemanticRiskRequest] = []

    def review_semantic_risks(
        self,
        request: SemanticRiskRequest,
    ) -> Mapping[str, Any]:
        self.calls.append(request)
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def _evidence(
    evidence_id: str,
    *,
    status: EvidenceStatus = EvidenceStatus.active,
) -> EvidenceObject:
    return EvidenceObject(
        evidence_id=evidence_id,
        identity_digest="a" * 64,
        source_id=_SOURCE_ID,
        source_format=SourceFormat.csv,
        source_locator=TabularSourceLocator(columns=["revenue"]),
        evidence_type="missing_value_rate",
        evidence_scope=EvidenceScope.internal_observation,
        extraction_method="deterministic",
        finding=f"Bounded finding for {evidence_id}.",
        supporting_evidence="Exact supporting evidence.",
        confidence="high",
        limitations=[],
        relevant_roles=["executive", "data_analyst"],
        decision_relevance="Relevant to review.",
        created_by="evidence_builder",
        status=status,
        invalidated_reason=(
            "Superseded." if status == EvidenceStatus.invalidated else None
        ),
    )


def _view(
    role_key: RoleKey,
    claim_evidence_ids: list[list[str]],
) -> RoleView:
    findings = [
        GroundedFinding(
            claim=f"Claim {index} for {role_key.value}.",
            evidence_references=[
                EvidenceReference(evidence_id=evidence_id)
                for evidence_id in evidence_ids
            ],
            confidence="medium",
        )
        for index, evidence_ids in enumerate(claim_evidence_ids)
    ]
    return RoleView(
        role_key=role_key,
        role_concern=f"Concern for {role_key.value}.",
        key_findings=findings,
        risks_or_assumptions=[],
        missing_information=[],
        next_action=None,
        dependency=None,
        human_review_required=True,
    )


def _outcomes(*views: RoleView) -> dict[RoleKey, RoleOutcome]:
    by_role = {view.role_key: view for view in views}
    return {
        role_key: by_role.get(
            role_key,
            InsufficientEvidence(
                role_key=role_key,
                reason="No successful RoleView.",
            ),
        )
        for role_key in _ROLE_EXECUTION_ORDER
    }


def _deterministic_result() -> RiskReviewResult:
    return RiskReviewResult(
        findings=[],
        reviewed_role_keys=list(_ROLE_EXECUTION_ORDER),
        has_blocking_risks=False,
        human_review_required=False,
    )


def _candidate_payload(
    *,
    role_key: RoleKey = RoleKey.executive,
    claim_index: int = 0,
    evidence_ids: list[str] | None = None,
    disposition: SemanticReviewDisposition = (
        SemanticReviewDisposition.needs_human_review
    ),
) -> dict[str, Any]:
    return {
        "risk_code": SemanticRiskCode.citation_claim_mismatch.value,
        "role_key": role_key.value,
        "claim_index": claim_index,
        "evidence_ids": [_EV_EXEC] if evidence_ids is None else evidence_ids,
        "explanation": "The claim may exceed the cited evidence.",
        "review_question": "Does the cited evidence directly support this claim?",
        "confidence": "medium",
        "disposition": disposition.value,
    }


def _result_payload(
    reviewed_role_keys: list[RoleKey],
    *,
    candidates: list[dict[str, Any]] | None = None,
    human_review_required: bool | None = None,
) -> dict[str, Any]:
    candidate_values = candidates or []
    if human_review_required is None:
        human_review_required = any(
            candidate["disposition"]
            != SemanticReviewDisposition.likely_supported.value
            for candidate in candidate_values
        )
    return {
        "candidates": candidate_values,
        "reviewed_role_keys": [key.value for key in reviewed_role_keys],
        "reviewer_model": "offline-semantic-reviewer",
        "human_review_required": human_review_required,
    }


def test_no_successful_role_views_returns_empty_without_provider_call():
    provider = _FakeProvider(RuntimeError("must not be called"))

    result = review_semantic_risks(
        provider=provider,
        role_outcomes=_outcomes(),
        evidence_objects=[],
        deterministic_risk_result=_deterministic_result(),
    )

    assert result.candidates == []
    assert result.reviewed_role_keys == []
    assert result.reviewer_model is None
    assert result.human_review_required is False
    assert provider.calls == []

    valid_outcomes = _outcomes()
    invalid_cases: list[tuple[dict[Any, Any], str, str | None]] = []

    missing_key = dict(valid_outcomes)
    missing_key.pop(RoleKey.project_manager)
    invalid_cases.append((missing_key, "exactly the five", None))

    non_role_key: dict[Any, Any] = dict(valid_outcomes)
    executive_outcome = non_role_key.pop(RoleKey.executive)
    non_role_key["executive"] = executive_outcome
    invalid_cases.append((non_role_key, "non-RoleKey", "InsufficientEvidence"))

    unsupported_value: dict[Any, Any] = dict(valid_outcomes)
    unsupported_value[RoleKey.executive] = object()
    invalid_cases.append((unsupported_value, "unsupported", "object"))

    mismatched_view: dict[Any, Any] = dict(valid_outcomes)
    mismatched_view[RoleKey.executive] = _view(
        RoleKey.sales_marketing,
        [[_EV_EXEC]],
    )
    invalid_cases.append(
        (mismatched_view, "sales_marketing", "RoleView")
    )

    mismatched_insufficient: dict[Any, Any] = dict(valid_outcomes)
    mismatched_insufficient[RoleKey.executive] = InsufficientEvidence(
        role_key=RoleKey.data_engineer,
        reason="Mismatched role.",
    )
    invalid_cases.append(
        (mismatched_insufficient, "data_engineer", "InsufficientEvidence")
    )

    mismatched_failure: dict[Any, Any] = dict(valid_outcomes)
    mismatched_failure[RoleKey.executive] = RoleGenerationFailure(
        role_key=RoleKey.project_manager,
        failure_code="provider_error",
        reason="Mismatched role.",
    )
    invalid_cases.append(
        (mismatched_failure, "project_manager", "RoleGenerationFailure")
    )

    invalid_provider = _FakeProvider(RuntimeError("must not be called"))
    for invalid_outcomes, expected_text, expected_type in invalid_cases:
        with pytest.raises(SemanticRiskInputError) as exc_info:
            review_semantic_risks(
                provider=invalid_provider,
                role_outcomes=invalid_outcomes,  # type: ignore[arg-type]
                evidence_objects=[],
                deterministic_risk_result=_deterministic_result(),
            )
        error_text = str(exc_info.value)
        assert expected_text in error_text
        if expected_type is not None:
            assert expected_type in error_text
    assert invalid_provider.calls == []


def test_request_contains_successful_role_views_in_fixed_order():
    executive = _view(RoleKey.executive, [[_EV_EXEC]])
    analyst = _view(RoleKey.data_analyst, [[_EV_ANALYST]])
    provider = _FakeProvider(
        _result_payload([RoleKey.executive, RoleKey.data_analyst])
    )

    review_semantic_risks(
        provider=provider,
        role_outcomes=_outcomes(analyst, executive),
        evidence_objects=[
            _evidence(_EV_EXEC),
            _evidence(_EV_ANALYST),
        ],
        deterministic_risk_result=_deterministic_result(),
    )

    request = provider.calls[0]
    assert [view.role_key for view in request.role_views] == [
        RoleKey.executive,
        RoleKey.data_analyst,
    ]
    assert request.deterministic_risk_result == _deterministic_result()


def test_request_contains_only_cited_evidence_and_registry_fails_closed():
    executive = _view(RoleKey.executive, [[_EV_EXEC]])
    analyst = _view(RoleKey.data_analyst, [[_EV_ANALYST, _EV_EXEC]])
    cited_exec = _evidence(_EV_EXEC)
    cited_analyst = _evidence(_EV_ANALYST)
    unrelated = _evidence(_EV_UNRELATED)
    provider = _FakeProvider(
        _result_payload([RoleKey.executive, RoleKey.data_analyst])
    )

    review_semantic_risks(
        provider=provider,
        role_outcomes=_outcomes(executive, analyst),
        evidence_objects=[
            cited_exec,
            unrelated,
            cited_exec.model_copy(deep=True),
            cited_analyst,
        ],
        deterministic_risk_result=_deterministic_result(),
    )

    request = provider.calls[0]
    assert [item.evidence_id for item in request.evidence_objects] == [
        _EV_EXEC,
        _EV_ANALYST,
    ]
    assert request.allowed_evidence_ids == frozenset(
        {_EV_EXEC, _EV_ANALYST}
    )
    assert _EV_UNRELATED not in request.allowed_evidence_ids

    conflict = cited_exec.model_copy(
        update={"finding": "Conflicting record for the same evidence ID."}
    )
    conflict_provider = _FakeProvider(
        _result_payload([RoleKey.executive])
    )
    with pytest.raises(SemanticRiskInputError, match="Conflicting"):
        review_semantic_risks(
            provider=conflict_provider,
            role_outcomes=_outcomes(executive),
            evidence_objects=[cited_exec, conflict],
            deterministic_risk_result=_deterministic_result(),
        )
    assert conflict_provider.calls == []


def test_valid_semantic_risk_candidate_is_accepted():
    executive = _view(RoleKey.executive, [[_EV_EXEC]])
    provider = _FakeProvider(
        _result_payload(
            [RoleKey.executive],
            candidates=[_candidate_payload()],
        )
    )

    result = review_semantic_risks(
        provider=provider,
        role_outcomes=_outcomes(executive),
        evidence_objects=[_evidence(_EV_EXEC)],
        deterministic_risk_result=_deterministic_result(),
    )

    assert len(result.candidates) == 1
    candidate = result.candidates[0]
    assert isinstance(candidate, SemanticRiskCandidate)
    assert not isinstance(candidate, RiskFinding)
    assert candidate.risk_code == SemanticRiskCode.citation_claim_mismatch
    assert candidate.disposition == SemanticReviewDisposition.needs_human_review
    assert result.human_review_required is True


def test_candidate_role_not_in_successful_views_fails_closed():
    executive = _view(RoleKey.executive, [[_EV_EXEC]])
    provider = _FakeProvider(
        _result_payload(
            [RoleKey.executive],
            candidates=[
                _candidate_payload(role_key=RoleKey.data_analyst)
            ],
        )
    )

    with pytest.raises(SemanticRiskResponseError):
        review_semantic_risks(
            provider=provider,
            role_outcomes=_outcomes(executive),
            evidence_objects=[_evidence(_EV_EXEC)],
            deterministic_risk_result=_deterministic_result(),
        )


def test_out_of_range_claim_index_fails_closed():
    executive = _view(RoleKey.executive, [[_EV_EXEC]])
    provider = _FakeProvider(
        _result_payload(
            [RoleKey.executive],
            candidates=[_candidate_payload(claim_index=1)],
        )
    )

    with pytest.raises(SemanticRiskResponseError, match="out of range"):
        review_semantic_risks(
            provider=provider,
            role_outcomes=_outcomes(executive),
            evidence_objects=[_evidence(_EV_EXEC)],
            deterministic_risk_result=_deterministic_result(),
        )


def test_unknown_inactive_and_uncited_candidate_evidence_fail_closed():
    executive = _view(RoleKey.executive, [[_EV_EXEC]])
    active = _evidence(_EV_EXEC)
    inactive = _evidence(_EV_INACTIVE, status=EvidenceStatus.invalidated)
    uncited = _evidence(_EV_UNRELATED)

    cases = (
        (_EV_UNKNOWN, [active], "unknown"),
        (_EV_INACTIVE, [active, inactive], "inactive"),
        (_EV_UNRELATED, [active, uncited], "not cited"),
    )
    for evidence_id, evidence_objects, expected_message in cases:
        provider = _FakeProvider(
            _result_payload(
                [RoleKey.executive],
                candidates=[
                    _candidate_payload(evidence_ids=[evidence_id])
                ],
            )
        )
        with pytest.raises(
            SemanticRiskResponseError,
            match=expected_message,
        ):
            review_semantic_risks(
                provider=provider,
                role_outcomes=_outcomes(executive),
                evidence_objects=evidence_objects,
                deterministic_risk_result=_deterministic_result(),
            )


@pytest.mark.parametrize(
    "malformed_output",
    [
        {},
        {
            **_result_payload([RoleKey.executive]),
            "provider_metadata": {"latency": 1},
        },
        _result_payload(
            [RoleKey.executive],
            candidates=[
                {
                    **_candidate_payload(),
                    "chain_of_thought": "private reasoning",
                }
            ],
        ),
        _result_payload(
            [RoleKey.executive],
            candidates=[
                _candidate_payload(
                    evidence_ids=[_EV_EXEC, _EV_EXEC]
                )
            ],
        ),
        _result_payload(
            [RoleKey.executive],
            candidates=[_candidate_payload(evidence_ids=[])],
        ),
        _result_payload(
            [RoleKey.executive],
            candidates=[_candidate_payload(claim_index=-1)],
        ),
        _result_payload(
            [RoleKey.executive],
            candidates=[
                {
                    **_candidate_payload(),
                    "explanation": " ",
                }
            ],
        ),
        _result_payload(
            [RoleKey.executive],
            candidates=[
                {
                    **_candidate_payload(),
                    "automatic_blocking": True,
                }
            ],
        ),
    ],
)
def test_malformed_or_extra_provider_output_fails_schema_validation(
    malformed_output,
):
    executive = _view(RoleKey.executive, [[_EV_EXEC]])
    provider = _FakeProvider(malformed_output)

    with pytest.raises(SemanticRiskResponseError):
        review_semantic_risks(
            provider=provider,
            role_outcomes=_outcomes(executive),
            evidence_objects=[_evidence(_EV_EXEC)],
            deterministic_risk_result=_deterministic_result(),
        )


def test_provider_exception_becomes_sanitized_provider_error():
    executive = _view(RoleKey.executive, [[_EV_EXEC]])
    provider = _FakeProvider(RuntimeError("secret-token-from-provider"))

    with pytest.raises(SemanticRiskProviderError) as exc_info:
        review_semantic_risks(
            provider=provider,
            role_outcomes=_outcomes(executive),
            evidence_objects=[_evidence(_EV_EXEC)],
            deterministic_risk_result=_deterministic_result(),
        )

    assert "secret-token-from-provider" not in str(exc_info.value)
    assert len(provider.calls) == 1


def test_reviewed_roles_and_human_review_flag_are_deterministic():
    executive = _view(RoleKey.executive, [[_EV_EXEC]])
    analyst = _view(RoleKey.data_analyst, [[_EV_ANALYST]])
    evidence = [_evidence(_EV_EXEC), _evidence(_EV_ANALYST)]
    outcomes = _outcomes(analyst, executive)

    supported_provider = _FakeProvider(
        _result_payload(
            [RoleKey.executive, RoleKey.data_analyst],
            candidates=[
                _candidate_payload(
                    disposition=SemanticReviewDisposition.likely_supported
                )
            ],
            human_review_required=False,
        )
    )
    supported = review_semantic_risks(
        provider=supported_provider,
        role_outcomes=outcomes,
        evidence_objects=evidence,
        deterministic_risk_result=_deterministic_result(),
    )
    assert supported.reviewed_role_keys == [
        RoleKey.executive,
        RoleKey.data_analyst,
    ]
    assert supported.human_review_required is False

    uncertain_provider = _FakeProvider(
        _result_payload(
            [RoleKey.executive, RoleKey.data_analyst],
            candidates=[
                _candidate_payload(
                    disposition=SemanticReviewDisposition.reviewer_uncertain
                )
            ],
            human_review_required=True,
        )
    )
    uncertain = review_semantic_risks(
        provider=uncertain_provider,
        role_outcomes=outcomes,
        evidence_objects=evidence,
        deterministic_risk_result=_deterministic_result(),
    )
    assert uncertain.human_review_required is True

    invalid_outputs = (
        _result_payload(
            [RoleKey.executive],
        ),
        _result_payload(
            [RoleKey.data_analyst, RoleKey.executive],
        ),
        _result_payload(
            [RoleKey.executive, RoleKey.data_analyst],
            candidates=[
                _candidate_payload(
                    disposition=SemanticReviewDisposition.likely_supported
                )
            ],
            human_review_required=True,
        ),
        {
            **_result_payload(
                [RoleKey.executive, RoleKey.data_analyst],
            ),
            "reviewed_role_keys": ["executive", "executive"],
        },
    )
    for invalid_output in invalid_outputs:
        with pytest.raises(SemanticRiskResponseError):
            review_semantic_risks(
                provider=_FakeProvider(invalid_output),
                role_outcomes=outcomes,
                evidence_objects=evidence,
                deterministic_risk_result=_deterministic_result(),
            )
