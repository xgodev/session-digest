from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_CONFIG_PATH = Path("~/.claude/session-digest.json")
DEFAULT_SCHEDULE = "0 23 * * *"
DEFAULT_MIN_USER_TURNS = 3
DEFAULT_MIN_CHARS = 2000


class ConfigError(Exception):
    """Raised when the configuration is missing or unusable."""


@dataclass(frozen=True)
class ProjectMapping:
    """Where one project's knowledge goes."""

    folder: str
    repo: Path | None = None


@dataclass(frozen=True)
class Config:
    """Resolved configuration. All paths are absolute."""

    knowledge_base: Path
    schedule: str = DEFAULT_SCHEDULE
    commit: bool = False
    projects: dict[str, ProjectMapping] = field(default_factory=dict)
    projects_root: Path = field(
        default_factory=lambda: Path("~/.claude/projects").expanduser()
    )
    min_user_turns: int = DEFAULT_MIN_USER_TURNS
    min_chars: int = DEFAULT_MIN_CHARS


def _resolve(value: str) -> Path:
    return Path(value).expanduser()


def load_config(path: Path | None = None) -> Config:
    """Read and validate the configuration file."""
    config_path = (path or DEFAULT_CONFIG_PATH).expanduser()
    if not config_path.is_file():
        raise ConfigError(f"config not found: {config_path}")

    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"invalid JSON in {config_path}: {exc}") from exc

    if not isinstance(payload, dict):
        raise ConfigError(f"invalid JSON in {config_path}: expected an object")

    base = payload.get("knowledge_base")
    if not base:
        raise ConfigError("knowledge_base is required")

    projects: dict[str, ProjectMapping] = {}
    for key, raw in (payload.get("projects") or {}).items():
        repo = raw.get("repo")
        projects[key] = ProjectMapping(
            folder=raw.get("folder") or key,
            repo=_resolve(repo) if repo else None,
        )

    projects_root = payload.get("projects_root")

    return Config(
        knowledge_base=_resolve(base),
        schedule=payload.get("schedule", DEFAULT_SCHEDULE),
        commit=bool(payload.get("commit", False)),
        projects=projects,
        projects_root=(
            _resolve(projects_root)
            if projects_root
            else Path("~/.claude/projects").expanduser()
        ),
        min_user_turns=int(payload.get("min_user_turns", DEFAULT_MIN_USER_TURNS)),
        min_chars=int(payload.get("min_chars", DEFAULT_MIN_CHARS)),
    )


def mapping_for(config: Config, project_dir: str) -> ProjectMapping:
    """Return the mapping for a project, deriving one when absent.

    Claude Code encodes a session's cwd in the directory name by replacing
    every path separator with a dash. Without an explicit entry we read the
    directory back as a path and use its last segment as the folder name.
    """
    explicit = config.projects.get(project_dir)
    if explicit is not None:
        return explicit

    as_path = Path("/" + project_dir.strip("-").replace("-", "/"))
    return ProjectMapping(folder=as_path.name, repo=as_path)
