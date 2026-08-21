# BACKLOG.md

Version: 1.0

Status: Active

---

# Current Backlog

## Next Engineering Package

### EP-043 — REST API

STEP 1 (Investigation), STEP 2 (Implementation), STEP 3 (API Contract
Hardening), and STEP 4 (Finalization & Release Readiness) all
complete. EP-043 is now marked COMPLETE. Scope was confirmed directly
by the project owner (the STEP 1 investigation stopped because the
repository established only the title "REST API," with no purpose,
consumers, endpoint surface, security model, dependency, or lifecycle
integration defined anywhere -- see `EP043_STEP1_REPORT.md`). Full
design: `docs/architecture/designs/EP043_DESIGN.md`.

As built: `RestApiServer` (`src/core/api/rest_api_server.py`) is a
Bootstrap-level sibling of `InteractiveShell` -- not a
Core -> Service -> Module subsystem -- built entirely on the Python
standard library (`http.server`), with no new `requirements.txt`
dependency. It binds `127.0.0.1:8080` by default and exposes three
endpoints: `GET /health`, `GET /api/v1/status`, `POST
/api/v1/commands`. `ApiRouter` (`src/core/api/api_router.py`)
dispatches every command request through the exact same
`CommandRouter` instance `InteractiveShell` and `TelegramRouter`
already use -- no business logic was added or duplicated.
`api.enabled` defaults to `false` (unlike EP-039/040/041's `true`
default), a deliberate deviation from the implementation prompt's
illustrative `enabled: true` example: unlike those stateless outbound
clients, enabling this subsystem binds and listens on a real network
socket as a side effect of `Bootstrap.initialize()`, so it stays off
by default for safety and to avoid port conflicts in the many existing
EP-001..042 tests that construct a real `Bootstrap` for wiring checks
alone.

DEFERRED (see Non-goals in `EP043_DESIGN.md`, and Future Ideas below):
authentication/authorization, TLS, CORS, rate limiting, OpenAPI/Swagger
generation, WebSocket support, per-subsystem REST resources (v1 has
one generic command endpoint instead of e.g. dedicated
`/api/v1/email/...` routes).

STEP 3 (contract hardening, see `EP043_STEP3_REPORT.md`) added a
`415 Unsupported Media Type` response for `POST /api/v1/commands`
when `Content-Type` is present and not `application/json` (a missing
header is still treated leniently), and fixed a robustness gap where a
malformed `api.port` (wrong type or out of range) could raise an
uncaught exception during `Bootstrap.initialize()` instead of
degrading safely to "REST API disabled." No endpoint, status-code
policy, or configuration default changed.

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
handled by a separate future maintenance EP. EP-043 deliberately
sidesteps this collision by registering a single `EP043` test suite
rather than a same-named Service/Module pair.

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
- REST API authentication/authorization (API keys, JWT, OAuth, RBAC) -- deferred from EP-043 v1
- REST API TLS/HTTPS support -- deferred from EP-043 v1
- REST API CORS configuration -- deferred from EP-043 v1
- REST API rate limiting -- deferred from EP-043 v1
- REST API OpenAPI/Swagger schema generation -- deferred from EP-043 v1
- Per-subsystem REST resources (e.g. dedicated /api/v1/email/... routes) -- deferred from EP-043 v1, which ships one generic /api/v1/commands endpoint instead
- TestRegistry NAME-collision fix (Service/Module test pairs sharing a NAME are only partially reachable via `test EP0NN`) -- pre-existing since EP-038, tracked again during EP-042 and EP-043

---

## Future Ideas

- Voice commands

- Browser automation

- Desktop assistant

- Plugin marketplace

---

End of document.