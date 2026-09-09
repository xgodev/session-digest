# session-digest

Turn Claude Code session transcripts into durable, routed knowledge.

## The problem

Claude Code sessions produce knowledge — decisions, root causes, corrections
the user made, invariants discovered along the way — and that knowledge dies
in the transcript. The `.jsonl` files under `~/.claude/projects/` are
write-only: nobody rereads megabytes of session history looking for the one
paragraph that mattered.

The concrete failure that motivated this plugin: a knowledge base with
automatic git sync, working perfectly, fed by fifty-five sessions over two
months, went two months without a single new note. The sync was automatic;
writing the note depended on someone remembering, and that judgment failed
every single time. The lesson this plugin encodes: whatever depends on
someone remembering does not happen.

## How it works

A scheduled job runs a two-stage filter.

**Stage one is a script**, and a script cannot judge meaning — it can only
count. It discards the obviously empty using objective signals: how many
user turns the session had, whether any file was written, whether anything
was committed, and the transcript's size on disk. This kills "what's the
path to that file?" without spending a single token, and it is fully
deterministic and unit-tested.

**Stage two is an agent**, invoked once per project, and only the agent
judges substance — because judging substance requires reading and
understanding content, which the script deliberately does not do. Given a
condensed batch of a project's new sessions, the agent decides whether there
is a decision, a root-caused bug, a user correction, or a concrete delivery
worth recording. `nothing to record` is a legitimate outcome of that
judgment, not a failure: most sessions have nothing durable to say, and the
watermark advances exactly the same whether or not a note gets written.

Whatever the agent decides is worth keeping goes to one of two destinations,
by kind:

- **Technical learnings** — a gotcha, an invariant, "do X not Y in this
  codebase" — go to the project's own repository, into its existing docs,
  `CLAUDE.md`, or a project skill, so the next session on that project (by
  anyone) finds them where the code already lives.
- **Project narrative** — timeline entries, decisions and their reasoning,
  pending work, and user corrections — go to a knowledge base folder you
  configure, separate from any one repository.

## Installation

```bash
pip install .
```

This installs the `session-digest` command (see `[project.scripts]` in
`pyproject.toml`). Requires Python 3.11+ and nothing beyond the standard
library.

Then write a configuration file (see below) and run:

```bash
session-digest install
```

## Configuration

Configuration lives at `~/.claude/session-digest.json` by default (override
with `--config` on any subcommand). Example:

```json
{
  "knowledge_base": "~/notes",
  "schedule": "0 23 * * *",
  "commit": false,
  "projects": {
    "-Users-me-Projects-example": {
      "folder": "example",
      "repo": "~/Projects/example"
    }
  },
  "projects_root": "~/.claude/projects",
  "min_user_turns": 3,
  "min_bytes": 2000
}
```

| Field | Required | Default | Meaning |
|---|---|---|---|
| `knowledge_base` | yes | — | Directory where project narrative notes are written. |
| `schedule` | no | `0 23 * * *` | A five-field cron expression for how often the job runs. |
| `commit` | no | `false` | Whether the skill may create a local commit in a project's repository after writing to it. Never causes a push. |
| `projects` | no | `{}` | Explicit mapping from a project's directory name under `projects_root` to where its knowledge goes. Each entry has `folder` (the subfolder under `knowledge_base` for that project's narrative notes) and `repo` (the absolute path to that project's repository, or omitted if it has none). Without an entry, the destination is derived from the working directory Claude Code encoded into the session directory's name, and the knowledge base folder falls back to that directory's basename. |
| `projects_root` | no | `~/.claude/projects` | Where Claude Code stores session directories. |
| `min_user_turns` | no | `3` | A session with fewer user turns than this is dropped by the cheap filter unless it wrote a file or committed. |
| `min_bytes` | no | `2000` | A session smaller than this many bytes on disk is dropped by the cheap filter regardless of anything else. |

## Commands

- **`session-digest scan`** — lists, as JSON, every project with sessions
  newer than its watermark that survive the cheap filter. Read-only.
- **`session-digest extract PROJECT`** — prints one project's sessions
  condensed into context-sized text slices. `PROJECT` must be the token
  immediately following `extract`, before any option (e.g.
  `session-digest extract -Users-me-project --config PATH`), because
  project directory names come from Claude Code encoding a filesystem path
  and can themselves begin with a dash — a position argparse would
  otherwise try to parse as an option.
- **`session-digest run`** — the end-to-end job: scans, and for every
  candidate project extracts its sessions and invokes `claude -p` once with
  the `session-digest` skill and the condensed material. A project's
  watermark advances only when its invocation succeeds, so a mid-run crash
  resumes from where it stopped on the next run.
- **`session-digest install`** — writes the periodic job: a launchd plist on
  macOS, a crontab entry elsewhere. Add `--dry-run` to print what would be
  written without touching disk.
- **`session-digest uninstall`** — removes the periodic job.

### Exit codes

| Code | Meaning |
|---|---|
| 0 | Success, including "nothing to do". |
| 1 | Hard error: bad configuration, a schedule that cannot be installed, a malformed invocation, or an unexpected failure. |
| 2 | The run completed but one or more projects failed. |
| 3 | Another run already holds the lock (a benign skip, not a failure). |

## Guarantees

- **This tool never runs `git push`.** It does not appear anywhere in the
  codebase, and it never will: writing a file is reversible, publishing it
  is not, and this plugin only ever does the former.
- **Committing into your own repository is opt-in and off by default.**
  Set `commit: true` in the configuration to let the skill create a local
  commit after it writes to a project's repository; leave it `false` (the
  default) and changes are left uncommitted for you to review and sync
  yourself.
- **The knowledge base's own git sync, if any, is entirely yours to manage.**
  This plugin writes files into it and nothing more.
