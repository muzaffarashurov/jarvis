# EP-059 — Distributed Runtime — Design Specification (STEP 1)

Status: **STEP 1 — DESIGN PROPOSED / OWNER APPROVAL REQUIRED.**

**STEP 2 implementation has NOT begun.**

No source file, test file, configuration file, dependency file, or
Bootstrap file has been created or modified as part of producing this
document. The only artifact created by EP-059 STEP 1 is this document
itself, `docs/architecture/designs/EP059_DESIGN.md`.

---

## 0. How this document relates to EP-054 through EP-058

Each of the five prior Phase 9 EPs began with a roadmap line whose
only content was a title and a phase-level, multi-EP-wide goal. Each
STEP 1 document disclosed this gap explicitly, then found a
concrete, textual anchor elsewhere in the repository — a docstring,
a runtime-visible message, or an unwired-but-complete package —
naming the exact mechanism the EP should build. **EP-059 is
different, and this document discloses that difference up front
rather than manufacturing a false anchor:** exhaustive search
(Section 2) found no docstring, comment, config key, or design
document anywhere in this repository that names "Distributed
Runtime," "distributed execution," "cluster," "multi-instance,"
"multi-node," or any close synonym as deferred, planned, or
out-of-scope future work. This is the first Phase 9/10 EP in this
project's history for which STEP 1 could not locate a specific,
already-written sentence pointing at the intended mechanism.

This does not mean no grounded candidate exists — Section 3's
discovery instead builds the candidate set from what the *runtime
architecture itself* already does today (Section 3.1–3.6), and
Section 5 evaluates several genuinely different ways EP-059 could
extend it, exactly as this task's own instructions require ("do not
assume that a requested capability needs new infrastructure — first
identify what already exists and what can be extended").

---

## 1. Problem / Goal

**Stated goal (verbatim, from the only two places EP-059 is named in
this repository):** `docs/architecture/JARVIS_ROADMAP.md`'s Phase 10
header: *"Complete the AI Operating System."* `docs/engineering/
ENGINEERING_GUIDE.md`'s identical wording. Beyond this one shared,
two-EP-wide sentence (Phase 10 = EP-059 + EP-060), and the bare title
"EP-059 Distributed Runtime," **no further specification exists
anywhere in the repository** (Section 2).

**What this document treats as the actual, derivable problem,** given
Section 3's discovery: Jarvis today runs as a single OS process
(`src/main.py` → one `Bootstrap` instance) that already hosts
*several concurrently-running execution contexts* inside that one
process — an interactive Shell loop, an auto-started, network-listening
REST API server on its own thread, a pool of daemon worker threads
(EP-036), and (when explicitly started) a Telegram bot gateway — all
sharing one `CommandRouter`/`Orchestrator` and one set of Services.
**No component in the repository today can answer the question "what
is this running Jarvis instance's runtime actually doing right now,
across all of its concurrent execution contexts?"** Each subsystem
reports its own status in isolation (`api status`, `worker status`,
`scheduler status`, ...); nothing aggregates them into a single,
consistent view of the process's own runtime shape. This document's
recommended approach (Section 5, Candidate A) treats *that* as
EP-059's grounded v1 scope — formalizing Jarvis's already-real,
already-running multi-execution-context architecture as a first-class,
introspectable "Runtime" concept, without inventing multi-machine
clustering, a new network protocol, or a new consensus/coordination
mechanism the repository gives no evidence anyone has designed.

---

## 2. Repository/specification inventory — what the repository actually says about EP-059 (verbatim)

| Location | Exact content |
|---|---|
| `docs/architecture/JARVIS_ROADMAP.md` line 1155 (Phase 10 checklist) | `EP-059 Distributed Runtime` — a bare title, no elaboration, no checkmark |
| `docs/architecture/JARVIS_ROADMAP.md` lines 258-259 ("Next Engineering Package" note, added by EP-058 STEP 4 doc-sync) | `**Next Engineering Package: EP-059 Distributed Runtime — NOT STARTED.** No EP-059 design, research, or implementation work has begun.` — a status pointer, not a spec |
| `docs/BACKLOG.md` lines 13-16 | `### EP-059 — Distributed Runtime` / `**NOT STARTED.**` — same pointer |
| `CHANGELOG.md` (EP-058 STEP 4 entry) | References EP-059 only as "the next, not-started Engineering Package" |
| `docs/architecture/JARVIS_ROADMAP.md` line 1020 / `docs/engineering/ENGINEERING_GUIDE.md` line 173 | `## Phase 10 — Jarvis Operating System` / `Complete the AI Operating System.` — a **phase-level** goal shared with EP-060 only, not EP-059-specific |
| Every EP-054–058 `_DESIGN.md`/`_ARCHITECTURE_AUDIT.md` | Zero mention of EP-059 by name or scope anywhere |
| Everywhere else (`PROJECT_MANIFEST.md`, `AI_GENERATION_STANDARD.md`, every package docstring in `src/`) | **Zero** mentions of "distributed," "cluster," "multi-node," "multi-instance," or "distributed runtime" that refer to Jarvis's own execution model. (Two coincidental, unrelated uses of the word "distributed" exist in `src/services/collaboration_service.py`/`collaboration_result.py`, both describing EP-032's in-process broadcast of "a request... distributed[ed]" to already-registered local `AgentProvider`s — confirmed, by reading both in full, to have no relationship to multi-process or multi-machine execution.) |

**Conclusion:** unlike EP-054 (`append_capabilities()`'s docstring),
EP-056 (`PromptBuilder`'s "reserved for the future Capability
Registry"), EP-057 (`compress_query()`'s zero-caller status), or
EP-058 (`PlanningProvider`'s explicit "future AI-/LLM-backed" callout),
**no existing file in this repository names a specific mechanism
EP-059 is meant to build.** This is disclosed as a first-class
discovery finding, not glossed over — Section 5's candidates are
therefore derived entirely from Section 3's inventory of the
*existing runtime's own shape*, not from a quoted sentence telling
this document what to build.

---

## 3. Current architecture / discovery findings

### 3.1 Exactly one process, one Bootstrap, confirmed by direct reading of the only entry point

`src/main.py` (`main()`) constructs exactly one `Bootstrap()`,
calls `bootstrap.run()` (which calls `initialize()` once), then hands
control to `bootstrap.shell.run()` — the interactive Shell's own
blocking main loop — until the user exits. There is no second entry
point, no `--worker`/`--daemon` CLI flag, no `multiprocessing`/`os.fork`/
`subprocess` call anywhere that would start a second, cooperating
Jarvis process (confirmed: `grep -rn "multiprocessing\|os.fork\|
Popen.*main.py" src/` returns no match tying it to Jarvis's own
runtime). **Jarvis today has no concept of "more than one instance of
itself" at all** — this is the single most important, and most
un-anchored, discovery finding this document makes: any candidate
that assumes multi-process or multi-machine coordination already has
*some* seed to build on would be factually wrong.

### 3.2 Several execution contexts already run concurrently inside that one process, sharing one `CommandRouter`

Confirmed by direct reading of `src/bootstrap.py`'s `initialize()`
sequence:

- **The interactive Shell** (`InteractiveShell`, constructed at line
  315) — the foreground, blocking loop `main.py` ultimately runs.
- **The REST API Server** (`RestApiServer`, EP-043) — confirmed, by
  its own construction-site docstring (`_build_rest_api_server`,
  quoted verbatim): *"RestApiServer is Jarvis's first component that
  binds and listens on a real network socket as a side effect of
  `initialize()`."* Built on `ThreadingHTTPServer` (confirmed,
  `rest_api_server.py` line 73/396) — i.e., **already a real,
  concurrent, multi-threaded network server**, auto-started
  (`server.start()` called unconditionally once `api.enabled` is
  true, `api.enabled` defaulting to `false`) as a side effect of
  `Bootstrap.initialize()`, running on its own thread(s) alongside the
  Shell for the remainder of the process's life.
- **`BackgroundWorkerService`/`BackgroundWorkerPool`** (EP-036) — a
  pool of `worker_count` daemon threads (default confirmed in
  `config/config.yaml`), started immediately upon construction
  (`BackgroundWorkerPool.__init__` starts its threads directly,
  confirmed by direct reading), running for the process's life
  whenever `background_workers.enabled` is true (default `true`).
  **This pool is deliberately, tightly coupled to `WorkflowEngine.run(workflow_id)`
  only** (confirmed: `BackgroundWorkerPool.__init__(self, workflow_engine:
  WorkflowEngine, ...)`, `submit(self, workflow_id: str) -> str`) — it
  is not a general-purpose task runner, and this document does not
  propose making it one (Section 5, Candidate D, rejected).
- **The Telegram bot gateway** (`TelegramService`/`TelegramClient`,
  reached through `TelegramRouter` wrapping the same `CommandRouter`)
  — confirmed present, but confirmed **not** auto-started as a side
  effect of `initialize()` the way `RestApiServer` is (no
  `telegram_service.start()`/equivalent call in the `initialize()`
  sequence; `telegram.auto_start` exists in every EP's own full
  bootstrap test-config fixture and defaults to `false`) — it requires
  an explicit action to begin listening for incoming messages.
- **The Scheduler** (`SchedulerService`/`Scheduler`, `EP-011`) —
  registered with a set of default jobs at construction, but (like
  Telegram) confirmed not auto-started as a side effect of
  `initialize()` (no unconditional `.start()`/tick-loop-launch call in
  the sequence this document read).

**This is the closest thing to "distributed" that genuinely exists in
this repository today: a single logical Jarvis "brain" (one
`CommandRouter`, one set of Services) already reachable from, and
already running, multiple concurrent execution contexts — but all
within one OS process, on one machine, sharing one Python interpreter
and its GIL.** No inter-process, inter-machine, or inter-instance
communication exists anywhere.

### 3.3 No unified view of "what is this Jarvis instance's runtime doing right now"

Confirmed by exhaustive search (`grep -rn "class.*Module\b"
src/modules/*.py` → 33 `CommandModule`s; 25 of them already register
their own `"status"` action): every subsystem reports its own status
in isolation. `Orchestrator` (`src/core/orchestrator.py`) tracks
loaded skills and its own `is_running()` flag — it has no knowledge
of `RestApiServer`, `BackgroundWorkerService`, or the Shell at all
(confirmed by its own, complete public method list:
`load_skills`/`_discover_skills`/`start`/`stop`/`is_running`/`skills`).
**`Bootstrap` itself is the only object in the process that holds a
reference to every one of Section 3.2's concurrent execution
contexts** (each already exposed as its own `None`-able public
property: `bootstrap.rest_api_server`, `bootstrap.background_worker_service`,
`bootstrap.shell`, confirmed present and unmodified) — but nothing
today aggregates them into one report.

### 3.4 File-backed persistence exists, but is not designed for concurrent multi-writer access

`MemoryService` (`memory.persistent`), `ConversationManager`
(`conversation.storage_file`), and Long-Term Memory each read/write a
single JSON file on disk, guarded by an in-process `threading.Lock`
(confirmed for `MemoryStore`, `EP057_ARCHITECTURE_AUDIT.md` Section
3.1's own prior finding, unchanged). **These locks protect against
concurrent *threads within one process* — they provide no protection
against two separate OS processes writing the same file
concurrently** (no file locking, no atomic-rename-on-write pattern,
no version/conflict detection was found anywhere in
`memory_persistence.py`/`conversation_manager.py`). This is a real,
concrete constraint any candidate proposing multiple, cooperating
Jarvis *processes* sharing state would have to confront — and none
of this repository's existing code has ever needed to, since no such
multi-process scenario exists today (Section 3.1).

### 3.5 `ProcessRegistry` naming precedent — two, unrelated, already-disambiguated packages

`src/core/execution/process_registry.py` (tracks raw OS subprocess
handles Jarvis itself launches, e.g. for desktop automation) and
`src/core/processes/process_registry.py` (EP-008's own catalog of
named, logical processes with restart policies) are two, already
explicitly disambiguated (by the second file's own docstring,
Section 3 confirms), unrelated packages — **neither tracks or
registers separate Jarvis *instances*.** A candidate reusing the word
"registry" for a new, EP-059-specific concept must not collide with
either name or its established meaning (Section 6.1).

### 3.6 The `EventBus` (EP-037) is already used for cross-subsystem, in-process notification — and is already the pattern `BackgroundWorkerPool` itself uses to publish task-completion events

`src/core/events.py`'s `EventBus` is confirmed, via direct reading of
`src/bootstrap.py` lines ~1370–1405, to already carry
`"background_worker.task_completed"`/`"background_worker.task_failed"`
events from `BackgroundWorkerPool` to at least one other subscriber
wired at the Bootstrap level — i.e., **this repository already has
an established, working, in-process publish/subscribe mechanism for
"something happened in one execution context, another part of the
process should know about it."** It is explicitly, and confirmed,
in-process only (no network transport, no cross-process delivery of
any kind exists in `events.py`, confirmed by its own module contents).

### 3.7 `CommandRouter` / `CommandModule` precedent — confirmed still current

Every skill, including `PlanningModule`/`ContextCompressionModule`/
`BackgroundWorkerModule`/every other module referenced above, is a
`CommandModule` registered with the unmodified `CommandRouter.dispatch()`.
Any new, EP-059-facing CLI surface should follow this same,
established pattern (Section 6.4) unless a specific reason exists not
to.

---

## 4. Existing infrastructure reuse (what this document will and will not touch)

**Reusable, unmodified, as-is:**

- `Bootstrap`'s own, already-existing public properties
  (`rest_api_server`, `background_worker_service`, `shell`, and
  others already confirmed present) — the *only* way this document's
  recommended candidate reads the runtime's current shape; no new
  Bootstrap-internal state is invented.
- `RestApiServer.is_running()`/`.host`/`.port` (EP-043, unmodified).
- `BackgroundWorkerService.status()` → `BackgroundWorkerStatus`
  (EP-036, unmodified) — already reports `enabled`/`running`/
  `worker_count`/`task_count`.
- `SchedulerService.status()` → `SchedulerStatus` (EP-011, unmodified,
  confirmed present).
- The `CommandRouter`/`CommandModule` pattern (unmodified) — for any
  new CLI surface.
- Standard library `os.getpid()`/`time.monotonic()` — for basic
  process-identity/uptime reporting, requiring no new dependency.

**Explicitly not reused, and not proposed to be built:** any
networking, discovery, consensus, or multi-process coordination
primitive — none exists in this repository today (Section 3.1/3.4),
and Section 5 explains why inventing one from nothing is rejected for
v1.

---

## 5. Candidate approaches

### Candidate A — A read-only "Runtime" introspection surface over Jarvis's already-existing concurrent execution contexts (recommended)

Add a new, small `RuntimeService`
(`src/services/runtime_service.py`) that is handed already-built
references to whichever of Section 3.2's execution contexts exist
this run (`rest_api_server`, `background_worker_service`, `shell`,
and — narrowly — a process-identity/uptime snapshot via the standard
library) and produces one aggregated `RuntimeStatus` snapshot: which
execution contexts are active, basic identifying facts about each
(REST API host/port if running; worker count/task count if running;
whether the Shell is the current foreground loop), and the process's
own PID and uptime. Exposed via one new `CommandModule`
(`RuntimeModule`, a new `"runtime"` CLI namespace: `runtime status`/
`runtime help`) and, since `RestApiServer`'s own `ApiRouter` already
forwards arbitrary `CommandRouter` dispatches unchanged (confirmed,
Section 6.6), automatically reachable over the REST API too, with
zero REST-layer-specific code.

**Why recommended:** (1) it is the only candidate that reuses
*exclusively* already-built, already-tested components, through
their existing public, `None`-checked properties/methods — zero new
execution, networking, or coordination logic of any kind. (2) It
directly answers Section 1's derived problem (no unified runtime view
exists today) without requiring this document to invent a
specification for a problem the repository gives no evidence anyone
has actually posed. (3) It carries the smallest possible risk
profile of any interpretation of "Distributed Runtime" this document
could propose: read-only, no state mutation, no new failure mode
introduced into `Bootstrap.initialize()`'s own sequence (Section 4's
"minimal file scope"/"minimal duplication" criteria, weighted
explicitly by this task's own instructions). (4) It is honestly
scoped: this document does not claim Candidate A makes Jarvis
"distributed" in the multi-machine sense — it names, precisely, what
it does (formalizes and exposes the already-existing multi-execution-
context architecture) and defers the harder, genuinely-distributed
questions (Candidates B/C) to a future EP with actual repository
evidence to ground them, exactly as `EP057_DESIGN.md`'s own rejected
Candidates and `EP058_DESIGN.md`'s own rejected Candidate D were each
deferred rather than invented from nothing.

### Candidate B — Multi-process horizontal scaling of the REST API server (rejected for v1)

Spawn `N` OS processes, each running its own `Bootstrap`/`RestApiServer`
pair bound to different ports (or sharing one port via
`SO_REUSEPORT`), for genuine multi-process, multi-core concurrency.
**This document does not recommend this candidate for v1:** (1) no
precedent exists anywhere in this repository for spawning a second
Jarvis process (Section 3.1) — this would be entirely new
infrastructure, not an extension of anything that exists. (2) Section
3.4's finding is directly disqualifying for any interpretation that
assumes shared state: `MemoryService`/`ConversationManager`'s
file-backed persistence has no multi-process-safe locking of any
kind, so `N` independent processes would either corrupt shared state
files or silently diverge into `N` inconsistent copies of "the same"
Jarvis — a data-integrity risk this document is not in a position to
resolve without a substantially larger, separately-scoped storage
redesign. (3) It introduces real new operational complexity (process
supervision, port allocation, health-checking a process from another
process) with zero existing precedent to reuse.

### Candidate C — A multi-instance registry/discovery mechanism (rejected for v1)

A lightweight, `ProcessRegistry`-style catalog letting independently-
running Jarvis instances (same machine or across a network) register
themselves and discover/query each other via the already-existing
REST API. **This document does not recommend this candidate:** it
requires inventing a registration/discovery/heartbeat protocol this
repository has zero prior art for (unlike Section 3.5's two
`ProcessRegistry` packages, which track subprocesses/logical jobs
*within* one Jarvis instance, not separate Jarvis instances). It also
meaningfully widens Jarvis's network attack surface (any registered
peer could, in principle, be queried or could query others) — a
security posture change this document has no repository-grounded
basis to scope safely. Matches the same "invent a protocol from
nothing" rejection reasoning `EP057_DESIGN.md`'s Candidate D and
`EP058_DESIGN.md`'s Candidate D each already established for this
project.

### Candidate D — Generalize `BackgroundWorkerPool` into an arbitrary, `CommandRouter`-dispatching task queue (rejected for v1, but the second-most-grounded)

Widen EP-036's existing worker-thread pool so any subsystem, not only
`WorkflowEngine`, can submit background work. **This document does
not recommend this candidate:** `BackgroundWorkerPool`'s constructor
and `submit()` signature are deliberately, tightly coupled to a
concrete `WorkflowEngine`/`workflow_id` (Section 3.2, confirmed by
direct reading) — genuinely widening it would require either
modifying EP-036's own core file (against this project's own,
repeatedly-applied "treat completed EPs' core files as fixed"
precedent) or duplicating its entire thread-pool/task-status-tracking
logic in a new, parallel class (directly against this task's own
"minimal duplication" evaluation criterion). Recorded as the
second-most-grounded candidate, and a plausible, separately-scoped
future direction (very possibly relevant to EP-060's own "Jarvis
Operating System" capstone), but not a clean v1 fit under this
document's own evaluation criteria.

---

## 6. Recommended approach

**Candidate A**, per Section 5's reasoning. Everything in Sections
6.1–11 is provisional, written against Candidate A, and not
authorized until Owner Decision D1 (Section 15) is explicitly
approved.

### 6.1 Naming (Owner Decision D2)

This document recommends the CLI namespace `runtime` (`RuntimeModule`,
`RuntimeService`, `RuntimeStatus`) — confirmed to collide with no
existing `CommandRouter` namespace, class name, or module name
anywhere in `src/` (`grep -rln "class Runtime" src/` returns no match
today). This avoids the two, already-established, unrelated
`ProcessRegistry` names (Section 3.5) and the already-taken
`Orchestrator`/`Scheduler` names, none of which describe this
document's actual scope (a cross-cutting status *view*, not a new
execution or scheduling engine).

### 6.2 `RuntimeService` — provisional interface

```text
class RuntimeService:
    def __init__(
        self,
        started_at: float,
        rest_api_server: RestApiServer | None,
        background_worker_service: BackgroundWorkerService | None,
        shell: InteractiveShell | None,
    ) -> None: ...

    def status(self) -> RuntimeStatus: ...
```

`RuntimeStatus` (a new, plain, frozen dataclass in a new
`src/core/runtime/runtime_result.py`-equivalent module, or inline in
`runtime_service.py` if small enough to avoid a needless extra file
— Owner Decision D3) carries: `pid: int`, `uptime_seconds: float`,
`shell_active: bool`, `api_active: bool`, `api_host: str | None`,
`api_port: int | None`, `background_workers_active: bool`,
`background_worker_count: int`, `background_worker_task_count: int`.
Every field is derived by calling an already-existing, unmodified
public method/property on an already-constructed object
(`RestApiServer.is_running()`/`.host`/`.port`,
`BackgroundWorkerService.status()`) — `RuntimeService` performs no
computation of its own beyond assembling these already-real facts
into one shape, and never starts, stops, or reconfigures any
component it reports on (read-only, matching this document's own
"minimal risk" framing, Section 5).

### 6.3 `RuntimeModule` — provisional CLI surface

| Action | Description |
|---|---|
| `runtime help` | Lists `runtime status`. |
| `runtime status` | Formats `RuntimeService.status()`'s `RuntimeStatus` for the shell — process PID/uptime, which execution contexts are active, and each active context's own already-existing summary facts. |

No `runtime start`/`stop`/`register` action of any kind — this
document's recommended scope is strictly read-only introspection,
never control (Section 5's own risk-minimization reasoning).

### 6.4 Integration points

- `Bootstrap` (`src/bootstrap.py`) — additive only: construct one
  `RuntimeService(...)` after every other subsystem it reports on has
  already been constructed (so a `None` reference correctly reflects
  "this run didn't build/enable that subsystem," never a
  not-yet-constructed one), and register `RuntimeModule(runtime_service)`
  with the already-existing, unmodified `CommandRouter`. No
  construction-ordering change to any existing subsystem.
- `RestApiServer.is_running()`/`.host`/`.port` (EP-043, unmodified) —
  read-only.
- `BackgroundWorkerService.status()` (EP-036, unmodified) —
  read-only.
- **No** integration with `AgentEngine`, `PlanningEngine`,
  `PlanExecutionEngine`, `ToolEngine`, `WorkflowEngine`,
  `SchedulerService`, `TelegramService`, `DiscordService`, or
  `EventBus` in v1 — Owner Decision D4 (Section 15) asks whether the
  owner wants `Scheduler`/`Telegram` status folded in at v1 or
  deferred, since neither auto-starts (Section 3.2) and their
  inclusion would change `RuntimeService`'s constructor surface.
- **No** network-layer-specific code for REST reachability — since
  `ApiRouter` (EP-043) already forwards any `CommandRouter`-registered
  command unchanged (confirmed by direct reading of
  `src/core/api/rest_api_server.py`'s `ApiRouter`, which dispatches by
  namespace/action exactly as `InteractiveShell`/`TelegramRouter`
  already do), `runtime status` becomes reachable over HTTP the
  moment `RuntimeModule` is registered, with zero REST-specific code
  written for it.

---

## 7. Architecture / data flow

```text
Bootstrap.initialize()
  |
  |-- constructs RestApiServer (if api.enabled)        [existing, EP-043]
  |-- constructs BackgroundWorkerService (if enabled)  [existing, EP-036]
  |-- constructs InteractiveShell                       [existing]
  |
  '-- (new, additive) constructs RuntimeService(
          started_at=<captured at Bootstrap construction time>,
          rest_api_server=self._rest_api_server,
          background_worker_service=self._background_worker_service,
          shell=self._shell,
      )
      '-- registers RuntimeModule(runtime_service) with CommandRouter

Caller (any of the three already-existing dispatch paths, unchanged):
  InteractiveShell            -> CommandRouter.dispatch("runtime status")
  RestApiServer -> ApiRouter  -> CommandRouter.dispatch("runtime status")
  TelegramRouter (if started) -> CommandRouter.dispatch("runtime status")
      |
      v
  RuntimeModule.execute("status", [])
      |
      v
  RuntimeService.status()
      |-- rest_api_server.is_running() / .host / .port   (read-only)
      |-- background_worker_service.status()             (read-only)
      |-- os.getpid() / time.monotonic() - started_at     (stdlib only)
      v
  RuntimeStatus  ->  CommandResult(success=True, message=<formatted>)
```

No new arrows exist beyond "one more `CommandModule` dispatched the
same way every other one already is" and "one more Service reading
already-public facts from already-constructed objects." Nothing in
this diagram introduces a new thread, a new socket, a new file, or a
new process.

---

## 8. Detailed implementation plan (provisional, contingent on D1)

1. Create `src/services/runtime_service.py`: `RuntimeStatus`
   (frozen dataclass), `RuntimeService` (constructor + `status()`),
   following the exact docstring/type-hint/error-handling conventions
   `EP057_DESIGN.md`/`EP058_DESIGN.md`'s own recommended Candidate A
   sections already established for this project's Service layer.
2. Create `src/modules/runtime_module.py`: `RuntimeModule` — `help`/
   `status` actions only, formatting `RuntimeStatus` into a
   `CommandResult`, mirroring `PlanningModule`/`ContextCompressionModule`'s
   own existing `_status()` formatting style.
3. Modify `src/bootstrap.py`: one new import block, one new
   `RuntimeService(...)` construction (placed after
   `_rest_api_server`/`_background_worker_service`/`_shell` are all
   already assigned, so no ordering hazard exists), one new
   `router.register(RuntimeModule(runtime_service))` call, and one
   new, `None`-defaulted `self._runtime_service` instance attribute
   plus its own public `runtime_service` property, mirroring every
   other subsystem's existing property pattern exactly. No existing
   construction site, ordering, or registration call is touched.
   **Construction-ordering clarification (approved documentation
   update):** `_background_worker_service` is assigned inside
   `_build_command_router()` (called from `initialize()` before
   `_shell`/`_rest_api_server` are constructed), not afterward --
   `RuntimeService` must therefore be constructed only once
   `_build_command_router()` has already returned and
   `_shell`/`_rest_api_server` have also already been assigned (i.e.,
   at the end of `initialize()`, not anywhere inside
   `_build_command_router()` itself). This guarantees `RuntimeService`
   is handed the same, final, live `background_worker_service`
   reference `Bootstrap.background_worker_service` itself exposes,
   never an early or stale `None` captured before that subsystem's own
   construction attempt (successful or not) has completed.
4. Modify `src/modules/test_module.py`: one new import line
   registering the new EP-059 test suite, exactly matching the
   one-line pattern every prior EP already established.
5. Create `tests/EP059/__init__.py`, `tests/EP059/test_runtime.py`
   (Section 9).

No other file is touched (Section 10).

---

## 9. Testing strategy

Mirrors the now-five-times-established convention
(`EP054_DESIGN.md`–`EP058_DESIGN.md` Section 12/testing sections):

- **`tests/EP059/test_runtime.py`** (primary, always-run suite):
  - `RuntimeService.status()` with every dependency `None` (no REST
    API, no background workers, no shell reference) — confirms a
    clean, all-`False`/zero snapshot, never a crash.
  - `RuntimeService.status()` with a real, unmodified `RestApiServer`
    bound to an ephemeral local port and a real, unmodified
    `BackgroundWorkerService` backed by a real `WorkflowEngine` (both
    already-existing, already-tested components — never faked, since
    neither makes any external network call beyond binding a
    loopback socket) — confirms `api_active`/`api_host`/`api_port`
    and `background_workers_active`/`background_worker_count`/
    `background_worker_task_count` are populated correctly, then
    confirms both are cleanly torn down (`server.stop()`/
    `service.shutdown()`) at the end of the test.
  - `pid`/`uptime_seconds` sanity checks (`pid == os.getpid()`;
    `uptime_seconds >= 0` and increases across two calls separated by
    a short, real sleep).
  - `RuntimeModule` CLI-layer tests: `runtime help` lists `runtime
    status`; `runtime status` with arguments is either ignored or
    rejected with a clear usage message (Owner Decision D5); output
    formatting contains the expected labels.
  - `CommandRouter` dispatch-equivalence test, mirroring every prior
    EP's own identical test.
  - **Real, enabled `Bootstrap` test:** a full `Bootstrap.initialize()`
    run (mirroring `EP057_ARCHITECTURE_AUDIT.md`/`EP058_ARCHITECTURE_AUDIT.md`'s
    own "real object graph, not a fake" precedent) confirming
    `bootstrap.runtime_service` is constructed, `RuntimeModule` is
    registered under `"runtime"`, and `runtime status` dispatches
    successfully through the real `CommandRouter` — proving the
    Bootstrap wiring genuinely works end to end, not merely at the
    unit level.
  - Regression guard: confirm `api status`/`worker status`
    (already-existing, unmodified actions) are completely unaffected
    by `RuntimeModule`'s own, separate registration.
- **Regression:** `tests/EP043` (REST API Server) and `tests/EP036`
  (Background Worker Pool/Service/Module) re-run to confirm zero
  change to either subsystem's own behavior.

---

## 10. File-scope matrix (provisional — NOT authorized until D1 is approved)

### CREATE

- `src/services/runtime_service.py` — `RuntimeStatus`, `RuntimeService`.
- `src/modules/runtime_module.py` — `RuntimeModule`.
- `tests/EP059/__init__.py`, `tests/EP059/test_runtime.py`.

### MODIFY

- `src/bootstrap.py` — additive only: one new import block, one new
  `self._runtime_service` attribute + public property, one new
  `RuntimeService(...)` construction placed after every dependency it
  reads has already been assigned, and one new
  `router.register(RuntimeModule(...))` call. No existing
  construction, ordering, or registration call for any other
  subsystem is touched.
- `src/modules/test_module.py` — additive only: one new import line.

### DO NOT MODIFY

- `src/core/api/rest_api_server.py`, `src/services/`-layer code for
  the REST API (if any beyond the module itself) — **zero changes**;
  `is_running()`/`.host`/`.port` are called, never modified.
- `src/core/background_workers/`, `src/services/background_worker_service.py`,
  `src/modules/background_worker_module.py` — **zero changes**;
  `status()` is called, never modified. Candidate D (Section 5),
  which would require modifying `background_worker_pool.py`, is
  explicitly rejected for v1.
- `src/core/agent/`, `src/core/planning/`, `src/core/plan_execution/`,
  `src/core/tool/`, `src/core/collaboration/`, `src/core/workflow_engine/`,
  `src/core/workflow_scheduler/`, `src/core/automation_engine/`
  (EP-028–035) — **zero changes**; none is touched or called by this
  candidate at all.
- `src/core/scheduler.py`, `src/services/scheduler_service.py`,
  `src/modules/scheduler_module.py` (EP-011) — **zero changes** in
  v1's default scope (Owner Decision D4 may widen this).
- `src/core/telegram/`, `src/services/telegram_service.py`,
  `src/modules/telegram_module.py` — **zero changes** in v1's default
  scope (Owner Decision D4 may widen this).
- `src/core/memory/`, `src/core/ai/conversation.py`,
  `conversation_manager.py`, and every other file-backed persistence
  component named in Section 3.4 — **zero changes**; this document
  explicitly does not attempt to make any of them multi-process-safe
  (that is Candidate B's own, rejected territory).
- `src/core/command_router.py`, `src/core/orchestrator.py`,
  `src/core/events.py` — zero changes; the existing dispatch and
  event mechanisms are used exactly as they already exist, never
  modified.
- `config/config.yaml` — **zero changes anticipated**; `RuntimeService`
  reads no configuration of its own in v1 (Owner Decision D6 covers
  the one plausible exception, a `runtime.enabled` gate).
- Every EP-001…EP-058 design/audit document and every other prior
  EP's source/test files, and `JARVIS_ROADMAP.md`/`BACKLOG.md`/
  `CHANGELOG.md`/`RELEASE_NOTES.md` (STEP 1 does not update
  documentation, per this task's own instruction).

---

## 11. Risks / edge cases

- **Risk: this document's own honest disclosure (Section 0/2) that no
  specific textual anchor exists means Owner Decision D1 carries more
  weight than any prior EP's own D1** — if the owner's actual intent
  for "Distributed Runtime" is closer to Candidate B or C, this
  document's entire Sections 6–10 are void and a substantially
  different, larger design would be needed. This risk is disclosed,
  not hidden, precisely so the owner can redirect before any code is
  written.
- **Edge case: `Bootstrap.initialize()` called more than once, or a
  test constructs `Bootstrap` without calling `run()`/`shutdown()`**
  (confirmed, Section 3.2's own quoted docstring, to be a real,
  existing pattern many EP-001–042 tests already rely on) —
  `RuntimeService`'s `started_at` must be captured once, at
  `Bootstrap.__init__()` or at the start of `initialize()` (not
  re-captured on a second `initialize()` call), so `uptime_seconds`
  behaves sensibly; this is a construction-ordering detail STEP 2
  must get right, not a design ambiguity.
- **Edge case: every dependency is `None`** (e.g., `api.enabled:
  false` and `background_workers.enabled: false`, both plausible,
  independently-configured states) — `RuntimeStatus` must still
  report a valid, all-`False`/zero snapshot, never raise (Section 9's
  first test case covers this explicitly).
- **Edge case: a REST client calls `runtime status` over HTTP while
  the REST API server itself is one of the things being reported on**
  — `is_running()` will correctly report `True` in this case (the
  server answering the request is, by definition, running); no
  special-casing is needed or proposed.
- **Risk: scope creep toward "control," not "introspection."** This
  document deliberately does not propose `runtime restart`/`shutdown`/
  any mutating action — Owner Decision D5 exists specifically so the
  owner can explicitly widen this if desired, rather than this
  document silently assuming it.

---

## 12. Configuration considerations

**No new configuration key is proposed for v1** — `RuntimeService`
reads no `runtime.*` section at all; it is constructed unconditionally
whenever `Bootstrap.initialize()` runs, since it performs no I/O of
its own and has nothing to gate (unlike every prior EP's own Candidate
A, none of which needed a network socket, an AI-provider call, or a
thread pool). Owner Decision D6 (Section 15) exists in case the owner
prefers an explicit `runtime.enabled` flag anyway, for consistency
with every other subsystem's own gating convention, even though
nothing here has a cost or risk to gate against.

---

## 13. Command/API surface

As established in Section 6.3/6.4: one new CLI namespace (`runtime`,
two actions: `help`/`status`), automatically reachable over the
already-existing REST API with zero REST-specific code, since
`ApiRouter` already forwards any registered `CommandRouter` action
unchanged.

---

## 14. Security and privacy considerations

- **No new AI-provider call, no new network client, no new
  credential handling of any kind** — `RuntimeService` only reads
  already-public facts from already-constructed, already-trusted,
  in-process objects.
- **Information disclosure, considered explicitly:** `runtime status`
  discloses the REST API's own configured host/port (already
  disclosed today by `api status`, confirmed present) and the
  background worker pool's configured size/task count (already
  disclosed today by `worker status`, confirmed present) — this
  document's own aggregation discloses **nothing that isn't already
  independently disclosed today**, by design (Section 6.2 pulls only
  from already-existing, already-public status methods).
- **No control surface** — read-only in v1 (Section 6.3), so no new
  way to stop, start, or reconfigure any subsystem is introduced.
- **Pre-existing REST API authentication characteristic (approved
  documentation update):** the REST API Server (EP-043) has no
  authentication or authorization layer of any kind today, for any
  command reachable through it — this is a pre-existing characteristic
  of `RestApiServer`/`ApiRouter`, not something EP-059 introduces,
  changes, or regresses. Because `runtime status` becomes reachable
  over HTTP the moment `RuntimeModule` is registered (Section 6.4),
  it inherits this same, already-existing lack of authentication,
  exactly as `api status`/`worker status` already do today. This
  document does not propose adding authentication (out of scope for
  EP-059), and the information `runtime status` discloses is,
  per the point above, already independently disclosed today by
  those existing commands.

---

## 15. Owner Decisions

None of the decisions below is yet approved. Sections 6–13's
provisional architecture is **not** authorized for STEP 2 until D1 is
approved (and D2–D6, where applicable, are resolved).

### D1 — What does "Distributed Runtime" concretely mean for v1? (primary, definitional decision)

**Question:** Given Section 2's finding that no existing file names a
specific mechanism, which of Section 5's candidate interpretations
(or an owner-supplied alternative not considered here) should EP-059
v1 actually build?
**Options:** (a) Candidate A — a new, read-only `RuntimeService`/
`RuntimeModule` introspection surface over Jarvis's already-existing
concurrent execution contexts (recommended); (b) Candidate B —
multi-process horizontal scaling of the REST API server (not
recommended — no precedent, and Section 3.4's file-backed-persistence
finding makes shared state genuinely unsafe without a separately-
scoped storage redesign); (c) Candidate C — a multi-instance registry/
discovery mechanism (not recommended — requires inventing a new
network protocol and widens the attack surface with no repository
precedent); (d) Candidate D — generalize `BackgroundWorkerPool` into
an arbitrary task queue (not recommended for v1 — would require
either modifying an already-complete EP-036 core file or duplicating
its logic, though flagged as a plausible, separately-scoped future
direction, possibly relevant to EP-060); (e) an owner-supplied
alternative, in which case this entire document would need to be
revised before STEP 2.
**Recommended option:** (a).
**Technical reasoning:** (a) is the only candidate built entirely
from already-existing, already-tested, already-public components,
with zero new execution, networking, or coordination logic — the
smallest possible risk and file-scope footprint of the four, matching
this task's own stated evaluation criteria (reuse, minimal
duplication, minimal file scope) more directly than any alternative.
**Security impact:** (a) discloses nothing not already independently
disclosed today (Section 14); (b) and (c) each introduce a materially
new network/process attack surface this document has no
repository-grounded basis to scope safely.
**Compatibility impact:** (a) is fully additive; (b) risks data
corruption across independently-writing processes (Section 3.4); (c)
is unscoped until its own protocol is designed; (d) modifies or
duplicates EP-036.
**What changes in STEP 2:** (a) → build exactly Section 10's file
scope. (b)/(c)/(d) → this document would need a full revision scoping
a substantially larger, differently-shaped design before STEP 2 could
begin.

### D2 — CLI namespace name

**Question:** Is `runtime` (Section 6.1) an acceptable namespace, or
does the owner prefer an alternative (e.g. `system`, `instance`)?
**Options:** (a) `runtime` (as proposed, confirmed collision-free);
(b) an owner-specified alternative.
**Recommended option:** (a).
**What changes in STEP 2:** (b) → rename `RuntimeModule`/
`RuntimeService`/the CLI namespace throughout Sections 6–10
consistently.

### D3 — Where `RuntimeStatus` lives

**Question:** Should `RuntimeStatus` be a small, inline dataclass
inside `runtime_service.py` (as most recently-added Services in this
project keep their own result dataclasses, e.g. `QueryOutcome` in
EP-057's `context_compression_service.py`), or should it live in its
own `src/core/runtime/`-style module, mirroring the heavier
Engine/Manager/Provider packages (EP-028 onward)?
**Options:** (a) inline in `runtime_service.py`, no new package
(simplest, smallest file-scope footprint, matches EP-057's own
precedent for a single, small result type); (b) a new
`src/core/runtime/` package with its own `__init__.py`/result module,
matching the heavier Engine-family convention.
**Recommended option:** (a) — `RuntimeService` introspects; it does
not own an Engine/Manager/Provider hierarchy of its own, so the
heavier package structure would be disproportionate to its actual
scope (two read-only methods' worth of logic).
**What changes in STEP 2:** (a) → `RuntimeStatus` defined in
`runtime_service.py` itself, no new package. (b) → Section 10's file
scope gains a new `src/core/runtime/` directory.

### D4 — Should `Scheduler`/`Telegram` status be included in v1's snapshot?

**Question:** Section 6.4 scopes v1 to only the two execution
contexts that are *auto-started* as a side effect of `initialize()`
(REST API Server, Background Worker Pool) plus the always-present
Shell reference. `SchedulerService`/`TelegramService` exist but are
not auto-started (Section 3.2) — should their status be folded into
`RuntimeStatus` anyway, given they are still additional execution
contexts once explicitly started?
**Options:** (a) v1 scope as proposed — REST API + Background Workers
+ Shell only (simplest, matches the "auto-started as a side effect of
initialize()" framing precisely); (b) widen `RuntimeService`'s
constructor to also accept `scheduler_service`/`telegram_service`
and report their status too, regardless of auto-start behavior.
**Recommended option:** (a) — for v1, matching the narrowest, most
defensible reading of "what is this process's runtime doing right
now without any further operator action," and keeping the initial
file scope and constructor surface minimal; (b) is a natural,
low-risk future widening this design does not foreclose.
**What changes in STEP 2:** (a) → `RuntimeService.__init__()` takes
exactly the three parameters in Section 6.2. (b) → two more,
`None`-able constructor parameters and two more `RuntimeStatus`
fields, each read through `SchedulerService.status()`/
`TelegramService`'s own already-existing status-equivalent (to be
confirmed present before committing to this option).

### D5 — Read-only in v1, or include a control action?

**Question:** Section 6.3/11 deliberately propose no mutating
`runtime` action (no restart/shutdown/reconfigure). Does the owner
want any such action considered for v1, or confirm read-only-only
scope?
**Options:** (a) read-only only, as proposed (`help`/`status`); (b)
add a scoped control action (e.g. `runtime shutdown`, forwarding to
`Bootstrap.shutdown()`).
**Recommended option:** (a) — matches this document's own explicit
risk-minimization framing (Section 5/11); a shutdown-triggering
command reachable over the REST API in particular would be a
materially different security posture this document has not
attempted to scope.
**What changes in STEP 2:** (a) → exactly Section 6.3's two actions.
(b) → a new action, its own error handling, and a dedicated security
review this document does not currently include.

### D6 — Explicit `runtime.enabled` configuration gate, or unconditional construction?

**Question:** Section 12 notes `RuntimeService` has no cost or risk
to gate against, unlike every prior subsystem's own `<name>.enabled`
key. Should EP-059 still add one, purely for convention-consistency
with every other subsystem in this project?
**Options:** (a) no new configuration key — construct unconditionally
(as proposed, simplest); (b) add `runtime.enabled` (default `true`),
matching every other subsystem's own gating convention even though
nothing here needs to be disabled for cost/risk reasons.
**Recommended option:** (a) — introducing a config key with no
behavioral reason to ever be set to `false` adds surface area without
benefit; a future EP that adds a genuinely gate-worthy `runtime.*`
capability (e.g., Owner Decision D5's control action, if approved
later) can introduce the key at that point.
**What changes in STEP 2:** (a) → no `config/config.yaml` change at
all. (b) → one new, two-line `config/config.yaml` addition and a
`bool(config.get("runtime.enabled", True))` check at the construction
site, mirroring every other subsystem's own convention.
