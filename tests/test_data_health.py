"""
tests/test_data_health.py — Tests for app/data_health.py (Task 4).

Coverage targets:
  A. analyze_data_health — summary fields, candidate list structure
  B. DataHealthSummary contents — row_count, col_count, dup_count, missing_rates
  C. HealthFindingCandidate list — no evidence_id field, correct evidence_type_keys,
                                   correct normalized_claim_keys, correct locators
  D. Per-finding rules — duplicates, missing values, mixed types, constant columns,
                          all-null columns, unnamed columns
  E. Minting boundary enforcement — no evidence_id on any candidate
  F. Edge cases — empty DataFrame (zero rows), single-column, no findings (clean data)
  G. Integration — sample CSV round-trip
  H. DataHealthSummary schema — added in Task 4
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from app.data_health import (
    ET_ALL_NULL_COLUMN,
    ET_CONSTANT_COLUMN,
    ET_DUPLICATE_ROW,
    ET_MISSING_VALUE,
    ET_MIXED_TYPES,
    ET_SCHEMA_UNNAMED,
    analyze_data_health,
)
from app.data_parser import parse_csv
from app.file_intake import ingest_csv
from app.schemas import (
    DataHealthSummary,
    HealthFindingCandidate,
    SemanticContextCategory,
    SourceFormat,
    SourceManifestEntry,
    SourceScope,
    TabularSourceLocator,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FIXED_DT = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
_SAMPLE_CSV_PATH = Path("sample_data") / "regional_sales_q1_q4.csv"


def _entry(raw: bytes) -> SourceManifestEntry:
    return ingest_csv(raw, semantic_context_category=SemanticContextCategory.data_source, created_at=_FIXED_DT)


def _parse(raw: bytes) -> tuple[pd.DataFrame, SourceManifestEntry]:
    entry = _entry(raw)
    return parse_csv(raw, entry), entry


def _find_candidates_by_type(candidates: list[HealthFindingCandidate], evidence_type: str) -> list[HealthFindingCandidate]:
    return [c for c in candidates if c.evidence_type == evidence_type]


# ===========================================================================
# A. analyze_data_health — basic structure
# ===========================================================================


class TestAnalyzeDataHealthStructure:

    def test_returns_tuple(self):
        raw = b"a,b\n1,2\n3,4\n"
        df, entry = _parse(raw)
        result = analyze_data_health(df, entry)
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_first_element_is_data_health_summary(self):
        raw = b"a,b\n1,2\n3,4\n"
        df, entry = _parse(raw)
        summary, _ = analyze_data_health(df, entry)
        assert isinstance(summary, DataHealthSummary)

    def test_second_element_is_list(self):
        raw = b"a,b\n1,2\n3,4\n"
        df, entry = _parse(raw)
        _, candidates = analyze_data_health(df, entry)
        assert isinstance(candidates, list)

    def test_all_candidates_are_health_finding_candidates(self):
        raw = b"a,b\n1,2\n3,4\n"
        df, entry = _parse(raw)
        _, candidates = analyze_data_health(df, entry)
        for c in candidates:
            assert isinstance(c, HealthFindingCandidate)

    def test_zero_column_df_raises(self):
        from app.schemas import SourceScope
        from app.identity import generate_source_id
        sid, digest = generate_source_id(
            source_format="csv",
            semantic_context_category="data_source",
            normalized_content="placeholder",
        )
        entry = SourceManifestEntry(
            source_id=sid,
            identity_digest=digest,
            source_format=SourceFormat.csv,
            semantic_context_category=SemanticContextCategory.data_source,
            source_scope=SourceScope.internal_observation,
            id_algo_version="v1",
            created_at=_FIXED_DT,
        )
        empty_df = pd.DataFrame()
        with pytest.raises(ValueError, match="zero-column"):
            analyze_data_health(empty_df, entry)


# ===========================================================================
# B. DataHealthSummary contents
# ===========================================================================


class TestDataHealthSummaryContents:

    def test_row_count(self):
        raw = b"a,b\n1,2\n3,4\n5,6\n"
        df, entry = _parse(raw)
        summary, _ = analyze_data_health(df, entry)
        assert summary.row_count == 3

    def test_column_count(self):
        raw = b"a,b,c\n1,2,3\n"
        df, entry = _parse(raw)
        summary, _ = analyze_data_health(df, entry)
        assert summary.column_count == 3

    def test_source_id_matches_entry(self):
        raw = b"a,b\n1,2\n"
        df, entry = _parse(raw)
        summary, _ = analyze_data_health(df, entry)
        assert summary.source_id == entry.source_id

    def test_duplicate_row_count_zero_for_clean_data(self):
        raw = b"a,b\n1,2\n3,4\n"
        df, entry = _parse(raw)
        summary, _ = analyze_data_health(df, entry)
        assert summary.duplicate_row_count == 0

    def test_duplicate_row_count_detected(self):
        raw = b"a,b\n1,2\n1,2\n3,4\n"
        df, entry = _parse(raw)
        summary, _ = analyze_data_health(df, entry)
        assert summary.duplicate_row_count == 1

    def test_missing_value_rates_zero_for_complete_data(self):
        raw = b"a,b\n1,2\n3,4\n"
        df, entry = _parse(raw)
        summary, _ = analyze_data_health(df, entry)
        for rate in summary.missing_value_rates.values():
            assert rate == 0.0

    def test_missing_value_rates_computed(self):
        raw = b"a,b\n1,\n3,4\n5,\n"
        df, entry = _parse(raw)
        summary, _ = analyze_data_health(df, entry)
        assert summary.missing_value_rates["b"] == pytest.approx(2 / 3, rel=1e-4)

    def test_missing_rates_all_columns_present(self):
        raw = b"x,y,z\n1,2,3\n"
        df, entry = _parse(raw)
        summary, _ = analyze_data_health(df, entry)
        assert set(summary.missing_value_rates.keys()) == {"x", "y", "z"}

    def test_constant_columns_detected(self):
        raw = b"a,b\n1,CONST\n2,CONST\n3,CONST\n"
        df, entry = _parse(raw)
        summary, _ = analyze_data_health(df, entry)
        assert "b" in summary.constant_columns

    def test_no_constant_columns_for_varied_data(self):
        raw = b"a,b\n1,x\n2,y\n3,z\n"
        df, entry = _parse(raw)
        summary, _ = analyze_data_health(df, entry)
        assert summary.constant_columns == []

    def test_schema_issues_empty_for_clean_columns(self):
        raw = b"region,revenue\n1,100\n"
        df, entry = _parse(raw)
        summary, _ = analyze_data_health(df, entry)
        assert summary.schema_issues == []

    def test_zero_row_dataframe_produces_valid_summary(self):
        raw = b"a,b,c\n"  # header only
        df, entry = _parse(raw)
        summary, candidates = analyze_data_health(df, entry)
        assert summary.row_count == 0
        assert summary.column_count == 3
        assert candidates == []


# ===========================================================================
# C. HealthFindingCandidate list — minting boundary
# ===========================================================================


class TestMintingBoundaryEnforcement:
    """Confirm that no HealthFindingCandidate ever has an evidence_id field.

    This is the key invariant from Decision 002: data_health.py cannot mint
    evidence_id.  HealthFindingCandidate schema enforces this via extra="forbid".
    """

    def test_candidates_have_no_evidence_id_attribute(self):
        raw = b"a,b\n1,2\n1,2\n3,4\n"  # one duplicate
        df, entry = _parse(raw)
        _, candidates = analyze_data_health(df, entry)
        for c in candidates:
            assert not hasattr(c, "evidence_id"), (
                f"Candidate {c.evidence_type!r} has evidence_id field — minting boundary violated!"
            )

    def test_candidates_have_no_identity_digest_attribute(self):
        raw = b"a,b\n1,2\n1,2\n"
        df, entry = _parse(raw)
        _, candidates = analyze_data_health(df, entry)
        for c in candidates:
            assert not hasattr(c, "identity_digest")

    def test_pydantic_forbids_evidence_id_on_candidate(self):
        from pydantic import ValidationError
        raw = b"a,b\n1,2\n"
        df, entry = _parse(raw)
        _, candidates = analyze_data_health(df, entry)
        # Confirm that constructing HealthFindingCandidate with evidence_id raises.
        first = candidates[0] if candidates else None
        if first is not None:
            with pytest.raises(ValidationError):
                HealthFindingCandidate(
                    **first.model_dump(),
                    evidence_id="ev-test-000000000000",  # forbidden field
                )

    def test_all_candidates_source_id_matches_entry(self):
        raw = b"a,b\n1,\n2,\n1,\n"
        df, entry = _parse(raw)
        _, candidates = analyze_data_health(df, entry)
        for c in candidates:
            assert c.source_id == entry.source_id

    def test_all_candidates_source_format_is_csv(self):
        raw = b"a,b\n1,2\n1,2\n"
        df, entry = _parse(raw)
        _, candidates = analyze_data_health(df, entry)
        for c in candidates:
            assert c.source_format == SourceFormat.csv

    def test_all_candidates_have_tabular_locator(self):
        raw = b"a,b\n1,2\n1,2\n"
        df, entry = _parse(raw)
        _, candidates = analyze_data_health(df, entry)
        for c in candidates:
            assert isinstance(c.source_locator, TabularSourceLocator)

    def test_all_candidates_relevant_roles_nonempty(self):
        raw = b"a,b\n1,2\n1,2\n"
        df, entry = _parse(raw)
        _, candidates = analyze_data_health(df, entry)
        for c in candidates:
            assert len(c.relevant_roles) > 0

    def test_all_candidates_have_normalized_claim_key(self):
        raw = b"a,b\n1,\n1,\n"
        df, entry = _parse(raw)
        _, candidates = analyze_data_health(df, entry)
        for c in candidates:
            assert isinstance(c.normalized_claim_key, str)
            assert len(c.normalized_claim_key) > 0


# ===========================================================================
# D. Per-finding rules
# ===========================================================================


class TestDuplicateRowFinding:

    def test_duplicate_finding_emitted_when_dups_present(self):
        raw = b"a,b\n1,2\n1,2\n3,4\n"
        df, entry = _parse(raw)
        _, candidates = analyze_data_health(df, entry)
        dup_candidates = _find_candidates_by_type(candidates, ET_DUPLICATE_ROW)
        assert len(dup_candidates) == 1

    def test_duplicate_evidence_type_key(self):
        raw = b"a,b\n1,2\n1,2\n"
        df, entry = _parse(raw)
        _, candidates = analyze_data_health(df, entry)
        assert any(c.evidence_type == ET_DUPLICATE_ROW for c in candidates)

    def test_duplicate_claim_key(self):
        raw = b"a,b\n1,2\n1,2\n"
        df, entry = _parse(raw)
        _, candidates = analyze_data_health(df, entry)
        dup = _find_candidates_by_type(candidates, ET_DUPLICATE_ROW)[0]
        assert dup.normalized_claim_key == "data.duplicate_rows"

    def test_no_duplicate_finding_when_clean(self):
        raw = b"a,b\n1,2\n3,4\n"
        df, entry = _parse(raw)
        _, candidates = analyze_data_health(df, entry)
        assert not any(c.evidence_type == ET_DUPLICATE_ROW for c in candidates)

    def test_duplicate_rule_parameters(self):
        raw = b"a,b\n1,2\n1,2\n3,4\n"
        df, entry = _parse(raw)
        _, candidates = analyze_data_health(df, entry)
        dup = _find_candidates_by_type(candidates, ET_DUPLICATE_ROW)[0]
        assert dup.canonical_rule_parameters["duplicate_row_count"] == 1
        assert dup.canonical_rule_parameters["row_count"] == 3

    def test_multiple_duplicates(self):
        raw = b"a,b\n1,2\n1,2\n1,2\n3,4\n"
        df, entry = _parse(raw)
        _, candidates = analyze_data_health(df, entry)
        dup = _find_candidates_by_type(candidates, ET_DUPLICATE_ROW)[0]
        assert dup.canonical_rule_parameters["duplicate_row_count"] == 2

    def test_duplicate_finding_confidence_high(self):
        raw = b"a,b\n1,2\n1,2\n"
        df, entry = _parse(raw)
        _, candidates = analyze_data_health(df, entry)
        dup = _find_candidates_by_type(candidates, ET_DUPLICATE_ROW)[0]
        assert dup.confidence == "high"


class TestMissingValueFinding:

    def test_missing_finding_emitted_per_column(self):
        raw = b"a,b,c\n1,,3\n,2,3\n"
        df, entry = _parse(raw)
        _, candidates = analyze_data_health(df, entry)
        missing = _find_candidates_by_type(candidates, ET_MISSING_VALUE)
        missing_cols = {c.source_locator.columns[0] for c in missing}
        assert "a" in missing_cols
        assert "b" in missing_cols

    def test_no_missing_finding_for_complete_column(self):
        raw = b"a,b\n1,10\n2,20\n"
        df, entry = _parse(raw)
        _, candidates = analyze_data_health(df, entry)
        missing = _find_candidates_by_type(candidates, ET_MISSING_VALUE)
        assert len(missing) == 0

    def test_missing_claim_key_format(self):
        raw = b"my_col,b\n,2\n"
        df, entry = _parse(raw)
        _, candidates = analyze_data_health(df, entry)
        missing = _find_candidates_by_type(candidates, ET_MISSING_VALUE)
        keys = {c.normalized_claim_key for c in missing}
        assert "data.missing.my_col" in keys

    def test_missing_rate_in_rule_parameters(self):
        raw = b"a,b\n1,\n2,\n3,4\n"  # b: 2/3 missing
        df, entry = _parse(raw)
        _, candidates = analyze_data_health(df, entry)
        missing = _find_candidates_by_type(candidates, ET_MISSING_VALUE)
        b_candidate = next(c for c in missing if c.source_locator.columns == ["b"])
        assert b_candidate.canonical_rule_parameters["missing_rate"] == pytest.approx(2 / 3, rel=1e-4)

    def test_missing_confidence_high(self):
        raw = b"a,b\n1,\n2,3\n"
        df, entry = _parse(raw)
        _, candidates = analyze_data_health(df, entry)
        missing = _find_candidates_by_type(candidates, ET_MISSING_VALUE)
        for m in missing:
            assert m.confidence == "high"

    def test_one_finding_per_column_with_missing(self):
        raw = b"a,b\n1,\n,\n3,4\n"
        df, entry = _parse(raw)
        _, candidates = analyze_data_health(df, entry)
        missing = _find_candidates_by_type(candidates, ET_MISSING_VALUE)
        col_counts: dict[str, int] = {}
        for c in missing:
            col = c.source_locator.columns[0]
            col_counts[col] = col_counts.get(col, 0) + 1
        for col, count in col_counts.items():
            assert count == 1, f"Column {col!r} has {count} missing-value candidates"


class TestMixedTypeFinding:

    def test_mixed_type_detected(self):
        raw = b"a,b\n1,hello\n2,world\n3,100\n"
        df, entry = _parse(raw)
        _, candidates = analyze_data_health(df, entry)
        mixed = _find_candidates_by_type(candidates, ET_MIXED_TYPES)
        mixed_cols = {c.source_locator.columns[0] for c in mixed}
        assert "b" in mixed_cols

    def test_pure_numeric_column_not_flagged(self):
        raw = b"a,b\n1,10\n2,20\n3,30\n"
        df, entry = _parse(raw)
        _, candidates = analyze_data_health(df, entry)
        mixed = _find_candidates_by_type(candidates, ET_MIXED_TYPES)
        assert len(mixed) == 0

    def test_pure_string_column_not_flagged(self):
        raw = b"a,b\nNorth,East\nSouth,West\n"
        df, entry = _parse(raw)
        _, candidates = analyze_data_health(df, entry)
        mixed = _find_candidates_by_type(candidates, ET_MIXED_TYPES)
        assert len(mixed) == 0

    def test_mixed_type_claim_key_format(self):
        raw = b"revenue,segment\n100,B2B\n200,300\n"
        df, entry = _parse(raw)
        _, candidates = analyze_data_health(df, entry)
        mixed = _find_candidates_by_type(candidates, ET_MIXED_TYPES)
        keys = {c.normalized_claim_key for c in mixed}
        assert "data.mixed_types.segment" in keys


class TestConstantColumnFinding:

    def test_constant_column_detected(self):
        raw = b"a,b\n1,SAME\n2,SAME\n3,SAME\n"
        df, entry = _parse(raw)
        _, candidates = analyze_data_health(df, entry)
        const = _find_candidates_by_type(candidates, ET_CONSTANT_COLUMN)
        assert any(c.source_locator.columns == ["b"] for c in const)

    def test_non_constant_not_flagged(self):
        raw = b"a,b\n1,X\n2,Y\n3,Z\n"
        df, entry = _parse(raw)
        _, candidates = analyze_data_health(df, entry)
        const = _find_candidates_by_type(candidates, ET_CONSTANT_COLUMN)
        assert len(const) == 0

    def test_constant_column_claim_key(self):
        raw = b"status,val\nOK,1\nOK,2\nOK,3\n"
        df, entry = _parse(raw)
        _, candidates = analyze_data_health(df, entry)
        const = _find_candidates_by_type(candidates, ET_CONSTANT_COLUMN)
        keys = {c.normalized_claim_key for c in const}
        assert "data.constant_column.status" in keys


class TestAllNullColumnFinding:

    def test_all_null_column_detected(self):
        raw = b"a,b\n1,\n2,\n3,\n"
        df, entry = _parse(raw)
        _, candidates = analyze_data_health(df, entry)
        all_null = _find_candidates_by_type(candidates, ET_ALL_NULL_COLUMN)
        assert any(c.source_locator.columns == ["b"] for c in all_null)

    def test_partial_null_column_not_flagged_as_all_null(self):
        raw = b"a,b\n1,\n2,X\n3,\n"
        df, entry = _parse(raw)
        _, candidates = analyze_data_health(df, entry)
        all_null = _find_candidates_by_type(candidates, ET_ALL_NULL_COLUMN)
        assert not any(c.source_locator.columns == ["b"] for c in all_null)

    def test_all_null_claim_key_format(self):
        raw = b"notes,val\n,1\n,2\n"
        df, entry = _parse(raw)
        _, candidates = analyze_data_health(df, entry)
        all_null = _find_candidates_by_type(candidates, ET_ALL_NULL_COLUMN)
        keys = {c.normalized_claim_key for c in all_null}
        assert "data.schema.all_null_column.notes" in keys


class TestUnnamedColumnFinding:

    def test_unnamed_columns_detected(self):
        # Simulate a headerless CSV read with default settings that produces Unnamed: N.
        # We construct this DataFrame directly rather than from raw bytes.
        import io
        raw = b",col_b\n1,2\n3,4\n"  # first column has empty header → "Unnamed: 0"
        entry = _entry(raw)
        df = pd.read_csv(io.BytesIO(raw), dtype=str)
        # pandas may rename '' → 'Unnamed: 0' in some versions
        if any(str(c).startswith("Unnamed:") for c in df.columns):
            _, candidates = analyze_data_health(df, entry)
            schema = _find_candidates_by_type(candidates, ET_SCHEMA_UNNAMED)
            assert len(schema) > 0
        # If pandas version doesn't produce Unnamed: prefix, skip.

    def test_clean_column_names_produce_no_schema_finding(self):
        raw = b"region,revenue\n1,100\n"
        df, entry = _parse(raw)
        _, candidates = analyze_data_health(df, entry)
        schema = _find_candidates_by_type(candidates, ET_SCHEMA_UNNAMED)
        assert len(schema) == 0


# ===========================================================================
# E. No findings for clean data
# ===========================================================================


class TestNoFindingsForCleanData:
    def test_clean_csv_zero_candidates(self):
        raw = b"region,revenue\nNorth,100\nSouth,200\nEast,300\n"
        df, entry = _parse(raw)
        _, candidates = analyze_data_health(df, entry)
        assert candidates == []


# ===========================================================================
# F. DataHealthSummary schema (Task 4 addition)
# ===========================================================================


class TestDataHealthSummarySchema:
    def test_can_construct_manually(self):
        from app.identity import generate_source_id
        sid, _ = generate_source_id(
            source_format="csv",
            semantic_context_category="data_source",
            normalized_content="a,b\n1,2\n",
        )
        s = DataHealthSummary(
            source_id=sid,
            row_count=10,
            column_count=3,
            duplicate_row_count=1,
            missing_value_rates={"a": 0.1, "b": 0.0, "c": 0.5},
        )
        assert s.row_count == 10
        assert s.column_count == 3

    def test_missing_rate_out_of_range_rejected(self):
        from pydantic import ValidationError
        from app.identity import generate_source_id
        sid, _ = generate_source_id(
            source_format="csv",
            semantic_context_category="data_source",
            normalized_content="a,b\n1,2\n",
        )
        with pytest.raises(ValidationError):
            DataHealthSummary(
                source_id=sid,
                row_count=10,
                column_count=2,
                duplicate_row_count=0,
                missing_value_rates={"a": 1.5},  # > 1.0
            )

    def test_invalid_source_id_rejected(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            DataHealthSummary(
                source_id="not_a_valid_id",
                row_count=10,
                column_count=2,
                duplicate_row_count=0,
            )


# ===========================================================================
# G. Integration — sample CSV round-trip
# ===========================================================================


class TestSampleCsvIntegration:
    def test_sample_csv_produces_summary_and_candidates(self):
        raw = _SAMPLE_CSV_PATH.read_bytes()
        entry = ingest_csv(raw, semantic_context_category=SemanticContextCategory.data_source, created_at=_FIXED_DT)
        df = parse_csv(raw, entry)
        summary, candidates = analyze_data_health(df, entry)

        assert isinstance(summary, DataHealthSummary)
        assert summary.row_count == 13  # 13 data rows in sample
        assert summary.column_count == 9  # 9 columns in sample
        assert summary.source_id == entry.source_id

        assert isinstance(candidates, list)
        # Sample has: 1 duplicate row, missing values in q3_revenue and q4_revenue
        dup_candidates = _find_candidates_by_type(candidates, ET_DUPLICATE_ROW)
        assert len(dup_candidates) == 1
        assert dup_candidates[0].canonical_rule_parameters["duplicate_row_count"] == 1

        missing_candidates = _find_candidates_by_type(candidates, ET_MISSING_VALUE)
        missing_cols = {c.source_locator.columns[0] for c in missing_candidates}
        assert "q3_revenue" in missing_cols
        assert "q4_revenue" in missing_cols

    def test_sample_csv_no_evidence_id_on_any_candidate(self):
        raw = _SAMPLE_CSV_PATH.read_bytes()
        entry = ingest_csv(raw, semantic_context_category=SemanticContextCategory.data_source, created_at=_FIXED_DT)
        df = parse_csv(raw, entry)
        _, candidates = analyze_data_health(df, entry)
        for c in candidates:
            assert not hasattr(c, "evidence_id")

    def test_sample_csv_results_are_idempotent(self):
        raw = _SAMPLE_CSV_PATH.read_bytes()
        entry = ingest_csv(raw, semantic_context_category=SemanticContextCategory.data_source, created_at=_FIXED_DT)
        df = parse_csv(raw, entry)
        summary1, candidates1 = analyze_data_health(df, entry)
        summary2, candidates2 = analyze_data_health(df, entry)
        assert summary1.row_count == summary2.row_count
        assert summary1.duplicate_row_count == summary2.duplicate_row_count
        assert len(candidates1) == len(candidates2)
        # Same evidence_type_keys in same order.
        types1 = [c.evidence_type for c in candidates1]
        types2 = [c.evidence_type for c in candidates2]
        assert types1 == types2
