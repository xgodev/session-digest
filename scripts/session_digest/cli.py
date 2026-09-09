"""Command-line interface for session-digest.

Exit codes
----------
Every subcommand uses this same scale:

=====  ======================================================================
code   meaning
=====  ======================================================================
0      success, including "nothing to do"
1      hard error: bad config, a malformed invocation, or an unexpected
       failure
=====  ======================================================================
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import DEFAULT_CONFIG_PATH, ConfigError, load_config
from .extract import extract_project
from .scan import scan
from .state import DEFAULT_STATE_PATH, advance_watermark, read_watermarks, watermark_for

EXIT_OK = 0
EXIT_ERROR = 1

_EXTRACT_USAGE = "session-digest extract PROJECT [-h] [--config CONFIG] [--state STATE]"
_EXTRACT_OWN_OPTIONS = {"--config", "--state", "-h", "--help"}

_ADVANCE_USAGE = (
    "session-digest advance PROJECT (TIMESTAMP | --from-scan) [-h] "
    "[--config CONFIG] [--state STATE]"
)
_ADVANCE_OWN_OPTIONS = {"--config", "--state", "--from-scan", "-h", "--help"}

# Subcommands that take a project directory name as the token immediately
# following the subcommand name. See _split_leading_project_argv below.
_LEADING_PROJECT_COMMANDS = ("extract", "advance")


class _LeadingProjectArgError(Exception):
    """Raised when a subcommand is not immediately followed by a project id."""


def _split_leading_project_argv(
    argv: list[str], *, command: str, usage: str, own_options: set[str]
) -> tuple[str, list[str]]:
    """Pull the project id that must immediately follow `command` out of argv.

    Project directory names may begin with a dash (e.g.
    '-Users-me-Projetos-thing'), which collides with argparse's option
    parsing. Rather than rely on argparse to sort that out, the token
    right after the subcommand name is taken literally as the project id
    here, before argparse ever sees it. This is the only supported
    position for it: it must come immediately after the subcommand,
    before any option. Shared by 'extract' and 'advance', which both take
    a project id this way.

    Returns (project, remaining_argv), where remaining_argv still starts
    with `command` so the rest of the CLI's own options parse normally.
    Raises _LeadingProjectArgError if there is no token right after
    `command`, or if that token is one of the CLI's own options.
    """
    if len(argv) < 2:
        raise _LeadingProjectArgError(
            f"{command}: the project identifier must come immediately after "
            f"'{command}'; usage: {usage}"
        )

    candidate = argv[1]
    if candidate in own_options or candidate.startswith("--"):
        raise _LeadingProjectArgError(
            f"{command}: the project identifier must come immediately after "
            f"'{command}', not an option ({candidate!r}); usage: {usage}"
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
    # hand in main() via _split_leading_project_argv, then attached to the
    # parsed namespace below. See that function's docstring for why.

    advance_p = sub.add_parser(
        "advance",
        help="record that a project's sessions have been digested up to a timestamp",
        description=(
            "Move a project's watermark forward, so a future scan treats "
            "everything up to TIMESTAMP as already digested. PROJECT is "
            "the project directory name (it may start with a dash) and "
            "MUST be the token immediately following 'advance', before "
            "any option, e.g. "
            "'session-digest advance -p-one 1737000000 --config PATH'. "
            "TIMESTAMP is Unix epoch seconds (int or float); pass "
            "--from-scan instead to use the newest session mtime among "
            "the project's current scan candidates. The watermark never "
            "moves backward: a TIMESTAMP that is not newer than what is "
            "already recorded is reported, not applied."
        ),
        usage=_ADVANCE_USAGE,
    )
    # No 'project' positional is declared here either, for the same reason
    # as 'extract' above. 'timestamp' IS a normal positional: unlike the
    # project id, it never begins with a dash in practice, and rejecting a
    # bad value with a clear message is done by hand in _cmd_advance
    # rather than via argparse's type= (which would exit 2, not this
    # CLI's own error code, on a bad value).
    advance_p.add_argument("timestamp", nargs="?", default=None)
    advance_p.add_argument("--from-scan", action="store_true")
    advance_p.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    advance_p.add_argument("--state", type=Path, default=DEFAULT_STATE_PATH)

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


def _cmd_advance(config, marks, state_path: Path, project: str, args) -> int:
    if args.timestamp is not None and args.from_scan:
        print(
            "advance: pass either TIMESTAMP or --from-scan, not both; "
            f"usage: {_ADVANCE_USAGE}",
            file=sys.stderr,
        )
        return EXIT_ERROR
    if args.timestamp is None and not args.from_scan:
        print(
            "advance: TIMESTAMP or --from-scan is required; "
            f"usage: {_ADVANCE_USAGE}",
            file=sys.stderr,
        )
        return EXIT_ERROR

    if args.from_scan:
        for candidate in scan(config, marks):
            if candidate.project_dir == project:
                timestamp = candidate.newest_mtime
                break
        else:
            print(
                f"advance: {project} is not among the pending scan candidates; "
                "cannot use --from-scan",
                file=sys.stderr,
            )
            return EXIT_ERROR
    else:
        try:
            timestamp = float(args.timestamp)
        except ValueError:
            print(
                f"advance: TIMESTAMP must be a number, got {args.timestamp!r}",
                file=sys.stderr,
            )
            return EXIT_ERROR

    previous = watermark_for(marks, project)
    advance_watermark(state_path, project, timestamp)
    if timestamp > previous:
        print(f"advanced {project} watermark to {timestamp}")
    else:
        print(
            f"{project} watermark already at {previous}; {timestamp} is not "
            "newer, not advanced"
        )
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns a process exit code and never raises."""
    if argv is None:
        argv = sys.argv[1:]

    project: str | None = None
    is_help_request = len(argv) >= 2 and argv[1] in ("-h", "--help")
    if argv and argv[0] in _LEADING_PROJECT_COMMANDS and not is_help_request:
        usage = _EXTRACT_USAGE if argv[0] == "extract" else _ADVANCE_USAGE
        own_options = (
            _EXTRACT_OWN_OPTIONS if argv[0] == "extract" else _ADVANCE_OWN_OPTIONS
        )
        try:
            project, argv = _split_leading_project_argv(
                argv, command=argv[0], usage=usage, own_options=own_options
            )
        except _LeadingProjectArgError as exc:
            print(str(exc), file=sys.stderr)
            return EXIT_ERROR

    try:
        args = _build_parser().parse_args(argv)
    except SystemExit as exc:
        # argparse exits 0 for a help request and 2 for a usage error.
        # 0 is a real, documented outcome (let it through as-is); a
        # malformed invocation is remapped to this CLI's own hard-error
        # code instead.
        if exc.code == 0:
            raise
        return EXIT_ERROR

    if args.command in _LEADING_PROJECT_COMMANDS:
        args.project = project

    try:
        config = load_config(args.config)

        if args.command == "scan":
            marks = read_watermarks(args.state.expanduser())
            return _cmd_scan(config, marks)
        if args.command == "extract":
            marks = read_watermarks(args.state.expanduser())
            return _cmd_extract(config, marks, args.project)
        if args.command == "advance":
            state_path = args.state.expanduser()
            marks = read_watermarks(state_path)
            return _cmd_advance(config, marks, state_path, args.project, args)
    except ConfigError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_ERROR
    except Exception as exc:  # noqa: BLE001 - main() must return, never raise
        print(f"unexpected error: {exc}", file=sys.stderr)
        return EXIT_ERROR

    return EXIT_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
