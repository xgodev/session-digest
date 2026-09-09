from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path

from conftest import tool_use, user_text
from session_digest import cli
from session_digest.cli import main
from session_digest.lock import LockBusy
from session_digest.runner import DigestResult


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


# --- Finding 3: unambiguous exit codes for 'run' ------------------------


def test_run_returns_busy_code_when_lock_held(tmp_path, make_session, monkeypatch, capsys) -> None:
    config = prepare(tmp_path, make_session)

    @contextmanager
    def _busy(_path):
        raise LockBusy(f"another run holds {_path}")
        yield  # pragma: no cover - never reached

    monkeypatch.setattr(cli, "run_lock", _busy)

    code = main(["run", "--config", str(config), "--state", str(tmp_path / "s.json")])

    assert code == 3
    assert "holds" in capsys.readouterr().err


def test_run_returns_partial_failure_code(tmp_path, make_session, monkeypatch, capsys) -> None:
    config = prepare(tmp_path, make_session)
    monkeypatch.setattr(cli, "DEFAULT_LOCK_PATH", tmp_path / "lock.d")
    monkeypatch.setattr(
        cli,
        "run",
        lambda candidates, config, state: [DigestResult("-p-one", False, "boom")],
    )

    code = main(["run", "--config", str(config), "--state", str(tmp_path / "s.json")])

    assert code == 2


# --- Finding 4: honest uninstall reporting ------------------------------


def test_uninstall_reports_nothing_to_remove(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))

    code = main(["uninstall", "--platform", "linux"])

    assert code == 0
    assert "nothing to remove" in capsys.readouterr().out


def test_uninstall_reports_removed_when_present(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    target = tmp_path / ".config" / "session-digest" / "crontab.entry"
    target.parent.mkdir(parents=True)
    target.write_text("x", encoding="utf-8")

    code = main(["uninstall", "--platform", "linux"])

    assert code == 0
    assert "removed:" in capsys.readouterr().out
