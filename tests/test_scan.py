from __future__ import annotations

import os
from pathlib import Path

from conftest import assistant_text, tool_use, user_text
from session_digest.config import Config
from session_digest.scan import (
    is_substantial,
    scan,
    session_metrics,
)


def make_config(tmp_path: Path) -> Config:
    return Config(
        knowledge_base=tmp_path / "kb",
        projects_root=tmp_path / "projects",
        min_user_turns=3,
        min_bytes=100,
    )


def test_session_metrics_counts_real_user_turns(tmp_path, make_session) -> None:
    path = make_session(
        tmp_path,
        "s1",
        [
            user_text("first"),
            assistant_text("reply"),
            user_text("system noise", meta=True),
            user_text("second"),
        ],
    )

    metrics = session_metrics(path)

    assert metrics.user_turns == 2


def test_session_metrics_detects_edits_and_commits(tmp_path, make_session) -> None:
    path = make_session(
        tmp_path,
        "s1",
        [
            tool_use("Write", file_path="/tmp/a.py"),
            tool_use("Bash", command="git commit -m 'x'"),
        ],
    )

    metrics = session_metrics(path)

    assert metrics.has_edits is True
    assert metrics.has_commits is True


def test_session_metrics_reports_no_edits_for_reads(tmp_path, make_session) -> None:
    path = make_session(
        tmp_path,
        "s1",
        [tool_use("Read", file_path="/tmp/a.py"), tool_use("Grep", pattern="x")],
    )

    metrics = session_metrics(path)

    assert metrics.has_edits is False
    assert metrics.has_commits is False


def test_session_metrics_survives_corrupt_lines(tmp_path) -> None:
    path = tmp_path / "s1.jsonl"
    path.write_text('{"broken\n{"type":"user","message":{"content":"hi"}}\n', encoding="utf-8")

    metrics = session_metrics(path)

    assert metrics.user_turns == 1


def test_is_substantial_requires_turns_and_size() -> None:
    from session_digest.scan import SessionMetrics

    thin = SessionMetrics(Path("a"), 1.0, user_turns=1, has_edits=False, has_commits=False, size_bytes=10)
    assert is_substantial(thin, 3, 100) is False


def test_is_substantial_accepts_edits_despite_few_turns() -> None:
    from session_digest.scan import SessionMetrics

    short_but_productive = SessionMetrics(
        Path("a"), 1.0, user_turns=1, has_edits=True, has_commits=False, size_bytes=500
    )
    assert is_substantial(short_but_productive, 3, 100) is True


def test_scan_groups_by_project_and_skips_old_sessions(tmp_path, make_session) -> None:
    config = make_config(tmp_path)
    events = [user_text("a" * 200), user_text("b"), user_text("c"), tool_use("Edit", file_path="x")]
    make_session(config.projects_root / "-p-one", "old", events, mtime=100.0)
    make_session(config.projects_root / "-p-one", "new", events, mtime=300.0)
    make_session(config.projects_root / "-p-two", "fresh", events, mtime=400.0)

    candidates = scan(config, {"-p-one": 200.0})

    by_project = {c.project_dir: c for c in candidates}
    assert set(by_project) == {"-p-one", "-p-two"}
    assert [s.path.name for s in by_project["-p-one"].sessions] == ["new.jsonl"]
    assert by_project["-p-two"].newest_mtime == 400.0


def test_scan_drops_projects_whose_sessions_are_all_thin(tmp_path, make_session) -> None:
    config = make_config(tmp_path)
    make_session(config.projects_root / "-p-thin", "s", [user_text("hi")], mtime=300.0)

    assert scan(config, {}) == []


def test_scan_returns_empty_when_root_missing(tmp_path) -> None:
    config = Config(knowledge_base=tmp_path / "kb", projects_root=tmp_path / "absent")

    assert scan(config, {}) == []


def test_scan_skips_vanished_session_and_keeps_others(tmp_path, make_session) -> None:
    config = make_config(tmp_path)
    good_events = [
        user_text("a" * 200),
        user_text("b"),
        user_text("c"),
        tool_use("Edit", file_path="x"),
    ]
    project_dir = config.projects_root / "-p-one"
    make_session(project_dir, "good", good_events, mtime=300.0)

    # Simulate a session that Claude Code deletes between glob() listing it
    # and scan() measuring it: a dangling symlink still matches "*.jsonl"
    # but raises FileNotFoundError on stat().
    os.symlink(project_dir / "does-not-exist", project_dir / "vanished.jsonl")

    candidates = scan(config, {})

    by_project = {c.project_dir: c for c in candidates}
    assert [s.path.name for s in by_project["-p-one"].sessions] == ["good.jsonl"]
