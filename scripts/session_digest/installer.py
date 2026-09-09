from __future__ import annotations

import plistlib
from pathlib import Path

LABEL = "dev.xgodev.session-digest"
_FIELD_NAMES = ("Minute", "Hour", "Day", "Month", "Weekday")
_FIELD_RANGES = {
    "Minute": (0, 59),
    "Hour": (0, 23),
    "Day": (1, 31),
    "Month": (1, 12),
    "Weekday": (0, 7),
}


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
    scheduled at the wrong time. Each literal field is also range-checked,
    since launchd would otherwise silently misinterpret an out-of-range
    value (e.g. hour 25).

    POSIX cron ORs day-of-month with day-of-week when both are specified,
    while launchd's StartCalendarInterval ANDs them, so the same
    expression would mean two different schedules. That combination is
    rejected rather than translated; the crontab path is unaffected.
    """
    fields = _fields(expr)
    day, weekday = fields[2], fields[4]
    if day != "*" and weekday != "*":
        raise InstallError(
            "cron ORs day-of-month with day-of-week when both are given, "
            "but launchd's StartCalendarInterval ANDs them, so this "
            "expression cannot be translated as-is; use two separate "
            "launchd entries instead"
        )

    interval: dict[str, int] = {}
    for name, value in zip(_FIELD_NAMES, fields, strict=True):
        if value == "*":
            continue
        if not value.isdigit():
            raise InstallError(
                f"cron field {value!r} is not supported by launchd; "
                "use literal values or '*'"
            )
        number = int(value)
        low, high = _FIELD_RANGES[name]
        if not (low <= number <= high):
            raise InstallError(
                f"cron field {name} value {number} is out of range "
                f"({low}-{high})"
            )
        interval[name] = number
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
