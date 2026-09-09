from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from session_digest.lock import LockBusy, run_lock


def _make_stale(path: Path, stale_seconds: float = 3600) -> None:
    path.mkdir()
    old = time.time() - stale_seconds
    os.utime(path, (old, old))


def test_lock_creates_and_removes_directory(tmp_path: Path) -> None:
    path = tmp_path / "run.lock"

    with run_lock(path):
        assert path.is_dir()

    assert not path.exists()


def test_lock_rejects_concurrent_holder(tmp_path: Path) -> None:
    path = tmp_path / "run.lock"

    with run_lock(path):
        with pytest.raises(LockBusy):
            with run_lock(path):
                pass


def test_lock_reclaims_stale_holder(tmp_path: Path) -> None:
    path = tmp_path / "run.lock"
    path.mkdir()
    old = time.time() - 3600
    os.utime(path, (old, old))

    with run_lock(path, stale_after=60):
        assert path.is_dir()


def test_lock_releases_on_exception(tmp_path: Path) -> None:
    path = tmp_path / "run.lock"

    with pytest.raises(ValueError):
        with run_lock(path):
            raise ValueError("boom")

    assert not path.exists()


def test_lock_reclaim_of_nonempty_stale_directory_does_not_crash(tmp_path: Path) -> None:
    """A stale lock directory that still has leftover files can't be rmdir'd
    (OSError: not empty). That must not crash the run; it must fall through
    to the ordinary busy handling instead."""
    path = tmp_path / "run.lock"
    path.mkdir()
    (path / "leftover").write_text("x", encoding="utf-8")
    # Writing inside the directory bumps its mtime, so backdate it *after*
    # creating the leftover file to keep it looking stale.
    old = time.time() - 3600
    os.utime(path, (old, old))

    with pytest.raises(LockBusy):
        with run_lock(path, stale_after=60):
            pass


def test_lock_reclaim_race_surfaces_as_lock_busy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Two racing processes both see the lock as stale and both try to
    reclaim it. The loser's rmdir fails because the winner already removed
    (and re-created) the directory. That must surface as LockBusy, not an
    unhandled FileNotFoundError/OSError."""
    path = tmp_path / "run.lock"
    _make_stale(path)

    original_rmdir = os.rmdir
    calls = {"n": 0}

    def flaky_rmdir(p: object, *args: object, **kwargs: object) -> None:
        calls["n"] += 1
        if calls["n"] == 1:
            # Simulate the race: another process already removed the
            # stale directory before we got to it.
            raise FileNotFoundError("already reclaimed by another run")
        original_rmdir(p, *args, **kwargs)

    monkeypatch.setattr(os, "rmdir", flaky_rmdir)

    with pytest.raises(LockBusy):
        with run_lock(path, stale_after=60):
            pass
