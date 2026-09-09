# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
