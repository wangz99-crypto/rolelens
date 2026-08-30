"""Deterministic semantic plans for bounded Granite role-brief realization.

RoleLens owns every business proposition, governed reference, and handoff in
this module. Granite receives only the semantic source bindings needed to
realize the fifteen approved claims in concise language.
"""

from __future__ import annotations

import hashlib
import json
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.role_impact_brief import (
    ROLE_ORDER,
    ImpactKind,
    RoleBriefGenerationContext,
    RoleKey,
)


SectionKey = Literal[
    "why_it_matters",
    "what_still_holds",
    "what_to_verify_next",
]
SECTION_ORDER: tuple[SectionKey, ...] = (
    "why_it_matters",
    "what_still_holds",
    "what_to_verify_next",
)

_FINGERPRINT_PATTERN = r"^[0-9a-f]{64}$"
_ATOM_ID_PATTERN = r"^atom_[0-9a-f]{64}$"
_ROLE_LABELS: dict[RoleKey, str] = {
    "executive": "Executive",
    "data_analyst": "Data Analyst",
    "data_engineer": "Data Engineer",
    "sales_marketing": "Sales / Marketing",
    "project_manager": "Project Manager",
}


class _PlanContract(BaseModel):
    """Frozen, extra-forbidding base for internal plan contracts."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class SemanticAtom(_PlanContract):
    """One complete RoleLens-approved proposition and its governed refs."""

    atom_id: str = Field(pattern=_ATOM_ID_PATTERN)
    section: SectionKey
    canonical_claim: Annotated[str, Field(min_length=1, max_length=640)]
    evidence_refs: Annotated[tuple[str, ...], Field(max_length=7)]
    assumption_refs: Annotated[tuple[str, ...], Field(max_length=4)]

    @model_validator(mode="after")
    def references_are_unique(self) -> "SemanticAtom":
        """Reject duplicate governed references inside one atom."""
        if len(self.evidence_refs) != len(set(self.evidence_refs)):
            raise ValueError("SemanticAtom Evidence refs must be unique")
        if len(self.assumption_refs) != len(set(self.assumption_refs)):
            raise ValueError("SemanticAtom assumption refs must be unique")
        return self


class HandoffPlan(_PlanContract):
    """One fully deterministic optional cross-role coordination handoff."""

    target_role: RoleKey | None
    action: Annotated[str, Field(min_length=1, max_length=200)] | None

    @model_validator(mode="after")
    def target_and_action_agree(self) -> "HandoffPlan":
        """Require both handoff components together or neither component."""
        if self.target_role is None and self.action is not None:
            raise ValueError("A none handoff cannot contain an action")
        if self.target_role is not None and self.action is None:
            raise ValueError("A handoff target requires an action")
        if self.action is not None:
            if self.action != self.action.strip():
                raise ValueError("Handoff action must be canonical")
            if self.action.lower() == "none":
                raise ValueError("Handoff action cannot be none")
            if "<" in self.action or ">" in self.action:
                raise ValueError("Handoff action must not contain HTML")
        return self


class RoleBriefPlan(_PlanContract):
    """Exactly three governed narrative atoms and one handoff for one role."""

    role_key: RoleKey
    role_state: Annotated[str, Field(min_length=1, max_length=160)]
    impact_kind: ImpactKind
    why_atom: SemanticAtom
    holds_atom: SemanticAtom
    verify_atom: SemanticAtom
    handoff: HandoffPlan

    @model_validator(mode="after")
    def atom_sections_are_exact(self) -> "RoleBriefPlan":
        """Bind each named atom slot to its one canonical section."""
        observed = (
            self.why_atom.section,
            self.holds_atom.section,
            self.verify_atom.section,
        )
        if observed != SECTION_ORDER:
            raise ValueError("RoleBriefPlan atoms must use exact section identity")
        return self


class RoleBriefPlanSet(_PlanContract):
    """The complete deterministic five-role, fifteen-atom semantic plan."""

    fingerprint: str = Field(pattern=_FINGERPRINT_PATTERN)
    roles: Annotated[tuple[RoleBriefPlan, ...], Field(min_length=5, max_length=5)]

    @model_validator(mode="after")
    def topology_and_atom_ids_are_canonical(self) -> "RoleBriefPlanSet":
        """Require stable roles and reproducible state-bound atom IDs."""
        if tuple(role.role_key for role in self.roles) != ROLE_ORDER:
            raise ValueError("RoleBriefPlanSet roles must use canonical order")
        atom_ids: list[str] = []
        for role in self.roles:
            for atom in role_atoms(role):
                expected = build_semantic_atom_id(
                    fingerprint=self.fingerprint,
                    role_key=role.role_key,
                    section=atom.section,
                    canonical_claim=atom.canonical_claim,
                    evidence_refs=atom.evidence_refs,
                    assumption_refs=atom.assumption_refs,
                )
                if atom.atom_id != expected:
                    raise ValueError("SemanticAtom ID is not reproducible")
                atom_ids.append(atom.atom_id)
        if len(atom_ids) != len(set(atom_ids)):
            raise ValueError("SemanticAtom IDs must be unique")
        return self


def build_semantic_atom_id(
    *,
    fingerprint: str,
    role_key: RoleKey,
    section: SectionKey,
    canonical_claim: str,
    evidence_refs: tuple[str, ...],
    assumption_refs: tuple[str, ...],
) -> str:
    """Return a canonical SHA-256 semantic source binding."""
    canonical = json.dumps(
        {
            "assumption_refs": list(assumption_refs),
            "canonical_claim": canonical_claim,
            "evidence_refs": list(evidence_refs),
            "fingerprint": fingerprint,
            "role_key": role_key,
            "section": section,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"atom_{hashlib.sha256(canonical).hexdigest()}"


def role_atoms(role: RoleBriefPlan) -> tuple[SemanticAtom, SemanticAtom, SemanticAtom]:
    """Return one role's atoms in canonical narrative order."""
    return role.why_atom, role.holds_atom, role.verify_atom


def ordered_evidence_refs(role: RoleBriefPlan) -> tuple[str, ...]:
    """Return the stable unique Evidence union across one role's atoms."""
    return _ordered_union(*(atom.evidence_refs for atom in role_atoms(role)))


def ordered_assumption_refs(role: RoleBriefPlan) -> tuple[str, ...]:
    """Return the stable unique assumption union across one role's atoms."""
    return _ordered_union(*(atom.assumption_refs for atom in role_atoms(role)))


def render_handoff(handoff: HandoffPlan) -> str:
    """Render the unchanged human-readable product handoff contract."""
    if handoff.target_role is None:
        return "No additional cross-functional handoff is indicated."
    return f"{_ROLE_LABELS[handoff.target_role]} — {handoff.action}"


def validate_role_brief_plan_set(
    plan: RoleBriefPlanSet,
    context: RoleBriefGenerationContext,
    *,
    expected_fingerprint: str | None = None,
) -> RoleBriefPlanSet:
    """Validate plan semantics against the richer trusted server context."""
    validated = RoleBriefPlanSet.model_validate(plan.model_dump(mode="python"))
    if expected_fingerprint is not None and validated.fingerprint != expected_fingerprint:
        raise ValueError("RoleBriefPlanSet fingerprint is not the accepted state")
    targets = {target.role_key: target for target in context.role_targets}
    accepted_assumption_ids = {
        item.assumption_id for item in context.accepted_assumptions
    }
    for role in validated.roles:
        target = targets[role.role_key]
        if (role.role_state, role.impact_kind) != (target.state, target.impact_kind):
            raise ValueError("RoleBriefPlan role state is inconsistent")
        allowed_evidence_ids = tuple(
            item.evidence_id for item in target.allowed_evidence
        )
        if role.holds_atom.evidence_refs != allowed_evidence_ids:
            raise ValueError("Holds atom must bind all role-routed Evidence")
        for atom in role_atoms(role):
            if any(ref not in allowed_evidence_ids for ref in atom.evidence_refs):
                raise ValueError("SemanticAtom contains role-irrelevant Evidence")
            if any(ref not in accepted_assumption_ids for ref in atom.assumption_refs):
                raise ValueError("SemanticAtom contains an unknown assumption")
        if not set(target.required_assumption_refs).issubset(
            ordered_assumption_refs(role)
        ):
            raise ValueError("RoleBriefPlan omits a required changed assumption")
        if (
            role.handoff.target_role is not None
            and role.handoff.target_role not in target.allowed_handoff_roles
        ):
            raise ValueError("RoleBriefPlan contains an unapproved handoff target")
    return validated


def build_role_brief_plan_set(
    *,
    fingerprint: str,
    context: RoleBriefGenerationContext,
) -> RoleBriefPlanSet:
    """Build the five approved Role Brief meanings from trusted DD-3 context."""
    trusted = RoleBriefGenerationContext.model_validate(
        context.model_dump(mode="python")
    )
    accepted_order = tuple(
        item.assumption_id for item in trusted.accepted_assumptions
    )
    accepted_lift = next(
        item.value
        for item in trusted.accepted_assumptions
        if item.assumption_id == "asm-002"
    )
    changed_ids = tuple(
        item.assumption_id for item in trusted.changed_assumptions
    )
    target_by_key = {target.role_key: target for target in trusted.role_targets}

    roles: list[RoleBriefPlan] = []
    for role_key in ROLE_ORDER:
        target = target_by_key[role_key]
        claims, assumption_groups, handoff = _role_semantics(
            status=trusted.scenario.status,
            role_key=role_key,
            role_state=target.state,
            accepted_lift=accepted_lift,
            break_even_lift=trusted.scenario.break_even_lift,
            changed_ids=changed_ids,
            accepted_order=accepted_order,
        )
        holds_evidence = tuple(
            item.evidence_id for item in target.allowed_evidence
        )
        atoms = tuple(
            _build_atom(
                fingerprint=fingerprint,
                role_key=role_key,
                section=section,
                canonical_claim=claims[index],
                evidence_refs=holds_evidence if section == "what_still_holds" else (),
                assumption_refs=_ordered_from_allowed(
                    accepted_order,
                    (
                        *assumption_groups[index],
                        *(
                            target.required_assumption_refs
                            if section == "why_it_matters"
                            else ()
                        ),
                    ),
                ),
            )
            for index, section in enumerate(SECTION_ORDER)
        )
        roles.append(
            RoleBriefPlan(
                role_key=role_key,
                role_state=target.state,
                impact_kind=target.impact_kind,
                why_atom=atoms[0],
                holds_atom=atoms[1],
                verify_atom=atoms[2],
                handoff=handoff,
            )
        )
    plan = RoleBriefPlanSet(fingerprint=fingerprint, roles=tuple(roles))
    return validate_role_brief_plan_set(
        plan,
        trusted,
        expected_fingerprint=fingerprint,
    )


def _build_atom(
    *,
    fingerprint: str,
    role_key: RoleKey,
    section: SectionKey,
    canonical_claim: str,
    evidence_refs: tuple[str, ...],
    assumption_refs: tuple[str, ...],
) -> SemanticAtom:
    """Construct one atom with its reproducible semantic source binding."""
    return SemanticAtom(
        atom_id=build_semantic_atom_id(
            fingerprint=fingerprint,
            role_key=role_key,
            section=section,
            canonical_claim=canonical_claim,
            evidence_refs=evidence_refs,
            assumption_refs=assumption_refs,
        ),
        section=section,
        canonical_claim=canonical_claim,
        evidence_refs=evidence_refs,
        assumption_refs=assumption_refs,
    )


def _ordered_union(*groups: tuple[str, ...]) -> tuple[str, ...]:
    """Return first-seen unique strings across ordered groups."""
    seen: set[str] = set()
    result: list[str] = []
    for group in groups:
        for item in group:
            if item not in seen:
                seen.add(item)
                result.append(item)
    return tuple(result)


def _ordered_from_allowed(
    allowed_order: tuple[str, ...],
    requested: tuple[str, ...],
) -> tuple[str, ...]:
    """Project requested governed IDs into their canonical accepted order."""
    requested_set = set(requested)
    return tuple(item for item in allowed_order if item in requested_set)


def _role_semantics(
    *,
    status: str,
    role_key: RoleKey,
    role_state: str,
    accepted_lift: str,
    break_even_lift: str,
    changed_ids: tuple[str, ...],
    accepted_order: tuple[str, ...],
) -> tuple[
    tuple[str, str, str],
    tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]],
    HandoffPlan,
]:
    """Return frozen claims, their assumption bindings, and handoff."""
    if status == "DOES_NOT_CLEAR_BREAK_EVEN":
        return _does_not_clear_semantics(
            role_key=role_key,
            accepted_lift=accepted_lift,
            break_even_lift=break_even_lift,
            changed_ids=changed_ids,
        )
    if status == "CLEARS_BREAK_EVEN":
        return _clears_semantics(
            role_key=role_key,
            accepted_lift=accepted_lift,
            break_even_lift=break_even_lift,
            changed_ids=changed_ids,
            accepted_order=accepted_order,
        )
    return _not_evaluable_semantics(
        role_key=role_key,
        role_state=role_state,
        accepted_order=accepted_order,
    )


def _does_not_clear_semantics(
    *,
    role_key: RoleKey,
    accepted_lift: str,
    break_even_lift: str,
    changed_ids: tuple[str, ...],
) -> tuple[
    tuple[str, str, str],
    tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]],
    HandoffPlan,
]:
    """Return frozen semantics for a scenario below modeled break-even."""
    semantics = {
        "executive": (
            (
                "The current trusted scenario does not clear modeled break-even, so the Executive posture is Validate Scenario Assumptions First.",
                "Governed churn Evidence and the governed data foundation remain unchanged by this scenario revision.",
                f"Recheck accepted assumption asm-002, expected incremental lift {accepted_lift}, against modeled break-even lift {break_even_lift}.",
            ),
            (changed_ids, (), ("asm-002",)),
            HandoffPlan(
                target_role="project_manager",
                action="Coordinate scenario review around asm-002.",
            ),
        ),
        "data_analyst": (
            (
                "The Decision change is driven by accepted scenario assumptions, not by a change in observed Evidence."
                if changed_ids
                else "The current Decision state uses accepted scenario assumptions while governed observed Evidence remains separate.",
                "Governed churn Evidence remains available and unchanged.",
                "Keep asm-002 explicitly treated as an accepted assumption rather than observed Evidence.",
            ),
            (changed_ids, (), ("asm-002",)),
            HandoffPlan(target_role=None, action=None),
        ),
        "data_engineer": (
            (
                "This revision does not change the governed data foundation.",
                "The known TotalCharges parseability limitation remains documented without creating new engineering work in this revision.",
                "No new engineering verification is triggered by this scenario revision.",
            ),
            ((), (), ()),
            HandoffPlan(target_role=None, action=None),
        ),
        "sales_marketing": (
            (
                "The current trusted scenario does not clear modeled break-even, so Sales / Marketing remains blocked from pilot review.",
                "Governed churn Evidence remains unchanged; the block comes from the current trusted scenario rather than a new data issue.",
                f"Recheck accepted assumption asm-002, expected incremental lift {accepted_lift}, against modeled break-even lift {break_even_lift}. This does not authorize outreach or targeting.",
            ),
            (changed_ids, (), ("asm-002",)),
            HandoffPlan(target_role=None, action=None),
        ),
        "project_manager": (
            (
                "The current scenario status requires renewed cross-functional review of the accepted lift assumption.",
                "Governed Evidence and the governed data foundation remain unchanged by this scenario revision.",
                "Coordinate review of accepted assumption asm-002 before further pilot review.",
            ),
            (changed_ids, (), ("asm-002",)),
            HandoffPlan(
                target_role="data_analyst",
                action=(
                    "Recheck the accepted lift assumption as an assumption without "
                    "modifying governed Evidence."
                ),
            ),
        ),
    }
    return semantics[role_key]


def _clears_semantics(
    *,
    role_key: RoleKey,
    accepted_lift: str,
    break_even_lift: str,
    changed_ids: tuple[str, ...],
    accepted_order: tuple[str, ...],
) -> tuple[
    tuple[str, str, str],
    tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]],
    HandoffPlan,
]:
    """Return frozen semantics for a scenario clearing modeled break-even."""
    semantics = {
        "executive": (
            (
                "The current trusted scenario clears modeled break-even, so the Executive posture is Limited Pilot Review Candidate. This does not authorize execution.",
                "Governed churn Evidence and the governed data foundation remain in force.",
                f"Keep accepted assumption asm-002, expected incremental lift {accepted_lift}, visible against modeled break-even lift {break_even_lift} during review.",
            ),
            (changed_ids, (), ("asm-002",)),
            HandoffPlan(
                target_role="project_manager",
                action="Coordinate limited pilot review using the current trusted scenario.",
            ),
        ),
        "data_analyst": (
            (
                "The accepted scenario changed while governed observed Evidence remained unchanged."
                if changed_ids
                else "The current Decision uses accepted scenario assumptions while governed observed Evidence remains separate.",
                "Governed churn Evidence remains available and unchanged.",
                "Keep accepted scenario assumptions explicitly separated from observed Evidence during review.",
            ),
            (changed_ids, (), accepted_order),
            HandoffPlan(target_role=None, action=None),
        ),
        "data_engineer": (
            (
                "The current scenario result does not create a change to the governed data foundation.",
                "The known TotalCharges parseability limitation remains documented without creating new engineering work.",
                "No new engineering verification is triggered by this scenario result.",
            ),
            ((), (), ()),
            HandoffPlan(target_role=None, action=None),
        ),
        "sales_marketing": (
            (
                "The current trusted scenario clears modeled break-even, so Sales / Marketing is eligible for pilot review. Eligibility does not authorize execution, outreach, or targeting.",
                "The same governed churn Evidence and governed data foundation remain in force.",
                "Keep accepted assumption asm-002 visible during pilot review; eligibility for review is not execution authority.",
            ),
            (changed_ids, (), ("asm-002",)),
            HandoffPlan(
                target_role="project_manager",
                action="Coordinate limited pilot review using the current trusted scenario.",
            ),
        ),
        "project_manager": (
            (
                "The current trusted scenario supports preparing a limited pilot review, not executing or launching a pilot.",
                "Governed Evidence and the governed data foundation remain unchanged.",
                "Coordinate review using the current accepted assumptions and trusted scenario state.",
            ),
            (changed_ids, (), accepted_order),
            HandoffPlan(target_role=None, action=None),
        ),
    }
    return semantics[role_key]


def _not_evaluable_semantics(
    *,
    role_key: RoleKey,
    role_state: str,
    accepted_order: tuple[str, ...],
) -> tuple[
    tuple[str, str, str],
    tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]],
    HandoffPlan,
]:
    """Return conservative semantics for an unevaluable trusted scenario."""
    label = _ROLE_LABELS[role_key]
    claims = (
        f"The trusted scenario is not evaluable, so the {label} posture remains {role_state}.",
        "Governed Evidence and the governed data foundation remain unchanged.",
        "Review the accepted scenario assumptions without changing governed Evidence.",
    )
    return claims, ((), (), accepted_order), HandoffPlan(
        target_role=None,
        action=None,
    )
