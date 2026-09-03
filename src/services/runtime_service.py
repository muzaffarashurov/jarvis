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

Per Owner Decision D4, Scheduler/Telegram status is deliberately not
observed in v1 -- neither is auto-started as a side effect of
`Bootstrap.initialize()` (unlike the REST API Server and the
Background Worker Pool), so v1's scope is limited to the execution
contexts that exist as a side effect of bootstrapping alone.

Per Owner Decision D5, this service exposes no control surface of any
kind -- no restart/shutdown/reconfigure action exists here or in
`RuntimeModule`; `status()` is the only public method.

Per Owner Decision D6, no `runtime.*` configuration key is read or
introduced -- `RuntimeService` is constructed unconditionally whenever
`Bootstrap.initialize()` runs, since it performs no I/O of its own and
has nothing to gate.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass

from src.core.api.rest_api_server import RestApiServer
from src.core.shell import InteractiveShell
from src.services.background_worker_service import BackgroundWorkerService


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


class RuntimeService:
    """Read-only aggregator of Jarvis's own already-existing runtime facts.

    Depends only on already-constructed, `None`-able references to the
    execution contexts it reports on -- it never constructs, starts,
    stops, or reconfigures any of them. Safe to construct with every
    dependency `None` (e.g. every optional subsystem disabled this
    run); `status()` still returns a valid, all-`False`/zero snapshot
    in that case, never raising.
    """

    def __init__(
        self,
        started_at: float,
        rest_api_server: RestApiServer | None,
        background_worker_service: BackgroundWorkerService | None,
        shell: InteractiveShell | None,
    ) -> None:
        """Initialize the RuntimeService.

        Args:
            started_at: A `time.monotonic()` timestamp captured once,
                at `Bootstrap.__init__()` time (not at `initialize()`
                time, and not re-captured on a second `initialize()`
                call), used to compute `uptime_seconds`.
            rest_api_server: The already-constructed EP-043
                `RestApiServer` for this run, or None if the REST API
                subsystem is disabled or was not yet built. Never
                started, stopped, or reconfigured by this service --
                only `.is_running`/`.host`/`.port` are ever read.
            background_worker_service: The already-constructed EP-036
                `BackgroundWorkerService` for this run, or None if the
                Background Worker subsystem is disabled, invalidly
                configured, or unavailable this run. Never started,
                stopped, or reconfigured by this service -- only
                `.status()` is ever called.
            shell: The already-constructed `InteractiveShell` for this
                run, or None if it has not yet been built. Never
                driven or mutated by this service -- only its mere
                presence is reported.
        """
        self._started_at = started_at
        self._rest_api_server = rest_api_server
        self._background_worker_service = background_worker_service
        self._shell = shell

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
        )
