"""
tests/test_file_intake.py — Tests for app/file_intake.py (Task 3).

Coverage targets:
  A. ingest_csv — happy paths, idempotency, filename exclusion from identity,
                  upload_event_id exclusion, ordering sensitivity,
                  category isolation, collision detection, empty content,
                  UTF-8 BOM handling, whitespace-only content
  B. ingest_source — CSV dispatch, unsupported format rejection
  C. EmptySourceError — attributes and message
  D. UnsupportedSourceFormatError — attributes and message
  E. _resolve_source_scope — all categories
  F. Integration — sample file round-trip
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.file_intake import (
    EmptySourceError,
    UnsupportedSourceFormatError,
    _resolve_source_scope,
    ingest_csv,
    ingest_form_input,
    ingest_source,
)
from app.identity import IdentityCollisionError
from app.schemas import (
    SemanticContextCategory,
    SourceFormat,
    SourceManifestEntry,
    SourceScope,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SOURCE_ID_RE = re.compile(r"^src-[a-z0-9_]{1,12}-[0-9a-f]{12}$")
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")

_SAMPLE_CSV_PATH = Path("sample_data") / "regional_sales_q1_q4.csv"

_SIMPLE_CSV = b"region,revenue\nNorth,100\nSouth,200\n"
_FIXED_DT = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


# ===========================================================================
# A. ingest_csv
# ===========================================================================


class TestIngestCsv:

    def test_returns_source_manifest_entry(self):
        result = ingest_csv(
            _SIMPLE_CSV,
            semantic_context_category=SemanticContextCategory.data_source,
            created_at=_FIXED_DT,
        )
        assert isinstance(result, SourceManifestEntry)

    def test_source_id_format(self):
        result = ingest_csv(
            _SIMPLE_CSV,
            semantic_context_category=SemanticContextCategory.data_source,
            created_at=_FIXED_DT,
        )
        assert _SOURCE_ID_RE.match(result.source_id), (
            f"source_id {result.source_id!r} does not match regex"
        )

    def test_source_id_starts_with_src_csv(self):
        result = ingest_csv(
            _SIMPLE_CSV,
            semantic_context_category=SemanticContextCategory.data_source,
            created_at=_FIXED_DT,
        )
        assert result.source_id.startswith("src-csv-")

    def test_identity_digest_64_hex(self):
        result = ingest_csv(
            _SIMPLE_CSV,
            semantic_context_category=SemanticContextCategory.data_source,
            created_at=_FIXED_DT,
        )
        assert _DIGEST_RE.match(result.identity_digest)

    def test_source_format_is_csv(self):
        result = ingest_csv(
            _SIMPLE_CSV,
            semantic_context_category=SemanticContextCategory.data_source,
            created_at=_FIXED_DT,
        )
        assert result.source_format == SourceFormat.csv

    def test_semantic_category_preserved(self):
        result = ingest_csv(
            _SIMPLE_CSV,
            semantic_context_category=SemanticContextCategory.data_source,
            created_at=_FIXED_DT,
        )
        assert result.semantic_context_category == SemanticContextCategory.data_source

    def test_created_at_preserved(self):
        result = ingest_csv(
            _SIMPLE_CSV,
            semantic_context_category=SemanticContextCategory.data_source,
            created_at=_FIXED_DT,
        )
        assert result.created_at == _FIXED_DT

    def test_created_at_defaults_to_utc_now(self):
        before = datetime.now(tz=timezone.utc)
        result = ingest_csv(
            _SIMPLE_CSV,
            semantic_context_category=SemanticContextCategory.data_source,
        )
        after = datetime.now(tz=timezone.utc)
        assert result.created_at.tzinfo is not None
        assert before <= result.created_at <= after

    # --- Idempotency ---

    def test_same_content_same_category_same_source_id(self):
        r1 = ingest_csv(
            _SIMPLE_CSV,
            semantic_context_category=SemanticContextCategory.data_source,
            created_at=_FIXED_DT,
        )
        r2 = ingest_csv(
            _SIMPLE_CSV,
            semantic_context_category=SemanticContextCategory.data_source,
            created_at=_FIXED_DT,
        )
        assert r1.source_id == r2.source_id
        assert r1.identity_digest == r2.identity_digest

    def test_idempotent_five_calls(self):
        kwargs = dict(
            semantic_context_category=SemanticContextCategory.data_source,
            created_at=_FIXED_DT,
        )
        ids = {ingest_csv(_SIMPLE_CSV, **kwargs).source_id for _ in range(5)}
        assert len(ids) == 1

    # --- Filename excluded from identity ---

    def test_filename_does_not_affect_source_id(self):
        r1 = ingest_csv(
            _SIMPLE_CSV,
            semantic_context_category=SemanticContextCategory.data_source,
            filename="sales_jan.csv",
            created_at=_FIXED_DT,
        )
        r2 = ingest_csv(
            _SIMPLE_CSV,
            semantic_context_category=SemanticContextCategory.data_source,
            filename="sales_feb.csv",
            created_at=_FIXED_DT,
        )
        assert r1.source_id == r2.source_id
        assert r1.identity_digest == r2.identity_digest

    def test_filename_stored_as_metadata(self):
        result = ingest_csv(
            _SIMPLE_CSV,
            semantic_context_category=SemanticContextCategory.data_source,
            filename="my_data.csv",
            created_at=_FIXED_DT,
        )
        assert result.filename == "my_data.csv"

    def test_none_filename_stored_as_none(self):
        result = ingest_csv(
            _SIMPLE_CSV,
            semantic_context_category=SemanticContextCategory.data_source,
            created_at=_FIXED_DT,
        )
        assert result.filename is None

    # --- upload_event_id excluded from identity ---

    def test_upload_event_id_does_not_affect_source_id(self):
        r1 = ingest_csv(
            _SIMPLE_CSV,
            semantic_context_category=SemanticContextCategory.data_source,
            upload_event_id="evt-001",
            created_at=_FIXED_DT,
        )
        r2 = ingest_csv(
            _SIMPLE_CSV,
            semantic_context_category=SemanticContextCategory.data_source,
            upload_event_id="evt-002",
            created_at=_FIXED_DT,
        )
        assert r1.source_id == r2.source_id

    def test_upload_event_id_stored_as_metadata(self):
        result = ingest_csv(
            _SIMPLE_CSV,
            semantic_context_category=SemanticContextCategory.data_source,
            upload_event_id="evt-xyz",
            created_at=_FIXED_DT,
        )
        assert result.upload_event_id == "evt-xyz"

    # --- Row order sensitivity ---

    def test_different_row_order_produces_different_source_id(self):
        csv_ab = b"region,revenue\nNorth,100\nSouth,200\n"
        csv_ba = b"region,revenue\nSouth,200\nNorth,100\n"
        r1 = ingest_csv(
            csv_ab,
            semantic_context_category=SemanticContextCategory.data_source,
            created_at=_FIXED_DT,
        )
        r2 = ingest_csv(
            csv_ba,
            semantic_context_category=SemanticContextCategory.data_source,
            created_at=_FIXED_DT,
        )
        assert r1.source_id != r2.source_id

    # --- BOM stripping ---

    def test_utf8_bom_stripped_before_hashing(self):
        with_bom = b"\xef\xbb\xbfregion,revenue\nNorth,100\n"
        without_bom = b"region,revenue\nNorth,100\n"
        r1 = ingest_csv(
            with_bom,
            semantic_context_category=SemanticContextCategory.data_source,
            created_at=_FIXED_DT,
        )
        r2 = ingest_csv(
            without_bom,
            semantic_context_category=SemanticContextCategory.data_source,
            created_at=_FIXED_DT,
        )
        assert r1.source_id == r2.source_id

    # --- Semantic category isolation ---

    def test_same_content_different_category_different_source_id(self):
        r1 = ingest_csv(
            _SIMPLE_CSV,
            semantic_context_category=SemanticContextCategory.data_source,
            created_at=_FIXED_DT,
        )
        r2 = ingest_csv(
            _SIMPLE_CSV,
            semantic_context_category=SemanticContextCategory.internal_report,
            created_at=_FIXED_DT,
        )
        assert r1.source_id != r2.source_id

    # --- Content change ---

    def test_different_content_different_source_id(self):
        csv_a = b"region,revenue\nNorth,100\n"
        csv_b = b"region,revenue\nNorth,200\n"
        r1 = ingest_csv(csv_a, semantic_context_category=SemanticContextCategory.data_source, created_at=_FIXED_DT)
        r2 = ingest_csv(csv_b, semantic_context_category=SemanticContextCategory.data_source, created_at=_FIXED_DT)
        assert r1.source_id != r2.source_id

    # --- Empty content ---

    def test_empty_bytes_raises_empty_source_error(self):
        with pytest.raises(EmptySourceError):
            ingest_csv(b"", semantic_context_category=SemanticContextCategory.data_source, created_at=_FIXED_DT)

    def test_whitespace_only_raises_empty_source_error(self):
        with pytest.raises(EmptySourceError):
            ingest_csv(b"   \n  \t  ", semantic_context_category=SemanticContextCategory.data_source, created_at=_FIXED_DT)

    def test_bom_only_raises_empty_source_error(self):
        with pytest.raises(EmptySourceError):
            ingest_csv(b"\xef\xbb\xbf", semantic_context_category=SemanticContextCategory.data_source, created_at=_FIXED_DT)

    # --- Collision detection via identity_registry ---

    def test_identity_registry_matching_digest_no_error(self):
        """Same source with its own digest in the registry: no collision."""
        r1 = ingest_csv(_SIMPLE_CSV, semantic_context_category=SemanticContextCategory.data_source, created_at=_FIXED_DT)
        r2 = ingest_csv(
            _SIMPLE_CSV,
            semantic_context_category=SemanticContextCategory.data_source,
            created_at=_FIXED_DT,
            identity_registry={r1.source_id: r1.identity_digest},
        )
        assert r1.source_id == r2.source_id

    def test_identity_registry_mismatched_digest_raises_collision_error(self):
        """Same source_id but different digest in registry: collision error."""
        r1 = ingest_csv(_SIMPLE_CSV, semantic_context_category=SemanticContextCategory.data_source, created_at=_FIXED_DT)
        with pytest.raises(IdentityCollisionError):
            ingest_csv(
                _SIMPLE_CSV,
                semantic_context_category=SemanticContextCategory.data_source,
                created_at=_FIXED_DT,
                identity_registry={r1.source_id: "a" * 64},
            )

    def test_identity_registry_unrelated_entry_no_collision(self):
        """A registry entry for a different source_id must not trigger a collision."""
        csv_a = b"region,revenue\nNorth,100\n"
        csv_b = b"region,revenue\nSouth,200\n"
        r_a = ingest_csv(csv_a, semantic_context_category=SemanticContextCategory.data_source, created_at=_FIXED_DT)
        r_b = ingest_csv(csv_b, semantic_context_category=SemanticContextCategory.data_source, created_at=_FIXED_DT)
        assert r_a.source_id != r_b.source_id
        # Ingesting csv_b with r_a's registry entry must NOT raise:
        # different source_id ≠ collision.
        r_b2 = ingest_csv(
            csv_b,
            semantic_context_category=SemanticContextCategory.data_source,
            created_at=_FIXED_DT,
            identity_registry={r_a.source_id: r_a.identity_digest},
        )
        assert r_b2.source_id == r_b.source_id

    def test_no_bare_existing_digest_parameter(self):
        """ingest_csv must NOT accept a bare existing_digest parameter.

        A bare digest disconnected from a short_id is logically insufficient
        and has been removed from the API.
        """
        with pytest.raises(TypeError):
            ingest_csv(  # type: ignore[call-arg]
                _SIMPLE_CSV,
                semantic_context_category=SemanticContextCategory.data_source,
                created_at=_FIXED_DT,
                existing_digest="a" * 64,
            )

    # --- source_scope ---

    def test_data_source_category_scope_is_internal_observation(self):
        result = ingest_csv(
            _SIMPLE_CSV,
            semantic_context_category=SemanticContextCategory.data_source,
            created_at=_FIXED_DT,
        )
        assert result.source_scope == SourceScope.internal_observation

    def test_internal_report_category_scope_is_internal_observation(self):
        result = ingest_csv(
            _SIMPLE_CSV,
            semantic_context_category=SemanticContextCategory.internal_report,
            created_at=_FIXED_DT,
        )
        assert result.source_scope == SourceScope.internal_observation

    # --- id_algo_version ---

    def test_id_algo_version_stored(self):
        result = ingest_csv(
            _SIMPLE_CSV,
            semantic_context_category=SemanticContextCategory.data_source,
            created_at=_FIXED_DT,
        )
        assert result.id_algo_version == "v1"


# ===========================================================================
# B. ingest_source dispatcher
# ===========================================================================


class TestIngestSource:

    def test_csv_format_dispatched_correctly(self):
        result = ingest_source(
            _SIMPLE_CSV,
            source_format=SourceFormat.csv,
            semantic_context_category=SemanticContextCategory.data_source,
            created_at=_FIXED_DT,
        )
        assert isinstance(result, SourceManifestEntry)
        assert result.source_format == SourceFormat.csv

    def test_excel_format_raises_unsupported(self):
        with pytest.raises(UnsupportedSourceFormatError) as exc_info:
            ingest_source(
                b"fake excel bytes",
                source_format=SourceFormat.excel,
                semantic_context_category=SemanticContextCategory.data_source,
                created_at=_FIXED_DT,
            )
        assert "excel" in str(exc_info.value)

    def test_pasted_text_format_raises_unsupported(self):
        with pytest.raises(UnsupportedSourceFormatError):
            ingest_source(
                b"some pasted text",
                source_format=SourceFormat.pasted_text,
                semantic_context_category=SemanticContextCategory.industry_context,
                created_at=_FIXED_DT,
            )

    def test_markdown_format_raises_unsupported(self):
        with pytest.raises(UnsupportedSourceFormatError):
            ingest_source(
                b"# Heading\n\nContent.",
                source_format=SourceFormat.markdown,
                semantic_context_category=SemanticContextCategory.internal_report,
                created_at=_FIXED_DT,
            )

    def test_form_input_format_raises_unsupported(self):
        with pytest.raises(UnsupportedSourceFormatError):
            ingest_source(
                b"business question text",
                source_format=SourceFormat.form_input,
                semantic_context_category=SemanticContextCategory.business_question,
                created_at=_FIXED_DT,
            )


# ===========================================================================
# C. EmptySourceError
# ===========================================================================


class TestEmptySourceError:
    def test_is_value_error_subclass(self):
        assert issubclass(EmptySourceError, ValueError)

    def test_attributes_set(self):
        err = EmptySourceError(source_format="csv", filename="data.csv")
        assert err.source_format == "csv"
        assert err.filename == "data.csv"

    def test_none_filename(self):
        err = EmptySourceError(source_format="csv")
        assert err.filename is None

    def test_message_contains_format(self):
        err = EmptySourceError(source_format="csv")
        assert "csv" in str(err)

    def test_message_contains_filename_when_provided(self):
        err = EmptySourceError(source_format="csv", filename="my_data.csv")
        assert "my_data.csv" in str(err)


# ===========================================================================
# D. UnsupportedSourceFormatError
# ===========================================================================


class TestUnsupportedSourceFormatError:
    def test_is_value_error_subclass(self):
        assert issubclass(UnsupportedSourceFormatError, ValueError)

    def test_attribute_set(self):
        err = UnsupportedSourceFormatError("excel")
        assert err.source_format == "excel"

    def test_message_contains_format(self):
        err = UnsupportedSourceFormatError("excel")
        assert "excel" in str(err)


# ===========================================================================
# E. _resolve_source_scope
# ===========================================================================


class TestResolveSourceScope:
    def test_data_source_unlocked_defaults_to_internal(self):
        assert _resolve_source_scope(SemanticContextCategory.data_source) == SourceScope.internal_observation

    def test_internal_report_unlocked_defaults_to_internal(self):
        assert _resolve_source_scope(SemanticContextCategory.internal_report) == SourceScope.internal_observation

    def test_industry_context_locked_external(self):
        assert _resolve_source_scope(SemanticContextCategory.industry_context) == SourceScope.external_context

    def test_strategy_profile_locked_user_assertion(self):
        assert _resolve_source_scope(SemanticContextCategory.strategy_profile) == SourceScope.user_assertion

    def test_user_assumption_locked_user_assertion(self):
        assert _resolve_source_scope(SemanticContextCategory.user_assumption) == SourceScope.user_assertion

    def test_business_question_locked_decision_context(self):
        assert _resolve_source_scope(SemanticContextCategory.business_question) == SourceScope.decision_context

    def test_decision_goal_locked_decision_context(self):
        assert _resolve_source_scope(SemanticContextCategory.decision_goal) == SourceScope.decision_context


# ===========================================================================
# F. Integration — sample file round-trip
# ===========================================================================


class TestSampleFileIntegration:
    def test_sample_csv_produces_valid_manifest_entry(self):
        raw = _SAMPLE_CSV_PATH.read_bytes()
        result = ingest_csv(
            raw,
            semantic_context_category=SemanticContextCategory.data_source,
            filename=_SAMPLE_CSV_PATH.name,
            created_at=_FIXED_DT,
        )
        assert isinstance(result, SourceManifestEntry)
        assert _SOURCE_ID_RE.match(result.source_id)
        assert _DIGEST_RE.match(result.identity_digest)
        assert result.source_format == SourceFormat.csv
        assert result.filename == _SAMPLE_CSV_PATH.name

    def test_sample_csv_idempotent(self):
        raw = _SAMPLE_CSV_PATH.read_bytes()
        r1 = ingest_csv(raw, semantic_context_category=SemanticContextCategory.data_source, created_at=_FIXED_DT)
        r2 = ingest_csv(raw, semantic_context_category=SemanticContextCategory.data_source, created_at=_FIXED_DT)
        assert r1.source_id == r2.source_id
        assert r1.identity_digest == r2.identity_digest

    def test_sample_csv_collision_check(self):
        raw = _SAMPLE_CSV_PATH.read_bytes()
        r1 = ingest_csv(raw, semantic_context_category=SemanticContextCategory.data_source, created_at=_FIXED_DT)
        # Re-ingest with the identity_registry containing the known (source_id, digest): must not raise.
        r2 = ingest_csv(
            raw,
            semantic_context_category=SemanticContextCategory.data_source,
            created_at=_FIXED_DT,
            identity_registry={r1.source_id: r1.identity_digest},
        )
        assert r1.source_id == r2.source_id


# ===========================================================================
# G. ingest_form_input  (Task 5B-1 requirements 20–32)
# ===========================================================================

_FORM_TEXT = "Our primary strategy is to retain enterprise customers through proactive support."
_FORM_ASSUMPTION = "We assume that price sensitivity is low in the enterprise segment."
_FORM_BQ = "Should we invest in proactive churn-prevention features this quarter?"
_FORM_DG = "Reduce enterprise churn to below 5% within 12 months."


class TestIngestFormInput:
    """Tests 20–32 for ingest_form_input."""

    # -----------------------------------------------------------------------
    # 20. strategy_profile → form_input + user_assertion
    # -----------------------------------------------------------------------

    def test_strategy_profile_produces_form_input_user_assertion(self):
        result = ingest_form_input(
            _FORM_TEXT,
            semantic_context_category=SemanticContextCategory.strategy_profile,
            created_at=_FIXED_DT,
        )
        assert isinstance(result, SourceManifestEntry)
        assert result.source_format == SourceFormat.form_input
        assert result.source_scope == SourceScope.user_assertion
        assert result.semantic_context_category == SemanticContextCategory.strategy_profile

    # -----------------------------------------------------------------------
    # 21. user_assumption → form_input + user_assertion
    # -----------------------------------------------------------------------

    def test_user_assumption_produces_form_input_user_assertion(self):
        result = ingest_form_input(
            _FORM_ASSUMPTION,
            semantic_context_category=SemanticContextCategory.user_assumption,
            created_at=_FIXED_DT,
        )
        assert isinstance(result, SourceManifestEntry)
        assert result.source_format == SourceFormat.form_input
        assert result.source_scope == SourceScope.user_assertion
        assert result.semantic_context_category == SemanticContextCategory.user_assumption

    # -----------------------------------------------------------------------
    # 22. business_question → form_input + decision_context
    # -----------------------------------------------------------------------

    def test_business_question_produces_form_input_decision_context(self):
        result = ingest_form_input(
            _FORM_BQ,
            semantic_context_category=SemanticContextCategory.business_question,
            created_at=_FIXED_DT,
        )
        assert isinstance(result, SourceManifestEntry)
        assert result.source_format == SourceFormat.form_input
        assert result.source_scope == SourceScope.decision_context
        assert result.semantic_context_category == SemanticContextCategory.business_question

    # -----------------------------------------------------------------------
    # 23. decision_goal → form_input + decision_context
    # -----------------------------------------------------------------------

    def test_decision_goal_produces_form_input_decision_context(self):
        result = ingest_form_input(
            _FORM_DG,
            semantic_context_category=SemanticContextCategory.decision_goal,
            created_at=_FIXED_DT,
        )
        assert isinstance(result, SourceManifestEntry)
        assert result.source_format == SourceFormat.form_input
        assert result.source_scope == SourceScope.decision_context
        assert result.semantic_context_category == SemanticContextCategory.decision_goal

    # -----------------------------------------------------------------------
    # 24. Unsupported categories rejected
    # -----------------------------------------------------------------------

    def test_data_source_category_rejected(self):
        with pytest.raises(ValueError, match="data_source"):
            ingest_form_input(
                "some text",
                semantic_context_category=SemanticContextCategory.data_source,
                created_at=_FIXED_DT,
            )

    def test_internal_report_category_rejected(self):
        with pytest.raises(ValueError, match="internal_report"):
            ingest_form_input(
                "some text",
                semantic_context_category=SemanticContextCategory.internal_report,
                created_at=_FIXED_DT,
            )

    def test_industry_context_category_rejected(self):
        with pytest.raises(ValueError, match="industry_context"):
            ingest_form_input(
                "some industry text",
                semantic_context_category=SemanticContextCategory.industry_context,
                created_at=_FIXED_DT,
            )

    # -----------------------------------------------------------------------
    # 25. Blank input rejected
    # -----------------------------------------------------------------------

    def test_blank_text_raises_empty_source_error(self):
        with pytest.raises(EmptySourceError):
            ingest_form_input(
                "",
                semantic_context_category=SemanticContextCategory.strategy_profile,
                created_at=_FIXED_DT,
            )

    def test_whitespace_only_text_raises_empty_source_error(self):
        with pytest.raises(EmptySourceError):
            ingest_form_input(
                "   \n\t  ",
                semantic_context_category=SemanticContextCategory.strategy_profile,
                created_at=_FIXED_DT,
            )

    # -----------------------------------------------------------------------
    # 26. Identical input + category → stable source identity (idempotent)
    # -----------------------------------------------------------------------

    def test_stable_source_identity_idempotent(self):
        r1 = ingest_form_input(
            _FORM_TEXT,
            semantic_context_category=SemanticContextCategory.strategy_profile,
            created_at=_FIXED_DT,
        )
        r2 = ingest_form_input(
            _FORM_TEXT,
            semantic_context_category=SemanticContextCategory.strategy_profile,
            created_at=_FIXED_DT,
        )
        assert r1.source_id == r2.source_id
        assert r1.identity_digest == r2.identity_digest

    # -----------------------------------------------------------------------
    # 27. Same text + different categories → different source IDs
    # -----------------------------------------------------------------------

    def test_same_text_different_category_different_source_id(self):
        r_sp = ingest_form_input(
            _FORM_TEXT,
            semantic_context_category=SemanticContextCategory.strategy_profile,
            created_at=_FIXED_DT,
        )
        r_ua = ingest_form_input(
            _FORM_TEXT,
            semantic_context_category=SemanticContextCategory.user_assumption,
            created_at=_FIXED_DT,
        )
        assert r_sp.source_id != r_ua.source_id

    # -----------------------------------------------------------------------
    # 28. identity_registry same ID + same digest accepted (no error)
    # -----------------------------------------------------------------------

    def test_identity_registry_same_id_same_digest_accepted(self):
        r1 = ingest_form_input(
            _FORM_TEXT,
            semantic_context_category=SemanticContextCategory.strategy_profile,
            created_at=_FIXED_DT,
        )
        # Re-ingest with own identity in registry: must not raise.
        r2 = ingest_form_input(
            _FORM_TEXT,
            semantic_context_category=SemanticContextCategory.strategy_profile,
            created_at=_FIXED_DT,
            identity_registry={r1.source_id: r1.identity_digest},
        )
        assert r1.source_id == r2.source_id

    # -----------------------------------------------------------------------
    # 29. identity_registry same ID + different digest raises IdentityCollisionError
    # -----------------------------------------------------------------------

    def test_identity_registry_same_id_different_digest_raises(self):
        r1 = ingest_form_input(
            _FORM_TEXT,
            semantic_context_category=SemanticContextCategory.strategy_profile,
            created_at=_FIXED_DT,
        )
        with pytest.raises(IdentityCollisionError):
            ingest_form_input(
                _FORM_TEXT,
                semantic_context_category=SemanticContextCategory.strategy_profile,
                created_at=_FIXED_DT,
                identity_registry={r1.source_id: "a" * 64},
            )

    # -----------------------------------------------------------------------
    # 30. Unrelated registry entry does not raise
    # -----------------------------------------------------------------------

    def test_unrelated_registry_entry_does_not_raise(self):
        text_a = _FORM_TEXT
        text_b = _FORM_ASSUMPTION
        r_a = ingest_form_input(
            text_a,
            semantic_context_category=SemanticContextCategory.strategy_profile,
            created_at=_FIXED_DT,
        )
        r_b = ingest_form_input(
            text_b,
            semantic_context_category=SemanticContextCategory.user_assumption,
            created_at=_FIXED_DT,
        )
        assert r_a.source_id != r_b.source_id
        # Ingesting text_b with r_a in registry must NOT raise.
        r_b2 = ingest_form_input(
            text_b,
            semantic_context_category=SemanticContextCategory.user_assumption,
            created_at=_FIXED_DT,
            identity_registry={r_a.source_id: r_a.identity_digest},
        )
        assert r_b2.source_id == r_b.source_id

    # -----------------------------------------------------------------------
    # 31. Supplied identity_registry is not mutated
    # -----------------------------------------------------------------------

    def test_supplied_identity_registry_not_mutated(self):
        r1 = ingest_form_input(
            _FORM_TEXT,
            semantic_context_category=SemanticContextCategory.strategy_profile,
            created_at=_FIXED_DT,
        )
        registry: dict[str, str] = {r1.source_id: r1.identity_digest}
        original_keys = set(registry.keys())
        ingest_form_input(
            _FORM_TEXT,
            semantic_context_category=SemanticContextCategory.strategy_profile,
            created_at=_FIXED_DT,
            identity_registry=registry,
        )
        assert set(registry.keys()) == original_keys, (
            "ingest_form_input must not mutate the supplied identity_registry"
        )

    # -----------------------------------------------------------------------
    # 32. No candidate or EvidenceObject produced by file_intake
    # -----------------------------------------------------------------------

    def test_no_candidate_or_evidence_object_produced(self):
        """ingest_form_input returns only a SourceManifestEntry — no candidate or evidence."""
        from app.schemas import EvidenceObject

        # Any attempt to import TextEvidenceCandidate from file_intake must fail.
        import app.file_intake as fi
        assert not hasattr(fi, "TextEvidenceCandidate"), (
            "file_intake must not expose TextEvidenceCandidate"
        )
        assert not hasattr(fi, "build_evidence"), (
            "file_intake must not expose build_evidence"
        )

        result = ingest_form_input(
            _FORM_TEXT,
            semantic_context_category=SemanticContextCategory.strategy_profile,
            created_at=_FIXED_DT,
        )
        assert isinstance(result, SourceManifestEntry)
        assert not isinstance(result, EvidenceObject)

    # -----------------------------------------------------------------------
    # source_id format and metadata checks
    # -----------------------------------------------------------------------

    def test_source_id_starts_with_src_form(self):
        result = ingest_form_input(
            _FORM_TEXT,
            semantic_context_category=SemanticContextCategory.strategy_profile,
            created_at=_FIXED_DT,
        )
        assert result.source_id.startswith("src-form-")

    def test_upload_event_id_stored_as_metadata(self):
        result = ingest_form_input(
            _FORM_TEXT,
            semantic_context_category=SemanticContextCategory.strategy_profile,
            upload_event_id="form-session-001",
            created_at=_FIXED_DT,
        )
        assert result.upload_event_id == "form-session-001"

    def test_created_at_defaults_to_utc_now(self):
        before = datetime.now(tz=timezone.utc)
        result = ingest_form_input(
            _FORM_TEXT,
            semantic_context_category=SemanticContextCategory.strategy_profile,
        )
        after = datetime.now(tz=timezone.utc)
        assert result.created_at.tzinfo is not None
        assert before <= result.created_at <= after

    def test_filename_is_none(self):
        """ingest_form_input does not accept a filename; it must always be None."""
        result = ingest_form_input(
            _FORM_TEXT,
            semantic_context_category=SemanticContextCategory.strategy_profile,
            created_at=_FIXED_DT,
        )
        assert result.filename is None

    def test_id_algo_version_stored(self):
        result = ingest_form_input(
            _FORM_TEXT,
            semantic_context_category=SemanticContextCategory.strategy_profile,
            created_at=_FIXED_DT,
        )
        assert result.id_algo_version == "v1"
