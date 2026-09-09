from __future__ import annotations

import json
from pathlib import Path

import pytest

from conftest import tool_use, user_text
from session_digest import cli
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


# --- Finding 1: deterministic 'extract PROJECT' contract ---------------


def test_extract_bare_project_argument_does_not_crash(tmp_path, monkeypatch) -> None:
    """A bare 'extract PROJECT' must never raise SystemExit."""
    monkeypatch.setattr(cli, "DEFAULT_CONFIG_PATH", tmp_path / "absent.json")

    code = main(["extract", "-p-one"])

    assert code == 1


def test_extract_project_then_flags_works(tmp_path, make_session, capsys) -> None:
    config = prepare(tmp_path, make_session)

    code = main(
        ["extract", "-p-one", "--config", str(config), "--state", str(tmp_path / "s.json")]
    )

    assert code == 0
    assert "[USER]" in capsys.readouterr().out


def test_extract_flags_before_project_is_rejected(tmp_path, capsys) -> None:
    code = main(["extract", "--config", str(tmp_path / "c.json"), "-p-one"])

    err = capsys.readouterr().err
    assert code == 1
    assert "immediately after 'extract'" in err


def test_extract_without_project_returns_error(capsys) -> None:
    code = main(["extract"])

    err = capsys.readouterr().err
    assert code == 1
    assert "immediately after 'extract'" in err


def test_extract_help_reaches_argparse(capsys) -> None:
    """'--help' right after 'extract' is a help request, not a bad project id."""
    with pytest.raises(SystemExit) as exc_info:
        main(["extract", "--help"])

    assert exc_info.value.code == 0
    out = capsys.readouterr().out
    assert "project" in out
    assert "immediately after 'extract'" not in out


def test_extract_short_help_reaches_argparse(capsys) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["extract", "-h"])

    assert exc_info.value.code == 0
    out = capsys.readouterr().out
    assert "project" in out
    assert "immediately after 'extract'" not in out


# --- Finding 2: no exception ever escapes main() ------------------------


def test_unexpected_exception_becomes_error_code_not_traceback(
    tmp_path, make_session, monkeypatch, capsys
) -> None:
    config = prepare(tmp_path, make_session)

    def _boom(*_args, **_kwargs):
        raise OSError("permission denied")

    monkeypatch.setattr(cli, "scan", _boom)

    code = main(["scan", "--config", str(config), "--state", str(tmp_path / "s.json")])

    assert code == 1
    assert "permission denied" in capsys.readouterr().err


# --- Finding: usage errors must not collide with argparse's own exit code ---


def test_bogus_subcommand_returns_error_not_argparse_exit_code(capsys) -> None:
    """argparse would sys.exit(2) for an unknown subcommand; this CLI
    normalizes every usage error to 1 and must not raise SystemExit out of
    main()."""
    code = main(["bogus"])

    assert code == 1
    assert capsys.readouterr().err  # argparse's usage/error text


def test_empty_argv_returns_error_not_argparse_exit_code(capsys) -> None:
    code = main([])

    assert code == 1
    assert capsys.readouterr().err


def test_top_level_help_still_exits_zero(capsys) -> None:
    """A real help request keeps argparse's own exit code (0), unlike a
    usage error, which is remapped to 1."""
    with pytest.raises(SystemExit) as exc_info:
        main(["--help"])

    assert exc_info.value.code == 0
