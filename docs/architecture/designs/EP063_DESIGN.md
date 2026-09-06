# EP-063 — WorkflowSchedulerService Shutdown Coordination

STEP 1: Architecture Discovery & Design

Status: DESIGN PROPOSED — awaiting Owner Decision approval before STEP 2

---

## 0. How this scope was derived

`docs/architecture/JARVIS_ROADMAP.md` and `docs/BACKLOG.md` both state,
verbatim, **"No EP-063 or Phase 11 exists anywhere in this
repository"** as of the current release, and both entries for EP-062
say "Next Engineering Package: none yet defined." A full-text search
of `EP061_DESIGN.md`, `EP062_DESIGN.md`, and both EPs'
`docs/architecture/audits/*_ARCHITECTURE_AUDIT.md` files for "next
EP", "future EP", "EP-063", and "separately-scoped" turns up only
generic forward-looking caveats, never a named EP-063 candidate. Per
this task's own instructions, EP-063's scope must therefore be derived
from the repository's actual code and documentation, exactly as
EP-061 and EP-062 each had to do for themselves.

EP-061 and EP-062 both found their scope the same way: a still-open,
code-verified gap disclosed (directly or by clear structural analogy)
by an earlier EP, left untouched by every EP since. This STEP 1
followed the same method and, after ruling out several closer, more
obvious candidates (documented below), found one:
**`WorkflowSchedulerService` (EP-034) has the exact same "no public
shutdown for an auto-started background thread" defect that
`SchedulerService` (EP-011) had before EP-061 fixed it** — and it was
never noticed by EP-059 through EP-062 because every one of those
documents treats `src/core/workflow_scheduler/`,
`WorkflowSchedulerService`, and `workflow_scheduler_module.py` purely
as an unrelated "DO NOT MODIFY" subsystem (confirmed: `EP059_DESIGN.md`
Section 10 "DO NOT MODIFY" list; `EP060_DESIGN.md`, `EP061_DESIGN.md`
neither name nor inspect it at all — confirmed by grep, zero
substantive hits beyond `EP060_DESIGN.md`'s own testing-strategy
footnote distinguishing `tests/EP034/test_workflow_scheduler.py` from
`SchedulerService`'s own, separate test gap).

### 0.1 Candidates considered and rejected

- **Architecture Debt items** (`docs/architecture/ARCHITECTURE_DEBT.md`,
  AD-005 through AD-009) — explicitly barred from being fixed inside a
  normal Engineering Package by that document's own stated rule
  ("Never fix Architecture Debt during a normal Engineering Phase...
  addressed only during a dedicated cleanup milestone"). None of them
  concerns `WorkflowSchedulerService`'s shutdown lifecycle in any case
  (AD-001/AD-002 concern its config-validation and an unrelated
  unreachable exception handler in `Bootstrap`; both untouched by this
  design).
- **Telegram Gateway (`TelegramService`, EP-012) shutdown
  coordination** — investigated at length. `TelegramService` has an
  identical shape (`_poll_thread`/`_stop_event`, auto-started when
  `telegram.enabled` and `telegram.auto_start` are both true,
  `telegram.auto_start` defaulting to `false`) and, like
  `WorkflowSchedulerService`, is entirely unreachable from `Bootstrap`
  (constructed as a local variable inside `_build_command_router`,
  registered into `TelegramModule`, never stored as a `Bootstrap`
  attribute, unlike `_scheduler_service`/`_background_worker_service`/
  `_workflow_scheduler_service`). Rejected as the *primary* EP-063
  candidate in favor of `WorkflowSchedulerService` for two concrete,
  source-verified reasons: (1) Telegram already has a manual escape
  hatch — `telegram stop` — that an operator can invoke before process
  exit, and its `TelegramClient.disconnect()` releases no OS resource
  more sensitive than an HTTPS long-poll connection; `WorkflowSchedulerService`
  has no escape hatch of any kind once its tick loop is started, short
  of killing the process. (2) `WorkflowSchedulerService` is a much
  closer structural duplicate of the exact defect EP-061 already fixed
  once (same `_stop_event`/`_tick_thread` shape, same auto-start
  gating, same missing public counterpart to `_start_tick_loop()`),
  making it the more precise "the same gap, recurring in a sibling
  subsystem" story STEP 1 is meant to find, and Telegram's own
  `TelegramService`/`TelegramModule` currently have **zero** dedicated
  test coverage anywhere in this repository (confirmed: no
  `tests/EP012/` directory exists, and no other test file references
  `TelegramService`/`TelegramModule` — grep-confirmed), which would
  make Telegram shutdown coordination a substantially larger, riskier
  STEP 2 than closing an already-well-tested subsystem's identical
  gap. Telegram's gap remains real and is noted here for the owner's
  awareness, but is explicitly **not** EP-063's scope (see Section 5).
- **REST API authentication** (referenced across `EP043_DESIGN.md`
  Section 12, `EP045_DESIGN.md` Section 9.3, `EP059_DESIGN.md` Section
  14, `EP060_DESIGN.md` Owner Decision D3) — a real, repeatedly
  disclosed, deliberately deferred gap, but architecturally enormous
  compared to every EP in this repository's history since EP-043 (it
  would touch every REST-reachable module, not one file), and every
  prior EP that touched it treated it as a permanent "not in v1"
  stance rather than a scoped, deferred-to-a-specific-next-EP item.
  Not the smallest architecturally correct scope; rejected.
- **Generalizing `BackgroundWorkerPool` into an arbitrary task queue**
  (`EP059_DESIGN.md` Section 5, Candidate D; `EP060_DESIGN.md` Section
  7, Candidate B) — explicitly "rejected for v1" twice already, and
  explicitly speculative/large in both rejections. Not evidenced as
  newly ready; rejected.
- **Reviving `EventBus`'s unused `orchestrator.started`/
  `orchestrator.stopped` hooks** (`EP060_DESIGN.md` Section 5.6) —
  `EP060_DESIGN.md` itself evaluated and rejected this as "a
  materially larger, more speculative change" than what it chose
  instead. No new evidence changes that conclusion; rejected.
- **A CLI/REST-reachable `runtime shutdown` action**
  (`EP059_DESIGN.md` Owner Decision D5; `EP060_DESIGN.md` Owner
  Decision D3) — both documents that raised this concluded it
  requires REST authentication to be solved first (see above); still
  blocked on the same prerequisite; rejected for the same reason.

This is exactly the kind of "real, code-verified gap" STEP 1 is asked
to find: a concrete architectural defect, of a kind this repository
has already named and fixed once for a sibling subsystem, verified
directly against current source rather than assumed, that has stood
unnoticed since EP-034 first introduced `WorkflowSchedulerService` and
remained untouched across five subsequent Runtime-focused EPs
(EP-059 through EP-062) that had every reason to notice it and did
not, because their own scope statements explicitly fenced this
subsystem out.

---

## 1. Problem Statement

`WorkflowSchedulerService` (`src/services/workflow_scheduler_service.py`,
EP-034) owns a background tick thread (`self._tick_thread`) that,
once started, runs for the remainder of the process's life with
**no public method anywhere in this codebase that can stop it**.

Concretely, verified directly against current source:

1. The tick thread is started exactly once, inside
   `WorkflowSchedulerService.__init__`, when
   `workflow_scheduler.enabled` and `workflow_scheduler.auto_start`
   are both true (`config/config.yaml`: `enabled: true`, `auto_start:
   false` by default — see Section 2.4 for why `auto_start: false`
   does **not** make this a non-gap, unlike Telegram's analogous
   default).
2. `WorkflowSchedulerService.start(entry_id)`/`.stop(entry_id)` toggle
   one *registered scheduled workflow entry's* `enabled` flag
   (`WorkflowSchedulerEngine.start_entry`/`stop_entry`) — neither
   touches the tick thread itself. There is no service-level
   `start()`/`stop()` overload and no `entry_id`-less variant.
3. `WorkflowSchedulerModule` (`src/modules/workflow_scheduler_module.py`,
   CLI namespace `"autoflow"`) exposes exactly `{list, status, run,
   start, stop, info, help}` — none of which reaches the tick thread
   either; `_start`/`_stop` both require and forward an `entry_id`.
4. `Bootstrap.shutdown()` → `RuntimeService.shutdown()` (EP-060,
   widened by EP-061) already coordinates an ordered, idempotent
   shutdown of the REST API Server, the Scheduler (EP-011), and the
   Background Worker Service (EP-036) — but `RuntimeService`'s
   constructor has no `workflow_scheduler_service` parameter at all,
   confirmed by reading `src/services/runtime_service.py` directly
   (Section 2.1), so `WorkflowSchedulerService` is never observed or
   stopped by this sequence.
5. `Bootstrap` already retains a stored reference to the
   `WorkflowSchedulerService` it constructs — `self.
   _workflow_scheduler_service`, with a public `workflow_scheduler_service`
   property (`src/bootstrap.py`, confirmed lines ~288 and ~2619-2629)
   — but this reference is never passed into `RuntimeService`'s
   constructor call inside `initialize()` (confirmed: that call passes
   `rest_api_server`, `background_worker_service`, `shell`, and
   `scheduler_service` only).
6. The gap is not hypothetical or confined to `RuntimeShutdownReport`
   bookkeeping: this repository's own `tests/EP034/
   test_workflow_scheduler.py` has to reach into
   `WorkflowSchedulerService`'s private internals to clean up after
   itself — `service._stop_event.set()` /
   `service._tick_thread.join(timeout=2)`, both annotated
   `# noqa: SLF001` acknowledging the private-attribute access — in
   both `_test_service_tick_loop_start_stop` and
   `_test_service_auto_start_from_config` (lines 767-793). This is the
   exact whitebox-workaround signature `EP061_DESIGN.md`'s own Section
   0 used to identify `SchedulerService`'s pre-EP-061 gap.

**Net effect:** if an operator sets `workflow_scheduler.auto_start:
true` (the only way this subsystem's entire automatic-execution
feature — its reason for existing — can ever be used, since nothing
can start the tick loop after construction either; see Section 2.3),
`Bootstrap.shutdown()` at process exit does not, and cannot, ask
`WorkflowSchedulerService` to stop. The tick thread is a daemon
thread, so this does not hang process exit, but it means: (a) a
scheduled workflow run genuinely in progress at shutdown time
(`WorkflowSchedulerEngine.tick()` → `run_now()` →
`WorkflowEngine.run()`, potentially a multi-step, long-running
operation — Section 2.2) is abandoned mid-execution with no graceful
drain opportunity, unlike every other execution context
`RuntimeService.shutdown()` already coordinates; and (b) `runtime
status` never reports whether this subsystem is even active, unlike
the REST API Server, Scheduler, and Background Worker Service, all
three of which `RuntimeStatus` already surfaces.

---

## 2. Current Architecture / Verified Source-Level Findings

### 2.1 `RuntimeService` (`src/services/runtime_service.py`, EP-059/060/061)

Read directly, current state:

- `RuntimeStatus` (frozen dataclass): `pid`, `uptime_seconds`,
  `shell_active`, `api_active`, `api_host`, `api_port`,
  `background_workers_active`, `background_worker_count`,
  `background_worker_task_count`, `scheduler_active` (default
  `False`), `scheduler_jobs_registered` (default `0`). No
  `workflow_scheduler_*` field exists.
- `RuntimeShutdownReport` (frozen dataclass): `rest_api_was_active`,
  `rest_api_stopped`, `background_workers_was_active`,
  `background_workers_stopped`, `scheduler_was_active` (default
  `False`), `scheduler_stopped` (default `True`). No
  `workflow_scheduler_*` field exists.
- `RuntimeService.__init__(self, started_at, rest_api_server,
  background_worker_service, shell, scheduler_service=None)` — no
  `workflow_scheduler_service` parameter.
- `RuntimeService.status()` reads `self._scheduler_service.status()`
  (if not `None`) for `scheduler_active`/`scheduler_jobs_registered`,
  by exact analogy to how it reads `self._background_worker_service.
  status()`. `WorkflowSchedulerService.status()` (returning
  `WorkflowSchedulerStatus(running, entries_registered,
  entries_enabled)`) is never called.
- `RuntimeService.shutdown()` calls, in this order: (1)
  `self._rest_api_server.stop()`, (2) `self._scheduler_service.
  shutdown()`, (3) `self._background_worker_service.shutdown()`. No
  fourth step exists.

### 2.2 `WorkflowSchedulerEngine.tick()` — confirmed blocking, unlike `Scheduler.tick()`

Read directly (`src/core/workflow_scheduler/workflow_scheduler_engine.py`):

```
tick() -> for each due entry: run_now(entry.id)
run_now(entry_id) -> self._workflow_engine.run(entry.workflow_id)   # synchronous
```

`WorkflowEngine.run()` (`src/core/workflow_engine/workflow_engine.py`,
EP-033) walks every `WorkflowRequestStep` in the referenced
`WorkflowDefinition` in order, dispatching each one through
`PlanExecutionEngine.execute_request()` (EP-030) — which transitively
reaches Planning/Tool/Agent execution paths. `WorkflowEngine.run()`
takes no timeout parameter and returns only once every step has run
or the failure policy halts the remainder. This is a **materially
different blocking profile from `Scheduler.tick()`** (EP-011): per
`EP061_DESIGN.md` Section 2.1 and this design's own independent
re-verification, `Scheduler`'s `ExecutionEngine` dispatches through
non-blocking primitives only (`subprocess.Popen`, `webbrowser.open()`)
that never wait for the launched program/file/URL to finish —
`SchedulerService._resolve_shutdown_timeout()`'s own docstring states
this explicitly as the reason a short, fixed constant is safe for
Scheduler ("`_stop_event.wait()` unblocks immediately once
`_stop_event.set()` is called, regardless of `scheduler.tick_interval`").
That reasoning does **not** carry over to `WorkflowSchedulerService`:
if `_tick_loop()` is inside an in-progress `self._engine.tick()` call
(i.e., mid-`WorkflowEngine.run()`) when `_stop_event.set()` is called,
the loop does not re-check `_stop_event` until the current `tick()`
call returns — which can take as long as the scheduled workflow
itself takes to run. This is architecturally closer to
`BackgroundWorkerPool`'s own "already-accepted, potentially
long-running work" shutdown profile (`background_workers.
shutdown_timeout`, default 10 seconds) than to `SchedulerService`'s.

### 2.3 No way to (re)start the tick loop except at construction

`_start_tick_loop()` is `private` and called only from `__init__`.
There is no public `start()`/`resume()` method anywhere on
`WorkflowSchedulerService`. This means `workflow_scheduler.auto_start:
true` at process start is the *only* way this subsystem's automatic
execution ever runs — it is not an optional convenience atop an
otherwise CLI-startable feature; it is a hard prerequisite for the
feature's stated purpose ("[gives] an EP-033 workflow definition a
time trigger — runs it automatically on a schedule", per
`config/config.yaml`'s own comment and this class's own docstring).
This confirms the gap is reachable through entirely ordinary, intended
use of this subsystem, not merely a theoretical corner case.

### 2.4 Why `workflow_scheduler.auto_start: false`'s default does not dismiss this gap

This design deliberately does not apply the same "defaults off, so no
gap" reasoning `EP060_DESIGN.md` Owner Decision D4 and
`EP062_DESIGN.md` Section 0 both correctly applied to Telegram
(`telegram.auto_start` defaulting `false`, re-verified there as still
factually true and dispositive). The distinction, verified from
source and from `config/config.yaml`'s own comments:

- Telegram's gateway is an optional, separate *external interface*
  ("Telegram is only an external interface; the rest of Jarvis starts
  and runs normally whether or not this section is configured") that
  an operator can also start and stop manually, at will, via `telegram
  start`/`telegram stop`, independent of `auto_start`.
- `WorkflowSchedulerService` has no such manual start path at all
  (Section 2.3) — `auto_start: true` is not one convenience among
  several for reaching this subsystem's core purpose; it is the
  *only* path. An operator who wants what EP-034 was built to
  provide — scheduled, unattended workflow execution — has exactly
  one way to get it, and that one way is exactly the configuration
  under which this design's gap is live.

### 2.5 `WorkflowEngine` instance sharing with `BackgroundWorkerPool` — verified independence for shutdown purposes

`src/bootstrap.py` (`_build_command_router`, confirmed lines ~1249-1330)
constructs exactly one `WorkflowEngine` instance
(`workflow_engine_for_scheduler`) and passes the *same* instance to
both `WorkflowSchedulerEngine` (via `WorkflowSchedulerService`) and
`BackgroundWorkerPool` (confirmed:
`src/core/background_workers/background_worker_pool.py` imports and
calls `WorkflowEngine.run()` too, using the same shared instance
wired in the same `_build_command_router` method). This is a
**pre-existing characteristic, already live and unaffected by
EP-063**: `WorkflowSchedulerService`'s tick thread and
`BackgroundWorkerPool`'s own worker threads can already call
`WorkflowEngine.run()` concurrently today, for different
`workflow_id`s, regardless of whether EP-063 is implemented. EP-063
introduces no new concurrency here — it only adds a way to stop
*originating new* `WorkflowSchedulerService`-triggered calls; it does
not touch `WorkflowEngine`, `PlanExecutionEngine`, or
`BackgroundWorkerPool` in any way, and does not need to, since
stopping the tick loop's *trigger* is independent of whatever
`WorkflowEngine`-level concurrency guarantees already exist or don't
(out of scope either way — see Section 5). This confirms, by the same
method `EP061_DESIGN.md` Section 2.1 used for Scheduler vs.
Background Worker, that no shutdown-ordering *correctness* dependency
exists between `WorkflowSchedulerService` and `BackgroundWorkerService`.

### 2.6 `WorkflowSchedulerModule` (`src/modules/workflow_scheduler_module.py`)

CLI namespace `"autoflow"`. `_actions` dict is exactly `{list, status,
run, start, stop, info, help}` (7 actions). No `register` command
(entries are registered only via `WorkflowSchedulerService.register()`,
called from `Bootstrap`) — this module's own docstring states this
matches `SchedulerModule`/`WorkflowEngineModule` precedent
deliberately.

### 2.7 `Bootstrap` (`src/bootstrap.py`)

- `self._workflow_scheduler_service: WorkflowSchedulerService | None`
  already exists as an instance attribute (confirmed line ~279), with
  a public `workflow_scheduler_service` property (confirmed lines
  ~2618-2629) — this promotion from "local variable" to "stored
  attribute" (the same kind of change `EP060_DESIGN.md` Section 5.9
  made for `_scheduler_service`) was **already done**, apparently at
  EP-035 time for Automation Engine's own purposes, not for
  `RuntimeService`. EP-063 needs no equivalent promotion — it only
  needs to pass this already-stored reference into `RuntimeService`'s
  constructor call.
- `Bootstrap.shutdown()` (confirmed lines ~2164-2200) delegates
  entirely to `self._runtime_service.shutdown()` (falling back to a
  direct `RestApiServer.stop()` call only if `RuntimeService` was
  never constructed) and nulls `self._rest_api_server`/
  `self._background_worker_service` afterward, mirroring
  `self._scheduler_service`'s own precedent of being deliberately
  **not** nulled (`SchedulerService` remains usable after its tick
  loop stops — `EP061_DESIGN.md` Owner Decision D3). No change to
  `Bootstrap.shutdown()`'s own body is required by this design beyond
  its docstring (see Section 6).

### 2.8 Existing test coverage (`tests/EP034/test_workflow_scheduler.py`, 999 lines)

Already exercises: registration, duplicate/unknown-entry errors,
`start(entry_id)`/`stop(entry_id)`, disabled-subsystem rejection, the
tick loop's start/stop via **private** attribute access (Section 1,
item 6), auto-start-from-config, and the full `WorkflowSchedulerModule`
CLI surface. This is a real, substantial, pre-existing regression
suite EP-063 must not break and should build alongside, not replace.

---

## 3. Gap Analysis

| Execution context | Owns background thread? | Auto-starts? | Public stop primitive? | Observed by `RuntimeStatus`? | Coordinated by `RuntimeService.shutdown()`? |
|---|---|---|---|---|---|
| REST API Server (EP-043) | N/A (socket server) | `api.enabled` (default false) | `.stop()` | Yes | Yes (EP-060) |
| Scheduler (EP-011) | Yes | `scheduler.auto_start` (default **true**) | `.shutdown()` (EP-061) | Yes (EP-060) | Yes (EP-061) |
| Background Worker Pool (EP-036) | Yes (pool of N) | Always, if enabled | `.shutdown()` | Yes | Yes (EP-060) |
| **Workflow Scheduler (EP-034)** | **Yes** | `workflow_scheduler.auto_start` (default false, but the *only* path to the feature — Section 2.3/2.4) | **None** | **No** | **No** |
| Telegram Gateway (EP-012) | Yes | `telegram.auto_start` (default false, one of several paths) | `.stop()` (manual only) | No (disclosed non-gap, EP-060/062) | No (disclosed non-gap; separately noted, Section 0.1, not this EP's scope) |

The one cell with no existing mitigation of any kind — no public stop
primitive, no manual CLI escape hatch, no status visibility, no
shutdown coordination — is `WorkflowSchedulerService`. This is
EP-063's scope.

---

## 4. Goals

1. Add a public, idempotent `WorkflowSchedulerService.shutdown(wait:
   bool = True, timeout: float | None = None) -> bool` method that
   stops the tick loop, reusing the already-existing
   `_stop_event`/`_tick_thread` mechanism — structurally mirroring
   `SchedulerService.shutdown()` (EP-061) and
   `BackgroundWorkerService.shutdown()` (EP-036).
2. Wire this into `RuntimeService`: a new, keyword-defaulted
   `workflow_scheduler_service: WorkflowSchedulerService | None = None`
   constructor parameter (backward compatible, matching
   `scheduler_service`'s own EP-060 precedent exactly).
3. Widen `RuntimeStatus` with `workflow_scheduler_active: bool = False`
   and `workflow_scheduler_entries_registered: int = 0` (mirroring
   `scheduler_active`/`scheduler_jobs_registered`'s shape), so
   `runtime status` correctly reports this subsystem regardless of how
   it reaches its only-possible "running" state (Section 2.4).
4. Widen `RuntimeShutdownReport` with `workflow_scheduler_was_active:
   bool = False` and `workflow_scheduler_stopped: bool = True`
   (mirroring `scheduler_was_active`/`scheduler_stopped`'s shape and
   defaulting convention).
5. Wire `self._workflow_scheduler_service` (already stored on
   `Bootstrap` — Section 2.7) into the `RuntimeService(...)`
   constructor call inside `Bootstrap.initialize()`.
6. Extend `RuntimeService.shutdown()`'s coordinated sequence with a
   fourth step for `WorkflowSchedulerService`, in the ordering defined
   by Owner Decision D2 (Section 9).
7. Extend `RuntimeModule._status()`'s CLI/REST-reachable output with
   one new line, following the exact `Scheduler : ACTIVE/INACTIVE`
   pattern already used for `scheduler_active`.
8. Close the whitebox test workaround this design documents in
   Section 1, item 6 — after STEP 2, `tests/EP034/
   test_workflow_scheduler.py`'s two private-attribute-accessing tests
   may (owner's STEP 2 discretion, not mandated here) be rewritten to
   use the new public `shutdown()` instead, exactly as
   `EP061_DESIGN.md` disclosed (but deferred to STEP 2) an analogous
   `tests/EP060/test_runtime_lifecycle.py` docstring correction.

---

## 5. Non-Goals

- **No fix to Telegram Gateway shutdown coordination.** Investigated
  and found real (Section 0.1), but explicitly out of scope for this
  EP — different risk profile (manual escape hatch already exists),
  zero pre-existing test coverage (a materially larger STEP 2 lift),
  and deliberately left as a distinct, separately-scoped candidate for
  a future EP, exactly as `EP060_DESIGN.md`/`EP061_DESIGN.md` used
  "separately scoped, not ruled out" framing for their own deferred
  items.
- **No new public `start()`/`resume()` method on
  `WorkflowSchedulerService`.** This design does not add any way to
  restart the tick loop once `shutdown()` has stopped it —
  `_start_tick_loop()` remains private, called only from `__init__`,
  exactly matching `SchedulerService`'s and `BackgroundWorkerService`'s
  own precedent of exposing no public restart method.
- **No CLI/REST-reachable "stop the tick loop" action.** Exactly like
  `SchedulerService.shutdown()` (`EP061_DESIGN.md` Owner Decision D1)
  and `RuntimeService.shutdown()` itself (`EP060_DESIGN.md` Owner
  Decision D3), the new `WorkflowSchedulerService.shutdown()` is
  invoked only from the internal `RuntimeService.shutdown()`
  coordination path — never exposed through `WorkflowSchedulerModule`.
  `WorkflowSchedulerModule._actions` stays exactly `{list, status,
  run, start, stop, info, help}` (7, unchanged).
- **No change to per-entry `start(entry_id)`/`stop(entry_id)`
  semantics, `register`/`unregister`/`run_now`, or
  `calculate_next_run`.** All untouched.
- **No change to `WorkflowSchedulerEngine`, `ScheduledWorkflowRegistry`,
  `ScheduledWorkflow`, `WorkflowEngine`, or `PlanExecutionEngine`.**
  This design touches only `WorkflowSchedulerService`'s own lifecycle
  wrapper, `RuntimeService`/`RuntimeStatus`/`RuntimeShutdownReport`,
  `RuntimeModule`'s CLI formatting, and one `Bootstrap` call site
  widening — mirroring the "narrow, additive" shape
  `EP061_DESIGN.md` Section 6 established for the same class of fix.
- **No attempt to interrupt or cancel an in-progress
  `WorkflowEngine.run()` call.** There is no cancellation primitive
  anywhere in `WorkflowEngine`/`PlanExecutionEngine` today, and adding
  one is far outside this EP's scope. `shutdown()` can only wait (up
  to its resolved timeout) for the current tick's `run_now()` call to
  finish naturally; see Section 8 for the accepted, disclosed
  consequence.
- **No new `WorkflowSchedulerService` field/behavior beyond
  `shutdown()`.** `status()`'s existing three fields
  (`running`/`entries_registered`/`entries_enabled`) are read, not
  modified.
- **No fix to `ARCHITECTURE_DEBT.md` items** (AD-001/AD-002, both
  already filed against this same file, `workflow_scheduler_service.py`,
  and `bootstrap.py` respectively) — unrelated to shutdown lifecycle,
  and barred from normal-EP fixes regardless, per that document's own
  rule.
- **No new configuration key beyond the one proposed in Section 6.2**
  (`workflow_scheduler.shutdown_timeout`) — no other key is touched.

---

## 6. Proposed Design

No new module, class, package, registry, or abstraction is
introduced. This is a narrow, additive widening of four already-
existing files, following the exact structural precedent
`SchedulerService.shutdown()` (EP-061) already established for "a
service with a background execution context gains a public, idempotent
shutdown method, wired into `RuntimeService`'s existing coordination
sequence":

```
Bootstrap.shutdown()
        |
        v
RuntimeService.shutdown()  (EP-060; widened EP-061; widened here)
        |
        +--> 1. RestApiServer.stop()                        (unchanged, EP-043)
        +--> 2. SchedulerService.shutdown()                  (unchanged, EP-061)
        +--> 3. WorkflowSchedulerService.shutdown()    <-- NEW (EP-063),
        |            |                                          reuses the
        |            v                                          already-
        |        _stop_event.set()                              existing
        |        _tick_thread.join(timeout)                     _stop_event/
        |                                                        _tick_thread
        +--> 4. BackgroundWorkerService.shutdown()            (unchanged, EP-036)
```

### 6.1 `WorkflowSchedulerService.shutdown()`

```python
def shutdown(self, wait: bool = True, timeout: float | None = None) -> bool:
    """Stop the background tick loop, if one is running.

    Safe to call regardless of whether the tick loop was ever started
    (e.g. 'workflow_scheduler.auto_start: false', or already stopped)
    -- reports success immediately since there is nothing to stop.
    Does not affect any registered entry's enabled/disabled state, and
    does not prevent run(entry_id) from being called manually
    afterward -- only the automatic tick loop is stopped.

    Unlike SchedulerService.shutdown() (EP-061), this method's default
    timeout is read from 'workflow_scheduler.shutdown_timeout'
    configuration (mirroring BackgroundWorkerService.shutdown()'s own
    'background_workers.shutdown_timeout'), not a fixed constant --
    because, unlike Scheduler.tick() (whose ExecutionEngine never
    blocks), WorkflowSchedulerEngine.tick() can itself block for as
    long as a scheduled workflow's WorkflowEngine.run() call takes
    (see EP063_DESIGN.md Section 2.2).

    Args:
        wait: If True (default), block until the tick thread has
            exited or `timeout` elapses. If False, signal the stop and
            return immediately without joining.
        timeout: Maximum seconds to wait when `wait` is True. Defaults
            to this service's resolved
            'workflow_scheduler.shutdown_timeout' when not given
            explicitly.

    Returns:
        True if the tick loop is confirmed not running after this
        call (including if it was never running to begin with); False
        if `wait=True` and the thread did not exit within `timeout`
        (e.g. a scheduled workflow run was still in progress).
    """
```

Body structurally identical to `SchedulerService.shutdown()`
(Section 2 there): acquire `self._lifecycle_lock`, capture
`self._tick_thread`, return `True` immediately if `None`; otherwise
`self._stop_event.set()`; if `wait` is `False`, return
`not thread.is_alive()` without joining; otherwise
`thread.join(timeout=resolved_timeout)`, clear `self._tick_thread` to
`None` under the lock only if the captured thread is confirmed no
longer alive and is still the current one, and return whether it
stopped.

### 6.2 `_resolve_shutdown_timeout()` and the new configuration key

```python
def _resolve_shutdown_timeout(self) -> float:
    """Return 'workflow_scheduler.shutdown_timeout' (default: 10)."""
    value = self._config.get("workflow_scheduler.shutdown_timeout", 10)
    ...  # same defensive int/float coercion BackgroundWorkerService
         # already applies to 'background_workers.shutdown_timeout'
```

`config/config.yaml`'s `workflow_scheduler:` section gains one new
key, `shutdown_timeout: 10` (default, matching
`background_workers.shutdown_timeout`'s own default value and units —
seconds), with a comment explaining why (mirroring the
`background_workers.shutdown_timeout` comment's own style) that this
bounds how long `shutdown()` waits for an in-progress scheduled
workflow run to finish before giving up, distinct in kind from
`SchedulerService.shutdown()`'s fixed constant (Owner Decision D3,
Section 9).

### 6.3 `RuntimeStatus` widening

```python
scheduler_active: bool = False
scheduler_jobs_registered: int = 0
workflow_scheduler_active: bool = False               # NEW (EP-063)
workflow_scheduler_entries_registered: int = 0         # NEW (EP-063)
```

Appended last, after the existing `scheduler_*` pair, for the exact
dataclass-backward-compatibility reason `RuntimeShutdownReport`'s own
docstring already documents for `scheduler_was_active`/
`scheduler_stopped` (Section 2.1) — today's only construction call
site is fully keyword-based, so field order carries no behavioral
risk, but the convention is kept for consistency and defensiveness.

`RuntimeService.status()` gains:

```python
workflow_scheduler_active = False
workflow_scheduler_entries_registered = 0
if self._workflow_scheduler_service is not None:
    wf_scheduler_status = self._workflow_scheduler_service.status()
    workflow_scheduler_active = wf_scheduler_status.running
    workflow_scheduler_entries_registered = wf_scheduler_status.entries_registered
```

— by exact structural analogy to the existing `scheduler_*` block
immediately above it.

### 6.4 `RuntimeShutdownReport` widening

```python
scheduler_was_active: bool = False
scheduler_stopped: bool = True
workflow_scheduler_was_active: bool = False    # NEW (EP-063)
workflow_scheduler_stopped: bool = True        # NEW (EP-063)
```

`RuntimeService.shutdown()` gains, inserted as the third of four
sequential steps (Owner Decision D2, Section 9):

```python
workflow_scheduler_was_active = False
if self._workflow_scheduler_service is not None:
    workflow_scheduler_was_active = self._workflow_scheduler_service.status().running
workflow_scheduler_stopped = True
if self._workflow_scheduler_service is not None:
    workflow_scheduler_stopped = self._workflow_scheduler_service.shutdown()
```

— by exact structural analogy to the existing `scheduler_was_active`/
`scheduler_stopped` block, placed between it and the existing
`background_workers_was_active`/`background_workers_stopped` block.

### 6.5 `RuntimeService.__init__` widening

```python
def __init__(
    self,
    started_at: float,
    rest_api_server: RestApiServer | None,
    background_worker_service: BackgroundWorkerService | None,
    shell: InteractiveShell | None,
    scheduler_service: SchedulerService | None = None,
    workflow_scheduler_service: WorkflowSchedulerService | None = None,  # NEW
) -> None:
    ...
    self._workflow_scheduler_service = workflow_scheduler_service
```

Keyword-defaulted to `None`, so every existing call site (including
every EP-059/060/061/062 test's own `RuntimeService(...)`
constructions) continues to construct a valid `RuntimeService`
unchanged — the same backward-compatibility guarantee
`scheduler_service`'s own EP-060 introduction already relied on and
that this design's own regression suite must re-prove (Section 11).

### 6.6 `Bootstrap.initialize()` widening

One line added to the existing `RuntimeService(...)` constructor call:

```python
self._runtime_service = RuntimeService(
    started_at=self._started_at,
    rest_api_server=self._rest_api_server,
    background_worker_service=self._background_worker_service,
    shell=self._shell,
    scheduler_service=self._scheduler_service,
    workflow_scheduler_service=self._workflow_scheduler_service,  # NEW
)
```

`self._workflow_scheduler_service` is already assigned earlier in
`initialize()` (inside `_build_command_router`, Section 2.7) before
this line runs, exactly as `self._scheduler_service` already is — no
ordering change needed. `Bootstrap.shutdown()`'s own body needs no
change (it already delegates unconditionally to
`self._runtime_service.shutdown()`); only its docstring is updated to
describe the new fourth step, mirroring exactly how EP-061 updated
`Bootstrap.shutdown()`'s docstring without touching its body.
`self._workflow_scheduler_service` is **not** nulled after `shutdown()`
in `Bootstrap.shutdown()`, for the same reason `self._scheduler_service`
already isn't (Section 2.7): `WorkflowSchedulerService` remains a
fully usable object after its tick loop stops (`status()`, `list_entries()`,
`run(entry_id)`, `register()`/`unregister()` all continue to work
correctly).

### 6.7 `RuntimeModule._status()` widening

One new block, following the exact `Scheduler` block's shape:

```python
lines.append(
    f"Workflow Scheduler : "
    f"{'ACTIVE' if status.workflow_scheduler_active else 'INACTIVE'}"
)
if status.workflow_scheduler_active:
    lines.append(
        f"Workflow Scheduler entries registered : "
        f"{status.workflow_scheduler_entries_registered}"
    )
```

Appended after the existing `Scheduler`/`Scheduler jobs registered`
block, preserving the existing display order (REST API, Background
Workers, Scheduler, then this new block).

---

## 7. Status/CLI Behavior — Before and After

Given `workflow_scheduler.auto_start: true`, three entries registered,
two enabled, before shutdown is requested:

**Before this design:** `runtime status` shows PID/Uptime/Shell/REST
API/Background Workers/Scheduler only — nothing about Workflow
Scheduler, even though its tick thread is live. `Bootstrap.shutdown()`
stops REST, Scheduler, and Background Workers; the Workflow Scheduler
tick thread is left running as a daemon thread, mid-`tick()` or not,
until the interpreter itself exits.

**After this design:** `runtime status` additionally shows
`Workflow Scheduler : ACTIVE` and `Workflow Scheduler entries
registered : 3`. `Bootstrap.shutdown()` additionally signals the tick
loop to stop (third of four steps) and waits up to
`workflow_scheduler.shutdown_timeout` seconds (default 10) for any
in-progress tick to finish before proceeding to drain the Background
Worker Service. A subsequent `runtime status` call shows `Workflow
Scheduler : INACTIVE`.

---

## 8. Error / Edge Cases

- **`workflow_scheduler_service=None`** (subsystem disabled, or the
  Workflow Engine/Plan Execution Engine it depends on was unavailable
  this run — Section 2 of `bootstrap.py`'s own wiring comment):
  `status()` reports `workflow_scheduler_active=False`,
  `workflow_scheduler_entries_registered=0`; `shutdown()` reports
  `workflow_scheduler_was_active=False`,
  `workflow_scheduler_stopped=True` — "nothing to do" counts as
  success, exactly matching every other optional dependency's
  existing convention in this class.
- **Tick loop never started** (`auto_start: false`, the default):
  identical all-`False`/all-zero/`True` reporting as above, without
  needing a `None` service reference — `WorkflowSchedulerService.
  shutdown()` itself already returns `True` immediately when
  `self._tick_thread is None` (Section 6.1), matching
  `SchedulerService.shutdown()`'s own identical branch.
- **`shutdown()` called while a scheduled workflow run is genuinely
  in progress:** the tick thread does not observe `_stop_event` until
  its current `self._engine.tick()` call returns (Section 2.2). If
  the in-progress `WorkflowEngine.run()` call finishes within
  `workflow_scheduler.shutdown_timeout` seconds, `shutdown()` returns
  `True` once the thread confirms stopped. If it does not,
  `shutdown()` returns `False` (matching `SchedulerService.shutdown()`/
  `BackgroundWorkerService.shutdown()`'s own "return False rather than
  raise on timeout" convention) and the tick thread is left running
  as an abandoned daemon thread for the remainder of process exit —
  the same accepted, already-disclosed risk profile
  `EP060_DESIGN.md` Section 11 already accepted for
  `BackgroundWorkerService.shutdown()`'s own analogous case, not a new
  risk category introduced by this design. No workflow step is
  interrupted mid-step by this design in any way it wasn't already
  possible for a `PENDING`/`RUNNING` background-worker task to be
  interrupted before EP-036 (see `ARCHITECTURE_DEBT.md` AD-005, an
  unrelated, already-superseded concern for a different subsystem —
  not reopened by this design).
- **A second `Bootstrap.shutdown()`/`RuntimeService.shutdown()` call:**
  idempotent, exactly like the other three steps —
  `WorkflowSchedulerService.shutdown()`'s own idempotency (Section
  6.1: returns `True` immediately once `self._tick_thread` is already
  `None`) makes a second call to it, and therefore to
  `RuntimeService.shutdown()` as a whole, safe.
- **`WorkflowSchedulerService.status()` called concurrently with
  `shutdown()`:** both already synchronize through the same
  `self._lifecycle_lock` that guards `self._tick_thread`
  (`_is_tick_loop_running()` already acquires it) — no new locking is
  introduced or required; the new `shutdown()` method reuses the
  identical lock-acquisition shape `SchedulerService.shutdown()`
  already uses safely (a short, never-held-across-a-blocking-call
  critical section, confirmed by direct reading of both classes).
- **Malformed `workflow_scheduler.shutdown_timeout`** (non-numeric,
  negative): out of scope for this design to newly guard against
  beyond whatever defensive coercion `BackgroundWorkerService`'s own
  `_resolve_worker_count()`-style pattern already establishes as this
  repository's convention for a malformed numeric config value —
  STEP 2 should apply the same coercion `background_workers.
  shutdown_timeout` itself receives, not invent a new policy.
  (`ARCHITECTURE_DEBT.md` AD-001 already tracks an analogous
  malformed-config concern for `workflow_scheduler.tick_interval`
  specifically — that item is unrelated and untouched by this design;
  this note is about `shutdown_timeout`, a new key this design itself
  introduces, and only asks STEP 2 to apply existing, established
  coercion conventions to it, not to leave it unvalidated.)

---

## 9. Owner Decisions

### D1 — Should `WorkflowSchedulerService.shutdown()` be exposed through `WorkflowSchedulerModule`'s CLI/REST surface?

**Question:** Should `autoflow` gain a new, mutating action (e.g.
`autoflow shutdown`) that stops the tick loop directly, in addition to
internal `RuntimeService`-coordinated shutdown?

**Options:** (a) no new CLI/REST action — `shutdown()` remains
internal-only, invoked exclusively by `RuntimeService.shutdown()`
(recommended — matches `SchedulerService.shutdown()`'s own EP-061
Owner Decision D1 exactly, for the identical reasoning: this
repository's REST API remains unauthenticated, and any new
CLI-exposed action is automatically REST-reachable per
`EP059_DESIGN.md` Section 6.4); (b) add `autoflow shutdown` as a new
CLI action.

**Recommended option:** (a).

**What changes in STEP 2:** (a) → `WorkflowSchedulerModule._actions`
stays exactly `{list, status, run, start, stop, info, help}` (7,
unchanged). (b) → a new action, its own argument handling, and the
same unauthenticated-REST-exposure risk `EP061_DESIGN.md` Owner
Decision D1 already declined to accept for Scheduler, with no new
justification for accepting it here.

### D2 — Where should `WorkflowSchedulerService` be stopped relative to the REST API Server, Scheduler, and Background Worker Service?

**Question:** `RuntimeService.shutdown()`'s sequence is presently REST
→ Scheduler → Background Workers. `WorkflowSchedulerService`
originates new work (like REST/Scheduler) but, unlike either of them,
can itself block for a workflow-dependent duration while stopping
(Section 2.2) — closer in that one respect to Background Worker
Service's own drain profile. Where does it fit?

**Options:**
(a) **REST → Scheduler → Workflow Scheduler → Background Workers**
(recommended): preserves the established "silence new-work triggers
before draining already-accepted work" principle
(`EP061_DESIGN.md` Section 6) — `WorkflowSchedulerService` is still a
new-work-triggering context, not a work-accepting one, so it belongs
before Background Worker Service regardless of its own blocking
characteristics; and orders the three trigger-silencing steps from
fastest-to-settle to slowest-to-settle (REST's `.stop()` and
Scheduler's near-instant join, confirmed non-blocking per Section 2.2,
before Workflow Scheduler's potentially much longer join), so a
fast-closing trigger is never needlessly delayed behind a slow one
with no correctness reason to be. No correctness dependency requires
this specific order among the three trigger steps (verified: Section
2.5 confirms `WorkflowSchedulerService` and `SchedulerService` share
no state, exactly as `EP061_DESIGN.md` Section 2.1 already verified
for Scheduler vs. Background Worker) — this ordering is a
consistency/latency choice, not a correctness one.
(b) REST → Workflow Scheduler → Scheduler → Background Workers —
equally correct, no shared state to violate; rejected only for
being a less intuitive read of the "fast trigger first" grouping.
(c) Immediately before Background Workers with no distinction from
option (a) in outcome, differing only in exact list position — this
is what (a) already specifies; not a distinct option.

**Recommended option:** (a).

**What changes in STEP 2:** (a) → `RuntimeService.shutdown()`'s body
gains the new step as the third of four, exactly as drafted in
Section 6.4. (b)/(c) → same code, different statement order within
the method body; no observable behavioral difference given Section
2.5's confirmed independence, so (a) is preferred purely for
readability/consistency, not correctness.

### D3 — Should `shutdown()`'s join timeout be a new `workflow_scheduler.shutdown_timeout` configuration key, or a fixed constant (mirroring `SchedulerService`'s EP-061 Owner Decision D4)?

**Question:** `EP061_DESIGN.md` Owner Decision D4 chose a fixed,
unconfigurable constant for `SchedulerService.shutdown()`'s join
timeout, reasoning that none of Scheduler's executors block the tick
thread on arbitrary external execution. Section 2.2 of this document
establishes that `WorkflowSchedulerEngine.tick()` does **not** share
that property — it can block for as long as a scheduled workflow's
`WorkflowEngine.run()` call takes. Should EP-063 follow EP-061's fixed-
constant precedent anyway, for consistency, or diverge and introduce a
new, configurable `workflow_scheduler.shutdown_timeout` key, mirroring
`BackgroundWorkerService.shutdown()`'s own `background_workers.
shutdown_timeout`?

**Options:** (a) new configurable `workflow_scheduler.shutdown_timeout`
key, default `10` (recommended — matches the subsystem this class's
blocking profile actually resembles, `BackgroundWorkerService`, not
the one it superficially resembles, `SchedulerService`; a fixed short
constant here would make `shutdown()` return `False` routinely for any
scheduled workflow that takes longer than that constant to run, which
is a realistic, not edge-case, occurrence for this subsystem's stated
purpose); (b) fixed constant (e.g. 5 seconds), matching
`SchedulerService`'s own precedent exactly, for consistency across the
two schedulers.

**Recommended option:** (a).

**What changes in STEP 2:** (a) → `config/config.yaml`'s
`workflow_scheduler:` section gains one new key (Section 6.2);
`WorkflowSchedulerService._resolve_shutdown_timeout()` reads it,
mirroring `BackgroundWorkerService`'s own resolution method's shape.
(b) → no configuration change; `_resolve_shutdown_timeout()` returns a
class constant, mirroring `SchedulerService._DEFAULT_SHUTDOWN_TIMEOUT`
instead — but `shutdown()` would then return `False` far more often in
ordinary use than either `SchedulerService.shutdown()` or
`BackgroundWorkerService.shutdown()` do today, which this document
does not recommend accepting silently.

### D4 — Should `Bootstrap.shutdown()` null `self._workflow_scheduler_service` after shutdown, matching what it already does for `_rest_api_server`/`_background_worker_service`?

**Question:** `Bootstrap.shutdown()` nulls `self._rest_api_server`/
`self._background_worker_service` after delegating to
`RuntimeService.shutdown()`, but deliberately does **not** null
`self._scheduler_service` (EP-061 Owner Decision D3: `SchedulerService`
remains a fully usable object — `status()`, `doctor()`, `list_jobs()`,
manual `run(job_id)` — once its tick loop is stopped). Should
`self._workflow_scheduler_service` follow the nulled pair's precedent
or the not-nulled `_scheduler_service` precedent?

**Options:** (a) do not null it (recommended — for the identical
reason EP-061 gave for `_scheduler_service`: `WorkflowSchedulerService.
status()`, `list_entries()`, `get_entry()`, `run(entry_id)`,
`register()`/`unregister()` all remain fully correct and usable after
the tick loop alone is stopped; nothing about this object becomes
unusable the way a stopped `RestApiServer` or a shut-down
`BackgroundWorkerPool` reference does); (b) null it, matching
`_rest_api_server`/`_background_worker_service`'s own precedent
instead.

**Recommended option:** (a).

**What changes in STEP 2:** (a) → `bootstrap.workflow_scheduler_service`
remains non-`None` and identity-preserved across `shutdown()`, exactly
like `bootstrap.scheduler_service` already does. (b) → the property
would return `None` after shutdown, breaking any caller (present or
future) that reasonably expects to still call
`bootstrap.workflow_scheduler_service.list_entries()` after a graceful
shutdown, for no compensating benefit.

---

## 10. RuntimeService Compatibility Impact

- **`RuntimeStatus`**: two new fields, both defaulted
  (`workflow_scheduler_active: bool = False`,
  `workflow_scheduler_entries_registered: int = 0`), appended last.
  Every existing construction call site (production and test) that
  does not pass them continues to work unchanged — this is the
  identical guarantee `scheduler_active`/`scheduler_jobs_registered`
  already rely on since EP-060.
- **`RuntimeShutdownReport`**: two new fields, both defaulted
  (`workflow_scheduler_was_active: bool = False`,
  `workflow_scheduler_stopped: bool = True`), appended last, same
  guarantee.
- **`RuntimeService.__init__`**: one new keyword-defaulted parameter
  (`workflow_scheduler_service: WorkflowSchedulerService | None =
  None`). Every existing call site — production (`Bootstrap.
  initialize()`, widened per Section 6.6) and test
  (`tests/EP059/test_runtime.py`, `tests/EP060/
  test_runtime_lifecycle.py`, `tests/EP061/test_scheduler_shutdown.py`,
  `tests/EP062/test_background_worker_status.py`) — continues to
  construct a valid `RuntimeService` unmodified. This is the exact
  backward-compatibility class this design's own regression suite
  (Section 11) must re-prove, mirroring `EP060_DESIGN.md`
  Section 13's "widened status, backward compatibility" test and
  `EP061_DESIGN.md`'s identical re-proof for its own new parameter.
- **`RuntimeService.status()`/`.shutdown()`**: both remain the entire
  public surface (`{status, shutdown}`, unchanged) — no new public
  method is added to `RuntimeService` itself.
- **No REST/CLI contract change beyond `runtime status`'s formatted
  text output** (Section 6.7) — `runtime`'s own action set stays
  exactly `{status, help}` (2, unchanged), so nothing new becomes
  REST-reachable via `ApiRouter`'s existing forwarding behavior
  (`EP059_DESIGN.md` Section 6.4) beyond one additional line of
  already-read-only text in an already-REST-reachable action.

---

## 11. Testing Strategy

New suite: `tests/EP063/test_workflow_scheduler_shutdown.py`,
self-contained per this repository's own per-EP convention (no import
from `tests/EP059/`–`tests/EP062/`; local builder functions, following
`tests/EP061/test_scheduler_shutdown.py`'s own documented precedent of
deliberately near-identical-but-independent local copies), built on
`src.testing.base_test.BaseTest`/`src.testing.registry.TestRegistry`,
registered via one new import line in `src/modules/test_module.py`
(`import tests.EP063.test_workflow_scheduler_shutdown`), matching
every prior EP's identical registration pattern (Section 2 of this
document; confirmed convention going back through
`tests.EP062.test_background_worker_status`).

Coverage required, mirroring `EP061_DESIGN.md` Section 12's own four-
part shape:

1. **`WorkflowSchedulerService.shutdown()` in isolation:**
   - Never started (`auto_start: false`, default): `shutdown()`
     returns `True` immediately, no thread ever existed.
   - Started, then `shutdown(wait=True)`: tick thread confirmed
     stopped (`not thread.is_alive()`), `status().running` becomes
     `False`.
   - `wait=False`: returns immediately, signals `_stop_event` without
     blocking.
   - Called twice in direct succession: idempotent, second call
     returns `True` immediately (mirrors `SchedulerService.shutdown()`'s
     own idempotency test).
   - **A tick genuinely in progress when `shutdown()` is called:**
     construct a real `WorkflowEngine` bound to a `WorkflowDefinition`
     with a deliberately slow step (e.g. a step whose provider sleeps
     for a controlled, short-but-nonzero duration under test), trigger
     a tick, call `shutdown(timeout=<longer than the sleep>)` from a
     second thread, and confirm it returns `True` only once the
     in-progress run has actually completed — this is the test that
     did not exist for `SchedulerService` (because it doesn't need
     it, Section 2.2) and is the direct regression proof for this
     design's central architectural finding (Section 2.2, Owner
     Decision D3).
   - **Timeout genuinely exceeded:** same setup, `shutdown(timeout=<
     shorter than the sleep>)` returns `False`; `status().running`
     confirmed still momentarily `True`/thread still alive
     immediately after the call (before the slow step naturally
     finishes in the background).
   - `_resolve_shutdown_timeout()` reads
     `workflow_scheduler.shutdown_timeout` when present, falls back to
     `10` when absent — direct regression proof for Owner Decision D3.
2. **`RuntimeService`'s widened `status()`/`shutdown()`:**
   - Constructed with the exact original five keyword arguments (no
     `workflow_scheduler_service`) — confirms it still succeeds and
     `status().workflow_scheduler_active is False`, matching every
     other "dependency not supplied" field's existing convention. This
     is the direct regression proof for Section 10's backward-
     compatibility claim, mirroring `EP060_DESIGN.md`/
     `EP061_DESIGN.md`'s own identical test for their own new
     parameter.
   - Constructed with a real, unmodified `WorkflowSchedulerService`
     under both `workflow_scheduler.auto_start: true` and `false` —
     confirms `workflow_scheduler_active` matches
     `WorkflowSchedulerService.status().running` in both cases, and
     `workflow_scheduler_entries_registered` matches
     `status().entries_registered`.
   - `shutdown()`, real `WorkflowSchedulerService` (auto-started) +
     real `RestApiServer` + real `BackgroundWorkerService`: confirms
     all three (plus the pre-existing `SchedulerService`) are stopped;
     explicit call-order-recording proxies (matching
     `EP061_DESIGN.md`'s own "call-order-recording proxies" technique)
     confirm the REST → Scheduler → Workflow Scheduler → Background
     Workers ordering from Owner Decision D2.
   - `shutdown()`, all dependencies `None`: confirms
     `workflow_scheduler_was_active=False`/
     `workflow_scheduler_stopped=True`, never raises.
   - Idempotency: call `shutdown()` twice — second call reports
     `workflow_scheduler_was_active=False` (already stopped),
     `workflow_scheduler_stopped=True`.
   - **Regression guard:** confirms `runtime status`/`worker status`/
     `scheduler status`/`autoflow status` (already-existing,
     unmodified actions) are unaffected in their own right by this
     widening.
3. **Real end-to-end `Bootstrap` wiring:** build a full `Bootstrap`
   with `workflow_scheduler.auto_start: true` and at least one
   registered, enabled scheduled entry with a fast interval, call
   `bootstrap.initialize()`, confirm `bootstrap.workflow_scheduler_service.
   status().running is True`, call `bootstrap.shutdown()`, confirm
   `status().running is False` and
   `bootstrap.workflow_scheduler_service is not None` (Owner Decision
   D4 — not nulled), and confirm a second `bootstrap.shutdown()` call
   remains safe.
4. **Public-surface guards:** `WorkflowSchedulerService`'s public
   method set stays exactly `{register, unregister, start, stop, run,
   list_entries, get_entry, status, shutdown}` (9, one addition from
   8); `WorkflowSchedulerModule._actions` stays exactly `{list,
   status, run, start, stop, info, help}` (7, unchanged — Owner
   Decision D1); `RuntimeService`'s public surface stays exactly
   `{status, shutdown}` (2, unchanged); `RuntimeModule._actions` stays
   exactly `{status, help}` (2, unchanged).

**Regression re-runs required** (unmodified): `tests/EP034/
test_workflow_scheduler.py` (must continue to pass byte-for-byte
unmodified, proving `WorkflowSchedulerService`'s pre-existing behavior
is genuinely untouched — its own two whitebox-workaround tests,
Section 1 item 6, are explicitly permitted, not required, to be
rewritten against the new public `shutdown()` at STEP 2's discretion,
mirroring `EP061_DESIGN.md`'s own disclosed-but-deferred-to-STEP-2
docstring correction for `tests/EP060/test_runtime_lifecycle.py`);
`tests/EP059/test_runtime.py`; `tests/EP060/test_runtime_lifecycle.py`;
`tests/EP061/test_scheduler_shutdown.py`; `tests/EP062/
test_background_worker_status.py`; `tests/EP036/*`; `tests/EP043/*`.

**Note on test-fixture reuse:** `tests/EP061/test_scheduler_shutdown.py`
already imports and constructs a real `WorkflowEngine`/
`WorkflowEngineManager`/`WorkflowDefinition`/`WorkflowRequestStep`
(needed there for its own `BackgroundWorkerService` end-to-end
fixture) — EP-063's own fixtures can reuse this exact, already-proven
construction pattern rather than inventing a new one, matching this
repository's own "real objects, not mocks" precedent
(`EP059_DESIGN.md`'s own stated approach, reused by every EP since).

---

## 12. Expected File Scope (for STEP 2 — not authorized by this document)

### MODIFY

- `src/services/workflow_scheduler_service.py` — add `shutdown()` and
  `_resolve_shutdown_timeout()` (Section 6.1/6.2). No other method's
  signature or behavior changes.
- `src/services/runtime_service.py` — widen `RuntimeStatus`,
  `RuntimeShutdownReport`, `RuntimeService.__init__`, `status()`,
  `shutdown()` (Section 6.3-6.5). Docstring updates throughout,
  matching this file's own established per-EP annotation convention.
- `src/bootstrap.py` — one line added to the existing
  `RuntimeService(...)` call inside `initialize()` (Section 6.6);
  `shutdown()`'s docstring updated to describe the new fourth step
  (its body is unchanged). No other line changes.
- `src/modules/runtime_module.py` — `_status()` gains one new
  formatted block (Section 6.7). `HELP_TEXT`, `_actions`, `_help()`
  unchanged.
- `config/config.yaml` — `workflow_scheduler:` section gains one new
  key, `shutdown_timeout: 10`, with an explanatory comment (Section
  6.2, Owner Decision D3).
- `src/modules/test_module.py` — one new import line (Section 11),
  matching every prior EP's identical, unitemized-in-detail addition
  (`EP062_ARCHITECTURE_AUDIT.md`'s own STEP 3 finding #2 already
  established this specific kind of one-line addition as expected,
  non-blocking, and consistent with EP-059/060/061's own STEP 2 work).

### CREATE

- `tests/EP063/__init__.py` (empty package marker, matching every
  other `tests/EPxxx/__init__.py`).
- `tests/EP063/test_workflow_scheduler_shutdown.py` (Section 11).

### DO NOT MODIFY (see Section 13, Protected Files)

---

## 13. Protected Files

The following must remain byte-identical/unmodified by EP-063,
verified independently at STEP 3 exactly as every prior EP's own
audit has done for its own scope:

- `src/core/workflow_scheduler/workflow_scheduler_engine.py`,
  `scheduled_workflow_registry.py`, `scheduled_workflow.py` — this
  design touches only `WorkflowSchedulerService`'s lifecycle wrapper,
  never the engine it wraps (Section 5).
- `src/modules/workflow_scheduler_module.py` — read via
  `WorkflowSchedulerService.status()` indirectly through
  `RuntimeService`, never modified itself; its own `_status()`
  formatting and `_actions` dict are untouched (Owner Decision D1).
- `src/core/scheduler/*.py`, `src/services/scheduler_service.py`,
  `src/modules/scheduler_module.py` (EP-011/EP-061) — zero changes;
  `.status()`/`.shutdown()` are called by `RuntimeService`, unmodified.
- `src/core/background_workers/*.py`,
  `src/services/background_worker_service.py`,
  `src/modules/background_worker_module.py` (EP-036/EP-062) — zero
  changes; `.status()`/`.shutdown()` are called by `RuntimeService`,
  unmodified.
- `src/core/api/rest_api_server.py`, `src/modules/*` REST-layer code
  (EP-043) — zero changes.
- `src/core/workflow_engine/*.py` (EP-033) — zero changes; `.run()` is
  called transitively, unmodified.
- `src/core/plan_execution/*.py`, `src/core/tool/*.py`,
  `src/core/agent/*.py` (EP-028–031) — zero changes; not touched or
  called directly by this design at all.
- `src/services/telegram_service.py`, `src/modules/telegram_module.py`,
  `src/core/telegram/*.py` (EP-012) — zero changes; Telegram shutdown
  coordination is explicitly out of scope (Section 5, Section 0.1).
- `docs/architecture/ARCHITECTURE_DEBT.md` — no entry added, resolved,
  or edited; AD-001/AD-002 remain exactly as filed.
- `docs/architecture/designs/EP059_DESIGN.md` through
  `EP062_DESIGN.md`, and every file under
  `docs/architecture/audits/` — historical record, never edited by a
  later EP's STEP 1/2 in this repository's established convention.
- `tests/EP034/test_workflow_scheduler.py` — re-run unmodified as
  regression (Section 11); any rewrite of its two whitebox-workaround
  tests is explicitly optional, STEP-2-discretionary, not required by
  this design.
- `CHANGELOG.md`, `RELEASE_NOTES.md`, `docs/BACKLOG.md`,
  `docs/architecture/JARVIS_ROADMAP.md` — STEP 4 concerns, per this
  task's own STEP 1 rules; untouched by this document.

---

## 14. Acceptance Criteria

1. `WorkflowSchedulerService.shutdown(wait=True, timeout=None) ->
   bool` exists, is idempotent, and behaves exactly as specified in
   Section 6.1/8.
2. `WorkflowSchedulerService`'s public method set is exactly
   `{register, unregister, start, stop, run, list_entries, get_entry,
   status, shutdown}` (9).
3. `RuntimeService(...)` accepts an optional
   `workflow_scheduler_service` keyword argument; omitting it
   continues to construct a valid instance (`status().
   workflow_scheduler_active is False`).
4. `RuntimeService.status().workflow_scheduler_active` and
   `.workflow_scheduler_entries_registered` correctly mirror a real
   `WorkflowSchedulerService.status()`'s `running`/`entries_registered`
   in both the `auto_start: true` and `auto_start: false` cases.
5. `RuntimeService.shutdown()` stops a real, auto-started
   `WorkflowSchedulerService` as its third of four coordinated steps
   (REST → Scheduler → Workflow Scheduler → Background Workers),
   confirmed via call-order-recording proxies.
6. A tick genuinely in progress at `shutdown()` time is waited for (up
   to `workflow_scheduler.shutdown_timeout`, default 10s) rather than
   abandoned instantly, and `shutdown()` correctly returns `False` if
   that timeout is exceeded.
7. `bootstrap.workflow_scheduler_service` remains non-`None` and
   identity-preserved across `bootstrap.shutdown()`.
8. `runtime status` displays a `Workflow Scheduler : ACTIVE/INACTIVE`
   line (and, when active, an entries-registered line), matching the
   existing `Scheduler`/`Background Workers` lines' formatting
   convention exactly.
9. `WorkflowSchedulerModule._actions` and `RuntimeModule._actions`
   remain exactly `{list, status, run, start, stop, info, help}` and
   `{status, help}` respectively — no new CLI/REST-reachable mutating
   action exists anywhere as a result of this EP.
10. Full regression: `tests/EP034/test_workflow_scheduler.py`,
    `tests/EP059/test_runtime.py`, `tests/EP060/
    test_runtime_lifecycle.py`, `tests/EP061/
    test_scheduler_shutdown.py`, `tests/EP062/
    test_background_worker_status.py`, `tests/EP036/*`,
    `tests/EP043/*` all pass unmodified (except, at STEP 2's
    discretion only, the two named whitebox tests in
    `test_workflow_scheduler.py`).
11. New suite `tests/EP063/test_workflow_scheduler_shutdown.py`
    passes, registered via one new import line in
    `src/modules/test_module.py`.
12. No file outside Section 12's "MODIFY"/"CREATE" lists is changed.

---

## 15. STEP 2 Implementation Boundaries

**STEP 2 is expected to implement exactly:**

- `WorkflowSchedulerService.shutdown()`/`_resolve_shutdown_timeout()`
  (Section 6.1/6.2).
- `RuntimeStatus`/`RuntimeShutdownReport`/`RuntimeService.__init__`/
  `.status()`/`.shutdown()` widening (Section 6.3-6.5).
- The one-line `Bootstrap.initialize()` call-site widening plus a
  `Bootstrap.shutdown()` docstring update (Section 6.6).
- The one new `RuntimeModule._status()` display block (Section 6.7).
- The one new `config/config.yaml` key (Section 6.2).
- The one new `test_module.py` import line and the new
  `tests/EP063/` suite (Section 11).

**STEP 2 must not:**

- Add any CLI/REST-reachable mutating action for either
  `WorkflowSchedulerService` or `RuntimeService` (Owner Decision D1;
  `EP060_DESIGN.md` Owner Decision D3 precedent).
- Touch `WorkflowSchedulerEngine`, `ScheduledWorkflowRegistry`,
  `ScheduledWorkflow`, `WorkflowEngine`, `PlanExecutionEngine`,
  `SchedulerService`, `BackgroundWorkerService`/`Pool`,
  `RestApiServer`, or any Telegram file (Section 13).
- Add a restart/resume capability to `WorkflowSchedulerService`
  (Section 5).
- Attempt to cancel or interrupt an in-progress `WorkflowEngine.run()`
  call (Section 5/8).
- Modify `ARCHITECTURE_DEBT.md`, any prior EP's design/audit document,
  `CHANGELOG.md`, `RELEASE_NOTES.md`, `docs/BACKLOG.md`, or
  `docs/architecture/JARVIS_ROADMAP.md` (those are STEP 4 concerns).
- Rewrite `tests/EP034/test_workflow_scheduler.py`'s two
  whitebox-workaround tests unless doing so purely to use the new
  public `shutdown()` instead of private-attribute access — and even
  then, this is disclosed as optional/STEP-2-discretionary, not
  mandated by this design (Section 11).
- Reopen or resolve `ARCHITECTURE_DEBT.md` AD-001/AD-002, even though
  both concern files this EP also touches — unrelated concerns,
  explicitly out of scope (Section 5, Section 9's own note under
  Section 8).

---

## 16. Final Verification (performed before concluding STEP 1)

- Re-read this complete document end-to-end against the actual
  current source of `src/services/workflow_scheduler_service.py`,
  `src/services/runtime_service.py`, `src/bootstrap.py`,
  `src/modules/runtime_module.py`, `src/modules/
  workflow_scheduler_module.py`, `src/core/workflow_scheduler/
  workflow_scheduler_engine.py`, `src/core/workflow_engine/
  workflow_engine.py`, `src/core/background_workers/
  background_worker_pool.py`, `config/config.yaml`, and
  `tests/EP034/test_workflow_scheduler.py` — every class name, method
  name, field name, config key, default value, and line-range
  reference above was verified directly against this repository's
  actual current content, not assumed from convention.
- Verified Goals do not contradict Non-Goals (e.g. Section 4 item 6's
  new shutdown step vs. Section 5's "no CLI/REST action" — the former
  is internal-only coordination, the latter concerns the CLI/REST
  surface specifically; not a contradiction).
- Verified Owner Decisions (D1-D4) are individually consistent with
  Section 6's proposed design and Section 12's file-impact list — no
  decision implies a file change absent from Section 12, and no file
  in Section 12 lacks a corresponding decision or goal justifying it.
- Verified the STEP 2 file-impact list (Section 12) matches the
  Testing Strategy (Section 11) and Protected Files (Section 13) with
  no overlap or omission.
- Verified no requirement in this document depends on an undocumented
  assumption: every load-bearing factual claim (blocking behavior,
  shared `WorkflowEngine` instance, existing `Bootstrap` attribute,
  test whitebox workaround, config defaults) is cited to a specific,
  re-checked file and, where useful, a line range.
- Verified no prior EP's Owner Decision is contradicted:
  `EP059_DESIGN.md` D3/D4/D5/D6, `EP060_DESIGN.md` D1-D5,
  `EP061_DESIGN.md` D1-D4, and `EP062_DESIGN.md` D1-D3 were each
  re-read; none constrains `WorkflowSchedulerService` at all (all
  explicitly fence it out as "DO NOT MODIFY"/unrelated), so none is
  contradicted by this design widening it for the first time.
- Confirmed that STEP 1 changed **only**
  `docs/architecture/designs/EP063_DESIGN.md`. No production code,
  test, configuration, dependency file, or other documentation file
  was created or modified.
