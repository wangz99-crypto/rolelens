"""Deterministic authority and grounding tests for Slice 4 role briefs."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from app.role_impact_brief import (
    ROLE_ORDER,
    AcceptedAssumptionContext,
    AcceptedRevisionContext,
    ChangedAssumptionContext,
    DecisionIdentityContext,
    FoundationStateContext,
    GovernedEvidenceContext,
    RoleBriefGenerationContext,
    RoleImpactBrief,
    RoleImpactBriefSet,
    RoleImpactBriefValidationError,
    TrustedRoleStateContext,
    TrustedScenarioContext,
    build_role_brief_targets,
    validate_role_impact_brief_set,
)


def _context() -> RoleBriefGenerationContext:
    """Return one trusted Hero context with a real changed lift assumption."""
    changed_assumptions = (
        ChangedAssumptionContext(
            assumption_id="asm-002", before_value="0.08", after_value="0.03"
        ),
    )
    role_states = (
        TrustedRoleStateContext(
            role_key="executive", state="Validate assumptions first", impact_kind="changed"
        ),
        TrustedRoleStateContext(
            role_key="data_analyst", state="Evidence basis remains valid", impact_kind="unchanged"
        ),
        TrustedRoleStateContext(
            role_key="data_engineer", state="Data foundation remains valid", impact_kind="unchanged"
        ),
        TrustedRoleStateContext(
            role_key="sales_marketing", state="Blocked by scenario", impact_kind="blocked"
        ),
        TrustedRoleStateContext(
            role_key="project_manager", state="Reopen scenario validation", impact_kind="changed"
        ),
    )
    governed_evidence = tuple(
        GovernedEvidenceContext(
            evidence_id=f"ev-{index}",
            label=f"Evidence {index}",
            finding="A bounded descriptive association was recorded.",
            scope="internal_observation",
            limitations=("The association does not establish causation.",),
            relevant_roles=ROLE_ORDER,
        )
        for index in range(1, 8)
    )
    return RoleBriefGenerationContext(
        decision=DecisionIdentityContext(
            decision_id="dec-001",
            title="Customer Retention Pilot",
            business_question="Should a limited pilot remain under review?",
        ),
        revision=AcceptedRevisionContext(
            revision_id="rev-002", label="Human revision"
        ),
        scenario=TrustedScenarioContext(
            status="DOES_NOT_CLEAR_BREAK_EVEN",
            expected_incremental_retained="15",
            expected_scenario_value="7500",
            intervention_cost="15000",
            net_scenario_value="-7500",
            break_even_lift="0.06",
            currency="USD",
        ),
        accepted_assumptions=(
            AcceptedAssumptionContext(
                assumption_id="asm-001",
                label="Pilot population",
                value="500",
                unit="customers",
                currency=None,
            ),
            AcceptedAssumptionContext(
                assumption_id="asm-002",
                label="Expected lift",
                value="0.03",
                unit="fraction",
                currency=None,
            ),
            AcceptedAssumptionContext(
                assumption_id="asm-003",
                label="Cost / intervention",
                value="30",
                unit="currency_per_customer",
                currency="USD",
            ),
            AcceptedAssumptionContext(
                assumption_id="asm-004",
                label="Retained value",
                value="500",
                unit="currency_per_customer",
                currency="USD",
            ),
        ),
        changed_assumptions=changed_assumptions,
        role_states=role_states,
        role_targets=build_role_brief_targets(
            role_states,
            governed_evidence,
            changed_assumptions,
        ),
        governed_evidence=governed_evidence,
        foundation=FoundationStateContext(
            observed_evidence="unchanged",
            data_health="unchanged",
            source_provenance="unchanged",
        ),
    )


def _brief(role_key: str, **overrides: Any) -> RoleImpactBrief:
    """Build one concise valid brief with optional field overrides."""
    payload: dict[str, Any] = {
        "role_key": role_key,
        "why_it_matters": "The trusted scenario posture requires bounded review.",
        "what_still_holds": "Observed Evidence and the checked data foundation remain unchanged.",
        "what_to_verify_next": "Recheck the accepted expected-lift assumption.",
        "evidence_refs": ("ev-1",),
        "assumption_refs": ("asm-002",),
        "next_handoff": "Data Analyst — Coordinate the next review with Project Manager.",
    }
    payload.update(overrides)
    return RoleImpactBrief.model_validate(payload)


def _brief_set(**role_overrides: dict[str, Any]) -> RoleImpactBriefSet:
    """Build a complete stable brief set."""
    return RoleImpactBriefSet(
        briefs=tuple(
            _brief(role, **role_overrides.get(role, {})) for role in ROLE_ORDER
        )
    )


def test_exact_five_valid_roles_pass() -> None:
    """The only accepted topology is all five roles in stable order."""
    result = validate_role_impact_brief_set(_brief_set(), _context())
    assert tuple(item.role_key for item in result.briefs) == ROLE_ORDER


def test_role_targets_are_exact_ordered_and_derived_from_governed_evidence() -> None:
    """Every generation target is a complete deterministic policy projection."""
    context = _context()
    assert tuple(item.role_key for item in context.role_targets) == ROLE_ORDER
    for target in context.role_targets:
        assert tuple(item.evidence_id for item in target.allowed_evidence) == tuple(
            item.evidence_id
            for item in context.governed_evidence
            if target.role_key in item.relevant_roles
        )
        expected_required = (
            ("asm-002",)
            if target.impact_kind in {"changed", "blocked", "recomputed"}
            else ()
        )
        assert target.required_assumption_refs == expected_required
        assert target.allowed_handoff_roles == ROLE_ORDER


@pytest.mark.parametrize(
    "mutate",
    [
        lambda payload: payload.update(
            {"role_targets": tuple(reversed(payload["role_targets"]))}
        ),
        lambda payload: payload.update(
            {"role_targets": payload["role_targets"][:-1]}
        ),
        lambda payload: payload["role_targets"][0].update(
            {
                "allowed_evidence": (
                    *payload["role_targets"][0]["allowed_evidence"],
                    payload["role_targets"][0]["allowed_evidence"][0],
                )
            }
        ),
        lambda payload: payload["role_targets"][0]["allowed_evidence"][0].update(
            {"evidence_id": "ev-unknown"}
        ),
        lambda payload: payload["governed_evidence"][0].update(
            {"relevant_roles": ["data_analyst"]}
        ),
        lambda payload: payload["role_targets"][0].update(
            {"required_assumption_refs": []}
        ),
        lambda payload: payload["role_targets"][1].update(
            {"required_assumption_refs": ["asm-002"]}
        ),
        lambda payload: payload["role_targets"][0].update(
            {"allowed_handoff_roles": ["legal"]}
        ),
    ],
    ids=[
        "wrong-order",
        "missing-target",
        "duplicate-evidence",
        "unknown-evidence",
        "role-irrelevant-evidence",
        "missing-required-assumption",
        "fabricated-required-assumption",
        "unapproved-handoff-role",
    ],
)
def test_inconsistent_role_target_context_fails_closed(mutate: Any) -> None:
    """Malformed routing cannot enter the provider generation boundary."""
    payload = _context().model_dump()
    mutate(payload)
    with pytest.raises(ValidationError):
        RoleBriefGenerationContext.model_validate(payload)


@pytest.mark.parametrize(
    "briefs",
    [
        lambda: tuple(_brief(role) for role in reversed(ROLE_ORDER)),
        lambda: tuple(_brief(role) for role in ROLE_ORDER[:-1]),
        lambda: tuple(_brief(role) for role in (*ROLE_ORDER[:-1], "executive")),
        lambda: tuple(_brief(role) for role in (*ROLE_ORDER, "executive")),
    ],
    ids=["wrong-order", "missing-role", "duplicate-role", "extra-role"],
)
def test_invalid_role_topologies_fail(briefs: Any) -> None:
    """Wrong order, missing, duplicate, and sixth roles fail closed."""
    with pytest.raises(ValidationError):
        RoleImpactBriefSet(briefs=briefs())


def test_unknown_role_fails_before_brief_set_validation() -> None:
    """A fabricated sixth function cannot enter even one brief contract."""
    with pytest.raises(ValidationError):
        _brief("legal")


def test_unknown_evidence_ref_fails() -> None:
    """A syntactically plausible but unexposed Evidence ID is rejected."""
    brief_set = _brief_set(executive={"evidence_refs": ("ev-unknown",)})
    with pytest.raises(RoleImpactBriefValidationError, match="unknown Evidence"):
        validate_role_impact_brief_set(brief_set, _context())


def test_role_irrelevant_evidence_ref_fails() -> None:
    """A valid Evidence ID cannot be attached to an irrelevant role."""
    base = _context()
    context_payload = base.model_dump()
    context_payload["governed_evidence"][0]["relevant_roles"] = ("data_analyst",)
    governed_evidence = tuple(
        GovernedEvidenceContext.model_validate(item)
        for item in context_payload["governed_evidence"]
    )
    context_payload["role_targets"] = [
        item.model_dump()
        for item in build_role_brief_targets(
            base.role_states,
            governed_evidence,
            base.changed_assumptions,
        )
    ]
    context = RoleBriefGenerationContext.model_validate(context_payload)
    with pytest.raises(RoleImpactBriefValidationError, match="irrelevant"):
        validate_role_impact_brief_set(_brief_set(), context)


def test_unknown_assumption_ref_fails() -> None:
    """Fabricated assumption IDs are rejected before product output."""
    brief_set = _brief_set(executive={"assumption_refs": ("asm-999",)})
    with pytest.raises(RoleImpactBriefValidationError, match="unknown assumption"):
        validate_role_impact_brief_set(brief_set, _context())


def test_scenario_impact_role_must_cite_real_changed_assumption() -> None:
    """Changed, blocked, and recomputed roles must cite a real changed input."""
    brief_set = _brief_set(sales_marketing={"assumption_refs": ("asm-003",)})
    with pytest.raises(RoleImpactBriefValidationError, match="changed assumption"):
        validate_role_impact_brief_set(brief_set, _context())


@pytest.mark.parametrize(
    "unsafe_text",
    [
        "The pilot is approved.",
        "Sales is authorized to proceed.",
        "Tech support causes churn.",
        "These customers will churn.",
        "Target month-to-month customers.",
        "Contact high-risk customers.",
        "Granite changed the decision state.",
        "ROI will be positive.",
        "The analyst has completed validation.",
        "Engineering should deploy by Friday.",
        "Legal should own the next review.",
        "Jordan owns the review.",
        "Send outreach to month-to-month customers.",
        "Prioritize month-to-month customers for retention.",
        "Focus retention efforts on month-to-month accounts.",
        "Direct retention efforts toward fiber customers.",
        "Month-to-month customers have a higher chance of churning.",
        "These subscribers are more likely to churn.",
        "This segment has elevated churn risk.",
        "Tech support is a key driver of churn.",
        "Lack of tech support is responsible for churn.",
        "Contract type drives customer churn.",
    ],
)
def test_prohibited_claims_fail_closed(unsafe_text: str) -> None:
    """Authority, causation, prediction, targeting, and invention all fail."""
    brief_set = _brief_set(executive={"why_it_matters": unsafe_text})
    with pytest.raises(RoleImpactBriefValidationError, match="prohibited"):
        validate_role_impact_brief_set(brief_set, _context())


_REAL_GRANITE_APPROVAL_GATE = (
    "Wait for executive approval after data validation before planning any "
    "outreach or targeting."
)


@pytest.mark.parametrize(
    "field",
    [
        "why_it_matters",
        "what_still_holds",
        "what_to_verify_next",
        "next_handoff",
    ],
)
def test_real_granite_approval_gate_fails_in_every_narrative_field(
    field: str,
) -> None:
    """Authority gates fail across the entire model-authored brief surface."""
    value = (
        f"Data Analyst — {_REAL_GRANITE_APPROVAL_GATE}"
        if field == "next_handoff"
        else _REAL_GRANITE_APPROVAL_GATE
    )
    brief_set = _brief_set(sales_marketing={field: value})
    with pytest.raises(RoleImpactBriefValidationError, match="prohibited"):
        validate_role_impact_brief_set(brief_set, _context())


@pytest.mark.parametrize(
    "unsafe_text",
    [
        "Executive approval is required.",
        "Manager approval is required.",
        "Leadership approval is required.",
        "The next step requires approval.",
        "Await approval before continuing.",
        "Wait for approval before continuing.",
        "Obtain approval before continuing.",
        "Seek approval before continuing.",
        "The next step needs authorization.",
        "The next step must be authorized.",
        "Continue after approval.",
        "The review is pending approval.",
        "Wait for the Executive to approve the pilot.",
        "Project Manager must authorize the next step.",
        "Sales may proceed after leadership approval.",
        "Data Analyst approval is required before outreach.",
    ],
)
def test_invented_approval_and_authorization_gates_fail(unsafe_text: str) -> None:
    """No RoleLens role or generic authority may become an invented approver."""
    brief_set = _brief_set(executive={"why_it_matters": unsafe_text})
    with pytest.raises(RoleImpactBriefValidationError, match="prohibited"):
        validate_role_impact_brief_set(brief_set, _context())


@pytest.mark.parametrize(
    "safe_text",
    [
        "Granite does not authorize execution.",
        "No approval is implied by this brief.",
        "This brief does not grant authorization.",
    ],
)
def test_negated_authority_language_remains_allowed(safe_text: str) -> None:
    """The shared local-negation mechanism preserves explicit non-authority."""
    brief_set = _brief_set(executive={"why_it_matters": safe_text})
    assert validate_role_impact_brief_set(brief_set, _context()) == brief_set


@pytest.mark.parametrize(
    "safe_text",
    [
        "Reopen scenario validation.",
        "Review the accepted lift assumption.",
        "Verify the accepted scenario inputs.",
        "Coordinate the next review.",
        "Wait for the revised scenario to be accepted.",
    ],
)
def test_review_verify_and_validation_language_remains_allowed(
    safe_text: str,
) -> None:
    """Review and acceptance are not mistaken for approval authority."""
    brief_set = _brief_set(executive={"what_to_verify_next": safe_text})
    assert validate_role_impact_brief_set(brief_set, _context()) == brief_set


def test_blocked_sales_safe_nearby_outreach_control_passes() -> None:
    """Planning remains conditional without inventing an approval gate."""
    safe_text = (
        "Recheck the accepted lift assumption before planning any outreach or "
        "targeting."
    )
    brief_set = _brief_set(sales_marketing={"what_to_verify_next": safe_text})
    assert validate_role_impact_brief_set(brief_set, _context()) == brief_set


def test_blocked_sales_cannot_be_reversed() -> None:
    """Granite cannot make blocked Sales eligible to proceed."""
    brief_set = _brief_set(
        sales_marketing={"why_it_matters": "Proceed with the pilot outreach."}
    )
    with pytest.raises(RoleImpactBriefValidationError, match="blocked Sales"):
        validate_role_impact_brief_set(brief_set, _context())


def test_blocked_sales_cannot_be_called_eligible_to_proceed() -> None:
    """The exact prohibited posture reversal fails without financial wording."""
    brief_set = _brief_set(
        sales_marketing={"why_it_matters": "Sales is eligible to proceed."}
    )
    with pytest.raises(RoleImpactBriefValidationError, match="blocked Sales"):
        validate_role_impact_brief_set(brief_set, _context())


@pytest.mark.parametrize(
    "safe_text",
    [
        "Sales should not proceed with outreach.",
        "Sales is not eligible to proceed.",
        "Sales should not begin outreach.",
    ],
)
def test_explicitly_negated_blocked_sales_language_passes(safe_text: str) -> None:
    """The shared local-negation rule preserves clear governance language."""
    brief_set = _brief_set(sales_marketing={"why_it_matters": safe_text})
    assert validate_role_impact_brief_set(brief_set, _context()) == brief_set


@pytest.mark.parametrize(
    "unsafe_text",
    [
        "Sales is eligible to proceed.",
        "Sales can proceed with the pilot.",
        "Sales can move forward with outreach.",
        "Sales may initiate outreach.",
        "Sales can start the campaign.",
    ],
)
def test_positive_blocked_sales_reversals_fail(unsafe_text: str) -> None:
    """Natural positive posture reversals remain prohibited."""
    brief_set = _brief_set(sales_marketing={"why_it_matters": unsafe_text})
    with pytest.raises(RoleImpactBriefValidationError, match="blocked Sales"):
        validate_role_impact_brief_set(brief_set, _context())


@pytest.mark.parametrize(
    "safe_text",
    [
        "The sample shows a higher recorded churn rate for month-to-month contracts.",
        "The observed association does not establish causation.",
    ],
)
def test_safe_descriptive_association_language_passes(safe_text: str) -> None:
    """Recorded descriptive differences remain available without causal claims."""
    brief_set = _brief_set(data_analyst={"why_it_matters": safe_text})
    assert validate_role_impact_brief_set(brief_set, _context()) == brief_set


@pytest.mark.parametrize(
    "unsafe_text",
    [
        "Revise the observed evidence to reflect the 3% lift.",
        "Use the expected-lift assumption as evidence of retention improvement.",
    ],
)
def test_data_analyst_cannot_rewrite_evidence_or_promote_assumptions(
    unsafe_text: str,
) -> None:
    """Analyst interpretation preserves observed Evidence/assumption separation."""
    brief_set = _brief_set(data_analyst={"what_to_verify_next": unsafe_text})
    with pytest.raises(RoleImpactBriefValidationError, match="Data Analyst"):
        validate_role_impact_brief_set(brief_set, _context())


@pytest.mark.parametrize(
    "safe_text",
    [
        "The expected-lift assumption changed, while observed Evidence remains unchanged.",
        "Recheck the assumption without rewriting observed Evidence.",
    ],
)
def test_data_analyst_safe_separation_language_passes(safe_text: str) -> None:
    """Analyst may explain changes without changing the Evidence layer."""
    brief_set = _brief_set(data_analyst={"what_still_holds": safe_text})
    assert validate_role_impact_brief_set(brief_set, _context()) == brief_set


@pytest.mark.parametrize(
    "unsafe_text",
    [
        "Deploy a pipeline because the lift changed.",
        "Rebuild ETL because lift changed.",
        "Change the schema for the revised scenario.",
        "Modify ingestion to reflect the new lift.",
        "Migrate data for the scenario revision.",
        "Alter the data model after recalculation.",
    ],
)
def test_data_engineer_cannot_invent_technical_work(unsafe_text: str) -> None:
    """Unchanged foundation state cannot imply pipeline or schema work."""
    brief_set = _brief_set(data_engineer={"why_it_matters": unsafe_text})
    with pytest.raises(RoleImpactBriefValidationError, match="Data Engineer"):
        validate_role_impact_brief_set(brief_set, _context())


@pytest.mark.parametrize(
    "safe_text",
    [
        "No pipeline change is indicated by the accepted scenario revision.",
        "Data Health and source provenance remain unchanged.",
    ],
)
def test_data_engineer_safe_foundation_language_passes(safe_text: str) -> None:
    """Negative technical-work language and unchanged foundation language pass."""
    brief_set = _brief_set(data_engineer={"what_still_holds": safe_text})
    assert validate_role_impact_brief_set(brief_set, _context()) == brief_set


@pytest.mark.parametrize(
    "handoff",
    [
        "Project Manager — Review pilot financials",
        "Data Engineer — Confirm assumptions with data engineer",
        "Data Analyst — Validate TotalCharges parsing",
        "No additional cross-functional handoff is indicated.",
        "Data Analyst — Reopen scenario validation",
    ],
)
def test_live_granite_handoffs_pass_canonical_validation(handoff: str) -> None:
    """Every observed live handoff passes without capitalization guessing."""
    brief_set = _brief_set(executive={"next_handoff": handoff})
    assert validate_role_impact_brief_set(brief_set, _context()) == brief_set


@pytest.mark.parametrize(
    "handoff",
    [
        "Reopen scenario validation with Data Analyst.",
        "Customer Success — Reopen scenario validation.",
        "Data Analyst and Customer Success — Reopen scenario validation.",
        "Data Analyst —",
        "No additional cross-functional handoff is indicated",
    ],
)
def test_handoff_requires_exact_approved_prefix_and_controlled_none(
    handoff: str,
) -> None:
    """An approved role mention away from the canonical prefix is insufficient."""
    brief_set = _brief_set(executive={"next_handoff": handoff})
    with pytest.raises(RoleImpactBriefValidationError, match="next_handoff"):
        validate_role_impact_brief_set(brief_set, _context())


@pytest.mark.parametrize(
    "function_name",
    [
        "Customer Success",
        "Legal",
        "Finance",
        "HR",
        "Compliance",
        "Engineering Manager",
        "Account Management",
        "Revenue Strategy",
        "Retention Team",
    ],
)
def test_handoff_rejects_every_fabricated_function(function_name: str) -> None:
    """Mentioning an approved role cannot smuggle in a sixth function."""
    brief_set = _brief_set(
        executive={
            "next_handoff": f"Executive — Coordinate with {function_name}."
        }
    )
    with pytest.raises(RoleImpactBriefValidationError, match="unapproved"):
        validate_role_impact_brief_set(brief_set, _context())


def test_safe_bounded_negative_language_passes() -> None:
    """Explicit governance language is not mistaken for an authority claim."""
    brief_set = _brief_set(
        sales_marketing={
            "why_it_matters": "The modeled scenario does not clear break-even, so outreach must not begin.",
            "what_still_holds": "Observed Evidence remains unchanged and does not authorize targeting.",
            "what_to_verify_next": "Recheck the expected-lift assumption before reopening pilot review.",
            "next_handoff": "Data Analyst — Recheck the assumption while Sales remains blocked.",
        }
    )
    assert validate_role_impact_brief_set(brief_set, _context()) == brief_set
