"""Offline contract and propagation tests for experimental DD-2.

Exactly 10 top-level test functions. No external service is used.
"""

from __future__ import annotations

import ast
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from app.decision_diff import (
    ScenarioAssumption,
    ScenarioStatus,
    calculate_break_even_scenario,
)
from app.decision_diff_engine import (
    ChangedScenarioAssumption,
    DecisionDependencyNode,
    DecisionDependencyRegistry,
    DecisionDiff,
    DecisionDiffEngineError,
    DecisionImpact,
    DecisionImpactPolicy,
    DecisionImpactType,
    build_decision_diff,
)


_ROOT = Path(__file__).parent.parent


def _assumption(
    assumption_id: str,
    revision_id: str,
    key: str,
    value: str,
    unit: str,
    currency: str | None,
) -> ScenarioAssumption:
    """Build one exact DD-1 assumption for an engine fixture."""
    return ScenarioAssumption(
        assumption_id=assumption_id,
        revision_id=revision_id,
        key=key,
        value=Decimal(value),
        unit=unit,
        currency=currency,
    )


def _scenario_assumptions(
    revision_id: str,
    *,
    lift: str = "0.08",
) -> tuple[ScenarioAssumption, ...]:
    """Return the four stable logical inputs for one revision."""
    return (
        _assumption(
            "asm-001", revision_id, "pilot_population", "500", "customers", None
        ),
        _assumption(
            "asm-002",
            revision_id,
            "expected_incremental_lift",
            lift,
            "fraction",
            None,
        ),
        _assumption(
            "asm-003",
            revision_id,
            "cost_per_intervention",
            "30",
            "currency_per_customer",
            "USD",
        ),
        _assumption(
            "asm-004",
            revision_id,
            "retained_customer_value",
            "500",
            "currency_per_customer",
            "USD",
        ),
    )


def _node(
    object_id: str,
    object_type: str,
    dependencies: tuple[str, ...],
    policy: DecisionImpactPolicy,
) -> DecisionDependencyNode:
    """Build one dependency node for test fixture assembly."""
    return DecisionDependencyNode(
        object_id=object_id,
        object_type=object_type,
        dependency_refs=dependencies,
        impact_policy=policy,
    )


def _hero_registry() -> DecisionDependencyRegistry:
    """Assemble the DD-2 Hero graph from generic production contracts."""
    unchanged = DecisionImpactPolicy.ALWAYS_UNCHANGED
    recompute = DecisionImpactPolicy.RECOMPUTE_ON_DEPENDENCY_CHANGE
    return DecisionDependencyRegistry(
        nodes=(
            _node("obj-observed-churn", "observed_evidence", (), unchanged),
            _node("obj-segment-evidence", "observed_evidence", (), unchanged),
            _node("obj-data-health", "data_health", (), unchanged),
            _node("obj-source-provenance", "source_provenance", (), unchanged),
            _node(
                "obj-break-even",
                "scenario_result",
                ("asm-001", "asm-002", "asm-003", "asm-004"),
                recompute,
            ),
            _node(
                "obj-executive-posture",
                "executive_posture",
                ("obj-break-even",),
                recompute,
            ),
            _node(
                "obj-sales-posture",
                "sales_posture",
                ("obj-break-even", "obj-executive-posture"),
                DecisionImpactPolicy.BLOCK_IF_SCENARIO_NOT_CLEAR,
            ),
            _node(
                "obj-pm-handoff",
                "project_manager_handoff",
                ("obj-executive-posture", "obj-sales-posture"),
                recompute,
            ),
            _node(
                "obj-decision-brief",
                "decision_brief",
                ("obj-break-even", "obj-pm-handoff"),
                DecisionImpactPolicy.STALE_ON_DEPENDENCY_CHANGE,
            ),
        )
    )


def _build(after_lift: str = "0.03") -> DecisionDiff:
    """Build the standard rev-001 to rev-002 Hero diff."""
    return build_decision_diff(
        _scenario_assumptions("rev-001", lift="0.08"),
        _scenario_assumptions("rev-002", lift=after_lift),
        scenario_id="scn-001",
        before_revision_id="rev-001",
        after_revision_id="rev-002",
        registry=_hero_registry(),
    )


def _impact_map(diff: DecisionDiff) -> dict[str, DecisionImpact]:
    """Index impacts by object ID for order-independent assertions."""
    return {impact.object_id: impact for impact in diff.impacts}


def test_dd2_contracts_are_frozen_extra_forbidding_and_fail_closed() -> None:
    """All public models reject mutation, extras, and malformed required state."""
    diff = _build()
    node = _hero_registry().nodes[0]
    registry = _hero_registry()
    changed = diff.changed_assumptions[0]
    impact = diff.impacts[0]
    models = (node, registry, changed, impact, diff)
    for model in models:
        with pytest.raises(ValidationError):
            model.model_validate({**model.model_dump(), "unexpected": True})
        with pytest.raises(ValidationError):
            model.__setattr__(next(iter(model.model_fields)), "changed")

    with pytest.raises(ValidationError):
        ChangedScenarioAssumption(
            assumption_id="asm-002",
            key="expected_incremental_lift",
            before_value=Decimal("0.08"),
            after_value=Decimal("0.08"),
            unit="fraction",
            currency=None,
        )
    with pytest.raises(ValidationError):
        DecisionImpact(
            object_id="obj-example-node",
            object_type="decision_brief",
            impact_type=DecisionImpactType.STALE,
            trigger_refs=(),
            previous_status=None,
            new_status=None,
        )
    with pytest.raises(ValidationError):
        DecisionDiff.model_validate(
            {**diff.model_dump(), "after_revision_id": "rev-001"}
        )


def test_hero_eight_to_three_detects_one_change_and_exact_scenarios() -> None:
    """The Hero diff detects only asm-002 and preserves exact DD-1 results."""
    diff = _build("0.03")
    assert diff.changed_assumptions == (
        ChangedScenarioAssumption(
            assumption_id="asm-002",
            key="expected_incremental_lift",
            before_value=Decimal("0.08"),
            after_value=Decimal("0.03"),
            unit="fraction",
            currency=None,
        ),
    )
    assert diff.before_scenario_result.net_scenario_value == Decimal("5000.00")
    assert diff.before_scenario_result.status is ScenarioStatus.CLEARS_BREAK_EVEN
    assert diff.after_scenario_result.net_scenario_value == Decimal("-7500.00")
    assert (
        diff.after_scenario_result.status
        is ScenarioStatus.DOES_NOT_CLEAR_BREAK_EVEN
    )


def test_hero_eight_to_three_has_exact_propagated_impact_map() -> None:
    """The declared Hero policies block Sales and stale the Decision Brief."""
    impacts = _impact_map(_build("0.03"))
    expected_types = {
        "obj-observed-churn": DecisionImpactType.UNCHANGED,
        "obj-segment-evidence": DecisionImpactType.UNCHANGED,
        "obj-data-health": DecisionImpactType.UNCHANGED,
        "obj-source-provenance": DecisionImpactType.UNCHANGED,
        "obj-break-even": DecisionImpactType.RECOMPUTED,
        "obj-executive-posture": DecisionImpactType.RECOMPUTED,
        "obj-sales-posture": DecisionImpactType.BLOCKED,
        "obj-pm-handoff": DecisionImpactType.RECOMPUTED,
        "obj-decision-brief": DecisionImpactType.STALE,
    }
    assert {key: value.impact_type for key, value in impacts.items()} == expected_types
    assert impacts["obj-break-even"].trigger_refs == ("asm-002",)
    assert impacts["obj-break-even"].previous_status == "CLEARS_BREAK_EVEN"
    assert impacts["obj-break-even"].new_status == "DOES_NOT_CLEAR_BREAK_EVEN"
    assert impacts["obj-executive-posture"].trigger_refs == ("obj-break-even",)
    assert impacts["obj-sales-posture"].trigger_refs == (
        "obj-break-even",
        "obj-executive-posture",
    )
    assert impacts["obj-pm-handoff"].trigger_refs == (
        "obj-executive-posture",
        "obj-sales-posture",
    )
    assert impacts["obj-decision-brief"].trigger_refs == (
        "obj-break-even",
        "obj-pm-handoff",
    )
    assert all(
        impact.previous_status is None and impact.new_status is None
        for impact in impacts.values()
        if impact.object_type != "scenario_result"
    )


def test_hero_roots_remain_unchanged_without_triggers() -> None:
    """Observed facts, health, and provenance do not depend on the scenario."""
    impacts = _impact_map(_build("0.03"))
    root_ids = (
        "obj-observed-churn",
        "obj-segment-evidence",
        "obj-data-health",
        "obj-source-provenance",
    )
    for object_id in root_ids:
        assert impacts[object_id].impact_type is DecisionImpactType.UNCHANGED
        assert impacts[object_id].trigger_refs == ()


def test_eight_to_seven_recomputes_sales_and_propagates_downstream() -> None:
    """Sales is recomputed, not blocked, when the revised scenario still clears."""
    diff = _build("0.07")
    impacts = _impact_map(diff)
    assert diff.after_scenario_result.net_scenario_value == Decimal("2500.00")
    assert diff.after_scenario_result.status is ScenarioStatus.CLEARS_BREAK_EVEN
    expected = {
        "obj-break-even": DecisionImpactType.RECOMPUTED,
        "obj-executive-posture": DecisionImpactType.RECOMPUTED,
        "obj-sales-posture": DecisionImpactType.RECOMPUTED,
        "obj-pm-handoff": DecisionImpactType.RECOMPUTED,
        "obj-decision-brief": DecisionImpactType.STALE,
    }
    assert {object_id: impacts[object_id].impact_type for object_id in expected} == expected
    assert all(
        impacts[object_id].impact_type is DecisionImpactType.UNCHANGED
        for object_id in (
            "obj-observed-churn",
            "obj-segment-evidence",
            "obj-data-health",
            "obj-source-provenance",
        )
    )


def test_identical_values_produce_no_changes_and_all_nodes_unchanged() -> None:
    """Different revision IDs with equal values create a fully unchanged diff."""
    diff = _build("0.08")
    assert diff.changed_assumptions == ()
    assert all(
        impact.impact_type is DecisionImpactType.UNCHANGED
        and impact.trigger_refs == ()
        for impact in diff.impacts
    )
    scenario_impact = next(
        impact for impact in diff.impacts if impact.object_type == "scenario_result"
    )
    assert scenario_impact.previous_status == "CLEARS_BREAK_EVEN"
    assert scenario_impact.new_status == "CLEARS_BREAK_EVEN"


def test_registry_and_scenario_node_configuration_reject_invalid_graphs() -> None:
    """Duplicate, unresolved, cyclic, self, root, and scenario graphs fail."""
    unchanged = DecisionImpactPolicy.ALWAYS_UNCHANGED
    recompute = DecisionImpactPolicy.RECOMPUTE_ON_DEPENDENCY_CHANGE
    root = _node("obj-root-node", "observed_evidence", (), unchanged)
    with pytest.raises(ValidationError):
        DecisionDependencyRegistry(nodes=(root, root))
    with pytest.raises(ValidationError):
        DecisionDependencyRegistry(
            nodes=(
                root,
                _node(
                    "obj-child-node",
                    "decision_brief",
                    ("obj-missing-node",),
                    recompute,
                ),
            )
        )
    with pytest.raises(ValidationError):
        _node(
            "obj-self-node",
            "decision_brief",
            ("obj-self-node",),
            recompute,
        )
    with pytest.raises(ValidationError):
        DecisionDependencyRegistry(
            nodes=(
                _node("obj-cycle-one", "decision_brief", ("obj-cycle-two",), recompute),
                _node("obj-cycle-two", "decision_brief", ("obj-cycle-one",), recompute),
            )
        )
    with pytest.raises(ValidationError):
        _node("obj-bad-root", "observed_evidence", ("asm-001",), unchanged)
    with pytest.raises(ValidationError):
        _node("obj-empty-child", "decision_brief", (), recompute)

    base_kwargs = {
        "before_assumptions": _scenario_assumptions("rev-001"),
        "after_assumptions": _scenario_assumptions("rev-002", lift="0.03"),
        "scenario_id": "scn-001",
        "before_revision_id": "rev-001",
        "after_revision_id": "rev-002",
    }
    malformed_registries = (
        DecisionDependencyRegistry(nodes=(root,)),
        DecisionDependencyRegistry(
            nodes=(
                _node(
                    "obj-scenario-node",
                    "scenario_result",
                    ("asm-001", "asm-002", "asm-003"),
                    recompute,
                ),
            )
        ),
        DecisionDependencyRegistry(
            nodes=(
                _node(
                    "obj-scenario-node",
                    "scenario_result",
                    ("asm-001", "asm-002", "asm-003", "asm-004"),
                    DecisionImpactPolicy.STALE_ON_DEPENDENCY_CHANGE,
                ),
            )
        ),
        DecisionDependencyRegistry(
            nodes=(
                _node(
                    "obj-scenario-one",
                    "scenario_result",
                    ("asm-001", "asm-002", "asm-003", "asm-004"),
                    recompute,
                ),
                _node(
                    "obj-scenario-two",
                    "scenario_result",
                    ("asm-001", "asm-002", "asm-003", "asm-004"),
                    recompute,
                ),
            )
        ),
    )
    for registry in malformed_registries:
        with pytest.raises(DecisionDiffEngineError):
            build_decision_diff(**base_kwargs, registry=registry)


def test_engine_rejects_illegal_revisions_and_unknown_assumption_refs() -> None:
    """Identity, metadata, completeness, refs, and evaluability fail safely."""
    before = _scenario_assumptions("rev-001")
    after = list(_scenario_assumptions("rev-002", lift="0.03"))
    registry = _hero_registry()
    common = {
        "before_assumptions": before,
        "scenario_id": "scn-001",
        "before_revision_id": "rev-001",
        "after_revision_id": "rev-002",
        "registry": registry,
    }
    identity_change = tuple(after[:1]) + (
        ScenarioAssumption.model_validate(
            {**after[1].model_dump(), "assumption_id": "asm-009"}
        ),
    ) + tuple(after[2:])
    key_swap = (
        _assumption(
            "asm-001", "rev-002", "expected_incremental_lift", "0.03", "fraction", None
        ),
        _assumption(
            "asm-002", "rev-002", "pilot_population", "500", "customers", None
        ),
        after[2],
        after[3],
    )
    invalid_unit = tuple(after[:1]) + (
        after[1].model_copy(update={"unit": "percent"}),
    ) + tuple(after[2:])
    changed_currency = tuple(after[:2]) + tuple(
        ScenarioAssumption.model_validate({**item.model_dump(), "currency": "EUR"})
        for item in after[2:]
    )
    invalid_scope = tuple(after[:1]) + (
        after[1].model_copy(update={"source_scope": "internal_observation"}),
    ) + tuple(after[2:])
    illegal_after_sequences = (
        identity_change,
        key_swap,
        invalid_unit,
        changed_currency,
        invalid_scope,
        tuple(after[:3]),
    )
    for illegal_after in illegal_after_sequences:
        with pytest.raises(DecisionDiffEngineError) as error:
            build_decision_diff(after_assumptions=illegal_after, **common)
        assert "errors.pydantic.dev" not in str(error.value)
        assert "ScenarioAssumption(" not in str(error.value)

    with pytest.raises(DecisionDiffEngineError):
        build_decision_diff(
            before,
            _scenario_assumptions("rev-001"),
            scenario_id="scn-001",
            before_revision_id="rev-001",
            after_revision_id="rev-001",
            registry=registry,
        )
    unknown_ref_nodes = tuple(
        node
        if node.object_type != "scenario_result"
        else DecisionDependencyNode.model_validate(
            {
                **node.model_dump(),
                "dependency_refs": ("asm-001", "asm-002", "asm-003", "asm-999"),
            }
        )
        for node in registry.nodes
    )
    with pytest.raises(DecisionDiffEngineError, match="unknown"):
        build_decision_diff(
            after_assumptions=tuple(after),
            **{**common, "registry": DecisionDependencyRegistry(nodes=unknown_ref_nodes)},
        )

    complete_before = calculate_break_even_scenario(
        before, scenario_id="scn-001", revision_id="rev-001"
    )
    not_evaluable_after = calculate_break_even_scenario(
        tuple(after[:3]), scenario_id="scn-001", revision_id="rev-002"
    )
    with patch(
        "app.decision_diff_engine.calculate_break_even_scenario",
        side_effect=(complete_before, not_evaluable_after),
    ), pytest.raises(DecisionDiffEngineError, match="complete evaluable"):
        build_decision_diff(after_assumptions=tuple(after), **common)


def test_input_orders_do_not_change_diff_and_callers_are_not_mutated() -> None:
    """Assumption and registry order are irrelevant and all inputs stay frozen."""
    before = _scenario_assumptions("rev-001")
    after = _scenario_assumptions("rev-002", lift="0.03")
    registry = _hero_registry()
    snapshots = (
        tuple(item.model_dump() for item in before),
        tuple(item.model_dump() for item in after),
        registry.model_dump(),
    )
    first = build_decision_diff(
        before,
        after,
        scenario_id="scn-001",
        before_revision_id="rev-001",
        after_revision_id="rev-002",
        registry=registry,
    )
    second = build_decision_diff(
        tuple(reversed(before)),
        tuple(reversed(after)),
        scenario_id="scn-001",
        before_revision_id="rev-001",
        after_revision_id="rev-002",
        registry=DecisionDependencyRegistry(nodes=tuple(reversed(registry.nodes))),
    )
    assert first == second
    assert tuple(item.model_dump() for item in before) == snapshots[0]
    assert tuple(item.model_dump() for item in after) == snapshots[1]
    assert registry.model_dump() == snapshots[2]


def test_module_is_side_effect_free_generic_and_import_bounded() -> None:
    """Production source has only allowed imports and no Hero special cases."""
    module_path = _ROOT / "app" / "decision_diff_engine.py"
    source = module_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    imports.update(
        alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names
    )
    allowed_roots = {
        "__future__",
        "heapq",
        "re",
        "collections.abc",
        "decimal",
        "enum",
        "typing",
        "pydantic",
        "app.decision_diff",
    }
    assert imports <= allowed_roots
    forbidden_text = (
        "EvidenceObject",
        "role_engine",
        "WorkflowPlan",
        "streamlit",
        "granite",
        "provider",
        "os.environ",
        "socket",
        "requests",
        "httpx",
        "time.time",
        "uuid",
        "random",
        "obj-executive-posture",
        "obj-sales-posture",
        "obj-pm-handoff",
        "obj-decision-brief",
    )
    assert not any(text.lower() in source.lower() for text in forbidden_text)
    propagation_node = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_propagate_impacts"
    )
    propagation_source = ast.get_source_segment(source, propagation_node) or ""
    assert "expected_incremental_lift" not in propagation_source
    assert "build_hero_registry" not in source
    assert "build_retention_registry" not in source
    assert "build_telco_registry" not in source
