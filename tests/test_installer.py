from __future__ import annotations

import plistlib
from pathlib import Path

import pytest

from session_digest.installer import (
    InstallError,
    crontab_line,
    cron_to_calendar_interval,
    launchd_plist,
)


def test_cron_to_calendar_interval_reads_hour_and_minute() -> None:
    assert cron_to_calendar_interval("30 9 * * *") == {"Hour": 9, "Minute": 30}


def test_cron_to_calendar_interval_includes_weekday() -> None:
    assert cron_to_calendar_interval("0 8 * * 1") == {
        "Hour": 8,
        "Minute": 0,
        "Weekday": 1,
    }


def test_cron_to_calendar_interval_includes_day_of_month() -> None:
    assert cron_to_calendar_interval("0 8 15 * *") == {
        "Hour": 8,
        "Minute": 0,
        "Day": 15,
    }


def test_cron_to_calendar_interval_rejects_wrong_arity() -> None:
    with pytest.raises(InstallError, match="five fields"):
        cron_to_calendar_interval("0 8 * *")


def test_cron_to_calendar_interval_rejects_step_syntax() -> None:
    with pytest.raises(InstallError, match="not supported"):
        cron_to_calendar_interval("*/15 * * * *")


def test_launchd_plist_is_valid_and_runs_the_executable(tmp_path: Path) -> None:
    xml = launchd_plist("dev.xgodev.session-digest", "0 23 * * *", "/usr/local/bin/session-digest", tmp_path)

    parsed = plistlib.loads(xml.encode("utf-8"))

    assert parsed["Label"] == "dev.xgodev.session-digest"
    assert parsed["ProgramArguments"] == ["/usr/local/bin/session-digest", "run"]
    assert parsed["StartCalendarInterval"] == {"Hour": 23, "Minute": 0}
    assert parsed["StandardErrorPath"].startswith(str(tmp_path))


def test_launchd_plist_does_not_keep_alive(tmp_path: Path) -> None:
    parsed = plistlib.loads(
        launchd_plist("l", "0 23 * * *", "/bin/true", tmp_path).encode("utf-8")
    )

    assert parsed.get("KeepAlive", False) is False
    assert parsed.get("RunAtLoad", False) is False


def test_crontab_line_pairs_schedule_with_command() -> None:
    assert crontab_line("0 23 * * *", "/usr/local/bin/session-digest") == (
        "0 23 * * * /usr/local/bin/session-digest run"
    )


def test_crontab_line_rejects_wrong_arity() -> None:
    with pytest.raises(InstallError, match="five fields"):
        crontab_line("0 23 * *", "/bin/true")
