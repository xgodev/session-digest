from __future__ import annotations

import json
from pathlib import Path

from conftest import tool_use, user_text
from session_digest.cli import main


def prepare(tmp_path: Path, make_session) -> Path:
    projects = tmp_path / "projects"
    make_session(
        projects / "-p-one",
        "s",
        [user_text("a" * 3000), tool_use("Write", file_path="x")],
        mtime=500.0,
    )
    config = tmp_path / "config.json"
    config.write_text(
        json.dumps(
            {
                "knowledge_base": str(tmp_path / "kb"),
                "projects_root": str(projects),
            }
        ),
        encoding="utf-8",
    )
    return config


def test_scan_prints_candidates_as_json(tmp_path, make_session, capsys) -> None:
    config = prepare(tmp_path, make_session)

    code = main(["scan", "--config", str(config), "--state", str(tmp_path / "s.json")])

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload[0]["project_dir"] == "-p-one"
    assert payload[0]["sessions"] == 1


def test_extract_prints_transcript(tmp_path, make_session, capsys) -> None:
    config = prepare(tmp_path, make_session)

    code = main(
        ["extract", "-p-one", "--config", str(config), "--state", str(tmp_path / "s.json")]
    )

    assert code == 0
    assert "[USER]" in capsys.readouterr().out


def test_extract_reports_unknown_project(tmp_path, make_session, capsys) -> None:
    config = prepare(tmp_path, make_session)

    code = main(
        ["extract", "-nope", "--config", str(config), "--state", str(tmp_path / "s.json")]
    )

    assert code == 1
    assert "no sessions" in capsys.readouterr().err


def test_missing_config_exits_with_message(tmp_path, capsys) -> None:
    code = main(["scan", "--config", str(tmp_path / "absent.json")])

    assert code == 1
    assert "config not found" in capsys.readouterr().err


def test_install_dry_run_prints_plist_without_writing(tmp_path, make_session, capsys) -> None:
    config = prepare(tmp_path, make_session)

    code = main(["install", "--config", str(config), "--dry-run", "--platform", "darwin"])

    assert code == 0
    assert "StartCalendarInterval" in capsys.readouterr().out


def test_install_dry_run_prints_crontab_on_linux(tmp_path, make_session, capsys) -> None:
    config = prepare(tmp_path, make_session)

    code = main(["install", "--config", str(config), "--dry-run", "--platform", "linux"])

    assert code == 0
    assert "run" in capsys.readouterr().out
