"""Provider-neutral dataset primer and grounded orientation contracts.

Only the explicit ``ibm_telco_churn_v1`` playbook is supported. Deterministic
construction reads frozen metadata, never raw CSV rows. Provider execution is
optional, validates all glossary and Evidence references, and fails safely.
"""

from __future__ import annotations

import json
import math
import pathlib
import re
from collections.abc import Mapping, Sequence
from typing import Any, Literal, Protocol, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.business_profile import (
    IBM_TELCO_CHURN_PROFILE_ID,
    BusinessDatasetProfile,
)
from app.schemas import EvidenceObject, EvidenceScope, EvidenceStatus


class DatasetOrientationError(ValueError):
    """Raised for sanitized deterministic orientation-input failures."""


_DATASET_NAME = "IBM Telco Customer Churn"
_INTERPRETATION_BOUNDARY = (
    "Descriptive associations only; no causation, individual prediction, "
    "or outreach authorization."
)
_DISCLOSURE = (
    "This is a fictional IBM sample dataset, not real customer production data."
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
_GUARDRAILS = (
    "Observed differences are descriptive associations and do not establish causation.",
    "Aggregate evidence does not estimate an individual customer's churn probability.",
    "The evidence does not authorize customer targeting, outreach, approval, or execution.",
    "The currency used by MonthlyCharges and TotalCharges is not specified and must not be assumed.",
)
_BUSINESS_EVIDENCE_TYPES = (
    "business_overall_churn",
    "business_contract_churn",
    "business_support_churn",
    "business_internet_churn",
    "business_payment_churn",
    "business_churn_medians",
    "business_parseability",
)
_PUBLIC_DATA_DIR = pathlib.Path(__file__).parent.parent / "sample_data" / "public"
_DEFAULT_CONTEXT_PATH = _PUBLIC_DATA_DIR / "ibm_telco_customer_churn_context.json"
_DEFAULT_GLOSSARY_PATH = _PUBLIC_DATA_DIR / "ibm_telco_customer_churn_glossary.json"
_DEFAULT_PROVENANCE_PATH = _PUBLIC_DATA_DIR / "ibm_telco_customer_churn.provenance.json"
_EVIDENCE_ID_RE = re.compile(r"^ev-[a-z0-9_]{1,12}-[0-9a-f]{12}$")
_CUSTOMER_ID_RE = re.compile(r"\b[0-9]{4}-[A-Z0-9]{5}\b")
_CURRENCY_RE = re.compile(
    r"(?:[$€£¥]|\b(?:USD|EUR|GBP|JPY|dollars?|euros?|pounds?|yen)\b)",
    re.IGNORECASE,
)
_FORBIDDEN_CLAIM_RE = re.compile(
    r"(?:\bcauses?\b|\bdrives?\b|\bleads? to\b|\bpredict(?:s|ed|ion)?\b|"
    r"\bchurn probability\b|\blikely to churn\b|\btarget(?:ing|ed)? customers?\b|"
    r"\bshould (?:contact|target|reach)\b|\bauthoriz(?:e|es|ed)\b"
    r"[^.!?]{0,40}\b(?:targeting|outreach)\b|"
    r"\bcompleted validation\b|\bfully validated\b|\bROI\b|"
    r"\bfinancial return\b|\bprofit(?:able|ability)?\b)",
    re.IGNORECASE,
)
_SAFE_NEGATED_BOUNDARY_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"the observed differences do not establish causation",
        r"these aggregate patterns do not predict individual churn",
        (
            r"these aggregate patterns do not predict individual churn and "
            r"do not authorize customer targeting or outreach"
        ),
        (
            r"the evidence does not estimate an individual customer's "
            r"churn probability"
        ),
        r"the evidence does not authorize customer targeting or outreach",
        r"no roi or financial return can be inferred from this dataset",
        (
            r"the analysis cannot identify which individual customer will "
            r"churn"
        ),
        r"these findings must not be used to target customers",
        r"association is not causation",
    )
)


class _FrozenContract(BaseModel):
    """Frozen, extra-forbidding base for local orientation contracts."""

    model_config = ConfigDict(extra="forbid", frozen=True)


def _non_blank(value: str, field_name: str) -> str:
    """Return non-blank text or raise a validation error."""
    if not value or not value.strip():
        raise ValueError(f"{field_name} must not be blank")
    return value


def _unique_non_blank(values: Sequence[str], field_name: str) -> None:
    """Require distinct non-blank string values."""
    if any(not value or not value.strip() for value in values):
        raise ValueError(f"{field_name} must not contain blank values")
    if len(values) != len(set(values)):
        raise ValueError(f"{field_name} must not contain duplicates")


def _contains_positive_or_ambiguous_overclaim(text: str) -> bool:
    """Detect overclaims after excluding only controlled negated sentences.

    This is deliberately not a general-purpose negation parser. A sentence is
    exempt only when its normalized full text matches one approved boundary
    statement. Mixed, positive, and ambiguous sentences remain subject to the
    complete overclaim pattern.
    """
    normalized = " ".join(text.replace("’", "'").split())
    sentences = re.split(r"(?<=[.!?])\s+", normalized)
    for sentence in sentences:
        bounded = sentence.strip().rstrip(".!?").strip()
        if not bounded:
            continue
        if any(
            pattern.fullmatch(bounded)
            for pattern in _SAFE_NEGATED_BOUNDARY_PATTERNS
        ):
            continue
        if _FORBIDDEN_CLAIM_RE.search(bounded):
            return True
    return False


class DatasetGlossaryTerm(_FrozenContract):
    """Plain-language orientation for one approved dataset field."""

    field_name: str
    plain_language: str
    primary_use: str
    caution: str

    @field_validator("field_name", "plain_language", "primary_use", "caution")
    @classmethod
    def text_non_blank(cls, value: str, info: Any) -> str:
        """Reject blank glossary text."""
        return _non_blank(value, info.field_name)


class DatasetPrimer(_FrozenContract):
    """Deterministic, controlled orientation facts for the approved playbook."""

    profile_id: Literal["ibm_telco_churn_v1"]
    dataset_name: Literal["IBM Telco Customer Churn"]
    dataset_context: str
    business_question: str
    row_count: int = Field(..., gt=0)
    unique_customer_count: int = Field(..., gt=0)
    churned_count: int = Field(..., gt=0)
    overall_churn_rate_pct: float = Field(..., ge=0, le=100)
    total_charges_parse_issue_count: int = Field(..., ge=0)
    currency_status: str
    glossary_terms: tuple[DatasetGlossaryTerm, ...]
    interpretation_boundary: Literal[
        "Descriptive associations only; no causation, individual prediction, or outreach authorization."
    ]
    disclosure: Literal[
        "This is a fictional IBM sample dataset, not real customer production data."
    ]
    guardrails: tuple[str, ...]

    @field_validator("dataset_context", "business_question", "currency_status")
    @classmethod
    def text_non_blank(cls, value: str, info: Any) -> str:
        """Reject blank primer text."""
        return _non_blank(value, info.field_name)

    @field_validator("overall_churn_rate_pct")
    @classmethod
    def rate_finite(cls, value: float) -> float:
        """Reject non-finite rates."""
        if not math.isfinite(value):
            raise ValueError("overall_churn_rate_pct must be finite")
        return value

    @model_validator(mode="after")
    def primer_is_consistent(self) -> "DatasetPrimer":
        """Enforce fixed glossary, guardrails, and derived aggregate facts."""
        if self.unique_customer_count != self.row_count:
            raise ValueError("row and unique-customer counts must match")
        if self.churned_count > self.unique_customer_count:
            raise ValueError("churned_count must not exceed customer count")
        expected_rate = round(
            self.churned_count / self.unique_customer_count * 100,
            2,
        )
        if self.overall_churn_rate_pct != expected_rate:
            raise ValueError("overall churn rate must match supplied counts")
        if self.total_charges_parse_issue_count > self.row_count:
            raise ValueError("parse issue count must not exceed row count")
        field_names = tuple(term.field_name for term in self.glossary_terms)
        if field_names != _GLOSSARY_FIELDS:
            raise ValueError("glossary fields must match the approved fixed order")
        if len(field_names) != len(set(field_names)):
            raise ValueError("glossary field names must be unique")
        if self.guardrails != _GUARDRAILS:
            raise ValueError("guardrails must match the approved controlled text")
        return self


class OrientationEvidenceSnapshot(_FrozenContract):
    """Minimum approved Evidence fields sent to an orientation provider."""

    evidence_id: str
    evidence_type: str
    finding: str
    limitations: tuple[str, ...]
    decision_relevance: str

    @field_validator("evidence_id")
    @classmethod
    def evidence_id_valid(cls, value: str) -> str:
        """Require the standard Evidence identifier syntax."""
        if not _EVIDENCE_ID_RE.fullmatch(value):
            raise ValueError("evidence_id has invalid syntax")
        return value

    @field_validator("evidence_type")
    @classmethod
    def evidence_type_approved(cls, value: str) -> str:
        """Permit only approved business-profile Evidence types."""
        if value not in _BUSINESS_EVIDENCE_TYPES:
            raise ValueError("evidence_type is not approved for orientation")
        return value

    @field_validator("finding", "decision_relevance")
    @classmethod
    def text_non_blank(cls, value: str, info: Any) -> str:
        """Reject blank snapshot text."""
        return _non_blank(value, info.field_name)

    @field_validator("limitations")
    @classmethod
    def limitations_unique_non_blank(
        cls,
        values: tuple[str, ...],
    ) -> tuple[str, ...]:
        """Require distinct non-blank limitation statements."""
        _unique_non_blank(values, "limitations")
        return values


class DatasetOrientationRequest(_FrozenContract):
    """Exact provider-neutral payload boundary for dataset orientation."""

    primer: DatasetPrimer
    business_evidence: tuple[OrientationEvidenceSnapshot, ...]
    allowed_evidence_ids: frozenset[str]

    @model_validator(mode="after")
    def request_is_exact(self) -> "DatasetOrientationRequest":
        """Require seven ordered snapshots and their exact Evidence ID set."""
        types = tuple(item.evidence_type for item in self.business_evidence)
        if types != _BUSINESS_EVIDENCE_TYPES:
            raise ValueError("business Evidence must match the approved fixed order")
        ids = tuple(item.evidence_id for item in self.business_evidence)
        if len(ids) != len(set(ids)):
            raise ValueError("business Evidence IDs must be unique")
        if self.allowed_evidence_ids != frozenset(ids):
            raise ValueError("allowed Evidence IDs must exactly match snapshots")
        return self


class OrientationTermExplanation(_FrozenContract):
    """Granite plain-language explanation of one selected glossary term."""

    field_name: str
    explanation: str
    caution: str

    @field_validator("field_name", "explanation", "caution")
    @classmethod
    def text_non_blank(cls, value: str, info: Any) -> str:
        """Reject blank output term text."""
        return _non_blank(value, info.field_name)


class OrientationPattern(_FrozenContract):
    """One Evidence-cited aggregate pattern in the Granite brief."""

    headline: str
    plain_language_explanation: str
    evidence_ids: tuple[str, ...]

    @field_validator("headline", "plain_language_explanation")
    @classmethod
    def text_non_blank(cls, value: str, info: Any) -> str:
        """Reject blank pattern text."""
        return _non_blank(value, info.field_name)

    @field_validator("evidence_ids")
    @classmethod
    def evidence_ids_non_empty_unique(
        cls,
        values: tuple[str, ...],
    ) -> tuple[str, ...]:
        """Require one or more unique, syntactically valid citations."""
        if not values:
            raise ValueError("evidence_ids must not be empty")
        _unique_non_blank(values, "evidence_ids")
        if any(not _EVIDENCE_ID_RE.fullmatch(value) for value in values):
            raise ValueError("evidence_ids contain invalid syntax")
        return values


class DatasetOrientationBrief(_FrozenContract):
    """Validated grounded Granite orientation for a first-time business user."""

    dataset_overview: str
    business_question_in_plain_language: str
    terms_to_know: tuple[OrientationTermExplanation, ...]
    key_patterns: tuple[OrientationPattern, ...]
    why_this_matters: str
    evidence_boundary_acknowledged: Literal[True]

    @field_validator(
        "dataset_overview",
        "business_question_in_plain_language",
        "why_this_matters",
    )
    @classmethod
    def text_non_blank(cls, value: str, info: Any) -> str:
        """Reject blank top-level output text."""
        return _non_blank(value, info.field_name)

    @model_validator(mode="after")
    def output_is_bounded(self) -> "DatasetOrientationBrief":
        """Enforce fixed cardinality and prohibited content boundaries."""
        fields = [term.field_name for term in self.terms_to_know]
        if len(fields) != 4 or len(fields) != len(set(fields)):
            raise ValueError("terms_to_know must contain exactly four unique fields")
        headlines = [pattern.headline for pattern in self.key_patterns]
        if len(headlines) != 3 or len(headlines) != len(set(headlines)):
            raise ValueError("key_patterns must contain three unique headlines")

        all_text = [
            self.dataset_overview,
            self.business_question_in_plain_language,
            self.why_this_matters,
            *fields,
            *(term.explanation for term in self.terms_to_know),
            *(term.caution for term in self.terms_to_know),
            *headlines,
            *(pattern.plain_language_explanation for pattern in self.key_patterns),
        ]
        if any(_CUSTOMER_ID_RE.search(text) for text in all_text):
            raise ValueError("orientation output must not contain customer IDs")
        if any(_CURRENCY_RE.search(text) for text in all_text):
            raise ValueError("orientation output must not invent currency")
        bounded_claim_text = [
            self.why_this_matters,
            *headlines,
            *(pattern.plain_language_explanation for pattern in self.key_patterns),
        ]
        if any(
            _contains_positive_or_ambiguous_overclaim(text)
            for text in bounded_claim_text
        ):
            raise ValueError("orientation output exceeds the evidence boundary")
        return self


class DatasetOrientationProvider(Protocol):
    """Provider-neutral interface for one structured orientation brief."""

    def generate_dataset_orientation(
        self,
        request: DatasetOrientationRequest,
    ) -> Mapping[str, Any]:
        """Return one raw structured orientation mapping."""
        ...


_FAILURE_REASONS = {
    "provider_error": "Dataset orientation provider failed.",
    "invalid_output": "Dataset orientation output failed structured validation.",
    "invalid_evidence_reference": (
        "Dataset orientation cited Evidence outside the approved request."
    ),
    "invalid_glossary_reference": (
        "Dataset orientation referenced a field outside the approved glossary."
    ),
}


class DatasetOrientationFailure(_FrozenContract):
    """Typed safe failure that never substitutes a successful brief."""

    failure_code: Literal[
        "provider_error",
        "invalid_output",
        "invalid_evidence_reference",
        "invalid_glossary_reference",
    ]
    reason: str

    @field_validator("reason")
    @classmethod
    def reason_non_blank(cls, value: str) -> str:
        """Require controlled non-blank failure text."""
        return _non_blank(value, "reason")

    @model_validator(mode="after")
    def reason_matches_code(self) -> "DatasetOrientationFailure":
        """Lock every public failure code to one controlled safe reason."""
        if self.reason != _FAILURE_REASONS[self.failure_code]:
            raise ValueError("reason must match the controlled failure code")
        return self


DatasetOrientationOutcome: TypeAlias = (
    DatasetOrientationBrief | DatasetOrientationFailure
)


class _ContextDocument(_FrozenContract):
    """Validated shape of the frozen context metadata file."""

    dataset_context: str
    business_question: str
    decision_goal: str
    strategy_profile: str
    user_assumption: str

    @field_validator("dataset_context", "business_question", "decision_goal", "strategy_profile", "user_assumption")
    @classmethod
    def values_non_blank(cls, value: str, info: Any) -> str:
        """Reject blank frozen context fields."""
        return _non_blank(value, info.field_name)


class _GlossaryEntryDocument(_FrozenContract):
    """Validated frozen glossary-entry shape."""

    field: str
    plain_language: str
    primary_use: str
    caution: str

    @field_validator("field", "plain_language", "primary_use", "caution")
    @classmethod
    def values_non_blank(cls, value: str, info: Any) -> str:
        """Reject blank frozen glossary fields."""
        return _non_blank(value, info.field_name)


class _GlossaryDocument(_FrozenContract):
    """Validated shape of the frozen glossary metadata file."""

    dataset_name: Literal["IBM Telco Customer Churn"]
    currency_status: str
    fields: tuple[_GlossaryEntryDocument, ...]

    @field_validator("currency_status")
    @classmethod
    def currency_status_non_blank(cls, value: str) -> str:
        """Reject blank currency-status text."""
        return _non_blank(value, "currency_status")


def _load_json_mapping(path: pathlib.Path) -> Mapping[str, Any]:
    """Read one JSON object or raise only controlled orientation errors."""
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        raise DatasetOrientationError(
            "Dataset orientation metadata could not be loaded."
        ) from None
    if not isinstance(parsed, Mapping):
        raise DatasetOrientationError(
            "Dataset orientation metadata has an invalid structure."
        )
    return parsed


def build_dataset_primer(
    business_profile: BusinessDatasetProfile,
    *,
    business_question: str,
    context_path: pathlib.Path | None = None,
    glossary_path: pathlib.Path | None = None,
    provenance_path: pathlib.Path | None = None,
) -> DatasetPrimer:
    """Build the deterministic primer from typed profile and frozen metadata."""
    if type(business_profile) is not BusinessDatasetProfile:
        raise DatasetOrientationError(
            "Dataset Primer requires an exact BusinessDatasetProfile."
        )
    if business_profile.profile_id != IBM_TELCO_CHURN_PROFILE_ID:
        raise DatasetOrientationError("Dataset profile is not supported.")
    if not isinstance(business_question, str) or not business_question.strip():
        raise DatasetOrientationError("Business question must not be blank.")

    try:
        context = _ContextDocument.model_validate(
            _load_json_mapping(context_path or _DEFAULT_CONTEXT_PATH)
        )
        glossary = _GlossaryDocument.model_validate(
            _load_json_mapping(glossary_path or _DEFAULT_GLOSSARY_PATH)
        )
        provenance = _load_json_mapping(
            provenance_path or _DEFAULT_PROVENANCE_PATH
        )
        if (
            provenance.get("dataset_name") != _DATASET_NAME
            or type(provenance.get("original_row_count")) is not int
            or provenance.get("original_row_count") != 7_043
            or type(provenance.get("original_column_count")) is not int
            or provenance.get("original_column_count") != 21
            or provenance.get("fictional_company_sample") is not True
            or provenance.get("disclosure") != _DISCLOSURE
        ):
            raise ValueError("provenance facts are inconsistent")
        if (
            business_profile.row_count != 7_043
            or business_profile.unique_customer_count != 7_043
            or business_profile.churned_count != 1_869
            or business_profile.overall_churn_rate_pct != 26.54
            or business_profile.total_charges_parse_issue_count != 11
        ):
            raise ValueError("business profile facts are inconsistent")

        terms = tuple(
            DatasetGlossaryTerm(
                field_name=item.field,
                plain_language=item.plain_language,
                primary_use=item.primary_use,
                caution=item.caution,
            )
            for item in glossary.fields
        )
        return DatasetPrimer(
            profile_id=business_profile.profile_id,
            dataset_name=glossary.dataset_name,
            dataset_context=context.dataset_context,
            business_question=business_question,
            row_count=business_profile.row_count,
            unique_customer_count=business_profile.unique_customer_count,
            churned_count=business_profile.churned_count,
            overall_churn_rate_pct=business_profile.overall_churn_rate_pct,
            total_charges_parse_issue_count=(
                business_profile.total_charges_parse_issue_count
            ),
            currency_status=glossary.currency_status,
            glossary_terms=terms,
            interpretation_boundary=_INTERPRETATION_BOUNDARY,
            disclosure=_DISCLOSURE,
            guardrails=_GUARDRAILS,
        )
    except DatasetOrientationError:
        raise
    except Exception:
        raise DatasetOrientationError(
            "Dataset orientation metadata failed validation."
        ) from None


def build_dataset_orientation_request(
    *,
    business_profile: BusinessDatasetProfile,
    evidence_objects: Sequence[EvidenceObject],
    business_question: str,
) -> DatasetOrientationRequest:
    """Build the exact seven-Evidence provider request or fail safely."""
    try:
        primer = build_dataset_primer(
            business_profile,
            business_question=business_question,
        )
        if not isinstance(evidence_objects, Sequence):
            raise ValueError("Evidence input must be a sequence")
        if len(evidence_objects) != 7:
            raise ValueError("exactly seven business Evidence Objects required")
        if any(type(item) is not EvidenceObject for item in evidence_objects):
            raise ValueError("Evidence values must be exact EvidenceObject values")

        by_type: dict[str, EvidenceObject] = {}
        seen_ids: set[str] = set()
        source_ids: set[str] = set()
        for evidence in evidence_objects:
            if evidence.evidence_type not in _BUSINESS_EVIDENCE_TYPES:
                raise ValueError("nonbusiness Evidence is not permitted")
            if (
                evidence.evidence_type in by_type
                or evidence.evidence_id in seen_ids
            ):
                raise ValueError("duplicate business Evidence is not permitted")
            if (
                evidence.status is not EvidenceStatus.active
                or evidence.extraction_method != "deterministic"
                or evidence.evidence_scope is not EvidenceScope.internal_observation
                or evidence.created_by != "evidence_builder"
                or evidence.source_format.value != "csv"
            ):
                raise ValueError("business Evidence provenance is invalid")
            by_type[evidence.evidence_type] = evidence
            seen_ids.add(evidence.evidence_id)
            source_ids.add(evidence.source_id)
        if set(by_type) != set(_BUSINESS_EVIDENCE_TYPES) or len(source_ids) != 1:
            raise ValueError("business Evidence set is incomplete or mixed-source")

        snapshots = tuple(
            OrientationEvidenceSnapshot(
                evidence_id=by_type[evidence_type].evidence_id,
                evidence_type=evidence_type,
                finding=by_type[evidence_type].finding,
                limitations=tuple(by_type[evidence_type].limitations),
                decision_relevance=by_type[evidence_type].decision_relevance,
            )
            for evidence_type in _BUSINESS_EVIDENCE_TYPES
        )
        return DatasetOrientationRequest(
            primer=primer,
            business_evidence=snapshots,
            allowed_evidence_ids=frozenset(
                snapshot.evidence_id for snapshot in snapshots
            ),
        )
    except DatasetOrientationError:
        raise
    except Exception:
        raise DatasetOrientationError(
            "Dataset orientation request failed validation."
        ) from None


def _failure(code: str) -> DatasetOrientationFailure:
    """Construct one controlled typed orientation failure."""
    return DatasetOrientationFailure(
        failure_code=code,
        reason=_FAILURE_REASONS[code],
    )


def orient_dataset(
    *,
    provider: DatasetOrientationProvider,
    request: DatasetOrientationRequest,
) -> DatasetOrientationOutcome:
    """Generate, validate, and ground one brief without raising raw failures."""
    try:
        raw_output = provider.generate_dataset_orientation(request)
    except Exception:
        return _failure("provider_error")
    try:
        brief = DatasetOrientationBrief.model_validate(raw_output)
    except Exception:
        return _failure("invalid_output")

    glossary_fields = {
        term.field_name for term in request.primer.glossary_terms
    }
    if any(
        term.field_name not in glossary_fields
        for term in brief.terms_to_know
    ):
        return _failure("invalid_glossary_reference")
    if any(
        evidence_id not in request.allowed_evidence_ids
        for pattern in brief.key_patterns
        for evidence_id in pattern.evidence_ids
    ):
        return _failure("invalid_evidence_reference")
    return brief
