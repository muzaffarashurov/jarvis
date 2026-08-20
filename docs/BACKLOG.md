# BACKLOG.md

Version: 1.0

Status: Active

---

# Current Backlog

## Next Engineering Package

### EP-043 — REST API

Not yet started. STEP 1 (Design) has not begun.

Note: EP-042 — Email Integration is now fully complete through
STEP 4 (see CHANGELOG.md / docs/RELEASE_NOTES.md), and is now marked
complete in docs/architecture/JARVIS_ROADMAP.md. It is a new,
independent Core -> Service -> Module subsystem
(`src/core/email/`, `src/services/email_service.py`,
`src/modules/email_module.py`) exposing exactly four read-only
operations -- `list_folders()`, `list_messages(folder, limit)`,
`get_message(folder, uid)`, `search_messages(folder, criteria)` --
against a standard, provider-independent IMAP server, using the
Python standard library (`imaplib` + `email`) directly. No
send/reply/forward/delete/move/flag operation, no provider-specific
API (Gmail API, Microsoft Graph, Outlook API), no OAuth, and no
background polling exists anywhere in this subsystem.
Authentication uses two configurable environment-variable names
(default `EMAIL_IMAP_USERNAME`/`EMAIL_IMAP_PASSWORD`), read per-call
and never placed in config. `email.enabled` defaults to `false`
(unlike EP-039/040/041's `true` default), since IMAP has no safe
universal default host. `EmailService` has no dependency on any
other Engineering Package's service or engine.

SCOPE NOTE: EP-042 STEP 3 was a Deep Audit and returned a final
verdict of PASS WITH NOTES. Three defects were found and fixed (see
CHANGELOG.md "Fixed" section for v0.1.9-ep042), and no P0
(security/data-mutation) issue was identified. One pre-existing,
out-of-scope technical-debt item was recorded but deliberately left
unfixed: `TestRegistry`'s `NAME.upper()` keying means only one of
`EmailServiceTest`/`EmailModuleTest` is reachable via the CLI
`test EP042` command -- this predates EP-042, affects every prior
integration EP's Service/Module test pair as well, and should be
handled by a separate future maintenance EP.

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