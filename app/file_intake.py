"""
app/file_intake.py — RoleLens source intake for CSV, pasted text, and form input (Tasks 3 & 5B-1).

Responsibilities:
  - Accept raw file bytes (CSV) or exact text (form input) and a declared SourceFormat.
  - Normalize content via identity.normalize_source_content().
  - Generate a SourceManifestEntry by calling identity.generate_source_id().
  - Enforce the locked semantic_context_category → source_scope mapping.
  - Produce a SourceManifestEntry (one per source accepted).

Supported source formats:
  - csv             (ingest_csv / ingest_source)
  - form_input      (ingest_form_input — Task 5B-1)
  - pasted_text     (delegated to text_parser.py)
  - txt             (text_parser.py)
  - markdown        (text_parser.py)

Formats deferred:
  - excel:       Task 3 extension or later (requires openpyxl)
  - pdf_text:    delayed optional V1 support

Architecture invariants:
  - This module does NOT mint evidence_id values.
  - This module does NOT produce TextEvidenceCandidate or EvidenceObject values.
  - Identity generation is delegated to app/identity.py.
  - Timestamp generation is delegated to app/utils.utc_now().
  - Empty content (zero bytes after normalization) is a hard failure — an
    empty source cannot produce valid evidence.
  - Unsupported formats for ingest_source raise ValueError immediately.
  - Collision checking uses the explicit check_identity_collision() API.
    Callers may pass an identity_registry (short_id → identity_digest) to
    detect collisions against previously seen sources.  A bare existing_digest
    disconnected from a short_id is NOT accepted.
"""

from __future__ import annotations

from datetime import datetime
from typing import Mapping, Sequence

from app.identity import (
    check_identity_collision,
    generate_source_id,
    normalize_source_content,
)
from app.schemas import (
    SemanticContextCategory,
    SourceFormat,
    SourceManifestEntry,
    SourceScope,
    _LOCKED_CATEGORY_SCOPE,
)
from app.utils import utc_now

# ---------------------------------------------------------------------------
# Supported formats for direct intake (ingest_source dispatcher)
# ---------------------------------------------------------------------------

_INTAKE_SUPPORTED_FORMATS: frozenset[SourceFormat] = frozenset(
    {SourceFormat.csv}
)

# Categories accepted by ingest_form_input and the required source_scope for each.
_FORM_INPUT_SUPPORTED_CATEGORIES: dict[SemanticContextCategory, SourceScope] = {
    SemanticContextCategory.strategy_profile: SourceScope.user_assertion,
    SemanticContextCategory.user_assumption: SourceScope.user_assertion,
    SemanticContextCategory.business_question: SourceScope.decision_context,
    SemanticContextCategory.decision_goal: SourceScope.decision_context,
}

# ---------------------------------------------------------------------------
# Hard errors
# ---------------------------------------------------------------------------


class EmptySourceError(ValueError):
    """Raised when the normalized source content is empty.

    An empty source cannot produce Evidence Objects and must not be admitted
    to the pipeline.  The caller must surface this as a user-visible validation
    failure, not a silent skip.
    """

    def __init__(self, source_format: str, filename: str | None = None) -> None:
        self.source_format = source_format
        self.filename = filename
        name_info = f" (filename={filename!r})" if filename else ""
        super().__init__(
            f"Empty source content rejected for format {source_format!r}{name_info}.  "
            "An empty source cannot produce Evidence Objects.  "
            "Resolve the source before re-submitting."
        )


class UnsupportedSourceFormatError(ValueError):
    """Raised when a source format is not yet supported by this intake module.

    This is a structured error so callers can distinguish unsupported-format
    failures from other ValueErrors.
    """

    def __init__(self, source_format: str) -> None:
        self.source_format = source_format
        supported = ", ".join(f.value for f in sorted(_INTAKE_SUPPORTED_FORMATS, key=lambda f: f.value))
        super().__init__(
            f"Source format {source_format!r} is not supported by file_intake in Task 3.  "
            f"Currently supported: {supported}.  "
            "For pasted text, txt, or markdown use app/text_parser.py."
        )


# ---------------------------------------------------------------------------
# Public API: ingest_csv
# ---------------------------------------------------------------------------


def ingest_csv(
    raw_bytes: bytes,
    *,
    semantic_context_category: SemanticContextCategory,
    filename: str | None = None,
    upload_event_id: str | None = None,
    id_algo_version: str = "v1",
    created_at: datetime | None = None,
    identity_registry: Mapping[str, str] | None = None,
) -> SourceManifestEntry:
    """Accept raw CSV bytes and produce a SourceManifestEntry.

    The filename is recorded as metadata but is NOT an identity input.
    Two CSV files with identical content and category but different filenames
    produce the same source_id.

    Args:
        raw_bytes:                 Raw CSV file bytes (UTF-8 encoding assumed).
        semantic_context_category: Semantic purpose (must be appropriate for
                                   tabular data, e.g. data_source).
        filename:                  Original filename.  Stored as metadata only,
                                   excluded from identity.  May be None.
        upload_event_id:           Optional upload event identifier.  Excluded
                                   from identity.
        id_algo_version:           Identity algorithm version.  Default "v1".
        created_at:                Timezone-aware datetime.  Defaults to
                                   utc_now() if not provided.
        identity_registry:         Optional mapping of short_id → identity_digest
                                   used for collision detection.  When provided,
                                   check_identity_collision() is called with the
                                   generated (source_id, identity_digest) pair.

    Returns:
        SourceManifestEntry with stable source_id and identity_digest.

    Raises:
        EmptySourceError:          If normalized content is empty.
        ValueError:                If bytes cannot be decoded as UTF-8.
        IdentityCollisionError:    If identity_registry contains this short_id
                                   under a different digest (propagated from
                                   identity.check_identity_collision).
        ValidationError:           If SourceManifestEntry construction fails.
    """
    normalized = normalize_source_content(raw_bytes)

    if not normalized.strip():
        raise EmptySourceError(
            source_format=SourceFormat.csv.value,
            filename=filename,
        )

    source_id, identity_digest = generate_source_id(
        source_format=SourceFormat.csv.value,
        semantic_context_category=semantic_context_category.value,
        normalized_content=normalized,
        id_algo_version=id_algo_version,
    )

    if identity_registry is not None:
        check_identity_collision(
            short_id=source_id,
            identity_digest=identity_digest,
            existing_identities=identity_registry,
        )

    source_scope = _resolve_source_scope(semantic_context_category)
    ts = created_at if created_at is not None else utc_now()

    return SourceManifestEntry(
        source_id=source_id,
        identity_digest=identity_digest,
        source_format=SourceFormat.csv,
        semantic_context_category=semantic_context_category,
        source_scope=source_scope,
        filename=filename,
        upload_event_id=upload_event_id,
        id_algo_version=id_algo_version,
        created_at=ts,
    )


# ---------------------------------------------------------------------------
# Public API: ingest_source (general dispatcher)
# ---------------------------------------------------------------------------


def ingest_source(
    raw_bytes: bytes,
    *,
    source_format: SourceFormat,
    semantic_context_category: SemanticContextCategory,
    filename: str | None = None,
    upload_event_id: str | None = None,
    id_algo_version: str = "v1",
    created_at: datetime | None = None,
    identity_registry: Mapping[str, str] | None = None,
) -> SourceManifestEntry:
    """Dispatch raw source bytes to the appropriate intake handler.

    In Task 3, only CSV is handled here.  Pasted text (pasted_text, txt,
    markdown) must be submitted via app/text_parser.parse_pasted_text().
    All other formats raise UnsupportedSourceFormatError.

    Args:
        raw_bytes:                 Raw source bytes.
        source_format:             Declared physical format of the source.
        semantic_context_category: Semantic purpose of the source.
        filename:                  Optional original filename (metadata only).
        upload_event_id:           Optional upload event identifier.
        id_algo_version:           Identity algorithm version.  Default "v1".
        created_at:                Timezone-aware datetime for provenance.
        identity_registry:         Optional short_id → identity_digest registry
                                   for collision detection.

    Returns:
        SourceManifestEntry.

    Raises:
        UnsupportedSourceFormatError: If source_format is not csv.
        EmptySourceError:             If normalized content is empty.
        IdentityCollisionError:       Propagated from identity.py.
    """
    if source_format not in _INTAKE_SUPPORTED_FORMATS:
        raise UnsupportedSourceFormatError(source_format.value)

    # CSV
    return ingest_csv(
        raw_bytes,
        semantic_context_category=semantic_context_category,
        filename=filename,
        upload_event_id=upload_event_id,
        id_algo_version=id_algo_version,
        created_at=created_at,
        identity_registry=identity_registry,
    )


# ---------------------------------------------------------------------------
# Public API: ingest_form_input
# ---------------------------------------------------------------------------


def ingest_form_input(
    text: str,
    *,
    semantic_context_category: SemanticContextCategory,
    upload_event_id: str | None = None,
    id_algo_version: str = "v1",
    created_at: datetime | None = None,
    identity_registry: Mapping[str, str] | None = None,
) -> SourceManifestEntry:
    """Accept exact user-entered text and produce a SourceManifestEntry.

    Creates a form_input source manifest for strategy profile, user assumption,
    business question, or decision goal context text.

    The text is the identity input (normalized via normalize_source_content).
    Field extraction (UserContextLocator construction) is performed by the
    Task 5B-2 extractor, not here.

    Args:
        text:                      Exact user-entered text (must not be blank).
        semantic_context_category: Must be one of strategy_profile,
                                   user_assumption, business_question, or
                                   decision_goal.
        upload_event_id:           Optional upload event identifier (metadata
                                   only; excluded from identity).
        id_algo_version:           Identity algorithm version.  Default "v1".
        created_at:                Timezone-aware datetime.  Defaults to
                                   utc_now() if not provided.
        identity_registry:         Optional mapping of short_id → identity_digest
                                   used for collision detection.  When provided,
                                   check_identity_collision() is called with the
                                   generated (source_id, identity_digest) pair.

    Returns:
        SourceManifestEntry with stable source_id and identity_digest.

    Raises:
        EmptySourceError:          If text is blank or whitespace-only.
        ValueError:                If semantic_context_category is not supported
                                   by ingest_form_input.
        IdentityCollisionError:    If identity_registry contains this short_id
                                   under a different digest.
        ValidationError:           If SourceManifestEntry construction fails.
    """
    if semantic_context_category not in _FORM_INPUT_SUPPORTED_CATEGORIES:
        raise ValueError(
            f"ingest_form_input does not accept "
            f"semantic_context_category={semantic_context_category.value!r}. "
            f"Supported: {[c.value for c in sorted(_FORM_INPUT_SUPPORTED_CATEGORIES, key=lambda c: c.value)]!r}"
        )

    normalized = normalize_source_content(text)

    if not normalized.strip():
        raise EmptySourceError(
            source_format=SourceFormat.form_input.value,
            filename=None,
        )

    source_id, identity_digest = generate_source_id(
        source_format=SourceFormat.form_input.value,
        semantic_context_category=semantic_context_category.value,
        normalized_content=normalized,
        id_algo_version=id_algo_version,
    )

    if identity_registry is not None:
        check_identity_collision(
            short_id=source_id,
            identity_digest=identity_digest,
            existing_identities=identity_registry,
        )

    source_scope = _FORM_INPUT_SUPPORTED_CATEGORIES[semantic_context_category]
    ts = created_at if created_at is not None else utc_now()

    return SourceManifestEntry(
        source_id=source_id,
        identity_digest=identity_digest,
        source_format=SourceFormat.form_input,
        semantic_context_category=semantic_context_category,
        source_scope=source_scope,
        filename=None,
        upload_event_id=upload_event_id,
        id_algo_version=id_algo_version,
        created_at=ts,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _resolve_source_scope(category: SemanticContextCategory) -> SourceScope:
    """Resolve source_scope for a given semantic_context_category.

    Locked categories use the mapping from _LOCKED_CATEGORY_SCOPE.
    Unlocked categories (data_source, internal_report) default to
    internal_observation — the conservative choice for tabular sources.

    Args:
        category: The semantic context category.

    Returns:
        The appropriate SourceScope value.
    """
    if category in _LOCKED_CATEGORY_SCOPE:
        return _LOCKED_CATEGORY_SCOPE[category]
    return SourceScope.internal_observation
