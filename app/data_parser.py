"""
app/data_parser.py — RoleLens CSV bytes → validated pandas DataFrame (Task 4).

Responsibilities:
  - Accept raw CSV bytes and a SourceManifestEntry.
  - Validate that the source is CSV format.
  - Decode, parse, and return a pandas DataFrame.
  - Detect and report parsing errors as structured exceptions.
  - Reject all-null DataFrames and frames with no columns.

Architecture invariants:
  - This module does NOT produce Evidence Objects or HealthFindingCandidates.
  - It does NOT mint evidence_id values.
  - It does NOT perform data-health analysis — that belongs in data_health.py.
  - Normalization (BOM, line endings) was already applied by file_intake.py
    when the SourceManifestEntry was created.  data_parser.py re-decodes from
    bytes independently because it receives raw bytes (the manifest entry holds
    provenance, not the parsed content).
"""

from __future__ import annotations

import io

import pandas as pd

from app.schemas import SourceFormat, SourceManifestEntry


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class CsvParseError(ValueError):
    """Raised when raw CSV bytes cannot be parsed into a DataFrame.

    Attributes:
        source_id: The source_id of the failing source.
        detail:    Human-readable description of the parse failure.
    """

    def __init__(self, source_id: str, detail: str) -> None:
        self.source_id = source_id
        self.detail = detail
        super().__init__(
            f"CSV parse failed for source_id={source_id!r}: {detail}"
        )


class EmptyDataFrameError(ValueError):
    """Raised when the parsed DataFrame has no usable data.

    This covers:
      - No columns (zero-column frame).
      - All cells are null (entirely-null frame).
      - Zero data rows (header-only file with no data rows is allowed as a
        warning, but entirely null is a hard error).

    Attributes:
        source_id: The source_id of the failing source.
        reason:    Brief description of why the frame is considered empty.
    """

    def __init__(self, source_id: str, reason: str) -> None:
        self.source_id = source_id
        self.reason = reason
        super().__init__(
            f"Empty or all-null DataFrame for source_id={source_id!r}: {reason}"
        )


class SourceFormatMismatchError(ValueError):
    """Raised when a SourceManifestEntry with a non-CSV format is passed.

    data_parser.py only handles CSV sources.  Excel parsing requires openpyxl
    and is a separate module (deferred to a later task).
    """

    def __init__(self, source_id: str, actual_format: str) -> None:
        self.source_id = source_id
        self.actual_format = actual_format
        super().__init__(
            f"data_parser.parse_csv expects SourceFormat.csv, "
            f"got {actual_format!r} for source_id={source_id!r}.  "
            "For Excel sources use a dedicated Excel parser (not yet implemented)."
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def parse_csv(
    raw_bytes: bytes,
    manifest_entry: SourceManifestEntry,
) -> pd.DataFrame:
    """Parse raw CSV bytes into a validated pandas DataFrame.

    Args:
        raw_bytes:       Raw CSV bytes.  BOM and line endings are handled
                         internally by pandas / UTF-8 decode with sig stripping.
        manifest_entry:  SourceManifestEntry for this source.  Used for
                         source_id context in error messages and format
                         validation.

    Returns:
        Parsed pandas DataFrame.  Column names are strings.  The index is the
        default integer RangeIndex (row order is preserved).

    Raises:
        SourceFormatMismatchError: If manifest_entry.source_format != csv.
        CsvParseError:             If pandas cannot parse the bytes as CSV.
        EmptyDataFrameError:       If the resulting DataFrame has no columns,
                                   or is entirely null.
    """
    source_id = manifest_entry.source_id

    if manifest_entry.source_format != SourceFormat.csv:
        raise SourceFormatMismatchError(
            source_id=source_id,
            actual_format=manifest_entry.source_format.value,
        )

    try:
        df = pd.read_csv(
            io.BytesIO(raw_bytes),
            encoding="utf-8",
            encoding_errors="strict",
            dtype=str,           # read all columns as str; type analysis is data_health.py's job
            keep_default_na=True,
            na_values=["", "NA", "N/A", "NULL", "null", "None", "nan", "NaN"],
        )
    except UnicodeDecodeError as exc:
        raise CsvParseError(
            source_id=source_id,
            detail=f"UTF-8 decode error: {exc}",
        ) from exc
    except pd.errors.ParserError as exc:
        raise CsvParseError(
            source_id=source_id,
            detail=f"CSV parser error: {exc}",
        ) from exc
    except pd.errors.EmptyDataError:
        raise EmptyDataFrameError(
            source_id=source_id,
            reason="No columns were found — the CSV is empty or header-only with no data.",
        )
    except Exception as exc:
        raise CsvParseError(
            source_id=source_id,
            detail=f"Unexpected parse error: {exc}",
        ) from exc

    # Validate the resulting frame.
    if df.shape[1] == 0:
        raise EmptyDataFrameError(
            source_id=source_id,
            reason="DataFrame has zero columns.",
        )

    # Only reject all-null when there are actual data rows.
    if len(df) > 0 and df.isnull().all(axis=None):
        raise EmptyDataFrameError(
            source_id=source_id,
            reason="All cells in the DataFrame are null.",
        )

    # Ensure column names are strings (pandas may produce int column names
    # for headerless CSVs read with default settings, though dtype=str covers
    # values, not column names).
    df.columns = [str(col) for col in df.columns]

    return df
