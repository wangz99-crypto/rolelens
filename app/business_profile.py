"""Deterministic aggregate business profiling for approved decision playbooks.

Task 10C-1 supports only the frozen fictional IBM Telco Customer Churn
sample. It produces validated aggregate profile contracts and
BusinessFindingCandidate values; Evidence Objects remain the exclusive
responsibility of :mod:`app.evidence_builder`.
"""

from __future__ import annotations

import math
from typing import Any, Literal

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas import (
    BusinessFindingCandidate,
    SemanticContextCategory,
    SourceFormat,
    SourceManifestEntry,
    SourceScope,
    TabularSourceLocator,
)


class BusinessProfileError(ValueError):
    """Raised when an approved business playbook cannot profile its input."""


IBM_TELCO_CHURN_PROFILE_ID = "ibm_telco_churn_v1"

_DATASET_NAME = "IBM Telco Customer Churn"
_INTERPRETATION_BOUNDARY = (
    "Descriptive associations only; no causation, individual prediction, "
    "or outreach authorization."
)
_REQUIRED_COLUMNS = frozenset(
    {
        "customerID",
        "tenure",
        "InternetService",
        "TechSupport",
        "Contract",
        "PaymentMethod",
        "MonthlyCharges",
        "TotalCharges",
        "Churn",
    }
)
_CONTRACT_ORDER = ("Month-to-month", "One year", "Two year")
_TECH_SUPPORT_ORDER = ("No", "Yes", "No internet service")
_INTERNET_SERVICE_ORDER = ("Fiber optic", "DSL", "No")
_PAYMENT_METHOD_ORDER = (
    "Electronic check",
    "Mailed check",
    "Bank transfer (automatic)",
    "Credit card (automatic)",
)
_ASSOCIATION_LIMITATION = (
    "This is a descriptive association and does not establish causation."
)
_TARGETING_LIMITATION = (
    "Aggregate differences do not authorize individual customer targeting "
    "or outreach."
)


class _LocalContract(BaseModel):
    """Frozen, extra-forbidding base for local profiler outputs."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class SegmentChurnRate(_LocalContract):
    """Observed churn count and rate for one aggregate segment."""

    segment: str
    customers: int = Field(..., gt=0)
    churned: int = Field(..., ge=0)
    churn_rate_pct: float = Field(..., ge=0, le=100)

    @field_validator("segment")
    @classmethod
    def segment_non_blank(cls, value: str) -> str:
        """Reject blank segment labels."""
        if not value or not value.strip():
            raise ValueError("segment must not be blank")
        return value

    @model_validator(mode="after")
    def rate_matches_counts(self) -> "SegmentChurnRate":
        """Require a feasible count and its exact two-decimal derived rate."""
        if self.churned > self.customers:
            raise ValueError("churned must not exceed customers")
        expected = round(self.churned / self.customers * 100, 2)
        if self.churn_rate_pct != expected:
            raise ValueError("churn_rate_pct must equal the derived rate")
        return self


class ChurnStatusMedians(_LocalContract):
    """Non-negative numeric medians for one observed churn status."""

    churn_status: Literal["No", "Yes"]
    customers: int = Field(..., gt=0)
    median_tenure: float
    median_monthly_charges: float
    median_total_charges: float

    @field_validator(
        "median_tenure",
        "median_monthly_charges",
        "median_total_charges",
    )
    @classmethod
    def medians_finite_non_negative(cls, value: float) -> float:
        """Reject non-finite or negative medians."""
        if not math.isfinite(value) or value < 0:
            raise ValueError("numeric medians must be finite and non-negative")
        return value


class BusinessDatasetProfile(_LocalContract):
    """Complete deterministic aggregate profile for the approved sample."""

    profile_id: Literal["ibm_telco_churn_v1"]
    dataset_name: Literal["IBM Telco Customer Churn"]
    row_count: int = Field(..., gt=0)
    unique_customer_count: int = Field(..., gt=0)
    churned_count: int = Field(..., ge=0)
    retained_count: int = Field(..., ge=0)
    overall_churn_rate_pct: float = Field(..., ge=0, le=100)
    total_charges_parse_issue_count: int = Field(..., ge=0)
    contract_rates: tuple[SegmentChurnRate, ...]
    tech_support_rates: tuple[SegmentChurnRate, ...]
    internet_service_rates: tuple[SegmentChurnRate, ...]
    payment_method_rates: tuple[SegmentChurnRate, ...]
    medians_by_churn_status: tuple[ChurnStatusMedians, ...]
    interpretation_boundary: Literal[
        "Descriptive associations only; no causation, individual prediction, or outreach authorization."
    ]

    @model_validator(mode="after")
    def aggregates_are_consistent(self) -> "BusinessDatasetProfile":
        """Reject caller-supplied aggregates inconsistent with their parts."""
        if self.row_count != self.unique_customer_count:
            raise ValueError("row and unique-customer counts must match")
        if self.churned_count + self.retained_count != self.unique_customer_count:
            raise ValueError("churn status counts must match unique customers")
        expected_rate = round(
            self.churned_count / self.unique_customer_count * 100,
            2,
        )
        if self.overall_churn_rate_pct != expected_rate:
            raise ValueError("overall_churn_rate_pct must equal the derived rate")
        if self.total_charges_parse_issue_count > self.row_count:
            raise ValueError("parse issue count must not exceed row count")

        for field_name, rates in (
            ("contract_rates", self.contract_rates),
            ("tech_support_rates", self.tech_support_rates),
            ("internet_service_rates", self.internet_service_rates),
            ("payment_method_rates", self.payment_method_rates),
        ):
            if not rates:
                raise ValueError(f"{field_name} must not be empty")
            labels = [rate.segment for rate in rates]
            if len(labels) != len(set(labels)):
                raise ValueError(f"{field_name} segment labels must be unique")
            if sum(rate.customers for rate in rates) != self.unique_customer_count:
                raise ValueError(f"{field_name} customer counts are inconsistent")
            if sum(rate.churned for rate in rates) != self.churned_count:
                raise ValueError(f"{field_name} churn counts are inconsistent")

        statuses = [item.churn_status for item in self.medians_by_churn_status]
        if statuses != ["No", "Yes"]:
            raise ValueError("medians_by_churn_status must contain exactly No then Yes")
        if self.medians_by_churn_status[0].customers != self.retained_count:
            raise ValueError("retained median count is inconsistent")
        if self.medians_by_churn_status[1].customers != self.churned_count:
            raise ValueError("churned median count is inconsistent")
        return self


def _normalized_text(dataframe: pd.DataFrame, column: str) -> pd.Series:
    """Return a whitespace-normalized calculation copy of a text column."""
    return dataframe[column].astype("string").fillna("").str.strip()


def _validated_numeric(
    dataframe: pd.DataFrame,
    column: str,
) -> pd.Series:
    """Return a finite, non-negative numeric calculation series."""
    numeric = pd.to_numeric(_normalized_text(dataframe, column), errors="coerce")
    if numeric.isna().any() or (numeric < 0).any():
        raise BusinessProfileError(
            f"{column} must contain only finite non-negative numeric values."
        )
    if not all(math.isfinite(float(value)) for value in numeric):
        raise BusinessProfileError(
            f"{column} must contain only finite non-negative numeric values."
        )
    return numeric


def _segment_rates(
    segments: pd.Series,
    churn: pd.Series,
    order: tuple[str, ...],
) -> tuple[SegmentChurnRate, ...]:
    """Compute approved segment aggregates in fixed playbook order."""
    rates: list[SegmentChurnRate] = []
    for label in order:
        selected = segments == label
        customers = int(selected.sum())
        churned = int((selected & (churn == "Yes")).sum())
        rates.append(
            SegmentChurnRate(
                segment=label,
                customers=customers,
                churned=churned,
                churn_rate_pct=round(churned / customers * 100, 2),
            )
        )
    return tuple(rates)


def _rate_parameters(
    profile_id: str,
    metric: str,
    rates: tuple[SegmentChurnRate, ...],
) -> dict[str, Any]:
    """Return stable JSON-compatible identity parameters for segment rates."""
    return {
        "profile_id": profile_id,
        "metric": metric,
        "segments": [rate.model_dump(mode="json") for rate in rates],
    }


def _candidate(
    *,
    source_manifest: SourceManifestEntry,
    profile: BusinessDatasetProfile,
    evidence_type: str,
    claim_key: str,
    columns: list[str],
    metric: str,
    parameters: dict[str, Any],
    finding: str,
    supporting_evidence: str,
    limitations: list[str],
    relevant_roles: list[str],
    decision_relevance: str,
) -> BusinessFindingCandidate:
    """Construct one validated aggregate candidate with CSV provenance."""
    return BusinessFindingCandidate(
        source_id=source_manifest.source_id,
        source_format=SourceFormat.csv,
        source_locator=TabularSourceLocator(
            columns=columns,
            row_range=(0, profile.row_count - 1),
            metric=metric,
            aggregation="deterministic aggregate",
        ),
        evidence_type=evidence_type,
        canonical_rule_parameters=parameters,
        normalized_claim_key=claim_key,
        finding=finding,
        supporting_evidence=supporting_evidence,
        confidence="high",
        limitations=limitations,
        relevant_roles=relevant_roles,
        decision_relevance=decision_relevance,
        business_profile_id=profile.profile_id,
    )


def _build_candidates(
    profile: BusinessDatasetProfile,
    source_manifest: SourceManifestEntry,
) -> tuple[BusinessFindingCandidate, ...]:
    """Build the seven approved aggregate findings in locked order."""
    association = [_ASSOCIATION_LIMITATION, _TARGETING_LIMITATION]
    contract = profile.contract_rates
    support = profile.tech_support_rates
    internet = profile.internet_service_rates
    payment = profile.payment_method_rates
    retained, churned = profile.medians_by_churn_status
    retained_pct = round(profile.retained_count / profile.row_count * 100, 2)
    parse_pct = round(
        profile.total_charges_parse_issue_count / profile.row_count * 100,
        2,
    )
    boundary = "This descriptive result is an association, not a causal conclusion."

    return (
        _candidate(
            source_manifest=source_manifest,
            profile=profile,
            evidence_type="business_overall_churn",
            claim_key="business.telco.overall_churn",
            columns=["customerID", "Churn"],
            metric="overall_churn_rate",
            parameters={
                "profile_id": profile.profile_id,
                "metric": "overall_churn_rate",
                "customers": profile.row_count,
                "churned": profile.churned_count,
                "churn_rate_pct": profile.overall_churn_rate_pct,
            },
            finding=(
                f"{profile.churned_count:,} of {profile.row_count:,} customers "
                f"are marked as churned ({profile.overall_churn_rate_pct:.2f}%). "
                + boundary
            ),
            supporting_evidence=(
                f"Churn counts: Yes={profile.churned_count:,}; "
                f"No={profile.retained_count:,}; total unique customers="
                f"{profile.unique_customer_count:,}."
            ),
            limitations=association
            + ["The sample describes a fictional IBM telco dataset."],
            relevant_roles=[
                "executive",
                "data_analyst",
                "sales_marketing",
                "project_manager",
            ],
            decision_relevance=(
                "Provides the shared aggregate baseline for a bounded retention-pilot discussion."
            ),
        ),
        _candidate(
            source_manifest=source_manifest,
            profile=profile,
            evidence_type="business_contract_churn",
            claim_key="business.telco.churn_by_contract",
            columns=["Contract", "Churn"],
            metric="churn_by_contract",
            parameters=_rate_parameters(
                profile.profile_id,
                "churn_by_contract",
                contract,
            ),
            finding=(
                f"Month-to-month: {contract[0].churned:,} of "
                f"{contract[0].customers:,} churned "
                f"({contract[0].churn_rate_pct:.2f}%); One year: "
                f"{contract[1].churned:,} of {contract[1].customers:,} churned "
                f"({contract[1].churn_rate_pct:.2f}%); Two year: "
                f"{contract[2].churned:,} of {contract[2].customers:,} churned "
                f"({contract[2].churn_rate_pct:.2f}%). "
                + boundary
            ),
            supporting_evidence=(
                f"Contract aggregates cover all {profile.row_count:,} customers "
                f"and all {profile.churned_count:,} churn records."
            ),
            limitations=association
            + ["Contract groups may differ on other observed or unobserved factors."],
            relevant_roles=[
                "executive",
                "data_analyst",
                "sales_marketing",
                "project_manager",
            ],
            decision_relevance=(
                "Identifies a contract-associated pattern for aggregate pilot validation."
            ),
        ),
        _candidate(
            source_manifest=source_manifest,
            profile=profile,
            evidence_type="business_support_churn",
            claim_key="business.telco.churn_by_tech_support",
            columns=["TechSupport", "Churn"],
            metric="churn_by_tech_support",
            parameters=_rate_parameters(
                profile.profile_id,
                "churn_by_tech_support",
                support,
            ),
            finding=(
                f"TechSupport No: {support[0].churned:,} of "
                f"{support[0].customers:,} churned "
                f"({support[0].churn_rate_pct:.2f}%); Yes: "
                f"{support[1].churned:,} of {support[1].customers:,} churned "
                f"({support[1].churn_rate_pct:.2f}%); No internet service: "
                f"{support[2].churned:,} of {support[2].customers:,} churned "
                f"({support[2].churn_rate_pct:.2f}%). "
                + boundary
            ),
            supporting_evidence=(
                f"TechSupport aggregates cover all {profile.row_count:,} customers "
                f"and all {profile.churned_count:,} churn records."
            ),
            limitations=association
            + ["TechSupport status is not evidence of service-effect direction."],
            relevant_roles=["data_analyst", "sales_marketing", "executive"],
            decision_relevance=(
                "Provides an aggregate service-support pattern for validation design."
            ),
        ),
        _candidate(
            source_manifest=source_manifest,
            profile=profile,
            evidence_type="business_internet_churn",
            claim_key="business.telco.churn_by_internet_service",
            columns=["InternetService", "Churn"],
            metric="churn_by_internet_service",
            parameters=_rate_parameters(
                profile.profile_id,
                "churn_by_internet_service",
                internet,
            ),
            finding=(
                f"Fiber optic: {internet[0].churned:,} of "
                f"{internet[0].customers:,} churned "
                f"({internet[0].churn_rate_pct:.2f}%); DSL: "
                f"{internet[1].churned:,} of {internet[1].customers:,} churned "
                f"({internet[1].churn_rate_pct:.2f}%); No internet service: "
                f"{internet[2].churned:,} of {internet[2].customers:,} churned "
                f"({internet[2].churn_rate_pct:.2f}%). "
                + boundary
            ),
            supporting_evidence=(
                f"InternetService aggregates cover all {profile.row_count:,} "
                f"customers and all {profile.churned_count:,} churn records."
            ),
            limitations=association
            + ["Service categories may reflect different customer contexts."],
            relevant_roles=["data_analyst", "sales_marketing", "executive"],
            decision_relevance=(
                "Provides an aggregate service-type pattern for bounded analysis."
            ),
        ),
        _candidate(
            source_manifest=source_manifest,
            profile=profile,
            evidence_type="business_payment_churn",
            claim_key="business.telco.churn_by_payment_method",
            columns=["PaymentMethod", "Churn"],
            metric="churn_by_payment_method",
            parameters=_rate_parameters(
                profile.profile_id,
                "churn_by_payment_method",
                payment,
            ),
            finding=(
                f"Electronic check: {payment[0].churned:,} of "
                f"{payment[0].customers:,} churned "
                f"({payment[0].churn_rate_pct:.2f}%); Mailed check: "
                f"{payment[1].churned:,} of {payment[1].customers:,} churned "
                f"({payment[1].churn_rate_pct:.2f}%); Bank transfer (automatic): "
                f"{payment[2].churned:,} of {payment[2].customers:,} churned "
                f"({payment[2].churn_rate_pct:.2f}%); Credit card (automatic): "
                f"{payment[3].churned:,} of {payment[3].customers:,} churned "
                f"({payment[3].churn_rate_pct:.2f}%). "
                + boundary
            ),
            supporting_evidence=(
                f"PaymentMethod aggregates cover all {profile.row_count:,} "
                f"customers and all {profile.churned_count:,} churn records."
            ),
            limitations=association
            + ["Payment methods may correlate with other account characteristics."],
            relevant_roles=["data_analyst", "sales_marketing", "executive"],
            decision_relevance=(
                "Provides an aggregate payment-method pattern for bounded validation."
            ),
        ),
        _candidate(
            source_manifest=source_manifest,
            profile=profile,
            evidence_type="business_churn_medians",
            claim_key="business.telco.churn_status_medians",
            columns=["Churn", "tenure", "MonthlyCharges", "TotalCharges"],
            metric="churn_status_medians",
            parameters={
                "profile_id": profile.profile_id,
                "metric": "churn_status_medians",
                "statuses": [
                    item.model_dump(mode="json")
                    for item in profile.medians_by_churn_status
                ],
            },
            finding=(
                f"Churned customers have median tenure "
                f"{churned.median_tenure:.1f} versus "
                f"{retained.median_tenure:.1f} for retained customers, and "
                f"median MonthlyCharges {churned.median_monthly_charges:.2f} "
                f"versus {retained.median_monthly_charges:.2f}. The groups contain "
                f"{churned.customers:,} churned customers "
                f"({profile.overall_churn_rate_pct:.2f}% of {profile.row_count:,}) "
                f"and {retained.customers:,} retained customers "
                f"({retained_pct:.2f}%); median TotalCharges is "
                f"{churned.median_total_charges:,.2f} versus "
                f"{retained.median_total_charges:,.2f}. "
                + boundary
            ),
            supporting_evidence=(
                f"No: customers={retained.customers}, tenure={retained.median_tenure:.1f}, "
                f"MonthlyCharges={retained.median_monthly_charges:.2f}, "
                f"TotalCharges={retained.median_total_charges:.2f}; Yes: "
                f"customers={churned.customers}, tenure={churned.median_tenure:.1f}, "
                f"MonthlyCharges={churned.median_monthly_charges:.2f}, "
                f"TotalCharges={churned.median_total_charges:.2f}."
            ),
            limitations=association
            + ["Medians summarize groups and do not describe every customer."],
            relevant_roles=["executive", "data_analyst", "sales_marketing"],
            decision_relevance=(
                "Frames aggregate tenure and charge differences for pilot measurement."
            ),
        ),
        _candidate(
            source_manifest=source_manifest,
            profile=profile,
            evidence_type="business_parseability",
            claim_key="business.telco.total_charges_parseability",
            columns=["TotalCharges"],
            metric="total_charges_parseability",
            parameters={
                "profile_id": profile.profile_id,
                "metric": "total_charges_parseability",
                "rows": profile.row_count,
                "parse_issue_count": profile.total_charges_parse_issue_count,
                "parse_issue_rate_pct": parse_pct,
            },
            finding=(
                f"{profile.total_charges_parse_issue_count:,} of "
                f"{profile.row_count:,} TotalCharges values are blank or nonnumeric "
                f"({parse_pct:.2f}%); the original column is stored as text. "
                "The issue affects calculations using TotalCharges but does not "
                "make the other profile metrics invalid. "
                + boundary
            ),
            supporting_evidence=(
                f"TotalCharges parse audit: "
                f"{profile.total_charges_parse_issue_count:,} blank or nonnumeric "
                f"values; {profile.row_count - profile.total_charges_parse_issue_count:,} "
                "numeric values."
            ),
            limitations=association
            + ["TotalCharges medians exclude the 11 unparseable values."],
            relevant_roles=["data_engineer", "data_analyst", "project_manager"],
            decision_relevance=(
                "Records the bounded parsing limitation for TotalCharges-based analysis."
            ),
        ),
    )


def build_business_profile(
    dataframe: Any,
    source_manifest: SourceManifestEntry,
    *,
    profile_id: str,
) -> tuple[BusinessDatasetProfile, tuple[BusinessFindingCandidate, ...]]:
    """Build the selected deterministic aggregate business playbook.

    Only ``ibm_telco_churn_v1`` is supported. The caller's DataFrame is read
    without mutation, and all errors are converted to display-safe messages.
    """
    if profile_id != IBM_TELCO_CHURN_PROFILE_ID:
        raise BusinessProfileError("Unsupported business profile ID.")
    if type(source_manifest) is not SourceManifestEntry:
        raise BusinessProfileError(
            "Business profiling requires an exact SourceManifestEntry."
        )
    if (
        source_manifest.source_format is not SourceFormat.csv
        or source_manifest.semantic_context_category
        is not SemanticContextCategory.data_source
        or source_manifest.source_scope is not SourceScope.internal_observation
    ):
        raise BusinessProfileError(
            "Business profiling requires an internal-observation CSV data source."
        )
    if type(dataframe) is not pd.DataFrame or dataframe.empty:
        raise BusinessProfileError("Business profiling requires a non-empty DataFrame.")
    if not _REQUIRED_COLUMNS.issubset(dataframe.columns):
        raise BusinessProfileError("Required Telco profile columns are missing.")

    try:
        customer_ids = _normalized_text(dataframe, "customerID")
        if (customer_ids == "").any() or customer_ids.duplicated().any():
            raise BusinessProfileError(
                "customerID values must be non-blank and unique."
            )

        churn = _normalized_text(dataframe, "Churn")
        if not set(churn.unique()).issubset({"No", "Yes"}) or not {
            "No",
            "Yes",
        }.issubset(set(churn.unique())):
            raise BusinessProfileError("Churn must contain only Yes and No values.")

        tenure = _validated_numeric(dataframe, "tenure")
        monthly_charges = _validated_numeric(dataframe, "MonthlyCharges")
        total_charges_text = _normalized_text(dataframe, "TotalCharges")
        total_charges = pd.to_numeric(total_charges_text, errors="coerce")
        total_charges = total_charges.where(
            total_charges.map(
                lambda value: (
                    not pd.isna(value) and math.isfinite(float(value))
                )
            )
        )

        normalized_categories = {
            "Contract": _normalized_text(dataframe, "Contract"),
            "TechSupport": _normalized_text(dataframe, "TechSupport"),
            "InternetService": _normalized_text(dataframe, "InternetService"),
            "PaymentMethod": _normalized_text(dataframe, "PaymentMethod"),
        }
        for column, required in (
            ("Contract", _CONTRACT_ORDER),
            ("TechSupport", _TECH_SUPPORT_ORDER),
            ("InternetService", _INTERNET_SERVICE_ORDER),
            ("PaymentMethod", _PAYMENT_METHOD_ORDER),
        ):
            if not set(required).issubset(set(normalized_categories[column].unique())):
                raise BusinessProfileError(
                    "Required frozen Telco categories are missing."
                )

        row_count = len(dataframe)
        churned_count = int((churn == "Yes").sum())
        retained_count = int((churn == "No").sum())
        medians: list[ChurnStatusMedians] = []
        for status in ("No", "Yes"):
            selected = churn == status
            medians.append(
                ChurnStatusMedians(
                    churn_status=status,
                    customers=int(selected.sum()),
                    median_tenure=round(float(tenure[selected].median()), 2),
                    median_monthly_charges=round(
                        float(monthly_charges[selected].median()),
                        2,
                    ),
                    median_total_charges=round(
                        float(total_charges[selected].median()),
                        2,
                    ),
                )
            )

        profile = BusinessDatasetProfile(
            profile_id=IBM_TELCO_CHURN_PROFILE_ID,
            dataset_name=_DATASET_NAME,
            row_count=row_count,
            unique_customer_count=int(customer_ids.nunique()),
            churned_count=churned_count,
            retained_count=retained_count,
            overall_churn_rate_pct=round(churned_count / row_count * 100, 2),
            total_charges_parse_issue_count=int(total_charges.isna().sum()),
            contract_rates=_segment_rates(
                normalized_categories["Contract"],
                churn,
                _CONTRACT_ORDER,
            ),
            tech_support_rates=_segment_rates(
                normalized_categories["TechSupport"],
                churn,
                _TECH_SUPPORT_ORDER,
            ),
            internet_service_rates=_segment_rates(
                normalized_categories["InternetService"],
                churn,
                _INTERNET_SERVICE_ORDER,
            ),
            payment_method_rates=_segment_rates(
                normalized_categories["PaymentMethod"],
                churn,
                _PAYMENT_METHOD_ORDER,
            ),
            medians_by_churn_status=tuple(medians),
            interpretation_boundary=_INTERPRETATION_BOUNDARY,
        )
        return profile, _build_candidates(profile, source_manifest)
    except BusinessProfileError:
        raise
    except Exception:
        raise BusinessProfileError(
            "Business profiling failed validation."
        ) from None
