"""EP-036 Background Worker Pool.

Runs already-registered EP-033 `WorkflowDefinition`s in the
background, off the calling thread, by dispatching each submitted
`workflow_id` through the already-existing `WorkflowEngine.run()`
exclusively -- the same "reach a completed EP only through its public
API" discipline EP-034's `WorkflowSchedulerEngine` and EP-035's
`AutomationEngine` already follow. This package performs no AI
reasoning, no planning, and no direct subsystem/tool invocation of its
own; it only decides *which thread* an already-completed EP's public
API call happens to run on.

STEP 1 SCOPE NOTE (read before touching this package): this first
implementation step delivers only the core, standalone pool --
`BackgroundWorkerPool` (this package) plus its own EP-036 test suite.
It is deliberately NOT wired into `src/bootstrap.py` yet (no
`BackgroundWorkerService`/`BackgroundWorkerModule`, no
`background_workers.*` config, no CLI namespace, no production
worker-thread pool started at application boot). Test-process
isolation (letting `jarvis> test EP036` run safely inside an
already-running Jarvis application that may, in a later step, have
its own production pool) and any change to the global test runner are
explicitly out of scope for this step and are left for a later EP-036
step, per the EP-036 STEP 1 prompt. Nothing in this package assumes,
requires, or creates any such production wiring -- `BackgroundWorkerPool`
is fully self-contained and usable standalone, exactly as delivered
here.

Public API:
    BackgroundWorkerPool -- Configurable pool of daemon worker threads
        that execute submitted workflow runs and track their status.
    BackgroundTask -- Snapshot of a single submitted unit of work.
    TaskStatus -- The lifecycle states a BackgroundTask passes through.
    BackgroundWorkerPoolError -- Base class for errors raised by this
        package itself.
    InvalidWorkerCountError -- Raised when constructed with an invalid
        `worker_count`.
    PoolShutDownError -- Raised by `submit()` once the pool has been
        shut down.
"""

from __future__ import annotations

from src.core.background_workers.background_worker_pool import (
    BackgroundTask,
    BackgroundWorkerPool,
    BackgroundWorkerPoolError,
    InvalidWorkerCountError,
    PoolShutDownError,
    TaskStatus,
)

__all__ = [
    "BackgroundWorkerPool",
    "BackgroundTask",
    "TaskStatus",
    "BackgroundWorkerPoolError",
    "InvalidWorkerCountError",
    "PoolShutDownError",
]
