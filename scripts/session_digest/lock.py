from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

DEFAULT_STALE_AFTER = 3600.0


class LockBusy(Exception):
    """Raised when another run already holds the lock."""


@contextmanager
def run_lock(path: Path, stale_after: float = DEFAULT_STALE_AFTER) -> Iterator[Path]:
    """Mutual exclusion via atomic mkdir, with stale-lock reclamation.

    A crashed run must not block every future run: a lock directory older
    than stale_after is treated as abandoned.
    """
    target = path.expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)

    if target.is_dir() and time.time() - target.stat().st_mtime > stale_after:
        target.rmdir()

    try:
        target.mkdir()
    except FileExistsError as exc:
        raise LockBusy(f"another run holds {target}") from exc

    try:
        yield target
    finally:
        try:
            target.rmdir()
        except OSError:
            pass
