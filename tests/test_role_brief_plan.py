"""Focused tests for deterministic five-role semantic planning."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from app import product_api
from app.role_brief_plan import (
    SECTION_ORDER,
    HandoffPlan,
    RoleBriefPlanSet,
    build_role_brief_plan_set,
    build_semantic_atom_id,
    ordered_assumption_refs,
    ordered_evidence_refs,
    role_atoms,
    validate_role_brief_plan_set,
)
from app.role_impact_brief import ROLE_ORDER, RoleBriefGenerationContext


def _trusted_plan(
    lift: str,
) -> tuple[RoleBriefPlanSet, RoleBriefGenerationContext]:
    """Build one plan from the real frozen product/DD-3 path."""
    request = product_api.RoleBriefRequest(
        pilot_population=500,
        expected_incremental_lift=lift,
        cost_per_intervention="30",
        retained_customer_value="500",
        currency="USD",
    )
    build = product_api._rebuild_trusted_revision(request)
    context = product_api._role_brief_generation_context(build)
    return (
        build_role_brief_plan_set(
            fingerprint=product_api._fingerprint_for_build(build),
            context=context,
        ),
        context,
    )


def test_plan_has_canonical_five_role_fifteen_atom_topology() -> None:
    """Every role owns exactly the three fixed narrative sections."""
    plan, _context = _trusted_plan("0.03")
    assert tuple(role.role_key for role in plan.roles) == ROLE_ORDER
    assert sum(len(role_atoms(role)) for role in plan.roles) == 15
    assert all(
        tuple(atom.section for atom in role_atoms(role)) == SECTION_ORDER
        for role in plan.roles
    )
    assert all(
        atom.atom_id.startswith("atom_") and len(atom.atom_id) == 69
        for role in plan.roles
        for atom in role_atoms(role)
    )


def test_repeated_builds_reproduce_plan_and_atom_ids() -> None:
    """The same accepted state produces byte-stable semantic source bindings."""
    first, _context = _trusted_plan("0.03")
    second, _context = _trusted_plan("0.03")
    assert first == second
    assert [atom.atom_id for role in first.roles for atom in role_atoms(role)] == [
        atom.atom_id for role in second.roles for atom in role_atoms(role)
    ]


@pytest.mark.parametrize("change", ["fingerprint", "claim", "evidence", "assumption"])
def test_atom_id_changes_with_every_governed_component(change: str) -> None:
    """Fingerprint, proposition, and both reference sets are ID-bound."""
    plan, _context = _trusted_plan("0.03")
    role = plan.roles[0]
    atom = role.holds_atom
    values: dict[str, Any] = {
        "fingerprint": plan.fingerprint,
        "role_key": role.role_key,
        "section": atom.section,
        "canonical_claim": atom.canonical_claim,
        "evidence_refs": atom.evidence_refs,
        "assumption_refs": atom.assumption_refs,
    }
    if change == "fingerprint":
        values["fingerprint"] = "a" * 64
    elif change == "claim":
        values["canonical_claim"] = f"{atom.canonical_claim} Review."
    elif change == "evidence":
        values["evidence_refs"] = atom.evidence_refs[:-1]
    else:
        values["assumption_refs"] = ("asm-002",)
    assert build_semantic_atom_id(**values) != atom.atom_id


def test_does_not_clear_hero_plan_freezes_required_semantics() -> None:
    """The real 3% Hero state creates the approved blocked-review plan."""
    plan, context = _trusted_plan("0.03")
    assert context.scenario.status == "DOES_NOT_CLEAR_BREAK_EVEN"
    executive, _analyst, engineer, sales, manager = plan.roles
    assert "blocked from pilot review" in sales.why_atom.canonical_claim
    assert "asm-002" in sales.verify_atom.assumption_refs
    assert sales.handoff == HandoffPlan(target_role=None, action=None)
    assert "without creating new engineering work" in engineer.holds_atom.canonical_claim
    assert "No new engineering verification" in engineer.verify_atom.canonical_claim
    assert executive.handoff.target_role == "project_manager"
    assert manager.handoff.target_role == "data_analyst"
    assert "0.03" in executive.verify_atom.canonical_claim
    assert context.scenario.break_even_lift in executive.verify_atom.canonical_claim


def test_clears_hero_plan_freezes_required_semantics() -> None:
    """The real 7% state permits review while withholding execution authority."""
    plan, context = _trusted_plan("0.07")
    assert context.scenario.status == "CLEARS_BREAK_EVEN"
    executive, _analyst, engineer, sales, manager = plan.roles
    assert "eligible for pilot review" in sales.why_atom.canonical_claim
    assert "does not authorize execution, outreach, or targeting" in (
        sales.why_atom.canonical_claim
    )
    assert sales.handoff.target_role == "project_manager"
    assert "Limited Pilot Review Candidate" in executive.why_atom.canonical_claim
    assert "does not authorize execution" in executive.why_atom.canonical_claim
    assert "not executing or launching a pilot" in manager.why_atom.canonical_claim
    assert manager.handoff.target_role is None
    assert "without creating new engineering work" in engineer.holds_atom.canonical_claim


def test_evidence_bindings_are_exactly_role_scoped() -> None:
    """Holds atoms bind existing target routing without a new relevance matrix."""
    plan, context = _trusted_plan("0.03")
    targets = {target.role_key: target for target in context.role_targets}
    assert [len(ordered_evidence_refs(role)) for role in plan.roles] == [6, 7, 1, 6, 3]
    for role in plan.roles:
        allowed = tuple(
            item.evidence_id for item in targets[role.role_key].allowed_evidence
        )
        assert role.holds_atom.evidence_refs == allowed
        assert set(ordered_evidence_refs(role)) <= set(allowed)


def test_assumption_bindings_are_known_and_include_required_changes() -> None:
    """Atom assumptions stay inside accepted IDs and retain changed grounding."""
    plan, context = _trusted_plan("0.03")
    accepted = {item.assumption_id for item in context.accepted_assumptions}
    targets = {target.role_key: target for target in context.role_targets}
    for role in plan.roles:
        refs = ordered_assumption_refs(role)
        assert set(refs) <= accepted
        assert set(targets[role.role_key].required_assumption_refs) <= set(refs)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda payload: payload.update({"roles": payload["roles"][:-1]}),
        lambda payload: payload.update(
            {
                "roles": (
                    payload["roles"][0],
                    payload["roles"][0],
                    *payload["roles"][2:],
                )
            }
        ),
        lambda payload: payload.update({"roles": tuple(reversed(payload["roles"]))}),
        lambda payload: payload["roles"][0]["holds_atom"].update(
            {"section": "why_it_matters"}
        ),
        lambda payload: payload["roles"][0]["why_atom"].update(
            {"atom_id": "atom_" + "0" * 64}
        ),
    ],
    ids=[
        "missing-role",
        "duplicate-role",
        "wrong-order",
        "wrong-section",
        "unreproducible-id",
    ],
)
def test_malformed_plan_topology_or_atom_binding_fails(mutate: Any) -> None:
    """Plan shape and source bindings fail before provider construction."""
    plan, _context = _trusted_plan("0.03")
    payload = plan.model_dump()
    mutate(payload)
    with pytest.raises(ValidationError):
        RoleBriefPlanSet.model_validate(payload)


@pytest.mark.parametrize(
    "payload",
    [
        {"target_role": None, "action": "Coordinate review."},
        {"target_role": "executive", "action": None},
        {"target_role": "executive", "action": ""},
        {"target_role": "executive", "action": "none"},
        {"target_role": "legal", "action": "Review."},
    ],
)
def test_malformed_handoff_fails(payload: dict[str, Any]) -> None:
    """Handoff target/action invariants are model-independent."""
    with pytest.raises(ValidationError):
        HandoffPlan.model_validate(payload)


def test_role_irrelevant_evidence_fails_context_validation() -> None:
    """A reproducibly rebound atom still cannot borrow another role's Evidence."""
    plan, context = _trusted_plan("0.03")
    payload = plan.model_dump()
    engineer = payload["roles"][2]
    atom = engineer["why_atom"]
    foreign_ref = context.role_targets[0].allowed_evidence[0].evidence_id
    atom["evidence_refs"] = (foreign_ref,)
    atom["atom_id"] = build_semantic_atom_id(
        fingerprint=plan.fingerprint,
        role_key="data_engineer",
        section="why_it_matters",
        canonical_claim=atom["canonical_claim"],
        evidence_refs=(foreign_ref,),
        assumption_refs=atom["assumption_refs"],
    )
    rebound = RoleBriefPlanSet.model_validate(payload)
    with pytest.raises(ValueError, match="role-irrelevant"):
        validate_role_brief_plan_set(rebound, context)


def test_unknown_assumption_fails_context_validation() -> None:
    """A reproducibly rebound atom still cannot invent an assumption ID."""
    plan, context = _trusted_plan("0.03")
    payload = plan.model_dump()
    analyst = payload["roles"][1]
    atom = analyst["why_atom"]
    atom["assumption_refs"] = ("asm-999",)
    atom["atom_id"] = build_semantic_atom_id(
        fingerprint=plan.fingerprint,
        role_key="data_analyst",
        section="why_it_matters",
        canonical_claim=atom["canonical_claim"],
        evidence_refs=atom["evidence_refs"],
        assumption_refs=("asm-999",),
    )
    rebound = RoleBriefPlanSet.model_validate(payload)
    with pytest.raises(ValueError, match="unknown assumption"):
        validate_role_brief_plan_set(rebound, context)
