from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .config import Config
from .state import watermark_for

EDIT_TOOLS = frozenset({"Write", "Edit", "NotebookEdit", "MultiEdit"})
COMMIT_MARKERS = ("git commit", "git merge", "git tag")


@dataclass(frozen=True)
class SessionMetrics:
    """Objective signals about one session. No semantics, only counting."""

    path: Path
    mtime: float
    user_turns: int
    has_edits: bool
    has_commits: bool
    size_bytes: int


@dataclass(frozen=True)
class ProjectCandidate:
    """One project with the sessions worth handing to the agent."""

    project_dir: str
    sessions: list[SessionMetrics]
    newest_mtime: float


def _blocks(message: object) -> list[dict]:
    if not isinstance(message, dict):
        return []
    content = message.get("content")
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    return [block for block in (content or []) if isinstance(block, dict)]


def session_metrics(path: Path) -> SessionMetrics:
    """Measure one session file, tolerating corrupt lines."""
    user_turns = 0
    has_edits = False
    has_commits = False

    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue

        kind = event.get("type")
        if kind == "user" and not event.get("isMeta"):
            user_turns += 1
        if kind != "assistant":
            continue

        for block in _blocks(event.get("message")):
            if block.get("type") != "tool_use":
                continue
            name = block.get("name", "")
            if name in EDIT_TOOLS:
                has_edits = True
            if name == "Bash":
                command = str((block.get("input") or {}).get("command", ""))
                if any(marker in command for marker in COMMIT_MARKERS):
                    has_commits = True

    stat_result = path.stat()
    return SessionMetrics(
        path=path,
        mtime=stat_result.st_mtime,
        user_turns=user_turns,
        has_edits=has_edits,
        has_commits=has_commits,
        size_bytes=stat_result.st_size,
    )


def is_substantial(
    metrics: SessionMetrics, min_user_turns: int, min_bytes: int
) -> bool:
    """Cheap prefilter. Discards the obviously empty, never judges meaning.

    ``min_bytes`` is a byte-size threshold (the session file's size on
    disk), not a character count.

    A session that wrote files or committed earned a look regardless of
    size; judging whether it is worth a note is the agent's job.
    """
    if metrics.size_bytes < min_bytes:
        return False
    if metrics.has_edits or metrics.has_commits:
        return True
    return metrics.user_turns >= min_user_turns


def scan(config: Config, marks: dict[str, float]) -> list[ProjectCandidate]:
    """Find projects with sessions newer than their watermark."""
    root = config.projects_root.expanduser()
    if not root.is_dir():
        return []

    candidates: list[ProjectCandidate] = []
    for project in sorted(p for p in root.iterdir() if p.is_dir()):
        since = watermark_for(marks, project.name)
        sessions = []
        for session in sorted(project.glob("*.jsonl")):
            try:
                if session.stat().st_mtime <= since:
                    continue
                metrics = session_metrics(session)
            except OSError:
                # Claude Code writes into this directory live: a file
                # listed by glob() can vanish, or otherwise become
                # unreadable, before it is measured. Skip it rather than
                # letting one bad file kill the scan for every project.
                continue
            if is_substantial(metrics, config.min_user_turns, config.min_bytes):
                sessions.append(metrics)

        if sessions:
            candidates.append(
                ProjectCandidate(
                    project_dir=project.name,
                    sessions=sessions,
                    newest_mtime=max(s.mtime for s in sessions),
                )
            )

    return candidates
