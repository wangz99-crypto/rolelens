"""
app/role_engine.py — RoleLens provider-neutral grounded role engine (Task 6A-2).

Responsibilities:
  - Load config/role_policy.json at runtime and validate its structure.
  - For each of the five roles (in fixed execution order), filter eligible
    evidence, build a RoleRequest, call the provider, and validate the output.
  - Enforce strict citation validation on every EvidenceReference in every
    GroundedFinding.
  - Return an insertion-ordered dict[RoleKey, RoleOutcome] containing exactly
    the five role outcomes.

Architecture invariants:
  - No live LLM provider, no Granite/API calls, no prompt templates.
  - No mock provider in this module — mocks belong in tests only.
  - No parallel execution.
  - Provider output is always validated through RoleView.model_validate().
  - No citation-free fallback RoleView is ever created.
  - One role failing does not erase outcomes from other roles.
"""

from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, Sequence, Union

from pydantic import ValidationError

from app.schemas import (
    EvidenceObject,
    EvidenceStatus,
    GroundedFinding,
    RoleKey,
    RoleView,
)

# ---------------------------------------------------------------------------
# Fixed execution order — must not be changed without a policy review.
# ---------------------------------------------------------------------------

_EXECUTION_ORDER: list[RoleKey] = [
    RoleKey.executive,
    RoleKey.data_analyst,
    RoleKey.data_engineer,
    RoleKey.sales_marketing,
    RoleKey.project_manager,
]

# ---------------------------------------------------------------------------
# Typed outcomes
# ---------------------------------------------------------------------------


class EvidenceRegistryConflictError(ValueError):
    """Raised when one evidence_id identifies two different records.

    Attributes:
        evidence_id: The duplicate evidence identifier.
        existing_identity_digest: Digest on the first registered record.
        new_identity_digest: Digest on the conflicting record.
    """

    def __init__(
        self,
        evidence_id: str,
        existing_identity_digest: str,
        new_identity_digest: str,
    ) -> None:
        self.evidence_id = evidence_id
        self.existing_identity_digest = existing_identity_digest
        self.new_identity_digest = new_identity_digest
        super().__init__(
            f"Conflicting EvidenceObject records share evidence_id={evidence_id!r}: "
            f"existing_identity_digest={existing_identity_digest!r}, "
            f"new_identity_digest={new_identity_digest!r}."
        )


@dataclass(frozen=True)
class InsufficientEvidence:
    """Returned when a role has zero eligible evidence.

    The provider is not called.  No citation-free RoleView is created.
    """

    role_key: RoleKey
    reason: str


@dataclass(frozen=True)
class RoleGenerationFailure:
    """Returned when provider output cannot be validated.

    failure_code is one of:
      provider_error              — the provider raised an exception
      invalid_output              — RoleView.model_validate() rejected the output
      role_mismatch               — output.role_key != requested role
      unknown_evidence_reference  — cited evidence_id not in global registry
      inactive_evidence_reference — cited evidence exists but is invalidated
      hidden_evidence_reference   — cited evidence active but not exposed to provider
    """

    role_key: RoleKey
    failure_code: str
    reason: str

    _VALID_CODES: frozenset[str] = field(
        default=frozenset({
            "provider_error",
            "invalid_output",
            "role_mismatch",
            "unknown_evidence_reference",
            "inactive_evidence_reference",
            "hidden_evidence_reference",
        }),
        init=False,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        if self.failure_code not in self._VALID_CODES:
            raise ValueError(
                f"RoleGenerationFailure.failure_code must be one of "
                f"{sorted(self._VALID_CODES)!r}, got {self.failure_code!r}"
            )


# Union of all possible outcomes for one role.
RoleOutcome = Union[RoleView, InsufficientEvidence, RoleGenerationFailure]


# ---------------------------------------------------------------------------
# Provider contract
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RoleRequest:
    """Immutable bundle passed to a RoleProvider.

    Attributes:
        role_key:             The role being generated.
        role_policy:          The policy definition for this role (dict from JSON).
        inputs:               Policy-filtered inputs for this role.
        exposed_evidence_ids: frozenset of evidence_id values that were placed in
                              the inputs.  The engine uses this to validate citations.
    """

    role_key: RoleKey
    role_policy: Mapping[str, Any]
    inputs: Mapping[str, Any]
    exposed_evidence_ids: frozenset[str]


class RoleProvider(Protocol):
    """Provider-neutral contract for generating a role view.

    The provider receives a RoleRequest and returns a raw structured mapping
    that will be validated through RoleView.model_validate().

    Implementations must not construct RoleView themselves — the engine owns
    that validation step.
    """

    def generate_role_view(self, request: RoleRequest) -> Mapping[str, Any]:
        ...


# ---------------------------------------------------------------------------
# Policy loading and validation
# ---------------------------------------------------------------------------

_DEFAULT_POLICY_PATH = pathlib.Path(__file__).parent.parent / "config" / "role_policy.json"

_REQUIRED_ROLE_KEYS: frozenset[str] = frozenset(k.value for k in RoleKey)


def load_policy(path: pathlib.Path = _DEFAULT_POLICY_PATH) -> dict[str, Any]:
    """Load and structurally validate config/role_policy.json.

    Fails closed: raises RuntimeError on any structural issue.
    """
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeError(
            f"role_engine: cannot read policy file {path}: {exc}"
        ) from exc

    try:
        policy = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"role_engine: policy file {path} is not valid JSON: {exc}"
        ) from exc

    if "roles" not in policy:
        raise RuntimeError(
            f"role_engine: policy file {path} is missing top-level 'roles' key"
        )

    policy_keys = set(policy["roles"].keys())
    if policy_keys != _REQUIRED_ROLE_KEYS:
        raise RuntimeError(
            f"role_engine: policy role keys {sorted(policy_keys)!r} do not exactly "
            f"match required {sorted(_REQUIRED_ROLE_KEYS)!r}"
        )

    for role_key, role_def in policy["roles"].items():
        if "allowed_inputs" not in role_def:
            raise RuntimeError(
                f"role_engine: role {role_key!r} is missing 'allowed_inputs' in policy"
            )
        if "required_outputs" not in role_def:
            raise RuntimeError(
                f"role_engine: role {role_key!r} is missing 'required_outputs' in policy"
            )

    return policy


# ---------------------------------------------------------------------------
# Evidence registry helpers
# ---------------------------------------------------------------------------


def _build_evidence_registry(
    evidence_objects: Sequence[EvidenceObject],
) -> dict[str, EvidenceObject]:
    """Build a fail-closed evidence_id registry for O(1) citation lookup.

    Exact duplicate records retain the first occurrence. If a repeated
    evidence_id has any different EvidenceObject field, the engine input is
    invalid and processing stops before any provider call.
    """
    registry: dict[str, EvidenceObject] = {}
    for evidence in evidence_objects:
        existing = registry.get(evidence.evidence_id)
        if existing is None:
            registry[evidence.evidence_id] = evidence
            continue
        if existing == evidence:
            continue
        raise EvidenceRegistryConflictError(
            evidence_id=evidence.evidence_id,
            existing_identity_digest=existing.identity_digest,
            new_identity_digest=evidence.identity_digest,
        )
    return registry


def _eligible_evidence(
    role_key: RoleKey,
    evidence_objects: Sequence[EvidenceObject],
) -> list[EvidenceObject]:
    """Return evidence that is active and mentions role_key.value in relevant_roles."""
    return [
        ev for ev in evidence_objects
        if ev.status == EvidenceStatus.active
        and role_key.value in ev.relevant_roles
    ]


# ---------------------------------------------------------------------------
# Citation validation
# ---------------------------------------------------------------------------


def _validate_citations(
    role_key: RoleKey,
    key_findings: list[GroundedFinding],
    registry: dict[str, EvidenceObject],
    exposed_ids: frozenset[str],
) -> RoleGenerationFailure | None:
    """Validate all evidence citations in a list of GroundedFinding records.

    Returns RoleGenerationFailure on the first violation found, or None if all
    citations are valid.

    Checks in order:
      1. evidence_id not in registry           → unknown_evidence_reference
      2. evidence is invalidated               → inactive_evidence_reference
      3. evidence active but not exposed       → hidden_evidence_reference
    """
    for finding in key_findings:
        for ref in finding.evidence_references:
            ev_id = ref.evidence_id
            if ev_id not in registry:
                return RoleGenerationFailure(
                    role_key=role_key,
                    failure_code="unknown_evidence_reference",
                    reason=(
                        f"Evidence ID {ev_id!r} cited by role {role_key.value!r} "
                        "does not exist in the global evidence registry."
                    ),
                )
            ev = registry[ev_id]
            if ev.status != EvidenceStatus.active:
                return RoleGenerationFailure(
                    role_key=role_key,
                    failure_code="inactive_evidence_reference",
                    reason=(
                        f"Evidence ID {ev_id!r} cited by role {role_key.value!r} "
                        f"has status={ev.status.value!r} and may not be cited."
                    ),
                )
            if ev_id not in exposed_ids:
                return RoleGenerationFailure(
                    role_key=role_key,
                    failure_code="hidden_evidence_reference",
                    reason=(
                        f"Evidence ID {ev_id!r} cited by role {role_key.value!r} "
                        "was not included in the provider's exposed evidence set."
                    ),
                )
    return None


# ---------------------------------------------------------------------------
# Single-role execution
# ---------------------------------------------------------------------------


def _run_one_role(
    role_key: RoleKey,
    role_def: dict[str, Any],
    provider: RoleProvider,
    available_inputs: Mapping[str, Any],
    evidence_objects: Sequence[EvidenceObject],
    registry: dict[str, EvidenceObject],
) -> RoleOutcome:
    """Execute one non-PM role and return a typed outcome."""
    allowed_inputs: list[str] = role_def["allowed_inputs"]

    # Filter eligible evidence for this role.
    eligible = _eligible_evidence(role_key, evidence_objects)
    if not eligible:
        return InsufficientEvidence(
            role_key=role_key,
            reason=(
                f"Role {role_key.value!r} has no eligible active evidence. "
                "No provider call was made."
            ),
        )

    # Build the policy-filtered inputs dict.
    filtered_inputs: dict[str, Any] = {}
    for key in allowed_inputs:
        if key == "evidence_objects":
            filtered_inputs["evidence_objects"] = eligible
        elif key in available_inputs:
            filtered_inputs[key] = available_inputs[key]

    exposed_ids = frozenset(ev.evidence_id for ev in eligible)

    request = RoleRequest(
        role_key=role_key,
        role_policy=role_def,
        inputs=filtered_inputs,
        exposed_evidence_ids=exposed_ids,
    )

    # Call provider, catching all exceptions.
    try:
        raw_output = provider.generate_role_view(request)
    except Exception as exc:
        return RoleGenerationFailure(
            role_key=role_key,
            failure_code="provider_error",
            reason=f"Provider raised an exception for role {role_key.value!r}: {exc}",
        )

    # Validate provider output through RoleView schema.
    try:
        view = RoleView.model_validate(raw_output)
    except (ValidationError, Exception) as exc:
        return RoleGenerationFailure(
            role_key=role_key,
            failure_code="invalid_output",
            reason=(
                f"Provider output for role {role_key.value!r} failed schema "
                f"validation: {exc}"
            ),
        )

    # Check role_key match.
    if view.role_key != role_key:
        return RoleGenerationFailure(
            role_key=role_key,
            failure_code="role_mismatch",
            reason=(
                f"Provider returned role_key={view.role_key.value!r} but "
                f"expected {role_key.value!r}."
            ),
        )

    # Validate citations.
    citation_failure = _validate_citations(
        role_key=role_key,
        key_findings=list(view.key_findings),
        registry=registry,
        exposed_ids=exposed_ids,
    )
    if citation_failure is not None:
        return citation_failure

    return view


def _run_project_manager(
    role_def: dict[str, Any],
    provider: RoleProvider,
    available_inputs: Mapping[str, Any],
    prior_outcomes: dict[RoleKey, RoleOutcome],
    registry: dict[str, EvidenceObject],
) -> RoleOutcome:
    """Execute the Project Manager role after the first four roles."""
    role_key = RoleKey.project_manager
    allowed_inputs: list[str] = role_def["allowed_inputs"]

    # Collect successful prior RoleViews.
    successful_views: list[RoleView] = [
        outcome for outcome in prior_outcomes.values()
        if isinstance(outcome, RoleView)
    ]

    # Collect exposed evidence IDs: union of all cited IDs in prior RoleViews.
    exposed_ids: frozenset[str] = frozenset(
        ref.evidence_id
        for view in successful_views
        for finding in view.key_findings
        for ref in finding.evidence_references
    )

    if not successful_views or not exposed_ids:
        return InsufficientEvidence(
            role_key=role_key,
            reason=(
                "Project Manager requires at least one successful prior RoleView "
                "with cited evidence. No provider call was made."
            ),
        )

    # Aggregate missing_information from successful views, preserving first-seen order.
    seen: set[str] = set()
    aggregated_missing: list[str] = []
    for view in successful_views:
        for item in view.missing_information:
            if item not in seen:
                seen.add(item)
                aggregated_missing.append(item)

    # Build policy-filtered inputs.
    filtered_inputs: dict[str, Any] = {}
    for key in allowed_inputs:
        if key == "role_views":
            filtered_inputs["role_views"] = successful_views
        elif key == "missing_information":
            filtered_inputs["missing_information"] = aggregated_missing
        elif key in available_inputs:
            filtered_inputs[key] = available_inputs[key]

    request = RoleRequest(
        role_key=role_key,
        role_policy=role_def,
        inputs=filtered_inputs,
        exposed_evidence_ids=exposed_ids,
    )

    # Call provider.
    try:
        raw_output = provider.generate_role_view(request)
    except Exception as exc:
        return RoleGenerationFailure(
            role_key=role_key,
            failure_code="provider_error",
            reason=f"Provider raised an exception for role {role_key.value!r}: {exc}",
        )

    # Validate output.
    try:
        view = RoleView.model_validate(raw_output)
    except (ValidationError, Exception) as exc:
        return RoleGenerationFailure(
            role_key=role_key,
            failure_code="invalid_output",
            reason=(
                f"Provider output for role {role_key.value!r} failed schema "
                f"validation: {exc}"
            ),
        )

    # Check role_key match.
    if view.role_key != role_key:
        return RoleGenerationFailure(
            role_key=role_key,
            failure_code="role_mismatch",
            reason=(
                f"Provider returned role_key={view.role_key.value!r} but "
                f"expected {role_key.value!r}."
            ),
        )

    # Validate citations against the PM's allowed exposed IDs.
    citation_failure = _validate_citations(
        role_key=role_key,
        key_findings=list(view.key_findings),
        registry=registry,
        exposed_ids=exposed_ids,
    )
    if citation_failure is not None:
        return citation_failure

    return view


# ---------------------------------------------------------------------------
# Public engine function
# ---------------------------------------------------------------------------


def run_role_engine(
    provider: RoleProvider,
    evidence_objects: Sequence[EvidenceObject],
    available_inputs: Mapping[str, Any],
    policy_path: pathlib.Path = _DEFAULT_POLICY_PATH,
) -> dict[RoleKey, RoleOutcome]:
    """Run all five roles in fixed execution order and return typed outcomes.

    Args:
        provider:          Provider-neutral RoleProvider implementation.
        evidence_objects:  All EvidenceObject records for this run.
        available_inputs:  Pipeline inputs (data_health_summary, strategy_profile,
                           business_question, risk_results, etc.).  Keys not in a
                           role's allowed_inputs are silently excluded.
        policy_path:       Path to role_policy.json.  Defaults to the production
                           config/role_policy.json relative to this file.

    Returns:
        Insertion-ordered dict[RoleKey, RoleOutcome] with exactly five entries
        in the fixed execution order.
    """
    policy = load_policy(policy_path)
    roles_def: dict[str, Any] = policy["roles"]

    registry = _build_evidence_registry(evidence_objects)
    outcomes: dict[RoleKey, RoleOutcome] = {}

    # Run the first four roles in fixed execution order.
    for role_key in _EXECUTION_ORDER[:4]:
        role_def = roles_def[role_key.value]
        outcomes[role_key] = _run_one_role(
            role_key=role_key,
            role_def=role_def,
            provider=provider,
            available_inputs=available_inputs,
            evidence_objects=evidence_objects,
            registry=registry,
        )

    # Run the Project Manager last.
    pm_def = roles_def[RoleKey.project_manager.value]
    outcomes[RoleKey.project_manager] = _run_project_manager(
        role_def=pm_def,
        provider=provider,
        available_inputs=available_inputs,
        prior_outcomes=outcomes,
        registry=registry,
    )

    return outcomes
