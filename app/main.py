"""Product-first Streamlit surface for the governed RoleLens demo.

Normal import defines helpers only.  It does not render Streamlit, read
credentials, construct providers, or call the network.  Only the explicit
``Run with IBM Granite`` button invokes live analysis.
"""

from __future__ import annotations

import json
import os
import pathlib
from collections.abc import Mapping, MutableMapping
from typing import Any

import pandas as pd
import streamlit as st

from app.dataset_orientation import (
    DatasetOrientationBrief,
    DatasetOrientationFailure,
    build_dataset_primer,
)
from app.demo_pipeline import (
    DemoAnalysisResult,
    DemoPipelineError,
    PreparedDemoInputs,
    _safe_role_failure_reason,
    prepare_demo_inputs,
    run_live_demo_analysis,
)
from app.human_review import HumanReviewInputError, review_workflow_plan
from app.memo_generator import DecisionMemoInputError, compose_decision_memo
from app.product_view import (
    build_action_plan_summary,
    build_decision_brief,
    build_memo_summary,
    build_role_comparison,
)
from app.role_engine import InsufficientEvidence, RoleGenerationFailure
from app.schemas import (
    EvidenceScope,
    HumanReviewDecision,
    HumanReviewSession,
    HumanReviewStepInput,
    RoleKey,
    RoleView,
    WorkflowPlan,
    WorkflowStepKind,
    WorkflowStepStatus,
)


# Explicit source modes.
DEMO_SOURCE_NONE = "none"
DEMO_SOURCE_IBM_TELCO = "ibm_telco"
DEMO_SOURCE_CUSTOM = "custom"
DEMO_SOURCE_SYNTHETIC_FIXTURE = "synthetic_fixture"
DEMO_SOURCE_MODES = frozenset(
    {
        DEMO_SOURCE_NONE,
        DEMO_SOURCE_IBM_TELCO,
        DEMO_SOURCE_CUSTOM,
        DEMO_SOURCE_SYNTHETIC_FIXTURE,
    }
)

_ROOT = pathlib.Path(__file__).parent.parent
_SAMPLE_DATA_DIR = _ROOT / "sample_data"
_IBM_CSV_PATH = _SAMPLE_DATA_DIR / "public" / "ibm_telco_customer_churn.csv"
_IBM_CONTEXT_PATH = (
    _SAMPLE_DATA_DIR / "public" / "ibm_telco_customer_churn_context.json"
)
_DEMO_CSV_PATH = _SAMPLE_DATA_DIR / "b2b_saas_retention_demo.csv"
_DEMO_JSON_PATH = _SAMPLE_DATA_DIR / "b2b_saas_retention_demo.json"

_IBM_PROFILE_ID = "ibm_telco_churn_v1"
_IBM_SOURCE_LABEL = "IBM Telco public demo"
_SYNTHETIC_SOURCE_LABEL = "Synthetic B2B SaaS QA fixture"

_SK_PREPARED = "rolelens_prepared_inputs"
_SK_ANALYSIS = "rolelens_analysis_result"
_SK_REVIEW_SESSION = "rolelens_review_session"
_SK_MEMO = "rolelens_decision_memo"
_SK_REVIEW_PRESET_LOADED = "rolelens_review_preset_loaded"
_SK_SOURCE_LABEL = "rolelens_source_label"

_CONTEXT_WIDGET_KEYS = (
    "field_industry_context",
    "field_strategy_profile",
    "field_business_question",
    "field_decision_goal",
    "field_user_assumption",
)
_REVIEW_WIDGET_PREFIXES = (
    "review_decision_",
    "review_note_",
    "review_revised_",
)
_ROLE_DISPLAY = {
    RoleKey.executive: "Executive",
    RoleKey.data_analyst: "Data Analyst / Data Scientist",
    RoleKey.data_engineer: "Data Engineer",
    RoleKey.sales_marketing: "Sales / Marketing",
    RoleKey.project_manager: "Project Manager",
}
_ROLE_DISPLAY_ORDER = tuple(_ROLE_DISPLAY)


def _configured() -> bool:
    """Return whether all required watsonx.ai variables are non-blank."""
    required = ("WATSONX_APIKEY", "WATSONX_URL", "WATSONX_PROJECT_ID")
    return all(os.environ.get(key, "").strip() for key in required)


def _load_json(path: pathlib.Path) -> dict[str, Any]:
    """Load a local JSON object, returning an empty object on failure."""
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _load_sample_data() -> dict[str, Any]:
    """Load the synthetic QA sidecar."""
    return _load_json(_DEMO_JSON_PATH)


def _load_ibm_context() -> dict[str, Any]:
    """Load the frozen IBM Telco public context sidecar."""
    return _load_json(_IBM_CONTEXT_PATH)


def _initialize_demo_widget_state(state: MutableMapping[str, Any]) -> None:
    """Initialize source and editable context widget state."""
    for key in _CONTEXT_WIDGET_KEYS:
        state.setdefault(key, "")
    mode = state.setdefault("demo_source_mode", DEMO_SOURCE_NONE)
    if mode not in DEMO_SOURCE_MODES:
        state["demo_source_mode"] = DEMO_SOURCE_NONE


def _clear_review_widget_state(state: MutableMapping[str, Any]) -> None:
    """Clear only RoleLens review preset and per-step widget keys."""
    for key in list(state):
        if (
            key in {"demo_review_preset", _SK_REVIEW_PRESET_LOADED}
            or any(key.startswith(prefix) for prefix in _REVIEW_WIDGET_PREFIXES)
        ):
            del state[key]


def _invalidate_prepared_demo_state(state: MutableMapping[str, Any]) -> None:
    """Clear prepared and downstream RoleLens state after input changes."""
    _clear_review_widget_state(state)
    for key in (_SK_PREPARED, _SK_ANALYSIS, _SK_REVIEW_SESSION, _SK_MEMO):
        state.pop(key, None)


def _invalidate_prepared_demo_session_state() -> None:
    """Invalidate prepared state from a Streamlit widget callback."""
    _invalidate_prepared_demo_state(st.session_state)


def _write_context_fields(
    values: Mapping[str, Any],
    state: MutableMapping[str, Any],
    *,
    industry_source_key: str,
) -> None:
    """Copy exact sidecar context values into their widget keys."""
    source_to_widget = {
        industry_source_key: "field_industry_context",
        "strategy_profile": "field_strategy_profile",
        "business_question": "field_business_question",
        "decision_goal": "field_decision_goal",
        "user_assumption": "field_user_assumption",
    }
    for source_key, widget_key in source_to_widget.items():
        value = values.get(source_key, "")
        state[widget_key] = value if isinstance(value, str) else ""


def _apply_ibm_telco_sample(
    context: Mapping[str, Any],
    state: MutableMapping[str, Any],
) -> None:
    """Select IBM mode and populate context without preparing or calling AI."""
    _invalidate_prepared_demo_state(state)
    state.pop("csv_uploader", None)
    _write_context_fields(
        context,
        state,
        industry_source_key="dataset_context",
    )
    state["demo_source_mode"] = DEMO_SOURCE_IBM_TELCO
    state[_SK_SOURCE_LABEL] = _IBM_SOURCE_LABEL


def _apply_synthetic_sample(
    sample: Mapping[str, Any],
    state: MutableMapping[str, Any],
) -> None:
    """Select the QA fixture and populate its existing context fields."""
    _invalidate_prepared_demo_state(state)
    state.pop("csv_uploader", None)
    _write_context_fields(
        sample,
        state,
        industry_source_key="industry_context",
    )
    state["demo_source_mode"] = DEMO_SOURCE_SYNTHETIC_FIXTURE
    state[_SK_SOURCE_LABEL] = _SYNTHETIC_SOURCE_LABEL


def _handle_csv_uploader_change() -> None:
    """Select custom mode for an upload, or none after it is cleared."""
    previous_mode = st.session_state.get(
        "demo_source_mode",
        DEMO_SOURCE_NONE,
    )
    uploaded_file = st.session_state.get("csv_uploader")
    if uploaded_file is None:
        st.session_state["demo_source_mode"] = DEMO_SOURCE_NONE
        st.session_state.pop(_SK_SOURCE_LABEL, None)
    else:
        if previous_mode in {
            DEMO_SOURCE_IBM_TELCO,
            DEMO_SOURCE_SYNTHETIC_FIXTURE,
        }:
            for key in _CONTEXT_WIDGET_KEYS:
                st.session_state[key] = ""
        st.session_state["demo_source_mode"] = DEMO_SOURCE_CUSTOM
        filename = getattr(uploaded_file, "name", "")
        safe_name = filename if isinstance(filename, str) and filename else "CSV"
        st.session_state[_SK_SOURCE_LABEL] = f"Custom upload: {safe_name}"
    _invalidate_prepared_demo_state(st.session_state)


def _resolve_demo_source(
    source_mode: str,
    uploaded_file: Any,
) -> tuple[bytes, str, str | None, str]:
    """Resolve one explicit source to bytes, filename, profile, and label."""
    if source_mode == DEMO_SOURCE_IBM_TELCO:
        if not _IBM_CSV_PATH.is_file():
            raise ValueError("IBM Telco public demo CSV is unavailable.")
        return (
            _IBM_CSV_PATH.read_bytes(),
            _IBM_CSV_PATH.name,
            _IBM_PROFILE_ID,
            _IBM_SOURCE_LABEL,
        )
    if source_mode == DEMO_SOURCE_SYNTHETIC_FIXTURE:
        if not _DEMO_CSV_PATH.is_file():
            raise ValueError("Synthetic QA fixture CSV is unavailable.")
        return (
            _DEMO_CSV_PATH.read_bytes(),
            _DEMO_CSV_PATH.name,
            None,
            _SYNTHETIC_SOURCE_LABEL,
        )
    if source_mode == DEMO_SOURCE_CUSTOM:
        if uploaded_file is None:
            raise ValueError("No custom CSV upload is selected.")
        try:
            csv_bytes = uploaded_file.getvalue()
            filename = uploaded_file.name
        except Exception:
            raise ValueError("Uploaded CSV could not be read.") from None
        if not isinstance(csv_bytes, bytes) or not isinstance(filename, str):
            raise ValueError("Uploaded CSV is invalid.")
        return csv_bytes, filename, None, f"Custom upload: {filename}"
    if source_mode == DEMO_SOURCE_NONE:
        raise ValueError("No CSV source is selected.")
    raise ValueError("Demo source mode is invalid.")


def _prepare_demo_inputs_transaction(
    state: MutableMapping[str, Any],
    *,
    csv_bytes: bytes,
    filename: str,
    industry_context: str,
    strategy_profile: str,
    business_question: str,
    decision_goal: str,
    user_assumption: str | None,
    business_profile_id: str | None,
    source_label: str,
) -> PreparedDemoInputs:
    """Prepare first, then atomically replace prepared/downstream state."""
    prepared = prepare_demo_inputs(
        csv_bytes=csv_bytes,
        filename=filename,
        industry_context=industry_context,
        strategy_profile=strategy_profile,
        business_question=business_question,
        decision_goal=decision_goal,
        user_assumption=user_assumption,
        business_profile_id=business_profile_id,
    )
    state[_SK_PREPARED] = prepared
    state[_SK_SOURCE_LABEL] = source_label
    _clear_review_widget_state(state)
    for key in (_SK_ANALYSIS, _SK_REVIEW_SESSION, _SK_MEMO):
        state.pop(key, None)
    return prepared


def _run_live_demo_analysis_transaction(
    state: MutableMapping[str, Any],
    prepared: PreparedDemoInputs,
) -> DemoAnalysisResult:
    """Run live analysis first, then replace analysis/downstream state."""
    analysis = run_live_demo_analysis(prepared)
    state[_SK_ANALYSIS] = analysis
    _clear_review_widget_state(state)
    for key in (_SK_REVIEW_SESSION, _SK_MEMO):
        state.pop(key, None)
    return analysis


def _reset_rolelens_state() -> None:
    """Clear only RoleLens-owned and RoleLens widget session keys."""
    _invalidate_prepared_demo_state(st.session_state)
    keys = (
        *_CONTEXT_WIDGET_KEYS,
        "demo_source_mode",
        "csv_uploader",
        _SK_SOURCE_LABEL,
        "review_note_no_action",
    )
    for key in keys:
        st.session_state.pop(key, None)


def _build_synthetic_review_preset(
    workflow_plan: WorkflowPlan,
) -> dict[str, dict[str, str]]:
    """Build deterministic editable controls from typed workflow fields."""
    if type(workflow_plan) is not WorkflowPlan:
        raise HumanReviewInputError("workflow_plan must be exactly a WorkflowPlan")
    non_gate_steps = [
        step
        for step in workflow_plan.steps
        if step.step_kind is not WorkflowStepKind.semantic_review_gate
    ]
    revision_step = next(
        (
            step
            for step in non_gate_steps
            if not step.blocks_downstream
            and step.status is not WorkflowStepStatus.blocked
        ),
        non_gate_steps[0] if non_gate_steps else None,
    )
    rejection_step = next(
        (
            step
            for step in reversed(workflow_plan.steps)
            if step.step_kind is WorkflowStepKind.role_action
            and step is not revision_step
            and (revision_step is None or step.sequence > revision_step.sequence)
        ),
        None,
    )
    preset: dict[str, dict[str, str]] = {}
    for step in workflow_plan.steps:
        if step.step_kind is WorkflowStepKind.semantic_review_gate:
            decision = "accept"
            note = "Semantic candidates reviewed as probabilistic and non-authoritative."
            revised_action = ""
        elif step is revision_step:
            decision = "revise"
            note = "Synthetic revision requires evidence revalidation."
            revised_action = (
                f"Revalidate synthetic step {step.sequence} for "
                f"{step.owner_role.value} before downstream use."
            )
        elif step is rejection_step:
            decision = "reject"
            note = "Synthetic downstream role action rejected pending review."
            revised_action = ""
        else:
            decision = "accept"
            note = (
                "Blocking status acknowledged without clearing the blocker."
                if step.blocks_downstream
                else ""
            )
            revised_action = ""
        preset[step.step_id] = {
            "decision": decision,
            "reviewer_note": note,
            "revised_action": revised_action,
        }
    return preset


def _apply_synthetic_review_preset(
    workflow_plan: WorkflowPlan,
    state: MutableMapping[str, Any],
) -> None:
    """Populate editable review widgets without recording any review."""
    preset = _build_synthetic_review_preset(workflow_plan)
    state["demo_review_preset"] = preset
    state[_SK_REVIEW_PRESET_LOADED] = True
    for step_id, control in preset.items():
        state[f"review_decision_{step_id}"] = control["decision"]
        state[f"review_note_{step_id}"] = control["reviewer_note"]
        state[f"review_revised_{step_id}"] = control["revised_action"]


def _build_human_review_inputs(
    workflow_plan: WorkflowPlan,
    raw_controls: Mapping[str, Mapping[str, Any]],
) -> dict[str, HumanReviewStepInput]:
    """Build exact typed review inputs or raise a sanitized public error."""
    if type(workflow_plan) is not WorkflowPlan:
        raise HumanReviewInputError("workflow_plan must be exactly a WorkflowPlan")
    if not isinstance(raw_controls, Mapping):
        raise HumanReviewInputError("Review controls must be a mapping.")
    plan_step_ids = tuple(step.step_id for step in workflow_plan.steps)
    if any(not isinstance(key, str) for key in raw_controls) or set(
        raw_controls
    ) != set(plan_step_ids):
        raise HumanReviewInputError("Review controls must match workflow plan steps.")

    inputs: dict[str, HumanReviewStepInput] = {}
    for step in workflow_plan.steps:
        control = raw_controls[step.step_id]
        if not isinstance(control, Mapping):
            raise HumanReviewInputError(f"Review controls are invalid for step {step.step_id}.")
        raw_decision = control.get("decision")
        decision = raw_decision.value if isinstance(raw_decision, HumanReviewDecision) else raw_decision
        if decision not in {"accept", "reject", "revise"}:
            raise HumanReviewInputError(f"A review decision is required for step {step.step_id}.")
        note = control.get("reviewer_note") or None
        revised = control.get("revised_action") or None
        if note is not None and (not isinstance(note, str) or not note.strip()):
            raise HumanReviewInputError(f"Reviewer note is invalid for step {step.step_id}.")
        if revised is not None and (not isinstance(revised, str) or not revised.strip()):
            raise HumanReviewInputError(f"Revised action is invalid for step {step.step_id}.")
        is_gate = step.step_kind is WorkflowStepKind.semantic_review_gate
        if is_gate and decision == "revise":
            raise HumanReviewInputError(f"Semantic review gate {step.step_id} cannot be revised.")
        if (is_gate or decision in {"reject", "revise"}) and note is None:
            raise HumanReviewInputError(f"Reviewer note is required for step {step.step_id}.")
        if decision == "revise" and (revised is None or revised == step.action):
            raise HumanReviewInputError(f"A distinct revised action is required for step {step.step_id}.")
        try:
            inputs[step.step_id] = HumanReviewStepInput(
                decision=HumanReviewDecision(decision),
                reviewer_note=note,
                revised_action=revised if decision == "revise" else None,
            )
        except (TypeError, ValueError):
            raise HumanReviewInputError(
                f"Review input validation failed for step {step.step_id}."
            ) from None
    return inputs


def _record_empty_workflow_review(
    state: MutableMapping[str, Any],
    workflow_plan: WorkflowPlan,
    overall_note: str,
) -> HumanReviewSession:
    """Record an explicit written acknowledgment for an empty workflow."""
    if not isinstance(overall_note, str) or not overall_note.strip():
        raise HumanReviewInputError("No-action review note is required.")
    session = review_workflow_plan(
        workflow_plan,
        {},
        no_action_acknowledged=True,
        overall_note=overall_note,
    )
    if not session.human_review_complete:
        raise HumanReviewInputError("No-action acknowledgment did not complete review.")
    state[_SK_REVIEW_SESSION] = session
    state.pop(_SK_MEMO, None)
    return session


def _role_name(role_key: RoleKey) -> str:
    """Return the fixed human-readable role name."""
    return _ROLE_DISPLAY.get(role_key, role_key.value)


def _render_header() -> None:
    """Render the product name, promise, process, and configuration status."""
    st.title("RoleLens")
    st.markdown(
        "Turn business data into a shared, reviewable decision — not another AI answer."
    )
    st.caption("Understand → Compare Roles → Coordinate → Review → Decide")
    if _configured():
        st.success("watsonx.ai configured — Live IBM Granite / watsonx.ai")
    else:
        st.warning(
            "watsonx.ai not configured — set WATSONX_APIKEY, WATSONX_URL, "
            "and WATSONX_PROJECT_ID"
        )


def _render_sidebar_setup() -> None:
    """Render explicit source selection and the two pipeline transactions."""
    _initialize_demo_widget_state(st.session_state)
    with st.sidebar:
        st.header("Demo setup")
        if st.button("Load IBM Telco public demo", key="btn_load_ibm", type="primary"):
            context = _load_ibm_context()
            if context:
                _apply_ibm_telco_sample(context, st.session_state)
                st.success("IBM Telco public demo loaded. Prepare Evidence when ready.")
            else:
                st.error("IBM Telco public demo context is unavailable.")

        with st.expander("Advanced / QA", expanded=False):
            if st.button("Load synthetic QA fixture", key="btn_load_synthetic"):
                sample = _load_sample_data()
                if sample:
                    _apply_synthetic_sample(sample, st.session_state)
                    st.success("Synthetic QA fixture loaded.")
                else:
                    st.error("Synthetic QA fixture is unavailable.")

        uploaded_file = st.file_uploader(
            "Upload a custom CSV",
            type=["csv"],
            key="csv_uploader",
            on_change=_handle_csv_uploader_change,
        )

        mode = st.session_state.get("demo_source_mode", DEMO_SOURCE_NONE)
        label = st.session_state.get(_SK_SOURCE_LABEL, "No source selected")
        st.info(f"Active source mode: {mode}\n\nSource: {label}")

        st.text_area(
            "Industry Context",
            key="field_industry_context",
            on_change=_invalidate_prepared_demo_session_state,
        )
        st.text_area(
            "Strategy Profile",
            key="field_strategy_profile",
            on_change=_invalidate_prepared_demo_session_state,
        )
        st.text_input(
            "Business Question",
            key="field_business_question",
            on_change=_invalidate_prepared_demo_session_state,
        )
        st.text_input(
            "Decision Goal",
            key="field_decision_goal",
            on_change=_invalidate_prepared_demo_session_state,
        )
        st.text_area(
            "User Assumption (optional)",
            key="field_user_assumption",
            on_change=_invalidate_prepared_demo_session_state,
        )

        if st.button("Prepare evidence", key="btn_prepare", type="primary"):
            try:
                csv_bytes, filename, profile_id, resolved_label = _resolve_demo_source(
                    mode,
                    uploaded_file,
                )
                values = {
                    key: st.session_state.get(key, "") for key in _CONTEXT_WIDGET_KEYS
                }
                for required_key in _CONTEXT_WIDGET_KEYS[:4]:
                    if not values[required_key].strip():
                        raise ValueError("All required decision-context fields must be completed.")
                prepared = _prepare_demo_inputs_transaction(
                    st.session_state,
                    csv_bytes=csv_bytes,
                    filename=filename,
                    industry_context=values["field_industry_context"],
                    strategy_profile=values["field_strategy_profile"],
                    business_question=values["field_business_question"],
                    decision_goal=values["field_decision_goal"],
                    user_assumption=values["field_user_assumption"].strip() or None,
                    business_profile_id=profile_id,
                    source_label=resolved_label,
                )
                st.success(
                    f"Evidence prepared: {len(prepared.evidence_objects)} objects from "
                    f"{prepared.row_count:,} rows."
                )
            except DemoPipelineError as exc:
                st.error(f"Preparation failed: {exc}")
            except ValueError as exc:
                st.error(str(exc))

        prepared = st.session_state.get(_SK_PREPARED)
        if st.button(
            "Run with IBM Granite",
            key="btn_run_live",
            type="primary",
            disabled=prepared is None,
        ):
            if not _configured():
                st.error("watsonx.ai is not configured.")
            else:
                try:
                    analysis = _run_live_demo_analysis_transaction(
                        st.session_state,
                        prepared,
                    )
                    ready = sum(
                        isinstance(value, RoleView)
                        for value in analysis.role_outcomes.values()
                    )
                    st.success(f"Analysis complete: {ready}/5 role views produced.")
                except DemoPipelineError as exc:
                    st.error(f"Live run failed: {exc}")

        if st.button("Reset demo", key="btn_reset"):
            _reset_rolelens_state()
            st.rerun()


def _render_decision_brief() -> None:
    """Render the first-screen business decision summary."""
    st.header("Decision Brief")
    prepared = st.session_state.get(_SK_PREPARED)
    if prepared is None:
        st.info(
            "1. Load the IBM public demo or upload a CSV\n\n"
            "2. Prepare deterministic Evidence\n\n"
            "3. Run IBM Granite for orientation and role views"
        )
        return
    analysis = st.session_state.get(_SK_ANALYSIS)
    label = st.session_state.get(_SK_SOURCE_LABEL, "Prepared source")
    view = build_decision_brief(prepared, analysis, source_label=label)
    st.subheader(view.dataset_name)
    st.caption(f"Source: {view.source_label}")
    st.info(view.disclosure)
    st.markdown(f"**Business question:** {view.business_question}")
    status_col, posture_col = st.columns(2)
    with status_col:
        st.metric("Decision status", view.decision_status)
        st.caption(view.status_detail)
    with posture_col:
        st.markdown("**Recommended posture**")
        st.warning(view.recommended_posture)
    if view.metrics:
        for column, metric in zip(st.columns(4), view.metrics):
            with column:
                st.metric(metric.label, metric.value, help=metric.help_text)
    if view.patterns:
        st.subheader("What the evidence suggests")
        for column, pattern in zip(st.columns(3), view.patterns):
            with column:
                with st.container(border=True):
                    st.markdown(f"**{pattern.headline}**")
                    st.write(pattern.explanation)
                    st.caption(
                        f"{pattern.source_label} | Evidence: "
                        + ", ".join(pattern.evidence_ids)
                    )
    if view.orientation_notice:
        st.warning(view.orientation_notice)
    if view.guardrails:
        st.subheader("What the evidence does not authorize")
        for guardrail in view.guardrails:
            st.info(guardrail)
    if analysis is not None:
        ready = sum(isinstance(value, RoleView) for value in analysis.role_outcomes.values())
        summary = build_action_plan_summary(analysis)
        cols = st.columns(3)
        cols[0].metric("Successful role views", f"{ready}/5")
        cols[1].metric("Workflow status", summary.plan_status)
        cols[2].metric("Blocking steps", summary.blocker_count)


def _render_data_health_detail() -> None:
    """Render all existing deterministic data-health fields."""
    prepared = st.session_state.get(_SK_PREPARED)
    if prepared is None:
        st.info("Prepare Evidence first.")
        return
    summary = prepared.data_health_summary
    st.caption(f"Source: {summary.source_id}")
    cols = st.columns(3)
    cols[0].metric("Rows", summary.row_count)
    cols[1].metric("Columns", summary.column_count)
    cols[2].metric("Duplicate rows", summary.duplicate_row_count)
    st.markdown("**Missing value rates**")
    st.json(summary.missing_value_rates)
    st.markdown("**Mixed-type columns**")
    st.write(summary.columns_with_mixed_types or "None")
    st.markdown("**Constant columns**")
    st.write(summary.constant_columns or "None")
    st.markdown("**Schema issues**")
    st.write(summary.schema_issues or "None")
    st.markdown("**Complete typed Data Health record**")
    st.json(summary.model_dump(mode="json"))
    st.markdown("**Bounded data preview**")
    st.caption(
        f"Showing up to 10 rows from {prepared.row_count:,} rows and "
        f"{prepared.column_count} columns."
    )
    if prepared.dataframe_preview_records:
        st.dataframe(
            pd.DataFrame(list(prepared.dataframe_preview_records)),
            use_container_width=True,
            hide_index=True,
        )


def _render_data_explained() -> None:
    """Render deterministic primer and optional Granite orientation."""
    st.header("Data Explained")
    prepared = st.session_state.get(_SK_PREPARED)
    if prepared is None:
        st.info("Prepare Evidence to explain the selected data source.")
        return
    profile = prepared.business_profile
    if profile is None:
        st.info("No registered business playbook is active for this source.")
        _render_data_health_detail()
        return
    business_question = prepared.available_inputs["business_question"]
    primer = build_dataset_primer(profile, business_question=business_question)
    st.subheader("Deterministic Dataset Primer")
    st.write(primer.dataset_context)
    st.markdown(f"**Currency status:** {primer.currency_status}")
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "Field": term.field_name,
                    "Plain language": term.plain_language,
                    "Primary use": term.primary_use,
                    "Caution": term.caution,
                }
                for term in primer.glossary_terms
            ]
        ),
        use_container_width=True,
        hide_index=True,
    )
    st.warning(
        f"Data quality note: {primer.total_charges_parse_issue_count} "
        "TotalCharges values have parse issues."
    )
    chart1, chart2, chart3 = st.columns(3)
    with chart1:
        st.markdown("**Churn rate by Contract**")
        contract_frame = pd.DataFrame(
            {
                "Contract": [item.segment for item in profile.contract_rates],
                "Recorded churn rate (%)": [
                    item.churn_rate_pct for item in profile.contract_rates
                ],
            }
        ).set_index("Contract")
        st.bar_chart(contract_frame)
    with chart2:
        st.markdown("**Median tenure by Churn status**")
        tenure_frame = pd.DataFrame(
            {
                "Churn status": [
                    item.churn_status for item in profile.medians_by_churn_status
                ],
                "Median tenure": [
                    item.median_tenure for item in profile.medians_by_churn_status
                ],
            }
        ).set_index("Churn status")
        st.bar_chart(tenure_frame)
    with chart3:
        st.markdown("**Median MonthlyCharges by Churn status**")
        charges_frame = pd.DataFrame(
            {
                "Churn status": [
                    item.churn_status for item in profile.medians_by_churn_status
                ],
                "Median MonthlyCharges": [
                    item.median_monthly_charges
                    for item in profile.medians_by_churn_status
                ],
            }
        ).set_index("Churn status")
        st.bar_chart(charges_frame)

    analysis = st.session_state.get(_SK_ANALYSIS)
    if analysis is None:
        st.caption("Granite orientation has not run; deterministic facts remain available.")
        return
    orientation = analysis.dataset_orientation_outcome
    if isinstance(orientation, DatasetOrientationFailure):
        st.warning("IBM Granite orientation was unavailable; the deterministic primer remains available.")
        return
    if isinstance(orientation, DatasetOrientationBrief):
        st.subheader("Explained by IBM Granite")
        st.write(orientation.dataset_overview)
        st.markdown(
            f"**Business question in plain language:** "
            f"{orientation.business_question_in_plain_language}"
        )
        st.markdown("**Terms to know**")
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Field": term.field_name,
                        "Explanation": term.explanation,
                        "Caution": term.caution,
                    }
                    for term in orientation.terms_to_know
                ]
            ),
            use_container_width=True,
            hide_index=True,
        )
        for pattern in orientation.key_patterns:
            with st.container(border=True):
                st.markdown(f"**{pattern.headline}**")
                st.write(pattern.plain_language_explanation)
                st.caption("Evidence: " + ", ".join(pattern.evidence_ids))
        st.info(orientation.why_this_matters)


def _render_role_comparison() -> None:
    """Render five role contrasts and one selected concise detail."""
    st.header("Role Comparison")
    analysis = st.session_state.get(_SK_ANALYSIS)
    if analysis is None:
        st.info("Run IBM Granite to compare the five policy-constrained roles.")
        return
    rows = build_role_comparison(analysis)
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "Role": row.role_name,
                    "Primary question": row.primary_question,
                    "Current focus": row.current_focus,
                    "Evidence-backed signal": row.evidence_backed_signal,
                    "Next handoff": row.next_handoff,
                    "Status": row.status,
                }
                for row in rows
            ]
        ),
        use_container_width=True,
        hide_index=True,
    )
    selected_name = st.selectbox(
        "Inspect one role",
        options=[row.role_name for row in rows],
        key="selected_product_role",
    )
    selected = next(row for row in rows if row.role_name == selected_name)
    outcome = analysis.role_outcomes[selected.role_key]
    with st.container(border=True):
        st.subheader(selected.role_name)
        if isinstance(outcome, RoleView):
            st.markdown(f"**Role concern:** {outcome.role_concern}")
            for finding in outcome.key_findings[:3]:
                evidence_ids = [ref.evidence_id for ref in finding.evidence_references]
                st.write(finding.claim)
                st.caption("Evidence: " + ", ".join(evidence_ids))
            st.markdown(f"**Next action:** {outcome.next_action or 'None identified.'}")
            st.markdown(f"**Dependency:** {outcome.dependency or 'None identified.'}")
            st.markdown("**Missing information:**")
            st.write(outcome.missing_information or "None recorded.")
        else:
            st.warning(selected.status)
            st.write(selected.evidence_backed_signal)


def _render_step_card(step: Any) -> None:
    """Render one unchanged WorkflowStep in a compact native container."""
    with st.container(border=True):
        st.markdown(f"**{step.step_id} — {_role_name(step.owner_role)}**")
        st.write(step.action)
        st.caption(
            f"Status: {step.status.value} | Evidence: "
            + (", ".join(step.supporting_evidence_ids) or "None")
        )


def _render_action_plan() -> None:
    """Render bounded blockers and role actions without changing the plan."""
    st.header("Action Plan")
    analysis = st.session_state.get(_SK_ANALYSIS)
    if analysis is None:
        st.info("Run IBM Granite to produce the deterministic WorkflowPlan.")
        return
    summary = build_action_plan_summary(analysis)
    columns = st.columns(4)
    columns[0].metric("Plan status", summary.plan_status)
    columns[1].metric("Total steps", summary.step_count)
    columns[2].metric("Blockers", summary.blocker_count)
    columns[3].metric("Semantic review gates", summary.review_gate_count)
    st.subheader("Priority blockers")
    if not summary.priority_blockers:
        st.success("No blocking workflow steps.")
    for step in summary.priority_blockers:
        _render_step_card(step)
    st.subheader("Role-owned actions")
    if not summary.role_actions:
        st.info("No role-owned actions are present.")
    for step in summary.role_actions:
        _render_step_card(step)
    st.caption("The complete unchanged WorkflowPlan is preserved in Audit Trail.")


def _render_review_controls(plan: WorkflowPlan) -> None:
    """Render exact per-step simulated-review inputs in one expander."""
    if not plan.steps:
        st.warning("No actionable workflow step was proposed.")
        note = st.text_area("No-action review note", key="review_note_no_action")
        if st.button("Acknowledge no actionable workflow", key="btn_acknowledge_no_action"):
            try:
                _record_empty_workflow_review(st.session_state, plan, note)
                st.success("No actionable workflow acknowledged.")
            except HumanReviewInputError as exc:
                st.error(f"Review input error: {exc}")
        return
    if st.button("Load editable demo review", key="btn_load_preset"):
        _apply_synthetic_review_preset(plan, st.session_state)
        st.info("Editable demo values loaded; no review has been recorded.")
    controls: dict[str, dict[str, Any]] = {}
    with st.expander("Review detailed decisions", expanded=False):
        previous_role: RoleKey | None = None
        for step in plan.steps:
            if step.owner_role is not previous_role:
                st.subheader(_role_name(step.owner_role))
                previous_role = step.owner_role
            st.markdown(f"**{step.step_id}** — {step.action}")
            is_gate = step.step_kind is WorkflowStepKind.semantic_review_gate
            options = ["select", "accept", "reject"] + ([] if is_gate else ["revise"])
            decision_key = f"review_decision_{step.step_id}"
            note_key = f"review_note_{step.step_id}"
            revised_key = f"review_revised_{step.step_id}"
            st.session_state.setdefault(decision_key, "select")
            st.session_state.setdefault(note_key, "")
            st.session_state.setdefault(revised_key, "")
            decision = st.selectbox(
                f"Decision for {step.step_id}",
                options=options,
                key=decision_key,
            )
            note = st.text_input(f"Reviewer note for {step.step_id}", key=note_key)
            revised = None
            if decision == "revise" and not is_gate:
                revised = st.text_input(
                    f"Revised action for {step.step_id}",
                    key=revised_key,
                )
            controls[step.step_id] = {
                "decision": decision,
                "reviewer_note": note or None,
                "revised_action": revised or None,
            }
    if st.button("Record simulated human review", key="btn_record_review", type="primary"):
        try:
            step_inputs = _build_human_review_inputs(plan, controls)
            session = review_workflow_plan(plan, step_inputs)
            st.session_state[_SK_REVIEW_SESSION] = session
            st.session_state.pop(_SK_MEMO, None)
            if session.human_review_complete:
                st.success("Simulated human review recorded and complete.")
            else:
                st.warning(f"Review remains pending for {len(session.pending_step_ids)} steps.")
        except HumanReviewInputError as exc:
            st.error(f"Review input error: {exc}")


def _render_review_and_memo() -> None:
    """Render compact human review and post-review memo summary."""
    st.header("Review & Memo")
    analysis = st.session_state.get(_SK_ANALYSIS)
    if analysis is None:
        st.info("Run IBM Granite before simulated human review.")
        return
    summary = build_action_plan_summary(analysis)
    pending = len(analysis.workflow_plan.steps)
    review_session = st.session_state.get(_SK_REVIEW_SESSION)
    if review_session is not None:
        pending = len(review_session.pending_step_ids)
    columns = st.columns(4)
    columns[0].metric("Plan steps", summary.step_count)
    columns[1].metric("Blockers", summary.blocker_count)
    columns[2].metric("Pending review", pending)
    columns[3].metric("Semantic gates", summary.review_gate_count)
    st.warning("Simulated review does not authorize execution.")
    if review_session is None or not review_session.human_review_complete:
        _render_review_controls(analysis.workflow_plan)
        review_session = st.session_state.get(_SK_REVIEW_SESSION)
    if review_session is not None and review_session.human_review_complete:
        if st.button("Compose reviewed Decision Memo", key="btn_compose_memo", type="primary"):
            try:
                memo = compose_decision_memo(
                    workflow_plan=analysis.workflow_plan,
                    human_review_session=review_session,
                    evidence_objects=list(analysis.prepared_inputs.evidence_objects),
                )
                st.session_state[_SK_MEMO] = memo
                st.success("Decision Memo composed.")
            except DecisionMemoInputError as exc:
                st.error(f"Memo composition failed: {exc}")
            except Exception:
                st.error("Memo composition failed validation.")
    memo = st.session_state.get(_SK_MEMO)
    if memo is None:
        return
    view = build_memo_summary(memo)
    st.subheader("Decision Memo summary")
    columns = st.columns(4)
    columns[0].metric("Status", view.memo_status)
    columns[1].metric("Retained", view.retained_count)
    columns[2].metric("Rejected", view.rejected_count)
    columns[3].metric("Unresolved blockers", view.unresolved_blocker_count)
    st.metric("Human revisions", view.revision_count)
    st.markdown("**Top retained actions**")
    for action in view.top_retained_actions:
        st.write(f"{action.step_id}: {action.action}")
    st.markdown("**Rejected actions**")
    for action in view.rejected_actions:
        st.write(f"{action.step_id}: {action.original_action}")
    if view.unresolved_blocker_count:
        st.error("Unresolved blockers remain and are not cleared by review.")
    if view.revision_count:
        st.warning("Human revisions require evidence revalidation.")
    st.warning("Simulated review does not authorize execution.")
    for notice in view.control_notices:
        st.warning(notice)


def _render_evidence_detail() -> None:
    """Render every EvidenceObject field, including locator and identity."""
    prepared = st.session_state.get(_SK_PREPARED)
    if prepared is None:
        st.info("Prepare Evidence first.")
        return
    st.info("Rule: No Evidence ID, no decision claim.")
    for evidence in prepared.evidence_objects:
        with st.expander(
            f"{evidence.evidence_id} — {evidence.evidence_scope.value} "
            f"({evidence.evidence_type})"
        ):
            st.json(evidence.model_dump(mode="json"))


def _render_roles_and_risks_detail() -> None:
    """Render complete role outputs and both risk result types."""
    analysis = st.session_state.get(_SK_ANALYSIS)
    if analysis is None:
        st.info("Run IBM Granite first.")
        return
    for role_key in _ROLE_DISPLAY_ORDER:
        outcome = analysis.role_outcomes[role_key]
        with st.expander(_role_name(role_key)):
            if isinstance(outcome, RoleView):
                st.json(outcome.model_dump(mode="json"))
            elif isinstance(outcome, InsufficientEvidence):
                st.error("Typed failure: insufficient_evidence")
                st.write(outcome.reason)
            elif isinstance(outcome, RoleGenerationFailure):
                st.error(f"Typed failure: {outcome.failure_code}")
                st.write(_safe_role_failure_reason(outcome.failure_code))
    st.subheader("Deterministic risks")
    st.json(analysis.deterministic_risk_result.model_dump(mode="json"))
    st.subheader("Semantic candidates")
    st.json(analysis.semantic_risk_result.model_dump(mode="json"))


def _render_workflow_detail() -> None:
    """Render the complete unchanged WorkflowPlan and lineage."""
    analysis = st.session_state.get(_SK_ANALYSIS)
    if analysis is None:
        st.info("Run IBM Granite first.")
        return
    plan = analysis.workflow_plan
    st.caption(
        f"Status: {plan.plan_status.value} | Method: {plan.planning_method} | "
        f"Human review required: {plan.human_review_required}"
    )
    st.json(
        {
            "plan_status": plan.plan_status.value,
            "included_role_keys": [value.value for value in plan.included_role_keys],
            "blocking_step_ids": plan.blocking_step_ids,
            "human_review_required": plan.human_review_required,
            "planning_method": plan.planning_method,
        }
    )
    for step in plan.steps:
        with st.expander(f"{step.step_id} — {_role_name(step.owner_role)}"):
            st.json(step.model_dump(mode="json"))
    if not plan.steps:
        st.info("No actionable workflow steps.")


def _render_memo_detail() -> None:
    """Render the complete memo, all sections, and Evidence appendix."""
    memo = st.session_state.get(_SK_MEMO)
    if memo is None:
        st.info("Compose the reviewed Decision Memo first.")
        return
    st.json(memo.model_dump(mode="json"))


def _render_audit_trail() -> None:
    """Render dense secondary inspection surfaces for full provenance."""
    st.header("Audit Trail")
    health, evidence, roles, workflow, memo = st.tabs(
        ["Data Health", "Evidence", "Roles & Risks", "Full Workflow", "Full Decision Memo"]
    )
    with health:
        _render_data_health_detail()
    with evidence:
        _render_evidence_detail()
    with roles:
        _render_roles_and_risks_detail()
    with workflow:
        _render_workflow_detail()
    with memo:
        _render_memo_detail()


def main() -> None:
    """Render the six-tab RoleLens product experience."""
    st.set_page_config(page_title="RoleLens", page_icon="🔎", layout="wide")
    _render_header()
    _render_sidebar_setup()
    tabs = st.tabs(
        [
            "Decision Brief",
            "Data Explained",
            "Role Comparison",
            "Action Plan",
            "Review & Memo",
            "Audit Trail",
        ]
    )
    with tabs[0]:
        _render_decision_brief()
    with tabs[1]:
        _render_data_explained()
    with tabs[2]:
        _render_role_comparison()
    with tabs[3]:
        _render_action_plan()
    with tabs[4]:
        _render_review_and_memo()
    with tabs[5]:
        _render_audit_trail()


if __name__ == "__main__":
    main()
