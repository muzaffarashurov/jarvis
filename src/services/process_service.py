"""Process orchestration service for EP-008 Process Catalog & Smart Orchestrator.

ProcessService coordinates process lifecycle (start/stop/restart/health)
and dependency resolution across the catalog owned by ProcessRegistry.
It contains no business logic of its own: every lifecycle action is
delegated to whichever existing component already owns that process
(InvoiceService, FastResponseService), per the project's Existing Code
Policy ("Always use existing services... never replace them").

TODO -- architecture gap:
The task's requested layering is
    ProcessService -> WorkflowService -> ExecutionEngine
but no WorkflowService / Workflow Engine component exists anywhere in
this codebase (no src/services/workflow_service.py or equivalent, and
src/core/orchestrator.py only loads skills -- it does not run
workflows). Per the Unknown API Policy, this service does not invent
one. The "workflow_engine" catalog entry is registered for visibility
(`process list` / `process status`), but its start/stop/restart/health
operations are TODO stubs until a real WorkflowService exists.
InvoiceService and FastResponseService, which do exist, are wired in
directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from loguru import logger

from src.core.command_router import CommandResult
from src.core.config import Config
from src.core.execution.engine import ExecutionEngine
from src.core.processes.process import Process, ProcessHealth
from src.core.processes.process_registry import ProcessRegistry
from src.services.fast_response_service import FastResponseService
from src.services.invoice_service import InvoiceService, InvoiceStatus


class UnknownProcessError(Exception):
    """Raised when an operation references a process id not in the catalog."""


class DependencyResolutionError(Exception):
    """Raised when dependency resolution finds a cycle or missing dependency."""


class ProcessHandler(Protocol):
    """Internal adapter interface used to reach an existing service.

    Every process id maps to exactly one ProcessHandler, so adding a
    new coordinated process never requires changing ProcessService's
    start/stop/restart/health logic itself.
    """

    def start(self) -> CommandResult:
        """Start the underlying process."""

    def stop(self) -> CommandResult:
        """Stop the underlying process."""

    def restart(self) -> CommandResult:
        """Restart the underlying process."""

    def health(self) -> ProcessHealth:
        """Return the current health of the underlying process."""


class _InvoiceHandler:
    """Adapts the existing InvoiceService to the ProcessHandler interface."""

    _HEALTH_MAP: dict[InvoiceStatus, ProcessHealth] = {
        InvoiceStatus.RUNNING: ProcessHealth.RUNNING,
        InvoiceStatus.STOPPED: ProcessHealth.STOPPED,
        InvoiceStatus.FAILED: ProcessHealth.FAILED,
        InvoiceStatus.UNKNOWN: ProcessHealth.UNKNOWN,
    }

    def __init__(self, invoice_service: InvoiceService) -> None:
        self._service = invoice_service

    def start(self) -> CommandResult:
        return self._service.start()

    def stop(self) -> CommandResult:
        return self._service.stop()

    def restart(self) -> CommandResult:
        return self._service.restart()

    def health(self) -> ProcessHealth:
        return self._HEALTH_MAP.get(self._service.status(), ProcessHealth.UNKNOWN)


class _FastResponseHandler:
    """Adapts the existing FastResponseService to the ProcessHandler interface.

    FastResponseService coordinates an Excel workbook opened through
    the OS default application; it exposes no stop()/restart()
    lifecycle (see src/services/fast_response_service.py). Per the
    Unknown API Policy those are not invented here.
    """

    def __init__(self, fast_response_service: FastResponseService) -> None:
        self._service = fast_response_service

    def start(self) -> CommandResult:
        return self._service.open_workbook()

    def stop(self) -> CommandResult:
        # TODO:
        # FastResponseService does not expose a stop/close operation
        # for a workbook opened via the OS default application.
        return CommandResult(success=False, message="Fast Response Board has no stop operation.")

    def restart(self) -> CommandResult:
        # TODO:
        # FastResponseService does not expose a restart operation.
        return CommandResult(
            success=False, message="Fast Response Board has no restart operation."
        )

    def health(self) -> ProcessHealth:
        info = self._service.get_info()
        if info.is_ready:
            return ProcessHealth.READY
        return ProcessHealth.FAILED if info.error_message else ProcessHealth.UNKNOWN


class _UnimplementedHandler:
    """Stub handler for processes with no backing service yet (workflow_engine).

    TODO:
    Replace with a real handler once a WorkflowService / Workflow
    Engine component exists in this project.
    """

    def __init__(self, name: str) -> None:
        self._name = name

    def start(self) -> CommandResult:
        return CommandResult(success=False, message=f"{self._name} is not implemented yet.")

    def stop(self) -> CommandResult:
        return CommandResult(success=False, message=f"{self._name} is not implemented yet.")

    def restart(self) -> CommandResult:
        return CommandResult(success=False, message=f"{self._name} is not implemented yet.")

    def health(self) -> ProcessHealth:
        return ProcessHealth.UNKNOWN


@dataclass(frozen=True)
class DoctorReport:
    """Result of `process doctor`'s diagnostic checks.

    Attributes:
        registry_ok: Whether the catalog has at least one process.
        dependencies_ok: Whether every process resolves a valid
            (cycle-free, fully-registered) startup order.
        execution_engine_ok: Whether the shared ExecutionEngine is wired in.
        workflow_engine_ok: Whether a "workflow_engine" entry is
            registered in the catalog. Does not confirm a live
            WorkflowService, since none exists yet (see module TODO).
        configuration_ok: Whether 'processes.*' configuration loaded.
    """

    registry_ok: bool
    dependencies_ok: bool
    execution_engine_ok: bool
    workflow_engine_ok: bool
    configuration_ok: bool

    @property
    def is_ready(self) -> bool:
        """Return True only if every diagnostic check passed."""
        return (
            self.registry_ok
            and self.dependencies_ok
            and self.execution_engine_ok
            and self.workflow_engine_ok
            and self.configuration_ok
        )


class ProcessService:
    """Coordinates process lifecycle and dependency resolution.

    Responsibilities:
        - Start / stop / restart a registered process.
        - Resolve and validate dependency order before starting.
        - Report health for a single process.
        - Run the `process doctor` readiness checks.

    No business logic lives here: every lifecycle action is delegated
    to the ProcessHandler mapped to that process id.
    """

    def __init__(
        self,
        registry: ProcessRegistry,
        execution_engine: ExecutionEngine,
        config: Config,
        invoice_service: InvoiceService,
        fast_response_service: FastResponseService,
    ) -> None:
        """Initialize the ProcessService.

        Args:
            registry: Catalog of known processes.
            execution_engine: Shared ExecutionEngine, used only for the
                `process doctor` connectivity check.
            config: Loaded application configuration ('processes.*').
            invoice_service: Existing Invoice Automation service.
            fast_response_service: Existing Fast Response Board service.
        """
        self._registry = registry
        self._execution_engine = execution_engine
        self._config = config
        self._handlers: dict[str, ProcessHandler] = {
            "invoice_automation": _InvoiceHandler(invoice_service),
            "fast_response_board": _FastResponseHandler(fast_response_service),
            "workflow_engine": _UnimplementedHandler("Workflow Engine"),
        }

    # ---------- Public API ----------

    def list_processes(self) -> list[Process]:
        """Return every registered process."""
        return self._registry.list_all()

    def get_process(self, process_id: str) -> Process:
        """Return a single registered process.

        Args:
            process_id: The id of the process to look up.

        Returns:
            The matching Process.

        Raises:
            UnknownProcessError: If `process_id` is not registered.
        """
        process = self._registry.find(process_id)
        if process is None:
            raise UnknownProcessError(f"Unknown process: '{process_id}'.")
        return process

    def health(self, process_id: str) -> ProcessHealth:
        """Return the current health of a registered process.

        Args:
            process_id: The id of the process to check.

        Returns:
            The process's current ProcessHealth.

        Raises:
            UnknownProcessError: If `process_id` is not registered.
        """
        self.get_process(process_id)
        handler = self._handlers.get(process_id)
        return handler.health() if handler is not None else ProcessHealth.UNKNOWN

    def resolve_start_order(self, process_id: str) -> list[str]:
        """Resolve the order in which `process_id` and its dependencies must start.

        Args:
            process_id: The process to resolve an order for.

        Returns:
            Process ids in required start order, ending with `process_id`.

        Raises:
            UnknownProcessError: If any process id in the graph is unregistered.
            DependencyResolutionError: If a dependency cycle is found.
        """
        order: list[str] = []
        self._visit(process_id, order, visiting=set(), visited=set())
        return order

    def validate_startup_order(self) -> bool:
        """Validate that every registered process resolves a valid start order.

        Returns:
            True if every process resolves without missing dependencies
            or cycles, False otherwise.
        """
        for process in self._registry.list_all():
            try:
                self.resolve_start_order(process.id)
            except (UnknownProcessError, DependencyResolutionError) as exc:
                logger.error(f"Startup order invalid for '{process.id}': {exc}")
                return False
        return True

    def start(self, process_id: str) -> CommandResult:
        """Start a process, starting any missing dependencies first.

        Args:
            process_id: The process to start.

        Returns:
            A CommandResult describing the outcome. If dependency
            resolution fails, the process itself is not started.
        """
        try:
            order = self.resolve_start_order(process_id)
        except (UnknownProcessError, DependencyResolutionError) as exc:
            return CommandResult(success=False, message=str(exc))

        for dependency_id in order[:-1]:
            if self.health(dependency_id) in (ProcessHealth.RUNNING, ProcessHealth.READY):
                continue
            result = self._start_single(dependency_id)
            if not result.success:
                message = f"Dependency '{dependency_id}' failed to start: {result.message}"
                logger.error(message)
                return CommandResult(success=False, message=message)
            logger.info(f"Dependency resolved: '{dependency_id}'.")

        return self._start_single(process_id)

    def stop(self, process_id: str) -> CommandResult:
        """Stop a single process. Dependents are not cascaded.

        Args:
            process_id: The process to stop.

        Returns:
            A CommandResult describing the outcome.

        Raises:
            UnknownProcessError: If `process_id` is not registered.
        """
        self.get_process(process_id)
        handler = self._handlers.get(process_id)
        if handler is None:
            return CommandResult(success=False, message=f"'{process_id}' has no handler.")

        result = handler.stop()
        if result.success:
            logger.info(f"Process stopped: '{process_id}'.")
        else:
            logger.error(f"Process failed to stop: '{process_id}': {result.message}")
        return result

    def restart(self, process_id: str) -> CommandResult:
        """Restart a process (stop, then start with dependency resolution).

        Args:
            process_id: The process to restart.

        Returns:
            A CommandResult describing the outcome. If the stop step
            fails, start is not attempted.
        """
        stop_result = self.stop(process_id)
        if not stop_result.success:
            return stop_result

        start_result = self.start(process_id)
        if start_result.success:
            logger.info(f"Process restarted: '{process_id}'.")
        return start_result

    def run_doctor(self) -> DoctorReport:
        """Run the `process doctor` readiness checks.

        Returns:
            A DoctorReport describing registry, dependency, execution
            engine, workflow engine, and configuration health.
        """
        return DoctorReport(
            registry_ok=len(self._registry.list_all()) > 0,
            dependencies_ok=self.validate_startup_order(),
            execution_engine_ok=self._execution_engine is not None,
            workflow_engine_ok=self._registry.is_registered("workflow_engine"),
            configuration_ok=self._config.get("processes.dependency_check") is not None,
        )

    # ---------- Internal helpers ----------

    def _start_single(self, process_id: str) -> CommandResult:
        """Start exactly one process via its handler, without resolving dependencies."""
        handler = self._handlers.get(process_id)
        if handler is None:
            return CommandResult(success=False, message=f"'{process_id}' has no handler.")

        result = handler.start()
        if result.success:
            logger.info(f"Process started: '{process_id}'.")
        else:
            logger.error(f"Process failed to start: '{process_id}': {result.message}")
        return result

    def _visit(
        self, process_id: str, order: list[str], visiting: set[str], visited: set[str]
    ) -> None:
        """Depth-first visit used to build a topological start order.

        Args:
            process_id: The process id currently being visited.
            order: Accumulator of process ids in resolved start order.
            visiting: Ids currently on the recursion stack (cycle detection).
            visited: Ids already fully resolved and appended to `order`.

        Raises:
            UnknownProcessError: If `process_id` or a dependency is unregistered.
            DependencyResolutionError: If a dependency cycle is found.
        """
        if process_id in visited:
            return
        if process_id in visiting:
            raise DependencyResolutionError(f"Dependency cycle detected at '{process_id}'.")

        process = self.get_process(process_id)
        visiting.add(process_id)
        for dependency_id in process.dependencies:
            if not self._registry.is_registered(dependency_id):
                raise DependencyResolutionError(
                    f"'{process_id}' depends on unregistered process '{dependency_id}'."
                )
            self._visit(dependency_id, order, visiting, visited)
        visiting.discard(process_id)
        visited.add(process_id)
        order.append(process_id)
