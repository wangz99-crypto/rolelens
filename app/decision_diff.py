"""Deterministic break-even scenario calculation for the DD-1 spike.

The module accepts only caller-supplied scenario assumptions. It performs no
I/O and does not infer values from datasets or filenames.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from decimal import Decimal, DecimalException
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator


class DecisionDiffInputError(ValueError):
    """Raised when scenario calculation inputs fail closed validation."""


class _DecisionDiffContract(BaseModel):
    """Frozen base for local DD-1 contracts."""

    model_config = ConfigDict(extra="forbid", frozen=True)


_ASSUMPTION_ID_RE = re.compile(r"^asm-[0-9]{3}$")
_REVISION_ID_RE = re.compile(r"^rev-[0-9]{3}$")
_SCENARIO_ID_RE = re.compile(r"^scn-[0-9]{3}$")
_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")

_CANONICAL_KEYS = (
    "pilot_population",
    "expected_incremental_lift",
    "cost_per_intervention",
    "retained_customer_value",
)
_FINANCIAL_KEYS = ("cost_per_intervention", "retained_customer_value")

_CLEARS_INTERPRETATION = (
    "Under the supplied assumptions, this scenario clears the modeled "
    "break-even threshold."
)
_DOES_NOT_CLEAR_INTERPRETATION = (
    "Under the supplied assumptions, this scenario does not clear the modeled "
    "break-even threshold."
)
_NOT_EVALUABLE_INTERPRETATION = (
    "The break-even scenario cannot be evaluated because required scenario "
    "assumptions are missing."
)


class ScenarioAssumption(_DecisionDiffContract):
    """One versioned, caller-supplied input to a break-even scenario."""

    assumption_id: str
    revision_id: str
    key: Literal[
        "pilot_population",
        "expected_incremental_lift",
        "cost_per_intervention",
        "retained_customer_value",
    ]
    value: Decimal
    unit: str
    currency: str | None
    source_scope: Literal["user_assumption"] = "user_assumption"

    @field_validator("assumption_id")
    @classmethod
    def assumption_id_is_valid(cls, value: str) -> str:
        """Require a caller-supplied stable assumption ID."""
        if _ASSUMPTION_ID_RE.fullmatch(value) is None:
            raise ValueError("assumption_id must match ^asm-[0-9]{3}$")
        return value

    @field_validator("revision_id")
    @classmethod
    def revision_id_is_valid(cls, value: str) -> str:
        """Require a caller-supplied stable revision ID."""
        if _REVISION_ID_RE.fullmatch(value) is None:
            raise ValueError("revision_id must match ^rev-[0-9]{3}$")
        return value

    @field_validator("value")
    @classmethod
    def value_is_finite(cls, value: Decimal) -> Decimal:
        """Reject NaN and positive or negative infinity."""
        if not value.is_finite():
            raise ValueError("value must be finite")
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
    def currency_is_explicit_or_none(cls, value: str | None) -> str | None:
        """Require an explicit three-letter uppercase code or no currency."""
        if value is not None and _CURRENCY_RE.fullmatch(value) is None:
            raise ValueError("currency must match ^[A-Z]{3}$ or be None")
        return value

    @model_validator(mode="after")
    def key_specific_rules(self) -> "ScenarioAssumption":
        """Enforce the value, unit, and currency rules for the selected key."""
        if self.key == "pilot_population":
            if self.value <= 0:
                raise ValueError("pilot_population value must be greater than zero")
            if self.value != self.value.to_integral_value():
                raise ValueError("pilot_population value must be integer-valued")
            if self.unit != "customers":
                raise ValueError("pilot_population unit must equal customers")
            if self.currency is not None:
                raise ValueError("pilot_population currency must be None")
        elif self.key == "expected_incremental_lift":
            if self.value < 0 or self.value > 1:
                raise ValueError(
                    "expected_incremental_lift value must be between zero and one"
                )
            if self.unit != "fraction":
                raise ValueError("expected_incremental_lift unit must equal fraction")
            if self.currency is not None:
                raise ValueError("expected_incremental_lift currency must be None")
        elif self.key == "cost_per_intervention":
            if self.value < 0:
                raise ValueError(
                    "cost_per_intervention value must be greater than or equal to zero"
                )
            if self.unit != "currency_per_customer":
                raise ValueError(
                    "cost_per_intervention unit must equal currency_per_customer"
                )
        else:
            if self.value <= 0:
                raise ValueError(
                    "retained_customer_value value must be greater than zero"
                )
            if self.unit != "currency_per_customer":
                raise ValueError(
                    "retained_customer_value unit must equal currency_per_customer"
                )
        return self


class ScenarioStatus(str, Enum):
    """The three possible outcomes of the break-even calculation."""

    NOT_EVALUABLE = "NOT_EVALUABLE"
    CLEARS_BREAK_EVEN = "CLEARS_BREAK_EVEN"
    DOES_NOT_CLEAR_BREAK_EVEN = "DOES_NOT_CLEAR_BREAK_EVEN"


class ScenarioResult(_DecisionDiffContract):
    """Complete auditable result for one requested scenario revision."""

    scenario_id: str
    revision_id: str
    input_assumption_ids: tuple[str, ...]
    missing_input_keys: tuple[str, ...]
    expected_incremental_retained: Decimal | None
    expected_scenario_value: Decimal | None
    intervention_cost: Decimal | None
    net_scenario_value: Decimal | None
    break_even_lift: Decimal | None
    currency: str | None
    status: ScenarioStatus
    interpretation: str

    @field_validator("scenario_id")
    @classmethod
    def scenario_id_is_valid(cls, value: str) -> str:
        """Require a caller-supplied stable scenario ID."""
        if _SCENARIO_ID_RE.fullmatch(value) is None:
            raise ValueError("scenario_id must match ^scn-[0-9]{3}$")
        return value

    @field_validator("revision_id")
    @classmethod
    def result_revision_id_is_valid(cls, value: str) -> str:
        """Require a caller-supplied stable revision ID."""
        if _REVISION_ID_RE.fullmatch(value) is None:
            raise ValueError("revision_id must match ^rev-[0-9]{3}$")
        return value

    @field_validator("input_assumption_ids")
    @classmethod
    def input_ids_are_valid_and_unique(
        cls,
        value: tuple[str, ...],
    ) -> tuple[str, ...]:
        """Require valid, duplicate-free assumption IDs."""
        if any(_ASSUMPTION_ID_RE.fullmatch(item) is None for item in value):
            raise ValueError("input_assumption_ids must contain valid assumption IDs")
        if len(value) != len(set(value)):
            raise ValueError("input_assumption_ids must not contain duplicates")
        return value

    @field_validator("missing_input_keys")
    @classmethod
    def missing_keys_are_canonical(
        cls,
        value: tuple[str, ...],
    ) -> tuple[str, ...]:
        """Require known, duplicate-free missing keys in canonical order."""
        canonical_subset = tuple(key for key in _CANONICAL_KEYS if key in value)
        if value != canonical_subset or len(value) != len(set(value)):
            raise ValueError("missing_input_keys must be unique and in canonical order")
        return value

    @field_validator(
        "expected_incremental_retained",
        "expected_scenario_value",
        "intervention_cost",
        "net_scenario_value",
        "break_even_lift",
    )
    @classmethod
    def calculated_values_are_finite(
        cls,
        value: Decimal | None,
    ) -> Decimal | None:
        """Reject non-finite calculated values."""
        if value is not None and not value.is_finite():
            raise ValueError("calculated scenario values must be finite")
        return value

    @field_validator("currency")
    @classmethod
    def result_currency_is_not_blank(cls, value: str | None) -> str | None:
        """Require an explicit three-letter uppercase code or no currency."""
        if value is not None and _CURRENCY_RE.fullmatch(value) is None:
            raise ValueError("currency must match ^[A-Z]{3}$ or be None")
        return value

    @model_validator(mode="after")
    def state_is_complete_and_consistent(self) -> "ScenarioResult":
        """Keep evaluable and non-evaluable result states mutually exclusive."""
        calculated = (
            self.expected_incremental_retained,
            self.expected_scenario_value,
            self.intervention_cost,
            self.net_scenario_value,
            self.break_even_lift,
        )
        if self.status is ScenarioStatus.NOT_EVALUABLE:
            if not self.missing_input_keys:
                raise ValueError("NOT_EVALUABLE requires at least one missing input key")
            if len(self.input_assumption_ids) + len(self.missing_input_keys) != 4:
                raise ValueError(
                    "NOT_EVALUABLE supplied and missing input counts must total four"
                )
            if any(value is not None for value in calculated):
                raise ValueError("NOT_EVALUABLE cannot contain calculated values")
            if self.interpretation != _NOT_EVALUABLE_INTERPRETATION:
                raise ValueError("NOT_EVALUABLE interpretation is invalid")
            return self

        if self.missing_input_keys:
            raise ValueError("evaluable scenarios cannot contain missing input keys")
        if len(self.input_assumption_ids) != 4:
            raise ValueError("evaluable scenarios require exactly four assumption IDs")
        if any(value is None for value in calculated):
            raise ValueError("evaluable scenarios require all calculated values")
        if (
            self.expected_scenario_value is None
            or self.intervention_cost is None
            or self.net_scenario_value is None
            or self.expected_scenario_value - self.intervention_cost
            != self.net_scenario_value
        ):
            raise ValueError(
                "net_scenario_value must equal expected_scenario_value minus "
                "intervention_cost"
            )
        expected_interpretation = (
            _CLEARS_INTERPRETATION
            if self.status is ScenarioStatus.CLEARS_BREAK_EVEN
            else _DOES_NOT_CLEAR_INTERPRETATION
        )
        if self.interpretation != expected_interpretation:
            raise ValueError("evaluable scenario interpretation is invalid")
        if self.status is ScenarioStatus.CLEARS_BREAK_EVEN:
            if self.net_scenario_value is None or self.net_scenario_value <= 0:
                raise ValueError("CLEARS_BREAK_EVEN requires positive net scenario value")
        elif self.net_scenario_value is None or self.net_scenario_value > 0:
            raise ValueError(
                "DOES_NOT_CLEAR_BREAK_EVEN requires non-positive net scenario value"
            )
        return self


def _validate_calculation_ids(scenario_id: str, revision_id: str) -> None:
    """Validate caller IDs without exposing supplied values in errors."""
    if not isinstance(scenario_id, str) or _SCENARIO_ID_RE.fullmatch(scenario_id) is None:
        raise DecisionDiffInputError("scenario_id must match ^scn-[0-9]{3}$.")
    if not isinstance(revision_id, str) or _REVISION_ID_RE.fullmatch(revision_id) is None:
        raise DecisionDiffInputError("revision_id must match ^rev-[0-9]{3}$.")


def _validated_currency(
    assumptions_by_key: dict[str, ScenarioAssumption],
) -> str | None:
    """Return a shared explicit currency, or fail closed on incompatible inputs."""
    if not all(key in assumptions_by_key for key in _FINANCIAL_KEYS):
        return None
    cost_currency = assumptions_by_key["cost_per_intervention"].currency
    value_currency = assumptions_by_key["retained_customer_value"].currency
    if (cost_currency is None) != (value_currency is None):
        raise DecisionDiffInputError(
            "Financial assumption currencies must both be provided or both be omitted."
        )
    if cost_currency != value_currency:
        raise DecisionDiffInputError("Financial assumption currencies must match.")
    return cost_currency


def calculate_break_even_scenario(
    assumptions: Sequence[ScenarioAssumption],
    *,
    scenario_id: str,
    revision_id: str,
) -> ScenarioResult:
    """Calculate an exact break-even scenario from validated assumptions.

    Caller order does not affect the returned result. Missing inputs yield a
    non-evaluable result, while malformed, duplicate, or inconsistent inputs
    raise :class:`DecisionDiffInputError` with controlled messages.
    """
    _validate_calculation_ids(scenario_id, revision_id)
    if isinstance(assumptions, (str, bytes, bytearray)) or not isinstance(
        assumptions, Sequence
    ):
        raise DecisionDiffInputError(
            "assumptions must be a sequence of ScenarioAssumption objects."
        )
    if any(type(item) is not ScenarioAssumption for item in assumptions):
        raise DecisionDiffInputError(
            "assumptions must contain only ScenarioAssumption objects."
        )

    assumption_ids = [item.assumption_id for item in assumptions]
    if len(assumption_ids) != len(set(assumption_ids)):
        raise DecisionDiffInputError("Duplicate assumption_id values are not allowed.")
    keys = [item.key for item in assumptions]
    if len(keys) != len(set(keys)):
        raise DecisionDiffInputError("Duplicate assumption keys are not allowed.")
    if any(item.revision_id != revision_id for item in assumptions):
        raise DecisionDiffInputError(
            "All assumptions must match the requested revision_id."
        )

    assumptions_by_key = {item.key: item for item in assumptions}
    currency = _validated_currency(assumptions_by_key)
    missing_keys = tuple(
        key for key in _CANONICAL_KEYS if key not in assumptions_by_key
    )
    ordered_input_ids = tuple(
        assumptions_by_key[key].assumption_id
        for key in _CANONICAL_KEYS
        if key in assumptions_by_key
    )
    if missing_keys:
        return ScenarioResult(
            scenario_id=scenario_id,
            revision_id=revision_id,
            input_assumption_ids=ordered_input_ids,
            missing_input_keys=missing_keys,
            expected_incremental_retained=None,
            expected_scenario_value=None,
            intervention_cost=None,
            net_scenario_value=None,
            break_even_lift=None,
            currency=currency,
            status=ScenarioStatus.NOT_EVALUABLE,
            interpretation=_NOT_EVALUABLE_INTERPRETATION,
        )

    population = assumptions_by_key["pilot_population"].value
    lift = assumptions_by_key["expected_incremental_lift"].value
    cost_per_intervention = assumptions_by_key["cost_per_intervention"].value
    retained_customer_value = assumptions_by_key["retained_customer_value"].value
    try:
        expected_incremental_retained = population * lift
        expected_scenario_value = (
            expected_incremental_retained * retained_customer_value
        )
        intervention_cost = population * cost_per_intervention
        net_scenario_value = expected_scenario_value - intervention_cost
        break_even_lift = cost_per_intervention / retained_customer_value
    except DecimalException:
        raise DecisionDiffInputError(
            "Scenario arithmetic could not be completed with the supplied values."
        ) from None

    clears = net_scenario_value > 0
    status = (
        ScenarioStatus.CLEARS_BREAK_EVEN
        if clears
        else ScenarioStatus.DOES_NOT_CLEAR_BREAK_EVEN
    )
    interpretation = (
        _CLEARS_INTERPRETATION if clears else _DOES_NOT_CLEAR_INTERPRETATION
    )
    return ScenarioResult(
        scenario_id=scenario_id,
        revision_id=revision_id,
        input_assumption_ids=ordered_input_ids,
        missing_input_keys=(),
        expected_incremental_retained=expected_incremental_retained,
        expected_scenario_value=expected_scenario_value,
        intervention_cost=intervention_cost,
        net_scenario_value=net_scenario_value,
        break_even_lift=break_even_lift,
        currency=currency,
        status=status,
        interpretation=interpretation,
    )
