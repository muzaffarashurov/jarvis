"""Plugin loader for EP-009 Plugin SDK & Plugin Manager.

PluginLoader drives a registered Plugin through its lifecycle (load,
initialize, start, stop, unload), resolving dependencies and verifying
basic compatibility before activating a plugin. It owns the one place
live plugin instances are held; PluginRegistry only stores catalog
metadata and status (see plugin_registry.py), matching the project's
Single Source of Truth rule.
"""

from __future__ import annotations

from loguru import logger

from src.core.plugins.plugin import Plugin, PluginInterface, PluginStatus
from src.core.plugins.plugin_context import PluginContext
from src.core.plugins.plugin_registry import PluginRegistry

_ACTIVE_STATUSES = (PluginStatus.LOADED, PluginStatus.INITIALIZED, PluginStatus.RUNNING)


class PluginAlreadyLoadedError(Exception):
    """Raised when `load()` is called for a plugin that is already active."""


class MissingDependencyError(Exception):
    """Raised when a plugin depends on a plugin id that is not registered."""


class DependencyCycleError(Exception):
    """Raised when plugin dependencies form a cycle."""


class VersionMismatchError(Exception):
    """Raised when a plugin fails a basic compatibility check."""


class PluginInitializationError(Exception):
    """Raised when a plugin's entry point, `initialize()`, or lifecycle call fails."""


class PluginLoader:
    """Resolves dependencies and drives plugins through their lifecycle.

    Responsibilities:
        - Load a plugin (resolve dependencies, verify compatibility,
          instantiate its entry point, initialize, and start it).
        - Unload a plugin (stop it and release its live instance).
        - Reload a plugin (unload, then load).
        - Resolve a plugin's dependency load order.
        - Verify basic plugin compatibility before loading.
    """

    def __init__(self, registry: PluginRegistry, context: PluginContext) -> None:
        """Initialize the PluginLoader.

        Args:
            registry: Catalog of known plugins.
            context: Shared services context passed to every plugin's
                `initialize()` call.
        """
        self._registry = registry
        self._context = context
        self._instances: dict[str, PluginInterface] = {}

    # ---------- Public API ----------

    def load(self, plugin_id: str) -> None:
        """Load a plugin, resolving and loading its dependencies first.

        Args:
            plugin_id: The plugin to load.

        Raises:
            PluginNotFoundError: If `plugin_id` or a dependency is not registered.
            PluginAlreadyLoadedError: If the plugin is already active.
            MissingDependencyError: If a dependency id is not registered.
            DependencyCycleError: If a dependency cycle is found.
            VersionMismatchError: If the plugin fails compatibility verification.
            PluginInitializationError: If the plugin's entry point,
                `initialize()`, or `start()` raises.
        """
        order = self.resolve_dependencies(plugin_id)
        for dependency_id in order[:-1]:
            dependency = self._registry.get(dependency_id)
            if dependency.status in _ACTIVE_STATUSES:
                continue
            self._activate(dependency_id)
            logger.info(f"Dependency resolved: '{dependency_id}'.")

        self._activate(plugin_id)

    def unload(self, plugin_id: str) -> None:
        """Unload a plugin, stopping and releasing its live instance.

        A plugin that is not currently active is treated as already
        unloaded and this method returns without error.

        Args:
            plugin_id: The plugin to unload.

        Raises:
            PluginNotFoundError: If `plugin_id` is not registered.
            PluginInitializationError: If the plugin's `stop()` raises.
        """
        plugin = self._registry.get(plugin_id)
        if plugin.status not in _ACTIVE_STATUSES:
            logger.info(f"Plugin already unloaded: '{plugin_id}'.")
            return

        instance = self._instances.pop(plugin_id, None)
        if instance is not None:
            try:
                instance.stop()
            except Exception as exc:  # noqa: BLE001 - a failing plugin must not crash the loader
                self._registry.update_status(plugin_id, PluginStatus.FAILED)
                logger.error(f"Plugin failed: '{plugin_id}': {exc}")
                raise PluginInitializationError(
                    f"Plugin '{plugin_id}' failed to stop: {exc}"
                ) from exc

        self._registry.update_status(plugin_id, PluginStatus.STOPPED)
        logger.info(f"Plugin stopped: '{plugin_id}'.")
        self._registry.update_status(plugin_id, PluginStatus.UNLOADED)
        logger.info(f"Plugin unloaded: '{plugin_id}'.")

    def reload(self, plugin_id: str) -> None:
        """Reload a plugin: unload it, then load it again.

        Args:
            plugin_id: The plugin to reload.

        Raises:
            PluginNotFoundError: If `plugin_id` or a dependency is not registered.
            MissingDependencyError: If a dependency id is not registered.
            DependencyCycleError: If a dependency cycle is found.
            VersionMismatchError: If the plugin fails compatibility verification.
            PluginInitializationError: If stopping or (re)loading fails.
        """
        self.unload(plugin_id)
        self.load(plugin_id)

    def resolve_dependencies(self, plugin_id: str) -> list[str]:
        """Resolve the order in which `plugin_id` and its dependencies must load.

        Args:
            plugin_id: The plugin to resolve an order for.

        Returns:
            Plugin ids in required load order, ending with `plugin_id`.

        Raises:
            PluginNotFoundError: If `plugin_id` is not registered.
            MissingDependencyError: If a dependency id is not registered.
            DependencyCycleError: If a dependency cycle is found.
        """
        order: list[str] = []
        self._visit(plugin_id, order, visiting=set(), visited=set())
        return order

    def verify_compatibility(self, plugin: Plugin) -> None:
        """Verify a plugin passes basic compatibility checks before loading.

        Only structural checks are performed (a non-blank declared
        version); no semantic version-range resolution is implemented,
        since EP-009 explicitly defers external manifest files
        ("Do NOT implement external manifest files yet.").

        Args:
            plugin: The plugin to verify.

        Raises:
            VersionMismatchError: If `plugin.version` is missing/blank.
        """
        if not plugin.version.strip():
            raise VersionMismatchError(f"Plugin '{plugin.id}' has no declared version.")

    def context_is_ready(self) -> bool:
        """Return whether this loader's PluginContext exposes core services.

        Returns:
            True if the context has a configuration and execution
            engine reference.
        """
        return self._context.config is not None and self._context.execution_engine is not None

    # ---------- Internal helpers ----------

    def _activate(self, plugin_id: str) -> None:
        """Drive a single plugin through load -> initialize -> start.

        Args:
            plugin_id: The plugin to activate.

        Raises:
            PluginAlreadyLoadedError: If the plugin is already active.
            VersionMismatchError: If the plugin fails compatibility verification.
            PluginInitializationError: If the plugin's entry point,
                `initialize()`, or `start()` raises.
        """
        plugin = self._registry.get(plugin_id)
        if plugin.status in _ACTIVE_STATUSES:
            raise PluginAlreadyLoadedError(f"Plugin already loaded: '{plugin_id}'.")

        self.verify_compatibility(plugin)
        self._registry.update_status(plugin_id, PluginStatus.LOADED)
        logger.info(f"Plugin loaded: '{plugin_id}'.")

        if plugin.entry_point is None:
            # Metadata-only plugin (see EP-009 "Default Plugins"): status
            # bookkeeping only. Its existing implementation is never
            # rewritten or re-invoked here.
            #
            # TODO:
            # This RUNNING/STOPPED bookkeeping is not cross-checked
            # against the real state ProcessService/InvoiceService/
            # FastResponseService already track for these same
            # modules (EP-009.1 "Synchronize plugin status"). Doing so
            # would require injecting one of those services into
            # PluginLoader or PluginService, which is a constructor
            # signature change not authorized by this task. Left as a
            # TODO rather than adding that dependency unasked.
            self._registry.update_status(plugin_id, PluginStatus.INITIALIZED)
            logger.info(f"Plugin initialized: '{plugin_id}'.")
            self._registry.update_status(plugin_id, PluginStatus.RUNNING)
            logger.info(f"Plugin started: '{plugin_id}'.")
            return

        try:
            instance = plugin.entry_point()
            if not isinstance(instance, PluginInterface):
                raise TypeError(
                    f"Entry point for '{plugin_id}' does not implement PluginInterface."
                )
            instance.initialize(self._context)
            self._registry.update_status(plugin_id, PluginStatus.INITIALIZED)
            logger.info(f"Plugin initialized: '{plugin_id}'.")
            instance.start()
        except Exception as exc:  # noqa: BLE001 - a failing plugin must not crash the loader
            self._registry.update_status(plugin_id, PluginStatus.FAILED)
            logger.error(f"Plugin failed: '{plugin_id}': {exc}")
            raise PluginInitializationError(
                f"Plugin '{plugin_id}' failed to load: {exc}"
            ) from exc

        self._instances[plugin_id] = instance
        self._registry.update_status(plugin_id, PluginStatus.RUNNING)
        logger.info(f"Plugin started: '{plugin_id}'.")

    def _visit(
        self, plugin_id: str, order: list[str], visiting: set[str], visited: set[str]
    ) -> None:
        """Depth-first visit used to build a topological load order.

        Args:
            plugin_id: The plugin id currently being visited.
            order: Accumulator of plugin ids in resolved load order.
            visiting: Ids currently on the recursion stack (cycle detection).
            visited: Ids already fully resolved and appended to `order`.

        Raises:
            PluginNotFoundError: If `plugin_id` is not registered.
            MissingDependencyError: If a dependency id is not registered.
            DependencyCycleError: If a dependency cycle is found.
        """
        if plugin_id in visited:
            return
        if plugin_id in visiting:
            raise DependencyCycleError(f"Dependency cycle detected at '{plugin_id}'.")

        plugin = self._registry.get(plugin_id)
        visiting.add(plugin_id)
        for dependency_id in plugin.dependencies:
            if not self._registry.is_registered(dependency_id):
                raise MissingDependencyError(
                    f"'{plugin_id}' depends on unregistered plugin '{dependency_id}'."
                )
            self._visit(dependency_id, order, visiting, visited)
        visiting.discard(plugin_id)
        visited.add(plugin_id)
        order.append(plugin_id)
