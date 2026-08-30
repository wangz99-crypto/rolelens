"""Focused safety and contract tests for the Slice 1 and Slice 2 product API."""

from __future__ import annotations

import ast
import importlib
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app import product_api
from app.role_brief_plan import (
    RoleBriefPlanSet,
    ordered_assumption_refs,
    ordered_evidence_refs,
    render_handoff,
)
from app.role_impact_brief import (
    ROLE_ORDER,
    RoleBriefGenerationContext,
    RoleImpactBrief,
    RoleImpactBriefSet,
)


_ROOT = Path(__file__).parent.parent
_API_PATH = _ROOT / "app" / "product_api.py"
_EXPECTED_EVIDENCE_TYPES = {
    "business_overall_churn",
    "business_contract_churn",
    "business_support_churn",
    "business_internet_churn",
    "business_payment_churn",
    "business_churn_medians",
    "business_parseability",
}
_BASELINE_REQUEST = {
    "pilot_population": 500,
    "expected_incremental_lift": 0.08,
    "cost_per_intervention": 30,
    "retained_customer_value": 500,
    "currency": "USD",
}


def _post_revision(**updates: Any) -> Any:
    """POST one complete scenario request with selected value updates."""
    return TestClient(product_api.app).post(
        "/api/demo/decision/recalculate",
        json={**_BASELINE_REQUEST, **updates},
    )


def _post_role_brief(**updates: Any) -> Any:
    """POST accepted scenario assumptions to the stateless role-brief endpoint."""
    return TestClient(product_api.app).post(
        "/api/demo/decision/role-brief",
        json={**_BASELINE_REQUEST, **updates},
    )


def _valid_briefs(
    plan: RoleBriefPlanSet,
    context: RoleBriefGenerationContext,
) -> RoleImpactBriefSet:
    """Realize canonical plan claims through the offline provider seam."""
    briefs = []
    assert tuple(role.role_key for role in plan.roles) == ROLE_ORDER
    assert tuple(target.role_key for target in context.role_targets) == ROLE_ORDER
    for role in plan.roles:
        briefs.append(
            RoleImpactBrief(
                role_key=role.role_key,
                why_it_matters=role.why_atom.canonical_claim,
                what_still_holds=role.holds_atom.canonical_claim,
                what_to_verify_next=role.verify_atom.canonical_claim,
                evidence_refs=ordered_evidence_refs(role),
                assumption_refs=ordered_assumption_refs(role),
                next_handoff=render_handoff(role.handoff),
            )
        )
    return RoleImpactBriefSet(briefs=tuple(briefs))


class _FakeRoleBriefProvider:
    """Offline provider seam recording trusted plans and richer contexts."""

    model_id = "ibm/granite-offline-test"

    def __init__(self) -> None:
        self.plans: list[RoleBriefPlanSet] = []
        self.contexts: list[RoleBriefGenerationContext] = []

    def generate(
        self,
        plan: RoleBriefPlanSet,
        context: RoleBriefGenerationContext,
    ) -> RoleImpactBriefSet:
        """Record one call and return a context-grounded valid brief set."""
        self.plans.append(plan)
        self.contexts.append(context)
        return _valid_briefs(plan, context)


@pytest.fixture(scope="module")
def payload() -> dict[str, Any]:
    """Load the real frozen demo once for response assertions."""
    response = TestClient(product_api.app).get("/api/demo/decision")
    assert response.status_code == 200
    return response.json()


def test_normal_import_has_no_file_network_or_provider_side_effects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Import exposes the app without preparing data or constructing providers."""
    calls: list[tuple[Any, ...]] = []

    def forbidden(*args: Any, **kwargs: Any) -> None:
        calls.append((args, kwargs))
        raise AssertionError("import performed a forbidden side effect")

    monkeypatch.setattr(Path, "read_bytes", forbidden)
    monkeypatch.setattr(Path, "read_text", forbidden)
    module = sys.modules.pop("app.product_api")
    try:
        imported = importlib.import_module("app.product_api")
        assert imported.app.title == "RoleLens Product API"
        assert calls == []
    finally:
        sys.modules["app.product_api"] = module


def test_health_returns_status_ok() -> None:
    """The liveness endpoint returns only its frozen status contract."""
    response = TestClient(product_api.app).get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_demo_uses_frozen_sample_and_exact_profile_values(
    payload: dict[str, Any],
) -> None:
    """The response reflects the real IBM public sample and sidecar context."""
    context = __import__("json").loads(
        (
            _ROOT
            / "sample_data"
            / "public"
            / "ibm_telco_customer_churn_context.json"
        ).read_text(encoding="utf-8")
    )
    assert payload["decision"]["business_question"] == context["business_question"]
    assert payload["decision"]["source_label"] == "IBM Telco"
    assert payload["evidence"] == {
        "status": "LOCKED",
        "governed_evidence_count": 7,
        "customer_count": 7043,
        "recorded_churn_rate_pct": 26.54,
        "month_to_month_churn_rate_pct": 42.71,
        "total_charges_parse_issue_count": 11,
        "data_health_checked": True,
        "source_provenance_locked": True,
    }


def test_exactly_seven_business_evidence_types_are_selected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Selection contains exactly one approved type from the Data Health source."""
    real_prepare = product_api.prepare_demo_inputs
    observed: dict[str, Any] = {}

    def recording_prepare(*args: Any, **kwargs: Any) -> Any:
        prepared = real_prepare(*args, **kwargs)
        source_id = prepared.data_health_summary.source_id
        selected = [
            evidence
            for evidence in prepared.evidence_objects
            if evidence.evidence_type in _EXPECTED_EVIDENCE_TYPES
            and evidence.status.value == "active"
        ]
        observed["types"] = [item.evidence_type for item in selected]
        observed["source_ids"] = [item.source_id for item in selected]
        observed["health_source_id"] = source_id
        return prepared

    monkeypatch.setattr(product_api, "prepare_demo_inputs", recording_prepare)
    response = TestClient(product_api.app).get("/api/demo/decision")
    assert response.status_code == 200
    assert len(observed["types"]) == 7
    assert set(observed["types"]) == _EXPECTED_EVIDENCE_TYPES
    assert len(set(observed["types"])) == 7
    assert set(observed["source_ids"]) == {observed["health_source_id"]}


def test_dd1_calculator_is_called_exactly_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One request performs exactly one calculation through the existing DD-1."""
    real_calculator = product_api.calculate_break_even_scenario
    calls = 0

    def recording_calculator(*args: Any, **kwargs: Any) -> Any:
        nonlocal calls
        calls += 1
        return real_calculator(*args, **kwargs)

    monkeypatch.setattr(
        product_api, "calculate_break_even_scenario", recording_calculator
    )
    response = TestClient(product_api.app).get("/api/demo/decision")
    assert response.status_code == 200
    assert calls == 1


def test_exact_baseline_scenario(payload: dict[str, Any]) -> None:
    """The API surfaces the exact existing 8% DD-1 result."""
    assert payload["scenario"] == {
        "scenario_id": "scn-001",
        "status": "CLEARS_BREAK_EVEN",
        "expected_incremental_retained": 40.0,
        "expected_scenario_value": 20000.0,
        "intervention_cost": 15000.0,
        "net_scenario_value": 5000.0,
        "break_even_lift": 0.06,
        "currency": "USD",
    }


def test_four_ordered_human_assumptions(payload: dict[str, Any]) -> None:
    """Only the four ordered caller-supplied assumptions are returned."""
    assumptions = payload["assumptions"]
    assert [item["assumption_id"] for item in assumptions] == [
        "asm-001",
        "asm-002",
        "asm-003",
        "asm-004",
    ]
    assert [item["key"] for item in assumptions] == [
        "pilot_population",
        "expected_incremental_lift",
        "cost_per_intervention",
        "retained_customer_value",
    ]
    assert [item["value"] for item in assumptions] == [500.0, 0.08, 30.0, 500.0]
    assert all(item["source_scope"] == "user_assumption" for item in assumptions)


def test_five_frozen_baseline_role_nodes(payload: dict[str, Any]) -> None:
    """The exact five presentation-only role states are returned in fixed order."""
    assert payload["roles"] == [
        {
            "role_key": "executive",
            "label": "Executive",
            "baseline_state": "Pilot review candidate",
            "state_kind": "current",
        },
        {
            "role_key": "data_analyst",
            "label": "Data Analyst",
            "baseline_state": "Evidence basis valid",
            "state_kind": "foundation",
        },
        {
            "role_key": "data_engineer",
            "label": "Data Engineer",
            "baseline_state": "Data foundation valid",
            "state_kind": "foundation",
        },
        {
            "role_key": "sales_marketing",
            "label": "Sales / Marketing",
            "baseline_state": "Eligible for pilot review",
            "state_kind": "current",
        },
        {
            "role_key": "project_manager",
            "label": "Project Manager",
            "baseline_state": "Prepare limited pilot review",
            "state_kind": "current",
        },
    ]


def test_api_has_no_forbidden_integration_imports() -> None:
    """The thin API does not connect later-slice engines or provider paths."""
    tree = ast.parse(_API_PATH.read_text(encoding="utf-8"))
    imports = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    forbidden_fragments = {
        "streamlit",
        "main",
        "decision_lab",
        "decision_workspace",
        "role_engine",
        "workflow_planner",
        "human_review",
        "memo_generator",
        "semantic_risk_reviewer",
        "granite",
    }
    assert not any(
        fragment in imported
        for imported in imports
        for fragment in forbidden_fragments
    )


def test_response_does_not_leak_internal_evidence_fields(
    payload: dict[str, Any],
) -> None:
    """Evidence identity and provenance internals remain outside Slice 1."""
    serialized = __import__("json").dumps(payload)
    for forbidden in ("evidence_id", "identity_digest", "source_locator"):
        assert forbidden not in serialized


def test_safe_error_response_contains_no_internal_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unexpected preparation failures are replaced by one controlled message."""
    secret = "raw,row,contents\nsecret-customer,https://errors.pydantic.dev/traceback"

    def failing_prepare(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError(secret)

    monkeypatch.setattr(product_api, "prepare_demo_inputs", failing_prepare)
    response = TestClient(product_api.app, raise_server_exceptions=False).get(
        "/api/demo/decision"
    )
    assert response.status_code == 503
    assert response.json() == {"detail": product_api._PRODUCT_ERROR}
    assert secret not in response.text
    assert "traceback" not in response.text.lower()
    assert "pydantic" not in response.text.lower()


def test_hero_post_calls_dd3_once_and_returns_exact_trusted_diff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The 8% to 3% Hero runs once through DD-3 and returns bounded truth."""
    real_builder = product_api.build_rolelens_decision_revision
    calls = 0

    def recording_builder(*args: Any, **kwargs: Any) -> Any:
        nonlocal calls
        calls += 1
        return real_builder(*args, **kwargs)

    monkeypatch.setattr(
        product_api,
        "build_rolelens_decision_revision",
        recording_builder,
    )
    response = _post_revision(expected_incremental_lift=0.03)
    assert response.status_code == 200
    assert calls == 1
    result = response.json()
    assert result["revision"] == {
        "revision_id": "rev-002",
        "label": "Human revision",
    }
    assert result["before_scenario"] == {
        "scenario_id": "scn-001",
        "status": "CLEARS_BREAK_EVEN",
        "expected_incremental_retained": 40.0,
        "expected_scenario_value": 20000.0,
        "intervention_cost": 15000.0,
        "net_scenario_value": 5000.0,
        "break_even_lift": 0.06,
        "currency": "USD",
    }
    assert result["scenario"] == {
        "scenario_id": "scn-001",
        "status": "DOES_NOT_CLEAR_BREAK_EVEN",
        "expected_incremental_retained": 15.0,
        "expected_scenario_value": 7500.0,
        "intervention_cost": 15000.0,
        "net_scenario_value": -7500.0,
        "break_even_lift": 0.06,
        "currency": "USD",
    }
    assert result["diff"] == {
        "kind": "decision_posture_changed",
        "headline": "Decision posture changed",
        "changed_assumptions": [
            {
                "assumption_id": "asm-002",
                "key": "expected_incremental_lift",
                "label": "Expected lift",
                "before_value": 0.08,
                "after_value": 0.03,
                "unit": "fraction",
                "currency": None,
            }
        ],
        "scenario_status_changed": True,
        "role_posture_changed": True,
        "observed_evidence_unchanged": True,
    }
    assert "ai_brief" not in result


def test_hero_role_states_and_foundation_invariants_are_exact() -> None:
    """Hero roles and unchanged product foundations come only from DD-3."""
    response = _post_revision(expected_incremental_lift=0.03)
    assert response.status_code == 200
    result = response.json()
    assert result["roles"] == [
        {"role_key": "executive", "label": "Executive", "state": "Validate assumptions first", "impact_kind": "changed"},
        {"role_key": "data_analyst", "label": "Data Analyst", "state": "Evidence basis remains valid", "impact_kind": "unchanged"},
        {"role_key": "data_engineer", "label": "Data Engineer", "state": "Data foundation remains valid", "impact_kind": "unchanged"},
        {"role_key": "sales_marketing", "label": "Sales / Marketing", "state": "Blocked by scenario", "impact_kind": "blocked"},
        {"role_key": "project_manager", "label": "Project Manager", "state": "Reopen scenario validation", "impact_kind": "changed"},
    ]
    evidence = result["evidence"]
    assert evidence["governed_evidence_count"] == 7
    assert evidence["observed_evidence_unchanged"] is True
    assert evidence["data_health_unchanged"] is True
    assert evidence["source_provenance_unchanged"] is True


def test_seven_percent_recomputes_without_blocking_roles() -> None:
    """A changed but clearing scenario keeps postures and marks recomputation."""
    response = _post_revision(expected_incremental_lift=0.07)
    assert response.status_code == 200
    result = response.json()
    assert result["scenario"]["net_scenario_value"] == 2500.0
    assert result["scenario"]["status"] == "CLEARS_BREAK_EVEN"
    assert result["diff"]["kind"] == "scenario_changed"
    assert result["diff"]["headline"] == (
        "Scenario changed; decision posture remains the same"
    )
    roles = {item["role_key"]: item for item in result["roles"]}
    assert roles["executive"]["impact_kind"] == "recomputed"
    assert roles["sales_marketing"]["impact_kind"] == "recomputed"
    assert roles["project_manager"]["impact_kind"] == "recomputed"
    assert roles["data_analyst"]["impact_kind"] == "unchanged"
    assert roles["data_engineer"]["impact_kind"] == "unchanged"
    assert roles["sales_marketing"]["state"] == "Eligible for pilot review"


def test_decimal_string_lift_reaches_dd3_as_exact_decimal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The React decimal string is preserved exactly at the DD-3 boundary."""
    real_builder = product_api.build_rolelens_decision_revision
    received: dict[str, Decimal] = {}

    def recording_builder(*args: Any, **kwargs: Any) -> Any:
        after_assumptions = kwargs["after_assumptions"]
        received["lift"] = after_assumptions[1].value
        return real_builder(*args, **kwargs)

    monkeypatch.setattr(
        product_api,
        "build_rolelens_decision_revision",
        recording_builder,
    )
    response = _post_revision(expected_incremental_lift="0.333")
    assert response.status_code == 200
    assert received["lift"] == Decimal("0.333")


def test_logical_baseline_request_returns_no_change_control() -> None:
    """Equal logical values produce no changes and no user-facing revision."""
    response = _post_revision()
    assert response.status_code == 200
    result = response.json()
    assert result["revision"] == {"revision_id": "rev-001", "label": "Baseline"}
    assert result["diff"]["kind"] == "no_change"
    assert result["diff"]["headline"] == "No scenario assumption changed"
    assert result["diff"]["changed_assumptions"] == []
    assert all(role["impact_kind"] == "unchanged" for role in result["roles"])


def test_non_lift_assumption_propagates_generically() -> None:
    """Changing intervention cost uses the same trusted propagation path."""
    response = _post_revision(cost_per_intervention=35)
    assert response.status_code == 200
    result = response.json()
    assert result["scenario"]["net_scenario_value"] == 2500.0
    assert result["scenario"]["status"] == "CLEARS_BREAK_EVEN"
    assert result["diff"]["kind"] == "scenario_changed"
    assert result["diff"]["changed_assumptions"] == [
        {
            "assumption_id": "asm-003",
            "key": "cost_per_intervention",
            "label": "Cost / intervention",
            "before_value": 30.0,
            "after_value": 35.0,
            "unit": "currency_per_customer",
            "currency": "USD",
        }
    ]


@pytest.mark.parametrize(
    "update",
    [
        {"pilot_population": 0},
        {"cost_per_intervention": -1},
        {"retained_customer_value": 0},
        {"expected_incremental_lift": 1.01},
        {"currency": "EUR"},
        {"unexpected": "raw internal value"},
    ],
)
def test_invalid_recalculation_inputs_fail_with_bounded_error(
    update: dict[str, Any],
) -> None:
    """Shape and authoritative assumption failures never expose diagnostics."""
    response = _post_revision(**update)
    assert response.status_code == 422
    assert response.json() == {"detail": product_api._INVALID_ASSUMPTIONS_ERROR}
    assert "pydantic" not in response.text.lower()
    assert "traceback" not in response.text.lower()
    assert "raw internal value" not in response.text.lower()


def test_post_uses_only_dd3_entry_and_leaks_no_internal_snapshots(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST does not call the imported GET calculator or expose DD internals."""
    def forbidden_calculator(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("POST called DD-1 directly")

    monkeypatch.setattr(
        product_api,
        "calculate_break_even_scenario",
        forbidden_calculator,
    )
    response = _post_revision(expected_incremental_lift=0.03)
    assert response.status_code == 200
    serialized = response.text.lower()
    for forbidden in (
        "snapshot_json",
        "identity_digest",
        "evidence_id",
        "trigger_refs",
        "obj-break-even",
        "traceback",
        "pydantic",
    ):
        assert forbidden not in serialized


def test_evidence_detail_endpoint_returns_exact_real_ordered_projection() -> None:
    """The depth endpoint is an exact bounded view of seven real Evidence Objects."""
    context = product_api._prepare_product_context()
    response = TestClient(product_api.app).get("/api/demo/decision/evidence")
    assert response.status_code == 200
    result = response.json()
    assert [item["evidence_type"] for item in result] == list(
        product_api._BUSINESS_EVIDENCE_TYPES
    )
    assert len(result) == 7
    for detail, evidence in zip(result, context.business_evidence, strict=True):
        assert detail == {
            "evidence_id": evidence.evidence_id,
            "evidence_type": evidence.evidence_type,
            "label": product_api._EVIDENCE_LABELS[evidence.evidence_type],
            "finding": evidence.finding,
            "confidence": evidence.confidence,
            "extraction_method": evidence.extraction_method,
            "scope": evidence.evidence_scope.value,
            "source_label": "IBM Telco public demo",
            "limitations": evidence.limitations,
            "relevant_roles": evidence.relevant_roles,
        }


def test_evidence_detail_endpoint_excludes_unapproved_and_internal_fields() -> None:
    """Depth exposes product fields, never other scopes or provenance internals."""
    response = TestClient(product_api.app).get("/api/demo/decision/evidence")
    assert response.status_code == 200
    result = response.json()
    assert all(item["scope"] == "internal_observation" for item in result)
    assert all(item["evidence_type"] in _EXPECTED_EVIDENCE_TYPES for item in result)
    serialized = response.text.lower()
    for forbidden in (
        "identity_digest",
        "source_locator",
        "source_manifest",
        "snapshot_json",
        "supporting_evidence",
        "canonical_rule",
        "external_context",
        '"assumption"',
        '"health',
    ):
        assert forbidden not in serialized


def test_evidence_detail_failure_is_sanitized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Evidence preparation failures retain no raw source or diagnostic text."""
    secret = "secret source_locator snapshot_json https://errors.pydantic.dev"

    def failing_context() -> None:
        raise RuntimeError(secret)

    monkeypatch.setattr(product_api, "_prepare_product_context", failing_context)
    response = TestClient(product_api.app, raise_server_exceptions=False).get(
        "/api/demo/decision/evidence"
    )
    assert response.status_code == 503
    assert response.json() == {"detail": product_api._EVIDENCE_ERROR}
    assert secret not in response.text
    assert "traceback" not in response.text.lower()
    assert "pydantic" not in response.text.lower()


def test_unexpected_recalculation_failure_is_sanitized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unexpected DD-3 failures retain no payload or internal exception text."""
    def failing_builder(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("secret snapshot_json https://errors.pydantic.dev")

    monkeypatch.setattr(
        product_api,
        "build_rolelens_decision_revision",
        failing_builder,
    )
    response = _post_revision(expected_incremental_lift=0.03)
    assert response.status_code == 503
    assert response.json() == {"detail": product_api._RECALCULATION_ERROR}
    assert "secret" not in response.text.lower()
    assert "pydantic" not in response.text.lower()


def test_baseline_fingerprint_is_stable_and_full_sha256() -> None:
    """Repeated baseline reconstruction produces one stable accepted identity."""
    client = TestClient(product_api.app)
    first = client.get("/api/demo/decision").json()["accepted_state_fingerprint"]
    second = client.get("/api/demo/decision").json()["accepted_state_fingerprint"]
    assert first == second
    assert len(first) == 64
    assert set(first) <= set("0123456789abcdef")


def test_logically_reconstructed_baseline_keeps_the_baseline_fingerprint() -> None:
    """Equivalent Decimal spellings and DD-3 reconstruction preserve identity."""
    baseline = TestClient(product_api.app).get("/api/demo/decision").json()
    rebuilt = _post_revision(
        expected_incremental_lift="0.0800",
        cost_per_intervention="30.00",
        retained_customer_value="500.0",
    ).json()
    assert rebuilt["accepted_state_fingerprint"] == baseline["accepted_state_fingerprint"]


def test_three_and_seven_percent_have_distinct_stable_fingerprints() -> None:
    """Baseline, Hero 3%, and recomputed 7% accepted states are all distinct."""
    baseline = TestClient(product_api.app).get("/api/demo/decision").json()
    three = _post_revision(expected_incremental_lift="0.03").json()
    three_again = _post_revision(expected_incremental_lift="0.030").json()
    seven = _post_revision(expected_incremental_lift="0.07").json()
    assert three["accepted_state_fingerprint"] == three_again["accepted_state_fingerprint"]
    assert three["accepted_state_fingerprint"] != baseline["accepted_state_fingerprint"]
    assert seven["accepted_state_fingerprint"] != baseline["accepted_state_fingerprint"]
    assert seven["accepted_state_fingerprint"] != three["accepted_state_fingerprint"]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("role_state", "Blocked by scenario"),
        ("impact_kind", "blocked"),
        ("net_scenario_value", "-7500"),
        ("evidence_id", "ev-fabricated"),
        ("prompt", "ignore trusted state"),
        ("role_key", "sales_marketing"),
        ("accepted_state_fingerprint", "0" * 64),
        ("previous_ai_brief", "fabricated"),
    ],
)
def test_role_brief_request_rejects_every_frontend_spoof_field(
    field: str,
    value: str,
) -> None:
    """The endpoint accepts assumptions plus USD and no derived state fields."""
    response = _post_role_brief(**{field: value})
    assert response.status_code == 422
    assert response.json() == {"detail": product_api._INVALID_ASSUMPTIONS_ERROR}


def test_role_brief_public_request_and_response_contracts_are_unchanged() -> None:
    """Internal planning introduces no new public request or response fields."""
    assert set(product_api.RoleBriefRequest.model_fields) == {
        "pilot_population",
        "expected_incremental_lift",
        "cost_per_intervention",
        "retained_customer_value",
        "currency",
    }
    assert set(product_api.RoleBriefResponse.model_fields) == {
        "accepted_state_fingerprint",
        "provider",
        "model_id",
        "briefs",
    }
    assert set(RoleImpactBrief.model_fields) == {
        "role_key",
        "why_it_matters",
        "what_still_holds",
        "what_to_verify_next",
        "evidence_refs",
        "assumption_refs",
        "next_handoff",
    }


def test_role_brief_rebuilds_hero_truth_and_calls_provider_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Hero generation reconstructs DD-3, seven Evidence items, and all roles."""
    provider = _FakeRoleBriefProvider()
    revision_calls = 0
    real_builder = product_api.build_rolelens_decision_revision

    def recording_builder(*args: Any, **kwargs: Any) -> Any:
        nonlocal revision_calls
        revision_calls += 1
        return real_builder(*args, **kwargs)

    monkeypatch.setattr(product_api, "build_rolelens_decision_revision", recording_builder)
    monkeypatch.setattr(product_api, "_build_role_brief_provider", lambda: provider)
    response = _post_role_brief(expected_incremental_lift="0.03")
    assert response.status_code == 200
    assert revision_calls == 1
    assert len(provider.plans) == 1
    assert len(provider.contexts) == 1
    plan = provider.plans[0]
    context = provider.contexts[0]
    assert context.scenario.net_scenario_value == "-7500"
    assert context.scenario.status == "DOES_NOT_CLEAR_BREAK_EVEN"
    sales = next(item for item in context.role_states if item.role_key == "sales_marketing")
    assert sales.state == "Blocked by scenario"
    assert sales.impact_kind == "blocked"
    assert tuple(item.assumption_id for item in context.changed_assumptions) == ("asm-002",)
    assert len(context.governed_evidence) == 7
    assert tuple(item.role_key for item in context.role_targets) == ROLE_ORDER
    expected_ids_by_role = {
        role_key: {
            item.evidence_id
            for item in context.governed_evidence
            if role_key in item.relevant_roles
        }
        for role_key in ROLE_ORDER
    }
    actual_ids_by_role = {
        target.role_key: {item.evidence_id for item in target.allowed_evidence}
        for target in context.role_targets
    }
    assert actual_ids_by_role == expected_ids_by_role
    assert [
        len(actual_ids_by_role[role_key]) for role_key in ROLE_ORDER
    ] == [6, 7, 1, 6, 3]
    parseability = next(
        item
        for item in context.governed_evidence
        if "data_engineer" in item.relevant_roles
    )
    assert actual_ids_by_role["data_engineer"] == {parseability.evidence_id}
    assert parseability.evidence_id not in actual_ids_by_role["executive"]
    assert parseability.evidence_id not in actual_ids_by_role["sales_marketing"]
    assert parseability.evidence_id in actual_ids_by_role["project_manager"]
    assert {
        target.role_key: target.required_assumption_refs
        for target in context.role_targets
    } == {
        "executive": ("asm-002",),
        "data_analyst": (),
        "data_engineer": (),
        "sales_marketing": ("asm-002",),
        "project_manager": ("asm-002",),
    }
    result = response.json()
    assert result["provider"] == "IBM watsonx.ai"
    assert result["model_id"] == provider.model_id
    assert len(result["briefs"]) == 5
    accepted_fingerprint = _post_revision(
        expected_incremental_lift="0.03"
    ).json()["accepted_state_fingerprint"]
    assert result["accepted_state_fingerprint"] == accepted_fingerprint
    assert plan.fingerprint == accepted_fingerprint
    assert len(plan.roles) == 5
    assert sum(
        len((role.why_atom, role.holds_atom, role.verify_atom))
        for role in plan.roles
    ) == 15


def test_baseline_role_brief_does_not_fabricate_human_revision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Baseline assumptions still traverse DD-3 but retain baseline semantics."""
    provider = _FakeRoleBriefProvider()
    monkeypatch.setattr(product_api, "_build_role_brief_provider", lambda: provider)
    response = _post_role_brief()
    assert response.status_code == 200
    context = provider.contexts[0]
    assert context.revision.model_dump() == {
        "revision_id": "rev-001",
        "label": "Baseline",
    }
    assert context.changed_assumptions == ()
    assert all(item.impact_kind == "current" for item in context.role_states)
    assert all(not item.required_assumption_refs for item in context.role_targets)


def test_non_role_brief_routes_never_construct_or_call_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GET, evidence depth, and recalculation remain deterministic-only routes."""
    calls = 0

    def forbidden_provider() -> None:
        nonlocal calls
        calls += 1
        raise AssertionError("Granite provider must not be constructed")

    monkeypatch.setattr(product_api, "_build_role_brief_provider", forbidden_provider)
    client = TestClient(product_api.app)
    assert client.get("/api/demo/decision").status_code == 200
    assert client.get("/api/demo/decision/evidence").status_code == 200
    assert _post_revision(expected_incremental_lift="0.03").status_code == 200
    assert calls == 0


@pytest.mark.parametrize("failure_stage", ["configuration", "generation"])
def test_role_brief_failures_are_bounded_and_sanitized(
    monkeypatch: pytest.MonkeyPatch,
    failure_stage: str,
) -> None:
    """Configuration, network, malformed, and validator failures share safe API text."""
    secret = "secret-key raw-response project-id traceback"

    if failure_stage == "configuration":
        def failing_builder() -> None:
            raise RuntimeError(secret)

        monkeypatch.setattr(product_api, "_build_role_brief_provider", failing_builder)
    else:
        class FailingProvider:
            model_id = "ibm/granite-secret"

            def generate(
                self,
                _plan: RoleBriefPlanSet,
                _context: RoleBriefGenerationContext,
            ) -> None:
                raise RuntimeError(secret)

        monkeypatch.setattr(
            product_api,
            "_build_role_brief_provider",
            lambda: FailingProvider(),
        )

    response = _post_role_brief(expected_incremental_lift="0.03")
    assert response.status_code == 503
    assert response.json() == {"detail": product_api._ROLE_BRIEF_ERROR}
    assert secret not in response.text


def test_role_brief_response_exposes_no_provider_internals(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only fingerprint, provider, model ID, and validated briefs leave the API."""
    provider = _FakeRoleBriefProvider()
    monkeypatch.setattr(product_api, "_build_role_brief_provider", lambda: provider)
    response = _post_role_brief(expected_incremental_lift="0.03")
    assert response.status_code == 200
    assert set(response.json()) == {
        "accepted_state_fingerprint",
        "provider",
        "model_id",
        "briefs",
    }
    serialized = response.text.lower()
    for forbidden in (
        "prompt",
        "raw_response",
        "project_id",
        "watsonx_url",
        "api_key",
        "chain-of-thought",
        "snapshot_json",
        "identity_digest",
        "atom_id",
        "canonical_claim",
        "handoffplan",
        "rolebriefplan",
        "semanticatom",
    ):
        assert forbidden not in serialized
