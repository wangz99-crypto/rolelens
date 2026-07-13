"""
app/evidence_builder.py — RoleLens Evidence Object builder (Task 5).

This is the SOLE module permitted to mint evidence_id values.

Responsibilities:
  - Accept a list[HealthFindingCandidate] and a list[SourceManifestEntry].
  - Build an explicit source manifest registry that detects duplicate and
    conflicting manifest entries (same source_id with incompatible metadata).
  - Validate that each candidate's source_format matches its manifest's
    source_format (ProvenanceMismatchError if not).
  - For each candidate, generate the evidence_id and identity_digest using
    identity.generate_evidence_id() with the manifest's id_algo_version.
  - Detect duplicate candidates (same identity inputs → return the existing
    evidence_id, no second EvidenceObject).
  - Detect and raise IdentityCollisionError on short-ID collision with a
    different digest (does not create a collision EvidenceObject).
  - Derive evidence_scope from the SourceManifestEntry's source_scope and
    semantic_context_category.
  - Return list[EvidenceObject] with all minted evidence_ids.

Architecture invariants:
  - No other module may generate evidence_id values.
  - HealthFindingCandidate has no evidence_id field — this module adds it.
  - data_health.py produces HealthFindingCandidate; this module produces
    EvidenceObject.  The boundary is enforced by both schemas.
  - Empty input list is valid and returns an empty list.
  - sources with source_scope == decision_context must not produce EvidenceObjects
    — raise EvidenceScopeError if attempted.
  - identity.py computes deterministic IDs; this module is the only place that
    constructs EvidenceObject records from HealthFindingCandidate objects.

Decision 002 evidence_scope derivation:
  source_scope=internal_observation → evidence_scope=internal_observation
  source_scope=external_context     → evidence_scope=external_context
  source_scope=user_assertion       → evidence_scope=assumption
    UNLESS semantic_context_category=strategy_profile → evidence_scope=stated_priority
  source_scope=decision_context     → EvidenceScopeError (no EvidenceObject produced)
"""

from __future__ import annotations

from app.identity import (
    IdentityCollisionError,
    canonicalize_locator,
    canonicalize_rule_parameters,
    check_identity_collision,
    generate_evidence_id,
)
from app.schemas import (
    EvidenceObject,
    EvidenceScope,
    EvidenceStatus,
    HealthFindingCandidate,
    SemanticContextCategory,
    SourceManifestEntry,
    SourceScope,
)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class EvidenceScopeError(ValueError):
    """Raised when a HealthFindingCandidate originates from a source whose
    source_scope is decision_context.

    business_question and decision_goal sources must not produce EvidenceObjects.
    They provide decision context, not factual evidence.  This error enforces
    the admissibility boundary from Decision 002.

    Attributes:
        source_id:    The source_id of the disqualified source.
        source_scope: The source_scope value that triggered the error.
    """

    def __init__(self, source_id: str, source_scope: str) -> None:
        self.source_id = source_id
        self.source_scope = source_scope
        super().__init__(
            f"source_id={source_id!r} has source_scope={source_scope!r}.  "
            "Sources with decision_context scope do not produce EvidenceObjects.  "
            "business_question and decision_goal are decision context, not evidence."
        )


class MissingSourceManifestError(ValueError):
    """Raised when a HealthFindingCandidate references a source_id that is
    not present in the provided list[SourceManifestEntry].

    This enforces that every candidate is traceable to a known, registered
    source before evidence_id is minted.

    Attributes:
        source_id: The source_id that could not be found.
    """

    def __init__(self, source_id: str) -> None:
        self.source_id = source_id
        super().__init__(
            f"No SourceManifestEntry found for source_id={source_id!r}.  "
            "Every HealthFindingCandidate must be traceable to a registered source "
            "before evidence_id is minted."
        )


class ProvenanceMismatchError(ValueError):
    """Raised when a HealthFindingCandidate's source_format does not match
    the source_format recorded in its SourceManifestEntry.

    Evidence identity is grounded in the manifest.  A mismatch means the
    candidate was produced from a different physical format than the
    registered source, which is an integrity violation.

    Attributes:
        source_id:              The source_id of the mismatched source.
        manifest_source_format: The source_format in the SourceManifestEntry.
        candidate_source_format: The source_format in the HealthFindingCandidate.
    """

    def __init__(
        self,
        source_id: str,
        manifest_source_format: str,
        candidate_source_format: str,
    ) -> None:
        self.source_id = source_id
        self.manifest_source_format = manifest_source_format
        self.candidate_source_format = candidate_source_format
        super().__init__(
            f"Provenance mismatch for source_id={source_id!r}: "
            f"manifest.source_format={manifest_source_format!r} but "
            f"candidate.source_format={candidate_source_format!r}.  "
            "The candidate must have been produced from the registered source. "
            "Do not construct an EvidenceObject from mismatched provenance."
        )


class ConflictingSourceManifestError(ValueError):
    """Raised when two SourceManifestEntry objects share the same source_id
    and identity_digest but have conflicting identity metadata.

    Upload-event metadata (filename, upload_event_id, created_at) may differ
    and does not trigger this error.  Only identity-relevant fields
    (source_format, semantic_context_category, source_scope, id_algo_version)
    are compared.

    Attributes:
        source_id: The source_id with conflicting metadata.
    """

    def __init__(self, source_id: str, detail: str) -> None:
        self.source_id = source_id
        super().__init__(
            f"Conflicting SourceManifestEntry for source_id={source_id!r}: {detail}.  "
            "Two manifests with the same source_id and digest must have identical "
            "identity metadata (source_format, semantic_context_category, "
            "source_scope, id_algo_version)."
        )


# ---------------------------------------------------------------------------
# Manifest registry builder
# ---------------------------------------------------------------------------


def _build_manifest_registry(
    source_manifests: list[SourceManifestEntry],
) -> dict[str, SourceManifestEntry]:
    """Build a source_id → SourceManifestEntry registry from a list of manifests.

    Handles duplicates as follows:
      - Same source_id + same identity_digest + same identity metadata:
        treated as the same source identity; one entry is kept.
      - Same source_id + different identity_digest:
        IdentityCollisionError is raised.
      - Same source_id + same identity_digest + conflicting identity metadata
        (source_format, semantic_context_category, source_scope, id_algo_version):
        ConflictingSourceManifestError is raised.

    Upload-event metadata (filename, upload_event_id, created_at) may differ
    and does not cause an error.

    Args:
        source_manifests: List of SourceManifestEntry objects.

    Returns:
        dict mapping source_id to SourceManifestEntry.

    Raises:
        IdentityCollisionError: If the same source_id maps to different digests.
        ConflictingSourceManifestError: If same source_id+digest has conflicting
                                        identity metadata.
    """
    registry: dict[str, SourceManifestEntry] = {}

    for manifest in source_manifests:
        sid = manifest.source_id
        if sid not in registry:
            registry[sid] = manifest
            continue

        existing = registry[sid]

        # Check for identity_digest collision.
        if existing.identity_digest != manifest.identity_digest:
            raise IdentityCollisionError(
                short_id=sid,
                existing_digest=existing.identity_digest,
                new_digest=manifest.identity_digest,
            )

        # Same digest — check that identity metadata matches.
        _identity_fields = (
            "source_format",
            "semantic_context_category",
            "source_scope",
            "id_algo_version",
        )
        for field in _identity_fields:
            if getattr(existing, field) != getattr(manifest, field):
                raise ConflictingSourceManifestError(
                    source_id=sid,
                    detail=(
                        f"{field}={getattr(existing, field)!r} (existing) != "
                        f"{getattr(manifest, field)!r} (new)"
                    ),
                )

        # Same digest and same identity metadata — same source identity.
        # Keep the existing entry; do not replace it.

    return registry


# ---------------------------------------------------------------------------
# Evidence scope derivation
# ---------------------------------------------------------------------------


def _derive_evidence_scope(
    source_scope: SourceScope,
    semantic_context_category: SemanticContextCategory,
) -> EvidenceScope:
    """Derive EvidenceScope from source provenance.

    Decision 002 mapping:
      internal_observation → internal_observation
      external_context     → external_context
      user_assertion + strategy_profile → stated_priority
      user_assertion (other)            → assumption
      decision_context     → EvidenceScopeError (caller must handle)

    Args:
        source_scope:              SourceScope of the originating source.
        semantic_context_category: SemanticContextCategory of the source.

    Returns:
        EvidenceScope for the resulting EvidenceObject.

    Raises:
        EvidenceScopeError: If source_scope is decision_context.
    """
    if source_scope == SourceScope.decision_context:
        raise EvidenceScopeError(
            source_id="<unknown>",   # caller will set the real source_id
            source_scope=source_scope.value,
        )
    if source_scope == SourceScope.internal_observation:
        return EvidenceScope.internal_observation
    if source_scope == SourceScope.external_context:
        return EvidenceScope.external_context
    if source_scope == SourceScope.user_assertion:
        if semantic_context_category == SemanticContextCategory.strategy_profile:
            return EvidenceScope.stated_priority
        return EvidenceScope.assumption
    # Exhaustive — all SourceScope values are handled above.
    raise ValueError(f"Unrecognized source_scope: {source_scope!r}")  # pragma: no cover


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_evidence(
    candidates: list[HealthFindingCandidate],
    source_manifests: list[SourceManifestEntry],
) -> list[EvidenceObject]:
    """Convert validated HealthFindingCandidate objects into EvidenceObject records.

    This is the only function in the codebase permitted to mint evidence_id values.

    The id_algo_version used for evidence identity generation is taken from the
    SourceManifestEntry for the candidate's source_id, not a separate default.

    Duplicate handling:
      If two candidates produce the same identity inputs (same source_id,
      evidence_type_key, locator, rule_parameters, and claim_key), only one
      EvidenceObject is created.  The duplicate candidate is silently
      deduplicated — no error is raised.

    Collision handling:
      If the computed short_id matches an existing entry in this batch but the
      full identity_digest differs, IdentityCollisionError is raised immediately.
      No EvidenceObject is created for the colliding candidate.

    Empty input:
      An empty candidate list returns an empty EvidenceObject list.  This is
      not an error — a clean dataset produces no health findings.

    Args:
        candidates:       list[HealthFindingCandidate] from data_health.py.
                          Must not contain evidence_id fields (enforced by schema).
        source_manifests: list[SourceManifestEntry] providing provenance for
                          each candidate.  Every candidate's source_id must
                          appear in this list.

    Returns:
        list[EvidenceObject] with stable, minted evidence_id values.

    Raises:
        MissingSourceManifestError:     If a candidate references an unknown source_id.
        ProvenanceMismatchError:        If candidate.source_format != manifest.source_format.
        EvidenceScopeError:             If a source has source_scope=decision_context.
        IdentityCollisionError:         If a short ID collision is detected within
                                        this batch (not in a persistent registry).
        ConflictingSourceManifestError: If two manifests share a source_id and digest
                                        but have conflicting identity metadata.
    """
    if not candidates:
        return []

    # Build an explicit registry from source_id → SourceManifestEntry.
    # This detects duplicate and conflicting manifests before processing any candidate.
    manifest_by_source_id = _build_manifest_registry(source_manifests)

    # Per-batch evidence registry: evidence_id → identity_digest.
    # Used exclusively for exact-duplicate detection and collision detection.
    seen: dict[str, str] = {}

    results: list[EvidenceObject] = []

    for candidate in candidates:
        # --- Look up the source manifest ---
        manifest = manifest_by_source_id.get(candidate.source_id)
        if manifest is None:
            raise MissingSourceManifestError(source_id=candidate.source_id)

        # --- Enforce provenance: candidate.source_format must match manifest ---
        if candidate.source_format != manifest.source_format:
            raise ProvenanceMismatchError(
                source_id=candidate.source_id,
                manifest_source_format=manifest.source_format.value,
                candidate_source_format=candidate.source_format.value,
            )

        # --- Enforce admissibility: decision_context sources produce no evidence ---
        if manifest.source_scope == SourceScope.decision_context:
            raise EvidenceScopeError(
                source_id=candidate.source_id,
                source_scope=manifest.source_scope.value,
            )

        # --- Derive evidence_scope ---
        evidence_scope = _derive_evidence_scope(
            manifest.source_scope,
            manifest.semantic_context_category,
        )

        # --- Canonicalize identity inputs ---
        canonical_locator = canonicalize_locator(candidate.source_locator)
        canonical_params = canonicalize_rule_parameters(candidate.canonical_rule_parameters)

        # --- Generate evidence_id using the manifest's id_algo_version ---
        evidence_id, identity_digest = generate_evidence_id(
            source_id=candidate.source_id,
            evidence_type_key=candidate.evidence_type,
            canonical_source_locator=canonical_locator,
            canonical_rule_parameters=canonical_params,
            normalized_claim_key=candidate.normalized_claim_key,
            id_algo_version=manifest.id_algo_version,
        )

        # --- Collision and deduplication detection (within this batch) ---
        check_identity_collision(
            short_id=evidence_id,
            identity_digest=identity_digest,
            existing_identities=seen,
        )

        if evidence_id in seen:
            # Exact duplicate (same short_id AND same digest): deduplicate silently.
            continue

        # --- Register in the per-batch evidence registry ---
        seen[evidence_id] = identity_digest

        # --- Build the EvidenceObject ---
        obj = EvidenceObject(
            evidence_id=evidence_id,
            identity_digest=identity_digest,
            source_id=candidate.source_id,
            source_format=candidate.source_format,
            source_locator=candidate.source_locator,
            evidence_type=candidate.evidence_type,
            evidence_scope=evidence_scope,
            extraction_method="deterministic",
            finding=candidate.finding,
            supporting_evidence=candidate.supporting_evidence,
            confidence=candidate.confidence,
            limitations=candidate.limitations,
            relevant_roles=candidate.relevant_roles,
            decision_relevance=candidate.decision_relevance,
            id_algo_version=manifest.id_algo_version,
            created_by="evidence_builder",
            status=EvidenceStatus.active,
            invalidated_reason=None,
        )
        results.append(obj)

    return results
