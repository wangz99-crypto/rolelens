"""Strict product-native contracts and validators for Granite role briefs.

Granite may interpret only the trusted state represented by
``RoleBriefGenerationContext``.  Validation in this module is deterministic
and rejects the complete five-role response when any brief crosses a RoleLens
authority or grounding boundary.
"""

from __future__ import annotations

import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


RoleKey = Literal[
    "executive",
    "data_analyst",
    "data_engineer",
    "sales_marketing",
    "project_manager",
]
ImpactKind = Literal["current", "unchanged", "recomputed", "changed", "blocked"]

ROLE_ORDER: tuple[RoleKey, ...] = (
    "executive",
    "data_analyst",
    "data_engineer",
    "sales_marketing",
    "project_manager",
)

BriefText = Annotated[str, Field(min_length=1, max_length=320)]
HandoffText = Annotated[str, Field(min_length=1, max_length=240)]
ContextText = Annotated[str, Field(min_length=1, max_length=1200)]
ShortText = Annotated[str, Field(min_length=1, max_length=160)]
DecimalText = Annotated[str, Field(pattern=r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$")]


class RoleImpactBriefValidationError(ValueError):
    """Raised when a generated brief set fails deterministic trust checks."""


class _BriefContract(BaseModel):
    """Frozen, extra-forbidding base for all Slice 4 brief contracts."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class RoleImpactBrief(_BriefContract):
    """One bounded role-aware interpretation of trusted deterministic state."""

    role_key: RoleKey
    why_it_matters: BriefText
    what_still_holds: BriefText
    what_to_verify_next: BriefText
    evidence_refs: Annotated[tuple[str, ...], Field(min_length=1, max_length=7)]
    assumption_refs: Annotated[tuple[str, ...], Field(max_length=4)]
    next_handoff: HandoffText

    @field_validator(
        "why_it_matters",
        "what_still_holds",
        "what_to_verify_next",
        "next_handoff",
    )
    @classmethod
    def text_is_plain_and_bounded(cls, value: str) -> str:
        """Reject surrounding whitespace, HTML, and control characters."""
        if value != value.strip():
            raise ValueError("brief text must not contain surrounding whitespace")
        if "<" in value or ">" in value:
            raise ValueError("brief text must not contain HTML")
        if any(ord(character) < 32 and character not in "\t" for character in value):
            raise ValueError("brief text must not contain control characters")
        return value

    @model_validator(mode="after")
    def references_are_unique(self) -> "RoleImpactBrief":
        """Reject duplicate references inside one brief."""
        if len(self.evidence_refs) != len(set(self.evidence_refs)):
            raise ValueError("evidence_refs must not contain duplicates")
        if len(self.assumption_refs) != len(set(self.assumption_refs)):
            raise ValueError("assumption_refs must not contain duplicates")
        return self


class RoleImpactBriefSet(_BriefContract):
    """Exactly one brief for each approved role in stable product order."""

    briefs: Annotated[tuple[RoleImpactBrief, ...], Field(min_length=5, max_length=5)]

    @model_validator(mode="after")
    def roles_are_exact_and_ordered(self) -> "RoleImpactBriefSet":
        """Require all and only the five approved roles in canonical order."""
        role_keys = tuple(brief.role_key for brief in self.briefs)
        if role_keys != ROLE_ORDER:
            raise ValueError("briefs must contain the five approved roles in stable order")
        return self


class DecisionIdentityContext(_BriefContract):
    """Bounded identity for the trusted product Decision."""

    decision_id: ShortText
    title: ShortText
    business_question: ContextText


class AcceptedRevisionContext(_BriefContract):
    """Identity and human label of the accepted deterministic revision."""

    revision_id: Literal["rev-001", "rev-002"]
    label: Literal["Baseline", "Human revision"]


class TrustedScenarioContext(_BriefContract):
    """Exact string projection of the already-calculated scenario result."""

    status: Literal[
        "CLEARS_BREAK_EVEN", "DOES_NOT_CLEAR_BREAK_EVEN", "NOT_EVALUABLE"
    ]
    expected_incremental_retained: DecimalText
    expected_scenario_value: DecimalText
    intervention_cost: DecimalText
    net_scenario_value: DecimalText
    break_even_lift: DecimalText
    currency: Literal["USD"]


class AcceptedAssumptionContext(_BriefContract):
    """One accepted human scenario assumption with exact decimal transport."""

    assumption_id: Literal["asm-001", "asm-002", "asm-003", "asm-004"]
    label: ShortText
    value: DecimalText
    unit: ShortText
    currency: Literal["USD"] | None


class ChangedAssumptionContext(_BriefContract):
    """One real baseline-to-accepted assumption change."""

    assumption_id: Literal["asm-001", "asm-002", "asm-003", "asm-004"]
    before_value: DecimalText
    after_value: DecimalText


class TrustedRoleStateContext(_BriefContract):
    """One deterministic role posture supplied for interpretation only."""

    role_key: RoleKey
    state: ShortText
    impact_kind: ImpactKind


class GovernedEvidenceContext(_BriefContract):
    """One bounded observed Evidence projection safe for Granite context."""

    evidence_id: ShortText
    label: ShortText
    finding: ContextText
    scope: Literal["internal_observation"]
    limitations: Annotated[tuple[ContextText, ...], Field(max_length=8)]
    relevant_roles: Annotated[tuple[RoleKey, ...], Field(min_length=1, max_length=5)]


class AllowedEvidenceContext(_BriefContract):
    """One governed Evidence projection explicitly allowed for one role."""

    evidence_id: ShortText
    label: ShortText
    finding: ContextText
    scope: Literal["internal_observation"]
    limitations: Annotated[tuple[ContextText, ...], Field(max_length=8)]


class RoleBriefTargetContext(_BriefContract):
    """One deterministic generation target with role-filtered grounding."""

    role_key: RoleKey
    state: ShortText
    impact_kind: ImpactKind
    allowed_evidence: Annotated[
        tuple[AllowedEvidenceContext, ...], Field(min_length=1, max_length=7)
    ]
    required_assumption_refs: Annotated[tuple[str, ...], Field(max_length=4)]
    allowed_handoff_roles: Annotated[
        tuple[RoleKey, ...], Field(min_length=1, max_length=5)
    ]

    @model_validator(mode="after")
    def target_collections_are_unique(self) -> "RoleBriefTargetContext":
        """Reject duplicate Evidence, assumption, and handoff references."""
        evidence_ids = tuple(item.evidence_id for item in self.allowed_evidence)
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("allowed_evidence must not contain duplicate IDs")
        if len(self.required_assumption_refs) != len(
            set(self.required_assumption_refs)
        ):
            raise ValueError("required_assumption_refs must not contain duplicates")
        if len(self.allowed_handoff_roles) != len(set(self.allowed_handoff_roles)):
            raise ValueError("allowed_handoff_roles must not contain duplicates")
        return self


class FoundationStateContext(_BriefContract):
    """Trusted invariants that scenario revisions cannot rewrite."""

    observed_evidence: Literal["unchanged", "locked"]
    data_health: Literal["unchanged", "checked"]
    source_provenance: Literal["unchanged", "locked"]


class RoleBriefGenerationContext(_BriefContract):
    """Complete bounded internal context for generation and strict validation."""

    decision: DecisionIdentityContext
    revision: AcceptedRevisionContext
    scenario: TrustedScenarioContext
    accepted_assumptions: Annotated[
        tuple[AcceptedAssumptionContext, ...], Field(min_length=4, max_length=4)
    ]
    changed_assumptions: Annotated[
        tuple[ChangedAssumptionContext, ...], Field(max_length=4)
    ]
    role_states: Annotated[
        tuple[TrustedRoleStateContext, ...], Field(min_length=5, max_length=5)
    ]
    role_targets: Annotated[
        tuple[RoleBriefTargetContext, ...], Field(min_length=5, max_length=5)
    ]
    governed_evidence: Annotated[
        tuple[GovernedEvidenceContext, ...], Field(min_length=7, max_length=7)
    ]
    foundation: FoundationStateContext

    @model_validator(mode="after")
    def collections_are_canonical(self) -> "RoleBriefGenerationContext":
        """Fail closed unless all deterministic routing collections agree."""
        if tuple(item.role_key for item in self.role_states) != ROLE_ORDER:
            raise ValueError("role_states must use the stable approved role order")
        if tuple(item.role_key for item in self.role_targets) != ROLE_ORDER:
            raise ValueError("role_targets must use the stable approved role order")
        if tuple(item.assumption_id for item in self.accepted_assumptions) != (
            "asm-001",
            "asm-002",
            "asm-003",
            "asm-004",
        ):
            raise ValueError("accepted_assumptions must use canonical assumption order")
        evidence_ids = tuple(item.evidence_id for item in self.governed_evidence)
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("governed_evidence must not contain duplicate IDs")
        changed_ids = tuple(item.assumption_id for item in self.changed_assumptions)
        if len(changed_ids) != len(set(changed_ids)):
            raise ValueError("changed_assumptions must not contain duplicate IDs")
        accepted_ids = {item.assumption_id for item in self.accepted_assumptions}
        if any(item not in accepted_ids for item in changed_ids):
            raise ValueError("changed_assumptions contains an unknown assumption ID")

        evidence_by_id = {item.evidence_id: item for item in self.governed_evidence}
        role_state_by_key = {item.role_key: item for item in self.role_states}
        for target in self.role_targets:
            state = role_state_by_key[target.role_key]
            if (target.state, target.impact_kind) != (state.state, state.impact_kind):
                raise ValueError("role target state does not match trusted role state")

            allowed_ids = tuple(item.evidence_id for item in target.allowed_evidence)
            expected_ids = tuple(
                item.evidence_id
                for item in self.governed_evidence
                if target.role_key in item.relevant_roles
            )
            if allowed_ids != expected_ids:
                raise ValueError(
                    "role target allowed Evidence must exactly match governed relevance"
                )
            for allowed in target.allowed_evidence:
                governed = evidence_by_id.get(allowed.evidence_id)
                if governed is None:
                    raise ValueError("role target contains unknown allowed Evidence")
                if target.role_key not in governed.relevant_roles:
                    raise ValueError("role target contains role-irrelevant Evidence")
                if allowed.model_dump() != governed.model_dump(
                    exclude={"relevant_roles"}
                ):
                    raise ValueError("role target allowed Evidence projection is inconsistent")

            expected_required = (
                changed_ids
                if changed_ids
                and target.impact_kind in {"changed", "blocked", "recomputed"}
                else ()
            )
            if target.required_assumption_refs != expected_required:
                raise ValueError(
                    "role target required assumptions do not match trusted changes"
                )
            if any(item not in accepted_ids for item in target.required_assumption_refs):
                raise ValueError("role target contains an unknown required assumption")
            if any(item not in ROLE_ORDER for item in target.allowed_handoff_roles):
                raise ValueError("role target contains an unapproved handoff role")
        return self


def build_role_brief_targets(
    role_states: tuple[TrustedRoleStateContext, ...],
    governed_evidence: tuple[GovernedEvidenceContext, ...],
    changed_assumptions: tuple[ChangedAssumptionContext, ...],
) -> tuple[RoleBriefTargetContext, ...]:
    """Derive exact per-role generation allowlists from trusted policy metadata."""
    changed_ids = tuple(item.assumption_id for item in changed_assumptions)
    return tuple(
        RoleBriefTargetContext(
            role_key=role_state.role_key,
            state=role_state.state,
            impact_kind=role_state.impact_kind,
            allowed_evidence=tuple(
                AllowedEvidenceContext(
                    evidence_id=evidence.evidence_id,
                    label=evidence.label,
                    finding=evidence.finding,
                    scope=evidence.scope,
                    limitations=evidence.limitations,
                )
                for evidence in governed_evidence
                if role_state.role_key in evidence.relevant_roles
            ),
            required_assumption_refs=(
                changed_ids
                if changed_ids
                and role_state.impact_kind in {"changed", "blocked", "recomputed"}
                else ()
            ),
            allowed_handoff_roles=ROLE_ORDER,
        )
        for role_state in role_states
    )


_POSITIVE_CLAIM_PATTERNS = (
    re.compile(r"\b(?:pilot|action|plan|decision)\s+(?:is|was|has been)\s+approved\b", re.I),
    re.compile(r"\bapproval\s+(?:is|was|has been)\s+granted\b", re.I),
    re.compile(r"\b(?:approve|authorize)\b[^.]{0,60}\b(?:pilot|action|plan|decision)\b", re.I),
    re.compile(r"\b(?:we|granite|ai|the model)\s+(?:recommend(?:s)?\s+)?(?:approve|approves|approved|approving|authorize|authorizes)\b", re.I),
    re.compile(r"\bauthorized\s+to\b", re.I),
    re.compile(r"\b(?:tech support|contract|payment method|internet service|tenure|monthly charges?)\b[^.]{0,90}\b(?:causes?|caused|drives?|leads? to|results? in)\s+(?:customer\s+)?churn\b", re.I),
    re.compile(r"\b(?:lack of\s+)?(?:tech support|contract type|payment method|internet service)\b[^.]{0,80}\b(?:is|was|are|were)?\s*(?:a\s+)?(?:key\s+)?driver\s+of\s+(?:customer\s+)?churn\b", re.I),
    re.compile(r"\b(?:lack of\s+)?(?:tech support|contract type|payment method|internet service)\b[^.]{0,80}\b(?:is|was|are|were)\s+responsible\s+for\s+(?:customer\s+)?churn\b", re.I),
    re.compile(r"\bcustomers?\s+(?:will|would|are likely to|are expected to)\s+churn\b", re.I),
    re.compile(r"\b(?:customers?|subscribers?|accounts?|segments?)\b[^.]{0,70}\b(?:have|has)\s+(?:a\s+)?(?:higher|greater|elevated|increased)\s+(?:chance|likelihood|risk)\s+of\s+churning\b", re.I),
    re.compile(r"\b(?:customers?|subscribers?|accounts?|segments?)\b[^.]{0,70}\b(?:are|is)\s+more\s+likely\s+to\s+churn\b", re.I),
    re.compile(r"\b(?:this|the)\s+segment\b[^.]{0,40}\b(?:has|shows)\s+(?:an?\s+)?(?:elevated|higher|increased)\s+churn\s+risk\b", re.I),
    re.compile(r"\bpredict(?:s|ed|ing)?\b[^.]{0,70}\bchurn\b", re.I),
    re.compile(r"\bhigh[- ]risk customers?\b", re.I),
    re.compile(r"\btarget(?:ing|ed|s)?\b[^.]{0,60}\bcustomers?\b", re.I),
    re.compile(r"\bcontact(?:ing|ed|s)?\b[^.]{0,60}\bcustomers?\b", re.I),
    re.compile(r"\breach out to\b[^.]{0,60}\bcustomers?\b", re.I),
    re.compile(r"\boutreach\s+to\b[^.]{0,60}\bcustomers?\b", re.I),
    re.compile(r"\bprioriti[sz]e\b[^.]{0,80}\b(?:customers?|accounts?|subscribers?)\b[^.]{0,50}\bretention\b", re.I),
    re.compile(r"\b(?:focus|direct)\s+retention\s+efforts?\s+(?:on|toward|towards)\b[^.]{0,80}\b(?:customers?|accounts?|subscribers?)\b", re.I),
    re.compile(r"\b(?:begin|launch|proceed with|start)\b[^.]{0,50}\boutreach\b", re.I),
    re.compile(r"\b(?:granite|ai|the model)\b[^.]{0,80}\b(?:changed|set|determined|calculated|recomputed)\b[^.]{0,50}\b(?:decision|state|status|posture)\b", re.I),
    re.compile(r"\broi\s+(?:will|would|is expected to|is predicted to)\s+be\s+positive\b", re.I),
    re.compile(r"\b(?:has|have)\s+completed\b|\bcompleted\s+(?:work|validation|review)\b", re.I),
    re.compile(r"\b(?:legal|finance|compliance|human resources|hr)\s+(?:should|must|will)\b", re.I),
    re.compile(r"\b(?:owns|owner of|accountable for)\b", re.I),
    re.compile(r"\bby\s+(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|today|tomorrow)\b", re.I),
    re.compile(r"\bby\s+[0-9]{4}-[0-9]{2}-[0-9]{2}\b|\bwithin\s+[0-9]+\s+(?:days|weeks|months)\b", re.I),
    re.compile(r"\bdeadline\b", re.I),
)

_AUTHORITY_GATE_PATTERNS = (
    re.compile(
        r"\b(?:executive|manager|leadership|project manager|data analyst|data engineer|sales(?:\s*/\s*|\s+and\s+|\s+)marketing)\s+(?:approval|authorization)\b",
        re.I,
    ),
    re.compile(
        r"\b(?:requires?|needs?|awaits?|obtain(?:s|ed|ing)?|seek(?:s|ing)?)\s+(?:(?:executive|manager|leadership|project manager|data analyst|data engineer)\s+)?(?:approval|authorization)\b",
        re.I,
    ),
    re.compile(
        r"\bwait(?:s|ed|ing)?\s+for\s+(?:(?:executive|manager|leadership|project manager|data analyst|data engineer)\s+)?(?:approval|authorization)\b",
        re.I,
    ),
    re.compile(
        r"\b(?:after|pending|subject\s+to)\s+(?:(?:executive|manager|leadership|project manager|data analyst|data engineer)\s+)?(?:approval|authorization)\b",
        re.I,
    ),
    re.compile(
        r"\b(?:approval|authorization)\s+(?:is\s+)?(?:required|needed|pending)\b",
        re.I,
    ),
    re.compile(r"\bmust\s+be\s+authorized\b", re.I),
    re.compile(
        r"\b(?:grant(?:s|ed|ing)?|request(?:s|ed|ing)?)\s+(?:approval|authorization)\b",
        re.I,
    ),
    re.compile(r"\b(?:approv(?:e|es|ed|ing)|authoriz(?:e|es|ed|ing))\b", re.I),
)

_NEGATING_PREFIXES = (
    "not ",
    "no ",
    "never ",
    "do not ",
    "does not ",
    "did not ",
    "must not ",
    "cannot ",
    "should not ",
    "avoid ",
    "without ",
    "blocked from ",
    "remain blocked ",
)


_NEGATION_WINDOW = re.compile(
    r"(?:\bnot|\bno|\bnever|\bwithout|\bcannot|\bcan't|\bavoid(?:s|ed|ing)?|\bblocked\s+from)\b(?:\s+[a-z-]+){0,3}\s*$",
    re.I,
)
_BLOCKED_SALES_REVERSAL_PATTERNS = (
    re.compile(r"\beligible\s+to\s+proceed\b", re.I),
    re.compile(r"\bproceed\s+with\s+(?:the\s+)?pilot\b", re.I),
    re.compile(r"\bmove\s+forward\s+with\s+(?:the\s+)?(?:pilot|outreach|campaign)\b", re.I),
    re.compile(r"\b(?:initiate|begin|launch|start)\s+(?:the\s+)?(?:outreach|campaign|pilot)\b", re.I),
)
_ANALYST_EVIDENCE_BOUNDARY_PATTERNS = (
    re.compile(r"\b(?:revise|rewrite|rewriting|update|modify|alter)\b[^.]{0,65}\b(?:observed\s+)?evidence\b", re.I),
    re.compile(r"\buse\b[^.]{0,70}\bassumption\b[^.]{0,30}\bas\s+(?:observed\s+)?evidence\b", re.I),
    re.compile(r"\bassumption\b[^.]{0,55}\b(?:becomes?|constitutes?|proves?)\b[^.]{0,40}\b(?:evidence|observed business fact|retention improvement)\b", re.I),
)
_ENGINEER_WORK_PATTERNS = (
    re.compile(r"\bdeploy\b[^.]{0,45}\bpipeline\b", re.I),
    re.compile(r"\brebuild\b[^.]{0,35}\betl\b", re.I),
    re.compile(r"\bchange\b[^.]{0,35}\bschema\b", re.I),
    re.compile(r"\bmodify\b[^.]{0,35}\bingestion\b", re.I),
    re.compile(r"\bmigrate\b[^.]{0,35}\bdata\b", re.I),
    re.compile(r"\balter\b[^.]{0,35}\bdata\s+model\b", re.I),
    re.compile(r"\bpipeline\s+change\b[^.]{0,35}\b(?:required|needed|indicated)\b", re.I),
)
_APPROVED_HANDOFF_LABELS: tuple[tuple[str, RoleKey], ...] = (
    ("Executive", "executive"),
    ("Data Analyst", "data_analyst"),
    ("Data Engineer", "data_engineer"),
    ("Sales / Marketing", "sales_marketing"),
    ("Project Manager", "project_manager"),
)
_APPROVED_ROLE_MENTION_PATTERNS = tuple(
    re.compile(pattern, re.I)
    for pattern in (
        r"\bexecutive\b",
        r"\bdata analyst\b",
        r"\bdata engineer\b",
        r"\bsales(?:\s*/\s*|\s+and\s+|\s+)marketing\b",
        r"\bproject manager\b",
    )
)
_UNAPPROVED_ORGANIZATIONAL_REFERENCES = re.compile(
    r"\b(?:customer success|legal|finance|human resources|hr|compliance|engineering manager|account management|revenue strategy|retention team|operations)\b",
    re.I,
)


def _match_is_negated(text: str, match_start: int) -> bool:
    """Recognize explicit local negation immediately before a matched phrase."""
    prefix = text.lower()[max(0, match_start - 56) : match_start]
    if any(prefix.endswith(negation) for negation in _NEGATING_PREFIXES):
        return True
    return _NEGATION_WINDOW.search(prefix) is not None


def _contains_unnegated_match(
    text: str,
    patterns: tuple[re.Pattern[str], ...],
) -> bool:
    """Apply one shared local-negation rule to deterministic phrase patterns."""
    return any(
        not _match_is_negated(text, match.start())
        for pattern in patterns
        for match in pattern.finditer(text)
    )


def _contains_prohibited_claim(text: str) -> bool:
    """Return whether bounded text contains an unnegated prohibited claim."""
    return _contains_unnegated_match(
        text,
        (*_POSITIVE_CLAIM_PATTERNS, *_AUTHORITY_GATE_PATTERNS),
    )


def _parse_next_handoff(
    next_handoff: str,
) -> tuple[RoleKey | Literal["none"], str]:
    """Parse one exact controlled-none or canonical approved-label handoff."""
    if next_handoff == "No additional cross-functional handoff is indicated.":
        return "none", ""
    for label, role_key in _APPROVED_HANDOFF_LABELS:
        prefix = f"{label} — "
        if next_handoff.startswith(prefix):
            action = next_handoff[len(prefix) :]
            if not action or action != action.strip():
                raise RoleImpactBriefValidationError(
                    "next_handoff action must be non-empty and canonical"
                )
            return role_key, action
    raise RoleImpactBriefValidationError(
        "next_handoff must start with an approved RoleLens function"
    )


def _validate_next_handoff(next_handoff: str) -> None:
    """Validate canonical WHO syntax and targeted action-level references."""
    target_role, action = _parse_next_handoff(next_handoff)
    if target_role == "none":
        return
    redacted_action = action
    for pattern in _APPROVED_ROLE_MENTION_PATTERNS:
        redacted_action = pattern.sub("", redacted_action)
    if _UNAPPROVED_ORGANIZATIONAL_REFERENCES.search(redacted_action):
        raise RoleImpactBriefValidationError(
            "next_handoff contains an unapproved organizational function"
        )


def validate_role_impact_brief_set(
    brief_set: RoleImpactBriefSet,
    context: RoleBriefGenerationContext,
) -> RoleImpactBriefSet:
    """Apply all deterministic grounding and authority checks to five briefs."""
    evidence_by_id = {item.evidence_id: item for item in context.governed_evidence}
    assumption_ids = {item.assumption_id for item in context.accepted_assumptions}
    target_by_key = {item.role_key: item for item in context.role_targets}

    for brief in brief_set.briefs:
        for evidence_ref in brief.evidence_refs:
            evidence = evidence_by_id.get(evidence_ref)
            if evidence is None:
                raise RoleImpactBriefValidationError("brief contains an unknown Evidence ref")
            if brief.role_key not in evidence.relevant_roles:
                raise RoleImpactBriefValidationError(
                    "brief contains an Evidence ref irrelevant to its role"
                )
        if any(ref not in assumption_ids for ref in brief.assumption_refs):
            raise RoleImpactBriefValidationError("brief contains an unknown assumption ref")

        target = target_by_key[brief.role_key]
        if not set(target.required_assumption_refs).issubset(brief.assumption_refs):
            raise RoleImpactBriefValidationError(
                "scenario-impact brief must cite a real changed assumption"
            )

        combined_text = " ".join(
            (
                brief.why_it_matters,
                brief.what_still_holds,
                brief.what_to_verify_next,
                brief.next_handoff,
            )
        )
        _validate_next_handoff(brief.next_handoff)
        if (
            brief.role_key == "sales_marketing"
            and target.impact_kind == "blocked"
            and _contains_unnegated_match(
                combined_text,
                _BLOCKED_SALES_REVERSAL_PATTERNS,
            )
        ):
            raise RoleImpactBriefValidationError(
                "blocked Sales brief must not recommend proceeding"
            )
        if (
            brief.role_key == "data_analyst"
            and _contains_unnegated_match(
                combined_text,
                _ANALYST_EVIDENCE_BOUNDARY_PATTERNS,
            )
        ):
            raise RoleImpactBriefValidationError(
                "Data Analyst brief must preserve Evidence and assumption separation"
            )
        if (
            brief.role_key == "data_engineer"
            and context.foundation.data_health == "unchanged"
            and context.foundation.source_provenance == "unchanged"
            and _contains_unnegated_match(
                combined_text,
                _ENGINEER_WORK_PATTERNS,
            )
        ):
            raise RoleImpactBriefValidationError(
                "Data Engineer brief must not invent technical work"
            )
        if _contains_prohibited_claim(combined_text):
            raise RoleImpactBriefValidationError(
                "brief contains a prohibited authority or unsupported claim"
            )

    return brief_set
