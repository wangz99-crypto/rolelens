"""
tests/test_text_parser.py — Tests for app/text_parser.py (Task 3).

Coverage targets:
  A. parse_pasted_text — happy paths, idempotency, format acceptance,
                         category isolation, scope resolution, collision detection,
                         unsupported format rejection, empty content,
                         bytes input, BOM stripping
  B. _resolve_source_scope — all categories
  C. utils.utc_now and utils.to_json_str via text_parser integration
  D. Created_at defaulting and preservation
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

import pytest

from app.identity import IdentityCollisionError
from app.schemas import (
    SemanticContextCategory,
    SourceFormat,
    SourceManifestEntry,
    SourceScope,
)
from app.text_parser import _resolve_source_scope, parse_pasted_text

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SOURCE_ID_RE = re.compile(r"^src-[a-z0-9_]{1,12}-[0-9a-f]{12}$")
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")

_FIXED_DT = datetime(2025, 6, 1, 8, 0, 0, tzinfo=timezone.utc)
_SAMPLE_TEXT = "Global cloud market grew 22% in 2024. Enterprise adoption is highest in APAC."
_SAMPLE_STRATEGY = "Priority: expand into SMB segment in APAC with a lower-cost product tier."


# ===========================================================================
# A. parse_pasted_text
# ===========================================================================


class TestParsePastedText:

    # --- Basic structure ---

    def test_returns_source_manifest_entry(self):
        result = parse_pasted_text(
            _SAMPLE_TEXT,
            semantic_context_category=SemanticContextCategory.industry_context,
            created_at=_FIXED_DT,
        )
        assert isinstance(result, SourceManifestEntry)

    def test_source_id_format(self):
        result = parse_pasted_text(
            _SAMPLE_TEXT,
            semantic_context_category=SemanticContextCategory.industry_context,
            created_at=_FIXED_DT,
        )
        assert _SOURCE_ID_RE.match(result.source_id)

    def test_source_id_starts_with_src_ptxt(self):
        result = parse_pasted_text(
            _SAMPLE_TEXT,
            semantic_context_category=SemanticContextCategory.industry_context,
            created_at=_FIXED_DT,
        )
        assert result.source_id.startswith("src-ptxt-")

    def test_identity_digest_64_hex(self):
        result = parse_pasted_text(
            _SAMPLE_TEXT,
            semantic_context_category=SemanticContextCategory.industry_context,
            created_at=_FIXED_DT,
        )
        assert _DIGEST_RE.match(result.identity_digest)

    def test_source_format_defaults_to_pasted_text(self):
        result = parse_pasted_text(
            _SAMPLE_TEXT,
            semantic_context_category=SemanticContextCategory.industry_context,
            created_at=_FIXED_DT,
        )
        assert result.source_format == SourceFormat.pasted_text

    def test_filename_is_none(self):
        result = parse_pasted_text(
            _SAMPLE_TEXT,
            semantic_context_category=SemanticContextCategory.industry_context,
            created_at=_FIXED_DT,
        )
        assert result.filename is None

    def test_upload_event_id_is_none(self):
        result = parse_pasted_text(
            _SAMPLE_TEXT,
            semantic_context_category=SemanticContextCategory.industry_context,
            created_at=_FIXED_DT,
        )
        assert result.upload_event_id is None

    # --- Format variants ---

    def test_txt_format_accepted(self):
        result = parse_pasted_text(
            "Plain text report content.",
            semantic_context_category=SemanticContextCategory.internal_report,
            source_format=SourceFormat.txt,
            created_at=_FIXED_DT,
        )
        assert result.source_format == SourceFormat.txt
        assert result.source_id.startswith("src-txt-")

    def test_markdown_format_accepted(self):
        result = parse_pasted_text(
            "# Report\n\nContent goes here.",
            semantic_context_category=SemanticContextCategory.internal_report,
            source_format=SourceFormat.markdown,
            created_at=_FIXED_DT,
        )
        assert result.source_format == SourceFormat.markdown
        assert result.source_id.startswith("src-md-")

    def test_csv_format_rejected(self):
        with pytest.raises(ValueError, match="does not accept"):
            parse_pasted_text(
                "col_a,col_b\n1,2\n",
                semantic_context_category=SemanticContextCategory.data_source,
                source_format=SourceFormat.csv,
                created_at=_FIXED_DT,
            )

    def test_excel_format_rejected(self):
        with pytest.raises(ValueError, match="does not accept"):
            parse_pasted_text(
                b"fake excel",
                semantic_context_category=SemanticContextCategory.data_source,
                source_format=SourceFormat.excel,
                created_at=_FIXED_DT,
            )

    def test_form_input_format_rejected(self):
        with pytest.raises(ValueError, match="does not accept"):
            parse_pasted_text(
                "What is driving churn?",
                semantic_context_category=SemanticContextCategory.business_question,
                source_format=SourceFormat.form_input,
                created_at=_FIXED_DT,
            )

    # --- Idempotency ---

    def test_same_text_same_category_idempotent(self):
        kwargs = dict(
            semantic_context_category=SemanticContextCategory.industry_context,
            created_at=_FIXED_DT,
        )
        r1 = parse_pasted_text(_SAMPLE_TEXT, **kwargs)
        r2 = parse_pasted_text(_SAMPLE_TEXT, **kwargs)
        assert r1.source_id == r2.source_id
        assert r1.identity_digest == r2.identity_digest

    def test_idempotent_five_calls(self):
        kwargs = dict(
            semantic_context_category=SemanticContextCategory.strategy_profile,
            created_at=_FIXED_DT,
        )
        ids = {parse_pasted_text(_SAMPLE_STRATEGY, **kwargs).source_id for _ in range(5)}
        assert len(ids) == 1

    # --- Semantic category isolation ---

    def test_same_text_different_category_different_source_id(self):
        """Decision 002: same text in different semantic fields → different source_id."""
        r_industry = parse_pasted_text(
            _SAMPLE_TEXT,
            semantic_context_category=SemanticContextCategory.industry_context,
            created_at=_FIXED_DT,
        )
        r_strategy = parse_pasted_text(
            _SAMPLE_TEXT,
            semantic_context_category=SemanticContextCategory.strategy_profile,
            created_at=_FIXED_DT,
        )
        assert r_industry.source_id != r_strategy.source_id

    def test_all_text_categories_produce_distinct_ids(self):
        categories = [c.value for c in SemanticContextCategory]
        ids = [
            parse_pasted_text(
                "shared content for isolation test",
                semantic_context_category=SemanticContextCategory(cat),
                created_at=_FIXED_DT,
            ).source_id
            for cat in categories
        ]
        assert len(set(ids)) == len(categories)

    # --- Source scope ---

    def test_industry_context_scope_is_external(self):
        result = parse_pasted_text(
            _SAMPLE_TEXT,
            semantic_context_category=SemanticContextCategory.industry_context,
            created_at=_FIXED_DT,
        )
        assert result.source_scope == SourceScope.external_context

    def test_strategy_profile_scope_is_user_assertion(self):
        result = parse_pasted_text(
            _SAMPLE_STRATEGY,
            semantic_context_category=SemanticContextCategory.strategy_profile,
            created_at=_FIXED_DT,
        )
        assert result.source_scope == SourceScope.user_assertion

    def test_business_question_scope_is_decision_context(self):
        result = parse_pasted_text(
            "What is driving churn?",
            semantic_context_category=SemanticContextCategory.business_question,
            created_at=_FIXED_DT,
        )
        assert result.source_scope == SourceScope.decision_context

    def test_decision_goal_scope_is_decision_context(self):
        result = parse_pasted_text(
            "Reduce churn to under 15% in Q3.",
            semantic_context_category=SemanticContextCategory.decision_goal,
            created_at=_FIXED_DT,
        )
        assert result.source_scope == SourceScope.decision_context

    def test_user_assumption_scope_is_user_assertion(self):
        result = parse_pasted_text(
            "We assume churn is driven by pricing.",
            semantic_context_category=SemanticContextCategory.user_assumption,
            created_at=_FIXED_DT,
        )
        assert result.source_scope == SourceScope.user_assertion

    def test_internal_report_scope_defaults_to_internal_observation(self):
        result = parse_pasted_text(
            "Q3 performance review text.",
            semantic_context_category=SemanticContextCategory.internal_report,
            created_at=_FIXED_DT,
        )
        assert result.source_scope == SourceScope.internal_observation

    # --- Bytes input ---

    def test_bytes_input_accepted(self):
        raw = _SAMPLE_TEXT.encode("utf-8")
        result = parse_pasted_text(
            raw,
            semantic_context_category=SemanticContextCategory.industry_context,
            created_at=_FIXED_DT,
        )
        assert isinstance(result, SourceManifestEntry)

    def test_bytes_and_str_produce_same_id(self):
        text_str = _SAMPLE_TEXT
        text_bytes = _SAMPLE_TEXT.encode("utf-8")
        r1 = parse_pasted_text(text_str, semantic_context_category=SemanticContextCategory.industry_context, created_at=_FIXED_DT)
        r2 = parse_pasted_text(text_bytes, semantic_context_category=SemanticContextCategory.industry_context, created_at=_FIXED_DT)
        assert r1.source_id == r2.source_id

    def test_utf8_bom_bytes_stripped(self):
        with_bom = b"\xef\xbb\xbf" + _SAMPLE_TEXT.encode("utf-8")
        without_bom = _SAMPLE_TEXT.encode("utf-8")
        r1 = parse_pasted_text(with_bom, semantic_context_category=SemanticContextCategory.industry_context, created_at=_FIXED_DT)
        r2 = parse_pasted_text(without_bom, semantic_context_category=SemanticContextCategory.industry_context, created_at=_FIXED_DT)
        assert r1.source_id == r2.source_id

    # --- Collision detection via identity_registry ---

    def test_no_registry_no_collision_check(self):
        """identity_registry=None (default): no collision check, always succeeds."""
        r = parse_pasted_text(
            _SAMPLE_TEXT,
            semantic_context_category=SemanticContextCategory.industry_context,
            created_at=_FIXED_DT,
        )
        assert isinstance(r, SourceManifestEntry)

    def test_no_bare_existing_digest_parameter(self):
        """parse_pasted_text must NOT accept a bare existing_digest argument."""
        with pytest.raises(TypeError):
            parse_pasted_text(  # type: ignore[call-arg]
                _SAMPLE_TEXT,
                semantic_context_category=SemanticContextCategory.industry_context,
                created_at=_FIXED_DT,
                existing_digest="a" * 64,
            )

    def test_same_id_same_digest_accepted(self):
        """Same source_id + same digest in the registry: accepted (same identity)."""
        r1 = parse_pasted_text(
            _SAMPLE_TEXT,
            semantic_context_category=SemanticContextCategory.industry_context,
            created_at=_FIXED_DT,
        )
        r2 = parse_pasted_text(
            _SAMPLE_TEXT,
            semantic_context_category=SemanticContextCategory.industry_context,
            created_at=_FIXED_DT,
            identity_registry={r1.source_id: r1.identity_digest},
        )
        assert r1.source_id == r2.source_id
        assert r1.identity_digest == r2.identity_digest

    def test_same_id_different_digest_raises_collision_error(self):
        """Same source_id but different digest in the registry: IdentityCollisionError."""
        r1 = parse_pasted_text(
            _SAMPLE_TEXT,
            semantic_context_category=SemanticContextCategory.industry_context,
            created_at=_FIXED_DT,
        )
        with pytest.raises(IdentityCollisionError):
            parse_pasted_text(
                _SAMPLE_TEXT,
                semantic_context_category=SemanticContextCategory.industry_context,
                created_at=_FIXED_DT,
                identity_registry={r1.source_id: "f" * 64},
            )

    def test_unrelated_registry_entry_no_collision(self):
        """A registry entry for a different source_id must not raise.

        An unrelated digest in the registry under a different short_id
        must never be treated as a collision.
        """
        text_a = "Content A — industry context."
        text_b = "Content B — industry context."
        r_a = parse_pasted_text(text_a, semantic_context_category=SemanticContextCategory.industry_context, created_at=_FIXED_DT)
        r_b = parse_pasted_text(text_b, semantic_context_category=SemanticContextCategory.industry_context, created_at=_FIXED_DT)
        assert r_a.source_id != r_b.source_id
        # Ingesting text_b with only r_a in the registry must NOT raise.
        r_b2 = parse_pasted_text(
            text_b,
            semantic_context_category=SemanticContextCategory.industry_context,
            created_at=_FIXED_DT,
            identity_registry={r_a.source_id: r_a.identity_digest},
        )
        assert r_b2.source_id == r_b.source_id

    def test_identity_registry_not_mutated(self):
        """The supplied identity_registry must not be modified."""
        r1 = parse_pasted_text(
            _SAMPLE_TEXT,
            semantic_context_category=SemanticContextCategory.industry_context,
            created_at=_FIXED_DT,
        )
        registry: dict[str, str] = {}
        parse_pasted_text(
            _SAMPLE_TEXT,
            semantic_context_category=SemanticContextCategory.industry_context,
            created_at=_FIXED_DT,
            identity_registry=registry,
        )
        assert registry == {}, "identity_registry must not be mutated by parse_pasted_text"

    # --- Algo version ---

    def test_default_algo_version_v1(self):
        result = parse_pasted_text(
            _SAMPLE_TEXT,
            semantic_context_category=SemanticContextCategory.industry_context,
            created_at=_FIXED_DT,
        )
        assert result.id_algo_version == "v1"

    # --- created_at ---

    def test_created_at_preserved(self):
        result = parse_pasted_text(
            _SAMPLE_TEXT,
            semantic_context_category=SemanticContextCategory.industry_context,
            created_at=_FIXED_DT,
        )
        assert result.created_at == _FIXED_DT

    def test_created_at_defaults_to_utc(self):
        before = datetime.now(tz=timezone.utc)
        result = parse_pasted_text(
            _SAMPLE_TEXT,
            semantic_context_category=SemanticContextCategory.industry_context,
        )
        after = datetime.now(tz=timezone.utc)
        assert result.created_at.tzinfo is not None
        assert before <= result.created_at <= after

    # --- Content change ---

    def test_different_text_different_source_id(self):
        r1 = parse_pasted_text("Content A.", semantic_context_category=SemanticContextCategory.industry_context, created_at=_FIXED_DT)
        r2 = parse_pasted_text("Content B.", semantic_context_category=SemanticContextCategory.industry_context, created_at=_FIXED_DT)
        assert r1.source_id != r2.source_id


# ===========================================================================
# B. _resolve_source_scope (text_parser version)
# ===========================================================================


class TestTextParserResolveSourceScope:
    def test_industry_context_external(self):
        assert _resolve_source_scope(SemanticContextCategory.industry_context) == SourceScope.external_context

    def test_strategy_profile_user_assertion(self):
        assert _resolve_source_scope(SemanticContextCategory.strategy_profile) == SourceScope.user_assertion

    def test_user_assumption_user_assertion(self):
        assert _resolve_source_scope(SemanticContextCategory.user_assumption) == SourceScope.user_assertion

    def test_business_question_decision_context(self):
        assert _resolve_source_scope(SemanticContextCategory.business_question) == SourceScope.decision_context

    def test_decision_goal_decision_context(self):
        assert _resolve_source_scope(SemanticContextCategory.decision_goal) == SourceScope.decision_context

    def test_data_source_internal_observation(self):
        assert _resolve_source_scope(SemanticContextCategory.data_source) == SourceScope.internal_observation

    def test_internal_report_internal_observation(self):
        assert _resolve_source_scope(SemanticContextCategory.internal_report) == SourceScope.internal_observation
