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
from .state import DEFAULT_STATE_PATH, read_watermarks

EXIT_OK = 0
EXIT_ERROR = 1

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

    if args.command == "extract":
        args.project = project

    try:
        config = load_config(args.config)

        if args.command == "scan":
            marks = read_watermarks(args.state.expanduser())
            return _cmd_scan(config, marks)
        if args.command == "extract":
            marks = read_watermarks(args.state.expanduser())
            return _cmd_extract(config, marks, args.project)
    except ConfigError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_ERROR
    except Exception as exc:  # noqa: BLE001 - main() must return, never raise
        print(f"unexpected error: {exc}", file=sys.stderr)
        return EXIT_ERROR

    return EXIT_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
