# EP036 — Architecture Audit (STEP 4)

Status: READ-ONLY audit, per `docs/architecture/AI_DEVELOPMENT_PLAYBOOK.md`.

No source code, tests, or configuration were modified while producing this report.

---

# Scope

Audits EP-036 (Background Workers) STEP 1–3 as implemented and validated:

- `BackgroundWorkerPool` — `src/core/background_workers/background_worker_pool.py` (STEP 1)
- `BackgroundWorkerService` — `src/services/background_worker_service.py` (STEP 2)
- `BackgroundWorkerModule` — `src/modules/background_worker_module.py` (STEP 3)
- `src/core/background_workers/__init__.py` (public package API)
- Bootstrap wiring — `src/bootstrap.py`
- Configuration — `config/config.yaml` (`background_workers.*`)
- Test suites — `tests/EP036/test_background_worker_pool.py`,
  `tests/EP036/test_background_worker_service.py`,
  `tests/EP036/test_background_worker_module.py`
- Test registration — `src/modules/test_module.py`

This audit reviews EP-036 only, per playbook scope discipline.

---

# 1. BackgroundWorkerPool (STEP 1)

Owns a fixed set of daemon worker threads pulling `workflow_id`s off an
internal `queue.Queue`, dispatched exclusively through EP-033's
`WorkflowEngine.run(workflow_id)`.

- Reaches EP-033 through exactly one public method, mirroring
  `WorkflowSchedulerEngine` (EP-034) and `AutomationEngine` (EP-035). No
  workflow-execution logic is duplicated.
- Two independent locks (`_tasks_lock`, `_lifecycle_lock`) with a
  documented invariant: neither is ever held while calling
  `WorkflowEngine.run()` or while blocked on `queue.get()`. This avoids
  lock contention with arbitrary, potentially slow workflow code.
- `get_task()`/`list_tasks()` return `dataclasses.replace()` copies, so
  callers can never mutate the pool's internal `BackgroundTask` state —
  correct encapsulation.

## 2. BackgroundWorkerService (STEP 2)

Thin, config-driven owner of a single `BackgroundWorkerPool`. Resolves
`background_workers.enabled` / `worker_count` / `shutdown_timeout`,
constructs the pool once if enabled, and exposes a narrow forwarding API
(`status`, `submit`, `get_task`, `list_tasks`, `shutdown`).

- No task-execution logic of its own — every task-facing method is a
  direct forward to the pool, consistent with the "no hidden coupling"
  rule.
- `background_workers.enabled` defaults to `True`, matching the
  established soft-toggle convention (`workflow_engine.enabled`,
  `workflow_scheduler.enabled`, `automation.enabled`).

## 3. BackgroundWorkerModule (STEP 3)

Exposes the `worker` CLI namespace (`status`, `submit`, `list`, `info`,
`stop`, `help`) as thin `CommandModule` handlers, following the
`AutomationModule` / `WorkflowSchedulerModule` pattern.

- Pure translation layer: calls STEP 2's already-existing public API
  unchanged and formats `CommandResult` objects; no business logic
  duplicated in the CLI layer.
- Catches only the two domain exceptions STEP 2 already documents
  raising (`BackgroundWorkerServiceError`, `PoolShutDownError`).
- No `worker register`/`worker start` command exists, matching the
  EP-034/EP-035 precedent that there is no "register" concept distinct
  from direct submission.

## 4. Bootstrap wiring

`BackgroundWorkerService` is constructed only if
`workflow_engine_for_scheduler` (the live EP-033 `WorkflowEngine`) is
available this run — a hard dependency, matching how EP-034/EP-035
handle the same dependency. Construction failures
(`BackgroundWorkerServiceError`, `BackgroundWorkerPoolError`) are caught
and logged, leaving `self._background_worker_service = None` rather than
raising out of `Bootstrap.__init__` — consistent graceful-degradation
pattern with the rest of the file.

`BackgroundWorkerModule` is registered with the router only after the
service is confirmed constructed, avoiding a CLI namespace pointing at a
non-existent service.

## 5. Configuration

`config/config.yaml`'s `background_workers` block documents intent
clearly (`enabled`, `worker_count`, `shutdown_timeout`) and explicitly
notes that process-exit shutdown wiring is deferred — see Section 12.

## 6. CLI / module integration

Consistent with `AutomationModule`/`WorkflowSchedulerModule`: same
`CommandResult` shape, same `name`/`execute(action, arguments)` contract,
same `help` action convention.

## 7. Thread lifecycle and shutdown behavior

- Idle workers poll the queue every `poll_interval` (default 0.05s) so
  an idle pool shuts down quickly; a worker already executing a task is
  never interrupted mid-`WorkflowEngine.run()`.
- `shutdown()` never reports success from `join()` returning alone —
  every join is followed by an explicit `Thread.is_alive()` check, and
  only a confirmed-dead worker counts as stopped. This directly
  satisfies the "explicit `Thread.is_alive()` verification after
  `join()`" constraint carried over from STEP 1's design lessons.
- Threads are `daemon=True`, so an un-shut-down pool cannot itself hang
  interpreter exit — see Section 12 for the related production-safety
  observation.

## 8. Task lifecycle / state management

`PENDING → RUNNING → COMPLETED|FAILED` is enforced by
`_execute_task` alone; no other code path mutates `task.status`. State
transitions are always performed under `_tasks_lock`, and reads return
copies — no torn reads possible from another thread.

## 9. Error handling and fault containment

`_execute_task` never lets a bad workflow kill its worker thread: both
`WorkflowEngineError` and a bare `Exception` are caught and recorded as
a `FAILED` task with an `error` message, and the worker loop continues.
This matches the "production safety" requirement that a single bad task
must not take down the pool.

## 10. Encapsulation and coupling (Pool → Service → Module)

Dependency direction is one-way and consistent: `Module` depends on
`Service`'s public API only; `Service` depends on `Pool`'s public API
only; `Pool` depends on `WorkflowEngine.run()` only. No layer reaches
into another's private attributes. No circular imports were found.

## 11. Interaction with EP-033/EP-034/EP-035

`BackgroundWorkerPool` reuses the same live `WorkflowEngine` instance
Bootstrap already built for EP-033, through its public `run()` method —
the identical "reach a completed EP only through its public API"
discipline `WorkflowSchedulerEngine` (EP-034) and `AutomationEngine`
(EP-035) already follow. EP-036 introduces no new dependency edge that
EP-033 doesn't already expose, and nothing in EP-033/034/035 depends on
EP-036 — the dependency direction is strictly one-way, avoiding a cycle
across the four EPs.

## 12. Architecture risks / production-safety observations

Two items were identified. Neither is Critical or High — both are
consistent with issues the project has previously classified as Medium
or Low and tracked in `ARCHITECTURE_DEBT.md` rather than fixed inline.

**a. No process-exit shutdown wiring.** `src/main.py` only wires
`_save_memory_on_shutdown`; nothing calls
`BackgroundWorkerService.shutdown()` automatically at process exit.
This is explicitly and knowingly deferred — documented in three places
(`src/core/background_workers/__init__.py`,
`src/services/background_worker_service.py`, and the
`background_workers` block in `config/config.yaml`) as "a later EP-036
step." Because worker threads are daemon threads, this cannot hang
process exit, but it does mean any `RUNNING` task is terminated
mid-`WorkflowEngine.run()` and any `PENDING` queued task is silently
dropped on interpreter exit, unless a user has manually run
`worker stop` first. Recorded as **AD-005** below.

**b. Unbounded task history.** `BackgroundWorkerPool._tasks` retains
every `BackgroundTask` ever submitted for the pool's lifetime, with no
eviction, TTL, or cap. In a long-running Jarvis process with many
`worker submit` calls, this grows without bound. Not a concern for the
STEP 1–3 scope as delivered (no retention requirement was ever
specified), but a legitimate forward-looking scale item. Recorded as
**AD-006** below.

No Critical or High findings were identified. STEP 1–3 do not require a
dedicated Bug Fix step.

---

# Strengths

- Clean, one-way layering (Pool → Service → Module) matching the
  EP-034/EP-035 precedent exactly.
- No hidden coupling: every cross-layer and cross-EP call goes through a
  documented public method only.
- Correct thread-safety discipline: two purpose-specific locks, snapshot
  reads, and no lock held across a blocking/slow call.
- Shutdown correctness: `is_alive()`-verified termination rather than
  trusting `join()`'s return.
- Fault containment: a single bad workflow cannot kill a worker thread
  or the pool.
- Test isolation solved correctly at the pool level (`worker_threads()`
  instead of `threading.enumerate()`), carried through all three STEPs.
- Backward-compatible, consistent configuration defaults
  (`enabled: true`) matching sibling subsystems.

# Weaknesses / risks

- See Section 12 items (a) and (b) above.
- `BackgroundWorkerService._resolve_shutdown_timeout()` runs
  unconditionally in `__init__`, even when
  `background_workers.enabled` is `False`. An invalid
  `shutdown_timeout` therefore disables the whole subsystem via
  Bootstrap's catch block even though the timeout is functionally
  irrelevant to a disabled pool. Minor validation-ordering inconsistency
  only — not raised to a debt entry given its low impact, but noted here
  for visibility.
- `worker stop` has no corresponding `worker start`: once stopped, the
  pool cannot be revived without restarting the process. This matches
  EP-011 `ProcessModule`'s "process stop" precedent, so it is an
  accepted, consistent pattern rather than a new risk.

---

# Architecture Debt discovered

Two new items are genuinely justified by this audit and have been added
to `docs/architecture/ARCHITECTURE_DEBT.md`:

- **AD-005** (Medium) — No process-exit shutdown wiring for
  `BackgroundWorkerService`; in-flight/pending tasks are lost on
  interpreter exit outside of an explicit `worker stop`.
- **AD-006** (Low) — `BackgroundWorkerPool._tasks` has no eviction/TTL,
  growing unbounded over a long-running process.

No other findings met the bar for a new debt entry.

---

# Regression assessment

STEP 1, STEP 2, and STEP 3 behavior is intact. This audit made no
changes to `background_worker_pool.py`, `background_worker_service.py`,
`background_worker_module.py`, their test files, `bootstrap.py`, or
`config/config.yaml`.

# Production safety

Confirmed: a running Jarvis process remains usable before and after
this audit. No code was touched; the audit is read-only by construction.

---

EP-036 STEP 4 (Architecture Audit) is complete.
