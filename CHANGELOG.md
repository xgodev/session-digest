# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-09-09

### Removed

- The plugin's own scheduling and agent-invocation layers: `installer.py`
  (the launchd plist / crontab writer), `runner.py` (the `claude -p`
  subprocess layer, `build_prompt`, `run_project`, `run`, `DigestResult`),
  and `lock.py` (the directory lock that only existed to stop two scheduled
  runs colliding). Removed with them: the `install`, `uninstall`, and `run`
  CLI subcommands and their tests, and the `schedule`, `timeout`, and
  `commit` configuration fields that only served this code.
- Reason: Claude Code now has a native local scheduled-task facility that
  stores a task as a skill under `~/.claude/scheduled-tasks/<id>/SKILL.md`
  and runs it as a real Claude session. A scheduled task IS an agent
  session, so it reads the `session-digest` skill and calls `scan` and
  `extract` directly — no installer, no subprocess invocation, and no lock
  are needed to make that happen. Keeping this plugin's own scheduling and
  invocation code around after that would have meant maintaining and
  documenting machinery that no longer does anything a user needs.

### Changed

- `scan` and `extract` are unaffected: they remain the deterministic,
  unit-tested prep work an agent still needs, and the watermark state
  (`session_digest.state`, including `advance_watermark`) stays as the
  public surface an agent session uses to record progress once it has
  judged a project's sessions.
- `README.md` rewritten to describe the tool as two deterministic commands
  plus a skill, with scheduling left entirely to Claude Code's own
  scheduled tasks.

## [0.1.0] - 2026-09-09

### Added

- Initial release: a stdlib-only Python CLI (`session-digest`) that finds
  Claude Code sessions newer than a per-project watermark, discards the
  obviously empty by objective signals (user turns, whether files were
  written, whether anything was committed, size), condenses the rest into
  slices that fit an agent's context, and invokes a headless agent once per
  project via `claude -p`.
- Commands: `scan` (list pending projects), `extract` (print one project's
  condensed transcript), `run` (digest every pending project end to end),
  `install` (schedule the periodic job via launchd on macOS or crontab
  elsewhere), and `uninstall` (remove it).
- Per-project watermark state that advances only on success, an atomic
  directory lock with orphan reclamation so a crashed run cannot wedge every
  future run, and a configuration file (`~/.claude/session-digest.json`)
  covering the knowledge base location, schedule, opt-in commit behaviour,
  and per-project repository mappings.
- The `session-digest` skill: judges whether a batch of condensed sessions
  contains anything worth recording, and if so routes technical learnings to
  the project's own repository and project narrative to the configured
  knowledge base, using six note templates (timeline, decisions, pending
  work, corrections, learnings, and a map-of-content index).
- 84 tests covering the watermark, the cheap filter, project grouping, the
  extractor's slicing, the lock, and the installer.
