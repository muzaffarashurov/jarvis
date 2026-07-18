"""Catalog registry for EP-009 Plugin SDK & Plugin Manager.

PluginRegistry stores plugin catalog entries (metadata) and owns the
one place `Plugin.status` may be mutated, matching this project's
Single Source of Truth rule. It performs no loading, no dependency
resolution, and no execution -- those responsibilities belong to
PluginLoader and PluginService respectively. This mirrors
ProcessRegistry's role for the Process Catalog (see
src/core/processes/process_registry.py).
"""

from __future__ import annotations

from threading import Lock

from loguru import logger

from src.core.plugins.plugin import Plugin, PluginStatus


class PluginRegistryError(Exception):
    """Raised for invalid catalog operations (e.g. duplicate plugin id)."""


class PluginNotFoundError(Exception):
    """Raised when an operation references a plugin id not in the catalog."""


class PluginRegistry:
    """Thread-safe catalog of plugins known to the Plugin Manager.

    Responsibilities:
        - Register a plugin in the catalog.
        - Unregister a plugin from the catalog.
        - Return a single registered plugin, raising if unknown.
        - Find a single registered plugin without raising.
        - List all registered plugins.
        - Own updates to a plugin's lifecycle `status`.
    """

    def __init__(self) -> None:
        """Initialize an empty PluginRegistry."""
        self._plugins: dict[str, Plugin] = {}
        self._lock = Lock()

    def register(self, plugin: Plugin) -> None:
        """Register a plugin in the catalog.

        Args:
            plugin: The Plugin to add.

        Raises:
            PluginRegistryError: If a plugin with the same id is
                already registered.
        """
        with self._lock:
            if plugin.id in self._plugins:
                raise PluginRegistryError(f"Plugin already registered: '{plugin.id}'.")
            self._plugins[plugin.id] = plugin
        logger.info(f"Plugin registered: '{plugin.id}'.")

    def unregister(self, plugin_id: str) -> None:
        """Remove a plugin from the catalog.

        Args:
            plugin_id: The id of the plugin to remove.

        Raises:
            PluginNotFoundError: If `plugin_id` is not registered.
        """
        with self._lock:
            if plugin_id not in self._plugins:
                raise PluginNotFoundError(f"Unknown plugin: '{plugin_id}'.")
            del self._plugins[plugin_id]
        logger.info(f"Plugin unregistered: '{plugin_id}'.")

    def get(self, plugin_id: str) -> Plugin:
        """Return a single registered plugin.

        Args:
            plugin_id: The id of the plugin to look up.

        Returns:
            The matching Plugin.

        Raises:
            PluginNotFoundError: If `plugin_id` is not registered.
        """
        plugin = self.find(plugin_id)
        if plugin is None:
            raise PluginNotFoundError(f"Unknown plugin: '{plugin_id}'.")
        return plugin

    def find(self, plugin_id: str) -> Plugin | None:
        """Return the catalog entry for a plugin id, if registered.

        Args:
            plugin_id: The id of the plugin to find.

        Returns:
            The Plugin, or None if not registered.
        """
        with self._lock:
            return self._plugins.get(plugin_id)

    def list(self) -> list[Plugin]:
        """Return every registered plugin, ordered by id.

        Returns:
            A list of Plugin entries sorted by id.
        """
        with self._lock:
            return sorted(self._plugins.values(), key=lambda plugin: plugin.id)

    def is_registered(self, plugin_id: str) -> bool:
        """Return whether a plugin id is currently registered.

        Args:
            plugin_id: The id to check.

        Returns:
            True if a plugin with this id exists in the catalog.
        """
        with self._lock:
            return plugin_id in self._plugins

    def update_status(self, plugin_id: str, status: PluginStatus) -> None:
        """Update a registered plugin's lifecycle status.

        This is the only method permitted to assign to `Plugin.status`,
        keeping the registry the single owner of plugin lifecycle
        state (see the project's Single Source of Truth rule).

        Args:
            plugin_id: The id of the plugin to update.
            status: The new PluginStatus.

        Raises:
            PluginNotFoundError: If `plugin_id` is not registered.
        """
        with self._lock:
            plugin = self._plugins.get(plugin_id)
            if plugin is None:
                raise PluginNotFoundError(f"Unknown plugin: '{plugin_id}'.")
            plugin.status = status
        logger.debug(f"Plugin status updated: '{plugin_id}' -> {status.value}.")
