"""Offline tests for bounded one-call Granite language realization."""

from __future__ import annotations

import builtins
import importlib
import json
import sys
from collections.abc import Callable, Mapping
from typing import Any

import pytest

from app.granite_role_brief_provider import (
    DEFAULT_MAX_COMPLETION_TOKENS,
    DEFAULT_MODEL_ID,
    GraniteRoleBriefConfigurationError,
    GraniteRoleBriefProvider,
    GraniteRoleBriefProviderError,
    GraniteRoleBriefResponseError,
    GraniteRoleBriefSettings,
    _build_response_schema,
)
from app.role_brief_plan import (
    SECTION_ORDER,
    RoleBriefPlanSet,
    ordered_assumption_refs,
    ordered_evidence_refs,
    render_handoff,
    role_atoms,
)
from app.role_impact_brief import ROLE_ORDER, RoleBriefGenerationContext
from tests.test_role_brief_plan import _trusted_plan


_SECRET = "slice-four-secret-must-not-leak"


class _FakeChatClient:
    """Record exact chat calls and return one configured offline response."""

    def __init__(
        self,
        response: Mapping[str, Any]
        | Callable[[list[dict[str, str]], Mapping[str, Any]], Mapping[str, Any]],
    ) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    def chat(
        self,
        *,
        messages: list[dict[str, str]],
        params: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        """Record exactly one provider request."""
        self.calls.append({"messages": messages, "params": params})
        if callable(self.response):
            return self.response(messages, params)
        return self.response


def _response(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Wrap one payload in the standard chat response shape."""
    return {"choices": [{"message": {"content": json.dumps(payload)}}]}


def _wire_payload(plan: RoleBriefPlanSet) -> dict[str, Any]:
    """Realize every atom with its canonical claim for a safe offline response."""
    return {
        role.role_key: {
            "role_key": role.role_key,
            "sections": {
                atom.section: {
                    "atom_id": atom.atom_id,
                    "text": atom.canonical_claim,
                }
                for atom in role_atoms(role)
            },
        }
        for role in plan.roles
    }


def _valid_environment(model_id: str | None = None) -> dict[str, str]:
    """Return complete offline settings without touching process environment."""
    environment = {
        "WATSONX_URL": "https://us-south.ml.cloud.ibm.com",
        "WATSONX_APIKEY": _SECRET,
        "WATSONX_PROJECT_ID": "offline-project",
    }
    if model_id is not None:
        environment["WATSONX_MODEL_ID"] = model_id
    return environment


def test_import_is_lazy_and_constructs_no_sdk(monkeypatch: pytest.MonkeyPatch) -> None:
    """Module import never reads credentials or imports the watsonx SDK."""
    for name in (
        "WATSONX_URL",
        "WATSONX_APIKEY",
        "WATSONX_PROJECT_ID",
        "WATSONX_MODEL_ID",
    ):
        monkeypatch.delenv(name, raising=False)
    imports: list[str] = []
    original_import = builtins.__import__

    def guarded_import(
        name: str,
        globals: Mapping[str, Any] | None = None,
        locals: Mapping[str, Any] | None = None,
        fromlist: tuple[str, ...] = (),
        level: int = 0,
    ) -> Any:
        if name.startswith("ibm_watsonx_ai"):
            imports.append(name)
            raise AssertionError("SDK construction is forbidden during import")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    monkeypatch.delitem(sys.modules, "app.granite_role_brief_provider", raising=False)
    imported = importlib.import_module("app.granite_role_brief_provider")
    assert imported.GraniteRoleBriefProvider is not None
    assert imports == []


@pytest.mark.parametrize(
    "missing_name", ["WATSONX_URL", "WATSONX_APIKEY", "WATSONX_PROJECT_ID"]
)
def test_environment_validation_fails_closed(missing_name: str) -> None:
    """Every required live setting is mandatory without leaking values."""
    environment = _valid_environment()
    environment.pop(missing_name)
    with pytest.raises(GraniteRoleBriefConfigurationError) as error:
        GraniteRoleBriefSettings.from_environment(environment)
    assert _SECRET not in str(error.value)
    assert missing_name not in str(error.value)


def test_secret_is_absent_from_repr_and_configuration_errors() -> None:
    """API keys never appear in settings or provider diagnostics."""
    settings = GraniteRoleBriefSettings.from_environment(_valid_environment())
    assert _SECRET not in repr(settings)

    def failing_credentials(**_kwargs: Any) -> None:
        raise RuntimeError(_SECRET)

    with pytest.raises(GraniteRoleBriefConfigurationError) as error:
        GraniteRoleBriefProvider.from_env(
            environ=_valid_environment(),
            credentials_factory=failing_credentials,
            model_factory=lambda **_kwargs: pytest.fail("model factory must not run"),
        )
    assert _SECRET not in str(error.value)


@pytest.mark.parametrize(
    ("configured", "expected"),
    [(None, DEFAULT_MODEL_ID), ("ibm/custom-granite", "ibm/custom-granite")],
)
def test_default_and_custom_model_construction(
    configured: str | None,
    expected: str,
) -> None:
    """Live construction records the actual default or configured model ID."""
    model_calls: list[dict[str, Any]] = []
    client = _FakeChatClient({})

    def model_factory(**kwargs: Any) -> _FakeChatClient:
        model_calls.append(kwargs)
        return client

    provider = GraniteRoleBriefProvider.from_env(
        environ=_valid_environment(configured),
        credentials_factory=lambda **_kwargs: object(),
        model_factory=model_factory,
    )
    assert provider.model_id == expected
    assert model_calls[0]["model_id"] == expected
    assert _SECRET not in repr(provider)


def test_exactly_one_chat_call_realizes_all_five_roles() -> None:
    """One plan produces all fifteen atoms through one structured chat call."""
    plan, context = _trusted_plan("0.03")
    client = _FakeChatClient(_response(_wire_payload(plan)))
    result = GraniteRoleBriefProvider(client).generate(plan, context)
    assert tuple(brief.role_key for brief in result.briefs) == ROLE_ORDER
    assert len(client.calls) == 1
    call = client.calls[0]
    assert [message["role"] for message in call["messages"]] == ["system", "user"]
    assert call["params"]["temperature"] == 0
    assert call["params"]["n"] == 1
    assert call["params"]["max_completion_tokens"] == DEFAULT_MAX_COMPLETION_TOKENS
    assert call["params"]["response_format"]["type"] == "json_schema"
    schema = call["params"]["response_format"]["json_schema"]
    assert schema["name"] == "role_impact_brief_wire"
    assert schema["schema"] == _build_response_schema(plan)


def test_system_message_is_a_compact_language_realization_contract() -> None:
    """Granite is assigned phrasing only, never business-governance choices."""
    plan, context = _trusted_plan("0.03")
    client = _FakeChatClient(_response(_wire_payload(plan)))
    GraniteRoleBriefProvider(client).generate(plan, context)
    system = client.calls[0]["messages"][0]["content"].lower()
    for phrase in (
        "bounded language realizer",
        "preserve the complete meaning of canonical_claim",
        "express only that meaning",
        "do not add facts, conditions, causes, workflow, authority, permissions",
        "preserve supplied numbers and statuses exactly",
        "role titles are lenses, not authorities",
        "return the exact supplied atom_id",
        "do not generate handoffs",
        "do not choose evidence",
        "do not choose assumptions",
        "language realization only",
    ):
        assert phrase in system


def test_user_payload_is_plan_only_without_governance_choice_surfaces() -> None:
    """Granite sees atom sources, never reference catalogs or handoff plans."""
    plan, context = _trusted_plan("0.03")
    client = _FakeChatClient(_response(_wire_payload(plan)))
    GraniteRoleBriefProvider(client).generate(plan, context)
    payload = json.loads(client.calls[0]["messages"][1]["content"])
    assert set(payload) == {"fingerprint", "roles"}
    assert payload["fingerprint"] == plan.fingerprint
    assert [role["role_key"] for role in payload["roles"]] == list(ROLE_ORDER)
    assert all(
        set(role) == {"role_key", "role_state", "impact_kind", "sections"}
        for role in payload["roles"]
    )
    assert all(
        set(role["sections"]) == set(SECTION_ORDER)
        for role in payload["roles"]
    )
    assert all(
        set(atom) == {"atom_id", "canonical_claim"}
        for role in payload["roles"]
        for atom in role["sections"].values()
    )
    serialized = json.dumps(payload).lower()
    for forbidden in (
        "governed_evidence",
        "allowed_evidence",
        "evidence_refs",
        "accepted_assumptions",
        "changed_assumptions",
        "assumption_refs",
        "allowed_handoff_roles",
        "handoff",
        "target_role",
    ):
        assert forbidden not in serialized


def test_dynamic_schema_binds_exact_roles_sections_and_atom_ids() -> None:
    """Each wire section can return only its assigned semantic source ID."""
    plan, _context = _trusted_plan("0.03")
    schema = _build_response_schema(plan)
    assert "uniqueItems" not in json.dumps(schema)
    assert schema["required"] == list(ROLE_ORDER)
    assert set(schema["properties"]) == set(ROLE_ORDER)
    assert schema["additionalProperties"] is False
    for role in plan.roles:
        role_schema = schema["properties"][role.role_key]
        assert set(role_schema["properties"]) == {"role_key", "sections"}
        assert role_schema["properties"]["role_key"]["enum"] == [role.role_key]
        sections = role_schema["properties"]["sections"]
        assert sections["required"] == list(SECTION_ORDER)
        assert set(sections["properties"]) == set(SECTION_ORDER)
        expected = {atom.section: atom for atom in role_atoms(role)}
        for section in SECTION_ORDER:
            atom_schema = sections["properties"][section]
            assert set(atom_schema["properties"]) == {"atom_id", "text"}
            assert atom_schema["properties"]["atom_id"]["enum"] == [
                expected[section].atom_id
            ]


def test_inconsistent_plan_is_revalidated_before_chat() -> None:
    """A bypass-constructed plan inconsistency fails before provider I/O."""
    plan, context = _trusted_plan("0.03")
    inconsistent = plan.model_copy(update={"roles": tuple(reversed(plan.roles))})
    client = _FakeChatClient(_response(_wire_payload(plan)))
    with pytest.raises(GraniteRoleBriefProviderError, match="plan is inconsistent"):
        GraniteRoleBriefProvider(client).generate(inconsistent, context)
    assert client.calls == []


@pytest.mark.parametrize(
    "variant",
    [
        "wrong-atom",
        "cross-role-atom",
        "cross-section-atom",
        "missing-section",
        "extra-section",
        "missing-role",
        "extra-role",
        "wrong-role-key",
    ],
)
def test_wire_structural_or_atom_binding_spoof_fails_closed(variant: str) -> None:
    """Granite cannot change role, section, or semantic source binding."""
    plan, context = _trusted_plan("0.03")
    wire = _wire_payload(plan)
    executive = wire["executive"]
    if variant == "wrong-atom":
        executive["sections"]["why_it_matters"]["atom_id"] = "atom_" + "0" * 64
    elif variant == "cross-role-atom":
        executive["sections"]["why_it_matters"]["atom_id"] = wire[
            "data_analyst"
        ]["sections"]["why_it_matters"]["atom_id"]
    elif variant == "cross-section-atom":
        executive["sections"]["why_it_matters"]["atom_id"] = executive[
            "sections"
        ]["what_still_holds"]["atom_id"]
    elif variant == "missing-section":
        executive["sections"].pop("what_to_verify_next")
    elif variant == "extra-section":
        executive["sections"]["reasoning"] = executive["sections"][
            "why_it_matters"
        ]
    elif variant == "missing-role":
        wire.pop("project_manager")
    elif variant == "extra-role":
        wire["legal"] = executive
    else:
        wire["data_engineer"]["role_key"] = "executive"
    client = _FakeChatClient(_response(wire))
    with pytest.raises(GraniteRoleBriefResponseError):
        GraniteRoleBriefProvider(client).generate(plan, context)
    assert len(client.calls) == 1


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("evidence_refs", ["ev-spoof"]),
        ("assumption_refs", ["asm-999"]),
        ("next_handoff", "Legal — Approve."),
        ("next_handoff_role", "legal"),
        ("next_handoff_action", "Approve."),
    ],
)
def test_wire_governance_field_spoof_fails_closed(field: str, value: Any) -> None:
    """Granite cannot return any reference or handoff governance output."""
    plan, context = _trusted_plan("0.03")
    wire = _wire_payload(plan)
    wire["executive"][field] = value
    with pytest.raises(GraniteRoleBriefResponseError):
        GraniteRoleBriefProvider(_FakeChatClient(_response(wire))).generate(
            plan,
            context,
        )


@pytest.mark.parametrize(
    "response",
    [
        {"choices": [{"message": {"content": "```json\n{}\n```"}}]},
        {"choices": [{"message": {"content": "not json"}}]},
        {"choices": []},
        {},
    ],
    ids=["markdown-fence", "malformed-json", "empty-choices", "missing-choices"],
)
def test_malformed_responses_are_rejected(response: Mapping[str, Any]) -> None:
    """Only valid standalone JSON in a non-empty choice is accepted."""
    plan, context = _trusted_plan("0.03")
    with pytest.raises(GraniteRoleBriefResponseError):
        GraniteRoleBriefProvider(_FakeChatClient(response)).generate(plan, context)


@pytest.mark.parametrize(
    "invalid_text",
    ["", "x" * 321, "<b>unsafe</b>", "unsafe\ncontrol"],
    ids=["blank", "overlong", "html", "control"],
)
def test_invalid_realization_text_fails_closed(invalid_text: str) -> None:
    """Realized text remains plain, bounded, and non-empty."""
    plan, context = _trusted_plan("0.03")
    wire = _wire_payload(plan)
    wire["executive"]["sections"]["why_it_matters"]["text"] = invalid_text
    with pytest.raises(GraniteRoleBriefResponseError):
        GraniteRoleBriefProvider(_FakeChatClient(_response(wire))).generate(
            plan,
            context,
        )


def test_final_governance_fields_are_reconstructed_from_plan() -> None:
    """Only text comes from Granite; refs and handoffs are exact plan unions."""
    plan, context = _trusted_plan("0.03")
    result = GraniteRoleBriefProvider(
        _FakeChatClient(_response(_wire_payload(plan)))
    ).generate(plan, context)
    for brief, role in zip(result.briefs, plan.roles, strict=True):
        assert brief.evidence_refs == ordered_evidence_refs(role)
        assert brief.assumption_refs == ordered_assumption_refs(role)
        assert brief.next_handoff == render_handoff(role.handoff)


def test_correct_atom_id_does_not_bypass_final_safety_validation() -> None:
    """Semantic source binding is not a claim of formal text equivalence."""
    plan, context = _trusted_plan("0.03")
    wire = _wire_payload(plan)
    wire["executive"]["sections"]["why_it_matters"][
        "text"
    ] = "Executive approval is required."
    client = _FakeChatClient(_response(wire))
    with pytest.raises(GraniteRoleBriefResponseError):
        GraniteRoleBriefProvider(client).generate(plan, context)
    assert len(client.calls) == 1


def test_provider_exception_is_sanitized_and_not_retried() -> None:
    """Raw provider diagnostics do not escape and one failed call is final."""
    plan, context = _trusted_plan("0.03")

    def fail(
        _messages: list[dict[str, str]],
        _params: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        raise RuntimeError(f"network {_SECRET}")

    client = _FakeChatClient(fail)
    with pytest.raises(GraniteRoleBriefProviderError) as error:
        GraniteRoleBriefProvider(client).generate(plan, context)
    assert _SECRET not in str(error.value)
    assert len(client.calls) == 1


def test_valid_standalone_json_returns_final_product_briefs() -> None:
    """A fully safe realization returns the unchanged final five-brief shape."""
    plan, context = _trusted_plan("0.07")
    result = GraniteRoleBriefProvider(
        _FakeChatClient(_response(_wire_payload(plan)))
    ).generate(plan, context)
    assert tuple(brief.role_key for brief in result.briefs) == ROLE_ORDER
    assert len(result.briefs) == 5
