# EP-044 Desktop UI — Design Specification

Status: **STEP 1 — Design and Architecture Investigation (no
implementation).** The roadmap (`docs/architecture/JARVIS_ROADMAP.md`)
establishes only the two-word title "Desktop UI" for EP-044, with no
functional scope, target platform, or technology defined anywhere in
the repository. `docs/BACKLOG.md`'s "Future Ideas" list contains one
unelaborated entry, "Desktop assistant," which is not evidence of a
defined feature set. This mirrors EP-043's STEP 1 starting condition
(see `docs/architecture/designs/EP043_DESIGN.md`, header note), and
this document follows the same resolution pattern: derive everything
that *is* determinable from existing architecture, and mark everything
that is a genuine product decision as **UNRESOLVED** or
**RECOMMENDED — OWNER APPROVAL REQUIRED** rather than inventing it.

Follows `EP043_DESIGN.md`'s structure and terminology where
applicable. EP-044 is architecturally a **second consumer** of the
same pattern EP-043 introduced (external client via HTTP), not a new
architectural layer.

---

## 1. Status

STEP 1 — Design and Architecture Investigation. No implementation
code has been written. This document, and the STEP 1 final report,
are the only outputs of this step.

## 2. Objective

Determine the correct architecture for a native Desktop UI that lets
a local user interact with Jarvis graphically, as an external client
of the existing EP-043 REST API — without duplicating `CommandRouter`,
`Service`, `Core`, or `Module` logic, and without modifying any
existing source file.

## 3. Problem Statement

Jarvis currently exposes three transports into the shared
`CommandRouter`: `InteractiveShell` (terminal CLI), `TelegramRouter`
(chat bridge), and, as of EP-043, `RestApiServer` (local HTTP). All
three are either text-only or remote-chat-only. There is no graphical,
windowed interface for a user sitting at the same machine Jarvis runs
on. `src/ui/` already contains three placeholder files
(`dashboard.py`, `tray.py`, `notifications.py`) — all zero bytes,
i.e. reserved but unimplemented — which is repository evidence that a
graphical surface was anticipated, but they define no contract,
class, or convention to build on.

## 4. Current State

- `src/ui/dashboard.py`, `src/ui/tray.py`, `src/ui/notifications.py`
  exist and are empty (0 bytes). No class, function, or docstring to
  reuse or extend. They do not constitute an existing architecture and
  are not assumed to define EP-044's shape.
- EP-043 (`RestApiServer`/`ApiRouter`, `src/core/api/`) is complete
  and is the only programmatic, non-interactive-shell entry point into
  Jarvis. Full contract in Section 13 below.
- `requirements.txt` contains no GUI toolkit (no `PySide6`, `PyQt6`,
  `tkinter` is stdlib and not listed, `wxPython`, `Kivy`, `Dear PyGui`
  — none present).
- `requirements.txt` already contains `requests`, actively used for
  outbound HTTP by `src/services/github_service.py`,
  `src/services/discord_service.py`,
  `src/core/ai/providers/gemini_provider.py`, and
  `src/core/ai/claude_provider.py`. This is an existing, proven
  dependency for talking to an HTTP endpoint from Jarvis-owned code —
  directly reusable for the Desktop UI's REST client with **zero new
  dependency** for that layer.
- `pyproject.toml` declares `requires-python = ">=3.12"`. No OS marker,
  platform classifier, or packaging tool configuration exists.
- No `docs/architecture/JARVIS_ARCHITECTURE_VISION.md`,
  `PROJECT_OVERVIEW.md`, or `README.md` passage specifies a target
  operating system, windowing toolkit, or "primary user" persona for
  a graphical interface. `README.md` describes Jarvis generally as
  supporting "software development, automation, desktop control and
  knowledge management," which does not specify a UI technology.
- `docs/BACKLOG.md` lists REST API auth/TLS/CORS/rate-limiting as
  explicitly deferred from EP-043 v1 — none has been implemented since.

## 5. Desired State

A minimal, native Desktop UI application that:

- Runs as an independent process from the Jarvis server process (the
  one running `Bootstrap`/`RestApiServer`/`InteractiveShell`).
- Communicates with Jarvis exclusively through the existing EP-043
  REST API — never through direct imports of `Core`, `Service`, or
  `Module` code.
- Displays connection/health state, lets the user submit a command,
  and displays the result or an error — matching, at minimum, what
  `InteractiveShell` already exposes over the CLI.
- Never freezes the UI thread while waiting on a network response.
- Remains additive: it must not alter `RestApiServer`, `ApiRouter`,
  `CommandRouter`, `InteractiveShell`, or any other existing
  transport.

## 6. Scope

**In scope for EP-044 STEP 1 (this document):**

- Technology evaluation and recommendation for the GUI toolkit.
- UI architectural pattern recommendation (MVC/MVP/MVVM).
- Application package structure.
- REST API client design (contract only — no implementation).
- Screen/window architecture for a minimal V1.
- Application state model.
- Threading/responsiveness model.
- Configuration model for the Desktop UI as a separate process.
- Error handling model.
- Logging approach.
- Packaging/distribution direction (design-level only).
- Platform support investigation.
- Testing strategy for a future STEP 2.
- Dependency evaluation.
- Backward compatibility analysis.

**Out of scope for STEP 1 (and for EP-044 V1, pending Section 12):**

See Section 7 and Section 12.

## 7. Non-Goals

- No implementation code, UI screens, widgets, windows, or application
  entrypoints (this STEP).
- No API client implementation (this STEP).
- No modification of `src/core/api/`, `src/bootstrap.py`,
  `config/config.yaml`, `requirements.txt`, or any other existing
  file.
- No new REST endpoints on the server side — EP-044 consumes EP-043's
  existing contract unchanged.
- No authentication/authorization design beyond what EP-043 already
  provides (none in v1) — see Section 20.
- No installer, executable, or packaging artifact (this STEP).
- No chat history, memory browser, agent management, workflow editor,
  project browser, settings dashboard, voice control, file management,
  or autonomous agent controls in V1 — no repository evidence
  supports including them (see Section 8).

## 8. User Interaction Scope

Derived from the actual EP-043 v1 endpoint surface (Section 13) and
from this STEP's own investigation checklist, which enumerates the
same capabilities as its "at minimum evaluate" baseline — i.e., the
V1 scope below is not invented; it is the graphical equivalent of the
REST API's existing surface, which is itself the graphical equivalent
of what `InteractiveShell` already does.

### REQUIRED FOR EP-044 V1

- Connection/health status display (`GET /health`).
- Jarvis status display (`GET /api/v1/status`).
- Command input (module, action, arguments) and submission
  (`POST /api/v1/commands`).
- Command result display (`success`/`message` body).
- Error display (network error, timeout, HTTP error, transport-level
  4xx/5xx per Section 13).
- Application connection configuration (API base URL / host / port),
  since the Desktop UI is a separate process from the Jarvis server
  and cannot assume the server's configured port (Section 17).

### OPTIONAL / FUTURE

- CLI-syntax single-line command input (parsed client-side into
  module/action/arguments) as an alternative to discrete input fields
  — see Section 15, Decision D5.
- System tray integration (there is a placeholder file,
  `src/ui/tray.py`, but it is empty and defines no contract; tray
  presence/behavior is not derivable from the repository and is not
  assumed for V1).
- Desktop notifications (same reasoning; `src/ui/notifications.py` is
  an empty placeholder, not a specification).
- Command history / previous-result log within a session.

### OUT OF SCOPE

- Chat history browser, memory browser, agent management, workflow
  editor, project browser, settings dashboard beyond connection
  configuration, voice control, file management, autonomous agent
  controls — none of EP-043's v1 endpoints expose these, and no
  design document defines them for EP-044.
- Any functionality requiring new REST endpoints beyond EP-043's
  existing three.
- Authentication UI (login screens, token entry) — EP-043 v1 has no
  authentication to configure (Section 20).

### UNRESOLVED — PROJECT OWNER DECISION REQUIRED

- Whether `src/ui/dashboard.py`, `src/ui/tray.py`,
  `src/ui/notifications.py` are intended to be filled in by EP-044, by
  a later EP, or are stale placeholders predating the current roadmap
  structure. They are empty and carry no docstring or comment
  indicating ownership. This document does not assume EP-044 owns
  them; STEP 2 should not silently populate them without an explicit
  owner decision, since doing so would be "modifying files not
  explicitly listed in the task" under `AI_GENERATION_STANDARD.md`'s
  File Modification Policy if their ownership is not first confirmed.

## 9. Technology Evaluation

Investigated against: Python 3.12 (`pyproject.toml`), no existing GUI
dependency, `pyautogui`/`selenium`/`openpyxl` already present (desktop
automation and spreadsheet libraries — not GUI toolkits, no bearing on
this decision), MIT license (`LICENSE`), and the project's
established stdlib-first, dependency-averse precedent set by EP-043
(Section 16 of `EP043_DESIGN.md`: "adds zero dependency-selection
risk," mirroring EP-042's `imaplib`-only `EmailService`).

| Criterion | Option A: PySide6 | Option B: PyQt6 | Option C: Tkinter |
|---|---|---|---|
| Python integration | Official Qt-for-Python bindings, actively maintained by the Qt Company | Community/Riverbank bindings, functionally similar to PySide6 | Stdlib, always available |
| License | LGPLv3 — compatible with distributing an MIT-licensed application | GPLv3 or commercial — GPL terms are not clearly compatible with the project's MIT license (`LICENSE`) without a commercial license purchase | Python Software Foundation License (stdlib) — no conflict |
| Cross-platform support | Windows, Linux, macOS — mature, uniform | Windows, Linux, macOS — mature, uniform | Windows, Linux, macOS — mature but visually dated, some platform inconsistencies |
| UI quality | Native-looking widgets, modern styling, rich widget set | Equivalent to PySide6 (same underlying Qt) | Basic; limited native styling without extra work |
| Threading / event-loop model | Qt event loop with `QThread` + signals/slots — a well-established pattern for keeping network I/O off the UI thread | Identical to PySide6 (same Qt event loop) | Single-threaded `tkinter` main loop; background work requires manual `after()` polling and a thread-safe queue — no native signal/slot equivalent |
| REST API integration | Straightforward: run `requests` calls in a `QThread`/worker, emit a Qt signal back to the UI thread | Same as PySide6 | Possible but more manual: a worker thread posts results into a `queue.Queue`, and the UI polls it via `after()` |
| Packaging / installer creation | Supported by PyInstaller and similar tools | Supported by PyInstaller and similar tools | Supported by PyInstaller; smallest resulting bundle since no extra toolkit ships |
| Dependency size | ~50-70 MB installed (Qt binaries) | Comparable to PySide6 | Zero — ships with CPython on Windows/macOS; on some Linux distributions `tkinter` requires a separate OS package (`python3-tk`), which is an OS-level dependency, not a `requirements.txt` one |
| Type safety | Full type stubs available (`PySide6-stubs` / built-in in recent releases) | Type stubs available (`PyQt6-stubs`) | Minimal typing support in stdlib `tkinter` |
| Maintainability | High — large ecosystem, long-term Qt Company backing | High — comparable ecosystem | Lower for a "native desktop UI" ambition — acceptable for a minimal utility window, but limited for future growth (Section 8 "Optional/Future") |
| New dependency required | Yes | Yes | No |
| Compatibility with project's dependency-averse precedent (Section 16, EP-043) | Violates the "no new dependency unless justified" default — but a GUI toolkit is a case where stdlib genuinely cannot deliver the stated objective (native desktop UI with a responsive, non-blocking UX) | Same as PySide6, plus a licensing concern the project has no stated position on | Fully compatible with the precedent — zero new dependency |

## 10. Technology Decision

**RECOMMENDED — OWNER APPROVAL REQUIRED**

Recommend **PySide6** as the primary candidate for a native, responsive
Desktop UI, with **Tkinter** documented as the zero-dependency
fallback if the owner prefers to preserve EP-043's "no new dependency"
precedent over UI quality/threading ergonomics.

**PyQt6 is not recommended**: its GPL/commercial dual license creates
an unresolved compatibility question against the project's MIT
`LICENSE` that PySide6 (LGPLv3) does not raise. This is excluded from
further consideration rather than left as a live option, since
PySide6 dominates it on every other criterion in Section 9.

This decision requires owner approval because it is the **first GUI
dependency ever introduced** into the project, and
`AI_GENERATION_STANDARD.md`'s Dependency Policy requires explaining
why existing infrastructure (the standard library) is insufficient
before adding one — Section 9's threading/event-loop and UI-quality
comparison is that justification, but the decision itself is a
product/architecture threshold the owner should confirm, not one
STEP 1 should finalize unilaterally.

```
Dependency: PySide6
Purpose: Native, responsive windowed GUI toolkit for the Desktop UI.
Why existing infrastructure is insufficient: The standard library's
  only GUI option, tkinter, has no signal/slot or event-driven
  async model — background REST calls would require manual queue
  polling via after(), which is materially harder to keep correct
  and responsive than Qt's QThread + signal/slot pattern (Section 15).
Alternative: tkinter (stdlib, zero new dependency, weaker threading
  ergonomics and dated widget styling) — viable if the owner prioritizes
  the zero-new-dependency precedent over UI/threading quality.
Decision: RECOMMENDED — OWNER APPROVAL REQUIRED.
```

## 11. UI Architecture

**Recommendation: MVVM (Model-View-ViewModel).**

Evaluated against MVC and MVP:

- **MVC** couples the Controller to specific View widgets, which in a
  Qt application tends to leak Qt widget references into logic that
  should be independently testable. Rejected for this project's stated
  testability requirements (`AI_GENERATION_STANDARD.md`, Testing
  Policy: "Avoid hidden dependencies").
- **MVP** is workable with Qt but requires each Presenter to manually
  push every state change into View methods, which duplicates state
  that Qt's signal/slot mechanism already exists to propagate
  automatically.
- **MVVM** fits Qt's signal/slot model directly: a ViewModel exposes
  Qt signals (e.g. `status_changed`, `command_result_received`,
  `error_occurred`) that Views (widgets) connect to declaratively. The
  ViewModel holds no reference to any widget, so it is fully testable
  headlessly (no `QApplication` event loop required) — directly
  satisfying Section 23's requirement to test as much as possible
  without launching a real GUI.

The REST API client (Section 14) is a Model-layer dependency injected
into ViewModels — never accessed directly by a View — consistent with
`AI_GENERATION_STANDARD.md`'s Dependency Policy (constructor injection,
no service instantiated inside business/UI logic).

## 12. Application Structure

```
desktop/
    app/                # Application entrypoint, QApplication setup, DI wiring
    api/                # REST API client (Section 14) — transport only
    models/              # Client-side DTOs mirroring src/core/api/dto.py's contract
    viewmodels/          # MVVM ViewModels — Qt signals, no widget references
    views/               # Qt widgets/windows — bind to ViewModel signals only
    state/               # Application state enum/model (Section 18)
    config/              # Desktop-client-only configuration (Section 17)
    resources/           # Icons, static assets (parallels existing assets/)
```

This mirrors the layering EP-043 established on the server side
(`RestApiServer` → `ApiRouter` → `CommandRouter`) with the direction
inverted: `views/` → `viewmodels/` → `api/` → the same
`POST /api/v1/commands` contract EP-043 already ships. No layer here
duplicates `CommandRouter`, `Service`, `Core`, or `Module` logic — the
deepest this package reaches into Jarvis is an HTTP call.

`desktop/` is proposed as a new top-level directory, parallel to
`src/`, rather than nested inside `src/ui/` — because the three
existing `src/ui/*.py` placeholders are unowned (Section 8,
UNRESOLVED) and this structure should not implicitly claim them. This
placement is itself a decision requiring confirmation; see Section 28,
Decision D1.

## 13. REST API Integration

Verified directly against `src/core/api/` and
`docs/architecture/designs/EP043_DESIGN.md` (Sections 8, 9, 21.4):

| Method | Path | Purpose | Request body | Success response | Error responses |
|---|---|---|---|---|---|
| `GET` | `/health` | Liveness check, no `CommandRouter` call | none | `200 {"status": "ok"}` | 404/405/500 |
| `GET` | `/api/v1/status` | Equivalent of CLI `system status` | none | `200 {"success": bool, "message": str}` | 404/405/500 |
| `POST` | `/api/v1/commands` | Generic `(module, action, arguments)` dispatch | `{"module": str, "action"?: str, "arguments"?: [str]}` | `200 {"success": bool, "message": str}` (always 200 once routed — business failure is carried in `success: false`, not the HTTP status) | 400 (malformed JSON / invalid fields), 404, 405, 415 (bad `Content-Type`), 500 |

Key contract facts the Desktop UI must respect:

- **`success: false` still returns HTTP 200.** The UI must branch on
  the JSON body's `success` field, not the HTTP status code, to
  distinguish "the command ran and failed" from "the command ran and
  succeeded." Only HTTP status distinguishes transport-level failures
  (Section 19).
- `Content-Type: application/json` should be sent explicitly on
  `POST /api/v1/commands` to avoid a `415` (a missing header is
  tolerated leniently server-side, but an explicit correct header
  avoids relying on that leniency).
- No authentication header or token is required or supported — see
  Section 20.
- Default server binding is `127.0.0.1:8080` (`config/config.yaml`,
  `api.host`/`api.port`), but this is only the *server's* default; the
  Desktop UI must treat host/port as its own configurable value
  (Section 17), not assume it.

The Desktop UI consumes exactly these three endpoints and no others.
It must not attempt to reach any Core/Service/Module class directly —
this is the "critical architectural principle" both this STEP's
instructions and EP-043's own design (`EP043_DESIGN.md` Section 6)
establish: Desktop UI → API Client → REST API → `ApiRouter` →
`CommandRouter` → existing architecture, unchanged.

## 14. API Client Design

`desktop/api/jarvis_api_client.py` (name illustrative — not created in
this STEP):

- Built on `requests` — already an established Jarvis dependency
  (Section 4), so this layer introduces **zero new dependencies**.
- Responsibilities: perform the three HTTP calls in Section 13,
  serialize the request body, deserialize the response body into
  client-side DTOs (Section 12, `models/`), and translate transport
  failures into a small, typed exception hierarchy the ViewModel layer
  can branch on (Section 19). It contains no business logic and makes
  no decision about *what* a command means — identical in spirit to
  how `ApiRouter` on the server side contains no business logic
  (`src/core/api/api_router.py` module docstring).
- **Timeout policy**: every request must specify an explicit timeout
  (`requests`' `timeout=` parameter) — undefined in the repository,
  proposed default of a few seconds, exact value marked
  `RECOMMENDED — OWNER APPROVAL REQUIRED` since it is a UX/product
  tradeoff, not purely architectural (Section 28, Decision D3).
- **Retries**: none proposed for V1. `POST /api/v1/commands` may
  dispatch commands with side effects (e.g. sending an email, per
  `EmailService`), so blind automatic retries on timeout risk
  duplicate execution. Retries are therefore explicitly **out of
  scope for V1** unless a future EP introduces command idempotency
  keys — not something this STEP can invent.
- **Connection errors** (server not running, wrong host/port):
  surfaced as a distinct client-side error type from **HTTP errors**
  (4xx/5xx, which mean the server responded) and from **malformed
  responses** (a 200 whose body isn't valid JSON, or is JSON but
  missing an expected field) — three distinct categories, all
  translated into the Section 19 error model.
- **API version handling**: the client targets `/api/v1/...`
  explicitly (not a bare `/status`/`/commands`), matching EP-043's own
  versioned surface. No version-negotiation logic is proposed, since
  EP-043 defines no version-negotiation mechanism to integrate with.
- **Base URL configuration**: injected into the client at
  construction time from Section 17's Desktop-owned configuration —
  never hardcoded.

Not implemented in this STEP, per Section 0 of the governing prompt.

## 15. Screen Architecture

Minimum V1 screen set, derived from Section 8's REQUIRED list:

### Main Window

- **Purpose**: the single window for V1. Hosts all required
  functionality; no multi-window navigation is justified by the
  current scope.
- **Data source**: `MainWindowViewModel`, backed by the API client.
- **API interaction**: triggers `GET /health` on startup/reconnect and
  polls or re-checks periodically (exact cadence: Section 28,
  Decision D4, UNRESOLVED).
- **State**: bound to the Section 18 application state model.
- **User actions**: submit a command, trigger a manual reconnect/health
  check, open connection settings.

Sub-areas within the Main Window (not separate windows):

| Area | Purpose | Data source | User actions |
|---|---|---|---|
| Connection indicator | Shows disconnected / connecting / connected / API unavailable | `GET /health` result, polled/refreshed | Manual "reconnect" trigger |
| Status area | Shows the `GET /api/v1/status` result (mirrors CLI `system status`) | `GET /api/v1/status` | Manual refresh |
| Command input | Module / action / arguments entry (Section 8, Decision D5) | User input | Submit |
| Output/result area | Shows the most recent `CommandResponse` (`success`, `message`) or the most recent error | `POST /api/v1/commands` result, or an error from Section 19 | None (read-only) |
| Connection settings | Host/port/timeout configuration (Section 17) | Section 17 Desktop config | Save / apply |

A separate modal "Settings" window is possible but not required for
V1; an inline settings panel within the Main Window is sufficient
given the small number of configurable values (host, port, timeout)
and avoids introducing multi-window navigation complexity not
justified by current scope.

This remains intentionally minimal per this STEP's instruction to
avoid designing a large UI platform.

## 16. Application State

Proposed states (Qt `Enum`, no external state-management framework —
none is justified by this scope):

```
DISCONNECTED
CONNECTING
CONNECTED
REQUEST_IN_PROGRESS
COMMAND_SUCCEEDED
COMMAND_FAILED
API_UNAVAILABLE
MALFORMED_RESPONSE
```

`ConnectionState` (disconnected / connecting / connected / API
unavailable) and `CommandState` (idle / in-progress /
succeeded / failed / malformed-response) are proposed as two small,
independent enums rather than one combined state machine, since the
connection health and the outcome of the last submitted command are
orthogonal concerns (a command can fail while the connection itself
stays healthy, e.g. `success: false` in Section 13). Held on the
`MainWindowViewModel` (Section 11) as plain Qt properties/signals — no
third-party state-management library (e.g. Redux-style stores) is
justified for two small enums and this scope.

## 17. Configuration

**Decision: the Desktop UI owns its own configuration, separate from
`config/config.yaml`.**

Reasoning: the Desktop UI is designed to run as an independent process
from the Jarvis server (Section 5). Reading `config/config.yaml`
directly would couple the Desktop UI's config lifecycle to the
server's, require the Desktop UI to have filesystem access to the
server's install directory even when running on a different machine
(the REST API already supports being reached over loopback from a
separate process — nothing in EP-043 assumes same-directory colocation
for a client), and would violate this STEP's explicit instruction:
"The Desktop UI must not require direct access to JARVIS's internal
configuration files unless explicitly justified." No such
justification exists in the repository.

Proposed Desktop-owned configuration values:

- API base URL (or separately, host + port) — default value proposed
  to mirror EP-043's own default (`127.0.0.1:8080`,
  `config/config.yaml` `api:` section) purely as a sensible starting
  value for the common case where both processes run on the same
  machine with default settings — not read from that file at runtime.
- Connection timeout (Section 14).
- Any future UI-only preferences (not defined for V1).

**UNRESOLVED — PROJECT OWNER DECISION REQUIRED**: the storage
mechanism for this Desktop-owned configuration (a small
`desktop/config/` YAML file analogous to `config/config.yaml`; a
per-user config file in a platform-appropriate location; or in-app
settings persisted via Qt's `QSettings`) is a product/platform
decision this STEP does not resolve, since it interacts directly with
the still-unresolved platform-support question (Section 21) and
appropriate storage locations differ by OS.

## 18. Error Handling

Proposed error categories, each mapped to a distinct, typed exception
in the API client (Section 14) and a distinct display treatment in the
UI:

| Category | Cause | Shown to user | Logged |
|---|---|---|---|
| Network error | Server unreachable, connection refused | Yes — plain-language "cannot reach Jarvis" message | Yes (debug level) |
| Timeout | Request exceeded the configured timeout | Yes — "request timed out" | Yes |
| HTTP error (4xx/5xx) | Transport-level rejection (Section 13) | Yes — the server's `ErrorPayload.message`, which is already guaranteed by EP-043 to never contain a stack trace (`api_error.py` docstring) | Yes |
| API validation error (400) | Malformed request the UI itself built (should be rare if the UI validates input before sending) | Yes | Yes |
| API internal error (500) | Unexpected server-side failure | Yes — generic message only, matching what the server already sends | Yes |
| Command failure (`success: false`, HTTP 200) | The command ran but the underlying operation failed (Section 13) | Yes — the `message` field, in the result area, not as an "error" per se | No (not an error — a normal result) |
| Malformed response | 200 status but body isn't valid JSON / missing expected fields | Yes — generic "unexpected response from Jarvis" | Yes, with the raw body at debug level only |
| Unexpected client error | Any exception not covered above (bug in the Desktop UI itself) | Yes — generic message, never a raw Python traceback in the UI | Yes, with full traceback |

Raw Python exceptions are never shown to the user directly, consistent
with EP-043's own client-facing error policy
(`api_error.py`: "the client never receives a Python stack trace").

## 19. Security

- EP-043 v1 has **no authentication or authorization**
  (`EP043_DESIGN.md` Sections 11-12; confirmed unchanged as of this
  STEP — Section 4). The Desktop UI therefore also has none to
  integrate with: any process that can reach the configured host/port
  can issue the same commands the Desktop UI can. This is not a new
  risk EP-044 introduces; it is the same risk EP-043 already accepted
  and documented, now exercised through a second client.
- The Desktop UI does not need to store credentials, tokens, or API
  keys for talking to Jarvis, because none exist in the current
  contract.
- If a future EP adds authentication to the REST API, the Desktop UI's
  API client (Section 14) is the layer that would need updating —
  documented here as a forward-compatibility note, not designed now.
- The Desktop UI should not expose internal error detail beyond what
  the server already sends (Section 18) — this is already guaranteed
  server-side by EP-043's `ApiInternalError` never carrying the
  original exception message.
- Because `POST /api/v1/commands` has "effectively shell-equivalent
  access" (`EP043_DESIGN.md` Section 19, "Risks"), a Desktop UI makes
  that access more discoverable/convenient to a local user, but does
  not change what is reachable — anyone who could already reach the
  loopback port could already do this via `curl` or any HTTP client.

## 20. Logging

- Reuse the project's existing `loguru` convention
  (`requirements.txt` already includes `loguru>=0.7.2`; used
  throughout `src/`, including `src/core/api/rest_api_server.py`) —
  no new logging framework is justified.
- Log connection attempts, state transitions (Section 16), and command
  submissions/results at a level consistent with existing components
  (e.g. `RestApiServer` logs server start/stop at `info`, request
  errors at `error` and `debug` — `src/core/api/rest_api_server.py`
  lines 110/205/330/341).
- Never log full command arguments if they could contain sensitive
  values entered by the user (mirrors this STEP's own instruction and
  the project's existing Logging Policy in `AI_GENERATION_STANDARD.md`:
  "Never log credentials... tokens... sensitive data").
- Desktop UI log destination (console vs. a log file under a
  Desktop-owned directory) is a packaging-adjacent detail deferred to
  STEP 2, since it depends on the still-unresolved platform-support
  and packaging decisions (Sections 21-22).

## 21. Packaging

Design-level only, per this STEP's explicit instruction — no
packaging tool is installed or invoked.

- **PyInstaller** is the most-established option for producing a
  standalone executable from a PySide6/Tkinter application and is
  compatible with both technology candidates in Section 9.
- Packaging is **not** part of EP-044 V1's functional scope (Section
  6/8) — it is a distribution concern, not a UI feature. Recommend
  packaging be scoped as its own later STEP or sub-package (e.g.
  EP-044.2), consistent with the project's own precedent for splitting
  large EPs (`JARVIS_ROADMAP.md`, "Engineering Package Policy").
- Until then, the Desktop UI runs from source (`python -m ...`), the
  same way the existing CLI (`src/main.py`) already does.

## 22. Platform Support

**UNRESOLVED — PROJECT OWNER DECISION REQUIRED.**

No document in `docs/architecture/`, `README.md`, or
`PROJECT_MANIFEST.md` specifies a target operating system for any
Jarvis component, including EP-044. `requirements.txt` includes
`pyautogui` (cross-platform desktop automation) and `selenium`
(cross-platform browser automation) — neither implies a specific OS.

This does not block the architecture: both technology candidates in
Section 9 (PySide6, Tkinter) are cross-platform (Windows/Linux/macOS)
by default, so the UI architecture in Sections 11-16 remains valid
regardless of which platform(s) are ultimately targeted. What remains
genuinely undecided is which platform(s) STEP 2 should actually build,
test, and package for — that is a scope decision, not an architecture
one, and is left to the owner.

## 23. Testing Strategy

Following the project's existing per-EP testing convention
(`tests/EP043/test_rest_api.py`, `AI_DEVELOPMENT_PLAYBOOK.md`
Phase 3), a future `tests/EP044/` suite should cover, without
launching a real GUI event loop wherever possible:

- **API client tests**: mock/stub HTTP responses (matching EP-043's
  own approach of testing against a real HTTP server on an
  OS-assigned ephemeral port, `EP043_DESIGN.md` Section 17) for all
  three endpoints, malformed JSON, non-2xx statuses, and connection
  refusal/timeout.
- **DTO/model tests**: client-side `models/` (Section 12)
  serialization/deserialization round-trips against known-good and
  known-bad payloads.
- **ViewModel/state tests**: since MVVM ViewModels (Section 11) hold
  no widget references, these are testable as plain Python objects —
  construct a ViewModel with a fake/mock API client, assert on emitted
  signals and resulting state (Section 16), with no `QApplication`
  instance required.
- **Error handling tests**: one test per Section 18 category, using a
  mock API client that raises/returns each case.
- Scenarios explicitly required by this STEP's instructions: connection
  failure, timeout, successful command, failed command
  (`success: false`), malformed API response — all covered by the
  above.
- **UI/widget tests** (View layer only): out of scope for "testable
  without a real GUI" and proposed as a smaller, separate, optional
  test tier (e.g. using `pytest-qt`) if the owner wants widget-level
  coverage — not required for the MVVM boundary itself to be fully
  tested.

Not created in this STEP, per Section 0/23 of the governing prompt.

## 24. Dependencies

```
Dependency: PySide6 (RECOMMENDED) or tkinter (fallback, stdlib)
Purpose: GUI toolkit — see Section 10.
Why existing infrastructure is insufficient: no GUI toolkit exists
  in requirements.txt or the stdlib beyond tkinter; a native desktop
  UI requires one by definition.
Alternative: tkinter (see Section 9/10 comparison).
Decision: RECOMMENDED — OWNER APPROVAL REQUIRED.
```

```
Dependency: requests
Purpose: REST API client transport (Section 14).
Why existing infrastructure is insufficient: N/A — already a project
  dependency (requirements.txt), already used for outbound HTTP by
  src/services/github_service.py, src/services/discord_service.py,
  and two AI provider modules (Section 4).
Alternative: N/A.
Decision: DECIDED — reuse, no new dependency.
```

No other new dependency is proposed. `requirements.txt` is not
modified by this STEP.

## 25. Backward Compatibility

EP-044, as designed, cannot break any existing transport, because it
never touches server-side code:

- **CLI / `InteractiveShell`**: unaffected — the Desktop UI runs in a
  separate process and never imports `src/core/shell.py`.
- **`TelegramRouter`, Discord, Email, Git, GitHub, REST API
  (`RestApiServer`/`ApiRouter`)**: unaffected — no file under
  `src/core/`, `src/services/`, or `src/modules/` is modified by this
  design.
- **Existing tests**: unaffected — no existing test file is modified;
  a new `tests/EP044/` suite is additive only (Section 23).
- **Existing configuration**: unaffected — `config/config.yaml` is not
  modified; the Desktop UI's configuration is a separate, new,
  Desktop-owned artifact (Section 17).
- The Desktop UI is additive and does not replace the CLI, matching
  this STEP's explicit instruction.

## 26. Alternatives Considered

- **Direct Core/Service/Module access from the Desktop UI** (bypassing
  the REST API): rejected. This STEP's own governing instructions and
  EP-043's design both establish that external clients must go through
  the REST API; direct access would duplicate `CommandRouter` dispatch
  logic inside a second (UI) process and violate
  `AI_GENERATION_STANDARD.md`'s "never introduce a second
  implementation of existing functionality."
- **Per-subsystem REST resources instead of the generic `/api/v1/commands`
  endpoint**: not applicable to EP-044 — this is an EP-043 API-surface
  decision, already made and explicitly closed
  (`EP043_DESIGN.md` Section 21.3), not reopened here.
- **A combined MVC pattern instead of MVVM** (Section 11): rejected due
  to weaker headless testability with Qt's signal/slot model.
- **CLI-syntax single-line command input** vs. discrete module/action/
  argument fields (Section 15): both remain viable; discrete fields
  are recommended as the simpler V1 default because they require zero
  client-side parsing logic (Section 28, Decision D5).

## 27. Architectural Decisions

```
Decision: D1 — New top-level `desktop/` package, not nested in `src/ui/`.
Reason: The three existing src/ui/*.py files are empty and unowned
  (Section 8); a new top-level directory avoids implicitly claiming
  them without an explicit owner decision.
Alternatives: Nest inside src/ui/; repurpose the existing three files.
Consequences: A small structural decision the owner should confirm
  before STEP 2, since it affects every subsequent file path.
Status: RECOMMENDED — OWNER APPROVAL REQUIRED.
```

```
Decision: D2 — MVVM as the UI architectural pattern.
Reason: Best fit for Qt's signal/slot model and headless testability
  (Section 11).
Alternatives: MVC, MVP (Section 11).
Consequences: ViewModels must never hold widget references; Views
  must never contain API-calling logic.
Status: DECIDED.
```

```
Decision: D3 — Request timeout policy and exact value.
Reason: Every REST call must have an explicit timeout (Section 14);
  the exact duration is a UX tradeoff, not purely architectural.
Alternatives: A short fixed timeout (a few seconds); a
  user-configurable value with a short default; separate timeouts
  per endpoint.
Consequences: Too short risks false "unreachable" states on a slow
  first health check; too long risks a UI that feels frozen even
  with correct threading (Section 15 mitigates but does not eliminate
  this).
Status: RECOMMENDED — OWNER APPROVAL REQUIRED.
```

```
Decision: D4 — Health-check polling cadence.
Reason: Section 15's Main Window connection indicator needs a refresh
  strategy; no repository evidence defines one.
Alternatives: Manual-only (user clicks "reconnect"); periodic polling
  at a fixed interval; polling only after a failed command.
Consequences: Periodic polling adds background HTTP traffic and
  another timer to manage on the UI thread (Section 15 threading
  model must account for it); manual-only is simpler but less
  informative if the server goes down mid-session.
Status: UNRESOLVED — PROJECT OWNER DECISION REQUIRED.
```

```
Decision: D5 — Discrete module/action/arguments input fields (not a
  single CLI-syntax text field) for V1 command submission.
Reason: Zero client-side parsing logic required — the UI simply
  populates the same three fields ApiRouter already accepts
  (Section 13/14), keeping the API client a pure transport layer with
  no text-parsing responsibility.
Alternatives: A single CLI-syntax input, client-side split via
  shlex.split() before constructing the request body (Section 8,
  Optional/Future) — offers CLI-like UX parity but adds a parsing
  step to the client.
Consequences: Slightly less CLI-like UX for V1; can be added later
  as an alternative input mode without changing the API client
  contract.
Status: DECIDED (for V1); CLI-style input remains a documented future
  option.
```

```
Decision: D6 — Desktop UI owns its own configuration, not
  config/config.yaml.
Reason: Section 17 — the Desktop UI is a separate process and must
  not require filesystem access to the server's internal
  configuration.
Alternatives: Read config/config.yaml's `api.*` section directly at
  startup.
Consequences: The Desktop UI's default host/port must be kept
  manually consistent with config/config.yaml's defaults if either
  changes (both currently 127.0.0.1:8080) — a minor, documented
  coupling-by-convention rather than a code coupling.
Status: DECIDED. Storage mechanism itself remains UNRESOLVED — see
  Section 17.
```

## 28. Open Questions

Genuine project-owner decisions this STEP cannot resolve from repository
evidence:

1. GUI toolkit approval: PySide6 (recommended) vs. Tkinter
   (zero-dependency fallback) — Section 10, Decision (Section 24).
2. Package location: new top-level `desktop/` vs. reusing/repurposing
   the existing empty `src/ui/*.py` files — Section 27, Decision D1.
3. Ownership and intended purpose of `src/ui/dashboard.py`,
   `src/ui/tray.py`, `src/ui/notifications.py` — Section 8.
4. Target platform(s) for STEP 2's build/test/packaging effort —
   Section 22.
5. Request timeout value — Section 27, Decision D3.
6. Health-check polling cadence (manual vs. periodic, and interval) —
   Section 27, Decision D4.
7. Desktop-owned configuration storage mechanism (file format and
   location) — Section 17.
8. Whether packaging (Section 21) is scoped as part of EP-044 or
   deferred to a dedicated sub-package (e.g. EP-044.2).

## 29. STEP 2 Implementation Boundary

If the owner approves the recommendations in this document
(Sections 10, 27), STEP 2 may implement:

- The `desktop/` package structure (Section 12), pending Decision D1.
- The API client (`desktop/api/`) against the exact contract in
  Section 13/14, using `requests`.
- Client-side DTOs (`desktop/models/`) mirroring
  `src/core/api/dto.py`'s external contract.
- ViewModels (`desktop/viewmodels/`) per Section 11, with the state
  model from Section 16.
- The Main Window and sub-areas from Section 15, using discrete
  module/action/arguments input fields (Decision D5).
- The threading model from Section 15 (worker thread + Qt
  signal/slot).
- Desktop-owned configuration (Section 17), once Decision D6's storage
  mechanism (Open Question 7) is resolved.
- The `tests/EP044/` suite (Section 23).

STEP 2 must **not**:

- Modify any file under `src/core/`, `src/bootstrap.py`, `src/main.py`,
  `config/`, or `requirements.txt` beyond what Decision D1/Open
  Question 1 explicitly authorize (a `requirements.txt` addition for
  the approved GUI toolkit is the only exception, and only after
  explicit approval).
- Add new REST endpoints or modify `src/core/api/`.
- Implement packaging/installers (Section 21) — deferred.
- Implement any item in Section 8's "Out of Scope" list.
- Populate `src/ui/dashboard.py`, `src/ui/tray.py`,
  `src/ui/notifications.py` without first resolving Open Question 3.

## 30. STEP 1 Threading and Responsiveness (design detail)

*(Placed here to satisfy the governing prompt's mandatory Section 15
requirement with a complete standalone treatment; cross-referenced
from Section 15/Screen Architecture above.)*

- **UI thread**: owns the Qt event loop and all widgets. Never
  performs blocking I/O (no direct `requests` calls on this thread).
- **Worker/network execution**: each REST call (Section 13) runs on a
  `QThread` (or `QThreadPool`-managed `QRunnable`) created and owned
  by the API client or the ViewModel that invokes it — never the View.
- **Communication back to UI**: the worker emits a Qt signal
  (e.g. `result_ready(CommandResponse)`, `error_occurred(ApiClientError)`)
  connected via Qt's queued-connection mechanism, which safely
  marshals the callback onto the UI thread without manual locking.
- **Cancellation**: if the user submits a new command while one is in
  flight, the UI should either disable the submit control until the
  in-flight request resolves (simplest, recommended for V1) or support
  cancellation of the in-flight `requests` call — the latter is more
  complex (requests' blocking calls are not natively cancellable
  mid-flight without additional machinery) and not required for V1.
- **Timeout behavior**: enforced by the API client (Section 14) via
  `requests`' `timeout=` parameter; a timeout surfaces as the
  "Timeout" error category (Section 18), not a frozen UI.

If Tkinter is selected instead of PySide6 (Section 10), the equivalent
model is: a background `threading.Thread` performs the `requests`
call, places the result on a `queue.Queue`, and the Tkinter main loop
polls that queue via `root.after(...)` — functionally equivalent but
requires hand-written marshaling instead of Qt's built-in
signal/slot queuing.

## 31. Acceptance Criteria

STEP 1 (this document) is accepted when:

- [x] Existing repository architecture, `PROJECT_MANIFEST.md`,
      `AI_GENERATION_STANDARD.md`, `AI_DEVELOPMENT_PLAYBOOK.md`, and
      `JARVIS_ROADMAP.md` have been inspected.
- [x] EP-043's design document and actual implementation
      (`src/core/api/*.py`, Bootstrap integration,
      `config/config.yaml`) have been inspected and its contract
      documented exactly (Section 13).
- [x] EP-038 through EP-042 design documents have been sampled for
      structural/terminology convention (Section 27 headers cross-
      checked against `EP042_DESIGN.md`).
- [x] GUI technology options have been evaluated with a comparison
      table (Section 9) and a recommendation issued, marked for owner
      approval (Section 10).
- [x] The Desktop UI ↔ REST API relationship is fully defined
      (Section 13) and verified against the shipped EP-043 contract,
      not invented.
- [x] V1 scope is separated into Required / Optional / Out of Scope /
      Unresolved (Section 8).
- [x] Threading/responsiveness is designed (Sections 15, 30).
- [x] Configuration is designed, with the storage mechanism explicitly
      left open where it is a genuine unresolved decision (Section 17).
- [x] Error handling is designed (Section 18).
- [x] Security implications are documented (Section 19).
- [x] Packaging strategy is documented at the design level only
      (Section 21).
- [x] Testing strategy is documented (Section 23).
- [x] Dependencies are justified, and only one (the GUI toolkit) is
      marked as requiring approval (Section 24).
- [x] Backward compatibility is addressed and confirmed unaffected
      (Section 25).
- [x] No implementation code, UI file, test file, or existing source
      file was created or modified by this STEP.
- [x] Every genuine product/ownership decision is marked UNRESOLVED or
      RECOMMENDED — OWNER APPROVAL REQUIRED rather than assumed
      (Section 28).

End of document.
