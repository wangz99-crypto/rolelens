"""
tests/test_role_schemas.py — Task 6A-1: RoleKey, GroundedFinding, RoleView schemas.

12 test functions covering:
 1. RoleKey contains exactly five approved machine keys.
 2. Policy JSON contains exactly the same five keys.
 3. Every policy required_outputs list matches the new RoleView contract.
 4. Valid GroundedFinding.
 5. Empty evidence_references rejected.
 6. Duplicate evidence IDs within one finding rejected.
 7. Valid RoleView.
 8. Empty key_findings rejected.
 9. Blank list values rejected.
10. Duplicate list values rejected.
11. Blank optional next_action/dependency rejected.
12. Extra fields rejected and models remain frozen.
"""

from __future__ import annotations

import json
import pathlib

import pytest
from pydantic import ValidationError

from app.schemas import (
    EvidenceReference,
    GroundedFinding,
    RoleKey,
    RoleView,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_POLICY_PATH = pathlib.Path("config/role_policy.json")

_REQUIRED_OUTPUTS = [
    "role_concern",
    "key_findings",
    "risks_or_assumptions",
    "missing_information",
    "next_action",
    "dependency",
    "human_review_required",
]

# Shared fixture values
_EV_ID_A = "ev-missing_val-0123456789ab"
_EV_ID_B = "ev-outlier_fla-aabbccddeeff"


def _ref(ev_id: str) -> EvidenceReference:
    return EvidenceReference(evidence_id=ev_id)


def _finding(ev_ids: list[str] | None = None, confidence: str = "high") -> GroundedFinding:
    if ev_ids is None:
        ev_ids = [_EV_ID_A]
    return GroundedFinding(
        claim="Column revenue has 18% missing values, limiting analysis.",
        evidence_references=[_ref(eid) for eid in ev_ids],
        confidence=confidence,  # type: ignore[arg-type]
    )


def _valid_role_view(**overrides) -> dict:
    base = dict(
        role_key=RoleKey.data_engineer,
        role_concern="Data quality must be resolved before modelling can proceed.",
        key_findings=[_finding()],
        risks_or_assumptions=["Revenue column missing rate may be seasonal."],
        missing_information=["Source system documentation not provided."],
        next_action="Impute or flag missing revenue values.",
        dependency=None,
        human_review_required=False,
    )
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Test 1: RoleKey contains exactly five approved machine keys
# ---------------------------------------------------------------------------

def test_role_key_exactly_five_values():
    expected = {"executive", "data_analyst", "data_engineer", "sales_marketing", "project_manager"}
    actual = {k.value for k in RoleKey}
    assert actual == expected, f"RoleKey values differ: {actual}"


# ---------------------------------------------------------------------------
# Test 2: Policy JSON contains exactly the same five keys
# ---------------------------------------------------------------------------

def test_policy_role_keys_match_role_key_enum():
    policy = json.loads(_POLICY_PATH.read_text(encoding="utf-8"))
    policy_keys = set(policy["roles"].keys())
    enum_keys = {k.value for k in RoleKey}
    assert policy_keys == enum_keys, (
        f"config/role_policy.json role keys {policy_keys!r} "
        f"do not match RoleKey enum {enum_keys!r}"
    )


# ---------------------------------------------------------------------------
# Test 3: Every policy required_outputs matches the RoleView contract
# ---------------------------------------------------------------------------

def test_policy_required_outputs_match_role_view_contract():
    policy = json.loads(_POLICY_PATH.read_text(encoding="utf-8"))
    for role_key, role_def in policy["roles"].items():
        actual = role_def["required_outputs"]
        assert actual == _REQUIRED_OUTPUTS, (
            f"role={role_key!r}: required_outputs {actual!r} "
            f"does not match expected {_REQUIRED_OUTPUTS!r}"
        )


# ---------------------------------------------------------------------------
# Test 4: Valid GroundedFinding
# ---------------------------------------------------------------------------

def test_valid_grounded_finding():
    f = _finding([_EV_ID_A, _EV_ID_B], confidence="medium")
    assert f.claim.startswith("Column revenue")
    assert len(f.evidence_references) == 2
    assert f.confidence == "medium"


# ---------------------------------------------------------------------------
# Test 5: Empty evidence_references rejected
# ---------------------------------------------------------------------------

def test_empty_evidence_references_rejected():
    with pytest.raises(ValidationError, match="evidence_references"):
        GroundedFinding(
            claim="Some observation.",
            evidence_references=[],
            confidence="low",
        )


# ---------------------------------------------------------------------------
# Test 6: Duplicate evidence IDs within one finding rejected
# ---------------------------------------------------------------------------

def test_duplicate_evidence_ids_within_finding_rejected():
    with pytest.raises(ValidationError, match="duplicate"):
        GroundedFinding(
            claim="Duplicate citation.",
            evidence_references=[_ref(_EV_ID_A), _ref(_EV_ID_A)],
            confidence="high",
        )


# ---------------------------------------------------------------------------
# Test 7: Valid RoleView
# ---------------------------------------------------------------------------

def test_valid_role_view():
    rv = RoleView(**_valid_role_view())
    assert rv.role_key == RoleKey.data_engineer
    assert len(rv.key_findings) == 1
    assert rv.human_review_required is False
    assert rv.dependency is None


# ---------------------------------------------------------------------------
# Test 8: Empty key_findings rejected
# ---------------------------------------------------------------------------

def test_empty_key_findings_rejected():
    with pytest.raises(ValidationError, match="key_findings"):
        RoleView(**_valid_role_view(key_findings=[]))


# ---------------------------------------------------------------------------
# Test 9: Blank list values rejected
# ---------------------------------------------------------------------------

def test_blank_risks_or_assumptions_rejected():
    with pytest.raises(ValidationError, match="risks_or_assumptions"):
        RoleView(**_valid_role_view(risks_or_assumptions=["valid risk", ""]))


def test_blank_missing_information_rejected():
    with pytest.raises(ValidationError, match="missing_information"):
        RoleView(**_valid_role_view(missing_information=["  "]))


# ---------------------------------------------------------------------------
# Test 10: Duplicate list values rejected
# ---------------------------------------------------------------------------

def test_duplicate_risks_or_assumptions_rejected():
    with pytest.raises(ValidationError, match="risks_or_assumptions"):
        RoleView(**_valid_role_view(
            risks_or_assumptions=["Same risk.", "Same risk."]
        ))


def test_duplicate_missing_information_rejected():
    with pytest.raises(ValidationError, match="missing_information"):
        RoleView(**_valid_role_view(
            missing_information=["Same gap.", "Same gap."]
        ))


# ---------------------------------------------------------------------------
# Test 11: Blank optional next_action/dependency rejected
# ---------------------------------------------------------------------------

def test_blank_next_action_rejected():
    with pytest.raises(ValidationError, match="next_action"):
        RoleView(**_valid_role_view(next_action="   "))


def test_blank_dependency_rejected():
    with pytest.raises(ValidationError, match="dependency"):
        RoleView(**_valid_role_view(dependency=""))


# ---------------------------------------------------------------------------
# Test 12: Extra fields rejected and models remain frozen
# ---------------------------------------------------------------------------

def test_extra_field_on_grounded_finding_rejected():
    with pytest.raises(ValidationError):
        GroundedFinding(
            claim="Valid claim.",
            evidence_references=[_ref(_EV_ID_A)],
            confidence="high",
            unknown_field="surprise",
        )


def test_extra_field_on_role_view_rejected():
    with pytest.raises(ValidationError):
        RoleView(**_valid_role_view(display_name="should be rejected"))


def test_role_view_is_frozen():
    rv = RoleView(**_valid_role_view())
    with pytest.raises(ValidationError):
        rv.role_concern = "mutated"  # type: ignore[misc]
    # Value is unchanged after failed assignment.
    assert "mutated" not in rv.role_concern


def test_grounded_finding_is_frozen():
    f = _finding()
    original_claim = f.claim
    with pytest.raises(ValidationError):
        f.claim = "overwritten"  # type: ignore[misc]
    assert f.claim == original_claim
