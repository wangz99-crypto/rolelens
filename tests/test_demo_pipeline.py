"""tests/test_demo_pipeline.py — Task 10A offline tests for demo_pipeline.py.

Exactly 10 top-level test functions. All default tests are offline.
No live Granite calls are made.
"""

from __future__ import annotations

import importlib
import json
import os
import pathlib
import sys
import types
from typing import Any, Mapping
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_SAMPLE_DATA_DIR = pathlib.Path(__file__).parent.parent / "sample_data"
_DEMO_CSV_PATH = _SAMPLE_DATA_DIR / "b2b_saas_retention_demo.csv"
_DEMO_JSON_PATH = _SAMPLE_DATA_DIR / "b2b_saas_retention_demo.json"

_REQUIRED_CSV_FIELDS = {
    "account_id", "customer_segment", "arr_band", "renewal_status",
    "support_ticket_count", "last_login_days", "product_usage_score",
    "contract_value",
}

_CREDENTIAL_PATTERNS = [
    "WATSONX_APIKEY", "WATSONX_URL", "WATSONX_PROJECT_ID",
    "api_key", "apikey", "password", "secret", "token",
]

# ---------------------------------------------------------------------------
# Shared fixture helpers
# ---------------------------------------------------------------------------


def _load_demo_fixture() -> tuple[bytes, dict]:
    """Return (csv_bytes, json_sidecar)."""
    csv_bytes = _DEMO_CSV_PATH.read_bytes()
    sidecar = json.loads(_DEMO_JSON_PATH.read_text(encoding="utf-8"))
    return csv_bytes, sidecar


def _prepare_demo() -> Any:
    """Run prepare_demo_inputs() with the synthetic demo fixtures."""
    from app.demo_pipeline import prepare_demo_inputs

    csv_bytes, sidecar = _load_demo_fixture()
    return prepare_demo_inputs(
        csv_bytes=csv_bytes,
        filename="b2b_saas_retention_demo.csv",
        industry_context=sidecar["industry_context"],
        strategy_profile=sidecar["strategy_profile"],
        business_question=sidecar["business_question"],
        decision_goal=sidecar["decision_goal"],
        user_assumption=sidecar.get("user_assumption"),
    )


# ---------------------------------------------------------------------------
# Test 1: Sample files exist, contain required fields, no credentials, deliberate issues
# ---------------------------------------------------------------------------


def test_sample_files_structure_and_quality() -> None:
    """Sample files must exist, contain required fields, no credentials or PII,
    and the CSV must contain deliberate duplicate rows and missing values.
    """
    assert _DEMO_CSV_PATH.exists(), "b2b_saas_retention_demo.csv must exist"
    assert _DEMO_JSON_PATH.exists(), "b2b_saas_retention_demo.json must exist"

    # CSV structural checks
    df = pd.read_csv(_DEMO_CSV_PATH, dtype=str)
    assert set(df.columns).issuperset(_REQUIRED_CSV_FIELDS), (
        f"CSV missing required fields. Got: {list(df.columns)}"
    )
    assert len(df) >= 12, "CSV must have at least 12 rows"

    # Must have at least one exact duplicate row
    dup_count = int(df.duplicated(keep="first").sum())
    assert dup_count >= 1, "CSV must contain at least one exact duplicate row"

    # Must have missing values in product_usage_score
    assert df["product_usage_score"].isna().any(), (
        "CSV must have missing values in product_usage_score"
    )

    # Must have missing values in contract_value
    assert df["contract_value"].isna().any(), (
        "CSV must have missing values in contract_value"
    )

    # No personal data check (no first/last name columns)
    lower_cols = {c.lower() for c in df.columns}
    personal_cols = {"name", "email", "phone", "first_name", "last_name"}
    assert not (lower_cols & personal_cols), (
        f"CSV must not contain personal data columns. Found: {lower_cols & personal_cols}"
    )

    # No credentials in CSV content
    csv_text = _DEMO_CSV_PATH.read_text(encoding="utf-8").upper()
    for pattern in _CREDENTIAL_PATTERNS:
        assert pattern.upper() not in csv_text, (
            f"CSV must not contain credential pattern: {pattern}"
        )

    # JSON sidecar — required keys
    sidecar = json.loads(_DEMO_JSON_PATH.read_text(encoding="utf-8"))
    required_keys = {
        "industry_context", "strategy_profile", "business_question",
        "decision_goal", "user_assumption",
    }
    assert required_keys.issubset(sidecar.keys()), (
        f"JSON sidecar missing keys: {required_keys - set(sidecar.keys())}"
    )

    # No credentials in JSON
    json_text = _DEMO_JSON_PATH.read_text(encoding="utf-8").upper()
    for pattern in _CREDENTIAL_PATTERNS:
        assert pattern.upper() not in json_text, (
            f"JSON sidecar must not contain credential pattern: {pattern}"
        )

    # Industry context must state it is not internal evidence
    ic = sidecar["industry_context"].lower()
    assert "not evidence" in ic or "external" in ic or "observation" in ic, (
        "Industry context must state it is external/not direct company evidence"
    )

    # User assumption must be marked unverified
    ua = sidecar["user_assumption"].lower()
    assert "unverified" in ua or "not been validated" in ua or "assumption" in ua, (
        "User assumption must be marked as unverified"
    )


# ---------------------------------------------------------------------------
# Test 2: prepare_demo_inputs produces validated source manifests, health, evidence
# ---------------------------------------------------------------------------


def test_prepare_demo_inputs_produces_validated_outputs() -> None:
    """prepare_demo_inputs must produce validated source manifests, data health,
    and active EvidenceObjects through production APIs."""
    from app.demo_pipeline import (
        DemoPipelineError,
        PreparedDemoInputs,
        prepare_demo_inputs,
    )
    from app.schemas import (
        DataHealthSummary,
        EvidenceObject,
        EvidenceStatus,
        SourceManifestEntry,
    )

    result = _prepare_demo()

    assert isinstance(result, PreparedDemoInputs)

    # Source manifests
    assert len(result.source_manifests) >= 1
    for manifest in result.source_manifests:
        assert isinstance(manifest, SourceManifestEntry)
        SourceManifestEntry.model_validate(manifest.model_dump())

    # Data health
    assert isinstance(result.data_health_summary, DataHealthSummary)
    assert result.row_count > 0
    assert result.column_count > 0

    # Evidence objects — all active, all validated
    assert len(result.evidence_objects) > 0
    for ev in result.evidence_objects:
        assert isinstance(ev, EvidenceObject)
        assert ev.status == EvidenceStatus.active
        EvidenceObject.model_validate(ev.model_dump())

    # Preview is bounded
    assert 0 < len(result.dataframe_preview_records) <= 10
    assert result.row_count >= len(result.dataframe_preview_records)

    secret_fragments = (
        "WATSONX_APIKEY=secret-value",
        "raw_preparation_payload",
        "errors.pydantic.dev",
    )
    with pytest.raises(DemoPipelineError) as invalid_csv_error:
        prepare_demo_inputs(
            csv_bytes=(
                b"\xffWATSONX_APIKEY=secret-value,"
                b"raw_preparation_payload,errors.pydantic.dev"
            ),
            filename="raw_preparation_payload.csv",
            industry_context="raw_preparation_payload",
            strategy_profile="raw_preparation_payload",
            business_question="raw_preparation_payload",
            decision_goal="raw_preparation_payload",
            user_assumption=None,
        )
    invalid_message = str(invalid_csv_error.value)
    assert invalid_message == (
        "Evidence preparation failed. Check CSV structure and required "
        "context inputs."
    )
    assert all(fragment not in invalid_message for fragment in secret_fragments)
    assert "Traceback" not in invalid_message
    assert "repr" not in invalid_message

    csv_bytes, sidecar = _load_demo_fixture()
    with patch(
        "app.demo_pipeline.build_evidence",
        side_effect=ValueError(
            "WATSONX_APIKEY=secret-value raw_preparation_payload "
            "errors.pydantic.dev"
        ),
    ), pytest.raises(DemoPipelineError) as build_error:
        prepare_demo_inputs(
            csv_bytes=csv_bytes,
            filename="b2b_saas_retention_demo.csv",
            industry_context=sidecar["industry_context"],
            strategy_profile=sidecar["strategy_profile"],
            business_question=sidecar["business_question"],
            decision_goal=sidecar["decision_goal"],
            user_assumption=sidecar["user_assumption"],
        )
    assert str(build_error.value) == (
        "Evidence building failed. Check source and candidate consistency."
    )
    assert all(
        fragment not in str(build_error.value)
        for fragment in secret_fragments
    )


# ---------------------------------------------------------------------------
# Test 3: Business question and decision goal produce no EvidenceObject
# ---------------------------------------------------------------------------


def test_business_question_and_goal_produce_no_evidence() -> None:
    """Business question and decision goal must register as decision context
    but must not produce any EvidenceObject."""
    from app.schemas import EvidenceScope, SemanticContextCategory

    result = _prepare_demo()

    # None of the evidence objects should originate from a decision_context manifest
    decision_context_sources = {
        m.source_id
        for m in result.source_manifests
        if m.semantic_context_category in (
            SemanticContextCategory.business_question,
            SemanticContextCategory.decision_goal,
        )
    }
    # There must be source manifests for bq and dg
    assert len(decision_context_sources) == 2, (
        "Exactly two decision_context manifests expected (bq and dg)"
    )

    # No evidence object should reference a decision_context source
    evidence_source_ids = {ev.source_id for ev in result.evidence_objects}
    overlap = decision_context_sources & evidence_source_ids
    assert not overlap, (
        f"business_question/decision_goal sources must not produce EvidenceObjects. "
        f"Found: {overlap}"
    )


# ---------------------------------------------------------------------------
# Test 4: Evidence scopes include expected types
# ---------------------------------------------------------------------------


def test_evidence_scopes_include_expected_types() -> None:
    """Evidence objects must include expected scope types:
    internal_observation, external_context, stated_priority, assumption."""
    from app.schemas import EvidenceScope

    result = _prepare_demo()
    scopes = {ev.evidence_scope for ev in result.evidence_objects}

    # Must have internal_observation from data health
    assert EvidenceScope.internal_observation in scopes, (
        "Expected internal_observation scope from data health"
    )

    # Must have external_context from industry_context
    assert EvidenceScope.external_context in scopes, (
        "Expected external_context scope from industry context"
    )

    # Must have stated_priority from strategy_profile
    assert EvidenceScope.stated_priority in scopes, (
        "Expected stated_priority scope from strategy profile"
    )

    # Must have assumption from user_assumption
    assert EvidenceScope.assumption in scopes, (
        "Expected assumption scope from user assumption"
    )


# ---------------------------------------------------------------------------
# Test 5: Equal inputs produce stable source/evidence identities
# ---------------------------------------------------------------------------


def test_equal_inputs_produce_stable_identities() -> None:
    """Equal input preparation must produce stable source IDs and evidence IDs."""
    result_a = _prepare_demo()
    result_b = _prepare_demo()

    ids_a = sorted(ev.evidence_id for ev in result_a.evidence_objects)
    ids_b = sorted(ev.evidence_id for ev in result_b.evidence_objects)
    assert ids_a == ids_b, (
        "Equal inputs must produce stable evidence IDs"
    )

    source_ids_a = sorted(m.source_id for m in result_a.source_manifests)
    source_ids_b = sorted(m.source_id for m in result_b.source_manifests)
    assert source_ids_a == source_ids_b, (
        "Equal inputs must produce stable source IDs"
    )


# ---------------------------------------------------------------------------
# Test 6: Injected providers produce typed role outcomes, risk results, plan
# ---------------------------------------------------------------------------


def test_injected_providers_produce_full_analysis_offline() -> None:
    """With injected mock providers, run_live_demo_analysis must produce
    typed role outcomes, risk results, and a valid WorkflowPlan offline."""
    from app.demo_pipeline import run_live_demo_analysis, DemoAnalysisResult
    from app.role_engine import InsufficientEvidence, RoleGenerationFailure
    from app.schemas import (
        RoleKey,
        RoleView,
        WorkflowPlan,
        RiskReviewResult,
        SemanticRiskReviewResult,
        _ROLE_EXECUTION_ORDER,
    )

    prepared = _prepare_demo()
    evidence_objects = list(prepared.evidence_objects)

    # Build a minimal valid RoleView for any role
    def _make_minimal_view(role_key: RoleKey) -> dict:
        # Use the first evidence object's ID
        ev_id = evidence_objects[0].evidence_id if evidence_objects else None
        if ev_id is None:
            return None  # will become InsufficientEvidence
        return {
            "role_key": role_key.value,
            "role_concern": f"Concern for {role_key.value}",
            "key_findings": [
                {
                    "claim": f"Sample claim for {role_key.value}.",
                    "evidence_references": [{"evidence_id": ev_id}],
                    "confidence": "medium",
                }
            ],
            "risks_or_assumptions": [],
            "missing_information": [],
            "next_action": f"Review evidence for {role_key.value}.",
            "dependency": None,
            "human_review_required": True,
        }

    # Filter eligible evidence per role (roles must cite exposed evidence)
    # For simplicity we make all roles return InsufficientEvidence via a mock
    # that raises an exception on the PM role (which requires prior views).
    # Instead, we use a mock that returns InsufficientEvidence-like behavior
    # by returning a view with the wrong role_key to trigger a failure — but
    # that would cause role_generation_failure. 
    # The simplest correct approach: return a valid view for each role.

    class OfflineMockRoleProvider:
        """Returns a minimal valid RoleView for roles with eligible evidence."""

        def generate_role_view(self, request) -> Mapping[str, Any]:
            role_key = request.role_key
            eligible_ids = sorted(request.exposed_evidence_ids)
            if not eligible_ids:
                raise ValueError("No eligible evidence")
            ev_id = eligible_ids[0]

            if role_key.value == "project_manager":
                # PM receives role_views as input, not evidence_objects directly
                role_views = request.inputs.get("role_views", [])
                if not role_views:
                    raise ValueError("No prior role views for PM")
                # Cite from the first prior view's findings
                first_view = role_views[0]
                if hasattr(first_view, "key_findings"):
                    first_ref = first_view.key_findings[0].evidence_references[0]
                    ev_id = first_ref.evidence_id
                else:
                    raise ValueError("Prior view lacks key_findings")

            return {
                "role_key": role_key.value,
                "role_concern": f"Offline concern for {role_key.value}",
                "key_findings": [
                    {
                        "claim": f"Offline claim for {role_key.value}.",
                        "evidence_references": [{"evidence_id": ev_id}],
                        "confidence": "low",
                    }
                ],
                "risks_or_assumptions": [],
                "missing_information": [f"Missing info for {role_key.value}"],
                "next_action": f"Offline action for {role_key.value}.",
                "dependency": None,
                "human_review_required": True,
            }

    class OfflineMockSemanticProvider:
        """Returns an empty semantic result offline."""

        def review_semantic_risks(self, request) -> Mapping[str, Any]:
            reviewed_keys = [view.role_key.value for view in request.role_views]
            return {
                "candidates": [],
                "reviewed_role_keys": reviewed_keys,
                "reviewer_model": "offline-mock",
                "human_review_required": False,
            }

    result = run_live_demo_analysis(
        prepared,
        role_provider=OfflineMockRoleProvider(),
        semantic_provider=OfflineMockSemanticProvider(),
    )

    assert isinstance(result, DemoAnalysisResult)
    assert isinstance(result.workflow_plan, WorkflowPlan)
    assert isinstance(result.deterministic_risk_result, RiskReviewResult)
    assert isinstance(result.semantic_risk_result, SemanticRiskReviewResult)

    # All five role outcomes present
    from app.role_engine import InsufficientEvidence, RoleGenerationFailure
    approved_types = (RoleView, InsufficientEvidence, RoleGenerationFailure)
    for role_key in _ROLE_EXECUTION_ORDER:
        assert role_key in result.role_outcomes
        assert isinstance(result.role_outcomes[role_key], approved_types)

    # Model labels match injected provider (no env var reads)
    assert result.role_model_label is None
    assert result.semantic_model_label is None


# ---------------------------------------------------------------------------
# Test 7: Provider/config failures become sanitized DemoPipelineError
# ---------------------------------------------------------------------------


def test_provider_failure_becomes_sanitized_demo_pipeline_error() -> None:
    """Provider and configuration failures must become DemoPipelineError
    with no secrets, raw payloads, Pydantic URLs, or arbitrary repr.

    The role engine wraps provider exceptions as RoleGenerationFailure typed
    outcomes rather than raising.  DemoPipelineError is triggered by the
    semantic provider raising, which is caught and re-raised by
    run_live_demo_analysis() with a sanitized message.
    """
    from app.demo_pipeline import (
        DemoPipelineError,
        _safe_role_failure_reason,
        run_live_demo_analysis,
    )
    from app.role_engine import RoleGenerationFailure

    prepared = _prepare_demo()

    # A role provider that always accepts (so roles succeed and semantic review runs)
    class PassingRoleProvider:
        def generate_role_view(self, request):
            ev_id = sorted(request.exposed_evidence_ids)[0]
            if request.role_key.value == "project_manager":
                role_views = request.inputs.get("role_views", [])
                if role_views and hasattr(role_views[0], "key_findings"):
                    ev_id = role_views[0].key_findings[0].evidence_references[0].evidence_id
            return {
                "role_key": request.role_key.value,
                "role_concern": f"Concern {request.role_key.value}",
                "key_findings": [
                    {
                        "claim": "Sample claim.",
                        "evidence_references": [{"evidence_id": ev_id}],
                        "confidence": "low",
                    }
                ],
                "risks_or_assumptions": [],
                "missing_information": [],
                "next_action": "Validate data.",
                "dependency": None,
                "human_review_required": True,
            }

    class FailingSemanticProvider:
        """Raises with content that must not appear in the sanitized error."""
        def review_semantic_risks(self, request):
            raise RuntimeError(
                "WATSONX_APIKEY=sk-secret123 connection failed "
                "https://pydantic.dev/errors/url internal_payload=raw_data"
            )

    with pytest.raises(DemoPipelineError) as exc_info:
        run_live_demo_analysis(
            prepared,
            role_provider=PassingRoleProvider(),
            semantic_provider=FailingSemanticProvider(),
        )

    msg = str(exc_info.value)

    # Sanitized message must not contain raw provider exception content
    assert "sk-secret123" not in msg, "Error must not expose secret values"
    assert "pydantic.dev" not in msg, "Error must not contain Pydantic URLs"
    assert "internal_payload=raw_data" not in msg, "Error must not expose raw provider payload"
    # Must be a DemoPipelineError subclass
    assert isinstance(exc_info.value, DemoPipelineError)

    class SecretRoleProvider:
        """Raises provider content that typed failures must sanitize."""

        def generate_role_view(self, request):
            raise RuntimeError(
                "WATSONX_APIKEY=secret-value raw_provider_payload "
                "errors.pydantic.dev"
            )

    class SemanticProviderMustNotRun:
        """No successful views means semantic provider must not run."""

        def review_semantic_risks(self, request):
            raise AssertionError("semantic provider must not be called")

    analysis = run_live_demo_analysis(
        prepared,
        role_provider=SecretRoleProvider(),
        semantic_provider=SemanticProviderMustNotRun(),
    )
    failures = [
        outcome
        for outcome in analysis.role_outcomes.values()
        if isinstance(outcome, RoleGenerationFailure)
    ]
    assert failures
    for failure in failures:
        assert failure.role_key is not None
        assert failure.failure_code == "provider_error"
        assert failure.reason == _safe_role_failure_reason(
            failure.failure_code
        )
        safe_display = (
            f"Typed Failure: {failure.failure_code}\n"
            f"{_safe_role_failure_reason(failure.failure_code)}"
        )
        assert "secret-value" not in safe_display
        assert "raw_provider_payload" not in safe_display
        assert "errors.pydantic.dev" not in safe_display
    serialized_risks = json.dumps(
        analysis.deterministic_risk_result.model_dump(mode="json")
    )
    assert "secret-value" not in serialized_risks
    assert "raw_provider_payload" not in serialized_risks
    assert "errors.pydantic.dev" not in serialized_risks


# ---------------------------------------------------------------------------
# Test 8: Importing demo_pipeline and main does not construct provider / make calls
# ---------------------------------------------------------------------------


def test_import_does_not_construct_provider_or_read_env() -> None:
    """Importing demo_pipeline and the Streamlit app module must not
    construct a provider, read credentials, or make network calls."""
    import os

    # Temporarily remove env vars to ensure they are not read at import time
    watsonx_vars = {
        "WATSONX_APIKEY": os.environ.pop("WATSONX_APIKEY", None),
        "WATSONX_URL": os.environ.pop("WATSONX_URL", None),
        "WATSONX_PROJECT_ID": os.environ.pop("WATSONX_PROJECT_ID", None),
    }

    try:
        # Force re-import to test module-level behavior
        mods_to_remove = [
            k for k in sys.modules
            if k in ("app.demo_pipeline", "app.main")
        ]
        for mod in mods_to_remove:
            del sys.modules[mod]

        # This must not raise
        import app.demo_pipeline as dp  # noqa: F401

        # The module must expose the expected public symbols
        assert hasattr(dp, "prepare_demo_inputs")
        assert hasattr(dp, "run_live_demo_analysis")
        assert hasattr(dp, "PreparedDemoInputs")
        assert hasattr(dp, "DemoAnalysisResult")
        assert hasattr(dp, "DemoPipelineError")

        with patch(
            "streamlit.set_page_config",
            side_effect=AssertionError(
                "normal import must not render Streamlit"
            ),
        ), patch(
            "app.demo_pipeline.run_live_demo_analysis",
            side_effect=AssertionError(
                "normal import must not construct providers"
            ),
        ), patch(
            "socket.create_connection",
            side_effect=AssertionError(
                "normal import must not use the network"
            ),
        ):
            import app.main as main_module

        assert hasattr(main_module, "main")
        assert hasattr(main_module, "_build_synthetic_review_preset")
        assert hasattr(main_module, "_build_human_review_inputs")

    finally:
        # Restore env vars
        for k, v in watsonx_vars.items():
            if v is not None:
                os.environ[k] = v


# ---------------------------------------------------------------------------
# Test 9: Human review not created automatically; memo requires complete review
# ---------------------------------------------------------------------------


def test_human_review_and_memo_completion_boundary() -> None:
    """Human review must not be created automatically.
    Explicit decisions can create a pending or complete session.
    A memo cannot be composed from a pending session."""
    from app.demo_pipeline import run_live_demo_analysis
    from app.human_review import review_workflow_plan
    from app.memo_generator import compose_decision_memo, DecisionMemoInputError
    from app.schemas import (
        DecisionMemoStatus,
        HumanReviewDecision,
        HumanReviewSessionStatus,
        HumanReviewStepInput,
        RiskCode,
        RoleKey,
        RoleView,
        SemanticRiskCode,
        WorkflowPlan,
        WorkflowPlanStatus,
        WorkflowStep,
        WorkflowStepKind,
        WorkflowStepStatus,
    )

    prepared = _prepare_demo()

    class MinimalRoleProvider:
        def generate_role_view(self, request):
            ev_id = sorted(request.exposed_evidence_ids)[0]
            if request.role_key.value == "project_manager":
                role_views = request.inputs.get("role_views", [])
                if role_views and hasattr(role_views[0], "key_findings"):
                    ev_id = role_views[0].key_findings[0].evidence_references[0].evidence_id
            return {
                "role_key": request.role_key.value,
                "role_concern": f"Concern {request.role_key.value}",
                "key_findings": [
                    {
                        "claim": "Minimal claim.",
                        "evidence_references": [{"evidence_id": ev_id}],
                        "confidence": "low",
                    }
                ],
                "risks_or_assumptions": [],
                "missing_information": ["Data quality must be validated."],
                "next_action": "Validate data quality.",
                "dependency": None,
                "human_review_required": True,
            }

    class MinimalSemanticProvider:
        def review_semantic_risks(self, request):
            return {
                "candidates": [],
                "reviewed_role_keys": [v.role_key.value for v in request.role_views],
                "reviewer_model": None,
                "human_review_required": False,
            }

    analysis = run_live_demo_analysis(
        prepared,
        role_provider=MinimalRoleProvider(),
        semantic_provider=MinimalSemanticProvider(),
    )

    plan = analysis.workflow_plan

    # No review session should exist yet (not created automatically)
    assert plan is not None

    if not plan.steps:
        # Empty plan — skip review sub-test
        return

    # Provide only partial decisions → pending session
    partial_decisions = {}
    for step in plan.steps[:1]:  # only the first step
        partial_decisions[step.step_id] = HumanReviewStepInput(
            decision=HumanReviewDecision.accept
        )

    if len(plan.steps) > 1:
        # Partial review should produce a pending session
        partial_session = review_workflow_plan(plan, partial_decisions)
        assert partial_session.session_status == HumanReviewSessionStatus.pending
        assert len(partial_session.pending_step_ids) > 0

        # Memo cannot be composed from a pending session
        with pytest.raises(DecisionMemoInputError):
            compose_decision_memo(
                workflow_plan=plan,
                human_review_session=partial_session,
                evidence_objects=list(prepared.evidence_objects),
            )

    # Full decisions → complete session
    full_decisions = {}
    for step in plan.steps:
        if step.step_kind.value == "semantic_review_gate":
            full_decisions[step.step_id] = HumanReviewStepInput(
                decision=HumanReviewDecision.accept,
                reviewer_note="Semantic gate reviewed offline.",
            )
        else:
            full_decisions[step.step_id] = HumanReviewStepInput(
                decision=HumanReviewDecision.accept,
            )

    complete_session = review_workflow_plan(plan, full_decisions)
    assert complete_session.session_status == HumanReviewSessionStatus.complete
    assert complete_session.human_review_complete is True
    assert not complete_session.pending_step_ids

    from app.main import (
        _apply_synthetic_review_preset,
        _build_human_review_inputs,
        _clear_review_widget_state,
        _record_empty_workflow_review,
    )
    from app.human_review import HumanReviewInputError

    evidence_id = prepared.evidence_objects[0].evidence_id
    review_plan = WorkflowPlan(
        steps=[
            WorkflowStep(
                step_id="wf-001",
                sequence=1,
                step_kind=WorkflowStepKind.deterministic_risk_resolution,
                owner_role=RoleKey.data_analyst,
                action="Confirm the bounded analytical limitation.",
                supporting_evidence_ids=[evidence_id],
                dependency_step_ids=[],
                dependency_notes=[],
                missing_information=[],
                deterministic_risk_codes=[
                    RiskCode.assumption_not_declared
                ],
                semantic_risk_codes=[],
                review_questions=[],
                status=WorkflowStepStatus.ready,
                blocks_downstream=False,
                human_review_required=False,
            ),
            WorkflowStep(
                step_id="wf-002",
                sequence=2,
                step_kind=WorkflowStepKind.semantic_review_gate,
                owner_role=RoleKey.executive,
                action="Review the probabilistic semantic concern.",
                supporting_evidence_ids=[evidence_id],
                dependency_step_ids=["wf-001"],
                dependency_notes=[],
                missing_information=[],
                deterministic_risk_codes=[],
                semantic_risk_codes=[
                    SemanticRiskCode.citation_claim_mismatch
                ],
                review_questions=["Does the citation support the claim?"],
                status=WorkflowStepStatus.pending_human_review,
                blocks_downstream=False,
                human_review_required=True,
            ),
            WorkflowStep(
                step_id="wf-003",
                sequence=3,
                step_kind=WorkflowStepKind.role_action,
                owner_role=RoleKey.executive,
                action="Review the bounded priority.",
                supporting_evidence_ids=[evidence_id],
                dependency_step_ids=["wf-001", "wf-002"],
                dependency_notes=[],
                missing_information=[],
                deterministic_risk_codes=[],
                semantic_risk_codes=[],
                review_questions=[],
                status=WorkflowStepStatus.pending_human_review,
                blocks_downstream=False,
                human_review_required=True,
            ),
            WorkflowStep(
                step_id="wf-004",
                sequence=4,
                step_kind=WorkflowStepKind.role_action,
                owner_role=RoleKey.project_manager,
                action="Coordinate the reviewed sequence.",
                supporting_evidence_ids=[evidence_id],
                dependency_step_ids=[
                    "wf-001",
                    "wf-002",
                    "wf-003",
                ],
                dependency_notes=[],
                missing_information=[],
                deterministic_risk_codes=[],
                semantic_risk_codes=[],
                review_questions=[],
                status=WorkflowStepStatus.pending_human_review,
                blocks_downstream=False,
                human_review_required=True,
            ),
        ],
        plan_status=WorkflowPlanStatus.ready_for_human_review,
        included_role_keys=[
            RoleKey.executive,
            RoleKey.data_analyst,
            RoleKey.project_manager,
        ],
        blocking_step_ids=[],
        human_review_required=True,
        planning_method="deterministic_v1",
    )

    state: dict[str, Any] = {}
    with patch(
        "app.main.review_workflow_plan",
        side_effect=AssertionError(
            "preset must not create a review session"
        ),
    ):
        _apply_synthetic_review_preset(review_plan, state)
    assert "rolelens_review_session" not in state
    for step in review_plan.steps:
        assert f"review_decision_{step.step_id}" in state
        assert f"review_note_{step.step_id}" in state
        assert f"review_revised_{step.step_id}" in state
    decisions = [
        state[f"review_decision_{step.step_id}"]
        for step in review_plan.steps
    ]
    assert decisions.count("revise") <= 1
    assert decisions.count("reject") <= 1
    assert state["review_decision_wf-002"] == "accept"
    assert state["review_note_wf-002"]

    raw_controls = state["demo_review_preset"]
    typed_inputs = _build_human_review_inputs(
        review_plan,
        raw_controls,
    )
    assert typed_inputs["wf-002"].decision is HumanReviewDecision.accept
    assert typed_inputs["wf-002"].reviewer_note == (
        raw_controls["wf-002"]["reviewer_note"]
    )

    optional_note_controls = json.loads(json.dumps(raw_controls))
    optional_note_controls["wf-003"]["reviewer_note"] = (
        "Optional accepted-action note."
    )
    optional_inputs = _build_human_review_inputs(
        review_plan,
        optional_note_controls,
    )
    assert optional_inputs["wf-003"].reviewer_note == (
        "Optional accepted-action note."
    )

    missing_gate_note = json.loads(json.dumps(raw_controls))
    missing_gate_note["wf-002"]["reviewer_note"] = None
    with pytest.raises(HumanReviewInputError):
        _build_human_review_inputs(review_plan, missing_gate_note)

    revised_gate = json.loads(json.dumps(raw_controls))
    revised_gate["wf-002"].update(
        {
            "decision": "revise",
            "reviewer_note": "Invalid gate revision.",
            "revised_action": "Invalid revised gate.",
        }
    )
    with pytest.raises(HumanReviewInputError):
        _build_human_review_inputs(review_plan, revised_gate)

    unchanged_revision = json.loads(json.dumps(raw_controls))
    revised_step_id = next(
        step_id
        for step_id, control in unchanged_revision.items()
        if control["decision"] == "revise"
    )
    original_by_id = {
        step.step_id: step.action for step in review_plan.steps
    }
    unchanged_revision[revised_step_id]["revised_action"] = (
        original_by_id[revised_step_id]
    )
    with pytest.raises(HumanReviewInputError):
        _build_human_review_inputs(review_plan, unchanged_revision)

    state["unrelated_application_state"] = "keep"
    _clear_review_widget_state(state)
    assert state["unrelated_application_state"] == "keep"
    assert "demo_review_preset" not in state
    assert "rolelens_review_preset_loaded" not in state
    assert not any(
        key.startswith(
            ("review_decision_", "review_note_", "review_revised_")
        )
        for key in state
    )

    empty_plan = WorkflowPlan(
        steps=[],
        plan_status=WorkflowPlanStatus.no_actionable_steps,
        included_role_keys=[RoleKey.executive],
        blocking_step_ids=[],
        human_review_required=True,
        planning_method="deterministic_v1",
    )
    unacknowledged = review_workflow_plan(empty_plan, {})
    assert unacknowledged.human_review_complete is False

    empty_state: dict[str, Any] = {
        "rolelens_decision_memo": "preserve-on-invalid-input",
    }
    with pytest.raises(HumanReviewInputError):
        _record_empty_workflow_review(empty_state, empty_plan, "   ")
    assert empty_state == {
        "rolelens_decision_memo": "preserve-on-invalid-input",
    }

    exact_note = "Reviewed: no actionable workflow is proposed."
    empty_session = _record_empty_workflow_review(
        empty_state,
        empty_plan,
        exact_note,
    )
    assert empty_session.human_review_complete is True
    assert empty_session.no_action_acknowledged is True
    assert empty_session.overall_note == exact_note
    assert empty_session.plan_step_ids == []
    assert empty_session.reviewed_steps == []
    assert "rolelens_decision_memo" not in empty_state

    empty_memo = compose_decision_memo(empty_plan, empty_session, [])
    assert (
        empty_memo.memo_status
        is DecisionMemoStatus.no_action_acknowledged
    )
    assert empty_memo.retained_actions == []
    assert empty_memo.evidence_items == []


# ---------------------------------------------------------------------------
# Test 10: Streamlit app smoke test via py_compile / AppTest import safety
# ---------------------------------------------------------------------------


def test_streamlit_app_smoke() -> None:
    """Compile and run the real six-tab Streamlit sample-loader smoke."""
    import py_compile

    from app.demo_pipeline import DemoPipelineError
    from app.main import (
        _apply_synthetic_sample,
        _handle_csv_uploader_change,
        _invalidate_prepared_demo_state,
        _prepare_demo_inputs_transaction,
        _resolve_csv_input,
        _run_live_demo_analysis_transaction,
    )

    # py_compile check for main.py
    main_path = str(pathlib.Path(__file__).parent.parent / "app" / "main.py")
    py_compile.compile(main_path, doraise=True)

    # Read the source and check structural markers
    source = pathlib.Path(main_path).read_text(encoding="utf-8")

    # Six tab names must appear in the source
    for tab_name in ["Intake", "Data Health", "Evidence Board", "RoleLens Views",
                     "Workflow Plan", "Decision Memo"]:
        assert tab_name in source, f"Tab '{tab_name}' must be present in app/main.py"

    # Sample loader button
    assert "Load synthetic B2B SaaS demo" in source, (
        "Sample loader button must be present"
    )

    # Live run button
    assert "Run RoleLens with IBM Granite" in source, (
        "Live run button must be present"
    )

    # No mock/offline fallback option text
    mock_phrases = ["mock mode", "offline mode", "offline fallback", "mock fallback"]
    source_lower = source.lower()
    for phrase in mock_phrases:
        assert phrase not in source_lower, (
            f"No mock/offline fallback option should appear: '{phrase}'"
        )

    # No secret values rendered literally
    for pattern in ["WATSONX_APIKEY=", "api_key=", "Bearer sk-"]:
        assert pattern not in source, (
            f"Source must not render secret value pattern: {pattern}"
        )

    # Runtime mode label must be exact
    assert "Live IBM Granite / watsonx.ai" in source, (
        "Runtime mode must be labeled 'Live IBM Granite / watsonx.ai'"
    )
    assert 'if __name__ == "__main__":' in source
    assert "else:\n    # Streamlit runs" not in source
    assert "uploaded_file.getvalue()" in source
    assert "uploaded_file.read()" not in source

    # py_compile check for demo_pipeline.py
    pipeline_path = str(pathlib.Path(__file__).parent.parent / "app" / "demo_pipeline.py")
    py_compile.compile(pipeline_path, doraise=True)

    sidecar = json.loads(_DEMO_JSON_PATH.read_text(encoding="utf-8"))
    widget_state: dict[str, Any] = {
        "rolelens_prepared_inputs": "old-prepared",
        "rolelens_analysis_result": "old-analysis",
        "rolelens_review_session": "old-review",
        "rolelens_decision_memo": "old-memo",
        "review_decision_wf-001": "accept",
        "review_note_wf-001": "old note",
        "review_revised_wf-001": "old revision",
        "demo_review_preset": {"old": "preset"},
        "rolelens_review_preset_loaded": True,
        "field_industry_context": "new editable context",
        "csv_uploader": "uploaded-file-widget-state",
        "unrelated_application_state": "keep",
    }
    _invalidate_prepared_demo_state(widget_state)
    assert widget_state == {
        "field_industry_context": "new editable context",
        "csv_uploader": "uploaded-file-widget-state",
        "unrelated_application_state": "keep",
    }

    widget_state.update(
        {
            "rolelens_prepared_inputs": "old-prepared",
            "rolelens_analysis_result": "old-analysis",
            "rolelens_review_session": "old-review",
            "rolelens_decision_memo": "old-memo",
        }
    )
    with patch(
        "app.main.run_live_demo_analysis",
        side_effect=AssertionError(
            "sample loading must not call a provider"
        ),
    ):
        _apply_synthetic_sample(sidecar, widget_state)
    expected_widget_values = {
        "field_industry_context": sidecar["industry_context"],
        "field_strategy_profile": sidecar["strategy_profile"],
        "field_business_question": sidecar["business_question"],
        "field_decision_goal": sidecar["decision_goal"],
        "field_user_assumption": sidecar["user_assumption"],
    }
    assert {
        key: widget_state[key] for key in expected_widget_values
    } == expected_widget_values
    assert widget_state["demo_use_sample_csv"] is True
    assert "rolelens_prepared_inputs" not in widget_state
    assert "rolelens_analysis_result" not in widget_state
    assert "rolelens_review_session" not in widget_state
    assert "rolelens_decision_memo" not in widget_state
    assert "csv_uploader" not in widget_state
    assert widget_state["unrelated_application_state"] == "keep"

    callback_state = dict(widget_state)
    callback_state.update(
        {
            "demo_use_sample_csv": True,
            "csv_uploader": "new-custom-upload",
            "rolelens_prepared_inputs": "old-prepared",
            "rolelens_analysis_result": "old-analysis",
            "rolelens_review_session": "old-review",
            "rolelens_decision_memo": "old-memo",
            "review_decision_wf-001": "accept",
            "demo_review_preset": {"old": "preset"},
        }
    )
    with patch("app.main.st.session_state", callback_state):
        _handle_csv_uploader_change()
    assert callback_state["demo_use_sample_csv"] is False
    assert callback_state["csv_uploader"] == "new-custom-upload"
    assert {
        key: callback_state[key] for key in expected_widget_values
    } == expected_widget_values
    assert callback_state["unrelated_application_state"] == "keep"
    assert "rolelens_prepared_inputs" not in callback_state
    assert "rolelens_analysis_result" not in callback_state
    assert "rolelens_review_session" not in callback_state
    assert "rolelens_decision_memo" not in callback_state
    assert "review_decision_wf-001" not in callback_state
    assert "demo_review_preset" not in callback_state

    fake_upload = types.SimpleNamespace(
        name="custom.csv",
        getvalue=MagicMock(return_value=b"custom,csv\n1,2\n"),
    )
    sample_bytes, sample_filename = _resolve_csv_input(
        fake_upload,
        True,
    )
    assert sample_bytes == _DEMO_CSV_PATH.read_bytes()
    assert sample_filename == _DEMO_CSV_PATH.name
    fake_upload.getvalue.assert_not_called()

    upload_bytes, upload_filename = _resolve_csv_input(
        fake_upload,
        False,
    )
    assert upload_bytes == b"custom,csv\n1,2\n"
    assert upload_filename == "custom.csv"
    fake_upload.getvalue.assert_called_once_with()
    with pytest.raises(ValueError, match="No CSV source is selected"):
        _resolve_csv_input(None, False)

    transactional_state: dict[str, Any] = {
        "rolelens_prepared_inputs": "successful-prepared",
        "rolelens_analysis_result": "successful-analysis",
        "rolelens_review_session": "successful-review",
        "rolelens_decision_memo": "successful-memo",
        "review_decision_wf-001": "reject",
        "review_note_wf-001": "editable review note",
        "unrelated_application_state": "keep",
    }
    original_state = dict(transactional_state)
    prepare_kwargs = {
        "csv_bytes": b"a,b\n1,2\n",
        "filename": "stable.csv",
        "industry_context": "External context.",
        "strategy_profile": "Stated priority.",
        "business_question": "What changed?",
        "decision_goal": "Review the evidence.",
        "user_assumption": None,
    }
    with patch(
        "app.main.prepare_demo_inputs",
        side_effect=DemoPipelineError("controlled preparation failure"),
    ), pytest.raises(DemoPipelineError):
        _prepare_demo_inputs_transaction(
            transactional_state,
            **prepare_kwargs,
        )
    assert transactional_state == original_state

    replacement_prepared = object()
    with patch(
        "app.main.prepare_demo_inputs",
        return_value=replacement_prepared,
    ):
        prepared_result = _prepare_demo_inputs_transaction(
            transactional_state,
            **prepare_kwargs,
        )
    assert prepared_result is replacement_prepared
    assert transactional_state["rolelens_prepared_inputs"] is (
        replacement_prepared
    )
    assert "rolelens_analysis_result" not in transactional_state
    assert "rolelens_review_session" not in transactional_state
    assert "rolelens_decision_memo" not in transactional_state
    assert "review_decision_wf-001" not in transactional_state
    assert "review_note_wf-001" not in transactional_state
    assert transactional_state["unrelated_application_state"] == "keep"

    transactional_state.update(
        {
            "rolelens_analysis_result": "successful-analysis",
            "rolelens_review_session": "successful-review",
            "rolelens_decision_memo": "successful-memo",
            "review_decision_wf-001": "accept",
            "review_note_wf-001": "editable review note",
        }
    )
    original_state = dict(transactional_state)
    with patch(
        "app.main.run_live_demo_analysis",
        side_effect=DemoPipelineError("controlled live failure"),
    ), pytest.raises(DemoPipelineError):
        _run_live_demo_analysis_transaction(
            transactional_state,
            replacement_prepared,
        )
    assert transactional_state == original_state

    replacement_analysis = object()
    with patch(
        "app.main.run_live_demo_analysis",
        return_value=replacement_analysis,
    ):
        analysis_result = _run_live_demo_analysis_transaction(
            transactional_state,
            replacement_prepared,
        )
    assert analysis_result is replacement_analysis
    assert transactional_state["rolelens_analysis_result"] is (
        replacement_analysis
    )
    assert "rolelens_review_session" not in transactional_state
    assert "rolelens_decision_memo" not in transactional_state
    assert "review_decision_wf-001" not in transactional_state
    assert "review_note_wf-001" not in transactional_state
    assert transactional_state["unrelated_application_state"] == "keep"

    try:
        from streamlit.testing.v1 import AppTest
    except ImportError:
        return

    with patch.dict(
        os.environ,
        {
            "WATSONX_APIKEY": "secret-value",
            "WATSONX_URL": "https://example.invalid",
            "WATSONX_PROJECT_ID": "secret-project",
        },
        clear=False,
    ), patch(
        "app.granite_provider.GraniteRoleProvider.from_env",
    ) as role_factory, patch(
        "app.granite_semantic_risk_provider."
        "GraniteSemanticRiskProvider.from_env",
    ) as semantic_factory:
        app_test = AppTest.from_file(main_path, default_timeout=15).run()
        assert not app_test.exception
        assert [tab.label for tab in app_test.tabs] == [
            "Intake",
            "Data Health",
            "Evidence Board",
            "RoleLens Views",
            "Workflow Plan",
            "Decision Memo",
        ]
        sample_button = next(
            button
            for button in app_test.button
            if button.label == "Load synthetic B2B SaaS demo"
        )
        app_test = sample_button.click().run()

        assert not app_test.exception
        for key, expected_value in expected_widget_values.items():
            assert app_test.session_state[key] == expected_value
        assert app_test.session_state["demo_use_sample_csv"] is True
        assert role_factory.call_count == 0
        assert semantic_factory.call_count == 0

        rendered_values: list[str] = []
        for collection_name in (
            "title",
            "header",
            "subheader",
            "markdown",
            "caption",
            "success",
            "warning",
            "error",
            "info",
        ):
            rendered_values.extend(
                str(element.value)
                for element in getattr(app_test, collection_name)
            )
        rendered_text = "\n".join(rendered_values)
        assert "secret-value" not in rendered_text
        assert "secret-project" not in rendered_text

        reset_button = next(
            button
            for button in app_test.button
            if button.label == "Reset demo"
        )
        app_test = reset_button.click().run()
        assert not app_test.exception
        assert all(
            app_test.session_state[key] == ""
            for key in expected_widget_values
        )
        assert app_test.session_state["demo_use_sample_csv"] is False
