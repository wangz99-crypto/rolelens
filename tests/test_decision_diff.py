"""Offline contract tests for the experimental DD-1 break-even spike.

Exactly 10 top-level test functions. No external service is used.
"""

from __future__ import annotations

import ast
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.decision_diff import (
    DecisionDiffInputError,
    ScenarioAssumption,
    ScenarioResult,
    ScenarioStatus,
    calculate_break_even_scenario,
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
    """Build one assumption while keeping test decimals exact."""
    return ScenarioAssumption(
        assumption_id=assumption_id,
        revision_id=revision_id,
        key=key,
        value=Decimal(value),
        unit=unit,
        currency=currency,
    )


def _hero_assumptions(
    revision_id: str = "rev-001",
    lift: str = "0.08",
) -> tuple[ScenarioAssumption, ...]:
    """Return the four logical Hero inputs for one immutable revision."""
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


def test_scenario_assumption_rejects_malformed_contract_inputs() -> None:
    """IDs, units, extras, non-finite values, and observation fields fail."""
    base = {
        "assumption_id": "asm-001",
        "revision_id": "rev-001",
        "key": "pilot_population",
        "value": Decimal("500"),
        "unit": "customers",
        "currency": None,
    }
    invalid_updates = (
        {"assumption_id": "asm-1"},
        {"revision_id": "revision-001"},
        {"unit": "people"},
        {"unexpected": "forbidden"},
        {"value": Decimal("NaN")},
        {"value": Decimal("Infinity")},
        {"evidence_id": "ev-test-000000000000"},
        {"source_id": "src-test-000000000000"},
        {"identity_digest": "0" * 64},
    )
    for update in invalid_updates:
        with pytest.raises(ValidationError):
            ScenarioAssumption.model_validate({**base, **update})


def test_hero_eight_percent_returns_exact_clearing_result() -> None:
    """The 8% Hero assumptions produce the exact positive scenario result."""
    result = calculate_break_even_scenario(
        _hero_assumptions(), scenario_id="scn-001", revision_id="rev-001"
    )
    assert result == ScenarioResult(
        scenario_id="scn-001",
        revision_id="rev-001",
        input_assumption_ids=("asm-001", "asm-002", "asm-003", "asm-004"),
        missing_input_keys=(),
        expected_incremental_retained=Decimal("40.00"),
        expected_scenario_value=Decimal("20000.00"),
        intervention_cost=Decimal("15000"),
        net_scenario_value=Decimal("5000.00"),
        break_even_lift=Decimal("0.06"),
        currency="USD",
        status=ScenarioStatus.CLEARS_BREAK_EVEN,
        interpretation=(
            "Under the supplied assumptions, this scenario clears the modeled "
            "break-even threshold."
        ),
    )
    valid_payload = result.model_dump()
    adversarial_updates = (
        {"input_assumption_ids": ()},
        {"input_assumption_ids": ("asm-001", "asm-002", "asm-003")},
        {"net_scenario_value": Decimal("123")},
    )
    for update in adversarial_updates:
        with pytest.raises(ValidationError):
            ScenarioResult.model_validate({**valid_payload, **update})


def test_three_percent_revision_is_exact_and_does_not_mutate_revision_one() -> None:
    """A new 3% revision is negative while revision one remains unchanged."""
    revision_one = _hero_assumptions()
    revision_one_snapshot = tuple(item.model_dump() for item in revision_one)
    revision_two = _hero_assumptions(revision_id="rev-002", lift="0.03")
    result = calculate_break_even_scenario(
        revision_two, scenario_id="scn-001", revision_id="rev-002"
    )
    assert result.expected_incremental_retained == Decimal("15.00")
    assert result.expected_scenario_value == Decimal("7500.00")
    assert result.intervention_cost == Decimal("15000")
    assert result.net_scenario_value == Decimal("-7500.00")
    assert result.break_even_lift == Decimal("0.06")
    assert result.currency == "USD"
    assert result.status is ScenarioStatus.DOES_NOT_CLEAR_BREAK_EVEN
    assert tuple(item.model_dump() for item in revision_one) == revision_one_snapshot
    assert all(item.revision_id == "rev-001" for item in revision_one)


def test_exact_six_percent_boundary_does_not_clear() -> None:
    """Net zero is intentionally classified conservatively."""
    result = calculate_break_even_scenario(
        _hero_assumptions(lift="0.06"),
        scenario_id="scn-001",
        revision_id="rev-001",
    )
    assert result.expected_incremental_retained == Decimal("30.00")
    assert result.expected_scenario_value == Decimal("15000.00")
    assert result.intervention_cost == Decimal("15000")
    assert result.net_scenario_value == Decimal("0.00")
    assert result.break_even_lift == Decimal("0.06")
    assert result.status is ScenarioStatus.DOES_NOT_CLEAR_BREAK_EVEN


def test_missing_lift_is_not_evaluable_without_partial_calculations() -> None:
    """A missing lift is named and suppresses every calculated value."""
    assumptions = tuple(
        item for item in _hero_assumptions() if item.key != "expected_incremental_lift"
    )
    result = calculate_break_even_scenario(
        assumptions, scenario_id="scn-001", revision_id="rev-001"
    )
    assert result.input_assumption_ids == ("asm-001", "asm-003", "asm-004")
    assert result.missing_input_keys == ("expected_incremental_lift",)
    assert result.currency == "USD"
    assert result.status is ScenarioStatus.NOT_EVALUABLE
    assert result.interpretation == (
        "The break-even scenario cannot be evaluated because required scenario "
        "assumptions are missing."
    )
    assert result.expected_incremental_retained is None
    assert result.expected_scenario_value is None
    assert result.intervention_cost is None
    assert result.net_scenario_value is None
    assert result.break_even_lift is None
    with pytest.raises(ValidationError):
        ScenarioResult.model_validate(
            {**result.model_dump(), "input_assumption_ids": ()}
        )


def test_invalid_numeric_boundaries_fail_assumption_validation() -> None:
    """Impossible or out-of-range scenario quantities are rejected."""
    invalid = (
        ("cost_per_intervention", "-0.01", "currency_per_customer", "USD"),
        ("retained_customer_value", "0", "currency_per_customer", "USD"),
        ("expected_incremental_lift", "-0.01", "fraction", None),
        ("expected_incremental_lift", "1.01", "fraction", None),
        ("pilot_population", "0", "customers", None),
        ("pilot_population", "-1", "customers", None),
        ("pilot_population", "1.5", "customers", None),
    )
    for key, value, unit, currency in invalid:
        with pytest.raises(ValidationError):
            _assumption("asm-001", "rev-001", key, value, unit, currency)


def test_duplicates_and_revision_mismatches_fail_with_controlled_errors() -> None:
    """Ambiguous IDs, keys, revisions, and container types fail closed."""
    hero = _hero_assumptions()
    duplicate_id = (
        hero[0],
        hero[1],
        hero[2],
        hero[3].model_copy(update={"assumption_id": "asm-003"}),
    )
    duplicate_key = (
        hero[0],
        hero[1],
        hero[2],
        hero[3].model_copy(update={"key": "cost_per_intervention"}),
    )
    wrong_revision = hero[:-1] + (
        _assumption(
            "asm-004",
            "rev-002",
            "retained_customer_value",
            "500",
            "currency_per_customer",
            "USD",
        ),
    )
    cases = (
        (duplicate_id, "Duplicate assumption_id values are not allowed."),
        (duplicate_key, "Duplicate assumption keys are not allowed."),
        (wrong_revision, "All assumptions must match the requested revision_id."),
    )
    for assumptions, expected in cases:
        with pytest.raises(DecisionDiffInputError) as error:
            calculate_break_even_scenario(
                assumptions, scenario_id="scn-001", revision_id="rev-001"
            )
        assert str(error.value) == expected
        assert "errors.pydantic.dev" not in str(error.value)
    with pytest.raises(DecisionDiffInputError, match="must be a sequence"):
        calculate_break_even_scenario(  # type: ignore[arg-type]
            iter(hero), scenario_id="scn-001", revision_id="rev-001"
        )


def test_currency_rules_fail_closed_and_never_infer_currency() -> None:
    """Only matching supplied financial currencies can label a result."""
    hero = _hero_assumptions()
    mismatch = hero[:-1] + (
        ScenarioAssumption.model_validate(
            {**hero[-1].model_dump(), "currency": "EUR"}
        ),
    )
    one_sided = hero[:-1] + (
        ScenarioAssumption.model_validate(
            {**hero[-1].model_dump(), "currency": None}
        ),
    )
    for assumptions in (mismatch, one_sided):
        with pytest.raises(DecisionDiffInputError):
            calculate_break_even_scenario(
                assumptions, scenario_id="scn-001", revision_id="rev-001"
            )
    usd_result = calculate_break_even_scenario(
        hero, scenario_id="scn-001", revision_id="rev-001"
    )
    assert usd_result.currency == "USD"

    euro_assumptions = tuple(
        ScenarioAssumption.model_validate({**item.model_dump(), "currency": "EUR"})
        if item.key in {"cost_per_intervention", "retained_customer_value"}
        else item
        for item in hero
    )
    euro_result = calculate_break_even_scenario(
        euro_assumptions, scenario_id="scn-001", revision_id="rev-001"
    )
    assert euro_result.currency == "EUR"

    for invalid_currency in ("usd", "US dollars", "banana", ""):
        with pytest.raises(ValidationError):
            ScenarioAssumption.model_validate(
                {**hero[2].model_dump(), "currency": invalid_currency}
            )
        with pytest.raises(ValidationError):
            ScenarioResult.model_validate(
                {**usd_result.model_dump(), "currency": invalid_currency}
            )

    no_currency = tuple(
        ScenarioAssumption.model_validate({**item.model_dump(), "currency": None})
        if item.key in {"cost_per_intervention", "retained_customer_value"}
        else item
        for item in hero
    )
    no_currency_result = calculate_break_even_scenario(
        no_currency, scenario_id="scn-001", revision_id="rev-001"
    )
    assert no_currency_result.currency is None
    assert "ibm" not in (_ROOT / "app" / "decision_diff.py").read_text(
        encoding="utf-8"
    ).lower()


def test_order_independence_canonical_ids_and_input_immutability() -> None:
    """Logical inputs are order-independent and remain unchanged."""
    inputs = _hero_assumptions()
    snapshots = tuple(item.model_dump() for item in inputs)
    first = calculate_break_even_scenario(
        inputs, scenario_id="scn-001", revision_id="rev-001"
    )
    second = calculate_break_even_scenario(
        tuple(reversed(inputs)), scenario_id="scn-001", revision_id="rev-001"
    )
    assert first == second
    assert first.input_assumption_ids == (
        "asm-001",
        "asm-002",
        "asm-003",
        "asm-004",
    )
    assert tuple(item.model_dump() for item in inputs) == snapshots
    with pytest.raises(ValidationError):
        inputs[0].value = Decimal("1")  # type: ignore[misc]


def test_module_is_side_effect_free_and_assumptions_are_separate() -> None:
    """The spike has no forbidden imports, fields, or conversion functions."""
    module_path = _ROOT / "app" / "decision_diff.py"
    source = module_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_roots = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported_roots.update(
        (node.module or "").split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    )
    assert imported_roots.isdisjoint(
        {
            "app",
            "os",
            "socket",
            "requests",
            "httpx",
            "urllib",
            "time",
            "datetime",
            "uuid",
            "random",
        }
    )
    assert not any("granite" in name or "provider" in name for name in imported_roots)
    assert set(ScenarioAssumption.model_fields) == {
        "assumption_id",
        "revision_id",
        "key",
        "value",
        "unit",
        "currency",
        "source_scope",
    }
    function_names = {
        node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
    }
    assert not any("evidence" in name.lower() for name in function_names)
    for forbidden_field in ("evidence_id", "source_id", "identity_digest"):
        with pytest.raises(ValidationError):
            ScenarioAssumption.model_validate(
                {
                    **_hero_assumptions()[0].model_dump(),
                    forbidden_field: "forbidden",
                }
            )
