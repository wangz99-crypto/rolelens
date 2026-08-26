"""RoleLens adapter for the experimental DD-3 Decision Diff spike.

The adapter binds the generic DD-1/DD-2 contracts to the approved IBM Telco
business profile while keeping observed Evidence immutable and separate from
caller-supplied scenario assumptions. It performs no I/O and grants no
approval or execution authority.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator, model_validator

from app.business_profile import BusinessDatasetProfile
from app.decision_diff import ScenarioAssumption, ScenarioResult, ScenarioStatus
from app.decision_diff_engine import (
    DecisionDependencyNode,
    DecisionDependencyRegistry,
    DecisionDiff,
    DecisionDiffEngineError,
    DecisionImpactPolicy,
    DecisionImpactType,
    build_decision_diff,
)
from app.schemas import (
    DataHealthSummary,
    EvidenceObject,
    EvidenceScope,
    EvidenceStatus,
    SemanticContextCategory,
    SourceFormat,
    SourceManifestEntry,
    SourceScope,
)


class RoleLensDecisionDiffError(ValueError):
    """Raised when a public DD-3 operation fails closed validation."""


class _RoleLensDecisionDiffContract(BaseModel):
    """Frozen, extra-forbidding base for DD-3 public contracts."""

    model_config = ConfigDict(extra="forbid", frozen=True)


_PROFILE_ID = "ibm_telco_churn_v1"
_DATASET_NAME = "IBM Telco Customer Churn"
_BUSINESS_EVIDENCE_TYPES = (
    "business_overall_churn",
    "business_contract_churn",
    "business_support_churn",
    "business_internet_churn",
    "business_payment_churn",
    "business_churn_medians",
    "business_parseability",
)
_SCENARIO_KEYS = (
    "pilot_population",
    "expected_incremental_lift",
    "cost_per_intervention",
    "retained_customer_value",
)
_REGISTRY_OBJECT_TYPES = {
    "obj-observed-evidence": "observed_evidence",
    "obj-data-health": "data_health",
    "obj-source-provenance": "source_provenance",
    "obj-break-even": "scenario_result",
    "obj-executive-posture": "executive_posture",
    "obj-sales-posture": "sales_posture",
    "obj-pm-handoff": "project_manager_handoff",
    "obj-decision-brief": "decision_brief",
}
_CONTROL_NOTICE = (
    "Scenario postures support human review only and do not authorize customer "
    "targeting, outreach, approval, or execution."
)
_SEPARATION_NOTICE = "Scenario assumptions remain separate from observed Evidence."
_AUTHORITY_NOTICE = (
    "Scenario postures do not authorize customer targeting, outreach, approval, "
    "or execution."
)


def _canonical_json(value: BaseModel) -> str:
    """Return deterministic canonical JSON for one validated model."""
    return json.dumps(
        value.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def _parsed_canonical_model(
    snapshot_json: str,
    model_type: type[BaseModel],
) -> BaseModel:
    """Parse and revalidate canonical snapshot JSON without leaking diagnostics."""
    try:
        payload = json.loads(snapshot_json)
        model = model_type.model_validate(payload)
    except (json.JSONDecodeError, TypeError, ValidationError):
        raise ValueError("snapshot_json must contain valid canonical model JSON") from None
    if _canonical_json(model) != snapshot_json:
        raise ValueError("snapshot_json must use deterministic canonical JSON")
    return model


class EvidenceInvariantSnapshot(_RoleLensDecisionDiffContract):
    """Complete immutable snapshot of one existing business EvidenceObject."""

    evidence_id: str
    evidence_type: str
    identity_digest: str
    source_id: str
    finding: str
    snapshot_json: str

    @field_validator(
        "evidence_id",
        "evidence_type",
        "identity_digest",
        "source_id",
        "finding",
        "snapshot_json",
    )
    @classmethod
    def text_is_non_blank(cls, value: str) -> str:
        """Require every text field to contain meaningful content."""
        if not isinstance(value, str) or not value.strip():
            raise ValueError("snapshot text fields must not be blank")
        return value

    @model_validator(mode="after")
    def snapshot_matches_declared_identity(self) -> "EvidenceInvariantSnapshot":
        """Require the complete canonical EvidenceObject to match summary fields."""
        evidence = _parsed_canonical_model(self.snapshot_json, EvidenceObject)
        if (
            evidence.evidence_id != self.evidence_id
            or evidence.evidence_type != self.evidence_type
            or evidence.identity_digest != self.identity_digest
            or evidence.source_id != self.source_id
            or evidence.finding != self.finding
        ):
            raise ValueError("snapshot fields must match the complete EvidenceObject")
        return self


class RoleLensEvidenceBasis(_RoleLensDecisionDiffContract):
    """Fixed observed IBM Telco evidence, health, and source-provenance basis."""

    profile_id: Literal["ibm_telco_churn_v1"]
    dataset_name: Literal["IBM Telco Customer Churn"]
    data_source_id: str
    business_evidence: tuple[EvidenceInvariantSnapshot, ...]
    data_health_snapshot_json: str
    source_manifest_snapshot_json: str

    @field_validator(
        "data_source_id",
        "data_health_snapshot_json",
        "source_manifest_snapshot_json",
    )
    @classmethod
    def text_is_non_blank(cls, value: str) -> str:
        """Reject blank identifiers and snapshots."""
        if not isinstance(value, str) or not value.strip():
            raise ValueError("evidence-basis text fields must not be blank")
        return value

    @model_validator(mode="after")
    def basis_is_complete_and_consistent(self) -> "RoleLensEvidenceBasis":
        """Lock evidence order, identity uniqueness, health, and provenance."""
        if tuple(item.evidence_type for item in self.business_evidence) != (
            _BUSINESS_EVIDENCE_TYPES
        ):
            raise ValueError("business_evidence must use the approved fixed order")
        evidence_ids = tuple(item.evidence_id for item in self.business_evidence)
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("business evidence IDs must be unique")
        if any(item.source_id != self.data_source_id for item in self.business_evidence):
            raise ValueError("business evidence must share data_source_id")

        health = _parsed_canonical_model(
            self.data_health_snapshot_json,
            DataHealthSummary,
        )
        manifest = _parsed_canonical_model(
            self.source_manifest_snapshot_json,
            SourceManifestEntry,
        )
        if health.source_id != self.data_source_id:
            raise ValueError("data-health source must match data_source_id")
        if (
            manifest.source_id != self.data_source_id
            or manifest.source_format is not SourceFormat.csv
            or manifest.semantic_context_category
            is not SemanticContextCategory.data_source
            or manifest.source_scope is not SourceScope.internal_observation
        ):
            raise ValueError("source manifest must be the matching internal CSV source")
        return self


class ExecutiveScenarioPosture(str, Enum):
    """Non-authorizing Executive posture derived from scenario status."""

    LIMITED_PILOT_REVIEW_CANDIDATE = "LIMITED_PILOT_REVIEW_CANDIDATE"
    VALIDATE_SCENARIO_ASSUMPTIONS_FIRST = "VALIDATE_SCENARIO_ASSUMPTIONS_FIRST"


class SalesPilotPosture(str, Enum):
    """Non-authorizing Sales posture derived from scenario status."""

    ELIGIBLE_FOR_PILOT_REVIEW = "ELIGIBLE_FOR_PILOT_REVIEW"
    BLOCKED_BY_SCENARIO = "BLOCKED_BY_SCENARIO"


class ProjectManagerHandoff(str, Enum):
    """Non-authorizing PM handoff derived from scenario status."""

    PREPARE_LIMITED_PILOT_REVIEW = "PREPARE_LIMITED_PILOT_REVIEW"
    REOPEN_SCENARIO_VALIDATION = "REOPEN_SCENARIO_VALIDATION"


class ScenarioDecisionProjection(_RoleLensDecisionDiffContract):
    """Deterministic business postures for one evaluable scenario revision."""

    revision_id: str
    scenario_result: ScenarioResult
    executive_posture: ExecutiveScenarioPosture
    sales_posture: SalesPilotPosture
    project_manager_handoff: ProjectManagerHandoff
    evidence_ids: tuple[str, ...]
    assumption_ids: tuple[str, ...]
    control_notice: str

    @field_validator("revision_id", "control_notice")
    @classmethod
    def text_is_non_blank(cls, value: str) -> str:
        """Reject blank projection text."""
        if not isinstance(value, str) or not value.strip():
            raise ValueError("projection text fields must not be blank")
        return value

    @field_validator("evidence_ids")
    @classmethod
    def evidence_ids_are_complete(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """Require exactly seven unique, non-blank Evidence IDs."""
        if len(value) != 7 or len(value) != len(set(value)):
            raise ValueError("evidence_ids must contain seven unique IDs")
        if any(not isinstance(item, str) or not item.strip() for item in value):
            raise ValueError("evidence_ids must not contain blank IDs")
        return value

    @field_validator("assumption_ids")
    @classmethod
    def assumption_ids_are_complete(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """Require exactly four unique, non-blank assumption IDs."""
        if len(value) != 4 or len(value) != len(set(value)):
            raise ValueError("assumption_ids must contain four unique IDs")
        if any(not isinstance(item, str) or not item.strip() for item in value):
            raise ValueError("assumption_ids must not contain blank IDs")
        return value

    @model_validator(mode="after")
    def projection_matches_scenario_status(self) -> "ScenarioDecisionProjection":
        """Reject non-evaluable or posture-inconsistent caller constructions."""
        if self.revision_id != self.scenario_result.revision_id:
            raise ValueError("projection revision must match scenario result")
        if self.assumption_ids != self.scenario_result.input_assumption_ids:
            raise ValueError("projection assumptions must match scenario result order")
        if self.control_notice != _CONTROL_NOTICE:
            raise ValueError("projection control notice is invalid")
        if self.scenario_result.status is ScenarioStatus.CLEARS_BREAK_EVEN:
            expected = (
                ExecutiveScenarioPosture.LIMITED_PILOT_REVIEW_CANDIDATE,
                SalesPilotPosture.ELIGIBLE_FOR_PILOT_REVIEW,
                ProjectManagerHandoff.PREPARE_LIMITED_PILOT_REVIEW,
            )
        elif self.scenario_result.status is ScenarioStatus.DOES_NOT_CLEAR_BREAK_EVEN:
            expected = (
                ExecutiveScenarioPosture.VALIDATE_SCENARIO_ASSUMPTIONS_FIRST,
                SalesPilotPosture.BLOCKED_BY_SCENARIO,
                ProjectManagerHandoff.REOPEN_SCENARIO_VALIDATION,
            )
        else:
            raise ValueError("NOT_EVALUABLE scenarios cannot be projected")
        actual = (
            self.executive_posture,
            self.sales_posture,
            self.project_manager_handoff,
        )
        if actual != expected:
            raise ValueError("scenario status and business postures are inconsistent")
        return self


class RoleLensDecisionRevision(_RoleLensDecisionDiffContract):
    """Complete immutable DD-3 revision over one unchanged Evidence basis."""

    evidence_basis: RoleLensEvidenceBasis
    before_projection: ScenarioDecisionProjection
    after_projection: ScenarioDecisionProjection
    decision_diff: DecisionDiff
    unchanged_evidence_ids: tuple[str, ...]
    notices: tuple[str, ...]

    @model_validator(mode="after")
    def revision_is_complete_and_consistent(self) -> "RoleLensDecisionRevision":
        """Enforce projection, evidence, impact, and notice invariants."""
        evidence_ids = tuple(
            item.evidence_id for item in self.evidence_basis.business_evidence
        )
        diff = self.decision_diff
        if (
            self.before_projection.revision_id != diff.before_revision_id
            or self.after_projection.revision_id != diff.after_revision_id
        ):
            raise ValueError("projection revisions must match Decision Diff revisions")
        if (
            self.before_projection.scenario_result != diff.before_scenario_result
            or self.after_projection.scenario_result != diff.after_scenario_result
        ):
            raise ValueError("projection results must match Decision Diff results")
        if (
            self.before_projection.evidence_ids != evidence_ids
            or self.after_projection.evidence_ids != evidence_ids
            or self.unchanged_evidence_ids != evidence_ids
        ):
            raise ValueError("all revision evidence IDs must equal the Evidence basis")

        impacts = {item.object_id: item for item in diff.impacts}
        if len(diff.impacts) != len(_REGISTRY_OBJECT_TYPES) or set(impacts) != set(
            _REGISTRY_OBJECT_TYPES
        ):
            raise ValueError("Decision Diff must contain every DD-3 registry impact")
        if any(
            impacts[object_id].object_type != object_type
            for object_id, object_type in _REGISTRY_OBJECT_TYPES.items()
        ):
            raise ValueError("Decision Diff registry object types are inconsistent")
        for object_id in (
            "obj-observed-evidence",
            "obj-data-health",
            "obj-source-provenance",
        ):
            if impacts[object_id].impact_type is not DecisionImpactType.UNCHANGED:
                raise ValueError("observed product foundations must remain unchanged")

        currency = self.after_projection.scenario_result.currency
        currency_notice = (
            f"Scenario currency {currency} is user-supplied and is not inferred "
            "from the IBM Telco dataset."
            if currency is not None
            else "No scenario currency was supplied; the IBM Telco dataset currency "
            "remains unspecified."
        )
        if self.notices != (
            _SEPARATION_NOTICE,
            _AUTHORITY_NOTICE,
            currency_notice,
        ):
            raise ValueError("revision notices are invalid")
        return self


def _snapshot_product_inputs(
    business_profile: BusinessDatasetProfile,
    evidence_objects: Sequence[EvidenceObject],
    data_health_summary: DataHealthSummary,
    source_manifests: Sequence[SourceManifestEntry],
) -> str:
    """Snapshot every caller product input in deterministic sequence order."""
    payload = {
        "business_profile": business_profile.model_dump(mode="json"),
        "evidence_objects": [item.model_dump(mode="json") for item in evidence_objects],
        "data_health_summary": data_health_summary.model_dump(mode="json"),
        "source_manifests": [item.model_dump(mode="json") for item in source_manifests],
    }
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def _validate_product_inputs(
    business_profile: BusinessDatasetProfile,
    evidence_objects: Sequence[EvidenceObject],
    data_health_summary: DataHealthSummary,
    source_manifests: Sequence[SourceManifestEntry],
) -> None:
    """Revalidate exact current product contracts with controlled failures."""
    if type(business_profile) is not BusinessDatasetProfile:
        raise RoleLensDecisionDiffError(
            "business_profile must be the approved BusinessDatasetProfile."
        )
    if type(data_health_summary) is not DataHealthSummary:
        raise RoleLensDecisionDiffError(
            "data_health_summary must be a DataHealthSummary object."
        )
    if isinstance(evidence_objects, (str, bytes, bytearray)) or not isinstance(
        evidence_objects,
        Sequence,
    ):
        raise RoleLensDecisionDiffError(
            "evidence_objects must be a sequence of EvidenceObject values."
        )
    if isinstance(source_manifests, (str, bytes, bytearray)) or not isinstance(
        source_manifests,
        Sequence,
    ):
        raise RoleLensDecisionDiffError(
            "source_manifests must be a sequence of SourceManifestEntry values."
        )
    if any(type(item) is not EvidenceObject for item in evidence_objects):
        raise RoleLensDecisionDiffError(
            "evidence_objects must contain only exact EvidenceObject values."
        )
    if any(type(item) is not SourceManifestEntry for item in source_manifests):
        raise RoleLensDecisionDiffError(
            "source_manifests must contain only exact SourceManifestEntry values."
        )
    try:
        BusinessDatasetProfile.model_validate(business_profile.model_dump())
        DataHealthSummary.model_validate(data_health_summary.model_dump())
        for evidence in evidence_objects:
            EvidenceObject.model_validate(evidence.model_dump())
        for manifest in source_manifests:
            SourceManifestEntry.model_validate(manifest.model_dump())
    except (AttributeError, ValidationError):
        raise RoleLensDecisionDiffError(
            "RoleLens product inputs failed contract validation."
        ) from None


def _build_evidence_basis(
    business_profile: BusinessDatasetProfile,
    evidence_objects: Sequence[EvidenceObject],
    data_health_summary: DataHealthSummary,
    source_manifests: Sequence[SourceManifestEntry],
) -> RoleLensEvidenceBasis:
    """Select and snapshot the exact approved business Evidence foundation."""
    if (
        business_profile.profile_id != _PROFILE_ID
        or business_profile.dataset_name != _DATASET_NAME
    ):
        raise RoleLensDecisionDiffError(
            "Only the approved IBM Telco business profile is supported."
        )

    selected: list[EvidenceObject] = []
    for evidence_type in _BUSINESS_EVIDENCE_TYPES:
        matches = [
            item for item in evidence_objects if item.evidence_type == evidence_type
        ]
        if len(matches) != 1:
            raise RoleLensDecisionDiffError(
                "Exactly one active EvidenceObject is required for each approved "
                "business evidence type."
            )
        selected.append(matches[0])

    if any(
        item.status is not EvidenceStatus.active
        or item.evidence_scope is not EvidenceScope.internal_observation
        or item.extraction_method != "deterministic"
        or item.source_format is not SourceFormat.csv
        or item.created_by != "evidence_builder"
        for item in selected
    ):
        raise RoleLensDecisionDiffError(
            "Approved business Evidence must be active deterministic internal CSV "
            "observations created by evidence_builder."
        )
    evidence_ids = [item.evidence_id for item in selected]
    if len(evidence_ids) != len(set(evidence_ids)):
        raise RoleLensDecisionDiffError("Approved business Evidence IDs must be unique.")
    source_ids = {item.source_id for item in selected}
    if len(source_ids) != 1:
        raise RoleLensDecisionDiffError(
            "Approved business Evidence must share exactly one source_id."
        )
    data_source_id = next(iter(source_ids))
    if data_health_summary.source_id != data_source_id:
        raise RoleLensDecisionDiffError(
            "Data health and approved business Evidence must share one source_id."
        )

    source_matches = [
        item for item in source_manifests if item.source_id == data_source_id
    ]
    if len(source_matches) != 1:
        raise RoleLensDecisionDiffError(
            "Exactly one matching data-source manifest is required."
        )
    manifest = source_matches[0]
    if (
        manifest.source_format is not SourceFormat.csv
        or manifest.semantic_context_category
        is not SemanticContextCategory.data_source
        or manifest.source_scope is not SourceScope.internal_observation
    ):
        raise RoleLensDecisionDiffError(
            "The matching manifest must be an internal-observation CSV data source."
        )

    snapshots = tuple(
        EvidenceInvariantSnapshot(
            evidence_id=item.evidence_id,
            evidence_type=item.evidence_type,
            identity_digest=item.identity_digest,
            source_id=item.source_id,
            finding=item.finding,
            snapshot_json=_canonical_json(item),
        )
        for item in selected
    )
    return RoleLensEvidenceBasis(
        profile_id=_PROFILE_ID,
        dataset_name=_DATASET_NAME,
        data_source_id=data_source_id,
        business_evidence=snapshots,
        data_health_snapshot_json=_canonical_json(data_health_summary),
        source_manifest_snapshot_json=_canonical_json(manifest),
    )


def _stable_assumption_ids(
    assumptions: Sequence[ScenarioAssumption],
) -> tuple[str, ...]:
    """Return the four stable IDs in DD-1 canonical key order."""
    if isinstance(assumptions, (str, bytes, bytearray)) or not isinstance(
        assumptions,
        Sequence,
    ):
        raise RoleLensDecisionDiffError(
            "before_assumptions must be a ScenarioAssumption sequence."
        )
    if len(assumptions) != 4 or any(
        type(item) is not ScenarioAssumption for item in assumptions
    ):
        raise RoleLensDecisionDiffError(
            "before_assumptions must contain four ScenarioAssumption values."
        )
    by_key = {item.key: item for item in assumptions}
    if len(by_key) != 4 or set(by_key) != set(_SCENARIO_KEYS):
        raise RoleLensDecisionDiffError(
            "before_assumptions must contain each scenario key exactly once."
        )
    return tuple(by_key[key].assumption_id for key in _SCENARIO_KEYS)


def _build_rolelens_registry(
    assumption_ids: tuple[str, ...],
) -> DecisionDependencyRegistry:
    """Build the private DD-3 dependency registry for the current product."""
    unchanged = DecisionImpactPolicy.ALWAYS_UNCHANGED
    recompute = DecisionImpactPolicy.RECOMPUTE_ON_DEPENDENCY_CHANGE
    return DecisionDependencyRegistry(
        nodes=(
            DecisionDependencyNode(
                object_id="obj-observed-evidence",
                object_type="observed_evidence",
                dependency_refs=(),
                impact_policy=unchanged,
            ),
            DecisionDependencyNode(
                object_id="obj-data-health",
                object_type="data_health",
                dependency_refs=(),
                impact_policy=unchanged,
            ),
            DecisionDependencyNode(
                object_id="obj-source-provenance",
                object_type="source_provenance",
                dependency_refs=(),
                impact_policy=unchanged,
            ),
            DecisionDependencyNode(
                object_id="obj-break-even",
                object_type="scenario_result",
                dependency_refs=assumption_ids,
                impact_policy=recompute,
            ),
            DecisionDependencyNode(
                object_id="obj-executive-posture",
                object_type="executive_posture",
                dependency_refs=("obj-break-even", "obj-observed-evidence"),
                impact_policy=recompute,
            ),
            DecisionDependencyNode(
                object_id="obj-sales-posture",
                object_type="sales_posture",
                dependency_refs=(
                    "obj-break-even",
                    "obj-executive-posture",
                    "obj-observed-evidence",
                ),
                impact_policy=DecisionImpactPolicy.BLOCK_IF_SCENARIO_NOT_CLEAR,
            ),
            DecisionDependencyNode(
                object_id="obj-pm-handoff",
                object_type="project_manager_handoff",
                dependency_refs=(
                    "obj-executive-posture",
                    "obj-sales-posture",
                    "obj-data-health",
                ),
                impact_policy=recompute,
            ),
            DecisionDependencyNode(
                object_id="obj-decision-brief",
                object_type="decision_brief",
                dependency_refs=(
                    "obj-break-even",
                    "obj-pm-handoff",
                    "obj-observed-evidence",
                    "obj-source-provenance",
                ),
                impact_policy=DecisionImpactPolicy.STALE_ON_DEPENDENCY_CHANGE,
            ),
        )
    )


def _projection(
    result: ScenarioResult,
    evidence_ids: tuple[str, ...],
) -> ScenarioDecisionProjection:
    """Map one DD-1 result to exact non-authorizing business postures."""
    if result.status is ScenarioStatus.CLEARS_BREAK_EVEN:
        executive = ExecutiveScenarioPosture.LIMITED_PILOT_REVIEW_CANDIDATE
        sales = SalesPilotPosture.ELIGIBLE_FOR_PILOT_REVIEW
        handoff = ProjectManagerHandoff.PREPARE_LIMITED_PILOT_REVIEW
    elif result.status is ScenarioStatus.DOES_NOT_CLEAR_BREAK_EVEN:
        executive = ExecutiveScenarioPosture.VALIDATE_SCENARIO_ASSUMPTIONS_FIRST
        sales = SalesPilotPosture.BLOCKED_BY_SCENARIO
        handoff = ProjectManagerHandoff.REOPEN_SCENARIO_VALIDATION
    else:
        raise RoleLensDecisionDiffError(
            "Scenario projections require complete evaluable results."
        )
    return ScenarioDecisionProjection(
        revision_id=result.revision_id,
        scenario_result=result,
        executive_posture=executive,
        sales_posture=sales,
        project_manager_handoff=handoff,
        evidence_ids=evidence_ids,
        assumption_ids=result.input_assumption_ids,
        control_notice=_CONTROL_NOTICE,
    )


def build_rolelens_decision_revision(
    *,
    business_profile: BusinessDatasetProfile,
    evidence_objects: Sequence[EvidenceObject],
    data_health_summary: DataHealthSummary,
    source_manifests: Sequence[SourceManifestEntry],
    before_assumptions: Sequence[ScenarioAssumption],
    after_assumptions: Sequence[ScenarioAssumption],
    scenario_id: str,
    before_revision_id: str,
    after_revision_id: str,
) -> RoleLensDecisionRevision:
    """Build one deterministic DD-3 revision over fixed observed Evidence."""
    try:
        _validate_product_inputs(
            business_profile,
            evidence_objects,
            data_health_summary,
            source_manifests,
        )
        evidence_basis = _build_evidence_basis(
            business_profile,
            evidence_objects,
            data_health_summary,
            source_manifests,
        )
        before_product_snapshot = _snapshot_product_inputs(
            business_profile,
            evidence_objects,
            data_health_summary,
            source_manifests,
        )
        registry = _build_rolelens_registry(
            _stable_assumption_ids(before_assumptions)
        )
        decision_diff = build_decision_diff(
            before_assumptions,
            after_assumptions,
            scenario_id=scenario_id,
            before_revision_id=before_revision_id,
            after_revision_id=after_revision_id,
            registry=registry,
        )
        evidence_ids = tuple(
            item.evidence_id for item in evidence_basis.business_evidence
        )
        before_projection = _projection(
            decision_diff.before_scenario_result,
            evidence_ids,
        )
        after_projection = _projection(
            decision_diff.after_scenario_result,
            evidence_ids,
        )
        after_product_snapshot = _snapshot_product_inputs(
            business_profile,
            evidence_objects,
            data_health_summary,
            source_manifests,
        )
        if after_product_snapshot != before_product_snapshot:
            raise RoleLensDecisionDiffError(
                "RoleLens product inputs changed during Decision Diff execution."
            )
        currency = after_projection.scenario_result.currency
        currency_notice = (
            f"Scenario currency {currency} is user-supplied and is not inferred "
            "from the IBM Telco dataset."
            if currency is not None
            else "No scenario currency was supplied; the IBM Telco dataset currency "
            "remains unspecified."
        )
        return RoleLensDecisionRevision(
            evidence_basis=evidence_basis,
            before_projection=before_projection,
            after_projection=after_projection,
            decision_diff=decision_diff,
            unchanged_evidence_ids=evidence_ids,
            notices=(
                _SEPARATION_NOTICE,
                _AUTHORITY_NOTICE,
                currency_notice,
            ),
        )
    except RoleLensDecisionDiffError:
        raise
    except DecisionDiffEngineError:
        raise RoleLensDecisionDiffError(
            "Scenario revisions failed Decision Diff validation."
        ) from None
    except ValidationError:
        raise RoleLensDecisionDiffError(
            "RoleLens Decision Diff output failed contract validation."
        ) from None
    except Exception:
        raise RoleLensDecisionDiffError(
            "RoleLens Decision Diff could not be built from the supplied inputs."
        ) from None
