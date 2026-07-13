"""
tests/test_identity.py — Tests for app/identity.py (Task 2).

Coverage targets:
  A. normalize_source_content — encoding, BOM, NFC, line endings
  B. _format_abbrev — all registered formats, unknown format error
  C. _evidence_type_abbrev — truncation, sanitization, empty guard
  D. canonicalize_locator — Pydantic model and dict input, key-sort determinism
  E. canonicalize_rule_parameters — sorted keys, NaN/Inf rejection
  F. generate_source_id — idempotency, ordering sensitivity, semantic isolation,
                          collision detection, digest format, short ID format
  G. generate_evidence_id — idempotency, collision detection, locator sensitivity,
                            claim key sensitivity, free-form text isolation,
                            digest format, short ID format
  H. IdentityCollisionError — attributes, message content
  I. Cross-cutting — format_abbrev values match SOURCE_ID regex middle group,
                     evidence_type_abbrev values match EVIDENCE_ID regex middle group

Decision 002 validation:
  - Same content + same category → same source_id (idempotent across runs)
  - Same content + different category → different source_id
  - Row/column/section order changes → different source_id
  - free-form 'finding' text is NOT an identity input
  - existing_digest mismatch → IdentityCollisionError
  - existing_digest match → no error
"""

from __future__ import annotations

import json
import re
import unicodedata

import pytest

from app.identity import (
    IDENTITY_ALGO_VERSION,
    IdentityCollisionError,
    _FORMAT_ABBREV,
    _evidence_type_abbrev,
    _format_abbrev,
    _sha256_hex,
    canonicalize_locator,
    canonicalize_rule_parameters,
    check_identity_collision,
    generate_evidence_id,
    generate_source_id,
    normalize_source_content,
)
from app.schemas import (
    SemanticContextCategory,
    SourceFormat,
    TabularSourceLocator,
    TextSourceLocator,
    UserContextLocator,
)

# ---------------------------------------------------------------------------
# Regex mirrors from schemas.py — used to verify ID format compliance
# ---------------------------------------------------------------------------

_SOURCE_ID_RE = re.compile(r"^src-[a-z0-9_]{1,12}-[0-9a-f]{12}$")
_EVIDENCE_ID_RE = re.compile(r"^ev-[a-z0-9_]{1,12}-[0-9a-f]{12}$")
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")


# ===========================================================================
# A. normalize_source_content
# ===========================================================================


class TestNormalizeSourceContent:
    def test_str_passthrough(self):
        assert normalize_source_content("hello") == "hello"

    def test_bytes_utf8_decoded(self):
        assert normalize_source_content(b"hello") == "hello"

    def test_bytes_utf8_bom_stripped(self):
        with_bom = b"\xef\xbb\xbfhello"
        assert normalize_source_content(with_bom) == "hello"

    def test_str_bom_stripped(self):
        assert normalize_source_content("\ufeffhello") == "hello"

    def test_crlf_normalized(self):
        assert normalize_source_content("a\r\nb\r\nc") == "a\nb\nc"

    def test_lone_cr_normalized(self):
        assert normalize_source_content("a\rb\rc") == "a\nb\nc"

    def test_mixed_line_endings_normalized(self):
        result = normalize_source_content("a\r\nb\rc\n")
        assert result == "a\nb\nc\n"

    def test_nfc_applied(self):
        # NFC: decomposed form → composed form
        decomposed = unicodedata.normalize("NFD", "caf\u00e9")  # café NFD
        composed = unicodedata.normalize("NFC", "caf\u00e9")    # café NFC
        assert normalize_source_content(decomposed) == composed

    def test_nfc_idempotent(self):
        text = "café résumé"
        nfc_text = unicodedata.normalize("NFC", text)
        assert normalize_source_content(nfc_text) == nfc_text

    def test_invalid_utf8_bytes_raises_value_error(self):
        with pytest.raises(ValueError, match="not valid UTF-8"):
            normalize_source_content(b"\xff\xfe invalid")

    def test_empty_string(self):
        assert normalize_source_content("") == ""

    def test_empty_bytes(self):
        assert normalize_source_content(b"") == ""

    def test_bom_only(self):
        assert normalize_source_content("\ufeff") == ""

    def test_bom_bytes_only(self):
        assert normalize_source_content(b"\xef\xbb\xbf") == ""

    def test_unicode_preserved(self):
        # Non-ASCII content that is already NFC should be preserved intact.
        text = "数据分析 résumé"
        result = normalize_source_content(text)
        assert result == unicodedata.normalize("NFC", text)

    def test_no_bom_in_middle_stripped(self):
        # BOM stripping only removes leading BOM, not internal occurrences.
        text = "a\ufeffb"
        result = normalize_source_content(text)
        # lstrip("\ufeff") on "a\ufeffb" → "a\ufeffb" (no leading BOM)
        assert result == "a\ufeffb"

    def test_trailing_newline_preserved(self):
        assert normalize_source_content("line1\nline2\n") == "line1\nline2\n"

    def test_whitespace_only(self):
        assert normalize_source_content("   \t  ") == "   \t  "


# ===========================================================================
# B. _format_abbrev
# ===========================================================================


class TestFormatAbbrev:
    def test_csv(self):
        assert _format_abbrev("csv") == "csv"

    def test_excel(self):
        assert _format_abbrev("excel") == "xls"

    def test_pasted_text(self):
        assert _format_abbrev("pasted_text") == "ptxt"

    def test_txt(self):
        assert _format_abbrev("txt") == "txt"

    def test_markdown(self):
        assert _format_abbrev("markdown") == "md"

    def test_form_input(self):
        assert _format_abbrev("form_input") == "form"

    def test_pdf_text_raises_value_error(self):
        # pdf_text is not an active SourceFormat in V1; it must not have a
        # registered abbreviation and must raise ValueError when passed.
        with pytest.raises(ValueError, match="No stable abbreviation"):
            _format_abbrev("pdf_text")

    def test_unknown_format_raises_value_error(self):
        with pytest.raises(ValueError, match="No stable abbreviation"):
            _format_abbrev("unknown_format")

    def test_all_registered_abbrevs_match_schema_regex(self):
        abbrev_re = re.compile(r"^[a-z0-9_]{1,12}$")
        for fmt, abbrev in _FORMAT_ABBREV.items():
            assert abbrev_re.match(abbrev), (
                f"Abbreviation {abbrev!r} for format {fmt!r} does not match "
                "the required regex [a-z0-9_]{1,12}"
            )

    def test_enum_values_covered(self):
        # Every active SourceFormat enum member must have an abbreviation.
        for member in SourceFormat:
            result = _format_abbrev(member.value)
            assert isinstance(result, str)
            assert len(result) >= 1


# ===========================================================================
# C. _evidence_type_abbrev
# ===========================================================================


class TestEvidenceTypeAbbrev:
    def test_short_key_returned_as_is(self):
        assert _evidence_type_abbrev("missing") == "missing"

    def test_exactly_12_chars(self):
        assert _evidence_type_abbrev("abcdefghijkl") == "abcdefghijkl"

    def test_longer_than_12_truncated(self):
        result = _evidence_type_abbrev("missing_value_rate")
        assert len(result) == 12
        assert result == "missing_valu"

    def test_truncation_only_no_sanitization(self):
        # _evidence_type_abbrev only truncates — it does NOT lowercase or
        # replace characters.  Callers must pass already-validated keys.
        result = _evidence_type_abbrev("abc_def_xyz_more")
        assert result == "abc_def_xyz_"

    def test_result_matches_evidence_id_abbrev_regex(self):
        abbrev_re = re.compile(r"^[a-z0-9_]{1,12}$")
        for key in [
            "missing_value_rate",
            "duplicate_row",
            "outlier_flag",
            "schema_issue",
            "a",
            "abcdefghijkl",
            "abcdefghijklmnop",
        ]:
            result = _evidence_type_abbrev(key)
            assert abbrev_re.match(result), (
                f"Abbreviation {result!r} for key {key!r} does not match regex"
            )

    def test_single_char_key(self):
        assert _evidence_type_abbrev("a") == "a"


# ===========================================================================
# D. canonicalize_locator
# ===========================================================================


class TestCanonicalizeLocator:
    def test_tabular_locator_pydantic(self):
        loc = TabularSourceLocator(columns=["revenue", "cost"])
        result = canonicalize_locator(loc)
        parsed = json.loads(result)
        assert parsed["locator_type"] == "tabular"
        assert parsed["columns"] == ["revenue", "cost"]

    def test_tabular_locator_keys_sorted(self):
        loc = TabularSourceLocator(
            columns=["a"],
            metric="mean",
            aggregation="sum",
            sheet_name="Sheet1",
        )
        result = canonicalize_locator(loc)
        keys = list(json.loads(result).keys())
        assert keys == sorted(keys)

    def test_text_locator_pydantic(self):
        loc = TextSourceLocator(line_start=0, line_end=10)
        result = canonicalize_locator(loc)
        parsed = json.loads(result)
        assert parsed["locator_type"] == "text"
        assert parsed["line_start"] == 0
        assert parsed["line_end"] == 10

    def test_user_context_locator_pydantic(self):
        loc = UserContextLocator(
            field_name="strategy_goal",
            context_category=SemanticContextCategory.strategy_profile,
        )
        result = canonicalize_locator(loc)
        parsed = json.loads(result)
        assert parsed["locator_type"] == "user_context"
        assert parsed["field_name"] == "strategy_goal"

    def test_valid_dict_validated_through_schema(self):
        # A valid SourceLocator dict is validated through TypeAdapter(SourceLocator)
        # before canonicalization.
        d = {"locator_type": "tabular", "columns": ["x"], "row_range": None}
        result = canonicalize_locator(d)
        parsed = json.loads(result)
        assert parsed["columns"] == ["x"]

    def test_arbitrary_dict_rejected(self):
        """An arbitrary dict that does not conform to any SourceLocator type is rejected."""
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            canonicalize_locator({"not": "a_locator", "random_key": 42})

    def test_dict_with_invalid_locator_type_rejected(self):
        """A dict with an unrecognized locator_type discriminator is rejected."""
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            canonicalize_locator({"locator_type": "unknown_type", "columns": ["x"]})

    def test_arbitrary_pydantic_model_rejected(self):
        """An arbitrary Pydantic BaseModel that is not a SourceLocator is rejected."""
        from pydantic import BaseModel, ValidationError

        class _ArbitraryModel(BaseModel):
            x: int = 1

        with pytest.raises(ValidationError):
            canonicalize_locator(_ArbitraryModel())

    def test_unsupported_type_raises_type_error(self):
        with pytest.raises(TypeError, match="Pydantic model or dict"):
            canonicalize_locator("not_a_model")

    def test_different_locator_types_produce_different_strings(self):
        tabular = TabularSourceLocator(columns=["a"])
        text = TextSourceLocator(line_start=0)
        assert canonicalize_locator(tabular) != canonicalize_locator(text)

    def test_same_locator_produces_same_string(self):
        loc1 = TabularSourceLocator(columns=["revenue", "cost"])
        loc2 = TabularSourceLocator(columns=["revenue", "cost"])
        assert canonicalize_locator(loc1) == canonicalize_locator(loc2)

    def test_different_columns_produce_different_strings(self):
        loc1 = TabularSourceLocator(columns=["revenue"])
        loc2 = TabularSourceLocator(columns=["cost"])
        assert canonicalize_locator(loc1) != canonicalize_locator(loc2)

    def test_column_order_preserved(self):
        # Column order is meaningful — reordering must produce a different string.
        loc1 = TabularSourceLocator(columns=["a", "b"])
        loc2 = TabularSourceLocator(columns=["b", "a"])
        assert canonicalize_locator(loc1) != canonicalize_locator(loc2)

    def test_none_fields_included(self):
        # None-valued optional fields are included in the serialized output.
        loc = TabularSourceLocator(columns=["x"])
        result = canonicalize_locator(loc)
        parsed = json.loads(result)
        assert "sheet_name" in parsed
        assert parsed["sheet_name"] is None

    def test_result_is_valid_json(self):
        loc = TabularSourceLocator(columns=["revenue"])
        result = canonicalize_locator(loc)
        # Should not raise.
        parsed = json.loads(result)
        assert isinstance(parsed, dict)


# ===========================================================================
# E. canonicalize_rule_parameters
# ===========================================================================


class TestCanonicalizeRuleParameters:
    def test_empty_dict(self):
        result = canonicalize_rule_parameters({})
        assert json.loads(result) == {}

    def test_keys_sorted(self):
        params = {"z_threshold": 3.0, "column": "revenue", "min_count": 5}
        result = canonicalize_rule_parameters(params)
        keys = list(json.loads(result).keys())
        assert keys == sorted(keys)

    def test_nested_dict_keys_sorted(self):
        params = {"thresholds": {"z": 3.0, "a": 1.0}}
        result = canonicalize_rule_parameters(params)
        nested_keys = list(json.loads(result)["thresholds"].keys())
        assert nested_keys == sorted(nested_keys)

    def test_same_params_same_string(self):
        params = {"column": "revenue", "min_count": 5}
        assert canonicalize_rule_parameters(params) == canonicalize_rule_parameters(params)

    def test_different_params_different_strings(self):
        p1 = {"column": "revenue"}
        p2 = {"column": "cost"}
        assert canonicalize_rule_parameters(p1) != canonicalize_rule_parameters(p2)

    def test_nan_raises(self):
        import math
        with pytest.raises(ValueError):
            canonicalize_rule_parameters({"threshold": float("nan")})

    def test_infinity_raises(self):
        with pytest.raises(ValueError):
            canonicalize_rule_parameters({"threshold": float("inf")})

    def test_negative_infinity_raises(self):
        with pytest.raises(ValueError):
            canonicalize_rule_parameters({"threshold": float("-inf")})

    def test_string_value_preserved(self):
        result = canonicalize_rule_parameters({"key": "value"})
        assert json.loads(result) == {"key": "value"}

    def test_int_value_preserved(self):
        result = canonicalize_rule_parameters({"count": 42})
        assert json.loads(result) == {"count": 42}

    def test_list_value_order_preserved(self):
        # Lists are order-sensitive: [1,2] ≠ [2,1]
        r1 = canonicalize_rule_parameters({"cols": [1, 2]})
        r2 = canonicalize_rule_parameters({"cols": [2, 1]})
        assert r1 != r2

    def test_result_is_valid_json(self):
        result = canonicalize_rule_parameters({"threshold": 3.0})
        parsed = json.loads(result)
        assert isinstance(parsed, dict)

    # --- Recursive type rejection ---

    def test_nested_integer_key_rejected(self):
        """A nested dict with a non-string key must be rejected."""
        with pytest.raises(ValueError):
            canonicalize_rule_parameters({"nested": {1: "x"}})

    def test_nested_tuple_rejected(self):
        """A tuple nested inside a list must be rejected."""
        with pytest.raises(ValueError):
            canonicalize_rule_parameters({"nested": (1, 2)})

    def test_nested_set_rejected(self):
        """A set nested inside a list must be rejected."""
        with pytest.raises(ValueError):
            canonicalize_rule_parameters({"items": {1, 2, 3}})

    def test_nested_bytes_rejected(self):
        """bytes nested in a list must be rejected."""
        with pytest.raises(ValueError):
            canonicalize_rule_parameters({"data": [b"binary"]})

    def test_deeply_nested_unsupported_value_rejected(self):
        """An unsupported type three levels deep must be rejected."""
        with pytest.raises(ValueError):
            canonicalize_rule_parameters({"a": {"b": {"c": (1, 2)}}})

    def test_deeply_nested_non_string_key_rejected(self):
        """A non-string key two levels deep must be rejected."""
        with pytest.raises(ValueError):
            canonicalize_rule_parameters({"outer": {42: "v"}})

    def test_deeply_nested_nan_rejected(self):
        """NaN three levels deep must be rejected."""
        import math
        with pytest.raises(ValueError):
            canonicalize_rule_parameters({"a": {"b": float("nan")}})

    def test_valid_nested_json_accepted(self):
        """A deeply nested but fully valid JSON structure is accepted."""
        params = {
            "config": {
                "threshold": 0.05,
                "labels": ["low", "high"],
                "nested": {"active": True, "count": 42, "note": None},
            }
        }
        result = canonicalize_rule_parameters(params)
        parsed = json.loads(result)
        assert parsed["config"]["nested"]["count"] == 42

    def test_non_dict_input_rejected(self):
        """canonicalize_rule_parameters requires a dict at the top level."""
        with pytest.raises(ValueError):
            canonicalize_rule_parameters([1, 2, 3])  # type: ignore[arg-type]


# ===========================================================================
# F. generate_source_id
# ===========================================================================


class TestGenerateSourceId:

    # --- Format validation ---

    def test_returns_tuple_of_two_strings(self):
        sid, digest = generate_source_id(
            source_format="csv",
            semantic_context_category="data_source",
            normalized_content="col_a,col_b\n1,2\n",
        )
        assert isinstance(sid, str)
        assert isinstance(digest, str)

    def test_source_id_matches_schema_regex(self):
        sid, _ = generate_source_id(
            source_format="csv",
            semantic_context_category="data_source",
            normalized_content="a,b\n1,2\n",
        )
        assert _SOURCE_ID_RE.match(sid), f"source_id {sid!r} does not match regex"

    def test_identity_digest_is_64_hex_chars(self):
        _, digest = generate_source_id(
            source_format="csv",
            semantic_context_category="data_source",
            normalized_content="a,b\n1,2\n",
        )
        assert _DIGEST_RE.match(digest), f"identity_digest {digest!r} is not 64 hex chars"

    def test_source_id_starts_with_src_csv(self):
        sid, _ = generate_source_id(
            source_format="csv",
            semantic_context_category="data_source",
            normalized_content="a,b\n1,2\n",
        )
        assert sid.startswith("src-csv-")

    def test_source_id_excel_prefix(self):
        sid, _ = generate_source_id(
            source_format="excel",
            semantic_context_category="data_source",
            normalized_content="sheet1_content",
        )
        assert sid.startswith("src-xls-")

    def test_source_id_pasted_text_prefix(self):
        sid, _ = generate_source_id(
            source_format="pasted_text",
            semantic_context_category="industry_context",
            normalized_content="some pasted text",
        )
        assert sid.startswith("src-ptxt-")

    def test_source_id_markdown_prefix(self):
        sid, _ = generate_source_id(
            source_format="markdown",
            semantic_context_category="internal_report",
            normalized_content="# Report\n\nContent.",
        )
        assert sid.startswith("src-md-")

    def test_source_id_txt_prefix(self):
        sid, _ = generate_source_id(
            source_format="txt",
            semantic_context_category="internal_report",
            normalized_content="Plain text content.",
        )
        assert sid.startswith("src-txt-")

    def test_source_id_form_input_prefix(self):
        sid, _ = generate_source_id(
            source_format="form_input",
            semantic_context_category="business_question",
            normalized_content="What is driving churn?",
        )
        assert sid.startswith("src-form-")

    # --- Idempotency ---

    def test_same_inputs_produce_same_id(self):
        kwargs = dict(
            source_format="csv",
            semantic_context_category="data_source",
            normalized_content="col_a,col_b\n1,2\n3,4\n",
        )
        sid1, d1 = generate_source_id(**kwargs)
        sid2, d2 = generate_source_id(**kwargs)
        assert sid1 == sid2
        assert d1 == d2

    def test_idempotent_across_multiple_calls(self):
        kwargs = dict(
            source_format="markdown",
            semantic_context_category="industry_context",
            normalized_content="# Industry Report\n\nSome findings.",
        )
        results = [generate_source_id(**kwargs) for _ in range(5)]
        assert len(set(r[0] for r in results)) == 1
        assert len(set(r[1] for r in results)) == 1

    # --- Order sensitivity ---

    def test_row_order_change_produces_different_id(self):
        """CSV row order is meaningful: reordered rows → different source_id."""
        s1, _ = generate_source_id(
            source_format="csv",
            semantic_context_category="data_source",
            normalized_content="a,b\n1,2\n3,4\n",
        )
        s2, _ = generate_source_id(
            source_format="csv",
            semantic_context_category="data_source",
            normalized_content="a,b\n3,4\n1,2\n",
        )
        assert s1 != s2

    def test_section_order_change_produces_different_id(self):
        """Markdown section order is meaningful."""
        s1, _ = generate_source_id(
            source_format="markdown",
            semantic_context_category="internal_report",
            normalized_content="# Section A\n\nContent A\n\n# Section B\n\nContent B\n",
        )
        s2, _ = generate_source_id(
            source_format="markdown",
            semantic_context_category="internal_report",
            normalized_content="# Section B\n\nContent B\n\n# Section A\n\nContent A\n",
        )
        assert s1 != s2

    # --- Semantic isolation ---

    def test_same_content_different_category_produces_different_id(self):
        """Decision 002: same text in different semantic fields → different source_id."""
        content = "Market share declined by 10%."
        s_industry, _ = generate_source_id(
            source_format="pasted_text",
            semantic_context_category="industry_context",
            normalized_content=content,
        )
        s_strategy, _ = generate_source_id(
            source_format="pasted_text",
            semantic_context_category="strategy_profile",
            normalized_content=content,
        )
        assert s_industry != s_strategy

    def test_business_question_isolated_from_data_source(self):
        content = "revenue,cost\n100,80\n"
        s_data, _ = generate_source_id(
            source_format="csv",
            semantic_context_category="data_source",
            normalized_content=content,
        )
        s_question, _ = generate_source_id(
            source_format="csv",
            semantic_context_category="business_question",
            normalized_content=content,
        )
        assert s_data != s_question

    def test_all_seven_categories_produce_distinct_ids(self):
        content = "shared content"
        categories = [c.value for c in SemanticContextCategory]
        ids = [
            generate_source_id(
                source_format="pasted_text",
                semantic_context_category=cat,
                normalized_content=content,
            )[0]
            for cat in categories
        ]
        # All seven should be distinct.
        assert len(set(ids)) == 7

    # --- Content sensitivity ---

    def test_different_content_produces_different_id(self):
        s1, _ = generate_source_id(
            source_format="csv",
            semantic_context_category="data_source",
            normalized_content="a,b\n1,2\n",
        )
        s2, _ = generate_source_id(
            source_format="csv",
            semantic_context_category="data_source",
            normalized_content="a,b\n1,3\n",
        )
        assert s1 != s2

    def test_whitespace_only_change_produces_different_id(self):
        """A source changed only by whitespace (after normalization) is a different source."""
        s1, _ = generate_source_id(
            source_format="pasted_text",
            semantic_context_category="industry_context",
            normalized_content="Market share declined.",
        )
        s2, _ = generate_source_id(
            source_format="pasted_text",
            semantic_context_category="industry_context",
            normalized_content="Market share declined.  ",  # trailing spaces
        )
        assert s1 != s2

    # --- Algo version sensitivity ---

    def test_different_algo_version_produces_different_id(self):
        kwargs = dict(
            source_format="csv",
            semantic_context_category="data_source",
            normalized_content="a,b\n1,2\n",
        )
        s1, _ = generate_source_id(**kwargs, id_algo_version="v1")
        s2, _ = generate_source_id(**kwargs, id_algo_version="v2")
        assert s1 != s2

    def test_default_algo_version_is_v1(self):
        s1, _ = generate_source_id(
            source_format="csv",
            semantic_context_category="data_source",
            normalized_content="x",
        )
        s2, _ = generate_source_id(
            source_format="csv",
            semantic_context_category="data_source",
            normalized_content="x",
            id_algo_version="v1",
        )
        assert s1 == s2

    # --- Input validation ---

    def test_unknown_format_raises_value_error(self):
        # "unsupported_format" is not a valid SourceFormat value.
        with pytest.raises(ValueError):
            generate_source_id(
                source_format="unsupported_format",
                semantic_context_category="data_source",
                normalized_content="content",
            )

    def test_invalid_semantic_category_rejected(self):
        # "not_real" is not a valid SemanticContextCategory.
        with pytest.raises(ValueError):
            generate_source_id(
                source_format="csv",
                semantic_context_category="not_real",
                normalized_content="content",
            )

    def test_padded_algo_version_rejected(self):
        with pytest.raises(ValueError, match="id_algo_version"):
            generate_source_id(
                source_format="csv",
                semantic_context_category="data_source",
                normalized_content="content",
                id_algo_version=" v1 ",
            )

    def test_pdf_text_source_format_rejected_by_generate_source_id(self):
        # pdf_text is not an active SourceFormat in V1.
        with pytest.raises(ValueError):
            generate_source_id(
                source_format="pdf_text",
                semantic_context_category="data_source",
                normalized_content="content",
            )

    def test_different_content_produces_different_ids_not_collision(self):
        # Two different content strings produce different source IDs.
        # This is not a collision — they are just different sources.
        sid_a, digest_a = generate_source_id(
            source_format="csv",
            semantic_context_category="data_source",
            normalized_content="content_a",
        )
        sid_b, digest_b = generate_source_id(
            source_format="csv",
            semantic_context_category="data_source",
            normalized_content="content_b",
        )
        assert sid_a != sid_b
        assert digest_a != digest_b
        # They have different short IDs — checking one's digest against the
        # other's registry entry does NOT constitute a collision.
        check_identity_collision(sid_a, digest_a, {sid_b: digest_b})  # no error
        check_identity_collision(sid_b, digest_b, {sid_a: digest_a})  # no error

    # --- Digest is not source_id ---

    def test_identity_digest_differs_from_source_id(self):
        sid, digest = generate_source_id(
            source_format="csv",
            semantic_context_category="data_source",
            normalized_content="a,b\n1,2\n",
        )
        assert sid != digest

    # --- Empty content ---

    def test_empty_content_produces_valid_id(self):
        sid, digest = generate_source_id(
            source_format="csv",
            semantic_context_category="data_source",
            normalized_content="",
        )
        assert _SOURCE_ID_RE.match(sid)
        assert _DIGEST_RE.match(digest)


# ===========================================================================
# G. generate_evidence_id
# ===========================================================================


class TestGenerateEvidenceId:

    def _base_locator_str(self) -> str:
        return canonicalize_locator(TabularSourceLocator(columns=["revenue"]))

    def _base_params_str(self) -> str:
        return canonicalize_rule_parameters({"threshold": 0.05})

    def test_returns_tuple_of_two_strings(self):
        eid, digest = generate_evidence_id(
            source_id="src-csv-abcdef012345",
            evidence_type_key="missing_value_rate",
            canonical_source_locator=self._base_locator_str(),
            canonical_rule_parameters=self._base_params_str(),
            normalized_claim_key="data.missing.revenue",
        )
        assert isinstance(eid, str)
        assert isinstance(digest, str)

    def test_evidence_id_matches_schema_regex(self):
        eid, _ = generate_evidence_id(
            source_id="src-csv-abcdef012345",
            evidence_type_key="missing_value_rate",
            canonical_source_locator=self._base_locator_str(),
            canonical_rule_parameters=self._base_params_str(),
            normalized_claim_key="data.missing.revenue",
        )
        assert _EVIDENCE_ID_RE.match(eid), f"evidence_id {eid!r} does not match regex"

    def test_identity_digest_is_64_hex_chars(self):
        _, digest = generate_evidence_id(
            source_id="src-csv-abcdef012345",
            evidence_type_key="missing_value_rate",
            canonical_source_locator=self._base_locator_str(),
            canonical_rule_parameters=self._base_params_str(),
            normalized_claim_key="data.missing.revenue",
        )
        assert _DIGEST_RE.match(digest)

    def test_evidence_id_starts_with_ev_prefix(self):
        eid, _ = generate_evidence_id(
            source_id="src-csv-abcdef012345",
            evidence_type_key="missing_value_rate",
            canonical_source_locator=self._base_locator_str(),
            canonical_rule_parameters=self._base_params_str(),
            normalized_claim_key="data.missing.revenue",
        )
        assert eid.startswith("ev-")

    def test_evidence_type_abbrev_in_id(self):
        eid, _ = generate_evidence_id(
            source_id="src-csv-abcdef012345",
            evidence_type_key="missing_value_rate",
            canonical_source_locator=self._base_locator_str(),
            canonical_rule_parameters=self._base_params_str(),
            normalized_claim_key="data.missing.revenue",
        )
        # "missing_value_rate"[:12] == "missing_valu"
        assert eid.startswith("ev-missing_valu-")

    def test_short_type_key_in_id(self):
        eid, _ = generate_evidence_id(
            source_id="src-csv-abcdef012345",
            evidence_type_key="outlier",
            canonical_source_locator=self._base_locator_str(),
            canonical_rule_parameters=self._base_params_str(),
            normalized_claim_key="data.outlier",
        )
        assert eid.startswith("ev-outlier-")

    # --- Idempotency ---

    def test_same_inputs_produce_same_id(self):
        kwargs = dict(
            source_id="src-csv-abcdef012345",
            evidence_type_key="duplicate_row",
            canonical_source_locator=self._base_locator_str(),
            canonical_rule_parameters=self._base_params_str(),
            normalized_claim_key="data.duplicate_rows",
        )
        eid1, d1 = generate_evidence_id(**kwargs)
        eid2, d2 = generate_evidence_id(**kwargs)
        assert eid1 == eid2
        assert d1 == d2

    # --- Sensitivity to each identity input ---

    def test_different_source_id_produces_different_evidence_id(self):
        kwargs = dict(
            evidence_type_key="missing_value_rate",
            canonical_source_locator=self._base_locator_str(),
            canonical_rule_parameters=self._base_params_str(),
            normalized_claim_key="data.missing.revenue",
        )
        eid1, _ = generate_evidence_id(source_id="src-csv-aaaaaaaaaaaa", **kwargs)
        eid2, _ = generate_evidence_id(source_id="src-csv-bbbbbbbbbbbb", **kwargs)
        assert eid1 != eid2

    def test_different_evidence_type_produces_different_id(self):
        kwargs = dict(
            source_id="src-csv-abcdef012345",
            canonical_source_locator=self._base_locator_str(),
            canonical_rule_parameters=self._base_params_str(),
            normalized_claim_key="data.missing.revenue",
        )
        eid1, _ = generate_evidence_id(evidence_type_key="missing_value_rate", **kwargs)
        eid2, _ = generate_evidence_id(evidence_type_key="duplicate_row", **kwargs)
        assert eid1 != eid2

    def test_different_locator_produces_different_id(self):
        kwargs = dict(
            source_id="src-csv-abcdef012345",
            evidence_type_key="missing_value_rate",
            canonical_rule_parameters=self._base_params_str(),
            normalized_claim_key="data.missing.revenue",
        )
        loc1 = canonicalize_locator(TabularSourceLocator(columns=["revenue"]))
        loc2 = canonicalize_locator(TabularSourceLocator(columns=["cost"]))
        eid1, _ = generate_evidence_id(canonical_source_locator=loc1, **kwargs)
        eid2, _ = generate_evidence_id(canonical_source_locator=loc2, **kwargs)
        assert eid1 != eid2

    def test_different_rule_parameters_produces_different_id(self):
        kwargs = dict(
            source_id="src-csv-abcdef012345",
            evidence_type_key="missing_value_rate",
            canonical_source_locator=self._base_locator_str(),
            normalized_claim_key="data.missing.revenue",
        )
        p1 = canonicalize_rule_parameters({"threshold": 0.05})
        p2 = canonicalize_rule_parameters({"threshold": 0.10})
        eid1, _ = generate_evidence_id(canonical_rule_parameters=p1, **kwargs)
        eid2, _ = generate_evidence_id(canonical_rule_parameters=p2, **kwargs)
        assert eid1 != eid2

    def test_different_claim_key_produces_different_id(self):
        kwargs = dict(
            source_id="src-csv-abcdef012345",
            evidence_type_key="missing_value_rate",
            canonical_source_locator=self._base_locator_str(),
            canonical_rule_parameters=self._base_params_str(),
        )
        eid1, _ = generate_evidence_id(normalized_claim_key="data.missing.revenue", **kwargs)
        eid2, _ = generate_evidence_id(normalized_claim_key="data.missing.cost", **kwargs)
        assert eid1 != eid2

    # --- Free-form text is NOT an identity input ---

    def test_free_form_finding_does_not_affect_id(self):
        """Free-form 'finding' text is not an identity input — it must not be passed."""
        # generate_evidence_id has no 'finding' parameter; this tests the
        # contract by verifying the function signature rejects unexpected kwargs.
        with pytest.raises(TypeError):
            generate_evidence_id(  # type: ignore[call-arg]
                source_id="src-csv-abcdef012345",
                evidence_type_key="missing_value_rate",
                canonical_source_locator=self._base_locator_str(),
                canonical_rule_parameters=self._base_params_str(),
                normalized_claim_key="data.missing.revenue",
                finding="Revenue column has 5% missing values.",  # must not exist
            )

    # --- Algo version sensitivity ---

    def test_different_algo_version_produces_different_id(self):
        kwargs = dict(
            source_id="src-csv-abcdef012345",
            evidence_type_key="missing_value_rate",
            canonical_source_locator=self._base_locator_str(),
            canonical_rule_parameters=self._base_params_str(),
            normalized_claim_key="data.missing.revenue",
        )
        eid1, _ = generate_evidence_id(**kwargs, id_algo_version="v1")
        eid2, _ = generate_evidence_id(**kwargs, id_algo_version="v2")
        assert eid1 != eid2

    # --- Input validation ---

    def test_invalid_source_id_rejected(self):
        # "not-valid" does not match src-[a-z0-9_]{1,12}-[0-9a-f]{12}.
        with pytest.raises(ValueError):
            generate_evidence_id(
                source_id="not-valid",
                evidence_type_key="missing_value_rate",
                canonical_source_locator=self._base_locator_str(),
                canonical_rule_parameters=self._base_params_str(),
                normalized_claim_key="data.missing.revenue",
            )

    def test_invalid_evidence_type_key_rejected(self):
        # Uppercase is not allowed in evidence_type_key.
        with pytest.raises(ValueError):
            generate_evidence_id(
                source_id="src-csv-abcdef012345",
                evidence_type_key="MISSING_VALUE",
                canonical_source_locator=self._base_locator_str(),
                canonical_rule_parameters=self._base_params_str(),
                normalized_claim_key="data.missing.revenue",
            )

    def test_invalid_normalized_claim_key_rejected(self):
        # Uppercase is not allowed in normalized_claim_key.
        with pytest.raises(ValueError):
            generate_evidence_id(
                source_id="src-csv-abcdef012345",
                evidence_type_key="missing_value_rate",
                canonical_source_locator=self._base_locator_str(),
                canonical_rule_parameters=self._base_params_str(),
                normalized_claim_key="Data.Missing",
            )

    def test_padded_algo_version_rejected(self):
        with pytest.raises(ValueError, match="id_algo_version"):
            generate_evidence_id(
                source_id="src-csv-abcdef012345",
                evidence_type_key="missing_value_rate",
                canonical_source_locator=self._base_locator_str(),
                canonical_rule_parameters=self._base_params_str(),
                normalized_claim_key="data.missing.revenue",
                id_algo_version=" v1 ",
            )

    def test_pure_function_idempotent(self):
        # generate_evidence_id is a pure function: same inputs → same outputs.
        eid, digest = generate_evidence_id(
            source_id="src-csv-abcdef012345",
            evidence_type_key="missing_value_rate",
            canonical_source_locator=self._base_locator_str(),
            canonical_rule_parameters=self._base_params_str(),
            normalized_claim_key="data.missing.revenue",
        )
        eid2, digest2 = generate_evidence_id(
            source_id="src-csv-abcdef012345",
            evidence_type_key="missing_value_rate",
            canonical_source_locator=self._base_locator_str(),
            canonical_rule_parameters=self._base_params_str(),
            normalized_claim_key="data.missing.revenue",
        )
        assert eid == eid2
        assert digest == digest2

    # --- Canonical-JSON enforcement ---

    def test_unsorted_locator_json_rejected(self):
        """Locator JSON with unsorted keys must be rejected even if parseable."""
        # canonical form has keys sorted; manually building unsorted JSON fails.
        unsorted = '{"locator_type":"tabular","row_range":null,"columns":["revenue"],"sheet_name":null,"cell_range":null,"metric":null,"aggregation":null}'
        # Verify it actually parses but is unsorted vs canonical.
        canonical = self._base_locator_str()
        assert json.loads(unsorted) == json.loads(canonical)  # same data
        assert unsorted != canonical                           # different bytes
        with pytest.raises(ValueError, match="canonical form"):
            generate_evidence_id(
                source_id="src-csv-abcdef012345",
                evidence_type_key="missing_value_rate",
                canonical_source_locator=unsorted,
                canonical_rule_parameters=self._base_params_str(),
                normalized_claim_key="data.missing.revenue",
            )

    def test_non_canonical_params_json_rejected(self):
        """Params JSON with extra whitespace must be rejected."""
        non_canonical = '{ "threshold" : 0.05 }'
        canonical = self._base_params_str()
        assert json.loads(non_canonical) == json.loads(canonical)
        assert non_canonical != canonical
        with pytest.raises(ValueError, match="canonical form"):
            generate_evidence_id(
                source_id="src-csv-abcdef012345",
                evidence_type_key="missing_value_rate",
                canonical_source_locator=self._base_locator_str(),
                canonical_rule_parameters=non_canonical,
                normalized_claim_key="data.missing.revenue",
            )

    def test_json_string_as_locator_rejected(self):
        """A bare JSON string (not a locator object) must be rejected."""
        with pytest.raises(ValueError):
            generate_evidence_id(
                source_id="src-csv-abcdef012345",
                evidence_type_key="missing_value_rate",
                canonical_source_locator='"just a string"',
                canonical_rule_parameters=self._base_params_str(),
                normalized_claim_key="data.missing.revenue",
            )

    def test_json_list_as_rule_parameters_rejected(self):
        """A JSON array where a JSON object is required must be rejected."""
        with pytest.raises(ValueError, match="JSON object"):
            generate_evidence_id(
                source_id="src-csv-abcdef012345",
                evidence_type_key="missing_value_rate",
                canonical_source_locator=self._base_locator_str(),
                canonical_rule_parameters='[1,2,3]',
                normalized_claim_key="data.missing.revenue",
            )

    def test_output_of_canonicalize_functions_is_accepted(self):
        """Output directly from canonicalize_locator() and canonicalize_rule_parameters()
        must be accepted by generate_evidence_id without error."""
        loc = canonicalize_locator(TabularSourceLocator(columns=["revenue"]))
        params = canonicalize_rule_parameters({"threshold": 0.05})
        eid, digest = generate_evidence_id(
            source_id="src-csv-abcdef012345",
            evidence_type_key="missing_value_rate",
            canonical_source_locator=loc,
            canonical_rule_parameters=params,
            normalized_claim_key="data.missing.revenue",
        )
        assert _EVIDENCE_ID_RE.match(eid)
        assert _DIGEST_RE.match(digest)

    def test_unsorted_params_json_rejected(self):
        """Params JSON with unsorted keys must be rejected."""
        unsorted_params = '{"z_key":1,"a_key":2}'
        canonical_params = canonicalize_rule_parameters({"z_key": 1, "a_key": 2})
        # Canonical form sorts keys: a_key < z_key.
        assert json.loads(unsorted_params) == json.loads(canonical_params)
        assert unsorted_params != canonical_params
        with pytest.raises(ValueError, match="canonical form"):
            generate_evidence_id(
                source_id="src-csv-abcdef012345",
                evidence_type_key="missing_value_rate",
                canonical_source_locator=self._base_locator_str(),
                canonical_rule_parameters=unsorted_params,
                normalized_claim_key="data.missing.revenue",
            )

    # --- Two findings from same source must not collide when keys differ ---

    def test_two_different_findings_same_source_different_ids(self):
        kwargs = dict(
            source_id="src-csv-abcdef012345",
            evidence_type_key="missing_value_rate",
            canonical_source_locator=self._base_locator_str(),
            canonical_rule_parameters=self._base_params_str(),
        )
        eid1, _ = generate_evidence_id(
            normalized_claim_key="data.missing.revenue", **kwargs
        )
        eid2, _ = generate_evidence_id(
            normalized_claim_key="data.missing.cost", **kwargs
        )
        assert eid1 != eid2

    # --- Evidence from two different sources stays separate ---

    def test_same_finding_different_sources_different_ids(self):
        kwargs = dict(
            evidence_type_key="missing_value_rate",
            canonical_source_locator=self._base_locator_str(),
            canonical_rule_parameters=self._base_params_str(),
            normalized_claim_key="data.missing.revenue",
        )
        eid1, _ = generate_evidence_id(source_id="src-csv-aaaaaaaaaaaa", **kwargs)
        eid2, _ = generate_evidence_id(source_id="src-csv-bbbbbbbbbbbb", **kwargs)
        assert eid1 != eid2

    # --- evidence_id != source_id ---

    def test_evidence_id_does_not_equal_source_id(self):
        src_id = "src-csv-abcdef012345"
        eid, _ = generate_evidence_id(
            source_id=src_id,
            evidence_type_key="missing_value_rate",
            canonical_source_locator=self._base_locator_str(),
            canonical_rule_parameters=self._base_params_str(),
            normalized_claim_key="data.missing.revenue",
        )
        assert eid != src_id
        assert eid.startswith("ev-")
        assert src_id.startswith("src-")


# ===========================================================================
# H. IdentityCollisionError
# ===========================================================================


class TestIdentityCollisionError:
    def test_attributes_set_correctly(self):
        err = IdentityCollisionError(
            short_id="src-csv-abcdef012345",
            existing_digest="a" * 64,
            new_digest="b" * 64,
        )
        assert err.short_id == "src-csv-abcdef012345"
        assert err.existing_digest == "a" * 64
        assert err.new_digest == "b" * 64

    def test_message_contains_short_id(self):
        err = IdentityCollisionError(
            short_id="src-csv-abcdef012345",
            existing_digest="a" * 64,
            new_digest="b" * 64,
        )
        assert "src-csv-abcdef012345" in str(err)

    def test_is_exception_subclass(self):
        assert issubclass(IdentityCollisionError, Exception)

    def test_raise_and_catch(self):
        with pytest.raises(IdentityCollisionError) as exc_info:
            raise IdentityCollisionError(
                short_id="ev-test-000000000000",
                existing_digest="c" * 64,
                new_digest="d" * 64,
            )
        assert exc_info.value.short_id == "ev-test-000000000000"

    def test_both_digests_in_message(self):
        existing = "e" * 64
        new = "f" * 64
        err = IdentityCollisionError("src-csv-000000000000", existing, new)
        msg = str(err)
        assert existing in msg
        assert new in msg


# ===========================================================================
# H.5 TestCheckIdentityCollision — targeted collision API tests
# ===========================================================================


class TestCheckIdentityCollision:
    """Tests for the new check_identity_collision() registry-aware API.

    This function replaces the incorrect 'existing_digest' parameter pattern
    where a bare digest was passed without identifying which short_id it belonged to.
    """

    def test_absent_short_id_no_error(self):
        """Short ID not in registry: no error."""
        check_identity_collision("src-csv-aabbccddee00", "a" * 64, {})

    def test_same_short_id_same_digest_no_error(self):
        """Same short ID + same digest: same identity, no error."""
        check_identity_collision(
            "src-csv-aabbccddee00",
            "a" * 64,
            {"src-csv-aabbccddee00": "a" * 64},
        )

    def test_same_short_id_different_digest_raises(self):
        """Same short ID + different digest: collision."""
        with pytest.raises(IdentityCollisionError) as exc_info:
            check_identity_collision(
                "src-csv-aabbccddee00",
                "b" * 64,
                {"src-csv-aabbccddee00": "a" * 64},
            )
        assert exc_info.value.short_id == "src-csv-aabbccddee00"
        assert exc_info.value.existing_digest == "a" * 64
        assert exc_info.value.new_digest == "b" * 64

    def test_different_short_ids_not_a_collision(self):
        """Two different short IDs with different digests are NOT a collision.

        An unrelated existing digest in the registry must not create a false
        collision when the short IDs differ.
        """
        sid_a = "src-csv-aaaaaaaaaaaa"
        sid_b = "src-csv-bbbbbbbbbbbb"
        digest_a = "a" * 64
        digest_b = "b" * 64

        # sid_b is in the registry with digest_b.
        # Checking sid_a with digest_a must not raise.
        check_identity_collision(sid_a, digest_a, {sid_b: digest_b})  # no error
        check_identity_collision(sid_b, digest_b, {sid_a: digest_a})  # no error

    def test_registry_collision_requires_same_short_id(self):
        """A collision only occurs when the same short ID maps to a different digest.

        Different short IDs with different digests (even if digests look like
        a mismatch) never produce a collision.
        """
        registry = {
            "src-csv-111111111111": "a" * 64,
            "src-csv-222222222222": "b" * 64,
        }
        # These short IDs are not in the registry at all — no collision.
        check_identity_collision("src-csv-333333333333", "c" * 64, registry)
        # These are in the registry with the correct digest — no collision.
        check_identity_collision("src-csv-111111111111", "a" * 64, registry)
        check_identity_collision("src-csv-222222222222", "b" * 64, registry)

    def test_empty_registry_never_raises(self):
        """An empty registry never produces a collision."""
        check_identity_collision("src-csv-aabbccddee00", "a" * 64, {})
        check_identity_collision("ev-missing_val-012345", "b" * 64, {})


# ===========================================================================
# I. Cross-cutting: ID format compliance across all source types
# ===========================================================================


class TestCrossCuttingFormatCompliance:
    """Verify that every source format produces a valid source_id."""

    @pytest.mark.parametrize("fmt", [m.value for m in SourceFormat])
    def test_all_source_formats_produce_valid_source_id(self, fmt):
        sid, digest = generate_source_id(
            source_format=fmt,
            semantic_context_category="data_source",
            normalized_content="test content",
        )
        assert _SOURCE_ID_RE.match(sid), f"source_id {sid!r} invalid for format {fmt!r}"
        assert _DIGEST_RE.match(digest), f"digest {digest!r} invalid for format {fmt!r}"

    @pytest.mark.parametrize("cat", [m.value for m in SemanticContextCategory])
    def test_all_semantic_categories_produce_valid_source_id(self, cat):
        sid, digest = generate_source_id(
            source_format="pasted_text",
            semantic_context_category=cat,
            normalized_content="test content",
        )
        assert _SOURCE_ID_RE.match(sid), f"source_id {sid!r} invalid for category {cat!r}"
        assert _DIGEST_RE.match(digest), f"digest {digest!r} invalid for category {cat!r}"

    @pytest.mark.parametrize("evidence_type_key", [
        "missing_value_rate",
        "duplicate_row",
        "outlier_flag",
        "schema_issue",
        "a",
        "abcdefghijkl",
        "abcdefghijklmnopqrstuvwxyz",
        "mixed_type_column",
        "constant_column",
        "high_cardinality",
    ])
    def test_all_evidence_type_keys_produce_valid_evidence_id(self, evidence_type_key):
        eid, digest = generate_evidence_id(
            source_id="src-csv-abcdef012345",
            evidence_type_key=evidence_type_key,
            canonical_source_locator=canonicalize_locator(
                TabularSourceLocator(columns=["col"])
            ),
            canonical_rule_parameters=canonicalize_rule_parameters({}),
            normalized_claim_key="data.test",
        )
        assert _EVIDENCE_ID_RE.match(eid), (
            f"evidence_id {eid!r} invalid for type_key {evidence_type_key!r}"
        )
        assert _DIGEST_RE.match(digest)

    def test_identity_algo_version_constant_is_v1(self):
        assert IDENTITY_ALGO_VERSION == "v1"

    def test_sha256_hex_returns_64_chars(self):
        result = _sha256_hex("test input")
        assert len(result) == 64
        assert re.match(r"^[0-9a-f]{64}$", result)

    def test_sha256_hex_deterministic(self):
        assert _sha256_hex("hello") == _sha256_hex("hello")

    def test_sha256_hex_different_inputs(self):
        assert _sha256_hex("hello") != _sha256_hex("world")


# ===========================================================================
# J. Golden identity vectors — frozen v1 byte format
# ===========================================================================


class TestGoldenIdentityVectors:
    """Fixed, independently computed test vectors that freeze the v1 identity format.

    These values are hardcoded literals.  They must NOT be computed by calling
    generate_source_id, generate_evidence_id, or _sha256_hex at import time.

    Any change to the identity byte format (separator, normalization, JSON
    encoding, key ordering) will break these tests — which is exactly the
    intended signal.
    """

    # -----------------------------------------------------------------------
    # Source vector
    # -----------------------------------------------------------------------

    _SRC_FORMAT = "csv"
    _SRC_CATEGORY = "data_source"
    _SRC_CONTENT = "a,b\n1,2\n"
    _SRC_ALGO = "v1"

    _EXPECTED_SOURCE_ID = "src-csv-de5a97ee1b6f"
    _EXPECTED_SRC_DIGEST = (
        "de5a97ee1b6fba4c36d28889fdb30cf136701a2b457d59d1c33c4be30f15623c"
    )

    def test_source_id_golden(self):
        """generate_source_id produces the exact expected source_id for the frozen vector."""
        sid, _ = generate_source_id(
            source_format=self._SRC_FORMAT,
            semantic_context_category=self._SRC_CATEGORY,
            normalized_content=self._SRC_CONTENT,
            id_algo_version=self._SRC_ALGO,
        )
        assert sid == self._EXPECTED_SOURCE_ID, (
            f"source_id changed from frozen value.  "
            f"Got {sid!r}, expected {self._EXPECTED_SOURCE_ID!r}.  "
            "The v1 identity byte format must not be modified."
        )

    def test_source_digest_golden(self):
        """generate_source_id produces the exact expected identity_digest."""
        _, digest = generate_source_id(
            source_format=self._SRC_FORMAT,
            semantic_context_category=self._SRC_CATEGORY,
            normalized_content=self._SRC_CONTENT,
            id_algo_version=self._SRC_ALGO,
        )
        assert digest == self._EXPECTED_SRC_DIGEST, (
            f"identity_digest changed from frozen value.  "
            f"Got {digest!r}, expected {self._EXPECTED_SRC_DIGEST!r}.  "
            "The v1 identity byte format must not be modified."
        )

    # -----------------------------------------------------------------------
    # Evidence vector
    # -----------------------------------------------------------------------

    _EV_SOURCE_ID = "src-csv-de5a97ee1b6f"
    _EV_TYPE_KEY = "missing_value_rate"
    _EV_CLAIM_KEY = "data.missing.revenue"
    _EV_ALGO = "v1"

    _EXPECTED_EVIDENCE_ID = "ev-missing_valu-59cdfb4bad67"
    _EXPECTED_EV_DIGEST = (
        "59cdfb4bad67d69966bcb90936b52e4315aedc0989753f8a894d9a35fc6517cc"
    )

    def _golden_locator(self) -> str:
        return canonicalize_locator(TabularSourceLocator(columns=["revenue"]))

    def _golden_params(self) -> str:
        return canonicalize_rule_parameters({"threshold": 0.05})

    def test_evidence_id_golden(self):
        """generate_evidence_id produces the exact expected evidence_id for the frozen vector."""
        eid, _ = generate_evidence_id(
            source_id=self._EV_SOURCE_ID,
            evidence_type_key=self._EV_TYPE_KEY,
            canonical_source_locator=self._golden_locator(),
            canonical_rule_parameters=self._golden_params(),
            normalized_claim_key=self._EV_CLAIM_KEY,
            id_algo_version=self._EV_ALGO,
        )
        assert eid == self._EXPECTED_EVIDENCE_ID, (
            f"evidence_id changed from frozen value.  "
            f"Got {eid!r}, expected {self._EXPECTED_EVIDENCE_ID!r}.  "
            "The v1 identity byte format must not be modified."
        )

    def test_evidence_digest_golden(self):
        """generate_evidence_id produces the exact expected identity_digest."""
        _, digest = generate_evidence_id(
            source_id=self._EV_SOURCE_ID,
            evidence_type_key=self._EV_TYPE_KEY,
            canonical_source_locator=self._golden_locator(),
            canonical_rule_parameters=self._golden_params(),
            normalized_claim_key=self._EV_CLAIM_KEY,
            id_algo_version=self._EV_ALGO,
        )
        assert digest == self._EXPECTED_EV_DIGEST, (
            f"identity_digest changed from frozen value.  "
            f"Got {digest!r}, expected {self._EXPECTED_EV_DIGEST!r}.  "
            "The v1 identity byte format must not be modified."
        )

    def test_both_golden_values_are_hardcoded_literals(self):
        """Verify the expected values are literal strings, not computed at runtime.

        This test documents the contract: expected values in this class must
        be string literals, never computed from the identity functions themselves.
        """
        assert isinstance(self._EXPECTED_SOURCE_ID, str)
        assert isinstance(self._EXPECTED_SRC_DIGEST, str)
        assert isinstance(self._EXPECTED_EVIDENCE_ID, str)
        assert isinstance(self._EXPECTED_EV_DIGEST, str)
        # Check they match the required format patterns.
        assert _SOURCE_ID_RE.match(self._EXPECTED_SOURCE_ID)
        assert _DIGEST_RE.match(self._EXPECTED_SRC_DIGEST)
        assert _EVIDENCE_ID_RE.match(self._EXPECTED_EVIDENCE_ID)
        assert _DIGEST_RE.match(self._EXPECTED_EV_DIGEST)
