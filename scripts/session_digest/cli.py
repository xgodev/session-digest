from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from .config import DEFAULT_CONFIG_PATH, ConfigError, load_config
from .extract import extract_project
from .installer import LABEL, InstallError, crontab_line, launchd_plist
from .lock import LockBusy, run_lock
from .runner import run
from .scan import scan
from .state import DEFAULT_STATE_PATH, read_watermarks

DEFAULT_LOCK_PATH = Path("~/.claude/state/session-digest.lock.d")
DEFAULT_LOG_DIR = Path("~/.claude/logs")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="session-digest",
        description="Distil Claude Code sessions into durable knowledge.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    scan = sub.add_parser("scan", help="list projects with undigested sessions")
    scan.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    scan.add_argument("--state", type=Path, default=DEFAULT_STATE_PATH)

    extract = sub.add_parser("extract", help="print a project's condensed transcript")
    extract.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    extract.add_argument("--state", type=Path, default=DEFAULT_STATE_PATH)
    extract.add_argument("project")

    run = sub.add_parser("run", help="digest every pending project")
    run.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    run.add_argument("--state", type=Path, default=DEFAULT_STATE_PATH)

    install = sub.add_parser("install", help="install the periodic job")
    install.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    install.add_argument("--dry-run", action="store_true")
    install.add_argument("--platform", default=sys.platform)

    uninstall = sub.add_parser("uninstall", help="remove the periodic job")
    uninstall.add_argument("--platform", default=sys.platform)
    return parser


def _cmd_scan(config, marks) -> int:
    payload = [
        {
            "project_dir": candidate.project_dir,
            "sessions": len(candidate.sessions),
            "newest_mtime": candidate.newest_mtime,
        }
        for candidate in scan(config, marks)
    ]
    print(json.dumps(payload, indent=2))
    return 0


def _cmd_extract(config, marks, project: str) -> int:
    for candidate in scan(config, marks):
        if candidate.project_dir == project:
            for piece in extract_project([s.path for s in candidate.sessions]):
                print(piece)
            return 0
    print(f"no sessions pending for {project}", file=sys.stderr)
    return 1


def _cmd_run(config, marks, state: Path) -> int:
    try:
        with run_lock(DEFAULT_LOCK_PATH):
            results = run(scan(config, marks), config, state)
    except LockBusy as exc:
        print(str(exc), file=sys.stderr)
        return 0

    for result in results:
        status = "ok" if result.ok else "failed"
        print(f"{result.project_dir}: {status}")
    return 0 if all(r.ok for r in results) else 1


def _executable() -> str:
    return shutil.which("session-digest") or "session-digest"


def _cmd_install(config, platform: str, dry_run: bool) -> int:
    log_dir = DEFAULT_LOG_DIR.expanduser()
    if platform == "darwin":
        rendered = launchd_plist(LABEL, config.schedule, _executable(), log_dir)
        target = Path(f"~/Library/LaunchAgents/{LABEL}.plist").expanduser()
    else:
        rendered = crontab_line(config.schedule, _executable())
        target = Path("~/.config/session-digest/crontab.entry").expanduser()

    if dry_run:
        print(rendered)
        return 0

    log_dir.mkdir(parents=True, exist_ok=True)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(rendered, encoding="utf-8")
    print(f"written: {target}")
    if platform == "darwin":
        print(f"activate with: launchctl load {target}")
    else:
        print(f"activate with: (crontab -l; cat {target}) | crontab -")
    return 0


def _cmd_uninstall(platform: str) -> int:
    if platform == "darwin":
        target = Path(f"~/Library/LaunchAgents/{LABEL}.plist").expanduser()
        print(f"run: launchctl unload {target}")
    else:
        target = Path("~/.config/session-digest/crontab.entry").expanduser()
        print("remove the session-digest line from your crontab")
    target.unlink(missing_ok=True)
    print(f"removed: {target}")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns a process exit code and never raises."""
    # Reorder arguments for extract command if project name starts with dash
    if argv and len(argv) > 2 and argv[0] == "extract":
        if argv[1].startswith("-") and argv[1] not in ["--config", "--state"]:
            # Move project (argv[1]) to the end with -- separator
            project = argv[1]
            argv = [argv[0]] + argv[2:] + ["--", project]

    args = _build_parser().parse_args(argv)

    if args.command == "uninstall":
        return _cmd_uninstall(args.platform)

    try:
        config = load_config(args.config)
    except ConfigError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    try:
        if args.command == "install":
            return _cmd_install(config, args.platform, args.dry_run)

        marks = read_watermarks(args.state.expanduser())

        if args.command == "scan":
            return _cmd_scan(config, marks)
        if args.command == "extract":
            return _cmd_extract(config, marks, args.project)
        if args.command == "run":
            return _cmd_run(config, marks, args.state.expanduser())
    except InstallError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
