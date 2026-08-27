"""Thin, deterministic product API for the first RoleLens React slice.

The module exposes only bounded product presentation data. Importing it does
not read sample files, construct providers, inspect environment credentials, or
perform network access. The frozen demo inputs are prepared for each explicit
``GET /api/demo/decision`` request through the existing RoleLens Python core.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict

from app.decision_diff import ScenarioAssumption, calculate_break_even_scenario
from app.demo_pipeline import prepare_demo_inputs


_ROOT = Path(__file__).resolve().parent.parent
_PUBLIC_CSV = _ROOT / "sample_data" / "public" / "ibm_telco_customer_churn.csv"
_PUBLIC_CONTEXT = (
    _ROOT / "sample_data" / "public" / "ibm_telco_customer_churn_context.json"
)
_BUSINESS_PROFILE_ID = "ibm_telco_churn_v1"
_PRODUCT_ERROR = "RoleLens could not load the demo decision safely."
_DISCLOSURE = (
    "This is a fictional IBM sample dataset, not real customer production data."
)

_BUSINESS_EVIDENCE_TYPES = (
    "business_overall_churn",
    "business_contract_churn",
    "business_support_churn",
    "business_internet_churn",
    "business_payment_churn",
    "business_churn_medians",
    "business_parseability",
)


class _ProductContract(BaseModel):
    """Frozen, closed base contract for Slice 1 API responses."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class HealthResponse(_ProductContract):
    """API liveness response."""

    status: Literal["ok"]


class DecisionResponse(_ProductContract):
    """Bounded identity and context for the single demo decision."""

    decision_id: str
    title: str
    business_question: str
    source_label: str
    disclosure: str


class RevisionResponse(_ProductContract):
    """Current immutable baseline revision presentation."""

    revision_id: Literal["rev-001"]
    label: Literal["Baseline"]


class EvidenceSummaryResponse(_ProductContract):
    """Bounded observed-evidence summary without internal identifiers."""

    status: Literal["LOCKED"]
    governed_evidence_count: int
    customer_count: int
    recorded_churn_rate_pct: float
    month_to_month_churn_rate_pct: float
    total_charges_parse_issue_count: int
    data_health_checked: bool
    source_provenance_locked: bool


class AssumptionResponse(_ProductContract):
    """One ordered human-supplied scenario assumption."""

    assumption_id: str
    key: str
    label: str
    value: float
    unit: str
    currency: str | None
    source_scope: Literal["user_assumption"]


class ScenarioResponse(_ProductContract):
    """Bounded DD-1 baseline result for product rendering."""

    scenario_id: str
    status: str
    expected_incremental_retained: float
    expected_scenario_value: float
    intervention_cost: float
    net_scenario_value: float
    break_even_lift: float
    currency: str


class RoleResponse(_ProductContract):
    """Frozen Slice 1 organizational presentation node."""

    role_key: Literal[
        "executive",
        "data_analyst",
        "data_engineer",
        "sales_marketing",
        "project_manager",
    ]
    label: str
    baseline_state: str
    state_kind: Literal["current", "foundation"]


class DemoDecisionResponse(_ProductContract):
    """Complete bounded response for the Slice 1 Decision Room."""

    decision: DecisionResponse
    revision: RevisionResponse
    evidence: EvidenceSummaryResponse
    assumptions: tuple[AssumptionResponse, ...]
    scenario: ScenarioResponse
    roles: tuple[RoleResponse, ...]


_ASSUMPTION_LABELS = {
    "pilot_population": "Pilot population",
    "expected_incremental_lift": "Expected lift",
    "cost_per_intervention": "Cost / intervention",
    "retained_customer_value": "Retained value",
}

_BASELINE_ROLES = (
    RoleResponse(
        role_key="executive",
        label="Executive",
        baseline_state="Pilot review candidate",
        state_kind="current",
    ),
    RoleResponse(
        role_key="data_analyst",
        label="Data Analyst",
        baseline_state="Evidence basis valid",
        state_kind="foundation",
    ),
    RoleResponse(
        role_key="data_engineer",
        label="Data Engineer",
        baseline_state="Data foundation valid",
        state_kind="foundation",
    ),
    RoleResponse(
        role_key="sales_marketing",
        label="Sales / Marketing",
        baseline_state="Eligible for pilot review",
        state_kind="current",
    ),
    RoleResponse(
        role_key="project_manager",
        label="Project Manager",
        baseline_state="Prepare limited pilot review",
        state_kind="current",
    ),
)


def _baseline_assumptions() -> tuple[ScenarioAssumption, ...]:
    """Construct the four approved DD-1 inputs without calculating them."""
    return (
        ScenarioAssumption(
            assumption_id="asm-001",
            revision_id="rev-001",
            key="pilot_population",
            value=Decimal("500"),
            unit="customers",
            currency=None,
        ),
        ScenarioAssumption(
            assumption_id="asm-002",
            revision_id="rev-001",
            key="expected_incremental_lift",
            value=Decimal("0.08"),
            unit="fraction",
            currency=None,
        ),
        ScenarioAssumption(
            assumption_id="asm-003",
            revision_id="rev-001",
            key="cost_per_intervention",
            value=Decimal("30"),
            unit="currency_per_customer",
            currency="USD",
        ),
        ScenarioAssumption(
            assumption_id="asm-004",
            revision_id="rev-001",
            key="retained_customer_value",
            value=Decimal("500"),
            unit="currency_per_customer",
            currency="USD",
        ),
    )


def _required_decimal(value: Decimal | None) -> float:
    """Convert a required calculated Decimal after DD-1 validates it."""
    if value is None:
        raise ValueError("The baseline scenario is incomplete.")
    return float(value)


def _build_demo_decision() -> DemoDecisionResponse:
    """Build one real baseline response entirely through approved core paths."""
    context = json.loads(_PUBLIC_CONTEXT.read_text(encoding="utf-8"))
    prepared = prepare_demo_inputs(
        csv_bytes=_PUBLIC_CSV.read_bytes(),
        filename=_PUBLIC_CSV.name,
        industry_context=context["dataset_context"],
        strategy_profile=context["strategy_profile"],
        business_question=context["business_question"],
        decision_goal=context["decision_goal"],
        user_assumption=context["user_assumption"],
        business_profile_id=_BUSINESS_PROFILE_ID,
    )
    profile = prepared.business_profile
    if profile is None:
        raise ValueError("The approved business profile is unavailable.")

    business_evidence = tuple(
        evidence
        for evidence in prepared.evidence_objects
        if evidence.evidence_type in _BUSINESS_EVIDENCE_TYPES
        and evidence.status.value == "active"
    )
    selected_types = tuple(evidence.evidence_type for evidence in business_evidence)
    if len(business_evidence) != len(_BUSINESS_EVIDENCE_TYPES) or set(
        selected_types
    ) != set(_BUSINESS_EVIDENCE_TYPES):
        raise ValueError("The governed evidence basis is incomplete.")
    if len(selected_types) != len(set(selected_types)):
        raise ValueError("The governed evidence basis contains duplicates.")
    if any(
        evidence.source_id != prepared.data_health_summary.source_id
        for evidence in business_evidence
    ):
        raise ValueError("The governed evidence source is inconsistent.")

    assumptions = _baseline_assumptions()
    scenario = calculate_break_even_scenario(
        assumptions,
        scenario_id="scn-001",
        revision_id="rev-001",
    )
    month_to_month = next(
        item for item in profile.contract_rates if item.segment == "Month-to-month"
    )

    assumption_response = tuple(
        AssumptionResponse(
            assumption_id=item.assumption_id,
            key=item.key,
            label=_ASSUMPTION_LABELS[item.key],
            value=float(item.value),
            unit=item.unit,
            currency=item.currency,
            source_scope=item.source_scope,
        )
        for item in assumptions
    )
    if scenario.currency is None:
        raise ValueError("The baseline scenario currency is unavailable.")

    return DemoDecisionResponse(
        decision=DecisionResponse(
            decision_id="dec-001",
            title="Customer Retention Pilot",
            business_question=context["business_question"],
            source_label="IBM Telco",
            disclosure=_DISCLOSURE,
        ),
        revision=RevisionResponse(revision_id="rev-001", label="Baseline"),
        evidence=EvidenceSummaryResponse(
            status="LOCKED",
            governed_evidence_count=len(business_evidence),
            customer_count=profile.unique_customer_count,
            recorded_churn_rate_pct=profile.overall_churn_rate_pct,
            month_to_month_churn_rate_pct=month_to_month.churn_rate_pct,
            total_charges_parse_issue_count=(
                profile.total_charges_parse_issue_count
            ),
            data_health_checked=True,
            source_provenance_locked=True,
        ),
        assumptions=assumption_response,
        scenario=ScenarioResponse(
            scenario_id=scenario.scenario_id,
            status=scenario.status.value,
            expected_incremental_retained=_required_decimal(
                scenario.expected_incremental_retained
            ),
            expected_scenario_value=_required_decimal(
                scenario.expected_scenario_value
            ),
            intervention_cost=_required_decimal(scenario.intervention_cost),
            net_scenario_value=_required_decimal(scenario.net_scenario_value),
            break_even_lift=_required_decimal(scenario.break_even_lift),
            currency=scenario.currency,
        ),
        roles=_BASELINE_ROLES,
    )


app = FastAPI(title="RoleLens Product API", version="1.0.0")


@app.get("/api/health", response_model=HealthResponse)
def get_health() -> HealthResponse:
    """Return a bounded liveness response."""
    return HealthResponse(status="ok")


@app.get("/api/demo/decision", response_model=DemoDecisionResponse)
def get_demo_decision() -> DemoDecisionResponse:
    """Return the real deterministic IBM Telco baseline or a safe error."""
    try:
        return _build_demo_decision()
    except Exception:
        raise HTTPException(status_code=503, detail=_PRODUCT_ERROR) from None
