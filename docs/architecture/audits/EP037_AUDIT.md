# EP037 — Architecture Audit (STEP 4)

Status: READ-ONLY audit, per `docs/architecture/AI_DEVELOPMENT_PLAYBOOK.md`.

No source code, tests, or configuration were modified while producing this report.

---

# Scope

Audits EP-037 (Event Bus Enhancement & Cross-EP Decoupling) STEP 1–3 as implemented and validated:

- `EventBus` — `src/core/events.py` (STEP 2: thread-safety)
- `workflow.completed` publication — `src/services/workflow_engine_service.py`,
  `src/core/workflow_scheduler/workflow_scheduler_engine.py` (STEP 2)
- `background_worker.task_completed` / `background_worker.task_failed`
  publication — `src/core/background_workers/background_worker_pool.py`,
  `src/services/background_worker_service.py` (STEP 2)
- `AutomationEngine` subscription to `workflow.completed`, replacing
  `set_automation_hook()` for production wiring (STEP 2)
- BackgroundWorker → AutomationEngine adapter, subscribed to
  `background_worker.task_completed` only (STEP 3)
- Bootstrap wiring — `src/bootstrap.py`
- Test suite — `tests/EP037/test_event_bus.py`, registered in
  `src/modules/test_module.py`

This audit reviews EP-037 only, per playbook scope discipline. It does not
re-audit EP-033/034/035/036 internals beyond how EP-037 touches them.

---

# 1. EventBus (STEP 2)

`src/core/events.py::EventBus` is the project's sole publish/subscribe
mechanism (first introduced in EP-001, extended here) -- no second
EventBus implementation exists anywhere in the repository.

- Thread safety was added specifically because EP-036 worker threads,
  and now a production automation adapter, publish/subscribe
  concurrently: a single `threading.Lock` guards `_subscribers`;
  `subscribe()`/`unsubscribe()` mutate under the lock; `publish()`
  takes a snapshot copy of the handler list under the lock, then
  releases the lock before invoking any handler.
- This is the identical "lock, snapshot, release, then call out"
  discipline `BackgroundWorkerPool` already established in EP-036 --
  not a new pattern invented for EP-037.
- A handler that itself calls `subscribe()`/`unsubscribe()`/`publish()`
  during its own invocation cannot deadlock: the lock is never held
  while a handler runs. Verified directly by
  `_test_handler_subscribe_during_publish_no_deadlock` and
  `_test_handler_self_unsubscribe_during_publish`.
- Public API (`subscribe`, `unsubscribe`, `publish`, `event_names`) is
  byte-for-byte unchanged from EP-001; `Orchestrator`'s three original
  publishes (`skills.loaded`, `orchestrator.started`,
  `orchestrator.stopped`) required no changes.

## 2. workflow.completed (STEP 2)

`WorkflowEngineService.run()` and `WorkflowSchedulerEngine`'s dispatch
path both publish a single shared event name, `workflow.completed`,
with `definition_id`/`result` kwargs, at the exact point their existing
`automation_hook` already fired. Both engines gained an optional
`event_bus` constructor parameter, defaulting to `None`, reproducing
pre-EP-037 behavior exactly when omitted.

- Purely additive: `set_automation_hook()` and its call sites are
  untouched in both classes -- an external caller can still use the
  hook directly (`_test_set_automation_hook_still_works_directly`).
- Neither engine imports `AutomationEngine` or any EP-035 type; the
  only new import in both files is `from src.core.events import
  EventBus`, verified not to be an EP-035 type by EP-035's own
  `_test_hook_types_are_not_ep035_types` (see Section 11).

## 3. background_worker.task_completed / task_failed (STEP 2)

`BackgroundWorkerPool._execute_task` publishes
`background_worker.task_completed` (`task_id`, `workflow_id`, `result`)
or `background_worker.task_failed` (`task_id`, `workflow_id`, `error`)
at the existing `COMPLETED`/`FAILED` transitions, always outside
`_tasks_lock` -- the same lock-then-release-then-call-out discipline as
`EventBus.publish()` itself. `BackgroundWorkerPool`/`BackgroundWorkerService`
gained an optional `event_bus` parameter; task state semantics, locking,
and shutdown behavior are unchanged (confirmed by
`_test_background_worker_pool_task_state_unaffected_by_event_bus` and
`_test_background_worker_pool_and_service_api_unchanged`).

## 4. AutomationEngine subscription (STEP 2)

Bootstrap's production wiring reaches `AutomationEngine.notify_run()`
by `event_bus.subscribe("workflow.completed", automation_engine.notify_run)`
instead of the two separate `set_automation_hook()` calls the pre-EP-037
wiring used. One subscription now covers both the on-demand and
scheduled paths, since both engines publish the same event name.

## 5. BackgroundWorker → AutomationEngine adapter (STEP 3)

`BackgroundWorkerPool` calls `WorkflowEngine.run()` directly, not
through `WorkflowEngineService`, so a `worker submit` task never
publishes `workflow.completed` and had no path to automation before
STEP 3. A small closure defined inline in
`Bootstrap._build_command_router` subscribes to
`background_worker.task_completed` only, and re-keys the event's
existing `workflow_id` kwarg to the `definition_id` kwarg
`notify_run()` requires:

```python
def _on_background_worker_task_completed(**kwargs) -> None:
    automation_engine.notify_run(
        definition_id=kwargs["workflow_id"], result=kwargs["result"]
    )
```

- STEP 2's event payload contract is completely unchanged; the
  adapter adapts at the call site only, per the approved STEP 3 scope.
- Deliberately **not** subscribed to `background_worker.task_failed`:
  that event carries only `error: str`, never a `WorkflowRunResult`,
  which `notify_run()` requires and which a bare exception never
  produces. Verified by
  `_test_background_worker_task_failed_never_triggers_automation`.
- No new public API, no new class, no new file -- matching the
  "keep the adapter small and local" constraint.

## 6. Bootstrap wiring

Both subscriptions (`workflow.completed`, `background_worker.task_completed`)
are established inside the same `try` block as `AutomationEngine`
construction, gated by the identical `automation.enabled` check that
previously gated the hook-based wiring -- a disabled Automation Engine
still subscribes to neither event, verified by
`_test_bootstrap_disabled_automation_never_fires` and
`_test_bootstrap_disabled_automation_also_skips_background_worker_adapter`.
The adapter subscription happens before `BackgroundWorkerService`/`Pool`
are constructed further down the same method; this ordering is safe
because `EventBus.subscribe()` does not require a future publisher to
exist yet.

## 7. EventBus thread safety

Covered in Section 1. The concrete new production consequence,
introduced by STEP 3, is that `automation_engine.notify_run()` --
which can itself dispatch a full second workflow run via
`WorkflowEngine.run()` -- now executes synchronously on whichever
`BackgroundWorkerPool` worker thread just completed a task, not only
on the main thread (the on-demand/scheduled paths already had this
property; STEP 3 extends it to the worker-thread path). See Section 12
for the resulting production-safety observation.

## 8. Duplicate-notification prevention

The STEP 2 conflict (hook + event both wired to `notify_run` for the
same event source, double-firing every matched rule) does not recur
here, and cannot recur between STEP 2 and STEP 3's two subscriptions,
for a structural reason rather than a configuration one:
`workflow.completed` and `background_worker.task_completed` are
disjoint event names, each with exactly one subscriber, published from
two call paths that never both fire for the same task/run --
`BackgroundWorkerPool` never publishes `workflow.completed`, and
`WorkflowEngineService`/`WorkflowSchedulerEngine` are never invoked by
`BackgroundWorkerPool`. Verified directly by three tests:
`_test_on_demand_run_triggers_automation_exactly_once_via_event`,
`_test_background_worker_completion_adapter_triggers_automation_exactly_once`,
and, most directly,
`_test_background_worker_and_workflow_completed_do_not_double_fire`,
which keeps both subscriptions live at once (the real Bootstrap shape)
and confirms a background-only completion still fires the action
workflow exactly once. A fourth test,
`_test_hook_and_event_together_would_double_fire_if_both_wired`,
deliberately reproduces the STEP 2 misconfiguration in isolation and
confirms it *would* double-fire -- proving the exactly-once tests are
meaningful rather than vacuously true.

## 9. Interaction with EP-033/EP-034/EP-035/EP-036

No EP-033/EP-034/EP-035/EP-036 public API was removed or had its
existing behavior changed. `set_automation_hook()` remains fully
functional and independently usable in both EP-033 and EP-034 engines.
`BackgroundWorkerPool`/`BackgroundWorkerService`'s pre-EP-037 call
shape (no `event_bus` argument) still works unchanged. Regression
suites for all four EPs pass with identical counts to the pre-EP-037
baseline, with one understood, non-regression difference: EP-035's
suite count rose from 141 to 143, entirely explained by
`_test_hook_types_are_not_ep035_types` (see Section 11) now scanning
one additional import line in each of the two files EP-037 touched --
not a weakened or modified assertion.

## 10. Lifecycle and error handling

`EventBus` itself has no lifecycle beyond the process lifetime (Section
1). The adapter introduces no new lifecycle: it is a stateless closure,
created once during `Bootstrap._build_command_router` and never torn
down explicitly (matching every other subscription on this bus, none
of which are ever unsubscribed by Bootstrap). Error handling is
layered consistently: `EventBus.publish()` isolates a handler
exception with a log line; `notify_run()` additionally isolates a
per-rule dispatch exception internally (unchanged EP-035 behavior).
The adapter itself has no `try`/`except` of its own -- it relies
entirely on `EventBus.publish()`'s isolation, exactly like every other
handler subscribed to this bus.

## 11. Architectural layering

Dependency direction remains one-way and unchanged in shape:
`AutomationEngine` (EP-035) is still never imported by
`WorkflowEngineService`/`WorkflowSchedulerEngine` (EP-033/034) or by
`BackgroundWorkerPool`/`BackgroundWorkerService` (EP-036) -- confirmed
live by EP-035's own `_test_hook_types_are_not_ep035_types`, which
inspects the actual import lines of both EP-033/034 files and asserts
neither references `automation_engine`/`Automation`. The new
`from src.core.events import EventBus` import in each of those files,
plus in the two EP-036 files, is a dependency on core infrastructure
(`src/core/events.py`), the same category as `Config`/`Logger`, not a
peer-EP dependency. All new wiring (both subscriptions) lives in
`Bootstrap`, the project's existing composition root -- no EP source
file reaches into another EP's internals to wire these subscriptions
itself.

## 12. Architecture risks / production-safety observations

One new item was identified, upgrading a risk the EP-037 STEP 1 design
report already flagged as hypothetical ("a slow or misbehaving
subscriber could delay that worker") into a concrete, real production
behavior now that STEP 3 gives `BackgroundWorkerPool` a genuine
subscriber that does real work.

**Background-worker-triggered automation runs synchronously on the
worker thread.** When a `worker submit` task completes successfully
and matches an automation rule, `notify_run()` dispatches the rule's
action workflow via a direct, synchronous `WorkflowEngine.run()` call,
executing on the same `BackgroundWorkerPool` worker thread that just
finished the triggering task -- not on a separate thread, and not
queued back through the pool. With the default `worker_count` of 4,
several near-simultaneous task completions that each trigger a
slow-running action workflow could tie up multiple workers longer than
their own task's own execution time, delaying the pool's processing of
whatever else is `PENDING` in the queue. This does not corrupt task
state, does not deadlock (the automation action workflow itself is a
plain synchronous call, same as any other workflow run), and does not
affect shutdown correctness -- it is a latency characteristic, not a
defect. Recorded as **AD-007** below.

No Critical or High findings were identified.

---

# Strengths

- Zero second EventBus implementation anywhere -- the explicit
  constraint from the STEP 1 approval was honored throughout STEP 2
  and STEP 3.
- Every new production wiring point (`workflow.completed` subscription,
  the STEP 3 adapter) is additive: no existing public API was removed,
  narrowed, or had its behavior changed for a caller that doesn't use
  the new `event_bus` parameter.
- The STEP 2 hook/event double-trigger conflict was resolved
  structurally (disjoint event names, one subscriber each, disjoint
  publisher call paths) rather than by convention or by a comment
  asking future authors to be careful -- and STEP 3 extends that same
  structural guarantee rather than introducing a new risk of it.
- The double-fire scenario was proven to actually occur in isolation
  (`_test_hook_and_event_together_would_double_fire_if_both_wired`),
  which is stronger evidence than merely asserting the current wiring
  is correct.
- STEP 3's adapter is intentionally minimal: no new class, no new
  file, no new public API, no new configuration, no new CLI --
  matching the approved scope exactly.
- EP-035's own test suite, unmodified, independently re-validates that
  neither EP-033 nor EP-034 source file was pulled into an EP-035
  dependency by this work.

# Weaknesses / risks

- See Section 12 (AD-007).
- The STEP 3 adapter's `kwargs["workflow_id"]` / `kwargs["result"]`
  key access is implicitly coupled to `BackgroundWorkerPool`'s exact
  `publish()` kwarg names. If a future change altered that payload's
  key names, the adapter would not raise or fail loudly -- `EventBus.
  publish()`'s own exception isolation would catch the resulting
  `KeyError`, log it, and silently stop triggering automation for
  background-worker completions, with no other visible symptom.
  Recorded as **AD-008** below.
- `background_worker.task_failed` still has zero subscribers by
  design (per the approved STEP 3 scope) -- an accepted limitation,
  not new debt, matching the STEP 1 design report's original
  "no concrete subscriber exists yet" note.

---

# Architecture Debt discovered

Two new items are genuinely justified by this audit and have been
added to `docs/architecture/ARCHITECTURE_DEBT.md`:

- **AD-007** (Low) -- background-worker-triggered automation action
  workflows run synchronously on the triggering worker thread, which
  can delay that worker's availability for further queued tasks.
- **AD-008** (Low) -- the STEP 3 adapter's payload key access is
  implicitly, not explicitly, coupled to `BackgroundWorkerPool`'s
  publish-call kwarg names, with a silent (log-only) failure mode if
  that shape ever changes.

No other findings met the bar for a new debt entry.

---

# Regression assessment

EP-033, EP-034, EP-035, and EP-036 behavior is intact. This audit made
no changes to any STEP 1-3 source or test file. All regression suites
were previously re-verified during STEP 3's own validation
(EP033: 182, EP034: 113, EP035: 143 -- explained in Section 9,
EP036/STEP2/STEP3: 101/48/53, EP001: 20 -- all 0 failed).

# Production safety

Confirmed: a running Jarvis process remains usable before and after
this audit. No code was touched; the audit is read-only by
construction.

---

EP-037 STEP 4 (Architecture Audit) is complete.
