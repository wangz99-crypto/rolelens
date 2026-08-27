"""Focused safety and contract tests for the Slice 1 product API."""

from __future__ import annotations

import ast
import importlib
import sys
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app import product_api


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
        "decision_diff_engine",
        "decision_diff_rolelens",
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
