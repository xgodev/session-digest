"""Whole-repository guarantees that don't belong to any one module."""

from __future__ import annotations

from pathlib import Path

SCRIPTS_ROOT = Path(__file__).resolve().parent.parent / "scripts"


def test_no_file_under_scripts_runs_git_push() -> None:
    """The plugin's headline guarantee: it never runs `git push`.

    Writing a file is reversible; publishing it is not. This plugin only
    ever does the former, and that must remain true of every file under
    scripts/, not just the ones a reviewer happened to read.
    """
    offenders = [
        path
        for path in SCRIPTS_ROOT.rglob("*")
        if path.is_file()
        and path.suffix in {".py", ""}
        and "git push" in path.read_text(encoding="utf-8", errors="ignore")
    ]

    assert offenders == []
