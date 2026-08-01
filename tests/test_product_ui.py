"""Offline tests for the Task 10C-2B product-first Streamlit surface.

Exactly 10 top-level test functions.  No live Granite call is made.
"""

from __future__ import annotations

import importlib
import json
import os
import pathlib
import socket
import sys
import types
from dataclasses import FrozenInstanceError
from functools import lru_cache
from typing import Any, Mapping
from unittest.mock import MagicMock, patch

import pytest

from app.dataset_orientation import (
    DatasetOrientationBrief,
    DatasetOrientationFailure,
)
from app.demo_pipeline import prepare_demo_inputs, run_live_demo_analysis
from app.human_review import review_workflow_plan
from app.main import (
    DEMO_SOURCE_CUSTOM,
    DEMO_SOURCE_IBM_TELCO,
    DEMO_SOURCE_NONE,
    DEMO_SOURCE_SYNTHETIC_FIXTURE,
    _apply_ibm_telco_sample,
    _apply_synthetic_sample,
    _build_human_review_inputs,
    _build_synthetic_review_preset,
    _handle_csv_uploader_change,
    _resolve_demo_source,
)
from app.memo_generator import compose_decision_memo
from app.product_view import (
    ActionPlanSummary,
    DecisionBriefView,
    MemoSummary,
    MetricCard,
    PatternCard,
    RoleComparisonRow,
    build_action_plan_summary,
    build_decision_brief,
    build_memo_summary,
    build_role_comparison,
)
from app.role_engine import InsufficientEvidence, RoleGenerationFailure
from app.schemas import RoleKey, RoleView


_ROOT = pathlib.Path(__file__).parent.parent
_PUBLIC_CSV = _ROOT / "sample_data" / "public" / "ibm_telco_customer_churn.csv"
_PUBLIC_CONTEXT = (
    _ROOT / "sample_data" / "public" / "ibm_telco_customer_churn_context.json"
)
_SYNTHETIC_CONTEXT = _ROOT / "sample_data" / "b2b_saas_retention_demo.json"
_MAIN_PATH = _ROOT / "app" / "main.py"


@lru_cache(maxsize=1)
def _prepared_ibm():
    """Prepare the frozen public sample once without any provider."""
    context = json.loads(_PUBLIC_CONTEXT.read_text(encoding="utf-8"))
    return prepare_demo_inputs(
        csv_bytes=_PUBLIC_CSV.read_bytes(),
        filename=_PUBLIC_CSV.name,
        industry_context=context["dataset_context"],
        strategy_profile=context["strategy_profile"],
        business_question=context["business_question"],
        decision_goal=context["decision_goal"],
        user_assumption=context["user_assumption"],
        business_profile_id="ibm_telco_churn_v1",
    )


def _orientation_output(prepared=None) -> dict[str, Any]:
    """Return one valid grounded orientation mapping."""
    selected = prepared or _prepared_ibm()
    evidence_by_type = {
        item.evidence_type: item.evidence_id for item in selected.evidence_objects
    }
    return {
        "dataset_overview": "This fictional sample contains aggregate customer account records.",
        "business_question_in_plain_language": "Should a limited validation pilot be reviewed?",
        "terms_to_know": [
            {"field_name": "Churn", "explanation": "The recorded outcome.", "caution": "It does not explain why."},
            {"field_name": "Contract", "explanation": "The contract category.", "caution": "Differences are descriptive."},
            {"field_name": "tenure", "explanation": "Recorded account tenure.", "caution": "Use only within this sample."},
            {"field_name": "MonthlyCharges", "explanation": "The recorded recurring charge.", "caution": "Currency is unspecified."},
        ],
        "key_patterns": [
            {"headline": "Granite overall pattern", "plain_language_explanation": "Recorded churn is summarized in aggregate.", "evidence_ids": [evidence_by_type["business_overall_churn"]]},
            {"headline": "Granite contract pattern", "plain_language_explanation": "Contract groups have different recorded rates.", "evidence_ids": [evidence_by_type["business_contract_churn"]]},
            {"headline": "Granite median pattern", "plain_language_explanation": "Churn-status groups have different medians.", "evidence_ids": [evidence_by_type["business_churn_medians"]]},
        ],
        "why_this_matters": "These descriptive aggregates frame governed validation questions.",
        "evidence_boundary_acknowledged": True,
    }


class _OrientationProvider:
    """Return the fixed valid orientation mapping."""

    def generate_dataset_orientation(self, request) -> Mapping[str, Any]:
        return _orientation_output()


class _RoleProvider:
    """Return one valid low-confidence grounded view per exposed role."""

    def generate_role_view(self, request) -> Mapping[str, Any]:
        evidence_id = sorted(request.exposed_evidence_ids)[0]
        if request.role_key is RoleKey.project_manager:
            prior = request.inputs["role_views"][0]
            evidence_id = prior.key_findings[0].evidence_references[0].evidence_id
        return {
            "role_key": request.role_key.value,
            "role_concern": f"Focus for {request.role_key.value}",
            "key_findings": [
                {
                    "claim": f"First grounded signal for {request.role_key.value}.",
                    "evidence_references": [{"evidence_id": evidence_id}],
                    "confidence": "low",
                },
                {
                    "claim": f"Second grounded signal for {request.role_key.value}.",
                    "evidence_references": [{"evidence_id": evidence_id}],
                    "confidence": "low",
                },
            ],
            "risks_or_assumptions": [],
            "missing_information": [f"Gap for {request.role_key.value}."],
            "next_action": f"Handoff for {request.role_key.value}.",
            "dependency": "Complete validation first.",
            "human_review_required": True,
        }


class _SemanticProvider:
    """Return an empty, exact reviewed-role response."""

    def review_semantic_risks(self, request) -> Mapping[str, Any]:
        return {
            "candidates": [],
            "reviewed_role_keys": [view.role_key.value for view in request.role_views],
            "reviewer_model": "offline-product-ui",
            "human_review_required": False,
        }


@lru_cache(maxsize=1)
def _analysis():
    """Build a complete offline analysis once."""
    return run_live_demo_analysis(
        _prepared_ibm(),
        role_provider=_RoleProvider(),
        semantic_provider=_SemanticProvider(),
        orientation_provider=_OrientationProvider(),
    )


@lru_cache(maxsize=1)
def _memo():
    """Build one mixed reviewed memo through existing public contracts."""
    analysis = _analysis()
    preset = _build_synthetic_review_preset(analysis.workflow_plan)
    inputs = _build_human_review_inputs(analysis.workflow_plan, preset)
    session = review_workflow_plan(analysis.workflow_plan, inputs)
    return compose_decision_memo(
        analysis.workflow_plan,
        session,
        list(analysis.prepared_inputs.evidence_objects),
    )


def test_frozen_product_view_contracts_validate_and_are_immutable() -> None:
    """Required text is non-blank and all presentation contracts are frozen."""
    metric = MetricCard("Customers", "7,043", "Frozen sample count.")
    pattern = PatternCard("Pattern", "Explanation", ("ev-" + "a" * 32,), "Source")
    brief = DecisionBriefView(
        "Dataset", "Source", "Disclosure", "Question", "STATUS", "Posture",
        "Detail", (metric,), (pattern,), ("Guardrail",), None,
    )
    role = RoleComparisonRow(
        RoleKey.executive, "Executive", "Question", "Focus", "Signal", "Handoff", "Ready"
    )
    action = ActionPlanSummary("blocked", 0, 0, 0, (), ())
    memo = MemoSummary("reviewed", 0, 0, 0, 0, (), (), ("Notice",))
    for value in (metric, pattern, brief, role, action, memo):
        with pytest.raises(FrozenInstanceError):
            value.placeholder = "changed"
    with pytest.raises(ValueError, match="must not be blank"):
        MetricCard(" ", "1", "Help")
    with pytest.raises(TypeError, match="tuple"):
        PatternCard("Pattern", "Explanation", ["ev-" + "a" * 32], "Source")


def test_ibm_loader_selects_only_public_profile_source() -> None:
    """IBM quick start clears custom state and maps the exact context keys."""
    context = json.loads(_PUBLIC_CONTEXT.read_text(encoding="utf-8"))
    state = {
        "csv_uploader": object(),
        "rolelens_prepared_inputs": object(),
        "rolelens_analysis_result": object(),
        "unrelated": "keep",
    }
    with patch("app.main.run_live_demo_analysis", side_effect=AssertionError):
        _apply_ibm_telco_sample(context, state)
    assert "csv_uploader" not in state
    assert state["demo_source_mode"] == DEMO_SOURCE_IBM_TELCO
    assert state["field_industry_context"] == context["dataset_context"]
    for key in ("strategy_profile", "business_question", "decision_goal", "user_assumption"):
        assert state[f"field_{key}"] == context[key]
    resolved = _resolve_demo_source(DEMO_SOURCE_IBM_TELCO, object())
    assert resolved[0] == _PUBLIC_CSV.read_bytes()
    assert resolved[1:] == (
        _PUBLIC_CSV.name,
        "ibm_telco_churn_v1",
        "IBM Telco public demo",
    )
    assert state["unrelated"] == "keep"


def test_custom_and_synthetic_modes_never_activate_profile() -> None:
    """Non-playbook modes stay profile-free and custom bytes use getvalue()."""
    upload = types.SimpleNamespace(
        name="ibm_telco_customer_churn.csv",
        getvalue=MagicMock(return_value=b"a,b\n1,2\n"),
    )
    custom = _resolve_demo_source(DEMO_SOURCE_CUSTOM, upload)
    assert custom == (
        b"a,b\n1,2\n",
        "ibm_telco_customer_churn.csv",
        None,
        "Custom upload: ibm_telco_customer_churn.csv",
    )
    upload.getvalue.assert_called_once_with()
    synthetic = _resolve_demo_source(DEMO_SOURCE_SYNTHETIC_FIXTURE, upload)
    assert synthetic[2] is None
    upload.getvalue.assert_called_once_with()
    sample = json.loads(_SYNTHETIC_CONTEXT.read_text(encoding="utf-8"))
    state: dict[str, Any] = {"csv_uploader": upload}
    _apply_synthetic_sample(sample, state)
    assert state["demo_source_mode"] == DEMO_SOURCE_SYNTHETIC_FIXTURE
    assert "csv_uploader" not in state

    context_keys = (
        "field_industry_context",
        "field_strategy_profile",
        "field_business_question",
        "field_decision_goal",
        "field_user_assumption",
    )
    for predefined_mode in (
        DEMO_SOURCE_IBM_TELCO,
        DEMO_SOURCE_SYNTHETIC_FIXTURE,
    ):
        predefined_state = {
            "demo_source_mode": predefined_mode,
            "csv_uploader": upload,
            "rolelens_source_label": "Predefined source",
            **{key: f"predefined {key}" for key in context_keys},
            "rolelens_prepared_inputs": object(),
            "rolelens_analysis_result": object(),
        }
        with patch("app.main.st.session_state", predefined_state):
            _handle_csv_uploader_change()
        assert predefined_state["demo_source_mode"] == DEMO_SOURCE_CUSTOM
        assert all(predefined_state[key] == "" for key in context_keys)
        assert "rolelens_prepared_inputs" not in predefined_state
        assert "rolelens_analysis_result" not in predefined_state

    custom_state = {
        "demo_source_mode": DEMO_SOURCE_CUSTOM,
        "csv_uploader": upload,
        **{key: f"custom {key}" for key in context_keys},
    }
    with patch("app.main.st.session_state", custom_state):
        _handle_csv_uploader_change()
    assert all(
        custom_state[key] == f"custom {key}" for key in context_keys
    )

    callback_state = {"csv_uploader": None, "demo_source_mode": DEMO_SOURCE_CUSTOM}
    with patch("app.main.st.session_state", callback_state):
        _handle_csv_uploader_change()
    assert callback_state["demo_source_mode"] == DEMO_SOURCE_NONE
    assert "rolelens_source_label" not in callback_state
    with pytest.raises(ValueError, match="No CSV source"):
        _resolve_demo_source(DEMO_SOURCE_NONE, None)


def test_decision_brief_before_analysis_uses_exact_profile_facts() -> None:
    """The evidence-ready IBM brief uses only frozen profile and primer facts."""
    prepared = _prepared_ibm()
    view = build_decision_brief(prepared, source_label="IBM Telco public demo")
    assert view.dataset_name == "IBM Telco Customer Churn"
    assert view.disclosure == "This is a fictional IBM sample dataset, not real customer production data."
    assert view.decision_status == "EVIDENCE READY"
    assert view.recommended_posture == "Limited validation pilot for human review; no customer targeting or outreach."
    assert [(item.label, item.value) for item in view.metrics] == [
        ("Customers", "7,043"),
        ("Recorded churn", "1,869"),
        ("Overall churn rate", "26.54%"),
        ("TotalCharges parse issues", "11"),
    ]
    assert len(view.patterns) == 3
    assert {item.source_label for item in view.patterns} == {"Deterministic business profile"}
    assert all(item.evidence_ids for item in view.patterns)
    assert len(view.guardrails) == 4


def test_granite_orientation_replaces_only_patterns_and_failure_falls_back() -> None:
    """Typed orientation success/failure changes only presentation patterns."""
    prepared = _prepared_ibm()
    base = _analysis()
    successful = build_decision_brief(prepared, base, source_label="IBM Telco public demo")
    assert [item.headline for item in successful.patterns] == [
        "Granite overall pattern",
        "Granite contract pattern",
        "Granite median pattern",
    ]
    assert {item.source_label for item in successful.patterns} == {"IBM Granite orientation"}
    expected_ids = [tuple(item["evidence_ids"]) for item in _orientation_output()["key_patterns"]]
    assert [item.evidence_ids for item in successful.patterns] == expected_ids
    failed_analysis = types.SimpleNamespace(
        dataset_primer=base.dataset_primer,
        dataset_orientation_outcome=DatasetOrientationFailure(
            failure_code="provider_error",
            reason="Dataset orientation provider failed.",
        ),
        workflow_plan=base.workflow_plan,
    )
    failed = build_decision_brief(prepared, failed_analysis, source_label="IBM Telco public demo")
    fallback = build_decision_brief(prepared, source_label="IBM Telco public demo")
    assert failed.patterns == fallback.patterns
    assert "unavailable" in failed.orientation_notice


def test_role_comparison_is_fixed_order_bounded_and_failure_safe() -> None:
    """Five distinct questions expose only the first claim and typed failures."""
    analysis = _analysis()
    outcomes = dict(analysis.role_outcomes)
    outcomes[RoleKey.data_engineer] = InsufficientEvidence(
        role_key=RoleKey.data_engineer,
        reason="Sensitive raw insufficiency reason.",
    )
    outcomes[RoleKey.sales_marketing] = RoleGenerationFailure(
        role_key=RoleKey.sales_marketing,
        failure_code="provider_error",
        reason="Sensitive raw provider reason.",
    )
    rows = build_role_comparison(types.SimpleNamespace(role_outcomes=outcomes))
    assert [row.role_key for row in rows] == list(RoleKey)
    assert len({row.primary_question for row in rows}) == 5
    assert rows[0].evidence_backed_signal.startswith("First grounded signal")
    assert "Second grounded" not in rows[0].evidence_backed_signal
    rendered = " ".join(row.status + row.evidence_backed_signal for row in rows)
    assert "Sensitive raw" not in rendered
    assert rows[2].status == "Insufficient evidence"
    assert rows[3].status == "Generation failure: provider_error"


def test_action_plan_summary_is_bounded_and_non_mutating() -> None:
    """Summary counts exact steps while preserving IDs, citations, and plan."""
    analysis = _analysis()
    before = analysis.workflow_plan.model_dump(mode="json")
    summary = build_action_plan_summary(analysis)
    assert summary.step_count == len(analysis.workflow_plan.steps)
    assert summary.blocker_count == sum(step.blocks_downstream for step in analysis.workflow_plan.steps)
    assert summary.review_gate_count == sum(step.step_kind.value == "semantic_review_gate" for step in analysis.workflow_plan.steps)
    assert summary.priority_blockers == tuple(
        step for step in analysis.workflow_plan.steps if step.blocks_downstream
    )[:3]
    assert len(summary.role_actions) <= 5
    for step in (*summary.priority_blockers, *summary.role_actions):
        original = next(item for item in analysis.workflow_plan.steps if item.step_id == step.step_id)
        assert step.supporting_evidence_ids == original.supporting_evidence_ids
    assert analysis.workflow_plan.model_dump(mode="json") == before


def test_memo_summary_preserves_reviewed_records_without_mutation() -> None:
    """MemoSummary counts and references existing records without rewriting."""
    memo = _memo()
    before = memo.model_dump(mode="json")
    summary = build_memo_summary(memo)
    assert summary.retained_count == len(memo.retained_actions)
    assert summary.rejected_count == len(memo.rejected_steps)
    assert summary.unresolved_blocker_count == len(memo.unresolved_blocking_step_ids)
    assert summary.revision_count == len(memo.human_revision_step_ids)
    assert summary.top_retained_actions == tuple(memo.retained_actions[:3])
    assert summary.rejected_actions == tuple(memo.rejected_steps)
    assert summary.control_notices == tuple(memo.control_notices)
    assert memo.model_dump(mode="json") == before


def test_imports_are_provider_env_network_and_render_safe() -> None:
    """Normal imports perform no rendering, provider construction, or I/O."""
    for name in ("app.main", "app.product_view"):
        sys.modules.pop(name, None)
    with patch("streamlit.title", side_effect=AssertionError("rendered")), patch(
        "app.demo_pipeline.run_live_demo_analysis",
        side_effect=AssertionError("provider called"),
    ), patch.object(
        os._Environ,
        "get",
        side_effect=AssertionError("environment read"),
    ), patch.object(
        socket,
        "create_connection",
        side_effect=AssertionError("network called"),
    ):
        product = importlib.import_module("app.product_view")
        main = importlib.import_module("app.main")
    assert hasattr(product, "build_decision_brief")
    assert hasattr(main, "main")


def test_streamlit_product_app_ibm_prepare_path() -> None:
    """AppTest proves the six-tab IBM preparation path is provider-free."""
    try:
        from streamlit.testing.v1 import AppTest
    except ImportError:
        return
    with patch.dict(
        os.environ,
        {
            "WATSONX_APIKEY": "secret-product-key",
            "WATSONX_URL": "https://example.invalid",
            "WATSONX_PROJECT_ID": "secret-product-project",
        },
        clear=False,
    ), patch(
        "app.granite_provider.GraniteRoleProvider.from_env"
    ) as role_factory, patch(
        "app.granite_semantic_risk_provider.GraniteSemanticRiskProvider.from_env"
    ) as semantic_factory, patch(
        "app.granite_dataset_orientation_provider.GraniteDatasetOrientationProvider.from_env"
    ) as orientation_factory:
        app = AppTest.from_file(str(_MAIN_PATH), default_timeout=30).run()
        assert not app.exception
        primary_labels = [tab.label for tab in app.tabs[:6]]
        assert primary_labels == [
            "Decision Brief", "Data Explained", "Role Comparison",
            "Action Plan", "Review & Memo", "Audit Trail",
        ]
        synthetic_button = next(
            button
            for button in app.button
            if button.label == "Load synthetic QA fixture"
        )
        app = synthetic_button.click().run()
        assert not app.exception
        assert (
            app.session_state["demo_source_mode"]
            == DEMO_SOURCE_SYNTHETIC_FIXTURE
        )
        assert app.session_state["csv_uploader"] is None
        assert role_factory.call_count == 0
        assert semantic_factory.call_count == 0
        assert orientation_factory.call_count == 0

        ibm_button = next(button for button in app.button if button.label == "Load IBM Telco public demo")
        app = ibm_button.click().run()
        prepare_button = next(button for button in app.button if button.label == "Prepare evidence")
        app = prepare_button.click().run()
        assert not app.exception
        prepared = app.session_state["rolelens_prepared_inputs"]
        assert prepared.business_profile.profile_id == "ibm_telco_churn_v1"
        rendered = "\n".join(
            str(element.value)
            for collection in (
                app.title, app.header, app.subheader, app.markdown, app.caption,
                app.info, app.warning, app.success, app.error, app.metric,
            )
            for element in collection
        )
        for fact in ("IBM Telco Customer Churn", "7,043", "26.54%", "Audit Trail"):
            assert fact in rendered or fact in [tab.label for tab in app.tabs]
        for chart_title in (
            "Churn rate by Contract",
            "Median tenure by Churn status",
            "Median MonthlyCharges by Churn status",
        ):
            assert chart_title in rendered
        assert "Median tenure and MonthlyCharges by Churn status" not in rendered
        assert "secret-product-key" not in rendered
        assert "secret-product-project" not in rendered
        assert role_factory.call_count == 0
        assert semantic_factory.call_count == 0
        assert orientation_factory.call_count == 0
