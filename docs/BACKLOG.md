# BACKLOG.md

Version: 1.0

Status: Active

---

# Current Backlog

## Next Engineering Package

### EP-048 — Wake Word

**NOT STARTED.** Per `docs/architecture/JARVIS_ROADMAP.md`'s Phase 7
sequencing, EP-048 (Wake Word) is the next Engineering Package after
EP-047's completion. No design, research, or implementation work has
begun. `src/skills/voice/wake_word.py` remains the empty,
pre-existing placeholder EP-046's own design already identified for
it -- confirmed byte-identical to its EP-046-shipped (empty) state
throughout EP-047 STEP 1-3.

### EP-047 — Text-to-Speech

STEP 1 (Design & Research), STEP 2 (Implementation & Verification),
and STEP 3 (Documentation & Audit Closure) all complete. EP-047 is
now marked COMPLETE with verdict **PASS WITH DOCUMENTED
LIMITATIONS**. Full design: `docs/architecture/designs/EP047_DESIGN.md`
(including Section 9a's record of the owner decisions that resolved
STEP 1's open questions, and Section 17's as-built summary). Full
audit: `docs/architecture/audits/EP047_AUDIT.md`.

Built as an offline `pyttsx3`-based TTS engine
(`src/skills/voice/text_to_speech.py`) that speaks text through the
OS's native speech driver (SAPI5 on Windows), composed into the
*existing* `voice` `CommandModule` (`src/skills/voice/skill.py`) as
an additive `speak` action -- no new dispatch mechanism, no second
namespace, no change to `src/core/command_router.py`,
`src/core/api/`, Telegram, `desktop/`, or `web/`. Action: `voice
speak <text>`, joined from its arguments and spoken via a blocking
`engine.say()`/`engine.runAndWait()` call; never dispatches through
`CommandRouter` and never automatically speaks another command's
result. Supports English and Russian, contingent on a matching OS
voice being installed -- Uzbek is explicitly out of scope (no offline
TTS engine evaluated has a first-class Uzbek voice) and receives no
special-case handling anywhere in code: an unconfigured or
voice-less language always fails the same generic path, whether
that language is Uzbek or any other. `voice.tts.enabled` defaults to
`false`, independent of `voice.enabled` (STT) for failure-mode
purposes (a TTS construction failure never disables STT, and vice
versa) -- though the `voice` namespace itself remains registered only
when `voice.enabled` (STT) is also true, a disclosed, as-built
limitation (see `EP047_AUDIT.md` Known Limitations). Tests: EP-047
49/0/0; EP-043 83/83, EP-044 52/52, EP-045 38/38, EP-046 57/0/1 all
unchanged; full suite 5,655 passed / 0 failed / 1 skipped in this
verification run (an earlier-documented two-failure baseline for
EP-039/EP-041 was re-investigated and found to be an
environment-dependent, network-availability difference, not a code
regression -- see `EP047_AUDIT.md` Section 11 for detail).

Two disclosed, non-blocking gaps remain: no real Windows/SAPI5
audible speech has been confirmed by a human in any environment this
project has run in, and TTS-only operation (with STT/microphone
fully disabled) is not currently supported, due to the
registration-gating limitation above. Recommended as the first
manual-verification item, and a candidate small follow-up design
decision, once EP-047 reaches the actual target Windows workstation.
See `EP047_AUDIT.md` Section 13 for full detail.

### EP-046 — Speech-to-Text

STEP 1 (Design & Planning), STEP 2 (Implementation & Verification),
and STEP 3 (Documentation & Audit Closure) all complete. EP-046 is
now marked COMPLETE with verdict **PASS WITH DOCUMENTED
LIMITATIONS**. Full design: `docs/architecture/designs/EP046_DESIGN.md`
(including Section 9a/9b/9c's record of the owner decisions that
resolved STEP 1's open questions, and Section 16's as-built summary).
Full audit: `docs/architecture/audits/EP046_AUDIT.md`.

Built as an offline Vosk-based STT engine
(`src/skills/voice/speech_to_text.py`) plus a separate `sounddevice`
audio-capture layer (`src/skills/voice/audio_capture.py`), composed
by a new `voice` `CommandModule` (`src/skills/voice/skill.py`) that
dispatches recognized text through the existing, unmodified
`CommandRouter` -- no new dispatch mechanism, no `src/core/api/`,
Telegram, or `desktop/`/`web/` change. Actions: `voice listen`
(primary -- capture, transcribe, and dispatch if confident enough),
`voice transcribe` (capture and transcribe only, never dispatch),
`voice status`, `voice help`. Supports Russian, Uzbek, and English
via Vosk small models (`vosk-model-small-ru-0.22`,
`vosk-model-small-uz-0.22`, `vosk-model-small-en-us-0.15`), manually
installed under `voice.model_dir` -- none bundled in the repository.
`voice.enabled` defaults to `false`; low-confidence transcripts are
never auto-executed. Tests: EP-046 57/0/1 (one disclosed, expected
skip); EP-043 83/83, EP-044 52/52, EP-045 38/38 all unchanged; full
suite 5,641 passed / 2 failed (EP-039/EP-041, pre-existing and
independently confirmed unrelated to EP-046) / 1 skipped.

Two disclosed, non-blocking gaps remain, both stemming from the same
cause -- no Vosk model files and no physical microphone exist in any
environment this project has run in: no real audio has been
transcribed by a loaded model, and no real microphone capture has
been verified. Recommended as the first manual-verification item
once EP-046 reaches the actual target workstation. See
`EP046_AUDIT.md` Section 14 for full detail.

### EP-045 — Web Dashboard

STEP 1 (Design & Architecture Investigation), STEP 2
(Implementation), and STEP 3 (Documentation & Audit Closure) all
complete. EP-045 is now marked COMPLETE with verdict **PASS**. Full
design: `docs/architecture/designs/EP045_DESIGN.md` (including
Section 22a's record of the owner decisions that resolved STEP 1's
open questions). Full audit:
`docs/architecture/audits/EP045_AUDIT.md`.

As built: `web/public/{index.html, app.js, styles.css}` is a plain
HTML/CSS/JavaScript dashboard -- no framework, no build step, no new
dependency -- consuming EP-043's REST API exclusively, over
same-origin `fetch()` calls to `GET /health`, `GET /api/v1/status`,
and `POST /api/v1/commands` using relative URLs (no dashboard-side
API base URL configuration is needed, a direct consequence of
same-origin serving). Same-origin serving was implemented by adding
an **optional** `static_dir` capability to the existing
`RestApiServer` (`src/core/api/rest_api_server.py`) -- off by
default, gated by a new, opt-in `api.web_dashboard_dir` config key
(`config/config.yaml`) resolved in `src/bootstrap.py`. This was the
one `src/core/api/` change made in this EP, demonstrated as
technically necessary before being made (only one process can bind
`api.host:api.port`, and a CORS policy was ruled out by owner
decision) -- see `EP045_AUDIT.md` Section 6/7 for the verification.
No CORS policy, no authentication, and no network-exposure change
were introduced; EP-043's three existing routes and their behavior
are byte-identical to before this EP.

DEFERRED (see Non-Goals in `EP045_DESIGN.md`, and Future Ideas
below): chat, memory browser, agent management, workflow editor,
voice control, file management, notifications, authentication UI,
periodic health-check polling, command history, CLI-syntax command
input.

NON-BLOCKING LIMITATION (see `EP045_AUDIT.md` Section 5/14 for
detail): `web/public/app.js` and `styles.css` have no dedicated
automated unit test -- no JavaScript test runner exists in this
project. Both were verified working via a manual functional smoke
test during STEP 2. This does not affect correctness, security,
architecture, or any passing `test EP045` assertion.

OWNER DECISION REQUIRED (carried from STEP 1, still open): explicit
target-browser sign-off (STEP 1 proposed "current evergreen browsers
only"; STEP 2 implemented against that assumption but the owner has
not explicitly re-confirmed it as final).

Note: EP-044 — Desktop UI is now fully complete through STEP 3 (see
`docs/architecture/designs/EP044_DESIGN.md` and
`docs/architecture/audits/EP044_AUDIT.md`), and remains marked
complete in `docs/architecture/JARVIS_ROADMAP.md`, unchanged by
EP-045 (`desktop/` confirmed byte-identical to its pre-EP-045 state).
STEP 1 (Design & Architecture Investigation), STEP 2
(Implementation), and STEP 3 (Final Verification, Architectural
Audit & Documentation) all complete. EP-044 is now marked COMPLETE
with verdict **PASS WITH DOCUMENTED LIMITATIONS**. Full design:
`docs/architecture/designs/EP044_DESIGN.md`. Full audit:
`docs/architecture/audits/EP044_AUDIT.md`.

As built: `desktop/` is a new top-level package (a PySide6 MVVM
client, not nested under `src/`), consuming EP-043's REST API
exclusively over HTTP -- `desktop/api/jarvis_api_client.py` (built on
the already-existing `requests` dependency) is the only component
that talks to Jarvis, calling `GET /health`, `GET /api/v1/status`,
and `POST /api/v1/commands` unchanged. No file under `src/core/`,
`src/services/`, or `src/modules/` is imported by `desktop/`
business logic. Network calls run on a worker `QThread`
(`desktop/viewmodels/api_worker.py`) with results delivered back to
the UI thread via Qt signals, so the GUI event loop is never blocked.
Desktop configuration (host/port/timeout) is stored separately from
`config/config.yaml`, in a per-user YAML file
(`desktop/config/desktop_config.py`), matching the design's required
separation of client and server configuration. `PySide6==6.11.2` was
added to `requirements.txt` as the project's first-ever GUI
dependency; no other dependency changed.

DEFERRED (see Non-Goals in `EP044_DESIGN.md`, and Future Ideas
below): tray integration, desktop notifications, command history,
CLI-syntax command input, packaging/installer/executable generation,
authentication UI, chat/memory/agent browsers, workflow editor,
voice control, file management.

NON-BLOCKING LIMITATION (see `EP044_AUDIT.md` Section 5 for detail):
`EP044_DESIGN.md` Section 20 (Logging) specifies reusing the
project's `loguru` convention for connection attempts, state
transitions, and command submissions/results; the STEP 2
implementation does not yet call `loguru` anywhere in `desktop/`.
This does not affect correctness, security, architecture, or any
passing test, and is left for a small, separate follow-up rather
than folded into the STEP 3 audit gate.

OWNER DECISION REQUIRED (carried from STEP 1, still open): automatic
health-check polling cadence (STEP 2 implemented manual-only,
consistent with the design leaving this unresolved); target
platform(s) for future packaging (Windows/Linux/macOS); packaging
scope (own EP vs. EP-044 sub-package); ownership of the three
pre-existing, empty `src/ui/dashboard.py` / `tray.py` /
`notifications.py` placeholder files, which STEP 1, STEP 2, and
STEP 3 all confirmed remain untouched and byte-identical to their
pre-EP-044 state.

Note: EP-043 — REST API is now fully complete through STEP 4 (see
CHANGELOG.md / docs/RELEASE_NOTES.md), and remains marked complete in
docs/architecture/JARVIS_ROADMAP.md, unchanged by EP-044. STEP 1
(Investigation), STEP 2 (Implementation), STEP 3 (API Contract
Hardening), and STEP 4 (Finalization & Release Readiness) all
complete. Scope was confirmed directly by the project owner (the
STEP 1 investigation stopped because the repository established only
the title "REST API," with no purpose, consumers, endpoint surface,
security model, dependency, or lifecycle integration defined anywhere
-- see `EP043_STEP1_REPORT.md`). Full design:
`docs/architecture/designs/EP043_DESIGN.md`.

As built: `RestApiServer` (`src/core/api/rest_api_server.py`) is a
Bootstrap-level sibling of `InteractiveShell` -- not a
Core -> Service -> Module subsystem -- built entirely on the Python
standard library (`http.server`), with no new `requirements.txt`
dependency (at the time of EP-043; EP-044 subsequently added
`PySide6` for its own, separate Desktop client). It binds
`127.0.0.1:8080` by default and exposes three endpoints:
`GET /health`, `GET /api/v1/status`, `POST /api/v1/commands`.
`ApiRouter` (`src/core/api/api_router.py`) dispatches every command
request through the exact same `CommandRouter` instance
`InteractiveShell` and `TelegramRouter` already use -- no business
logic was added or duplicated. `api.enabled` defaults to `false`
(unlike EP-039/040/041's `true` default), a deliberate deviation from
the implementation prompt's illustrative `enabled: true` example:
unlike those stateless outbound clients, enabling this subsystem
binds and listens on a real network socket as a side effect of
`Bootstrap.initialize()`, so it stays off by default for safety and
to avoid port conflicts in the many existing EP-001..042 tests that
construct a real `Bootstrap` for wiring checks alone.

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