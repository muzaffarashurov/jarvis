"""Business logic that wires EP-036 BackgroundWorkerPool into the application.

BackgroundWorkerService is a thin, config-driven owner of a single
`BackgroundWorkerPool` instance, matching the architecture named in
the EP-036 STEP 2 task brief:

    config -> Bootstrap -> BackgroundWorkerService -> BackgroundWorkerPool

It implements no task-execution logic of its own -- dequeuing,
dispatch, and status tracking all remain exclusively
`BackgroundWorkerPool`'s concern (itself reaching EP-033's
`WorkflowEngine` only through its public `run()` method, unchanged
since STEP 1). This service's own responsibility is limited to:
resolving 'background_workers.*' configuration, deciding whether a
pool should exist at all this run, owning the one pool instance it
creates, and exposing a narrow wrapper API so no other module ever
needs to reach into the pool's internals directly.

STEP 2 SCOPE NOTE: this step wires configuration, this Service, and
Bootstrap construction only. No CLI-facing `BackgroundWorkerModule`
and no 'background_workers' command namespace exist yet -- those
remain a deliberately separate, later step, exactly as EP-036's own
package docstring (`src/core/background_workers/__init__.py`)
originally deferred them from STEP 1. Application-level shutdown
wiring (calling `shutdown()` from `src/main.py` at process exit) is
likewise deferred; this class exposes a proper `shutdown()` method so
that later wiring is a pure addition, but nothing in this step calls
it automatically.

Lifecycle, matching EP-034's `WorkflowSchedulerService` in spirit but
adapted to how `BackgroundWorkerPool` itself works: unlike
`WorkflowSchedulerEngine` (constructed inert, started separately via
`auto_start`), `BackgroundWorkerPool.__init__` starts its worker
threads immediately -- there is no decoupled "construct but don't
start" step to gate without modifying the pool itself (out of scope
for STEP 2; see the STEP 2 plan's defect check). So this service has
exactly one gate, 'background_workers.enabled': True constructs (and
so starts) the pool at `BackgroundWorkerService.__init__` time; False
never constructs one at all (`_pool` stays None for this instance's
entire lifetime -- there is no separate "paused, not yet started"
state to model).

Backward compatibility: 'background_workers.enabled' defaults to True
when absent, matching every other soft-toggle subsystem in this
project ('workflow_engine.enabled', 'workflow_scheduler.enabled',
'automation.enabled'). This is safe specifically for this subsystem
because nothing in STEP 2 wires any producer to call `submit()`
automatically -- an enabled-by-default pool this run only means
`worker_count` idle daemon threads exist, blocked on an empty queue,
with zero other observable behavior change.
"""

from __future__ import annotations

from dataclasses import dataclass

from loguru import logger

from src.core.background_workers.background_worker_pool import (
    BackgroundTask,
    BackgroundWorkerPool,
    BackgroundWorkerPoolError,
)
from src.core.config import Config
from src.core.workflow_engine.workflow_engine import WorkflowEngine

_DEFAULT_WORKER_COUNT = 4
_DEFAULT_SHUTDOWN_TIMEOUT = 10.0


class BackgroundWorkerServiceError(Exception):
    """Raised for invalid 'background_workers.*' configuration.

    Distinct from `BackgroundWorkerPoolError` (raised by
    `BackgroundWorkerPool` itself for a bad `worker_count` at
    construction time) -- this covers configuration problems this
    service detects before ever attempting to construct a pool, e.g.
    a non-integer 'background_workers.worker_count'. Both are treated
    as equally "this subsystem is disabled for this run" by Bootstrap.
    """


@dataclass(frozen=True)
class BackgroundWorkerStatus:
    """Result of a background-worker status query.

    Attributes:
        enabled: Whether 'background_workers.enabled' resolved True
            for this run.
        running: Whether this service currently owns a live pool.
            Always equal to `enabled` for a successfully constructed
            `BackgroundWorkerService` (see the class docstring's
            lifecycle note) -- kept as its own field for callers that
            care about pool liveness specifically, and so this shape
            stays stable if a future step introduces a state where
            they can differ (e.g. a pause/resume step).
        worker_count: Configured worker thread count, or 0 if not running.
        task_count: Number of tasks ever submitted to the live pool
            (across every status), or 0 if not running.
    """

    enabled: bool
    running: bool
    worker_count: int
    task_count: int


class BackgroundWorkerService:
    """Owns configuration resolution and the lifecycle of one BackgroundWorkerPool.

    Depends only on Config (its own 'background_workers.*' settings)
    and an already-constructed WorkflowEngine (EP-033), forwarded
    unchanged to the pool it builds. Implements no task-execution
    logic of its own -- every task-facing method below is a direct,
    narrow forward to the pool it owns; no other module is ever given
    the pool instance itself (see the class docstring's architecture
    note on hidden-coupling avoidance).
    """

    def __init__(self, config: Config, workflow_engine: WorkflowEngine) -> None:
        """Initialize the BackgroundWorkerService, constructing its pool if enabled.

        Args:
            config: Loaded application configuration, used to resolve
                'background_workers.enabled', 'background_workers.worker_count',
                and 'background_workers.shutdown_timeout'.
            workflow_engine: The already-constructed EP-033
                WorkflowEngine forwarded unchanged to the
                BackgroundWorkerPool this service builds (when
                enabled). Never mutated by this service.

        Raises:
            BackgroundWorkerServiceError: If 'background_workers.worker_count'
                is present but not a positive integer.
            BackgroundWorkerPoolError: Propagated unchanged if pool
                construction itself rejects the resolved worker count
                (defensive -- this should not happen given the
                validation performed here first).
        """
        self._config = config
        self._workflow_engine = workflow_engine
        self._shutdown_timeout = self._resolve_shutdown_timeout()
        self._pool: BackgroundWorkerPool | None = None

        if bool(config.get("background_workers.enabled", True)):
            worker_count = self._resolve_worker_count()
            self._pool = BackgroundWorkerPool(
                workflow_engine=workflow_engine,
                worker_count=worker_count,
            )
            logger.info(
                f"Background Worker Service started with {worker_count} worker(s)."
            )
        else:
            logger.info(
                "Background Worker Service disabled "
                "('background_workers.enabled: false')."
            )

    # ---------- Public API ----------

    def status(self) -> BackgroundWorkerStatus:
        """Return the Background Worker subsystem's overall status."""
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

    def submit(self, workflow_id: str) -> str:
        """Submit a workflow for background execution.

        Args:
            workflow_id: The id of an already-registered EP-033
                WorkflowDefinition, forwarded unchanged to
                `BackgroundWorkerPool.submit()`.

        Returns:
            The newly generated task id (see `BackgroundWorkerPool.submit`).

        Raises:
            BackgroundWorkerServiceError: If the Background Worker
                subsystem is disabled this run.
            PoolShutDownError: Propagated unchanged if the pool has
                already been shut down.
        """
        if self._pool is None:
            raise BackgroundWorkerServiceError("Background Worker service disabled.")
        return self._pool.submit(workflow_id)

    def get_task(self, task_id: str) -> BackgroundTask | None:
        """Return a snapshot of a submitted task, or None if unknown/unavailable.

        Args:
            task_id: A task id previously returned by `submit()`.

        Returns:
            A `BackgroundTask` snapshot, or None if the subsystem is
            disabled this run or `task_id` is unknown to the pool.
        """
        if self._pool is None:
            return None
        return self._pool.get_task(task_id)

    def list_tasks(self) -> list[BackgroundTask]:
        """Return every task ever submitted to the live pool, or [] if unavailable."""
        if self._pool is None:
            return []
        return self._pool.list_tasks()

    def shutdown(self, wait: bool = True, timeout: float | None = None) -> bool:
        """Shut down the owned pool, if one exists.

        Safe to call regardless of whether the subsystem is enabled
        this run -- a disabled service (no pool) reports success
        immediately, since there is nothing to shut down.

        Args:
            wait: Forwarded unchanged to `BackgroundWorkerPool.shutdown()`.
            timeout: Maximum seconds to wait. Defaults to this
                service's resolved 'background_workers.shutdown_timeout'
                when not given explicitly.

        Returns:
            True if the subsystem is disabled (nothing to shut down)
            or every worker was confirmed stopped; False otherwise
            (see `BackgroundWorkerPool.shutdown` for exact semantics).
        """
        if self._pool is None:
            return True
        resolved_timeout = timeout if timeout is not None else self._shutdown_timeout
        return self._pool.shutdown(wait=wait, timeout=resolved_timeout)

    # ---------- Internal helpers ----------

    def _resolve_worker_count(self) -> int:
        """Resolve and validate 'background_workers.worker_count'.

        Returns:
            The configured worker count (default `_DEFAULT_WORKER_COUNT`).

        Raises:
            BackgroundWorkerServiceError: If the configured value is
                not a positive integer. (`BackgroundWorkerPool` itself
                only guards against non-positive integers, not wrong
                types -- this mirrors how Bootstrap validates
                'embedding.batch_size' before constructing
                EmbeddingEngine.)
        """
        value = self._config.get("background_workers.worker_count", _DEFAULT_WORKER_COUNT)
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise BackgroundWorkerServiceError(
                "Invalid value for 'background_workers.worker_count': expected a "
                f"positive integer, got {value!r}."
            )
        return value

    def _resolve_shutdown_timeout(self) -> float:
        """Resolve and validate 'background_workers.shutdown_timeout'.

        Returns:
            The configured shutdown timeout in seconds (default
            `_DEFAULT_SHUTDOWN_TIMEOUT`).

        Raises:
            BackgroundWorkerServiceError: If the configured value is
                not a positive number.
        """
        value = self._config.get(
            "background_workers.shutdown_timeout", _DEFAULT_SHUTDOWN_TIMEOUT
        )
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
            raise BackgroundWorkerServiceError(
                "Invalid value for 'background_workers.shutdown_timeout': expected a "
                f"positive number, got {value!r}."
            )
        return float(value)
