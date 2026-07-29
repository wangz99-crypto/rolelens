"""
app/schemas.py — RoleLens core identity and provenance schemas (Task 1 / Task 5B-1 / Task 6A-1).

Defines all Pydantic v2 models for:
  - Enums: SourceFormat, SemanticContextCategory, SourceScope,
           EvidenceScope, EvidenceStatus
  - Locators: TabularSourceLocator, TextSourceLocator, UserContextLocator
  - SourceLocator discriminated union
  - SourceManifestEntry
  - EvidenceObject
  - EvidenceReference
  - HealthFindingCandidate
  - TextEvidenceCandidate  (Task 5B-1)
  - RoleKey                (Task 6A-1)
  - GroundedFinding        (Task 6A-1)
  - RoleView               (Task 6A-1)

ID generation and hashing belong in app/identity.py (Task 2).
This module validates ID format and digest format only.

Architecture invariants enforced here:
  - HealthFindingCandidate has no evidence_id field (minting boundary).
  - TextEvidenceCandidate has no evidence_id or identity_digest (minting boundary).
  - RoleView requires at least one GroundedFinding — no evidence means no RoleView.
  - EvidenceStatus contains only "active" and "invalidated".
  - Cross-object reference existence is NOT validated here.
  - All models use extra="forbid" and frozen=True.
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

    frozen=True makes all contract models immutable after construction.
    This prevents a model_validator from leaving a model in an illegal state
    after a failed after-validator on single-field assignment.  Revised
    objects must be reconstructed and validated rather than mutated in place.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)


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


# ---------------------------------------------------------------------------
# Task 4 — DataHealthSummary (added here as part of the first vertical slice)
# ---------------------------------------------------------------------------


class DataHealthSummary(ContractModel):
    """Summary of deterministic data-health metrics for a tabular source.

    Produced by data_health.py.  Does NOT contain evidence_id values.
    Evidence minting happens downstream in evidence_builder.py.

    readiness_score is intentionally absent: no defensible scoring method
    has been approved.  It is deferred until a scoring method is reviewed.
    """

    source_id: str = Field(
        ...,
        description="source_id of the CSV or tabular source that was analyzed",
    )
    row_count: int = Field(..., ge=0, description="Total number of rows in the source")
    column_count: int = Field(..., ge=0, description="Total number of columns in the source")
    duplicate_row_count: int = Field(
        ...,
        ge=0,
        description="Number of fully duplicated rows (all columns identical)",
    )
    missing_value_rates: dict[str, float] = Field(
        default_factory=dict,
        description="Per-column fraction of missing values (0.0–1.0)",
    )
    columns_with_mixed_types: list[str] = Field(
        default_factory=list,
        description="Column names where multiple Python types are detected",
    )
    constant_columns: list[str] = Field(
        default_factory=list,
        description="Column names where all non-null values are identical",
    )
    schema_issues: list[str] = Field(
        default_factory=list,
        description="Structured schema issue descriptions (e.g. unnamed columns)",
    )

    @field_validator("source_id")
    @classmethod
    def _validate_source_id_field(cls, v: str) -> str:
        return _validate_source_id(v)

    @field_validator("missing_value_rates")
    @classmethod
    def _validate_missing_value_rates(cls, v: dict) -> dict:
        for col, rate in v.items():
            if not isinstance(col, str):
                raise ValueError("missing_value_rates keys must be str column names")
            if not isinstance(rate, float) or not (0.0 <= rate <= 1.0):
                raise ValueError(
                    f"missing_value_rates[{col!r}] must be a float in [0.0, 1.0], got {rate!r}"
                )
        return v


# ---------------------------------------------------------------------------
# Task 5B-1 — TextEvidenceCandidate
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Locked identity values per semantic category for TextEvidenceCandidate.
# These are fixed by spec and enforced by the model_validator below.
# ---------------------------------------------------------------------------

#: Categories that TextEvidenceCandidate accepts.
_TEXT_CANDIDATE_CATEGORIES: frozenset[SemanticContextCategory] = frozenset({
    SemanticContextCategory.industry_context,
    SemanticContextCategory.strategy_profile,
    SemanticContextCategory.user_assumption,
})

#: Permitted machine-level role keys for TextEvidenceCandidate.relevant_roles.
_PERMITTED_ROLE_KEYS: frozenset[str] = frozenset({
    "executive",
    "data_analyst",
    "data_engineer",
    "sales_marketing",
    "project_manager",
})

#: Locked evidence_type per category.
_LOCKED_EVIDENCE_TYPE: dict[SemanticContextCategory, str] = {
    SemanticContextCategory.industry_context: "industry_context_statement",
    SemanticContextCategory.strategy_profile: "strategy_priority_statement",
    SemanticContextCategory.user_assumption: "user_assumption_statement",
}

#: Locked normalized_claim_key per category.
_LOCKED_CLAIM_KEY: dict[SemanticContextCategory, str] = {
    SemanticContextCategory.industry_context: "context.industry_context.paragraph",
    SemanticContextCategory.strategy_profile: "context.strategy_profile.statement",
    SemanticContextCategory.user_assumption: "context.user_assumption.statement",
}

#: The only permitted extraction policy version.
_LOCKED_EXTRACTION_POLICY: str = "exact_source_statement_v1"


class TextEvidenceCandidate(ContractModel):
    """A bounded, deterministic evidence candidate derived from exact user-provided text.

    Represents evidence grounded in industry context, strategy profile statements,
    or user assumptions.  The semantic category determines and locks the
    evidence_type, normalized_claim_key, and canonical_rule_parameters values.

    This model intentionally has NO evidence_id or identity_digest field.
    Those are minted exclusively by app/evidence_builder.py when converting
    this candidate into an EvidenceObject.

    The later evidence builder sets finding = exact_excerpt and
    supporting_evidence = exact_excerpt.

    Supported semantic_context_category values:
      - industry_context   (pasted_text / txt / markdown + TextSourceLocator)
      - strategy_profile   (form_input + UserContextLocator)
      - user_assumption    (form_input + UserContextLocator)

    Rejected categories:
      - business_question, decision_goal, data_source, internal_report

    relevant_roles must contain only the following machine keys (no display names):
      executive, data_analyst, data_engineer, sales_marketing, project_manager
    """

    source_id: str = Field(..., description="source_id of the originating source")
    source_format: SourceFormat = Field(
        ..., description="Physical format of the originating source"
    )
    source_locator: SourceLocator = Field(
        ..., description="Typed locator pointing to the evidence span within the source"
    )
    semantic_context_category: SemanticContextCategory = Field(
        ..., description="Semantic category; must be industry_context, strategy_profile, or user_assumption"
    )
    evidence_type: str = Field(
        ..., description="Locked evidence type for this category"
    )
    canonical_rule_parameters: dict[str, Any] = Field(
        ..., description="Locked extraction-policy parameters for this category"
    )
    normalized_claim_key: str = Field(
        ..., description="Locked claim key for this category"
    )
    exact_excerpt: str = Field(
        ..., description="Verbatim text excerpt (preserved without rewriting)"
    )
    confidence: Literal["low", "medium", "high"] = Field(
        ..., description="Confidence level for this evidence"
    )
    limitations: list[str] = Field(
        ..., description="Non-empty list of unique, non-blank limitation statements"
    )
    relevant_roles: list[str] = Field(
        ..., description="Non-empty unique list of permitted machine role keys"
    )
    decision_relevance: str = Field(
        ..., description="How this evidence impacts the business decision (non-blank)"
    )

    # ---- field validators ----

    @field_validator("source_id")
    @classmethod
    def source_id_format(cls, v: str) -> str:
        return _validate_source_id(v)

    @field_validator("exact_excerpt")
    @classmethod
    def exact_excerpt_non_blank(cls, v: str) -> str:
        """exact_excerpt must not be blank or whitespace-only."""
        if not v or not v.strip():
            raise ValueError("exact_excerpt must not be blank or whitespace-only")
        return v

    @field_validator("limitations")
    @classmethod
    def limitations_valid(cls, v: list[str]) -> list[str]:
        """limitations must be non-empty; no blank values; all unique."""
        if not v:
            raise ValueError("limitations must contain at least one value")
        blank = [x for x in v if not x or not x.strip()]
        if blank:
            raise ValueError("limitations must not contain blank values")
        if len(v) != len(set(v)):
            raise ValueError("limitations must be unique; duplicate values are not allowed")
        return v

    @field_validator("relevant_roles")
    @classmethod
    def relevant_roles_valid(cls, v: list[str]) -> list[str]:
        """relevant_roles must be non-empty, contain only permitted machine keys, no duplicates."""
        if not v:
            raise ValueError("relevant_roles must not be empty")
        unknown = [r for r in v if r not in _PERMITTED_ROLE_KEYS]
        if unknown:
            raise ValueError(
                f"relevant_roles contains unknown role keys: {unknown!r}. "
                f"Permitted keys: {sorted(_PERMITTED_ROLE_KEYS)!r}"
            )
        if len(v) != len(set(v)):
            raise ValueError("relevant_roles must not contain duplicate role keys")
        return v

    @field_validator("decision_relevance")
    @classmethod
    def decision_relevance_non_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("decision_relevance must not be blank")
        return v

    # ---- cross-field model validators ----

    @model_validator(mode="after")
    def category_allowed(self) -> "TextEvidenceCandidate":
        """semantic_context_category must be one of the three permitted categories."""
        if self.semantic_context_category not in _TEXT_CANDIDATE_CATEGORIES:
            raise ValueError(
                f"TextEvidenceCandidate does not accept "
                f"semantic_context_category={self.semantic_context_category.value!r}. "
                f"Permitted: {[c.value for c in sorted(_TEXT_CANDIDATE_CATEGORIES, key=lambda c: c.value)]!r}"
            )
        return self

    @model_validator(mode="after")
    def locked_identity_values(self) -> "TextEvidenceCandidate":
        """evidence_type, normalized_claim_key, and canonical_rule_parameters
        must match the locked values for the given semantic_context_category.
        """
        cat = self.semantic_context_category
        if cat not in _TEXT_CANDIDATE_CATEGORIES:
            # category_allowed validator will surface the primary error.
            return self

        # Validate evidence_type
        expected_et = _LOCKED_EVIDENCE_TYPE[cat]
        if self.evidence_type != expected_et:
            raise ValueError(
                f"For semantic_context_category={cat.value!r}, "
                f"evidence_type must be {expected_et!r}, got {self.evidence_type!r}"
            )

        # Validate normalized_claim_key
        expected_ck = _LOCKED_CLAIM_KEY[cat]
        if self.normalized_claim_key != expected_ck:
            raise ValueError(
                f"For semantic_context_category={cat.value!r}, "
                f"normalized_claim_key must be {expected_ck!r}, "
                f"got {self.normalized_claim_key!r}"
            )

        # Validate canonical_rule_parameters
        expected_params = {
            "extraction_policy": _LOCKED_EXTRACTION_POLICY,
            "semantic_context_category": cat.value,
        }
        if self.canonical_rule_parameters != expected_params:
            raise ValueError(
                f"For semantic_context_category={cat.value!r}, "
                f"canonical_rule_parameters must be exactly "
                f"{expected_params!r}, got {self.canonical_rule_parameters!r}"
            )

        return self

    @model_validator(mode="after")
    def format_and_locator_compatible(self) -> "TextEvidenceCandidate":
        """source_format and source_locator must be compatible.

        industry_context: pasted_text, txt, or markdown + TextSourceLocator
        strategy_profile: form_input + UserContextLocator
        user_assumption:  form_input + UserContextLocator
        """
        cat = self.semantic_context_category
        fmt = self.source_format
        loc = self.source_locator

        if cat == SemanticContextCategory.industry_context:
            allowed_formats = {SourceFormat.pasted_text, SourceFormat.txt, SourceFormat.markdown}
            if fmt not in allowed_formats:
                raise ValueError(
                    f"industry_context requires source_format in "
                    f"{[f.value for f in sorted(allowed_formats, key=lambda f: f.value)]!r}, "
                    f"got {fmt.value!r}"
                )
            if not isinstance(loc, TextSourceLocator):
                raise ValueError(
                    f"industry_context requires TextSourceLocator, "
                    f"got {type(loc).__name__}"
                )
        elif cat in (SemanticContextCategory.strategy_profile, SemanticContextCategory.user_assumption):
            if fmt != SourceFormat.form_input:
                raise ValueError(
                    f"{cat.value!r} requires source_format='form_input', got {fmt.value!r}"
                )
            if not isinstance(loc, UserContextLocator):
                raise ValueError(
                    f"{cat.value!r} requires UserContextLocator, "
                    f"got {type(loc).__name__}"
                )
            # context_category on the locator must match semantic_context_category
            if loc.context_category != cat:
                raise ValueError(
                    f"UserContextLocator.context_category must equal "
                    f"semantic_context_category={cat.value!r}, "
                    f"got context_category={loc.context_category.value!r}"
                )

        return self


# ---------------------------------------------------------------------------
# Task 6A-1 — RoleKey, GroundedFinding, RoleView
# ---------------------------------------------------------------------------


def _validate_str_list_no_blank_or_dup(values: list[str], field: str) -> None:
    """Shared helper: reject blank strings and duplicates in a string list field."""
    blank = [v for v in values if not v or not v.strip()]
    if blank:
        raise ValueError(f"{field} must not contain blank strings")
    if len(values) != len(set(values)):
        raise ValueError(f"{field} must not contain duplicate strings")


class RoleKey(str, Enum):
    """Machine keys for the five V1 roles.

    Values must exactly match the keys in config/role_policy.json.
    No display names are attached here — display names are in the policy file.
    """

    executive = "executive"
    data_analyst = "data_analyst"
    data_engineer = "data_engineer"
    sales_marketing = "sales_marketing"
    project_manager = "project_manager"


class GroundedFinding(ContractModel):
    """One claim produced by a role view, grounded in cited Evidence Objects.

    Every claim must be backed by at least one EvidenceReference.
    The later role engine will validate that each referenced evidence_id:
      - exists in the current trajectory
      - has status='active'
      - was included in the evidence set exposed to the provider call

    This schema validates format only, not registry existence.
    """

    claim: str = Field(..., description="The role-specific claim or observation (non-blank)")
    evidence_references: list[EvidenceReference] = Field(
        ..., description="Non-empty list of Evidence Objects that ground this claim"
    )
    confidence: Literal["low", "medium", "high"] = Field(
        ..., description="Confidence level for this claim"
    )

    @field_validator("claim")
    @classmethod
    def claim_non_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("claim must not be blank or whitespace-only")
        return v

    @field_validator("evidence_references")
    @classmethod
    def evidence_references_non_empty_unique(
        cls, v: list[EvidenceReference]
    ) -> list[EvidenceReference]:
        """evidence_references must be non-empty and evidence_id values must be unique."""
        if not v:
            raise ValueError("evidence_references must not be empty")
        ids = [ref.evidence_id for ref in v]
        if len(ids) != len(set(ids)):
            raise ValueError(
                "evidence_references must not contain duplicate evidence_id values "
                "within a single GroundedFinding"
            )
        return v


class RoleView(ContractModel):
    """The output produced by one role provider for a given decision context.

    key_findings must be non-empty: no evidence means no RoleView.
    The later role engine returns a typed failure instead of creating a
    citation-free RoleView.

    Duplicate evidence IDs across different GroundedFinding records are allowed
    because one Evidence Object may legitimately support multiple claims.

    next_action and dependency are optional but must not be blank when supplied.
    """

    role_key: RoleKey = Field(..., description="Machine key of the role producing this view")
    role_concern: str = Field(
        ..., description="The primary concern this role brings to the decision (non-blank)"
    )
    key_findings: list[GroundedFinding] = Field(
        ..., description="Non-empty list of grounded claims produced by this role"
    )
    risks_or_assumptions: list[str] = Field(
        default_factory=list,
        description="Risks or unverified assumptions identified; no blank or duplicate strings",
    )
    missing_information: list[str] = Field(
        default_factory=list,
        description="Information gaps that limit this role's analysis; no blank or duplicate strings",
    )
    next_action: str | None = Field(
        None, description="Recommended next action, when applicable (non-blank if supplied)"
    )
    dependency: str | None = Field(
        None, description="Blocking dependency, when applicable (non-blank if supplied)"
    )
    human_review_required: bool = Field(
        ..., description="Whether human review is required before acting on this view"
    )

    @field_validator("role_concern")
    @classmethod
    def role_concern_non_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("role_concern must not be blank or whitespace-only")
        return v

    @field_validator("key_findings")
    @classmethod
    def key_findings_non_empty(cls, v: list[GroundedFinding]) -> list[GroundedFinding]:
        if not v:
            raise ValueError(
                "key_findings must not be empty; no evidence means no RoleView"
            )
        return v

    @field_validator("risks_or_assumptions")
    @classmethod
    def risks_no_blank_or_duplicate(cls, v: list[str]) -> list[str]:
        _validate_str_list_no_blank_or_dup(v, "risks_or_assumptions")
        return v

    @field_validator("missing_information")
    @classmethod
    def missing_info_no_blank_or_duplicate(cls, v: list[str]) -> list[str]:
        _validate_str_list_no_blank_or_dup(v, "missing_information")
        return v

    @field_validator("next_action")
    @classmethod
    def next_action_non_blank(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            raise ValueError("next_action must not be blank when supplied")
        return v

    @field_validator("dependency")
    @classmethod
    def dependency_non_blank(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            raise ValueError("dependency must not be blank when supplied")
        return v


# ---------------------------------------------------------------------------
# Task 7A — RiskCode, RiskSeverity, RiskFinding, RiskReviewResult
# ---------------------------------------------------------------------------

_ROLE_EXECUTION_ORDER: list[RoleKey] = [
    RoleKey.executive,
    RoleKey.data_analyst,
    RoleKey.data_engineer,
    RoleKey.sales_marketing,
    RoleKey.project_manager,
]


class RiskCode(str, Enum):
    """Machine keys for deterministic epistemic and workflow risk codes.

    Task 7A produces only these codes.  Semantic claim review (causation,
    ROI/budget, natural-language boundary violations) belongs to Task 7B.
    """

    external_context_only       = "external_context_only"
    assumption_only             = "assumption_only"
    stated_priority_only        = "stated_priority_only"
    assumption_not_declared     = "assumption_not_declared"
    action_without_internal_evidence = "action_without_internal_evidence"
    human_review_bypass         = "human_review_bypass"
    insufficient_evidence       = "insufficient_evidence"
    role_generation_failure     = "role_generation_failure"


class RiskSeverity(str, Enum):
    """Severity levels for RiskFinding records."""

    low      = "low"
    medium   = "medium"
    high     = "high"
    critical = "critical"


class RiskFinding(ContractModel):
    """One deterministic risk finding produced by the Task 7A risk checker.

    Does not contain free-form model reasoning or provider metadata.
    """

    risk_code: RiskCode = Field(..., description="Machine key identifying the risk type")
    severity: RiskSeverity = Field(..., description="Severity level of this risk")
    role_key: RoleKey = Field(..., description="Role for which this finding was produced")
    claim_index: int | None = Field(
        None,
        description="Index into RoleView.key_findings (0-based); None for role-level findings",
    )
    evidence_ids: list[str] = Field(
        default_factory=list,
        description="evidence_id values involved in this risk finding; no duplicates",
    )
    message: str = Field(..., description="Human-readable description of the risk (non-blank)")
    required_action: str = Field(
        ..., description="What must be done to resolve or mitigate this risk (non-blank)"
    )
    blocks_downstream: bool = Field(
        ..., description="Whether this risk blocks downstream pipeline execution"
    )
    requires_human_review: bool = Field(
        ..., description="Whether this risk requires a human reviewer to proceed"
    )

    @field_validator("claim_index")
    @classmethod
    def claim_index_non_negative(cls, v: int | None) -> int | None:
        if v is not None and v < 0:
            raise ValueError("claim_index must be >= 0 when supplied")
        return v

    @field_validator("evidence_ids")
    @classmethod
    def evidence_ids_valid_and_unique(cls, v: list[str]) -> list[str]:
        """evidence_ids must be valid EvidenceReference-style IDs with no duplicates."""
        for eid in v:
            if not _EVIDENCE_ID_RE.match(eid):
                raise ValueError(
                    f"evidence_ids contains an invalid evidence_id: {eid!r}"
                )
        if len(v) != len(set(v)):
            raise ValueError("evidence_ids must not contain duplicate evidence_id values")
        return v

    @field_validator("message")
    @classmethod
    def message_non_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("message must not be blank")
        return v

    @field_validator("required_action")
    @classmethod
    def required_action_non_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("required_action must not be blank")
        return v


class RiskReviewResult(ContractModel):
    """The complete output of one check_role_risks() call.

    reviewed_role_keys must contain exactly the five RoleKey values in fixed
    execution order.  has_blocking_risks and human_review_required are derived
    from the findings list and must equal the corresponding aggregate.
    """

    findings: list[RiskFinding] = Field(
        default_factory=list,
        description="All RiskFinding records produced for this run",
    )
    reviewed_role_keys: list[RoleKey] = Field(
        ...,
        description="The five RoleKey values in fixed execution order",
    )
    has_blocking_risks: bool = Field(
        ..., description="True iff any finding has blocks_downstream=True"
    )
    human_review_required: bool = Field(
        ..., description="True iff any finding has requires_human_review=True"
    )

    @field_validator("reviewed_role_keys")
    @classmethod
    def reviewed_role_keys_fixed_order(cls, v: list[RoleKey]) -> list[RoleKey]:
        """Must contain exactly the five RoleKey values in the fixed execution order."""
        if v != _ROLE_EXECUTION_ORDER:
            raise ValueError(
                f"reviewed_role_keys must be exactly {[k.value for k in _ROLE_EXECUTION_ORDER]!r} "
                f"in that order, got {[k.value for k in v]!r}"
            )
        return v

    @model_validator(mode="after")
    def derived_flags_consistent(self) -> "RiskReviewResult":
        """has_blocking_risks and human_review_required must match the findings."""
        expected_blocking = any(f.blocks_downstream for f in self.findings)
        if self.has_blocking_risks != expected_blocking:
            raise ValueError(
                f"has_blocking_risks={self.has_blocking_risks!r} does not match "
                f"any(finding.blocks_downstream) which is {expected_blocking!r}"
            )
        expected_review = any(f.requires_human_review for f in self.findings)
        if self.human_review_required != expected_review:
            raise ValueError(
                f"human_review_required={self.human_review_required!r} does not match "
                f"any(finding.requires_human_review) which is {expected_review!r}"
            )
        return self


# ---------------------------------------------------------------------------
# Task 7B-1 — probabilistic semantic-risk review contracts
# ---------------------------------------------------------------------------


class SemanticRiskCode(str, Enum):
    """Machine keys for provider-generated semantic review candidates."""

    citation_claim_mismatch = "citation_claim_mismatch"
    unsupported_company_specific_claim = "unsupported_company_specific_claim"
    causation_overreach = "causation_overreach"
    unsupported_roi_or_budget = "unsupported_roi_or_budget"
    role_boundary_violation = "role_boundary_violation"
    unsupported_completion_or_validation_claim = (
        "unsupported_completion_or_validation_claim"
    )


class SemanticReviewDisposition(str, Enum):
    """Human-review disposition proposed by the semantic reviewer."""

    needs_human_review = "needs_human_review"
    likely_supported = "likely_supported"
    reviewer_uncertain = "reviewer_uncertain"


class SemanticRiskCandidate(ContractModel):
    """One probabilistic semantic-review candidate, not a RiskFinding."""

    risk_code: SemanticRiskCode
    role_key: RoleKey
    claim_index: int = Field(..., ge=0)
    evidence_ids: list[str]
    explanation: str
    review_question: str
    confidence: Literal["low", "medium", "high"]
    disposition: SemanticReviewDisposition

    @field_validator("evidence_ids")
    @classmethod
    def evidence_ids_non_empty_valid_unique(cls, v: list[str]) -> list[str]:
        """Require at least one valid, unique evidence identifier."""
        if not v:
            raise ValueError("evidence_ids must not be empty")
        for evidence_id in v:
            _validate_evidence_id(evidence_id)
        if len(v) != len(set(v)):
            raise ValueError(
                "evidence_ids must not contain duplicate evidence_id values"
            )
        return v

    @field_validator("explanation")
    @classmethod
    def explanation_non_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("explanation must not be blank")
        return v

    @field_validator("review_question")
    @classmethod
    def review_question_non_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("review_question must not be blank")
        return v


class SemanticRiskReviewResult(ContractModel):
    """Validated output of one probabilistic semantic-risk review."""

    candidates: list[SemanticRiskCandidate] = Field(default_factory=list)
    reviewed_role_keys: list[RoleKey]
    reviewer_model: str | None
    human_review_required: bool

    @field_validator("reviewed_role_keys")
    @classmethod
    def reviewed_role_keys_unique_fixed_order(
        cls,
        v: list[RoleKey],
    ) -> list[RoleKey]:
        """Require a duplicate-free subsequence of the fixed role order."""
        if len(v) != len(set(v)):
            raise ValueError(
                "reviewed_role_keys must not contain duplicate role keys"
            )
        positions = {role_key: index for index, role_key in enumerate(_ROLE_EXECUTION_ORDER)}
        if v != sorted(v, key=positions.__getitem__):
            raise ValueError(
                "reviewed_role_keys must preserve the fixed role execution order"
            )
        return v

    @model_validator(mode="after")
    def semantic_review_consistency(self) -> "SemanticRiskReviewResult":
        """Validate candidate roles and the derived human-review flag."""
        reviewed = set(self.reviewed_role_keys)
        unreviewed_candidate_roles = {
            candidate.role_key
            for candidate in self.candidates
            if candidate.role_key not in reviewed
        }
        if unreviewed_candidate_roles:
            raise ValueError(
                "SemanticRiskCandidate role_key values must be present in "
                "reviewed_role_keys"
            )

        expected_review = any(
            candidate.disposition != SemanticReviewDisposition.likely_supported
            for candidate in self.candidates
        )
        if self.human_review_required != expected_review:
            raise ValueError(
                f"human_review_required={self.human_review_required!r} does not "
                "match whether any candidate disposition requires review "
                f"({expected_review!r})"
            )
        return self


# ---------------------------------------------------------------------------
# Task 8A — deterministic Workflow Planner contracts
# ---------------------------------------------------------------------------

_WORKFLOW_STEP_ID_RE = re.compile(r"^wf-[0-9]{3}$")


class WorkflowStepKind(str, Enum):
    """Machine keys for the three deterministic workflow step kinds."""

    deterministic_risk_resolution = "deterministic_risk_resolution"
    semantic_review_gate = "semantic_review_gate"
    role_action = "role_action"


class WorkflowStepStatus(str, Enum):
    """Current review readiness of a generated workflow step."""

    ready = "ready"
    blocked = "blocked"
    pending_human_review = "pending_human_review"


class WorkflowPlanStatus(str, Enum):
    """Derived aggregate status for a deterministic workflow plan."""

    blocked = "blocked"
    ready_for_human_review = "ready_for_human_review"
    no_actionable_steps = "no_actionable_steps"


class WorkflowStep(ContractModel):
    """One immutable, evidence-grounded step in a deterministic workflow."""

    step_id: str
    sequence: int = Field(..., ge=1)
    step_kind: WorkflowStepKind
    owner_role: RoleKey
    action: str
    supporting_evidence_ids: list[str]
    dependency_step_ids: list[str]
    dependency_notes: list[str]
    missing_information: list[str]
    deterministic_risk_codes: list[RiskCode]
    semantic_risk_codes: list[SemanticRiskCode]
    review_questions: list[str]
    status: WorkflowStepStatus
    blocks_downstream: bool
    human_review_required: bool

    @field_validator("step_id")
    @classmethod
    def step_id_format(cls, value: str) -> str:
        """Require the stable ``wf-NNN`` step identifier format."""
        if not _WORKFLOW_STEP_ID_RE.fullmatch(value):
            raise ValueError("step_id must match wf-[0-9]{3}")
        return value

    @field_validator("action")
    @classmethod
    def action_non_blank(cls, value: str) -> str:
        """Reject blank executable action text."""
        if not value or not value.strip():
            raise ValueError("action must not be blank")
        return value

    @field_validator("supporting_evidence_ids")
    @classmethod
    def supporting_evidence_ids_valid_unique(
        cls,
        values: list[str],
    ) -> list[str]:
        """Require valid, duplicate-free Evidence Object identifiers."""
        for evidence_id in values:
            _validate_evidence_id(evidence_id)
        if len(values) != len(set(values)):
            raise ValueError(
                "supporting_evidence_ids must not contain duplicates"
            )
        return values

    @field_validator("dependency_step_ids")
    @classmethod
    def dependency_step_ids_valid_unique(
        cls,
        values: list[str],
    ) -> list[str]:
        """Require valid, duplicate-free workflow dependency identifiers."""
        if any(not _WORKFLOW_STEP_ID_RE.fullmatch(value) for value in values):
            raise ValueError(
                "dependency_step_ids values must match wf-[0-9]{3}"
            )
        if len(values) != len(set(values)):
            raise ValueError(
                "dependency_step_ids must not contain duplicates"
            )
        return values

    @field_validator(
        "dependency_notes",
        "missing_information",
        "review_questions",
    )
    @classmethod
    def string_lists_non_blank_unique(
        cls,
        values: list[str],
        info: Any,
    ) -> list[str]:
        """Reject blank or duplicate free-text list values."""
        _validate_str_list_no_blank_or_dup(values, info.field_name)
        return values

    @field_validator("deterministic_risk_codes", "semantic_risk_codes")
    @classmethod
    def risk_code_lists_unique(
        cls,
        values: list[Any],
        info: Any,
    ) -> list[Any]:
        """Reject repeated typed risk codes within one step."""
        if len(values) != len(set(values)):
            raise ValueError(f"{info.field_name} must not contain duplicates")
        return values

    @model_validator(mode="after")
    def step_kind_contract(self) -> "WorkflowStep":
        """Enforce self-dependency and step-kind cross-field invariants."""
        if self.step_id in self.dependency_step_ids:
            raise ValueError("a workflow step cannot depend on itself")

        if self.step_kind == WorkflowStepKind.semantic_review_gate:
            if not self.semantic_risk_codes:
                raise ValueError(
                    "semantic_review_gate requires semantic_risk_codes"
                )
            if not self.review_questions:
                raise ValueError(
                    "semantic_review_gate requires review_questions"
                )
            if self.deterministic_risk_codes:
                raise ValueError(
                    "semantic_review_gate requires empty "
                    "deterministic_risk_codes"
                )
            if self.status != WorkflowStepStatus.pending_human_review:
                raise ValueError(
                    "semantic_review_gate status must be pending_human_review"
                )
            if self.blocks_downstream:
                raise ValueError(
                    "semantic_review_gate cannot block downstream steps"
                )
            if not self.human_review_required:
                raise ValueError(
                    "semantic_review_gate requires human review"
                )

        if (
            self.step_kind
            == WorkflowStepKind.deterministic_risk_resolution
        ):
            if not self.deterministic_risk_codes:
                raise ValueError(
                    "deterministic_risk_resolution requires "
                    "deterministic_risk_codes"
                )
            if self.semantic_risk_codes or self.review_questions:
                raise ValueError(
                    "deterministic_risk_resolution requires empty semantic "
                    "risk codes and review questions"
                )
        return self


class WorkflowPlan(ContractModel):
    """Complete deterministic V1 workflow plan."""

    steps: list[WorkflowStep]
    plan_status: WorkflowPlanStatus
    included_role_keys: list[RoleKey]
    blocking_step_ids: list[str]
    human_review_required: bool
    planning_method: Literal["deterministic_v1"]

    @field_validator("included_role_keys")
    @classmethod
    def included_roles_fixed_order_unique(
        cls,
        values: list[RoleKey],
    ) -> list[RoleKey]:
        """Require a unique subsequence of the canonical role order."""
        if len(values) != len(set(values)):
            raise ValueError("included_role_keys must not contain duplicates")
        expected = [
            role_key
            for role_key in _ROLE_EXECUTION_ORDER
            if role_key in set(values)
        ]
        if values != expected:
            raise ValueError(
                "included_role_keys must preserve fixed role execution order"
            )
        return values

    @field_validator("blocking_step_ids")
    @classmethod
    def blocking_ids_valid_unique(cls, values: list[str]) -> list[str]:
        """Require valid, duplicate-free blocking step identifiers."""
        if any(not _WORKFLOW_STEP_ID_RE.fullmatch(value) for value in values):
            raise ValueError(
                "blocking_step_ids values must match wf-[0-9]{3}"
            )
        if len(values) != len(set(values)):
            raise ValueError("blocking_step_ids must not contain duplicates")
        return values

    @model_validator(mode="after")
    def plan_consistency(self) -> "WorkflowPlan":
        """Validate sequence, dependencies, blockers, and derived flags."""
        step_ids = [step.step_id for step in self.steps]
        if len(step_ids) != len(set(step_ids)):
            raise ValueError("WorkflowStep IDs must be unique")

        expected_sequences = list(range(1, len(self.steps) + 1))
        if [step.sequence for step in self.steps] != expected_sequences:
            raise ValueError(
                "WorkflowStep sequence values must be contiguous from 1"
            )
        expected_ids = [
            f"wf-{sequence:03d}" for sequence in expected_sequences
        ]
        if step_ids != expected_ids:
            raise ValueError(
                "WorkflowStep IDs must correspond exactly to sequence values"
            )

        sequence_by_id = {
            step.step_id: step.sequence for step in self.steps
        }
        for step in self.steps:
            for dependency_id in step.dependency_step_ids:
                dependency_sequence = sequence_by_id.get(dependency_id)
                if dependency_sequence is None:
                    raise ValueError(
                        "dependency_step_ids must reference existing steps"
                    )
                if dependency_sequence >= step.sequence:
                    raise ValueError(
                        "dependencies must reference earlier workflow steps"
                    )

        expected_blocking_ids = [
            step.step_id for step in self.steps if step.blocks_downstream
        ]
        if self.blocking_step_ids != expected_blocking_ids:
            raise ValueError(
                "blocking_step_ids must exactly match blocking workflow steps"
            )

        if not self.steps:
            expected_status = WorkflowPlanStatus.no_actionable_steps
        elif self.blocking_step_ids:
            expected_status = WorkflowPlanStatus.blocked
        else:
            expected_status = WorkflowPlanStatus.ready_for_human_review
        if self.plan_status != expected_status:
            raise ValueError(
                "plan_status is inconsistent with steps and blocking_step_ids"
            )
        if not self.human_review_required:
            raise ValueError(
                "WorkflowPlan.human_review_required must always be true"
            )
        return self


# ---------------------------------------------------------------------------
# Task 9A — deterministic simulated Human Review Ledger contracts
# ---------------------------------------------------------------------------


class HumanReviewDecision(str, Enum):
    """Simulated memo-review decision for one immutable workflow step."""

    accept = "accept"
    reject = "reject"
    revise = "revise"


class HumanReviewSessionStatus(str, Enum):
    """Completion state of a simulated human-review session."""

    pending = "pending"
    complete = "complete"


class HumanReviewStepInput(ContractModel):
    """One caller-supplied simulated human decision."""

    decision: HumanReviewDecision
    reviewer_note: str | None = None
    revised_action: str | None = None

    @field_validator("reviewer_note", "revised_action")
    @classmethod
    def optional_text_non_blank(
        cls,
        value: str | None,
        info: Any,
    ) -> str | None:
        """Reject blank text whenever an optional text field is supplied."""
        if value is not None and (not value or not value.strip()):
            raise ValueError(f"{info.field_name} must not be blank")
        return value

    @model_validator(mode="after")
    def decision_fields_are_consistent(self) -> "HumanReviewStepInput":
        """Enforce accept, reject, and revise input combinations."""
        if self.decision == HumanReviewDecision.accept:
            if self.revised_action is not None:
                raise ValueError("accept requires revised_action=None")
        elif self.decision == HumanReviewDecision.reject:
            if self.reviewer_note is None:
                raise ValueError("reject requires reviewer_note")
            if self.revised_action is not None:
                raise ValueError("reject requires revised_action=None")
        else:
            if self.reviewer_note is None:
                raise ValueError("revise requires reviewer_note")
            if self.revised_action is None:
                raise ValueError("revise requires revised_action")
        return self


class HumanReviewedStep(ContractModel):
    """Immutable snapshot of one reviewed WorkflowStep and its decision."""

    step_id: str
    sequence: int = Field(..., ge=1)
    step_kind: WorkflowStepKind
    owner_role: RoleKey
    original_action: str
    final_action: str | None
    decision: HumanReviewDecision
    reviewer_note: str | None
    supporting_evidence_ids: list[str]
    deterministic_risk_codes: list[RiskCode]
    semantic_risk_codes: list[SemanticRiskCode]
    original_status: WorkflowStepStatus
    blocks_downstream: bool
    revision_requires_revalidation: bool

    @field_validator("step_id")
    @classmethod
    def step_id_format(cls, value: str) -> str:
        """Require the existing stable WorkflowStep identifier format."""
        if not _WORKFLOW_STEP_ID_RE.fullmatch(value):
            raise ValueError("step_id must match wf-[0-9]{3}")
        return value

    @field_validator("original_action")
    @classmethod
    def original_action_non_blank(cls, value: str) -> str:
        """Require original action text."""
        if not value or not value.strip():
            raise ValueError("original_action must not be blank")
        return value

    @field_validator("final_action", "reviewer_note")
    @classmethod
    def optional_review_text_non_blank(
        cls,
        value: str | None,
        info: Any,
    ) -> str | None:
        """Reject blank final actions and notes when supplied."""
        if value is not None and (not value or not value.strip()):
            raise ValueError(f"{info.field_name} must not be blank")
        return value

    @field_validator("supporting_evidence_ids")
    @classmethod
    def evidence_ids_valid_unique(cls, values: list[str]) -> list[str]:
        """Require valid, duplicate-free Evidence Object identifiers."""
        for evidence_id in values:
            _validate_evidence_id(evidence_id)
        if len(values) != len(set(values)):
            raise ValueError(
                "supporting_evidence_ids must not contain duplicates"
            )
        return values

    @field_validator("deterministic_risk_codes", "semantic_risk_codes")
    @classmethod
    def review_risk_codes_unique(
        cls,
        values: list[Any],
        info: Any,
    ) -> list[Any]:
        """Reject duplicate risk-code lineage."""
        if len(values) != len(set(values)):
            raise ValueError(f"{info.field_name} must not contain duplicates")
        return values

    @model_validator(mode="after")
    def decision_snapshot_is_consistent(self) -> "HumanReviewedStep":
        """Enforce decision output and semantic-gate review rules."""
        if self.decision == HumanReviewDecision.accept:
            if self.final_action != self.original_action:
                raise ValueError(
                    "accept requires final_action to equal original_action"
                )
            if self.revision_requires_revalidation:
                raise ValueError(
                    "accept cannot require revision revalidation"
                )
        elif self.decision == HumanReviewDecision.reject:
            if self.final_action is not None:
                raise ValueError("reject requires final_action=None")
            if self.reviewer_note is None:
                raise ValueError("reject requires reviewer_note")
            if self.revision_requires_revalidation:
                raise ValueError(
                    "reject cannot require revision revalidation"
                )
        else:
            if self.final_action is None:
                raise ValueError("revise requires final_action")
            if self.final_action == self.original_action:
                raise ValueError(
                    "revise requires final_action to differ from original_action"
                )
            if self.reviewer_note is None:
                raise ValueError("revise requires reviewer_note")
            if not self.revision_requires_revalidation:
                raise ValueError(
                    "revise requires revision_requires_revalidation=true"
                )

        if self.step_kind == WorkflowStepKind.semantic_review_gate:
            if self.decision == HumanReviewDecision.revise:
                raise ValueError("semantic_review_gate cannot be revised")
            if self.reviewer_note is None:
                raise ValueError(
                    "semantic_review_gate decisions require reviewer_note"
                )
        return self


class HumanReviewSession(ContractModel):
    """Deterministic simulated review ledger bound to one WorkflowPlan."""

    plan_digest: str
    plan_step_ids: list[str]
    reviewed_steps: list[HumanReviewedStep]
    pending_step_ids: list[str]
    accepted_step_ids: list[str]
    rejected_step_ids: list[str]
    revised_step_ids: list[str]
    session_status: HumanReviewSessionStatus
    no_action_acknowledged: bool = Field(strict=True)
    overall_note: str | None
    human_review_complete: bool
    review_method: Literal["simulated_human_review_v1"]

    @field_validator("plan_digest")
    @classmethod
    def plan_digest_format(cls, value: str) -> str:
        """Require a full lowercase SHA-256 digest."""
        if not _DIGEST_RE.fullmatch(value):
            raise ValueError(
                "plan_digest must be 64 lowercase hexadecimal characters"
            )
        return value

    @field_validator(
        "plan_step_ids",
        "pending_step_ids",
        "accepted_step_ids",
        "rejected_step_ids",
        "revised_step_ids",
    )
    @classmethod
    def step_id_lists_valid_unique(
        cls,
        values: list[str],
        info: Any,
    ) -> list[str]:
        """Require valid, duplicate-free workflow IDs in every ID list."""
        if any(not _WORKFLOW_STEP_ID_RE.fullmatch(value) for value in values):
            raise ValueError(
                f"{info.field_name} values must match wf-[0-9]{{3}}"
            )
        if len(values) != len(set(values)):
            raise ValueError(f"{info.field_name} must not contain duplicates")
        return values

    @field_validator("overall_note")
    @classmethod
    def overall_note_non_blank(cls, value: str | None) -> str | None:
        """Reject a blank overall note when supplied."""
        if value is not None and (not value or not value.strip()):
            raise ValueError("overall_note must not be blank")
        return value

    @field_validator("reviewed_steps")
    @classmethod
    def reviewed_steps_ordered_unique(
        cls,
        values: list[HumanReviewedStep],
    ) -> list[HumanReviewedStep]:
        """Require unique reviewed steps in strictly increasing sequence."""
        step_ids = [step.step_id for step in values]
        if len(step_ids) != len(set(step_ids)):
            raise ValueError("reviewed step IDs must be unique")
        sequences = [step.sequence for step in values]
        if sequences != sorted(sequences) or len(sequences) != len(set(sequences)):
            raise ValueError(
                "reviewed_steps must be ordered by unique sequence values"
            )
        return values

    @model_validator(mode="after")
    def session_partition_is_consistent(self) -> "HumanReviewSession":
        """Validate plan binding, derived decisions, and completion state."""
        reviewed_ids = [step.step_id for step in self.reviewed_steps]
        reviewed_set = set(reviewed_ids)
        pending_set = set(self.pending_step_ids)
        plan_set = set(self.plan_step_ids)
        if reviewed_set & pending_set:
            raise ValueError(
                "reviewed and pending step IDs must be disjoint"
            )
        if reviewed_set | pending_set != plan_set:
            raise ValueError(
                "reviewed and pending step IDs must partition plan_step_ids"
            )
        if len(reviewed_ids) + len(self.pending_step_ids) != len(
            self.plan_step_ids
        ):
            raise ValueError(
                "reviewed and pending step IDs must cover plan_step_ids exactly"
            )

        for step in self.reviewed_steps:
            expected_sequence = self.plan_step_ids.index(step.step_id) + 1
            if step.sequence != expected_sequence:
                raise ValueError(
                    "reviewed step sequence must match plan_step_ids position"
                )

        def expected_subsequence(ids: list[str]) -> list[str]:
            selected = set(ids)
            return [
                step_id
                for step_id in self.plan_step_ids
                if step_id in selected
            ]

        if reviewed_ids != expected_subsequence(reviewed_ids):
            raise ValueError(
                "reviewed step IDs must preserve plan_step_ids order"
            )
        if self.pending_step_ids != expected_subsequence(
            self.pending_step_ids
        ):
            raise ValueError(
                "pending_step_ids must preserve plan_step_ids order"
            )

        expected_decision_ids = {
            HumanReviewDecision.accept: [
                step.step_id
                for step in self.reviewed_steps
                if step.decision == HumanReviewDecision.accept
            ],
            HumanReviewDecision.reject: [
                step.step_id
                for step in self.reviewed_steps
                if step.decision == HumanReviewDecision.reject
            ],
            HumanReviewDecision.revise: [
                step.step_id
                for step in self.reviewed_steps
                if step.decision == HumanReviewDecision.revise
            ],
        }
        if self.accepted_step_ids != expected_decision_ids[
            HumanReviewDecision.accept
        ]:
            raise ValueError(
                "accepted_step_ids must match reviewed accept decisions"
            )
        if self.rejected_step_ids != expected_decision_ids[
            HumanReviewDecision.reject
        ]:
            raise ValueError(
                "rejected_step_ids must match reviewed reject decisions"
            )
        if self.revised_step_ids != expected_decision_ids[
            HumanReviewDecision.revise
        ]:
            raise ValueError(
                "revised_step_ids must match reviewed revise decisions"
            )

        if self.plan_step_ids:
            if self.no_action_acknowledged:
                raise ValueError(
                    "non-empty plans cannot use no_action_acknowledged"
                )
            expected_status = (
                HumanReviewSessionStatus.complete
                if not self.pending_step_ids
                else HumanReviewSessionStatus.pending
            )
        else:
            if (
                self.reviewed_steps
                or self.pending_step_ids
                or self.accepted_step_ids
                or self.rejected_step_ids
                or self.revised_step_ids
            ):
                raise ValueError(
                    "empty-plan sessions cannot contain step records or IDs"
                )
            if self.no_action_acknowledged and self.overall_note is None:
                raise ValueError(
                    "acknowledged empty plans require overall_note"
                )
            expected_status = (
                HumanReviewSessionStatus.complete
                if self.no_action_acknowledged
                else HumanReviewSessionStatus.pending
            )

        if self.session_status != expected_status:
            raise ValueError(
                "session_status is inconsistent with pending review state"
            )
        expected_complete = (
            self.session_status == HumanReviewSessionStatus.complete
        )
        if self.human_review_complete != expected_complete:
            raise ValueError(
                "human_review_complete must match session_status"
            )
        return self
