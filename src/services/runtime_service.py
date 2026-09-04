"""RuntimeService: a read-only introspection surface over Jarvis's own runtime.

Per `EP059_DESIGN.md` (Owner Decision D1, "Candidate A"), this module
adds exactly one new capability: a small, read-only aggregation of
facts that already exist elsewhere in the process into one
`RuntimeStatus` snapshot -- which execution contexts (Shell, REST API
Server, Background Worker Pool) are active this run, basic identifying
facts about each, and the process's own PID/uptime. It performs no
computation of its own beyond assembling these already-real facts into
one shape, and never starts, stops, reconfigures, or otherwise
mutates any component it reports on.

Every field is derived by calling an already-existing, unmodified
public property/method on an already-constructed object:
`RestApiServer.is_running`/`.host`/`.port` (EP-043), and
`BackgroundWorkerService.status()` -> `BackgroundWorkerStatus`
(EP-036). `RuntimeService` imports neither `RestApiServer` nor
`BackgroundWorkerService`'s own internals -- only their already-public
surface, exactly as `EP059_DESIGN.md` Section 4/6.2 specifies.

Per Owner Decision D3, `RuntimeStatus` is kept as a small, inline,
frozen dataclass in this file, matching EP-057's own precedent for a
single, small result type (`QueryOutcome` in
`context_compression_service.py`) rather than a new `src/core/runtime/`
package -- `RuntimeService` introspects; it does not own an
Engine/Manager/Provider hierarchy of its own.

Per Owner Decision D4 (EP-059), Scheduler/Telegram status was
originally excluded from v1 on the premise that neither is
auto-started as a side effect of `Bootstrap.initialize()`. EP-060
(`EP060_DESIGN.md` Section 5.3) found this premise to be factually
incorrect for the Scheduler specifically: `SchedulerService.__init__`
auto-starts its own tick-loop thread whenever `scheduler.enabled` and
`scheduler.auto_start` are both true -- and both default to `true` in
`config/config.yaml`. `RuntimeStatus` is therefore widened (EP-060
Section 9.1) to also observe Scheduler, read-only, via
`SchedulerService.status()`. Telegram remains excluded --
`telegram.auto_start` genuinely defaults to `false`, so EP-059's
original reasoning still holds for it (EP-060 Owner Decision D4,
recommended option (a)).

Per Owner Decision D5 (EP-059), this service originally exposed no
control surface of any kind. EP-060 (`EP060_DESIGN.md` Section 9.2-9.3,
Owner Decision D1/D2) adds exactly one new, narrow control operation --
`shutdown()` -- coordinating an already-fixed, already-ordered shutdown
of the two execution contexts that already expose a public, idempotent
shutdown primitive (REST API Server, Background Worker Service). It
does not become a general control API: no `start()`/`restart()`/
per-component-targeted operation is added, and the Scheduler's tick
loop is deliberately left unstopped (no public primitive exists to
stop it without modifying an EP-011 core file -- EP-060 Owner Decision
D5, recommended option (a), out of scope for this EP). `shutdown()` is
invoked exclusively by `Bootstrap.shutdown()` -- it is never exposed
as a `RuntimeModule` CLI/REST action (EP-060 Owner Decision D3,
recommended option (a)); see `runtime_module.py`.

Per Owner Decision D6, no `runtime.*` configuration key is read or
introduced -- `RuntimeService` is constructed unconditionally whenever
`Bootstrap.initialize()` runs, since it performs no I/O of its own and
has nothing to gate. `shutdown()` reuses
`BackgroundWorkerService.shutdown()`'s own already-existing default
timeout resolution (`background_workers.shutdown_timeout`) rather than
introducing a new configuration key (EP-060 Section 14).
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass

from src.core.api.rest_api_server import RestApiServer
from src.core.shell import InteractiveShell
from src.services.background_worker_service import BackgroundWorkerService
from src.services.scheduler_service import SchedulerService


@dataclass(frozen=True)
class RuntimeStatus:
    """One aggregated snapshot of this Jarvis instance's own runtime shape.

    Attributes:
        pid: This process's OS process id (`os.getpid()`).
        uptime_seconds: Seconds elapsed since this `Bootstrap` instance
            was constructed (not since `initialize()` completed, and
            not re-captured on a second `initialize()` call -- see
            `RuntimeService.__init__`'s `started_at` parameter).
        shell_active: Whether an `InteractiveShell` reference was
            supplied this run (the Shell has no separate
            "running"/"stopped" state of its own to report beyond its
            mere existence -- see `EP059_DESIGN.md` Section 6.2).
        api_active: Whether the REST API Server is currently listening
            (`RestApiServer.is_running`), or False if no
            `RestApiServer` reference was supplied this run (e.g.
            'api.enabled: false').
        api_host: The REST API Server's configured host, or None if
            `api_active` is False.
        api_port: The REST API Server's actual bound port, or None if
            `api_active` is False.
        background_workers_active: Whether the Background Worker Pool
            is currently running
            (`BackgroundWorkerService.status().running`), or False if
            no `BackgroundWorkerService` reference was supplied this
            run.
        background_worker_count: The Background Worker Pool's
            configured worker-thread count, or 0 if
            `background_workers_active` is False.
        background_worker_task_count: The number of tasks ever
            submitted to the live Background Worker Pool, or 0 if
            `background_workers_active` is False.
        scheduler_active: Whether the Scheduler's tick loop is
            currently running (`SchedulerService.status().running`),
            or False if no `SchedulerService` reference was supplied
            this run. Added by EP-060 (Section 9.1), correcting
            EP-059 Owner Decision D4's now-outdated premise that the
            Scheduler is never auto-started as a side effect of
            `Bootstrap.initialize()` -- see this module's docstring.
        scheduler_jobs_registered: The number of jobs currently
            registered with the Scheduler
            (`SchedulerService.status().jobs_registered`), or 0 if
            `scheduler_active` is False. Added by EP-060.
    """

    pid: int
    uptime_seconds: float
    shell_active: bool
    api_active: bool
    api_host: str | None
    api_port: int | None
    background_workers_active: bool
    background_worker_count: int
    background_worker_task_count: int
    scheduler_active: bool = False
    scheduler_jobs_registered: int = 0


@dataclass(frozen=True)
class RuntimeShutdownReport:
    """Result of `RuntimeService.shutdown()` (EP-060).

    Attributes:
        rest_api_was_active: Whether the REST API Server was running
            immediately before this call (False if no `RestApiServer`
            reference was supplied, or if it was already stopped).
        rest_api_stopped: True if the REST API Server is confirmed not
            running after this call (including if it was never active
            to begin with -- nothing to do counts as success).
        background_workers_was_active: Whether the Background Worker
            Service reported `running=True` immediately before this
            call (False if no `BackgroundWorkerService` reference was
            supplied). Per `EP060_DESIGN.md` Section 5.5/9.3, this
            field inherits a pre-existing `BackgroundWorkerService.
            status()` limitation: it cannot distinguish "running" from
            "already shut down" -- a second `shutdown()` call may still
            report this as True even though shutdown already completed.
            This is disclosed, not fixed, by EP-060.
        background_workers_stopped: The `bool` returned by
            `BackgroundWorkerService.shutdown()` unchanged (True if
            every worker was confirmed stopped, or if the subsystem was
            disabled this run; False if termination was not verified or
            timed out). True if no `BackgroundWorkerService` reference
            was supplied.
    """

    rest_api_was_active: bool
    rest_api_stopped: bool
    background_workers_was_active: bool
    background_workers_stopped: bool


class RuntimeService:
    """Read-only/lifecycle-coordinating aggregator of Jarvis's own runtime.

    Depends only on already-constructed, `None`-able references to the
    execution contexts it reports on and coordinates -- it never
    constructs any of them, never becomes their sole reference-holder
    (`Bootstrap` remains that), and never starts or reconfigures any of
    them. Safe to construct with every dependency `None` (e.g. every
    optional subsystem disabled this run); `status()` still returns a
    valid, all-`False`/zero snapshot in that case, and `shutdown()`
    still returns a valid, all-"nothing to do" report, neither ever
    raising for that reason alone.

    Public surface is exactly `{status, shutdown}` (EP-060
    `EP060_DESIGN.md` Section 9.2) -- no `start()`, `restart()`, or
    per-component-targeted operation exists, and nothing about which
    components `shutdown()` acts on is configurable or dynamically
    dispatched; it coordinates one fixed, predetermined sequence.
    """

    def __init__(
        self,
        started_at: float,
        rest_api_server: RestApiServer | None,
        background_worker_service: BackgroundWorkerService | None,
        shell: InteractiveShell | None,
        scheduler_service: SchedulerService | None = None,
    ) -> None:
        """Initialize the RuntimeService.

        Args:
            started_at: A `time.monotonic()` timestamp captured once,
                at `Bootstrap.__init__()` time (not at `initialize()`
                time, and not re-captured on a second `initialize()`
                call), used to compute `uptime_seconds`.
            rest_api_server: The already-constructed EP-043
                `RestApiServer` for this run, or None if the REST API
                subsystem is disabled or was not yet built. Only
                `.is_running`/`.host`/`.port` are ever read by
                `status()`; only `.stop()` is ever called, and only by
                `shutdown()` (EP-060) -- never started or reconfigured
                by this service.
            background_worker_service: The already-constructed EP-036
                `BackgroundWorkerService` for this run, or None if the
                Background Worker subsystem is disabled, invalidly
                configured, or unavailable this run. Only `.status()`
                is ever read by `status()`; only `.shutdown()` is ever
                called, and only by `shutdown()` (EP-060) -- never
                started or reconfigured by this service.
            shell: The already-constructed `InteractiveShell` for this
                run, or None if it has not yet been built. Never
                driven or mutated by this service -- only its mere
                presence is reported.
            scheduler_service: The already-constructed EP-011
                `SchedulerService` for this run, or None if the
                Scheduler subsystem is disabled or was not yet built.
                Keyword-defaulted to `None` so every existing EP-059
                call site continues to construct a valid
                `RuntimeService` unchanged (`EP060_DESIGN.md` Section
                9.1). Only `.status()` is ever read -- `shutdown()`
                (EP-060) deliberately does not call anything on this
                dependency; the Scheduler's tick loop is observed, not
                controlled, in v1 (Owner Decision D5).
        """
        self._started_at = started_at
        self._rest_api_server = rest_api_server
        self._background_worker_service = background_worker_service
        self._shell = shell
        self._scheduler_service = scheduler_service

    # ---------- Public API ----------

    def status(self) -> RuntimeStatus:
        """Return one aggregated `RuntimeStatus` snapshot of the current runtime.

        Never raises: every dependency is read defensively (`None`
        dependencies simply report as inactive), and every field comes
        from an already-existing, unmodified public property/method on
        an already-constructed object -- no new computation, network
        call, or file I/O is performed here.
        """
        api_active = False
        api_host: str | None = None
        api_port: int | None = None
        if self._rest_api_server is not None and self._rest_api_server.is_running:
            api_active = True
            api_host = self._rest_api_server.host
            api_port = self._rest_api_server.port

        background_workers_active = False
        background_worker_count = 0
        background_worker_task_count = 0
        if self._background_worker_service is not None:
            worker_status = self._background_worker_service.status()
            background_workers_active = worker_status.running
            background_worker_count = worker_status.worker_count
            background_worker_task_count = worker_status.task_count

        scheduler_active = False
        scheduler_jobs_registered = 0
        if self._scheduler_service is not None:
            scheduler_status = self._scheduler_service.status()
            scheduler_active = scheduler_status.running
            scheduler_jobs_registered = scheduler_status.jobs_registered

        return RuntimeStatus(
            pid=os.getpid(),
            uptime_seconds=time.monotonic() - self._started_at,
            shell_active=self._shell is not None,
            api_active=api_active,
            api_host=api_host,
            api_port=api_port,
            background_workers_active=background_workers_active,
            background_worker_count=background_worker_count,
            background_worker_task_count=background_worker_task_count,
            scheduler_active=scheduler_active,
            scheduler_jobs_registered=scheduler_jobs_registered,
        )

    def shutdown(self) -> RuntimeShutdownReport:
        """Coordinate graceful shutdown of the execution contexts this
        service already observes that already expose a public, idempotent
        stop/shutdown primitive: the REST API Server and the Background
        Worker Service (`EP060_DESIGN.md` Section 9.3).

        Deliberately excludes the Scheduler -- `SchedulerService`
        (EP-011) exposes no public method to stop its tick loop; adding
        one would mean modifying an already-completed EP's own core
        file, which `EP060_DESIGN.md` Owner Decision D5 treats as a
        separate, future decision, not a default action. Deliberately
        excludes the Shell -- `InteractiveShell` owns no background
        thread or held OS resource of its own to release; its lifecycle
        is owned by whichever loop is running it (`main.py`), not by
        this service.

        Ordering: the REST API Server is stopped first, then the
        Background Worker Service is shut down second (`wait=True`,
        using its own already-resolved
        'background_workers.shutdown_timeout' default) -- closing the
        external, network-reachable listener before background
        execution is signaled to stop, so no new HTTP-triggered command
        can be dispatched while workers are draining.

        Idempotent: safe to call more than once. Every underlying call
        (`RestApiServer.stop()`, `BackgroundWorkerService.shutdown()`)
        is already independently idempotent, so a second call is a
        no-op for a subsystem already stopped. This method holds no
        additional "already shut down" state of its own.

        Partial failure handling: no `try`/`except` is added here.
        `RestApiServer.stop()` propagates any OS-level exception
        unguarded, unchanged from `Bootstrap.shutdown()`'s own,
        pre-EP-060 behavior. `BackgroundWorkerService.shutdown()`
        already returns `False` rather than raising on a timeout; that
        `bool` is forwarded into the report unchanged. Because the REST
        API Server is stopped first, an exception there means the
        Background Worker Service is never reached for that call.

        Returns:
            A `RuntimeShutdownReport` describing which subsystems were
            active before this call and whether each was confirmed
            stopped.
        """
        rest_api_was_active = (
            self._rest_api_server is not None and self._rest_api_server.is_running
        )
        if self._rest_api_server is not None:
            self._rest_api_server.stop()
        rest_api_stopped = (
            self._rest_api_server is None or not self._rest_api_server.is_running
        )

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
        )
