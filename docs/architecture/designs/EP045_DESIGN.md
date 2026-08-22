# EP-045 — Web Dashboard — Design Specification

Status: **COMPLETE — STEP 1 (Design & Architecture Investigation),
STEP 2 (Implementation), and STEP 3 (Final Verification, Architectural
Audit & Documentation) all complete.** Verdict recorded in
`docs/architecture/audits/EP045_AUDIT.md`. Owner decisions that
resolved this document's STEP 1 open questions are recorded in
Section 22a immediately below; the "Implemented As" notes threaded
through the sections below identify, section by section, where final
implemented behavior matches, narrows, or (in one case — same-origin
serving needing no dashboard-side config at all) simplifies what
STEP 1 proposed. The original STEP 1 text is otherwise preserved
unchanged beneath these notes, so this document remains an accurate
record of both what was *proposed* and what was *actually delivered*
— matching the exact convention `EP044_DESIGN.md` established (see
`EP044_AUDIT.md` Section 18, "Documentation Consistency").

---

## STEP 1 (original) — Design and Architecture Investigation

The remainder of this document, unless marked "Implemented As" in a
STEP 2/3 annotation, is preserved exactly as approved at STEP 1.
`docs/architecture/JARVIS_ROADMAP.md` established only the two-word
title "Web Dashboard" for EP-045, with no functional
scope, technology, or hosting model defined anywhere in the
repository. This mirrors EP-043's and EP-044's own STEP 1 starting
condition (see `EP043_DESIGN.md` header note, `EP044_DESIGN.md`
Section 0/1), and this document follows the same resolution pattern:
derive everything that *is* determinable from existing, shipped
architecture, and mark every genuine product decision as
**UNRESOLVED** or **RECOMMENDED — OWNER APPROVAL REQUIRED** rather
than inventing it.

Follows `EP043_DESIGN.md`/`EP044_DESIGN.md`'s structure and
terminology where applicable. EP-045 is architecturally a **third
consumer** of the same pattern EP-043 introduced and EP-044 already
validated (external client via HTTP) — not a new architectural layer,
and not a bypass of the REST API.

---

## 1. Purpose

Define the architecture, requirements, and implementation plan for a
web-based dashboard that lets a user interact with Jarvis from a
browser, as an external client of the existing EP-043 REST API —
without duplicating `CommandRouter`, `Service`, `Core`, or `Module`
logic, without modifying `src/core/api/`, and without modifying
EP-044's `desktop/` package.

## 2. Scope

**In scope for EP-045 STEP 1 (this document):**

- Repository/documentation vs. implementation discrepancy analysis.
- The exact, current EP-043 REST API contract, re-verified against
  source (not only against `EP043_DESIGN.md`'s prose).
- What EP-044 already solved that is reusable *conceptually* for a
  browser client, and what is Desktop-UI-specific and does not
  transfer.
- Functional scope for a first Web Dashboard (Required / Optional /
  Future / Out of Scope).
- Frontend technology evaluation and a single recommendation.
- Proposed architecture, UI architecture, state model, and error
  handling model.
- Security analysis of exposing a browser client against EP-043's
  current no-auth, loopback-only posture.
- Testing strategy for a future STEP 2.
- Packaging/deployment direction (design-level only).
- Dependencies STEP 2 would likely require (not installed here).
- Proposed directory structure (not created here).
- Open questions requiring owner approval.
- Non-goals.
- STEP 2 boundary and acceptance criteria.

**Out of scope for STEP 1 (and deferred pending Section 21):**

See Sections 6 (Non-Goals) and 20 (Open Questions).

## 3. Existing Architecture

### 3.1 Repository Discovery

Per `PROJECT_MANIFEST.md` (the mandatory single source of truth for
project discovery) and `AI_GENERATION_STANDARD.md` ("Never manually
guess the project structure... discovered through
`PROJECT_MANIFEST.md`"), the following were read directly, not
assumed:

- `PROJECT_MANIFEST.md`, `AI_GENERATION_STANDARD.md`,
  `docs/architecture/AI_DEVELOPMENT_PLAYBOOK.md`,
  `docs/architecture/JARVIS_ROADMAP.md`, `docs/BACKLOG.md`,
  `docs/architecture/NON_GOALS.md`.
- `docs/architecture/designs/EP043_DESIGN.md`,
  `docs/architecture/designs/EP044_DESIGN.md`,
  `docs/architecture/audits/EP044_AUDIT.md`.
- `src/core/api/__init__.py`, `api_error.py`, `api_router.py`,
  `dto.py`, `rest_api_server.py` (full source, not summary).
- `desktop/` (full tree: `app/`, `api/`, `models/`, `viewmodels/`,
  `views/`, `state/`, `config/`), specifically
  `desktop/api/jarvis_api_client.py` and
  `desktop/config/desktop_config.py` read in full.
- `requirements.txt`, `pyproject.toml`, `src/bootstrap.py` (API-related
  sections: imports, `_build_rest_api_server`, `shutdown()`,
  `rest_api_server` property), `src/main.py`.
- `config/config.yaml`'s `api:` section.
- `src/ui/dashboard.py`, `src/ui/tray.py`, `src/ui/notifications.py`
  (confirmed empty, MD5 `d41d8cd9…` / 0 bytes, same as EP-044's own
  finding).

### 3.2 Documentation vs. Implementation — Discrepancy Check

Per this STEP's governing instruction ("the actual repository
implementation is authoritative... explicitly identify discrepancies
if they exist"), each design-document claim below was independently
re-verified against source rather than trusted as-is:

| Claim (from `EP043_DESIGN.md` / `EP044_DESIGN.md`) | Verified against | Result |
|---|---|---|
| Three endpoints exactly: `GET /health`, `GET /api/v1/status`, `POST /api/v1/commands` | `src/core/api/rest_api_server.py`, `_ROUTES` dict | **Confirmed, no discrepancy.** |
| `success: false` still returns HTTP 200; only transport-level problems produce non-2xx | `rest_api_server.py`, `_dispatch()` | **Confirmed.** |
| `CommandRequest` shape `{module: str, action: str="", arguments: list[str]=[]}` | `src/core/api/dto.py` | **Confirmed.** |
| Error body `{"error": {"code": str, "message": str}}` | `src/core/api/dto.py` (`ErrorPayload`) | **Confirmed.** |
| `api.enabled` defaults to `false`; default bind `127.0.0.1:8080` | `config/config.yaml` `api:` section | **Confirmed.** |
| No authentication, CORS, TLS, or rate limiting exists | `src/core/api/*.py` full read; no such code found | **Confirmed — none exists.** |
| EP-044's `desktop/` never imports `src.core`/`src.services`/`src.modules`/`CommandRouter` | Direct read of `desktop/api/jarvis_api_client.py`, `desktop/config/desktop_config.py`; corroborated by `EP044_AUDIT.md` Section 6's grep evidence | **Confirmed.** |
| `requests` and `PyYAML` are pre-existing dependencies, reusable with zero new cost | `requirements.txt` | **Confirmed** — both present (`requests`, `PyYAML>=6.0.1`), alongside `PySide6==6.11.2` (EP-044's own new, GUI-only dependency, not relevant to a browser client). |
| `src/ui/dashboard.py`/`tray.py`/`notifications.py` are empty and unowned | `ls -la`, `md5sum` | **Confirmed** — still 0 bytes, still unresolved per `docs/BACKLOG.md`'s "OWNER DECISION REQUIRED" list. |
| EP-044 status: COMPLETE, `test EP044` → 52/52, `test EP043` → 83/83, full regression 5,511/5,511 | `docs/architecture/JARVIS_ROADMAP.md` "Current" section, `docs/BACKLOG.md` | **Confirmed as documented; not independently re-run in this STEP** (STEP 1 is read-only investigation — see Section 22). |

No discrepancy was found between documentation and implementation for
any statement load-bearing to this design. No documentation was
silently corrected. No missing architecture was invented.

### 3.3 Existing Transports

Jarvis currently has four transports into the shared `CommandRouter`
(`src/core/command_router.py`), the single dispatch point behind
every one of them:

```
InteractiveShell (CLI)         ─┐
TelegramRouter (chat bridge)    ├─►  CommandRouter  ─►  Service/Core/Module stack
RestApiServer/ApiRouter (HTTP)  │
Desktop UI (external process,   ┘
  via RestApiServer/ApiRouter)
```

The Desktop UI (EP-044) is not itself a transport into
`CommandRouter` — it is an external HTTP client of the `RestApiServer`
transport, exactly as EP-045 must also be. This is the pattern this
document proposes EP-045 extend, not replace.

## 4. EP-043 REST API Contract

Re-verified directly against `src/core/api/rest_api_server.py`,
`dto.py`, and `api_error.py` (not only against
`EP043_DESIGN.md`/`EP044_DESIGN.md`'s prose — see Section 3.2).

### 4.1 Endpoints

| Method | Path | Purpose | Request body | Success response | Error responses |
|---|---|---|---|---|---|
| `GET` | `/health` | Liveness check. Does not touch `CommandRouter`. | none | `200 {"status": "ok"}` | 404 (n/a here), 405 (wrong method), 500 |
| `GET` | `/api/v1/status` | Equivalent of CLI `system status`. | none | `200 {"success": bool, "message": str}` | 404, 405, 500 |
| `POST` | `/api/v1/commands` | Generic `(module, action, arguments)` dispatch through `CommandRouter`. | `{"module": str, "action"?: str, "arguments"?: [str]}` | `200 {"success": bool, "message": str}` (**always 200 once routed** — business failure is carried in `success: false`, not HTTP status) | 400 (malformed JSON / invalid fields), 404, 405, 415 (bad `Content-Type`), 500 |

Any other path returns 404. A known path called with an unsupported
method returns 405.

### 4.2 Request/response structures

- `CommandRequest`: `module` (string, required, non-empty), `action`
  (string, optional, default `""`), `arguments` (array of strings,
  optional, default `[]`).
- `CommandResponse` (also used for `/api/v1/status`):
  `{"success": bool, "message": str}`.
- `HealthResponse`: `{"status": "ok"}`.
- `ErrorPayload` (any 4xx/5xx): `{"error": {"code": str, "message": str}}`,
  where `code` is one of `validation_error` (400), `not_found` (404),
  `method_not_allowed` (405), `unsupported_media_type` (415),
  `internal_error` (500).

### 4.3 Content-Type policy

`POST /api/v1/commands`: `application/json` (parameters ignored) is
accepted; any other explicit `Content-Type` is rejected with `415`; a
missing header is treated leniently and still parsed as JSON.

### 4.4 Configuration

```yaml
api:
  enabled: false
  host: "127.0.0.1"
  port: 8080
```

Absence of the `api` section is handled identically to
`enabled: false`.

### 4.5 Server lifecycle

`RestApiServer` is a Bootstrap-level sibling of `InteractiveShell`
(not a `Service`), built on `http.server.ThreadingHTTPServer`,
started inside `Bootstrap.initialize()` when `api.enabled` is `true`,
and stopped by `Bootstrap.shutdown()`. The listener runs on a daemon
thread independent of `InteractiveShell`'s blocking main loop.

### 4.6 Authentication posture

**None.** No API key, JWT, OAuth, session, or cookie mechanism exists
anywhere in `src/core/api/`. The full command surface — "effectively
shell-equivalent access" per `EP043_DESIGN.md` Section 19 — is
reachable by anything that can reach the bound host/port. This is the
single most important fact governing Section 9 (Security) below.

### 4.7 Current limitations (unchanged since EP-043/EP-044)

No authentication/authorization, no TLS, **no CORS handling**, no rate
limiting, no OpenAPI/Swagger schema, no WebSocket/streaming support,
no per-subsystem REST resources (one generic
`/api/v1/commands` endpoint), no network exposure beyond loopback by
default. All of these are pre-existing, explicitly deferred
(`docs/BACKLOG.md`), not something EP-045 introduces or is expected to
fix.

**The CORS gap is new-relevant for EP-045 specifically** (Section 9.2):
EP-044's Desktop UI never needed CORS, because a native `requests` call
is not subject to browser same-origin policy. A browser-based Web
Dashboard is the first EP-043 client for which this gap has a
concrete, immediate consequence, and is treated in detail below.

## 5. EP-044 Relationship

### 5.1 What is reused *conceptually*

EP-044 already solved, once, the general problem "how does a Jarvis
UI client consume the EP-043 contract correctly" — the following
patterns are reusable as *architecture*, not as *code* (EP-045 must
not import from `desktop/`; a browser cannot run Python anyway):

- **Client-side DTOs mirroring the server contract exactly**
  (`desktop/models/dto.py`'s relationship to `src/core/api/dto.py`):
  EP-045's equivalent (TypeScript/JS types or plain JSON handling,
  depending on Section 7's outcome) should mirror the same
  `CommandRequest`/`CommandResponse`/`HealthResponse`/`ErrorPayload`
  shapes from Section 4.2, independently re-derived for the chosen
  frontend technology.
- **A typed error category model** (`desktop/api/client_errors.py`):
  network error / timeout / HTTP error / malformed response, as
  distinct categories with distinct user-facing treatment (Section 12
  below), not one generic "something went wrong."
- **Timeout policy, no automatic retries**: `desktop/api/jarvis_api_client.py`
  uses `DEFAULT_TIMEOUT_SECONDS = 10.0` and explicitly implements no
  retries, because `POST /api/v1/commands` may have side effects
  (EP044_DESIGN.md Section 14, "Retries"). The same reasoning applies
  unchanged to a browser client and is proposed as EP-045's default
  (Section 20, Open Question 4, for the exact value).
- **`success: false` still means HTTP 200 — clients must branch on
  the body, not the status code**: `desktop/viewmodels/main_window_viewmodel.py`
  encodes this; EP-045's UI layer must encode the identical rule
  (Section 11).
- **Client-owned configuration, separate from `config/config.yaml`**
  (`desktop/config/desktop_config.py`, Decision D6): the same
  separation-of-concerns applies to EP-045 (Section 17), though the
  storage *mechanism* necessarily differs (a browser cannot read an
  arbitrary filesystem YAML file the way a desktop process can —
  Section 17 below).
- **Never shows a raw Python/server stack trace; surfaces the
  server's own pre-sanitized `ErrorPayload.message`** — reusable
  verbatim as a UI-layer rule regardless of frontend technology.

### 5.2 What is Desktop-UI-specific and does **not** transfer

- Qt's `QThread` + signal/slot threading model (Section 15/30 of
  `EP044_DESIGN.md`) has no meaning in a browser; a Web Dashboard's
  non-blocking model is the browser's native asynchronous HTTP
  (`fetch`/`XMLHttpRequest`) plus whatever the chosen frontend
  technology's own state/rendering model provides (Section 8, 11).
- MVVM as specified for EP-044 is a Qt-specific pattern
  choice; EP-045's UI architecture (Section 11) must be re-derived
  for the browser/chosen-framework context, not assumed identical.
- `desktop/config/desktop_config.py`'s per-user filesystem YAML file
  (`~/.jarvis-desktop/config.yaml`) is a desktop-process concept with
  no browser equivalent (Section 17).
- `PySide6` is irrelevant to EP-045; it is a GUI-toolkit dependency
  for a native desktop process, not a web technology.
- Packaging via PyInstaller (`EP044_DESIGN.md` Section 21) does not
  apply; a Web Dashboard's "packaging" is a static-asset build (Section
  16).

### 5.3 No modification to EP-044

Per this EP's mandatory constraint, `desktop/` is not read as a
dependency to modify, extend, or share code with — only as prior art
to learn architectural lessons from (Section 5.1). No file under
`desktop/` is referenced by, imported by, or intended to be modified
by anything EP-045 proposes.

## 6. Functional Requirements

Derived directly from EP-043's actual v1 endpoint surface (Section 4)
and EP-044's own precedent for what "the graphical equivalent of the
REST API's existing surface" means (`EP044_DESIGN.md` Section 8) —
not invented independently for EP-045.

### REQUIRED FOR EP-045 V1

- Connection status display (`GET /health`).
- Jarvis status display (`GET /api/v1/status`).
- Command input (module, action, arguments) and submission
  (`POST /api/v1/commands`).
- Command result display (`success`/`message` body, per Section 4.1's
  "always 200 once routed" rule).
- API/transport error display (network error, timeout, HTTP 4xx/5xx,
  malformed response — Section 12).
- Dashboard-side connection configuration (API base URL / host /
  port), since the Web Dashboard, like the Desktop UI, cannot assume
  the server's configured port (Section 17).
- Responsive layout (usable at both desktop and typical laptop/tablet
  browser widths — see Section 6, "responsive layout" in this STEP's
  own governing checklist).
- A stated, minimal browser-compatibility baseline (Section 8.5).

### OPTIONAL / FUTURE

- Command history / previous-result log within a browser session
  (client-side only; no new server-side persistence — matches
  `EP044_DESIGN.md`'s identical "Optional/Future" item for the
  Desktop UI).
- CLI-syntax single-line command input parsed client-side into
  module/action/arguments, mirroring `EP044_DESIGN.md` Decision D5's
  identical trade-off.
- Automatic health-check polling (see Section 20, Open Question 6 —
  mirrors `EP044_DESIGN.md`'s own still-unresolved Decision D4).

### OUT OF SCOPE

- Chat, memory browser, agent management, workflow editor, voice
  control, file manager, notifications, real-time streaming, advanced
  analytics — **none of these appear in
  `docs/architecture/JARVIS_ROADMAP.md`, `docs/BACKLOG.md`, or any
  other project document as a requirement for EP-045.** Per this
  STEP's governing instruction, these are not added "unless the
  existing project documentation explicitly requires them," and no
  such requirement exists. (Several — voice, memory browser, agent
  management, workflow editor — are instead separately roadmapped as
  their *own*, later, unstarted Engineering Packages: Phase 7
  "Voice," and the already-completed-as-backend-only Phase 3/4/5
  Memory/Agent/Workflow Engines, none of which currently expose any
  UI at all, desktop or web.)
- Authentication UI (login screens, token entry) — EP-043 v1 has no
  authentication to configure (Section 9.3).
- Any functionality requiring a new REST endpoint beyond EP-043's
  existing three (Section 6.1 below covers the one exception process).

### UNRESOLVED — PROJECT OWNER DECISION REQUIRED

- Whether `src/ui/dashboard.py` is intended to be filled in by EP-045
  specifically (its name is suggestive, but it is empty and carries no
  docstring, contract, or comment indicating ownership — the same
  finding EP-044's STEP 1 made for all three `src/ui/*.py` files, and
  still true, byte-for-byte, at the time of this STEP; see Section
  3.1). This document does not assume EP-045 owns it. Populating it
  without an explicit owner decision would be "modifying files not
  explicitly listed in the task" under `AI_GENERATION_STANDARD.md`'s
  File Modification Policy.

### 6.1 New-endpoint policy

Per this STEP's explicit governing instruction, no new REST endpoint
is proposed. Every requirement in "REQUIRED FOR EP-045 V1" above is
satisfiable by EP-043's existing three endpoints (Section 4.1) with no
gap. No item requiring a new endpoint was identified during this
investigation; this section exists to record that the check was
performed, per Section 4 of the governing prompt ("If new endpoints
appear necessary, list them as OPEN QUESTIONS / FUTURE WORK").

## 7. Non-Functional Requirements

- **No new REST endpoints, no modification to `src/core/api/`**
  (Section 6.1).
- **No modification to EP-044's `desktop/` package** (Section 5.3).
- **No direct import of `src.core`, `src.services`, `src.modules`,
  `CommandRouter`, or any Bootstrap-internal object from any Web
  Dashboard code** — the boundary EP-043's and EP-044's own designs
  both already establish (Section 8).
- **Non-blocking UI**: no user-facing freeze while a request is in
  flight (Section 11.4).
- **No credentials, tokens, or secrets** handled or stored by the
  dashboard, since EP-043 v1 has none to manage (Section 9.3).
- **Minimal dependency footprint**, consistent with the project's
  demonstrated stdlib-first, dependency-averse precedent
  (`EP043_DESIGN.md` Section 16, `EP044_DESIGN.md` Section 9's
  comparison table) — a browser frontend inherently requires build
  tooling a Python backend does not, so this principle is applied as
  "minimal *relative to the chosen frontend ecosystem's norms*," not
  "zero dependencies" (Section 14).

## 8. Technology Evaluation

Investigated against: no existing frontend, no `package.json`, no
`node_modules`, no `webpack`/`vite`/`.babelrc`/`tsconfig.json`
anywhere in the repository (confirmed by direct `find`/`ls` during
this STEP); Python 3.12 backend (`pyproject.toml`); the project's
`config/config.yaml`-driven, YAML/dataclass-based configuration
convention; and EP-044's own precedent of evaluating options in a
comparison table before recommending one (`EP044_DESIGN.md` Section
9).

| Criterion | Option A: React + Vite | Option B: Vue 3 + Vite | Option C: Plain HTML/CSS/JS (no framework, no build step) |
|---|---|---|---|
| Project compatibility | New ecosystem (Node/npm) for a currently pure-Python repo; no existing convention to conflict with | Same as React — new ecosystem | Zero new ecosystem — no Node/npm/build tooling of any kind required |
| Dependency footprint | `react`, `react-dom`, `vite` + dev deps (~100-200MB in `node_modules`, none shipped to the browser) | Comparable to React; Vue's runtime itself is smaller | None — no `node_modules`, no `package.json`, no lockfile |
| Maintainability | High for a growing UI; component model scales well if EP-045 later grows (Section 21's caution against scope creep still applies) | Comparable to React; often considered slightly gentler learning curve | Lower as complexity grows (manual DOM management); acceptable for the intentionally small V1 scope in Section 6 |
| Build complexity | Requires a build step (`vite build`) producing static assets to serve (Section 16) | Same as React | **None** — files can be served as-is; no build step, no bundler config to maintain |
| Testing | Mature ecosystem (Vitest/Jest + Testing Library) for component-level and logic-level tests | Comparable (Vitest + Vue Test Utils) | Plain JS is testable with any JS test runner, but there is no component-boundary convention to test against — tests would be ad hoc |
| Development experience | Hot-module-reload dev server (`vite dev`), TypeScript support, large ecosystem | Comparable dev experience | Manual browser refresh; no HMR; simplest possible mental model |
| Integration with EP-043 REST API | Straightforward: `fetch()`/`axios` calls from components/hooks | Straightforward: `fetch()`/`axios` calls from components/composables | Straightforward: `fetch()` calls from plain `<script>` — the API contract (Section 4) does not require any framework |
| Packaging/deployment implications | Produces a `dist/` of static files; needs a decision on same-origin vs. separate server (Section 16) | Same as React | Produces no separate build artifact — the source files *are* the deployable artifact; same Section 16 hosting decision still applies |
| Consistency with existing project conventions | None — this would be the project's first JS/Node dependency of any kind (`requirements.txt`/`pyproject.toml` show zero JS tooling today) | Same as React | Best fit for a Python-only repository with an explicit "avoid unnecessary dependencies" standard (`AI_GENERATION_STANDARD.md`, "Dependency Policy") |
| Fit for Section 6's *intentionally minimal* V1 scope (status + one command form + one result area) | More framework than the V1 feature set requires — the entire V1 UI is a handful of static regions bound to three endpoints, not a multi-view application | Same over-fit concern as React | **Best fit** — the V1 feature set (Section 6) is exactly the complexity level plain HTML/CSS/JS handles well: a handful of DOM regions, three `fetch()` calls, no client-side routing, no complex state tree |
| Risk of scope creep | Framework choice creates gravitational pull toward "since we have React, let's add more views" — a real risk given Section 21's explicit warning against this EP becoming "a large application framework" (echoing `EP043_DESIGN.md` Section 21.3's identical caution for the REST API itself) | Same risk as React | Lowest — a framework-free approach structurally resists scope creep, since adding features costs proportionally more effort without component/routing scaffolding already in place |

## 9. Recommended Technology

> **Implemented As (STEP 2/3):** APPROVED and implemented exactly as
> recommended below — plain HTML/CSS/JavaScript, no framework, no
> build step. `web/public/{index.html, app.js, styles.css}`. No
> `package.json`, no Node.js requirement was introduced. See
> `docs/architecture/audits/EP045_AUDIT.md` Section 6.

**RECOMMENDED — OWNER APPROVAL REQUIRED**

Recommend **plain HTML/CSS/JavaScript, with no build step and no
frontend framework**, served as static files, for EP-045 V1.

Rationale:

- The V1 functional scope (Section 6) is deliberately small: a
  connection indicator, a status display, one command-submission
  form, and one result/error area — four DOM regions bound to three
  `fetch()` calls. This is squarely within what unframeworked
  HTML/CSS/JS handles cleanly, and does not need component
  composition, client-side routing, or a state-management library to
  stay maintainable at this scope.
- It introduces **zero new project dependencies** — no `package.json`,
  no `node_modules`, no Node.js toolchain requirement for anyone
  building or running Jarvis. This is the same reasoning
  `EP043_DESIGN.md` Section 16 used to justify a stdlib-only REST
  server ("adds zero dependency-selection risk") and the same
  dependency-averse precedent `AI_GENERATION_STANDARD.md`'s
  Dependency Policy establishes project-wide ("Never introduce a new
  third-party dependency unless explicitly requested... Always reuse
  existing libraries already used by the project").
- Unlike EP-044's GUI-toolkit decision (Section 9 of
  `EP044_DESIGN.md`), where the stdlib (`tkinter`) was judged
  genuinely insufficient for a *responsive, threaded, native* desktop
  UI, no equivalent "the simplest option cannot deliver the stated
  objective" argument exists here: a browser already provides an
  asynchronous, non-blocking HTTP primitive (`fetch`) natively, so the
  justification EP-044 used to add a first-ever GUI dependency does
  not carry over to justify a first-ever JS-framework dependency.
- It requires no packaging/build pipeline decision (Section 16) beyond
  "serve these static files," which is the simplest available option
  and defers any framework/build-tooling investment until a
  demonstrated V2 requirement exists.

**React + Vite is documented as the recommended fallback** if the
owner anticipates EP-045 growing substantially beyond V1's scope
(e.g. toward the "Optional/Future" items in Section 6, or beyond) and
prefers to pay the framework/build-tooling cost once, up front, rather
than potentially migrating later. **Vue 3 + Vite is comparable to
React on every criterion in Section 8** and is not separately
recommended over React, since nothing in the repository favors one
over the other — Section 8's table applies to both equally.

This decision requires owner approval because, like EP-044's GUI
toolkit decision, it is a **first-of-its-kind dependency category** for
the project (the first JS-ecosystem tooling of any kind, if React/Vue
is chosen instead) — a product/architecture threshold this STEP should
not finalize unilaterally, exactly as `EP044_DESIGN.md` Section 10
treated its own PySide6 recommendation.

```
Technology: Plain HTML/CSS/JavaScript (no framework, no build step)
Purpose: Frontend for the EP-045 Web Dashboard, V1.
Why existing infrastructure is insufficient: N/A — this option adds
  no new infrastructure; it uses only what a browser already provides.
Alternative: React + Vite (or Vue 3 + Vite, equivalent on all
  Section 8 criteria) — recommended fallback if the owner anticipates
  scope growth beyond V1 and prefers to pay framework/build cost
  up front.
Decision: RECOMMENDED — OWNER APPROVAL REQUIRED.
```

## 10. Proposed Architecture

```text
Browser (user's machine, loopback or LAN per Section 9.4)
      │  HTTP (fetch)
      ▼
  Web Dashboard          (static HTML/CSS/JS, or a future framework
                           build's output — Section 16 hosting model)
      │  HTTP (fetch, same three endpoints EP-044 already consumes)
      ▼
  EP-043 REST API         (RestApiServer/ApiRouter — src/core/api/,
                           UNCHANGED, no new endpoint)
      │
      ▼
  CommandRouter            (SHARED — unchanged, same instance every
                           other transport already uses)
      │
      ▼
  JARVIS                  (existing Service/Core/Module stack —
                           unchanged)
```

This is architecturally identical in shape to EP-044's diagram
(`EP044_DESIGN.md` Section 13's table, `EP043_DESIGN.md` Section 6) —
the Web Dashboard is a fourth client of the same unchanged contract,
not a new architectural layer. The Web Dashboard must **not** directly
import or access `src.core`, `src.services`, `src.modules`,
`CommandRouter`, Bootstrap internals, database internals, or any other
Jarvis internal implementation detail — a browser process could not do
this even if instructed to (it cannot execute Python or reach the
filesystem the server runs on), but the same boundary is stated here
explicitly, matching EP-043/EP-044's own architectural principle
verbatim.

## 11. UI Architecture

Kept intentionally small, matching Section 6's minimal V1 scope and
this STEP's explicit instruction not to "turn EP-045 into a complete
Jarvis web platform."

### 11.1 Page structure

**Single page, no client-side routing.** The V1 feature set (Section
6) does not justify multiple views or a router; a single page with
four regions is sufficient and avoids introducing routing complexity
the scope does not need — the same reasoning `EP044_DESIGN.md`
Section 15 used to justify a single Main Window with sub-areas rather
than multiple windows.

### 11.2 Regions

| Region | Purpose | Data source | User actions |
|---|---|---|---|
| Connection indicator | Shows disconnected / connecting / connected / API unavailable | `GET /health`, checked on load and on manual refresh | Manual "reconnect"/"check connection" button |
| Status area | Shows the `GET /api/v1/status` result (mirrors CLI `system status`) | `GET /api/v1/status` | Manual refresh |
| Command area | Module / action / arguments input fields and a submit control | User input | Submit |
| Result area | Shows the most recent `CommandResponse` (`success`, `message`) | `POST /api/v1/commands` result | None (read-only) |
| Error area | Shows the most recent transport-level error (Section 12), separate from a business-level `success: false` result | Any caught error from Sections 4/12 | None (read-only) |
| Connection settings | API base URL / host / port configuration (Section 17) | Section 17 dashboard-side config | Save / apply |

Discrete module/action/arguments input fields are proposed for V1
(not a single CLI-syntax text field), mirroring `EP044_DESIGN.md`
Decision D5's identical reasoning: zero client-side command-line
parsing logic is required, keeping the fetch layer a pure transport
concern. A CLI-syntax alternative remains a documented Optional/Future
item (Section 6), not a V1 requirement.

### 11.3 Navigation

None required — a single page satisfies Section 6's entire REQUIRED
list.

### 11.4 Responsive behavior

The regions in Section 11.2 should be laid out in a single column on
narrow viewports and may use a wider grid on desktop viewports — no
component library or CSS framework is required to achieve this; plain
CSS (flexbox/grid + media queries) is sufficient for four static
regions and is consistent with Section 9's recommended
no-framework technology.

### 11.5 Browser compatibility baseline

**RECOMMENDED — OWNER APPROVAL REQUIRED**: current versions of
Chrome, Firefox, Safari, and Edge (i.e., no explicit legacy-browser
support, no polyfills). No repository document specifies a browser
support matrix; this is proposed as the smallest reasonable baseline
for a local/loopback administrative tool, not derived from an existing
project statement (Section 20, Open Question 5).

## 12. API Integration

Mirrors `EP044_DESIGN.md` Section 14's API-client design, re-expressed
for a browser `fetch()`-based client rather than Python `requests`:

- All three endpoints from Section 4.1 are called via `fetch()`.
  `POST /api/v1/commands` sends `Content-Type: application/json`
  explicitly (Section 4.3 — avoids relying on the server's lenient
  no-header fallback).
- **`success: false` still means HTTP 200.** The dashboard must
  inspect the parsed JSON body's `success` field to distinguish "the
  command ran and failed" from "the command ran and succeeded" — the
  identical rule `desktop/viewmodels/main_window_viewmodel.py` already
  encodes for the Desktop UI (Section 5.1).
- **Timeout**: `fetch()` has no built-in timeout; an `AbortController`
  with a timer is the standard browser mechanism to enforce one.
  Exact duration: see Section 20, Open Question 4 (proposed default
  mirrors EP-044's `DEFAULT_TIMEOUT_SECONDS = 10.0`, for consistency
  across Jarvis's two existing REST clients, pending owner
  confirmation).
- **No automatic retries**, for the identical reason
  `EP044_DESIGN.md` Section 14 gives: `POST /api/v1/commands` may have
  side effects, so a failed/timed-out request must not be silently
  retried.
- **Error categories** (mirroring Section 5.1's typed-error model,
  re-expressed for the browser): network error (`fetch` rejects, e.g.
  `TypeError: Failed to fetch` — server unreachable), timeout (the
  `AbortController` fired), HTTP error (4xx/5xx — the server
  responded with `ErrorPayload`, Section 4.2), and malformed response
  (200 status but the body is not valid JSON, or is JSON missing an
  expected field). These four categories are distinct and must be
  handled distinctly in the Error area (Section 11.2), not collapsed
  into one generic message.
- **No client-side model/DTO layer beyond plain JSON handling** is
  proposed for V1, since Section 9 recommends no framework and no
  build step — a TypeScript type layer (mirroring
  `desktop/models/dto.py`'s relationship to `src/core/api/dto.py`)
  becomes available naturally if Section 9's fallback (React/Vue with
  TypeScript) is chosen instead; this is noted as a consequence of the
  Section 9 decision, not a separate open question.

## 13. State Management

Two independent, small state concerns, mirroring `EP044_DESIGN.md`
Section 16's identical reasoning for keeping connection health and
command outcome orthogonal:

```
ConnectionState: DISCONNECTED | CONNECTING | CONNECTED | API_UNAVAILABLE
CommandState:    IDLE | REQUEST_IN_PROGRESS | SUCCEEDED | FAILED | ERROR
```

No external state-management library (Redux-equivalent, or any
framework-specific store) is proposed for V1 — two small enum-like
values held in plain JavaScript variables (or component state, if
Section 9's framework fallback is chosen) are sufficient for this
scope, matching Section 7's "minimal dependency footprint"
requirement and `EP044_DESIGN.md` Section 16's identical conclusion
("no third-party state-management library... is justified for two
small enums and this scope").

## 14. Error Handling

Directly mirrors `EP044_DESIGN.md` Section 18's seven-category model,
re-verified as applicable unchanged to a browser client:

| Category | Cause | Shown to user | Notes |
|---|---|---|---|
| Network error | Server unreachable / connection refused / CORS-blocked (Section 9.2) | Yes — plain-language "cannot reach Jarvis" message | A CORS failure and a genuine connection failure are indistinguishable to `fetch()` (both reject with a generic `TypeError`) — the dashboard cannot tell these apart client-side; Section 9.2 is the mitigation. |
| Timeout | `AbortController` fired before a response arrived | Yes — "request timed out" | |
| HTTP error (4xx/5xx) | Transport-level rejection (Section 4) | Yes — the server's `ErrorPayload.message`, already guaranteed never to contain a stack trace | |
| Command failure (`success: false`, HTTP 200) | The command ran but the underlying operation failed | Yes — the `message` field, in the Result area, **not** the Error area (it is a normal result, not a transport error) | Matches `EP044_DESIGN.md`'s identical distinction. |
| Malformed response | 200 status but body isn't valid JSON / missing expected fields | Yes — generic "unexpected response from Jarvis" | |
| Unexpected client error | Any exception not covered above (a bug in the dashboard's own JS) | Yes — generic message, never a raw stack trace/console-only detail exposed in the UI | |

Raw server or client stack traces are never shown to the user,
matching EP-043's own client-facing error policy
(`src/core/api/api_error.py`) and EP-044's identical rule
(`EP044_DESIGN.md` Section 18).

## 15. Security

### 9.1 Current EP-043 posture (inherited, unchanged)

No authentication, no TLS, no rate limiting (Section 4.6-4.7). A Web
Dashboard does not change this posture — it is a fourth client of an
already-no-auth API, exactly as EP-044 was the third.

### 9.2 CORS — the one genuinely new consideration for EP-045

> **Implemented As (STEP 2/3):** Owner selected same-origin serving
> (Option A below) specifically to avoid this. **No CORS policy was
> added.** `RestApiServer` gained an optional `static_dir` capability
> instead (see Section 21's updated note and
> `docs/architecture/audits/EP045_AUDIT.md` Section 8). This
> subsection's analysis is preserved because it is exactly the
> reasoning that led to that choice, not because CORS was implemented.

Unlike EP-044's native `requests` calls, a browser `fetch()` call from
a page served on one origin (e.g. `http://127.0.0.1:5173` if served by
a dev server, or a different port than the API) to
`http://127.0.0.1:8080` (the API's default) is subject to the
browser's same-origin policy and **CORS preflight requirements**.
`src/core/api/rest_api_server.py` (confirmed by direct read, Section
3.2) sends no `Access-Control-Allow-Origin` header and has no
`OPTIONS` handler — a cross-origin `fetch()` from the dashboard to the
API **will fail** unless one of the following is true:

1. **Same-origin deployment** (Section 16, Option A): the dashboard is
   served *by* `RestApiServer` itself, or from the exact same
   `host:port`, eliminating the cross-origin problem entirely without
   any CORS code change.
2. **A CORS policy is added to `RestApiServer`** — this would be a
   **new REST API capability**, explicitly out of scope for this STEP
   (Section 6.1: no new endpoints or server-side changes are proposed)
   and already listed as a `docs/BACKLOG.md` item deferred from
   EP-043 v1 ("REST API CORS configuration"). This document does
   **not** propose implementing it; it is listed as Open Question 1
   below, since resolving it requires an owner decision about whether
   EP-045 or a separate EP should modify `src/core/api/`.

This is the direct, concrete reason Section 16 treats "same-origin vs.
separate frontend server" as the single most consequential open
architectural question in this document — it is not merely a
deployment-convenience choice, it determines whether the dashboard can
function *at all* without an EP-043 server-side change.

### 9.3 Authentication

None to configure — EP-043 v1 has none (Section 4.6). If a future EP
adds authentication to the REST API, the Web Dashboard's API layer
(Section 12) is the layer that would need updating — a
forward-compatibility note, not a design decision made now (identical
in spirit to `EP044_DESIGN.md` Section 19's equivalent note for the
Desktop UI).

### 9.4 Localhost binding vs. browser exposure

A browser-based client raises one consideration a native desktop
client does not: **if the dashboard's static files are served from a
non-loopback address** (e.g. so a phone or another machine on the same
LAN can open it), the *browser* may be running on a different machine
than Jarvis, meaning the REST API (`api.host`) would also need to be
reachable from that machine — which `EP043_DESIGN.md` Section 11
already documents is "technically possible but not a supported v1
deployment mode" given the total absence of authentication. This
document does not propose changing `api.host`'s safe loopback-only
default or deployment posture; it flags that a Web Dashboard makes the
temptation to do so more likely than a desktop-only client did, and
that doing so remains just as unsafe as it already was under EP-043's
own documented risk acceptance (Section 4.6-4.7).

### 9.5 CSRF

Not applicable in the traditional sense: EP-043 has no session/cookie
mechanism for CSRF to exploit (Section 4.6). If authentication is
added in a future EP, CSRF should be re-evaluated at that time
depending on the authentication mechanism chosen (e.g. cookie-based
sessions would need CSRF protection; a bearer-token scheme typically
would not, if the token is never stored in a cookie). Not a v1 concern
today.

### 9.6 Sensitive configuration / error information leakage

Unchanged from EP-043's own guarantee (`api_error.py`: client never
receives a raw stack trace) and EP-044's identical rule
(`EP044_DESIGN.md` Section 19) — the Web Dashboard displays only the
server's own pre-sanitized `ErrorPayload.message` or a generic
client-side string, never internal diagnostic detail (Section 14).

## 16. Testing Strategy

Following the project's existing per-EP testing convention
(`tests/EP043/test_rest_api.py`, `tests/EP044/test_desktop_ui.py`,
`AI_DEVELOPMENT_PLAYBOOK.md` Phase 3), a future `tests/EP045/` suite
— and, since this frontend has no Python runtime of its own, a
JS-side test suite colocated with the frontend code — should cover:

- **API client tests** (JS): mocked/stubbed `fetch()` responses for
  all three endpoints, HTTP 400/404/405/415/500, connection
  failure/refusal, timeout, and malformed JSON — the same category
  list `tests/EP044/test_desktop_ui.py`'s 13 API-client tests already
  establish as sufficient coverage for this exact contract (Section
  4), re-implemented for `fetch()` instead of `requests`.
- **Component/UI tests**: for V1's no-framework approach (Section 9),
  DOM-manipulation logic can be tested with a lightweight DOM-testing
  library (e.g. `@testing-library/dom` with `jsdom`) without a full
  browser; if the React/Vue fallback (Section 9) is chosen instead,
  each framework's own established testing convention (Testing
  Library + Vitest/Jest) applies.
- **Error-state tests**: one test per Section 14 category, mirroring
  `tests/EP044/test_desktop_ui.py`'s equivalent structure.
- **Connection-failure tests**: dashboard behavior when `GET /health`
  fails (Section 11.2's Connection indicator must show
  `API_UNAVAILABLE`/`DISCONNECTED`, not crash or hang).
- **Command-execution tests**: success, business failure
  (`success: false`), and transport failure paths for
  `POST /api/v1/commands`.
- **Browser/headless tests**: an end-to-end smoke test (e.g. via a
  headless-browser tool) that loads the dashboard, waits for a real
  `GET /health` success against a real, test-started `RestApiServer`
  (the same integration-test pattern
  `tests/EP044/test_desktop_ui.py`'s 2 "real-server integration
  tests" already establish, adapted to drive a browser instead of a
  Python client), and confirms the connection indicator updates.
- **Integration/regression**: `test EP043` and `test EP044` must
  continue passing unmodified — EP-045 STEP 2 touches neither
  `src/core/api/` nor `desktop/` (Sections 6.1, 5.3), so no regression
  in either suite is expected; a fresh `test all` run should still
  confirm this rather than assume it.

**What can be tested without a real browser**: all of the above except
the final headless end-to-end smoke test — the same "test as much as
possible without launching a real GUI/window" principle
`EP044_DESIGN.md` Section 23 already establishes for the Desktop UI's
MVVM ViewModel layer applies here to the dashboard's fetch/state logic,
which should be structured (even without a framework) so it is
callable and testable independent of live DOM rendering.

**What requires browser automation**: only the final end-to-end smoke
test above — verifying that the actual rendered page performs a real
`fetch()` and updates real DOM elements.

## 17. Configuration

**Decision (proposed): the Web Dashboard owns its own client-side
configuration, separate from `config/config.yaml` — the identical
principle `EP044_DESIGN.md` Decision D6 already established for the
Desktop UI, re-applied.**

Unlike the Desktop UI, a browser cannot read an arbitrary server-side
filesystem file at all (no filesystem access from browser JS), so this
is not merely a "should not" (Desktop UI's reasoning) but a "cannot"
constraint for a Web Dashboard by construction — reinforcing the same
conclusion `EP044_DESIGN.md` reached by a different, weaker argument.

Proposed dashboard-side configuration values (mirroring
`EP044_DESIGN.md` Section 17's list): API base URL (or host + port),
and request timeout.

**UNRESOLVED — PROJECT OWNER DECISION REQUIRED**: the storage
mechanism differs fundamentally from EP-044's filesystem-YAML answer,
since a browser has no general filesystem access. Candidate options,
none selected here:

1. A hardcoded default (e.g. `http://127.0.0.1:8080`) baked into the
   served JS at build/serve time, with an in-page settings form that
   persists overrides to the browser's storage.
2. Browser storage (`localStorage`) for a user-adjusted override,
   defaulting to option 1's value if unset.
3. A small server-provided configuration endpoint or injected
   `<meta>`/global-JS-variable value at serve time (relevant only
   under Section 16's same-origin-serving option, where *something* —
   even if not `RestApiServer` itself — controls what HTML is served).

This is a genuine unresolved product/architecture decision, not
resolved here, since it interacts directly with Section 16's
still-open hosting-model question (an answer to "how is this served"
partially determines which of options 1-3 is even available).

## 18. Non-Goals

Explicitly not part of EP-045, matching this document's own governing
instruction to avoid scope creep:

- Chat, memory browser, agent management, workflow editor, voice
  control, file manager, notifications, real-time streaming/WebSocket
  support, advanced analytics (Section 6, "Out of Scope").
- Any new REST endpoint or modification to `src/core/api/` (Section
  6.1) — including a CORS policy (Section 9.2), which remains
  `docs/BACKLOG.md`'s pre-existing, still-deferred item unless a
  future EP or an owner-approved amendment to this document decides
  otherwise.
- Any modification to EP-044's `desktop/` package (Section 5.3).
- Authentication/authorization of any kind (Section 9.3) — EP-043 v1
  has none to build against.
- A frontend framework, build pipeline, or component library beyond
  Section 9's recommendation, unless the owner selects the React/Vue
  fallback.
- Packaging/installer artifacts, containerization, or a CI/CD pipeline
  for the dashboard (design-level direction only — Section 16).
- Any implementation code, file creation beyond this design document,
  or dependency installation (this STEP — see Section 22).

## 19. Dependencies

Every dependency STEP 2 would likely require, separated by category.
**None are installed by this STEP.**

### Existing (already in the project, reusable with zero new cost)

- None directly reusable for the *frontend* itself — EP-045's
  frontend is a new technology category for this repository (no
  existing JS tooling of any kind exists today, per Section 8's
  investigation). `requests`/`PyYAML` (reused by EP-044) are
  Python-side and not applicable to a browser client.
- `src/core/api/*` (server-side, EP-043) — consumed unchanged, no new
  dependency incurred by consuming it.

### New (contingent on Section 9's decision)

```
If Plain HTML/CSS/JS (RECOMMENDED) is approved:
  No new dependency. No package.json. No Node.js requirement for
  running the dashboard (a Node.js *development-convenience* tool
  such as a trivial static-file server is optional, not required —
  Python's own stdlib `http.server` module, already indirectly
  proven suitable for HTTP serving by EP-043's own RestApiServer,
  could serve static files equally well for local development if the
  owner prefers not to introduce even a dev-only Node dependency).

If React + Vite (fallback) is approved instead:
  react, react-dom (runtime)
  vite (build tool, dev dependency)
  A Node.js toolchain (npm/pnpm/yarn) — required to run Vite at all;
    this itself is a new environmental requirement for the project
    (Section 9's stated cost of choosing this fallback).
```

### Optional

- A headless-browser test tool (Section 16's end-to-end smoke test) —
  e.g. Playwright or a comparable tool — needed only for the one
  browser-automation test category in Section 16, regardless of which
  Section 9 option is chosen.

### Development/test dependencies

- If Section 9's no-framework option is chosen and any JS-side unit
  tests are desired (Section 16): a minimal JS test runner (e.g. `node`'s
  built-in test runner, or a small dependency like `vitest` used in
  standalone mode without the rest of the Vite/React stack).

No dependency in this section is installed, added to any manifest, or
otherwise acted upon during this STEP.

## 20. Proposed Directory Structure

Proposed, not created, in this STEP:

```
web/                        # New top-level directory, parallel to
                             # src/ and desktop/ (see rationale below)
    public/                 # Static HTML entry point, favicon, etc.
        index.html
    src/                     # Frontend source
        api/                 # fetch()-based API client (Section 12)
        components/          # UI regions (Section 11.2) — plain JS
                             # modules for the no-framework option, or
                             # framework components for the fallback
        state/               # ConnectionState/CommandState (Section 13)
        config/              # Dashboard-side configuration (Section 17)
        styles/               # CSS
    tests/                   # JS-side tests (Section 16) — separate
                             # from the project's tests/EP0NN/
                             # convention, since those are Python/
                             # pytest-based and this is a JS suite
    package.json             # Only if Section 9's framework fallback
                             # is chosen; absent for the plain-JS
                             # recommendation
```

`web/` is proposed as a new top-level directory rather than nested
inside `src/` (which is exclusively Python) or `desktop/` (which is
EP-044's own package, not to be modified — Section 5.3), mirroring
`EP044_DESIGN.md` Decision D1's identical reasoning for placing
`desktop/` at the top level rather than inside `src/ui/`.

**EXISTING** (unchanged by EP-045): `src/`, `desktop/`, `config/`,
`docs/`, `tests/EP001`-`tests/EP044`.

**NEW IN STEP 2** (pending owner approval of this document): `web/`
and everything under it; `tests/EP045/` (a thin Python-side
integration/regression suite, if any Python-side test — e.g. the
real-server integration smoke test in Section 16 — is implemented
using the project's existing `pytest`/`TestRegistry` convention rather
than purely in JS).

**MODIFIED IN STEP 2**: none proposed under `src/`, `config/`,
`requirements.txt`, or `desktop/`, **unless** Open Question 1 (CORS)
is resolved by the owner in favor of a server-side change — in which
case `src/core/api/rest_api_server.py` would require modification, but
that is explicitly not decided or authorized by this document (Section
6.1, 18).

## 21. Packaging / Deployment

> **Implemented As (STEP 2/3):** Owner resolved Open Question 1 in
> favor of **Option A** below. `RestApiServer` gained an optional
> `static_dir: Path | None = None` constructor parameter and a
> `_try_serve_static()` handler method; wired through a new,
> opt-in `api.web_dashboard_dir` config key
> (`config/config.yaml`, default `"web/public"`) resolved by
> `Bootstrap._resolve_web_dashboard_dir()`. When unset, empty, or
> pointing at a non-existent directory, behavior is byte-identical to
> pre-EP-045 `RestApiServer` (verified by
> `tests/EP045/test_web_dashboard.py`). See
> `docs/architecture/audits/EP045_AUDIT.md` Sections 6 and 8 for the
> full justification-and-verification record; the STEP 2 "changed
> files" report contains the original "why this change is required"
> demonstration requested before the change was made.

Design-level only, per this STEP's explicit instruction — no
packaging tool is installed or invoked, no build is run.

- **Development mode**: for the recommended no-framework option
  (Section 9), "development mode" is simply opening/serving the static
  files directly — no build step exists to run. For the framework
  fallback, `vite dev`'s hot-reload dev server would be used.
- **Production build**: no-framework option produces no build
  artifact distinct from its source (the files themselves are the
  deployable unit). The framework fallback would produce a `dist/`
  folder of static assets via `vite build`.
- **Static files / serving strategy — the central open question**:
  two genuinely different models, both viable, not resolved here:

  - **Option A — Same-origin, served by `RestApiServer` itself.**
    `RestApiServer` (Section 4.5) would need a new capability to serve
    static files alongside its existing three JSON routes. This
    **would require modifying `src/core/api/rest_api_server.py`** —
    out of this STEP's scope to decide or implement (Section 6.1) —
    but has the significant advantage of eliminating Section 9.2's
    CORS problem entirely, since the dashboard and the API would share
    an origin.
  - **Option B — Separate frontend server/process**, serving the
    static files independently (e.g. a lightweight dev server, or any
    static-file host) on a different port than `RestApiServer`. This
    requires **no change to `src/core/api/`**, staying fully within
    this STEP's non-goals (Section 18), but **requires resolving
    Section 9.2's CORS gap** for the dashboard to function at all —
    which itself requires an `src/core/api/rest_api_server.py` change
    (a CORS policy) unless the two are somehow still made same-origin
    by other means (e.g. a reverse proxy in front of both — a further,
    undesigned option).

  **Both viable paths converge on the same conclusion: some
  `src/core/api/` change is likely necessary for EP-045 to function
  end-to-end, whether that change is "serve static files" (Option A)
  or "add a CORS policy" (Option B).** This document does not
  authorize either change; it is the single most important
  architectural fact this STEP surfaces, and is escalated as Open
  Question 1 (Section 22) rather than decided.

- **Desktop/local usage**: the primary supported deployment mode for
  V1, consistent with EP-043's own loopback-only default (Section 4.5)
  and EP-044's identical local-usage framing.
- **Future remote/LAN usage**: not designed here; would compound
  Section 9.4's already-documented risk (no authentication) and is
  explicitly out of scope for V1 (Section 18).

## 22a. Owner Decisions (received prior to STEP 2) — Resolution of Section 22

The project owner resolved the following Section 22 questions before
STEP 2 began (verbatim decisions recorded in
`docs/architecture/audits/EP045_AUDIT.md` Section 2; full text in the
STEP 2 delivery's governing instructions):

| # | Question | Owner Decision |
|---|---|---|
| 1 | Same-origin vs. separate server | **Same-origin (Option A).** `src/core/api/rest_api_server.py` modification authorized, conditioned on demonstrating necessity first (done — see Section 21 note and the STEP 2 report). |
| 2 | CORS policy | **Not needed** — resolved as a consequence of Question 1's same-origin decision. No CORS policy was added. |
| 3 | Frontend technology | **Plain HTML/CSS/JavaScript approved**, no React/Vue/build step. |
| 4 | Dashboard location | **`web/public/` approved** (implemented as designed in Section 20). |
| 5 | Target browsers | Not explicitly re-confirmed by the owner; STEP 2 made no browser-specific accommodation, so Section 11.5's proposed evergreen-browser baseline stands as the de facto implemented assumption — **remains open** for explicit owner sign-off. |
| 6 | Health-check polling cadence | **Manual-only implemented** (a "Check connection" button and a one-time page-load check — no periodic polling), consistent with the owner's overall "keep V1 minimal" instruction and EP-044's own identical precedent. |
| 7 | Request timeout | **10 seconds implemented** (`REQUEST_TIMEOUT_MS = 10_000` in `web/public/app.js`), matching EP-044's own resolved value. |
| 8 | Dashboard-side config storage | **Resolved by elimination**: same-origin serving (Question 1) means `app.js` uses relative URLs (`fetch("/health")`, etc.) — no API base URL/host/port needs to be configured or stored anywhere. This is a direct, documented consequence of the Question 1 decision, not an independent choice. |
| 9 | Localhost-only vs. network access | **Localhost-only confirmed** — owner decision #4 explicitly: "Keep the current EP-043 localhost/no-auth security posture unchanged. Do not expose the API to the network." No change to `api.host`'s default. |
| 10 | Packaging/deployment sub-package split | **Not split** — implemented within EP-045 STEP 2 directly, per the owner's "proceed with STEP 2" instruction. |

Question 5 (target browsers) is the only Section 22 item that remains
genuinely open after STEP 2/3; it is carried forward, unresolved, in
`docs/architecture/audits/EP045_AUDIT.md` Section 13 ("Open
Questions").

## 22. Open Questions (original STEP 1 text, preserved for record)

Genuine project-owner decisions this STEP cannot resolve from
repository evidence, in priority order (Question 1 is the most
architecturally consequential — see Section 21):

1. **Same-origin vs. separate frontend server (Section 16, 9.2)** —
   and, as a direct consequence, **whether `src/core/api/rest_api_server.py`
   may be modified at all as part of EP-045** (to serve static files,
   to add a CORS policy, or both). This is the single decision every
   other open question and much of Section 11-17's design partially
   depends on.
2. **CORS policy** (Section 9.2) — if Option B (Section 16) is chosen:
   should it be scoped as part of EP-045, or as a separate,
   `docs/BACKLOG.md`-tracked follow-up to EP-043 itself (the backlog
   already lists "REST API CORS configuration" as a deferred EP-043
   v1 item, independent of EP-045's existence)?
3. **Frontend technology approval**: plain HTML/CSS/JS (recommended,
   Section 9) vs. React/Vue + Vite (fallback).
4. **Dashboard location/package structure**: confirm `web/` as a new
   top-level directory (Section 20), or an alternative.
5. **Target browsers** (Section 11.5): confirm the proposed "current
   evergreen browsers only" baseline, or specify a different one.
6. **Health-check polling cadence** (Section 6, "Optional/Future"):
   manual-only (simplest, mirrors EP-044's own still-unresolved
   Decision D4) vs. periodic polling, and at what interval.
7. **Request timeout value** (Section 12): confirm the proposed
   10-second default (matching EP-044's own resolved value), or set a
   different one.
8. **Dashboard-side configuration storage mechanism** (Section 17):
   which of the three candidate options (or another) is acceptable,
   given no browser filesystem access exists.
9. **Localhost-only vs. future network access** (Section 9.4): confirm
   V1 stays loopback-only-recommended (matching EP-043's own posture),
   or explicitly accept LAN exposure risk for a specific use case.
10. **Packaging/deployment scope**: should Section 21's hosting
    decision (whichever Question 1 resolves to) be implemented as part
    of EP-045 STEP 2, or split into a sub-package (e.g. EP-045.1
    frontend, EP-045.2 hosting/CORS), mirroring the project's own
    "Engineering Package Policy" for large EPs
    (`docs/architecture/JARVIS_ROADMAP.md`)?

None of these is silently decided by this document. Per
`AI_GENERATION_STANDARD.md` ("If functionality requires changing
architecture, STOP... leave a TODO") and this STEP's own governing
instruction, Question 1 in particular is flagged as a case where STEP
2 may need to touch `src/core/api/` — which every other constraint in
this document otherwise forbids — and is therefore the one question
that most requires explicit owner resolution before STEP 2 begins.

## 23. STEP 2 Boundary

> **Implemented As (STEP 2/3):** Delivered within this boundary
> exactly — see `docs/architecture/audits/EP045_AUDIT.md` Section 17
> ("File Change Audit") for the complete, verified list of every file
> created or modified. No file outside this section's authorized set
> was touched.

If the owner approves this document's recommendations (Sections 9,
10, and a resolution to Open Question 1), STEP 2 may implement:

**Files to create:**

- `web/` and its full proposed structure (Section 20), for whichever
  technology Question 3 resolves to.
- `tests/EP045/` (Python-side, if any test uses the existing
  `pytest`/`TestRegistry` convention — e.g. a real-server integration
  smoke test mirroring `tests/EP044/test_desktop_ui.py`'s pattern) and
  `web/tests/` (JS-side, Section 16).

**Files potentially modified** (contingent entirely on Open Question
1's resolution):

- `src/core/api/rest_api_server.py` — **only** if the owner selects
  Option A (same-origin static-file serving) or approves a CORS policy
  addition for Option B. **Not modified under any other outcome.**
- `config/config.yaml` — only if a same-origin serving decision
  (Option A) requires a new configuration key (e.g. a static-files
  directory path); not modified otherwise.
- `docs/architecture/JARVIS_ROADMAP.md`, `docs/BACKLOG.md` — status
  updates upon EP-045 completion, mirroring the exact convention
  EP-043/EP-044 already established (`EP044_AUDIT.md` Section 18).

**Dependencies potentially added:**

- Section 19's "New (contingent on Section 9's decision)" list —
  nothing beyond what that section already enumerates.

**Tests to create:** Section 16's full list (API client, component/UI,
error-state, connection-failure, command-execution, one headless
browser smoke test, regression confirmation).

**Tests to update:** none in `tests/EP001`-`tests/EP044` are expected
to require any change, since EP-045 does not modify `src/core/api/`'s
existing three endpoints' behavior (only, possibly, adds a capability
alongside them, per Open Question 1) and does not touch `desktop/`
(Section 5.3) — this expectation should be confirmed by a fresh
`test all` run at STEP 2/3, not assumed.

**Configuration changes:** none, unless Open Question 1 resolves to
Option A requiring a new `config/config.yaml` key (see above).

**Documentation changes:** `EP045_DESIGN.md` itself (STEP 2/3
addenda, mirroring `EP043_DESIGN.md` Section 21/22's and
`EP044_DESIGN.md`'s own precedent of appending an "as-built" summary
after implementation, rather than rewriting this document's original
STEP 1 content), plus the roadmap/backlog status updates above.

**STEP 2 must not:**

- Modify `desktop/`, or any file under `src/services/`,
  `src/modules/`, or `src/bootstrap.py` (Section 5.3, 7).
- Add a new REST endpoint beyond what Open Question 1/2's resolution
  explicitly authorizes.
- Implement any item in Section 6's "Out of Scope" list or Section
  18's Non-Goals.
- Implement packaging/installers/CI pipelines (Section 21) beyond
  whatever minimal static-file-serving mechanism Open Question 1
  resolves to.
- Populate `src/ui/dashboard.py` without first resolving Section 6's
  UNRESOLVED ownership question.
- Silently decide any of Section 22's ten open questions.

## 24. Acceptance Criteria

STEP 1 (this document) is accepted when:

- [x] `PROJECT_MANIFEST.md`, `AI_GENERATION_STANDARD.md`,
      `AI_DEVELOPMENT_PLAYBOOK.md`, `JARVIS_ROADMAP.md`,
      `docs/BACKLOG.md`, `docs/architecture/NON_GOALS.md` have been
      inspected.
- [x] `EP043_DESIGN.md`, `EP044_DESIGN.md`, `EP044_AUDIT.md`, and the
      actual EP-043/EP-044 source (`src/core/api/**`, `desktop/**`)
      have been inspected and cross-checked for discrepancies
      (Section 3.2) — none found.
- [x] The EP-043 REST API contract is documented exactly as
      implemented (Section 4), not as previously summarized.
- [x] What is reusable from EP-044 conceptually, and what is not, is
      explicitly separated (Section 5).
- [x] V1 functional scope is separated into Required / Optional /
      Future / Out of Scope / Unresolved (Section 6), with no item
      added beyond what project documentation supports.
- [x] No new REST endpoint is proposed as V1 scope (Section 6.1);
      any endpoint-adjacent need (CORS, static-file serving) is
      escalated as an Open Question (Section 22), not decided.
- [x] Frontend technology options are evaluated with a comparison
      table (Section 8) and a recommendation is issued, marked for
      owner approval (Section 9).
- [x] The Web Dashboard ↔ REST API architecture is fully defined
      (Section 10) and matches EP-043/EP-044's own established
      boundary principle.
- [x] UI architecture, state management, and error handling are
      designed (Sections 11, 13, 14).
- [x] Security implications — including the CORS gap specific to a
      browser client — are documented (Section 15).
- [x] Testing strategy is documented, separating what needs a real
      browser from what does not (Section 16).
- [x] Dependencies are separated into existing / new / optional /
      dev-test categories, contingent on the technology decision
      (Section 19).
- [x] A proposed directory structure is documented without being
      created (Section 20).
- [x] Packaging/deployment is documented at the design level only,
      surfacing the same-origin-vs-CORS tension as the central open
      question (Section 21).
- [x] Every genuine product/ownership decision is marked UNRESOLVED
      or RECOMMENDED — OWNER APPROVAL REQUIRED (Section 22), not
      assumed.
- [x] STEP 2's boundary is explicit, including the narrow,
      conditional exception under which `src/core/api/` may be
      touched (Section 23).
- [x] No implementation code, frontend file, test file, or existing
      source file was created or modified by this STEP.

STEP 2 (future) will be considered acceptable only once it further
satisfies, at minimum:

> **Implemented As (STEP 2/3):** every criterion below is satisfied
> and independently re-verified in
> `docs/architecture/audits/EP045_AUDIT.md` Sections 6-11 and 12
> ("Regression Verification"): EP-045 38/38, EP-043 83/83 (unmodified,
> no regression), EP-044 52/52 (`desktop/` untouched, no regression),
> full suite 5,549/5,549. Same-origin (Option A) was implemented
> consistently with no CORS failure in normal operation, since no
> cross-origin request is ever made.

- Dashboard starts successfully (loads in a browser without error).
- Dashboard communicates with EP-043 (`GET /health` succeeds against a
  real running server).
- Health/connection status is displayed and updates correctly.
- Jarvis status (`GET /api/v1/status`) is displayed.
- Commands can be submitted and results displayed, correctly
  distinguishing `success: true`/`false` per Section 4.1/12.
- All Section 14 error categories are handled without the UI crashing
  or hanging.
- The UI remains responsive (no blocking call on the main/render
  thread — Section 7).
- `test EP043` remains green, unmodified.
- `test EP044` remains green, unmodified.
- Full regression (`test all`) remains green.
- Whatever Open Question 1 resolves to (Option A or B, Section 16) is
  implemented consistently, with no CORS failure in normal operation.

## 25. Verification

> **Implemented As (STEP 2/3):** Superseded by
> `docs/architecture/audits/EP045_AUDIT.md`, which performs the full
> STEP 2/3 verification (regression re-run, file-change audit, and
> requirement-by-requirement conformance check) this section's STEP 1
> text could not yet perform. The STEP 1 text below is preserved
> unchanged as the historical record of what STEP 1 itself verified.

Because this is STEP 1 only, no implementation test was run for
EP-045 itself. Read-only repository inspection was performed (Section
3.1) and documentation was cross-checked against source (Section
3.2) — no source file, test file, configuration file, or dependency
manifest was modified as part of that inspection.


Verified that the only file created or modified by this STEP is:

```
docs/architecture/designs/EP045_DESIGN.md
```

No source code, no frontend code, no dependency, no configuration
change, no test, and no EP-044 (`desktop/`) file was created,
modified, or deleted by this STEP.

---

## 26. STEP 2/3 Implementation Summary (as-built)

Added after STEP 1's original text above, without altering it, per
this STEP's instruction to "clearly distinguish planned design from
implemented behavior."

**Delivered:**

- `web/public/index.html`, `web/public/app.js`, `web/public/styles.css`
  — plain HTML/CSS/JS dashboard, no build step, no framework.
  Same-origin `fetch()` calls to `/health`, `/api/v1/status`,
  `/api/v1/commands` using relative URLs.
- `src/core/api/rest_api_server.py` — added an optional `static_dir`
  parameter, a `_try_serve_static()` handler method, and a
  `static_dir` property. Off by default; behavior is unchanged from
  pre-EP-045 when unset.
- `src/bootstrap.py` — added `_resolve_web_dashboard_dir()`, reading
  the new `api.web_dashboard_dir` config key and degrading safely to
  "not served" if absent/empty/nonexistent.
- `config/config.yaml` — added `api.web_dashboard_dir: "web/public"`.
- `tests/EP045/test_web_dashboard.py` (38 tests) and one registration
  import in `src/modules/test_module.py`.

**Full independent verification, requirement-by-requirement
conformance, security review, and final verdict:** see
`docs/architecture/audits/EP045_AUDIT.md`.

**Not delivered (by design, per owner decision #5 and Section 6/18
above):** authentication, CORS, chat, memory browser, agent
management, workflow editor, voice, file management, notifications,
periodic health polling, any change to `desktop/`.

End of document.
