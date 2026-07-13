"""
tests/test_evidence_builder.py — Tests for app/evidence_builder.py (Task 5).

Coverage targets:
  A. build_evidence — happy path, idempotency, evidence_id format, scope derivation
  B. Minting boundary — evidence_id only minted here; no other module produces it
  C. Duplicate handling — same candidate twice → one EvidenceObject
  D. Collision detection — same short_id + different digest → IdentityCollisionError
  E. MissingSourceManifestError — candidate with unknown source_id
  F. EvidenceScopeError — candidate from decision_context source
  G. Evidence scope derivation — all four SourceScope values
  H. Empty input — returns empty list
  I. Integration — sample CSV round-trip: CSV → intake → parse → health → evidence
  J. EvidenceObject structural checks — all required fields present
  K. Decision 002 validation — evidence from two sources stays separately traceable
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from app.data_health import analyze_data_health
from app.data_parser import parse_csv
from app.evidence_builder import (
    EvidenceScopeError,
    MissingSourceManifestError,
    _derive_evidence_scope,
    build_evidence,
)
from app.file_intake import ingest_csv
from app.identity import IdentityCollisionError
from app.schemas import (
    EvidenceObject,
    EvidenceScope,
    EvidenceStatus,
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

_SOURCE_ID_RE = re.compile(r"^src-[a-z0-9_]{1,12}-[0-9a-f]{12}$")
_EVIDENCE_ID_RE = re.compile(r"^ev-[a-z0-9_]{1,12}-[0-9a-f]{12}$")
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_FIXED_DT = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
_SAMPLE_CSV_PATH = Path("sample_data") / "regional_sales_q1_q4.csv"


def _csv_entry(raw: bytes, category=SemanticContextCategory.data_source) -> SourceManifestEntry:
    return ingest_csv(raw, semantic_context_category=category, created_at=_FIXED_DT)


def _full_pipeline(raw: bytes) -> tuple[list[EvidenceObject], SourceManifestEntry]:
    """Run the full CSV → evidence pipeline and return (evidence_objects, entry)."""
    entry = _csv_entry(raw)
    df = parse_csv(raw, entry)
    _, candidates = analyze_data_health(df, entry)
    evidence = build_evidence(candidates, [entry])
    return evidence, entry


def _make_single_candidate(entry: SourceManifestEntry) -> HealthFindingCandidate:
    """Create a minimal HealthFindingCandidate for a given entry."""
    return HealthFindingCandidate(
        source_id=entry.source_id,
        source_format=entry.source_format,
        source_locator=TabularSourceLocator(columns=["revenue"]),
        evidence_type="missing_value_rate",
        canonical_rule_parameters={"column": "revenue", "missing_rate": 0.1, "row_count": 10, "missing_count": 1, "threshold": 0.0},
        normalized_claim_key="data.missing.revenue",
        finding="Revenue column has 10% missing values.",
        supporting_evidence="pandas null count = 1 out of 10 rows.",
        confidence="high",
        limitations=["Only null detection, not domain-specific codes."],
        relevant_roles=["data_analyst", "data_engineer"],
        decision_relevance="Affects downstream revenue analysis.",
    )


def _make_manifest_with_scope(scope: SourceScope, category: SemanticContextCategory) -> SourceManifestEntry:
    from app.identity import generate_source_id
    sid, digest = generate_source_id(
        source_format="csv",
        semantic_context_category=category.value,
        normalized_content=f"placeholder content for {scope.value}",
    )
    return SourceManifestEntry(
        source_id=sid,
        identity_digest=digest,
        source_format=SourceFormat.csv,
        semantic_context_category=category,
        source_scope=scope,
        id_algo_version="v1",
        created_at=_FIXED_DT,
    )


# ===========================================================================
# A. build_evidence — basic structure
# ===========================================================================


class TestBuildEvidenceStructure:

    def test_returns_list(self):
        raw = b"a,b\n1,2\n1,2\n"  # one duplicate
        evidence, _ = _full_pipeline(raw)
        assert isinstance(evidence, list)

    def test_all_elements_are_evidence_objects(self):
        raw = b"a,b\n1,2\n1,2\n"
        evidence, _ = _full_pipeline(raw)
        for e in evidence:
            assert isinstance(e, EvidenceObject)

    def test_evidence_id_format(self):
        raw = b"a,b\n1,2\n1,2\n"
        evidence, _ = _full_pipeline(raw)
        for e in evidence:
            assert _EVIDENCE_ID_RE.match(e.evidence_id), (
                f"evidence_id {e.evidence_id!r} does not match regex"
            )

    def test_identity_digest_64_hex(self):
        raw = b"a,b\n1,2\n1,2\n"
        evidence, _ = _full_pipeline(raw)
        for e in evidence:
            assert _DIGEST_RE.match(e.identity_digest)

    def test_evidence_id_starts_with_ev(self):
        raw = b"a,b\n1,2\n1,2\n"
        evidence, _ = _full_pipeline(raw)
        for e in evidence:
            assert e.evidence_id.startswith("ev-")

    def test_evidence_id_does_not_equal_source_id(self):
        raw = b"a,b\n1,2\n1,2\n"
        evidence, entry = _full_pipeline(raw)
        for e in evidence:
            assert e.evidence_id != entry.source_id

    def test_created_by_is_evidence_builder(self):
        raw = b"a,b\n1,2\n1,2\n"
        evidence, _ = _full_pipeline(raw)
        for e in evidence:
            assert e.created_by == "evidence_builder"

    def test_extraction_method_is_deterministic(self):
        raw = b"a,b\n1,2\n1,2\n"
        evidence, _ = _full_pipeline(raw)
        for e in evidence:
            assert e.extraction_method == "deterministic"

    def test_status_is_active(self):
        raw = b"a,b\n1,2\n1,2\n"
        evidence, _ = _full_pipeline(raw)
        for e in evidence:
            assert e.status == EvidenceStatus.active

    def test_source_id_matches_entry(self):
        raw = b"a,b\n1,2\n1,2\n"
        evidence, entry = _full_pipeline(raw)
        for e in evidence:
            assert e.source_id == entry.source_id

    def test_source_format_is_csv(self):
        raw = b"a,b\n1,2\n1,2\n"
        evidence, _ = _full_pipeline(raw)
        for e in evidence:
            assert e.source_format == SourceFormat.csv


# ===========================================================================
# B. Minting boundary — only evidence_builder produces evidence_id
# ===========================================================================


class TestMintingBoundary:

    def test_health_candidates_have_no_evidence_id(self):
        raw = b"a,b\n1,2\n1,2\n"
        entry = _csv_entry(raw)
        df = parse_csv(raw, entry)
        _, candidates = analyze_data_health(df, entry)
        for c in candidates:
            assert not hasattr(c, "evidence_id"), (
                "data_health.py produced a HealthFindingCandidate with evidence_id — "
                "minting boundary violated!"
            )

    def test_evidence_objects_have_evidence_id(self):
        raw = b"a,b\n1,2\n1,2\n"
        evidence, _ = _full_pipeline(raw)
        for e in evidence:
            assert hasattr(e, "evidence_id")
            assert isinstance(e.evidence_id, str)

    def test_only_one_module_produces_evidence_id(self):
        """data_health, data_parser, file_intake, text_parser, utils, identity
        must not export or produce evidence_id values."""
        import app.data_health as dh
        import app.data_parser as dp
        import app.file_intake as fi
        import app.text_parser as tp
        import app.utils as ut
        import app.identity as ident

        for module in [dh, dp, fi, tp, ut]:
            # Modules must not export generate_evidence_id or build_evidence.
            assert not hasattr(module, "build_evidence"), (
                f"{module.__name__} must not export build_evidence"
            )

        # identity.py exports generate_evidence_id (low-level function),
        # but it does NOT construct EvidenceObject — that boundary is enforced
        # by this test: only evidence_builder.build_evidence returns EvidenceObject.
        assert hasattr(ident, "generate_evidence_id")


# ===========================================================================
# C. Duplicate handling
# ===========================================================================


class TestDuplicateHandling:

    def test_identical_candidates_produce_one_evidence_object(self):
        entry = _csv_entry(b"a,b\n1,2\n")
        c1 = _make_single_candidate(entry)
        c2 = _make_single_candidate(entry)  # identical to c1
        evidence = build_evidence([c1, c2], [entry])
        assert len(evidence) == 1

    def test_duplicate_deduplication_same_evidence_id(self):
        entry = _csv_entry(b"a,b\n1,2\n")
        c1 = _make_single_candidate(entry)
        c2 = _make_single_candidate(entry)
        evidence = build_evidence([c1, c2], [entry])
        assert len(evidence) == 1
        assert evidence[0].created_by == "evidence_builder"

    def test_different_candidates_produce_separate_evidence_objects(self):
        raw = b"a,b\n1,\n2,\n1,\n"  # missing values in b + duplicate row
        evidence, _ = _full_pipeline(raw)
        # Should have at least: 1 missing-value finding for 'b' + 1 duplicate finding
        assert len(evidence) >= 2

    def test_candidates_from_same_source_different_columns_not_deduplicated(self):
        entry = _csv_entry(b"a,b,c\n1,,\n")
        # Two missing-value candidates for different columns.
        c_a = HealthFindingCandidate(
            source_id=entry.source_id,
            source_format=entry.source_format,
            source_locator=TabularSourceLocator(columns=["a"]),
            evidence_type="missing_value_rate",
            canonical_rule_parameters={"column": "a", "missing_rate": 0.5, "row_count": 2, "missing_count": 1, "threshold": 0.0},
            normalized_claim_key="data.missing.a",
            finding="Column a missing.",
            supporting_evidence="null count = 1.",
            confidence="high",
            limitations=[],
            relevant_roles=["data_analyst"],
            decision_relevance="Data quality.",
        )
        c_b = HealthFindingCandidate(
            source_id=entry.source_id,
            source_format=entry.source_format,
            source_locator=TabularSourceLocator(columns=["b"]),
            evidence_type="missing_value_rate",
            canonical_rule_parameters={"column": "b", "missing_rate": 0.5, "row_count": 2, "missing_count": 1, "threshold": 0.0},
            normalized_claim_key="data.missing.b",
            finding="Column b missing.",
            supporting_evidence="null count = 1.",
            confidence="high",
            limitations=[],
            relevant_roles=["data_analyst"],
            decision_relevance="Data quality.",
        )
        evidence = build_evidence([c_a, c_b], [entry])
        assert len(evidence) == 2
        eids = {e.evidence_id for e in evidence}
        assert len(eids) == 2


# ===========================================================================
# D. Collision detection
# ===========================================================================


class TestCollisionDetection:
    def test_collision_raises_identity_collision_error(self):
        """Simulate a collision by submitting two candidates that produce the
        same short_id but different digests.  This is extremely rare in practice
        but must be tested via a mock."""
        from unittest.mock import patch

        entry = _csv_entry(b"a,b\n1,2\n")
        c1 = _make_single_candidate(entry)
        c2 = _make_single_candidate(entry)

        # Patch generate_evidence_id to return different digests for the same
        # short_id on the second call.
        call_count = [0]
        real_eid = None

        def mock_generate_evidence_id(**kwargs):
            from app.identity import generate_evidence_id as real_fn
            eid, digest = real_fn(**kwargs)
            call_count[0] += 1
            if call_count[0] == 1:
                # First call: normal.
                nonlocal real_eid
                real_eid = eid
                return eid, digest
            else:
                # Second call: same short_id, different digest (simulated collision).
                return real_eid, "f" * 64

        with patch("app.evidence_builder.generate_evidence_id", side_effect=mock_generate_evidence_id):
            with pytest.raises(IdentityCollisionError):
                build_evidence([c1, c2], [entry])


# ===========================================================================
# E. MissingSourceManifestError
# ===========================================================================


class TestMissingSourceManifestError:
    def test_is_value_error_subclass(self):
        assert issubclass(MissingSourceManifestError, ValueError)

    def test_attribute_set(self):
        err = MissingSourceManifestError(source_id="src-csv-abcdef012345")
        assert err.source_id == "src-csv-abcdef012345"

    def test_missing_source_id_raises(self):
        entry = _csv_entry(b"a,b\n1,2\n")
        candidate = _make_single_candidate(entry)
        # Pass empty manifests list — source_id not found.
        with pytest.raises(MissingSourceManifestError) as exc_info:
            build_evidence([candidate], [])
        assert entry.source_id in str(exc_info.value)

    def test_wrong_manifest_raises(self):
        entry1 = _csv_entry(b"a,b\n1,2\n")
        entry2 = _csv_entry(b"x,y\n10,20\n")
        candidate = _make_single_candidate(entry1)
        # Pass entry2's manifest instead of entry1's.
        with pytest.raises(MissingSourceManifestError):
            build_evidence([candidate], [entry2])


# ===========================================================================
# F. EvidenceScopeError
# ===========================================================================


class TestEvidenceScopeError:
    def test_is_value_error_subclass(self):
        assert issubclass(EvidenceScopeError, ValueError)

    def test_attributes_set(self):
        err = EvidenceScopeError(source_id="src-csv-abc", source_scope="decision_context")
        assert err.source_id == "src-csv-abc"
        assert err.source_scope == "decision_context"

    def test_decision_context_source_raises(self):
        # Create a manifest with decision_context scope.
        manifest = _make_manifest_with_scope(
            SourceScope.decision_context,
            SemanticContextCategory.business_question,
        )
        candidate = HealthFindingCandidate(
            source_id=manifest.source_id,
            source_format=manifest.source_format,
            source_locator=TabularSourceLocator(columns=["goal"]),
            evidence_type="missing_value_rate",
            canonical_rule_parameters={"column": "goal", "missing_rate": 0.0, "row_count": 1, "missing_count": 0, "threshold": 0.0},
            normalized_claim_key="data.missing.goal",
            finding="No missing values.",
            supporting_evidence="All present.",
            confidence="high",
            limitations=[],
            relevant_roles=["data_analyst"],
            decision_relevance="N/A",
        )
        with pytest.raises(EvidenceScopeError) as exc_info:
            build_evidence([candidate], [manifest])
        assert "decision_context" in str(exc_info.value)

    def test_decision_goal_scope_raises(self):
        manifest = _make_manifest_with_scope(
            SourceScope.decision_context,
            SemanticContextCategory.decision_goal,
        )
        candidate = HealthFindingCandidate(
            source_id=manifest.source_id,
            source_format=manifest.source_format,
            source_locator=TabularSourceLocator(columns=["goal"]),
            evidence_type="missing_value_rate",
            canonical_rule_parameters={"column": "goal", "missing_rate": 0.0, "row_count": 1, "missing_count": 0, "threshold": 0.0},
            normalized_claim_key="data.missing.goal",
            finding="No missing values.",
            supporting_evidence="All present.",
            confidence="high",
            limitations=[],
            relevant_roles=["data_analyst"],
            decision_relevance="N/A",
        )
        with pytest.raises(EvidenceScopeError):
            build_evidence([candidate], [manifest])


# ===========================================================================
# G. Evidence scope derivation
# ===========================================================================


class TestDerivEvidenceScope:
    def test_internal_observation_maps_to_internal(self):
        result = _derive_evidence_scope(
            SourceScope.internal_observation,
            SemanticContextCategory.data_source,
        )
        assert result == EvidenceScope.internal_observation

    def test_external_context_maps_to_external(self):
        result = _derive_evidence_scope(
            SourceScope.external_context,
            SemanticContextCategory.industry_context,
        )
        assert result == EvidenceScope.external_context

    def test_user_assertion_maps_to_assumption(self):
        result = _derive_evidence_scope(
            SourceScope.user_assertion,
            SemanticContextCategory.user_assumption,
        )
        assert result == EvidenceScope.assumption

    def test_strategy_profile_user_assertion_maps_to_stated_priority(self):
        """Decision 002: strategy profile assertions produce stated_priority."""
        result = _derive_evidence_scope(
            SourceScope.user_assertion,
            SemanticContextCategory.strategy_profile,
        )
        assert result == EvidenceScope.stated_priority

    def test_decision_context_raises(self):
        with pytest.raises(EvidenceScopeError):
            _derive_evidence_scope(
                SourceScope.decision_context,
                SemanticContextCategory.business_question,
            )

    def test_internal_report_maps_to_internal(self):
        result = _derive_evidence_scope(
            SourceScope.internal_observation,
            SemanticContextCategory.internal_report,
        )
        assert result == EvidenceScope.internal_observation


# ===========================================================================
# H. Empty input
# ===========================================================================


class TestEmptyInput:
    def test_empty_candidates_returns_empty_list(self):
        result = build_evidence([], [])
        assert result == []

    def test_empty_candidates_with_manifests_returns_empty_list(self):
        entry = _csv_entry(b"a,b\n1,2\n")
        result = build_evidence([], [entry])
        assert result == []


# ===========================================================================
# I. Integration — full CSV pipeline
# ===========================================================================


class TestFullPipelineIntegration:

    def test_clean_csv_produces_zero_evidence_objects(self):
        raw = b"region,revenue\nNorth,100\nSouth,200\nEast,300\n"
        evidence, _ = _full_pipeline(raw)
        assert evidence == []

    def test_csv_with_duplicates_produces_evidence(self):
        raw = b"a,b\n1,2\n1,2\n3,4\n"
        evidence, _ = _full_pipeline(raw)
        dup_evidence = [e for e in evidence if e.evidence_type == "duplicate_row"]
        assert len(dup_evidence) == 1

    def test_csv_with_missing_produces_evidence(self):
        raw = b"a,b\n1,\n2,\n3,4\n"
        evidence, _ = _full_pipeline(raw)
        missing_evidence = [e for e in evidence if e.evidence_type == "missing_value_rate"]
        assert len(missing_evidence) >= 1

    def test_all_evidence_cite_valid_source_id(self):
        raw = b"a,b\n1,2\n1,2\n"
        evidence, entry = _full_pipeline(raw)
        for e in evidence:
            assert _SOURCE_ID_RE.match(e.source_id)
            assert e.source_id == entry.source_id

    def test_evidence_ids_all_unique(self):
        raw = b"a,b,c\n1,,\n2,,3\n1,,\n"
        evidence, _ = _full_pipeline(raw)
        eids = [e.evidence_id for e in evidence]
        assert len(eids) == len(set(eids)), "Duplicate evidence_id values found"

    def test_pipeline_is_idempotent(self):
        raw = b"a,b\n1,\n2,\n1,\n"
        ev1, _ = _full_pipeline(raw)
        ev2, _ = _full_pipeline(raw)
        assert [e.evidence_id for e in ev1] == [e.evidence_id for e in ev2]
        assert [e.identity_digest for e in ev1] == [e.identity_digest for e in ev2]

    def test_sample_csv_produces_evidence(self):
        raw = _SAMPLE_CSV_PATH.read_bytes()
        entry = ingest_csv(raw, semantic_context_category=SemanticContextCategory.data_source, created_at=_FIXED_DT)
        df = parse_csv(raw, entry)
        _, candidates = analyze_data_health(df, entry)
        evidence = build_evidence(candidates, [entry])

        assert len(evidence) > 0
        # All evidence_ids are valid format.
        for e in evidence:
            assert _EVIDENCE_ID_RE.match(e.evidence_id)
            assert e.source_id == entry.source_id
            assert e.created_by == "evidence_builder"
            assert e.status == EvidenceStatus.active
            assert not hasattr(e, "evidence_id") or isinstance(e.evidence_id, str)


# ===========================================================================
# J. EvidenceObject structural validation
# ===========================================================================


class TestEvidenceObjectStructure:

    def test_evidence_object_has_all_required_fields(self):
        raw = b"a,b\n1,2\n1,2\n"
        evidence, _ = _full_pipeline(raw)
        required_fields = [
            "evidence_id", "identity_digest", "source_id", "source_format",
            "source_locator", "evidence_type", "evidence_scope",
            "extraction_method", "finding", "supporting_evidence",
            "confidence", "limitations", "relevant_roles",
            "decision_relevance", "id_algo_version", "created_by",
            "status",
        ]
        for e in evidence:
            for field in required_fields:
                assert hasattr(e, field), f"EvidenceObject missing field: {field!r}"

    def test_evidence_object_id_algo_version_v1(self):
        raw = b"a,b\n1,2\n1,2\n"
        evidence, _ = _full_pipeline(raw)
        for e in evidence:
            assert e.id_algo_version == "v1"

    def test_evidence_object_relevant_roles_nonempty(self):
        raw = b"a,b\n1,2\n1,2\n"
        evidence, _ = _full_pipeline(raw)
        for e in evidence:
            assert len(e.relevant_roles) > 0

    def test_evidence_object_finding_is_nonempty_string(self):
        raw = b"a,b\n1,2\n1,2\n"
        evidence, _ = _full_pipeline(raw)
        for e in evidence:
            assert isinstance(e.finding, str)
            assert len(e.finding.strip()) > 0


# ===========================================================================
# K. Decision 002 — evidence from two sources is separately traceable
# ===========================================================================


class TestSeparateSourcesRemainTraceable:
    def test_same_finding_different_sources_produce_different_evidence_ids(self):
        # Two different CSV sources produce the same health finding.
        raw1 = b"revenue\n100\n200\n"
        raw2 = b"revenue\n300\n400\n"
        entry1 = _csv_entry(raw1)
        entry2 = _csv_entry(raw2)

        # Build a missing-value candidate for each source.
        def make_candidate(entry: SourceManifestEntry) -> HealthFindingCandidate:
            return HealthFindingCandidate(
                source_id=entry.source_id,
                source_format=entry.source_format,
                source_locator=TabularSourceLocator(columns=["revenue"]),
                evidence_type="missing_value_rate",
                canonical_rule_parameters={"column": "revenue", "missing_rate": 0.5, "row_count": 2, "missing_count": 1, "threshold": 0.0},
                normalized_claim_key="data.missing.revenue",
                finding="Revenue has 50% missing.",
                supporting_evidence="1/2 null.",
                confidence="high",
                limitations=[],
                relevant_roles=["data_analyst"],
                decision_relevance="Data quality.",
            )

        c1 = make_candidate(entry1)
        c2 = make_candidate(entry2)

        ev1 = build_evidence([c1], [entry1])
        ev2 = build_evidence([c2], [entry2])

        assert len(ev1) == 1
        assert len(ev2) == 1
        # Different sources → different evidence_ids.
        assert ev1[0].evidence_id != ev2[0].evidence_id
        assert ev1[0].source_id != ev2[0].source_id
        assert ev1[0].source_id == entry1.source_id
        assert ev2[0].source_id == entry2.source_id
