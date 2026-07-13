"""
app/identity.py — RoleLens deterministic identity and canonicalization (Task 2).

Responsibilities:
  - Normalize source content (UTF-8, BOM-stripped, NFC, LF line endings).
  - Generate a stable hybrid source_id: src-{format_abbrev}-{12_hex}.
  - Generate a stable hybrid evidence_id: ev-{type_abbrev}-{12_hex}.
  - Produce a full SHA-256 identity_digest for collision detection.
  - Serialize SourceLocator and rule-parameter dicts into a deterministic
    canonical string suitable as an identity input.
  - Raise IdentityCollisionError when a short ID matches an existing entry
    but the full identity_digest differs.

Architecture invariants enforced here:
  - Identity generation belongs ONLY in this module.
  - utils.py, schemas.py, data_health.py, and evidence_builder.py must NOT
    perform hashing or ID construction independently.
  - No in-memory-only collision registry: callers must persist (short_id,
    identity_digest) pairs and pass the known digest when checking collisions.
  - Free-form 'finding' and 'explanation' text are NOT identity inputs.
  - Normalization is order-preserving: no row, column, section, or key
    reordering is applied beyond JSON key-sort for dict canonicalization.

Decision 002 contract references:
  source_id identity inputs:  id_algo_version | source_format | semantic_context_category | normalized_content
  evidence_id identity inputs: id_algo_version | source_id | evidence_type_key | canonical_source_locator | canonical_rule_parameters | normalized_claim_key
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    # Avoid a circular import at runtime; schemas imports nothing from identity.
    from app.schemas import SourceFormat, SemanticContextCategory, SourceLocator

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Algorithm version string embedded in every identity input string.
#: Changing this value changes ALL IDs produced by this module, which is the
#: intended migration mechanism when the hashing algorithm or normalization
#: rules change.
IDENTITY_ALGO_VERSION: str = "v1"

#: Number of hex characters taken from the SHA-256 digest to form the short ID
#: suffix.  12 hex chars = 48 bits of entropy.  Collision probability at
#: 1 million entries ≈ 1.7 × 10⁻⁷ (birthday bound).  Acceptable for V1.
_SHORT_HEX_LEN: int = 12

#: Stable mapping from SourceFormat value to a safe, short abbreviation used
#: in the source_id prefix.  Must match the regex [a-z0-9_]{1,12}.
#: Adding a new SourceFormat REQUIRES a new entry here before that format can
#: produce a source_id.
_FORMAT_ABBREV: dict[str, str] = {
    "csv":         "csv",
    "excel":       "xls",
    "pasted_text": "ptxt",
    "txt":         "txt",
    "markdown":    "md",
    "form_input":  "form",
    # pdf_text is delayed optional; include now so intake cannot silently fall
    # through to the _unknown branch if it is ever mistakenly passed.
    "pdf_text":    "pdf",
}

#: Regex that a format_abbrev must satisfy (mirrors _SOURCE_ID_RE middle group).
_ABBREV_RE = re.compile(r"^[a-z0-9_]{1,12}$")

# Pipe character used as field separator in identity input strings.  Must not
# appear naturally in any of the identity fields.
_SEP = "|"


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class IdentityCollisionError(Exception):
    """Raised when a newly computed short ID matches an existing entry whose
    full identity_digest is different from the newly computed digest.

    This indicates a 48-bit hash collision in the short ID suffix, which is an
    extremely rare event.  The caller must NOT silently resolve this: it must
    surface the error and abort the current operation.

    Attributes:
        short_id:          The colliding short ID (src-… or ev-…).
        existing_digest:   The full SHA-256 digest of the previously stored entry.
        new_digest:        The full SHA-256 digest of the new entry that triggered
                           the collision.
    """

    def __init__(self, short_id: str, existing_digest: str, new_digest: str) -> None:
        self.short_id = short_id
        self.existing_digest = existing_digest
        self.new_digest = new_digest
        super().__init__(
            f"Identity collision on '{short_id}': "
            f"existing_digest={existing_digest!r} != new_digest={new_digest!r}.  "
            "Existing entry was NOT overwritten.  "
            "Abort the current operation and inspect the collision."
        )


# ---------------------------------------------------------------------------
# Content normalization
# ---------------------------------------------------------------------------


def normalize_source_content(raw: str | bytes) -> str:
    """Normalize source content to a canonical string form.

    Normalization steps (order-preserving — no row, column, section, or
    record reordering is applied):
      1. Decode bytes as UTF-8 (strict) if not already a str.
      2. Strip UTF-8 BOM (U+FEFF) from the start.
      3. Apply Unicode NFC normalization.
      4. Normalize line endings to LF (\\n).

    Args:
        raw: Raw source content as bytes or str.

    Returns:
        Normalized str ready to be used as an identity input.

    Raises:
        ValueError: If bytes cannot be decoded as UTF-8.
    """
    if isinstance(raw, bytes):
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError(
                f"Source content is not valid UTF-8: {exc}"
            ) from exc
    else:
        text = raw

    # Strip BOM.
    text = text.lstrip("\ufeff")

    # NFC normalization.
    text = unicodedata.normalize("NFC", text)

    # Normalize line endings: CRLF → LF, then lone CR → LF.
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    return text


# ---------------------------------------------------------------------------
# Canonical serialization helpers
# ---------------------------------------------------------------------------


def _canonical_json(value: Any) -> str:
    """Return a deterministic JSON string for a dict or list value.

    Rules:
      - dict keys are recursively sorted (all nesting depths).
      - No indentation or trailing spaces.
      - ensure_ascii=True for cross-platform byte-level determinism.
      - NaN and Infinity are rejected by json.dumps default (allow_nan=False).

    Args:
        value: A JSON-serializable value (dict, list, str, int, float, bool,
               None).

    Returns:
        Canonical JSON string.

    Raises:
        TypeError: If value contains a non-JSON-serializable type.
        ValueError: If value contains NaN or Infinity floats.
    """
    return json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False)


def canonicalize_locator(locator: Any) -> str:
    """Serialize a SourceLocator (Pydantic model) into a canonical string.

    Uses the model's .model_dump() output (which is a plain dict), then
    applies _canonical_json for deterministic key-sorted JSON.

    The locator_type discriminator field is included in the output so that
    TabularSourceLocator and TextSourceLocator with identical non-type fields
    do not collide.

    Args:
        locator: A SourceLocator instance (TabularSourceLocator,
                 TextSourceLocator, or UserContextLocator).  Also accepts a
                 plain dict for testing convenience.

    Returns:
        Canonical JSON string suitable as an identity input.
    """
    if hasattr(locator, "model_dump"):
        locator_dict = locator.model_dump()
    elif isinstance(locator, dict):
        locator_dict = locator
    else:
        raise TypeError(
            f"canonicalize_locator requires a Pydantic model or dict, "
            f"got {type(locator).__name__!r}"
        )
    return _canonical_json(locator_dict)


def canonicalize_rule_parameters(params: dict[str, Any]) -> str:
    """Serialize canonical_rule_parameters into a deterministic string.

    Args:
        params: A dict that has already passed HealthFindingCandidate
                canonical_rule_parameters validation (no NaN, no Infinity,
                no non-JSON types).

    Returns:
        Canonical JSON string.

    Raises:
        TypeError: If params contains a non-JSON-serializable type.
        ValueError: If params contains NaN or Infinity.
    """
    return _canonical_json(params)


# ---------------------------------------------------------------------------
# SHA-256 hashing helper
# ---------------------------------------------------------------------------


def _sha256_hex(data: str) -> str:
    """Return the lowercase hex SHA-256 digest of a UTF-8 encoded string."""
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Format abbreviation lookup
# ---------------------------------------------------------------------------


def _format_abbrev(source_format_value: str) -> str:
    """Return the stable abbreviation for a SourceFormat value.

    Args:
        source_format_value: The string value of a SourceFormat enum member
                             (e.g. "csv", "excel", "pasted_text").

    Returns:
        Short abbreviation string, e.g. "csv", "xls", "ptxt".

    Raises:
        ValueError: If the format value has no registered abbreviation.
    """
    abbrev = _FORMAT_ABBREV.get(source_format_value)
    if abbrev is None:
        raise ValueError(
            f"No stable abbreviation registered for SourceFormat {source_format_value!r}.  "
            "Add an entry to _FORMAT_ABBREV in app/identity.py."
        )
    return abbrev


def _evidence_type_abbrev(evidence_type_key: str) -> str:
    """Derive a stable, safe abbreviation from an evidence_type_key.

    The abbreviation is the first 12 characters of the key, lowercased,
    with any character outside [a-z0-9_] replaced by '_'.  This matches
    the regex [a-z0-9_]{1,12} required by the evidence_id format.

    Because evidence_type_key is already validated by _EVIDENCE_TYPE_RE
    (^[a-z][a-z0-9_]{0,63}$), only alphanumeric characters and underscores
    are present; the sanitization step is a belt-and-suspenders guard.

    Args:
        evidence_type_key: A validated evidence_type string.

    Returns:
        1–12 character abbreviation.

    Raises:
        ValueError: If the key is empty after sanitization.
    """
    sanitized = re.sub(r"[^a-z0-9_]", "_", evidence_type_key.lower())
    abbrev = sanitized[:_SHORT_HEX_LEN]
    if not abbrev:
        raise ValueError(
            f"evidence_type_key {evidence_type_key!r} produced an empty abbreviation."
        )
    return abbrev


# ---------------------------------------------------------------------------
# Public API: generate_source_id
# ---------------------------------------------------------------------------


def generate_source_id(
    *,
    source_format: str,
    semantic_context_category: str,
    normalized_content: str,
    id_algo_version: str = IDENTITY_ALGO_VERSION,
    existing_digest: str | None = None,
) -> tuple[str, str]:
    """Generate a stable hybrid source_id and full SHA-256 identity_digest.

    Identity inputs (pipe-delimited, then SHA-256 hashed):
        id_algo_version | source_format | semantic_context_category | normalized_content

    Short ID format: src-{format_abbrev}-{first_12_hex_of_digest}

    Args:
        source_format:            SourceFormat enum value string (e.g. "csv").
        semantic_context_category: SemanticContextCategory enum value string.
        normalized_content:       Already-normalized source content string
                                  (call normalize_source_content first).
        id_algo_version:          Identity algorithm version tag.  Default "v1".
        existing_digest:          If the caller has previously stored a digest
                                  for this short_id, pass it here to trigger
                                  IdentityCollisionError if it differs from the
                                  newly computed digest.

    Returns:
        (source_id, identity_digest) where:
          - source_id is "src-{abbrev}-{12 hex chars}"
          - identity_digest is the full 64-char lowercase SHA-256 hex string

    Raises:
        ValueError: If source_format has no registered abbreviation.
        IdentityCollisionError: If existing_digest is provided and differs from
                                the newly computed digest.
    """
    abbrev = _format_abbrev(source_format)

    identity_input = _SEP.join([
        id_algo_version,
        source_format,
        semantic_context_category,
        normalized_content,
    ])

    digest = _sha256_hex(identity_input)
    short_id = f"src-{abbrev}-{digest[:_SHORT_HEX_LEN]}"

    if existing_digest is not None and existing_digest != digest:
        raise IdentityCollisionError(
            short_id=short_id,
            existing_digest=existing_digest,
            new_digest=digest,
        )

    return short_id, digest


# ---------------------------------------------------------------------------
# Public API: generate_evidence_id
# ---------------------------------------------------------------------------


def generate_evidence_id(
    *,
    source_id: str,
    evidence_type_key: str,
    canonical_source_locator: str,
    canonical_rule_parameters: str,
    normalized_claim_key: str,
    id_algo_version: str = IDENTITY_ALGO_VERSION,
    existing_digest: str | None = None,
) -> tuple[str, str]:
    """Generate a stable hybrid evidence_id and full SHA-256 identity_digest.

    Identity inputs (pipe-delimited, then SHA-256 hashed):
        id_algo_version | source_id | evidence_type_key |
        canonical_source_locator | canonical_rule_parameters | normalized_claim_key

    Free-form 'finding' and 'explanation' text are NOT identity inputs.

    Short ID format: ev-{evidence_type_abbrev}-{first_12_hex_of_digest}

    Args:
        source_id:                  source_id of the originating source.
        evidence_type_key:          Validated evidence_type string (rule key).
        canonical_source_locator:   Output of canonicalize_locator().
        canonical_rule_parameters:  Output of canonicalize_rule_parameters().
        normalized_claim_key:       Stable dot-separated claim key string.
        id_algo_version:            Identity algorithm version tag.  Default "v1".
        existing_digest:            If the caller has previously stored a digest
                                    for this short_id, pass it here to trigger
                                    IdentityCollisionError if it differs.

    Returns:
        (evidence_id, identity_digest) where:
          - evidence_id is "ev-{abbrev}-{12 hex chars}"
          - identity_digest is the full 64-char lowercase SHA-256 hex string

    Raises:
        IdentityCollisionError: If existing_digest differs from the newly
                                computed digest.
    """
    type_abbrev = _evidence_type_abbrev(evidence_type_key)

    identity_input = _SEP.join([
        id_algo_version,
        source_id,
        evidence_type_key,
        canonical_source_locator,
        canonical_rule_parameters,
        normalized_claim_key,
    ])

    digest = _sha256_hex(identity_input)
    short_id = f"ev-{type_abbrev}-{digest[:_SHORT_HEX_LEN]}"

    if existing_digest is not None and existing_digest != digest:
        raise IdentityCollisionError(
            short_id=short_id,
            existing_digest=existing_digest,
            new_digest=digest,
        )

    return short_id, digest
