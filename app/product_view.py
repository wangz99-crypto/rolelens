"""Pure presentation models for the RoleLens product-first demo.

This module transforms existing validated pipeline results into compact,
immutable view models.  It does not import Streamlit, read environment
variables, construct providers, or perform I/O.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Any

from app.dataset_orientation import (
    DatasetOrientationBrief,
    DatasetOrientationFailure,
    build_dataset_primer,
)
from app.role_engine import InsufficientEvidence, RoleGenerationFailure
from app.schemas import (
    DecisionMemo,
    RoleKey,
    RoleView,
    WorkflowPlanStatus,
    WorkflowStep,
    WorkflowStepKind,
)


_IBM_DISCLOSURE = (
    "This is a fictional IBM sample dataset, not real customer production data."
)
_IBM_POSTURE = (
    "Limited validation pilot for human review; no customer targeting or outreach."
)
_ROLE_ORDER = (
    RoleKey.executive,
    RoleKey.data_analyst,
    RoleKey.data_engineer,
    RoleKey.sales_marketing,
    RoleKey.project_manager,
)
_ROLE_NAMES = {
    RoleKey.executive: "Executive",
    RoleKey.data_analyst: "Data Analyst / Data Scientist",
    RoleKey.data_engineer: "Data Engineer",
    RoleKey.sales_marketing: "Sales / Marketing",
    RoleKey.project_manager: "Project Manager",
}
_PRIMARY_QUESTIONS = {
    RoleKey.executive: "Should leadership permit a limited validation pilot?",
    RoleKey.data_analyst: (
        "Which aggregate patterns are credible, and what remains unvalidated?"
    ),
    RoleKey.data_engineer: (
        "Is the data reliable and reproducible enough for downstream use?"
    ),
    RoleKey.sales_marketing: (
        "What aggregate segments merit validation without customer-level targeting?"
    ),
    RoleKey.project_manager: (
        "What must happen first, and where are the dependencies and review gates?"
    ),
}


def _require_text(value: Any, field_name: str) -> None:
    """Reject a non-string or blank required presentation field."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be blank")


def _require_text_tuple(values: Any, field_name: str) -> None:
    """Require an immutable tuple containing only non-blank strings."""
    if type(values) is not tuple:
        raise TypeError(f"{field_name} must be a tuple")
    for value in values:
        _require_text(value, field_name)


@dataclass(frozen=True)
class MetricCard:
    """One compact, deterministic metric shown in the Decision Brief."""

    label: str
    value: str
    help_text: str

    def __post_init__(self) -> None:
        for item in fields(self):
            _require_text(getattr(self, item.name), item.name)


@dataclass(frozen=True)
class PatternCard:
    """One presentation pattern with unchanged Evidence citations."""

    headline: str
    explanation: str
    evidence_ids: tuple[str, ...]
    source_label: str

    def __post_init__(self) -> None:
        _require_text(self.headline, "headline")
        _require_text(self.explanation, "explanation")
        _require_text(self.source_label, "source_label")
        _require_text_tuple(self.evidence_ids, "evidence_ids")
        if not self.evidence_ids:
            raise ValueError("evidence_ids must not be empty")


@dataclass(frozen=True)
class DecisionBriefView:
    """Primary business summary derived only from existing typed inputs."""

    dataset_name: str
    source_label: str
    disclosure: str
    business_question: str
    decision_status: str
    recommended_posture: str
    status_detail: str
    metrics: tuple[MetricCard, ...]
    patterns: tuple[PatternCard, ...]
    guardrails: tuple[str, ...]
    orientation_notice: str | None

    def __post_init__(self) -> None:
        for field_name in (
            "dataset_name",
            "source_label",
            "disclosure",
            "business_question",
            "decision_status",
            "recommended_posture",
            "status_detail",
        ):
            _require_text(getattr(self, field_name), field_name)
        if type(self.metrics) is not tuple:
            raise TypeError("metrics must be a tuple")
        if type(self.patterns) is not tuple:
            raise TypeError("patterns must be a tuple")
        _require_text_tuple(self.guardrails, "guardrails")
        if self.orientation_notice is not None:
            _require_text(self.orientation_notice, "orientation_notice")


@dataclass(frozen=True)
class RoleComparisonRow:
    """One policy role reduced to its primary decision-relevant contrast."""

    role_key: RoleKey
    role_name: str
    primary_question: str
    current_focus: str
    evidence_backed_signal: str
    next_handoff: str
    status: str

    def __post_init__(self) -> None:
        if type(self.role_key) is not RoleKey:
            raise TypeError("role_key must be a RoleKey")
        for item in fields(self):
            if item.name != "role_key":
                _require_text(getattr(self, item.name), item.name)


@dataclass(frozen=True)
class ActionPlanSummary:
    """Bounded product summary over an unchanged WorkflowPlan."""

    plan_status: str
    step_count: int
    blocker_count: int
    review_gate_count: int
    priority_blockers: tuple[WorkflowStep, ...]
    role_actions: tuple[WorkflowStep, ...]

    def __post_init__(self) -> None:
        _require_text(self.plan_status, "plan_status")
        for field_name in ("step_count", "blocker_count", "review_gate_count"):
            value = getattr(self, field_name)
            if type(value) is not int or value < 0:
                raise ValueError(f"{field_name} must be a non-negative integer")
        for field_name in ("priority_blockers", "role_actions"):
            values = getattr(self, field_name)
            if type(values) is not tuple:
                raise TypeError(f"{field_name} must be a tuple")
            if any(type(value) is not WorkflowStep for value in values):
                raise TypeError(f"{field_name} must contain WorkflowStep values")


@dataclass(frozen=True)
class MemoSummary:
    """Compact summary over an unchanged, reviewed DecisionMemo."""

    memo_status: str
    retained_count: int
    rejected_count: int
    unresolved_blocker_count: int
    revision_count: int
    top_retained_actions: tuple[Any, ...]
    rejected_actions: tuple[Any, ...]
    control_notices: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_text(self.memo_status, "memo_status")
        for field_name in (
            "retained_count",
            "rejected_count",
            "unresolved_blocker_count",
            "revision_count",
        ):
            value = getattr(self, field_name)
            if type(value) is not int or value < 0:
                raise ValueError(f"{field_name} must be a non-negative integer")
        if type(self.top_retained_actions) is not tuple:
            raise TypeError("top_retained_actions must be a tuple")
        if type(self.rejected_actions) is not tuple:
            raise TypeError("rejected_actions must be a tuple")
        _require_text_tuple(self.control_notices, "control_notices")


def _business_evidence_id(prepared_inputs: Any, evidence_type: str) -> str:
    """Return the unique matching business Evidence ID or fail closed."""
    matches = [
        evidence.evidence_id
        for evidence in prepared_inputs.evidence_objects
        if evidence.evidence_type == evidence_type
    ]
    if len(matches) != 1:
        raise ValueError(f"Expected one {evidence_type} Evidence Object")
    return matches[0]


def _fallback_patterns(prepared_inputs: Any) -> tuple[PatternCard, ...]:
    """Derive three deterministic patterns from profile values and Evidence."""
    profile = prepared_inputs.business_profile
    contract_text = ", ".join(
        f"{item.segment}: {item.churn_rate_pct:.2f}%"
        for item in profile.contract_rates
    )
    median_text = "; ".join(
        (
            f"Churn {item.churn_status}: median tenure {item.median_tenure:g}, "
            f"median MonthlyCharges {item.median_monthly_charges:.2f}"
        )
        for item in profile.medians_by_churn_status
    )
    source = "Deterministic business profile"
    return (
        PatternCard(
            headline="Recorded churn in the sample",
            explanation=(
                f"{profile.churned_count:,} of {profile.unique_customer_count:,} "
                f"customers have recorded churn ({profile.overall_churn_rate_pct:.2f}%)."
            ),
            evidence_ids=(
                _business_evidence_id(prepared_inputs, "business_overall_churn"),
            ),
            source_label=source,
        ),
        PatternCard(
            headline="Recorded churn differs by contract type",
            explanation=contract_text,
            evidence_ids=(
                _business_evidence_id(prepared_inputs, "business_contract_churn"),
            ),
            source_label=source,
        ),
        PatternCard(
            headline="Tenure and MonthlyCharges medians differ by churn status",
            explanation=median_text,
            evidence_ids=(
                _business_evidence_id(prepared_inputs, "business_churn_medians"),
            ),
            source_label=source,
        ),
    )


def build_decision_brief(
    prepared_inputs: Any,
    analysis_result: Any = None,
    *,
    source_label: str,
) -> DecisionBriefView:
    """Build the primary business brief without adding decision evidence."""
    _require_text(source_label, "source_label")
    profile = prepared_inputs.business_profile
    business_question = prepared_inputs.available_inputs.get("business_question", "")
    _require_text(business_question, "business_question")

    if profile is None:
        return DecisionBriefView(
            dataset_name=source_label,
            source_label=source_label,
            disclosure="No registered business playbook is active for this source.",
            business_question=business_question,
            decision_status="CUSTOM EVIDENCE MODE",
            recommended_posture=(
                "Review generic data health and Evidence before drawing conclusions."
            ),
            status_detail=(
                "RoleLens prepared generic Evidence; no IBM Telco profile or "
                "dataset-specific posture was applied."
            ),
            metrics=(),
            patterns=(),
            guardrails=(),
            orientation_notice=(
                "A registered business playbook is not active for this source."
            ),
        )

    primer = (
        analysis_result.dataset_primer
        if analysis_result is not None and analysis_result.dataset_primer is not None
        else build_dataset_primer(profile, business_question=business_question)
    )
    metrics = (
        MetricCard("Customers", f"{profile.unique_customer_count:,}", "Unique customer accounts in the frozen sample."),
        MetricCard("Recorded churn", f"{profile.churned_count:,}", "Customers whose Churn field is Yes."),
        MetricCard("Overall churn rate", f"{profile.overall_churn_rate_pct:.2f}%", "Descriptive recorded churn rate; not a prediction."),
        MetricCard("TotalCharges parse issues", f"{profile.total_charges_parse_issue_count:,}", "Blank values that cannot be parsed as numeric TotalCharges."),
    )
    patterns = _fallback_patterns(prepared_inputs)
    notice: str | None = None
    if analysis_result is None:
        status = "EVIDENCE READY"
        detail = (
            "Deterministic Evidence is prepared; live analysis and human review "
            "have not occurred."
        )
    else:
        plan_status = analysis_result.workflow_plan.plan_status
        if plan_status is WorkflowPlanStatus.blocked:
            status = "VALIDATION REQUIRED"
            detail = "The typed WorkflowPlan is blocked pending validation; nothing is approved or executable."
        elif plan_status is WorkflowPlanStatus.ready_for_human_review:
            status = "READY FOR HUMAN REVIEW"
            detail = "The typed WorkflowPlan is ready for explicit human review; it is not approved for execution."
        else:
            status = "NO ACTIONABLE WORKFLOW"
            detail = "The typed WorkflowPlan contains no actionable steps and still requires explicit acknowledgment."

        orientation = analysis_result.dataset_orientation_outcome
        if isinstance(orientation, DatasetOrientationBrief):
            patterns = tuple(
                PatternCard(
                    headline=item.headline,
                    explanation=item.plain_language_explanation,
                    evidence_ids=tuple(item.evidence_ids),
                    source_label="IBM Granite orientation",
                )
                for item in orientation.key_patterns
            )
        elif isinstance(orientation, DatasetOrientationFailure):
            notice = (
                "IBM Granite orientation was unavailable; the deterministic "
                "business profile is shown."
            )

    return DecisionBriefView(
        dataset_name=profile.dataset_name,
        source_label=source_label,
        disclosure=_IBM_DISCLOSURE,
        business_question=business_question,
        decision_status=status,
        recommended_posture=_IBM_POSTURE,
        status_detail=detail,
        metrics=metrics,
        patterns=patterns,
        guardrails=tuple(primer.guardrails),
        orientation_notice=notice,
    )


def build_role_comparison(analysis_result: Any) -> tuple[RoleComparisonRow, ...]:
    """Return five compact rows in canonical role order."""
    rows: list[RoleComparisonRow] = []
    for role_key in _ROLE_ORDER:
        outcome = analysis_result.role_outcomes[role_key]
        if isinstance(outcome, RoleView):
            rows.append(
                RoleComparisonRow(
                    role_key=role_key,
                    role_name=_ROLE_NAMES[role_key],
                    primary_question=_PRIMARY_QUESTIONS[role_key],
                    current_focus=outcome.role_concern,
                    evidence_backed_signal=outcome.key_findings[0].claim,
                    next_handoff=(
                        outcome.next_action
                        or outcome.dependency
                        or "No next action identified."
                    ),
                    status="Role view ready",
                )
            )
        elif isinstance(outcome, InsufficientEvidence):
            rows.append(
                RoleComparisonRow(
                    role_key=role_key,
                    role_name=_ROLE_NAMES[role_key],
                    primary_question=_PRIMARY_QUESTIONS[role_key],
                    current_focus="No grounded role view is available.",
                    evidence_backed_signal="No usable role insight was produced.",
                    next_handoff="Resolve the evidence gap before proposing an action.",
                    status="Insufficient evidence",
                )
            )
        elif isinstance(outcome, RoleGenerationFailure):
            rows.append(
                RoleComparisonRow(
                    role_key=role_key,
                    role_name=_ROLE_NAMES[role_key],
                    primary_question=_PRIMARY_QUESTIONS[role_key],
                    current_focus="No validated role view is available.",
                    evidence_backed_signal="No usable role insight was produced.",
                    next_handoff="Resolve the typed generation failure before use.",
                    status=f"Generation failure: {outcome.failure_code}",
                )
            )
        else:
            raise TypeError("Unsupported role outcome")
    return tuple(rows)


def build_action_plan_summary(analysis_result: Any) -> ActionPlanSummary:
    """Compress an existing plan without merging or rewriting its steps."""
    plan = analysis_result.workflow_plan
    blockers = tuple(step for step in plan.steps if step.blocks_downstream)
    review_gates = tuple(
        step
        for step in plan.steps
        if step.step_kind is WorkflowStepKind.semantic_review_gate
    )
    role_actions = tuple(
        step
        for step in plan.steps
        if step.step_kind is WorkflowStepKind.role_action
    )
    return ActionPlanSummary(
        plan_status=plan.plan_status.value,
        step_count=len(plan.steps),
        blocker_count=len(blockers),
        review_gate_count=len(review_gates),
        priority_blockers=blockers[:3],
        role_actions=role_actions[:5],
    )


def build_memo_summary(memo: DecisionMemo) -> MemoSummary:
    """Summarize only existing DecisionMemo fields and records."""
    if type(memo) is not DecisionMemo:
        raise TypeError("memo must be exactly a DecisionMemo")
    return MemoSummary(
        memo_status=memo.memo_status.value,
        retained_count=len(memo.retained_actions),
        rejected_count=len(memo.rejected_steps),
        unresolved_blocker_count=len(memo.unresolved_blocking_step_ids),
        revision_count=len(memo.human_revision_step_ids),
        top_retained_actions=tuple(memo.retained_actions[:3]),
        rejected_actions=tuple(memo.rejected_steps),
        control_notices=tuple(memo.control_notices),
    )
