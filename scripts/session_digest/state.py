from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

DEFAULT_STATE_PATH = Path("~/.claude/state/session-digest.json")


def read_watermarks(path: Path) -> dict[str, float]:
    """Read per-project watermarks, tolerating absence and corruption.

    State is a cache, not a source of truth: an unreadable file means we
    reprocess, which is safe, so it never raises.
    """
    try:
        payload = json.loads(path.expanduser().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    marks: dict[str, float] = {}
    for key, value in payload.items():
        try:
            marks[str(key)] = float(value)
        except (TypeError, ValueError):
            continue
    return marks


def watermark_for(marks: dict[str, float], project_dir: str) -> float:
    """Return the watermark for a project, or 0.0 when unseen."""
    return float(marks.get(project_dir, 0.0))


def advance_watermark(path: Path, project_dir: str, timestamp: float) -> None:
    """Move a project's watermark forward, never backward.

    Writes atomically: a crash mid-write must not corrupt the state of
    every other project.
    """
    target = path.expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)

    marks = read_watermarks(target)
    if timestamp <= watermark_for(marks, project_dir):
        return
    marks[project_dir] = float(timestamp)

    handle, temp_name = tempfile.mkstemp(dir=target.parent, suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(marks, stream, indent=2, sort_keys=True)
        os.replace(temp_name, target)
    except BaseException:
        Path(temp_name).unlink(missing_ok=True)
        raise
