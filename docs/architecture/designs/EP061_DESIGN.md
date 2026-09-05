# EP-061 — Scheduler Tick-Loop Shutdown

STEP 1: Architecture Discovery & Design

Status: DESIGN PROPOSED — awaiting Owner Decision approval before STEP 2

---

## 0. How this scope was derived

`docs/architecture/JARVIS_ROADMAP.md` and `docs/BACKLOG.md` both state,
verbatim, **"Next Engineering Package: none yet defined"** — EP-060
completed Phase 10 ("Jarvis Operating System"), the roadmap's last
currently-named phase, and no EP-061 or Phase 11 text exists anywhere
in this repository. There is therefore no roadmap line, backlog
entry, or phase heading that names EP-061's scope; per the STEP 1
instructions, that scope must be derived from the repository's actual
architecture and code, not assumed from the package number.

The repository already names its own most natural next candidate.
`docs/architecture/designs/EP060_DESIGN.md` Section 15, Owner Decision
D5, considered adding a public stop method to `SchedulerService`'s
tick loop, rejected it for EP-060 itself (to keep that EP's file scope
minimal), and recommended option (a) with this explicit note:

> "though this document notes (b) is the more *complete* fix for
> Section 5.4's underlying problem, and is **the most natural single
> follow-up EP-061 candidate this document's own discovery surfaces**,
> exactly as EP-059 flagged Candidate B/D as its own follow-ups."

This is confirmed independently in three more places:

- `src/services/scheduler_service.py`'s own docstring and code: a
  `_stop_event` and `_start_tick_loop()` already exist, but there is
  no public counterpart — `_is_tick_loop_running()`,
  `_start_tick_loop()`, and `_tick_loop()` are all private.
- `src/services/runtime_service.py`'s `RuntimeService.shutdown()`
  docstring: *"Deliberately excludes the Scheduler ... adding one
  would mean modifying an already-completed EP's own core file, which
  `EP060_DESIGN.md` Owner Decision D5 treats as a separate, future
  decision, not a default action."*
- `src/bootstrap.py`'s `Bootstrap.shutdown()` docstring: *"The
  Scheduler is deliberately not stopped here — it exposes no public
  shutdown primitive ... `self._scheduler_service` is intentionally
  left unset by this method."*
- `docs/architecture/audits/EP060_ARCHITECTURE_AUDIT.md` independently
  re-confirms D5 as approved-and-deferred, not rejected outright.

This is exactly the kind of "real, code-verified gap" STEP 1 is asked
to find: a concrete, disclosed, already-scoped limitation left behind
by the immediately preceding EP, rather than a speculative new
capability. EP-061 closes it.

**Design-validation note (added after initial STEP 1 draft):** the
data/control flow claims used to justify shutdown ordering (Section 6,
Owner Decision D2) were re-verified directly against
`src/core/scheduler/scheduler.py`, `src/core/execution/engine.py`, and
`src/core/workflow_engine/workflow_engine.py` rather than assumed. The
verified facts materially changed this document's ordering rationale
and are recorded in Section 6 and Owner Decision D2 below, superseding
an earlier, less carefully verified draft of that reasoning.

---

## 1. Problem Statement

`SchedulerService` (EP-011) auto-starts a background daemon thread
(the "tick loop") whenever `scheduler.enabled` and
`scheduler.auto_start` are both `true` — which is the default in
`config/config.yaml` today. That thread has no public way to be
stopped. `SchedulerService` already has a private `_stop_event`
(`threading.Event`) built for exactly this purpose and a private
`_tick_loop()` that already checks it (`while not
self._stop_event.wait(interval)`), but nothing outside the class ever
calls `_stop_event.set()`.

Consequences, all already disclosed in the repository:

- `RuntimeService.shutdown()` (EP-060) — the one coordination point
  that stops the REST API Server and the Background Worker Service at
  process shutdown — cannot also stop the Scheduler, because there is
  nothing public to call.
- `Bootstrap.shutdown()` explicitly leaves `self._scheduler_service`
  untouched, so `SchedulerService`'s tick thread keeps running
  (as a daemon thread) until the OS process itself exits, even after
  every other coordinated subsystem has been asked to stop.
- Every test in `tests/EP060/test_runtime_lifecycle.py` that
  constructs a real, enabled `SchedulerService` must reach into its
  private `_stop_event`/`_tick_thread` fields directly
  (`_stop_scheduler_tick_loop_for_test_cleanup`) to avoid leaking
  daemon threads across test cases — itself a symptom of the missing
  public primitive.

This is a real, narrow, already-scoped gap, not a new feature
invented for this EP.

---

## 2. Current Architecture / Existing Infrastructure

Relevant existing pieces, all reused unchanged except where explicitly
listed in Section 7:

- **`src/services/scheduler_service.py`** (EP-011) — owns the tick
  loop. Already has: `_tick_thread: threading.Thread | None`,
  `_stop_event: threading.Event`, `_lifecycle_lock: threading.Lock`,
  `_start_tick_loop()` (private, idempotent — guarded by
  `_lifecycle_lock`, no-ops if a thread already exists),
  `_tick_loop()` (private, the thread target — exits its `while` loop
  the moment `_stop_event` is set, logs `"Scheduler stopped."`), and
  `_is_tick_loop_running()` (private, `bool`, thread-safe).
- **`src/services/background_worker_service.py`** (EP-036) — the
  direct structural precedent for "a service that owns a background
  execution context and exposes a public, idempotent `shutdown()`":
  `shutdown(wait: bool = True, timeout: float | None = None) -> bool`,
  safe when nothing is running (`self._pool is None` → `True`
  immediately), resolves a config-driven default timeout
  (`background_workers.shutdown_timeout`) when `timeout` is not given.
- **`src/services/runtime_service.py`** (EP-059/EP-060) — already
  holds a `SchedulerService | None` reference
  (`self._scheduler_service`), already reads
  `SchedulerService.status()` in `status()`, and already has a
  `shutdown()` method that coordinates the REST API Server and
  Background Worker Service, in that order, returning a
  `RuntimeShutdownReport`. Its own docstring already documents the
  Scheduler exclusion as the thing this EP removes.
- **`src/bootstrap.py`** (all EPs) — constructs
  `SchedulerService` once (`_build_command_router()`, around line
  2051), stores it as `self._scheduler_service`, exposes it via the
  public `scheduler_service` property (EP-060 Owner Decision D6), and
  passes it into `RuntimeService(...)`. `Bootstrap.shutdown()`
  delegates entirely to `RuntimeService.shutdown()` (EP-060 Owner
  Decision D2) and explicitly does not touch `_scheduler_service`.
- **`src/modules/scheduler_module.py`** (EP-011) — the CLI/REST
  surface for the `scheduler` namespace: `list`, `status`, `doctor`,
  `run`, `start`, `stop` (per-**job** enable/disable, not the tick
  loop), `info`, `help`. Already the pattern EP-060 followed for
  `RuntimeModule`: a widened *service* does not automatically get a
  widened *CLI/REST surface*.
- **`config/config.yaml`** — `scheduler.enabled` (default `true`),
  `scheduler.auto_start` (default `true`), `scheduler.tick_interval`
  (default `1`). No `scheduler.shutdown_timeout` key exists.
- **`tests/EP060/test_runtime_lifecycle.py`** — already contains
  `_build_real_scheduler_service()` and
  `_stop_scheduler_tick_loop_for_test_cleanup()` helpers (the latter
  reaching into `SchedulerService._stop_event`/`_tick_thread`
  directly, `# noqa: SLF001`), and the guard test
  `_test_bootstrap_shutdown_does_not_touch_scheduler_service`.

Nothing above needs to be invented. Every mechanism EP-061 needs
already exists in some form (`_stop_event`, the
`BackgroundWorkerService.shutdown()` naming/shape precedent, the
`RuntimeService.shutdown()` coordination point, the
`RuntimeShutdownReport` dataclass shape) and only needs to be
connected.

### 2.1 Verified Scheduler → ExecutionEngine → BackgroundWorker control flow

Because Owner Decision D2 (Section 17) depends on how Scheduler-driven
work relates to Background-Worker-driven work, the actual call chain
was read directly from source rather than assumed:

- **`Scheduler.tick()`** (`src/core/scheduler/scheduler.py`) computes
  the list of due jobs, then calls `self.run_job(job.id)` for each,
  **synchronously, in a plain Python `for` loop, on the tick thread
  itself**. `run_job()` calls
  `self._execution_engine.run(job.command)` directly — `command` is a
  raw target string (program name, file path, or URL) handed to
  **`src/core/execution/engine.py`'s `ExecutionEngine`** (EP-003)
  unchanged.
- **`ExecutionEngine.run()`** selects an `Executor`
  (`src/core/execution/executors/{process,file,python,url}_executor.py`)
  and delegates to it. None of the four blocks the calling (tick)
  thread waiting for the launched program/file/URL handler to finish:
  `process_executor.py`, `python_executor.py`, and `file_executor.py`
  each call **`subprocess.Popen(...)` with no `.wait()` call**;
  `url_executor.py` instead calls Python's standard-library
  **`webbrowser.open(...)`**, which likewise launches the browser and
  returns immediately without waiting for it to exit — confirmed by
  reading all four executor files directly (STEP 3 audit,
  `EP061_ARCHITECTURE_AUDIT.md` Section 5/D4). A job's execution
  therefore returns to the tick loop almost immediately regardless of
  how long the launched program/file/URL handler itself runs.
- **`BackgroundWorkerService`** (EP-036, `src/services/
  background_worker_service.py`) does **not** use this same
  `ExecutionEngine` at all. It owns a `BackgroundWorkerPool` that runs
  already-registered EP-033 `WorkflowDefinition`s through
  **`WorkflowEngine`** (`src/core/workflow_engine/workflow_engine.py`),
  which in turn delegates each step to **EP-030's
  `PlanExecutionEngine.execute_request()`**
  (`src/core/plan_execution/plan_execution_engine.py`) — an entirely
  separate agent-planning/execution path (`PlanningEngine` +
  `PlanExecutionProvider`), never `src/core/execution/engine.py`'s
  `ExecutionEngine`.

**Conclusion, corrected from an earlier, less carefully verified
draft of this document:** `Scheduler`/`SchedulerService` and
`BackgroundWorkerService` do **not** share a queue, a pool, or an
execution engine. There is no code path by which a Scheduler tick
"feeds work into" the Background Worker Service, or vice versa. The
two are structurally independent; only `ExecutionEngine`'s own
`ProcessRegistry` (EP-003) is a theoretical, deep, indirect point
where a background workflow step invoking a tool that itself launches
a program could touch the same registry a Scheduler job also touches
— this does not create a shutdown-ordering dependency between the two
services, since neither service's `shutdown()` acts on
`ProcessRegistry` at all. Owner Decision D2 (Section 17) is written
against this verified, corrected understanding, not the original
(inaccurate) "same execution/workflow path" claim.

---

## 3. Gap Analysis

| What exists | What's missing |
|---|---|
| `SchedulerService._stop_event` (private) | A public method that sets it |
| `SchedulerService._tick_thread` (private) | A public method that joins it |
| `SchedulerService._is_tick_loop_running()` (private) | Already-public `status().running` reads the same fact — no new read-path needed |
| `RuntimeService.shutdown()` stops REST API + Background Workers | Does not stop Scheduler; `RuntimeShutdownReport` has no Scheduler fields |
| `Bootstrap.shutdown()` delegates to `RuntimeService.shutdown()` | Explicitly documented as leaving `_scheduler_service` unstopped |
| `BackgroundWorkerService.shutdown()` (naming/shape precedent) | `SchedulerService` has no method of this shape at all |
| `SchedulerModule` CLI (`list/status/doctor/run/start/stop/info/help`) | No tick-loop shutdown action — and, per Section 6 below, none should be added |

The missing piece is narrow: **one new public method on
`SchedulerService`** that stops the tick loop, plus **wiring it into
the one coordination point that already exists** for this exact
purpose (`RuntimeService.shutdown()` → `Bootstrap.shutdown()`).

---

## 4. Goals

1. Give `SchedulerService` a public, idempotent way to stop its own
   tick loop, without changing its default-`auto_start` behavior or
   any of its existing public methods' signatures or semantics.
2. Wire that new method into `RuntimeService.shutdown()`, in a fixed
   position in the existing shutdown sequence, so a full
   `Bootstrap.shutdown()` now stops every subsystem it starts
   automatically (REST API Server, Background Worker Service,
   Scheduler).
3. Reflect the new capability in `RuntimeShutdownReport` the same way
   the two existing subsystems are reflected (a `*_was_active`/
   `*_stopped` pair), keeping the dataclass's existing fields and
   their positions unchanged.
4. Preserve every EP-059/EP-060 backward-compatibility guarantee:
   `RuntimeService`'s constructor keyword-defaults, `status()`'s
   shape, and every currently-passing test in `tests/EP059/` and
   `tests/EP060/`.

## 5. Non-Goals

- No CLI/REST-reachable "stop the scheduler" action. Exactly like
  `RuntimeService.shutdown()` itself (EP-060 Owner Decision D3), the
  new `SchedulerService` method is invoked only from the internal
  shutdown coordination path, never exposed through
  `SchedulerModule`/`RuntimeModule`.
- No change to job scheduling semantics. `SchedulerService.stop(job_id)`
  (disable a specific job) is unrelated and untouched; the new method
  stops the tick *thread*, not any job.
- No change to `Scheduler`, `JobRegistry`, `Job`, or `ExecutionEngine`
  in `src/core/scheduler/` — those are Scheduler's own dependencies,
  already excluded from EP-059/EP-060's scope, and remain excluded
  here. This EP touches only `SchedulerService`'s own lifecycle
  wrapper around them.
- No new public restart/resume API. This EP does not add any public
  method to start the tick loop again once `shutdown()` has stopped
  it — `_start_tick_loop()` remains private, called only from
  `__init__`. This matches `BackgroundWorkerService`, which similarly
  exposes no public restart method after `shutdown()`. (This is a
  statement about this EP's public surface, not a claim that the tick
  loop could never technically be restarted by some future,
  separately-scoped EP — see Section 5's Telegram note for the same
  "separately scoped, not ruled out" framing applied elsewhere in this
  document.)
- No new `scheduler.*` configuration key (see Section 10).
- Telegram's own analogous gap (`docs/architecture/designs/
  EP060_DESIGN.md` Section 5.9, D4) is out of scope — that is a
  different subsystem with its own separate service, not touched or
  implied by this design.

---

## 6. Proposed Architecture

No new module, class, package, registry, or abstraction is
introduced. This EP is a narrow, additive widening of three already-
existing files, following the exact structural precedent
`BackgroundWorkerService.shutdown()` already set for "a service with
a background execution context gains a public, idempotent shutdown
method":

```
Bootstrap.shutdown()
        |
        v
RuntimeService.shutdown()  (already exists, EP-060)
        |
        +--> 1. RestApiServer.stop()                  (unchanged, EP-043)
        +--> 2. SchedulerService.shutdown()             <-- NEW (EP-061),
        |            |                                     reuses the
        |            v                                     already-
        |        _stop_event.set()                         existing
        |        _tick_thread.join(timeout)                _stop_event
        +--> 3. BackgroundWorkerService.shutdown()     (unchanged, EP-036)
```

`SchedulerService.shutdown()` does exactly what
`BackgroundWorkerService.shutdown()` does for its own background
context: it is a thin, idempotent stop primitive over an
already-existing private mechanism, added to the class that already
owns that mechanism — not a new orchestrator, not a new lifecycle
abstraction, not a change to how/when the tick loop *starts*.

Ordering decision (see Owner Decision D2, Section 17, revised after
verifying the actual control flow in Section 2.1): Section 2.1
confirms `Scheduler` and `BackgroundWorkerService` are structurally
independent — the Scheduler executes jobs synchronously through
EP-003's `ExecutionEngine` (whose executors never block waiting for
the launched program/file/URL/browser to finish), while Background
Workers run EP-033 `WorkflowDefinition`s through EP-030's
`PlanExecutionEngine`; neither feeds the other. There is therefore no
correctness dependency requiring one to stop before the other. The
chosen order instead follows one consistent principle already present
in `RuntimeService.shutdown()`'s own existing
rationale: **silence every source of *new* triggered work before
draining work that was already accepted.** The REST API Server (an
external, network-reachable *new*-work trigger) and the Scheduler's
tick loop (an internal, automatic *new*-work trigger) are stopped
first, in that order; the Background Worker Service — which drains
*already-submitted/running* tasks and may legitimately take up to its
own configured `background_workers.shutdown_timeout` (no fixed, short
bound) — is shut down last, so it is not left running the entire time
new Scheduler-triggered job executions could still be arriving.

---

## 7. Detailed Component Changes

### 7.1 `src/services/scheduler_service.py` (EP-011 — first non-purely-additive precedent already set by EP-060 for `bootstrap.py`; here the touch to this specific file is purely additive)

Add one new public method:

```python
def shutdown(self, wait: bool = True, timeout: float | None = None) -> bool:
    """Stop the background tick loop, if one is running.

    Safe to call regardless of whether the tick loop was ever
    started (e.g. 'scheduler.auto_start: false', or already
    stopped) -- reports success immediately since there is nothing
    to stop. Does not affect any registered Job's enabled/disabled
    state, and does not prevent 'scheduler run <job>' from being
    called manually afterward -- only the automatic tick loop is
    stopped.

    Args:
        wait: If True (default), block until the tick thread has
            exited or `timeout` elapses. If False, signal the stop
            and return immediately without joining.
        timeout: Maximum seconds to wait when `wait` is True.
            Defaults to this class's resolved shutdown timeout
            (see `_resolve_shutdown_timeout`, Section 10) when not
            given explicitly.

    Returns:
        True if the tick loop is confirmed not running after this
        call (including if it was never running to begin with);
        False if `wait=True` and the thread did not exit within
        `timeout`.
    """
    with self._lifecycle_lock:
        thread = self._tick_thread
        if thread is None:
            return True
        self._stop_event.set()

    if not wait:
        return not thread.is_alive()

    resolved_timeout = timeout if timeout is not None else self._shutdown_timeout
    thread.join(timeout=resolved_timeout)
    stopped = not thread.is_alive()
    if stopped:
        with self._lifecycle_lock:
            if self._tick_thread is thread:
                self._tick_thread = None
    return stopped
```

**Lock-scope design note (verified during implementation review):**
`_lifecycle_lock` is held only long enough to read `self._tick_thread`
and call `_stop_event.set()` — **not** across `thread.join()`.
`_start_tick_loop()` already serializes on the same lock, so this
still prevents a concurrent start/stop race; but a naive
implementation that held the lock for the full, potentially
multi-second `join()` call would also block any concurrent
`status()`/`doctor()` call (both call `_is_tick_loop_running()`,
which also takes `_lifecycle_lock`) for that entire duration, for no
correctness benefit — `Thread.join()` is safe to call without holding
any lock, and safe to call concurrently from multiple threads on the
same `Thread` object. The final `self._tick_thread = None` reset is
re-guarded by `if self._tick_thread is thread`, defensively handling
two concurrent `shutdown()` calls joining the same thread (both are
safe; only the first to re-acquire the lock actually clears the
attribute, and the identity check avoids a second, stale caller
clearing a hypothetical newer thread object).

Add, in `__init__`, one new attribute (mirroring
`BackgroundWorkerService._shutdown_timeout`):

```python
self._shutdown_timeout = self._resolve_shutdown_timeout()
```

placed before the existing `if bool(self._config.get("scheduler.enabled", ...))` auto-start block (construction order:
config/scheduler refs → new lifecycle fields, including the timeout →
conditional auto-start — the auto-start call itself is unmoved).

Add one new private helper, structurally identical to
`BackgroundWorkerService._resolve_shutdown_timeout` but with its own
hardcoded default (Section 10 explains why no new config key is
read):

```python
_DEFAULT_SHUTDOWN_TIMEOUT: float = 5.0

def _resolve_shutdown_timeout(self) -> float:
    """Return the fixed tick-loop join timeout.

    Unlike 'background_workers.shutdown_timeout', no
    'scheduler.shutdown_timeout' configuration key is read (Section
    10 of EP061_DESIGN.md) -- the tick loop's own `_stop_event.wait()`
    unblocks immediately once `_stop_event.set()` is called,
    regardless of `scheduler.tick_interval`, so a short, fixed join
    timeout is a defensive bound, not a tunable operational setting.
    """
    return self._DEFAULT_SHUTDOWN_TIMEOUT
```

`_start_tick_loop()`, `_tick_loop()`, `_is_tick_loop_running()`,
`status()`, `doctor()`, `register()`, `unregister()`, `start()`,
`stop()`, `run()`, `list_jobs()`, `get_job()`, `_ensure_enabled()` —
**all unchanged, byte-identical.**

### 7.2 `src/services/runtime_service.py` (EP-059/EP-060)

`RuntimeShutdownReport` gains two new fields, appended after the
existing four (append-only, matching `RuntimeStatus`'s own EP-060
precedent of appending new fields rather than inserting them):

```python
scheduler_was_active: bool = False
scheduler_stopped: bool = True
```

Defaulted so the one existing internal construction call site (the
only call site, per Section 0's confirmation there are no external
construction sites) continues to work either way; the defaults are
chosen to match "nothing to do" semantics, exactly like
`background_workers_stopped`'s existing default-true framing for the
disabled case.

`RuntimeService.shutdown()`'s body gains one new block, inserted
**between** the existing REST API Server block and the existing
Background Worker Service block (Section 6/Owner Decision D2's
verified ordering: silence new-work triggers — REST API, then
Scheduler — before draining already-accepted work — Background
Workers, last):

```python
rest_api_was_active = (
    self._rest_api_server is not None and self._rest_api_server.is_running
)
if self._rest_api_server is not None:
    self._rest_api_server.stop()
rest_api_stopped = (
    self._rest_api_server is None or not self._rest_api_server.is_running
)

# NEW (EP-061): stopped second -- after the external REST trigger,
# before draining the Background Worker Service (Section 6).
scheduler_was_active = False
if self._scheduler_service is not None:
    scheduler_was_active = self._scheduler_service.status().running
scheduler_stopped = True
if self._scheduler_service is not None:
    scheduler_stopped = self._scheduler_service.shutdown()

background_workers_was_active = False
if self._background_worker_service is not None:
    background_workers_was_active = self._background_worker_service.status().running
background_workers_stopped = True
if self._background_worker_service is not None:
    background_workers_stopped = self._background_worker_service.shutdown()

return RuntimeShutdownReport(
    rest_api_was_active=rest_api_was_active,
    rest_api_stopped=rest_api_stopped,
    background_workers_was_active=background_workers_was_active,
    background_workers_stopped=background_workers_stopped,
    scheduler_was_active=scheduler_was_active,
    scheduler_stopped=scheduler_stopped,
)
```

Note the deliberate distinction between **execution order** (REST API
→ Scheduler → Background Workers, matching the call sequence above)
and **field declaration order** in `RuntimeShutdownReport` (the two
new `scheduler_*` fields are still appended after the four existing
fields, not inserted between them — Section 7.2/13 keeps them last in
the dataclass purely for backward-compatibility safety, in case any
future code ever constructs this dataclass positionally; today's one
call site, shown above, is entirely keyword-based, so this is a
defensive convention, not a functional requirement).

The method's docstring is updated to remove the now-outdated
"Deliberately excludes the Scheduler" paragraph and describe the new,
three-subsystem ordering instead. No other part of `RuntimeService`
changes: `status()`, `RuntimeStatus`, the constructor signature, and
`RuntimeService`'s public-surface guarantee (`{status, shutdown}`,
unchanged — still exactly two public methods) are all untouched.

### 7.3 `src/bootstrap.py`

`Bootstrap.shutdown()`'s docstring is updated to remove the
"deliberately not stopped here" claim about the Scheduler and
describe the new behavior. Its **body is unchanged** — it already
delegates unconditionally to `self._runtime_service.shutdown()`,
which now, transitively, also stops the Scheduler. No new attribute,
no new property, no change to `_build_command_router()`'s existing
`SchedulerService(...)`/`RuntimeService(...)` construction sites.

One deliberate non-change: `Bootstrap.shutdown()` does **not** null
out `self._scheduler_service` the way it nulls `_rest_api_server` and
`_background_worker_service`. `SchedulerService` remains a valid,
usable object after its tick loop is stopped — `status()`, `doctor()`,
`list_jobs()`, and manual `run(job_id)` all continue to work exactly
as `BackgroundWorkerService`'s own non-tick-loop methods would if
called after `shutdown()` (i.e., they still run, they just have no
automatic execution behind them). Nulling the reference would be a
false signal that the object itself is gone, which it is not. See
Owner Decision D3, Section 17.

### 7.4 Not modified

- `src/modules/scheduler_module.py` (no new CLI action — Section 6,
  Owner Decision D1).
- `src/modules/runtime_module.py` (no new CLI/REST action — matches
  its own EP-060 Owner Decision D3 precedent exactly; `RuntimeModule`'s
  status formatting already prints the Scheduler line from `status()`,
  which is unaffected by this EP).
- `src/core/scheduler/*.py` (`Scheduler`, `JobRegistry`, `Job`,
  `ExecutionEngine`) — completely untouched.
- `config/config.yaml` — no key added or changed (Section 10).
- `requirements.txt`, `pyproject.toml` — no dependency change.
- `docs/BACKLOG.md`, `CHANGELOG.md`, `docs/RELEASE_NOTES.md`,
  `docs/architecture/JARVIS_ROADMAP.md` — STEP 1 does not modify
  these (only STEP 2/STEP 4, per the standard EP process this
  repository already follows, would update them).

---

## 8. Data / Control Flow

Normal process shutdown, after this EP:

1. `main.py`'s exit path (or a test) calls `Bootstrap.shutdown()`.
2. `Bootstrap.shutdown()` calls `self._runtime_service.shutdown()`
   (unchanged call site).
3. `RuntimeService.shutdown()`, in order (Section 6, Owner Decision
   D2):
   a. Reads and stops `RestApiServer` (unchanged) — closes the
      external, network-reachable trigger first.
   b. **New:** reads `SchedulerService.status().running`, then calls
      `SchedulerService.shutdown()` — closes the internal, automatic
      trigger second.
   c. Reads and shuts down `BackgroundWorkerService` (unchanged) —
      drains already-accepted background work last.
4. `SchedulerService.shutdown()` sets `_stop_event`. If the tick
   thread is currently blocked in `_stop_event.wait(interval)` (the
   idle case between ticks), it returns `True` immediately regardless
   of the configured `tick_interval`. If the tick thread is instead
   mid-tick — inside `Scheduler.tick()`'s `for job in due:` loop,
   already past the `wait()` call — it finishes executing that
   batch's due jobs first (each a fast, non-blocking
   `ExecutionEngine.run()` call, per Section 2.1) before it next
   reaches `_stop_event.wait()`, sees it already set, and exits the
   `while` loop; `"Scheduler stopped."` is logged (existing log line,
   `_tick_loop()` unchanged). `shutdown()` then joins the thread,
   bounded by `timeout` (Section 10, Owner Decision
   D4), before returning.
5. `RuntimeService.shutdown()` returns a `RuntimeShutdownReport` with
   all three subsystems' before/after facts.
6. `Bootstrap.shutdown()` returns; `self._scheduler_service` still
   refers to the same (now tick-loop-stopped) `SchedulerService`
   instance.

No new data crosses a process/network boundary; no new event is
published (the existing `orchestrator.started`/`orchestrator.stopped`
EventBus hooks remain unused and out of scope, exactly as EP-060
found them).

---

## 9. API / Public Surface Changes

| Component | Before | After |
|---|---|---|
| `SchedulerService` public methods | `register, unregister, start, stop, run, list_jobs, get_job, status, doctor` (9) | + `shutdown` (10) |
| `RuntimeService` public methods | `status, shutdown` (2) | unchanged (2) |
| `RuntimeShutdownReport` fields | 4 | 6 (2 appended) |
| `RuntimeStatus` fields | unchanged | unchanged |
| `SchedulerModule` CLI actions | `list, status, doctor, run, start, stop, info, help` (8) | unchanged (8) |
| `RuntimeModule` CLI actions | `status, help` (2) | unchanged (2) |
| REST surface (via `ApiRouter`/`RestApiServer`) | forwards whatever `CommandRouter` exposes | unchanged — no new module action means no new reachable endpoint |
| `Bootstrap` public properties | includes `scheduler_service` (EP-060) | unchanged |

---

## 10. Configuration Changes

**None required**, and none proposed. `SchedulerService.shutdown()`'s
join timeout is a small hardcoded constant
(`_DEFAULT_SHUTDOWN_TIMEOUT = 5.0`), not a new `scheduler.*` config
key, because:

- The tick loop's `_stop_event.wait(interval)` call returns as soon as
  `_stop_event.set()` is called — it does not wait out the remaining
  `tick_interval`. The only real work the join can be bounding is a
  tick already in progress at the moment `shutdown()` is called
  (Section 8, step 4) — and Section 2.1 verified that every job
  execution in that path (`Scheduler.run_job()` →
  `ExecutionEngine.run()` → an `Executor`) launches without blocking
  on the launched program/file/URL's own completion: three of the four
  executors (`process_executor.py`, `python_executor.py`,
  `file_executor.py`) use non-blocking `subprocess.Popen()` with no
  `.wait()`, and the fourth (`url_executor.py`) uses the standard
  library's `webbrowser.open()`, which is likewise fire-and-forget.
  So even a full batch of due jobs in one tick returns to the loop
  quickly, and this timeout is not bounding arbitrary, long-running
  external execution through any of the four executor paths. Unlike
  `BackgroundWorkerService.shutdown()`'s timeout (which bounds
  *arbitrary, potentially long-running submitted tasks* draining to
  completion), this timeout bounds only brief, verified-fast, in-
  process overhead — not arbitrary external work. A configurable value
  would have no realistic operational use.
- This keeps the "only if genuinely required" bar from the STEP 1
  instructions: adding a config key here would be process for its own
  sake, not a genuine need.

If a future EP finds the fixed 5-second bound insufficient (e.g. a
`_tick_loop()` iteration doing slow, blocking work inside
`Scheduler.tick()`), that would be a new, separately-scoped decision —
not assumed here.

---

## 11. Dependency Changes

None. No new package, no version bump.

---

## 12. Testing Strategy

New suite: `tests/EP061/test_scheduler_shutdown.py`, self-contained
(no import from `tests/EP059/` or `tests/EP060/`, matching both
suites' own "per-EP self-containment" precedent), using the existing
`src/testing/base_test.py` (`BaseTest`) / `src/testing/registry.py`
(`TestRegistry`) framework, real objects throughout (no mocks),
matching `tests/EP060/test_runtime_lifecycle.py`'s own style —
including reusable local builders analogous to
`_build_real_scheduler_service`.

Coverage required:

1. **`SchedulerService.shutdown()` in isolation**
   - Never started (`scheduler.auto_start: false`) → `shutdown()`
     returns `True` immediately, no thread ever existed.
   - Started (`auto_start: true`) → `shutdown()` returns `True`, and
     `_is_tick_loop_running()`/`status().running` is `False`
     afterward (asserted through the already-public `status()`, not
     by reaching into private state).
   - Idempotent: calling `shutdown()` twice in a row, second call
     also returns `True`, does not raise, does not hang.
   - `wait=False` returns promptly without blocking on `thread.join`.
   - A real `Scheduler.tick()` continues to be callable manually
     (`SchedulerService.run(job_id)`) after `shutdown()` — confirms
     only the automatic loop stopped, not the service itself.
2. **`RuntimeService.shutdown()` widened behavior**
   - All-`None` dependencies (including no `scheduler_service`) →
     unchanged existing behavior, `scheduler_was_active=False`,
     `scheduler_stopped=True`.
   - Real, running `SchedulerService` supplied → after
     `RuntimeService.shutdown()`, `scheduler_service.status().running`
     is `False`; `RuntimeShutdownReport.scheduler_was_active` is
     `True` and `.scheduler_stopped` is `True`.
   - Ordering: REST API Server is confirmed stopped before the
     Scheduler's tick loop, and the Scheduler's tick loop is confirmed
     stopped before Background Worker Service shutdown is invoked
     (Section 6/Owner Decision D2's verified REST → Scheduler →
     Background Workers sequence) — via a recording wrapper/spy
     around each of the three calls that captures call order, matching
     how EP-060's own suite proved REST-API-before-Background-Workers
     ordering.
   - Idempotency of the full three-subsystem `shutdown()`.
   - Lock-scope regression guard: a `shutdown()` call blocked inside
     `thread.join()` (simulated with a slow-but-bounded tick body, or
     a short artificial delay before the thread checks the stop event)
     does not block a concurrent `status()`/`doctor()` call — proving
     `_lifecycle_lock` is not held across the join itself (Section
     7.1's lock-scope design note).
3. **`Bootstrap` end-to-end**
   - `Bootstrap.initialize()` → `bootstrap.scheduler_service.status().running`
     is `True` (with `scheduler.auto_start: true` in the test config).
   - `Bootstrap.shutdown()` → `bootstrap.scheduler_service.status().running`
     is `False`, **and** `bootstrap.scheduler_service is` the same
     object as before (reference not nulled — Section 7.3, Owner
     Decision D3).
   - `Bootstrap.shutdown()` called twice does not raise and does not
     hang.
   - `Bootstrap.shutdown()` called without `initialize()` first does
     not raise (matches the existing
     `_test_bootstrap_shutdown_safe_without_initialize` precedent).
4. **Public-surface guards**
   - `SchedulerService`'s public method set is exactly the previous
     nine plus `shutdown` (ten total) — an explicit `dir()`/`inspect`
     based assertion, matching `tests/EP060/test_runtime_lifecycle.py`'s
     own `{status, shutdown}` surface-guard pattern, so a future EP
     cannot silently widen this further without a visible test
     failure.
   - `SchedulerModule`'s CLI action set is unchanged (still the
     original eight — no `shutdown` action leaked into the CLI/REST
     surface).
   - `RuntimeModule`'s CLI action set is unchanged (still `{status,
     help}`).

Full regression, reproduced exactly (matching the standard this
repository's own EPs already hold themselves to): `tests/EP059/
test_runtime.py`, `tests/EP060/test_runtime_lifecycle.py`,
`tests/EP036/*`, `tests/EP036-STEP2/*` / `EP036-STEP3/*` (if present
under those names), `tests/EP043/*`, `tests/EP011`-equivalent
scheduler tests if any exist under a different path — a repository
search for pre-existing `SchedulerService`/`Scheduler` test coverage
is required at STEP 2 start to confirm the exact full regression list
before implementation begins.

**One pre-existing test requires a disclosed, narrow update, not a
new failure to silently work around:**
`tests/EP060/test_runtime_lifecycle.py::
_test_bootstrap_shutdown_does_not_touch_scheduler_service`'s own
*comment* ("Owner Decision D5: Scheduler is observed, not controlled")
becomes stale prose once D5 is revisited by this EP — but critically,
**its assertions do not need to change**: the test only asserts
`bootstrap.scheduler_service is not None` and identity-preservation
across `shutdown()`, both of which remain true under this design
(Section 7.3 explicitly keeps the reference alive; only the internal
tick thread is stopped). STEP 2 must update the comment to explain the
new reality (tick loop now stopped, reference deliberately still not
nulled, for the reason given in Section 7.3) without weakening,
skipping, or deleting any assertion — the same "make the test agree
with the newly-approved contract, don't weaken it" discipline EP-060's
own STEP 4 applied to `tests/EP059/test_runtime.py`.

The existing `_stop_scheduler_tick_loop_for_test_cleanup()` helper in
`tests/EP060/test_runtime_lifecycle.py` (which reaches into
`SchedulerService._stop_event`/`_tick_thread` directly,
`# noqa: SLF001`) may optionally be simplified in STEP 2 to call the
new public `shutdown()` instead — a cleanup-only, non-functional
change to a test helper, not a new test requirement, and not
mandatory for this EP's acceptance criteria.

---

## 13. Backward Compatibility

- `SchedulerService.__init__`'s signature, defaults, and auto-start
  behavior are completely unchanged — this EP adds one field and one
  method, both purely additive.
- Every existing `SchedulerService` public method
  (`register/unregister/start/stop/run/list_jobs/get_job/status/doctor`)
  is untouched, same signature, same behavior.
- `RuntimeService.__init__`'s signature is untouched (no change at
  all — the Scheduler reference is already an existing, EP-060
  keyword-defaulted parameter; this EP only changes what
  `shutdown()` *does* with an already-accepted dependency).
- `RuntimeShutdownReport`'s four existing fields keep their names,
  types, and defaults; two new fields are appended. The dataclass has
  exactly one construction call site in the entire repository (Section
  0), so no external code can be broken by the addition.
- `Bootstrap.shutdown()`'s signature (`() -> None`) and its
  already-existing "safe to call twice / safe without `initialize()`"
  guarantees are unchanged; the only observable behavioral difference
  is that the Scheduler's tick loop is now also stopped.
- No REST endpoint, CLI command, or module action set changes size —
  see Section 9's table.
- One pre-existing test's *comment* (not its assertions) needs
  updating, disclosed explicitly in Section 12.

---

## 14. Failure / Edge Cases

- **`shutdown()` called when the tick loop was never started**
  (`auto_start: false`, or `enabled: false`): `self._tick_thread is
  None` → returns `True` immediately, matching
  `BackgroundWorkerService.shutdown()`'s own "nothing to do counts as
  success" precedent.
- **`shutdown()` called twice**: first call joins and clears
  `self._tick_thread` back to `None` on success; second call sees
  `None` and returns `True` immediately. If the first call's join
  timed out (`stopped=False`), `self._tick_thread` is deliberately
  *not* cleared, so a second call will attempt to join the same
  (still-alive) thread again — consistent, does not silently claim a
  false success on retry.
- **`shutdown()` called while a tick is already in progress**
  (verified in Section 2.1/8): `_stop_event.set()` does not interrupt
  the currently-executing `for job in due:` loop inside
  `Scheduler.tick()` — the thread finishes that batch's job
  executions (each a fast, non-blocking `ExecutionEngine.run()` call —
  Section 2.1) before it next checks `_stop_event`. `shutdown()`'s
  `join(timeout=...)` correctly waits out this window; it is not a
  bug, and the fixed 5-second
  default (Section 10) is sized to comfortably cover it given the
  verified non-blocking executor behavior.
- **Join timeout exceeded** (e.g. an unusually large batch of due jobs
  in one tick, or a future executor that blocks — defensive bound,
  not expected in today's code — Section 10): returns `False`.
  `RuntimeService.shutdown()` forwards this `False` into
  `RuntimeShutdownReport.scheduler_stopped` unchanged, exactly as it
  already forwards `BackgroundWorkerService.shutdown()`'s own possible
  `False`. No exception is raised or swallowed.
- **`Scheduler.tick()` raises inside the loop at the moment of
  shutdown**: unaffected — `_tick_loop()`'s existing
  `except Exception` guard (unchanged) already logs and continues
  until `_stop_event` is set; this EP does not touch that guard.
- **Concurrent `shutdown()` calls from two threads**: both take
  `self._lifecycle_lock` (already used by `_start_tick_loop()` for the
  same reason), serializing them — the second sees either `None`
  (already cleared) or the same thread object and joins it too,
  neither raising.
- **`RuntimeService.shutdown()` with `self._scheduler_service is
  None`** (Scheduler subsystem disabled this run): unchanged shape —
  `scheduler_was_active=False`, `scheduler_stopped=True`, exactly
  mirroring the existing all-`None`-dependency behavior for REST
  API/Background Workers.

---

## 15. Security / Safety Considerations

None beyond what already exists. No new network-reachable surface is
added (Section 9); the new method is reachable only from the same
internal `Bootstrap.shutdown()` → `RuntimeService.shutdown()` call
chain that already exists and is already internal-only (EP-059 Owner
Decision D3, EP-060 Owner Decision D3, both unchanged). No user input,
file, or network data is newly parsed or trusted.

---

## 16. File-Level Change Scope

**Changed (STEP 2):**

- `src/services/scheduler_service.py` — additive: one new field, one
  new private helper, one new public method.
- `src/services/runtime_service.py` — additive: two new
  `RuntimeShutdownReport` fields (appended, defaulted), one new block
  inside the existing `shutdown()` body, docstring updates.
- `src/bootstrap.py` — docstring-only change to `shutdown()`; body
  unchanged.
- `tests/EP061/test_scheduler_shutdown.py` — new file (STEP 2).
- `tests/EP060/test_runtime_lifecycle.py` — one comment-only update
  inside `_test_bootstrap_shutdown_does_not_touch_scheduler_service`
  (Section 12); no assertion changes.

**Explicitly protected — must remain untouched:**

- `src/core/scheduler/scheduler.py`, `job.py`, `job_registry.py`,
  `execution_engine`-related files under `src/core/scheduler/`.
- `src/modules/scheduler_module.py`, `src/modules/runtime_module.py`.
- `src/services/background_worker_service.py`,
  `src/core/api/rest_api_server.py` (only their already-existing
  `shutdown()`/`stop()` are called, unchanged).
- `config/config.yaml`, `requirements.txt`, `pyproject.toml`.
- `tests/EP059/test_runtime.py` (re-run as regression only).
- Every other existing `SchedulerService` public method's body.
- `docs/BACKLOG.md`, `CHANGELOG.md`, `docs/RELEASE_NOTES.md`,
  `docs/architecture/JARVIS_ROADMAP.md` (STEP 1 does not touch these;
  future STEPs of the standard process would).

**This STEP 1 change scope:** only
`docs/architecture/designs/EP061_DESIGN.md` (this file).

---

## 17. Owner Decisions

### D1 — Should the new tick-loop stop capability be exposed through `SchedulerModule`'s CLI/REST surface, in addition to internal shutdown coordination?

**Decision:** No. Add `SchedulerService.shutdown()` for internal use
only (called exclusively from `RuntimeService.shutdown()`); do not
add a `scheduler shutdown`/`scheduler stop-loop` CLI action.
**Alternatives considered:** (a) as decided — internal-only; (b) add
a CLI/REST-reachable action, symmetric with `background_workers`
having no CLI stop action either (background workers are also
internal-only via `RuntimeService.shutdown()`), so (b) would actually
be *asymmetric* with the precedent, not matching it.
**Why (a) is preferred:** `RuntimeService.shutdown()` itself is
internal-only by EP-060 Owner Decision D3 specifically to avoid
"unauthenticated REST-reachable process control" as a new risk
surface (`RuntimeModule`'s own status/help-only CLI action set, and
`EP059_DESIGN.md`'s documented lack of REST authentication generally).
A CLI-reachable Scheduler stop would reintroduce exactly the risk
EP-060 avoided, for a capability (stopping automatic job execution)
that is arguably more operationally sensitive than reading runtime
status.
**Architectural consequences:** `SchedulerModule`'s CLI action count
stays at eight; the only way to stop the tick loop remains full
process shutdown via `Bootstrap.shutdown()`.

### D2 — Where should the Scheduler be stopped relative to the REST API Server and Background Worker Service in `RuntimeService.shutdown()`'s sequence?

**Decision:** Second — after the REST API Server, before the
Background Worker Service. (This revises this document's own initial
draft, which had proposed "last"; see the verification note below.)
**Alternatives considered:** (a) last (after both — the initial draft
proposal); (b) first, before REST API Server; (c) as decided — between
REST API Server and Background Worker Service.
**Verification performed:** the initial draft's rationale for (a)
rested on a claim — that Scheduler ticks run jobs "through the same
execution/workflow path Background Workers may also use" — which
Section 2.1 shows is factually incorrect. Reading
`src/core/scheduler/scheduler.py`,
`src/core/execution/engine.py`/`executors/*.py`, and
`src/core/workflow_engine/workflow_engine.py` directly confirms
`Scheduler` executes jobs synchronously through EP-003's
`ExecutionEngine` (whose executors never block on the launched
program/file/URL's own completion), while
`BackgroundWorkerService` runs EP-033 workflows through EP-030's
`PlanExecutionEngine` — two structurally independent paths with no
queue or pool in common. There is therefore no correctness dependency
that requires the Scheduler to be stopped either before or after
Background Workers; option (a)'s implicit justification does not
hold.
**Why (c) is preferred over (a) and (b), given no correctness
dependency exists:** with the false dependency removed, the tie-break
is which ordering best matches `RuntimeService.shutdown()`'s own
already-established principle — silence sources of *new* triggered
work before draining work that was already accepted. The REST API
Server (external, new-work trigger) and the Scheduler (internal,
automatic, new-work trigger) both fit that description; the
Background Worker Service does not trigger new work, it drains
already-submitted/running work and may legitimately take up to its
own, separately configured `background_workers.shutdown_timeout`
(unbounded relative to Scheduler's fixed ~5s bound — Section 10).
Placing the Scheduler last (option a) would mean the tick loop keeps
firing new, synchronous job executions for the entire, potentially
much longer Background Worker drain window, for no benefit now that
the "same execution path" justification is known to be false. Placing
it first, before the REST API Server (option b), would leave a window
in which an external HTTP-triggered `scheduler run <job>` (reachable,
unauthenticated, through `ApiRouter.dispatch_command()` →
`CommandRouter.dispatch()`, confirmed in `src/core/api/api_router.py`)
could still be issued after the Scheduler's own automatic loop has
already stopped, which is a more surprising order for an operator
than closing the external trigger first. Option (c) closes both
new-work triggers, external first then internal, and only then drains
already-accepted work.
**Architectural consequences:** `RuntimeService.shutdown()`'s body
places the new Scheduler block between the existing REST API Server
and Background Worker Service blocks (Section 7.2). Field
*declaration* order in `RuntimeShutdownReport` is kept separate from
this execution order for backward-compatibility reasons (Section 7.2's
note) — the two new fields are still appended after the four existing
ones in the dataclass definition, even though the Scheduler is
stopped second, not last, at runtime. A three-way mutation-order test
(Section 12) enforces the REST → Scheduler → Background-Workers
sequence going forward.

### D3 — Should `Bootstrap.shutdown()` null out `self._scheduler_service` after stopping its tick loop, matching what it already does for `_rest_api_server`/`_background_worker_service`?

**Decision:** No — leave `self._scheduler_service` (and the public
`scheduler_service` property) populated after `shutdown()`.
**Alternatives considered:** (a) as decided — keep the reference;
(b) null it out, matching REST API Server/Background Worker Service
exactly, for full symmetry.
**Why (a) is preferred:** `RestApiServer`/`BackgroundWorkerService`
are nulled because, once stopped, calling almost anything else on
them either does nothing meaningful or (for the REST API Server)
cannot be restarted through the object that's being discarded anyway.
`SchedulerService`, by contrast, remains a fully functional object
after `shutdown()` — `status()`, `doctor()`, `list_jobs()`,
`get_job()`, and manual `run(job_id)` all continue to be meaningful
and correct (this mirrors `BackgroundWorkerService` itself, which
*also* is not discarded by `Bootstrap.shutdown()` — only
`_background_worker_service` is nulled, and that is arguably option
(b)'s actual behavior being copied incorrectly, since
`BackgroundWorkerService` itself has no "is this object still usable"
distinction from `SchedulerService` here). Nulling
`self._scheduler_service` would make `bootstrap.scheduler_service`
report `None` even though a perfectly usable object still exists,
breaking `doctor()`/`status()`/manual `run()` access after shutdown
for no correctness benefit. This also keeps the existing
`_test_bootstrap_shutdown_does_not_touch_scheduler_service` guard test
passing by assertion (only its comment needs updating — Section 12).
**Architectural consequences:** `Bootstrap.shutdown()`'s body requires
zero changes (Section 7.3) — only its docstring is updated. This is
the reason D3, uniquely among this EP's decisions, requires no source
change at all, only a documentation one.

### D4 — Should `SchedulerService.shutdown()`'s join timeout be a new `scheduler.shutdown_timeout` config key, mirroring `background_workers.shutdown_timeout`, or a fixed constant?

**Decision:** Fixed constant (`_DEFAULT_SHUTDOWN_TIMEOUT = 5.0`
seconds), not a new config key.
**Alternatives considered:** (a) as decided — constant; (b) new
`scheduler.shutdown_timeout` config key, resolved the same way
`background_workers.shutdown_timeout` is.
**Why (a) is preferred:** `background_workers.shutdown_timeout`
exists because submitted background tasks are arbitrary,
user/workflow-defined work of unbounded duration — the timeout bounds
a genuine, variable wait. The Scheduler's tick loop, by contrast,
blocks only on `_stop_event.wait(interval)`, which returns
essentially instantly once the event is set, regardless of
`tick_interval` — the join timeout here bounds ordinary thread
scheduling latency, not application work. A configuration key with no
realistic scenario in which changing it would matter fails the STEP 1
instruction to add configuration "only if genuinely required."
**Architectural consequences:** `config/config.yaml`'s `scheduler:`
section is untouched by this EP (Section 10); if a future EP makes
`_tick_loop()` itself perform slow, blocking work per iteration, that
future EP — not this one — would be the right place to reconsider a
configurable timeout, since it would be reacting to a newly introduced
need, not a currently existing one.

---

## 18. Acceptance Criteria

STEP 2 is complete and correct only if all of the following hold:

1. `SchedulerService` gains exactly one new public method
   (`shutdown`), with the signature and semantics specified in
   Section 7.1 — verified by an explicit public-surface count/name
   test (Section 12.4).
2. Every existing `SchedulerService` public method's behavior is
   provably unchanged (full regression pass on any pre-existing
   Scheduler-related test suite discovered at STEP 2 start).
3. `RuntimeService.shutdown()`, given a real, running `SchedulerService`,
   results in `scheduler_service.status().running is False`
   afterward, confirmed via the public `status()` API only (no
   reaching into private state from non-test, non-cleanup code).
4. `RuntimeShutdownReport` gains exactly the two fields specified in
   Section 7.2, both appended, both defaulted, with every existing
   field's name/type/default unchanged.
5. `RuntimeService`'s own public surface remains exactly `{status,
   shutdown}` (unchanged count) — this EP widens what `shutdown()`
   *does*, not `RuntimeService`'s own method count.
6. `Bootstrap.shutdown()`'s body is unmodified (Section 7.3, Owner
   Decision D3); only its docstring changes. `bootstrap.scheduler_service`
   remains non-`None` and identity-preserved across `shutdown()`.
7. No new CLI action, REST-reachable action, or configuration key is
   introduced anywhere (Sections 9, 10).
8. `tests/EP059/test_runtime.py` and the full, pre-existing
   `tests/EP060/test_runtime_lifecycle.py` suite both pass unmodified
   in assertions (only the one disclosed comment update, Section 12).
9. The final git diff for STEP 2 touches only the files listed in
   Section 16's "Changed" list — nothing under "Explicitly protected."
10. A new, self-contained `tests/EP061/` suite exists, covering at
    minimum every scenario enumerated in Section 12, and passes in
    full.

---

## 19. STEP 2 Implementation Plan

1. Re-confirm, at STEP 2 start, the exact current full-regression test
   list (search for any additional pre-existing Scheduler/EP-011 test
   coverage not already identified in Section 12, since this design
   was produced without modifying anything and a fresh `grep` at STEP
   2 start is cheap insurance against drift between STEP 1 and STEP
   2).
2. Implement `src/services/scheduler_service.py` changes exactly as
   specified in Section 7.1 (new field, new private helper, new
   public `shutdown()` method). Run only `SchedulerService`'s own
   existing tests (if any exist beyond `tests/EP060`'s helper usage)
   to confirm zero regression before touching any other file.
3. Implement `src/services/runtime_service.py` changes exactly as
   specified in Section 7.2 (`RuntimeShutdownReport` fields,
   `shutdown()` body addition, docstring update). Run
   `tests/EP059/test_runtime.py` and `tests/EP060/
   test_runtime_lifecycle.py` to confirm zero regression.
4. Update `src/bootstrap.py`'s `shutdown()` docstring only (Section
   7.3). Re-run the full `tests/EP060/test_runtime_lifecycle.py`
   suite, including the one disclosed comment update inside
   `_test_bootstrap_shutdown_does_not_touch_scheduler_service`
   (assertions unchanged).
5. Write `tests/EP061/test_scheduler_shutdown.py` covering every item
   in Section 12, using real objects throughout, no mocks, following
   `tests/EP060/test_runtime_lifecycle.py`'s own structural
   conventions (`BaseTest`/`TestRegistry`, local builder functions,
   `_ChdirGuard`-style helpers where needed).
6. Run the complete regression set identified in step 1, plus the new
   EP-061 suite, and record pass counts.
7. Produce a STEP 2 report documenting exactly what changed, exactly
   as EP-059/EP-060's own STEP 2 reports did, including the disclosed
   test-comment update and confirmation that Sections 16/18 of this
   document were satisfied.
8. Do not proceed to STEP 3 (Architecture Audit) within the same
   step; STEP 2 ends once implementation, tests, and the STEP 2 report
   exist.

---

End of document.
