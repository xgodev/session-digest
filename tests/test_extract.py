from __future__ import annotations

from conftest import assistant_text, tool_use, user_text
from session_digest.extract import (
    SESSION_MARKER,
    chunk,
    condense_session,
    extract_project,
)


def test_condense_marks_speakers(tmp_path, make_session) -> None:
    path = make_session(tmp_path, "s", [user_text("do it"), assistant_text("done")])

    text = condense_session(path)

    assert "[USER] do it" in text
    assert "[CLAUDE] done" in text


def test_condense_summarises_tool_calls(tmp_path, make_session) -> None:
    path = make_session(tmp_path, "s", [tool_use("Bash", command="ls -la")])

    text = condense_session(path)

    assert "[TOOL Bash] ls -la" in text


def test_condense_skips_meta_user_events(tmp_path, make_session) -> None:
    path = make_session(tmp_path, "s", [user_text("noise", meta=True), user_text("real")])

    text = condense_session(path)

    assert "noise" not in text
    assert "real" in text


def test_condense_includes_session_header(tmp_path, make_session) -> None:
    path = make_session(tmp_path, "abc", [user_text("hi")])

    text = condense_session(path)

    assert "SESSION abc" in text


def test_chunk_returns_single_chunk_when_small() -> None:
    assert chunk("short", 100) == ["short"]


def test_chunk_splits_on_session_boundaries() -> None:
    text = "\n\n##### SESSION a\nx" * 4

    chunks = chunk(text, 40)

    assert len(chunks) > 1
    assert all(len(c) <= 80 for c in chunks)
    assert "".join(chunks) == text


def test_chunk_splits_oversized_single_session() -> None:
    text = "\n\n##### SESSION a\n" + ("y" * 500)

    chunks = chunk(text, 100)

    assert len(chunks) >= 5
    assert "".join(chunks) == text


def test_extract_project_concatenates_sessions_in_order(tmp_path, make_session) -> None:
    first = make_session(tmp_path, "first", [user_text("one")], mtime=100.0)
    second = make_session(tmp_path, "second", [user_text("two")], mtime=200.0)

    chunks = extract_project([second, first], limit=10_000)

    joined = "".join(chunks)
    assert joined.index("one") < joined.index("two")


def test_extract_project_splits_at_real_session_boundaries(tmp_path, make_session) -> None:
    """Integration: goes through condense_session + extract_project's own
    join, unlike test_chunk_splits_on_session_boundaries which hand-builds
    marker text and would not catch the marker never appearing for real."""
    paths = [
        make_session(tmp_path, f"s{i}", [user_text("x" * 60)], mtime=float(i))
        for i in range(6)
    ]

    chunks = extract_project(paths, limit=150)

    assert len(chunks) > 1
    ordered = sorted(paths, key=lambda p: p.stat().st_mtime)
    expected = "".join(condense_session(p) for p in ordered)
    assert "".join(chunks) == expected
    for piece in chunks:
        assert piece.startswith(SESSION_MARKER), piece[:40]
