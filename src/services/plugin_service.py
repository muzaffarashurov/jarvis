"""Plugin Manager service for EP-009 Plugin SDK & Plugin Manager.

PluginService is the entry point CLI modules use to manage plugins. It
implements no plugin lifecycle logic of its own: loading, unloading,
and reloading are always delegated to PluginLoader, and catalog data
is always read from PluginRegistry, matching this project's Single
Source of Truth rule.
"""

from __future__ import annotations

from dataclasses import dataclass

from loguru import logger

from src.core.command_router import CommandResult
from src.core.config import Config
from src.core.plugins.plugin import Plugin, PluginStatus
from src.core.plugins.plugin_loader import (
    DependencyCycleError,
    MissingDependencyError,
    PluginAlreadyLoadedError,
    PluginInitializationError,
    PluginLoader,
    VersionMismatchError,
)
from src.core.plugins.plugin_registry import PluginNotFoundError, PluginRegistry

_LOAD_ERRORS = (
    PluginNotFoundError,
    PluginAlreadyLoadedError,
    MissingDependencyError,
    DependencyCycleError,
    VersionMismatchError,
    PluginInitializationError,
)


@dataclass(frozen=True)
class PluginDoctorReport:
    """Result of `plugin doctor`'s diagnostic checks.

    Attributes:
        registry_ok: Whether the catalog has at least one plugin.
        loader_ok: Whether a PluginLoader is wired in.
        dependencies_ok: Whether every plugin resolves a valid
            (cycle-free, fully-registered) load order.
        configuration_ok: Whether 'plugins.*' configuration loaded.
        context_ok: Whether the PluginLoader's PluginContext exposes a
            configuration and execution engine reference.
    """

    registry_ok: bool
    loader_ok: bool
    dependencies_ok: bool
    configuration_ok: bool
    context_ok: bool

    @property
    def is_ready(self) -> bool:
        """Return True only if every diagnostic check passed."""
        return (
            self.registry_ok
            and self.loader_ok
            and self.dependencies_ok
            and self.configuration_ok
            and self.context_ok
        )


class PluginService:
    """Coordinates plugin discovery, lifecycle, and diagnostics.

    Responsibilities:
        - Load / unload / reload a registered plugin.
        - List all registered plugins.
        - Return a single plugin's metadata for `plugin info`.
        - Report plugins currently RUNNING for `plugin status`.
        - Run the `plugin doctor` readiness checks.
    """

    def __init__(self, registry: PluginRegistry, loader: PluginLoader, config: Config) -> None:
        """Initialize the PluginService.

        Args:
            registry: Catalog of known plugins.
            loader: Loader used to drive plugin lifecycle transitions.
            config: Loaded application configuration ('plugins.*').
        """
        self._registry = registry
        self._loader = loader
        self._config = config

    # ---------- Public API ----------

    def list_plugins(self) -> list[Plugin]:
        """Return every registered plugin."""
        return self._registry.list()

    def get_plugin(self, plugin_id: str) -> Plugin:
        """Return a single registered plugin's metadata.

        Args:
            plugin_id: The id of the plugin to look up.

        Returns:
            The matching Plugin.

        Raises:
            PluginNotFoundError: If `plugin_id` is not registered.
        """
        return self._registry.get(plugin_id)

    def running_plugins(self) -> list[Plugin]:
        """Return every plugin currently reporting RUNNING status."""
        return [plugin for plugin in self._registry.list() if plugin.status == PluginStatus.RUNNING]

    def load_plugin(self, plugin_id: str) -> CommandResult:
        """Load a plugin by id, resolving dependencies first.

        Args:
            plugin_id: The plugin to load.

        Returns:
            A CommandResult describing the outcome.
        """
        try:
            self._loader.load(plugin_id)
        except _LOAD_ERRORS as exc:
            logger.error(f"Failed to load plugin '{plugin_id}': {exc}")
            return CommandResult(success=False, message=str(exc))

        return CommandResult(success=True, message=f"Plugin '{plugin_id}' loaded.")

    def unload_plugin(self, plugin_id: str) -> CommandResult:
        """Unload a plugin by id.

        Args:
            plugin_id: The plugin to unload.

        Returns:
            A CommandResult describing the outcome.
        """
        try:
            self._loader.unload(plugin_id)
        except (PluginNotFoundError, PluginInitializationError) as exc:
            logger.error(f"Failed to unload plugin '{plugin_id}': {exc}")
            return CommandResult(success=False, message=str(exc))

        return CommandResult(success=True, message=f"Plugin '{plugin_id}' unloaded.")

    def reload_plugin(self, plugin_id: str) -> CommandResult:
        """Reload a plugin by id (unload, then load).

        Args:
            plugin_id: The plugin to reload.

        Returns:
            A CommandResult describing the outcome.
        """
        try:
            self._loader.reload(plugin_id)
        except _LOAD_ERRORS as exc:
            logger.error(f"Failed to reload plugin '{plugin_id}': {exc}")
            return CommandResult(success=False, message=str(exc))

        return CommandResult(success=True, message=f"Plugin '{plugin_id}' reloaded.")

    def run_doctor(self) -> PluginDoctorReport:
        """Run the `plugin doctor` readiness checks."""
        return PluginDoctorReport(
            registry_ok=len(self._registry.list()) > 0,
            loader_ok=self._loader is not None,
            dependencies_ok=self._validate_dependencies(),
            configuration_ok=self._config.get("plugins.enabled") is not None,
            context_ok=self._loader.context_is_ready(),
        )

    # ---------- Default Plugins ----------

    @staticmethod
    def default_plugins() -> list[Plugin]:
        """Return metadata-only Plugin entries for existing Jarvis modules.

        Registers Invoice Automation, Fast Response Board, and
        Workflow Engine as plugins by metadata only, per EP-009's
        "Default Plugins" ("Do NOT rewrite their implementation.").
        Each has `entry_point=None`: PluginLoader treats that as a
        metadata-only plugin and performs lifecycle status bookkeeping
        without invoking any implementation.

        Returns:
            The default Plugin catalog entries.
        """
        return [
            Plugin(
                id="invoice_automation",
                name="Invoice Automation",
                version="1.0.0",
                description="External Invoice Automation script (EP-005).",
                author="Jarvis",
                capabilities=("invoice.automation",),
            ),
            Plugin(
                id="fast_response_board",
                name="Fast Response Board",
                version="1.0.0",
                description="Fast Response Board Excel workbook (EP-006).",
                author="Jarvis",
                capabilities=("fast_response.board",),
            ),
            Plugin(
                id="workflow_engine",
                name="Workflow Engine",
                version="1.0.0",
                description="Workflow Engine (EP-007).",
                author="Jarvis",
                dependencies=("invoice_automation", "fast_response_board"),
                capabilities=("workflow.orchestration",),
            ),
        ]

    # ---------- Internal helpers ----------

    def _validate_dependencies(self) -> bool:
        """Return True if every registered plugin resolves a valid load order."""
        for plugin in self._registry.list():
            try:
                self._loader.resolve_dependencies(plugin.id)
            except (PluginNotFoundError, MissingDependencyError, DependencyCycleError) as exc:
                logger.error(f"Dependency check failed for '{plugin.id}': {exc}")
                return False
        return True
