"""Product-native watsonx.ai provider for five-role Decision interpretation.

This module performs no environment reads, SDK construction, file reads, or
network calls at import time.  Live construction is isolated in
``GraniteRoleBriefProvider.from_env`` and one ``generate`` call maps to exactly
one ``ModelInference.chat`` call returning all five briefs.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

from pydantic import ValidationError

from app.role_brief_plan import (
    SECTION_ORDER,
    RoleBriefPlanSet,
    ordered_assumption_refs,
    ordered_evidence_refs,
    render_handoff,
    role_atoms,
    validate_role_brief_plan_set,
)
from app.role_impact_brief import (
    ROLE_ORDER,
    RoleBriefGenerationContext,
    RoleImpactBrief,
    RoleImpactBriefSet,
    RoleImpactBriefValidationError,
    validate_role_impact_brief_set,
)


DEFAULT_MODEL_ID = "ibm/granite-4-h-small"
DEFAULT_MAX_COMPLETION_TOKENS = 3200
_MIN_COMPLETION_TOKENS = 1500
_MAX_COMPLETION_TOKENS = 5000


class GraniteRoleBriefProviderError(RuntimeError):
    """Base sanitized failure for product-native Granite generation."""


class GraniteRoleBriefConfigurationError(GraniteRoleBriefProviderError):
    """Raised when live watsonx.ai construction cannot be completed safely."""


class GraniteRoleBriefResponseError(GraniteRoleBriefProviderError):
    """Raised when Granite returns malformed or policy-invalid output."""


@dataclass(frozen=True)
class GraniteRoleBriefSettings:
    """Validated environment settings with secret-safe representation."""

    url: str
    api_key: str = field(repr=False)
    project_id: str
    model_id: str = DEFAULT_MODEL_ID

    @classmethod
    def from_environment(
        cls,
        environ: Mapping[str, str] | None = None,
    ) -> "GraniteRoleBriefSettings":
        """Read required settings only during explicit live construction."""
        source = os.environ if environ is None else environ
        required = ("WATSONX_URL", "WATSONX_APIKEY", "WATSONX_PROJECT_ID")
        if any(not source.get(name) or not source[name].strip() for name in required):
            raise GraniteRoleBriefConfigurationError(
                "Required watsonx.ai configuration is unavailable."
            )
        model_id = source.get("WATSONX_MODEL_ID", DEFAULT_MODEL_ID).strip()
        return cls(
            url=source["WATSONX_URL"].strip(),
            api_key=source["WATSONX_APIKEY"].strip(),
            project_id=source["WATSONX_PROJECT_ID"].strip(),
            model_id=model_id or DEFAULT_MODEL_ID,
        )


class ChatInferenceClient(Protocol):
    """Injectable subset of the watsonx.ai chat inference client."""

    def chat(
        self,
        *,
        messages: list[dict[str, str]],
        params: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        """Return one standard watsonx.ai chat response."""
        ...


_SYSTEM_MESSAGE = """You are a bounded language realizer for RoleLens.
For every supplied SemanticAtom, preserve the complete meaning of canonical_claim and express only that meaning in concise role-readable language.
Do not add facts, conditions, causes, workflow, authority, permissions, or actions not already stated.
Preserve supplied numbers and statuses exactly when used. Role titles are lenses, not authorities.
Return the exact supplied atom_id for each realization.
Do not generate handoffs. Do not choose Evidence. Do not choose assumptions.
RoleLens already decided the business semantics; your job is language realization only.
Return one standalone JSON object matching the supplied response schema. Do not return Markdown, code fences, chain-of-thought, or text outside JSON."""


def _canonical_plan(plan: RoleBriefPlanSet) -> str:
    """Serialize only governed semantic sources needed for realization."""
    payload = {
        "fingerprint": plan.fingerprint,
        "roles": [
            {
                "role_key": role.role_key,
                "role_state": role.role_state,
                "impact_kind": role.impact_kind,
                "sections": {
                    atom.section: {
                        "atom_id": atom.atom_id,
                        "canonical_claim": atom.canonical_claim,
                    }
                    for atom in role_atoms(role)
                },
            }
            for role in plan.roles
        ],
    }
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _build_response_schema(plan: RoleBriefPlanSet) -> dict[str, Any]:
    """Build one request-scoped schema binding every expected atom ID."""
    role_properties: dict[str, Any] = {}
    for role in plan.roles:
        atoms_by_section = {atom.section: atom for atom in role_atoms(role)}
        section_properties = {
            section: {
                "type": "object",
                "properties": {
                    "atom_id": {
                        "type": "string",
                        "enum": [atoms_by_section[section].atom_id],
                    },
                    "text": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 320,
                    },
                },
                "required": ["atom_id", "text"],
                "additionalProperties": False,
            }
            for section in SECTION_ORDER
        }
        role_properties[role.role_key] = {
            "type": "object",
            "properties": {
                "role_key": {
                    "type": "string",
                    "enum": [role.role_key],
                },
                "sections": {
                    "type": "object",
                    "properties": section_properties,
                    "required": list(SECTION_ORDER),
                    "additionalProperties": False,
                },
            },
            "required": ["role_key", "sections"],
            "additionalProperties": False,
        }
    return {
        "type": "object",
        "properties": role_properties,
        "required": list(ROLE_ORDER),
        "additionalProperties": False,
    }


def _extract_json(response: Mapping[str, Any]) -> dict[str, Any]:
    """Extract one standalone JSON object without accepting Markdown wrappers."""
    if not isinstance(response, Mapping):
        raise GraniteRoleBriefResponseError("Granite returned an invalid response.")
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        raise GraniteRoleBriefResponseError("Granite returned an invalid response.")
    first = choices[0]
    if not isinstance(first, Mapping):
        raise GraniteRoleBriefResponseError("Granite returned an invalid response.")
    message = first.get("message")
    if not isinstance(message, Mapping):
        raise GraniteRoleBriefResponseError("Granite returned an invalid response.")
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise GraniteRoleBriefResponseError("Granite returned an invalid response.")
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        raise GraniteRoleBriefResponseError("Granite returned invalid JSON.") from None
    if not isinstance(parsed, dict):
        raise GraniteRoleBriefResponseError("Granite returned an invalid response.")
    return parsed


def _wire_to_brief_set(
    payload: Mapping[str, Any],
    plan: RoleBriefPlanSet,
    context: RoleBriefGenerationContext,
) -> RoleImpactBriefSet:
    """Combine realized text with deterministic refs and handoffs."""
    if set(payload) != set(ROLE_ORDER):
        raise GraniteRoleBriefResponseError("Granite returned an invalid response.")
    briefs: list[RoleImpactBrief] = []
    for role in plan.roles:
        raw_role = payload.get(role.role_key)
        if (
            not isinstance(raw_role, Mapping)
            or set(raw_role) != {"role_key", "sections"}
            or raw_role.get("role_key") != role.role_key
        ):
            raise GraniteRoleBriefResponseError(
                "Granite returned an invalid response."
            )
        sections = raw_role.get("sections")
        if not isinstance(sections, Mapping) or set(sections) != set(SECTION_ORDER):
            raise GraniteRoleBriefResponseError(
                "Granite returned an invalid response."
            )
        expected_atoms = {atom.section: atom for atom in role_atoms(role)}
        realized_text: dict[str, str] = {}
        for section in SECTION_ORDER:
            raw_atom = sections.get(section)
            if (
                not isinstance(raw_atom, Mapping)
                or set(raw_atom) != {"atom_id", "text"}
                or raw_atom.get("atom_id") != expected_atoms[section].atom_id
            ):
                raise GraniteRoleBriefResponseError(
                    "Granite returned an invalid response."
                )
            text = raw_atom.get("text")
            if (
                not isinstance(text, str)
                or text != text.strip()
                or not 1 <= len(text) <= 320
                or "<" in text
                or ">" in text
                or any(
                    ord(character) < 32 and character not in "\t"
                    for character in text
                )
            ):
                raise GraniteRoleBriefResponseError(
                    "Granite returned an invalid response."
                )
            realized_text[section] = text
        briefs.append(
            RoleImpactBrief(
                role_key=role.role_key,
                why_it_matters=realized_text["why_it_matters"],
                what_still_holds=realized_text["what_still_holds"],
                what_to_verify_next=realized_text["what_to_verify_next"],
                evidence_refs=ordered_evidence_refs(role),
                assumption_refs=ordered_assumption_refs(role),
                next_handoff=render_handoff(role.handoff),
            )
        )
    return RoleImpactBriefSet(briefs=tuple(briefs))


class GraniteRoleBriefProvider:
    """One-call provider for a validated five-role interpretation set."""

    def __init__(
        self,
        client: ChatInferenceClient,
        *,
        model_id: str = DEFAULT_MODEL_ID,
        max_completion_tokens: int = DEFAULT_MAX_COMPLETION_TOKENS,
    ) -> None:
        if not model_id.strip():
            raise GraniteRoleBriefConfigurationError("A Granite model ID is required.")
        if not _MIN_COMPLETION_TOKENS <= max_completion_tokens <= _MAX_COMPLETION_TOKENS:
            raise GraniteRoleBriefConfigurationError(
                "max_completion_tokens is outside the supported bounded range."
            )
        self._client = client
        self._model_id = model_id.strip()
        self._max_completion_tokens = max_completion_tokens

    @property
    def model_id(self) -> str:
        """Return the actual configured model identifier safe for API output."""
        return self._model_id

    @classmethod
    def from_env(
        cls,
        *,
        environ: Mapping[str, str] | None = None,
        credentials_factory: Callable[..., Any] | None = None,
        model_factory: Callable[..., ChatInferenceClient] | None = None,
        max_completion_tokens: int = DEFAULT_MAX_COMPLETION_TOKENS,
    ) -> "GraniteRoleBriefProvider":
        """Lazily construct the official SDK client from configured environment."""
        settings = GraniteRoleBriefSettings.from_environment(environ)
        if (credentials_factory is None) != (model_factory is None):
            raise GraniteRoleBriefConfigurationError(
                "Provider factories must be supplied together."
            )
        if credentials_factory is None and model_factory is None:
            try:
                from ibm_watsonx_ai import Credentials
                from ibm_watsonx_ai.foundation_models import ModelInference
            except ImportError:
                raise GraniteRoleBriefConfigurationError(
                    "The configured Granite provider is unavailable."
                ) from None
            credentials_factory = Credentials
            model_factory = ModelInference
        try:
            credentials = credentials_factory(
                url=settings.url,
                api_key=settings.api_key,
            )
            client = model_factory(
                model_id=settings.model_id,
                credentials=credentials,
                project_id=settings.project_id,
            )
        except Exception:
            raise GraniteRoleBriefConfigurationError(
                "The configured Granite provider is unavailable."
            ) from None
        return cls(
            client,
            model_id=settings.model_id,
            max_completion_tokens=max_completion_tokens,
        )

    def generate(
        self,
        plan: RoleBriefPlanSet,
        context: RoleBriefGenerationContext,
    ) -> RoleImpactBriefSet:
        """Generate and validate all five briefs through exactly one chat call."""
        try:
            trusted_context = RoleBriefGenerationContext.model_validate(
                context.model_dump(mode="python")
            )
            trusted_plan = validate_role_brief_plan_set(
                RoleBriefPlanSet.model_validate(plan.model_dump(mode="python")),
                trusted_context,
            )
        except (AttributeError, TypeError, ValueError, ValidationError):
            raise GraniteRoleBriefProviderError(
                "Role brief generation plan is inconsistent."
            ) from None
        params = {
            "temperature": 0,
            "max_completion_tokens": self._max_completion_tokens,
            "n": 1,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "role_impact_brief_wire",
                    "schema": _build_response_schema(trusted_plan),
                    "strict": False,
                },
            },
        }
        try:
            response = self._client.chat(
                messages=[
                    {"role": "system", "content": _SYSTEM_MESSAGE},
                    {"role": "user", "content": _canonical_plan(trusted_plan)},
                ],
                params=params,
            )
        except Exception:
            raise GraniteRoleBriefProviderError(
                "watsonx.ai role-brief generation failed."
            ) from None
        try:
            brief_set = _wire_to_brief_set(
                _extract_json(response),
                trusted_plan,
                trusted_context,
            )
            return validate_role_impact_brief_set(brief_set, trusted_context)
        except (
            GraniteRoleBriefResponseError,
            RoleImpactBriefValidationError,
            ValidationError,
            ValueError,
            TypeError,
        ):
            raise GraniteRoleBriefResponseError(
                "Granite returned an unsafe role-brief response."
            ) from None
