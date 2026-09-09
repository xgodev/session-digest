from __future__ import annotations

import json
from pathlib import Path

import pytest

from session_digest.config import (
    ConfigError,
    load_config,
    mapping_for,
)


def write_config(tmp_path: Path, payload: dict) -> Path:
    path = tmp_path / "session-digest.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_load_config_expands_user_paths(tmp_path: Path) -> None:
    path = write_config(tmp_path, {"knowledge_base": "~/Notes"})

    config = load_config(path)

    assert config.knowledge_base == Path.home() / "Notes"
    assert config.knowledge_base.is_absolute()


def test_load_config_applies_defaults(tmp_path: Path) -> None:
    path = write_config(tmp_path, {"knowledge_base": str(tmp_path / "kb")})

    config = load_config(path)

    assert config.schedule == "0 23 * * *"
    assert config.commit is False
    assert config.projects == {}
    assert config.projects_root == Path.home() / ".claude" / "projects"
    assert config.min_user_turns == 3
    assert config.min_chars == 2000


def test_load_config_reads_project_mapping(tmp_path: Path) -> None:
    path = write_config(
        tmp_path,
        {
            "knowledge_base": str(tmp_path / "kb"),
            "projects": {
                "-home-me-code-thing": {
                    "folder": "Thing",
                    "repo": "~/code/thing",
                }
            },
        },
    )

    config = load_config(path)
    mapping = config.projects["-home-me-code-thing"]

    assert mapping.folder == "Thing"
    assert mapping.repo == Path.home() / "code" / "thing"


def test_load_config_requires_knowledge_base(tmp_path: Path) -> None:
    path = write_config(tmp_path, {"schedule": "0 9 * * *"})

    with pytest.raises(ConfigError, match="knowledge_base"):
        load_config(path)


def test_load_config_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="not found"):
        load_config(tmp_path / "absent.json")


def test_load_config_rejects_malformed_json(tmp_path: Path) -> None:
    path = tmp_path / "session-digest.json"
    path.write_text("{not json", encoding="utf-8")

    with pytest.raises(ConfigError, match="invalid JSON"):
        load_config(path)


def test_mapping_for_derives_folder_from_project_dir(tmp_path: Path) -> None:
    path = write_config(tmp_path, {"knowledge_base": str(tmp_path / "kb")})
    config = load_config(path)

    mapping = mapping_for(config, "-Users-me-Projetos-github-com-me-OpenRig")

    assert mapping.folder == "OpenRig"
    assert mapping.repo == Path("/Users/me/Projetos/github/com/me/OpenRig")


def test_mapping_for_prefers_explicit_entry(tmp_path: Path) -> None:
    path = write_config(
        tmp_path,
        {
            "knowledge_base": str(tmp_path / "kb"),
            "projects": {"-Users-me-thing": {"folder": "Custom"}},
        },
    )
    config = load_config(path)

    mapping = mapping_for(config, "-Users-me-thing")

    assert mapping.folder == "Custom"
    assert mapping.repo is None
