"""
app/evidence_builder.py — RoleLens Evidence Object builder (Task 5).

This is the SOLE module permitted to mint evidence_id values.

Responsibilities:
  - Accept a list[HealthFindingCandidate] and a list[SourceManifestEntry].
  - For each candidate, generate the evidence_id and identity_digest using
    identity.generate_evidence_id().
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
    *,
    id_algo_version: str = "v1",
) -> list[EvidenceObject]:
    """Convert validated HealthFindingCandidate objects into EvidenceObject records.

    This is the only function in the codebase permitted to mint evidence_id values.

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
        id_algo_version:  Identity algorithm version.  Default "v1".

    Returns:
        list[EvidenceObject] with stable, minted evidence_id values.

    Raises:
        MissingSourceManifestError: If a candidate references an unknown source_id.
        EvidenceScopeError:         If a source has source_scope=decision_context.
        IdentityCollisionError:     If a short ID collision is detected within
                                    this batch (not in a persistent registry).
    """
    if not candidates:
        return []

    # Build a lookup from source_id → SourceManifestEntry.
    manifest_by_source_id: dict[str, SourceManifestEntry] = {
        m.source_id: m for m in source_manifests
    }

    # Deduplication registry: (short_id → identity_digest) for this batch.
    # IdentityCollisionError is raised if a short_id appears with a different digest.
    seen: dict[str, str] = {}      # short_id → identity_digest
    seen_digests: set[str] = set() # set of identity_digest already emitted

    results: list[EvidenceObject] = []

    for candidate in candidates:
        # --- Look up the source manifest ---
        manifest = manifest_by_source_id.get(candidate.source_id)
        if manifest is None:
            raise MissingSourceManifestError(source_id=candidate.source_id)

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

        # --- Generate evidence_id ---
        existing_digest = seen.get(None)  # placeholder; use short_id lookup below
        evidence_id, identity_digest = generate_evidence_id(
            source_id=candidate.source_id,
            evidence_type_key=candidate.evidence_type,
            canonical_source_locator=canonical_locator,
            canonical_rule_parameters=canonical_params,
            normalized_claim_key=candidate.normalized_claim_key,
            id_algo_version=id_algo_version,
        )

        # --- Collision detection (within this batch) ---
        if evidence_id in seen:
            if seen[evidence_id] != identity_digest:
                raise IdentityCollisionError(
                    short_id=evidence_id,
                    existing_digest=seen[evidence_id],
                    new_digest=identity_digest,
                )
            # Exact duplicate (same short_id AND same digest): deduplicate silently.
            # The duplicate candidate maps to the same evidence identity — skip.
            continue

        # --- Register in the deduplication registry ---
        seen[evidence_id] = identity_digest

        # --- Skip if we already emitted an EvidenceObject with this digest ---
        # (covers the case where two candidates are semantically identical but
        # presented as separate objects by the caller)
        if identity_digest in seen_digests:
            continue
        seen_digests.add(identity_digest)

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
            id_algo_version=id_algo_version,
            created_by="evidence_builder",
            status=EvidenceStatus.active,
            invalidated_reason=None,
        )
        results.append(obj)

    return results
