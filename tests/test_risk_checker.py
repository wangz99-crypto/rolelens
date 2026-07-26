"""
tests/test_risk_checker.py — Task 7A: deterministic epistemic and workflow risk checker.

Exactly 10 top-level test functions.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest

from app.risk_checker import RiskInputError, check_role_risks
from app.role_engine import InsufficientEvidence, RoleGenerationFailure, RoleOutcome
from app.schemas import (
    EvidenceObject,
    EvidenceReference,
    EvidenceScope,
    EvidenceStatus,
    GroundedFinding,
    RiskCode,
    RiskSeverity,
    RoleKey,
    RoleView,
    SourceFormat,
    TabularSourceLocator,
    _ROLE_EXECUTION_ORDER,
)

# ---------------------------------------------------------------------------
# Shared constants and helpers
# ---------------------------------------------------------------------------

_DT = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
_DIGEST = "a" * 64
_SRC_ID = "src-csv-000000000001"

# One stable evidence ID per role
_EV = {
    RoleKey.executive:       "ev-exec_ev_00-000000000001",
    RoleKey.data_analyst:    "ev-da_ev_0000-000000000002",
    RoleKey.data_engineer:   "ev-de_ev_0000-000000000003",
    RoleKey.sales_marketing: "ev-sm_ev_0000-000000000004",
    RoleKey.project_manager: "ev-pm_ev_0000-000000000005",
}

# Extra IDs for mixed-scope tests
_EV_EXT  = "ev-ext_ev_000-000000000006"
_EV_ASS  = "ev-ass_ev_000-000000000007"
_EV_PRI  = "ev-pri_ev_000-000000000008"


def _make_ev(
    evidence_id: str,
    relevant_roles: list[str],
    scope: EvidenceScope = EvidenceScope.internal_observation,
    status: EvidenceStatus = EvidenceStatus.active,
) -> EvidenceObject:
    return EvidenceObject(
        evidence_id=evidence_id,
        identity_digest=_DIGEST,
        source_id=_SRC_ID,
        source_format=SourceFormat.csv,
        source_locator=TabularSourceLocator(columns=["revenue"]),
        evidence_type="missing_value_rate",
        evidence_scope=scope,
        extraction_method="deterministic",
        finding="Finding text.",
        supporting_evidence="Supporting text.",
        confidence="high",
        relevant_roles=relevant_roles,
        decision_relevance="Relevant.",
        created_by="data_health",
        status=status,
        invalidated_reason="Superseded." if status == EvidenceStatus.invalidated else None,
    )


def _ref(ev_id: str) -> EvidenceReference:
    return EvidenceReference(evidence_id=ev_id)


def _finding(ev_id: str) -> GroundedFinding:
    return GroundedFinding(
        claim="A grounded claim.",
        evidence_references=[_ref(ev_id)],
        confidence="high",
    )


def _view(
    role_key: RoleKey,
    ev_id: str,
    *,
    next_action: str | None = None,
    risks_or_assumptions: list[str] | None = None,
    human_review_required: bool = False,
    extra_findings: list[GroundedFinding] | None = None,
) -> RoleView:
    findings = [_finding(ev_id)] + (extra_findings or [])
    return RoleView(
        role_key=role_key,
        role_concern=f"Concern for {role_key.value}.",
        key_findings=findings,
        risks_or_assumptions=risks_or_assumptions or [],
        missing_information=[],
        next_action=next_action,
        dependency=None,
        human_review_required=human_review_required,
    )


def _all_internal_outcomes(evidence: list[EvidenceObject] | None = None) -> dict[RoleKey, RoleOutcome]:
    """Build outcomes where every role cites its own internal_observation evidence."""
    return {
        RoleKey.executive:       _view(RoleKey.executive,       _EV[RoleKey.executive]),
        RoleKey.data_analyst:    _view(RoleKey.data_analyst,    _EV[RoleKey.data_analyst]),
        RoleKey.data_engineer:   _view(RoleKey.data_engineer,   _EV[RoleKey.data_engineer]),
        RoleKey.sales_marketing: _view(RoleKey.sales_marketing, _EV[RoleKey.sales_marketing]),
        RoleKey.project_manager: _view(RoleKey.project_manager, _EV[RoleKey.project_manager]),
    }


def _base_evidence() -> list[EvidenceObject]:
    return [
        _make_ev(_EV[RoleKey.executive],       ["executive"]),
        _make_ev(_EV[RoleKey.data_analyst],    ["data_analyst"]),
        _make_ev(_EV[RoleKey.data_engineer],   ["data_engineer"]),
        _make_ev(_EV[RoleKey.sales_marketing], ["sales_marketing"]),
        _make_ev(_EV[RoleKey.project_manager], ["project_manager"]),
    ]


# ===========================================================================
# Test 1: Valid RoleViews grounded in internal_observation → no risk findings
# ===========================================================================

def test_all_internal_observation_produces_no_findings():
    """RoleViews grounded solely in internal_observation produce zero RiskFinding records."""
    outcomes = _all_internal_outcomes()
    evidence = _base_evidence()
    result = check_role_risks(outcomes, evidence)

    assert result.findings == []
    assert result.has_blocking_risks is False
    assert result.human_review_required is False
    assert result.reviewed_role_keys == list(_ROLE_EXECUTION_ORDER)


# ===========================================================================
# Test 2: external_context_only → medium review risk
# ===========================================================================

def test_external_context_only_claim_produces_medium_review_risk():
    """A GroundedFinding citing only external_context evidence → external_context_only, medium."""
    ev_ext = _make_ev(_EV_EXT, ["executive"], scope=EvidenceScope.external_context)
    evidence = _base_evidence() + [ev_ext]

    outcomes = _all_internal_outcomes()
    # Override executive to cite external-context-only evidence.
    outcomes[RoleKey.executive] = _view(
        RoleKey.executive, _EV_EXT, human_review_required=True
    )

    result = check_role_risks(outcomes, evidence)

    exec_findings = [f for f in result.findings if f.role_key == RoleKey.executive]
    assert len(exec_findings) == 1
    f = exec_findings[0]
    assert f.risk_code == RiskCode.external_context_only
    assert f.severity == RiskSeverity.medium
    assert f.blocks_downstream is False
    assert f.requires_human_review is True
    assert "external context" in f.message.lower()
    assert _EV_EXT in f.evidence_ids


# ===========================================================================
# Test 3: assumption_only → blocking risk
# ===========================================================================

def test_assumption_only_claim_produces_blocking_risk():
    """A GroundedFinding citing only assumption-scope evidence → assumption_only, high, blocking."""
    ev_ass = _make_ev(_EV_ASS, ["executive"], scope=EvidenceScope.assumption)
    evidence = _base_evidence() + [ev_ass]

    outcomes = _all_internal_outcomes()
    outcomes[RoleKey.executive] = _view(
        RoleKey.executive,
        _EV_ASS,
        human_review_required=True,
        risks_or_assumptions=["Declared assumption."],
    )

    result = check_role_risks(outcomes, evidence)

    exec_findings = [f for f in result.findings if f.role_key == RoleKey.executive]
    risk_codes = {f.risk_code for f in exec_findings}
    assert RiskCode.assumption_only in risk_codes
    f = next(f for f in exec_findings if f.risk_code == RiskCode.assumption_only)
    assert f.severity == RiskSeverity.high
    assert f.blocks_downstream is True
    assert f.requires_human_review is True
    assert "assumption" in f.message.lower()


# ===========================================================================
# Test 4: assumption evidence + empty risks_or_assumptions → assumption_not_declared
# ===========================================================================

def test_assumption_evidence_with_empty_declaration_produces_not_declared():
    """Assumption evidence cited without populating risks_or_assumptions → assumption_not_declared."""
    ev_ass = _make_ev(_EV_ASS, ["executive"], scope=EvidenceScope.assumption)
    evidence = _base_evidence() + [ev_ass]

    outcomes = _all_internal_outcomes()
    # risks_or_assumptions intentionally left empty.
    outcomes[RoleKey.executive] = _view(
        RoleKey.executive,
        _EV_ASS,
        human_review_required=True,
        risks_or_assumptions=[],
    )

    result = check_role_risks(outcomes, evidence)

    codes = {f.risk_code for f in result.findings if f.role_key == RoleKey.executive}
    assert RiskCode.assumption_not_declared in codes


# ===========================================================================
# Test 5: stated_priority_only → medium review risk
# ===========================================================================

def test_stated_priority_only_produces_medium_review_risk():
    """A claim grounded only in stated_priority evidence → stated_priority_only, medium."""
    ev_pri = _make_ev(_EV_PRI, ["executive"], scope=EvidenceScope.stated_priority)
    evidence = _base_evidence() + [ev_pri]

    outcomes = _all_internal_outcomes()
    outcomes[RoleKey.executive] = _view(
        RoleKey.executive, _EV_PRI, human_review_required=True
    )

    result = check_role_risks(outcomes, evidence)

    exec_findings = [f for f in result.findings if f.role_key == RoleKey.executive]
    codes = {f.risk_code for f in exec_findings}
    assert RiskCode.stated_priority_only in codes
    f = next(f for f in exec_findings if f.risk_code == RiskCode.stated_priority_only)
    assert f.severity == RiskSeverity.medium
    assert f.blocks_downstream is False
    assert "stated priority" in f.message.lower()


# ===========================================================================
# Test 6: next_action without internal_observation → blocking risk
# ===========================================================================

def test_next_action_without_internal_observation_produces_blocking_risk():
    """RoleView.next_action with no internal_observation evidence → action_without_internal_evidence."""
    ev_ext = _make_ev(_EV_EXT, ["executive"], scope=EvidenceScope.external_context)
    evidence = _base_evidence() + [ev_ext]

    outcomes = _all_internal_outcomes()
    outcomes[RoleKey.executive] = _view(
        RoleKey.executive,
        _EV_EXT,
        next_action="Expand marketing spend.",
        human_review_required=True,
    )

    result = check_role_risks(outcomes, evidence)

    codes = {f.risk_code for f in result.findings if f.role_key == RoleKey.executive}
    assert RiskCode.action_without_internal_evidence in codes
    f = next(
        f for f in result.findings
        if f.role_key == RoleKey.executive
        and f.risk_code == RiskCode.action_without_internal_evidence
    )
    assert f.blocks_downstream is True
    assert f.requires_human_review is True
    assert f.claim_index is None


# ===========================================================================
# Test 7: review-required finding + human_review_required=False → exactly one bypass
# ===========================================================================

def test_human_review_bypass_produced_when_review_suppressed():
    """If a finding requires review but human_review_required=False → exactly one human_review_bypass."""
    ev_ext = _make_ev(_EV_EXT, ["executive"], scope=EvidenceScope.external_context)
    evidence = _base_evidence() + [ev_ext]

    outcomes = _all_internal_outcomes()
    # human_review_required=False despite external-context risk.
    outcomes[RoleKey.executive] = _view(
        RoleKey.executive,
        _EV_EXT,
        human_review_required=False,
    )

    result = check_role_risks(outcomes, evidence)

    bypass_findings = [
        f for f in result.findings
        if f.role_key == RoleKey.executive and f.risk_code == RiskCode.human_review_bypass
    ]
    assert len(bypass_findings) == 1
    bf = bypass_findings[0]
    assert bf.severity == RiskSeverity.critical
    assert bf.blocks_downstream is True
    assert bf.requires_human_review is True


# ===========================================================================
# Test 8: InsufficientEvidence and RoleGenerationFailure → typed risk findings
# ===========================================================================

def test_insufficient_and_generation_failure_produce_typed_findings():
    """InsufficientEvidence → insufficient_evidence (high); RoleGenerationFailure → role_generation_failure (critical)."""
    outcomes = _all_internal_outcomes()
    outcomes[RoleKey.data_analyst] = InsufficientEvidence(
        role_key=RoleKey.data_analyst,
        reason="No active evidence for this role.",
    )
    outcomes[RoleKey.data_engineer] = RoleGenerationFailure(
        role_key=RoleKey.data_engineer,
        failure_code="provider_error",
        reason="Provider crashed.",
    )
    evidence = _base_evidence()
    result = check_role_risks(outcomes, evidence)

    da_f = next(f for f in result.findings if f.role_key == RoleKey.data_analyst)
    assert da_f.risk_code == RiskCode.insufficient_evidence
    assert da_f.severity == RiskSeverity.high
    assert da_f.blocks_downstream is True
    assert da_f.claim_index is None

    de_f = next(f for f in result.findings if f.role_key == RoleKey.data_engineer)
    assert de_f.risk_code == RiskCode.role_generation_failure
    assert de_f.severity == RiskSeverity.critical
    assert de_f.blocks_downstream is True
    assert de_f.claim_index is None

    assert result.has_blocking_risks is True
    assert result.human_review_required is True


# ===========================================================================
# Test 9: Mixed evidence with internal_observation → no scope-only finding;
#         fail-closed for unknown/inactive/conflicting evidence
# ===========================================================================

def test_mixed_evidence_and_fail_closed_behavior():
    """internal_observation alongside other scopes suppresses scope-only findings.
    Invalid outcomes, unknown, inactive, and conflicting evidence raise RiskInputError.
    """
    ev_int = _make_ev(_EV[RoleKey.executive],  ["executive"], EvidenceScope.internal_observation)
    ev_ext = _make_ev(_EV_EXT,                  ["executive"], EvidenceScope.external_context)
    evidence = _base_evidence() + [ev_ext]

    # Mix internal + external for executive: no scope-only finding expected.
    mixed_view = RoleView(
        role_key=RoleKey.executive,
        role_concern="Concern.",
        key_findings=[
            GroundedFinding(
                claim="Mixed claim.",
                evidence_references=[_ref(_EV[RoleKey.executive]), _ref(_EV_EXT)],
                confidence="high",
            )
        ],
        risks_or_assumptions=[],
        missing_information=[],
        next_action=None,
        dependency=None,
        human_review_required=False,
    )
    outcomes = _all_internal_outcomes()
    outcomes[RoleKey.executive] = mixed_view

    result = check_role_risks(outcomes, evidence)
    codes = {f.risk_code for f in result.findings if f.role_key == RoleKey.executive}
    # No scope-only risk because internal_observation is present.
    assert RiskCode.external_context_only not in codes

    # Fail-closed: RoleView cites an unknown evidence_id.
    ghost_id = "ev-ghost_ev_00-aabbccddeeff"
    outcomes2 = _all_internal_outcomes()
    outcomes2[RoleKey.executive] = _view(RoleKey.executive, ghost_id)
    with pytest.raises(RiskInputError, match="unknown"):
        check_role_risks(outcomes2, _base_evidence())

    # Fail-closed: RoleView cites an invalidated evidence_id.
    ev_dead = _make_ev(
        _EV[RoleKey.executive], ["executive"],
        scope=EvidenceScope.internal_observation,
        status=EvidenceStatus.invalidated,
    )
    outcomes3 = _all_internal_outcomes()
    outcomes3[RoleKey.executive] = _view(RoleKey.executive, _EV[RoleKey.executive])
    with pytest.raises(RiskInputError, match="invalidated"):
        check_role_risks(outcomes3, [ev_dead] + _base_evidence()[1:])

    # Fail-closed: conflicting EvidenceObject records.
    ev_conflict = _make_ev(
        _EV[RoleKey.executive], ["executive"],
        scope=EvidenceScope.external_context,  # different scope = different object
    )
    with pytest.raises(RiskInputError):
        check_role_risks(outcomes, _base_evidence() + [ev_conflict])

    # Fail-closed before evidence validation: mapping key and outcome-declared
    # role identity must agree for every supported outcome type.
    mismatched_outcomes = (
        _view(
            RoleKey.sales_marketing,
            _EV[RoleKey.sales_marketing],
        ),
        InsufficientEvidence(
            role_key=RoleKey.data_engineer,
            reason="Mismatched role identity.",
        ),
        RoleGenerationFailure(
            role_key=RoleKey.project_manager,
            failure_code="provider_error",
            reason="Mismatched role identity.",
        ),
    )
    for mismatched in mismatched_outcomes:
        invalid_identity = _all_internal_outcomes()
        invalid_identity[RoleKey.executive] = mismatched
        with pytest.raises(RiskInputError) as exc_info:
            check_role_risks(invalid_identity, [])
        message = str(exc_info.value)
        assert "mapping_key='executive'" in message
        assert mismatched.role_key.value in message
        assert type(mismatched).__name__ in message

    # Fail-closed before evidence validation: unsupported outcome values.
    invalid_value = _all_internal_outcomes()
    invalid_value[RoleKey.executive] = object()  # type: ignore[assignment]
    with pytest.raises(RiskInputError) as exc_info:
        check_role_risks(invalid_value, [])
    assert "unsupported outcome" in str(exc_info.value)
    assert "object" in str(exc_info.value)

    # Fail-closed safely for a non-RoleKey mapping key; no .value assumption.
    invalid_key: dict[Any, RoleOutcome] = _all_internal_outcomes()
    executive_outcome = invalid_key.pop(RoleKey.executive)
    invalid_key["executive"] = executive_outcome
    with pytest.raises(RiskInputError) as exc_info:
        check_role_risks(invalid_key, [])  # type: ignore[arg-type]
    assert "non-RoleKey" in str(exc_info.value)
    assert "'executive'" in str(exc_info.value)

    # The exact five RoleKey values remain mandatory.
    missing_key = _all_internal_outcomes()
    missing_key.pop(RoleKey.project_manager)
    with pytest.raises(RiskInputError, match="exactly the five"):
        check_role_risks(missing_key, [])


# ===========================================================================
# Test 10: Deterministic ordering and aggregate flags
# ===========================================================================

def test_findings_are_deterministically_ordered_and_aggregates_correct():
    """Findings are ordered by role, then claim-level before role-level, then risk code.
    has_blocking_risks and human_review_required match the aggregate."""
    ev_ext = _make_ev(_EV_EXT, ["executive"], scope=EvidenceScope.external_context)
    ev_ass = _make_ev(_EV_ASS, ["data_analyst"], scope=EvidenceScope.assumption)
    evidence = _base_evidence() + [ev_ext, ev_ass]

    outcomes = _all_internal_outcomes()
    # Executive: external-context only (medium, non-blocking).
    outcomes[RoleKey.executive] = _view(
        RoleKey.executive, _EV_EXT, human_review_required=True
    )
    # Data analyst: assumption only, risks declared (high, blocking).
    outcomes[RoleKey.data_analyst] = _view(
        RoleKey.data_analyst,
        _EV_ASS,
        risks_or_assumptions=["Assumption declared."],
        human_review_required=True,
    )

    result = check_role_risks(outcomes, evidence)

    # All five reviewed roles present in order.
    assert result.reviewed_role_keys == list(_ROLE_EXECUTION_ORDER)

    # Executive findings come before data_analyst findings.
    exec_indices = [i for i, f in enumerate(result.findings) if f.role_key == RoleKey.executive]
    da_indices   = [i for i, f in enumerate(result.findings) if f.role_key == RoleKey.data_analyst]
    if exec_indices and da_indices:
        assert max(exec_indices) < min(da_indices)

    # Aggregate flags consistent.
    expected_blocking = any(f.blocks_downstream for f in result.findings)
    assert result.has_blocking_risks == expected_blocking
    expected_review = any(f.requires_human_review for f in result.findings)
    assert result.human_review_required == expected_review

    # Running the same check twice produces identical results (determinism).
    result2 = check_role_risks(outcomes, evidence)
    assert result.findings == result2.findings
    assert result.has_blocking_risks == result2.has_blocking_risks
    assert result.human_review_required == result2.human_review_required
