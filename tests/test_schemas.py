"""
tests/test_schemas.py — Task 1 (revised): Core identity and provenance schema tests.

Tests cover the original 20 requirements plus the 10 review corrections:

Original:
  1.  Valid construction of each enum and model
  2.  SourceLocator discriminated-union parsing for all three locator types
  3.  Invalid or missing locator_type
  4.  Empty columns rejected (TabularSourceLocator)
  5.  Invalid row ranges rejected
  6.  Invalid text ranges rejected
  7.  TextSourceLocator with no location fields rejected
  8.  Blank field_name rejected (UserContextLocator)
  9.  Invalid source_id format rejected
  10. Invalid evidence_id format rejected
  11. Invalid identity_digest rejected
  12. EvidenceObject with empty relevant_roles rejected
  13. EvidenceObject with blank role name rejected
  14. Invalidated evidence without invalidated_reason rejected
  15. Active evidence with invalidated_reason rejected
  16. HealthFindingCandidate has no evidence_id attribute
  17. Missing required fields produce ValidationError
  18. Valid EvidenceReference construction
  19. EvidenceReference validates format but not registry existence
  20. Valid model serialization and reconstruction

Review corrections (new):
  R1.  extra="forbid" rejects unknown fields on all models
  R2.  TextSourceLocator numeric index validation is safe for non-numeric strings
  R3.  canonical_rule_parameters recursive JSON-compatible validation
  R4.  HealthFindingCandidate relevant_roles rejects blank strings (unified validator)
  R5.  source_format + source_locator compatibility enforcement
  R6.  Blank heading_path rejected
  R7.  EvidenceObject id_algo_version non-blank enforced
  R8.  SourceManifestEntry created_at timezone-aware enforced
  R9.  Locked semantic_context_category → source_scope mappings
  R10. Task 1 boundaries preserved (no ID generation, no later schemas)
"""

from __future__ import annotations

import pytest
from datetime import datetime, timezone, timedelta
from pydantic import ValidationError

from app.schemas import (
    EvidenceObject,
    EvidenceReference,
    EvidenceScope,
    EvidenceStatus,
    HealthFindingCandidate,
    SemanticContextCategory,
    SourceFormat,
    SourceManifestEntry,
    SourceScope,
    TabularSourceLocator,
    TextSourceLocator,
    UserContextLocator,
)

# ---------------------------------------------------------------------------
# Shared fixture values
# ---------------------------------------------------------------------------

VALID_SOURCE_ID = "src-csv-0123456789ab"
VALID_EVIDENCE_ID = "ev-missing_val-0123456789ab"
VALID_DIGEST = "a" * 64  # 64 lowercase hex chars
VALID_DATETIME = datetime(2026, 7, 12, 0, 0, 0, tzinfo=timezone.utc)


def _tabular_locator() -> TabularSourceLocator:
    return TabularSourceLocator(columns=["customer_id", "churn"])


def _text_locator() -> TextSourceLocator:
    return TextSourceLocator(line_start=0, line_end=5)


def _user_locator() -> UserContextLocator:
    return UserContextLocator(
        field_name="business_question",
        context_category=SemanticContextCategory.business_question,
    )


def _valid_source_manifest(**overrides) -> dict:
    base = dict(
        source_id=VALID_SOURCE_ID,
        identity_digest=VALID_DIGEST,
        source_format=SourceFormat.csv,
        semantic_context_category=SemanticContextCategory.data_source,
        source_scope=SourceScope.internal_observation,
        created_at=VALID_DATETIME,
    )
    base.update(overrides)
    return base


def _valid_evidence_object(**overrides) -> dict:
    base = dict(
        evidence_id=VALID_EVIDENCE_ID,
        identity_digest=VALID_DIGEST,
        source_id=VALID_SOURCE_ID,
        source_format=SourceFormat.csv,
        source_locator=_tabular_locator(),
        evidence_type="missing_value_rate",
        evidence_scope=EvidenceScope.internal_observation,
        extraction_method="deterministic",
        finding="Column 'usage_frequency' has 42% missing values.",
        supporting_evidence="42 of 100 rows have null in column usage_frequency.",
        confidence="high",
        relevant_roles=["Data Engineer", "Data Analyst"],
        decision_relevance="Missing usage data limits churn model quality.",
        created_by="data_health",
    )
    base.update(overrides)
    return base


def _valid_health_candidate(**overrides) -> dict:
    base = dict(
        source_id=VALID_SOURCE_ID,
        source_format=SourceFormat.csv,
        source_locator=_tabular_locator(),
        evidence_type="missing_value_rate",
        canonical_rule_parameters={"column": "usage_frequency", "threshold": 0.2},
        normalized_claim_key="missing_value_rate.usage_frequency",
        finding="Column 'usage_frequency' has 42% missing values.",
        supporting_evidence="42 of 100 rows have null.",
        confidence="high",
        relevant_roles=["Data Engineer"],
        decision_relevance="Limits analysis quality.",
    )
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# 1. Enum validity
# ---------------------------------------------------------------------------


class TestEnums:
    def test_source_format_values(self):
        assert SourceFormat.csv == "csv"
        assert SourceFormat.excel == "excel"
        assert SourceFormat.pasted_text == "pasted_text"
        assert SourceFormat.txt == "txt"
        assert SourceFormat.markdown == "markdown"
        assert SourceFormat.form_input == "form_input"

    def test_pdf_text_not_in_source_format(self):
        """pdf_text must not be an active V1 SourceFormat value."""
        values = [f.value for f in SourceFormat]
        assert "pdf_text" not in values

    def test_semantic_context_category_values(self):
        cats = [c.value for c in SemanticContextCategory]
        assert "data_source" in cats
        assert "business_question" in cats
        assert "decision_goal" in cats
        assert "industry_context" in cats
        assert "strategy_profile" in cats
        assert "user_assumption" in cats
        assert "internal_report" in cats

    def test_source_scope_values(self):
        scopes = [s.value for s in SourceScope]
        assert "internal_observation" in scopes
        assert "external_context" in scopes
        assert "user_assertion" in scopes
        assert "decision_context" in scopes

    def test_evidence_scope_values(self):
        scopes = [s.value for s in EvidenceScope]
        assert "internal_observation" in scopes
        assert "external_context" in scopes
        assert "assumption" in scopes
        assert "stated_priority" in scopes

    def test_evidence_status_only_two_values(self):
        """EvidenceStatus must contain exactly active and invalidated."""
        values = {s.value for s in EvidenceStatus}
        assert values == {"active", "invalidated"}

    def test_evidence_status_no_duplicate_or_collision(self):
        """duplicate and collision must not be EvidenceStatus values."""
        values = [s.value for s in EvidenceStatus]
        assert "duplicate" not in values
        assert "collision" not in values


# ---------------------------------------------------------------------------
# 2. SourceLocator discriminated union — all three locator types
# ---------------------------------------------------------------------------


class TestSourceLocatorUnion:
    def test_tabular_locator_via_dict(self):
        data = {"locator_type": "tabular", "columns": ["a", "b"]}
        from pydantic import TypeAdapter
        from app.schemas import SourceLocator
        ta = TypeAdapter(SourceLocator)
        loc = ta.validate_python(data)
        assert isinstance(loc, TabularSourceLocator)
        assert loc.columns == ["a", "b"]

    def test_text_locator_via_dict(self):
        data = {"locator_type": "text", "line_start": 0}
        from pydantic import TypeAdapter
        from app.schemas import SourceLocator
        ta = TypeAdapter(SourceLocator)
        loc = ta.validate_python(data)
        assert isinstance(loc, TextSourceLocator)

    def test_user_context_locator_via_dict(self):
        data = {
            "locator_type": "user_context",
            "field_name": "strategy_goal",
            "context_category": "strategy_profile",
        }
        from pydantic import TypeAdapter
        from app.schemas import SourceLocator
        ta = TypeAdapter(SourceLocator)
        loc = ta.validate_python(data)
        assert isinstance(loc, UserContextLocator)


# ---------------------------------------------------------------------------
# 3. Invalid or missing locator_type
# ---------------------------------------------------------------------------


class TestInvalidLocatorType:
    def test_invalid_locator_type_raises(self):
        data = {"locator_type": "unknown", "columns": ["x"]}
        from pydantic import TypeAdapter
        from app.schemas import SourceLocator
        ta = TypeAdapter(SourceLocator)
        with pytest.raises(ValidationError):
            ta.validate_python(data)

    def test_missing_locator_type_raises(self):
        data = {"columns": ["x"]}
        from pydantic import TypeAdapter
        from app.schemas import SourceLocator
        ta = TypeAdapter(SourceLocator)
        with pytest.raises(ValidationError):
            ta.validate_python(data)


# ---------------------------------------------------------------------------
# 4. Empty columns rejected
# ---------------------------------------------------------------------------


class TestTabularLocatorColumns:
    def test_empty_columns_list_rejected(self):
        with pytest.raises(ValidationError, match="columns must not be empty"):
            TabularSourceLocator(columns=[])

    def test_blank_column_name_rejected(self):
        with pytest.raises(ValidationError, match="blank names"):
            TabularSourceLocator(columns=["valid", "  "])

    def test_empty_string_column_rejected(self):
        with pytest.raises(ValidationError, match="blank names"):
            TabularSourceLocator(columns=[""])

    def test_valid_columns_accepted(self):
        loc = TabularSourceLocator(columns=["customer_id", "revenue"])
        assert loc.columns == ["customer_id", "revenue"]


# ---------------------------------------------------------------------------
# 5. Invalid row ranges rejected
# ---------------------------------------------------------------------------


class TestTabularLocatorRowRange:
    def test_negative_start_rejected(self):
        with pytest.raises(ValidationError, match="non-negative"):
            TabularSourceLocator(columns=["a"], row_range=(-1, 5))

    def test_negative_end_rejected(self):
        with pytest.raises(ValidationError, match="non-negative"):
            TabularSourceLocator(columns=["a"], row_range=(0, -1))

    def test_start_exceeds_end_rejected(self):
        with pytest.raises(ValidationError, match="start must not exceed end"):
            TabularSourceLocator(columns=["a"], row_range=(10, 5))

    def test_equal_start_end_accepted(self):
        loc = TabularSourceLocator(columns=["a"], row_range=(5, 5))
        assert loc.row_range == (5, 5)

    def test_valid_row_range_accepted(self):
        loc = TabularSourceLocator(columns=["a"], row_range=(0, 99))
        assert loc.row_range == (0, 99)

    def test_none_row_range_accepted(self):
        loc = TabularSourceLocator(columns=["a"], row_range=None)
        assert loc.row_range is None


# ---------------------------------------------------------------------------
# 6. Invalid text ranges rejected
# ---------------------------------------------------------------------------


class TestTextLocatorRanges:
    def test_negative_line_start_rejected(self):
        with pytest.raises(ValidationError):
            TextSourceLocator(line_start=-1, line_end=5)

    def test_line_start_exceeds_line_end_rejected(self):
        with pytest.raises(ValidationError, match="line_start must not exceed line_end"):
            TextSourceLocator(line_start=10, line_end=5)

    def test_char_start_exceeds_char_end_rejected(self):
        with pytest.raises(ValidationError, match="char_start must not exceed char_end"):
            TextSourceLocator(char_start=100, char_end=50)

    def test_negative_paragraph_index_rejected(self):
        with pytest.raises(ValidationError):
            TextSourceLocator(paragraph_index=-1)

    def test_invalid_excerpt_checksum_rejected(self):
        with pytest.raises(ValidationError, match="64 lowercase hexadecimal"):
            TextSourceLocator(line_start=0, excerpt_checksum="not_a_digest")

    def test_valid_excerpt_checksum_accepted(self):
        loc = TextSourceLocator(line_start=0, excerpt_checksum="b" * 64)
        assert loc.excerpt_checksum == "b" * 64


# ---------------------------------------------------------------------------
# 7. TextSourceLocator with no location fields rejected
# ---------------------------------------------------------------------------


class TestTextLocatorRequiresField:
    def test_no_location_fields_rejected(self):
        with pytest.raises(ValidationError, match="at least one location field"):
            TextSourceLocator()

    def test_heading_path_alone_sufficient(self):
        loc = TextSourceLocator(heading_path="## Introduction")
        assert loc.heading_path == "## Introduction"

    def test_chunk_index_alone_sufficient(self):
        loc = TextSourceLocator(chunk_index=3)
        assert loc.chunk_index == 3


# ---------------------------------------------------------------------------
# 8. Blank field_name rejected in UserContextLocator
# ---------------------------------------------------------------------------


class TestUserContextLocator:
    def test_blank_field_name_rejected(self):
        with pytest.raises(ValidationError, match="must not be blank"):
            UserContextLocator(
                field_name="   ",
                context_category=SemanticContextCategory.business_question,
            )

    def test_empty_field_name_rejected(self):
        with pytest.raises(ValidationError, match="must not be blank"):
            UserContextLocator(
                field_name="",
                context_category=SemanticContextCategory.strategy_profile,
            )

    def test_valid_user_context_locator(self):
        loc = UserContextLocator(
            field_name="churn_goal",
            context_category=SemanticContextCategory.decision_goal,
            form_section="Goals",
        )
        assert loc.field_name == "churn_goal"
        assert loc.form_section == "Goals"


# ---------------------------------------------------------------------------
# 9. Invalid source_id format rejected
# ---------------------------------------------------------------------------


class TestSourceIdFormat:
    @pytest.mark.parametrize("bad_id", [
        "SOURCE-csv-0123456789ab",       # wrong prefix
        "src-CSV-0123456789ab",          # uppercase abbrev
        "src-csv-0123456789abcdef",      # hash too long (16 chars)
        "src-csv-0123456789",            # hash too short (10 chars)
        "src-csv-0123456789aZ",          # uppercase hex
        "src--0123456789ab",             # empty abbrev
        "src-this_is_too_long-0123456789ab",  # abbrev > 12 chars
        "ev-csv-0123456789ab",           # evidence prefix instead of source
        "",
    ])
    def test_invalid_source_id_rejected(self, bad_id: str):
        with pytest.raises(ValidationError):
            SourceManifestEntry(
                source_id=bad_id,
                identity_digest=VALID_DIGEST,
                source_format=SourceFormat.csv,
                semantic_context_category=SemanticContextCategory.data_source,
                source_scope=SourceScope.internal_observation,
                created_at=VALID_DATETIME,
            )

    @pytest.mark.parametrize("good_id", [
        "src-csv-0123456789ab",
        "src-excel-0123456789ab",
        "src-pasted_text-0123456789ab",  # abbrev with underscore, 11 chars
        "src-a-0123456789ab",            # minimal abbrev
    ])
    def test_valid_source_id_accepted(self, good_id: str):
        entry = SourceManifestEntry(**_valid_source_manifest(source_id=good_id))
        assert entry.source_id == good_id


# ---------------------------------------------------------------------------
# 10. Invalid evidence_id format rejected
# ---------------------------------------------------------------------------


class TestEvidenceIdFormat:
    @pytest.mark.parametrize("bad_id", [
        "EV-missing_val-0123456789ab",   # uppercase prefix
        "ev-MISSING_VAL-0123456789ab",   # uppercase abbrev
        "ev-missing_val-0123456789abcd", # hash too long
        "ev-missing_val-0123456789",     # hash too short
        "ev--0123456789ab",              # empty abbrev
        "src-missing_val-0123456789ab",  # source prefix instead of ev
        "",
    ])
    def test_invalid_evidence_id_rejected(self, bad_id: str):
        with pytest.raises(ValidationError):
            EvidenceObject(**_valid_evidence_object(evidence_id=bad_id))

    def test_valid_evidence_id_accepted(self):
        obj = EvidenceObject(**_valid_evidence_object())
        assert obj.evidence_id == VALID_EVIDENCE_ID


# ---------------------------------------------------------------------------
# 11. Invalid identity_digest rejected
# ---------------------------------------------------------------------------


class TestIdentityDigest:
    @pytest.mark.parametrize("bad_digest", [
        "a" * 63,          # too short
        "a" * 65,          # too long
        "A" * 64,          # uppercase
        "g" * 64,          # invalid hex character
        "",
        "abc123",
    ])
    def test_invalid_digest_rejected_on_manifest(self, bad_digest: str):
        with pytest.raises(ValidationError, match="identity_digest"):
            SourceManifestEntry(**_valid_source_manifest(identity_digest=bad_digest))

    def test_invalid_digest_rejected_on_evidence(self):
        with pytest.raises(ValidationError, match="identity_digest"):
            EvidenceObject(**_valid_evidence_object(identity_digest="z" * 64))

    def test_valid_digest_accepted(self):
        entry = SourceManifestEntry(**_valid_source_manifest())
        assert len(entry.identity_digest) == 64


# ---------------------------------------------------------------------------
# 12 & 13. relevant_roles validation on EvidenceObject
# ---------------------------------------------------------------------------


class TestRelevantRoles:
    def test_empty_relevant_roles_rejected(self):
        with pytest.raises(ValidationError, match="relevant_roles must not be empty"):
            EvidenceObject(**_valid_evidence_object(relevant_roles=[]))

    def test_blank_role_name_rejected(self):
        with pytest.raises(ValidationError, match="blank role names"):
            EvidenceObject(**_valid_evidence_object(relevant_roles=["Data Engineer", "  "]))

    def test_empty_string_role_rejected(self):
        with pytest.raises(ValidationError, match="blank role names"):
            EvidenceObject(**_valid_evidence_object(relevant_roles=[""]))

    def test_valid_roles_accepted(self):
        obj = EvidenceObject(**_valid_evidence_object(
            relevant_roles=["Executive", "Data Analyst", "Data Engineer"]
        ))
        assert len(obj.relevant_roles) == 3


# ---------------------------------------------------------------------------
# 14. Invalidated evidence without invalidated_reason rejected
# ---------------------------------------------------------------------------


class TestInvalidatedStatus:
    def test_invalidated_without_reason_rejected(self):
        with pytest.raises(ValidationError, match="invalidated_reason is required"):
            EvidenceObject(**_valid_evidence_object(
                status=EvidenceStatus.invalidated,
                invalidated_reason=None,
            ))

    def test_invalidated_with_blank_reason_rejected(self):
        with pytest.raises(ValidationError, match="invalidated_reason is required"):
            EvidenceObject(**_valid_evidence_object(
                status=EvidenceStatus.invalidated,
                invalidated_reason="   ",
            ))

    def test_invalidated_with_reason_accepted(self):
        obj = EvidenceObject(**_valid_evidence_object(
            status=EvidenceStatus.invalidated,
            invalidated_reason="Source CSV replaced with corrected version.",
        ))
        assert obj.status == EvidenceStatus.invalidated
        assert obj.invalidated_reason is not None


# ---------------------------------------------------------------------------
# 15. Active evidence with invalidated_reason rejected
# ---------------------------------------------------------------------------


class TestActiveStatusWithReason:
    def test_active_with_invalidated_reason_rejected(self):
        with pytest.raises(ValidationError, match="invalidated_reason must be absent"):
            EvidenceObject(**_valid_evidence_object(
                status=EvidenceStatus.active,
                invalidated_reason="This should not be here.",
            ))

    def test_active_without_reason_accepted(self):
        obj = EvidenceObject(**_valid_evidence_object(status=EvidenceStatus.active))
        assert obj.invalidated_reason is None


# ---------------------------------------------------------------------------
# 16. HealthFindingCandidate has no evidence_id field
# ---------------------------------------------------------------------------


class TestHealthFindingCandidateMintingBoundary:
    def test_no_evidence_id_attribute(self):
        """HealthFindingCandidate must not define evidence_id."""
        candidate = HealthFindingCandidate(**_valid_health_candidate())
        assert not hasattr(candidate, "evidence_id"), (
            "HealthFindingCandidate must not have an evidence_id attribute — "
            "only evidence_builder.py may mint evidence_id values"
        )

    def test_no_identity_digest_attribute(self):
        """HealthFindingCandidate must not define identity_digest."""
        candidate = HealthFindingCandidate(**_valid_health_candidate())
        assert not hasattr(candidate, "identity_digest")

    def test_evidence_id_field_not_in_model_fields(self):
        """evidence_id must not appear in HealthFindingCandidate model fields."""
        fields = HealthFindingCandidate.model_fields
        assert "evidence_id" not in fields
        assert "identity_digest" not in fields

    def test_valid_candidate_construction(self):
        candidate = HealthFindingCandidate(**_valid_health_candidate())
        assert candidate.evidence_type == "missing_value_rate"
        assert candidate.normalized_claim_key == "missing_value_rate.usage_frequency"


# ---------------------------------------------------------------------------
# 17. Missing required fields produce ValidationError
# ---------------------------------------------------------------------------


class TestMissingRequiredFields:
    def test_source_manifest_missing_source_id(self):
        data = _valid_source_manifest()
        del data["source_id"]
        with pytest.raises(ValidationError):
            SourceManifestEntry(**data)

    def test_source_manifest_missing_created_at(self):
        data = _valid_source_manifest()
        del data["created_at"]
        with pytest.raises(ValidationError):
            SourceManifestEntry(**data)

    def test_evidence_object_missing_finding(self):
        data = _valid_evidence_object()
        del data["finding"]
        with pytest.raises(ValidationError):
            EvidenceObject(**data)

    def test_evidence_object_missing_source_locator(self):
        data = _valid_evidence_object()
        del data["source_locator"]
        with pytest.raises(ValidationError):
            EvidenceObject(**data)

    def test_health_candidate_missing_normalized_claim_key(self):
        data = _valid_health_candidate()
        del data["normalized_claim_key"]
        with pytest.raises(ValidationError):
            HealthFindingCandidate(**data)

    def test_tabular_locator_missing_columns(self):
        with pytest.raises(ValidationError):
            TabularSourceLocator()

    def test_user_context_locator_missing_field_name(self):
        with pytest.raises(ValidationError):
            UserContextLocator(
                context_category=SemanticContextCategory.user_assumption
            )


# ---------------------------------------------------------------------------
# 18 & 19. EvidenceReference
# ---------------------------------------------------------------------------


class TestEvidenceReference:
    def test_valid_evidence_reference(self):
        ref = EvidenceReference(evidence_id=VALID_EVIDENCE_ID)
        assert ref.evidence_id == VALID_EVIDENCE_ID
        assert ref.relevance_note is None

    def test_valid_reference_with_note(self):
        ref = EvidenceReference(
            evidence_id=VALID_EVIDENCE_ID,
            relevance_note="Supports the missing-data risk flag.",
        )
        assert ref.relevance_note is not None

    def test_invalid_evidence_id_format_rejected(self):
        with pytest.raises(ValidationError):
            EvidenceReference(evidence_id="not-valid-id")

    def test_reference_does_not_validate_registry_existence(self):
        """
        A completely fabricated evidence_id with correct format must be
        accepted by EvidenceReference — format is all Task 1 validates.
        Registry existence checking is handled by trajectory validation (later).
        """
        fabricated_id = "ev-nonexistent-aabbccddeeff"
        ref = EvidenceReference(evidence_id=fabricated_id)
        assert ref.evidence_id == fabricated_id


# ---------------------------------------------------------------------------
# 20. Serialization and reconstruction
# ---------------------------------------------------------------------------


class TestSerialization:
    def test_source_manifest_round_trip(self):
        entry = SourceManifestEntry(**_valid_source_manifest())
        data = entry.model_dump()
        reconstructed = SourceManifestEntry(**data)
        assert reconstructed.source_id == entry.source_id
        assert reconstructed.identity_digest == entry.identity_digest
        assert reconstructed.source_format == entry.source_format

    def test_evidence_object_round_trip(self):
        obj = EvidenceObject(**_valid_evidence_object())
        data = obj.model_dump()
        reconstructed = EvidenceObject(**data)
        assert reconstructed.evidence_id == obj.evidence_id
        assert reconstructed.status == EvidenceStatus.active

    def test_health_candidate_round_trip(self):
        candidate = HealthFindingCandidate(**_valid_health_candidate())
        data = candidate.model_dump()
        reconstructed = HealthFindingCandidate(**data)
        assert reconstructed.normalized_claim_key == candidate.normalized_claim_key

    def test_evidence_object_json_serialization(self):
        obj = EvidenceObject(**_valid_evidence_object())
        json_str = obj.model_dump_json()
        assert VALID_EVIDENCE_ID in json_str
        assert "missing_value_rate" in json_str

    def test_tabular_locator_serialization(self):
        loc = TabularSourceLocator(
            columns=["a", "b"], row_range=(0, 9), sheet_name="Sheet1"
        )
        data = loc.model_dump()
        assert data["locator_type"] == "tabular"
        assert data["columns"] == ["a", "b"]
        reconstructed = TabularSourceLocator(**data)
        assert reconstructed.row_range == (0, 9)

    def test_text_locator_serialization(self):
        loc = TextSourceLocator(line_start=0, line_end=10, heading_path="## Intro")
        data = loc.model_dump()
        reconstructed = TextSourceLocator(**data)
        assert reconstructed.heading_path == "## Intro"

    def test_source_manifest_id_algo_version_default(self):
        entry = SourceManifestEntry(**_valid_source_manifest())
        assert entry.id_algo_version == "v1"

    def test_evidence_object_id_algo_version_default(self):
        obj = EvidenceObject(**_valid_evidence_object())
        assert obj.id_algo_version == "v1"

    def test_evidence_object_status_default(self):
        obj = EvidenceObject(**_valid_evidence_object())
        assert obj.status == EvidenceStatus.active

    def test_limitations_default_empty_list(self):
        obj = EvidenceObject(**_valid_evidence_object())
        assert obj.limitations == []


# ---------------------------------------------------------------------------
# R1. extra="forbid" — unknown fields rejected on all models
# ---------------------------------------------------------------------------


class TestExtraFieldsForbidden:
    def test_health_candidate_rejects_evidence_id(self):
        """HealthFindingCandidate must raise ValidationError when evidence_id is passed."""
        with pytest.raises(ValidationError):
            HealthFindingCandidate(**_valid_health_candidate(), evidence_id=VALID_EVIDENCE_ID)

    def test_health_candidate_rejects_identity_digest(self):
        """HealthFindingCandidate must raise ValidationError when identity_digest is passed."""
        with pytest.raises(ValidationError):
            HealthFindingCandidate(**_valid_health_candidate(), identity_digest=VALID_DIGEST)

    def test_evidence_object_rejects_unknown_field(self):
        with pytest.raises(ValidationError):
            EvidenceObject(**_valid_evidence_object(), unknown_field="surprise")

    def test_tabular_locator_rejects_unknown_field(self):
        with pytest.raises(ValidationError):
            TabularSourceLocator(columns=["a"], unexpected_key="value")

    def test_text_locator_rejects_unknown_field(self):
        with pytest.raises(ValidationError):
            TextSourceLocator(line_start=0, unexpected_key="value")

    def test_user_context_locator_rejects_unknown_field(self):
        with pytest.raises(ValidationError):
            UserContextLocator(
                field_name="x",
                context_category=SemanticContextCategory.user_assumption,
                unknown_key="y",
            )

    def test_source_manifest_rejects_unknown_field(self):
        with pytest.raises(ValidationError):
            SourceManifestEntry(**_valid_source_manifest(), extra_field="oops")

    def test_evidence_reference_rejects_unknown_field(self):
        with pytest.raises(ValidationError):
            EvidenceReference(evidence_id=VALID_EVIDENCE_ID, mystery_field=42)


# ---------------------------------------------------------------------------
# R2. TextSourceLocator safe index validation (no TypeError for strings)
# ---------------------------------------------------------------------------


class TestTextLocatorSafeValidation:
    def test_negative_integer_produces_validation_error(self):
        """Negative integer must produce ValidationError, not pass silently."""
        with pytest.raises(ValidationError):
            TextSourceLocator(line_start=-5)

    def test_non_numeric_string_produces_validation_error_not_type_error(self):
        """Non-numeric string must produce ValidationError, not TypeError.

        This test verifies the review finding: the previous mode='before' validator
        could raise a Python TypeError for string inputs. Using Field(ge=0) on
        typed int | None fields means Pydantic handles type coercion first;
        a non-integer string is rejected with ValidationError.
        """
        with pytest.raises(ValidationError):
            TextSourceLocator(line_start="invalid")

    def test_numeric_string_behavior_documented(self):
        """Pydantic v2 in strict=False mode coerces '5' → 5 for int fields.

        This behavior is intentional: Pydantic v2 accepts string representations
        of integers for int fields in lax mode. If strict parsing is required,
        model_config = ConfigDict(strict=True) must be set on ContractModel.
        Task 1 does not require strict mode; lax coercion is acceptable here.
        """
        # "5" is coerced to 5 by Pydantic v2 in lax mode — document this explicitly
        loc = TextSourceLocator(line_start="5")  # type: ignore[arg-type]
        assert loc.line_start == 5

    def test_valid_integer_still_accepted(self):
        loc = TextSourceLocator(line_start=0, line_end=10)
        assert loc.line_start == 0
        assert loc.line_end == 10

    def test_zero_is_valid(self):
        loc = TextSourceLocator(paragraph_index=0)
        assert loc.paragraph_index == 0


# ---------------------------------------------------------------------------
# R3. canonical_rule_parameters recursive JSON-compatible validation
# ---------------------------------------------------------------------------


class TestCanonicalRuleParamsRecursive:
    def test_valid_nested_json_accepted(self):
        candidate = HealthFindingCandidate(**_valid_health_candidate(
            canonical_rule_parameters={
                "column": "usage_frequency",
                "threshold": 0.2,
                "count": 42,
                "flag": True,
                "null_value": None,
                "tags": ["a", "b", 1, None],
                "nested": {"sub": "value", "deeper": {"x": 1}},
            }
        ))
        assert candidate.canonical_rule_parameters["threshold"] == 0.2

    def test_nested_set_rejected(self):
        with pytest.raises(ValidationError, match="non-JSON-compatible"):
            HealthFindingCandidate(**_valid_health_candidate(
                canonical_rule_parameters={"tags": {1, 2, 3}}
            ))

    def test_nested_bytes_rejected(self):
        with pytest.raises(ValidationError, match="non-JSON-compatible"):
            HealthFindingCandidate(**_valid_health_candidate(
                canonical_rule_parameters={"data": b"raw bytes"}
            ))

    def test_nested_complex_rejected(self):
        with pytest.raises(ValidationError, match="non-JSON-compatible"):
            HealthFindingCandidate(**_valid_health_candidate(
                canonical_rule_parameters={"z": complex(1, 2)}
            ))

    def test_nan_rejected(self):
        import math
        with pytest.raises(ValidationError, match="non-finite float"):
            HealthFindingCandidate(**_valid_health_candidate(
                canonical_rule_parameters={"value": float("nan")}
            ))

    def test_positive_infinity_rejected(self):
        with pytest.raises(ValidationError, match="non-finite float"):
            HealthFindingCandidate(**_valid_health_candidate(
                canonical_rule_parameters={"value": float("inf")}
            ))

    def test_negative_infinity_rejected(self):
        with pytest.raises(ValidationError, match="non-finite float"):
            HealthFindingCandidate(**_valid_health_candidate(
                canonical_rule_parameters={"value": float("-inf")}
            ))

    def test_deeply_nested_set_rejected(self):
        with pytest.raises(ValidationError, match="non-JSON-compatible"):
            HealthFindingCandidate(**_valid_health_candidate(
                canonical_rule_parameters={"outer": {"inner": {1, 2}}}
            ))

    def test_deeply_nested_nan_rejected(self):
        with pytest.raises(ValidationError, match="non-finite float"):
            HealthFindingCandidate(**_valid_health_candidate(
                canonical_rule_parameters={"outer": [1, float("nan")]}
            ))


# ---------------------------------------------------------------------------
# R4. Unified relevant_roles validation on HealthFindingCandidate
# ---------------------------------------------------------------------------


class TestHealthCandidateRelevantRoles:
    def test_empty_list_rejected(self):
        with pytest.raises(ValidationError, match="relevant_roles must not be empty"):
            HealthFindingCandidate(**_valid_health_candidate(relevant_roles=[]))

    def test_empty_string_rejected(self):
        with pytest.raises(ValidationError, match="blank role names"):
            HealthFindingCandidate(**_valid_health_candidate(relevant_roles=[""]))

    def test_whitespace_only_string_rejected(self):
        with pytest.raises(ValidationError, match="blank role names"):
            HealthFindingCandidate(**_valid_health_candidate(relevant_roles=["   "]))

    def test_valid_roles_accepted(self):
        candidate = HealthFindingCandidate(**_valid_health_candidate(
            relevant_roles=["Data Engineer", "Data Analyst"]
        ))
        assert len(candidate.relevant_roles) == 2


# ---------------------------------------------------------------------------
# R5. source_format + source_locator compatibility
# ---------------------------------------------------------------------------


class TestFormatLocatorCompatibility:
    # Rejected combinations
    def test_csv_with_text_locator_rejected(self):
        with pytest.raises(ValidationError, match="TabularSourceLocator"):
            EvidenceObject(**_valid_evidence_object(
                source_format=SourceFormat.csv,
                source_locator=_text_locator(),
            ))

    def test_pasted_text_with_tabular_locator_rejected(self):
        with pytest.raises(ValidationError, match="TextSourceLocator"):
            EvidenceObject(**_valid_evidence_object(
                source_format=SourceFormat.pasted_text,
                source_locator=_tabular_locator(),
            ))

    def test_form_input_with_tabular_locator_rejected(self):
        with pytest.raises(ValidationError, match="UserContextLocator"):
            EvidenceObject(**_valid_evidence_object(
                source_format=SourceFormat.form_input,
                source_locator=_tabular_locator(),
            ))

    def test_excel_with_text_locator_rejected(self):
        with pytest.raises(ValidationError, match="TabularSourceLocator"):
            EvidenceObject(**_valid_evidence_object(
                source_format=SourceFormat.excel,
                source_locator=_text_locator(),
            ))

    def test_markdown_with_tabular_locator_rejected(self):
        with pytest.raises(ValidationError, match="TextSourceLocator"):
            EvidenceObject(**_valid_evidence_object(
                source_format=SourceFormat.markdown,
                source_locator=_tabular_locator(),
            ))

    # Valid combinations — one per locator family
    def test_csv_with_tabular_locator_accepted(self):
        obj = EvidenceObject(**_valid_evidence_object(
            source_format=SourceFormat.csv,
            source_locator=_tabular_locator(),
        ))
        assert isinstance(obj.source_locator, TabularSourceLocator)

    def test_pasted_text_with_text_locator_accepted(self):
        obj = EvidenceObject(**_valid_evidence_object(
            source_format=SourceFormat.pasted_text,
            source_locator=_text_locator(),
        ))
        assert isinstance(obj.source_locator, TextSourceLocator)

    def test_form_input_with_user_context_locator_accepted(self):
        obj = EvidenceObject(**_valid_evidence_object(
            source_format=SourceFormat.form_input,
            source_locator=_user_locator(),
        ))
        assert isinstance(obj.source_locator, UserContextLocator)

    # Same checks on HealthFindingCandidate
    def test_health_candidate_csv_text_locator_rejected(self):
        with pytest.raises(ValidationError, match="TabularSourceLocator"):
            HealthFindingCandidate(**_valid_health_candidate(
                source_format=SourceFormat.csv,
                source_locator=_text_locator(),
            ))

    def test_health_candidate_pasted_text_tabular_locator_rejected(self):
        with pytest.raises(ValidationError, match="TextSourceLocator"):
            HealthFindingCandidate(**_valid_health_candidate(
                source_format=SourceFormat.pasted_text,
                source_locator=_tabular_locator(),
            ))

    def test_health_candidate_txt_text_locator_accepted(self):
        candidate = HealthFindingCandidate(**_valid_health_candidate(
            source_format=SourceFormat.txt,
            source_locator=_text_locator(),
        ))
        assert isinstance(candidate.source_locator, TextSourceLocator)


# ---------------------------------------------------------------------------
# R6. Blank heading_path rejected
# ---------------------------------------------------------------------------


class TestTextLocatorHeadingPath:
    def test_empty_heading_path_rejected(self):
        with pytest.raises(ValidationError, match="heading_path must not be blank"):
            TextSourceLocator(heading_path="")

    def test_whitespace_heading_path_rejected(self):
        with pytest.raises(ValidationError, match="heading_path must not be blank"):
            TextSourceLocator(heading_path="   ")

    def test_valid_heading_path_accepted(self):
        loc = TextSourceLocator(heading_path="## Introduction / ### Background")
        assert loc.heading_path == "## Introduction / ### Background"

    def test_none_heading_path_with_other_field_accepted(self):
        """None heading_path is fine as long as another location field is set."""
        loc = TextSourceLocator(heading_path=None, line_start=0)
        assert loc.heading_path is None
        assert loc.line_start == 0


# ---------------------------------------------------------------------------
# R7. EvidenceObject id_algo_version non-blank enforced
# ---------------------------------------------------------------------------


class TestEvidenceObjectIdAlgoVersion:
    def test_empty_id_algo_version_rejected(self):
        with pytest.raises(ValidationError, match="id_algo_version"):
            EvidenceObject(**_valid_evidence_object(id_algo_version=""))

    def test_whitespace_id_algo_version_rejected(self):
        with pytest.raises(ValidationError, match="id_algo_version"):
            EvidenceObject(**_valid_evidence_object(id_algo_version="   "))

    def test_default_v1_accepted(self):
        obj = EvidenceObject(**_valid_evidence_object())
        assert obj.id_algo_version == "v1"


# ---------------------------------------------------------------------------
# R8. SourceManifestEntry created_at timezone-aware
# ---------------------------------------------------------------------------


class TestCreatedAtTimezone:
    def test_utc_aware_accepted(self):
        entry = SourceManifestEntry(**_valid_source_manifest(
            created_at=datetime(2026, 7, 12, 0, 0, 0, tzinfo=timezone.utc)
        ))
        assert entry.created_at.tzinfo is not None

    def test_non_utc_aware_accepted(self):
        """Timezone-aware non-UTC datetimes are accepted.

        Normalization to UTC is the intake layer's responsibility, not schemas.py.
        """
        eastern = timezone(timedelta(hours=-5))
        entry = SourceManifestEntry(**_valid_source_manifest(
            created_at=datetime(2026, 7, 12, 10, 0, 0, tzinfo=eastern)
        ))
        assert entry.created_at.tzinfo is not None

    def test_naive_datetime_rejected(self):
        """Naive datetime (no tzinfo) must be rejected."""
        with pytest.raises(ValidationError, match="timezone-aware"):
            SourceManifestEntry(**_valid_source_manifest(
                created_at=datetime(2026, 7, 12, 0, 0, 0)  # no tzinfo
            ))


# ---------------------------------------------------------------------------
# R9. Locked semantic_context_category → source_scope mappings
# ---------------------------------------------------------------------------


class TestLockedCategoryScope:
    # Accepted combinations
    def test_business_question_requires_decision_context_accepted(self):
        entry = SourceManifestEntry(**_valid_source_manifest(
            semantic_context_category=SemanticContextCategory.business_question,
            source_scope=SourceScope.decision_context,
            source_format=SourceFormat.form_input,
        ))
        assert entry.source_scope == SourceScope.decision_context

    def test_decision_goal_requires_decision_context_accepted(self):
        entry = SourceManifestEntry(**_valid_source_manifest(
            semantic_context_category=SemanticContextCategory.decision_goal,
            source_scope=SourceScope.decision_context,
            source_format=SourceFormat.form_input,
        ))
        assert entry.source_scope == SourceScope.decision_context

    def test_industry_context_requires_external_context_accepted(self):
        entry = SourceManifestEntry(**_valid_source_manifest(
            semantic_context_category=SemanticContextCategory.industry_context,
            source_scope=SourceScope.external_context,
            source_format=SourceFormat.pasted_text,
        ))
        assert entry.source_scope == SourceScope.external_context

    def test_strategy_profile_requires_user_assertion_accepted(self):
        entry = SourceManifestEntry(**_valid_source_manifest(
            semantic_context_category=SemanticContextCategory.strategy_profile,
            source_scope=SourceScope.user_assertion,
            source_format=SourceFormat.form_input,
        ))
        assert entry.source_scope == SourceScope.user_assertion

    def test_user_assumption_requires_user_assertion_accepted(self):
        entry = SourceManifestEntry(**_valid_source_manifest(
            semantic_context_category=SemanticContextCategory.user_assumption,
            source_scope=SourceScope.user_assertion,
            source_format=SourceFormat.form_input,
        ))
        assert entry.source_scope == SourceScope.user_assertion

    # Rejected combinations (wrong scope for locked category)
    def test_business_question_wrong_scope_rejected(self):
        with pytest.raises(ValidationError, match="decision_context"):
            SourceManifestEntry(**_valid_source_manifest(
                semantic_context_category=SemanticContextCategory.business_question,
                source_scope=SourceScope.internal_observation,
                source_format=SourceFormat.form_input,
            ))

    def test_decision_goal_wrong_scope_rejected(self):
        with pytest.raises(ValidationError, match="decision_context"):
            SourceManifestEntry(**_valid_source_manifest(
                semantic_context_category=SemanticContextCategory.decision_goal,
                source_scope=SourceScope.external_context,
                source_format=SourceFormat.form_input,
            ))

    def test_industry_context_wrong_scope_rejected(self):
        with pytest.raises(ValidationError, match="external_context"):
            SourceManifestEntry(**_valid_source_manifest(
                semantic_context_category=SemanticContextCategory.industry_context,
                source_scope=SourceScope.internal_observation,
                source_format=SourceFormat.pasted_text,
            ))

    def test_strategy_profile_wrong_scope_rejected(self):
        with pytest.raises(ValidationError, match="user_assertion"):
            SourceManifestEntry(**_valid_source_manifest(
                semantic_context_category=SemanticContextCategory.strategy_profile,
                source_scope=SourceScope.decision_context,
                source_format=SourceFormat.form_input,
            ))

    def test_user_assumption_wrong_scope_rejected(self):
        with pytest.raises(ValidationError, match="user_assertion"):
            SourceManifestEntry(**_valid_source_manifest(
                semantic_context_category=SemanticContextCategory.user_assumption,
                source_scope=SourceScope.external_context,
                source_format=SourceFormat.form_input,
            ))

    # Unlocked categories accept flexible scope
    def test_data_source_accepts_internal_observation(self):
        entry = SourceManifestEntry(**_valid_source_manifest(
            semantic_context_category=SemanticContextCategory.data_source,
            source_scope=SourceScope.internal_observation,
        ))
        assert entry.semantic_context_category == SemanticContextCategory.data_source

    def test_internal_report_accepts_internal_observation(self):
        entry = SourceManifestEntry(**_valid_source_manifest(
            semantic_context_category=SemanticContextCategory.internal_report,
            source_scope=SourceScope.internal_observation,
        ))
        assert entry.semantic_context_category == SemanticContextCategory.internal_report


# ---------------------------------------------------------------------------
# Additional edge cases (retained from original + expanded)
# ---------------------------------------------------------------------------


class TestAdditionalEdgeCases:
    def test_blank_evidence_type_rejected(self):
        with pytest.raises(ValidationError, match="evidence_type"):
            EvidenceObject(**_valid_evidence_object(evidence_type="   "))

    def test_blank_finding_rejected(self):
        with pytest.raises(ValidationError, match="finding must not be blank"):
            EvidenceObject(**_valid_evidence_object(finding=""))

    def test_blank_supporting_evidence_rejected(self):
        with pytest.raises(ValidationError, match="supporting_evidence must not be blank"):
            EvidenceObject(**_valid_evidence_object(supporting_evidence="  "))

    def test_blank_decision_relevance_rejected(self):
        with pytest.raises(ValidationError, match="decision_relevance must not be blank"):
            EvidenceObject(**_valid_evidence_object(decision_relevance=""))

    def test_blank_id_algo_version_rejected_on_manifest(self):
        with pytest.raises(ValidationError, match="id_algo_version"):
            SourceManifestEntry(**_valid_source_manifest(id_algo_version=""))

    def test_health_candidate_blank_claim_key_rejected(self):
        with pytest.raises(ValidationError, match="normalized_claim_key"):
            HealthFindingCandidate(**_valid_health_candidate(normalized_claim_key=""))

    def test_health_candidate_top_level_set_in_rule_params_rejected(self):
        with pytest.raises(ValidationError, match="non-JSON-compatible"):
            HealthFindingCandidate(**_valid_health_candidate(
                canonical_rule_parameters={"bad_value": {1, 2, 3}}
            ))

    def test_health_candidate_top_level_bytes_in_rule_params_rejected(self):
        with pytest.raises(ValidationError, match="non-JSON-compatible"):
            HealthFindingCandidate(**_valid_health_candidate(
                canonical_rule_parameters={"bad_value": b"bytes"}
            ))

    def test_health_candidate_valid_rule_params_accepted(self):
        candidate = HealthFindingCandidate(**_valid_health_candidate(
            canonical_rule_parameters={
                "column": "usage_frequency",
                "threshold": 0.2,
                "row_count": 100,
                "tags": ["optional", "check"],
                "nested": {"sub": 1},
            }
        ))
        assert candidate.canonical_rule_parameters["threshold"] == 0.2

    def test_source_manifest_optional_fields_none_by_default(self):
        entry = SourceManifestEntry(**_valid_source_manifest())
        assert entry.filename is None
        assert entry.upload_event_id is None

    def test_source_manifest_with_optional_fields(self):
        entry = SourceManifestEntry(**_valid_source_manifest(
            filename="churn_data.csv",
            upload_event_id="upload-session-001",
        ))
        assert entry.filename == "churn_data.csv"
        assert entry.upload_event_id == "upload-session-001"


# ---------------------------------------------------------------------------
# Correction 1. validate_assignment=True — post-construction assignment
# ---------------------------------------------------------------------------


class TestFrozenModels:
    """Tests that ContractModel subclasses are fully immutable (frozen=True).

    frozen=True replaces validate_assignment=True.  Any attempt to assign a
    field after construction raises ValidationError.  Revised objects must be
    reconstructed and re-validated rather than mutated in place.
    """

    def test_invalid_source_id_assignment_rejected(self):
        """Assigning any field on a frozen SourceManifestEntry raises ValidationError."""
        entry = SourceManifestEntry(**_valid_source_manifest())
        with pytest.raises(ValidationError):
            entry.source_id = "bad"

    def test_valid_source_id_assignment_also_rejected(self):
        """Even a valid assignment is rejected because models are frozen.

        Revised objects must be reconstructed via SourceManifestEntry(**changes).
        """
        entry = SourceManifestEntry(**_valid_source_manifest())
        with pytest.raises(ValidationError):
            entry.source_id = "src-csv-aabbccddee11"

    def test_blank_id_algo_version_assignment_rejected_on_evidence(self):
        """Any assignment to EvidenceObject raises ValidationError (frozen)."""
        obj = EvidenceObject(**_valid_evidence_object())
        with pytest.raises(ValidationError):
            obj.id_algo_version = ""

    def test_whitespace_id_algo_version_assignment_rejected_on_evidence(self):
        obj = EvidenceObject(**_valid_evidence_object())
        with pytest.raises(ValidationError):
            obj.id_algo_version = "   "

    def test_blank_roles_assignment_rejected_on_health_candidate(self):
        """Assignment to HealthFindingCandidate is rejected (frozen)."""
        candidate = HealthFindingCandidate(**_valid_health_candidate())
        with pytest.raises(ValidationError):
            candidate.relevant_roles = [""]

    def test_incompatible_format_assignment_rejected_on_evidence(self):
        """Assigning an incompatible source_format to a frozen EvidenceObject raises
        ValidationError.  With frozen=True, even valid same-value assignments fail.

        Revised objects must be reconstructed and validated rather than mutated.
        Cross-field checks (format/locator compatibility) run on full reconstruction,
        not on individual field assignment.
        """
        obj = EvidenceObject(**_valid_evidence_object(
            source_format=SourceFormat.csv,
            source_locator=_tabular_locator(),
        ))
        # frozen=True rejects all post-construction assignment, including same-value.
        with pytest.raises(ValidationError):
            obj.source_format = SourceFormat.csv

    def test_model_remains_valid_and_unchanged_after_failed_assignment(self):
        """A failed assignment must not corrupt the model's existing valid value.

        With frozen=True, no assignment succeeds, so the model is always unchanged.
        This verifies the invariant: after any assignment attempt (caught or not),
        the original value is still present.
        """
        entry = SourceManifestEntry(**_valid_source_manifest())
        original_id = entry.source_id
        try:
            entry.source_id = "bad"
        except Exception:
            pass
        assert entry.source_id == original_id, (
            "Model must remain unchanged after failed assignment"
        )

    def test_cross_field_incompatible_assignment_impossible(self):
        """Assigning a mismatched source_format to an EvidenceObject is impossible.

        Because frozen=True, no field can be changed after construction.  An
        incompatible cross-field state can only be reached by constructing a new
        model with mismatched inputs — which is rejected by the model_validator.
        This test verifies that reconstruction with incompatible format+locator fails.
        """
        with pytest.raises(ValidationError):
            # pasted_text requires TextSourceLocator, not TabularSourceLocator.
            EvidenceObject(**_valid_evidence_object(
                source_format=SourceFormat.pasted_text,
                source_locator=_tabular_locator(),
            ))


# ---------------------------------------------------------------------------
# Correction 2. Stable identity-key syntax
# ---------------------------------------------------------------------------


class TestIdAlgoVersionSyntax:
    @pytest.mark.parametrize("bad", [
        " v1 ",       # padded
        "  ",         # whitespace only
        "",           # empty
        "V1",         # uppercase
        "v 1",        # space inside
        "-v1",        # starts with hyphen
        ".v1",        # starts with dot
        "a" * 33,     # too long (33 chars)
    ])
    def test_invalid_id_algo_version_rejected(self, bad: str):
        with pytest.raises(ValidationError, match="id_algo_version"):
            SourceManifestEntry(**_valid_source_manifest(id_algo_version=bad))

    @pytest.mark.parametrize("good", [
        "v1",
        "v1.1",
        "v2-beta",
        "0",
        "a1",
        "a" * 32,     # max length (32 chars)
    ])
    def test_valid_id_algo_version_accepted(self, good: str):
        entry = SourceManifestEntry(**_valid_source_manifest(id_algo_version=good))
        assert entry.id_algo_version == good

    def test_evidence_object_id_algo_version_padded_rejected(self):
        with pytest.raises(ValidationError, match="id_algo_version"):
            EvidenceObject(**_valid_evidence_object(id_algo_version=" v1 "))

    def test_evidence_object_valid_version_accepted(self):
        obj = EvidenceObject(**_valid_evidence_object(id_algo_version="v1.1"))
        assert obj.id_algo_version == "v1.1"


class TestEvidenceTypeSyntax:
    @pytest.mark.parametrize("bad", [
        " missing_value_rate ",   # padded
        "Missing Value Rate",     # uppercase + spaces
        "Hello World!",           # uppercase + special chars
        "missing value",          # space inside
        "missing-value",          # hyphen not allowed
        "1starts_with_digit",     # starts with digit
        "_starts_underscore",     # starts with underscore
        "a" * 65,                 # too long (65 chars)
        "",                       # empty
    ])
    def test_invalid_evidence_type_rejected_on_evidence_object(self, bad: str):
        with pytest.raises(ValidationError, match="evidence_type"):
            EvidenceObject(**_valid_evidence_object(evidence_type=bad))

    @pytest.mark.parametrize("good", [
        "missing_value_rate",
        "outlier_flag",
        "duplicate_row",
        "a",
        "a" * 64,     # max length
    ])
    def test_valid_evidence_type_accepted_on_evidence_object(self, good: str):
        obj = EvidenceObject(**_valid_evidence_object(evidence_type=good))
        assert obj.evidence_type == good

    def test_invalid_evidence_type_rejected_on_health_candidate(self):
        with pytest.raises(ValidationError, match="evidence_type"):
            HealthFindingCandidate(**_valid_health_candidate(
                evidence_type=" missing_value_rate "
            ))

    def test_valid_evidence_type_accepted_on_health_candidate(self):
        candidate = HealthFindingCandidate(**_valid_health_candidate(
            evidence_type="missing_value_rate"
        ))
        assert candidate.evidence_type == "missing_value_rate"


class TestNormalizedClaimKeySyntax:
    @pytest.mark.parametrize("bad", [
        "missing..rate",             # empty segment
        "Hello World!",              # uppercase + special chars
        " missing_value_rate ",      # padded
        "missing value rate",        # spaces
        "missing-value-rate",        # hyphens not allowed
        ".leading_dot",              # starts with dot
        "trailing_dot.",             # ends with dot
        "a.B.c",                     # uppercase segment
        "1starts_with_digit",        # starts with digit
        "",                          # empty
        "a" * 129,                   # too long (> 128 chars)
    ])
    def test_invalid_claim_key_rejected(self, bad: str):
        with pytest.raises(ValidationError, match="normalized_claim_key"):
            HealthFindingCandidate(**_valid_health_candidate(
                normalized_claim_key=bad
            ))

    @pytest.mark.parametrize("good", [
        "missing_value_rate",
        "missing_value_rate.usage_frequency",
        "outlier.revenue_concentration",
        "a",
        "a.b",
        "a.b.c.d",
        "a" * 128,                   # exactly at max length
    ])
    def test_valid_claim_key_accepted(self, good: str):
        candidate = HealthFindingCandidate(**_valid_health_candidate(
            normalized_claim_key=good
        ))
        assert candidate.normalized_claim_key == good

    def test_claim_key_exactly_128_chars_accepted(self):
        # Construct a valid 128-char key: "a.b_c.d_e..." repeating segments
        key = ".".join(["a" + "b" * 10] * 11)[:128]
        # Ensure it still matches the pattern after slicing
        import re
        pattern = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*$")
        if pattern.match(key) and len(key) <= 128:
            candidate = HealthFindingCandidate(**_valid_health_candidate(
                normalized_claim_key=key
            ))
            assert len(candidate.normalized_claim_key) <= 128

    def test_claim_key_129_chars_rejected(self):
        key = "a" * 129
        with pytest.raises(ValidationError, match="normalized_claim_key"):
            HealthFindingCandidate(**_valid_health_candidate(
                normalized_claim_key=key
            ))


# ---------------------------------------------------------------------------
# Correction 3. Text range completeness
# ---------------------------------------------------------------------------


class TestTextRangeCompleteness:
    def test_line_end_without_line_start_rejected(self):
        with pytest.raises(ValidationError, match="line_end requires line_start"):
            TextSourceLocator(line_end=5)

    def test_char_end_without_char_start_rejected(self):
        with pytest.raises(ValidationError, match="char_end requires char_start"):
            TextSourceLocator(char_end=100)

    def test_line_start_alone_accepted(self):
        loc = TextSourceLocator(line_start=3)
        assert loc.line_start == 3
        assert loc.line_end is None

    def test_char_start_alone_accepted(self):
        loc = TextSourceLocator(char_start=50)
        assert loc.char_start == 50
        assert loc.char_end is None

    def test_valid_paired_line_range_accepted(self):
        loc = TextSourceLocator(line_start=0, line_end=10)
        assert loc.line_start == 0
        assert loc.line_end == 10

    def test_valid_paired_char_range_accepted(self):
        loc = TextSourceLocator(char_start=10, char_end=50)
        assert loc.char_start == 10
        assert loc.char_end == 50

    def test_line_end_without_line_start_but_with_other_field_rejected(self):
        """line_end without line_start is rejected even when another field provides
        location context — the pair rule is independent of the at_least_one check."""
        with pytest.raises(ValidationError, match="line_end requires line_start"):
            TextSourceLocator(line_end=5, paragraph_index=2)

    def test_char_end_without_char_start_but_with_heading_rejected(self):
        with pytest.raises(ValidationError, match="char_end requires char_start"):
            TextSourceLocator(char_end=100, heading_path="## Intro")
