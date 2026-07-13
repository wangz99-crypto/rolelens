"""
app/utils.py — RoleLens shared helpers (Task 3).

Responsibilities:
  - Produce timezone-aware UTC datetime objects (required by SourceManifestEntry).
  - Serialize Pydantic models and plain dicts to JSON strings.
  - Persist run-log JSON to outputs/run_logs/.

Architecture invariants:
  - No identity generation, no hashing, no business logic here.
  - Identity generation belongs exclusively in app/identity.py.
  - All datetime values produced here are timezone-aware UTC.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Default directory for run-log output files.  Relative to the project root.
_RUN_LOG_DIR = Path("outputs") / "run_logs"


# ---------------------------------------------------------------------------
# Timestamp helpers
# ---------------------------------------------------------------------------


def utc_now() -> datetime:
    """Return the current time as a timezone-aware UTC datetime.

    Used as the default ``created_at`` value for SourceManifestEntry records.
    The intake layer is responsible for calling this function; schemas.py only
    validates that the datetime is timezone-aware.

    Returns:
        Current UTC datetime with tzinfo=timezone.utc.
    """
    return datetime.now(tz=timezone.utc)


# ---------------------------------------------------------------------------
# JSON serialization
# ---------------------------------------------------------------------------


def _default_json_serializer(obj: Any) -> Any:
    """JSON serializer for types not handled by the standard library.

    Supports:
      - datetime → ISO 8601 string (always includes timezone offset).
      - Pydantic BaseModel → .model_dump() dict.

    Raises:
        TypeError: For any other unserializable type.
    """
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, BaseModel):
        return obj.model_dump()
    raise TypeError(f"Object of type {type(obj).__name__!r} is not JSON serializable")


def to_json_str(obj: Any, *, indent: int | None = None) -> str:
    """Serialize an object to a JSON string.

    Args:
        obj:    Any JSON-serializable object, Pydantic model, or datetime.
        indent: Optional indentation for pretty-printing.

    Returns:
        JSON string.

    Raises:
        TypeError: If obj contains a non-serializable type.
    """
    return json.dumps(obj, default=_default_json_serializer, ensure_ascii=True, indent=indent)


# ---------------------------------------------------------------------------
# Run-log persistence
# ---------------------------------------------------------------------------


def save_run_log(
    log_data: Any,
    *,
    filename: str,
    log_dir: Path | str | None = None,
) -> Path:
    """Persist a run-log payload as a JSON file.

    The function creates the log directory and any intermediate directories if
    they do not exist.  It does not overwrite an existing file with the same
    name without warning, but it will overwrite if the path already exists
    (write-once semantics are the caller's responsibility).

    Args:
        log_data:  Any JSON-serializable object.
        filename:  Filename for the log file (must end with '.json').
        log_dir:   Directory in which to write the file.  Defaults to
                   ``outputs/run_logs/`` relative to the current working
                   directory.

    Returns:
        Resolved Path of the written file.

    Raises:
        ValueError: If filename does not end with '.json'.
        OSError:    If the directory cannot be created or the file cannot be
                    written.
    """
    if not filename.endswith(".json"):
        raise ValueError(
            f"Run log filename must end with '.json', got {filename!r}."
        )

    target_dir = Path(log_dir) if log_dir is not None else _RUN_LOG_DIR
    target_dir.mkdir(parents=True, exist_ok=True)

    target_path = target_dir / filename
    json_str = to_json_str(log_data, indent=2)
    target_path.write_text(json_str, encoding="utf-8")
    return target_path.resolve()
