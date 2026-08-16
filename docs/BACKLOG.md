# BACKLOG.md

Version: 1.0

Status: Active

---

# Current Backlog

## Next Engineering Package

### EP-040 — Telegram Information Integration

Implemented scope:

- A new, independent Core -> Service -> Module subsystem
  (`src/core/telegram_info/`, `src/services/telegram_info_service.py`,
  `src/modules/telegram_info_module.py`) exposing exactly one
  read-only operation -- `get_chat(chat_id)` -- against the Telegram
  Bot API, using the project's existing `python-telegram-bot`
  dependency directly. No message history, `getUpdates`/polling,
  chat listing/discovery, or any write/mutating Telegram operation
  exists anywhere in this subsystem; the first two are not achievable
  at all through the Bot API tier this project uses. Deliberately
  separate from EP-012 "Telegram Gateway" (`src/core/telegram/`,
  `src/services/telegram_service.py`,
  `src/modules/telegram_module.py`), which remains fully responsible
  for the inbound control gateway and was not modified -- all four of
  its files were confirmed byte-identical before and after this
  implementation. `TelegramInfoService` constructs its own,
  independent `telegram.Bot` instance and never calls
  `fetch_updates()`/`get_updates()` or touches EP-012's update
  offset/cursor. The existing `telegram.token` (EP-012's key) is
  reused read-only; no second token configuration was added.
  Config-gated in Bootstrap via `telegram_info.enabled` (default
  true). See CHANGELOG.md / docs/RELEASE_NOTES.md /
  docs/architecture/designs/EP040_DESIGN.md for full detail.

Status:

STEP 1-3 complete (design, implementation, and documentation). STEP 4
Architecture Audit not yet performed -- EP-040 is not yet marked
complete in docs/architecture/JARVIS_ROADMAP.md, and "Next Engineering
Package" below remains EP-040 rather than advancing to EP-041 until
that audit is done.

Note: EP-039 — GitHub Integration is now fully complete through
STEP 4 (see CHANGELOG.md / docs/RELEASE_NOTES.md /
docs/architecture/audits/EP039_ARCHITECTURE_AUDIT.md), and is now
marked complete in docs/architecture/JARVIS_ROADMAP.md. It is a new,
independent Core -> Service -> Module subsystem (`src/core/github/`,
`src/services/github_service.py`, `src/modules/github_module.py`)
exposing eight read-only operations against the GitHub REST API,
authenticated via the `GITHUB_TOKEN` environment variable only (never
placed in config). `GitHubService` has no dependency on any other
Engineering Package's service or engine.

SCOPE NOTE: EP-039 STEP 4 was a read-only Architecture Audit and
returned a final verdict of PASS. No new architecture debt was
identified -- the audit explicitly confirmed that GitHub's deferred
Tool Engine registration, absence of pagination/retries, and
read-only scope are deliberate scope decisions, not architectural
defects. Exactly one authoritative `GitHubService`/`GitHubModule`
implementation was confirmed, with no duplicate/parallel client.

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