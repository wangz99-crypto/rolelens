"""app/main.py — RoleLens Task 10A Streamlit demo application.

Six-tab evidence-grounded AI decision workflow for business teams.

Normal Python import defines UI functions without rendering the application,
constructing providers, or making network calls. Initial Streamlit rendering
may inspect only the boolean presence of required environment-variable names;
it never displays their values or constructs providers. Only the
'Run RoleLens with IBM Granite' button triggers run_live_demo_analysis().

Tabs:
  1. Intake
  2. Data Health
  3. Evidence Board
  4. RoleLens Views
  5. Workflow Plan
  6. Decision Memo
"""

from __future__ import annotations

import json
import os
import pathlib
from collections.abc import Mapping, MutableMapping
from typing import Any

import streamlit as st

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
from app.role_engine import InsufficientEvidence, RoleGenerationFailure
from app.schemas import (
    DecisionMemoActionOrigin,
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

# ---------------------------------------------------------------------------
# Page config — must be first Streamlit call
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Sample data paths
# ---------------------------------------------------------------------------

_SAMPLE_DATA_DIR = pathlib.Path(__file__).parent.parent / "sample_data"
_DEMO_CSV_PATH = _SAMPLE_DATA_DIR / "b2b_saas_retention_demo.csv"
_DEMO_JSON_PATH = _SAMPLE_DATA_DIR / "b2b_saas_retention_demo.json"

# ---------------------------------------------------------------------------
# Session state keys
# ---------------------------------------------------------------------------

_SK_PREPARED = "rolelens_prepared_inputs"
_SK_ANALYSIS = "rolelens_analysis_result"
_SK_REVIEW_SESSION = "rolelens_review_session"
_SK_MEMO = "rolelens_decision_memo"
_SK_REVIEW_PRESET_LOADED = "rolelens_review_preset_loaded"

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

# ---------------------------------------------------------------------------
# Role display names (policy-aligned)
# ---------------------------------------------------------------------------

_ROLE_DISPLAY = {
    RoleKey.executive: "Executive",
    RoleKey.data_analyst: "Data Analyst / Data Scientist",
    RoleKey.data_engineer: "Data Engineer",
    RoleKey.sales_marketing: "Sales / Marketing",
    RoleKey.project_manager: "Project Manager",
}

_ROLE_DISPLAY_ORDER = [
    RoleKey.executive,
    RoleKey.data_analyst,
    RoleKey.data_engineer,
    RoleKey.sales_marketing,
    RoleKey.project_manager,
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _configured() -> bool:
    """Return True iff all three watsonx.ai env vars are present and non-blank."""
    required = ["WATSONX_APIKEY", "WATSONX_URL", "WATSONX_PROJECT_ID"]
    return all(os.environ.get(k, "").strip() for k in required)


def _load_sample_data() -> dict:
    """Load demo JSON sidecar, return empty dict on failure."""
    try:
        return json.loads(_DEMO_JSON_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _initialize_demo_widget_state(
    state: MutableMapping[str, Any],
) -> None:
    """Initialize actual intake widget keys before widget construction."""
    for key in _CONTEXT_WIDGET_KEYS:
        state.setdefault(key, "")
    state.setdefault("demo_use_sample_csv", False)


def _apply_synthetic_sample(
    sample: Mapping[str, Any],
    state: MutableMapping[str, Any],
) -> None:
    """Invalidate prepared state, then write the synthetic intake values."""
    _invalidate_prepared_demo_state(state)
    state.pop("csv_uploader", None)
    source_to_widget = {
        "industry_context": "field_industry_context",
        "strategy_profile": "field_strategy_profile",
        "business_question": "field_business_question",
        "decision_goal": "field_decision_goal",
        "user_assumption": "field_user_assumption",
    }
    for source_key, widget_key in source_to_widget.items():
        value = sample.get(source_key, "")
        state[widget_key] = value if isinstance(value, str) else ""
    state["demo_use_sample_csv"] = True


def _clear_review_widget_state(
    state: MutableMapping[str, Any],
) -> None:
    """Clear only RoleLens review preset and per-step widget keys."""
    for key in list(state):
        if (
            key in {"demo_review_preset", _SK_REVIEW_PRESET_LOADED}
            or any(key.startswith(prefix) for prefix in _REVIEW_WIDGET_PREFIXES)
        ):
                del state[key]


def _invalidate_prepared_demo_state(
    state: MutableMapping[str, Any],
) -> None:
    """Clear prepared and downstream RoleLens state after an input change."""
    _clear_review_widget_state(state)
    for key in (
        _SK_PREPARED,
        _SK_ANALYSIS,
        _SK_REVIEW_SESSION,
        _SK_MEMO,
    ):
        state.pop(key, None)


def _invalidate_prepared_demo_session_state() -> None:
    """Apply decision-input invalidation to Streamlit session state."""
    _invalidate_prepared_demo_state(st.session_state)


def _handle_csv_uploader_change() -> None:
    """Select custom-upload mode and invalidate prepared RoleLens state."""
    st.session_state["demo_use_sample_csv"] = False
    _invalidate_prepared_demo_state(st.session_state)


def _resolve_csv_input(
    uploaded_file: Any,
    use_sample_csv: bool,
) -> tuple[bytes, str]:
    """Resolve exactly one selected CSV source without cursor dependence."""
    if use_sample_csv:
        if not _DEMO_CSV_PATH.is_file():
            raise ValueError("Synthetic sample CSV is unavailable.")
        return _DEMO_CSV_PATH.read_bytes(), _DEMO_CSV_PATH.name

    if uploaded_file is None:
        raise ValueError("No CSV source is selected.")

    try:
        csv_bytes = uploaded_file.getvalue()
        csv_filename = uploaded_file.name
    except Exception:
        raise ValueError("Uploaded CSV could not be read.") from None
    if not isinstance(csv_bytes, bytes) or not isinstance(csv_filename, str):
        raise ValueError("Uploaded CSV is invalid.")
    return csv_bytes, csv_filename


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
) -> PreparedDemoInputs:
    """Prepare first, then atomically replace prepared and downstream state."""
    prepared = prepare_demo_inputs(
        csv_bytes=csv_bytes,
        filename=filename,
        industry_context=industry_context,
        strategy_profile=strategy_profile,
        business_question=business_question,
        decision_goal=decision_goal,
        user_assumption=user_assumption,
    )
    state[_SK_PREPARED] = prepared
    _clear_review_widget_state(state)
    for key in (_SK_ANALYSIS, _SK_REVIEW_SESSION, _SK_MEMO):
        state.pop(key, None)
    return prepared


def _run_live_demo_analysis_transaction(
    state: MutableMapping[str, Any],
    prepared: PreparedDemoInputs,
) -> DemoAnalysisResult:
    """Run live analysis first, then atomically clear stale downstream state."""
    analysis = run_live_demo_analysis(prepared)
    state[_SK_ANALYSIS] = analysis
    _clear_review_widget_state(state)
    for key in (_SK_REVIEW_SESSION, _SK_MEMO):
        state.pop(key, None)
    return analysis


def _record_empty_workflow_review(
    state: MutableMapping[str, Any],
    workflow_plan: WorkflowPlan,
    overall_note: str,
) -> HumanReviewSession:
    """Record an explicit, written acknowledgment for an empty workflow."""
    if not isinstance(overall_note, str) or not overall_note.strip():
        raise HumanReviewInputError("No-action review note is required.")
    session = review_workflow_plan(
        workflow_plan,
        {},
        no_action_acknowledged=True,
        overall_note=overall_note,
    )
    if not session.human_review_complete:
        raise HumanReviewInputError(
            "No-action acknowledgment did not complete review."
        )
    state[_SK_REVIEW_SESSION] = session
    state.pop(_SK_MEMO, None)
    return session


def _reset_rolelens_state() -> None:
    """Clear only RoleLens-specific session keys."""
    _invalidate_prepared_demo_state(st.session_state)
    keys = [
        *_CONTEXT_WIDGET_KEYS,
        "demo_use_sample_csv",
        "csv_uploader",
    ]
    for key in keys:
        if key in st.session_state:
            del st.session_state[key]


def _build_synthetic_review_preset(
    workflow_plan: WorkflowPlan,
) -> dict[str, dict[str, str]]:
    """Build deterministic editable controls from typed workflow fields."""
    if type(workflow_plan) is not WorkflowPlan:
        raise HumanReviewInputError(
            "workflow_plan must be exactly a WorkflowPlan"
        )

    non_gate_steps = [
        step
        for step in workflow_plan.steps
        if step.step_kind is not WorkflowStepKind.semantic_review_gate
    ]
    revision_step = next(
        (
            step
            for step in non_gate_steps
            if (
                not step.blocks_downstream
                and step.status is not WorkflowStepStatus.blocked
            )
        ),
        non_gate_steps[0] if non_gate_steps else None,
    )
    rejection_step = next(
        (
            step
            for step in reversed(workflow_plan.steps)
            if (
                step.step_kind is WorkflowStepKind.role_action
                and step is not revision_step
                and (
                    revision_step is None
                    or step.sequence > revision_step.sequence
                )
            )
        ),
        None,
    )

    preset: dict[str, dict[str, str]] = {}
    for step in workflow_plan.steps:
        if step.step_kind is WorkflowStepKind.semantic_review_gate:
            decision = "accept"
            note = (
                "Semantic candidates reviewed as probabilistic and "
                "non-authoritative."
            )
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
            note = (
                "Synthetic downstream role action rejected pending review."
            )
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
    """Write a synthetic preset directly to the actual review widget keys."""
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
        raise HumanReviewInputError(
            "workflow_plan must be exactly a WorkflowPlan"
        )
    if not isinstance(raw_controls, Mapping):
        raise HumanReviewInputError("Review controls must be a mapping.")

    plan_step_ids = tuple(step.step_id for step in workflow_plan.steps)
    if (
        any(not isinstance(step_id, str) for step_id in raw_controls)
        or set(raw_controls) != set(plan_step_ids)
    ):
        raise HumanReviewInputError(
            "Review controls must match workflow plan steps."
        )

    inputs: dict[str, HumanReviewStepInput] = {}
    for step in workflow_plan.steps:
        control = raw_controls[step.step_id]
        if not isinstance(control, Mapping):
            raise HumanReviewInputError(
                f"Review controls are invalid for step {step.step_id}."
            )
        raw_decision = control.get("decision")
        decision_value = (
            raw_decision.value
            if isinstance(raw_decision, HumanReviewDecision)
            else raw_decision
        )
        if decision_value not in {"accept", "reject", "revise"}:
            raise HumanReviewInputError(
                f"A review decision is required for step {step.step_id}."
            )

        note = control.get("reviewer_note")
        revised_action = control.get("revised_action")
        if note == "":
            note = None
        if revised_action == "":
            revised_action = None
        if note is not None and (
            not isinstance(note, str) or not note.strip()
        ):
            raise HumanReviewInputError(
                f"Reviewer note is invalid for step {step.step_id}."
            )
        if revised_action is not None and (
            not isinstance(revised_action, str)
            or not revised_action.strip()
        ):
            raise HumanReviewInputError(
                f"Revised action is invalid for step {step.step_id}."
            )

        if step.step_kind is WorkflowStepKind.semantic_review_gate:
            if decision_value == "revise":
                raise HumanReviewInputError(
                    f"Semantic review gate {step.step_id} cannot be revised."
                )
            if note is None:
                raise HumanReviewInputError(
                    f"Semantic review gate {step.step_id} requires a "
                    "reviewer note."
                )
        elif decision_value == "reject" and note is None:
            raise HumanReviewInputError(
                f"Rejecting step {step.step_id} requires a reviewer note."
            )
        elif decision_value == "revise":
            if note is None:
                raise HumanReviewInputError(
                    f"Revising step {step.step_id} requires a reviewer note."
                )
            if revised_action is None:
                raise HumanReviewInputError(
                    f"Revising step {step.step_id} requires a revised action."
                )
            if revised_action == step.action:
                raise HumanReviewInputError(
                    f"Revised action for step {step.step_id} must differ "
                    "from the original action."
                )

        try:
            inputs[step.step_id] = HumanReviewStepInput(
                decision=HumanReviewDecision(decision_value),
                reviewer_note=note,
                revised_action=(
                    revised_action
                    if decision_value == "revise"
                    else None
                ),
            )
        except (TypeError, ValueError):
            raise HumanReviewInputError(
                f"Review input validation failed for step {step.step_id}."
            ) from None
    return inputs


def _evidence_scope_label(scope: EvidenceScope) -> str:
    mapping = {
        EvidenceScope.internal_observation: "Internal Observation",
        EvidenceScope.external_context: "External Context",
        EvidenceScope.assumption: "Assumption",
        EvidenceScope.stated_priority: "Stated Priority",
    }
    return mapping.get(scope, scope.value)


def _step_kind_label(kind: WorkflowStepKind) -> str:
    mapping = {
        WorkflowStepKind.deterministic_risk_resolution: "Deterministic Risk Resolution",
        WorkflowStepKind.semantic_review_gate: "Semantic Review Gate",
        WorkflowStepKind.role_action: "Role Action",
    }
    return mapping.get(kind, kind.value)


def _step_status_label(status: WorkflowStepStatus) -> str:
    mapping = {
        WorkflowStepStatus.ready: "Ready",
        WorkflowStepStatus.blocked: "BLOCKED",
        WorkflowStepStatus.pending_human_review: "Pending Human Review",
    }
    return mapping.get(status, status.value)


# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------


def _render_header() -> None:
    st.title("🔎 RoleLens")
    st.markdown(
        "**Evidence-grounded AI decision workflow for business teams**"
    )
    st.caption(
        "Not another CSV chatbot: every decision-bearing step preserves "
        "Evidence IDs, risk lineage, dependencies, and human review."
    )

    # Process ribbon
    st.markdown(
        "**Process:** `Evidence` → `Roles` → `Risks` → `Workflow` "
        "→ `Human Review` → `Memo`"
    )

    col1, col2 = st.columns([3, 1])
    with col1:
        if _configured():
            st.success("watsonx.ai configured — Live IBM Granite / watsonx.ai")
        else:
            st.warning("watsonx.ai not configured — set WATSONX_APIKEY, WATSONX_URL, WATSONX_PROJECT_ID")
    with col2:
        if st.button("Reset demo", key="btn_reset"):
            _reset_rolelens_state()
            st.rerun()


# ---------------------------------------------------------------------------
# Tab 1 — Intake
# ---------------------------------------------------------------------------


def _render_tab_intake() -> None:
    _initialize_demo_widget_state(st.session_state)
    st.header("Tab 1 — Intake")
    st.caption(
        "Upload a CSV and provide context. "
        "Preparing evidence is deterministic — no Granite call is made. "
        "Only 'Run RoleLens with IBM Granite' calls the live model."
    )

    # Sample loader
    st.subheader("Quick Start")
    if st.button("Load synthetic B2B SaaS demo", key="btn_load_sample"):
        sample = _load_sample_data()
        if not sample:
            st.error("Sample data files not found. Check sample_data/ directory.")
        else:
            _apply_synthetic_sample(sample, st.session_state)
            st.success("Synthetic B2B SaaS demo loaded. Review fields below, then click 'Prepare evidence'.")

    st.divider()

    # File uploader
    st.subheader("Data Source")
    uploaded_file = st.file_uploader(
        "Upload CSV (or use the sample loader above)",
        type=["csv"],
        key="csv_uploader",
        on_change=_handle_csv_uploader_change,
        help="CSV only. No Excel, PDF, or image parsing in Task 10A.",
    )

    use_sample_csv = st.session_state.get("demo_use_sample_csv", False)

    # Context fields
    st.subheader("Decision Context")

    industry_context = st.text_area(
        "Industry Context",
        height=100,
        key="field_industry_context",
        on_change=_invalidate_prepared_demo_session_state,
        help="External industry observation. Must not be used as direct company evidence.",
    )
    strategy_profile = st.text_area(
        "Strategy Profile",
        height=80,
        key="field_strategy_profile",
        on_change=_invalidate_prepared_demo_session_state,
        help="Company strategic priority. Stated intent, not verified performance.",
    )
    business_question = st.text_input(
        "Business Question",
        key="field_business_question",
        on_change=_invalidate_prepared_demo_session_state,
        help="Decision context only — produces no Evidence Object.",
    )
    decision_goal = st.text_input(
        "Decision Goal",
        key="field_decision_goal",
        on_change=_invalidate_prepared_demo_session_state,
        help="Decision context only — produces no Evidence Object.",
    )
    user_assumption = st.text_area(
        "User Assumption (optional)",
        height=60,
        key="field_user_assumption",
        on_change=_invalidate_prepared_demo_session_state,
        help="Unverified assumption. Flagged visibly in risk review.",
    )

    st.caption(
        "**Source scope:** Industry context = External Context | "
        "Strategy profile / Assumption = User Assertion | "
        "Business question / Decision goal = Decision Context (no Evidence Object produced)"
    )

    st.divider()

    # Prepare button
    col_prep, col_run = st.columns(2)
    with col_prep:
        if st.button("Prepare evidence", key="btn_prepare", type="primary"):
            try:
                csv_bytes, csv_filename = _resolve_csv_input(
                    uploaded_file,
                    use_sample_csv,
                )
            except ValueError:
                st.error("No CSV provided. Upload a file or load the synthetic demo.")
                return

            ic = st.session_state.get("field_industry_context") or industry_context
            sp = st.session_state.get("field_strategy_profile") or strategy_profile
            bq = st.session_state.get("field_business_question") or business_question
            dg = st.session_state.get("field_decision_goal") or decision_goal
            ua = st.session_state.get("field_user_assumption") or user_assumption

            if not ic.strip():
                st.error("Industry context is required.")
                return
            if not sp.strip():
                st.error("Strategy profile is required.")
                return
            if not bq.strip():
                st.error("Business question is required.")
                return
            if not dg.strip():
                st.error("Decision goal is required.")
                return

            with st.spinner("Preparing evidence (deterministic)…"):
                try:
                    prepared = _prepare_demo_inputs_transaction(
                        st.session_state,
                        csv_bytes=csv_bytes,
                        filename=csv_filename,
                        industry_context=ic,
                        strategy_profile=sp,
                        business_question=bq,
                        decision_goal=dg,
                        user_assumption=ua.strip() or None,
                    )
                    st.success(
                        f"Evidence prepared: {len(prepared.evidence_objects)} Evidence Object(s) "
                        f"from {prepared.row_count} CSV rows."
                    )
                except DemoPipelineError as exc:
                    st.error(f"Preparation failed: {exc}")

    with col_run:
        prepared: PreparedDemoInputs | None = st.session_state.get(_SK_PREPARED)
        run_disabled = prepared is None

        if st.button(
            "Run RoleLens with IBM Granite",
            key="btn_run_live",
            type="primary",
            disabled=run_disabled,
            help="Requires WATSONX_APIKEY, WATSONX_URL, WATSONX_PROJECT_ID" if not _configured() else None,
        ):
            if not _configured():
                st.error(
                    "watsonx.ai is not configured. Set WATSONX_APIKEY, WATSONX_URL, "
                    "and WATSONX_PROJECT_ID environment variables."
                )
            elif prepared is not None:
                with st.spinner("Running Live IBM Granite / watsonx.ai — this may take 30–90 seconds…"):
                    try:
                        analysis = _run_live_demo_analysis_transaction(
                            st.session_state,
                            prepared,
                        )
                        n_views = sum(
                            1 for v in analysis.role_outcomes.values()
                            if isinstance(v, RoleView)
                        )
                        st.success(
                            f"Analysis complete: {n_views}/5 role views produced."
                        )
                    except DemoPipelineError as exc:
                        st.error(f"Live run failed: {exc}")

    # Data preview
    prepared = st.session_state.get(_SK_PREPARED)
    if prepared is not None:
        st.divider()
        st.subheader("Data Preview")
        st.caption(
            f"Showing up to 10 rows. Full dataset: "
            f"{prepared.row_count} rows × {prepared.column_count} columns."
        )
        if prepared.dataframe_preview_records:
            import pandas as pd
            st.dataframe(pd.DataFrame(list(prepared.dataframe_preview_records)), use_container_width=True)
        st.info(
            f"**Source scope:** CSV registered as `data_source` (internal_observation). "
            f"Industry context is external — it cannot be cited as direct company evidence."
        )


# ---------------------------------------------------------------------------
# Tab 2 — Data Health
# ---------------------------------------------------------------------------


def _render_tab_data_health() -> None:
    st.header("Tab 2 — Data Health")

    prepared: PreparedDemoInputs | None = st.session_state.get(_SK_PREPARED)
    if prepared is None:
        st.info("Prepare evidence in Tab 1 first.")
        return

    s = prepared.data_health_summary
    st.caption(f"Source: `{s.source_id}`")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Rows", s.row_count)
    with col2:
        st.metric("Columns", s.column_count)
    with col3:
        dup_label = str(s.duplicate_row_count)
        if s.duplicate_row_count > 0:
            st.metric("Duplicate Rows", dup_label)
            st.warning(f"{s.duplicate_row_count} exact duplicate row(s) detected.")
        else:
            st.metric("Duplicate Rows", dup_label)

    st.subheader("Missing Value Rates")
    cols_with_missing = {c: r for c, r in s.missing_value_rates.items() if r > 0}
    if cols_with_missing:
        for col, rate in cols_with_missing.items():
            pct = round(rate * 100, 1)
            st.warning(f"**{col}**: {pct}% missing")
    else:
        st.success("No missing values detected.")

    st.subheader("Mixed-Type Columns")
    if s.columns_with_mixed_types:
        for col in s.columns_with_mixed_types:
            st.warning(f"Mixed types in column: **{col}**")
    else:
        st.success("No mixed-type columns detected.")

    st.subheader("Constant Columns")
    if s.constant_columns:
        for col in s.constant_columns:
            st.warning(f"Constant column (all non-null values identical): **{col}**")
    else:
        st.success("No constant columns detected.")

    st.subheader("Schema Issues")
    if s.schema_issues:
        for issue in s.schema_issues:
            st.warning(issue)
    else:
        st.success("No schema issues detected.")

    if s.duplicate_row_count > 0 or cols_with_missing:
        st.warning(
            "Data quality gaps detected. These are captured as Evidence Objects "
            "and will affect role views and risk assessment."
        )


# ---------------------------------------------------------------------------
# Tab 3 — Evidence Board
# ---------------------------------------------------------------------------


def _render_tab_evidence_board() -> None:
    st.header("Tab 3 — Evidence Board")
    st.info("**Rule: No Evidence ID, no decision claim.**")

    prepared: PreparedDemoInputs | None = st.session_state.get(_SK_PREPARED)
    if prepared is None:
        st.info("Prepare evidence in Tab 1 first.")
        return

    evidence_objects = prepared.evidence_objects
    if not evidence_objects:
        st.warning("No Evidence Objects were produced. Check data and context inputs.")
        return

    st.caption(f"{len(evidence_objects)} active Evidence Object(s)")

    scope_labels = {
        EvidenceScope.internal_observation: "Internal Observation",
        EvidenceScope.external_context: "External Context",
        EvidenceScope.assumption: "Assumption",
        EvidenceScope.stated_priority: "Stated Priority",
    }

    for ev in evidence_objects:
        scope_label = scope_labels.get(ev.evidence_scope, ev.evidence_scope.value)
        with st.expander(
            f"`{ev.evidence_id}` — {scope_label} ({ev.evidence_type})",
            expanded=False,
        ):
            col1, col2 = st.columns(2)
            with col1:
                st.markdown(f"**Evidence ID:** `{ev.evidence_id}`")
                st.markdown(f"**Evidence Scope:** {scope_label}")
                st.markdown(f"**Confidence:** {ev.confidence}")
                st.markdown(f"**Extraction Method:** {ev.extraction_method}")
                st.markdown(f"**Status:** {ev.status.value}")
            with col2:
                st.markdown(f"**Source ID:** `{ev.source_id}`")
                st.markdown(f"**Evidence Type:** `{ev.evidence_type}`")
                st.markdown(f"**Relevant Roles:** {', '.join(ev.relevant_roles)}")

            st.markdown("**Finding:**")
            st.write(ev.finding)

            if ev.supporting_evidence and ev.supporting_evidence != ev.finding:
                st.markdown("**Supporting Evidence:**")
                st.write(ev.supporting_evidence)

            st.markdown("**Decision Relevance:**")
            st.write(ev.decision_relevance)

            if ev.limitations:
                st.markdown("**Limitations:**")
                for lim in ev.limitations:
                    st.caption(f"⚠ {lim}")

            with st.expander("Source Locator", expanded=False):
                try:
                    st.json(ev.source_locator.model_dump(mode="json"))
                except Exception:
                    st.write(str(ev.source_locator))


# ---------------------------------------------------------------------------
# Tab 4 — RoleLens Views
# ---------------------------------------------------------------------------


def _render_tab_role_views() -> None:
    st.header("Tab 4 — RoleLens Views")
    st.caption(
        "The five roles are policy-constrained views over shared Evidence. "
        "They are not autonomous AI employees."
    )

    analysis: DemoAnalysisResult | None = st.session_state.get(_SK_ANALYSIS)
    if analysis is None:
        st.info("Run the live analysis in Tab 1 first.")
        return

    st.subheader("Role Views")
    for role_key in _ROLE_DISPLAY_ORDER:
        outcome = analysis.role_outcomes[role_key]
        display_name = _ROLE_DISPLAY[role_key]

        if isinstance(outcome, RoleView):
            with st.expander(f"**{display_name}** — Role View", expanded=False):
                st.markdown(f"**Role Concern:** {outcome.role_concern}")
                st.markdown(f"**Human Review Required:** {outcome.human_review_required}")

                if outcome.next_action:
                    st.markdown(f"**Next Action:** {outcome.next_action}")
                if outcome.dependency:
                    st.markdown(f"**Dependency:** {outcome.dependency}")

                st.markdown("**Key Findings:**")
                for i, finding in enumerate(outcome.key_findings):
                    ev_ids = ", ".join(
                        f"`{ref.evidence_id}`" for ref in finding.evidence_references
                    )
                    st.markdown(f"*Claim {i+1}* (confidence: {finding.confidence})")
                    st.write(finding.claim)
                    st.caption(f"Evidence: {ev_ids}")

                if outcome.risks_or_assumptions:
                    st.markdown("**Risks / Assumptions:**")
                    for r in outcome.risks_or_assumptions:
                        st.warning(r)

                if outcome.missing_information:
                    st.markdown("**Missing Information:**")
                    for m in outcome.missing_information:
                        st.caption(f"• {m}")

        elif isinstance(outcome, InsufficientEvidence):
            with st.expander(f"**{display_name}** — Insufficient Evidence", expanded=False):
                st.error(
                    f"**Typed Failure: insufficient_evidence**\n\n{outcome.reason}"
                )
                st.caption("No role insight or next action was fabricated.")

        elif isinstance(outcome, RoleGenerationFailure):
            with st.expander(f"**{display_name}** — Generation Failure", expanded=False):
                st.error(
                    f"**Typed Failure: {outcome.failure_code}**\n\n"
                    f"{_safe_role_failure_reason(outcome.failure_code)}"
                )
                st.caption("No role insight or next action was fabricated.")

    # Deterministic Risk Review
    st.subheader("Deterministic Risk Review")
    risk_result = analysis.deterministic_risk_result
    if not risk_result.findings:
        st.success("No deterministic risks detected.")
    else:
        st.warning(
            f"{len(risk_result.findings)} deterministic risk finding(s). "
            f"Blocking: {risk_result.has_blocking_risks}. "
            f"Human review required: {risk_result.human_review_required}."
        )
        for finding in risk_result.findings:
            role_name = _ROLE_DISPLAY.get(finding.role_key, finding.role_key.value)
            blocker_tag = " 🚫 BLOCKING" if finding.blocks_downstream else ""
            review_tag = " 👁 REVIEW REQUIRED" if finding.requires_human_review else ""
            ev_ids = ", ".join(f"`{e}`" for e in finding.evidence_ids) if finding.evidence_ids else "N/A"
            with st.expander(
                f"`{finding.risk_code.value}` — {role_name} [{finding.severity.value}]{blocker_tag}{review_tag}",
                expanded=False,
            ):
                st.markdown(f"**Message:** {finding.message}")
                st.markdown(f"**Required Action:** {finding.required_action}")
                st.markdown(f"**Evidence IDs:** {ev_ids}")
                if finding.claim_index is not None:
                    st.caption(f"Claim index: {finding.claim_index}")

    # Semantic Review
    st.subheader("Granite Semantic Review — probabilistic, non-authoritative")
    st.caption(
        "Semantic review is probabilistic. Candidates do not automatically block or approve work. "
        "likely_supported is not verified truth."
    )
    semantic = analysis.semantic_risk_result
    if not semantic.candidates:
        st.success("No semantic risk candidates produced.")
    else:
        st.info(
            f"{len(semantic.candidates)} semantic candidate(s). "
            f"Human review required: {semantic.human_review_required}."
        )
        for cand in semantic.candidates:
            role_name = _ROLE_DISPLAY.get(cand.role_key, cand.role_key.value)
            ev_ids = ", ".join(f"`{e}`" for e in cand.evidence_ids)
            with st.expander(
                f"`{cand.risk_code.value}` — {role_name} claim {cand.claim_index} "
                f"[{cand.disposition.value}]",
                expanded=False,
            ):
                st.markdown(f"**Explanation:** {cand.explanation}")
                st.markdown(f"**Review Question:** {cand.review_question}")
                st.markdown(f"**Evidence IDs:** {ev_ids}")
                st.markdown(f"**Confidence:** {cand.confidence}")
                st.markdown(f"**Disposition:** `{cand.disposition.value}`")
                st.caption("This is a probabilistic candidate — not a verified fact.")


# ---------------------------------------------------------------------------
# Tab 5 — Workflow Plan
# ---------------------------------------------------------------------------


def _render_tab_workflow() -> None:
    st.header("Tab 5 — Workflow Plan")

    analysis: DemoAnalysisResult | None = st.session_state.get(_SK_ANALYSIS)
    if analysis is None:
        st.info("Run the live analysis in Tab 1 first.")
        return

    plan = analysis.workflow_plan
    st.caption(
        f"Plan status: **{plan.plan_status.value}** | "
        f"Steps: {len(plan.steps)} | "
        f"Blocking steps: {len(plan.blocking_step_ids)} | "
        f"Planning method: {plan.planning_method}"
    )

    if plan.blocking_step_ids:
        st.error(f"BLOCKED: {', '.join(plan.blocking_step_ids)}")

    if plan.steps:
        st.subheader("Workflow Steps")

    for step in plan.steps:
        role_name = _ROLE_DISPLAY.get(step.owner_role, step.owner_role.value)
        kind_label = _step_kind_label(step.step_kind)
        status_label = _step_status_label(step.status)

        blocker_tag = " 🚫 BLOCKS DOWNSTREAM" if step.blocks_downstream else ""
        status_icon = "🔴" if step.status == WorkflowStepStatus.blocked else (
            "🟡" if step.status == WorkflowStepStatus.pending_human_review else "🟢"
        )

        with st.expander(
            f"{status_icon} `{step.step_id}` [{step.sequence}] {kind_label} — {role_name}{blocker_tag}",
            expanded=False,
        ):
            col1, col2 = st.columns(2)
            with col1:
                st.markdown(f"**Step ID:** `{step.step_id}`")
                st.markdown(f"**Kind:** {kind_label}")
                st.markdown(f"**Owner:** {role_name}")
                st.markdown(f"**Status:** {status_label}")
                st.markdown(f"**Blocks Downstream:** {step.blocks_downstream}")
                st.markdown(f"**Human Review Required:** {step.human_review_required}")
            with col2:
                ev_ids = ", ".join(f"`{e}`" for e in step.supporting_evidence_ids) or "None"
                dep_ids = ", ".join(f"`{d}`" for d in step.dependency_step_ids) or "None"
                st.markdown(f"**Evidence IDs:** {ev_ids}")
                st.markdown(f"**Dependencies:** {dep_ids}")

            st.markdown(f"**Action:** {step.action}")

            if step.dependency_notes:
                st.markdown("**Dependency Notes:**")
                for note in step.dependency_notes:
                    st.caption(f"• {note}")

            if step.deterministic_risk_codes:
                codes = ", ".join(f"`{c.value}`" for c in step.deterministic_risk_codes)
                st.markdown(f"**Deterministic Risk Codes:** {codes}")

            if step.semantic_risk_codes:
                codes = ", ".join(f"`{c.value}`" for c in step.semantic_risk_codes)
                st.markdown(f"**Semantic Risk Codes:** {codes}")

            if step.review_questions:
                st.markdown("**Review Questions:**")
                for q in step.review_questions:
                    st.caption(f"• {q}")

            if step.missing_information:
                st.markdown("**Missing Information:**")
                for m in step.missing_information:
                    st.caption(f"• {m}")

    st.divider()
    st.subheader("Human Review Controls")
    st.warning("Simulated review does not authorize execution.")

    if not plan.steps:
        st.warning("No actionable workflow step was proposed.")
        no_action_note = st.text_area(
            "No-action review note",
            key="review_note_no_action",
        )
        if st.button(
            "Acknowledge no actionable workflow",
            key="btn_acknowledge_no_action",
            type="primary",
        ):
            try:
                _record_empty_workflow_review(
                    st.session_state,
                    plan,
                    no_action_note,
                )
                st.success(
                    "No actionable workflow acknowledged. Go to Tab 6 to "
                    "compose the Decision Memo."
                )
            except HumanReviewInputError as exc:
                st.error(f"Review input error: {exc}")
            except Exception:
                st.error("No-action review could not be validated.")
        return

    # Preset loader writes actual widget state before controls are built.
    if st.button(
        "Synthetic review preset — review before recording",
        key="btn_load_preset",
    ):
        _apply_synthetic_review_preset(plan, st.session_state)
        st.info(
            "**Synthetic review preset — review before recording.** "
            "Editable values are loaded into the controls below. "
            "Review each decision before clicking 'Record simulated human review'."
        )

    # Per-step decision controls
    decisions: dict[str, dict[str, Any]] = {}

    for step in plan.steps:
        role_name = _ROLE_DISPLAY.get(step.owner_role, step.owner_role.value)
        kind_label = _step_kind_label(step.step_kind)
        st.markdown(f"**`{step.step_id}`** — {kind_label} ({role_name})")
        st.caption(step.action[:120] + ("…" if len(step.action) > 120 else ""))

        is_gate = step.step_kind == WorkflowStepKind.semantic_review_gate

        decision_options = ["select", "accept", "reject"]
        if not is_gate:
            decision_options.append("revise")
        decision_key = f"review_decision_{step.step_id}"
        note_key = f"review_note_{step.step_id}"
        revised_key = f"review_revised_{step.step_id}"
        st.session_state.setdefault(decision_key, "select")
        st.session_state.setdefault(note_key, "")
        st.session_state.setdefault(revised_key, "")

        decision_val = st.selectbox(
            f"Decision for {step.step_id}",
            options=decision_options,
            key=decision_key,
            label_visibility="collapsed",
        )

        note_required = (
            decision_val == "reject"
            or decision_val == "revise"
            or is_gate
        )
        reviewer_note = st.text_input(
            f"Reviewer note for {step.step_id}" + (" (required)" if note_required else ""),
            key=note_key,
        )

        revised_action = None
        if decision_val == "revise" and not is_gate:
            revised_action = st.text_input(
                f"Revised action for {step.step_id} (required — must differ from original)",
                key=revised_key,
            )

        decisions[step.step_id] = {
            "decision": decision_val,
            "reviewer_note": reviewer_note or None,
            "revised_action": revised_action or None,
        }

    st.divider()

    if st.button("Record simulated human review", key="btn_record_review", type="primary"):
        try:
            step_inputs = _build_human_review_inputs(plan, decisions)
            session = review_workflow_plan(plan, step_inputs)
            st.session_state[_SK_REVIEW_SESSION] = session
            if _SK_MEMO in st.session_state:
                del st.session_state[_SK_MEMO]
            if session.human_review_complete:
                st.success(
                    "Human review recorded and complete. Go to Tab 6 to "
                    "compose the Decision Memo."
                )
            else:
                pending = len(session.pending_step_ids)
                st.warning(
                    f"Review recorded but {pending} step(s) still pending: "
                    f"{', '.join(session.pending_step_ids)}"
                )
        except HumanReviewInputError as exc:
            st.error(f"Review input error: {exc}")
        except Exception:
            st.error("Review input could not be validated.")


# ---------------------------------------------------------------------------
# Tab 6 — Decision Memo
# ---------------------------------------------------------------------------


def _render_tab_memo() -> None:
    st.header("Tab 6 — Decision Memo")

    review_session = st.session_state.get(_SK_REVIEW_SESSION)
    analysis: DemoAnalysisResult | None = st.session_state.get(_SK_ANALYSIS)

    if analysis is None:
        st.info("Run the live analysis in Tab 1 first.")
        return

    if review_session is None:
        st.info("Record simulated human review in Tab 5 first.")
        return

    if not review_session.human_review_complete:
        st.warning(
            "Human review is not yet complete. "
            f"Pending steps: {', '.join(review_session.pending_step_ids)}"
        )
        return

    st.caption("Decision Memo is available. Compose to generate.")

    if st.button("Compose reviewed Decision Memo", key="btn_compose_memo", type="primary"):
        try:
            memo = compose_decision_memo(
                workflow_plan=analysis.workflow_plan,
                human_review_session=review_session,
                evidence_objects=list(analysis.prepared_inputs.evidence_objects),
            )
            st.session_state[_SK_MEMO] = memo
            st.success(f"Decision Memo composed. Status: {memo.memo_status.value}")
        except DecisionMemoInputError as exc:
            st.error(f"Memo composition failed: {exc}")
        except Exception:
            st.error("Memo composition failed validation.")

    memo = st.session_state.get(_SK_MEMO)
    if memo is None:
        return

    # 1. Review state
    st.subheader("1. Review State")
    status_map = {
        "reviewed": "Reviewed",
        "requires_revalidation": "Requires Revalidation (human revisions present)",
        "blocked": "Blocked (unresolved blockers)",
        "no_action_acknowledged": "No Action Acknowledged",
    }
    st.info(f"**Status:** {status_map.get(memo.memo_status.value, memo.memo_status.value)}")
    st.write(memo.review_summary)
    digest_short = memo.plan_digest[:16] + "…"
    st.caption(f"Plan digest (abbrev): `{digest_short}`")
    with st.expander("Full plan digest", expanded=False):
        st.code(memo.plan_digest)

    # 2. Retained action sequence
    st.subheader("2. Retained Action Sequence")
    if not memo.retained_actions:
        st.info("No retained actions.")
    else:
        for action in memo.retained_actions:
            role_name = _ROLE_DISPLAY.get(action.owner_role, action.owner_role.value)
            origin_label = (
                "Human revision — evidence support not revalidated"
                if action.action_origin == DecisionMemoActionOrigin.human_revision
                else "Accepted (original)"
            )
            with st.expander(
                f"`{action.step_id}` [{action.sequence}] {role_name} — {origin_label}",
                expanded=False,
            ):
                if action.action_origin == DecisionMemoActionOrigin.human_revision:
                    st.warning("**Human revision — evidence support not revalidated.**")
                    st.markdown(f"**Original Action:** {action.original_action}")
                    st.markdown(f"**Revised Action:** {action.action}")
                else:
                    st.markdown(f"**Action:** {action.action}")

                if action.reviewer_note:
                    st.caption(f"Reviewer note: {action.reviewer_note}")

                ev_ids = ", ".join(f"`{e}`" for e in action.supporting_evidence_ids) or "None"
                st.caption(f"Evidence: {ev_ids}")

                if action.deterministic_risk_codes:
                    codes = ", ".join(f"`{c.value}`" for c in action.deterministic_risk_codes)
                    st.caption(f"Deterministic risks: {codes}")
                if action.semantic_risk_codes:
                    codes = ", ".join(f"`{c.value}`" for c in action.semantic_risk_codes)
                    st.caption(f"Semantic risks: {codes}")
                st.caption(f"Original status: {action.original_status.value}")

    # 3. Semantic review decisions
    st.subheader("3. Semantic Review Decisions")
    if not memo.review_gates:
        st.info("No semantic review gates in this plan.")
    else:
        for gate in memo.review_gates:
            role_name = _ROLE_DISPLAY.get(gate.owner_role, gate.owner_role.value)
            with st.expander(f"`{gate.step_id}` Semantic Gate — {role_name}", expanded=False):
                st.markdown(f"**Decision:** {gate.decision.value}")
                if gate.reviewer_note:
                    st.write(f"Reviewer note: {gate.reviewer_note}")
                codes = ", ".join(f"`{c.value}`" for c in gate.semantic_risk_codes)
                st.caption(f"Semantic risk codes: {codes}")
                st.caption("Semantic decisions remain probabilistic and non-authoritative.")

    # 4. Rejected steps
    st.subheader("4. Rejected Steps")
    if not memo.rejected_steps:
        st.info("No steps were rejected.")
    else:
        for step in memo.rejected_steps:
            role_name = _ROLE_DISPLAY.get(step.owner_role, step.owner_role.value)
            with st.expander(f"`{step.step_id}` REJECTED — {role_name}", expanded=False):
                st.markdown(f"**Original Action:** {step.original_action}")
                if step.reviewer_note:
                    st.write(f"Reviewer note: {step.reviewer_note}")
                st.caption(f"Original status: {step.original_status.value}")

    # 5. Unresolved blockers
    st.subheader("5. Unresolved Blockers")
    if not memo.unresolved_blocking_step_ids:
        st.success("No unresolved blockers.")
    else:
        st.error(
            f"Unresolved blocking steps: "
            f"{', '.join(f'`{s}`' for s in memo.unresolved_blocking_step_ids)}"
        )
        st.caption("Accepting a remediation step does not mark the blocker as complete.")

    # 6. Missing information
    st.subheader("6. Missing Information")
    if not memo.missing_information:
        st.success("No missing information recorded.")
    else:
        for mi in memo.missing_information:
            role_name = _ROLE_DISPLAY.get(mi.owner_role, mi.owner_role.value)
            st.warning(f"**{role_name}** (`{mi.step_id}`):")
            for item in mi.items:
                st.caption(f"• {item}")

    # 7. Evidence cited
    st.subheader("7. Evidence Cited")
    if not memo.evidence_items:
        st.info("No evidence items cited.")
    else:
        for item in memo.evidence_items:
            scope_label = _evidence_scope_label(item.evidence_scope)
            with st.expander(f"`{item.evidence_id}` — {scope_label}", expanded=False):
                st.markdown(f"**Source ID:** `{item.source_id}`")
                st.markdown(f"**Confidence:** {item.confidence}")
                st.write(item.finding)
                st.write(item.decision_relevance)
                if item.limitations:
                    for lim in item.limitations:
                        st.caption(f"⚠ {lim}")

    # 8. Control notices
    st.subheader("8. Control Notices")
    for notice in memo.control_notices:
        st.warning(notice)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Render the full RoleLens Streamlit application."""
    st.set_page_config(
        page_title="RoleLens",
        page_icon="🔎",
        layout="wide",
    )
    _render_header()

    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "Intake",
        "Data Health",
        "Evidence Board",
        "RoleLens Views",
        "Workflow Plan",
        "Decision Memo",
    ])

    with tab1:
        _render_tab_intake()

    with tab2:
        _render_tab_data_health()

    with tab3:
        _render_tab_evidence_board()

    with tab4:
        _render_tab_role_views()

    with tab5:
        _render_tab_workflow()

    with tab6:
        _render_tab_memo()


if __name__ == "__main__":
    main()
