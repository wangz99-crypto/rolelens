"""app/demo_pipeline.py — RoleLens Task 10A demo pipeline orchestration.

Provides two public functions:
  prepare_demo_inputs()   — deterministic, no provider calls
  run_live_demo_analysis() — live IBM Granite / watsonx.ai, injected providers

Importing this module does NOT read environment variables or make any calls.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from app.context_evidence import extract_context_evidence
from app.data_health import analyze_data_health
from app.data_parser import parse_csv
from app.evidence_builder import build_evidence
from app.file_intake import ingest_csv
from app.risk_checker import check_role_risks
from app.role_engine import (
    InsufficientEvidence,
    RoleGenerationFailure,
    run_role_engine,
)
from app.schemas import (
    DataHealthSummary,
    EvidenceObject,
    SemanticContextCategory,
    SourceManifestEntry,
    WorkflowPlan,
)
from app.semantic_risk_reviewer import SemanticRiskProvider, review_semantic_risks
from app.workflow_planner import plan_workflow

# ---------------------------------------------------------------------------
# Public error
# ---------------------------------------------------------------------------


class DemoPipelineError(ValueError):
    """Raised for expected demo pipeline failures.

    Messages are safe to display: no API keys, project IDs, raw provider
    payloads, arbitrary repr, Pydantic validation URLs, or stack traces.
    """


# ---------------------------------------------------------------------------
# Immutable result containers
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PreparedDemoInputs:
    """Deterministic preparation result — no provider calls involved.

    Attributes:
        source_manifests:           All registered SourceManifestEntry objects.
        data_health_summary:        DataHealthSummary for the CSV source.
        evidence_objects:           All active EvidenceObjects built from candidates.
        available_inputs:           Policy-filtered inputs dict for run_role_engine().
        dataframe_preview_records:  Bounded preview rows as list-of-dicts.
        row_count:                  Total CSV row count.
        column_count:               Total CSV column count.
    """

    source_manifests: tuple[SourceManifestEntry, ...]
    data_health_summary: DataHealthSummary
    evidence_objects: tuple[EvidenceObject, ...]
    available_inputs: dict[str, Any]
    dataframe_preview_records: tuple[dict[str, Any], ...]
    row_count: int
    column_count: int


@dataclass(frozen=True)
class DemoAnalysisResult:
    """Live analysis result containing all role and risk outputs.

    Attributes:
        prepared_inputs:           The PreparedDemoInputs that were used.
        role_outcomes:             dict[RoleKey, RoleOutcome] for all five roles.
        deterministic_risk_result: RiskReviewResult from check_role_risks().
        semantic_risk_result:      SemanticRiskReviewResult from review_semantic_risks().
        workflow_plan:             WorkflowPlan from plan_workflow().
        role_model_label:          Model label string for display (or None).
        semantic_model_label:      Model label string for display (or None).
    """

    prepared_inputs: PreparedDemoInputs
    role_outcomes: dict
    deterministic_risk_result: Any
    semantic_risk_result: Any
    workflow_plan: WorkflowPlan
    role_model_label: str | None
    semantic_model_label: str | None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_PREVIEW_ROW_LIMIT = 10

_SAFE_ROLE_FAILURE_REASONS = {
    "provider_error": (
        "The live role provider did not return a usable result."
    ),
    "invalid_output": "The role output failed structured validation.",
    "role_mismatch": (
        "The role output did not match the requested policy role."
    ),
    "unknown_evidence_reference": (
        "The role output contained an invalid Evidence reference."
    ),
    "inactive_evidence_reference": (
        "The role output contained an invalid Evidence reference."
    ),
    "hidden_evidence_reference": (
        "The role output contained an invalid Evidence reference."
    ),
}


def _safe_role_failure_reason(failure_code: str) -> str:
    """Return a deterministic display-safe reason for a typed failure."""
    return _SAFE_ROLE_FAILURE_REASONS.get(
        failure_code,
        "The role output could not be used safely.",
    )


def _sanitize_role_outcomes(role_outcomes: dict) -> dict:
    """Replace only RoleGenerationFailure reasons with safe messages."""
    return {
        role_key: (
            RoleGenerationFailure(
                role_key=outcome.role_key,
                failure_code=outcome.failure_code,
                reason=_safe_role_failure_reason(outcome.failure_code),
            )
            if isinstance(outcome, RoleGenerationFailure)
            else outcome
        )
        for role_key, outcome in role_outcomes.items()
    }


def _data_health_summary_as_dict(summary: DataHealthSummary) -> dict[str, Any]:
    """Convert DataHealthSummary to a plain dict for available_inputs."""
    return summary.model_dump(mode="json")


def _build_available_inputs(
    *,
    data_health_summary: DataHealthSummary,
    evidence_objects: Sequence[EvidenceObject],
    strategy_profile: str,
    business_question: str,
    source_manifests: Sequence[SourceManifestEntry],
) -> dict[str, Any]:
    """Construct only the exact keys accepted by role_engine and role_policy.

    Accepted keys from role_policy.json allowed_inputs across all five roles:
      evidence_objects, data_health_summary, strategy_profile,
      business_question, risk_results, source_manifest, role_views,
      missing_information.

    risk_results is populated after check_role_risks() runs; it is not
    available during preparation.  role_views and missing_information are
    PM inputs assembled inside run_role_engine().
    """
    return {
        "evidence_objects": list(evidence_objects),
        "data_health_summary": _data_health_summary_as_dict(data_health_summary),
        "strategy_profile": strategy_profile,
        "business_question": business_question,
        "source_manifest": [m.model_dump(mode="json") for m in source_manifests],
    }


# ---------------------------------------------------------------------------
# Public API: prepare_demo_inputs
# ---------------------------------------------------------------------------


def prepare_demo_inputs(
    csv_bytes: bytes,
    filename: str,
    industry_context: str,
    strategy_profile: str,
    business_question: str,
    decision_goal: str,
    user_assumption: str | None,
) -> PreparedDemoInputs:
    """Deterministically prepare pipeline inputs from raw demo materials.

    No provider calls.  No LLM.  No environment variable reads.

    Steps:
      1. Register the CSV as data_source.
      2. Parse the CSV.
      3. Run deterministic data health.
      4. Register and extract exact-source evidence for industry_context,
         strategy_profile, and user_assumption (when non-blank).
      5. Register business_question and decision_goal as decision_context only;
         they produce no EvidenceObject.
      6. Build EvidenceObjects through evidence_builder.build_evidence().
      7. Construct available_inputs with only policy-accepted keys.
      8. Return a bounded dataframe preview.

    Raises:
        DemoPipelineError: For any expected intake or parsing failure.
    """
    try:
        # 1. Register CSV source
        csv_manifest = ingest_csv(
            csv_bytes,
            semantic_context_category=SemanticContextCategory.data_source,
            filename=filename,
        )

        # 2. Parse CSV
        df = parse_csv(csv_bytes, csv_manifest)

        # 3. Data health
        data_health_summary, health_candidates = analyze_data_health(df, csv_manifest)

        # 4a. Industry context → TextEvidenceCandidate(s)
        industry_extraction = extract_context_evidence(
            industry_context,
            semantic_context_category=SemanticContextCategory.industry_context,
            field_name="industry_context",
        )

        # 4b. Strategy profile → TextEvidenceCandidate
        strategy_extraction = extract_context_evidence(
            strategy_profile,
            semantic_context_category=SemanticContextCategory.strategy_profile,
            field_name="strategy_profile",
        )

        # 4c. User assumption → TextEvidenceCandidate (optional)
        assumption_extraction = None
        if user_assumption and user_assumption.strip():
            assumption_extraction = extract_context_evidence(
                user_assumption,
                semantic_context_category=SemanticContextCategory.user_assumption,
                field_name="user_assumption",
            )

        # 5. Decision context manifests (no candidates)
        bq_extraction = extract_context_evidence(
            business_question,
            semantic_context_category=SemanticContextCategory.business_question,
            field_name="business_question",
        )
        dg_extraction = extract_context_evidence(
            decision_goal,
            semantic_context_category=SemanticContextCategory.decision_goal,
            field_name="decision_goal",
        )

    except Exception:
        raise DemoPipelineError(
            "Evidence preparation failed. Check CSV structure and required "
            "context inputs."
        ) from None

    # Collect all source manifests
    all_manifests: list[SourceManifestEntry] = [
        csv_manifest,
        industry_extraction.source_manifest,
        strategy_extraction.source_manifest,
        bq_extraction.source_manifest,
        dg_extraction.source_manifest,
    ]
    if assumption_extraction is not None:
        all_manifests.append(assumption_extraction.source_manifest)

    # Collect all evidence candidates
    all_candidates: list = list(health_candidates)
    all_candidates.extend(industry_extraction.candidates)
    all_candidates.extend(strategy_extraction.candidates)
    if assumption_extraction is not None:
        all_candidates.extend(assumption_extraction.candidates)
    # bq and dg produce no candidates (confirmed: rejection_reason is set)

    # 6. Build EvidenceObjects
    try:
        evidence_objects = build_evidence(all_candidates, all_manifests)
    except Exception:
        raise DemoPipelineError(
            "Evidence building failed. Check source and candidate consistency."
        ) from None

    # 7. Construct available_inputs
    available_inputs = _build_available_inputs(
        data_health_summary=data_health_summary,
        evidence_objects=evidence_objects,
        strategy_profile=strategy_profile,
        business_question=business_question,
        source_manifests=all_manifests,
    )

    # 8. Bounded preview
    preview_rows = df.head(_PREVIEW_ROW_LIMIT).to_dict(orient="records")

    return PreparedDemoInputs(
        source_manifests=tuple(all_manifests),
        data_health_summary=data_health_summary,
        evidence_objects=tuple(evidence_objects),
        available_inputs=available_inputs,
        dataframe_preview_records=tuple(preview_rows),
        row_count=len(df),
        column_count=df.shape[1],
    )


# ---------------------------------------------------------------------------
# Public API: run_live_demo_analysis
# ---------------------------------------------------------------------------


def run_live_demo_analysis(
    prepared_inputs: PreparedDemoInputs,
    role_provider=None,
    semantic_provider: SemanticRiskProvider | None = None,
) -> DemoAnalysisResult:
    """Run the live IBM Granite pipeline on already-prepared inputs.

    When providers are omitted, constructs GraniteRoleProvider.from_env() and
    GraniteSemanticRiskProvider.from_env() — this is the only point where
    environment variables are read.

    No retry.  No parallel execution.  No caching.  No silent fallback.

    Raises:
        DemoPipelineError: For configuration or provider failures with a
            sanitized message — no API key, project ID, or provider payload.
    """
    # Lazy provider construction — only when callers omit them.
    role_model_label: str | None = None
    semantic_model_label: str | None = None

    if role_provider is None:
        try:
            from app.granite_provider import GraniteRoleProvider
            role_provider = GraniteRoleProvider.from_env()
            role_model_label = "IBM Granite / watsonx.ai"
        except Exception as exc:
            _cls = type(exc).__name__
            raise DemoPipelineError(
                f"Role provider configuration failed ({_cls}). "
                "Check that WATSONX_APIKEY, WATSONX_URL, and WATSONX_PROJECT_ID "
                "are set correctly."
            ) from None

    if semantic_provider is None:
        try:
            from app.granite_semantic_risk_provider import GraniteSemanticRiskProvider
            semantic_provider = GraniteSemanticRiskProvider.from_env()
            semantic_model_label = "IBM Granite / watsonx.ai"
        except Exception as exc:
            _cls = type(exc).__name__
            raise DemoPipelineError(
                f"Semantic risk provider configuration failed ({_cls}). "
                "Check that WATSONX_APIKEY, WATSONX_URL, and WATSONX_PROJECT_ID "
                "are set correctly."
            ) from None

    evidence_objects = list(prepared_inputs.evidence_objects)

    # Run all five roles (typed failures preserved)
    try:
        raw_role_outcomes = run_role_engine(
            provider=role_provider,
            evidence_objects=evidence_objects,
            available_inputs=prepared_inputs.available_inputs,
        )
        role_outcomes = _sanitize_role_outcomes(raw_role_outcomes)
    except Exception as exc:
        _cls = type(exc).__name__
        raise DemoPipelineError(
            f"Role engine failed ({_cls}). Check provider output and evidence inputs."
        ) from None

    # Deterministic risk checking (runs even when some roles fail)
    try:
        deterministic_risk_result = check_role_risks(role_outcomes, evidence_objects)
    except Exception as exc:
        _cls = type(exc).__name__
        raise DemoPipelineError(
            f"Risk checker failed ({_cls}). This is likely a pipeline input error."
        ) from None

    # Semantic review — covers successful RoleViews only
    try:
        semantic_risk_result = review_semantic_risks(
            provider=semantic_provider,
            role_outcomes=role_outcomes,
            evidence_objects=evidence_objects,
            deterministic_risk_result=deterministic_risk_result,
        )
    except Exception as exc:
        _cls = type(exc).__name__
        raise DemoPipelineError(
            f"Semantic risk review failed ({_cls}). Check provider output."
        ) from None

    # Deterministic workflow planning
    try:
        workflow_plan = plan_workflow(
            role_outcomes=role_outcomes,
            evidence_objects=evidence_objects,
            deterministic_risk_result=deterministic_risk_result,
            semantic_risk_result=semantic_risk_result,
        )
    except Exception as exc:
        _cls = type(exc).__name__
        raise DemoPipelineError(
            f"Workflow planning failed ({_cls}). Check role and risk outputs."
        ) from None

    return DemoAnalysisResult(
        prepared_inputs=prepared_inputs,
        role_outcomes=role_outcomes,
        deterministic_risk_result=deterministic_risk_result,
        semantic_risk_result=semantic_risk_result,
        workflow_plan=workflow_plan,
        role_model_label=role_model_label,
        semantic_model_label=semantic_model_label,
    )
