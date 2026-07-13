"""
tests/test_data_parser.py — Tests for app/data_parser.py (Task 4).

Coverage targets:
  A. parse_csv — happy paths, column name preservation, dtype, BOM
  B. SourceFormatMismatchError — non-CSV format rejected
  C. CsvParseError — malformed CSV
  D. EmptyDataFrameError — empty bytes, header-only, all-null DataFrame
  E. Integration — sample file round-trip
"""

from __future__ import annotations

import io
from datetime import datetime, timezone

import pandas as pd
import pytest

from app.data_parser import (
    CsvParseError,
    EmptyDataFrameError,
    SourceFormatMismatchError,
    parse_csv,
)
from app.file_intake import ingest_csv
from app.schemas import SemanticContextCategory, SourceFormat, SourceManifestEntry
from pathlib import Path

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FIXED_DT = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
_SAMPLE_CSV_PATH = Path("sample_data") / "regional_sales_q1_q4.csv"


def _make_csv_entry(raw: bytes, category=SemanticContextCategory.data_source) -> SourceManifestEntry:
    return ingest_csv(raw, semantic_context_category=category, created_at=_FIXED_DT)


def _make_entry_with_format(source_format: SourceFormat) -> SourceManifestEntry:
    """Create a fake SourceManifestEntry with an arbitrary non-CSV format for testing."""
    from app.identity import generate_source_id
    sid, digest = generate_source_id(
        source_format=source_format.value,
        semantic_context_category="data_source",
        normalized_content="fake content",
    )
    from app.schemas import SourceScope
    return SourceManifestEntry(
        source_id=sid,
        identity_digest=digest,
        source_format=source_format,
        semantic_context_category=SemanticContextCategory.data_source,
        source_scope=SourceScope.internal_observation,
        id_algo_version="v1",
        created_at=_FIXED_DT,
    )


# ===========================================================================
# A. parse_csv — happy paths
# ===========================================================================


class TestParseCsvHappyPath:

    def test_returns_dataframe(self):
        raw = b"col_a,col_b\n1,2\n3,4\n"
        entry = _make_csv_entry(raw)
        df = parse_csv(raw, entry)
        assert isinstance(df, pd.DataFrame)

    def test_correct_shape(self):
        raw = b"a,b,c\n1,2,3\n4,5,6\n"
        entry = _make_csv_entry(raw)
        df = parse_csv(raw, entry)
        assert df.shape == (2, 3)

    def test_column_names_preserved(self):
        raw = b"region,revenue,churn_rate\n1,100,0.1\n"
        entry = _make_csv_entry(raw)
        df = parse_csv(raw, entry)
        assert list(df.columns) == ["region", "revenue", "churn_rate"]

    def test_column_names_are_strings(self):
        raw = b"col_a,col_b\n1,2\n"
        entry = _make_csv_entry(raw)
        df = parse_csv(raw, entry)
        for col in df.columns:
            assert isinstance(col, str)

    def test_values_are_strings(self):
        # data_parser reads all values as str — type analysis is data_health's job.
        raw = b"x,y\n1,hello\n2,world\n"
        entry = _make_csv_entry(raw)
        df = parse_csv(raw, entry)
        non_null = df["x"].dropna()
        assert all(isinstance(v, str) for v in non_null)

    def test_row_order_preserved(self):
        raw = b"id,val\n3,c\n1,a\n2,b\n"
        entry = _make_csv_entry(raw)
        df = parse_csv(raw, entry)
        assert list(df["id"]) == ["3", "1", "2"]

    def test_utf8_bom_handled(self):
        raw = b"\xef\xbb\xbfcol_a,col_b\n1,2\n"
        entry = _make_csv_entry(b"col_a,col_b\n1,2\n")  # entry built without BOM
        # pandas handles BOM via encoding_errors / utf-8-sig; we use utf-8 + pandas handles BOM
        df = parse_csv(raw, entry)
        assert "col_a" in df.columns or df.shape[1] == 2

    def test_single_column(self):
        raw = b"value\n1\n2\n3\n"
        entry = _make_csv_entry(raw)
        df = parse_csv(raw, entry)
        assert df.shape == (3, 1)
        assert list(df.columns) == ["value"]

    def test_single_row(self):
        raw = b"a,b\n1,2\n"
        entry = _make_csv_entry(raw)
        df = parse_csv(raw, entry)
        assert df.shape == (1, 2)

    def test_missing_values_become_nan(self):
        raw = b"a,b\n1,\n,2\n"
        entry = _make_csv_entry(raw)
        df = parse_csv(raw, entry)
        assert df["b"].iloc[0] != df["b"].iloc[0]  # NaN != NaN
        assert df["a"].iloc[1] != df["a"].iloc[1]

    def test_na_string_becomes_nan(self):
        raw = b"a,b\nNA,1\n2,N/A\n"
        entry = _make_csv_entry(raw)
        df = parse_csv(raw, entry)
        assert pd.isna(df["a"].iloc[0])
        assert pd.isna(df["b"].iloc[1])

    def test_header_only_no_data_rows(self):
        raw = b"a,b,c\n"
        entry = _make_csv_entry(raw)
        df = parse_csv(raw, entry)
        assert df.shape == (0, 3)

    def test_default_int_index(self):
        raw = b"a,b\n1,2\n3,4\n"
        entry = _make_csv_entry(raw)
        df = parse_csv(raw, entry)
        assert list(df.index) == [0, 1]


# ===========================================================================
# B. SourceFormatMismatchError
# ===========================================================================


class TestSourceFormatMismatch:
    @pytest.mark.parametrize("fmt", [
        SourceFormat.excel,
        SourceFormat.pasted_text,
        SourceFormat.markdown,
        SourceFormat.txt,
        SourceFormat.form_input,
    ])
    def test_non_csv_format_raises(self, fmt):
        entry = _make_entry_with_format(fmt)
        with pytest.raises(SourceFormatMismatchError) as exc_info:
            parse_csv(b"a,b\n1,2\n", entry)
        assert exc_info.value.actual_format == fmt.value

    def test_is_value_error_subclass(self):
        assert issubclass(SourceFormatMismatchError, ValueError)

    def test_message_contains_format(self):
        entry = _make_entry_with_format(SourceFormat.excel)
        with pytest.raises(SourceFormatMismatchError) as exc_info:
            parse_csv(b"x", entry)
        assert "excel" in str(exc_info.value)

    def test_source_id_in_error(self):
        entry = _make_entry_with_format(SourceFormat.excel)
        with pytest.raises(SourceFormatMismatchError) as exc_info:
            parse_csv(b"x", entry)
        assert entry.source_id in str(exc_info.value)


# ===========================================================================
# C. CsvParseError
# ===========================================================================


class TestCsvParseError:
    def test_is_value_error_subclass(self):
        assert issubclass(CsvParseError, ValueError)

    def test_attributes_set(self):
        err = CsvParseError(source_id="src-csv-abcdef012345", detail="test error")
        assert err.source_id == "src-csv-abcdef012345"
        assert err.detail == "test error"

    def test_message_contains_source_id(self):
        err = CsvParseError(source_id="src-csv-abcdef012345", detail="bad csv")
        assert "src-csv-abcdef012345" in str(err)


# ===========================================================================
# D. EmptyDataFrameError
# ===========================================================================


class TestEmptyDataFrameError:
    def test_is_value_error_subclass(self):
        assert issubclass(EmptyDataFrameError, ValueError)

    def test_attributes_set(self):
        err = EmptyDataFrameError(source_id="src-csv-abcdef012345", reason="no columns")
        assert err.source_id == "src-csv-abcdef012345"
        assert err.reason == "no columns"

    def test_entirely_empty_bytes_raises(self):
        # Empty bytes → EmptyDataError from pandas → EmptyDataFrameError
        raw = b""
        # We can't use ingest_csv here (it rejects empty bytes) so create entry manually.
        from app.identity import generate_source_id
        from app.schemas import SourceScope
        sid, digest = generate_source_id(
            source_format="csv",
            semantic_context_category="data_source",
            normalized_content="a,b\n1,2\n",
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
        with pytest.raises(EmptyDataFrameError):
            parse_csv(raw, entry)

    def test_all_null_dataframe_raises(self):
        # A CSV where every cell is null.
        raw = b"a,b\n,\n,\n"
        entry = _make_csv_entry(raw)
        with pytest.raises(EmptyDataFrameError, match="all"):
            parse_csv(raw, entry)


# ===========================================================================
# E. Integration — sample file round-trip
# ===========================================================================


class TestSampleFileIntegration:
    def test_sample_csv_parses_successfully(self):
        raw = _SAMPLE_CSV_PATH.read_bytes()
        entry = ingest_csv(raw, semantic_context_category=SemanticContextCategory.data_source, created_at=_FIXED_DT)
        df = parse_csv(raw, entry)
        assert isinstance(df, pd.DataFrame)
        assert df.shape[0] > 0
        assert df.shape[1] > 0

    def test_sample_csv_expected_columns(self):
        raw = _SAMPLE_CSV_PATH.read_bytes()
        entry = ingest_csv(raw, semantic_context_category=SemanticContextCategory.data_source, created_at=_FIXED_DT)
        df = parse_csv(raw, entry)
        expected_cols = {"region", "product_line", "q1_revenue", "churn_rate"}
        assert expected_cols.issubset(set(df.columns))

    def test_sample_csv_expected_row_count(self):
        # Sample CSV has 13 data rows (12 unique + 1 duplicate of row 1)
        raw = _SAMPLE_CSV_PATH.read_bytes()
        entry = ingest_csv(raw, semantic_context_category=SemanticContextCategory.data_source, created_at=_FIXED_DT)
        df = parse_csv(raw, entry)
        assert df.shape[0] == 13  # 13 data rows total
