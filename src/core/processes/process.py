"""Process model for EP-008 Process Catalog & Smart Orchestrator.

Defines the static catalog entry (`Process`) and the small set of
enums describing a process's restart policy and health status. This
module owns no runtime state and performs no execution: it is pure
data, matching the "Configuration only" role of a model layer in this
project (see src/core/execution/models.py for the equivalent pattern
in the ExecutionEngine).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class RestartPolicy(str, Enum):
    """Supported restart policies for a registered process."""

    NEVER = "never"
    MANUAL = "manual"
    ALWAYS = "always"


class ProcessHealth(str, Enum):
    """Lifecycle/health states a process can report.

    Mirrors the states required by EP-008: READY, RUNNING, STOPPED,
    FAILED, UNKNOWN.
    """

    READY = "READY"
    RUNNING = "RUNNING"
    STOPPED = "STOPPED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class Process:
    """A single catalog entry describing a process Jarvis coordinates.

    A Process is metadata only: it does not hold a live handle, PID,
    or running state. Runtime state is always asked of the owning
    service (e.g. InvoiceService, FastResponseService) through
    ProcessService, per the project's Single Source of Truth rule.

    Attributes:
        id: Unique, stable identifier for the process
            (e.g. "invoice_automation"). Used as the dependency key.
        name: Human-readable display name (e.g. "Invoice Automation").
        description: Short description shown by `process info`.
        enabled: Whether this process participates in dependency
            resolution, startup, and `process status` reporting.
        dependencies: IDs of processes that must be running before
            this one is started.
        restart_policy: The RestartPolicy governing automatic restarts.
        health_check: Whether ProcessService should evaluate this
            process's health when computing status.
        startup_timeout: Maximum seconds allowed for this process to
            become RUNNING/READY after a start request.
        shutdown_timeout: Maximum seconds allowed for this process to
            reach STOPPED after a stop request.
    """

    id: str
    name: str
    description: str
    enabled: bool = True
    dependencies: tuple[str, ...] = field(default_factory=tuple)
    restart_policy: RestartPolicy = RestartPolicy.MANUAL
    health_check: bool = True
    startup_timeout: int = 30
    shutdown_timeout: int = 30
