"""
app/file_intake.py — RoleLens source intake for CSV and pasted text (Task 3).

Responsibilities:
  - Accept raw file bytes and a declared SourceFormat.
  - Normalize content via identity.normalize_source_content().
  - Generate a SourceManifestEntry by calling identity.generate_source_id().
  - Enforce the locked semantic_context_category → source_scope mapping.
  - Produce a list[SourceManifestEntry] (one per source accepted).

Supported source formats in this task (Task 3):
  - csv
  - pasted_text (delegated to text_parser.py)

Formats handled by other modules or deferred:
  - excel:       Task 3 extension or later (requires openpyxl)
  - txt:         text_parser.py (pasted_text variant)
  - markdown:    text_parser.py (pasted_text variant)
  - form_input:  later (user context form submission)
  - pdf_text:    delayed optional V1 support

Architecture invariants:
  - This module does NOT mint evidence_id values.
  - Identity generation is delegated to app/identity.py.
  - Timestamp generation is delegated to app/utils.utc_now().
  - Empty content (zero bytes after normalization) is a hard failure — an
    empty source cannot produce valid evidence.
  - Unsupported formats raise ValueError immediately; callers must not pass
    Excel, form_input, or pdf_text to this function in Task 3.
"""

from __future__ import annotations

from datetime import datetime
from typing import Sequence

from app.identity import generate_source_id, normalize_source_content
from app.schemas import (
    SemanticContextCategory,
    SourceFormat,
    SourceManifestEntry,
    SourceScope,
    _LOCKED_CATEGORY_SCOPE,
)
from app.utils import utc_now

# ---------------------------------------------------------------------------
# Supported formats for direct intake in Task 3
# ---------------------------------------------------------------------------

_INTAKE_SUPPORTED_FORMATS: frozenset[SourceFormat] = frozenset(
    {SourceFormat.csv}
)

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
    existing_digest: str | None = None,
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
        existing_digest:           If provided, passed to generate_source_id()
                                   for collision detection.

    Returns:
        SourceManifestEntry with stable source_id and identity_digest.

    Raises:
        EmptySourceError:          If normalized content is empty.
        ValueError:                If bytes cannot be decoded as UTF-8.
        IdentityCollisionError:    If existing_digest differs from computed
                                   digest (propagated from identity.py).
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
        existing_digest=existing_digest,
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
    existing_digest: str | None = None,
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
        existing_digest:           Optional digest for collision detection.

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
        existing_digest=existing_digest,
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
