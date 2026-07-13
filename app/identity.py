"""
app/identity.py — RoleLens deterministic identity and canonicalization (Task 2).

Responsibilities:
  - Normalize source content (UTF-8, BOM-stripped, NFC, LF line endings).
  - Generate a stable hybrid source_id: src-{format_abbrev}-{12_hex}.
  - Generate a stable hybrid evidence_id: ev-{type_abbrev}-{12_hex}.
  - Produce a full SHA-256 identity_digest for collision detection.
  - Serialize SourceLocator and rule-parameter dicts into a deterministic
    canonical string suitable as an identity input.
  - Provide check_identity_collision() for registry-aware collision detection.
    The generators themselves are pure functions; collision checking is explicit.

Architecture invariants enforced here:
  - Identity generation belongs ONLY in this module.
  - utils.py, schemas.py, data_health.py, and evidence_builder.py must NOT
    perform hashing or ID construction independently.
  - Generators are pure: they never consult a registry; callers invoke
    check_identity_collision() separately.
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
from typing import TYPE_CHECKING, Any, Mapping

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
#: 12 hex chars = 48 bits of entropy. At 1 million entries, the
#: birthday-bound probability of at least one short-ID collision is
#: approximately 1.8 × 10⁻³ (0.18%). Full digests and registry checks
#: therefore remain mandatory.
_SHORT_HEX_LEN: int = 12

#: Stable mapping from SourceFormat value to a safe, short abbreviation used
#: in the source_id prefix.  Must match the regex [a-z0-9_]{1,12}.
#: Adding a new SourceFormat REQUIRES a new entry here before that format can
#: produce a source_id.
#: pdf_text is NOT included: it is not an active SourceFormat in V1.
_FORMAT_ABBREV: dict[str, str] = {
    "csv":         "csv",
    "excel":       "xls",
    "pasted_text": "ptxt",
    "txt":         "txt",
    "markdown":    "md",
    "form_input":  "form",
}

#: Regex that a format_abbrev must satisfy (mirrors _SOURCE_ID_RE middle group).
_ABBREV_RE = re.compile(r"^[a-z0-9_]{1,12}$")

# Pipe character used as field separator in identity input strings.  Must not
# appear naturally in any of the identity fields.
_SEP = "|"

# Compiled regexes for public-API input validation (mirrored from schemas.py).
_SOURCE_ID_RE = re.compile(r"^src-[a-z0-9_]{1,12}-[0-9a-f]{12}$")
_ID_ALGO_VERSION_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,31}$")
_EVIDENCE_TYPE_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_CLAIM_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*$")
_CLAIM_KEY_MAX_LEN = 128


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class IdentityCollisionError(Exception):
    """Raised when a short ID is already registered under a different identity_digest.

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
    """Return a deterministic compact JSON string for a value.

    Rules:
      - dict keys are recursively sorted (all nesting depths).
      - No indentation or trailing spaces (compact separators).
      - ensure_ascii=False for Unicode-preserving identity inputs.
      - allow_nan=False: NaN and Infinity are rejected.

    Args:
        value: A JSON-serializable value (dict, list, str, int, float, bool,
               None).

    Returns:
        Canonical JSON string.

    Raises:
        TypeError: If value contains a non-JSON-serializable type.
        ValueError: If value contains NaN or Infinity floats.
    """
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _validate_json_params(value: Any, path: str = "root") -> None:
    """Recursively validate that a value is JSON-compatible for rule parameters.

    Allowed leaf types: None, bool, int, finite float, str.
    Allowed container types: list, dict with str keys only.

    Rejected at every nesting level:
      - non-string dict keys
      - tuple, set, frozenset
      - bytes, bytearray
      - complex
      - NaN, +Infinity, -Infinity
      - any other custom object

    Args:
        value: The value to validate.
        path:  Human-readable path string for error messages.

    Raises:
        ValueError: If value contains a non-JSON-compatible type or non-finite float.
    """
    import math

    if value is None or isinstance(value, bool) or isinstance(value, str):
        return
    if isinstance(value, int):
        # bool is a subclass of int — already handled above.
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(
                f"canonicalize_rule_parameters: non-finite float {value!r} "
                f"at {path}; NaN, Infinity, and -Infinity are not valid JSON values"
            )
        return
    if isinstance(value, list):
        for i, item in enumerate(value):
            _validate_json_params(item, path=f"{path}[{i}]")
        return
    if isinstance(value, dict):
        for k, v in value.items():
            if not isinstance(k, str):
                raise ValueError(
                    f"canonicalize_rule_parameters: dict key must be str, "
                    f"got {type(k).__name__!r} at {path}"
                )
            _validate_json_params(v, path=f"{path}.{k}")
        return
    # Anything else: tuple, set, frozenset, bytes, bytearray, complex, custom…
    raise ValueError(
        f"canonicalize_rule_parameters: unsupported type {type(value).__name__!r} "
        f"at {path}; only None, bool, int, finite float, str, list, and "
        f"dict with string keys are permitted"
    )


def canonicalize_locator(locator: Any) -> str:
    """Serialize a SourceLocator (Pydantic model) into a canonical string.

    All inputs — both Pydantic models and plain dicts — are validated through
    TypeAdapter(SourceLocator) before canonicalization, so that arbitrary
    Pydantic models are rejected.

    The locator_type discriminator field is included in the output so that
    TabularSourceLocator and TextSourceLocator with identical non-type fields
    do not collide.

    Args:
        locator: A SourceLocator instance (TabularSourceLocator,
                 TextSourceLocator, or UserContextLocator) OR a plain dict
                 that conforms to one of those subtypes.

    Returns:
        Canonical JSON string suitable as an identity input.

    Raises:
        TypeError:        If locator is not a Pydantic model or dict.
        ValidationError:  If the locator fails SourceLocator schema validation.
    """
    from pydantic import TypeAdapter
    from app.schemas import SourceLocator as _SourceLocator

    _ta = TypeAdapter(_SourceLocator)

    if hasattr(locator, "model_dump"):
        # Validate the model through TypeAdapter — rejects arbitrary BaseModel
        # subclasses that are not valid SourceLocator members.
        validated = _ta.validate_python(locator.model_dump())
    elif isinstance(locator, dict):
        validated = _ta.validate_python(locator)
    else:
        raise TypeError(
            f"canonicalize_locator requires a SourceLocator Pydantic model or dict, "
            f"got {type(locator).__name__!r}"
        )
    return _canonical_json(validated.model_dump())


def canonicalize_rule_parameters(params: dict[str, Any]) -> str:
    """Serialize canonical_rule_parameters into a deterministic string.

    Requires a dict and recursively validates that all keys are str and all
    values are JSON-compatible (None, bool, int, finite float, str, list, or
    dict with string keys).  Rejects at every nesting level: non-string dict
    keys, tuple, set, frozenset, bytes, bytearray, complex, NaN, Infinity, and
    arbitrary custom objects.

    Args:
        params: A dict with string keys and recursively JSON-compatible values.

    Returns:
        Canonical compact JSON string (keys sorted, no whitespace).

    Raises:
        ValueError: If params is not a dict, or contains a non-string key or
                    an unsupported / non-finite value at any nesting depth.
    """
    if not isinstance(params, dict):
        raise ValueError(
            f"canonicalize_rule_parameters: expected a dict, "
            f"got {type(params).__name__!r}"
        )
    _validate_json_params(params, path="root")
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
    """Derive a stable abbreviation from an already-valid evidence_type_key.

    Truncates the first 12 characters of the key.  Because evidence_type_key
    is validated by _EVIDENCE_TYPE_RE (^[a-z][a-z0-9_]{0,63}$) before this
    function is called, only lowercase alphanumerics and underscores are
    present.  No character replacement is performed: the caller must not pass
    invalid keys.

    Args:
        evidence_type_key: A validated evidence_type string (all lowercase,
                           starts with [a-z], contains only [a-z0-9_]).

    Returns:
        1–12 character abbreviation.

    Raises:
        ValueError: If the key is empty.
    """
    if not evidence_type_key:
        raise ValueError(
            "evidence_type_key must not be empty."
        )
    return evidence_type_key[:_SHORT_HEX_LEN]


# ---------------------------------------------------------------------------
# Public API: check_identity_collision
# ---------------------------------------------------------------------------


def check_identity_collision(
    short_id: str,
    identity_digest: str,
    existing_identities: Mapping[str, str],
) -> None:
    """Check a (short_id, identity_digest) pair against a registry.

    Registry rules:
      - short_id absent from registry: no error.
      - short_id present with the same digest: no error (same identity).
      - short_id present with a different digest: IdentityCollisionError.

    Two different short IDs are never reported as a collision, regardless of
    their digest values.

    Args:
        short_id:             The short ID to check (src-… or ev-…).
        identity_digest:      The newly computed full SHA-256 digest.
        existing_identities:  A mapping of short_id → identity_digest
                              representing the current registry state.

    Raises:
        IdentityCollisionError: If short_id is registered under a different
                                identity_digest.
    """
    existing = existing_identities.get(short_id)
    if existing is not None and existing != identity_digest:
        raise IdentityCollisionError(
            short_id=short_id,
            existing_digest=existing,
            new_digest=identity_digest,
        )


# ---------------------------------------------------------------------------
# Public API: generate_source_id
# ---------------------------------------------------------------------------


def generate_source_id(
    *,
    source_format: str,
    semantic_context_category: str,
    normalized_content: str,
    id_algo_version: str = IDENTITY_ALGO_VERSION,
) -> tuple[str, str]:
    """Generate a stable hybrid source_id and full SHA-256 identity_digest.

    Identity inputs (pipe-delimited, then SHA-256 hashed):
        id_algo_version | source_format | semantic_context_category | normalized_content

    Short ID format: src-{format_abbrev}-{first_12_hex_of_digest}

    All inputs are validated before hashing:
      - source_format must be a registered active SourceFormat value.
      - semantic_context_category must be a valid SemanticContextCategory value.
      - id_algo_version must match ^[a-z0-9][a-z0-9._-]{0,31}$.
      - normalized_content must be a str.

    Args:
        source_format:            SourceFormat enum value string (e.g. "csv").
        semantic_context_category: SemanticContextCategory enum value string.
        normalized_content:       Already-normalized source content string
                                  (call normalize_source_content first).
        id_algo_version:          Identity algorithm version tag.  Default "v1".

    Returns:
        (source_id, identity_digest) where:
          - source_id is "src-{abbrev}-{12 hex chars}"
          - identity_digest is the full 64-char lowercase SHA-256 hex string

    Raises:
        ValueError: If any input fails validation.
    """
    # --- Validate inputs ---
    from app.schemas import SourceFormat as _SourceFormat, SemanticContextCategory as _SCC

    # source_format must be a registered active SourceFormat.
    try:
        _SourceFormat(source_format)
    except ValueError:
        raise ValueError(
            f"source_format {source_format!r} is not a valid active SourceFormat value. "
            f"Valid values: {[m.value for m in _SourceFormat]}"
        )

    # semantic_context_category must be a valid SemanticContextCategory.
    try:
        _SCC(semantic_context_category)
    except ValueError:
        raise ValueError(
            f"semantic_context_category {semantic_context_category!r} is not a valid "
            f"SemanticContextCategory value. "
            f"Valid values: {[m.value for m in _SCC]}"
        )

    # id_algo_version must match the approved syntax.
    if not _ID_ALGO_VERSION_RE.match(id_algo_version):
        raise ValueError(
            f"id_algo_version must match ^[a-z0-9][a-z0-9._-]{{0,31}}$, "
            f"got: {id_algo_version!r}"
        )

    # normalized_content must be a str.
    if not isinstance(normalized_content, str):
        raise ValueError(
            f"normalized_content must be a str, got {type(normalized_content).__name__}"
        )

    # --- Build short ID ---
    abbrev = _format_abbrev(source_format)

    identity_input = _SEP.join([
        id_algo_version,
        source_format,
        semantic_context_category,
        normalized_content,
    ])

    digest = _sha256_hex(identity_input)
    short_id = f"src-{abbrev}-{digest[:_SHORT_HEX_LEN]}"

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
) -> tuple[str, str]:
    """Generate a stable hybrid evidence_id and full SHA-256 identity_digest.

    Identity inputs (pipe-delimited, then SHA-256 hashed):
        id_algo_version | source_id | evidence_type_key |
        canonical_source_locator | canonical_rule_parameters | normalized_claim_key

    Free-form 'finding' and 'explanation' text are NOT identity inputs.

    Short ID format: ev-{evidence_type_abbrev}-{first_12_hex_of_digest}

    All inputs are validated before hashing:
      - source_id must match src-[a-z0-9_]{1,12}-[0-9a-f]{12}.
      - evidence_type_key must match ^[a-z][a-z0-9_]{0,63}$.
      - normalized_claim_key must match ^[a-z][a-z0-9_]*(\\.[a-z][a-z0-9_]*)*$
        and must not exceed 128 characters.
      - id_algo_version must match ^[a-z0-9][a-z0-9._-]{0,31}$.
      - canonical_source_locator and canonical_rule_parameters must be
        valid canonical JSON strings.

    Args:
        source_id:                  source_id of the originating source.
        evidence_type_key:          Validated evidence_type string (rule key).
        canonical_source_locator:   Output of canonicalize_locator().
        canonical_rule_parameters:  Output of canonicalize_rule_parameters().
        normalized_claim_key:       Stable dot-separated claim key string.
        id_algo_version:            Identity algorithm version tag.  Default "v1".

    Returns:
        (evidence_id, identity_digest) where:
          - evidence_id is "ev-{abbrev}-{12 hex chars}"
          - identity_digest is the full 64-char lowercase SHA-256 hex string

    Raises:
        ValueError: If any input fails validation.
    """
    # --- Validate inputs ---

    # source_id format.
    if not _SOURCE_ID_RE.match(source_id):
        raise ValueError(
            f"source_id must match src-[a-z0-9_]{{1,12}}-[0-9a-f]{{12}}, "
            f"got: {source_id!r}"
        )

    # evidence_type_key syntax.
    if not _EVIDENCE_TYPE_RE.match(evidence_type_key):
        raise ValueError(
            f"evidence_type_key must match ^[a-z][a-z0-9_]{{0,63}}$, "
            f"got: {evidence_type_key!r}"
        )

    # normalized_claim_key syntax.
    if len(normalized_claim_key) > _CLAIM_KEY_MAX_LEN:
        raise ValueError(
            f"normalized_claim_key must not exceed {_CLAIM_KEY_MAX_LEN} characters, "
            f"got {len(normalized_claim_key)}"
        )
    if not _CLAIM_KEY_RE.match(normalized_claim_key):
        raise ValueError(
            f"normalized_claim_key must match "
            f"^[a-z][a-z0-9_]*(\\.[a-z][a-z0-9_]*)*$, got: {normalized_claim_key!r}"
        )

    # id_algo_version syntax.
    if not _ID_ALGO_VERSION_RE.match(id_algo_version):
        raise ValueError(
            f"id_algo_version must match ^[a-z0-9][a-z0-9._-]{{0,31}}$, "
            f"got: {id_algo_version!r}"
        )

    # canonical_source_locator: must be a str, parse to a valid SourceLocator,
    # re-canonicalize, and require exact match.
    if not isinstance(canonical_source_locator, str):
        raise ValueError(
            f"canonical_source_locator must be a str, "
            f"got {type(canonical_source_locator).__name__!r}"
        )
    try:
        _parsed_locator = json.loads(canonical_source_locator)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"canonical_source_locator must be valid JSON; "
            f"got: {canonical_source_locator!r} — {exc}"
        ) from exc
    # Validate the parsed object through the SourceLocator schema and re-canonicalize.
    try:
        _recanon_locator = canonicalize_locator(_parsed_locator)
    except Exception as exc:
        raise ValueError(
            f"canonical_source_locator does not represent a valid SourceLocator; "
            f"got: {canonical_source_locator!r} — {exc}"
        ) from exc
    if canonical_source_locator != _recanon_locator:
        raise ValueError(
            f"canonical_source_locator is not in canonical form.  "
            f"Expected: {_recanon_locator!r}  Got: {canonical_source_locator!r}.  "
            "Pass the output of canonicalize_locator() directly."
        )

    # canonical_rule_parameters: must be a str, parse to a JSON object, recursively
    # validate values, re-canonicalize, and require exact match.
    if not isinstance(canonical_rule_parameters, str):
        raise ValueError(
            f"canonical_rule_parameters must be a str, "
            f"got {type(canonical_rule_parameters).__name__!r}"
        )
    try:
        _parsed_params = json.loads(canonical_rule_parameters)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"canonical_rule_parameters must be valid JSON; "
            f"got: {canonical_rule_parameters!r} — {exc}"
        ) from exc
    if not isinstance(_parsed_params, dict):
        raise ValueError(
            f"canonical_rule_parameters must be a JSON object (dict), "
            f"got {type(_parsed_params).__name__!r}: {canonical_rule_parameters!r}"
        )
    # Recursively validate JSON-compatibility and re-canonicalize.
    try:
        _recanon_params = canonicalize_rule_parameters(_parsed_params)
    except Exception as exc:
        raise ValueError(
            f"canonical_rule_parameters contains invalid values; "
            f"got: {canonical_rule_parameters!r} — {exc}"
        ) from exc
    if canonical_rule_parameters != _recanon_params:
        raise ValueError(
            f"canonical_rule_parameters is not in canonical form.  "
            f"Expected: {_recanon_params!r}  Got: {canonical_rule_parameters!r}.  "
            "Pass the output of canonicalize_rule_parameters() directly."
        )

    # --- Build short ID ---
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

    return short_id, digest
