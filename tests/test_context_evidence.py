"""
tests/test_context_evidence.py — Task 5B-2: focused tests for app/context_evidence.py

Covers the 16 requirements specified in the task brief:

 1. industry_context produces one candidate per nonblank paragraph
 2. multiline paragraph span correctness
 3. exact normalized excerpt preservation
 4. inclusive line and character ranges
 5. paragraph_index and excerpt_checksum correctness
 6. repeated identical paragraphs have different locators
 7. CRLF and LF normalize consistently
 8. Unicode excerpt spans and checksum
 9. strategy_profile produces one correct UserContextLocator candidate
10. user_assumption produces one correct UserContextLocator candidate
11. business_question produces manifest but zero candidates
12. decision_goal produces manifest but zero candidates
13. blank raw_text rejected
14. blank field_name rejected for every category
15. unsupported category rejected
16. no EvidenceObject or evidence_id produced by this module
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

import pytest

from app.context_evidence import ContextEvidenceExtraction, extract_context_evidence
from app.identity import normalize_source_content
from app.schemas import (
    SemanticContextCategory,
    SourceFormat,
    SourceManifestEntry,
    TextEvidenceCandidate,
    TextSourceLocator,
    UserContextLocator,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FIXED_DT = datetime(2025, 6, 1, 0, 0, 0, tzinfo=timezone.utc)


def _industry(text: str, field_name: str = "context_field", **kw) -> ContextEvidenceExtraction:
    return extract_context_evidence(
        text,
        semantic_context_category=SemanticContextCategory.industry_context,
        field_name=field_name,
        created_at=_FIXED_DT,
        **kw,
    )


def _strategy(text: str, field_name: str = "strategy_field", **kw) -> ContextEvidenceExtraction:
    return extract_context_evidence(
        text,
        semantic_context_category=SemanticContextCategory.strategy_profile,
        field_name=field_name,
        created_at=_FIXED_DT,
        **kw,
    )


def _assumption(text: str, field_name: str = "assumption_field", **kw) -> ContextEvidenceExtraction:
    return extract_context_evidence(
        text,
        semantic_context_category=SemanticContextCategory.user_assumption,
        field_name=field_name,
        created_at=_FIXED_DT,
        **kw,
    )


# ---------------------------------------------------------------------------
# Test 1: industry_context produces one candidate per nonblank paragraph
# ---------------------------------------------------------------------------

class TestIndustryContextParagraphCount:
    def test_single_paragraph_yields_one_candidate(self):
        result = _industry("The SaaS market is growing at 15% annually.")
        assert len(result.candidates) == 1

    def test_two_paragraphs_yield_two_candidates(self):
        text = "First paragraph.\n\nSecond paragraph."
        result = _industry(text)
        assert len(result.candidates) == 2

    def test_three_paragraphs_yield_three_candidates(self):
        text = "Alpha.\n\nBeta.\n\nGamma."
        result = _industry(text)
        assert len(result.candidates) == 3

    def test_blank_lines_between_paragraphs_do_not_create_extra_candidates(self):
        text = "First.\n\n\n\nSecond."
        result = _industry(text)
        assert len(result.candidates) == 2

    def test_leading_and_trailing_blank_lines_ignored(self):
        text = "\n\nOnly paragraph.\n\n"
        result = _industry(text)
        assert len(result.candidates) == 1

    def test_whitespace_only_lines_not_candidates(self):
        text = "Real paragraph.\n   \n  \nAnother paragraph."
        result = _industry(text)
        # whitespace-only lines are blank → two paragraphs
        assert len(result.candidates) == 2


# ---------------------------------------------------------------------------
# Test 2: multiline paragraph span correctness
# ---------------------------------------------------------------------------

class TestMultilineParagraphSpan:
    def test_multiline_paragraph_has_correct_line_range(self):
        text = "Line one of para.\nLine two of para.\nLine three of para."
        result = _industry(text)
        assert len(result.candidates) == 1
        loc = result.candidates[0].source_locator
        assert isinstance(loc, TextSourceLocator)
        assert loc.line_start == 0
        assert loc.line_end == 2

    def test_second_paragraph_line_start_after_blank(self):
        text = "Para one.\n\nPara two line one.\nPara two line two."
        result = _industry(text)
        assert len(result.candidates) == 2
        loc1 = result.candidates[0].source_locator
        loc2 = result.candidates[1].source_locator
        assert loc1.line_start == 0
        assert loc1.line_end == 0
        assert loc2.line_start == 2
        assert loc2.line_end == 3


# ---------------------------------------------------------------------------
# Test 3: exact normalized excerpt preservation
# ---------------------------------------------------------------------------

class TestExactExcerptPreservation:
    def test_excerpt_matches_normalized_paragraph_text(self):
        text = "  The cloud market is booming.  "
        norm = normalize_source_content(text)
        result = _industry(text)
        assert len(result.candidates) == 1
        excerpt = result.candidates[0].exact_excerpt
        # excerpt must be a substring of the normalized text
        assert excerpt in norm

    def test_excerpt_is_substring_of_normalized_text(self):
        text = "Para one.\n\nPara two."
        norm = normalize_source_content(text)
        result = _industry(text)
        for c in result.candidates:
            assert c.exact_excerpt in norm

    def test_crlf_input_excerpt_matches_lf_excerpt(self):
        """CRLF and LF input produce the same excerpt (normalized to LF)."""
        crlf_text = "First paragraph.\r\n\r\nSecond paragraph."
        lf_text = "First paragraph.\n\nSecond paragraph."
        r_crlf = _industry(crlf_text)
        r_lf = _industry(lf_text)
        excerpts_crlf = [c.exact_excerpt for c in r_crlf.candidates]
        excerpts_lf = [c.exact_excerpt for c in r_lf.candidates]
        assert excerpts_crlf == excerpts_lf


# ---------------------------------------------------------------------------
# Test 4: inclusive line and character ranges
# ---------------------------------------------------------------------------

class TestInclusiveRanges:
    def test_char_start_and_end_are_inclusive(self):
        text = "Hello world."
        norm = normalize_source_content(text)
        result = _industry(text)
        assert len(result.candidates) == 1
        loc = result.candidates[0].source_locator
        assert isinstance(loc, TextSourceLocator)
        # char_start:char_end+1 must exactly equal the excerpt
        recovered = norm[loc.char_start : loc.char_end + 1]
        assert recovered == result.candidates[0].exact_excerpt

    def test_char_ranges_for_second_paragraph(self):
        text = "Para one.\n\nPara two."
        norm = normalize_source_content(text)
        result = _industry(text)
        assert len(result.candidates) == 2
        for c in result.candidates:
            loc = c.source_locator
            assert isinstance(loc, TextSourceLocator)
            recovered = norm[loc.char_start : loc.char_end + 1]
            assert recovered == c.exact_excerpt

    def test_multiline_char_range_is_inclusive(self):
        text = "Line A.\nLine B.\n\nLine C."
        norm = normalize_source_content(text)
        result = _industry(text)
        # First candidate spans two lines
        loc = result.candidates[0].source_locator
        assert isinstance(loc, TextSourceLocator)
        recovered = norm[loc.char_start : loc.char_end + 1]
        assert recovered == result.candidates[0].exact_excerpt


# ---------------------------------------------------------------------------
# Test 5: paragraph_index and excerpt_checksum correctness
# ---------------------------------------------------------------------------

class TestParagraphIndexAndChecksum:
    def test_paragraph_indices_are_sequential_from_zero(self):
        text = "A.\n\nB.\n\nC."
        result = _industry(text)
        for i, c in enumerate(result.candidates):
            loc = c.source_locator
            assert isinstance(loc, TextSourceLocator)
            assert loc.paragraph_index == i

    def test_excerpt_checksum_matches_sha256_of_excerpt(self):
        text = "The market is growing.\n\nCompetition is fierce."
        result = _industry(text)
        for c in result.candidates:
            loc = c.source_locator
            assert isinstance(loc, TextSourceLocator)
            expected = hashlib.sha256(c.exact_excerpt.encode("utf-8")).hexdigest()
            assert loc.excerpt_checksum == expected


# ---------------------------------------------------------------------------
# Test 6: repeated identical paragraphs have different locators
# ---------------------------------------------------------------------------

class TestRepeatedIdenticalParagraphs:
    def test_same_text_twice_has_different_paragraph_index(self):
        text = "Market is growing.\n\nMarket is growing."
        result = _industry(text)
        assert len(result.candidates) == 2
        loc0 = result.candidates[0].source_locator
        loc1 = result.candidates[1].source_locator
        assert isinstance(loc0, TextSourceLocator)
        assert isinstance(loc1, TextSourceLocator)
        assert loc0.paragraph_index == 0
        assert loc1.paragraph_index == 1
        # excerpt text is the same but locators differ
        assert result.candidates[0].exact_excerpt == result.candidates[1].exact_excerpt
        assert loc0.char_start != loc1.char_start


# ---------------------------------------------------------------------------
# Test 7: CRLF and LF normalize consistently
# ---------------------------------------------------------------------------

class TestCRLFNormalization:
    def test_crlf_source_produces_same_source_id_as_lf(self):
        crlf = "Industry insight.\r\n\r\nAnother insight."
        lf = "Industry insight.\n\nAnother insight."
        r_crlf = _industry(crlf)
        r_lf = _industry(lf)
        assert r_crlf.source_manifest.source_id == r_lf.source_manifest.source_id

    def test_crlf_source_produces_same_candidate_count_as_lf(self):
        crlf = "Para one.\r\nStill para one.\r\n\r\nPara two."
        lf = "Para one.\nStill para one.\n\nPara two."
        r_crlf = _industry(crlf)
        r_lf = _industry(lf)
        assert len(r_crlf.candidates) == len(r_lf.candidates) == 2


# ---------------------------------------------------------------------------
# Test 8: Unicode excerpt spans and checksum
# ---------------------------------------------------------------------------

class TestUnicodeExcerpts:
    def test_unicode_text_excerpt_preserved(self):
        text = "企業戦略：顧客維持率を向上させる。\n\n市場の成長率は年15%。"
        result = _industry(text)
        assert len(result.candidates) == 2
        norm = normalize_source_content(text)
        for c in result.candidates:
            loc = c.source_locator
            assert isinstance(loc, TextSourceLocator)
            recovered = norm[loc.char_start : loc.char_end + 1]
            assert recovered == c.exact_excerpt

    def test_unicode_checksum_is_correct(self):
        text = "Données du marché : croissance de 12 %."
        result = _industry(text)
        assert len(result.candidates) == 1
        c = result.candidates[0]
        loc = c.source_locator
        assert isinstance(loc, TextSourceLocator)
        expected_checksum = hashlib.sha256(c.exact_excerpt.encode("utf-8")).hexdigest()
        assert loc.excerpt_checksum == expected_checksum


# ---------------------------------------------------------------------------
# Test 9: strategy_profile produces one correct UserContextLocator candidate
# ---------------------------------------------------------------------------

class TestStrategyProfileCandidate:
    def test_produces_exactly_one_candidate(self):
        result = _strategy("Our priority is enterprise retention.", field_name="strategic_goal")
        assert len(result.candidates) == 1

    def test_candidate_has_user_context_locator(self):
        result = _strategy("Focus on churn reduction.", field_name="main_priority")
        c = result.candidates[0]
        assert isinstance(c.source_locator, UserContextLocator)
        assert c.source_locator.field_name == "main_priority"
        assert c.source_locator.context_category == SemanticContextCategory.strategy_profile

    def test_candidate_has_correct_locked_values(self):
        result = _strategy("Grow enterprise segment.", field_name="goal")
        c = result.candidates[0]
        assert c.evidence_type == "strategy_priority_statement"
        assert c.normalized_claim_key == "context.strategy_profile.statement"
        assert c.canonical_rule_parameters == {
            "extraction_policy": "exact_source_statement_v1",
            "semantic_context_category": "strategy_profile",
        }

    def test_candidate_confidence_is_high(self):
        result = _strategy("Expand into new markets.", field_name="f")
        assert result.candidates[0].confidence == "high"

    def test_candidate_source_format_is_form_input(self):
        result = _strategy("Reduce churn.", field_name="f")
        c = result.candidates[0]
        assert c.source_format == SourceFormat.form_input

    def test_manifest_source_format_is_form_input(self):
        result = _strategy("Invest in support.", field_name="f")
        assert result.source_manifest.source_format == SourceFormat.form_input

    def test_rejection_reason_is_none(self):
        result = _strategy("Some strategy text.", field_name="f")
        assert result.rejection_reason is None


# ---------------------------------------------------------------------------
# Test 10: user_assumption produces one correct UserContextLocator candidate
# ---------------------------------------------------------------------------

class TestUserAssumptionCandidate:
    def test_produces_exactly_one_candidate(self):
        result = _assumption("We assume price sensitivity is low.", field_name="assumption")
        assert len(result.candidates) == 1

    def test_candidate_has_user_context_locator(self):
        result = _assumption("Customers prefer speed.", field_name="key_assumption")
        c = result.candidates[0]
        assert isinstance(c.source_locator, UserContextLocator)
        assert c.source_locator.field_name == "key_assumption"
        assert c.source_locator.context_category == SemanticContextCategory.user_assumption

    def test_candidate_confidence_is_low(self):
        result = _assumption("We assume market is stable.", field_name="f")
        assert result.candidates[0].confidence == "low"

    def test_candidate_has_correct_locked_evidence_type(self):
        result = _assumption("An assumption about pricing.", field_name="f")
        assert result.candidates[0].evidence_type == "user_assumption_statement"

    def test_rejection_reason_is_none(self):
        result = _assumption("Some assumption.", field_name="f")
        assert result.rejection_reason is None


# ---------------------------------------------------------------------------
# Test 11: business_question produces manifest but zero candidates
# ---------------------------------------------------------------------------

class TestBusinessQuestion:
    def test_produces_manifest(self):
        result = extract_context_evidence(
            "Should we invest in churn prevention?",
            semantic_context_category=SemanticContextCategory.business_question,
            field_name="question",
            created_at=_FIXED_DT,
        )
        assert isinstance(result.source_manifest, SourceManifestEntry)
        assert result.source_manifest.source_format == SourceFormat.form_input

    def test_produces_zero_candidates(self):
        result = extract_context_evidence(
            "What is our main goal?",
            semantic_context_category=SemanticContextCategory.business_question,
            field_name="question",
            created_at=_FIXED_DT,
        )
        assert len(result.candidates) == 0

    def test_rejection_reason_is_nonblank(self):
        result = extract_context_evidence(
            "What should we prioritize?",
            semantic_context_category=SemanticContextCategory.business_question,
            field_name="question",
            created_at=_FIXED_DT,
        )
        assert result.rejection_reason is not None
        assert result.rejection_reason.strip() != ""
        assert "business_question" in result.rejection_reason


# ---------------------------------------------------------------------------
# Test 12: decision_goal produces manifest but zero candidates
# ---------------------------------------------------------------------------

class TestDecisionGoal:
    def test_produces_manifest(self):
        result = extract_context_evidence(
            "Reduce churn to under 5%.",
            semantic_context_category=SemanticContextCategory.decision_goal,
            field_name="goal",
            created_at=_FIXED_DT,
        )
        assert isinstance(result.source_manifest, SourceManifestEntry)
        assert result.source_manifest.source_format == SourceFormat.form_input

    def test_produces_zero_candidates(self):
        result = extract_context_evidence(
            "Achieve 95% retention.",
            semantic_context_category=SemanticContextCategory.decision_goal,
            field_name="goal",
            created_at=_FIXED_DT,
        )
        assert len(result.candidates) == 0

    def test_rejection_reason_is_nonblank(self):
        result = extract_context_evidence(
            "Grow revenue by 20%.",
            semantic_context_category=SemanticContextCategory.decision_goal,
            field_name="goal",
            created_at=_FIXED_DT,
        )
        assert result.rejection_reason is not None
        assert result.rejection_reason.strip() != ""
        assert "decision_goal" in result.rejection_reason


# ---------------------------------------------------------------------------
# Test 13: blank raw_text rejected
# ---------------------------------------------------------------------------

class TestBlankRawText:
    def test_empty_string_rejected(self):
        with pytest.raises(ValueError, match="raw_text"):
            extract_context_evidence(
                "",
                semantic_context_category=SemanticContextCategory.industry_context,
                field_name="f",
                created_at=_FIXED_DT,
            )

    def test_whitespace_only_rejected(self):
        with pytest.raises(ValueError, match="raw_text"):
            extract_context_evidence(
                "   \n\t  ",
                semantic_context_category=SemanticContextCategory.strategy_profile,
                field_name="f",
                created_at=_FIXED_DT,
            )


# ---------------------------------------------------------------------------
# Test 14: blank field_name rejected for every category
# ---------------------------------------------------------------------------

class TestBlankFieldName:
    @pytest.mark.parametrize("cat", [
        SemanticContextCategory.industry_context,
        SemanticContextCategory.strategy_profile,
        SemanticContextCategory.user_assumption,
        SemanticContextCategory.business_question,
        SemanticContextCategory.decision_goal,
    ])
    def test_blank_field_name_rejected(self, cat: SemanticContextCategory):
        with pytest.raises(ValueError, match="field_name"):
            extract_context_evidence(
                "Some text content here.",
                semantic_context_category=cat,
                field_name="",
                created_at=_FIXED_DT,
            )

    @pytest.mark.parametrize("cat", [
        SemanticContextCategory.industry_context,
        SemanticContextCategory.strategy_profile,
        SemanticContextCategory.user_assumption,
        SemanticContextCategory.business_question,
        SemanticContextCategory.decision_goal,
    ])
    def test_whitespace_only_field_name_rejected(self, cat: SemanticContextCategory):
        with pytest.raises(ValueError, match="field_name"):
            extract_context_evidence(
                "Some text content here.",
                semantic_context_category=cat,
                field_name="   ",
                created_at=_FIXED_DT,
            )


# ---------------------------------------------------------------------------
# Test 15: unsupported category rejected
# ---------------------------------------------------------------------------

class TestUnsupportedCategory:
    def test_data_source_rejected(self):
        with pytest.raises(ValueError, match="data_source"):
            extract_context_evidence(
                "Some text.",
                semantic_context_category=SemanticContextCategory.data_source,
                field_name="f",
                created_at=_FIXED_DT,
            )

    def test_internal_report_rejected(self):
        with pytest.raises(ValueError, match="internal_report"):
            extract_context_evidence(
                "Some text.",
                semantic_context_category=SemanticContextCategory.internal_report,
                field_name="f",
                created_at=_FIXED_DT,
            )


# ---------------------------------------------------------------------------
# Test 16: no EvidenceObject or evidence_id produced by this module
# ---------------------------------------------------------------------------

class TestNoBoundaryViolations:
    def test_industry_context_candidates_have_no_evidence_id(self):
        result = _industry("Market growing at 10%.")
        for c in result.candidates:
            assert isinstance(c, TextEvidenceCandidate)
            assert not hasattr(c, "evidence_id"), (
                "TextEvidenceCandidate must never carry evidence_id"
            )
            assert not hasattr(c, "identity_digest"), (
                "TextEvidenceCandidate must never carry identity_digest"
            )

    def test_strategy_profile_candidate_has_no_evidence_id(self):
        result = _strategy("Reduce churn.", field_name="f")
        c = result.candidates[0]
        assert not hasattr(c, "evidence_id")
        assert not hasattr(c, "identity_digest")

    def test_result_type_is_context_evidence_extraction(self):
        result = _industry("Market insight.")
        assert isinstance(result, ContextEvidenceExtraction)

    def test_source_code_does_not_import_evidence_builder(self):
        """Prove via AST that context_evidence.py never imports app.evidence_builder."""
        import ast
        import pathlib
        src = pathlib.Path("app/context_evidence.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert "evidence_builder" not in alias.name, (
                        f"context_evidence.py must not import evidence_builder, "
                        f"found: import {alias.name}"
                    )
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                assert "evidence_builder" not in module, (
                    f"context_evidence.py must not import from evidence_builder, "
                    f"found: from {module} import ..."
                )

    def test_source_code_does_not_call_build_evidence(self):
        """Prove via AST that context_evidence.py never calls build_evidence(...)."""
        import ast
        import pathlib
        src = pathlib.Path("app/context_evidence.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                name = ""
                if isinstance(func, ast.Name):
                    name = func.id
                elif isinstance(func, ast.Attribute):
                    name = func.attr
                assert name != "build_evidence", (
                    "context_evidence.py must not call build_evidence()"
                )

    def test_source_code_does_not_construct_evidence_object(self):
        """Prove via AST that context_evidence.py never calls EvidenceObject(...)."""
        import ast
        import pathlib
        src = pathlib.Path("app/context_evidence.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                name = ""
                if isinstance(func, ast.Name):
                    name = func.id
                elif isinstance(func, ast.Attribute):
                    name = func.attr
                assert name != "EvidenceObject", (
                    "context_evidence.py must not construct EvidenceObject"
                )


# ---------------------------------------------------------------------------
# Upload event ID — 5 new focused tests (repair)
# ---------------------------------------------------------------------------


class TestUploadEventId:
    def test_industry_upload_event_id_preserved_in_manifest(self):
        """upload_event_id passed to extract_context_evidence is stored in the manifest."""
        result = extract_context_evidence(
            "Global market grew 15%.",
            semantic_context_category=SemanticContextCategory.industry_context,
            field_name="context",
            upload_event_id="evt-industry-001",
            created_at=_FIXED_DT,
        )
        assert result.source_manifest.upload_event_id == "evt-industry-001"

    def test_upload_event_id_does_not_change_source_id(self):
        """upload_event_id is metadata only; the source identity is unchanged."""
        r1 = extract_context_evidence(
            "Cloud adoption is rising.",
            semantic_context_category=SemanticContextCategory.industry_context,
            field_name="context",
            upload_event_id=None,
            created_at=_FIXED_DT,
        )
        r2 = extract_context_evidence(
            "Cloud adoption is rising.",
            semantic_context_category=SemanticContextCategory.industry_context,
            field_name="context",
            upload_event_id="evt-different-999",
            created_at=_FIXED_DT,
        )
        assert r1.source_manifest.source_id == r2.source_manifest.source_id
        assert r1.source_manifest.identity_digest == r2.source_manifest.identity_digest

    def test_form_context_upload_event_id_preserved(self):
        """upload_event_id is forwarded to ingest_form_input for form categories."""
        result = extract_context_evidence(
            "Our priority is customer retention.",
            semantic_context_category=SemanticContextCategory.strategy_profile,
            field_name="strategy",
            upload_event_id="evt-form-007",
            created_at=_FIXED_DT,
        )
        assert result.source_manifest.upload_event_id == "evt-form-007"

    def test_unicode_character_offset_semantics(self):
        """char_start/char_end are Python character indexes, not byte offsets.

        For multi-byte Unicode text the slice normalized[char_start:char_end+1]
        must exactly equal the stored excerpt regardless of the byte width of
        individual characters.
        """
        text = "市場は成長中。\n\n顧客維持が重要。"
        from app.identity import normalize_source_content
        norm = normalize_source_content(text)
        result = extract_context_evidence(
            text,
            semantic_context_category=SemanticContextCategory.industry_context,
            field_name="context",
            created_at=_FIXED_DT,
        )
        for c in result.candidates:
            loc = c.source_locator
            assert isinstance(loc, TextSourceLocator)
            # Python string slicing (character indexes) must recover the exact excerpt.
            recovered = norm[loc.char_start : loc.char_end + 1]
            assert recovered == c.exact_excerpt, (
                f"Character-index slice must equal exact_excerpt; "
                f"char_start={loc.char_start}, char_end={loc.char_end}"
            )
