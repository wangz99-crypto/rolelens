"""Offline contract tests for the experimental RoleLens DD-3 adapter.

Exactly 10 top-level test functions. No external service is used.
"""

from __future__ import annotations

import ast
import json
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.decision_diff import ScenarioAssumption, ScenarioStatus
from app.decision_diff_engine import DecisionImpactType
from app.decision_diff_rolelens import (
    EvidenceInvariantSnapshot,
    ExecutiveScenarioPosture,
    ProjectManagerHandoff,
    RoleLensDecisionDiffError,
    RoleLensDecisionRevision,
    RoleLensEvidenceBasis,
    SalesPilotPosture,
    ScenarioDecisionProjection,
    build_rolelens_decision_revision,
)
from app.demo_pipeline import PreparedDemoInputs, prepare_demo_inputs
from app.schemas import EvidenceObject, EvidenceScope, EvidenceStatus, SourceScope


_ROOT = Path(__file__).parent.parent
_PUBLIC_CSV = _ROOT / "sample_data" / "public" / "ibm_telco_customer_churn.csv"
_EVIDENCE_TYPES = (
    "business_overall_churn",
    "business_contract_churn",
    "business_support_churn",
    "business_internet_churn",
    "business_payment_churn",
    "business_churn_medians",
    "business_parseability",
)
_EXPECTED_HERO_IMPACTS = {
    "obj-observed-evidence": DecisionImpactType.UNCHANGED,
    "obj-data-health": DecisionImpactType.UNCHANGED,
    "obj-source-provenance": DecisionImpactType.UNCHANGED,
    "obj-break-even": DecisionImpactType.RECOMPUTED,
    "obj-executive-posture": DecisionImpactType.RECOMPUTED,
    "obj-sales-posture": DecisionImpactType.BLOCKED,
    "obj-pm-handoff": DecisionImpactType.RECOMPUTED,
    "obj-decision-brief": DecisionImpactType.STALE,
}


@pytest.fixture(scope="module")
def prepared() -> PreparedDemoInputs:
    """Prepare the real public IBM Telco inputs through the current pipeline."""
    return prepare_demo_inputs(
        csv_bytes=_PUBLIC_CSV.read_bytes(),
        filename=_PUBLIC_CSV.name,
        industry_context="Public fictional context; not company-specific evidence.",
        strategy_profile="Validate a limited retention pilot before outreach.",
        business_question="Is a limited validation pilot supportable?",
        decision_goal="Review aggregate patterns and control boundaries.",
        user_assumption="Contract patterns may be associated with churn.",
        business_profile_id="ibm_telco_churn_v1",
    )


def _assumptions(
    revision_id: str,
    *,
    lift: str = "0.08",
    currency: str | None = "USD",
) -> tuple[ScenarioAssumption, ...]:
    """Return the four Hero assumptions with stable logical IDs."""
    return (
        ScenarioAssumption(
            assumption_id="asm-001",
            revision_id=revision_id,
            key="pilot_population",
            value=Decimal("500"),
            unit="customers",
            currency=None,
        ),
        ScenarioAssumption(
            assumption_id="asm-002",
            revision_id=revision_id,
            key="expected_incremental_lift",
            value=Decimal(lift),
            unit="fraction",
            currency=None,
        ),
        ScenarioAssumption(
            assumption_id="asm-003",
            revision_id=revision_id,
            key="cost_per_intervention",
            value=Decimal("30"),
            unit="currency_per_customer",
            currency=currency,
        ),
        ScenarioAssumption(
            assumption_id="asm-004",
            revision_id=revision_id,
            key="retained_customer_value",
            value=Decimal("500"),
            unit="currency_per_customer",
            currency=currency,
        ),
    )


def _kwargs(prepared: PreparedDemoInputs) -> dict[str, object]:
    """Return the fixed observed product context for one DD-3 build."""
    assert prepared.business_profile is not None
    return {
        "business_profile": prepared.business_profile,
        "evidence_objects": prepared.evidence_objects,
        "data_health_summary": prepared.data_health_summary,
        "source_manifests": prepared.source_manifests,
        "scenario_id": "scn-001",
        "before_revision_id": "rev-001",
        "after_revision_id": "rev-002",
    }


def _build(
    prepared: PreparedDemoInputs,
    *,
    after_lift: str = "0.03",
    currency: str | None = "USD",
    reverse: bool = False,
) -> RoleLensDecisionRevision:
    """Build the standard DD-3 Hero or one of its controls."""
    before = _assumptions("rev-001", currency=currency)
    after = _assumptions("rev-002", lift=after_lift, currency=currency)
    if reverse:
        before = tuple(reversed(before))
        after = tuple(reversed(after))
    return build_rolelens_decision_revision(
        **_kwargs(prepared),
        before_assumptions=before,
        after_assumptions=after,
    )


def _canonical(model: object) -> str:
    """Return the exact canonical JSON format required by DD-3."""
    return json.dumps(
        model.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def _product_snapshot(prepared: PreparedDemoInputs) -> str:
    """Return byte-comparable JSON for every caller product input."""
    assert prepared.business_profile is not None
    return json.dumps(
        {
            "business_profile": prepared.business_profile.model_dump(mode="json"),
            "evidence_objects": [
                item.model_dump(mode="json") for item in prepared.evidence_objects
            ],
            "data_health_summary": prepared.data_health_summary.model_dump(mode="json"),
            "source_manifests": [
                item.model_dump(mode="json") for item in prepared.source_manifests
            ],
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def _replace_evidence(
    prepared: PreparedDemoInputs,
    evidence_type: str,
    replacement: EvidenceObject,
) -> tuple[EvidenceObject, ...]:
    """Replace exactly one business EvidenceObject in the test input sequence."""
    return tuple(
        replacement if item.evidence_type == evidence_type else item
        for item in prepared.evidence_objects
    )


def test_public_contracts_are_frozen_extra_forbidding_and_reject_inconsistent_postures(
    prepared: PreparedDemoInputs,
) -> None:
    """All DD-3 models lock state and enforce exact scenario/posture pairing."""
    revision = _build(prepared)
    models = (
        revision.evidence_basis.business_evidence[0],
        revision.evidence_basis,
        revision.before_projection,
        revision,
    )
    for model in models:
        with pytest.raises(ValidationError):
            model.model_validate({**model.model_dump(), "unexpected": True})
        with pytest.raises(ValidationError):
            model.__setattr__(next(iter(model.model_fields)), "changed")

    inconsistent = {
        **revision.before_projection.model_dump(),
        "executive_posture": (
            ExecutiveScenarioPosture.VALIDATE_SCENARIO_ASSUMPTIONS_FIRST
        ),
    }
    with pytest.raises(ValidationError):
        ScenarioDecisionProjection.model_validate(inconsistent)
    with pytest.raises(ValidationError):
        RoleLensDecisionRevision.model_validate(
            {
                **revision.model_dump(),
                "unchanged_evidence_ids": tuple(
                    reversed(revision.unchanged_evidence_ids)
                ),
            }
        )


def test_real_telco_basis_has_exact_seven_ordered_complete_evidence_snapshots(
    prepared: PreparedDemoInputs,
) -> None:
    """The real current business Evidence is captured completely and canonically."""
    revision = _build(prepared)
    basis = revision.evidence_basis
    assert isinstance(basis, RoleLensEvidenceBasis)
    assert basis.profile_id == "ibm_telco_churn_v1"
    assert basis.dataset_name == "IBM Telco Customer Churn"
    assert len(basis.business_evidence) == 7
    assert tuple(item.evidence_type for item in basis.business_evidence) == (
        _EVIDENCE_TYPES
    )
    originals = {item.evidence_type: item for item in prepared.evidence_objects}
    for snapshot in basis.business_evidence:
        assert isinstance(snapshot, EvidenceInvariantSnapshot)
        original = originals[snapshot.evidence_type]
        assert snapshot.snapshot_json == _canonical(original)
        assert json.loads(snapshot.snapshot_json) == original.model_dump(mode="json")
        assert snapshot.evidence_id == original.evidence_id
        assert snapshot.identity_digest == original.identity_digest
        assert snapshot.source_id == original.source_id == basis.data_source_id
        assert snapshot.finding == original.finding
    assert basis.data_health_snapshot_json == _canonical(
        prepared.data_health_summary
    )
    matching_manifest = next(
        item
        for item in prepared.source_manifests
        if item.source_id == basis.data_source_id
    )
    assert basis.source_manifest_snapshot_json == _canonical(matching_manifest)


def test_basis_excludes_context_assumption_priority_and_health_evidence(
    prepared: PreparedDemoInputs,
) -> None:
    """Non-business Evidence remains present upstream but absent from the basis."""
    basis = _build(prepared).evidence_basis
    full = prepared.evidence_objects
    assert any(item.evidence_scope is EvidenceScope.external_context for item in full)
    assert any(item.evidence_scope is EvidenceScope.stated_priority for item in full)
    assert any(item.evidence_scope is EvidenceScope.assumption for item in full)
    health_evidence = {
        item.evidence_id
        for item in full
        if item.source_id == prepared.data_health_summary.source_id
        and item.evidence_type not in _EVIDENCE_TYPES
    }
    assert health_evidence
    basis_ids = {item.evidence_id for item in basis.business_evidence}
    excluded_ids = {
        item.evidence_id
        for item in full
        if item.evidence_scope
        in {
            EvidenceScope.external_context,
            EvidenceScope.stated_priority,
            EvidenceScope.assumption,
        }
        or item.evidence_id in health_evidence
    }
    assert basis_ids.isdisjoint(excluded_ids)
    assert tuple(item.evidence_type for item in basis.business_evidence) == (
        _EVIDENCE_TYPES
    )


def test_hero_eight_to_three_has_exact_arithmetic_postures_and_impact_map(
    prepared: PreparedDemoInputs,
) -> None:
    """The Hero revision bridges exact DD-1 results to exact DD-2 impacts."""
    revision = _build(prepared, after_lift="0.03")
    before = revision.before_projection
    after = revision.after_projection
    assert before.scenario_result.expected_incremental_retained == Decimal("40.00")
    assert before.scenario_result.expected_scenario_value == Decimal("20000.00")
    assert before.scenario_result.intervention_cost == Decimal("15000")
    assert before.scenario_result.net_scenario_value == Decimal("5000.00")
    assert before.scenario_result.break_even_lift == Decimal("0.06")
    assert before.scenario_result.status is ScenarioStatus.CLEARS_BREAK_EVEN
    assert after.scenario_result.expected_incremental_retained == Decimal("15.00")
    assert after.scenario_result.expected_scenario_value == Decimal("7500.00")
    assert after.scenario_result.intervention_cost == Decimal("15000")
    assert after.scenario_result.net_scenario_value == Decimal("-7500.00")
    assert after.scenario_result.break_even_lift == Decimal("0.06")
    assert after.scenario_result.status is ScenarioStatus.DOES_NOT_CLEAR_BREAK_EVEN
    assert before.executive_posture is (
        ExecutiveScenarioPosture.LIMITED_PILOT_REVIEW_CANDIDATE
    )
    assert before.sales_posture is SalesPilotPosture.ELIGIBLE_FOR_PILOT_REVIEW
    assert before.project_manager_handoff is (
        ProjectManagerHandoff.PREPARE_LIMITED_PILOT_REVIEW
    )
    assert after.executive_posture is (
        ExecutiveScenarioPosture.VALIDATE_SCENARIO_ASSUMPTIONS_FIRST
    )
    assert after.sales_posture is SalesPilotPosture.BLOCKED_BY_SCENARIO
    assert after.project_manager_handoff is (
        ProjectManagerHandoff.REOPEN_SCENARIO_VALIDATION
    )
    impacts = {
        item.object_id: item.impact_type for item in revision.decision_diff.impacts
    }
    assert impacts == _EXPECTED_HERO_IMPACTS


def test_eight_to_seven_stays_candidate_path_but_recomputes_dependents(
    prepared: PreparedDemoInputs,
) -> None:
    """A still-clearing revision recomputes Sales rather than blocking it."""
    revision = _build(prepared, after_lift="0.07")
    after = revision.after_projection
    assert after.scenario_result.net_scenario_value == Decimal("2500.00")
    assert after.scenario_result.status is ScenarioStatus.CLEARS_BREAK_EVEN
    assert after.executive_posture is (
        ExecutiveScenarioPosture.LIMITED_PILOT_REVIEW_CANDIDATE
    )
    assert after.sales_posture is SalesPilotPosture.ELIGIBLE_FOR_PILOT_REVIEW
    assert after.project_manager_handoff is (
        ProjectManagerHandoff.PREPARE_LIMITED_PILOT_REVIEW
    )
    impacts = {
        item.object_id: item.impact_type for item in revision.decision_diff.impacts
    }
    assert impacts == {
        **_EXPECTED_HERO_IMPACTS,
        "obj-sales-posture": DecisionImpactType.RECOMPUTED,
    }


def test_identical_values_keep_postures_and_every_impact_unchanged(
    prepared: PreparedDemoInputs,
) -> None:
    """Different revision IDs alone do not create logical changes."""
    revision = _build(prepared, after_lift="0.08")
    assert revision.decision_diff.changed_assumptions == ()
    assert all(
        item.impact_type is DecisionImpactType.UNCHANGED
        and item.trigger_refs == ()
        for item in revision.decision_diff.impacts
    )
    before = revision.before_projection.model_dump(mode="json")
    after = revision.after_projection.model_dump(mode="json")
    before.pop("revision_id")
    after.pop("revision_id")
    before["scenario_result"].pop("revision_id")
    after["scenario_result"].pop("revision_id")
    assert before == after
    assert revision.unchanged_evidence_ids == tuple(
        item.evidence_id for item in revision.evidence_basis.business_evidence
    )


def test_all_product_inputs_and_full_evidence_fields_remain_invariant(
    prepared: PreparedDemoInputs,
) -> None:
    """The adapter leaves every caller product model byte-for-byte unchanged."""
    before = _product_snapshot(prepared)
    revision = _build(prepared)
    after = _product_snapshot(prepared)
    assert before == after
    originals = {item.evidence_id: item for item in prepared.evidence_objects}
    for snapshot in revision.evidence_basis.business_evidence:
        original = originals[snapshot.evidence_id]
        restored = EvidenceObject.model_validate(json.loads(snapshot.snapshot_json))
        assert restored == original
        assert restored.finding == original.finding
        assert restored.limitations == original.limitations
        assert restored.source_id == original.source_id
        assert restored.source_locator == original.source_locator
        assert restored.evidence_scope == original.evidence_scope
        assert restored.identity_digest == original.identity_digest
        assert restored.status == original.status
    assert revision.unchanged_evidence_ids == tuple(
        item.evidence_id for item in revision.evidence_basis.business_evidence
    )


def test_invalid_product_contexts_fail_closed_with_controlled_errors(
    prepared: PreparedDemoInputs,
) -> None:
    """Profile, Evidence, source, and health ambiguity never pass silently."""
    base = _kwargs(prepared)
    before = _assumptions("rev-001")
    after = _assumptions("rev-002", lift="0.03")
    assert prepared.business_profile is not None
    business = {
        item.evidence_type: item
        for item in prepared.evidence_objects
        if item.evidence_type in _EVIDENCE_TYPES
    }
    other_source_id = next(
        item.source_id
        for item in prepared.source_manifests
        if item.source_id != prepared.data_health_summary.source_id
    )
    data_manifest = next(
        item
        for item in prepared.source_manifests
        if item.source_id == prepared.data_health_summary.source_id
    )

    cases: list[dict[str, object]] = []
    cases.append({"business_profile": None})
    cases.append(
        {
            "business_profile": prepared.business_profile.model_copy(
                update={"profile_id": "unsupported_profile"}
            )
        }
    )
    cases.append(
        {
            "evidence_objects": tuple(
                item
                for item in prepared.evidence_objects
                if item.evidence_type != "business_parseability"
            )
        }
    )
    cases.append(
        {
            "evidence_objects": prepared.evidence_objects
            + (
                business["business_overall_churn"].model_copy(
                    update={
                        "evidence_id": "ev-test-000000000001",
                        "identity_digest": "f" * 64,
                    }
                ),
            )
        }
    )
    inactive = business["business_overall_churn"].model_copy(
        update={
            "status": EvidenceStatus.invalidated,
            "invalidated_reason": "Test invalidation.",
        }
    )
    cases.append(
        {
            "evidence_objects": _replace_evidence(
                prepared,
                "business_overall_churn",
                inactive,
            )
        }
    )
    for scope in (EvidenceScope.external_context, EvidenceScope.assumption):
        cases.append(
            {
                "evidence_objects": _replace_evidence(
                    prepared,
                    "business_overall_churn",
                    business["business_overall_churn"].model_copy(
                        update={"evidence_scope": scope}
                    ),
                )
            }
        )
    cases.append(
        {
            "evidence_objects": _replace_evidence(
                prepared,
                "business_overall_churn",
                business["business_overall_churn"].model_copy(
                    update={"extraction_method": "llm_assisted"}
                ),
            )
        }
    )
    cases.append(
        {
            "evidence_objects": _replace_evidence(
                prepared,
                "business_overall_churn",
                business["business_overall_churn"].model_copy(
                    update={"source_id": other_source_id}
                ),
            )
        }
    )
    cases.append(
        {
            "data_health_summary": prepared.data_health_summary.model_copy(
                update={"source_id": other_source_id}
            )
        }
    )
    cases.append(
        {
            "source_manifests": tuple(
                item
                for item in prepared.source_manifests
                if item.source_id != data_manifest.source_id
            )
        }
    )
    cases.append(
        {
            "source_manifests": tuple(
                data_manifest.model_copy(update={"source_scope": SourceScope.external_context})
                if item.source_id == data_manifest.source_id
                else item
                for item in prepared.source_manifests
            )
        }
    )
    cases.append({"source_manifests": prepared.source_manifests + (data_manifest,)})

    for update in cases:
        with pytest.raises(RoleLensDecisionDiffError) as error:
            build_rolelens_decision_revision(
                **{**base, **update},
                before_assumptions=before,
                after_assumptions=after,
            )
        message = str(error.value)
        assert message
        assert "errors.pydantic.dev" not in message
        assert "EvidenceObject(" not in message
        assert "BusinessDatasetProfile(" not in message


def test_scenario_assumptions_stay_separate_order_independent_and_do_not_infer_currency(
    prepared: PreparedDemoInputs,
) -> None:
    """Assumption revisions never enter Evidence or borrow dataset currency."""
    usd = _build(prepared)
    reversed_inputs = _build(prepared, reverse=True)
    assert usd == reversed_inputs
    assert all(
        isinstance(item, EvidenceInvariantSnapshot)
        and not item.evidence_id.startswith("asm-")
        for item in usd.evidence_basis.business_evidence
    )
    assert not any(
        isinstance(item, ScenarioAssumption)
        for item in usd.evidence_basis.business_evidence
    )
    assert any(
        item.evidence_scope is EvidenceScope.assumption
        for item in prepared.evidence_objects
    )
    assert all(
        json.loads(item.snapshot_json)["evidence_scope"] != "assumption"
        for item in usd.evidence_basis.business_evidence
    )
    assert usd.notices[2] == (
        "Scenario currency USD is user-supplied and is not inferred from the IBM "
        "Telco dataset."
    )

    no_currency = _build(prepared, currency=None)
    assert no_currency.before_projection.scenario_result.currency is None
    assert no_currency.after_projection.scenario_result.currency is None
    assert no_currency.notices[2] == (
        "No scenario currency was supplied; the IBM Telco dataset currency remains "
        "unspecified."
    )


def test_production_module_is_import_and_side_effect_bounded() -> None:
    """The adapter uses only approved modules and trusted DD-2 construction."""
    module_path = _ROOT / "app" / "decision_diff_rolelens.py"
    source = module_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    imports.update(
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    )
    assert imports <= {
        "__future__",
        "json",
        "collections.abc",
        "enum",
        "typing",
        "pydantic",
        "app.decision_diff",
        "app.decision_diff_engine",
        "app.business_profile",
        "app.schemas",
    }
    forbidden = (
        "app.demo_pipeline",
        "app.product_view",
        "app.main",
        "app.role_engine",
        "app.risk_checker",
        "app.semantic_risk_reviewer",
        "app.workflow_planner",
        "app.human_review",
        "app.memo_generator",
        "granite",
        "provider",
        "streamlit",
        "os.environ",
        "socket",
        "requests",
        "httpx",
        "urllib",
        "time",
        "datetime",
        "uuid",
        "random",
        "pathlib",
        "open(",
    )
    assert not any(term in source.lower() for term in forbidden)
    imported_names = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }
    assert "calculate_break_even_scenario" not in imported_names
    calls = [
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    ]
    assert calls.count("build_decision_diff") == 1
    assert "DecisionDiff" not in calls
    function_names = {
        node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
    }
    assert "_propagate_impacts" not in function_names
    assert "calculate_break_even_scenario" not in function_names
    assert "expected_scenario_value =" not in source
    assert "break_even_lift =" not in source
    assert not any(name == "evidence_builder" for name in calls)
    test_tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    tests = [
        node
        for node in test_tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test_")
    ]
    assert len(tests) == 10
