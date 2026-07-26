"""
app/risk_checker.py — RoleLens deterministic epistemic and workflow Risk Checker (Task 7A).

Responsibilities:
  - Receive the dict[RoleKey, RoleOutcome] produced by the role engine and a
    sequence of EvidenceObjects.
  - Produce a RiskReviewResult containing all deterministic RiskFinding records.

Honest scope boundary (Task 7A only):
  This module does NOT determine:
    - whether a citation semantically supports a claim
    - correlation versus causation
    - unsupported ROI or budget claims
    - natural-language role-boundary violations

  Those require Task 7B semantic review (LLM-assisted) and subsequent human
  review. This module must not use keyword heuristics for those problems.

Architecture invariants:
  - Fully deterministic: no provider calls, no LLM, no Granite.
  - Fails closed: invalid or inconsistent input raises RiskInputError.
  - Does not silently repair invalid evidence citations in RoleViews.
  - One role's findings do not suppress or merge findings for other roles.
"""

from __future__ import annotations

from typing import Mapping, Sequence

from app.role_engine import InsufficientEvidence, RoleGenerationFailure, RoleOutcome
from app.schemas import (
    EvidenceObject,
    EvidenceScope,
    EvidenceStatus,
    GroundedFinding,
    RiskCode,
    RiskFinding,
    RiskReviewResult,
    RiskSeverity,
    RoleKey,
    RoleView,
    _ROLE_EXECUTION_ORDER,
)

# ---------------------------------------------------------------------------
# Risk-code precedence for deterministic finding ordering
# ---------------------------------------------------------------------------

_RISK_CODE_ORDER: dict[RiskCode, int] = {
    RiskCode.external_context_only:           0,
    RiskCode.assumption_only:                 1,
    RiskCode.stated_priority_only:            2,
    RiskCode.assumption_not_declared:         3,
    RiskCode.action_without_internal_evidence: 4,
    RiskCode.human_review_bypass:             5,
    RiskCode.insufficient_evidence:           6,
    RiskCode.role_generation_failure:         7,
}

# Sentinel for claim-level findings to sort before role-level (claim_index=None).
_ROLE_LEVEL_SORT_KEY = 10_000_000

# ---------------------------------------------------------------------------
# Public error type
# ---------------------------------------------------------------------------


class RiskInputError(ValueError):
    """Raised when the inputs to check_role_risks() are structurally invalid.

    Callers must not silently suppress this exception — invalid inputs indicate
    a pipeline ordering violation or an evidence registry inconsistency.
    """


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def check_role_risks(
    role_outcomes: Mapping[RoleKey, RoleOutcome],
    evidence_objects: Sequence[EvidenceObject],
) -> RiskReviewResult:
    """Deterministically check all five role outcomes for epistemic risks.

    Args:
        role_outcomes:    Output of run_role_engine().  Must contain exactly
                          the five RoleKey values.
        evidence_objects: All EvidenceObjects for this run.

    Returns:
        RiskReviewResult with ordered, deduplicated RiskFinding records.

    Raises:
        RiskInputError: If role_outcomes is missing keys, the evidence registry
                        has conflicting records, or a RoleView cites an unknown
                        or invalidated evidence_id.
    """
    _validate_role_outcomes(role_outcomes)
    registry = _build_registry(evidence_objects)
    _validate_role_view_citations(role_outcomes, registry)

    all_findings: list[RiskFinding] = []

    for role_key in _ROLE_EXECUTION_ORDER:
        outcome = role_outcomes[role_key]
        role_findings = _check_one_outcome(role_key, outcome, registry)
        all_findings.extend(role_findings)

    # Deduplicate then sort.
    unique_findings = _deduplicate(all_findings)
    ordered = _sort_findings(unique_findings)

    has_blocking = any(f.blocks_downstream for f in ordered)
    requires_review = any(f.requires_human_review for f in ordered)

    return RiskReviewResult(
        findings=ordered,
        reviewed_role_keys=list(_ROLE_EXECUTION_ORDER),
        has_blocking_risks=has_blocking,
        human_review_required=requires_review,
    )


# ---------------------------------------------------------------------------
# Input validation helpers
# ---------------------------------------------------------------------------


def _safe_repr(value: object) -> str:
    """Return a representation that cannot fail on an arbitrary mapping key."""
    try:
        return repr(value)
    except Exception:
        return f"<unrepresentable {type(value).__name__}>"


def _declared_role_key_text(value: object) -> str:
    """Render an outcome-declared role key without assuming its runtime type."""
    if isinstance(value, RoleKey):
        return value.value
    return _safe_repr(value)


def _validate_role_outcomes(
    role_outcomes: Mapping[RoleKey, RoleOutcome],
) -> None:
    """Validate keys, outcome types, and key/value role identity."""
    for mapping_key in role_outcomes:
        if not isinstance(mapping_key, RoleKey):
            raise RiskInputError(
                "role_outcomes contains a non-RoleKey mapping key: "
                f"{_safe_repr(mapping_key)} "
                f"(type={type(mapping_key).__name__})."
            )

    present = set(role_outcomes.keys())
    required = {k for k in _ROLE_EXECUTION_ORDER}
    if present != required:
        missing = required - present
        extra = present - required
        raise RiskInputError(
            f"role_outcomes must contain exactly the five RoleKey values. "
            f"Missing: {sorted(k.value for k in missing)!r}. "
            f"Extra: {sorted(k.value for k in extra)!r}."
        )

    allowed_types = (RoleView, InsufficientEvidence, RoleGenerationFailure)
    for mapping_key in _ROLE_EXECUTION_ORDER:
        outcome = role_outcomes[mapping_key]
        outcome_type = type(outcome)
        if outcome_type not in allowed_types:
            raise RiskInputError(
                f"role_outcomes[{mapping_key.value!r}] has unsupported outcome "
                f"type={outcome_type.__name__!r}. Expected exactly RoleView, "
                "InsufficientEvidence, or RoleGenerationFailure."
            )
        if outcome.role_key != mapping_key:
            raise RiskInputError(
                "Role outcome identity mismatch: "
                f"mapping_key={mapping_key.value!r}, "
                f"outcome_declared_role_key="
                f"{_declared_role_key_text(outcome.role_key)!r}, "
                f"outcome_type={outcome_type.__name__!r}."
            )


def _build_registry(
    evidence_objects: Sequence[EvidenceObject],
) -> dict[str, EvidenceObject]:
    """Build evidence_id → EvidenceObject registry, failing closed on conflicts."""
    registry: dict[str, EvidenceObject] = {}
    for ev in evidence_objects:
        eid = ev.evidence_id
        if eid not in registry:
            registry[eid] = ev
        else:
            existing = registry[eid]
            if existing == ev:
                # Exact duplicate — keep first, ignore redundant copy.
                continue
            # Same ID, different content.
            raise RiskInputError(
                f"Conflicting EvidenceObject records share evidence_id={eid!r}: "
                f"existing identity_digest={existing.identity_digest!r}, "
                f"new identity_digest={ev.identity_digest!r}. "
                "Do not silently repair conflicting evidence."
            )
    return registry


def _validate_role_view_citations(
    role_outcomes: Mapping[RoleKey, RoleOutcome],
    registry: dict[str, EvidenceObject],
) -> None:
    """Fail closed if any RoleView cites an unknown or invalidated evidence_id."""
    for role_key in _ROLE_EXECUTION_ORDER:
        outcome = role_outcomes[role_key]
        if not isinstance(outcome, RoleView):
            continue
        for finding in outcome.key_findings:
            for ref in finding.evidence_references:
                eid = ref.evidence_id
                if eid not in registry:
                    raise RiskInputError(
                        f"RoleView for {role_key.value!r} cites unknown "
                        f"evidence_id={eid!r}. The evidence registry must be "
                        "consistent with the role engine's input."
                    )
                ev = registry[eid]
                if ev.status != EvidenceStatus.active:
                    raise RiskInputError(
                        f"RoleView for {role_key.value!r} cites "
                        f"evidence_id={eid!r} which has status="
                        f"{ev.status.value!r}. Invalidated evidence must not "
                        "appear in a validated RoleView."
                    )


# ---------------------------------------------------------------------------
# Per-outcome risk generation
# ---------------------------------------------------------------------------


def _check_one_outcome(
    role_key: RoleKey,
    outcome: RoleOutcome,
    registry: dict[str, EvidenceObject],
) -> list[RiskFinding]:
    """Generate all RiskFinding records for one role outcome."""
    if isinstance(outcome, InsufficientEvidence):
        return [_insufficient_evidence_finding(role_key, outcome)]

    if isinstance(outcome, RoleGenerationFailure):
        return [_generation_failure_finding(role_key, outcome)]

    # outcome is a RoleView
    return _check_role_view(role_key, outcome, registry)


def _insufficient_evidence_finding(
    role_key: RoleKey, outcome: InsufficientEvidence
) -> RiskFinding:
    return RiskFinding(
        risk_code=RiskCode.insufficient_evidence,
        severity=RiskSeverity.high,
        role_key=role_key,
        claim_index=None,
        evidence_ids=[],
        message=(
            f"Role {role_key.value!r} has no eligible active evidence: "
            f"{outcome.reason}"
        ),
        required_action=(
            "Provide active evidence relevant to this role before proceeding."
        ),
        blocks_downstream=True,
        requires_human_review=True,
    )


def _generation_failure_finding(
    role_key: RoleKey, outcome: RoleGenerationFailure
) -> RiskFinding:
    return RiskFinding(
        risk_code=RiskCode.role_generation_failure,
        severity=RiskSeverity.critical,
        role_key=role_key,
        claim_index=None,
        evidence_ids=[],
        message=(
            f"Role {role_key.value!r} generation failed "
            f"(failure_code={outcome.failure_code!r}): {outcome.reason}"
        ),
        required_action=(
            "Resolve the role generation failure before downstream processing. "
            "Human review is required."
        ),
        blocks_downstream=True,
        requires_human_review=True,
    )


def _check_role_view(
    role_key: RoleKey,
    view: RoleView,
    registry: dict[str, EvidenceObject],
) -> list[RiskFinding]:
    """Generate all RiskFinding records for a successful RoleView."""
    findings: list[RiskFinding] = []

    # Claim-level checks.
    for claim_idx, grounded in enumerate(view.key_findings):
        findings.extend(
            _check_grounded_finding(
                role_key, claim_idx, grounded, registry,
                risks_or_assumptions=view.risks_or_assumptions,
            )
        )

    # Role-level action check.
    action_finding = _check_action_without_internal(role_key, view, registry)
    if action_finding:
        findings.append(action_finding)

    # Human-review bypass check.
    bypass_finding = _check_human_review_bypass(role_key, view, findings)
    if bypass_finding:
        findings.append(bypass_finding)

    return findings


def _check_grounded_finding(
    role_key: RoleKey,
    claim_idx: int,
    grounded: GroundedFinding,
    registry: dict[str, EvidenceObject],
    *,
    risks_or_assumptions: list[str],
) -> list[RiskFinding]:
    """Check one GroundedFinding for scope-based and declaration risks."""
    findings: list[RiskFinding] = []

    cited_ids = [ref.evidence_id for ref in grounded.evidence_references]
    cited_evs = [registry[eid] for eid in cited_ids]
    scopes = {ev.evidence_scope for ev in cited_evs}

    # Scope-only findings (only when internal_observation is NOT present).
    if EvidenceScope.internal_observation not in scopes:
        if scopes == {EvidenceScope.external_context}:
            findings.append(RiskFinding(
                risk_code=RiskCode.external_context_only,
                severity=RiskSeverity.medium,
                role_key=role_key,
                claim_index=claim_idx,
                evidence_ids=cited_ids,
                message=(
                    f"Claim {claim_idx} for role {role_key.value!r} is grounded "
                    "solely in external context. External context is not "
                    "company-specific proof and cannot independently validate "
                    "an internal conclusion."
                ),
                required_action=(
                    "Add at least one internal_observation evidence object to "
                    "ground this claim, or flag it as external context only."
                ),
                blocks_downstream=False,
                requires_human_review=True,
            ))
        elif scopes == {EvidenceScope.assumption}:
            findings.append(RiskFinding(
                risk_code=RiskCode.assumption_only,
                severity=RiskSeverity.high,
                role_key=role_key,
                claim_index=claim_idx,
                evidence_ids=cited_ids,
                message=(
                    f"Claim {claim_idx} for role {role_key.value!r} is grounded "
                    "solely in unverified assumptions. An unverified assumption "
                    "cannot independently support an action or company-specific "
                    "conclusion."
                ),
                required_action=(
                    "Validate this assumption with empirical evidence before "
                    "acting on this claim. Human review required."
                ),
                blocks_downstream=True,
                requires_human_review=True,
            ))
        elif scopes == {EvidenceScope.stated_priority}:
            findings.append(RiskFinding(
                risk_code=RiskCode.stated_priority_only,
                severity=RiskSeverity.medium,
                role_key=role_key,
                claim_index=claim_idx,
                evidence_ids=cited_ids,
                message=(
                    f"Claim {claim_idx} for role {role_key.value!r} is grounded "
                    "solely in stated priorities. A stated priority is not "
                    "measured performance and does not confirm execution or "
                    "outcome."
                ),
                required_action=(
                    "Supplement this claim with measured performance evidence, "
                    "or explicitly flag that it rests on stated intent only."
                ),
                blocks_downstream=False,
                requires_human_review=True,
            ))

    # Assumption-not-declared: any assumption scope + empty risks_or_assumptions.
    has_assumption = any(
        ev.evidence_scope == EvidenceScope.assumption for ev in cited_evs
    )
    if has_assumption and not risks_or_assumptions:
        findings.append(RiskFinding(
            risk_code=RiskCode.assumption_not_declared,
            severity=RiskSeverity.high,
            role_key=role_key,
            claim_index=claim_idx,
            evidence_ids=cited_ids,
            message=(
                f"Claim {claim_idx} for role {role_key.value!r} cites assumption "
                "evidence but RoleView.risks_or_assumptions is empty. Assumptions "
                "used as evidence must be declared in the role view."
            ),
            required_action=(
                "Populate risks_or_assumptions with a declaration of each "
                "assumption cited in this finding."
            ),
            blocks_downstream=True,
            requires_human_review=True,
        ))

    return findings


def _all_cited_ids_first_seen(view: RoleView) -> list[str]:
    """Collect all cited evidence_id values across all key_findings, first-seen order."""
    seen: set[str] = set()
    result: list[str] = []
    for finding in view.key_findings:
        for ref in finding.evidence_references:
            if ref.evidence_id not in seen:
                seen.add(ref.evidence_id)
                result.append(ref.evidence_id)
    return result


def _check_action_without_internal(
    role_key: RoleKey,
    view: RoleView,
    registry: dict[str, EvidenceObject],
) -> RiskFinding | None:
    """Return a risk finding if next_action is set but no internal_observation exists."""
    if view.next_action is None:
        return None

    all_ids = _all_cited_ids_first_seen(view)
    cited_evs = [registry[eid] for eid in all_ids]
    has_internal = any(
        ev.evidence_scope == EvidenceScope.internal_observation for ev in cited_evs
    )
    if has_internal:
        return None

    return RiskFinding(
        risk_code=RiskCode.action_without_internal_evidence,
        severity=RiskSeverity.high,
        role_key=role_key,
        claim_index=None,
        evidence_ids=all_ids,
        message=(
            f"Role {role_key.value!r} specifies next_action={view.next_action!r} "
            "but none of the cited evidence has scope=internal_observation. "
            "An action recommendation without internal evidence cannot proceed "
            "automatically."
        ),
        required_action=(
            "Add internal_observation evidence to justify this action, or "
            "remove the action recommendation until such evidence is available. "
            "Human review required."
        ),
        blocks_downstream=True,
        requires_human_review=True,
    )


def _check_human_review_bypass(
    role_key: RoleKey,
    view: RoleView,
    existing_findings: list[RiskFinding],
) -> RiskFinding | None:
    """If any finding requires review but human_review_required is False, create bypass finding."""
    role_findings = [f for f in existing_findings if f.role_key == role_key]
    any_requires_review = any(f.requires_human_review for f in role_findings)

    if not any_requires_review:
        return None
    if view.human_review_required:
        return None

    # Collect unique evidence IDs from existing role findings, first-seen order.
    seen: set[str] = set()
    bypass_ids: list[str] = []
    for f in role_findings:
        for eid in f.evidence_ids:
            if eid not in seen:
                seen.add(eid)
                bypass_ids.append(eid)

    return RiskFinding(
        risk_code=RiskCode.human_review_bypass,
        severity=RiskSeverity.critical,
        role_key=role_key,
        claim_index=None,
        evidence_ids=bypass_ids,
        message=(
            f"Role {role_key.value!r} has risk findings that require human review "
            "but RoleView.human_review_required is False. This is a workflow "
            "control bypass: the pipeline would proceed without required oversight."
        ),
        required_action=(
            "Set human_review_required=True on this RoleView, or resolve all "
            "findings that require human review before proceeding."
        ),
        blocks_downstream=True,
        requires_human_review=True,
    )


# ---------------------------------------------------------------------------
# Deduplication and ordering
# ---------------------------------------------------------------------------


def _deduplicate(findings: list[RiskFinding]) -> list[RiskFinding]:
    """Remove exact duplicate RiskFinding values (same field values), keep first seen."""
    seen: set[tuple] = set()
    result: list[RiskFinding] = []
    for f in findings:
        key = (
            f.risk_code, f.severity, f.role_key, f.claim_index,
            tuple(f.evidence_ids), f.message, f.required_action,
            f.blocks_downstream, f.requires_human_review,
        )
        if key not in seen:
            seen.add(key)
            result.append(f)
    return result


def _finding_sort_key(f: RiskFinding) -> tuple:
    """Sort key: role order, then claim-level before role-level, then risk-code order."""
    role_pos = next(
        i for i, k in enumerate(_ROLE_EXECUTION_ORDER) if k == f.role_key
    )
    claim_pos = f.claim_index if f.claim_index is not None else _ROLE_LEVEL_SORT_KEY
    code_pos = _RISK_CODE_ORDER.get(f.risk_code, 99)
    return (role_pos, claim_pos, code_pos)


def _sort_findings(findings: list[RiskFinding]) -> list[RiskFinding]:
    return sorted(findings, key=_finding_sort_key)
