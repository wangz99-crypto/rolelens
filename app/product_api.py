"""Thin deterministic API for the RoleLens React product.

Importing this module performs no file reads, provider construction, credential
access, or network activity. Each product request rebuilds the trusted frozen
IBM Telco context through the existing Python core.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, ValidationError

from app.business_profile import BusinessDatasetProfile
from app.decision_diff import ScenarioAssumption, ScenarioResult, calculate_break_even_scenario
from app.decision_diff_engine import DecisionImpactType
from app.decision_diff_rolelens import (
    ExecutiveScenarioPosture,
    ProjectManagerHandoff,
    RoleLensDecisionRevision,
    SalesPilotPosture,
    build_rolelens_decision_revision,
)
from app.demo_pipeline import PreparedDemoInputs, prepare_demo_inputs
from app.schemas import EvidenceObject


_ROOT = Path(__file__).resolve().parent.parent
_PUBLIC_CSV = _ROOT / "sample_data" / "public" / "ibm_telco_customer_churn.csv"
_PUBLIC_CONTEXT = _ROOT / "sample_data" / "public" / "ibm_telco_customer_churn_context.json"
_BUSINESS_PROFILE_ID = "ibm_telco_churn_v1"
_PRODUCT_ERROR = "RoleLens could not load the demo decision safely."
_EVIDENCE_ERROR = "Evidence details could not be loaded safely."
_INVALID_ASSUMPTIONS_ERROR = "Decision assumptions are invalid."
_RECALCULATION_ERROR = "RoleLens could not recalculate the demo decision safely."
_DISCLOSURE = "This is a fictional IBM sample dataset, not real customer production data."

_BUSINESS_EVIDENCE_TYPES = (
    "business_overall_churn",
    "business_contract_churn",
    "business_support_churn",
    "business_internet_churn",
    "business_payment_churn",
    "business_churn_medians",
    "business_parseability",
)

_EVIDENCE_LABELS = {
    "business_overall_churn": "Overall recorded churn",
    "business_contract_churn": "Recorded churn by contract",
    "business_support_churn": "Recorded churn by tech support",
    "business_internet_churn": "Recorded churn by internet service",
    "business_payment_churn": "Recorded churn by payment method",
    "business_churn_medians": "Churn-status medians",
    "business_parseability": "TotalCharges parseability",
}

_ROLE_KEY = Literal[
    "executive", "data_analyst", "data_engineer", "sales_marketing", "project_manager"
]
_IMPACT_KIND = Literal["current", "unchanged", "recomputed", "changed", "blocked"]
_DIFF_KIND = Literal["decision_posture_changed", "scenario_changed", "no_change"]


class _ProductContract(BaseModel):
    """Frozen, closed base contract for product API data."""

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
    """Accepted Slice 1 baseline revision presentation."""

    revision_id: Literal["rev-001"]
    label: Literal["Baseline"]


class RecalculatedRevisionResponse(_ProductContract):
    """Stateless revision presentation after recalculation."""

    revision_id: Literal["rev-001", "rev-002"]
    label: Literal["Baseline", "Human revision"]


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


class RevisionEvidenceSummaryResponse(EvidenceSummaryResponse):
    """Evidence summary plus invariants derived from trusted DD-3 results."""

    observed_evidence_unchanged: bool
    data_health_unchanged: bool
    source_provenance_unchanged: bool


class EvidenceDetailResponse(_ProductContract):
    """Bounded product-depth projection of one approved Evidence Object."""

    evidence_id: str
    evidence_type: str
    label: str
    finding: str
    confidence: Literal["low", "medium", "high"]
    extraction_method: Literal["deterministic", "llm_assisted"]
    scope: Literal[
        "internal_observation", "external_context", "stated_priority", "assumption"
    ]
    source_label: Literal["IBM Telco public demo"]
    limitations: tuple[str, ...]
    relevant_roles: tuple[_ROLE_KEY, ...]


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
    """Bounded trusted scenario result for product rendering."""

    scenario_id: str
    status: Literal["CLEARS_BREAK_EVEN", "DOES_NOT_CLEAR_BREAK_EVEN", "NOT_EVALUABLE"]
    expected_incremental_retained: float
    expected_scenario_value: float
    intervention_cost: float
    net_scenario_value: float
    break_even_lift: float
    currency: str


class RoleResponse(_ProductContract):
    """Frozen Slice 1 organizational presentation node."""

    role_key: _ROLE_KEY
    label: str
    baseline_state: str
    state_kind: Literal["current", "foundation"]


class RevisionRoleResponse(_ProductContract):
    """One role state derived from trusted projection and impact data."""

    role_key: _ROLE_KEY
    label: str
    state: str
    impact_kind: _IMPACT_KIND


class ChangedAssumptionResponse(_ProductContract):
    """One canonical bounded assumption change from DD-2."""

    assumption_id: str
    key: str
    label: str
    before_value: float
    after_value: float
    unit: str
    currency: str | None


class DecisionDiffResponse(_ProductContract):
    """Compact product diff without raw dependency objects."""

    kind: _DIFF_KIND
    headline: str
    changed_assumptions: tuple[ChangedAssumptionResponse, ...]
    scenario_status_changed: bool
    role_posture_changed: bool
    observed_evidence_unchanged: bool


class DemoDecisionResponse(_ProductContract):
    """Complete bounded response for the Slice 1 baseline."""

    decision: DecisionResponse
    revision: RevisionResponse
    evidence: EvidenceSummaryResponse
    assumptions: tuple[AssumptionResponse, ...]
    scenario: ScenarioResponse
    roles: tuple[RoleResponse, ...]


class RecalculateDecisionRequest(_ProductContract):
    """Only human-controlled scenario inputs accepted from the frontend."""

    pilot_population: int
    expected_incremental_lift: Decimal
    cost_per_intervention: Decimal
    retained_customer_value: Decimal
    currency: Literal["USD"]


class RecalculatedDecisionResponse(_ProductContract):
    """Bounded DD-3 response for an in-place Decision Room update."""

    decision: DecisionResponse
    revision: RecalculatedRevisionResponse
    evidence: RevisionEvidenceSummaryResponse
    assumptions: tuple[AssumptionResponse, ...]
    before_scenario: ScenarioResponse
    scenario: ScenarioResponse
    roles: tuple[RevisionRoleResponse, ...]
    diff: DecisionDiffResponse


class _InvalidDecisionAssumptions(ValueError):
    """Internal marker for controlled caller-input failures."""


@dataclass(frozen=True)
class _PreparedProductContext:
    """Validated real product context shared by GET and POST flows."""

    sidecar: dict[str, str]
    prepared: PreparedDemoInputs
    profile: BusinessDatasetProfile
    business_evidence: tuple[EvidenceObject, ...]
    month_to_month_churn_rate_pct: float


_ASSUMPTION_LABELS = {
    "pilot_population": "Pilot population",
    "expected_incremental_lift": "Expected lift",
    "cost_per_intervention": "Cost / intervention",
    "retained_customer_value": "Retained value",
}
_EXECUTIVE_STATES = {
    ExecutiveScenarioPosture.LIMITED_PILOT_REVIEW_CANDIDATE: "Pilot review candidate",
    ExecutiveScenarioPosture.VALIDATE_SCENARIO_ASSUMPTIONS_FIRST: "Validate assumptions first",
}
_SALES_STATES = {
    SalesPilotPosture.ELIGIBLE_FOR_PILOT_REVIEW: "Eligible for pilot review",
    SalesPilotPosture.BLOCKED_BY_SCENARIO: "Blocked by scenario",
}
_PROJECT_MANAGER_STATES = {
    ProjectManagerHandoff.PREPARE_LIMITED_PILOT_REVIEW: "Prepare limited pilot review",
    ProjectManagerHandoff.REOPEN_SCENARIO_VALIDATION: "Reopen scenario validation",
}

_BASELINE_ROLES = (
    RoleResponse(role_key="executive", label="Executive", baseline_state="Pilot review candidate", state_kind="current"),
    RoleResponse(role_key="data_analyst", label="Data Analyst", baseline_state="Evidence basis valid", state_kind="foundation"),
    RoleResponse(role_key="data_engineer", label="Data Engineer", baseline_state="Data foundation valid", state_kind="foundation"),
    RoleResponse(role_key="sales_marketing", label="Sales / Marketing", baseline_state="Eligible for pilot review", state_kind="current"),
    RoleResponse(role_key="project_manager", label="Project Manager", baseline_state="Prepare limited pilot review", state_kind="current"),
)


def _scenario_assumptions(
    *,
    revision_id: Literal["rev-001", "rev-002"],
    pilot_population: int,
    expected_incremental_lift: Decimal,
    cost_per_intervention: Decimal,
    retained_customer_value: Decimal,
    currency: Literal["USD"],
) -> tuple[ScenarioAssumption, ...]:
    """Construct canonical assumptions and delegate validation to DD-1."""
    try:
        return (
            ScenarioAssumption(assumption_id="asm-001", revision_id=revision_id, key="pilot_population", value=Decimal(pilot_population), unit="customers", currency=None),
            ScenarioAssumption(assumption_id="asm-002", revision_id=revision_id, key="expected_incremental_lift", value=expected_incremental_lift, unit="fraction", currency=None),
            ScenarioAssumption(assumption_id="asm-003", revision_id=revision_id, key="cost_per_intervention", value=cost_per_intervention, unit="currency_per_customer", currency=currency),
            ScenarioAssumption(assumption_id="asm-004", revision_id=revision_id, key="retained_customer_value", value=retained_customer_value, unit="currency_per_customer", currency=currency),
        )
    except (ValidationError, ValueError, TypeError):
        raise _InvalidDecisionAssumptions(_INVALID_ASSUMPTIONS_ERROR) from None


def _baseline_assumptions() -> tuple[ScenarioAssumption, ...]:
    """Construct the four approved baseline inputs through DD-1 contracts."""
    return _scenario_assumptions(
        revision_id="rev-001",
        pilot_population=500,
        expected_incremental_lift=Decimal("0.08"),
        cost_per_intervention=Decimal("30"),
        retained_customer_value=Decimal("500"),
        currency="USD",
    )


def _required_decimal(value: Decimal | None) -> float:
    """Convert a required calculated Decimal after core validation."""
    if value is None:
        raise ValueError("The scenario result is incomplete.")
    return float(value)


def _prepare_product_context() -> _PreparedProductContext:
    """Rebuild and validate the frozen IBM Telco context for one request."""
    sidecar = json.loads(_PUBLIC_CONTEXT.read_text(encoding="utf-8"))
    prepared = prepare_demo_inputs(
        csv_bytes=_PUBLIC_CSV.read_bytes(),
        filename=_PUBLIC_CSV.name,
        industry_context=sidecar["dataset_context"],
        strategy_profile=sidecar["strategy_profile"],
        business_question=sidecar["business_question"],
        decision_goal=sidecar["decision_goal"],
        user_assumption=sidecar["user_assumption"],
        business_profile_id=_BUSINESS_PROFILE_ID,
    )
    profile = prepared.business_profile
    if profile is None:
        raise ValueError("The approved business profile is unavailable.")
    selected_evidence = tuple(
        evidence for evidence in prepared.evidence_objects
        if evidence.evidence_type in _BUSINESS_EVIDENCE_TYPES and evidence.status.value == "active"
    )
    selected_types = tuple(evidence.evidence_type for evidence in selected_evidence)
    if len(selected_evidence) != 7 or set(selected_types) != set(_BUSINESS_EVIDENCE_TYPES):
        raise ValueError("The governed evidence basis is incomplete.")
    if len(selected_types) != len(set(selected_types)):
        raise ValueError("The governed evidence basis contains duplicates.")
    evidence_by_type = {item.evidence_type: item for item in selected_evidence}
    business_evidence = tuple(
        evidence_by_type[evidence_type]
        for evidence_type in _BUSINESS_EVIDENCE_TYPES
    )
    if any(evidence.source_id != prepared.data_health_summary.source_id for evidence in business_evidence):
        raise ValueError("The governed evidence source is inconsistent.")
    month_to_month = next(item for item in profile.contract_rates if item.segment == "Month-to-month")
    return _PreparedProductContext(
        sidecar=sidecar,
        prepared=prepared,
        profile=profile,
        business_evidence=business_evidence,
        month_to_month_churn_rate_pct=month_to_month.churn_rate_pct,
    )


def _decision_response(context: _PreparedProductContext) -> DecisionResponse:
    """Build the single bounded product Decision identity."""
    return DecisionResponse(
        decision_id="dec-001",
        title="Customer Retention Pilot",
        business_question=context.sidecar["business_question"],
        source_label="IBM Telco",
        disclosure=_DISCLOSURE,
    )


def _evidence_response(context: _PreparedProductContext) -> EvidenceSummaryResponse:
    """Build the accepted Slice 1 evidence summary."""
    return EvidenceSummaryResponse(
        status="LOCKED",
        governed_evidence_count=len(context.business_evidence),
        customer_count=context.profile.unique_customer_count,
        recorded_churn_rate_pct=context.profile.overall_churn_rate_pct,
        month_to_month_churn_rate_pct=context.month_to_month_churn_rate_pct,
        total_charges_parse_issue_count=context.profile.total_charges_parse_issue_count,
        data_health_checked=True,
        source_provenance_locked=True,
    )


def _evidence_detail_response(
    context: _PreparedProductContext,
) -> tuple[EvidenceDetailResponse, ...]:
    """Project the ordered governed Evidence Objects without internal payloads."""
    return tuple(
        EvidenceDetailResponse(
            evidence_id=item.evidence_id,
            evidence_type=item.evidence_type,
            label=_EVIDENCE_LABELS[item.evidence_type],
            finding=item.finding,
            confidence=item.confidence,
            extraction_method=item.extraction_method,
            scope=item.evidence_scope.value,
            source_label="IBM Telco public demo",
            limitations=tuple(item.limitations),
            relevant_roles=tuple(item.relevant_roles),
        )
        for item in context.business_evidence
    )


def _assumption_response(assumptions: tuple[ScenarioAssumption, ...]) -> tuple[AssumptionResponse, ...]:
    """Map canonical DD-1 assumptions to ordered product fields."""
    return tuple(
        AssumptionResponse(
            assumption_id=item.assumption_id,
            key=item.key,
            label=_ASSUMPTION_LABELS[item.key],
            value=float(item.value),
            unit=item.unit,
            currency=item.currency,
            source_scope=item.source_scope,
        ) for item in assumptions
    )


def _scenario_response(scenario: ScenarioResult) -> ScenarioResponse:
    """Map one trusted DD scenario result without recalculating it."""
    if scenario.currency is None:
        raise ValueError("The scenario currency is unavailable.")
    return ScenarioResponse(
        scenario_id=scenario.scenario_id,
        status=scenario.status.value,
        expected_incremental_retained=_required_decimal(scenario.expected_incremental_retained),
        expected_scenario_value=_required_decimal(scenario.expected_scenario_value),
        intervention_cost=_required_decimal(scenario.intervention_cost),
        net_scenario_value=_required_decimal(scenario.net_scenario_value),
        break_even_lift=_required_decimal(scenario.break_even_lift),
        currency=scenario.currency,
    )


def _build_demo_decision() -> DemoDecisionResponse:
    """Build one real baseline response through approved core paths."""
    context = _prepare_product_context()
    assumptions = _baseline_assumptions()
    scenario = calculate_break_even_scenario(assumptions, scenario_id="scn-001", revision_id="rev-001")
    return DemoDecisionResponse(
        decision=_decision_response(context),
        revision=RevisionResponse(revision_id="rev-001", label="Baseline"),
        evidence=_evidence_response(context),
        assumptions=_assumption_response(assumptions),
        scenario=_scenario_response(scenario),
        roles=_BASELINE_ROLES,
    )


def _impact_kind_for_posture(
    *, impact_type: DecisionImpactType, posture_changed: bool, allow_blocked: bool = False,
) -> Literal["unchanged", "recomputed", "changed", "blocked"]:
    """Map trusted impact plus projection comparison to product language."""
    if impact_type is DecisionImpactType.UNCHANGED and not posture_changed:
        return "unchanged"
    if impact_type is DecisionImpactType.RECOMPUTED:
        return "changed" if posture_changed else "recomputed"
    if allow_blocked and impact_type is DecisionImpactType.BLOCKED:
        return "blocked"
    raise ValueError("The trusted role impact is inconsistent.")


def _revision_roles(revision: RoleLensDecisionRevision) -> tuple[RevisionRoleResponse, ...]:
    """Derive five product roles only from DD-3 projections and impacts."""
    impacts = {item.object_id: item for item in revision.decision_diff.impacts}
    before = revision.before_projection
    after = revision.after_projection
    if impacts["obj-observed-evidence"].impact_type is not DecisionImpactType.UNCHANGED:
        raise ValueError("The observed-evidence foundation changed unexpectedly.")
    if (
        impacts["obj-data-health"].impact_type is not DecisionImpactType.UNCHANGED
        or impacts["obj-source-provenance"].impact_type is not DecisionImpactType.UNCHANGED
    ):
        raise ValueError("The data foundation changed unexpectedly.")
    return (
        RevisionRoleResponse(
            role_key="executive", label="Executive", state=_EXECUTIVE_STATES[after.executive_posture],
            impact_kind=_impact_kind_for_posture(
                impact_type=impacts["obj-executive-posture"].impact_type,
                posture_changed=before.executive_posture != after.executive_posture,
            ),
        ),
        RevisionRoleResponse(role_key="data_analyst", label="Data Analyst", state="Evidence basis remains valid", impact_kind="unchanged"),
        RevisionRoleResponse(role_key="data_engineer", label="Data Engineer", state="Data foundation remains valid", impact_kind="unchanged"),
        RevisionRoleResponse(
            role_key="sales_marketing", label="Sales / Marketing", state=_SALES_STATES[after.sales_posture],
            impact_kind=_impact_kind_for_posture(
                impact_type=impacts["obj-sales-posture"].impact_type,
                posture_changed=before.sales_posture != after.sales_posture,
                allow_blocked=True,
            ),
        ),
        RevisionRoleResponse(
            role_key="project_manager", label="Project Manager", state=_PROJECT_MANAGER_STATES[after.project_manager_handoff],
            impact_kind=_impact_kind_for_posture(
                impact_type=impacts["obj-pm-handoff"].impact_type,
                posture_changed=before.project_manager_handoff != after.project_manager_handoff,
            ),
        ),
    )


def _revision_evidence(
    context: _PreparedProductContext, revision: RoleLensDecisionRevision,
) -> RevisionEvidenceSummaryResponse:
    """Derive bounded foundation invariants from the validated DD-3 result."""
    impacts = {item.object_id: item for item in revision.decision_diff.impacts}
    basis_ids = tuple(item.evidence_id for item in revision.evidence_basis.business_evidence)
    baseline = _evidence_response(context)
    return RevisionEvidenceSummaryResponse(
        **baseline.model_dump(),
        observed_evidence_unchanged=(
            impacts["obj-observed-evidence"].impact_type is DecisionImpactType.UNCHANGED
            and revision.unchanged_evidence_ids == basis_ids
            and revision.before_projection.evidence_ids == basis_ids
            and revision.after_projection.evidence_ids == basis_ids
        ),
        data_health_unchanged=impacts["obj-data-health"].impact_type is DecisionImpactType.UNCHANGED,
        source_provenance_unchanged=impacts["obj-source-provenance"].impact_type is DecisionImpactType.UNCHANGED,
    )


def _revision_diff(
    revision: RoleLensDecisionRevision, evidence: RevisionEvidenceSummaryResponse,
) -> DecisionDiffResponse:
    """Map trusted structured DD-3 results to the compact product diff."""
    before = revision.before_projection
    after = revision.after_projection
    role_posture_changed = any((
        before.executive_posture != after.executive_posture,
        before.sales_posture != after.sales_posture,
        before.project_manager_handoff != after.project_manager_handoff,
    ))
    changed = revision.decision_diff.changed_assumptions
    if not changed:
        kind: _DIFF_KIND = "no_change"
        headline = "No scenario assumption changed"
    elif role_posture_changed:
        kind = "decision_posture_changed"
        headline = "Decision posture changed"
    else:
        kind = "scenario_changed"
        headline = "Scenario changed; decision posture remains the same"
    return DecisionDiffResponse(
        kind=kind,
        headline=headline,
        changed_assumptions=tuple(
            ChangedAssumptionResponse(
                assumption_id=item.assumption_id,
                key=item.key,
                label=_ASSUMPTION_LABELS[item.key],
                before_value=float(item.before_value),
                after_value=float(item.after_value),
                unit=item.unit,
                currency=item.currency,
            ) for item in changed
        ),
        scenario_status_changed=before.scenario_result.status != after.scenario_result.status,
        role_posture_changed=role_posture_changed,
        observed_evidence_unchanged=evidence.observed_evidence_unchanged,
    )


def _build_recalculated_decision(request: RecalculateDecisionRequest) -> RecalculatedDecisionResponse:
    """Rebuild context and execute exactly one trusted DD-3 revision."""
    context = _prepare_product_context()
    before_assumptions = _baseline_assumptions()
    after_assumptions = _scenario_assumptions(
        revision_id="rev-002",
        pilot_population=request.pilot_population,
        expected_incremental_lift=request.expected_incremental_lift,
        cost_per_intervention=request.cost_per_intervention,
        retained_customer_value=request.retained_customer_value,
        currency=request.currency,
    )
    revision = build_rolelens_decision_revision(
        business_profile=context.profile,
        evidence_objects=context.prepared.evidence_objects,
        data_health_summary=context.prepared.data_health_summary,
        source_manifests=context.prepared.source_manifests,
        before_assumptions=before_assumptions,
        after_assumptions=after_assumptions,
        scenario_id="scn-001",
        before_revision_id="rev-001",
        after_revision_id="rev-002",
    )
    evidence = _revision_evidence(context, revision)
    if not all((evidence.observed_evidence_unchanged, evidence.data_health_unchanged, evidence.source_provenance_unchanged)):
        raise ValueError("The trusted product foundations changed unexpectedly.")
    diff = _revision_diff(revision, evidence)
    has_logical_change = bool(diff.changed_assumptions)
    return RecalculatedDecisionResponse(
        decision=_decision_response(context),
        revision=RecalculatedRevisionResponse(
            revision_id="rev-002" if has_logical_change else "rev-001",
            label="Human revision" if has_logical_change else "Baseline",
        ),
        evidence=evidence,
        assumptions=_assumption_response(after_assumptions),
        before_scenario=_scenario_response(revision.before_projection.scenario_result),
        scenario=_scenario_response(revision.after_projection.scenario_result),
        roles=_revision_roles(revision),
        diff=diff,
    )


app = FastAPI(title="RoleLens Product API", version="2.0.0")


@app.exception_handler(RequestValidationError)
async def invalid_request_handler(_request: Request, _error: RequestValidationError) -> JSONResponse:
    """Replace request diagnostics with one bounded product error."""
    return JSONResponse(status_code=422, content={"detail": _INVALID_ASSUMPTIONS_ERROR})


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


@app.get(
    "/api/demo/decision/evidence",
    response_model=tuple[EvidenceDetailResponse, ...],
)
def get_demo_decision_evidence() -> tuple[EvidenceDetailResponse, ...]:
    """Return only the seven ordered approved business Evidence Objects."""
    try:
        return _evidence_detail_response(_prepare_product_context())
    except Exception:
        raise HTTPException(status_code=503, detail=_EVIDENCE_ERROR) from None


@app.post("/api/demo/decision/recalculate", response_model=RecalculatedDecisionResponse)
def recalculate_demo_decision(request: RecalculateDecisionRequest) -> RecalculatedDecisionResponse:
    """Run one stateless human revision through the trusted DD-3 entrypoint."""
    try:
        return _build_recalculated_decision(request)
    except _InvalidDecisionAssumptions:
        raise HTTPException(status_code=422, detail=_INVALID_ASSUMPTIONS_ERROR) from None
    except Exception:
        raise HTTPException(status_code=503, detail=_RECALCULATION_ERROR) from None
