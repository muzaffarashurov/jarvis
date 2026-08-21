# EP043 — Design

Status: **Implemented (STEP 2 complete, pending STEP 3/4).** Scope
confirmed directly by the project owner in the STEP 2 implementation
prompt, not re-derived from ambiguous repository evidence — the EP043
STEP 1 investigation stopped because the repository established only
the two-word title "REST API," with no purpose, consumers, endpoint
surface, security model, dependency, or lifecycle integration defined
anywhere (see `EP043_STEP1_REPORT.md`). This document designs against
that owner-confirmed scope and reflects the as-built implementation.
Follows `EP038_DESIGN.md`/`EP039_DESIGN.md`/`EP040_DESIGN.md`/
`EP041_DESIGN.md`/`EP042_DESIGN.md`'s structure and terminology where
applicable, but EP-043 is architecturally the *inverse* of those five
EPs (inbound listener vs. outbound per-call client), which is called
out explicitly wherever it changes a previously-established
convention.

---

## 1. Problem

Jarvis has no programmatic interface other than its interactive CLI
(`InteractiveShell`) and its Telegram bot bridge (`TelegramRouter`).
Nothing lets a local external process — a future web UI, a mobile
app, another local application, or an automation script — communicate
with Jarvis. Before this EP, no REST/HTTP-server implementation,
dependency, or configuration existed anywhere in the codebase
(confirmed by a repository-wide search during STEP 1 and re-confirmed
at the start of STEP 2).

## 2. Existing State

- No HTTP server, REST framework, or web dependency exists anywhere in
  `requirements.txt` or the source tree (`FastAPI`, `Flask`,
  `Starlette`, `Uvicorn`, `aiohttp`, `Werkzeug` — none present, none
  indirectly available).
- `config/config.yaml` had no `api.*`, `server.*`, `http.*`, or
  `rest.*` keys.
- `src/main.py` is a single-process entrypoint: `Bootstrap.run()`
  completes, then `shell.run()` blocks the main thread in
  `InteractiveShell`'s read-command loop until the user exits. Nothing
  in the existing architecture previously needed to run concurrently
  with that loop.
- `CommandRouter` (`src/core/command_router.py`) is already the single
  shared dispatch point behind both `InteractiveShell` and
  `TelegramRouter` (`src/core/telegram/telegram_router.py`): it parses
  `"<module> <action> [args...]"`, looks up a registered
  `CommandModule` by name, and returns a `CommandResult(success,
  message, should_exit)`. Every EP-level command (`system status`,
  `email inbox`, `discord send`, `test EP0NN`, etc.) is already
  reachable through this exact interface.

## 3. Desired State (owner-confirmed scope)

A REST API that:

- Lets external local clients invoke the same commands `InteractiveShell`
  already exposes, over HTTP, on `127.0.0.1` by default.
- Reuses the existing `CommandRouter`/Service/Core/Module stack
  unchanged — the REST API is an adapter, not a new business
  architecture.
- Runs as an independent, separately enable/disable-able component
  (`api.enabled`) that does not turn `InteractiveShell` into a server
  loop and does not require it to be running.
- Ships a minimal, versioned (`/api/v1/...`) surface for v1: a health
  check, a status/state read, and a generic command endpoint — not a
  bespoke per-subsystem endpoint for every existing integration.

## 4. Scope

**In scope for EP-043 v1:**

- `RestApiServer`: an HTTP transport component, separate from
  `InteractiveShell`, built on the Python standard library only.
- `ApiRouter`: a thin bridge from an HTTP command request to
  `CommandRouter.dispatch()` — no new business logic.
- Three endpoints: `GET /health`, `GET /api/v1/status`, `POST
  /api/v1/commands`.
- `api.enabled` / `api.host` / `api.port` configuration, integrated
  into the existing `Config`/`config.yaml` mechanism.
- Localhost-only (`127.0.0.1`) default binding.
- Centralized, structured JSON error handling (no stack traces to the
  client).
- Bootstrap lifecycle integration (`Bootstrap.rest_api_server`,
  `Bootstrap.shutdown()`).
- Tests covering the API layer, configuration gating, lifecycle, and
  `InteractiveShell` non-interference.

## 5. Non-goals (explicitly deferred — see `docs/BACKLOG.md`)

- Authentication/authorization (API keys, JWT, OAuth, RBAC).
- TLS/HTTPS.
- CORS configuration.
- Rate limiting.
- Per-subsystem REST resources (e.g. dedicated `/api/v1/email/...`
  endpoints) — v1 exposes one generic command endpoint instead.
- OpenAPI/Swagger schema generation.
- WebSocket / streaming support.
- Any network exposure beyond loopback (no `0.0.0.0` default, no LAN
  binding guidance beyond "don't, without adding auth first").
- Web UI, mobile app, or any client of the API itself.

## 6. Architecture

```text
External Client (loopback only)
      │  HTTP
      ▼
  RestApiServer   (src/core/api/rest_api_server.py — stdlib http.server)
      │
      ▼
   ApiRouter      (src/core/api/api_router.py)
      │  (module, action, arguments) -> raw command line
      ▼
 CommandRouter    (src/core/command_router.py — SHARED, unchanged)
      │
      ▼
  CommandModule   (existing Service/Core/Module stack — unchanged)
```

`InteractiveShell` and `TelegramRouter` dispatch through the exact
same `CommandRouter` instance built once in `Bootstrap.initialize()`.
`RestApiServer`/`ApiRouter` are added as a third caller of that same
router — no command logic is duplicated, and no existing Service,
Core, or Module code was modified for this EP.

`RestApiServer` is a Bootstrap-level sibling of `InteractiveShell`,
not a `Service` in the `Core -> Service -> Module` sense: it holds no
business state and calls no Module directly. This deliberately departs
from EP-038..042's "everything is a Service" precedent, because those
EPs are all stateless, per-call, *outbound* clients, while
`RestApiServer` is Jarvis's first *inbound listener* — a different
architectural role that the existing `Core -> Service -> Module`
layering was never intended to describe. The Bootstrap composition
therefore is:

```text
bootstrap
 ├── Core
 ├── Services
 ├── Modules
 ├── InteractiveShell
 └── RestApiServer
```

## 7. Components

| Component | File | Responsibility |
|---|---|---|
| `RestApiServer` | `src/core/api/rest_api_server.py` | Binds a socket, serves HTTP on a background daemon thread, routes requests, translates errors to JSON. No business logic. |
| `ApiRouter` | `src/core/api/api_router.py` | Reassembles `(module, action, arguments)` into a raw command line and calls `CommandRouter.dispatch()`. No parsing/business logic of its own. |
| DTOs | `src/core/api/dto.py` | `CommandRequest`, `CommandResponse`, `HealthResponse`, `ErrorPayload` — the API's external JSON contract, independent of internal domain objects. |
| Error hierarchy | `src/core/api/api_error.py` | `ApiError` and four subclasses, each carrying its own HTTP status code. |

## 8. API surface / Endpoint model

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Liveness check. Does not touch `CommandRouter`. |
| `GET` | `/api/v1/status` | Equivalent of the CLI's `system status`. |
| `POST` | `/api/v1/commands` | Generic command dispatch: any `(module, action, arguments)` the CLI itself could run. |

Any other path returns `404`. A known path called with an unsupported
method returns `405`.

## 9. Request/response model

`POST /api/v1/commands` request body:

```json
{"module": "system", "action": "status", "arguments": []}
```

- `module` (string, required, non-empty).
- `action` (string, optional, default `""`).
- `arguments` (array of strings, optional, default `[]`).

All three endpoints return, on a successfully *routed* request:

```json
{"success": true, "message": "..."}
```

for `/api/v1/status` and `/api/v1/commands`, or

```json
{"status": "ok"}
```

for `/health`.

**Deferred/simplified decision:** the underlying command's own
business result (`success`/`message`) is always returned with HTTP
`200`, even when `success: false` (e.g. an unknown module, or a
command that legitimately fails). Only REST-transport-level problems
— malformed JSON, a missing/invalid `module`, an unknown path, or an
unsupported method — produce a non-2xx status (`400`/`404`/`405`).
No design document specified a business-result-to-HTTP-status mapping,
and building one would require per-module business knowledge inside a
REST controller, which the "controllers must remain thin" requirement
explicitly rules out. This keeps `RestApiServer` a true thin adapter.
Clients must check the body's `success` field, not just the status
code, to know whether the underlying command succeeded.

Error body (any 4xx/5xx):

```json
{"error": {"code": "validation_error", "message": "..."}}
```

`code` is one of `validation_error` (400), `not_found` (404),
`method_not_allowed` (405), `internal_error` (500).

## 10. Configuration

```yaml
api:
  enabled: false
  host: "127.0.0.1"
  port: 8080
```

Added to `config/config.yaml` between `email:` and `ai:`. Absence of
the `api` section entirely is handled identically to `enabled: false`
(`Config.get("api.enabled", False)`), so it cannot break Jarvis
startup for any existing configuration file that predates this EP.

**Deviation from the STEP 2 prompt's illustrative example
(`enabled: true`):** the actual default is `enabled: false`. Every
prior EP-038..042 subsystem defaults to `true` because they are
stateless outbound clients with no observable effect when idle.
`RestApiServer` is different: enabling it binds and listens on a real
network socket as a side effect of `Bootstrap.initialize()`. A large
number of existing tests across EP-001..EP-042 construct a real
`Bootstrap` purely to verify dependency-injection wiring, calling only
`initialize()` (never `run()` or any shutdown hook). None of their
config templates include an `api` section, so they are unaffected
either way — but defaulting a new socket-binding subsystem to "off"
is the safer choice for any future test or deployment that doesn't
explicitly opt in, and avoids introducing port-conflict flakiness into
the existing test suite. This is exactly the kind of "safest solution,
documented" resolution the STEP 2 instructions call for when the
prompt's illustrative config and safe backward-compatible behavior
disagree.

## 11. Security

- Primary boundary: `127.0.0.1` bind by default. `RestApiServer`
  never defaults to `0.0.0.0`.
- No authentication/authorization in v1 (explicitly deferred — see
  Non-goals). The full command surface (equivalent to shell access) is
  reachable by anything that can reach the bound loopback port —
  practically, any local process/user on the same machine. Documented
  here as the accepted v1 risk, matching the STEP 2 instruction's
  explicit "do NOT over-engineer security at this stage" / "primary
  security boundary for v1 is 127.0.0.1."
- No TLS, no CORS handling, no rate limiting in v1.
- Operators changing `api.host` to a non-loopback address do so
  outside any safety net this EP provides; that configuration is
  technically possible but not a supported v1 deployment mode.

## 12. Authentication / Authorization

None in v1 (see Non-goals/Security). Deferred to a future EP; tracked
in `docs/BACKLOG.md`.

## 13. Error handling

Centralized in `_ApiRequestHandler._dispatch()`
(`rest_api_server.py`): every request is wrapped in a
`try/except ApiError` (structured, expected error → correct status
code) and a catch-all `except Exception` (logged via `loguru`, then
converted to a generic `ApiInternalError` — the client never receives
a Python stack trace or exception message from an unexpected failure).

## 14. Lifecycle

- `RestApiServer` is constructed and, if `api.enabled` is true,
  started (socket bound, daemon thread launched) inside
  `Bootstrap._build_rest_api_server()`, called from
  `Bootstrap.initialize()` — after `CommandRouter`/`InteractiveShell`
  are built, so `ApiRouter` always receives the fully-populated
  router.
- `InteractiveShell` is unaffected: `bootstrap.run()` completes exactly
  as before, then `main.py` calls the unchanged, blocking `shell.run()`.
  `RestApiServer`'s daemon thread runs independently for the process's
  remaining lifetime.
- `Bootstrap.shutdown()` (new) stops the server if running. `main.py`
  calls it once `shell.run()` returns, so a clean CLI exit also
  cleanly releases the bound port.
- The listener thread is a daemon thread, so an un-stopped server
  never blocks process exit even if `shutdown()` is skipped (e.g. a
  test that doesn't reach its `finally` block).

## 15. Bootstrap integration

- New import: `from src.core.api.api_router import ApiRouter`,
  `from src.core.api.rest_api_server import RestApiServer, RestApiServerError`.
- New attribute: `self._rest_api_server: RestApiServer | None`.
- New method: `_build_rest_api_server(command_router, config)`.
- New method: `shutdown()`.
- New property: `rest_api_server`.
- No existing Bootstrap method signature changed; no existing
  attribute removed or renamed.

## 16. Dependency decision

**No new dependency.** `RestApiServer` is built entirely on the Python
standard library (`http.server.ThreadingHTTPServer`,
`http.server.BaseHTTPRequestHandler`, `json`, `threading`).
`requirements.txt` is unchanged.

This resolves STEP 1's open ambiguity #6 ("framework/library") in the
safest available way given no design document specified a framework:
it adds zero dependency-selection risk, requires no
`requirements.txt` change, and mirrors this project's existing
precedent of preferring the standard library for a new integration EP
(EP-042's `EmailService` uses only `imaplib`/`email`, no third-party
IMAP client).

## 17. Testing strategy

Single combined suite, `tests/EP043/test_rest_api.py`
(`NAME = "EP043"`), deliberately **not** split into a
`RestApiServerTest`/`ApiRouterTest`-style Service/Module pair. EP-043
introduces no `Service`/`Module` pair — `ApiRouter`/`RestApiServer`
are transport-layer components — so a single suite is both accurate
and sidesteps the pre-existing `TestRegistry` NAME-collision
technical debt (see Regression safety, below) entirely rather than
triggering it.

Covers: `ApiRouter` dispatch (including shell-quoting of arguments
with spaces), all three endpoints over real HTTP against an
OS-assigned ephemeral port (`port=0`), malformed JSON, missing
`module`, unknown path (404), wrong method on a known path (405),
server start idempotency, stop/restart, real `Bootstrap` wiring for
`api.enabled: true` / `false` / absent, `Bootstrap.shutdown()`
(including "safe when nothing was started"), and a direct check that
`InteractiveShell`/`CommandRouter` still work with `RestApiServer`
running.

## 18. Regression safety

- `TestRegistry` collision (pre-existing technical debt, tracked
  since EP-038, documented in `docs/BACKLOG.md` and
  `docs/architecture/audits/EP042_ARCHITECTURE_AUDIT.md`): **not
  modified.** EP-043 avoids triggering it by registering a single
  suite name (`EP043`) instead of a same-named Service/Module pair.
- `api.enabled` defaults to `false`, and is entirely absent from
  every pre-EP-043 test config template, so no existing EP-001..042
  test unexpectedly binds a socket.
- `Bootstrap.__init__`/`initialize()` signatures unchanged; only
  additive attributes/methods/properties were introduced.
- `main.py` changed by exactly one line (`bootstrap.shutdown()` after
  `shell.run()`), which is a no-op whenever `rest_api_server` is
  `None` (the default).

## 19. Risks

- **No authentication in v1**: accepted, documented, deferred (see
  Security/Non-goals). Mitigated only by the loopback-only default.
- **Generic command endpoint exposes the full CLI surface**: by
  design (matches the STEP 2 instruction's framing of the REST API as
  parallel to the CLI reusing the same Service/Core/Module stack), but
  means anything that can reach the bound port has effectively shell-
  equivalent access. This is the direct consequence of having no
  authentication yet, not a separate risk.
- **`system exit` (and similarly process-lifecycle-affecting
  commands) dispatched over REST have no effect**: only
  `InteractiveShell`'s own loop reads `CommandResult.should_exit`;
  `RestApiServer` never does. Not a crash risk, but a client sending
  such a command could reasonably (and incorrectly) expect it to do
  something. Documented as a known limitation.
- **stdlib `ThreadingHTTPServer` is intentionally minimal**: no
  connection pooling tuning, no HTTP/2, no keep-alive tuning beyond
  Python's defaults. Acceptable for a v1, local-only, low-traffic
  interface; revisit if EP-043 usage grows beyond that.

## 20. Implementation plan (as executed)

1. `src/core/api/` package: `api_error.py`, `dto.py`, `api_router.py`,
   `rest_api_server.py`.
2. `src/bootstrap.py`: imports, `_rest_api_server` attribute,
   `_build_rest_api_server()`, `shutdown()`, `rest_api_server`
   property, wired into `initialize()`.
3. `src/main.py`: one-line `bootstrap.shutdown()` addition.
4. `config/config.yaml`: `api:` section added.
5. `tests/EP043/test_rest_api.py` (+ `__init__.py`), registered in
   `src/modules/test_module.py`.
6. Full regression run (`test all`) and static analysis (`ruff`) —
   see `EP043_STEP2_REPORT.md` for actual results.

---

## 21. STEP 3 Addendum — API Contract Hardening

STEP 3 audited the approved STEP 2 contract for stability and
robustness ahead of real external clients, and made two small,
backward-compatible changes. Full validation results:
`EP043_STEP3_REPORT.md`.

### 21.1 Content-Type policy (new)

`POST /api/v1/commands` now enforces a simple, explicit Content-Type
policy:

- **Present and `application/json`** (parameters like
  `; charset=utf-8` are ignored) → processed normally.
- **Present and anything else** (e.g. `text/plain`,
  `application/xml`) → `415 Unsupported Media Type`,
  `{"error": {"code": "unsupported_media_type", "message": "..."}}`.
- **Absent entirely** → still parsed as JSON (lenient). Chosen because
  a genuinely missing header is ambiguous, not a client error, and
  rejecting it would add friction for simple/manual clients (e.g.
  `curl` without an explicit `-H`) without a clear benefit — whereas
  an explicit, wrong declaration is unambiguous and worth catching
  early.

No other endpoint reads a request body, so this policy applies only
to `/api/v1/commands`.

### 21.2 Configuration robustness fix

`RestApiServer.start()` previously caught only `OSError` when binding
(covers "port already in use" and similar OS-level failures). Auditing
`api.port` handling for STEP 3 (§12 "Configuration Hardening") found
that a malformed value — wrong type (e.g. a YAML string) or a value
outside 0-65535 — raises `TypeError`/`OverflowError` from
`socket.bind()`, neither of which is an `OSError` subclass. Uncaught,
this would have propagated out of `Bootstrap._build_rest_api_server()`
and crashed `Bootstrap.initialize()` — inconsistent with every other
invalid `api.*` configuration case, which already degrades safely to
"REST API disabled" (see §11 Lifecycle). Fixed by broadening the catch
to `(OSError, TypeError, ValueError, OverflowError)`, all wrapped into
the same `RestApiServerError` → logged, `rest_api_server` stays
`None`, Jarvis continues starting normally.

### 21.3 Explicitly reviewed and retained unchanged

Per the STEP 3 instruction's "do not automatically change existing
behavior" guidance, the following were re-reviewed against STEP 3's
hardening requirements and deliberately left as-is:

- **§10's status-code policy** (`success: false` still returns HTTP
  `200`, not a 4xx/5xx): still the safest option absent any
  design-specified business-outcome-to-status mapping; changing it now
  would be a breaking contract change for a decision already reviewed
  and accepted at STEP 2 approval.
- **`api.enabled: false` / `api.host: "127.0.0.1"` defaults**:
  unchanged.
- **The generic `/api/v1/commands` endpoint** (vs. per-subsystem REST
  resources): STEP 3's own scope boundary (§24 "Do NOT expand the API
  into a large application framework") explicitly rules out adding
  endpoints "merely to make the API look more RESTful" without a
  demonstrated architectural requirement; none was found.
- **No OpenAPI/Swagger tooling was introduced**: STEP 3 checked for an
  existing project convention for a machine-readable API
  specification (searched `docs/`, `pyproject.toml`, `requirements.txt`)
  and found none, so per the STEP 3 instruction's explicit fallback
  ("if no such mechanism exists, simply document the contract in
  EP043_DESIGN.md"), the contract remains documented here in prose
  only (§8/§9) — OpenAPI remains a future extension (§16).

### 21.4 Final contract reference (unchanged endpoints, STEP 3 status codes added)

| Method | Path | Success | Client errors | Server error |
|---|---|---|---|---|
| GET | `/health` | 200 | 404 (unknown path — n/a here), 405 (wrong method) | 500 (unhandled exception) |
| GET | `/api/v1/status` | 200 | 404, 405 | 500 |
| POST | `/api/v1/commands` | 200 (always, once routed — see §10) | 400 (malformed JSON, missing/invalid `module`/`action`/`arguments`), 404, 405, 415 (bad `Content-Type`) | 500 |

Example, `POST /api/v1/commands`:

```json
// Request
{"module": "system", "action": "status", "arguments": []}

// Response (200)
{"success": true, "message": "..."}
```

```json
// Request with an unknown module
{"module": "does_not_exist"}

// Response (200 — routed successfully; the command itself failed)
{"success": false, "message": "Unknown module: does_not_exist\nType \"system help\" for available commands."}
```

```json
// Request with Content-Type: text/plain
// Response (415)
{"error": {"code": "unsupported_media_type", "message": "Unsupported Content-Type: 'text/plain'. Expected 'application/json'."}}
```

---

## 22. STEP 4 Addendum — Implemented vs. Deferred (Final Summary)

Added at finalization (STEP 4) as a single, explicit reference
consolidating §4-5, §21.3, and every STEP 2/3 report — no new scope
was introduced to produce this table; it restates decisions already
made and documented earlier in this file.

### Implemented (v1, shipped)

- `GET /health` — liveness check, no `CommandRouter` call.
- `GET /api/v1/status` — equivalent to CLI `system status`, via the
  shared `CommandRouter`.
- `POST /api/v1/commands` — generic `{module, action, arguments}`
  command dispatch through the shared `CommandRouter`.
- `RestApiServer` (`src/core/api/rest_api_server.py`): stdlib
  `http.server`-based HTTP transport, Bootstrap-level sibling of
  `InteractiveShell`, no new dependency.
- `ApiRouter` (`src/core/api/api_router.py`): thin bridge to the
  existing `CommandRouter` — no duplicated business logic.
- DTOs (`src/core/api/dto.py`) and a structured error hierarchy
  (`src/core/api/api_error.py`) — stable, predictable JSON contract.
- `api.enabled` / `api.host` / `api.port` configuration
  (`config/config.yaml`), integrated into the existing `Config`
  mechanism, with `enabled: false` and `host: "127.0.0.1"` as the
  safe defaults.
- Bootstrap lifecycle integration (`_build_rest_api_server()`,
  `shutdown()`, `rest_api_server` property) — starts inside
  `initialize()`, stops via `shutdown()`, independent of
  `InteractiveShell`.
- `415 Unsupported Media Type` Content-Type policy for
  `POST /api/v1/commands` (STEP 3).
- Configuration robustness: a malformed `api.port` degrades to "REST
  API disabled" rather than crashing startup (STEP 3).
- `tests/EP043/test_rest_api.py` — 83 assertions covering `ApiRouter`,
  real HTTP behavior for every route/error case, Bootstrap wiring,
  lifecycle (including repeated start/stop cycles), and one full
  external-client contract round-trip.

### Deferred / Future (explicitly not implemented in v1)

- Authentication/authorization (API keys, JWT, OAuth, RBAC) — required
  before any non-loopback `api.host` is safe to use.
- TLS/HTTPS.
- CORS configuration.
- Rate limiting.
- Per-subsystem REST resources (e.g. dedicated `/api/v1/email/...`
  endpoints) — v1 exposes one generic command endpoint instead.
- OpenAPI/Swagger schema generation — no existing project convention
  for one was found (checked in STEP 3); the contract is documented in
  prose in this file instead.
- WebSocket / streaming support.
- Any network exposure beyond loopback.
- A code-level guard preventing `api.host` from being set to a
  non-loopback address without authentication also being configured
  — currently an undocumented-in-code, documented-in-prose operator
  responsibility.
- Web UI, mobile app, or any client of the API itself.
- A richer `CommandResult`/error-category model that would allow a
  business-outcome-to-HTTP-status mapping beyond the current
  "transport success is always 200" policy.

No item in this list was added as new scope during STEP 4 — every
entry already appears in §5, §16, or a STEP 2/3 report; this section
exists only to give a single, final, unambiguous reference point.


