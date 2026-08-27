"""Standalone Streamlit product-validation spike for RoleLens DD-4.

Normal module import performs no rendering, sample-file reads, Evidence
preparation, provider construction, environment access, network access, or
scenario calculation. All product work is initiated by :func:`main` or by an
explicit helper called by it.
"""

from __future__ import annotations

import json
from collections.abc import MutableMapping
from decimal import Decimal
from pathlib import Path
from typing import Any

from app import decision_diff, decision_diff_rolelens, demo_pipeline
from app.decision_diff import ScenarioAssumption, ScenarioResult, ScenarioStatus
from app.decision_diff_engine import DecisionImpact, DecisionImpactType
from app.decision_diff_rolelens import (
    ExecutiveScenarioPosture,
    ProjectManagerHandoff,
    RoleLensDecisionRevision,
    SalesPilotPosture,
)


_ROOT = Path(__file__).parent.parent
_PUBLIC_CSV = _ROOT / "sample_data" / "public" / "ibm_telco_customer_churn.csv"
_PUBLIC_CONTEXT = (
    _ROOT / "sample_data" / "public" / "ibm_telco_customer_churn_context.json"
)

_SK_PREPARED = "decision_lab_prepared_inputs"
_SK_REVISION = "decision_lab_revision"
_SK_REVISION_LIFT = "decision_lab_revision_lift_pct"
_SK_LIFT_WIDGET = "decision_lab_after_lift_pct"

_TAGLINE = (
    "Change one business assumption. See what the decision must reconsider — "
    "without rewriting the facts."
)
_PROCESS_CAPTION = (
    "Observed Evidence → Human Assumption → Recalculation → Decision Diff"
)
_DATASET_DISCLOSURE = (
    "This is a fictional IBM sample dataset, not real customer production data."
)
_EVIDENCE_CONTEXT_CAPTION = (
    "These Evidence Objects provide the unchanged observed business context. "
    "They are not financial inputs to the break-even formula."
)
_CURRENCY_NOTICE = (
    "Scenario currency: USD — supplied by the user, not inferred from the IBM "
    "dataset."
)
_DATASET_CURRENCY_NOTICE = (
    "The IBM dataset's MonthlyCharges / TotalCharges currency remains unspecified."
)
_SCENARIO_DISCLOSURE = (
    "This is a deterministic scenario calculation under supplied assumptions. "
    "It is not a forecast, approval, or authorization to contact customers."
)
_FIXED_INPUT_DISCLOSURE = (
    "For this demo, pilot population, intervention cost, and retained-customer "
    "value are fixed scenario inputs. The human revision changes expected lift."
)
_UNCHANGED_EXPLANATION = (
    "The human changed a scenario assumption. The underlying observed dataset, "
    "Evidence IDs, findings, data-health result, and source provenance did not "
    "change."
)

_EVIDENCE_LABELS = {
    "business_overall_churn": "Overall recorded churn",
    "business_contract_churn": "Contract-group recorded churn",
    "business_support_churn": "Tech-support recorded churn",
    "business_internet_churn": "Internet-service recorded churn",
    "business_payment_churn": "Payment-method recorded churn",
    "business_churn_medians": "Churn-status medians",
    "business_parseability": "TotalCharges parseability",
}
_POSTURE_LABELS = {
    ExecutiveScenarioPosture.LIMITED_PILOT_REVIEW_CANDIDATE: (
        "Limited pilot review candidate"
    ),
    ExecutiveScenarioPosture.VALIDATE_SCENARIO_ASSUMPTIONS_FIRST: (
        "Validate scenario assumptions first"
    ),
    SalesPilotPosture.ELIGIBLE_FOR_PILOT_REVIEW: "Eligible for pilot review",
    SalesPilotPosture.BLOCKED_BY_SCENARIO: "Blocked by scenario",
    ProjectManagerHandoff.PREPARE_LIMITED_PILOT_REVIEW: (
        "Prepare limited pilot review"
    ),
    ProjectManagerHandoff.REOPEN_SCENARIO_VALIDATION: (
        "Reopen scenario validation"
    ),
}
_IMPACT_OBJECT_LABELS = {
    "obj-break-even": "Break-even Scenario",
    "obj-executive-posture": "Executive scenario posture",
    "obj-sales-posture": "Sales pilot posture",
    "obj-pm-handoff": "Project Manager handoff",
    "obj-decision-brief": "Current Decision Brief",
}
_ASSUMPTION_LABELS = {
    "pilot_population": "Pilot population",
    "expected_incremental_lift": "Expected incremental lift",
    "cost_per_intervention": "Cost per intervention",
    "retained_customer_value": "Retained customer value",
}


def _load_ibm_telco_inputs() -> demo_pipeline.PreparedDemoInputs:
    """Read the frozen public files and prepare real product Evidence offline."""
    context = json.loads(_PUBLIC_CONTEXT.read_text(encoding="utf-8"))
    return demo_pipeline.prepare_demo_inputs(
        csv_bytes=_PUBLIC_CSV.read_bytes(),
        filename=_PUBLIC_CSV.name,
        industry_context=context["dataset_context"],
        strategy_profile=context["strategy_profile"],
        business_question=context["business_question"],
        decision_goal=context["decision_goal"],
        user_assumption=context["user_assumption"],
        business_profile_id="ibm_telco_churn_v1",
    )


def _scenario_assumptions(
    revision_id: str,
    expected_lift: Decimal,
) -> tuple[ScenarioAssumption, ...]:
    """Construct the four fixed Hero assumptions with stable logical IDs."""
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
            value=expected_lift,
            unit="fraction",
            currency=None,
        ),
        ScenarioAssumption(
            assumption_id="asm-003",
            revision_id=revision_id,
            key="cost_per_intervention",
            value=Decimal("30"),
            unit="currency_per_customer",
            currency="USD",
        ),
        ScenarioAssumption(
            assumption_id="asm-004",
            revision_id=revision_id,
            key="retained_customer_value",
            value=Decimal("500"),
            unit="currency_per_customer",
            currency="USD",
        ),
    )


def _baseline_scenario() -> ScenarioResult:
    """Calculate the fixed 8% baseline through the existing DD-1 contract."""
    return decision_diff.calculate_break_even_scenario(
        _scenario_assumptions("rev-001", Decimal("0.08")),
        scenario_id="scn-001",
        revision_id="rev-001",
    )


def _build_revision(
    prepared: demo_pipeline.PreparedDemoInputs,
    after_lift: Decimal,
) -> RoleLensDecisionRevision:
    """Build a real rev-001 to rev-002 product revision only through DD-3."""
    if prepared.business_profile is None:
        raise decision_diff_rolelens.RoleLensDecisionDiffError(
            "The approved business profile is unavailable."
        )
    return decision_diff_rolelens.build_rolelens_decision_revision(
        business_profile=prepared.business_profile,
        evidence_objects=prepared.evidence_objects,
        data_health_summary=prepared.data_health_summary,
        source_manifests=prepared.source_manifests,
        before_assumptions=_scenario_assumptions("rev-001", Decimal("0.08")),
        after_assumptions=_scenario_assumptions("rev-002", after_lift),
        scenario_id="scn-001",
        before_revision_id="rev-001",
        after_revision_id="rev-002",
    )


def _format_count(value: int | Decimal) -> str:
    """Format an integral count without converting scenario values to float."""
    return f"{Decimal(value):,.0f}"


def _format_percent(value: Decimal, *, places: int = 1) -> str:
    """Format a fractional Decimal as a human-readable percentage."""
    percent = value * Decimal("100")
    return f"{percent:.{places}f}%"


def _format_money(value: Decimal, *, signed: bool = False) -> str:
    """Format a scenario currency value with an optional explicit sign."""
    if signed:
        return f"{value:+,.0f} USD"
    return f"{value:,.0f} USD"


def _status_label(status: ScenarioStatus) -> str:
    """Map a scenario status to approved plain product language."""
    if status is ScenarioStatus.CLEARS_BREAK_EVEN:
        return "Clears modeled break-even"
    if status is ScenarioStatus.DOES_NOT_CLEAR_BREAK_EVEN:
        return "Does not clear modeled break-even"
    return "Scenario is not evaluable"


def _baseline_rows(result: ScenarioResult) -> tuple[dict[str, str], ...]:
    """Return the exact baseline display values from a DD-1 result."""
    if any(
        value is None
        for value in (
            result.expected_incremental_retained,
            result.expected_scenario_value,
            result.intervention_cost,
            result.net_scenario_value,
            result.break_even_lift,
        )
    ):
        return ()
    return (
        {
            "label": "Expected incremental retained",
            "value": _format_count(result.expected_incremental_retained),
        },
        {
            "label": "Expected scenario value",
            "value": _format_money(result.expected_scenario_value),
        },
        {
            "label": "Intervention cost",
            "value": _format_money(result.intervention_cost),
        },
        {
            "label": "Net scenario value",
            "value": _format_money(result.net_scenario_value, signed=True),
        },
        {
            "label": "Modeled break-even lift",
            "value": _format_percent(result.break_even_lift, places=0),
        },
    )


def _revision_state(revision: RoleLensDecisionRevision) -> str:
    """Classify a revision from its structured assumption and posture results."""
    changed_assumptions = revision.decision_diff.changed_assumptions
    impacts_changed = any(
        item.impact_type is not DecisionImpactType.UNCHANGED
        for item in revision.decision_diff.impacts
    )
    if not changed_assumptions and not impacts_changed:
        return "unchanged"
    before = revision.before_projection
    after = revision.after_projection
    if (
        before.scenario_result.status is not after.scenario_result.status
        or before.executive_posture is not after.executive_posture
        or before.sales_posture is not after.sales_posture
        or before.project_manager_handoff is not after.project_manager_handoff
    ):
        return "posture_changed"
    return "scenario_changed"


def _headline(revision: RoleLensDecisionRevision) -> str:
    """Return the exact headline for the revision's structured state."""
    return {
        "posture_changed": "Decision posture changed",
        "scenario_changed": "Scenario changed; decision posture remains the same",
        "unchanged": "No scenario assumption changed",
    }[_revision_state(revision)]


def _decision_diff_headings(
    revision: RoleLensDecisionRevision,
) -> tuple[str, str, str]:
    """Return the exact headline, impact heading, and explanation heading."""
    state = _revision_state(revision)
    return {
        "posture_changed": (
            "Decision posture changed",
            "What must be reconsidered",
            "Why did the decision posture change?",
        ),
        "scenario_changed": (
            "Scenario changed; decision posture remains the same",
            "What was recomputed",
            "Why was the scenario recomputed?",
        ),
        "unchanged": (
            "No scenario assumption changed",
            "Decision impact",
            "Why did nothing change?",
        ),
    }[state]


def _before_after_rows(
    revision: RoleLensDecisionRevision,
    after_lift: Decimal,
) -> tuple[dict[str, str], ...]:
    """Create the compact before/after table from validated DD-3 outputs."""
    before = revision.before_projection
    after = revision.after_projection
    before_result = before.scenario_result
    after_result = after.scenario_result
    values = (
        (
            "Expected lift",
            _format_percent(Decimal("0.08")),
            _format_percent(after_lift),
        ),
        (
            "Expected incremental retained",
            _format_count(before_result.expected_incremental_retained),
            _format_count(after_result.expected_incremental_retained),
        ),
        (
            "Expected scenario value",
            _format_money(before_result.expected_scenario_value),
            _format_money(after_result.expected_scenario_value),
        ),
        (
            "Intervention cost",
            _format_money(before_result.intervention_cost),
            _format_money(after_result.intervention_cost),
        ),
        (
            "Net scenario value",
            _format_money(before_result.net_scenario_value, signed=True),
            _format_money(after_result.net_scenario_value, signed=True),
        ),
        (
            "Break-even",
            _status_label(before_result.status),
            _status_label(after_result.status),
        ),
        (
            "Executive scenario posture",
            _POSTURE_LABELS[before.executive_posture],
            _POSTURE_LABELS[after.executive_posture],
        ),
        (
            "Sales pilot posture",
            _POSTURE_LABELS[before.sales_posture],
            _POSTURE_LABELS[after.sales_posture],
        ),
        (
            "Project Manager handoff",
            _POSTURE_LABELS[before.project_manager_handoff],
            _POSTURE_LABELS[after.project_manager_handoff],
        ),
    )
    return tuple(
        {"Row": label, "Before": before_value, "After": after_value}
        for label, before_value, after_value in values
    )


def _impact_display(impact: DecisionImpact) -> str:
    """Map one actual DD-2 impact to concise UI language."""
    if (
        impact.object_id == "obj-decision-brief"
        and impact.impact_type is DecisionImpactType.STALE
    ):
        return "Stale — would need refresh"
    return {
        DecisionImpactType.UNCHANGED: "Unchanged",
        DecisionImpactType.RECOMPUTED: "Recomputed",
        DecisionImpactType.INVALIDATED: "Invalidated",
        DecisionImpactType.BLOCKED: "Blocked",
        DecisionImpactType.STALE: "Stale",
    }[impact.impact_type]


def _affected_output_rows(
    revision: RoleLensDecisionRevision,
) -> tuple[dict[str, str], ...]:
    """Show only registered downstream outputs using actual DD-2 impacts."""
    impacts = {item.object_id: item for item in revision.decision_diff.impacts}
    return tuple(
        {
            "Output": label,
            "Impact": _impact_display(impacts[object_id]),
        }
        for object_id, label in _IMPACT_OBJECT_LABELS.items()
    )


def _unchanged_rows(
    revision: RoleLensDecisionRevision,
) -> tuple[dict[str, str], ...]:
    """Show the actual unchanged DD-3 foundation impacts."""
    impacts = {item.object_id: item for item in revision.decision_diff.impacts}
    count = len(revision.evidence_basis.business_evidence)
    observed = _impact_display(impacts["obj-observed-evidence"])
    health = _impact_display(impacts["obj-data-health"])
    provenance = _impact_display(impacts["obj-source-provenance"])
    return (
        {
            "Foundation": "Observed business Evidence",
            "Result": f"{observed} — {count} Evidence Objects",
        },
        {"Foundation": "Data Health", "Result": health},
        {"Foundation": "Source provenance", "Result": provenance},
    )


def _short_finding(finding: str, limit: int = 160) -> str:
    """Return a compact single-line finding without exposing snapshot JSON."""
    compact = " ".join(finding.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1].rstrip() + "…"


def _evidence_rows(
    prepared: demo_pipeline.PreparedDemoInputs,
) -> tuple[dict[str, str], ...]:
    """Select exactly the seven compact DD-3 business Evidence rows."""
    rows: list[dict[str, str]] = []
    for evidence_type in _EVIDENCE_LABELS:
        matches = [
            item
            for item in prepared.evidence_objects
            if item.evidence_type == evidence_type
        ]
        if len(matches) != 1:
            raise ValueError("The observed business Evidence basis is incomplete.")
        item = matches[0]
        rows.append(
            {
                "evidence_type": item.evidence_type,
                "evidence_id": item.evidence_id,
                "short finding": _short_finding(item.finding),
            }
        )
    return tuple(rows)


def _changed_value(change: Any, value: Decimal) -> str:
    """Format one changed assumption using its declared scenario key."""
    if change.key == "expected_incremental_lift":
        return _format_percent(value)
    if change.key == "pilot_population":
        return f"{_format_count(value)} customers"
    if change.currency is not None:
        return f"{value:,.0f} {change.currency}"
    return str(value)


def _change_explanation(revision: RoleLensDecisionRevision) -> str:
    """Explain propagation from actual changes and registered trigger refs."""
    changed = revision.decision_diff.changed_assumptions
    if not changed:
        return (
            "No scenario assumption value changed. No registered dependency was "
            "triggered, so every registered impact remained unchanged."
        )
    change_sentences = [
        (
            f"{_ASSUMPTION_LABELS[item.key]} changed from "
            f"{_changed_value(item, item.before_value)} to "
            f"{_changed_value(item, item.after_value)}."
        )
        for item in changed
    ]
    impacts = {item.object_id: item for item in revision.decision_diff.impacts}
    break_even = impacts["obj-break-even"]
    changed_ids = {item.assumption_id for item in changed}
    if changed_ids.intersection(break_even.trigger_refs):
        change_sentences.append(
            "The Break-even Scenario depends directly on that human assumption."
        )
    downstream = (
        impacts["obj-executive-posture"],
        impacts["obj-sales-posture"],
        impacts["obj-pm-handoff"],
    )
    if any(item.trigger_refs for item in downstream):
        change_sentences.append(
            "Downstream scenario postures were then recomputed through the "
            "registered dependency chain."
        )
    if _revision_state(revision) == "scenario_changed":
        change_sentences.append(
            "The recalculated scenario still clears modeled break-even, and the "
            "resulting business postures remained logically the same."
        )
    return " ".join(change_sentences)


def _clear_revision(state: MutableMapping[str, Any]) -> None:
    """Remove every stored revision artifact so stale output cannot render."""
    state.pop(_SK_REVISION, None)
    state.pop(_SK_REVISION_LIFT, None)


def _store_loaded_inputs(
    state: MutableMapping[str, Any],
    prepared: demo_pipeline.PreparedDemoInputs,
) -> None:
    """Store RoleLens-owned preparation state and reset the Hero revision."""
    state[_SK_PREPARED] = prepared
    state[_SK_LIFT_WIDGET] = 8.0
    _clear_revision(state)


def _calculate_and_store_revision(
    state: MutableMapping[str, Any],
    prepared: demo_pipeline.PreparedDemoInputs,
    after_lift_pct: Decimal,
) -> RoleLensDecisionRevision:
    """Clear stale output, build safely, and store only a successful revision."""
    _clear_revision(state)
    after_lift = after_lift_pct / Decimal("100")
    revision = _build_revision(prepared, after_lift)
    state[_SK_REVISION] = revision
    state[_SK_REVISION_LIFT] = after_lift_pct
    return revision


def _invalidate_streamlit_revision() -> None:
    """Streamlit widget callback that invalidates a prior displayed revision."""
    import streamlit as st

    _clear_revision(st.session_state)


def _render_observed(st: Any, prepared: demo_pipeline.PreparedDemoInputs) -> None:
    """Render locked observed facts and the compact seven-item Evidence basis."""
    profile = prepared.business_profile
    if profile is None:
        st.error("IBM Telco evidence could not be loaded safely.")
        return
    contract_rate = next(
        item.churn_rate_pct
        for item in profile.contract_rates
        if item.segment == "Month-to-month"
    )
    st.info("1. Observed Evidence — locked")
    columns = st.columns(4)
    columns[0].metric("Customers", f"{profile.unique_customer_count:,}")
    columns[1].metric(
        "Recorded churn rate",
        f"{profile.overall_churn_rate_pct:.2f}%",
    )
    columns[2].metric(
        "Month-to-month recorded churn",
        f"{contract_rate:.2f}%",
    )
    columns[3].metric(
        "TotalCharges parse issues",
        f"{profile.total_charges_parse_issue_count:,}",
    )
    st.caption(_DATASET_DISCLOSURE)
    st.caption(
        "These are observed dataset facts. Changing a scenario assumption below "
        "does not rewrite them."
    )


def _render_evidence_expander(
    st: Any,
    prepared: demo_pipeline.PreparedDemoInputs,
) -> None:
    """Render the compact observed Evidence table and mandatory boundary text."""
    with st.expander("View unchanged Evidence basis"):
        st.dataframe(
            _evidence_rows(prepared),
            hide_index=True,
            use_container_width=True,
        )
        st.caption(_EVIDENCE_CONTEXT_CAPTION)


def _render_assumptions(st: Any) -> None:
    """Render all four visibly user-supplied baseline assumptions."""
    st.info("2. Human-supplied Scenario Assumptions")
    columns = st.columns(4)
    columns[0].metric(
        "Pilot population — User-supplied scenario assumption",
        "500 customers",
    )
    columns[1].metric(
        "Expected incremental lift — User-supplied scenario assumption",
        "8.0%",
    )
    columns[2].metric(
        "Cost per intervention — User-supplied scenario assumption",
        "30 USD",
    )
    columns[3].metric(
        "Retained customer value — User-supplied scenario assumption",
        "500 USD",
    )
    st.caption(_CURRENCY_NOTICE)
    st.caption(_DATASET_CURRENCY_NOTICE)


def _render_baseline(st: Any, result: ScenarioResult) -> None:
    """Render the baseline result calculated by DD-1."""
    st.info("Baseline Scenario")
    rows = _baseline_rows(result)
    first = st.columns(3)
    second = st.columns(2)
    for column, row in zip((*first, *second), rows):
        column.metric(row["label"], row["value"])
    if result.status is ScenarioStatus.CLEARS_BREAK_EVEN:
        st.success(_status_label(result.status))
    else:
        st.warning(_status_label(result.status))
    st.caption(_SCENARIO_DISCLOSURE)


def _render_revision_input(
    st: Any,
    prepared: demo_pipeline.PreparedDemoInputs,
) -> tuple[RoleLensDecisionRevision | None, Decimal | None]:
    """Render the one editable field and transactionally build a revision."""
    st.info("3. Human Revision")
    st.caption("Change one assumption and recalculate.")
    st.caption(_FIXED_INPUT_DISCLOSURE)
    st.session_state.setdefault(_SK_LIFT_WIDGET, 8.0)
    edited_value = st.number_input(
        "Expected incremental lift (%) — User-supplied scenario assumption",
        min_value=0.0,
        max_value=100.0,
        step=1.0,
        key=_SK_LIFT_WIDGET,
        on_change=_invalidate_streamlit_revision,
    )
    fixed = st.columns(3)
    fixed[0].metric(
        "Pilot population — User-supplied scenario assumption",
        "500 customers",
    )
    fixed[1].metric(
        "Cost per intervention — User-supplied scenario assumption",
        "30 USD",
    )
    fixed[2].metric(
        "Retained customer value — User-supplied scenario assumption",
        "500 USD",
    )
    after_lift_pct = Decimal(str(edited_value))
    stored_lift = st.session_state.get(_SK_REVISION_LIFT)
    if stored_lift is not None and Decimal(str(stored_lift)) != after_lift_pct:
        _clear_revision(st.session_state)

    revision = st.session_state.get(_SK_REVISION)
    if st.button("Recalculate decision", type="primary"):
        try:
            revision = _calculate_and_store_revision(
                st.session_state,
                prepared,
                after_lift_pct,
            )
        except Exception:
            _clear_revision(st.session_state)
            revision = None
            st.error("Decision revision could not be calculated safely.")
    revision_lift = st.session_state.get(_SK_REVISION_LIFT)
    return revision, (
        Decimal(str(revision_lift)) / Decimal("100")
        if revision is not None and revision_lift is not None
        else None
    )


def _render_decision_diff(
    st: Any,
    revision: RoleLensDecisionRevision,
    after_lift: Decimal,
) -> None:
    """Render the vertical Decision Diff story from validated DD-3 output."""
    st.info("4. Decision Diff")
    headline, impact_heading, explanation_heading = _decision_diff_headings(revision)
    if headline == "Decision posture changed":
        st.warning(headline)
    elif headline == "No scenario assumption changed":
        st.info(headline)
    else:
        st.success(headline)
    st.dataframe(
        _before_after_rows(revision, after_lift),
        hide_index=True,
        use_container_width=True,
    )

    st.info(impact_heading)
    st.dataframe(
        _affected_output_rows(revision),
        hide_index=True,
        use_container_width=True,
    )
    st.caption(
        "The current Decision Brief is not regenerated here. A stale brief would "
        "need refresh."
    )

    st.info("What did not change")
    st.dataframe(
        _unchanged_rows(revision),
        hide_index=True,
        use_container_width=True,
    )
    st.dataframe(
        tuple({"Observed business Evidence": label} for label in _EVIDENCE_LABELS.values()),
        hide_index=True,
        use_container_width=True,
    )
    st.success("Observed Evidence remained unchanged.")
    st.caption(_UNCHANGED_EXPLANATION)

    st.info(explanation_heading)
    st.caption(_change_explanation(revision))


def main() -> None:
    """Render the standalone, provider-free RoleLens Decision Lab page."""
    import streamlit as st

    st.title("RoleLens Decision Lab")
    st.caption(_TAGLINE)
    st.caption(_PROCESS_CAPTION)

    prepared = st.session_state.get(_SK_PREPARED)
    if prepared is None:
        load_clicked = st.button("Load IBM Telco evidence", type="primary")
        st.caption(_DATASET_DISCLOSURE)
        if not load_clicked:
            return
        try:
            prepared = _load_ibm_telco_inputs()
            _store_loaded_inputs(st.session_state, prepared)
        except Exception:
            st.error("IBM Telco evidence could not be loaded safely.")
            return

    try:
        baseline = _baseline_scenario()
    except Exception:
        st.error("Baseline scenario could not be calculated safely.")
        return

    _render_observed(st, prepared)
    try:
        _render_evidence_expander(st, prepared)
    except Exception:
        st.error("Observed Evidence basis could not be prepared safely.")
        return
    _render_assumptions(st)
    _render_baseline(st, baseline)
    revision, revision_lift = _render_revision_input(st, prepared)
    if revision is not None and revision_lift is not None:
        _render_decision_diff(st, revision, revision_lift)


if __name__ == "__main__":
    main()
