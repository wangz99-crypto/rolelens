"""Offline product-validation tests for the standalone DD-4 Decision Lab.

Exactly 10 top-level test functions. No external service is used.
"""

from __future__ import annotations

import ast
import importlib
import json
import os
import socket
import sys
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import pytest

from app.decision_diff import ScenarioAssumption, ScenarioStatus
from app.decision_diff_engine import DecisionImpactType
from app.decision_diff_rolelens import (
    ExecutiveScenarioPosture,
    ProjectManagerHandoff,
    RoleLensDecisionDiffError,
    SalesPilotPosture,
)
from app.demo_pipeline import PreparedDemoInputs
from app.schemas import EvidenceScope


_ROOT = Path(__file__).parent.parent
_MODULE_PATH = _ROOT / "app" / "decision_lab.py"
_FORBIDDEN_PRIMARY_PHRASES = (
    "roi predictor",
    "approved",
    "approval granted",
    "contact these customers",
    "high-risk customers",
    "prediction probability",
    "evidence supports the break-even calculation",
)


def _lab():
    """Import and return the render-safe Decision Lab module."""
    return importlib.import_module("app.decision_lab")


@pytest.fixture(scope="module")
def prepared() -> PreparedDemoInputs:
    """Load the frozen public IBM fixture through the explicit DD-4 helper."""
    return _lab()._load_ibm_telco_inputs()


def _revision(prepared: PreparedDemoInputs, lift: str):
    """Build one tested DD-4 revision from a fractional Decimal lift."""
    return _lab()._build_revision(prepared, Decimal(lift))


def _impact_map(revision) -> dict[str, DecisionImpactType]:
    """Index actual DD-2 impact types by registered object ID."""
    return {
        item.object_id: item.impact_type
        for item in revision.decision_diff.impacts
    }


def _rendered_text(app) -> str:
    """Collect visible native Streamlit content, including table values."""
    values: list[str] = []
    for collection_name in (
        "title",
        "caption",
        "info",
        "warning",
        "success",
        "error",
    ):
        values.extend(
            str(element.value)
            for element in getattr(app, collection_name)
        )
    for metric in app.metric:
        values.extend((str(metric.label), str(metric.value)))
    for dataframe in app.dataframe:
        value = dataframe.value
        values.append(value.to_string(index=False) if hasattr(value, "to_string") else str(value))
    values.extend(expander.label for expander in app.expander)
    return "\n".join(values)


def test_normal_import_is_render_provider_env_network_file_and_calculation_safe() -> None:
    """Importing app.decision_lab performs none of the guarded product work."""
    import streamlit
    from app import decision_diff, decision_diff_rolelens, demo_pipeline

    sys.modules.pop("app.decision_lab", None)
    with patch.object(
        streamlit,
        "title",
        side_effect=AssertionError("rendered"),
    ) as rendered, patch.object(
        Path,
        "read_bytes",
        side_effect=AssertionError("sample read"),
    ) as read_bytes, patch.object(
        Path,
        "read_text",
        side_effect=AssertionError("sample read"),
    ) as read_text, patch.object(
        demo_pipeline,
        "prepare_demo_inputs",
        side_effect=AssertionError("prepared Evidence"),
    ) as prepare, patch.object(
        decision_diff_rolelens,
        "build_rolelens_decision_revision",
        side_effect=AssertionError("built revision"),
    ) as build_revision, patch.object(
        decision_diff,
        "calculate_break_even_scenario",
        side_effect=AssertionError("calculated scenario"),
    ) as calculate, patch.object(
        os._Environ,
        "get",
        side_effect=AssertionError("environment read"),
    ), patch.object(
        socket,
        "create_connection",
        side_effect=AssertionError("network called"),
    ):
        module = importlib.import_module("app.decision_lab")
    assert hasattr(module, "main")
    assert rendered.call_count == 0
    assert read_bytes.call_count == 0
    assert read_text.call_count == 0
    assert prepare.call_count == 0
    assert build_revision.call_count == 0
    assert calculate.call_count == 0


def test_ibm_loader_prepares_real_observed_profile_without_provider_calls() -> None:
    """The explicit loader uses frozen context and returns exact observed facts."""
    lab = _lab()
    with patch(
        "app.granite_provider.GraniteRoleProvider.from_env"
    ) as role_factory, patch(
        "app.granite_semantic_risk_provider.GraniteSemanticRiskProvider.from_env"
    ) as semantic_factory, patch(
        "app.granite_dataset_orientation_provider."
        "GraniteDatasetOrientationProvider.from_env"
    ) as orientation_factory, patch.object(
        lab.demo_pipeline,
        "prepare_demo_inputs",
        wraps=lab.demo_pipeline.prepare_demo_inputs,
    ) as prepare:
        loaded = lab._load_ibm_telco_inputs()
    assert prepare.call_count == 1
    assert loaded.business_profile is not None
    profile = loaded.business_profile
    month_to_month = next(
        item for item in profile.contract_rates if item.segment == "Month-to-month"
    )
    assert profile.unique_customer_count == 7_043
    assert profile.overall_churn_rate_pct == 26.54
    assert month_to_month.churn_rate_pct == 42.71
    assert profile.total_charges_parse_issue_count == 11
    assert role_factory.call_count == 0
    assert semantic_factory.call_count == 0
    assert orientation_factory.call_count == 0


def test_baseline_eight_percent_uses_dd1_and_has_exact_bounded_presentation() -> None:
    """Baseline values come from DD-1 and use non-predictive product language."""
    lab = _lab()
    real_calculator = lab.decision_diff.calculate_break_even_scenario
    with patch.object(
        lab.decision_diff,
        "calculate_break_even_scenario",
        wraps=real_calculator,
    ) as calculate:
        result = lab._baseline_scenario()
    assert calculate.call_count == 1
    assert result.expected_incremental_retained == Decimal("40.00")
    assert result.expected_scenario_value == Decimal("20000.00")
    assert result.intervention_cost == Decimal("15000")
    assert result.net_scenario_value == Decimal("5000.00")
    assert result.break_even_lift == Decimal("0.06")
    assert result.status is ScenarioStatus.CLEARS_BREAK_EVEN
    rows = lab._baseline_rows(result)
    assert tuple(item["value"] for item in rows) == (
        "40",
        "20,000 USD",
        "15,000 USD",
        "+5,000 USD",
        "6%",
    )
    assert lab._status_label(result.status) == "Clears modeled break-even"
    primary = " ".join(item["value"] for item in rows).lower()
    assert not any(term in primary for term in _FORBIDDEN_PRIMARY_PHRASES)


def test_default_eight_to_three_uses_dd3_and_changes_exact_postures(
    prepared: PreparedDemoInputs,
) -> None:
    """The default Hero uses DD-3 and renders exact arithmetic and postures."""
    lab = _lab()
    real_builder = lab.decision_diff_rolelens.build_rolelens_decision_revision
    with patch.object(
        lab.decision_diff_rolelens,
        "build_rolelens_decision_revision",
        wraps=real_builder,
    ) as builder:
        revision = lab._build_revision(prepared, Decimal("0.03"))
    assert builder.call_count == 1
    assert revision.before_projection.scenario_result.net_scenario_value == Decimal(
        "5000.00"
    )
    assert revision.after_projection.scenario_result.net_scenario_value == Decimal(
        "-7500.00"
    )
    assert revision.before_projection.executive_posture is (
        ExecutiveScenarioPosture.LIMITED_PILOT_REVIEW_CANDIDATE
    )
    assert revision.after_projection.executive_posture is (
        ExecutiveScenarioPosture.VALIDATE_SCENARIO_ASSUMPTIONS_FIRST
    )
    assert revision.before_projection.sales_posture is (
        SalesPilotPosture.ELIGIBLE_FOR_PILOT_REVIEW
    )
    assert revision.after_projection.sales_posture is (
        SalesPilotPosture.BLOCKED_BY_SCENARIO
    )
    assert revision.before_projection.project_manager_handoff is (
        ProjectManagerHandoff.PREPARE_LIMITED_PILOT_REVIEW
    )
    assert revision.after_projection.project_manager_handoff is (
        ProjectManagerHandoff.REOPEN_SCENARIO_VALIDATION
    )
    assert lab._headline(revision) == "Decision posture changed"
    assert lab._decision_diff_headings(revision) == (
        "Decision posture changed",
        "What must be reconsidered",
        "Why did the decision posture change?",
    )
    rows = lab._before_after_rows(revision, Decimal("0.03"))
    row_map = {item["Row"]: item for item in rows}
    assert row_map["Expected lift"] == {
        "Row": "Expected lift",
        "Before": "8.0%",
        "After": "3.0%",
    }
    assert row_map["Net scenario value"]["After"] == "-7,500 USD"
    assert row_map["Sales pilot posture"]["After"] == "Blocked by scenario"


def test_eight_to_seven_keeps_candidate_postures_and_same_posture_headline(
    prepared: PreparedDemoInputs,
) -> None:
    """The clearing control recomputes artifacts without changing postures."""
    lab = _lab()
    revision = _revision(prepared, "0.07")
    assert revision.after_projection.scenario_result.net_scenario_value == Decimal(
        "2500.00"
    )
    assert revision.after_projection.scenario_result.status is (
        ScenarioStatus.CLEARS_BREAK_EVEN
    )
    assert revision.after_projection.executive_posture is (
        ExecutiveScenarioPosture.LIMITED_PILOT_REVIEW_CANDIDATE
    )
    assert revision.after_projection.sales_posture is (
        SalesPilotPosture.ELIGIBLE_FOR_PILOT_REVIEW
    )
    rows = lab._before_after_rows(revision, Decimal("0.07"))
    row_map = {item["Row"]: item for item in rows}
    assert row_map["Sales pilot posture"]["After"] == "Eligible for pilot review"
    assert revision.after_projection.project_manager_handoff is (
        ProjectManagerHandoff.PREPARE_LIMITED_PILOT_REVIEW
    )
    assert lab._headline(revision) == (
        "Scenario changed; decision posture remains the same"
    )
    assert lab._decision_diff_headings(revision) == (
        "Scenario changed; decision posture remains the same",
        "What was recomputed",
        "Why was the scenario recomputed?",
    )
    explanation = lab._change_explanation(revision)
    assert "still clears modeled break-even" in explanation
    assert "postures remained logically the same" in explanation
    impacts = _impact_map(revision)
    assert impacts == {
        "obj-observed-evidence": DecisionImpactType.UNCHANGED,
        "obj-data-health": DecisionImpactType.UNCHANGED,
        "obj-source-provenance": DecisionImpactType.UNCHANGED,
        "obj-break-even": DecisionImpactType.RECOMPUTED,
        "obj-executive-posture": DecisionImpactType.RECOMPUTED,
        "obj-sales-posture": DecisionImpactType.RECOMPUTED,
        "obj-pm-handoff": DecisionImpactType.RECOMPUTED,
        "obj-decision-brief": DecisionImpactType.STALE,
    }


def test_eight_to_eight_has_no_changes_all_unchanged_and_no_change_headline(
    prepared: PreparedDemoInputs,
) -> None:
    """Identical values across revisions produce a fully unchanged control."""
    lab = _lab()
    revision = _revision(prepared, "0.08")
    assert revision.decision_diff.changed_assumptions == ()
    assert all(
        item.impact_type is DecisionImpactType.UNCHANGED
        for item in revision.decision_diff.impacts
    )
    assert lab._headline(revision) == "No scenario assumption changed"
    assert "Decision posture changed" not in lab._headline(revision)
    assert lab._decision_diff_headings(revision) == (
        "No scenario assumption changed",
        "Decision impact",
        "Why did nothing change?",
    )
    explanation = lab._change_explanation(revision)
    assert "No registered dependency was triggered" in explanation
    assert "every registered impact remained unchanged" in explanation


def test_observed_evidence_presentation_is_exact_context_not_financial_input(
    prepared: PreparedDemoInputs,
) -> None:
    """The compact basis has exactly seven items and the mandatory boundary."""
    lab = _lab()
    rows = lab._evidence_rows(prepared)
    assert len(rows) == 7
    assert tuple(item["evidence_type"] for item in rows) == tuple(
        lab._EVIDENCE_LABELS
    )
    assert set(rows[0]) == {"evidence_type", "evidence_id", "short finding"}
    assert all(item["evidence_id"].startswith("ev-") for item in rows)
    assert "snapshot_json" not in json.dumps(rows)
    assert lab._EVIDENCE_CONTEXT_CAPTION == (
        "These Evidence Objects provide the unchanged observed business context. "
        "They are not financial inputs to the break-even formula."
    )
    revision = _revision(prepared, "0.03")
    assert tuple(item["evidence_id"] for item in rows) == (
        revision.unchanged_evidence_ids
    )


def test_currency_is_user_supplied_dataset_currency_uninferred_and_assumptions_separate(
    prepared: PreparedDemoInputs,
) -> None:
    """UI wording and contracts preserve the Evidence/assumption boundary."""
    lab = _lab()
    assert lab._CURRENCY_NOTICE == (
        "Scenario currency: USD — supplied by the user, not inferred from the IBM "
        "dataset."
    )
    assert lab._DATASET_CURRENCY_NOTICE == (
        "The IBM dataset's MonthlyCharges / TotalCharges currency remains "
        "unspecified."
    )
    assumptions = lab._scenario_assumptions("rev-001", Decimal("0.08"))
    assert all(isinstance(item, ScenarioAssumption) for item in assumptions)
    assert all(item.source_scope == "user_assumption" for item in assumptions)
    assert all(
        "evidence_id" not in item.model_fields and "source_id" not in item.model_fields
        for item in assumptions
    )
    basis_ids = {item["evidence_id"] for item in lab._evidence_rows(prepared)}
    assumption_evidence = {
        item.evidence_id
        for item in prepared.evidence_objects
        if item.evidence_scope is EvidenceScope.assumption
    }
    assert assumption_evidence
    assert basis_ids.isdisjoint(assumption_evidence)


def test_edit_and_controlled_failure_clear_prior_revision_state(
    prepared: PreparedDemoInputs,
) -> None:
    """Widget edits and failed DD-3 builds cannot leave stale revision output."""
    lab = _lab()
    old_revision = _revision(prepared, "0.03")
    state: dict[str, object] = {
        lab._SK_REVISION: old_revision,
        lab._SK_REVISION_LIFT: Decimal("3.0"),
    }
    lab._clear_revision(state)
    assert lab._SK_REVISION not in state
    assert lab._SK_REVISION_LIFT not in state

    state.update(
        {
            lab._SK_REVISION: old_revision,
            lab._SK_REVISION_LIFT: Decimal("3.0"),
        }
    )
    with patch.object(
        lab,
        "_build_revision",
        side_effect=RoleLensDecisionDiffError("controlled"),
    ), pytest.raises(RoleLensDecisionDiffError):
        lab._calculate_and_store_revision(
            state,
            prepared,
            Decimal("7.0"),
        )
    assert lab._SK_REVISION not in state
    assert lab._SK_REVISION_LIFT not in state

    loaded_state: dict[str, object] = {
        lab._SK_REVISION: old_revision,
        lab._SK_REVISION_LIFT: Decimal("3.0"),
    }
    lab._store_loaded_inputs(loaded_state, prepared)
    assert loaded_state[lab._SK_LIFT_WIDGET] == 8.0
    assert lab._SK_REVISION not in loaded_state
    assert lab._SK_REVISION_LIFT not in loaded_state


def test_streamlit_apptest_full_provider_free_hero_path() -> None:
    """AppTest validates the complete one-page default Hero interaction."""
    try:
        from streamlit.testing.v1 import AppTest
    except ImportError:
        return

    lab = _lab()
    real_builder = importlib.import_module(
        "app.decision_diff_rolelens"
    ).build_rolelens_decision_revision
    with patch.dict(
        os.environ,
        {
            "WATSONX_APIKEY": "secret-dd4-key",
            "WATSONX_URL": "https://example.invalid",
            "WATSONX_PROJECT_ID": "secret-dd4-project",
        },
        clear=False,
    ), patch(
        "app.granite_provider.GraniteRoleProvider.from_env"
    ) as role_factory, patch(
        "app.granite_semantic_risk_provider.GraniteSemanticRiskProvider.from_env"
    ) as semantic_factory, patch(
        "app.granite_dataset_orientation_provider."
        "GraniteDatasetOrientationProvider.from_env"
    ) as orientation_factory:
        with patch(
            "app.decision_diff_rolelens.build_rolelens_decision_revision",
            wraps=real_builder,
        ) as revision_builder:
            app = AppTest.from_file(str(_MODULE_PATH), default_timeout=30).run()
            assert not app.exception
            assert len(app.title) == 1
            assert app.title[0].value == "RoleLens Decision Lab"
            assert not app.tabs
            assert len(app.button) == 1
            assert app.button[0].label == "Load IBM Telco evidence"
            initial = _rendered_text(app)
            assert (
                "Observed Evidence → Human Assumption → Recalculation → Decision Diff"
                in initial
            )
            assert not app.metric
            assert not app.dataframe

            app = app.button[0].click().run()
            assert not app.exception
            loaded_text = _rendered_text(app)
            for fact in ("7,043", "26.54%", "42.71%", "11"):
                assert fact in loaded_text
            assert lab._FIXED_INPUT_DISCLOSURE in loaded_text
            assert app.session_state[lab._SK_LIFT_WIDGET] == 8.0
            assert lab._SK_REVISION not in app.session_state
            assert "Decision posture changed" not in loaded_text
            assert revision_builder.call_count == 0
            assert any(
                expander.label == "View unchanged Evidence basis"
                for expander in app.expander
            )
            lift_input = next(
                item
                for item in app.number_input
                if item.label.startswith("Expected incremental lift (%)")
            )
            assert lift_input.value == 8.0
            app = lift_input.set_value(3.0).run()
            assert lab._SK_REVISION not in app.session_state
            assert "Decision posture changed" not in _rendered_text(app)
            assert revision_builder.call_count == 0
            recalculate = next(
                button
                for button in app.button
                if button.label == "Recalculate decision"
            )
            app = recalculate.click().run()
            assert not app.exception
            assert revision_builder.call_count == 1
            rendered = _rendered_text(app)
            for required in (
                "Decision posture changed",
                "What must be reconsidered",
                "Why did the decision posture change?",
                "8.0%",
                "3.0%",
                "+5,000 USD",
                "-7,500 USD",
                "Blocked by scenario",
                "Observed Evidence remained unchanged.",
                (
                    "The human changed a scenario assumption. The underlying "
                    "observed dataset, Evidence IDs, findings, data-health result, "
                    "and source provenance did not change."
                ),
            ):
                assert required in rendered
            assert any(
                expander.label == "View unchanged Evidence basis"
                for expander in app.expander
            )
            assert "snapshot_json" not in rendered
            assert "identity_digest" not in rendered
            assert "secret-dd4-key" not in rendered
            assert "secret-dd4-project" not in rendered
            lowered = rendered.lower()
            assert not any(term in lowered for term in _FORBIDDEN_PRIMARY_PHRASES)
            assert role_factory.call_count == 0
            assert semantic_factory.call_count == 0
            assert orientation_factory.call_count == 0

            lift_input = next(
                item
                for item in app.number_input
                if item.label.startswith("Expected incremental lift (%)")
            )
            app = lift_input.set_value(7.0).run()
            assert lab._SK_REVISION not in app.session_state
            assert "Decision posture changed" not in _rendered_text(app)
            assert revision_builder.call_count == 1

    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    tests = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test_")
    ]
    assert len(tests) == 10
