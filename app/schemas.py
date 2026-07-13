"""
app/schemas.py — RoleLens core identity and provenance schemas (Task 1).

Defines all Pydantic v2 models for:
  - Enums: SourceFormat, SemanticContextCategory, SourceScope,
           EvidenceScope, EvidenceStatus
  - Locators: TabularSourceLocator, TextSourceLocator, UserContextLocator
  - SourceLocator discriminated union
  - SourceManifestEntry
  - EvidenceObject
  - EvidenceReference
  - HealthFindingCandidate

ID generation and hashing belong in app/identity.py (Task 2).
This module validates ID format and digest format only.

Architecture invariants enforced here:
  - HealthFindingCandidate has no evidence_id field (minting boundary).
  - EvidenceStatus contains only "active" and "invalidated".
  - Cross-object reference existence is NOT validated here.
  - All models use extra="forbid" and validate_assignment=True.
"""

from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from enum import Enum
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# ---------------------------------------------------------------------------
# Compiled regex patterns for ID and digest validation
# ---------------------------------------------------------------------------

_SOURCE_ID_RE = re.compile(r"^src-[a-z0-9_]{1,12}-[0-9a-f]{12}$")
_EVIDENCE_ID_RE = re.compile(r"^ev-[a-z0-9_]{1,12}-[0-9a-f]{12}$")
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")

# Stable identity-key syntax patterns.
# These define syntax only — vocabulary is controlled by identity.py and
# data_health.py, not by schemas.py.
_ID_ALGO_VERSION_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,31}$")
_EVIDENCE_TYPE_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_CLAIM_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*$")
_CLAIM_KEY_MAX_LEN = 128


# ---------------------------------------------------------------------------
# Shared base model
# ---------------------------------------------------------------------------


class ContractModel(BaseModel):
    """Base model for all RoleLens schema models.

    extra="forbid" ensures that LLM structured output cannot silently add
    unsupported fields, and HealthFindingCandidate actively rejects
    evidence_id and identity_digest at construction and assignment time.

    validate_assignment=True ensures that setting a field after construction
    re-runs all field validators, so the schema contract cannot be bypassed
    by post-construction assignment.
    """

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class SourceFormat(str, Enum):
    """Physical format of an uploaded or user-provided source.

    Separates physical format from semantic purpose (SemanticContextCategory).
    pdf_text is not included in the active V1 enum; it is delayed optional support.
    """

    csv = "csv"
    excel = "excel"
    pasted_text = "pasted_text"
    txt = "txt"
    markdown = "markdown"
    form_input = "form_input"


class SemanticContextCategory(str, Enum):
    """Semantic purpose of a source within the decision workflow.

    Separates semantic role from physical format (SourceFormat).
    The same physical format submitted for different semantic purposes
    produces different source_id values because this category is an
    identity input in app/identity.py.
    """

    data_source = "data_source"
    internal_report = "internal_report"
    industry_context = "industry_context"
    strategy_profile = "strategy_profile"
    business_question = "business_question"
    decision_goal = "decision_goal"
    user_assumption = "user_assumption"


class SourceScope(str, Enum):
    """Epistemic origin of a source.

    Controls evidence admissibility in the downstream pipeline.
    decision_context sources (business_question, decision_goal) do not
    produce EvidenceObjects; they provide pipeline context only.
    """

    internal_observation = "internal_observation"
    external_context = "external_context"
    user_assertion = "user_assertion"
    decision_context = "decision_context"


class EvidenceScope(str, Enum):
    """Epistemic status of a derived Evidence Object.

    Maps from SourceScope:
      internal_observation  → internal_observation evidence
      external_context      → external_context evidence
      user_assertion        → assumption evidence
      strategy goal/profile → stated_priority evidence

    risk_checker.py enforces that external_context and assumption evidence
    is not cited as direct company-specific proof.
    """

    internal_observation = "internal_observation"
    external_context = "external_context"
    assumption = "assumption"
    stated_priority = "stated_priority"


class EvidenceStatus(str, Enum):
    """Lifecycle status of an Evidence Object.

    Only two valid values:
      active      — valid and available for citation
      invalidated — invalidated after creation; downstream objects citing it
                    must be flagged for human review

    Duplicate evidence is a deduplication outcome handled during minting in
    evidence_builder.py — no duplicate EvidenceObject is created.
    A short-ID collision raises IdentityCollisionError in identity.py — it
    does not produce a collision EvidenceObject.
    """

    active = "active"
    invalidated = "invalidated"


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _validate_source_id(v: str) -> str:
    """Validate generic source_id format: src-{abbrev}-{12_hex}."""
    if not _SOURCE_ID_RE.match(v):
        raise ValueError(
            f"source_id must match src-[a-z0-9_]{{1,12}}-[0-9a-f]{{12}}, got: {v!r}"
        )
    return v


def _validate_evidence_id(v: str) -> str:
    """Validate generic evidence_id format: ev-{abbrev}-{12_hex}."""
    if not _EVIDENCE_ID_RE.match(v):
        raise ValueError(
            f"evidence_id must match ev-[a-z0-9_]{{1,12}}-[0-9a-f]{{12}}, got: {v!r}"
        )
    return v


def _validate_digest(v: str) -> str:
    """Validate identity_digest: exactly 64 lowercase hexadecimal characters."""
    if not _DIGEST_RE.match(v):
        raise ValueError(
            "identity_digest must be exactly 64 lowercase hexadecimal characters"
        )
    return v


def _validate_id_algo_version(v: str) -> str:
    """Validate id_algo_version syntax: ^[a-z0-9][a-z0-9._-]{0,31}$

    Rejects blank strings, padded strings, uppercase letters, and versions
    that do not start with an alphanumeric character.
    """
    if not _ID_ALGO_VERSION_RE.match(v):
        raise ValueError(
            f"id_algo_version must match ^[a-z0-9][a-z0-9._-]{{0,31}}$, got: {v!r}"
        )
    return v


def _validate_evidence_type(v: str) -> str:
    """Validate evidence_type syntax: ^[a-z][a-z0-9_]{0,63}$

    Rejects blank strings, padded strings, uppercase letters, spaces, and
    types that do not start with a lowercase letter.
    """
    if not _EVIDENCE_TYPE_RE.match(v):
        raise ValueError(
            f"evidence_type must match ^[a-z][a-z0-9_]{{0,63}}$, got: {v!r}"
        )
    return v


def _validate_relevant_roles(v: list[str]) -> list[str]:
    """Shared validator: relevant_roles must be non-empty with no blank strings.

    Does NOT hardcode valid role names — role existence is governed by
    role_policy.json, not by schemas.py.
    """
    if not v:
        raise ValueError("relevant_roles must not be empty")
    blank = [r for r in v if not r or not r.strip()]
    if blank:
        raise ValueError("relevant_roles must not contain blank role names")
    return v


def _validate_json_value(value: Any, path: str = "root") -> None:
    """Recursively validate that a value is JSON-compatible.

    Allowed types: None, bool, int, finite float, str, list, dict (str keys).
    Rejected: set, bytes, bytearray, complex, NaN, Infinity, -Infinity.
    Nested structures are validated recursively.
    """
    if value is None or isinstance(value, (bool, str)):
        return
    if isinstance(value, int):
        # bool is a subclass of int; already handled above
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(
                f"canonical_rule_parameters contains a non-finite float "
                f"({value!r}) at {path}; NaN, Infinity, and -Infinity are not "
                f"valid JSON values"
            )
        return
    if isinstance(value, list):
        for i, item in enumerate(value):
            _validate_json_value(item, path=f"{path}[{i}]")
        return
    if isinstance(value, dict):
        for k, v in value.items():
            if not isinstance(k, str):
                raise ValueError(
                    f"canonical_rule_parameters dict keys must be strings; "
                    f"got key of type {type(k).__name__} at {path}"
                )
            _validate_json_value(v, path=f"{path}.{k}")
        return
    # Anything else (set, bytes, bytearray, complex, …)
    raise ValueError(
        f"canonical_rule_parameters contains a non-JSON-compatible value of "
        f"type {type(value).__name__} at {path}"
    )


# Locked semantic-category → source-scope mappings.
# Only unambiguous mappings are enforced here.
# data_source and internal_report are intentionally excluded because their
# exact scope may depend on intake context.
_LOCKED_CATEGORY_SCOPE: dict[SemanticContextCategory, SourceScope] = {
    SemanticContextCategory.business_question: SourceScope.decision_context,
    SemanticContextCategory.decision_goal: SourceScope.decision_context,
    SemanticContextCategory.industry_context: SourceScope.external_context,
    SemanticContextCategory.strategy_profile: SourceScope.user_assertion,
    SemanticContextCategory.user_assumption: SourceScope.user_assertion,
}

# ---------------------------------------------------------------------------
# Source Locator models
# ---------------------------------------------------------------------------


class TabularSourceLocator(ContractModel):
    """Locates evidence within a tabular source (CSV or Excel).

    columns must be non-empty and contain no blank names.
    row_range, when supplied, must satisfy 0 <= start <= end.
    """

    locator_type: Literal["tabular"] = "tabular"
    columns: list[str] = Field(..., description="Column names referenced by this evidence")
    row_range: tuple[int, int] | None = Field(
        None, description="Inclusive (start, end) row indices (0-based)"
    )
    sheet_name: str | None = Field(None, description="Excel sheet name; None for CSV")
    cell_range: str | None = Field(None, description="Excel cell range, e.g. 'A1:D10'")
    metric: str | None = Field(None, description="Metric or measure referenced")
    aggregation: str | None = Field(None, description="Aggregation applied, e.g. 'mean'")

    @field_validator("columns")
    @classmethod
    def columns_non_empty(cls, v: list[str]) -> list[str]:
        """columns must be non-empty and contain no blank strings."""
        if not v:
            raise ValueError("columns must not be empty")
        blank = [c for c in v if not c or not c.strip()]
        if blank:
            raise ValueError("columns must not contain blank names")
        return v

    @field_validator("row_range")
    @classmethod
    def row_range_valid(cls, v: tuple[int, int] | None) -> tuple[int, int] | None:
        """Row indices must be non-negative and start must not exceed end."""
        if v is None:
            return v
        start, end = v
        if start < 0 or end < 0:
            raise ValueError("row_range indices must be non-negative")
        if start > end:
            raise ValueError("row_range start must not exceed end")
        return v


class TextSourceLocator(ContractModel):
    """Locates evidence within a text source (pasted text, TXT, Markdown).

    At least one meaningful location field must be supplied.
    Supplied numeric indexes must be non-negative (enforced via Field(ge=0)).
    A start index must not exceed its matching end index.
    heading_path, when supplied, must not be blank or whitespace-only.
    excerpt_checksum, when supplied, must be a 64-char lowercase hex string.
    """

    locator_type: Literal["text"] = "text"
    line_start: int | None = Field(None, ge=0, description="Inclusive start line (0-based)")
    line_end: int | None = Field(None, ge=0, description="Inclusive end line (0-based)")
    char_start: int | None = Field(None, ge=0, description="Inclusive start character offset")
    char_end: int | None = Field(None, ge=0, description="Inclusive end character offset")
    heading_path: str | None = Field(
        None, description="Heading hierarchy, e.g. '## Sec / ### Sub'"
    )
    paragraph_index: int | None = Field(None, ge=0, description="Paragraph index (0-based)")
    chunk_index: int | None = Field(None, ge=0, description="Chunk index for split text")
    excerpt_checksum: str | None = Field(
        None, description="SHA-256 hex of the raw excerpt for integrity verification"
    )

    @field_validator("heading_path")
    @classmethod
    def heading_path_non_blank(cls, v: str | None) -> str | None:
        """heading_path, when supplied, must not be blank or whitespace-only."""
        if v is not None and not v.strip():
            raise ValueError("heading_path must not be blank or whitespace-only when supplied")
        return v

    @field_validator("excerpt_checksum")
    @classmethod
    def checksum_format(cls, v: str | None) -> str | None:
        """excerpt_checksum must be exactly 64 lowercase hexadecimal characters."""
        if v is not None and not _DIGEST_RE.match(v):
            raise ValueError(
                "excerpt_checksum must be exactly 64 lowercase hexadecimal characters"
            )
        return v

    @model_validator(mode="after")
    def at_least_one_location_field(self) -> "TextSourceLocator":
        """At least one meaningful location field must be supplied.

        heading_path counts only when non-blank (blank is rejected by
        heading_path_non_blank before this validator runs).
        """
        location_fields = (
            self.line_start,
            self.line_end,
            self.char_start,
            self.char_end,
            self.heading_path,
            self.paragraph_index,
            self.chunk_index,
            self.excerpt_checksum,
        )
        if all(f is None for f in location_fields):
            raise ValueError(
                "TextSourceLocator requires at least one location field "
                "(line_start, line_end, char_start, char_end, heading_path, "
                "paragraph_index, chunk_index, or excerpt_checksum)"
            )
        return self

    @model_validator(mode="after")
    def end_requires_start(self) -> "TextSourceLocator":
        """An end index requires its matching start index.

        line_end without line_start is rejected.
        char_end without char_start is rejected.
        A start without an end is valid (open-ended span).
        """
        if self.line_end is not None and self.line_start is None:
            raise ValueError(
                "line_end requires line_start; supply line_start or omit line_end"
            )
        if self.char_end is not None and self.char_start is None:
            raise ValueError(
                "char_end requires char_start; supply char_start or omit char_end"
            )
        return self

    @model_validator(mode="after")
    def start_does_not_exceed_end(self) -> "TextSourceLocator":
        """A start index must not exceed its matching end index."""
        if self.line_start is not None and self.line_end is not None:
            if self.line_start > self.line_end:
                raise ValueError("line_start must not exceed line_end")
        if self.char_start is not None and self.char_end is not None:
            if self.char_start > self.char_end:
                raise ValueError("char_start must not exceed char_end")
        return self


class UserContextLocator(ContractModel):
    """Locates evidence within a user-provided context field (form, strategy profile, etc.).

    field_name must be non-blank.
    """

    locator_type: Literal["user_context"] = "user_context"
    field_name: str = Field(..., description="Name of the form or context field")
    form_section: str | None = Field(None, description="Section of the form, if applicable")
    context_category: SemanticContextCategory = Field(
        ..., description="Semantic category of this context field"
    )
    user_entered_version: str | None = Field(
        None, description="User-supplied version label for this context"
    )

    @field_validator("field_name")
    @classmethod
    def field_name_non_blank(cls, v: str) -> str:
        """field_name must be non-blank."""
        if not v or not v.strip():
            raise ValueError("field_name must not be blank")
        return v


# ---------------------------------------------------------------------------
# SourceLocator discriminated union
# ---------------------------------------------------------------------------

SourceLocator = Annotated[
    Union[TabularSourceLocator, TextSourceLocator, UserContextLocator],
    Field(discriminator="locator_type"),
]
"""Discriminated union of all source-locator types.

Use locator_type to select the correct subtype:
  "tabular"      → TabularSourceLocator
  "text"         → TextSourceLocator
  "user_context" → UserContextLocator
"""

# Format-to-locator compatibility constants (used by cross-field validators).
_TABULAR_FORMATS: frozenset[SourceFormat] = frozenset({
    SourceFormat.csv,
    SourceFormat.excel,
})
_TEXT_FORMATS: frozenset[SourceFormat] = frozenset({
    SourceFormat.pasted_text,
    SourceFormat.txt,
    SourceFormat.markdown,
})
_USER_CONTEXT_FORMATS: frozenset[SourceFormat] = frozenset({
    SourceFormat.form_input,
})


def _validate_format_locator_compat(
    source_format: SourceFormat,
    source_locator: Any,
    model_name: str,
) -> None:
    """Raise ValueError if source_format and source_locator are incompatible.

    Compatibility rules:
      csv, excel            → TabularSourceLocator required
      pasted_text, txt, md  → TextSourceLocator required
      form_input            → UserContextLocator required
    """
    if source_format in _TABULAR_FORMATS:
        if not isinstance(source_locator, TabularSourceLocator):
            raise ValueError(
                f"{model_name}: source_format={source_format.value!r} requires "
                f"TabularSourceLocator (locator_type='tabular'), got "
                f"{type(source_locator).__name__}"
            )
    elif source_format in _TEXT_FORMATS:
        if not isinstance(source_locator, TextSourceLocator):
            raise ValueError(
                f"{model_name}: source_format={source_format.value!r} requires "
                f"TextSourceLocator (locator_type='text'), got "
                f"{type(source_locator).__name__}"
            )
    elif source_format in _USER_CONTEXT_FORMATS:
        if not isinstance(source_locator, UserContextLocator):
            raise ValueError(
                f"{model_name}: source_format={source_format.value!r} requires "
                f"UserContextLocator (locator_type='user_context'), got "
                f"{type(source_locator).__name__}"
            )


# ---------------------------------------------------------------------------
# SourceManifestEntry
# ---------------------------------------------------------------------------


class SourceManifestEntry(ContractModel):
    """Records identity and provenance metadata for one uploaded or provided source.

    source_id and identity_digest are generated by app/identity.py (Task 2).
    Task 1 validates their formats only.

    filename and upload_event_id are excluded from identity generation;
    they are metadata about the upload event, not the source content.

    created_at must be timezone-aware. The intake layer is responsible for
    normalization to UTC; schemas.py validates awareness only.

    Five unambiguous semantic_context_category → source_scope mappings are
    enforced. data_source and internal_report are not locked because their
    exact scope may depend on intake context.
    """

    source_id: str = Field(..., description="Hybrid short source ID: src-{abbrev}-{12_hex}")
    identity_digest: str = Field(
        ..., description="Full SHA-256 identity digest (64 lowercase hex chars)"
    )
    source_format: SourceFormat = Field(..., description="Physical format of the source")
    semantic_context_category: SemanticContextCategory = Field(
        ..., description="Semantic purpose of this source in the decision workflow"
    )
    source_scope: SourceScope = Field(
        ..., description="Epistemic origin of this source"
    )
    filename: str | None = Field(
        None, description="Original filename (excluded from identity)"
    )
    upload_event_id: str | None = Field(
        None, description="Upload session identifier (excluded from identity)"
    )
    id_algo_version: str = Field(
        default="v1", description="Identity algorithm version used to generate source_id"
    )
    created_at: datetime = Field(
        ..., description="Timezone-aware timestamp of source registration"
    )

    @field_validator("source_id")
    @classmethod
    def source_id_format(cls, v: str) -> str:
        return _validate_source_id(v)

    @field_validator("identity_digest")
    @classmethod
    def identity_digest_format(cls, v: str) -> str:
        return _validate_digest(v)

    @field_validator("id_algo_version")
    @classmethod
    def id_algo_version_syntax(cls, v: str) -> str:
        """id_algo_version must match ^[a-z0-9][a-z0-9._-]{0,31}$."""
        return _validate_id_algo_version(v)

    @field_validator("created_at")
    @classmethod
    def created_at_timezone_aware(cls, v: datetime) -> datetime:
        """created_at must be timezone-aware.

        Naive datetime values are rejected. Timezone-aware values (including
        non-UTC) are accepted; normalization to UTC is the intake layer's
        responsibility.
        """
        if v.tzinfo is None or v.utcoffset() is None:
            raise ValueError(
                "created_at must be timezone-aware; naive datetime values are not accepted"
            )
        return v

    @model_validator(mode="after")
    def locked_category_scope(self) -> "SourceManifestEntry":
        """Enforce five unambiguous semantic_context_category → source_scope mappings.

        Locked mappings:
          business_question → decision_context
          decision_goal     → decision_context
          industry_context  → external_context
          strategy_profile  → user_assertion
          user_assumption   → user_assertion

        data_source and internal_report are intentionally not locked because
        their scope may depend on intake context.
        """
        required = _LOCKED_CATEGORY_SCOPE.get(self.semantic_context_category)
        if required is not None and self.source_scope != required:
            raise ValueError(
                f"semantic_context_category={self.semantic_context_category.value!r} "
                f"requires source_scope={required.value!r}, "
                f"got source_scope={self.source_scope.value!r}"
            )
        return self


# ---------------------------------------------------------------------------
# EvidenceObject
# ---------------------------------------------------------------------------


class EvidenceObject(ContractModel):
    """One Evidence Object derived from a source.

    evidence_id is minted exclusively by app/evidence_builder.py (Task 5).
    Task 1 validates the format only.

    finding and supporting_evidence are human-readable descriptions and are
    NOT identity inputs — changing them does not change evidence_id.

    If status is 'invalidated', invalidated_reason must be provided.
    If status is 'active', invalidated_reason must be absent.

    source_format and source_locator must be compatible (e.g. csv requires
    TabularSourceLocator).
    """

    evidence_id: str = Field(..., description="Hybrid short evidence ID: ev-{abbrev}-{12_hex}")
    identity_digest: str = Field(
        ..., description="Full SHA-256 identity digest (64 lowercase hex chars)"
    )
    source_id: str = Field(..., description="source_id of the originating source")
    source_format: SourceFormat = Field(..., description="Physical format of the originating source")
    source_locator: SourceLocator = Field(
        ..., description="Typed locator pointing to the evidence span within the source"
    )
    evidence_type: str = Field(
        ..., description="Rule key identifying the type of finding, e.g. 'missing_value_rate'"
    )
    evidence_scope: EvidenceScope = Field(
        ..., description="Epistemic status of this evidence"
    )
    extraction_method: Literal["deterministic", "llm_assisted"] = Field(
        ..., description="How this evidence was extracted"
    )
    finding: str = Field(
        ..., description="Human-readable description of the finding (not an identity input)"
    )
    supporting_evidence: str = Field(
        ..., description="Raw data or quote backing the finding (not an identity input)"
    )
    confidence: Literal["low", "medium", "high"] = Field(
        ..., description="Confidence level for this evidence"
    )
    limitations: list[str] = Field(
        default_factory=list, description="Known constraints or caveats; empty list allowed"
    )
    relevant_roles: list[str] = Field(
        ..., description="Non-empty list of role names that should consider this evidence"
    )
    decision_relevance: str = Field(
        ..., description="How this evidence impacts the business decision"
    )
    id_algo_version: str = Field(
        default="v1", description="Identity algorithm version used to generate evidence_id"
    )
    created_by: Literal["data_health", "evidence_builder", "llm_pipeline"] = Field(
        ..., description="Which pipeline stage created this evidence"
    )
    status: EvidenceStatus = Field(
        default=EvidenceStatus.active, description="Lifecycle status of this evidence"
    )
    invalidated_reason: str | None = Field(
        None, description="Required when status is 'invalidated'; must be absent when 'active'"
    )

    @field_validator("evidence_id")
    @classmethod
    def evidence_id_format(cls, v: str) -> str:
        return _validate_evidence_id(v)

    @field_validator("identity_digest")
    @classmethod
    def identity_digest_format(cls, v: str) -> str:
        return _validate_digest(v)

    @field_validator("source_id")
    @classmethod
    def source_id_format(cls, v: str) -> str:
        return _validate_source_id(v)

    @field_validator("evidence_type")
    @classmethod
    def evidence_type_syntax(cls, v: str) -> str:
        """evidence_type must match ^[a-z][a-z0-9_]{0,63}$."""
        return _validate_evidence_type(v)

    @field_validator("finding")
    @classmethod
    def finding_non_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("finding must not be blank")
        return v

    @field_validator("supporting_evidence")
    @classmethod
    def supporting_evidence_non_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("supporting_evidence must not be blank")
        return v

    @field_validator("relevant_roles")
    @classmethod
    def relevant_roles_valid(cls, v: list[str]) -> list[str]:
        return _validate_relevant_roles(v)

    @field_validator("decision_relevance")
    @classmethod
    def decision_relevance_non_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("decision_relevance must not be blank")
        return v

    @field_validator("id_algo_version")
    @classmethod
    def id_algo_version_syntax(cls, v: str) -> str:
        """id_algo_version must match ^[a-z0-9][a-z0-9._-]{0,31}$."""
        return _validate_id_algo_version(v)

    @model_validator(mode="after")
    def invalidation_consistency(self) -> "EvidenceObject":
        """invalidated_reason is required when invalidated, and forbidden when active."""
        if self.status == EvidenceStatus.invalidated:
            if not self.invalidated_reason or not self.invalidated_reason.strip():
                raise ValueError(
                    "invalidated_reason is required and must not be blank "
                    "when status is 'invalidated'"
                )
        elif self.status == EvidenceStatus.active:
            if self.invalidated_reason is not None:
                raise ValueError(
                    "invalidated_reason must be absent when status is 'active'"
                )
        return self

    @model_validator(mode="after")
    def format_locator_compatible(self) -> "EvidenceObject":
        """source_format and source_locator must be compatible."""
        _validate_format_locator_compat(
            self.source_format, self.source_locator, "EvidenceObject"
        )
        return self


# ---------------------------------------------------------------------------
# EvidenceReference
# ---------------------------------------------------------------------------


class EvidenceReference(ContractModel):
    """A citation of an Evidence Object by its evidence_id.

    Validates evidence_id format only.
    Whether the referenced EvidenceObject actually exists in the current
    trajectory is NOT validated here — that requires a separate registry
    or trajectory validation function (implemented later).
    """

    evidence_id: str = Field(..., description="evidence_id of the cited Evidence Object")
    relevance_note: str | None = Field(
        None, description="Optional note explaining why this evidence is cited here"
    )

    @field_validator("evidence_id")
    @classmethod
    def evidence_id_format(cls, v: str) -> str:
        return _validate_evidence_id(v)


# ---------------------------------------------------------------------------
# HealthFindingCandidate
# ---------------------------------------------------------------------------


class HealthFindingCandidate(ContractModel):
    """A structured finding produced by data_health.py before evidence minting.

    This model intentionally has NO evidence_id or identity_digest field.
    It is an intermediate type that app/evidence_builder.py converts into
    an EvidenceObject, at which point evidence_id is minted.

    Because ContractModel sets extra="forbid", passing evidence_id or
    identity_digest as constructor arguments will raise a ValidationError,
    actively enforcing the minting boundary.

    This design enforces the minting boundary:
      data_health.py  →  HealthFindingCandidate  →  evidence_builder.py  →  EvidenceObject
    """

    source_id: str = Field(..., description="source_id of the originating source")
    source_format: SourceFormat = Field(..., description="Physical format of the originating source")
    source_locator: SourceLocator = Field(
        ..., description="Typed locator pointing to the finding's span within the source"
    )
    evidence_type: str = Field(
        ..., description="Rule key identifying the type of finding, e.g. 'missing_value_rate'"
    )
    canonical_rule_parameters: dict[str, Any] = Field(
        ...,
        description=(
            "Deterministic, JSON-compatible parameters of the health rule that produced "
            "this finding. Used as an identity input in evidence_builder.py. "
            "Values must be JSON-serialisable: null, bool, int, finite float, str, "
            "list, or dict with string keys. NaN, Infinity, set, bytes, and complex "
            "are rejected."
        ),
    )
    normalized_claim_key: str = Field(
        ...,
        description=(
            "Short, stable, non-free-form key identifying the claim category, "
            "e.g. 'missing_value_rate.contract_value'. Used as an identity input."
        ),
    )
    finding: str = Field(
        ..., description="Human-readable description (not an identity input)"
    )
    supporting_evidence: str = Field(
        ..., description="Raw data or quote backing the finding (not an identity input)"
    )
    confidence: Literal["low", "medium", "high"] = Field(...)
    limitations: list[str] = Field(default_factory=list)
    relevant_roles: list[str] = Field(
        ..., description="Non-empty list of role names for this finding, no blank strings"
    )
    decision_relevance: str = Field(...)

    @field_validator("source_id")
    @classmethod
    def source_id_format(cls, v: str) -> str:
        return _validate_source_id(v)

    @field_validator("evidence_type")
    @classmethod
    def evidence_type_syntax(cls, v: str) -> str:
        """evidence_type must match ^[a-z][a-z0-9_]{0,63}$."""
        return _validate_evidence_type(v)

    @field_validator("normalized_claim_key")
    @classmethod
    def claim_key_syntax(cls, v: str) -> str:
        """normalized_claim_key must match ^[a-z][a-z0-9_]*(\\.[a-z][a-z0-9_]*)*$
        and must not exceed 128 characters.

        Rejects: padded strings, uppercase letters, spaces, empty dot-segments,
        and keys longer than 128 characters.
        """
        if len(v) > _CLAIM_KEY_MAX_LEN:
            raise ValueError(
                f"normalized_claim_key must not exceed {_CLAIM_KEY_MAX_LEN} characters, "
                f"got {len(v)}"
            )
        if not _CLAIM_KEY_RE.match(v):
            raise ValueError(
                f"normalized_claim_key must match "
                f"^[a-z][a-z0-9_]*(\\.[a-z][a-z0-9_]*)*$, got: {v!r}"
            )
        return v

    @field_validator("relevant_roles")
    @classmethod
    def relevant_roles_valid(cls, v: list[str]) -> list[str]:
        """Use shared validator: non-empty, no blank strings."""
        return _validate_relevant_roles(v)

    @field_validator("decision_relevance")
    @classmethod
    def decision_relevance_non_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("decision_relevance must not be blank")
        return v

    @field_validator("canonical_rule_parameters")
    @classmethod
    def rule_params_json_compatible(cls, v: dict[str, Any]) -> dict[str, Any]:
        """Recursively validate that all values are JSON-compatible.

        Accepts: None, bool, int, finite float, str, list, dict (str keys).
        Rejects: set, bytes, bytearray, complex, NaN, Infinity, -Infinity,
                 nested unsupported values.
        """
        _validate_json_value(v, path="canonical_rule_parameters")
        return v

    @model_validator(mode="after")
    def format_locator_compatible(self) -> "HealthFindingCandidate":
        """source_format and source_locator must be compatible."""
        _validate_format_locator_compat(
            self.source_format, self.source_locator, "HealthFindingCandidate"
        )
        return self
