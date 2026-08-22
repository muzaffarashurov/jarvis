"""MainWindowViewModel: MVVM state holder for the Desktop UI's Main Window.

Holds no widget references (EP044_DESIGN.md Section 11) and is fully
testable without a real Qt event loop or ``QApplication`` window --
only a ``JarvisApiClient`` (real or fake) is required to construct and
exercise it. Coordinates API calls via ``ApiWorker`` so the UI thread
is never blocked (Section 15/30), and translates API results/errors
into the state model defined in ``desktop/state/connection_state.py``
(Section 16).

Views (``desktop/views/main_window.py``) connect to this ViewModel's
signals and never call ``JarvisApiClient`` directly.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from desktop.api.client_errors import ApiClientError
from desktop.api.jarvis_api_client import JarvisApiClient
from desktop.models.dto import CommandRequest, CommandResponse, HealthResponse
from desktop.state.connection_state import CommandState, ConnectionState
from desktop.viewmodels.api_worker import ApiWorker

__all__ = ["MainWindowViewModel"]


class MainWindowViewModel(QObject):
    """ViewModel for the Desktop UI's single Main Window.

    Signals:
        connection_state_changed: Emitted with the new
            ``ConnectionState`` whenever it changes.
        command_state_changed: Emitted with the new ``CommandState``
            whenever it changes.
        health_result: Emitted with the ``HealthResponse`` after a
            successful health check.
        status_result: Emitted with the ``CommandResponse`` after a
            successful status request.
        command_result: Emitted with the ``CommandResponse`` after a
            successfully routed command (regardless of the command's
            own ``success`` field -- see
            ``desktop/models/dto.py``'s ``CommandResponse`` docstring).
        error_occurred: Emitted with an ``ApiClientError`` whenever any
            request fails at the transport level (EP044_DESIGN.md
            Section 18).
    """

    connection_state_changed = Signal(object)
    command_state_changed = Signal(object)
    health_result = Signal(object)
    status_result = Signal(object)
    command_result = Signal(object)
    error_occurred = Signal(object)

    def __init__(self, api_client: JarvisApiClient, parent: QObject | None = None) -> None:
        """Initialize the ViewModel.

        Args:
            api_client: The REST API client to use for all requests.
                Injected rather than constructed here, matching
                ``AI_GENERATION_STANDARD.md``'s Dependency Policy
                (constructor injection, no service instantiated inside
                business/UI logic) and making this ViewModel testable
                with a fake client.
            parent: Optional Qt parent object.
        """
        super().__init__(parent)
        self._api_client = api_client
        self._connection_state = ConnectionState.DISCONNECTED
        self._command_state = CommandState.IDLE
        self._active_workers: list[ApiWorker] = []

    @property
    def connection_state(self) -> ConnectionState:
        """Return the current connection state."""
        return self._connection_state

    @property
    def command_state(self) -> CommandState:
        """Return the current command state."""
        return self._command_state

    def check_health(self) -> None:
        """Trigger a background ``GET /health`` request.

        Updates ``connection_state`` to ``CONNECTING`` immediately,
        then to ``CONNECTED`` or ``API_UNAVAILABLE`` when the request
        completes.
        """
        self._set_connection_state(ConnectionState.CONNECTING)
        self._run(
            call=self._api_client.check_health,
            on_success=self._on_health_succeeded,
            on_failure=self._on_health_failed,
        )

    def load_status(self) -> None:
        """Trigger a background ``GET /api/v1/status`` request.

        Updates ``command_state`` to ``REQUEST_IN_PROGRESS`` while the
        request is in flight.
        """
        self._set_command_state(CommandState.REQUEST_IN_PROGRESS)
        self._run(
            call=self._api_client.get_status,
            on_success=self._on_status_succeeded,
            on_failure=self._on_command_failed,
        )

    def execute_command(self, module: str, action: str, arguments: list[str]) -> None:
        """Trigger a background ``POST /api/v1/commands`` request.

        Args:
            module: The target command namespace.
            action: The action within that namespace. May be empty.
            arguments: Additional positional arguments, in order.

        No automatic retry is performed on failure -- commands may
        have side effects (EP044_DESIGN.md Section 14/10).
        """
        request = CommandRequest(module=module, action=action, arguments=list(arguments))
        self._set_command_state(CommandState.REQUEST_IN_PROGRESS)
        self._run(
            call=lambda: self._api_client.execute_command(request),
            on_success=self._on_command_succeeded,
            on_failure=self._on_command_failed,
        )

    # ---------- internal: worker orchestration ----------

    def _run(self, call, on_success, on_failure) -> None:
        """Start an ApiWorker for ``call`` and wire its signals.

        The worker is kept alive in ``self._active_workers`` until it
        finishes, since a QThread with no surviving Python reference
        can be garbage-collected while still running.
        """
        worker = ApiWorker(call, parent=self)
        worker.succeeded.connect(on_success)
        worker.failed.connect(on_failure)
        worker.finished.connect(lambda: self._active_workers.remove(worker))
        self._active_workers.append(worker)
        worker.start()

    # ---------- internal: result/error handlers ----------

    def _on_health_succeeded(self, result: HealthResponse) -> None:
        self._set_connection_state(ConnectionState.CONNECTED)
        self.health_result.emit(result)

    def _on_health_failed(self, error: ApiClientError) -> None:
        self._set_connection_state(ConnectionState.API_UNAVAILABLE)
        self.error_occurred.emit(error)

    def _on_status_succeeded(self, result: CommandResponse) -> None:
        self._set_command_state(CommandState.SUCCEEDED if result.success else CommandState.FAILED)
        self.status_result.emit(result)

    def _on_command_succeeded(self, result: CommandResponse) -> None:
        self._set_command_state(CommandState.SUCCEEDED if result.success else CommandState.FAILED)
        self.command_result.emit(result)

    def _on_command_failed(self, error: ApiClientError) -> None:
        self._set_command_state(CommandState.ERROR)
        self.error_occurred.emit(error)

    # ---------- internal: state transitions ----------

    def _set_connection_state(self, state: ConnectionState) -> None:
        if state != self._connection_state:
            self._connection_state = state
            self.connection_state_changed.emit(state)

    def _set_command_state(self, state: CommandState) -> None:
        if state != self._command_state:
            self._command_state = state
            self.command_state_changed.emit(state)
