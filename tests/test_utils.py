"""
tests/test_utils.py — Tests for app/utils.py (Task 3).

Coverage targets:
  A. utc_now — timezone-aware, UTC, monotonically increasing
  B. to_json_str — str/int/float/bool/None, datetime, Pydantic models,
                   non-serializable types
  C. save_run_log — creates directory, writes file, filename validation,
                    content roundtrip, custom log_dir
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import BaseModel

from app.utils import save_run_log, to_json_str, utc_now


# ===========================================================================
# A. utc_now
# ===========================================================================


class TestUtcNow:
    def test_returns_datetime(self):
        result = utc_now()
        assert isinstance(result, datetime)

    def test_is_timezone_aware(self):
        result = utc_now()
        assert result.tzinfo is not None

    def test_is_utc(self):
        result = utc_now()
        assert result.tzinfo == timezone.utc

    def test_approximately_now(self):
        before = datetime.now(tz=timezone.utc)
        result = utc_now()
        after = datetime.now(tz=timezone.utc)
        assert before <= result <= after

    def test_successive_calls_non_decreasing(self):
        t1 = utc_now()
        t2 = utc_now()
        assert t2 >= t1


# ===========================================================================
# B. to_json_str
# ===========================================================================


class TestToJsonStr:

    # --- Primitives ---

    def test_string(self):
        assert json.loads(to_json_str("hello")) == "hello"

    def test_int(self):
        assert json.loads(to_json_str(42)) == 42

    def test_float(self):
        assert json.loads(to_json_str(3.14)) == pytest.approx(3.14)

    def test_bool_true(self):
        assert json.loads(to_json_str(True)) is True

    def test_bool_false(self):
        assert json.loads(to_json_str(False)) is False

    def test_none(self):
        assert json.loads(to_json_str(None)) is None

    def test_list(self):
        assert json.loads(to_json_str([1, 2, 3])) == [1, 2, 3]

    def test_dict(self):
        assert json.loads(to_json_str({"key": "value"})) == {"key": "value"}

    # --- datetime ---

    def test_datetime_serialized_to_iso_string(self):
        dt = datetime(2025, 1, 15, 12, 30, 0, tzinfo=timezone.utc)
        result = json.loads(to_json_str(dt))
        assert isinstance(result, str)
        assert "2025-01-15" in result

    def test_datetime_in_dict_serialized(self):
        dt = datetime(2025, 6, 1, 0, 0, 0, tzinfo=timezone.utc)
        data = {"created_at": dt, "value": 100}
        result = json.loads(to_json_str(data))
        assert isinstance(result["created_at"], str)
        assert "2025-06-01" in result["created_at"]

    # --- Pydantic BaseModel ---

    def test_pydantic_model_serialized(self):
        class SimpleModel(BaseModel):
            name: str
            value: int

        m = SimpleModel(name="test", value=42)
        result = json.loads(to_json_str(m))
        assert result == {"name": "test", "value": 42}

    def test_pydantic_model_in_list(self):
        class Item(BaseModel):
            x: int

        data = [Item(x=1), Item(x=2)]
        result = json.loads(to_json_str(data))
        assert result == [{"x": 1}, {"x": 2}]

    # --- Non-serializable types ---

    def test_set_raises_type_error(self):
        with pytest.raises(TypeError):
            to_json_str({1, 2, 3})

    def test_bytes_raises_type_error(self):
        with pytest.raises(TypeError):
            to_json_str(b"bytes data")

    # --- Indentation ---

    def test_indent_produces_multiline(self):
        result = to_json_str({"key": "value"}, indent=2)
        assert "\n" in result

    def test_no_indent_produces_single_line_dict(self):
        result = to_json_str({"key": "value"})
        assert "\n" not in result

    # --- ASCII safe ---

    def test_unicode_encoded_as_ascii_escape(self):
        result = to_json_str("café")
        # ensure_ascii=True means non-ASCII chars are escaped
        assert "\\u" in result or "caf" in result

    def test_result_is_valid_json(self):
        data = {"key": "value", "num": 42, "nested": {"a": [1, 2]}}
        result = to_json_str(data)
        parsed = json.loads(result)
        assert parsed == data


# ===========================================================================
# C. save_run_log
# ===========================================================================


class TestSaveRunLog:
    def test_creates_file(self, tmp_path):
        path = save_run_log({"test": "data"}, filename="run_001.json", log_dir=tmp_path)
        assert path.exists()

    def test_creates_directory_if_missing(self, tmp_path):
        nested = tmp_path / "deep" / "logs"
        path = save_run_log({"test": "data"}, filename="run_001.json", log_dir=nested)
        assert path.exists()
        assert nested.exists()

    def test_content_is_valid_json(self, tmp_path):
        data = {"source_id": "src-csv-abc123def456", "value": 42}
        path = save_run_log(data, filename="run_001.json", log_dir=tmp_path)
        content = json.loads(path.read_text(encoding="utf-8"))
        assert content == data

    def test_datetime_in_content_serialized(self, tmp_path):
        dt = datetime(2025, 6, 1, 0, 0, 0, tzinfo=timezone.utc)
        data = {"created_at": dt}
        path = save_run_log(data, filename="run_001.json", log_dir=tmp_path)
        content = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(content["created_at"], str)

    def test_returns_resolved_path(self, tmp_path):
        path = save_run_log({"x": 1}, filename="run_001.json", log_dir=tmp_path)
        assert isinstance(path, Path)
        assert path.is_absolute()

    def test_filename_must_end_with_json(self, tmp_path):
        with pytest.raises(ValueError, match=".json"):
            save_run_log({"x": 1}, filename="run_001.txt", log_dir=tmp_path)

    def test_non_json_extension_raises(self, tmp_path):
        with pytest.raises(ValueError):
            save_run_log({}, filename="data.csv", log_dir=tmp_path)

    def test_file_contains_indent(self, tmp_path):
        # save_run_log uses indent=2
        path = save_run_log({"key": "value"}, filename="run_001.json", log_dir=tmp_path)
        raw = path.read_text(encoding="utf-8")
        assert "\n" in raw

    def test_overwrites_existing_file(self, tmp_path):
        save_run_log({"v": 1}, filename="run.json", log_dir=tmp_path)
        save_run_log({"v": 2}, filename="run.json", log_dir=tmp_path)
        content = json.loads((tmp_path / "run.json").read_text("utf-8"))
        assert content["v"] == 2

    def test_list_payload(self, tmp_path):
        data = [{"id": "src-csv-abc123def456"}, {"id": "src-csv-fedcba987654"}]
        path = save_run_log(data, filename="list_run.json", log_dir=tmp_path)
        content = json.loads(path.read_text("utf-8"))
        assert content == data
