"""Offline tests for the Task 10C-2A Dataset Orientation boundary.

Exactly 10 top-level test functions. No live Granite call is made.
"""

from __future__ import annotations

import builtins
import importlib
import json
import math
import os
import pathlib
import random
import re
import socket
import sys
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Mapping
from unittest.mock import patch

import pandas as pd
import pytest
from pydantic import ValidationError

from app.business_profile import (
    IBM_TELCO_CHURN_PROFILE_ID,
    BusinessDatasetProfile,
    build_business_profile,
)
from app.dataset_orientation import (
    DatasetGlossaryTerm,
    DatasetOrientationBrief,
    DatasetOrientationError,
    DatasetOrientationFailure,
    DatasetPrimer,
    OrientationEvidenceSnapshot,
    build_dataset_orientation_request,
    build_dataset_primer,
    orient_dataset,
)
from app.evidence_builder import build_evidence
from app.file_intake import ingest_csv
from app.role_engine import RoleGenerationFailure
from app.schemas import (
    EvidenceObject,
    EvidenceScope,
    EvidenceStatus,
    RoleKey,
    RoleView,
    SemanticContextCategory,
)


_ROOT = pathlib.Path(__file__).parent.parent
_PUBLIC_CSV = _ROOT / "sample_data" / "public" / "ibm_telco_customer_churn.csv"
_SYNTHETIC_CSV = _ROOT / "sample_data" / "b2b_saas_retention_demo.csv"
_SYNTHETIC_CONTEXT = _ROOT / "sample_data" / "b2b_saas_retention_demo.json"
_FIXED_TIME = datetime(2026, 7, 31, tzinfo=timezone.utc)
_BUSINESS_QUESTION = (
    "Is the evidence sufficient to review a limited retention pilot?"
)
_EVIDENCE_TYPES = (
    "business_overall_churn",
    "business_contract_churn",
    "business_support_churn",
    "business_internet_churn",
    "business_payment_churn",
    "business_churn_medians",
    "business_parseability",
)
_GLOSSARY_FIELDS = (
    "customerID",
    "Churn",
    "Contract",
    "tenure",
    "MonthlyCharges",
    "TotalCharges",
    "InternetService",
    "TechSupport",
    "PaymentMethod",
    "PaperlessBilling",
)


def _profile_evidence() -> tuple[
    BusinessDatasetProfile,
    tuple[EvidenceObject, ...],
]:
    """Build the frozen profile and seven business Evidence Objects."""
    raw = _PUBLIC_CSV.read_bytes()
    manifest = ingest_csv(
        raw,
        semantic_context_category=SemanticContextCategory.data_source,
        filename=_PUBLIC_CSV.name,
        created_at=_FIXED_TIME,
    )
    dataframe = pd.read_csv(_PUBLIC_CSV, dtype=str, keep_default_na=False)
    profile, candidates = build_business_profile(
        dataframe,
        manifest,
        profile_id=IBM_TELCO_CHURN_PROFILE_ID,
    )
    return profile, tuple(build_evidence(candidates, [manifest]))


def _request():
    """Build one valid provider-neutral orientation request."""
    profile, evidence = _profile_evidence()
    return build_dataset_orientation_request(
        business_profile=profile,
        evidence_objects=evidence,
        business_question=_BUSINESS_QUESTION,
    )


def _valid_output(request=None) -> dict[str, Any]:
    """Return one bounded valid raw provider mapping."""
    selected = request or _request()
    ids = [item.evidence_id for item in selected.business_evidence]
    return {
        "dataset_overview": (
            "This fictional sample describes aggregate account, service, "
            "billing, tenure, and churn information."
        ),
        "business_question_in_plain_language": (
            "Do the aggregate facts support reviewing a limited validation pilot?"
        ),
        "terms_to_know": [
            {
                "field_name": "Churn",
                "explanation": "The recorded descriptive outcome.",
                "caution": "It does not explain why an account departed.",
            },
            {
                "field_name": "Contract",
                "explanation": "The recorded contract-term category.",
                "caution": "Group differences remain descriptive.",
            },
            {
                "field_name": "tenure",
                "explanation": "How long the account has remained in the sample.",
                "caution": "Interpret the documented sample measure only.",
            },
            {
                "field_name": "MonthlyCharges",
                "explanation": "The recurring charge value recorded for an account.",
                "caution": "Its monetary unit is unspecified.",
            },
        ],
        "key_patterns": [
            {
                "headline": "Overall observed churn",
                "plain_language_explanation": (
                    "The sample records a bounded aggregate churn rate."
                ),
                "evidence_ids": [ids[0]],
            },
            {
                "headline": "Contract groups differ",
                "plain_language_explanation": (
                    "Observed churn rates vary across contract groups."
                ),
                "evidence_ids": [ids[1]],
            },
            {
                "headline": "Tenure and charge medians differ",
                "plain_language_explanation": (
                    "The churn-status groups have different aggregate medians."
                ),
                "evidence_ids": [ids[5]],
            },
        ],
        "why_this_matters": (
            "These aggregates help functions frame questions for a limited "
            "validation pilot."
        ),
        "evidence_boundary_acknowledged": True,
    }


class _StaticProvider:
    """Offline provider returning or raising one configured value."""

    def __init__(self, result: Mapping[str, Any] | Exception) -> None:
        self.result = result
        self.calls = 0

    def generate_dataset_orientation(self, request) -> Mapping[str, Any]:
        self.calls += 1
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def _replace_evidence(evidence: EvidenceObject, **updates: Any) -> EvidenceObject:
    """Revalidate a controlled EvidenceObject variant."""
    payload = evidence.model_dump()
    payload.update(updates)
    return EvidenceObject.model_validate(payload)


def test_primer_and_glossary_contracts_fail_closed(tmp_path: pathlib.Path) -> None:
    """Local contracts reject malformed text, facts, lists, and constants."""
    request = _request()
    primer_payload = request.primer.model_dump()
    with pytest.raises(ValidationError):
        DatasetGlossaryTerm(
            field_name=" ",
            plain_language="Meaning",
            primary_use="Use",
            caution="Caution",
        )
    with pytest.raises(ValidationError):
        DatasetGlossaryTerm(
            field_name="Churn",
            plain_language="Meaning",
            primary_use="Use",
            caution="Caution",
            extra_field="forbidden",
        )

    duplicate_terms = list(request.primer.glossary_terms)
    duplicate_terms[1] = duplicate_terms[0]
    invalid_updates = [
        {"profile_id": "other_profile"},
        {"dataset_context": " "},
        {"row_count": 7_042},
        {"unique_customer_count": 7_042},
        {"churned_count": 7_044},
        {"overall_churn_rate_pct": 99.0},
        {"overall_churn_rate_pct": math.nan},
        {"total_charges_parse_issue_count": 8_000},
        {"glossary_terms": duplicate_terms},
        {"guardrails": tuple(reversed(request.primer.guardrails))},
        {"disclosure": "Not the controlled disclosure."},
        {"unexpected": "forbidden"},
    ]
    for update in invalid_updates:
        with pytest.raises(ValidationError):
            DatasetPrimer.model_validate({**primer_payload, **update})

    invalid_context = tmp_path / "metadata.json"
    invalid_context.write_text(
        '{"dataset_context":"WATSONX_APIKEY=secret raw payload"}',
        encoding="utf-8",
    )
    profile, _ = _profile_evidence()
    with pytest.raises(DatasetOrientationError) as error:
        build_dataset_primer(
            profile,
            business_question=_BUSINESS_QUESTION,
            context_path=invalid_context,
        )
    message = str(error.value)
    assert "secret" not in message
    assert "raw payload" not in message
    assert "errors.pydantic.dev" not in message
    assert str(invalid_context) not in message


def test_build_primer_loads_exact_frozen_metadata() -> None:
    """Frozen metadata produces exact facts, glossary order, and disclosure."""
    profile, _ = _profile_evidence()
    primer = build_dataset_primer(
        profile,
        business_question=_BUSINESS_QUESTION,
    )
    assert primer.profile_id == IBM_TELCO_CHURN_PROFILE_ID
    assert primer.dataset_name == "IBM Telco Customer Churn"
    assert primer.row_count == 7_043
    assert primer.unique_customer_count == 7_043
    assert primer.churned_count == 1_869
    assert primer.overall_churn_rate_pct == 26.54
    assert primer.total_charges_parse_issue_count == 11
    assert primer.business_question == _BUSINESS_QUESTION
    assert "fictional telecommunications" in primer.dataset_context
    assert tuple(term.field_name for term in primer.glossary_terms) == _GLOSSARY_FIELDS
    assert "not specified" in primer.currency_status
    assert primer.disclosure == (
        "This is a fictional IBM sample dataset, not real customer production data."
    )
    assert len(primer.guardrails) == 4


def test_request_contains_only_seven_minimal_evidence_snapshots() -> None:
    """Request snapshots preserve approved order and exclude sensitive fields."""
    request = _request()
    assert len(request.business_evidence) == 7
    assert tuple(item.evidence_type for item in request.business_evidence) == _EVIDENCE_TYPES
    snapshot_ids = tuple(item.evidence_id for item in request.business_evidence)
    assert request.allowed_evidence_ids == frozenset(snapshot_ids)
    for snapshot in request.business_evidence:
        assert isinstance(snapshot, OrientationEvidenceSnapshot)
        keys = set(snapshot.model_dump())
        assert keys == {
            "evidence_id",
            "evidence_type",
            "finding",
            "limitations",
            "decision_relevance",
        }
        assert not keys.intersection(
            {
                "raw_rows",
                "supporting_evidence",
                "source_locator",
                "source_manifest",
                "identity_digest",
                "customer_identifiers",
            }
        )


def test_request_rejects_corrupt_or_out_of_scope_evidence() -> None:
    """Missing, duplicate, extra, wrong-scope, and mixed-source inputs fail."""
    profile, evidence = _profile_evidence()
    first = evidence[0]
    invalidated = _replace_evidence(
        first,
        status=EvidenceStatus.invalidated,
        invalidated_reason="Invalidated for offline test.",
    )
    external = _replace_evidence(first, evidence_scope=EvidenceScope.external_context)
    assumption = _replace_evidence(first, evidence_scope=EvidenceScope.assumption)
    stated = _replace_evidence(first, evidence_scope=EvidenceScope.stated_priority)
    wrong_source = _replace_evidence(
        first,
        source_id="src-other-000000000001",
    )
    nonbusiness = _replace_evidence(first, evidence_type="missing_value_rate")
    cases = [
        evidence[:-1],
        evidence + (first,),
        (first, first, *evidence[2:]),
        (invalidated, *evidence[1:]),
        (external, *evidence[1:]),
        (assumption, *evidence[1:]),
        (stated, *evidence[1:]),
        (wrong_source, *evidence[1:]),
        (nonbusiness, *evidence[1:]),
    ]
    for invalid in cases:
        with pytest.raises(DatasetOrientationError) as error:
            build_dataset_orientation_request(
                business_profile=profile,
                evidence_objects=invalid,
                business_question=_BUSINESS_QUESTION,
            )
        message = str(error.value)
        assert "errors.pydantic.dev" not in message
        assert "EvidenceObject(" not in message
        assert first.finding not in message


def test_orient_dataset_accepts_valid_grounded_output() -> None:
    """Exactly four valid terms and three grounded patterns are accepted."""
    request = _request()
    safe_examples = [
        "The observed differences do not establish causation.",
        "These aggregate patterns do not predict individual churn.",
        (
            "The evidence does not estimate an individual customer's churn "
            "probability."
        ),
        "The evidence does not authorize customer targeting or outreach.",
        "No ROI or financial return can be inferred from this dataset.",
        "The analysis cannot identify which individual customer will churn.",
        "These findings must not be used to target customers.",
    ]
    for safe_statement in safe_examples:
        safe_payload = _valid_output(request)
        safe_payload["why_this_matters"] = safe_statement
        DatasetOrientationBrief.model_validate(safe_payload)

    safe_output = _valid_output(request)
    safe_output["why_this_matters"] = (
        "The observed differences do not establish causation. "
        "These aggregate patterns do not predict individual churn and do not "
        "authorize customer targeting or outreach. "
        "No ROI or financial return can be inferred from this dataset."
    )
    provider = _StaticProvider(safe_output)
    outcome = orient_dataset(provider=provider, request=request)
    assert isinstance(outcome, DatasetOrientationBrief)
    assert provider.calls == 1
    assert len(outcome.terms_to_know) == 4
    assert len(outcome.key_patterns) == 3
    assert outcome.evidence_boundary_acknowledged is True
    assert {
        evidence_id
        for pattern in outcome.key_patterns
        for evidence_id in pattern.evidence_ids
    }.issubset(request.allowed_evidence_ids)


def test_orient_dataset_returns_only_controlled_typed_failures() -> None:
    """Provider, schema, Evidence, and glossary failures never leak details."""
    request = _request()
    prohibited_claims = [
        "Contract type causes churn.",
        "Lack of support drives churn.",
        "These data predict individual churn probability.",
        "These customers are likely to churn.",
        "The company should target these customers.",
        "This evidence authorizes customer outreach.",
        "The retention pilot will generate ROI.",
        "The analysis proves a financial return.",
        "The model has completed validation.",
        "This could predict churn.",
        "This may authorize outreach.",
        "Potential ROI is expected.",
    ]
    for prohibited_claim in prohibited_claims:
        invalid_claim_output = _valid_output(request)
        invalid_claim_output["why_this_matters"] = prohibited_claim
        with pytest.raises(ValidationError):
            DatasetOrientationBrief.model_validate(invalid_claim_output)

    unknown_evidence = _valid_output(request)
    unknown_evidence["key_patterns"][0]["evidence_ids"] = [
        "ev-business-0000000000ff"
    ]
    unknown_glossary = _valid_output(request)
    unknown_glossary["terms_to_know"][0]["field_name"] = "UnknownField"
    cases = [
        (
            _StaticProvider(
                RuntimeError(
                    "WATSONX_APIKEY=secret raw payload errors.pydantic.dev"
                )
            ),
            "provider_error",
        ),
        (
            _StaticProvider(
                {"raw": "WATSONX_APIKEY=secret errors.pydantic.dev"}
            ),
            "invalid_output",
        ),
        (_StaticProvider(unknown_evidence), "invalid_evidence_reference"),
        (_StaticProvider(unknown_glossary), "invalid_glossary_reference"),
    ]
    for provider, expected_code in cases:
        outcome = orient_dataset(provider=provider, request=request)
        assert isinstance(outcome, DatasetOrientationFailure)
        assert outcome.failure_code == expected_code
        serialized = json.dumps(outcome.model_dump(mode="json"))
        assert "secret" not in serialized
        assert "raw payload" not in serialized
        assert "errors.pydantic.dev" not in serialized
        assert "Traceback" not in serialized
        assert "RuntimeError(" not in serialized
    with pytest.raises(ValidationError):
        DatasetOrientationFailure(
            failure_code="provider_error",
            reason="WATSONX_APIKEY=secret raw provider reason",
        )


def test_granite_adapter_is_import_safe_and_sends_bounded_json(monkeypatch) -> None:
    """Injected Granite adapter uses one deterministic JSON-schema chat call."""
    request = _request()
    output = _valid_output(request)
    sdk_imports: list[str] = []
    original_import = builtins.__import__

    def guarded_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name.startswith("ibm_watsonx_ai"):
            sdk_imports.append(name)
            raise AssertionError("SDK import is forbidden during module import")
        return original_import(name, *args, **kwargs)

    for name in (
        "WATSONX_APIKEY",
        "WATSONX_URL",
        "WATSONX_PROJECT_ID",
        "WATSONX_MODEL_ID",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(builtins, "__import__", guarded_import)
    monkeypatch.delitem(
        sys.modules,
        "app.granite_dataset_orientation_provider",
        raising=False,
    )
    module = importlib.import_module(
        "app.granite_dataset_orientation_provider"
    )
    assert sdk_imports == []

    class FakeClient:
        def __init__(self) -> None:
            self.calls: list[dict[str, Any]] = []

        def chat(self, *, messages, params):
            self.calls.append({"messages": messages, "params": params})
            return {
                "choices": [
                    {"message": {"content": json.dumps(output)}}
                ]
            }

    client = FakeClient()
    provider = module.GraniteDatasetOrientationProvider(client)
    raw = provider.generate_dataset_orientation(request)
    assert raw == output
    assert len(client.calls) == 1
    call = client.calls[0]
    assert call["params"]["temperature"] == 0
    assert call["params"]["max_completion_tokens"] == 900
    assert call["params"]["response_format"]["json_schema"]["schema"] == (
        DatasetOrientationBrief.model_json_schema()
    )
    system_message = call["messages"][0]["content"]
    approved_sentences = [
        "The observed differences do not establish causation.",
        "These aggregate patterns do not predict individual churn.",
        (
            "The evidence does not estimate an individual customer's churn "
            "probability."
        ),
        "The evidence does not authorize customer targeting or outreach.",
        "No ROI or financial return can be inferred from this dataset.",
        "The analysis cannot identify which individual customer will churn.",
        "These findings must not be used to target customers.",
    ]
    assert all(sentence in system_message for sentence in approved_sentences)
    assert "use only the following approved sentences verbatim" in system_message
    assert "as separate sentences. Do not paraphrase them." in system_message
    assert "you do not need to use all seven" in system_message
    assert "Return one JSON object only" in call["messages"][0]["content"]
    assert "positively or ambiguously" in call["messages"][0]["content"]
    assert "Set evidence_boundary_acknowledged to true" in (
        call["messages"][0]["content"]
    )
    DatasetOrientationBrief.model_validate(output)
    for invalid_statement in (
        "Contract type causes churn.",
        "This could predict churn.",
    ):
        invalid_output = _valid_output(request)
        invalid_output["why_this_matters"] = invalid_statement
        with pytest.raises(ValidationError):
            DatasetOrientationBrief.model_validate(invalid_output)
    payload = json.loads(call["messages"][1]["content"])
    assert set(payload) == {
        "primer",
        "business_evidence",
        "allowed_evidence_ids",
    }
    assert len(payload["business_evidence"]) == 7
    assert payload["allowed_evidence_ids"] == sorted(
        request.allowed_evidence_ids
    )
    serialized = call["messages"][1]["content"]
    assert "supporting_evidence" not in serialized
    assert "source_locator" not in serialized
    assert "identity_digest" not in serialized
    assert not re.search(r"\b[0-9]{4}-[A-Z0-9]{5}\b", serialized)
    assert "unit-test-secret" not in json.dumps(call)

    credential_calls: list[dict[str, Any]] = []
    model_calls: list[dict[str, Any]] = []
    credentials = object()

    def credentials_factory(**kwargs: Any) -> object:
        credential_calls.append(kwargs)
        return credentials

    def model_factory(**kwargs: Any) -> FakeClient:
        model_calls.append(kwargs)
        return client

    live_provider = module.GraniteDatasetOrientationProvider.from_env(
        environ={
            "WATSONX_APIKEY": "  unit-test-secret  ",
            "WATSONX_URL": "https://example.invalid",
            "WATSONX_PROJECT_ID": "offline-project",
        },
        credentials_factory=credentials_factory,
        model_factory=model_factory,
    )
    assert isinstance(live_provider, module.GraniteDatasetOrientationProvider)
    assert credential_calls == [
        {
            "url": "https://example.invalid",
            "api_key": "unit-test-secret",
        }
    ]
    assert model_calls == [
        {
            "model_id": "ibm/granite-4-h-small",
            "credentials": credentials,
            "project_id": "offline-project",
        }
    ]
    assert "unit-test-secret" not in repr(live_provider)


def test_demo_analysis_without_profile_skips_orientation() -> None:
    """Existing no-profile analysis never calls an orientation provider."""
    from app.demo_pipeline import prepare_demo_inputs, run_live_demo_analysis

    sidecar = json.loads(_SYNTHETIC_CONTEXT.read_text(encoding="utf-8"))
    prepared = prepare_demo_inputs(
        csv_bytes=_SYNTHETIC_CSV.read_bytes(),
        filename=_SYNTHETIC_CSV.name,
        industry_context=sidecar["industry_context"],
        strategy_profile=sidecar["strategy_profile"],
        business_question=sidecar["business_question"],
        decision_goal=sidecar["decision_goal"],
        user_assumption=sidecar["user_assumption"],
    )
    orientation = _StaticProvider(
        AssertionError("orientation must not be called")
    )
    result = run_live_demo_analysis(
        prepared,
        role_provider=_MinimalRoleProvider(),
        semantic_provider=_MinimalSemanticProvider(),
        orientation_provider=orientation,
    )
    assert orientation.calls == 0
    assert result.dataset_primer is None
    assert result.dataset_orientation_outcome is None
    assert result.orientation_model_label is None
    assert result.workflow_plan is not None


class _MinimalRoleProvider:
    """Offline provider producing one bounded cited finding per role."""

    def generate_role_view(self, request) -> Mapping[str, Any]:
        evidence_id = sorted(request.exposed_evidence_ids)[0]
        return {
            "role_key": request.role_key.value,
            "role_concern": f"Bounded concern for {request.role_key.value}.",
            "key_findings": [
                {
                    "claim": "The exposed aggregate evidence requires review.",
                    "evidence_references": [{"evidence_id": evidence_id}],
                    "confidence": "low",
                }
            ],
            "risks_or_assumptions": [],
            "missing_information": ["Pilot validation remains incomplete."],
            "next_action": "Review the bounded validation questions.",
            "dependency": None,
            "human_review_required": True,
        }


class _MinimalSemanticProvider:
    """Offline semantic provider returning no risk candidates."""

    def review_semantic_risks(self, request) -> Mapping[str, Any]:
        return {
            "candidates": [],
            "reviewed_role_keys": [
                view.role_key.value for view in request.role_views
            ],
            "reviewer_model": None,
            "human_review_required": False,
        }


def test_demo_analysis_with_profile_orients_once_and_failure_is_nonblocking() -> None:
    """Injected orientation succeeds or fails once while role workflow continues."""
    from app.demo_pipeline import prepare_demo_inputs, run_live_demo_analysis

    kwargs = {
        "csv_bytes": _PUBLIC_CSV.read_bytes(),
        "filename": _PUBLIC_CSV.name,
        "industry_context": "External fictional context, not company evidence.",
        "strategy_profile": "Review a limited validation pilot.",
        "business_question": _BUSINESS_QUESTION,
        "decision_goal": "Review role-specific validation responsibilities.",
        "user_assumption": "Observed group differences may merit review.",
        "business_profile_id": IBM_TELCO_CHURN_PROFILE_ID,
    }
    prepared = prepare_demo_inputs(**kwargs)

    success_provider = _StaticProvider(_valid_output(_request()))
    success = run_live_demo_analysis(
        prepared,
        role_provider=_MinimalRoleProvider(),
        semantic_provider=_MinimalSemanticProvider(),
        orientation_provider=success_provider,
    )
    assert success_provider.calls == 1
    assert isinstance(success.dataset_primer, DatasetPrimer)
    assert isinstance(success.dataset_orientation_outcome, DatasetOrientationBrief)
    assert success.orientation_model_label is None
    assert len(success.role_outcomes) == 5
    assert success.workflow_plan is not None

    failing_provider = _StaticProvider(
        RuntimeError("WATSONX_APIKEY=secret raw provider payload")
    )
    failure = run_live_demo_analysis(
        prepared,
        role_provider=_MinimalRoleProvider(),
        semantic_provider=_MinimalSemanticProvider(),
        orientation_provider=failing_provider,
    )
    assert failing_provider.calls == 1
    assert isinstance(failure.dataset_primer, DatasetPrimer)
    assert isinstance(
        failure.dataset_orientation_outcome,
        DatasetOrientationFailure,
    )
    assert failure.dataset_orientation_outcome.failure_code == "provider_error"
    assert len(failure.role_outcomes) == 5
    assert any(isinstance(value, RoleView) for value in failure.role_outcomes.values())
    assert not any(
        isinstance(value, RoleGenerationFailure)
        for value in failure.role_outcomes.values()
    )
    assert failure.workflow_plan is not None


def test_primer_request_are_deterministic_immutable_and_import_safe() -> None:
    """Construction and imports use no env, network, clock, UUID, or randomness."""
    profile, evidence = _profile_evidence()
    profile_before = profile.model_dump(mode="json")
    evidence_before = [item.model_dump(mode="json") for item in evidence]

    with patch.object(
        os.environ,
        "get",
        side_effect=AssertionError("environment access is forbidden"),
    ), patch.object(
        socket,
        "create_connection",
        side_effect=AssertionError("network access is forbidden"),
    ), patch.object(
        time,
        "time",
        side_effect=AssertionError("clock access is forbidden"),
    ), patch.object(
        uuid,
        "uuid4",
        side_effect=AssertionError("UUID access is forbidden"),
    ), patch.object(
        random,
        "random",
        side_effect=AssertionError("randomness is forbidden"),
    ):
        first_primer = build_dataset_primer(
            profile,
            business_question=_BUSINESS_QUESTION,
        )
        second_primer = build_dataset_primer(
            profile,
            business_question=_BUSINESS_QUESTION,
        )
        first_request = build_dataset_orientation_request(
            business_profile=profile,
            evidence_objects=evidence,
            business_question=_BUSINESS_QUESTION,
        )
        second_request = build_dataset_orientation_request(
            business_profile=profile,
            evidence_objects=evidence,
            business_question=_BUSINESS_QUESTION,
        )
    assert first_primer == second_primer
    assert first_request == second_request
    assert profile.model_dump(mode="json") == profile_before
    assert [item.model_dump(mode="json") for item in evidence] == evidence_before

    sdk_imports: list[str] = []
    original_import = builtins.__import__

    def guarded_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name.startswith("ibm_watsonx_ai"):
            sdk_imports.append(name)
            raise AssertionError("SDK import is forbidden")
        return original_import(name, *args, **kwargs)

    with patch.object(builtins, "__import__", side_effect=guarded_import):
        importlib.import_module("app.dataset_orientation")
        importlib.import_module("app.granite_dataset_orientation_provider")
    assert sdk_imports == []
