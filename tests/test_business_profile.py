"""Offline contract and integration tests for Task 10C-1.

Exactly 10 top-level test functions. No provider or network call is made.
"""

from __future__ import annotations

import math
import os
import pathlib
import random
import socket
import time
import uuid
from datetime import datetime, timezone
from unittest.mock import patch

import pandas as pd
import pytest
from pydantic import ValidationError

from app.business_profile import (
    IBM_TELCO_CHURN_PROFILE_ID,
    BusinessDatasetProfile,
    BusinessProfileError,
    ChurnStatusMedians,
    SegmentChurnRate,
    build_business_profile,
)
from app.evidence_builder import CandidateContractMismatchError, build_evidence
from app.file_intake import ingest_csv
from app.schemas import (
    BusinessFindingCandidate,
    EvidenceScope,
    EvidenceStatus,
    SemanticContextCategory,
    SourceFormat,
    SourceManifestEntry,
    SourceScope,
    TabularSourceLocator,
)


_ROOT = pathlib.Path(__file__).parent.parent
_PUBLIC_CSV = _ROOT / "sample_data" / "public" / "ibm_telco_customer_churn.csv"
_SYNTHETIC_CSV = _ROOT / "sample_data" / "b2b_saas_retention_demo.csv"
_SYNTHETIC_CONTEXT = (
    _ROOT / "sample_data" / "b2b_saas_retention_demo.json"
)
_FIXED_TIME = datetime(2026, 7, 31, tzinfo=timezone.utc)

_EVIDENCE_TYPES = [
    "business_overall_churn",
    "business_contract_churn",
    "business_support_churn",
    "business_internet_churn",
    "business_payment_churn",
    "business_churn_medians",
    "business_parseability",
]
_CLAIM_KEYS = [
    "business.telco.overall_churn",
    "business.telco.churn_by_contract",
    "business.telco.churn_by_tech_support",
    "business.telco.churn_by_internet_service",
    "business.telco.churn_by_payment_method",
    "business.telco.churn_status_medians",
    "business.telco.total_charges_parseability",
]
_ROLE_MAP = [
    ["executive", "data_analyst", "sales_marketing", "project_manager"],
    ["executive", "data_analyst", "sales_marketing", "project_manager"],
    ["data_analyst", "sales_marketing", "executive"],
    ["data_analyst", "sales_marketing", "executive"],
    ["data_analyst", "sales_marketing", "executive"],
    ["executive", "data_analyst", "sales_marketing"],
    ["data_engineer", "data_analyst", "project_manager"],
]


def _public_inputs() -> tuple[pd.DataFrame, SourceManifestEntry]:
    """Return a string-preserving DataFrame and deterministic CSV manifest."""
    raw = _PUBLIC_CSV.read_bytes()
    manifest = ingest_csv(
        raw,
        semantic_context_category=SemanticContextCategory.data_source,
        filename=_PUBLIC_CSV.name,
        created_at=_FIXED_TIME,
    )
    dataframe = pd.read_csv(_PUBLIC_CSV, dtype=str, keep_default_na=False)
    return dataframe, manifest


def _profile_and_candidates() -> tuple[
    BusinessDatasetProfile,
    tuple[BusinessFindingCandidate, ...],
    SourceManifestEntry,
]:
    """Build the approved profile from the frozen local public sample."""
    dataframe, manifest = _public_inputs()
    profile, candidates = build_business_profile(
        dataframe,
        manifest,
        profile_id=IBM_TELCO_CHURN_PROFILE_ID,
    )
    return profile, candidates, manifest


def _manifest_variant(
    manifest: SourceManifestEntry,
    **updates: object,
) -> SourceManifestEntry:
    """Revalidate a manifest with controlled provenance-field changes."""
    payload = manifest.model_dump()
    payload.update(updates)
    return SourceManifestEntry.model_validate(payload)


def test_business_candidate_and_local_contracts_fail_closed() -> None:
    """Candidate and aggregate contracts reject malformed caller data."""
    profile, candidates, _ = _profile_and_candidates()
    candidate_payload = candidates[0].model_dump()

    invalid_candidate_updates = [
        {"business_profile_id": "Bad Profile"},
        {"source_id": "bad-source"},
        {"evidence_type": "Bad Type"},
        {"normalized_claim_key": "Bad.Key"},
        {"finding": " "},
        {"supporting_evidence": ""},
        {"decision_relevance": " "},
        {"limitations": ["duplicate", "duplicate"]},
        {"limitations": [" "]},
        {"relevant_roles": []},
        {"relevant_roles": ["executive", "executive"]},
        {"canonical_rule_parameters": {"rate": math.nan}},
        {"evidence_id": "ev-test-000000000000"},
        {"identity_digest": "0" * 64},
        {"action": "Target a customer."},
        {"recommendation": "Unsupported recommendation."},
        {"customer_identifier_list": ["hidden"]},
    ]
    for update in invalid_candidate_updates:
        with pytest.raises(ValidationError):
            BusinessFindingCandidate.model_validate(
                {**candidate_payload, **update}
            )

    with pytest.raises(ValidationError):
        SegmentChurnRate(
            segment=" ", customers=10, churned=1, churn_rate_pct=10.0
        )
    with pytest.raises(ValidationError):
        SegmentChurnRate(
            segment="A", customers=10, churned=11, churn_rate_pct=110.0
        )
    with pytest.raises(ValidationError):
        SegmentChurnRate(
            segment="A", customers=10, churned=1, churn_rate_pct=9.99
        )
    with pytest.raises(ValidationError):
        SegmentChurnRate(
            segment="A",
            customers=10,
            churned=1,
            churn_rate_pct=10.0,
            extra_field=True,
        )
    with pytest.raises(ValidationError):
        ChurnStatusMedians(
            churn_status="No",
            customers=1,
            median_tenure=float("inf"),
            median_monthly_charges=1.0,
            median_total_charges=1.0,
        )

    profile_payload = profile.model_dump()
    with pytest.raises(ValidationError):
        BusinessDatasetProfile.model_validate(
            {**profile_payload, "retained_count": 5_173}
        )
    duplicate_rates = list(profile.contract_rates)
    duplicate_rates[1] = duplicate_rates[0]
    with pytest.raises(ValidationError):
        BusinessDatasetProfile.model_validate(
            {**profile_payload, "contract_rates": duplicate_rates}
        )
    with pytest.raises(ValidationError):
        BusinessDatasetProfile.model_validate(
            {**profile_payload, "unexpected": "forbidden"}
        )


def test_frozen_public_dataset_counts_and_overall_rate() -> None:
    """The frozen public CSV matches the approved dataset-level audit."""
    profile, _, _ = _profile_and_candidates()
    assert profile.profile_id == IBM_TELCO_CHURN_PROFILE_ID
    assert profile.dataset_name == "IBM Telco Customer Churn"
    assert profile.row_count == 7_043
    assert profile.unique_customer_count == 7_043
    assert profile.churned_count == 1_869
    assert profile.retained_count == 5_174
    assert profile.overall_churn_rate_pct == 26.54
    assert profile.interpretation_boundary == (
        "Descriptive associations only; no causation, individual prediction, "
        "or outreach authorization."
    )


def test_all_approved_segment_rates_match_frozen_audit() -> None:
    """Every approved segment count, rate, category, and order is exact."""
    profile, _, _ = _profile_and_candidates()
    expected = {
        "contract_rates": [
            ("Month-to-month", 3_875, 1_655, 42.71),
            ("One year", 1_473, 166, 11.27),
            ("Two year", 1_695, 48, 2.83),
        ],
        "tech_support_rates": [
            ("No", 3_473, 1_446, 41.64),
            ("Yes", 2_044, 310, 15.17),
            ("No internet service", 1_526, 113, 7.40),
        ],
        "internet_service_rates": [
            ("Fiber optic", 3_096, 1_297, 41.89),
            ("DSL", 2_421, 459, 18.96),
            ("No", 1_526, 113, 7.40),
        ],
        "payment_method_rates": [
            ("Electronic check", 2_365, 1_071, 45.29),
            ("Mailed check", 1_612, 308, 19.11),
            ("Bank transfer (automatic)", 1_544, 258, 16.71),
            ("Credit card (automatic)", 1_522, 232, 15.24),
        ],
    }
    for field_name, rows in expected.items():
        actual = [
            (
                rate.segment,
                rate.customers,
                rate.churned,
                rate.churn_rate_pct,
            )
            for rate in getattr(profile, field_name)
        ]
        assert actual == rows


def test_churn_status_medians_and_parse_issues_match_audit() -> None:
    """Both status medians and all eleven parsing issues are preserved."""
    profile, _, _ = _profile_and_candidates()
    actual = [
        (
            item.churn_status,
            item.customers,
            item.median_tenure,
            item.median_monthly_charges,
            item.median_total_charges,
        )
        for item in profile.medians_by_churn_status
    ]
    assert actual == [
        ("No", 5_174, 38.0, 64.43, 1_683.60),
        ("Yes", 1_869, 10.0, 79.65, 703.55),
    ]
    assert profile.total_charges_parse_issue_count == 11


def test_seven_business_candidates_are_bounded_and_role_relevant() -> None:
    """Candidate order, facts, roles, limitations, and language are locked."""
    _, candidates, _ = _profile_and_candidates()
    assert len(candidates) == 7
    assert [item.evidence_type for item in candidates] == _EVIDENCE_TYPES
    assert [item.normalized_claim_key for item in candidates] == _CLAIM_KEYS
    assert [item.relevant_roles for item in candidates] == _ROLE_MAP
    assert all(item.business_profile_id == IBM_TELCO_CHURN_PROFILE_ID for item in candidates)
    assert "1,869 of 7,043 customers are marked as churned (26.54%)." in candidates[0].finding
    assert "1,655 of 3,875 churned (42.71%)" in candidates[1].finding
    assert "1,446 of 3,473 churned (41.64%)" in candidates[2].finding
    assert "1,297 of 3,096 churned (41.89%)" in candidates[3].finding
    assert "1,071 of 2,365 churned (45.29%)" in candidates[4].finding
    assert "median tenure 10.0 versus 38.0" in candidates[5].finding
    assert "median MonthlyCharges 79.65 versus 64.43" in candidates[5].finding
    assert "11 of 7,043 TotalCharges values are blank or nonnumeric" in candidates[6].finding
    assert "original column is stored as text" in candidates[6].finding
    assert "does not make the other profile metrics invalid" in candidates[6].finding

    required_limitations = {
        "This is a descriptive association and does not establish causation.",
        "Aggregate differences do not authorize individual customer targeting or outreach.",
    }
    forbidden = (
        "causes",
        "drives",
        "predicts",
        "proves",
        "should target",
        "high-risk customer",
        "likely to churn",
        "recommended customer",
    )
    for candidate in candidates:
        assert required_limitations.issubset(candidate.limitations)
        assert len(candidate.limitations) >= 3
        assert candidate.confidence == "high"
        assert "%" in candidate.finding
        assert not any(term in candidate.finding.lower() for term in forbidden)
        assert not hasattr(candidate, "evidence_id")
        assert not hasattr(candidate, "identity_digest")


def test_evidence_builder_mints_stable_deduplicated_business_evidence() -> None:
    """Business candidates cross only the approved Evidence minting boundary."""
    _, candidates, manifest = _profile_and_candidates()
    first = build_evidence(candidates, [manifest])
    second = build_evidence(candidates, [manifest])
    deduplicated = build_evidence(candidates + candidates, [manifest])

    assert first == second
    assert deduplicated == first
    assert len(first) == 7
    assert [item.evidence_type for item in first] == _EVIDENCE_TYPES
    for evidence in first:
        assert evidence.source_id == manifest.source_id
        assert evidence.source_format is SourceFormat.csv
        assert evidence.evidence_scope is EvidenceScope.internal_observation
        assert evidence.extraction_method == "deterministic"
        assert evidence.created_by == "evidence_builder"
        assert evidence.status is EvidenceStatus.active
        assert evidence.source_locator.row_range == (0, 7_042)

    external_manifest = _manifest_variant(
        manifest,
        source_scope=SourceScope.external_context,
    )
    report_manifest = _manifest_variant(
        manifest,
        semantic_context_category=SemanticContextCategory.internal_report,
    )
    excel_manifest = _manifest_variant(
        manifest,
        source_format=SourceFormat.excel,
    )
    excel_candidate_payload = candidates[0].model_dump()
    excel_candidate_payload["source_format"] = SourceFormat.excel
    excel_candidate = BusinessFindingCandidate.model_validate(
        excel_candidate_payload
    )
    incompatible_pairs = [
        (candidates, external_manifest),
        (candidates, report_manifest),
        ((excel_candidate,), excel_manifest),
    ]
    for incompatible_candidates, incompatible_manifest in incompatible_pairs:
        with pytest.raises(CandidateContractMismatchError):
            build_evidence(
                incompatible_candidates,
                [incompatible_manifest],
            )


def test_profiler_rejects_invalid_inputs_with_sanitized_errors() -> None:
    """Malformed datasets, manifests, and playbook IDs fail closed safely."""
    dataframe, manifest = _public_inputs()
    first_customer_id = dataframe.loc[0, "customerID"]
    invalid_frames: list[pd.DataFrame] = []
    invalid_frames.append(dataframe.drop(columns=["Contract"]))

    duplicate_id = dataframe.copy(deep=True)
    duplicate_id.loc[1, "customerID"] = duplicate_id.loc[0, "customerID"]
    invalid_frames.append(duplicate_id)

    blank_id = dataframe.copy(deep=True)
    blank_id.loc[0, "customerID"] = " "
    invalid_frames.append(blank_id)

    invalid_churn = dataframe.copy(deep=True)
    invalid_churn.loc[0, "Churn"] = "Maybe"
    invalid_frames.append(invalid_churn)

    invalid_tenure = dataframe.copy(deep=True)
    invalid_tenure.loc[0, "tenure"] = "not-numeric"
    invalid_frames.append(invalid_tenure)

    invalid_monthly = dataframe.copy(deep=True)
    invalid_monthly.loc[0, "MonthlyCharges"] = "-1"
    invalid_frames.append(invalid_monthly)

    missing_category = dataframe[dataframe["Contract"] != "Two year"].copy()
    invalid_frames.append(missing_category)

    for invalid in invalid_frames:
        with pytest.raises(BusinessProfileError) as error:
            build_business_profile(
                invalid,
                manifest,
                profile_id=IBM_TELCO_CHURN_PROFILE_ID,
            )
        message = str(error.value)
        assert first_customer_id not in message
        assert "errors.pydantic.dev" not in message
        assert "DataFrame(" not in message

    wrong_manifests = [
        _manifest_variant(
            manifest,
            semantic_context_category=SemanticContextCategory.internal_report,
        ),
        _manifest_variant(
            manifest,
            source_scope=SourceScope.external_context,
        ),
        _manifest_variant(manifest, source_format=SourceFormat.excel),
    ]
    for wrong_manifest in wrong_manifests:
        with pytest.raises(BusinessProfileError):
            build_business_profile(
                dataframe,
                wrong_manifest,
                profile_id=IBM_TELCO_CHURN_PROFILE_ID,
            )
    with pytest.raises(BusinessProfileError):
        build_business_profile(
            dataframe,
            object(),  # type: ignore[arg-type]
            profile_id=IBM_TELCO_CHURN_PROFILE_ID,
        )
    with pytest.raises(BusinessProfileError, match="Unsupported business profile"):
        build_business_profile(
            dataframe,
            manifest,
            profile_id="unknown_profile",
        )


def test_prepare_demo_inputs_without_profile_preserves_existing_behavior() -> None:
    """The existing synthetic preparation path remains profile-neutral."""
    import json

    from app.demo_pipeline import prepare_demo_inputs

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
    assert prepared.business_profile is None
    assert not any(
        evidence.evidence_type in _EVIDENCE_TYPES
        for evidence in prepared.evidence_objects
    )


def test_prepare_demo_inputs_opt_in_adds_only_business_evidence() -> None:
    """Explicit playbook selection adds seven Evidence Objects, not role inputs."""
    from app.demo_pipeline import DemoPipelineError, prepare_demo_inputs

    kwargs = {
        "csv_bytes": _PUBLIC_CSV.read_bytes(),
        "filename": _PUBLIC_CSV.name,
        "industry_context": (
            "External fictional telco context; not company-specific evidence."
        ),
        "strategy_profile": "Validate a limited retention pilot before outreach.",
        "business_question": "Is a limited validation pilot supportable?",
        "decision_goal": "Review aggregate patterns and control boundaries.",
        "user_assumption": "Contract patterns may be associated with churn.",
    }
    baseline = prepare_demo_inputs(**kwargs)
    prepared = prepare_demo_inputs(
        **kwargs,
        business_profile_id=IBM_TELCO_CHURN_PROFILE_ID,
    )
    assert isinstance(prepared.business_profile, BusinessDatasetProfile)
    business_evidence = [
        item
        for item in prepared.evidence_objects
        if item.evidence_type in _EVIDENCE_TYPES
    ]
    assert len(business_evidence) == 7
    assert len(prepared.evidence_objects) == len(baseline.evidence_objects) + 7
    assert [item.evidence_type for item in business_evidence] == _EVIDENCE_TYPES
    assert "business_profile" not in prepared.available_inputs
    assert set(prepared.available_inputs) == {
        "evidence_objects",
        "data_health_summary",
        "strategy_profile",
        "business_question",
        "source_manifest",
    }

    with pytest.raises(DemoPipelineError) as error:
        prepare_demo_inputs(**kwargs, business_profile_id="unknown_profile")
    assert str(error.value) == (
        "Business profiling failed. Check the selected playbook and dataset "
        "structure."
    )


def test_profiler_is_deterministic_immutable_and_side_effect_free() -> None:
    """Equal calls are equal and use no provider, env, network, clock, or RNG."""
    from app.granite_provider import GraniteRoleProvider
    from app.granite_semantic_risk_provider import GraniteSemanticRiskProvider

    dataframe, manifest = _public_inputs()
    original = dataframe.copy(deep=True)
    module_source = (
        _ROOT / "app" / "business_profile.py"
    ).read_text(encoding="utf-8")
    assert "app.granite" not in module_source
    assert "uuid" not in module_source
    assert "random" not in module_source
    assert "os.environ" not in module_source

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
    ), patch.object(
        GraniteRoleProvider,
        "from_env",
        side_effect=AssertionError("role provider calls are forbidden"),
    ), patch.object(
        GraniteSemanticRiskProvider,
        "from_env",
        side_effect=AssertionError("semantic provider calls are forbidden"),
    ):
        first_profile, first_candidates = build_business_profile(
            dataframe,
            manifest,
            profile_id=IBM_TELCO_CHURN_PROFILE_ID,
        )
        second_profile, second_candidates = build_business_profile(
            dataframe,
            manifest,
            profile_id=IBM_TELCO_CHURN_PROFILE_ID,
        )

    assert first_profile == second_profile
    assert first_candidates == second_candidates
    pd.testing.assert_frame_equal(dataframe, original)
