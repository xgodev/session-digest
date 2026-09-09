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

An agent session runs a two-stage filter over each project's new sessions.

**Stage one is a script**, and a script cannot judge meaning — it can only
count. It discards the obviously empty using objective signals: how many
user turns the session had, whether any file was written, whether anything
was committed, and the transcript's size on disk. This kills "what's the
path to that file?" without spending a single token, and it is fully
deterministic and unit-tested.

**Stage two is an agent**, and only the agent judges substance — because
judging substance requires reading and understanding content, which the
script deliberately does not do. Given a condensed batch of a project's new
sessions, the agent decides whether there is a decision, a root-caused bug,
a user correction, or a concrete delivery worth recording. `nothing to
record` is a legitimate outcome of that judgment, not a failure: most
sessions have nothing durable to say, and the watermark advances exactly the
same whether or not a note gets written.

Whatever the agent decides is worth keeping goes to one of two destinations,
by kind:

- **Technical learnings** — a gotcha, an invariant, "do X not Y in this
  codebase" — go to the project's own repository, into its existing docs,
  `CLAUDE.md`, or a project skill, so the next session on that project (by
  anyone) finds them where the code already lives.
- **Project narrative** — timeline entries, decisions and their reasoning,
  pending work, and user corrections — go to a knowledge base folder you
  configure, separate from any one repository.

## What this tool is

`session-digest` is two deterministic CLI commands plus a skill:

- **`scan` and `extract`** do the cheap, testable, non-judgmental work: find
  sessions newer than a per-project watermark, discard the obviously empty,
  and condense the rest into text sized for an agent's context. This is
  exactly the kind of work that does not belong in an LLM turn.
- **The `session-digest` skill** (at `skills/session-digest/`) is the
  judgment half: given `scan` and `extract` output, it decides what is worth
  recording and where it belongs, using the note templates alongside it.

This plugin does **not** schedule itself and does **not** invoke an agent on
its own. Both used to be its job, with OS-level periodic-job machinery and a
command that shelled out to a headless agent invocation — but Claude Code
now has its own native scheduled-task facility: a scheduled task IS an agent
session, so it reads the `session-digest` skill and runs `scan` and
`extract` directly. Building and maintaining a second, redundant path to the
same result was a liability, not a feature, so it was removed. Set up your
own recurring schedule with Claude Code's scheduled tasks; point it at this
skill.

## Installation

```bash
pip install .
```

This installs the `session-digest` command (see `[project.scripts]` in
`pyproject.toml`). Requires Python 3.11+ and nothing beyond the standard
library.

Then write a configuration file (see below), create a Claude Code scheduled
task that reads the `session-digest` skill, and let it call `scan` and
`extract` on the cadence you choose.

## Configuration

Configuration lives at `~/.claude/session-digest.json` by default (override
with `--config` on `scan` and `extract`; see [CLI flags](#cli-flags) below
for what each subcommand accepts). Example:

```json
{
  "knowledge_base": "~/notes",
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
| `projects` | no | `{}` | Explicit mapping from a project's directory name under `projects_root` to where its knowledge goes. Each entry has `folder` (the subfolder under `knowledge_base` for that project's narrative notes) and `repo` (the absolute path to that project's repository, or omitted if it has none). Without an entry, the destination is derived from the working directory Claude Code encoded into the session directory's name, and the knowledge base folder falls back to that directory's basename. |
| `projects_root` | no | `~/.claude/projects` | Where Claude Code stores session directories. |
| `min_user_turns` | no | `3` | A session with fewer user turns than this is dropped by the cheap filter unless it wrote a file or committed. |
| `min_bytes` | no | `2000` | A session smaller than this many bytes on disk is dropped by the cheap filter regardless of anything else. |

## CLI flags

These apply across subcommands, not just to the JSON configuration above:

| Flag | Default | Accepted by |
|---|---|---|
| `--config PATH` | `~/.claude/session-digest.json` | `scan`, `extract` |
| `--state PATH` | `~/.claude/state/session-digest.json` | `scan`, `extract` |

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

Advancing a project's watermark (`session_digest.state.advance_watermark`) is
not a CLI command: it is called by the agent session that reads the
`session-digest` skill, once it has judged a project's new sessions and
decided nothing more is pending from them.

### Exit codes

| Code | Meaning |
|---|---|
| 0 | Success, including "nothing to do". |
| 1 | Hard error: bad configuration, a malformed invocation, or an unexpected failure. |

## Guarantees

- **This tool never runs `git push`.** It does not appear anywhere in the
  codebase, and it never will: writing a file is reversible, publishing it
  is not, and this plugin only ever does the former.
- **The knowledge base's own git sync, if any, is entirely yours to manage.**
  This plugin writes files into it and nothing more.
