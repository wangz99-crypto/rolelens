"""
app/data_health.py — RoleLens deterministic data-health analysis (Task 4).

Responsibilities:
  - Accept a SourceManifestEntry and a validated pandas DataFrame.
  - Compute deterministic health metrics.
  - Emit a DataHealthSummary and a list[HealthFindingCandidate].
  - NEVER mint evidence_id values — that is exclusively evidence_builder.py.

Approved normalized_claim_key vocabulary (Decision 002, Task 4):
  data.row_count                — total row count observation
  data.duplicate_rows           — duplicate row detection
  data.missing.{column}         — missing-value rate for a specific column
  data.mixed_types.{column}     — mixed types detected in a column
  data.constant_column.{column} — column has only one distinct non-null value
  data.schema.unnamed_columns   — column names look auto-generated (Unnamed: N)
  data.schema.all_null_column.{column} — an entire column is null

  Compound keys use dot-notation: data.{category}[.{detail}]
  The {column} suffix is the column name, lowercased and with non-alpha-numeric
  chars replaced by '_', then truncated to 64 chars.  If two columns produce
  the same sanitized suffix, the full-column-name hash is appended.

Architecture invariants:
  - HealthFindingCandidate has no evidence_id field (enforced by schema).
  - This module does not call identity.generate_evidence_id().
  - DataHealthSummary is emitted alongside the candidate list; it summarizes
    metrics but does not itself carry evidence_id.
  - An all-null DataFrame raises EmptyDataFrameError (from data_parser.py)
    before reaching this module — but a DataFrame with some null columns is
    valid input here.
  - Empty candidate list is valid output (no findings from a perfectly clean
    dataset is a legitimate result).
"""

from __future__ import annotations

import re
from typing import Any

import pandas as pd

from app.schemas import (
    DataHealthSummary,
    HealthFindingCandidate,
    SemanticContextCategory,
    SourceFormat,
    SourceManifestEntry,
    TabularSourceLocator,
)

# ---------------------------------------------------------------------------
# Constants: approved evidence_type_key vocabulary
# ---------------------------------------------------------------------------

#: Approved evidence_type_key strings for data-health findings.
#: These map directly to rule names and are stable identity inputs.
ET_DUPLICATE_ROW = "duplicate_row"
ET_MISSING_VALUE = "missing_value_rate"
ET_MIXED_TYPES = "mixed_type_column"
ET_CONSTANT_COLUMN = "constant_column"
ET_SCHEMA_UNNAMED = "unnamed_column"
ET_ALL_NULL_COLUMN = "all_null_column"

#: Threshold above which a missing-value rate is flagged as a finding.
_MISSING_RATE_THRESHOLD = 0.0   # flag any column with at least one missing value

#: Minimum number of duplicate rows to emit a finding.
_DUPLICATE_ROW_MIN = 1

#: Regex for sanitizing column names in claim keys.
_CLAIM_KEY_SANITIZE_RE = re.compile(r"[^a-z0-9]")

#: Maximum length for the column-name segment of a claim key.
_CLAIM_COL_MAX_LEN = 64

#: Roles relevant to data-health findings.
_DATA_HEALTH_ROLES = ["data_analyst", "data_engineer"]


# ---------------------------------------------------------------------------
# Column name → claim key suffix helper
# ---------------------------------------------------------------------------


def _col_to_claim_suffix(col_name: str) -> str:
    """Convert a column name to a safe, lowercase, dot-path segment.

    Steps:
      1. Lowercase.
      2. Replace non-alphanumeric characters with '_'.
      3. Strip leading/trailing underscores.
      4. Truncate to _CLAIM_COL_MAX_LEN characters.
      5. If the result is empty (e.g. all-special-char column name), fall back
         to 'col'.

    The result is used as the trailing segment in a dot-notation claim key.
    It does NOT guarantee global uniqueness across all column names — the
    caller is responsible for detecting and handling duplicate suffixes.

    Args:
        col_name: The original column name string.

    Returns:
        Safe lowercase segment string (at least 1 character).
    """
    lowered = col_name.lower()
    sanitized = _CLAIM_KEY_SANITIZE_RE.sub("_", lowered)
    stripped = sanitized.strip("_")
    truncated = stripped[:_CLAIM_COL_MAX_LEN] if stripped else "col"
    # Ensure it starts with a letter (claim key segments must match [a-z][a-z0-9_]*)
    if truncated and not truncated[0].isalpha():
        truncated = "col_" + truncated
    return truncated or "col"


def _build_missing_claim_key(col_name: str) -> str:
    return f"data.missing.{_col_to_claim_suffix(col_name)}"


def _build_mixed_type_claim_key(col_name: str) -> str:
    return f"data.mixed_types.{_col_to_claim_suffix(col_name)}"


def _build_constant_claim_key(col_name: str) -> str:
    return f"data.constant_column.{_col_to_claim_suffix(col_name)}"


def _build_all_null_claim_key(col_name: str) -> str:
    return f"data.schema.all_null_column.{_col_to_claim_suffix(col_name)}"


# ---------------------------------------------------------------------------
# Metric computation helpers
# ---------------------------------------------------------------------------


def _compute_missing_value_rates(df: pd.DataFrame) -> dict[str, float]:
    """Compute per-column fraction of null values.

    Returns a dict mapping column name → float in [0.0, 1.0].
    Columns with zero missing values are included with rate 0.0.
    """
    if len(df) == 0:
        return {col: 0.0 for col in df.columns}
    rates: dict[str, float] = {}
    for col in df.columns:
        null_count = int(df[col].isna().sum())
        rates[col] = round(null_count / len(df), 6)
    return rates


def _detect_duplicate_rows(df: pd.DataFrame) -> int:
    """Count the number of fully duplicated rows (all columns identical)."""
    if len(df) == 0:
        return 0
    return int(df.duplicated(keep="first").sum())


def _detect_mixed_type_columns(df: pd.DataFrame) -> list[str]:
    """Return column names where non-null values appear to have mixed Python types.

    Since data_parser.py reads all columns as str (dtype=str), every value is
    a string or NaN.  This check looks for columns that appear to contain a
    mix of numeric-looking and non-numeric-looking values, which is a practical
    proxy for mixed types in business data.

    Returns list of column names with detected mixed representation.
    """
    mixed: list[str] = []
    for col in df.columns:
        non_null = df[col].dropna()
        if len(non_null) == 0:
            continue
        # Attempt numeric parse on each value.
        numeric_count = 0
        for v in non_null:
            try:
                float(v)
                numeric_count += 1
            except (ValueError, TypeError):
                pass
        total = len(non_null)
        if 0 < numeric_count < total:
            mixed.append(col)
    return mixed


def _detect_constant_columns(df: pd.DataFrame) -> list[str]:
    """Return column names where all non-null values are identical."""
    constant: list[str] = []
    for col in df.columns:
        non_null = df[col].dropna()
        if len(non_null) > 0 and non_null.nunique() == 1:
            constant.append(col)
    return constant


def _detect_schema_issues(df: pd.DataFrame) -> list[str]:
    """Detect structural schema issues: unnamed columns."""
    issues: list[str] = []
    for col in df.columns:
        if re.match(r"^Unnamed:\s*\d+", str(col)):
            issues.append(f"unnamed_column: {col!r}")
    return issues


def _detect_all_null_columns(df: pd.DataFrame) -> list[str]:
    """Return column names where every value is null."""
    return [col for col in df.columns if df[col].isna().all()]


# ---------------------------------------------------------------------------
# HealthFindingCandidate factory helpers
# ---------------------------------------------------------------------------


def _make_candidate(
    *,
    source_id: str,
    source_format: SourceFormat,
    columns: list[str],
    evidence_type: str,
    rule_parameters: dict[str, Any],
    normalized_claim_key: str,
    finding: str,
    supporting_evidence: str,
    confidence: str,
    limitations: list[str],
    row_range: tuple[int, int] | None = None,
    metric: str | None = None,
    aggregation: str | None = None,
) -> HealthFindingCandidate:
    """Build a HealthFindingCandidate for a single data-health rule finding."""
    locator = TabularSourceLocator(
        columns=columns,
        row_range=row_range,
        metric=metric,
        aggregation=aggregation,
    )
    return HealthFindingCandidate(
        source_id=source_id,
        source_format=source_format,
        source_locator=locator,
        evidence_type=evidence_type,
        canonical_rule_parameters=rule_parameters,
        normalized_claim_key=normalized_claim_key,
        finding=finding,
        supporting_evidence=supporting_evidence,
        confidence=confidence,
        limitations=limitations,
        relevant_roles=_DATA_HEALTH_ROLES,
        decision_relevance=(
            "Data quality directly affects the reliability of all downstream "
            "role views, risk assessments, and decision recommendations."
        ),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def analyze_data_health(
    df: pd.DataFrame,
    manifest_entry: SourceManifestEntry,
) -> tuple[DataHealthSummary, list[HealthFindingCandidate]]:
    """Compute deterministic data-health metrics and produce finding candidates.

    This function is the sole producer of HealthFindingCandidate objects for
    tabular sources.  It does NOT mint evidence_id values.

    Args:
        df:              Validated pandas DataFrame from data_parser.parse_csv().
        manifest_entry:  SourceManifestEntry for the originating source.

    Returns:
        (DataHealthSummary, list[HealthFindingCandidate])

    The list may be empty if no findings are detected.  An empty list is valid
    output and does not indicate a pipeline failure.

    Raises:
        ValueError: If df has no columns (should have been caught in
                    data_parser.parse_csv, but defensively re-checked here).
    """
    if df.shape[1] == 0:
        raise ValueError(
            f"analyze_data_health received a zero-column DataFrame for "
            f"source_id={manifest_entry.source_id!r}.  "
            "This should have been caught by data_parser.parse_csv."
        )

    source_id = manifest_entry.source_id
    source_format = manifest_entry.source_format

    # --- Compute metrics ---
    row_count = len(df)
    col_count = df.shape[1]
    dup_count = _detect_duplicate_rows(df)
    missing_rates = _compute_missing_value_rates(df)
    mixed_type_cols = _detect_mixed_type_columns(df)
    constant_cols = _detect_constant_columns(df)
    schema_issues = _detect_schema_issues(df)
    all_null_cols = _detect_all_null_columns(df)

    # --- Build DataHealthSummary ---
    summary = DataHealthSummary(
        source_id=source_id,
        row_count=row_count,
        column_count=col_count,
        duplicate_row_count=dup_count,
        missing_value_rates=missing_rates,
        columns_with_mixed_types=mixed_type_cols,
        constant_columns=constant_cols,
        schema_issues=schema_issues,
    )

    candidates: list[HealthFindingCandidate] = []

    # --- Finding: duplicate rows ---
    if dup_count >= _DUPLICATE_ROW_MIN:
        dup_pct = round(dup_count / row_count * 100, 1) if row_count > 0 else 0.0
        candidates.append(_make_candidate(
            source_id=source_id,
            source_format=source_format,
            columns=list(df.columns),
            evidence_type=ET_DUPLICATE_ROW,
            rule_parameters={
                "duplicate_row_count": dup_count,
                "row_count": row_count,
                "threshold_min": _DUPLICATE_ROW_MIN,
            },
            normalized_claim_key="data.duplicate_rows",
            finding=(
                f"{dup_count} duplicate row(s) detected out of {row_count} total "
                f"({dup_pct}% of dataset)."
            ),
            supporting_evidence=(
                f"Full-row deduplication check identified {dup_count} row(s) "
                "that are identical to an earlier row in the dataset."
            ),
            confidence="high",
            limitations=[
                "Duplicate detection uses exact string matching after all columns "
                "are read as str.  Semantic near-duplicates are not detected.",
                "Row order is preserved; the first occurrence is retained.",
            ],
            metric="duplicate_row_count",
            aggregation="count",
        ))

    # --- Findings: missing values (one per column above threshold) ---
    for col, rate in missing_rates.items():
        if rate > _MISSING_RATE_THRESHOLD:
            null_count = round(rate * row_count)
            candidates.append(_make_candidate(
                source_id=source_id,
                source_format=source_format,
                columns=[col],
                evidence_type=ET_MISSING_VALUE,
                rule_parameters={
                    "column": col,
                    "missing_count": null_count,
                    "row_count": row_count,
                    "missing_rate": rate,
                    "threshold": _MISSING_RATE_THRESHOLD,
                },
                normalized_claim_key=_build_missing_claim_key(col),
                finding=(
                    f"Column '{col}' has {null_count} missing value(s) "
                    f"({rate:.1%} of rows)."
                ),
                supporting_evidence=(
                    f"pandas null detection found {null_count} null cells "
                    f"in column '{col}' out of {row_count} rows."
                ),
                confidence="high",
                limitations=[
                    "Missing-value detection treats empty string, 'NA', 'N/A', "
                    "'NULL', 'null', 'None', 'nan', 'NaN' as null values.",
                    "Domain-specific missing-value codes (e.g. -999) are not detected.",
                ],
                metric="missing_rate",
                aggregation="mean",
            ))

    # --- Findings: mixed types ---
    for col in mixed_type_cols:
        candidates.append(_make_candidate(
            source_id=source_id,
            source_format=source_format,
            columns=[col],
            evidence_type=ET_MIXED_TYPES,
            rule_parameters={"column": col},
            normalized_claim_key=_build_mixed_type_claim_key(col),
            finding=(
                f"Column '{col}' contains a mix of numeric-looking and "
                "non-numeric values."
            ),
            supporting_evidence=(
                f"Value-level numeric-parse check on column '{col}' found both "
                "parseable and non-parseable values among non-null entries."
            ),
            confidence="medium",
            limitations=[
                "Mixed-type detection uses float()-parseable values as a proxy.  "
                "It does not distinguish int from float.",
                "Deliberately heterogeneous columns (e.g. codes like 'N/A' alongside "
                "numbers) may be incorrectly flagged.",
            ],
            metric="mixed_type_fraction",
        ))

    # --- Findings: constant columns ---
    for col in constant_cols:
        candidates.append(_make_candidate(
            source_id=source_id,
            source_format=source_format,
            columns=[col],
            evidence_type=ET_CONSTANT_COLUMN,
            rule_parameters={"column": col},
            normalized_claim_key=_build_constant_claim_key(col),
            finding=f"Column '{col}' has only one distinct non-null value.",
            supporting_evidence=(
                f"nunique() on non-null values in column '{col}' returned 1."
            ),
            confidence="high",
            limitations=[
                "Constant-column detection ignores null values.  "
                "A column that is partially null and has one unique non-null "
                "value is flagged.",
                "A column that is entirely null is not flagged here — it is "
                "separately flagged as all_null_column.",
            ],
            metric="unique_value_count",
        ))

    # --- Findings: all-null columns (skip when zero rows — vacuously all-null) ---
    for col in (all_null_cols if row_count > 0 else []):
        candidates.append(_make_candidate(
            source_id=source_id,
            source_format=source_format,
            columns=[col],
            evidence_type=ET_ALL_NULL_COLUMN,
            rule_parameters={"column": col, "row_count": row_count},
            normalized_claim_key=_build_all_null_claim_key(col),
            finding=f"Column '{col}' contains no non-null values ({row_count} rows).",
            supporting_evidence=(
                f"pandas isna().all() returned True for column '{col}'."
            ),
            confidence="high",
            limitations=[
                "All-null detection treats empty string as null (consistent with "
                "data_parser.py na_values settings).",
            ],
            metric="null_count",
        ))

    # --- Findings: unnamed columns ---
    if schema_issues:
        unnamed_cols = [
            col for col in df.columns
            if re.match(r"^Unnamed:\s*\d+", str(col))
        ]
        if unnamed_cols:
            candidates.append(_make_candidate(
                source_id=source_id,
                source_format=source_format,
                columns=unnamed_cols,
                evidence_type=ET_SCHEMA_UNNAMED,
                rule_parameters={"unnamed_columns": unnamed_cols},
                normalized_claim_key="data.schema.unnamed_columns",
                finding=(
                    f"{len(unnamed_cols)} column(s) have auto-generated names "
                    f"(Unnamed: N): {unnamed_cols}."
                ),
                supporting_evidence=(
                    "pandas auto-generated column names matching 'Unnamed: N' "
                    "were detected, suggesting the CSV is missing a header row."
                ),
                confidence="high",
                limitations=[
                    "This check only detects pandas-style 'Unnamed: N' patterns.  "
                    "Other auto-generated naming conventions are not detected.",
                ],
            ))

    return summary, candidates
