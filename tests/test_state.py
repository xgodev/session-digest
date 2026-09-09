from __future__ import annotations

import json
from pathlib import Path

from session_digest.state import (
    advance_watermark,
    read_watermarks,
    watermark_for,
)


def test_read_watermarks_returns_empty_when_absent(tmp_path: Path) -> None:
    assert read_watermarks(tmp_path / "state.json") == {}


def test_read_watermarks_returns_empty_when_corrupt(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    path.write_text("{broken", encoding="utf-8")

    assert read_watermarks(path) == {}


def test_watermark_for_defaults_to_zero() -> None:
    assert watermark_for({}, "-a-b") == 0.0
    assert watermark_for({"-a-b": 12.5}, "-a-b") == 12.5


def test_advance_watermark_creates_parent_directories(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "state.json"

    advance_watermark(path, "-a-b", 42.0)

    assert json.loads(path.read_text(encoding="utf-8")) == {"-a-b": 42.0}


def test_advance_watermark_preserves_other_projects(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    advance_watermark(path, "-a-b", 1.0)

    advance_watermark(path, "-c-d", 2.0)

    assert read_watermarks(path) == {"-a-b": 1.0, "-c-d": 2.0}


def test_advance_watermark_never_moves_backwards(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    advance_watermark(path, "-a-b", 10.0)

    advance_watermark(path, "-a-b", 5.0)

    assert watermark_for(read_watermarks(path), "-a-b") == 10.0


def test_advance_watermark_leaves_no_temp_file(tmp_path: Path) -> None:
    path = tmp_path / "state.json"

    advance_watermark(path, "-a-b", 1.0)

    assert [p.name for p in tmp_path.iterdir()] == ["state.json"]
