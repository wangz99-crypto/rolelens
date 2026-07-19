"""
app/context_evidence.py — RoleLens deterministic context-evidence extractor (Task 5B-2).

Responsibilities:
  - Convert exact pasted industry context and structured form-input context
    into TextEvidenceCandidate records.
  - Register each source via existing intake functions (no hashing here).
  - Produce a ContextEvidenceExtraction result (manifest + candidates + optional
    rejection reason).

Architecture invariants:
  - Does NOT construct EvidenceObject records.
  - Does NOT call build_evidence() or any LLM.
  - Does NOT summarize, paraphrase, or infer company facts.
  - All text-to-candidate conversion is deterministic.
  - Source registration is delegated:
      industry_context              → text_parser.parse_pasted_text()
      strategy_profile / user_assumption / business_question / decision_goal
                                    → file_intake.ingest_form_input()
  - business_question and decision_goal produce a manifest but zero candidates.
  - No private underscore-prefixed constants are imported from app/schemas.py.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import Mapping

from app.file_intake import ingest_form_input
from app.identity import normalize_source_content
from app.schemas import (
    SemanticContextCategory,
    SourceFormat,
    SourceManifestEntry,
    TextEvidenceCandidate,
    TextSourceLocator,
    UserContextLocator,
)
from app.text_parser import parse_pasted_text

# ---------------------------------------------------------------------------
# Categories accepted by this extractor
# ---------------------------------------------------------------------------

_ACCEPTED_CATEGORIES: frozenset[SemanticContextCategory] = frozenset({
    SemanticContextCategory.industry_context,
    SemanticContextCategory.strategy_profile,
    SemanticContextCategory.user_assumption,
    SemanticContextCategory.business_question,
    SemanticContextCategory.decision_goal,
})

# ---------------------------------------------------------------------------
# Locked identity values (local copy — do not import private schema constants)
# ---------------------------------------------------------------------------

_EVIDENCE_TYPE: dict[SemanticContextCategory, str] = {
    SemanticContextCategory.industry_context: "industry_context_statement",
    SemanticContextCategory.strategy_profile: "strategy_priority_statement",
    SemanticContextCategory.user_assumption: "user_assumption_statement",
}

_CLAIM_KEY: dict[SemanticContextCategory, str] = {
    SemanticContextCategory.industry_context: "context.industry_context.paragraph",
    SemanticContextCategory.strategy_profile: "context.strategy_profile.statement",
    SemanticContextCategory.user_assumption: "context.user_assumption.statement",
}

_EXTRACTION_POLICY = "exact_source_statement_v1"

# ---------------------------------------------------------------------------
# Per-category defaults for candidate construction
# ---------------------------------------------------------------------------

_RELEVANT_ROLES: dict[SemanticContextCategory, list[str]] = {
    SemanticContextCategory.industry_context: ["executive", "sales_marketing"],
    SemanticContextCategory.strategy_profile: ["executive", "project_manager", "sales_marketing"],
    SemanticContextCategory.user_assumption: ["data_analyst", "executive", "project_manager", "sales_marketing"],
}

_CONFIDENCE: dict[SemanticContextCategory, str] = {
    SemanticContextCategory.industry_context: "medium",
    SemanticContextCategory.strategy_profile: "high",
    SemanticContextCategory.user_assumption: "low",
}

_LIMITATION: dict[SemanticContextCategory, str] = {
    SemanticContextCategory.industry_context: (
        "External industry context is not company-specific proof; "
        "it describes the broader market and must not be cited as direct evidence "
        "of this organisation's performance or position."
    ),
    SemanticContextCategory.strategy_profile: (
        "This is a stated strategic priority, not verified performance data; "
        "actual execution and outcomes may differ from the stated intent."
    ),
    SemanticContextCategory.user_assumption: (
        "This is an unverified user assumption; it has not been validated against "
        "empirical data and must be flagged for review in risk assessment."
    ),
}

_DECISION_RELEVANCE: dict[SemanticContextCategory, str] = {
    SemanticContextCategory.industry_context: (
        "Provides external market context that frames the decision environment."
    ),
    SemanticContextCategory.strategy_profile: (
        "Defines the stated strategic priority that shapes the decision criteria."
    ),
    SemanticContextCategory.user_assumption: (
        "Records an unvalidated assumption that must be surfaced in risk assessment."
    ),
}


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ContextEvidenceExtraction:
    """Result of a single extract_context_evidence() call.

    Attributes:
        source_manifest:  The SourceManifestEntry registered for this source.
        candidates:       Zero or more TextEvidenceCandidate records derived from
                          the source.  Empty for business_question and decision_goal.
        rejection_reason: None when candidates were produced; a non-blank explanation
                          when the category does not produce EvidenceObjects.
    """

    source_manifest: SourceManifestEntry
    candidates: tuple[TextEvidenceCandidate, ...]
    rejection_reason: str | None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def extract_context_evidence(
    raw_text: str,
    *,
    semantic_context_category: SemanticContextCategory,
    field_name: str,
    created_at: datetime | None = None,
    upload_event_id: str | None = None,
    identity_registry: Mapping[str, str] | None = None,
) -> ContextEvidenceExtraction:
    """Deterministically convert exact context text into TextEvidenceCandidate records.

    Does NOT call any LLM.  Does NOT construct EvidenceObject records.
    Source registration is delegated to existing intake functions.

    Args:
        raw_text:                  Exact source text (must not be blank).
        semantic_context_category: One of: industry_context, strategy_profile,
                                   user_assumption, business_question, decision_goal.
        field_name:                Name of the originating form field or context
                                   field (must not be blank).
        created_at:                Timezone-aware datetime.  Defaults to utc_now()
                                   if not provided.
        upload_event_id:           Optional upload event identifier (metadata only).
        identity_registry:         Optional short_id → identity_digest mapping for
                                   collision detection.  Not mutated.

    Returns:
        ContextEvidenceExtraction containing:
          - source_manifest: registered SourceManifestEntry
          - candidates:      zero or more TextEvidenceCandidate records
          - rejection_reason: None if candidates were produced; explanation if not

    Raises:
        ValueError:  If raw_text is blank, field_name is blank, or category is
                     not supported.
        IdentityCollisionError: Propagated from intake functions.
        ValidationError:        Propagated from schema construction.
    """
    # ---- upfront validation ----
    if not raw_text or not raw_text.strip():
        raise ValueError("raw_text must not be blank or whitespace-only")

    if not field_name or not field_name.strip():
        raise ValueError("field_name must not be blank or whitespace-only")

    if semantic_context_category not in _ACCEPTED_CATEGORIES:
        raise ValueError(
            f"extract_context_evidence does not accept "
            f"semantic_context_category={semantic_context_category.value!r}. "
            f"Accepted: {sorted(c.value for c in _ACCEPTED_CATEGORIES)!r}"
        )

    # ---- category dispatch ----
    if semantic_context_category == SemanticContextCategory.industry_context:
        return _extract_industry_context(
            raw_text=raw_text,
            upload_event_id=upload_event_id,
            created_at=created_at,
            identity_registry=identity_registry,
        )

    if semantic_context_category in (
        SemanticContextCategory.business_question,
        SemanticContextCategory.decision_goal,
    ):
        return _extract_decision_context(
            raw_text=raw_text,
            semantic_context_category=semantic_context_category,
            upload_event_id=upload_event_id,
            created_at=created_at,
            identity_registry=identity_registry,
        )

    # strategy_profile or user_assumption
    return _extract_form_context(
        raw_text=raw_text,
        semantic_context_category=semantic_context_category,
        field_name=field_name,
        upload_event_id=upload_event_id,
        created_at=created_at,
        identity_registry=identity_registry,
    )


# ---------------------------------------------------------------------------
# Internal branch handlers
# ---------------------------------------------------------------------------


def _extract_industry_context(
    raw_text: str,
    *,
    upload_event_id: str | None,
    created_at: datetime | None,
    identity_registry: Mapping[str, str] | None,
) -> ContextEvidenceExtraction:
    """Register the pasted text as pasted_text and extract one candidate per paragraph."""
    cat = SemanticContextCategory.industry_context

    manifest = parse_pasted_text(
        raw_text,
        semantic_context_category=cat,
        source_format=SourceFormat.pasted_text,
        upload_event_id=upload_event_id,
        created_at=created_at,
        identity_registry=identity_registry,
    )

    normalized = normalize_source_content(raw_text)
    paragraphs = _split_paragraphs(normalized)

    candidates: list[TextEvidenceCandidate] = []
    for para_idx, (excerpt, line_start, line_end, char_start, char_end) in enumerate(paragraphs):
        checksum = hashlib.sha256(excerpt.encode("utf-8")).hexdigest()
        locator = TextSourceLocator(
            line_start=line_start,
            line_end=line_end,
            char_start=char_start,
            char_end=char_end,
            paragraph_index=para_idx,
            excerpt_checksum=checksum,
        )
        candidate = TextEvidenceCandidate(
            source_id=manifest.source_id,
            source_format=SourceFormat.pasted_text,
            source_locator=locator,
            semantic_context_category=cat,
            evidence_type=_EVIDENCE_TYPE[cat],
            canonical_rule_parameters={
                "extraction_policy": _EXTRACTION_POLICY,
                "semantic_context_category": cat.value,
            },
            normalized_claim_key=_CLAIM_KEY[cat],
            exact_excerpt=excerpt,
            confidence=_CONFIDENCE[cat],  # type: ignore[arg-type]
            limitations=[_LIMITATION[cat]],
            relevant_roles=_RELEVANT_ROLES[cat],
            decision_relevance=_DECISION_RELEVANCE[cat],
        )
        candidates.append(candidate)

    return ContextEvidenceExtraction(
        source_manifest=manifest,
        candidates=tuple(candidates),
        rejection_reason=None,
    )


def _extract_form_context(
    raw_text: str,
    *,
    semantic_context_category: SemanticContextCategory,
    field_name: str,
    upload_event_id: str | None,
    created_at: datetime | None,
    identity_registry: Mapping[str, str] | None,
) -> ContextEvidenceExtraction:
    """Register as form_input and produce exactly one candidate."""
    cat = semantic_context_category

    manifest = ingest_form_input(
        raw_text,
        semantic_context_category=cat,
        upload_event_id=upload_event_id,
        created_at=created_at,
        identity_registry=identity_registry,
    )

    locator = UserContextLocator(
        field_name=field_name,
        context_category=cat,
    )

    normalized = normalize_source_content(raw_text)

    candidate = TextEvidenceCandidate(
        source_id=manifest.source_id,
        source_format=SourceFormat.form_input,
        source_locator=locator,
        semantic_context_category=cat,
        evidence_type=_EVIDENCE_TYPE[cat],
        canonical_rule_parameters={
            "extraction_policy": _EXTRACTION_POLICY,
            "semantic_context_category": cat.value,
        },
        normalized_claim_key=_CLAIM_KEY[cat],
        exact_excerpt=normalized,
        confidence=_CONFIDENCE[cat],  # type: ignore[arg-type]
        limitations=[_LIMITATION[cat]],
        relevant_roles=_RELEVANT_ROLES[cat],
        decision_relevance=_DECISION_RELEVANCE[cat],
    )

    return ContextEvidenceExtraction(
        source_manifest=manifest,
        candidates=(candidate,),
        rejection_reason=None,
    )


def _extract_decision_context(
    raw_text: str,
    *,
    semantic_context_category: SemanticContextCategory,
    upload_event_id: str | None,
    created_at: datetime | None,
    identity_registry: Mapping[str, str] | None,
) -> ContextEvidenceExtraction:
    """Register as form_input; return zero candidates with a rejection reason."""
    cat = semantic_context_category

    manifest = ingest_form_input(
        raw_text,
        semantic_context_category=cat,
        upload_event_id=upload_event_id,
        created_at=created_at,
        identity_registry=identity_registry,
    )

    rejection_reason = (
        f"semantic_context_category={cat.value!r} provides decision context to the pipeline "
        "but does not produce EvidenceObject records.  "
        "The manifest is registered for provenance tracking only."
    )

    return ContextEvidenceExtraction(
        source_manifest=manifest,
        candidates=(),
        rejection_reason=rejection_reason,
    )


# ---------------------------------------------------------------------------
# Paragraph splitting helpers
# ---------------------------------------------------------------------------


def _split_paragraphs(
    normalized: str,
) -> list[tuple[str, int, int, int, int]]:
    """Split a normalized (LF-only) text into non-blank paragraph spans.

    A paragraph is a maximal run of non-blank lines separated from other
    paragraphs by one or more blank lines.  Blank lines are lines that
    are empty or contain only whitespace.

    Returns a list of tuples:
        (excerpt, line_start, line_end, char_start, char_end)

    All indexes are 0-based and inclusive.
    char_start / char_end are inclusive Python string character indexes
    (not byte offsets) into the normalized string.
    excerpt is the exact substring normalized[char_start : char_end + 1].
    For multi-byte Unicode code-points, len() counts characters, not bytes,
    so slicing with these indexes recovers the exact excerpt regardless of
    the byte width of the characters involved.
    """
    lines = normalized.split("\n")
    paragraphs: list[tuple[str, int, int, int, int]] = []

    # Build a list of (line_index, char_offset_of_line_start) pairs.
    line_offsets: list[int] = []
    offset = 0
    for line in lines:
        line_offsets.append(offset)
        offset += len(line) + 1  # +1 for the '\n'

    i = 0
    n = len(lines)
    while i < n:
        # Skip blank lines.
        if not lines[i].strip():
            i += 1
            continue

        # Start of a paragraph.
        para_start_line = i
        para_start_char = line_offsets[i]

        # Collect all consecutive non-blank lines.
        while i < n and lines[i].strip():
            i += 1

        # i now points to the first blank line after the paragraph (or past end).
        para_end_line = i - 1
        para_end_char = line_offsets[para_end_line] + len(lines[para_end_line]) - 1

        excerpt = normalized[para_start_char : para_end_char + 1]
        paragraphs.append((excerpt, para_start_line, para_end_line, para_start_char, para_end_char))

    return paragraphs
