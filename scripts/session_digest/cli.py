"""Command-line interface for session-digest.

Exit codes
----------
Every subcommand uses this same scale, so a scheduled job can act on the
result without inspecting stderr text:

=====  ======================================================================
code   meaning
=====  ======================================================================
0      success, including "nothing to do"
1      hard error: bad config, a schedule that cannot be installed, a
       malformed invocation, or an unexpected failure
2      the run completed but one or more projects failed
3      another run already holds the lock (benign skip)
=====  ======================================================================
"""

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

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_PARTIAL_FAILURE = 2
EXIT_LOCK_BUSY = 3

_EXTRACT_USAGE = "session-digest extract PROJECT [-h] [--config CONFIG] [--state STATE]"
_EXTRACT_OWN_OPTIONS = {"--config", "--state", "-h", "--help"}


class _ExtractArgError(Exception):
    """Raised when 'extract' is not immediately followed by a project id."""


def _split_extract_argv(argv: list[str]) -> tuple[str, list[str]]:
    """Pull the project id that must immediately follow 'extract' out of argv.

    Project directory names may begin with a dash (e.g.
    '-Users-me-Projetos-thing'), which collides with argparse's option
    parsing. Rather than rely on argparse to sort that out, the token
    right after 'extract' is taken literally as the project id here,
    before argparse ever sees it. This is the only supported position for
    it: it must come immediately after 'extract', before any option.

    Returns (project, remaining_argv), where remaining_argv still starts
    with 'extract' so the rest of the CLI's own options parse normally.
    Raises _ExtractArgError if there is no token right after 'extract',
    or if that token is one of the CLI's own options.
    """
    if len(argv) < 2:
        raise _ExtractArgError(
            "extract: the project identifier must come immediately after "
            f"'extract'; usage: {_EXTRACT_USAGE}"
        )

    candidate = argv[1]
    if candidate in _EXTRACT_OWN_OPTIONS or candidate.startswith("--"):
        raise _ExtractArgError(
            f"extract: the project identifier must come immediately after "
            f"'extract', not an option ({candidate!r}); usage: {_EXTRACT_USAGE}"
        )

    remaining = [argv[0], *argv[2:]]
    return candidate, remaining


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="session-digest",
        description="Distil Claude Code sessions into durable knowledge.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    scan_p = sub.add_parser("scan", help="list projects with undigested sessions")
    scan_p.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    scan_p.add_argument("--state", type=Path, default=DEFAULT_STATE_PATH)

    extract_p = sub.add_parser(
        "extract",
        help="print a project's condensed transcript",
        description=(
            "Print a project's condensed transcript. PROJECT is the project "
            "directory name (it may start with a dash) and MUST be the "
            "token immediately following 'extract', before any option, "
            "e.g. 'session-digest extract -p-one --config PATH'."
        ),
        usage=_EXTRACT_USAGE,
    )
    extract_p.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    extract_p.add_argument("--state", type=Path, default=DEFAULT_STATE_PATH)
    # No 'project' positional is declared here: it is pulled out of argv by
    # hand in main() via _split_extract_argv, then attached to the parsed
    # namespace below. See that function's docstring for why.

    run_p = sub.add_parser("run", help="digest every pending project")
    run_p.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    run_p.add_argument("--state", type=Path, default=DEFAULT_STATE_PATH)

    install_p = sub.add_parser("install", help="install the periodic job")
    install_p.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    install_p.add_argument("--dry-run", action="store_true")
    install_p.add_argument("--platform", default=sys.platform)

    uninstall_p = sub.add_parser("uninstall", help="remove the periodic job")
    uninstall_p.add_argument("--platform", default=sys.platform)
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
    return EXIT_OK


def _cmd_extract(config, marks, project: str) -> int:
    for candidate in scan(config, marks):
        if candidate.project_dir == project:
            for piece in extract_project([s.path for s in candidate.sessions]):
                print(piece)
            return EXIT_OK
    print(f"no sessions pending for {project}", file=sys.stderr)
    return EXIT_ERROR


def _cmd_run(config, marks, state: Path) -> int:
    try:
        with run_lock(DEFAULT_LOCK_PATH):
            results = run(scan(config, marks), config, state)
    except LockBusy as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_LOCK_BUSY

    for result in results:
        status = "ok" if result.ok else "failed"
        print(f"{result.project_dir}: {status}")
    return EXIT_OK if all(r.ok for r in results) else EXIT_PARTIAL_FAILURE


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
        return EXIT_OK

    log_dir.mkdir(parents=True, exist_ok=True)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(rendered, encoding="utf-8")
    print(f"written: {target}")
    if platform == "darwin":
        print(f"activate with: launchctl load {target}")
    else:
        print(f"activate with: (crontab -l; cat {target}) | crontab -")
    return EXIT_OK


def _cmd_uninstall(platform: str) -> int:
    if platform == "darwin":
        target = Path(f"~/Library/LaunchAgents/{LABEL}.plist").expanduser()
        print(f"run: launchctl unload {target}")
    else:
        target = Path("~/.config/session-digest/crontab.entry").expanduser()
        print("remove the session-digest line from your crontab")

    existed = target.exists()
    target.unlink(missing_ok=True)
    print(f"removed: {target}" if existed else f"nothing to remove: {target}")
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns a process exit code and never raises."""
    if argv is None:
        argv = sys.argv[1:]

    project: str | None = None
    is_help_request = len(argv) >= 2 and argv[1] in ("-h", "--help")
    if argv and argv[0] == "extract" and not is_help_request:
        try:
            project, argv = _split_extract_argv(argv)
        except _ExtractArgError as exc:
            print(str(exc), file=sys.stderr)
            return EXIT_ERROR

    args = _build_parser().parse_args(argv)
    if args.command == "extract":
        args.project = project

    if args.command == "uninstall":
        return _cmd_uninstall(args.platform)

    try:
        config = load_config(args.config)

        if args.command == "install":
            return _cmd_install(config, args.platform, args.dry_run)

        marks = read_watermarks(args.state.expanduser())

        if args.command == "scan":
            return _cmd_scan(config, marks)
        if args.command == "extract":
            return _cmd_extract(config, marks, args.project)
        if args.command == "run":
            return _cmd_run(config, marks, args.state.expanduser())
    except ConfigError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_ERROR
    except InstallError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_ERROR
    except Exception as exc:  # noqa: BLE001 - main() must return, never raise
        print(f"unexpected error: {exc}", file=sys.stderr)
        return EXIT_ERROR

    return EXIT_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
