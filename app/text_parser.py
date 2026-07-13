"""
app/text_parser.py — RoleLens minimal pasted-text adapter (Task 3).

Responsibilities:
  - Accept raw pasted text as a str or bytes.
  - Normalize content via identity.normalize_source_content().
  - Validate that the source format is appropriate for pasted text
    (pasted_text, txt, or markdown).
  - Generate a SourceManifestEntry by calling identity.generate_source_id().
  - Enforce the locked semantic_context_category → source_scope mapping from
    schemas._LOCKED_CATEGORY_SCOPE.

Scope for V1 first vertical slice (Task 3):
  - No chunking.
  - No section splitting.
  - No heading extraction.
  - No PDF handling.
  - No Markdown structure parsing.

Later extensions (post-Task-3):
  - TXT / Markdown section splitting and heading extraction.
  - PDF text extraction (delayed optional V1 support).

Architecture invariants:
  - This module does NOT mint evidence_id values.
  - Identity generation is delegated to app/identity.py.
  - Timestamp generation is delegated to app/utils.utc_now().
  - Returned SourceManifestEntry has no filename (pasted text has no filename).
"""

from __future__ import annotations

from datetime import datetime

from typing import Mapping

from app.identity import check_identity_collision, generate_source_id, normalize_source_content
from app.schemas import (
    SemanticContextCategory,
    SourceFormat,
    SourceManifestEntry,
    SourceScope,
    _LOCKED_CATEGORY_SCOPE,
)
from app.utils import utc_now

# ---------------------------------------------------------------------------
# Accepted formats for pasted / plain text sources
# ---------------------------------------------------------------------------

_TEXT_INTAKE_FORMATS: frozenset[SourceFormat] = frozenset(
    {SourceFormat.pasted_text, SourceFormat.txt, SourceFormat.markdown}
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def parse_pasted_text(
    raw_text: str | bytes,
    *,
    semantic_context_category: SemanticContextCategory,
    source_format: SourceFormat = SourceFormat.pasted_text,
    id_algo_version: str = "v1",
    created_at: datetime | None = None,
    identity_registry: Mapping[str, str] | None = None,
) -> SourceManifestEntry:
    """Accept pasted text and produce a SourceManifestEntry.

    This is the minimal pasted-text adapter for the first vertical slice.
    It normalizes, hashes, and wraps the text into a provenance record.

    Args:
        raw_text:                  Raw pasted text as str or bytes.
        semantic_context_category: Semantic purpose of this text
                                   (e.g. industry_context, strategy_profile).
        source_format:             Physical format.  Must be one of
                                   pasted_text, txt, or markdown.
                                   Defaults to pasted_text.
        id_algo_version:           Identity algorithm version.  Default "v1".
        created_at:                Timezone-aware datetime for the manifest entry.
                                   Defaults to utc_now() if not provided.
        identity_registry:         Optional mapping of short_id → identity_digest
                                   used for collision detection.  When provided,
                                   check_identity_collision() is called with the
                                   generated (source_id, identity_digest) pair.
                                   An unrelated entry with a different short ID
                                   does not raise.  The registry is not mutated.

    Returns:
        SourceManifestEntry with a stable source_id and identity_digest.

    Raises:
        ValueError: If source_format is not a text intake format.
        ValueError: If raw_text cannot be decoded as UTF-8 (bytes input only).
        IdentityCollisionError: If identity_registry contains this source_id
                                under a different digest.
        ValidationError: If SourceManifestEntry construction fails.
    """
    if source_format not in _TEXT_INTAKE_FORMATS:
        raise ValueError(
            f"parse_pasted_text does not accept source_format={source_format.value!r}.  "
            f"Accepted formats: {', '.join(f.value for f in sorted(_TEXT_INTAKE_FORMATS, key=lambda f: f.value))}.  "
            "For tabular sources use app/file_intake.py."
        )

    normalized = normalize_source_content(raw_text)

    source_id, identity_digest = generate_source_id(
        source_format=source_format.value,
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

    # Resolve source_scope: locked categories use the locked mapping; others
    # must be resolved by the caller's category choice.
    source_scope = _resolve_source_scope(semantic_context_category)

    ts = created_at if created_at is not None else utc_now()

    return SourceManifestEntry(
        source_id=source_id,
        identity_digest=identity_digest,
        source_format=source_format,
        semantic_context_category=semantic_context_category,
        source_scope=source_scope,
        filename=None,
        upload_event_id=None,
        id_algo_version=id_algo_version,
        created_at=ts,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _resolve_source_scope(category: SemanticContextCategory) -> SourceScope:
    """Resolve the source_scope for a given semantic_context_category.

    Locked categories (business_question, decision_goal, industry_context,
    strategy_profile, user_assumption) have fixed scope values from the
    _LOCKED_CATEGORY_SCOPE mapping.

    Unlocked categories (data_source, internal_report) fall back to
    internal_observation as a conservative default for text sources.
    This matches the intuition that a pasted internal report is an
    internal_observation, and a pasted data source description is too.

    Args:
        category: The semantic context category.

    Returns:
        The appropriate SourceScope value.
    """
    if category in _LOCKED_CATEGORY_SCOPE:
        return _LOCKED_CATEGORY_SCOPE[category]
    # Unlocked categories: pasted text defaults to internal_observation.
    return SourceScope.internal_observation
