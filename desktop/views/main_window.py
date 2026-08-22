"""MainWindow: the Desktop UI's single window (EP044_DESIGN.md Section 15).

Contains presentation logic only: it binds to
``MainWindowViewModel``'s signals and forwards user actions (button
clicks) to ViewModel methods. It never performs HTTP requests
directly, never contains JARVIS business logic, and never touches
``JarvisApiClient`` or ``requests`` itself (EP-044 STEP 2 governing
instructions, Section 11 "Views").

Intentionally minimal, per EP044_DESIGN.md Section 15: connection
indicator, status area, command input (module/action/arguments),
output/result area, and inline connection settings -- no chat
history, memory browser, agent management, workflow editor, voice
control, or file management (out of scope, Section 8).
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from desktop.api.client_errors import ApiClientError
from desktop.config.desktop_config import DesktopConfig
from desktop.models.dto import CommandResponse, HealthResponse
from desktop.state.connection_state import CommandState, ConnectionState
from desktop.viewmodels.main_window_viewmodel import MainWindowViewModel

__all__ = ["MainWindow"]

_CONNECTION_STATE_LABELS = {
    ConnectionState.DISCONNECTED: "Disconnected",
    ConnectionState.CONNECTING: "Connecting...",
    ConnectionState.CONNECTED: "Connected",
    ConnectionState.API_UNAVAILABLE: "API unavailable",
}


class MainWindow(QMainWindow):
    """The Desktop UI's single Main Window.

    Sub-areas (EP044_DESIGN.md Section 15):
        - Connection indicator + connection settings (host/port).
        - Status area (``GET /api/v1/status``).
        - Command input (module/action/arguments) + execute action.
        - Output/result area (most recent result or error).
    """

    def __init__(
        self,
        view_model: MainWindowViewModel,
        initial_config: DesktopConfig,
        on_settings_applied=None,
    ) -> None:
        """Initialize the Main Window.

        Args:
            view_model: The ViewModel this window binds to. Injected,
                never constructed here (MVVM: the View does not own
                its ViewModel's dependencies).
            initial_config: The Desktop UI configuration to
                pre-populate the connection settings fields with.
            on_settings_applied: Optional callback invoked with a new
                ``DesktopConfig`` when the user clicks "Apply" in the
                connection settings area. The View does not persist
                configuration itself -- that is delegated to the
                caller (``desktop/app/main.py``), keeping
                file/YAML I/O out of the View layer.
        """
        super().__init__()
        self._view_model = view_model
        self._on_settings_applied = on_settings_applied

        self.setWindowTitle("Jarvis Desktop")

        self._build_ui(initial_config)
        self._connect_view_model_signals()

    # ---------- UI construction ----------

    def _build_ui(self, initial_config: DesktopConfig) -> None:
        central = QWidget(self)
        layout = QVBoxLayout(central)

        layout.addWidget(self._build_connection_group(initial_config))
        layout.addWidget(self._build_status_group())
        layout.addWidget(self._build_command_group())
        layout.addWidget(self._build_output_group())

        self.setCentralWidget(central)

    def _build_connection_group(self, initial_config: DesktopConfig) -> QGroupBox:
        group = QGroupBox("Connection")
        form = QFormLayout()

        self._host_input = QLineEdit(initial_config.host)
        self._port_input = QSpinBox()
        self._port_input.setRange(1, 65535)
        self._port_input.setValue(initial_config.port)

        self._connection_indicator = QLabel(_CONNECTION_STATE_LABELS[ConnectionState.DISCONNECTED])

        apply_button = QPushButton("Apply")
        apply_button.clicked.connect(self._on_apply_settings_clicked)

        reconnect_button = QPushButton("Check connection")
        reconnect_button.clicked.connect(self._view_model.check_health)

        buttons_row = QHBoxLayout()
        buttons_row.addWidget(apply_button)
        buttons_row.addWidget(reconnect_button)

        form.addRow("Host:", self._host_input)
        form.addRow("Port:", self._port_input)
        form.addRow("Status:", self._connection_indicator)
        form.addRow(buttons_row)

        group.setLayout(form)
        return group

    def _build_status_group(self) -> QGroupBox:
        group = QGroupBox("Jarvis status")
        layout = QVBoxLayout()

        self._status_label = QLabel("(not loaded)")
        self._status_label.setWordWrap(True)

        refresh_button = QPushButton("Refresh status")
        refresh_button.clicked.connect(self._view_model.load_status)

        layout.addWidget(self._status_label)
        layout.addWidget(refresh_button)
        group.setLayout(layout)
        return group

    def _build_command_group(self) -> QGroupBox:
        group = QGroupBox("Command")
        form = QFormLayout()

        self._module_input = QLineEdit()
        self._action_input = QLineEdit()
        self._arguments_input = QLineEdit()
        self._arguments_input.setPlaceholderText("space-separated arguments")

        self._execute_button = QPushButton("Execute")
        self._execute_button.clicked.connect(self._on_execute_clicked)

        form.addRow("Module:", self._module_input)
        form.addRow("Action:", self._action_input)
        form.addRow("Arguments:", self._arguments_input)
        form.addRow(self._execute_button)

        group.setLayout(form)
        return group

    def _build_output_group(self) -> QGroupBox:
        group = QGroupBox("Result")
        layout = QVBoxLayout()

        self._output_area = QPlainTextEdit()
        self._output_area.setReadOnly(True)

        layout.addWidget(self._output_area)
        group.setLayout(layout)
        return group

    # ---------- ViewModel signal wiring ----------

    def _connect_view_model_signals(self) -> None:
        self._view_model.connection_state_changed.connect(self._on_connection_state_changed)
        self._view_model.command_state_changed.connect(self._on_command_state_changed)
        self._view_model.health_result.connect(self._on_health_result)
        self._view_model.status_result.connect(self._on_status_result)
        self._view_model.command_result.connect(self._on_command_result)
        self._view_model.error_occurred.connect(self._on_error)

    # ---------- user action handlers ----------

    def _on_apply_settings_clicked(self) -> None:
        if self._on_settings_applied is not None:
            new_config = DesktopConfig(
                host=self._host_input.text().strip(),
                port=self._port_input.value(),
            )
            self._on_settings_applied(new_config)

    def _on_execute_clicked(self) -> None:
        module = self._module_input.text().strip()
        action = self._action_input.text().strip()
        arguments_text = self._arguments_input.text().strip()
        arguments = arguments_text.split() if arguments_text else []

        if not module:
            self._output_area.setPlainText("Module is required.")
            return

        self._execute_button.setEnabled(False)
        self._view_model.execute_command(module, action, arguments)

    # ---------- ViewModel signal handlers ----------

    def _on_connection_state_changed(self, state: ConnectionState) -> None:
        self._connection_indicator.setText(_CONNECTION_STATE_LABELS[state])

    def _on_command_state_changed(self, state: CommandState) -> None:
        if state != CommandState.REQUEST_IN_PROGRESS:
            self._execute_button.setEnabled(True)

    def _on_health_result(self, result: HealthResponse) -> None:
        pass  # Connection indicator already reflects this via connection_state_changed.

    def _on_status_result(self, result: CommandResponse) -> None:
        self._status_label.setText(result.message)

    def _on_command_result(self, result: CommandResponse) -> None:
        prefix = "OK" if result.success else "FAILED"
        self._output_area.setPlainText(f"[{prefix}] {result.message}")

    def _on_error(self, error: ApiClientError) -> None:
        self._output_area.setPlainText(f"Error: {error}")
