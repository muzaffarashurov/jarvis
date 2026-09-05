# EP-062 — BackgroundWorkerService Status/Shutdown Reconciliation

STEP 1: Architecture Discovery & Design

Status: DESIGN PROPOSED — awaiting Owner Decision approval before STEP 2

---

## 0. How this scope was derived

`docs/architecture/JARVIS_ROADMAP.md` and `docs/BACKLOG.md` both state,
verbatim, **"Next Engineering Package: none yet defined"** — EP-061
closed the last item EP-060 itself had explicitly flagged as its own
natural follow-up (the Scheduler tick-loop shutdown gap), and no
EP-062 or Phase 11 text exists anywhere in this repository. Unlike
EP-060 → EP-061, `EP061_DESIGN.md` and
`docs/architecture/audits/EP061_ARCHITECTURE_AUDIT.md` do not name a
specific "next EP" candidate anywhere (confirmed by a full-text search
of both documents for "next EP", "future EP", "EP-062", and
"separately-scoped" — the only hits are generic forward-looking
caveats about hypothetical future work, not a named candidate). Per
the STEP 1 instructions, EP-062's scope must therefore be derived from
the repository's actual code and documentation, not assumed from the
package number.

The repository does, however, already name and disclose a different,
older, still-open gap — one that predates EP-061 and that EP-061 never
touched. `docs/architecture/designs/EP060_DESIGN.md` Section 5.5,
titled *"A related, pre-existing limitation this document does not
fix"*, explicitly identifies that `BackgroundWorkerService.status()`
cannot distinguish "running" from "already shut down", explicitly
states that fixing it "would require modifying
`background_worker_service.py`, an EP-036 core file, which this
document does not propose", and explicitly defers it rather than
declaring it permanently out of scope. This is confirmed still true
and still unfixed in four independent places, verified directly
against the current source and tests during this STEP 1 (Section 2
below):

1. `src/services/background_worker_service.py`'s current `status()`
   body, read directly.
2. `src/services/runtime_service.py`'s own docstring for
   `RuntimeShutdownReport.background_workers_was_active`, which still
   says, verbatim: *"Per `EP060_DESIGN.md` Section 5.5/9.3, this field
   inherits a pre-existing `BackgroundWorkerService.status()`
   limitation ... This is disclosed, not fixed, by EP-060."*
3. `tests/EP060/test_runtime_lifecycle.py`'s
   `_test_shutdown_disclosed_background_worker_status_limitation`,
   which exists specifically to *pin* the buggy behavior ("Disclosed,
   unfixed limitation: still reports running=True") so that a future,
   silent change would be caught as a deviation from the documented
   contract — i.e., a test written to guard the bug's continued
   existence until an EP explicitly changes the contract, not one that
   asserts genuinely desired behavior.
4. `src/modules/background_worker_module.py`'s `worker status` CLI
   handler, which surfaces the same stale `running` value directly to
   an operator, live, at the Shell/REST layer — this is not merely a
   process-shutdown-time reporting artifact confined to
   `RuntimeShutdownReport`, but a reachable, user-facing
   inconsistency any time `worker stop` is run manually.

This is exactly the kind of "real, code-verified gap" STEP 1 is asked
to find: a concrete, already-disclosed, already-scoped limitation left
behind by an earlier EP (EP-060), independently re-confirmed against
current source rather than assumed, that has remained open across two
subsequent EPs (EP-060 itself and EP-061, neither of which touched
`background_worker_service.py`). EP-062 closes it.

Alternative candidates considered and rejected during this STEP 1's
discovery — see Section 9 (Non-Goals) for the full reasoning:

- Architecture Debt items in `docs/architecture/ARCHITECTURE_DEBT.md`
  (AD-005 through AD-009) — explicitly barred from being fixed inside
  a normal Engineering Package by that document's own stated rules
  ("Never fix Architecture Debt during a normal Engineering Phase
  (EP)... Architecture Debt is addressed only during a dedicated
  cleanup milestone").
- The Telegram exclusion from `RuntimeService` (`EP060_DESIGN.md`
  Section 9.1/Owner Decision D4) — re-verified during this STEP 1
  against `TelegramService.__init__`: `telegram.auto_start` genuinely
  defaults to `false`, so (unlike the Scheduler case EP-060 found
  factually wrong) there is no actual gap here; EP-059/EP-060's
  original reasoning still holds. Nothing to fix.

---

## 1. Problem Statement

`BackgroundWorkerService.status()` (`src/services/
background_worker_service.py`, EP-036) reports `running=True` based
solely on whether `self._pool` (a `BackgroundWorkerPool` reference) is
not `None`:

```python
def status(self) -> BackgroundWorkerStatus:
    if self._pool is None:
        return BackgroundWorkerStatus(
            enabled=False, running=False, worker_count=0, task_count=0
        )
    return BackgroundWorkerStatus(
        enabled=True,
        running=True,
        worker_count=self._pool.worker_count,
        task_count=len(self._pool.list_tasks()),
    )
```

`BackgroundWorkerService.shutdown()` never sets `self._pool` back to
`None` after shutting the pool down (confirmed by reading `shutdown()`
in full, Section 2 below) — it only calls `self._pool.shutdown(...)`.
Consequently, **once a `BackgroundWorkerService` has ever been
constructed with the subsystem enabled, `status().running` is `True`
for the rest of that object's life, even after `shutdown()` has been
called and every worker thread has genuinely terminated.**

Consequences, all already disclosed in the repository (Section 0):

- `RuntimeService.shutdown()` (EP-060) computes
  `background_workers_was_active` by calling
  `self._background_worker_service.status().running` *before*
  invoking `shutdown()` on it. On a **second** `RuntimeService.
  shutdown()` call (or any call after the pool was already shut down
  by some other path, e.g. a prior `worker stop`), this still reports
  `True`, even though the subsystem was already fully stopped —
  `RuntimeShutdownReport` cannot distinguish "was genuinely running"
  from "was already shut down".
- `RuntimeService.status()` (EP-059/EP-060) computes
  `RuntimeStatus.background_workers_active` the same way, so `runtime
  status`, called any time after a Background Worker shutdown, keeps
  reporting "Background Workers : ACTIVE" — including the worker
  thread count and task count lines that are gated behind that flag
  (`src/modules/runtime_module.py`) — even though every worker thread
  has actually terminated.
- `worker status` (`src/modules/background_worker_module.py`, EP-036
  STEP 3) surfaces the exact same stale value directly: an operator
  who runs `worker stop` followed by `worker status` sees "Running :
  YES", while a subsequent `worker submit` on the same instance would
  immediately raise `PoolShutDownError` — a directly observable,
  self-contradictory CLI experience, not merely an internal
  bookkeeping nuance.

This is a real, narrow, already-scoped gap in one method's body, not a
new feature invented for this EP.

---

## 2. Current Architecture / Verified Source-Level Findings

All facts below were re-read directly from the current source during
this STEP 1, not assumed from `EP060_DESIGN.md`'s own text.

### 2.1 `BackgroundWorkerService` (`src/services/background_worker_service.py`)

- **`__init__`** (lines ~121–162): if `background_workers.enabled`
  resolves `True`, constructs exactly one `BackgroundWorkerPool` and
  stores it as `self._pool`; otherwise `self._pool` stays `None` for
  the object's entire lifetime. There is no "paused, not yet started"
  state, and no code path re-assigns `self._pool` after construction
  other than this one `__init__`-time assignment.
- **`status()`** (lines 176–187, quoted verbatim in Section 1): the
  entire method. `running` is derived exclusively from `self._pool is
  not None` — it never reads `self._pool.is_shutdown` or any other
  liveness signal.
- **`shutdown()`** (lines 230–252): calls `self._pool.shutdown(wait=,
  timeout=)` and returns its `bool` result. **`self._pool` is never
  reassigned to `None` or otherwise mutated by this method** —
  confirmed by reading the full method body; the only statement
  touching `self._pool` is the one delegating call.
- Public method set (unchanged by this design, confirmed by direct
  `grep`/enumeration): `status`, `submit`, `get_task`, `list_tasks`,
  `shutdown` (5 total).

### 2.2 `BackgroundWorkerPool` (`src/core/background_workers/
background_worker_pool.py`, EP-036)

- **`is_shutdown`** (lines ~244–249) is an **already-existing, already
  public** property:

  ```python
  @property
  def is_shutdown(self) -> bool:
      """Return whether `shutdown()` has been called on this pool."""
      with self._lifecycle_lock:
          return self._is_shutdown
  ```

  Thread-safe (guarded by the pool's own `_lifecycle_lock`, the same
  lock `shutdown()` itself uses to set `self._is_shutdown = True`,
  confirmed at line 335). Set exactly once, unconditionally, as the
  first statement inside `shutdown()` (line ~334-335), regardless of
  `wait`/`timeout` — so `is_shutdown` becomes `True` the instant
  `shutdown()` is called, not only once workers have actually
  terminated.
- This property is **never read anywhere in the current
  codebase outside `background_worker_pool.py`'s own module**
  (confirmed by `grep -rn "is_shutdown" src/ tests/` — its only
  non-definition production use is inside `submit()`'s own
  `PoolShutDownError` guard, Section 2.2 of `background_worker_pool.py`
  itself). `BackgroundWorkerService` — the one class positioned to
  expose it upward — does not consume it at all today.

### 2.3 Consumers of `BackgroundWorkerService.status().running` — exhaustive

A repository-wide search (`grep -rn "background_worker_service\|
BackgroundWorkerService\|BackgroundWorkerStatus"` across `src/`,
`desktop/`, `web/`) found exactly these files referencing
`BackgroundWorkerService`/`BackgroundWorkerStatus` at all:

| File | Relationship |
|---|---|
| `src/services/background_worker_service.py` | Defines it. |
| `src/modules/background_worker_module.py` | Consumes `status().running` directly (`worker status` CLI, Section 2.4). |
| `src/services/runtime_service.py` | Consumes `status().running` directly, twice (`status()` and `shutdown()`, Section 2.5). |
| `src/bootstrap.py` | Constructs/stores/nulls the reference; **never calls `.status()`** (confirmed by grep — only `BackgroundWorkerService`/`BackgroundWorkerServiceError` imports and the constructor/property wiring appear, no `.status(` call). |
| `src/services/git_service.py`, `src/core/git/git_error.py`, `src/services/scheduler_service.py`, `src/core/background_workers/__init__.py` | Docstring/comment cross-references only — no code reads `.status()` or `.running`. |
| `src/modules/test_module.py` | Registers `tests.EP036.test_background_worker_service` for the test runner — no production dependency. |

**No other file in `src/`, `desktop/`, or `web/` references
`BackgroundWorkerService` or `BackgroundWorkerStatus` at all.** The
full consumer set of `.status().running` is exactly two call sites,
both already identified: `background_worker_module.py`'s `_status`
handler and `runtime_service.py`'s `status()`/`shutdown()`.

### 2.4 `BackgroundWorkerModule._status` (`src/modules/
background_worker_module.py`, EP-036 STEP 3)

```python
def _status(self, arguments: list[str]) -> CommandResult:
    status: BackgroundWorkerStatus = self._service.status()
    lines = [
        "Background Worker Status",
        f"Enabled : {'YES' if status.enabled else 'NO'}",
        f"Running : {'YES' if status.running else 'NO'}",
        f"Worker threads : {status.worker_count}",
        f"Tasks submitted : {status.task_count}",
    ]
    return CommandResult(success=True, message="\n\n".join(lines))
```

Reads `status.running` once, for display only — no branching on its
value (unlike `runtime status`, Section 2.5). `worker_count`/
`task_count` are always shown regardless of `running`, sourced from
`self._pool.worker_count`/`len(self._pool.list_tasks())` — both
remain valid, meaningful reads on an already-shut-down pool (a shut
down pool still has a fixed `worker_count` and a task history), so
this design does not touch how those two lines are populated.

### 2.5 `RuntimeService` (`src/services/runtime_service.py`, EP-059/
EP-060/EP-061)

Two read sites, both already identified in Section 1:

- **`status()`** (lines ~264–303): `background_workers_active =
  worker_status.running` feeds directly into `RuntimeStatus.
  background_workers_active`, which `src/modules/runtime_module.py`'s
  `_status` handler uses to gate two additional display lines
  (`background_worker_count`/`background_worker_task_count`) and one
  "ACTIVE"/"INACTIVE" label.
- **`shutdown()`** (lines ~382–397): `background_workers_was_active =
  self._background_worker_service.status().running` is read
  **before** `self._background_worker_service.shutdown()` is called,
  then fed into `RuntimeShutdownReport.background_workers_was_active`.

Neither site imports or touches `BackgroundWorkerPool` directly —
both go exclusively through `BackgroundWorkerService`'s own public
`status()`, unchanged by this design (Section 2.6/9.1's per Owner
Decision D5 precedent below).

---

## 3. Gap Analysis

| What exists | What's missing |
|---|---|
| `BackgroundWorkerPool.is_shutdown` (public, thread-safe, already correct) | Nothing consumes it upward — `BackgroundWorkerService.status()` never reads it |
| `BackgroundWorkerService.status()` derives `running` from `self._pool is not None` | Does not distinguish "pool exists and is running" from "pool exists but was shut down" |
| `RuntimeService`/`worker status` both consume `BackgroundWorkerService.status().running` as their sole liveness signal | Both inherit the same staleness, disclosed but unfixed since EP-060 |
| `tests/EP060/test_runtime_lifecycle.py` pins the current (buggy) behavior explicitly | Needs updating in STEP 2 once the contract changes (Section 7 below; not touched in STEP 1) |

The missing piece is narrow: **one changed expression inside one
existing method's body** (`BackgroundWorkerService.status()`), wiring
an already-public, already-correct property (`BackgroundWorkerPool.
is_shutdown`) into an already-existing field (`BackgroundWorkerStatus.
running`) that already claims, in its own docstring, to mean "whether
this service currently owns a live pool" — a claim `is_shutdown`
lets it finally keep accurately.

---

## 4. Goals

1. Make `BackgroundWorkerService.status().running` accurately reflect
   whether the owned pool is still live — `True` only while a pool
   exists **and** has not been shut down; `False` once `shutdown()`
   has been called on it (regardless of whether every worker thread
   has fully joined yet — see Section 8's edge-case discussion for why
   this is the correct granularity, matching `BackgroundWorkerPool.
   is_shutdown`'s own, already-established semantics).
2. Change nothing else about `BackgroundWorkerService`'s public
   surface, constructor, or any other method's behavior.
3. Let the fix propagate automatically to both existing consumers
   (`RuntimeService`, `BackgroundWorkerModule`) purely because they
   already call `BackgroundWorkerService.status()` — no consumer-side
   code needs to change.
4. Preserve every other field of `BackgroundWorkerStatus`
   (`enabled`, `worker_count`, `task_count`) exactly as today —
   this design touches only the expression that computes `running`.

## 5. Existing Related Infrastructure

- **`BackgroundWorkerPool.is_shutdown`** (Section 2.2) — the entire
  fix. Already public, already thread-safe, already set at exactly
  the right moment (`shutdown()`'s first statement), needs zero
  changes of its own.
- **`SchedulerService.status()`/`SchedulerStatus.running`** (EP-011,
  widened EP-060/EP-061) — the closest structural precedent in this
  repository for "a service's `status().running` field is a live,
  re-checked-every-call fact, not a one-time construction-time
  snapshot": `SchedulerStatus.running` is derived from
  `_is_tick_loop_running()`, itself a thread-safe read of live state,
  every time `status()` is called. This design brings
  `BackgroundWorkerStatus.running` into the same shape, for the same
  reason.
- **`RuntimeService`'s own docstring** (Section 0, point 2) already
  anticipates this exact fix's eventual arrival — it cites
  `EP060_DESIGN.md` Section 5.5/9.3 by name as the origin of the
  limitation it is inheriting, which this design proposes to close at
  the source rather than in `RuntimeService` itself (Section 6, Owner
  Decision D1).

Nothing above needs to be invented. The one mechanism EP-062 needs
(`BackgroundWorkerPool.is_shutdown`) already exists, in exactly the
shape required, and only needs to be read from one additional place.

---

## 6. Proposed Design

No new module, class, property, method, or abstraction is introduced.
This is a one-expression change inside `BackgroundWorkerService.
status()`'s existing body:

```python
def status(self) -> BackgroundWorkerStatus:
    """Return the Background Worker subsystem's overall status."""
    if self._pool is None:
        return BackgroundWorkerStatus(
            enabled=False, running=False, worker_count=0, task_count=0
        )
    return BackgroundWorkerStatus(
        enabled=True,
        running=not self._pool.is_shutdown,
        worker_count=self._pool.worker_count,
        task_count=len(self._pool.list_tasks()),
    )
```

The only change from today's body: `running=True` becomes
`running=not self._pool.is_shutdown`. Every other line, including the
`self._pool is None` branch (a genuinely different case — the
subsystem was never enabled this run at all, as opposed to having been
enabled and later shut down — Section 8 explains why these two cases
must stay distinguishable and why `enabled` is deliberately left
untouched by this design), is unchanged.

```
BackgroundWorkerService.status()
        |
        v
   self._pool is None?  -- unchanged: enabled=False, running=False
        |
        no
        v
   BackgroundWorkerStatus(
       enabled=True,                          (unchanged)
       running=not self._pool.is_shutdown,    <-- NEW (EP-062):
       |                                          reads the pool's own
       |                                          already-existing,
       |                                          already-correct
       |                                          public property
       worker_count=self._pool.worker_count,  (unchanged)
       task_count=len(self._pool.list_tasks())(unchanged)
   )
```

`BackgroundWorkerPool.is_shutdown`, `BackgroundWorkerService.
shutdown()`, `BackgroundWorkerService.__init__`, and every other
method on both classes are **untouched** — this design's entire
production-code footprint is the single expression shown above.

### 6.1 Why `enabled` is not touched

`BackgroundWorkerStatus.enabled`'s own docstring already defines it as
*"Whether `background_workers.enabled` resolved True for this run"* —
a static configuration fact fixed at construction time, deliberately
distinct from `running`'s dynamic, re-checked-every-call nature (this
is exactly the same distinction `SchedulerStatus` draws between a
job's own `enabled` flag and the tick loop's live `running` state,
Section 5). A pool that was enabled this run and has since been shut
down is still correctly described as "enabled=True" (the subsystem was
configured on for this run) and now-correctly "running=False" (it is
no longer live) — these are not contradictory; they are the same
distinction `enabled: true, auto_start: true` vs. a stopped tick loop
already draws for the Scheduler today. No change to `enabled`'s
computation is proposed or needed.

---

## 7. Status/CLI Behavior — Before and After

| Scenario | `status.running` today (disclosed bug) | `status.running` after EP-062 |
|---|---|---|
| `background_workers.enabled: false` | `False` | `False` (unchanged — `self._pool is None` branch untouched) |
| Enabled, never shut down | `True` | `True` (unchanged — `is_shutdown` is `False`) |
| Enabled, `shutdown()` called once | **`True` (bug)** | **`False` (fixed)** |
| Enabled, `shutdown()` called twice | **`True` (bug)** | **`False` (fixed)** |
| `worker stop` via CLI, then `worker status` | Prints `Running : YES` (contradicts a subsequent `worker submit` raising `PoolShutDownError`) | Prints `Running : NO` — now consistent with `submit()`'s own behavior |
| `runtime status`, called after a Background Worker shutdown | Prints `Background Workers : ACTIVE`, plus stale worker-thread/task-count lines | Prints `Background Workers : INACTIVE`; the two detail lines are no longer shown (`runtime_module.py`'s existing `if status.background_workers_active:` gate, unchanged, now gates correctly) |
| A second `RuntimeService.shutdown()` call | `RuntimeShutdownReport.background_workers_was_active` still `True` on the second call (cannot detect "already shut down") | `False` on the second call — the pool is genuinely no longer running, so it genuinely "was not active" immediately before that second call |

No change to `worker_count` or `task_count` in any scenario — both
remain populated from the pool's own already-existing, still-valid
`worker_count` property and `list_tasks()` method regardless of
shutdown state, exactly as today.

---

## 8. Error / Edge Cases

- **`shutdown(wait=False)`**: `BackgroundWorkerPool.shutdown()` sets
  `self._is_shutdown = True` as its very first statement (Section
  2.2), before checking `wait` at all — so `is_shutdown` (and, after
  this design, `status().running`) becomes `False`^[i.e. `running`
  becomes `False`] immediately, even though worker termination itself
  was not verified. This is the **correct** granularity: `is_shutdown`
  answers "has shutdown been signaled/requested", not "have all
  workers actually finished" — and that is exactly the question
  `status().running` should answer too (mirroring `SchedulerStatus.
  running`'s own semantics: it reflects whether the tick loop is
  currently supposed to be running, not a fine-grained "is a job
  executing right now"). A caller that needs to know whether workers
  have *fully drained* already has `shutdown()`'s own return value for
  that (`True` only if every worker was confirmed stopped via
  `Thread.is_alive()`, Section 2.2 of `background_worker_pool.py`) —
  this design does not change that contract at all.
- **`shutdown()` timed out (returned `False`)**: `is_shutdown` is still
  `True` (set unconditionally, before any join is attempted) — so
  `status().running` correctly becomes `False` even if one or more
  worker threads are, in fact, still finishing their current task.
  This is consistent with `shutdown()`'s own already-documented
  behavior (a `False` return does not mean "shutdown was not
  requested"; it means "termination could not be verified within the
  timeout") and requires no new handling.
- **Concurrent `status()` call during an in-progress `shutdown()`**:
  `is_shutdown` is read through the pool's own `_lifecycle_lock`
  (Section 2.2), the same lock `shutdown()` uses to set it — already
  race-safe, unchanged by this design. No new lock is introduced or
  needed in `BackgroundWorkerService`.
- **`self._pool is None` (subsystem disabled this run)**: entirely
  unaffected — that branch of `status()` is not touched by this
  design at all (Section 6).
- **A future pool replacement** (hypothetical — no such mechanism
  exists today, and none is proposed here): if some future EP ever
  allowed `self._pool` to be replaced with a fresh, running pool after
  a shutdown, `status()` would immediately and correctly reflect that
  new pool's own `is_shutdown` state, since `status()` always reads
  `self._pool.is_shutdown` fresh on every call rather than caching a
  value — no additional work would be required for that hypothetical
  case, though it remains explicitly out of this EP's scope (Section
  9).

---

## 9. Non-Goals

- **No new public method, property, or class anywhere.**
  `BackgroundWorkerService`'s public method set stays exactly
  `{status, submit, get_task, list_tasks, shutdown}` (5, unchanged —
  Section 2.1). `BackgroundWorkerPool.is_shutdown` already exists and
  is not modified.
- **No change to `BackgroundWorkerStatus`'s shape.** All four fields
  (`enabled`, `running`, `worker_count`, `task_count`) keep their
  names, types, and meanings; only the *value* assigned to `running`
  in one branch of one method changes (Section 6).
- **No change to `RuntimeStatus` or `RuntimeShutdownReport`'s shape.**
  Both dataclasses' fields, names, types, and defaults are entirely
  unchanged — `RuntimeService` already reads `BackgroundWorkerService.
  status().running` exactly as it does today; only the *value* that
  read now returns, after a shutdown, changes (Section 2.5/7). No line
  inside `runtime_service.py` is proposed to change.
- **No change to `runtime_module.py` or `background_worker_module.py`
  CLI formatting code.** Both already branch on `.running`/
  `.background_workers_active` correctly; they need no code change to
  start displaying the corrected value (Section 7) — only the value
  flowing into them changes, at its one source.
- **No change to `config/config.yaml` or any configuration key.**
  Nothing about this fix is configurable, gated, or optional — it is a
  correctness fix to an existing field's semantics, not a new,
  toggleable behavior. `BackgroundWorkerStatus.enabled` (the
  configuration-derived field) is untouched (Section 6.1).
- **No fix to any other disclosed limitation.** In particular:
  - `BackgroundWorkerPool._tasks`'s unbounded growth (AD-006) is
    unrelated and untouched.
  - The EP-037 STEP 3 automation-adapter's implicit event-payload
    contract (AD-008) is unrelated and untouched.
  - AD-005 ("no process-exit shutdown wiring calls
    `BackgroundWorkerService.shutdown()` automatically") is a
    **different, already-superseded** concern from a pre-EP-060
    snapshot of this codebase — `RuntimeService.shutdown()` →
    `Bootstrap.shutdown()` (EP-060) already wires this today. Even if
    it were still open, `docs/architecture/ARCHITECTURE_DEBT.md`'s own
    stated rule ("Architecture Debt is addressed only during a
    dedicated cleanup milestone") would keep it out of this EP's scope
    regardless. No `ARCHITECTURE_DEBT.md` entry is touched, added, or
    resolved by this design.
  - Any other AD-numbered item — none is evidenced as related to this
    fix, and the same "not fixed inside a normal EP" rule applies
    uniformly.
- **No restart/resume capability.** This design does not add any way
  to make a shut-down `BackgroundWorkerService`/`BackgroundWorkerPool`
  "running" again — `is_shutdown` is (and remains) a one-way flag,
  exactly as `BackgroundWorkerPool` already implements it today.
- **No CLI/REST-reachable action changes.** `worker`'s six actions
  (`status, submit, list, info, stop, help`) and `runtime`'s two
  (`status, help`) are unchanged in count and dispatch; only display
  content changes, per Section 7.
- **No test file is modified as part of STEP 1.** Per this task's
  explicit instruction, updating
  `tests/EP060/test_runtime_lifecycle.py::
  _test_shutdown_disclosed_background_worker_status_limitation` (and
  writing new EP-062 test coverage) is exclusively a STEP 2 activity
  (Section 12/13).

---

## 10. Owner Decisions

### D1 — Should the fix live in `BackgroundWorkerService.status()` itself, or in `RuntimeService` (e.g. by having `RuntimeService` read `BackgroundWorkerPool.is_shutdown` directly, or track its own "already shut down" flag)?

**Decision:** Fix it at the source — inside `BackgroundWorkerService.
status()` — not in `RuntimeService` and not by adding new state to
either class.
**Alternatives considered:** (a) as decided — fix `BackgroundWorkerService.status()`; (b) have `RuntimeService` track its own boolean ("have I already called `background_worker_service.shutdown()` before?") and use that to override `status().running`; (c) have `RuntimeService` reach past `BackgroundWorkerService` and read `self._background_worker_service._pool.is_shutdown` (or a newly-added `BackgroundWorkerService.is_shutdown` passthrough) directly.
**Why (a) is preferred:** `BackgroundWorkerService.status()`'s own
docstring already claims `running` means "whether this service
currently owns a live pool" (Section 3) — the bug is that the
implementation doesn't keep that promise, not that the promise itself
is wrong or belongs to a different layer. Option (b) would duplicate
state `BackgroundWorkerPool` already tracks correctly, and would only
fix `RuntimeService`'s two call sites while leaving `worker status`
(Section 2.4) — a second, independent, CLI-reachable consumer of the
same broken field — still wrong; per Section 2.3, there are exactly
two consumers, and only fixing the source fixes both automatically.
Option (c) would either reach through `BackgroundWorkerService`'s
encapsulation of its own `_pool` (a private attribute, by convention
not read from outside the class — consistent with this project's
existing `SchedulerService`/`RuntimeService` boundary, where
`RuntimeService` only ever calls `SchedulerService.status()`, never
reaches into `SchedulerService._tick_thread`), or add a second,
redundant public property (`BackgroundWorkerService.is_shutdown`)
whose only reason to exist would be to work around `status()` still
being wrong — treating the symptom instead of the cause.
**Architectural consequences:** `RuntimeService`, `runtime_module.py`,
and `background_worker_module.py` all require zero code changes
(Section 9) — the fix is entirely contained in one file,
`background_worker_service.py`, and propagates automatically to every
consumer because each already goes through `BackgroundWorkerService.
status()`.

### D2 — Should `running` reflect "shutdown has been signaled" (`is_shutdown`) or "every worker thread has actually terminated"?

**Decision:** "Shutdown has been signaled" — i.e., `not self._pool.
is_shutdown`, matching `BackgroundWorkerPool.is_shutdown`'s own,
already-established semantics exactly, with no additional
thread-liveness check.
**Alternatives considered:** (a) as decided — `is_shutdown`-based; (b)
a finer-grained check that also inspects `self._pool.worker_threads()`
and only reports `running=False` once every worker's `is_alive()` is
`False`.
**Why (a) is preferred:** Section 5's `SchedulerStatus.running`
precedent already establishes that this project's `*Status.running`
fields describe whether a subsystem is *currently supposed to be
active*, not a live, per-thread liveness poll — `SchedulerStatus.
running` reflects `_is_tick_loop_running()`, a similarly coarse,
already-thread-safe flag read, not a scan of the tick thread's precise
execution point. Option (b) would require `BackgroundWorkerStatus` (or
`status()`'s caller) to interpret a new, more complex tri-state
("running", "shutting down", "fully stopped") that no existing
consumer (`RuntimeService`, `worker status`) asks for or has any
display slot for today, and `shutdown()`'s own return value (Section
8) already answers "did every worker actually stop" precisely, for
any caller that needs that specific, stronger guarantee. Option (b)
would also reach past `is_shutdown` into `worker_threads()` for a
question `is_shutdown` already answers at the correct level of
abstraction for `status()`'s existing purpose (a quick, coarse
liveness summary, not a diagnostic worker-by-worker breakdown — that
already exists separately as `doctor()`-equivalent tooling would, if
this class had one; it does not, and this design does not add one).
**Architectural consequences:** `status()`'s change is exactly the
one-expression diff in Section 6 — no additional field is read from
`BackgroundWorkerPool`, and no new field is added to
`BackgroundWorkerStatus`.

### D3 — Should this design also touch `RuntimeShutdownReport.background_workers_was_active`'s docstring (which currently documents the bug being fixed) as part of STEP 1?

**Decision:** No — STEP 1 produces only this design document; the
docstring update is STEP 2 work, alongside the one disclosed test
update (Section 12/13).
**Alternatives considered:** (a) as decided — leave all production
code and docstrings untouched until STEP 2; (b) update the docstring
now, during STEP 1, since it is "only documentation".
**Why (a) is preferred:** this task's explicit STEP 1 instructions
prohibit modifying any production code during STEP 1, and a
docstring is part of `runtime_service.py`'s production source file —
the same file EP-061's own STEP 1 (`EP061_DESIGN.md` Section 16)
treated identically, deferring even docstring-only edits in files
outside this design document to STEP 2. Consistency with that
established precedent is preferred over a narrow "docs don't count"
carve-out.
**Architectural consequences:** none to the design itself — Section
13 (Expected File Scope) records this as a required STEP 2 edit
(docstring only, in `runtime_service.py`, no logic change) so it is
not forgotten.

---

## 11. RuntimeService Compatibility Impact

- **`RuntimeService.__init__`'s signature**: untouched — this design
  does not add, remove, or reorder any parameter.
- **`RuntimeStatus`'s fields**: untouched in name, type, and default
  (Section 9). Only the *value* `background_workers_active` receives,
  after a shutdown has occurred, changes from `True` (bug) to `False`
  (correct) — a behavioral correction, not a shape change.
- **`RuntimeShutdownReport`'s fields**: untouched in name, type, and
  default, for the same reason.
- **`RuntimeService`'s own public surface**: remains exactly
  `{status, shutdown}` (unchanged count, per EP-060/EP-061's own
  established guarantee) — this design does not touch
  `RuntimeService`'s method set at all, only the value one of its
  existing dependencies (`BackgroundWorkerService`) returns from a
  method it already calls.
- **Every `RuntimeService(...)` construction call site** (in
  `tests/EP059/test_runtime.py`, `tests/EP060/
  test_runtime_lifecycle.py`, `tests/EP061/test_scheduler_shutdown.py`,
  and `src/bootstrap.py`) continues to work unmodified — none
  constructs `BackgroundWorkerStatus`/`RuntimeStatus`/
  `RuntimeShutdownReport` positionally in a way this change could
  break (confirmed by the same absence of positional-construction risk
  EP-060/EP-061 already documented for these dataclasses).
- **One behavioral difference, already fully catalogued in Section 7**:
  `RuntimeStatus.background_workers_active` and
  `RuntimeShutdownReport.background_workers_was_active` both now
  report `False` after a genuine shutdown, where they previously
  (incorrectly) reported `True`. This is the entire, intended effect
  of this EP — not an incidental side effect — and is exactly the
  correction `runtime_service.py`'s own docstring (Section 0) already
  anticipates by name.

**No public API surface change is required or proposed anywhere in
this design.** Every class's method set, every dataclass's field set,
and every CLI action set named in this document (Sections 9, 11)
remains exactly as it is today; the sole change is the value produced
by one pre-existing expression.

---

## 12. Testing Strategy

New suite: `tests/EP062/test_background_worker_status.py`,
self-contained (no import from `tests/EP036/`, `tests/EP059/`,
`tests/EP060/`, or `tests/EP061/`, matching those suites' own
"per-EP self-containment" precedent), using the existing
`src/testing/base_test.py` (`BaseTest`)/`src/testing/registry.py`
(`TestRegistry`) framework, real objects throughout (no mocks),
matching `tests/EP036/test_background_worker_service.py`'s own style.

Coverage required:

1. **`BackgroundWorkerService.status()` in isolation**
   - Disabled (`background_workers.enabled: false`) → `status().running`
     is `False`, unaffected by this change (regression guard on the
     untouched branch).
   - Enabled, never shut down → `status().running` is `True`
     (regression guard on the "nothing changed here" case).
   - Enabled, `shutdown(wait=True)` called → `status().running` is
     `False` afterward (the core fix).
   - Enabled, `shutdown(wait=False)` called → `status().running` is
     `False` immediately, even without waiting for worker
     termination (Section 8's `is_shutdown`-vs-"fully joined" edge
     case, asserted explicitly so a future change cannot silently
     conflate the two).
   - `status()` called twice after `shutdown()` → `running` is `False`
     both times (idempotent observation — no new state is introduced
     that could make this flicker).
   - `worker_count`/`task_count` are unaffected by shutdown state,
     both before and after `shutdown()` (regression guard confirming
     Section 6's claim that only `running`'s expression changed).
2. **`RuntimeService` widened/corrected behavior**
   - `RuntimeService.status()`, given a real
     `BackgroundWorkerService` that has been shut down before
     `status()` is called → `RuntimeStatus.background_workers_active`
     is `False` (replaces/corrects, not merely regresses, the
     pre-EP-062 expectation).
   - `RuntimeService.shutdown()` called twice on a real, running
     `BackgroundWorkerService` → the **second** call's
     `RuntimeShutdownReport.background_workers_was_active` is now
     `False` (this is the disclosed-limitation test's corrected
     counterpart — see Section 13 for the one pre-existing test this
     replaces/updates).
   - `runtime status` (`RuntimeModule`) CLI output, called after a
     `BackgroundWorkerService` shutdown, no longer contains
     "Background Workers : ACTIVE" and no longer contains the
     worker-thread/task-count detail lines (Section 7's CLI-level
     table, asserted directly against `CommandResult.message`).
3. **`BackgroundWorkerModule` CLI (`worker status`)**
   - `worker stop` followed by `worker status` → the resulting
     `CommandResult.message` contains "Running : NO" (replacing
     today's self-contradictory "Running : YES" — Section 1/7).
   - `worker submit` after `worker stop` still raises/handles
     `PoolShutDownError` exactly as before (regression guard —
     confirms this design does not touch `submit()`'s own,
     independent shutdown guard).
4. **Public-surface guards**
   - `BackgroundWorkerService`'s public method set is still exactly
     the same five methods as before this EP (`status, submit,
     get_task, list_tasks, shutdown`) — an explicit `dir()`/`inspect`
     based assertion, matching `tests/EP061/
     test_scheduler_shutdown.py`'s own public-surface-guard pattern,
     so a future EP cannot silently widen this surface without a
     visible test failure.
   - `BackgroundWorkerStatus`'s field set (`enabled, running,
     worker_count, task_count`) is unchanged (via
     `dataclasses.fields`), guarding against an accidental shape
     change.

**One pre-existing test requires a disclosed, narrow update — a STEP 2
activity, not performed in STEP 1 (Section 10, Owner Decision D3):**
`tests/EP060/test_runtime_lifecycle.py::
_test_shutdown_disclosed_background_worker_status_limitation` currently
asserts the bug this EP fixes (`# Disclosed, unfixed limitation: still
reports running=True`). STEP 2 must update this test to assert the
corrected behavior (`bg_service.status().running` is `False` after
`shutdown()`, and `second_report.background_workers_was_active` is
`False`) — this is "make the test agree with the newly-approved
contract", the exact discipline `EP060_DESIGN.md`/`EP061_DESIGN.md`
both already applied to their own analogous test corrections, not a
weakening of any assertion. The test's docstring/name should also be
updated in STEP 2 to reflect that the limitation is now fixed rather
than disclosed-and-pinned (e.g. renamed to something like
`_test_shutdown_background_worker_status_reflects_shutdown_state`,
exact naming left to STEP 2).

Full regression, reproduced exactly (matching this repository's own
standard): `tests/EP036/test_background_worker_service.py`,
`tests/EP036/test_background_worker_module.py`, `tests/EP059/
test_runtime.py`, `tests/EP060/test_runtime_lifecycle.py`, `tests/
EP061/test_scheduler_shutdown.py` — a repository search for any
additional pre-existing `BackgroundWorkerService`/`BackgroundWorkerPool`
test coverage not already identified here is required at STEP 2 start,
matching `EP061_DESIGN.md` Section 12's own "fresh grep at STEP 2
start is cheap insurance against drift" precedent.

---

## 13. Expected File Scope

**This STEP 1 change scope:** only
`docs/architecture/designs/EP062_DESIGN.md` (this file). No other
file is created, modified, or deleted by STEP 1.

**Changed (STEP 2, once this design is approved):**

- `src/services/background_worker_service.py` — one-expression
  change inside `status()` (Section 6): `running=True` →
  `running=not self._pool.is_shutdown`. No other line changes.
- `src/services/runtime_service.py` — **docstring-only** update to
  `RuntimeShutdownReport.background_workers_was_active`'s docstring
  (removing the now-outdated "This is disclosed, not fixed, by
  EP-060" sentence and replacing it with a note that EP-062 fixed the
  underlying `BackgroundWorkerService.status()` limitation at its
  source) and, if needed for accuracy, a similar one-sentence update
  to `RuntimeStatus.background_workers_active`'s docstring. **No
  executable line in this file changes** — `runtime_service.py`
  already calls `BackgroundWorkerService.status().running` exactly as
  it should; only the value that call now returns changes, at its
  source in `background_worker_service.py`.
- `tests/EP060/test_runtime_lifecycle.py` — one test updated (Section
  10 Owner Decision D3, Section 12): `
  _test_shutdown_disclosed_background_worker_status_limitation`'s
  assertions and docstring corrected to reflect the fixed contract.
  No other test in this file changes.
- `tests/EP062/test_background_worker_status.py` — new file (STEP 2),
  per Section 12.

**Explicitly protected — must remain untouched:**

- `src/core/background_workers/background_worker_pool.py` — including
  `is_shutdown`, `shutdown()`, `submit()`, and every other method;
  this design reads `is_shutdown`, it does not change it or anything
  else in this file.
- `src/modules/background_worker_module.py` — its `_status`/`_stop`/
  `_submit` handlers already call the right methods; only the value
  `self._service.status()` returns changes, at its source.
- `src/modules/runtime_module.py` — same reasoning; its `_status`
  handler's existing `if status.background_workers_active:` gate
  already does the right thing once fed a correct value.
- `src/bootstrap.py` — does not call `.status()` at all (Section 2.3);
  nothing to change.
- `src/services/scheduler_service.py`,
  `src/core/scheduler/scheduler.py` — unrelated subsystem, untouched.
- `config/config.yaml`, `requirements.txt`, `pyproject.toml` — no
  configuration or dependency change anywhere in this design.
- `tests/EP059/test_runtime.py`, `tests/EP061/
  test_scheduler_shutdown.py`, `tests/EP036/
  test_background_worker_service.py`, `tests/EP036/
  test_background_worker_module.py` — re-run as regression only; no
  assertion in any of these needs to change (none of them asserts the
  specific disclosed-limitation behavior this design corrects — only
  `tests/EP060/test_runtime_lifecycle.py` does, per Section 12).
- `docs/BACKLOG.md`, `CHANGELOG.md`, `docs/RELEASE_NOTES.md`,
  `docs/architecture/JARVIS_ROADMAP.md`,
  `docs/architecture/ARCHITECTURE_DEBT.md` — STEP 1 does not modify
  these (future STEPs of the standard process would update the first
  four; `ARCHITECTURE_DEBT.md` is not touched by this EP at all, since
  nothing in this design's scope is an AD-tracked item, Section 9).

---

## 14. Acceptance Criteria

STEP 2 is complete and correct only if all of the following hold:

1. `BackgroundWorkerService.status()`'s only change is the one
   expression specified in Section 6 — verified by a diff/review
   confined to that single line inside that single method.
2. `BackgroundWorkerService`'s public method set is provably unchanged
   (`{status, submit, get_task, list_tasks, shutdown}`, 5 total) —
   verified by an explicit public-surface guard test (Section 12.4).
3. `BackgroundWorkerStatus`'s field set is provably unchanged
   (`enabled, running, worker_count, task_count`) — verified via
   `dataclasses.fields` (Section 12.4).
4. A real `BackgroundWorkerService`, enabled and never shut down,
   reports `status().running is True` (unchanged case, regression
   guard).
5. A real `BackgroundWorkerService`, enabled and then shut down
   (`wait=True` or `wait=False`), reports `status().running is False`
   afterward (the core fix, Section 12.1).
6. A real `BackgroundWorkerService`'s `worker_count`/`task_count`
   values are unaffected by shutdown state (Section 12.1).
7. `RuntimeService.status()`/`RuntimeService.shutdown()`, given a
   shut-down `BackgroundWorkerService`, report
   `background_workers_active=False`/`background_workers_was_active=
   False` respectively — with zero code changes required inside
   `runtime_service.py` itself beyond the disclosed docstring update
   (Section 13).
8. `worker status`, called after `worker stop`, reports "Running :
   NO" (Section 12.3).
9. `runtime status`, called after a Background Worker shutdown, no
   longer reports "Background Workers : ACTIVE" and no longer shows
   the worker-thread/task-count detail lines (Section 12.2).
10. `tests/EP060/test_runtime_lifecycle.py::
    _test_shutdown_disclosed_background_worker_status_limitation` is
    updated (assertions corrected, not weakened or deleted) to assert
    the fixed contract, and every other test in that file continues to
    pass unmodified.
11. `tests/EP036/test_background_worker_service.py`,
    `tests/EP036/test_background_worker_module.py`,
    `tests/EP059/test_runtime.py`, and `tests/EP061/
    test_scheduler_shutdown.py` all pass fully unmodified (pure
    regression — none of their existing assertions concerns the
    disclosed limitation this design fixes).
12. A new, self-contained `tests/EP062/` suite exists, covering at
    minimum every scenario enumerated in Section 12, and passes in
    full.
13. No new CLI action, REST-reachable action, configuration key,
    public method, or public property is introduced anywhere
    (Sections 9, 11).
14. The final STEP 2 diff touches only the files listed in Section
    13's "Changed" list — nothing under "Explicitly protected."

---

## 15. STEP 2 Implementation Boundaries

1. Re-confirm, at STEP 2 start, the exact current full-regression test
   list for `BackgroundWorkerService`/`BackgroundWorkerPool`/
   `RuntimeService` (a fresh `grep`, matching `EP061_DESIGN.md`
   Section 19's own precedent), since this design was produced without
   modifying anything and drift between STEP 1 and STEP 2 is cheap
   insurance to rule out.
2. Implement the one-expression change in `src/services/
   background_worker_service.py` specified in Section 6. Run
   `tests/EP036/test_background_worker_service.py` and `tests/EP036/
   test_background_worker_module.py` first, in isolation, to confirm
   zero regression before touching any other file.
3. Update `src/services/runtime_service.py`'s two affected docstrings
   only (Section 13) — no executable line changes. Re-run `tests/
   EP059/test_runtime.py`, `tests/EP060/test_runtime_lifecycle.py`,
   and `tests/EP061/test_scheduler_shutdown.py` to confirm the only
   behavioral difference anywhere is the one disclosed test update in
   Section 10/12/13.
4. Update `tests/EP060/test_runtime_lifecycle.py::
   _test_shutdown_disclosed_background_worker_status_limitation`
   exactly as Section 12/13 specify — correcting its assertions and
   docstring to match the newly-fixed contract, not weakening or
   deleting any check.
5. Write `tests/EP062/test_background_worker_status.py` covering every
   item in Section 12, using real objects throughout, no mocks,
   following `tests/EP036/test_background_worker_service.py`'s own
   structural conventions.
6. Run the complete regression set identified in step 1, plus the new
   EP-062 suite, and record pass counts.
7. Produce a STEP 2 report documenting exactly what changed, exactly
   as EP-060/EP-061's own STEP 2 reports did, including explicit
   confirmation that Sections 13/14 of this document were satisfied.
8. Do not proceed to STEP 3 (Architecture Audit) within the same
   step; STEP 2 ends once implementation, tests, and the STEP 2 report
   exist.

---

End of document.
