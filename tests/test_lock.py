from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from session_digest.lock import LockBusy, run_lock


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
