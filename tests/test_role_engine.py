"""
tests/test_role_engine.py — Task 6A-2: provider-neutral grounded role engine.

Exactly 10 test functions covering:
 1. Policy loads and provider requests contain only allowed inputs.
 2. Evidence is filtered by active status and relevant_roles.
 3. No eligible evidence returns InsufficientEvidence; provider not called.
 4. A valid grounded RoleView is accepted.
 5. Unknown evidence citation fails closed.
 6. Hidden active evidence citation fails closed.
 7. Invalidated evidence citation fails closed.
 8. Role-key mismatch and malformed/extra output fail closed.
 9. Provider exception becomes provider_error while other roles continue.
10. Project Manager runs last, receives only successful prior RoleViews,
    aggregates missing_information, may cite only exposed evidence.
"""

from __future__ import annotations

import pathlib
from datetime import datetime, timezone
from typing import Any, Mapping

import pytest

from app.role_engine import (
    EvidenceRegistryConflictError,
    InsufficientEvidence,
    RoleGenerationFailure,
    RoleProvider,
    RoleRequest,
    run_role_engine,
)
from app.schemas import (
    EvidenceObject,
    EvidenceReference,
    EvidenceScope,
    EvidenceStatus,
    GroundedFinding,
    RoleKey,
    RoleView,
    SourceFormat,
    TabularSourceLocator,
)

# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------

_POLICY_PATH = pathlib.Path("config/role_policy.json")
_DT = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

_EV_ID_EXEC = "ev-missing_val-0000000000aa"
_EV_ID_DA   = "ev-missing_val-0000000000bb"
_EV_ID_DE   = "ev-missing_val-0000000000cc"
_EV_ID_SM   = "ev-missing_val-0000000000dd"
_EV_ID_HIDDEN = "ev-missing_val-0000000000ee"
_DIGEST     = "a" * 64
_SRC_ID     = "src-csv-000000000001"


def _make_evidence(
    evidence_id: str,
    relevant_roles: list[str],
    status: EvidenceStatus = EvidenceStatus.active,
) -> EvidenceObject:
    return EvidenceObject(
        evidence_id=evidence_id,
        identity_digest=_DIGEST,
        source_id=_SRC_ID,
        source_format=SourceFormat.csv,
        source_locator=TabularSourceLocator(columns=["revenue"]),
        evidence_type="missing_value_rate",
        evidence_scope=EvidenceScope.internal_observation,
        extraction_method="deterministic",
        finding="Revenue column has 20% missing values.",
        supporting_evidence="20 of 100 rows have null in revenue.",
        confidence="high",
        relevant_roles=relevant_roles,
        decision_relevance="Affects model quality.",
        created_by="data_health",
        status=status,
        invalidated_reason="Superseded." if status == EvidenceStatus.invalidated else None,
    )


def _make_view(role_key: RoleKey, ev_id: str, missing: list[str] | None = None) -> dict:
    """Return a valid dict that can be model_validate'd into RoleView."""
    return {
        "role_key": role_key.value,
        "role_concern": f"Primary concern for {role_key.value}.",
        "key_findings": [
            {
                "claim": f"Grounded claim for {role_key.value}.",
                "evidence_references": [{"evidence_id": ev_id}],
                "confidence": "high",
            }
        ],
        "risks_or_assumptions": [],
        "missing_information": missing or [],
        "next_action": None,
        "dependency": None,
        "human_review_required": False,
    }


class _StubProvider:
    """Configurable stub — returns pre-set outputs per role_key."""

    def __init__(self, outputs: dict[RoleKey, Any] | None = None) -> None:
        self.outputs: dict[RoleKey, Any] = outputs or {}
        self.calls: list[RoleRequest] = []

    def generate_role_view(self, request: RoleRequest) -> Mapping[str, Any]:
        self.calls.append(request)
        if request.role_key not in self.outputs:
            raise KeyError(f"No output configured for {request.role_key}")
        result = self.outputs[request.role_key]
        if isinstance(result, Exception):
            raise result
        return result


def _all_evidence() -> list[EvidenceObject]:
    return [
        _make_evidence(_EV_ID_EXEC, ["executive"]),
        _make_evidence(_EV_ID_DA, ["data_analyst"]),
        _make_evidence(_EV_ID_DE, ["data_engineer"]),
        _make_evidence(_EV_ID_SM, ["sales_marketing"]),
    ]


def _all_stub_outputs() -> dict[RoleKey, Any]:
    return {
        RoleKey.executive:       _make_view(RoleKey.executive,       _EV_ID_EXEC),
        RoleKey.data_analyst:    _make_view(RoleKey.data_analyst,    _EV_ID_DA),
        RoleKey.data_engineer:   _make_view(RoleKey.data_engineer,   _EV_ID_DE),
        RoleKey.sales_marketing: _make_view(RoleKey.sales_marketing, _EV_ID_SM),
        RoleKey.project_manager: _make_view(RoleKey.project_manager, _EV_ID_EXEC),
    }


# ===========================================================================
# Test 1: Policy loads and provider requests contain only allowed inputs
# ===========================================================================

def test_policy_loads_and_inputs_filtered_to_allowed():
    """Provider receives only inputs listed in the role's allowed_inputs."""
    evidence = [_make_evidence(_EV_ID_EXEC, ["executive"])]
    provider = _StubProvider({
        RoleKey.executive:       _make_view(RoleKey.executive, _EV_ID_EXEC),
        RoleKey.data_analyst:    _make_view(RoleKey.data_analyst, _EV_ID_DA),
        RoleKey.data_engineer:   _make_view(RoleKey.data_engineer, _EV_ID_DE),
        RoleKey.sales_marketing: _make_view(RoleKey.sales_marketing, _EV_ID_SM),
        RoleKey.project_manager: _make_view(RoleKey.project_manager, _EV_ID_EXEC),
    })
    # Provide an input that is NOT in any allowed_inputs list.
    available = {
        "data_health_summary": {"row_count": 100},
        "forbidden_extra": "must_not_appear",
    }
    outcomes = run_role_engine(
        provider=provider,
        evidence_objects=evidence,
        available_inputs=available,
        policy_path=_POLICY_PATH,
    )
    # executive call received inputs; "forbidden_extra" must not be there.
    exec_call = next(c for c in provider.calls if c.role_key == RoleKey.executive)
    assert "forbidden_extra" not in exec_call.inputs
    # data_health_summary is in executive's allowed_inputs, so it should appear.
    assert "data_health_summary" in exec_call.inputs
    assert set(outcomes.keys()) == set(RoleKey)


# ===========================================================================
# Test 2: Evidence filtered by active status and relevant_roles
# ===========================================================================

def test_evidence_filtered_by_status_and_relevant_roles():
    """Evidence filtering and duplicate-ID registry behavior fail closed."""
    ev_active   = _make_evidence(_EV_ID_EXEC, ["executive"], EvidenceStatus.active)
    ev_inactive = _make_evidence(_EV_ID_DA,   ["executive"], EvidenceStatus.invalidated)
    ev_other    = _make_evidence(_EV_ID_DE,   ["data_engineer"], EvidenceStatus.active)

    provider = _StubProvider({
        RoleKey.executive:       _make_view(RoleKey.executive, _EV_ID_EXEC),
        RoleKey.data_analyst:    _make_view(RoleKey.data_analyst, _EV_ID_DA),
        RoleKey.data_engineer:   _make_view(RoleKey.data_engineer, _EV_ID_DE),
        RoleKey.sales_marketing: _make_view(RoleKey.sales_marketing, _EV_ID_SM),
        RoleKey.project_manager: _make_view(RoleKey.project_manager, _EV_ID_EXEC),
    })
    run_role_engine(
        provider=provider,
        evidence_objects=[ev_active, ev_inactive, ev_other],
        available_inputs={},
        policy_path=_POLICY_PATH,
    )
    exec_call = next(c for c in provider.calls if c.role_key == RoleKey.executive)
    exposed = exec_call.exposed_evidence_ids
    assert _EV_ID_EXEC in exposed          # active + executive
    assert _EV_ID_DA   not in exposed      # inactive
    assert _EV_ID_DE   not in exposed      # wrong role

    # An exact duplicate record is accepted, retains the first registry value,
    # and does not change normal role execution.
    duplicate_provider = _StubProvider(_all_stub_outputs())
    duplicate_outcomes = run_role_engine(
        provider=duplicate_provider,
        evidence_objects=[ev_active, ev_active.model_copy(deep=True)],
        available_inputs={},
        policy_path=_POLICY_PATH,
    )
    assert isinstance(duplicate_outcomes[RoleKey.executive], RoleView)

    # Any field difference for the same evidence_id is an invalid engine input.
    # Registry construction happens before provider calls.
    conflicting = ev_active.model_copy(
        update={
            "identity_digest": "b" * 64,
            "finding": "Conflicting finding for the same evidence ID.",
        }
    )
    conflict_provider = _StubProvider(_all_stub_outputs())
    with pytest.raises(EvidenceRegistryConflictError) as exc_info:
        run_role_engine(
            provider=conflict_provider,
            evidence_objects=[ev_active, conflicting],
            available_inputs={},
            policy_path=_POLICY_PATH,
        )
    assert exc_info.value.evidence_id == _EV_ID_EXEC
    assert exc_info.value.existing_identity_digest == _DIGEST
    assert exc_info.value.new_identity_digest == "b" * 64
    assert conflict_provider.calls == []


# ===========================================================================
# Test 3: No eligible evidence → InsufficientEvidence, provider not called
# ===========================================================================

def test_no_eligible_evidence_returns_insufficient_evidence():
    """Roles with zero active eligible evidence get InsufficientEvidence; no provider call."""
    # Provide evidence only for data_engineer; other roles get nothing.
    evidence = [_make_evidence(_EV_ID_DE, ["data_engineer"])]
    call_count: dict[RoleKey, int] = {}

    class _CountingProvider:
        def generate_role_view(self, request: RoleRequest) -> Mapping[str, Any]:
            call_count[request.role_key] = call_count.get(request.role_key, 0) + 1
            return _make_view(request.role_key, _EV_ID_DE)

    outcomes = run_role_engine(
        provider=_CountingProvider(),
        evidence_objects=evidence,
        available_inputs={},
        policy_path=_POLICY_PATH,
    )

    assert isinstance(outcomes[RoleKey.executive], InsufficientEvidence)
    assert RoleKey.executive not in call_count
    # data_engineer should be called and succeed.
    assert isinstance(outcomes[RoleKey.data_engineer], RoleView)
    assert call_count.get(RoleKey.data_engineer, 0) == 1


# ===========================================================================
# Test 4: Valid grounded RoleView is accepted
# ===========================================================================

def test_valid_grounded_role_view_accepted():
    """A correctly structured provider response produces a RoleView outcome."""
    evidence = _all_evidence()
    provider = _StubProvider(_all_stub_outputs())
    outcomes = run_role_engine(
        provider=provider,
        evidence_objects=evidence,
        available_inputs={},
        policy_path=_POLICY_PATH,
    )
    assert isinstance(outcomes[RoleKey.executive], RoleView)
    rv: RoleView = outcomes[RoleKey.executive]  # type: ignore[assignment]
    assert rv.role_key == RoleKey.executive
    assert len(rv.key_findings) == 1


# ===========================================================================
# Test 5: Unknown evidence citation fails closed
# ===========================================================================

def test_unknown_evidence_citation_fails_closed():
    """Citing an evidence_id that does not exist in the registry → unknown_evidence_reference."""
    ghost_id = "ev-ghost_ev_id-aabbccddeeff"
    evidence = [_make_evidence(_EV_ID_EXEC, ["executive"])]
    outputs = _all_stub_outputs()
    outputs[RoleKey.executive] = _make_view(RoleKey.executive, ghost_id)

    provider = _StubProvider(outputs)
    outcomes = run_role_engine(
        provider=provider,
        evidence_objects=evidence,
        available_inputs={},
        policy_path=_POLICY_PATH,
    )
    result = outcomes[RoleKey.executive]
    assert isinstance(result, RoleGenerationFailure)
    assert result.failure_code == "unknown_evidence_reference"


# ===========================================================================
# Test 6: Hidden active evidence citation fails closed
# ===========================================================================

def test_hidden_evidence_citation_fails_closed():
    """Citing active evidence that was not exposed to the provider → hidden_evidence_reference."""
    ev_exec    = _make_evidence(_EV_ID_EXEC, ["executive"])
    ev_hidden  = _make_evidence(_EV_ID_DA,   ["data_analyst"])  # active, but not for exec

    # Executive cites _EV_ID_DA which is active but was NOT in executive's exposed set.
    outputs = _all_stub_outputs()
    outputs[RoleKey.executive] = _make_view(RoleKey.executive, _EV_ID_DA)

    provider = _StubProvider(outputs)
    outcomes = run_role_engine(
        provider=provider,
        evidence_objects=[ev_exec, ev_hidden],
        available_inputs={},
        policy_path=_POLICY_PATH,
    )
    result = outcomes[RoleKey.executive]
    assert isinstance(result, RoleGenerationFailure)
    assert result.failure_code == "hidden_evidence_reference"


# ===========================================================================
# Test 7: Invalidated evidence citation fails closed
# ===========================================================================

def test_invalidated_evidence_citation_fails_closed():
    """Citing an invalidated evidence object → inactive_evidence_reference."""
    ev_active      = _make_evidence(_EV_ID_EXEC, ["executive"], EvidenceStatus.active)
    ev_invalidated = _make_evidence(_EV_ID_DA,   ["executive"], EvidenceStatus.invalidated)

    # Executive has both in its eligible pool by role (executive), but the
    # inactive one is filtered out from exposure.  Trick: cite it anyway.
    # The engine must look it up in the global registry and catch inactive status.
    # Because the inactive evidence is NOT in exposed_ids for the exec role,
    # we expect hidden_evidence_reference.  To get inactive_evidence_reference
    # specifically we must expose it by making it eligible (which means active);
    # but the spec says inactive evidence is never exposed.  Per citation
    # validation order: unknown → inactive → hidden.  Since the ID IS in the
    # registry (status=invalidated), we expect inactive_evidence_reference.
    #
    # Force the invalidated evidence to appear in the exposed set by giving it
    # a role that the engine will accept.  We do this by cheating the registry:
    # the engine builds the registry from ALL evidence_objects regardless of status.
    # So the id IS in registry → not unknown.
    # status == invalidated → inactive_evidence_reference fires before hidden check.

    outputs = _all_stub_outputs()
    # Make executive cite the invalidated evidence ID.
    outputs[RoleKey.executive] = _make_view(RoleKey.executive, _EV_ID_DA)

    provider = _StubProvider(outputs)
    outcomes = run_role_engine(
        provider=provider,
        evidence_objects=[ev_active, ev_invalidated],
        available_inputs={},
        policy_path=_POLICY_PATH,
    )
    result = outcomes[RoleKey.executive]
    assert isinstance(result, RoleGenerationFailure)
    # _EV_ID_DA is in registry (inactive), so we get inactive_evidence_reference.
    assert result.failure_code == "inactive_evidence_reference"


# ===========================================================================
# Test 8: Role-key mismatch and malformed/extra output fail closed
# ===========================================================================

def test_role_mismatch_and_invalid_output_fail_closed():
    """role_key mismatch and schema-invalid output both produce RoleGenerationFailure."""
    evidence = _all_evidence()

    # Case A: provider returns wrong role_key.
    outputs_mismatch = _all_stub_outputs()
    outputs_mismatch[RoleKey.executive] = _make_view(RoleKey.data_analyst, _EV_ID_EXEC)

    provider_mismatch = _StubProvider(outputs_mismatch)
    outcomes_a = run_role_engine(
        provider=provider_mismatch,
        evidence_objects=evidence,
        available_inputs={},
        policy_path=_POLICY_PATH,
    )
    r_a = outcomes_a[RoleKey.executive]
    assert isinstance(r_a, RoleGenerationFailure)
    assert r_a.failure_code == "role_mismatch"

    # Case B: provider returns structurally invalid output (missing required field).
    outputs_bad = _all_stub_outputs()
    outputs_bad[RoleKey.executive] = {"role_key": "executive"}  # missing required fields

    provider_bad = _StubProvider(outputs_bad)
    outcomes_b = run_role_engine(
        provider=provider_bad,
        evidence_objects=evidence,
        available_inputs={},
        policy_path=_POLICY_PATH,
    )
    r_b = outcomes_b[RoleKey.executive]
    assert isinstance(r_b, RoleGenerationFailure)
    assert r_b.failure_code == "invalid_output"


# ===========================================================================
# Test 9: Provider exception → provider_error; other roles continue
# ===========================================================================

def test_provider_exception_becomes_provider_error_others_continue():
    """A provider exception for one role produces provider_error; others complete normally."""
    evidence = _all_evidence()
    outputs = _all_stub_outputs()
    # Make data_analyst raise.
    outputs[RoleKey.data_analyst] = RuntimeError("simulated provider crash")

    provider = _StubProvider(outputs)
    outcomes = run_role_engine(
        provider=provider,
        evidence_objects=evidence,
        available_inputs={},
        policy_path=_POLICY_PATH,
    )

    da_result = outcomes[RoleKey.data_analyst]
    assert isinstance(da_result, RoleGenerationFailure)
    assert da_result.failure_code == "provider_error"
    assert "simulated provider crash" in da_result.reason

    # Other roles must still succeed.
    assert isinstance(outcomes[RoleKey.executive], RoleView)
    assert isinstance(outcomes[RoleKey.data_engineer], RoleView)


# ===========================================================================
# Test 10: Project Manager sequencing, aggregation, exposed evidence
# ===========================================================================

def test_project_manager_runs_last_aggregates_and_restricts_citations():
    """PM runs after first four, gets only successful RoleViews, aggregates
    missing_information, and may only cite evidence cited by prior views."""
    hidden_evidence = _make_evidence(_EV_ID_HIDDEN, ["project_manager"])
    evidence = [*_all_evidence(), hidden_evidence]

    prior_missing = [
        "Revenue breakdown by region missing.",
        "Segment validation not complete.",
    ]

    outputs: dict[RoleKey, Any] = {
        RoleKey.executive:       _make_view(RoleKey.executive,       _EV_ID_EXEC, missing=prior_missing[:1]),
        RoleKey.data_analyst:    _make_view(RoleKey.data_analyst,    _EV_ID_DA,   missing=prior_missing[1:]),
        RoleKey.data_engineer:   _make_view(RoleKey.data_engineer,   _EV_ID_DE),
        RoleKey.sales_marketing: _make_view(RoleKey.sales_marketing, _EV_ID_SM),
        RoleKey.project_manager: _make_view(RoleKey.project_manager, _EV_ID_HIDDEN),
    }

    pm_requests: list[RoleRequest] = []
    call_order: list[RoleKey] = []

    class _PMSpyProvider:
        def generate_role_view(self, request: RoleRequest) -> Mapping[str, Any]:
            call_order.append(request.role_key)
            if request.role_key == RoleKey.project_manager:
                pm_requests.append(request)
            return outputs[request.role_key]

    outcomes = run_role_engine(
        provider=_PMSpyProvider(),
        evidence_objects=evidence,
        available_inputs={},
        policy_path=_POLICY_PATH,
    )

    # The hidden ID exists and is active, but PM was not exposed to it through
    # any successful prior RoleView, so its citation fails closed.
    pm_outcome = outcomes[RoleKey.project_manager]
    assert isinstance(pm_outcome, RoleGenerationFailure)
    assert pm_outcome.failure_code == "hidden_evidence_reference"

    # Exactly one PM request was made.
    assert len(pm_requests) == 1
    pm_req = pm_requests[0]

    # PM's exposed_evidence_ids is the union of evidence cited by successful priors.
    assert _EV_ID_EXEC in pm_req.exposed_evidence_ids
    assert _EV_ID_DA in pm_req.exposed_evidence_ids
    assert _EV_ID_HIDDEN not in pm_req.exposed_evidence_ids

    # PM received successful role_views (not failures).
    pm_views = pm_req.inputs.get("role_views", [])
    assert all(isinstance(v, RoleView) for v in pm_views)
    assert len(pm_views) == 4  # all four prior roles succeeded

    # PM received aggregated missing_information.
    pm_missing = pm_req.inputs.get("missing_information", [])
    assert pm_missing == prior_missing

    # Verify execution order: PM is last in outcomes dict.
    keys = list(outcomes.keys())
    assert keys[-1] == RoleKey.project_manager
    assert keys[0] == RoleKey.executive
    assert call_order[-1] == RoleKey.project_manager
