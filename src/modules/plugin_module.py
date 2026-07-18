"""Plugin module: CLI command surface for EP-009 Plugin SDK & Plugin Manager.

Exposes the "plugin" command namespace (list, info, load, unload,
reload, status, doctor, help) as thin CommandModule handlers,
following the same pattern as ProcessModule. All coordination logic
lives in PluginService; this module only formats CommandResult
objects for the shell.
"""

from __future__ import annotations

from typing import Callable

from src.core.command_router import CommandResult
from src.core.plugins.plugin_registry import PluginNotFoundError
from src.services.plugin_service import PluginDoctorReport, PluginService

HELP_TEXT: str = (
    "Available commands\n\n"
    "plugin list\n"
    "plugin info <plugin>\n"
    "plugin load <plugin>\n"
    "plugin unload <plugin>\n"
    "plugin reload <plugin>\n"
    "plugin status\n"
    "plugin doctor\n"
    "plugin help"
)

ActionHandler = Callable[[list[str]], CommandResult]


class PluginModule:
    """Built-in "plugin" command namespace for the Plugin Manager.

    Responsibilities:
        - List all registered plugins (list).
        - Display details for a single plugin (info).
        - Load / unload / reload a plugin (load, unload, reload).
        - Report all currently running plugins (status).
        - Run plugin subsystem readiness diagnostics (doctor).
        - Report available commands (help).
    """

    def __init__(self, plugin_service: PluginService) -> None:
        """Initialize the PluginModule.

        Args:
            plugin_service: The service used to coordinate registered plugins.
        """
        self._service = plugin_service
        self._actions: dict[str, ActionHandler] = {
            "list": self._list,
            "info": self._info,
            "load": self._load,
            "unload": self._unload,
            "reload": self._reload,
            "status": self._status,
            "doctor": self._doctor,
            "help": self._help,
        }

    @property
    def name(self) -> str:
        """Return this module's command namespace: "plugin"."""
        return "plugin"

    def execute(self, action: str, arguments: list[str]) -> CommandResult:
        """Execute a "plugin" action.

        Args:
            action: The requested action (e.g. "list").
            arguments: Additional arguments (e.g. the plugin id).

        Returns:
            A CommandResult describing the outcome.
        """
        handler = self._actions.get(action)
        if handler is None:
            command = f"{self.name} {action}".strip()
            message = f'Unknown command: {command}\nType "plugin help" for available commands.'
            return CommandResult(success=False, message=message)

        return handler(arguments)

    def _help(self, arguments: list[str]) -> CommandResult:
        """Return the list of available plugin commands."""
        return CommandResult(success=True, message=HELP_TEXT)

    def _list(self, arguments: list[str]) -> CommandResult:
        """List every registered plugin with its id, name, and status."""
        plugins = self._service.list_plugins()
        if not plugins:
            return CommandResult(success=True, message="No plugins registered.")

        lines = ["Registered Plugins"]
        for plugin in plugins:
            lines.append(f"{plugin.id} ({plugin.name}) - {plugin.status.value}")
        return CommandResult(success=True, message="\n\n".join(lines))

    def _info(self, arguments: list[str]) -> CommandResult:
        """Display name, version, status, description, dependencies, capabilities."""
        plugin_id = self._require_id(arguments)
        if plugin_id is None:
            return CommandResult(success=False, message="Usage: plugin info <plugin>")

        try:
            plugin = self._service.get_plugin(plugin_id)
        except PluginNotFoundError as exc:
            return CommandResult(success=False, message=str(exc))

        dependencies = ", ".join(plugin.dependencies) if plugin.dependencies else "(none)"
        capabilities = ", ".join(plugin.capabilities) if plugin.capabilities else "(none)"
        pairs = (
            ("Name", plugin.name),
            ("Version", plugin.version),
            ("Status", plugin.status.value),
            ("Description", plugin.description),
            ("Dependencies", dependencies),
            ("Capabilities", capabilities),
        )
        message = "\n\n".join(f"{label}\n\n{value}" for label, value in pairs)
        return CommandResult(success=True, message=message)

    def _load(self, arguments: list[str]) -> CommandResult:
        """Load a plugin by id."""
        plugin_id = self._require_id(arguments)
        if plugin_id is None:
            return CommandResult(success=False, message="Usage: plugin load <plugin>")
        return self._service.load_plugin(plugin_id)

    def _unload(self, arguments: list[str]) -> CommandResult:
        """Unload a plugin by id."""
        plugin_id = self._require_id(arguments)
        if plugin_id is None:
            return CommandResult(success=False, message="Usage: plugin unload <plugin>")
        return self._service.unload_plugin(plugin_id)

    def _reload(self, arguments: list[str]) -> CommandResult:
        """Reload a plugin by id."""
        plugin_id = self._require_id(arguments)
        if plugin_id is None:
            return CommandResult(success=False, message="Usage: plugin reload <plugin>")
        return self._service.reload_plugin(plugin_id)

    def _status(self, arguments: list[str]) -> CommandResult:
        """Display all plugins currently reporting RUNNING."""
        running = self._service.running_plugins()
        if not running:
            return CommandResult(success=True, message="No plugins currently running.")

        lines = ["Running Plugins"]
        for plugin in running:
            lines.append(f"{plugin.id} ({plugin.name}) - {plugin.status.value}")
        return CommandResult(success=True, message="\n\n".join(lines))

    def _doctor(self, arguments: list[str]) -> CommandResult:
        """Run registry, loader, dependency, configuration, and context checks."""
        report: PluginDoctorReport = self._service.run_doctor()
        lines = [
            "Plugin Manager Doctor",
            f"Registry : {self._mark(report.registry_ok)}",
            f"Loader : {self._mark(report.loader_ok)}",
            f"Dependencies : {self._mark(report.dependencies_ok)}",
            f"Configuration : {self._mark(report.configuration_ok)}",
            f"Plugin Context : {self._mark(report.context_ok)}",
            f"Result : {'READY' if report.is_ready else 'FAILED'}",
        ]
        return CommandResult(success=report.is_ready, message="\n\n".join(lines))

    @staticmethod
    def _require_id(arguments: list[str]) -> str | None:
        """Return the first argument as a plugin id, or None if missing."""
        return arguments[0] if arguments else None

    @staticmethod
    def _mark(value: bool) -> str:
        """Format a boolean diagnostic check as "OK" or "FAIL"."""
        return "OK" if value else "FAIL"
