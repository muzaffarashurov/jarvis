# Architecture Debt

Version: 1.0

This document tracks architectural debt discovered during STEP 4 architecture audits.

The purpose of this document is to prevent non-critical issues from interrupting roadmap development.

Only issues confirmed by architecture audits may be recorded here.

---

# Rules

Critical issues

- Must be fixed immediately.
- Roadmap development stops until resolved.

High issues

- Fix before the next major milestone.

Medium issues

- Postpone.
- Schedule for Architecture Cleanup milestone.

Low issues

- Postpone.
- Fix only when touching related code.

Never fix Architecture Debt during a normal Engineering Phase (EP).

Architecture Debt is addressed only during a dedicated cleanup milestone.

---

# Status

| ID | Severity | Status |
|----|----------|--------|
| - | - | - |
| AD-005 | Medium | Open |
| AD-006 | Low | Open |
| AD-007 | Low | Open |
| AD-008 | Low | Open |

Status values:

- Open
- Planned
- In Progress
- Fixed
- Rejected

---

# Debt Items

---

## AD-001

**Severity**

Medium

**Discovered in**

EP034 Architecture Audit

**Files**

src/services/workflow_scheduler_service.py

**Description**

Malformed `workflow_scheduler.tick_interval` may terminate the background thread instead of degrading gracefully.

**Why it matters**

A configuration error can silently disable automatic workflow scheduling.

**Recommended solution**

Validate `tick_interval` during service initialization or move parsing inside the protected execution loop.

**Planned milestone**

Architecture Cleanup v0.2

**Status**

Open

---

## AD-002

**Severity**

Medium

**Discovered in**

EP034 Architecture Audit

**Files**

src/bootstrap.py

**Description**

Bootstrap catches `WorkflowSchedulerError`, but no component currently throws this exception.

**Why it matters**

Graceful degradation path exists but is currently unreachable.

**Recommended solution**

Introduce configuration validation that raises `WorkflowSchedulerError` for invalid scheduler settings.

**Planned milestone**

Architecture Cleanup v0.2

**Status**

Open

---

## AD-003

**Severity**

Low

**Discovered in**

EP033 Architecture Audit

**Files**

Multiple service modules

**Description**

Several service modules define identical `ProviderSelectionResult` DTOs.

**Why it matters**

Minor duplication of data transfer objects.

**Recommended solution**

Evaluate introducing a shared immutable DTO during Architecture Cleanup.

**Planned milestone**

Architecture Cleanup v0.2

**Status**

Open

---

## AD-005

**Severity**

Medium

**Discovered in**

EP036 Architecture Audit

**Files**

src/services/background_worker_service.py
src/main.py

**Description**

No process-exit shutdown wiring calls `BackgroundWorkerService.shutdown()` automatically. Worker threads are daemon threads, so this cannot hang process exit, but a `RUNNING` task is terminated mid-`WorkflowEngine.run()` and any `PENDING` queued task is silently dropped on interpreter exit unless a user has manually run `worker stop` first.

**Why it matters**

Background tasks can be lost without any graceful drain on normal process termination.

**Recommended solution**

Wire `BackgroundWorkerService.shutdown()` into `src/main.py`'s existing shutdown path, alongside `_save_memory_on_shutdown`.

**Planned milestone**

Architecture Cleanup v0.2

**Status**

Open

---

## AD-006

**Severity**

Low

**Discovered in**

EP036 Architecture Audit

**Files**

src/core/background_workers/background_worker_pool.py

**Description**

`BackgroundWorkerPool._tasks` retains every `BackgroundTask` ever submitted for the pool's lifetime, with no eviction, TTL, or cap.

**Why it matters**

In a long-running Jarvis process with many `worker submit` calls, task history memory usage grows unbounded.

**Recommended solution**

Evaluate a bounded history (eviction policy or TTL for `COMPLETED`/`FAILED` tasks) during Architecture Cleanup.

**Planned milestone**

Architecture Cleanup v0.2

**Status**

Open

---

## AD-007

**Severity**

Low

**Discovered in**

EP037 Architecture Audit

**Files**

src/bootstrap.py
src/core/automation_engine/automation_engine.py
src/core/background_workers/background_worker_pool.py

**Description**

When a background-worker task completion triggers an automation rule (via the EP-037 STEP 3 adapter), the rule's action workflow is dispatched synchronously through `AutomationEngine.notify_run()`, running on the same `BackgroundWorkerPool` worker thread that just completed the triggering task, rather than being queued back through the pool or dispatched on a separate thread.

**Why it matters**

Several near-simultaneous background task completions that each trigger a slow-running automation action workflow could tie up multiple pool workers longer than their own task's execution time, delaying processing of whatever else is queued. This does not corrupt task state or affect shutdown correctness -- it is a latency characteristic, not a defect.

**Recommended solution**

If this becomes a practical issue, consider dispatching automation-triggered action workflows through the pool itself (e.g. `BackgroundWorkerPool.submit()`) instead of synchronously inline, or documenting the expectation that automation action workflows triggered from background tasks should be lightweight.

**Planned milestone**

Architecture Cleanup v0.2

**Status**

Open

---

## AD-008

**Severity**

Low

**Discovered in**

EP037 Architecture Audit

**Files**

src/bootstrap.py

**Description**

The EP-037 STEP 3 BackgroundWorker-to-AutomationEngine adapter reads `kwargs["workflow_id"]` and `kwargs["result"]` from the `background_worker.task_completed` event without any explicit contract (e.g. a typed payload) tying it to `BackgroundWorkerPool`'s exact `publish()` kwarg names.

**Why it matters**

If a future change altered that payload's key names, the adapter would not fail loudly. `EventBus.publish()`'s own exception isolation would catch the resulting `KeyError`, log it, and silently stop triggering automation for background-worker completions, with no other visible symptom.

**Recommended solution**

If more EventBus payloads accumulate implicit key-name contracts like this one, consider a light typed-payload convention (e.g. a small dataclass per event) so a shape mismatch fails a type check instead of failing silently at runtime.

**Planned milestone**

Architecture Cleanup v0.2

**Status**

Open

---

# Completed Debt

Move resolved items here.

---

## AD-000

Example only.

Status: Fixed

Resolved in:

Architecture Cleanup v0.2

Description:

Example completed architecture improvement.

AD-004 — Unreachable AutomationError handler in Bootstrap

Status: Open
Priority: Medium
Introduced: EP-035
Related: AD-002

File:
src/bootstrap.py

Description:
The EP-035 Bootstrap wiring block catches AutomationError, but the
constructors executed inside the try block currently do not raise
AutomationError. Therefore the exception handler is currently unreachable.

Impact:
Low runtime risk. Moderate maintainability and documentation risk.
The graceful-degradation path is currently not backed by real
construction-time validation.

Recommended action:
Review together with AD-002 during a future Architecture Cleanup
milestone. Either introduce valid construction-time configuration
validation or simplify the unreachable exception handlers.

Do not fix during normal EP development.