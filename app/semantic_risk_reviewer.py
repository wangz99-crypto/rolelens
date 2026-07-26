"""Provider-neutral probabilistic semantic risk review (Task 7B-1).

Semantic review is probabilistic. All candidates remain reviewable and
non-authoritative; candidates marked ``needs_human_review`` or
``reviewer_uncertain`` require explicit human review. The reviewer does not
prove that a claim is false, and ``likely_supported`` is still not equivalent
to verified truth. Deterministic Task 7A findings remain authoritative for
mechanical checks. No semantic candidate automatically blocks or approves
downstream work. Keyword-based heuristics are intentionally excluded.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from pydantic import ValidationError

from app.role_engine import (
    InsufficientEvidence,
    RoleGenerationFailure,
    RoleOutcome,
)
from app.schemas import (
    EvidenceObject,
    EvidenceStatus,
    RiskReviewResult,
    RoleKey,
    RoleView,
    SemanticRiskReviewResult,
    _ROLE_EXECUTION_ORDER,
)


class SemanticRiskInputError(ValueError):
    """Raised when semantic-review input is internally inconsistent."""


class SemanticRiskProviderError(RuntimeError):
    """Raised when the semantic risk provider fails."""


class SemanticRiskResponseError(RuntimeError):
    """Raised when provider output violates the semantic-review contract."""


@dataclass(frozen=True)
class SemanticRiskRequest:
    """Exact bounded input exposed to a semantic risk provider."""

    role_views: tuple[RoleView, ...]
    evidence_objects: tuple[EvidenceObject, ...]
    deterministic_risk_result: RiskReviewResult
    allowed_evidence_ids: frozenset[str]


class SemanticRiskProvider(Protocol):
    """Provider-neutral semantic risk review interface."""

    def review_semantic_risks(
        self,
        request: SemanticRiskRequest,
    ) -> Mapping[str, Any]:
        """Return one structured semantic review mapping."""
        ...


def _safe_repr(value: object) -> str:
    """Return a representation without trusting an arbitrary object's repr."""
    try:
        return repr(value)
    except Exception:
        return f"<unrepresentable {type(value).__name__}>"


def _safe_declared_role_key(outcome: object) -> str:
    """Safely render an outcome-declared role key when one is present."""
    try:
        declared = getattr(outcome, "role_key")
    except (AttributeError, Exception):
        return "<absent or unreadable>"
    if isinstance(declared, RoleKey):
        return declared.value
    return _safe_repr(declared)


def _validate_role_outcomes(
    role_outcomes: Mapping[RoleKey, RoleOutcome],
) -> None:
    """Validate exact keys, approved value types, and role identity."""
    for mapping_key in role_outcomes:
        if not isinstance(mapping_key, RoleKey):
            raise SemanticRiskInputError(
                "role_outcomes contains a non-RoleKey mapping key: "
                f"mapping_key={_safe_repr(mapping_key)}, "
                f"outcome_type="
                f"{type(role_outcomes[mapping_key]).__name__!r}."
            )

    required = set(_ROLE_EXECUTION_ORDER)
    present = set(role_outcomes)
    if present != required:
        missing = sorted(
            role_key.value for role_key in required - present
        )
        extra = sorted(
            role_key.value for role_key in present - required
        )
        raise SemanticRiskInputError(
            "role_outcomes must contain exactly the five RoleKey values: "
            f"missing={missing!r}, extra={extra!r}."
        )

    approved_types = (RoleView, InsufficientEvidence, RoleGenerationFailure)
    for mapping_key in _ROLE_EXECUTION_ORDER:
        outcome = role_outcomes[mapping_key]
        outcome_type = type(outcome)
        declared_role_key = _safe_declared_role_key(outcome)
        if outcome_type not in approved_types:
            raise SemanticRiskInputError(
                f"role_outcomes mapping_key={mapping_key.value!r} has "
                f"unsupported outcome_type={outcome_type.__name__!r}, "
                f"outcome_declared_role_key={declared_role_key!r}."
            )
        if outcome.role_key != mapping_key:
            raise SemanticRiskInputError(
                "Role outcome identity mismatch: "
                f"mapping_key={mapping_key.value!r}, "
                f"outcome_declared_role_key={declared_role_key!r}, "
                f"outcome_type={outcome_type.__name__!r}."
            )


def _successful_role_views(
    role_outcomes: Mapping[RoleKey, RoleOutcome],
) -> tuple[RoleView, ...]:
    """Collect successful RoleViews in the fixed role execution order."""
    successful: list[RoleView] = []
    for role_key in _ROLE_EXECUTION_ORDER:
        outcome = role_outcomes.get(role_key)
        if not isinstance(outcome, RoleView):
            continue
        successful.append(outcome)
    return tuple(successful)


def _build_evidence_registry(
    evidence_objects: Sequence[EvidenceObject],
) -> dict[str, EvidenceObject]:
    """Build a fail-closed evidence registry, retaining exact duplicates."""
    registry: dict[str, EvidenceObject] = {}
    for evidence in evidence_objects:
        existing = registry.get(evidence.evidence_id)
        if existing is None:
            registry[evidence.evidence_id] = evidence
            continue
        if existing == evidence:
            continue
        raise SemanticRiskInputError(
            f"Conflicting EvidenceObject records share "
            f"evidence_id={evidence.evidence_id!r}: "
            f"existing_identity_digest={existing.identity_digest!r}, "
            f"new_identity_digest={evidence.identity_digest!r}."
        )
    return registry


def _cited_evidence(
    role_views: tuple[RoleView, ...],
    registry: Mapping[str, EvidenceObject],
) -> tuple[tuple[EvidenceObject, ...], frozenset[str]]:
    """Resolve only evidence cited by successful views, in first-seen order."""
    cited_ids: list[str] = []
    seen: set[str] = set()
    for view in role_views:
        for finding in view.key_findings:
            for reference in finding.evidence_references:
                evidence_id = reference.evidence_id
                if evidence_id in seen:
                    continue
                if evidence_id not in registry:
                    raise SemanticRiskInputError(
                        f"Successful RoleView {view.role_key.value!r} cites "
                        f"unknown evidence_id={evidence_id!r}."
                    )
                evidence = registry[evidence_id]
                if evidence.status != EvidenceStatus.active:
                    raise SemanticRiskInputError(
                        f"Successful RoleView {view.role_key.value!r} cites "
                        f"inactive evidence_id={evidence_id!r}."
                    )
                seen.add(evidence_id)
                cited_ids.append(evidence_id)

    return (
        tuple(registry[evidence_id] for evidence_id in cited_ids),
        frozenset(cited_ids),
    )


def _validate_provider_result(
    result: SemanticRiskReviewResult,
    role_views: tuple[RoleView, ...],
    registry: Mapping[str, EvidenceObject],
) -> None:
    """Validate all semantic candidates against exact role claims and evidence."""
    expected_role_keys = [view.role_key for view in role_views]
    if result.reviewed_role_keys != expected_role_keys:
        raise SemanticRiskResponseError(
            "reviewed_role_keys must exactly match successful RoleViews in "
            "fixed role order."
        )

    views_by_role = {view.role_key: view for view in role_views}
    for candidate in result.candidates:
        view = views_by_role.get(candidate.role_key)
        if view is None:
            raise SemanticRiskResponseError(
                f"SemanticRiskCandidate role_key={candidate.role_key.value!r} "
                "does not correspond to a successful RoleView."
            )
        if candidate.claim_index >= len(view.key_findings):
            raise SemanticRiskResponseError(
                f"SemanticRiskCandidate claim_index={candidate.claim_index} "
                f"is out of range for role_key={candidate.role_key.value!r}."
            )

        claim = view.key_findings[candidate.claim_index]
        claim_evidence_ids = {
            reference.evidence_id
            for reference in claim.evidence_references
        }
        for evidence_id in candidate.evidence_ids:
            evidence = registry.get(evidence_id)
            if evidence is None:
                raise SemanticRiskResponseError(
                    f"SemanticRiskCandidate cites unknown "
                    f"evidence_id={evidence_id!r}."
                )
            if evidence.status != EvidenceStatus.active:
                raise SemanticRiskResponseError(
                    f"SemanticRiskCandidate cites inactive "
                    f"evidence_id={evidence_id!r}."
                )
            if evidence_id not in claim_evidence_ids:
                raise SemanticRiskResponseError(
                    f"SemanticRiskCandidate evidence_id={evidence_id!r} is not "
                    "cited by the referenced claim."
                )


def review_semantic_risks(
    provider: SemanticRiskProvider,
    role_outcomes: Mapping[RoleKey, RoleOutcome],
    evidence_objects: Sequence[EvidenceObject],
    deterministic_risk_result: RiskReviewResult,
) -> SemanticRiskReviewResult:
    """Request and fully validate one probabilistic semantic risk review."""
    _validate_role_outcomes(role_outcomes)
    role_views = _successful_role_views(role_outcomes)
    if not role_views:
        return SemanticRiskReviewResult(
            candidates=[],
            reviewed_role_keys=[],
            reviewer_model=None,
            human_review_required=False,
        )

    registry = _build_evidence_registry(evidence_objects)
    cited_evidence, allowed_evidence_ids = _cited_evidence(role_views, registry)
    request = SemanticRiskRequest(
        role_views=role_views,
        evidence_objects=cited_evidence,
        deterministic_risk_result=deterministic_risk_result,
        allowed_evidence_ids=allowed_evidence_ids,
    )

    try:
        raw_result = provider.review_semantic_risks(request)
    except Exception:
        raise SemanticRiskProviderError(
            "Semantic risk provider failed during review."
        ) from None

    try:
        result = SemanticRiskReviewResult.model_validate(raw_result)
    except (ValidationError, ValueError, TypeError):
        raise SemanticRiskResponseError(
            "Semantic risk provider output failed schema validation."
        ) from None

    _validate_provider_result(result, role_views, registry)
    return result
