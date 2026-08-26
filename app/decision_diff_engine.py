"""Generic deterministic dependency propagation for the DD-2 spike.

The engine compares two complete DD-1 assumption revisions, reuses the DD-1
calculator, and propagates declared impacts through an explicit acyclic graph.
It performs no I/O and has no product-pipeline integrations.
"""

from __future__ import annotations

import heapq
import re
from collections.abc import Sequence
from decimal import Decimal
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator, model_validator

from app.decision_diff import (
    DecisionDiffInputError,
    ScenarioAssumption,
    ScenarioResult,
    ScenarioStatus,
    calculate_break_even_scenario,
)


class DecisionDiffEngineError(ValueError):
    """Raised when public DD-2 engine inputs fail closed validation."""


class _EngineContract(BaseModel):
    """Frozen, extra-forbidding base for local DD-2 contracts."""

    model_config = ConfigDict(extra="forbid", frozen=True)


_ASSUMPTION_ID_RE = re.compile(r"^asm-[0-9]{3}$")
_REVISION_ID_RE = re.compile(r"^rev-[0-9]{3}$")
_SCENARIO_ID_RE = re.compile(r"^scn-[0-9]{3}$")
_OBJECT_ID_RE = re.compile(r"^obj-[a-z0-9][a-z0-9-]{2,63}$")
_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")

_SCENARIO_KEYS = (
    "pilot_population",
    "expected_incremental_lift",
    "cost_per_intervention",
    "retained_customer_value",
)
_SCENARIO_STATUS_VALUES = frozenset(status.value for status in ScenarioStatus)

_ObjectType = Literal[
    "scenario_result",
    "executive_posture",
    "sales_posture",
    "project_manager_handoff",
    "decision_brief",
    "observed_evidence",
    "data_health",
    "source_provenance",
]
_ScenarioKey = Literal[
    "pilot_population",
    "expected_incremental_lift",
    "cost_per_intervention",
    "retained_customer_value",
]


def _is_dependency_ref(value: str) -> bool:
    """Return whether a string is a supported assumption or object reference."""
    return (
        _ASSUMPTION_ID_RE.fullmatch(value) is not None
        or _OBJECT_ID_RE.fullmatch(value) is not None
    )


class DecisionImpactType(str, Enum):
    """Possible propagation outcomes for one dependency node."""

    UNCHANGED = "UNCHANGED"
    RECOMPUTED = "RECOMPUTED"
    INVALIDATED = "INVALIDATED"
    BLOCKED = "BLOCKED"
    STALE = "STALE"


class DecisionImpactPolicy(str, Enum):
    """Metadata-declared policy for reacting to direct dependency changes."""

    ALWAYS_UNCHANGED = "ALWAYS_UNCHANGED"
    RECOMPUTE_ON_DEPENDENCY_CHANGE = "RECOMPUTE_ON_DEPENDENCY_CHANGE"
    BLOCK_IF_SCENARIO_NOT_CLEAR = "BLOCK_IF_SCENARIO_NOT_CLEAR"
    STALE_ON_DEPENDENCY_CHANGE = "STALE_ON_DEPENDENCY_CHANGE"
    INVALIDATE_ON_DEPENDENCY_CHANGE = "INVALIDATE_ON_DEPENDENCY_CHANGE"


class DecisionDependencyNode(_EngineContract):
    """One artifact and its explicit direct dependency metadata."""

    object_id: str
    object_type: _ObjectType
    dependency_refs: tuple[str, ...]
    impact_policy: DecisionImpactPolicy

    @field_validator("object_id")
    @classmethod
    def object_id_is_valid(cls, value: str) -> str:
        """Require the stable DD-2 object-ID syntax."""
        if _OBJECT_ID_RE.fullmatch(value) is None:
            raise ValueError("object_id must match ^obj-[a-z0-9][a-z0-9-]{2,63}$")
        return value

    @field_validator("dependency_refs")
    @classmethod
    def dependency_refs_are_valid(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """Require unique, syntactically valid dependency references."""
        if any(not isinstance(ref, str) or not ref.strip() for ref in value):
            raise ValueError("dependency_refs must not contain blank references")
        if any(not _is_dependency_ref(ref) for ref in value):
            raise ValueError("dependency_refs contain an unsupported reference")
        if len(value) != len(set(value)):
            raise ValueError("dependency_refs must not contain duplicates")
        return value

    @model_validator(mode="after")
    def dependency_policy_is_consistent(self) -> "DecisionDependencyNode":
        """Enforce root and dependency-driven policy cardinality."""
        if self.object_id in self.dependency_refs:
            raise ValueError("an object cannot depend on itself")
        if self.impact_policy is DecisionImpactPolicy.ALWAYS_UNCHANGED:
            if self.dependency_refs:
                raise ValueError("ALWAYS_UNCHANGED nodes must have zero dependencies")
        elif not self.dependency_refs:
            raise ValueError("dependency-driven nodes require at least one dependency")
        return self


class DecisionDependencyRegistry(_EngineContract):
    """A validated directed acyclic dependency graph."""

    nodes: tuple[DecisionDependencyNode, ...]

    @model_validator(mode="after")
    def graph_is_valid(self) -> "DecisionDependencyRegistry":
        """Require unique nodes, resolved object refs, and an acyclic graph."""
        if not self.nodes:
            raise ValueError("nodes must contain at least one dependency node")
        object_ids = [node.object_id for node in self.nodes]
        if len(object_ids) != len(set(object_ids)):
            raise ValueError("registry object_ids must be unique")
        known_ids = set(object_ids)
        object_dependencies: dict[str, tuple[str, ...]] = {}
        for node in self.nodes:
            refs = tuple(
                ref for ref in node.dependency_refs if _OBJECT_ID_RE.fullmatch(ref)
            )
            if any(ref not in known_ids for ref in refs):
                raise ValueError("all object dependency refs must resolve in the registry")
            object_dependencies[node.object_id] = refs

        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(object_id: str) -> None:
            if object_id in visiting:
                raise ValueError("dependency registry must not contain cycles")
            if object_id in visited:
                return
            visiting.add(object_id)
            for dependency_id in object_dependencies[object_id]:
                visit(dependency_id)
            visiting.remove(object_id)
            visited.add(object_id)

        for object_id in sorted(known_ids):
            visit(object_id)
        return self


class ChangedScenarioAssumption(_EngineContract):
    """A value-only change to one stable logical scenario assumption."""

    assumption_id: str
    key: _ScenarioKey
    before_value: Decimal
    after_value: Decimal
    unit: str
    currency: str | None

    @field_validator("assumption_id")
    @classmethod
    def assumption_id_is_valid(cls, value: str) -> str:
        """Require the DD-1 stable assumption-ID syntax."""
        if _ASSUMPTION_ID_RE.fullmatch(value) is None:
            raise ValueError("assumption_id must match ^asm-[0-9]{3}$")
        return value

    @field_validator("before_value", "after_value")
    @classmethod
    def values_are_finite(cls, value: Decimal) -> Decimal:
        """Reject non-finite changed values."""
        if not value.is_finite():
            raise ValueError("changed assumption values must be finite")
        return value

    @field_validator("unit")
    @classmethod
    def unit_is_not_blank(cls, value: str) -> str:
        """Reject blank units."""
        if not value.strip():
            raise ValueError("unit must not be blank")
        return value

    @field_validator("currency")
    @classmethod
    def currency_is_valid(cls, value: str | None) -> str | None:
        """Reuse the explicit DD-1 three-letter currency rule."""
        if value is not None and _CURRENCY_RE.fullmatch(value) is None:
            raise ValueError("currency must match ^[A-Z]{3}$ or be None")
        return value

    @model_validator(mode="after")
    def values_are_different(self) -> "ChangedScenarioAssumption":
        """A change record must describe an actual value change."""
        if self.before_value == self.after_value:
            raise ValueError("before_value and after_value must differ")
        return self


class DecisionImpact(_EngineContract):
    """Propagation outcome for one registered decision artifact."""

    object_id: str
    object_type: _ObjectType
    impact_type: DecisionImpactType
    trigger_refs: tuple[str, ...]
    previous_status: str | None
    new_status: str | None

    @field_validator("object_id")
    @classmethod
    def object_id_is_valid(cls, value: str) -> str:
        """Require the stable DD-2 object-ID syntax."""
        if _OBJECT_ID_RE.fullmatch(value) is None:
            raise ValueError("object_id must match ^obj-[a-z0-9][a-z0-9-]{2,63}$")
        return value

    @field_validator("trigger_refs")
    @classmethod
    def trigger_refs_are_valid(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """Require unique, syntactically valid trigger references."""
        if any(not _is_dependency_ref(ref) for ref in value):
            raise ValueError("trigger_refs contain an unsupported reference")
        if len(value) != len(set(value)):
            raise ValueError("trigger_refs must not contain duplicates")
        return value

    @model_validator(mode="after")
    def impact_state_is_consistent(self) -> "DecisionImpact":
        """Keep triggers and scenario-status fields consistent with impact type."""
        if self.impact_type is DecisionImpactType.UNCHANGED:
            if self.trigger_refs:
                raise ValueError("UNCHANGED impacts must have empty trigger_refs")
        elif not self.trigger_refs:
            raise ValueError("changed impacts must have at least one trigger_ref")

        if self.object_type == "scenario_result":
            if (
                self.previous_status not in _SCENARIO_STATUS_VALUES
                or self.new_status not in _SCENARIO_STATUS_VALUES
            ):
                raise ValueError("scenario_result impacts require scenario statuses")
        elif self.previous_status is not None or self.new_status is not None:
            raise ValueError("non-scenario impacts cannot contain scenario statuses")
        return self


class DecisionDiff(_EngineContract):
    """Structured comparison and propagation result for two scenario revisions."""

    scenario_id: str
    before_revision_id: str
    after_revision_id: str
    changed_assumptions: tuple[ChangedScenarioAssumption, ...]
    before_scenario_result: ScenarioResult
    after_scenario_result: ScenarioResult
    impacts: tuple[DecisionImpact, ...]

    @field_validator("scenario_id")
    @classmethod
    def scenario_id_is_valid(cls, value: str) -> str:
        """Require the DD-1 stable scenario-ID syntax."""
        if _SCENARIO_ID_RE.fullmatch(value) is None:
            raise ValueError("scenario_id must match ^scn-[0-9]{3}$")
        return value

    @field_validator("before_revision_id", "after_revision_id")
    @classmethod
    def revision_id_is_valid(cls, value: str) -> str:
        """Require the DD-1 stable revision-ID syntax."""
        if _REVISION_ID_RE.fullmatch(value) is None:
            raise ValueError("revision IDs must match ^rev-[0-9]{3}$")
        return value

    @model_validator(mode="after")
    def diff_is_consistent(self) -> "DecisionDiff":
        """Validate revision, scenario, change, and impact relationships."""
        if self.before_revision_id == self.after_revision_id:
            raise ValueError("before and after revision IDs must differ")
        if (
            self.before_scenario_result.scenario_id != self.scenario_id
            or self.after_scenario_result.scenario_id != self.scenario_id
        ):
            raise ValueError("scenario result IDs must match scenario_id")
        if (
            self.before_scenario_result.revision_id != self.before_revision_id
            or self.after_scenario_result.revision_id != self.after_revision_id
        ):
            raise ValueError("scenario result revision IDs must match the diff")
        if (
            self.before_scenario_result.status is ScenarioStatus.NOT_EVALUABLE
            or self.after_scenario_result.status is ScenarioStatus.NOT_EVALUABLE
        ):
            raise ValueError("DecisionDiff requires evaluable scenario results")

        changed_ids = [item.assumption_id for item in self.changed_assumptions]
        changed_keys = [item.key for item in self.changed_assumptions]
        if len(changed_ids) != len(set(changed_ids)):
            raise ValueError("changed assumption IDs must be unique")
        if len(changed_keys) != len(set(changed_keys)):
            raise ValueError("changed assumption keys must be unique")
        canonical_changed_keys = [
            key for key in _SCENARIO_KEYS if key in set(changed_keys)
        ]
        if changed_keys != canonical_changed_keys:
            raise ValueError("changed assumptions must use canonical key order")

        if not self.impacts:
            raise ValueError("impacts must not be empty")
        impact_ids = [impact.object_id for impact in self.impacts]
        if len(impact_ids) != len(set(impact_ids)):
            raise ValueError("impact object IDs must be unique")
        scenario_impacts = [
            impact for impact in self.impacts if impact.object_type == "scenario_result"
        ]
        if len(scenario_impacts) != 1:
            raise ValueError("impacts must contain exactly one scenario_result")
        scenario_impact = scenario_impacts[0]
        if (
            scenario_impact.previous_status
            != self.before_scenario_result.status.value
            or scenario_impact.new_status != self.after_scenario_result.status.value
        ):
            raise ValueError("scenario impact statuses must match scenario results")
        return self


def _validated_assumption_sequence(
    assumptions: Sequence[ScenarioAssumption],
    *,
    revision_id: str,
    label: str,
) -> tuple[ScenarioAssumption, ...]:
    """Revalidate one complete assumption sequence with controlled failures."""
    if isinstance(assumptions, (str, bytes, bytearray)) or not isinstance(
        assumptions, Sequence
    ):
        raise DecisionDiffEngineError(
            f"{label} assumptions must be a sequence of ScenarioAssumption objects."
        )
    if len(assumptions) != 4:
        raise DecisionDiffEngineError(
            f"{label} assumptions must contain exactly four items."
        )
    if any(type(item) is not ScenarioAssumption for item in assumptions):
        raise DecisionDiffEngineError(
            f"{label} assumptions must contain only ScenarioAssumption objects."
        )
    try:
        validated = tuple(
            ScenarioAssumption.model_validate(item.model_dump()) for item in assumptions
        )
    except (AttributeError, ValidationError):
        raise DecisionDiffEngineError(
            f"{label} assumptions contain an invalid scenario assumption."
        ) from None
    ids = [item.assumption_id for item in validated]
    keys = [item.key for item in validated]
    if len(ids) != len(set(ids)):
        raise DecisionDiffEngineError(
            f"{label} assumptions must have unique assumption IDs."
        )
    if len(keys) != len(set(keys)) or set(keys) != set(_SCENARIO_KEYS):
        raise DecisionDiffEngineError(
            f"{label} assumptions must contain each scenario key exactly once."
        )
    if any(item.revision_id != revision_id for item in validated):
        raise DecisionDiffEngineError(
            f"{label} assumptions must match the requested revision ID."
        )
    return validated


def _validated_registry(
    registry: DecisionDependencyRegistry,
) -> DecisionDependencyRegistry:
    """Revalidate the registry without leaking Pydantic diagnostics."""
    if type(registry) is not DecisionDependencyRegistry:
        raise DecisionDiffEngineError(
            "registry must be a DecisionDependencyRegistry object."
        )
    try:
        return DecisionDependencyRegistry.model_validate(registry.model_dump())
    except (AttributeError, ValidationError):
        raise DecisionDiffEngineError("registry contains invalid dependency metadata.") from None


def _topological_nodes(
    registry: DecisionDependencyRegistry,
) -> tuple[DecisionDependencyNode, ...]:
    """Return nodes in stable topological order with object-ID tie breaking."""
    nodes_by_id = {node.object_id: node for node in registry.nodes}
    indegree = {node.object_id: 0 for node in registry.nodes}
    dependents: dict[str, list[str]] = {node.object_id: [] for node in registry.nodes}
    for node in registry.nodes:
        for ref in node.dependency_refs:
            if ref in nodes_by_id:
                indegree[node.object_id] += 1
                dependents[ref].append(node.object_id)
    ready = [object_id for object_id, degree in indegree.items() if degree == 0]
    heapq.heapify(ready)
    ordered: list[DecisionDependencyNode] = []
    while ready:
        object_id = heapq.heappop(ready)
        ordered.append(nodes_by_id[object_id])
        for dependent_id in sorted(dependents[object_id]):
            indegree[dependent_id] -= 1
            if indegree[dependent_id] == 0:
                heapq.heappush(ready, dependent_id)
    if len(ordered) != len(registry.nodes):
        raise DecisionDiffEngineError("registry dependency graph must be acyclic.")
    return tuple(ordered)


def _impact_type_for_policy(
    policy: DecisionImpactPolicy,
    *,
    dependencies_changed: bool,
    after_status: ScenarioStatus,
) -> DecisionImpactType:
    """Apply one declared impact policy without inspecting artifact identity."""
    if not dependencies_changed or policy is DecisionImpactPolicy.ALWAYS_UNCHANGED:
        return DecisionImpactType.UNCHANGED
    if policy is DecisionImpactPolicy.RECOMPUTE_ON_DEPENDENCY_CHANGE:
        return DecisionImpactType.RECOMPUTED
    if policy is DecisionImpactPolicy.BLOCK_IF_SCENARIO_NOT_CLEAR:
        if after_status is ScenarioStatus.CLEARS_BREAK_EVEN:
            return DecisionImpactType.RECOMPUTED
        return DecisionImpactType.BLOCKED
    if policy is DecisionImpactPolicy.STALE_ON_DEPENDENCY_CHANGE:
        return DecisionImpactType.STALE
    return DecisionImpactType.INVALIDATED


def _propagate_impacts(
    registry: DecisionDependencyRegistry,
    *,
    changed_assumption_ids: frozenset[str],
    before_status: ScenarioStatus,
    after_status: ScenarioStatus,
) -> tuple[DecisionImpact, ...]:
    """Propagate changes using only direct refs and declared impact policies."""
    impacts_by_id: dict[str, DecisionImpact] = {}
    ordered_impacts: list[DecisionImpact] = []
    for node in _topological_nodes(registry):
        trigger_refs = tuple(
            ref
            for ref in node.dependency_refs
            if ref in changed_assumption_ids
            or (
                ref in impacts_by_id
                and impacts_by_id[ref].impact_type is not DecisionImpactType.UNCHANGED
            )
        )
        impact_type = _impact_type_for_policy(
            node.impact_policy,
            dependencies_changed=bool(trigger_refs),
            after_status=after_status,
        )
        is_scenario = node.object_type == "scenario_result"
        impact = DecisionImpact(
            object_id=node.object_id,
            object_type=node.object_type,
            impact_type=impact_type,
            trigger_refs=trigger_refs if impact_type is not DecisionImpactType.UNCHANGED else (),
            previous_status=before_status.value if is_scenario else None,
            new_status=after_status.value if is_scenario else None,
        )
        impacts_by_id[node.object_id] = impact
        ordered_impacts.append(impact)
    return tuple(ordered_impacts)


def build_decision_diff(
    before_assumptions: Sequence[ScenarioAssumption],
    after_assumptions: Sequence[ScenarioAssumption],
    *,
    scenario_id: str,
    before_revision_id: str,
    after_revision_id: str,
    registry: DecisionDependencyRegistry,
) -> DecisionDiff:
    """Build a deterministic, metadata-driven diff between two DD-1 revisions."""
    if before_revision_id == after_revision_id:
        raise DecisionDiffEngineError("before and after revision IDs must differ.")
    before = _validated_assumption_sequence(
        before_assumptions,
        revision_id=before_revision_id,
        label="before",
    )
    after = _validated_assumption_sequence(
        after_assumptions,
        revision_id=after_revision_id,
        label="after",
    )
    before_by_id = {item.assumption_id: item for item in before}
    after_by_id = {item.assumption_id: item for item in after}
    if set(before_by_id) != set(after_by_id):
        raise DecisionDiffEngineError(
            "Before and after revisions must contain the same assumption IDs."
        )
    for assumption_id in sorted(before_by_id):
        before_item = before_by_id[assumption_id]
        after_item = after_by_id[assumption_id]
        if before_item.key != after_item.key:
            raise DecisionDiffEngineError(
                "A stable assumption ID must keep the same scenario key."
            )
        if before_item.unit != after_item.unit:
            raise DecisionDiffEngineError(
                "A scenario revision must not change an assumption unit."
            )
        if before_item.currency != after_item.currency:
            raise DecisionDiffEngineError(
                "A scenario revision must not change an assumption currency."
            )
        if (
            before_item.source_scope != "user_assumption"
            or after_item.source_scope != "user_assumption"
        ):
            raise DecisionDiffEngineError(
                "Scenario revisions require user_assumption source scope."
            )

    try:
        before_result = calculate_break_even_scenario(
            before,
            scenario_id=scenario_id,
            revision_id=before_revision_id,
        )
        after_result = calculate_break_even_scenario(
            after,
            scenario_id=scenario_id,
            revision_id=after_revision_id,
        )
    except (DecisionDiffInputError, ValidationError):
        raise DecisionDiffEngineError(
            "Scenario revisions could not be evaluated with the supplied inputs."
        ) from None
    if (
        before_result.status is ScenarioStatus.NOT_EVALUABLE
        or after_result.status is ScenarioStatus.NOT_EVALUABLE
    ):
        raise DecisionDiffEngineError(
            "Decision Diff requires two complete evaluable scenario revisions."
        )

    changed: list[ChangedScenarioAssumption] = []
    for key in _SCENARIO_KEYS:
        before_item = next(item for item in before if item.key == key)
        after_item = after_by_id[before_item.assumption_id]
        if before_item.value != after_item.value:
            changed.append(
                ChangedScenarioAssumption(
                    assumption_id=before_item.assumption_id,
                    key=before_item.key,
                    before_value=before_item.value,
                    after_value=after_item.value,
                    unit=before_item.unit,
                    currency=before_item.currency,
                )
            )

    validated_registry = _validated_registry(registry)
    stable_assumption_ids = frozenset(before_by_id)
    for node in validated_registry.nodes:
        unknown_refs = [
            ref
            for ref in node.dependency_refs
            if _ASSUMPTION_ID_RE.fullmatch(ref) and ref not in stable_assumption_ids
        ]
        if unknown_refs:
            raise DecisionDiffEngineError(
                "registry contains an unknown scenario assumption reference."
            )

    scenario_nodes = [
        node
        for node in validated_registry.nodes
        if node.object_type == "scenario_result"
    ]
    if len(scenario_nodes) != 1:
        raise DecisionDiffEngineError(
            "registry must contain exactly one scenario_result node."
        )
    scenario_node = scenario_nodes[0]
    if (
        scenario_node.impact_policy
        is not DecisionImpactPolicy.RECOMPUTE_ON_DEPENDENCY_CHANGE
        or len(scenario_node.dependency_refs) != 4
        or set(scenario_node.dependency_refs) != stable_assumption_ids
        or any(_OBJECT_ID_RE.fullmatch(ref) for ref in scenario_node.dependency_refs)
    ):
        raise DecisionDiffEngineError(
            "scenario_result node must depend on all four assumptions and use "
            "RECOMPUTE_ON_DEPENDENCY_CHANGE."
        )

    impacts = _propagate_impacts(
        validated_registry,
        changed_assumption_ids=frozenset(item.assumption_id for item in changed),
        before_status=before_result.status,
        after_status=after_result.status,
    )
    if (
        len(impacts) != len(validated_registry.nodes)
        or {impact.object_id for impact in impacts}
        != {node.object_id for node in validated_registry.nodes}
    ):
        raise DecisionDiffEngineError(
            "propagation must produce exactly one impact per registry node."
        )
    try:
        return DecisionDiff(
            scenario_id=scenario_id,
            before_revision_id=before_revision_id,
            after_revision_id=after_revision_id,
            changed_assumptions=tuple(changed),
            before_scenario_result=before_result,
            after_scenario_result=after_result,
            impacts=impacts,
        )
    except ValidationError:
        raise DecisionDiffEngineError(
            "Decision Diff output failed internal contract validation."
        ) from None
