# BACKLOG.md

Version: 1.0

Status: Active

---

# Current Backlog

## Next Engineering Package

### EP-039 — GitHub Integration

Implemented scope:

- A new, independent Core -> Service -> Module subsystem
  (`src/core/github/`, `src/services/github_service.py`,
  `src/modules/github_module.py`) exposing eight read-only operations
  -- repository information, the authenticated user's own
  repositories, list/get issue, list/get pull request, list/get
  commit -- against the GitHub REST API, using the project's existing
  `requests` dependency directly. No third-party GitHub SDK was added.
  No create, update, delete, comment, merge, close, reopen, release,
  or any other write/mutating GitHub operation exists anywhere in this
  subsystem. `GitHubService` has no dependency on any other
  Engineering Package's service or engine, like `GitService` (EP-038)
  before it. Config-gated in Bootstrap via `github.enabled` (default
  true), matching every other soft-toggle subsystem. Authentication
  uses the `GITHUB_TOKEN` environment variable only -- it is never
  placed in `config/config.yaml` or any other config file, and it is
  never logged or included in an exception message or CLI output. See
  CHANGELOG.md / docs/RELEASE_NOTES.md /
  docs/architecture/designs/EP039_DESIGN.md for full detail.

Status:

STEP 1-3 complete (design, implementation, and documentation). STEP 4
Architecture Audit not yet performed -- EP-039 is not yet marked
complete in docs/architecture/JARVIS_ROADMAP.md, and "Next Engineering
Package" below remains EP-039 rather than advancing to EP-040 until
that audit is done.

Note: EP-038 — Git Integration is now fully complete through STEP 4
(see CHANGELOG.md / docs/RELEASE_NOTES.md /
docs/architecture/audits/EP038_AUDIT.md), and is now marked complete
in docs/architecture/JARVIS_ROADMAP.md. It is a new, independent
Core -> Service -> Module subsystem (`src/core/git/`,
`src/services/git_service.py`, `src/modules/git_module.py`) exposing
five read-only operations -- `status`, `diff`, `log`, `branch`,
`show` -- by shelling out to the system `git` executable via
`subprocess`, with no third-party git library. `GitService` has no
dependency on any other Engineering Package's service or engine -- the
first EP since EP-033 with zero cross-EP runtime dependency.

SCOPE NOTE: EP-038 STEP 4 was a read-only Architecture Audit. It
identified one new, non-urgent architecture-debt item: AD-009 (Low) --
`GitService.show()` passes a caller-supplied `ref` directly into
`git show`'s argv without the `--` separator `diff()` already
correctly uses for its own caller-supplied `path`, a narrow
defensive-coding inconsistency with limited practical impact (`git
show` has no generic write/execute option). Recorded in
docs/architecture/ARCHITECTURE_DEBT.md and explicitly deferred to a
future Architecture Cleanup milestone, not to EP-039.

---

# Purpose

This document contains ideas, improvements, feature requests and future work that are not yet assigned to an Engineering Package.

Items in this document are not commitments.

They serve as a pool of potential future work.

---

# Rules

Items may be added at any time.

Items may be removed.

Items may later become Engineering Packages.

Priority may change.

---

# Current Backlog

## AI

- Improve project retrieval quality
- Support hybrid search
- Support code embeddings
- Improve provider selection
- Feed EP-022's assembled RAG context into the AI Provider Framework
  for chat completion (deliberately out of scope for EP-022 itself)

---

## User Experience

- Better shell autocomplete
- Command history search
- Improved progress indicators

---

## Tools

- Git integration improvements
- Local file watcher
- Background indexing

---

## Future Ideas

- Voice commands

- Browser automation

- Desktop assistant

- Plugin marketplace

---

End of document.