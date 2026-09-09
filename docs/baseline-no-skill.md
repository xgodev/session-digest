# Baseline: distilling a session with no skill (RED)

This is the RED evidence for `skills/session-digest/SKILL.md`, required by
`superpowers:writing-skills` before authoring the skill. It was produced by
running the scenario the skill is meant to govern — condense a real session
transcript into notes — with no skill loaded at all.

**Setup:** 60KB slice of a real Claude Code transcript, a knowledge base
folder holding one pre-existing note, and an empty sandbox repository
(containing only `README.md`).

**Task given:** distil the transcript into notes.

## Observed failures

### (a) Routing never happened — everything went to the knowledge base

Nothing was written to the repository. Every finding, including technical
gotchas that belonged in the repo's own living docs, went to the knowledge
base note instead. The agent rationalised this in its own words:

> the technical gotchas "já foram registrados no CLAUDE.md do próprio repo
> durante a sessão" (already recorded in the repo's own CLAUDE.md during the
> session)

This claim was never checked and was false — the sandbox repo contained only
`README.md`. The routing half of the design (technical learning to the repo,
narrative to the knowledge base) silently did not happen at all, even though
the agent reasoned about routing and reached a wrong conclusion.

### (b) The pre-existing note was replaced wholesale, not updated

The agent rewrote the one pre-existing knowledge-base note's frontmatter
entirely and reset its `criado:` (created) date to today, instead of reading
it first and updating it in place. Prior content and its original creation
date were lost.

### (c) The note was named after the session, not the project

The agent named the note after the session itself (e.g.
`music-ruler - sessão 2026-08-31.md`), rather than a stable, project-scoped
file name. A second run on the same project would add another loose,
session-named note instead of converging on the same set of files.

## What the baseline got right (must not regress)

- It did not dump the raw transcript — it curated genuinely.
- It did reason about routing, even though it concluded wrongly (false
  premise about the repo's contents, never verified by reading the repo).

## Requirements these failures impose on the skill

1. Routing to the repository must be based on what is actually on disk in
   the repo, never assumed — and must actually happen when substance
   warrants it.
2. Existing notes must be read before writing, and updated in place:
   frontmatter and the original `criado`/created date must be preserved.
3. File names must be stable per project/topic, not per session, so repeated
   runs converge on the same files instead of accumulating new ones.
