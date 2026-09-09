from __future__ import annotations

import plistlib
from pathlib import Path

LABEL = "dev.xgodev.session-digest"
_FIELD_NAMES = ("Minute", "Hour", "Day", "Month", "Weekday")


class InstallError(Exception):
    """Raised when a schedule cannot be expressed on this platform."""


def _fields(expr: str) -> list[str]:
    fields = expr.split()
    if len(fields) != 5:
        raise InstallError(f"a cron schedule needs five fields, got: {expr!r}")
    return fields


def cron_to_calendar_interval(expr: str) -> dict[str, int]:
    """Translate a cron expression into launchd's StartCalendarInterval.

    launchd has no step or range syntax, so only literal values and '*'
    are accepted; anything richer is rejected loudly rather than silently
    scheduled at the wrong time.
    """
    interval: dict[str, int] = {}
    for name, value in zip(_FIELD_NAMES, _fields(expr), strict=True):
        if value == "*":
            continue
        if not value.isdigit():
            raise InstallError(
                f"cron field {value!r} is not supported by launchd; "
                "use literal values or '*'"
            )
        interval[name] = int(value)
    return interval


def launchd_plist(
    label: str, schedule: str, executable: str, log_dir: Path
) -> str:
    """Render the launchd job as plist XML."""
    payload = {
        "Label": label,
        "ProgramArguments": [executable, "run"],
        "StartCalendarInterval": cron_to_calendar_interval(schedule),
        "StandardOutPath": str(log_dir / "session-digest.out.log"),
        "StandardErrorPath": str(log_dir / "session-digest.err.log"),
        "RunAtLoad": False,
        "KeepAlive": False,
    }
    return plistlib.dumps(payload).decode("utf-8")


def crontab_line(schedule: str, executable: str) -> str:
    """Render the crontab entry."""
    return f"{' '.join(_fields(schedule))} {executable} run"
