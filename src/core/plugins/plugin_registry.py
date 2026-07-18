"""Catalog registry for EP-009 Plugin SDK & Plugin Manager.

PluginRegistry stores plugin catalog entries (metadata) and owns the
one place `Plugin.status` may be mutated, matching this project's
Single Source of Truth rule. It performs no loading, no dependency
resolution, and no execution -- those responsibilities belong to
PluginLoader and PluginService respectively. This mirrors
ProcessRegistry's role for the Process Catalog (see
src/core/processes/process_registry.py).

EP-009.1 adds alias-aware lookup (`resolve_id`), typo suggestions
(`suggest`), and a live consistency check (`duplicate_aliases`) on top
of the same `self._plugins` dict -- no second, alias-keyed store is
introduced, so the catalog keeps a single source of truth for plugin
identity.
"""

from __future__ import annotations

from difflib import get_close_matches
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
        - Resolve a plugin id or alias to its canonical plugin id.
        - Suggest close-matching plugin ids for a typo'd identifier.
        - Report id/alias collisions for `plugin doctor` (EP-009.1).
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
                already registered, or if `plugin`'s id/aliases
                collide with an already registered plugin's id/aliases.
        """
        with self._lock:
            if plugin.id in self._plugins:
                raise PluginRegistryError(f"Plugin already registered: '{plugin.id}'.")
            self._check_alias_collisions(plugin)
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
            plugin_id: The canonical id of the plugin to look up.
                Aliases are not accepted here; call `resolve_id` first
                if `plugin_id` may be an alias.

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
            plugin_id: The canonical id of the plugin to find.

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

    # ---------- Alias support (EP-009.1) ----------

    def resolve_id(self, identifier: str) -> str:
        """Resolve a plugin id or alias to its canonical plugin id.

        Args:
            identifier: A plugin id or one of its declared aliases.

        Returns:
            The canonical plugin id.

        Raises:
            PluginNotFoundError: If `identifier` matches no registered
                plugin id or alias.
        """
        with self._lock:
            if identifier in self._plugins:
                return identifier
            for plugin in self._plugins.values():
                if identifier in plugin.aliases:
                    return plugin.id
        raise PluginNotFoundError(f"Unknown plugin: '{identifier}'.")

    def suggest(self, identifier: str, limit: int = 3) -> list[str]:
        """Suggest close-matching plugin ids for an unrecognized identifier.

        Matches against every registered plugin's id and aliases, then
        maps any alias match back to its canonical plugin id, so every
        returned suggestion is an id a `plugin` command accepts.

        Args:
            identifier: The unrecognized id/alias the user typed.
            limit: Maximum number of suggestions to return.

        Returns:
            Canonical plugin ids closest to `identifier`, closest
            first, de-duplicated. Empty if nothing is close enough.
        """
        with self._lock:
            canonical_by_identifier: dict[str, str] = {}
            for plugin in self._plugins.values():
                canonical_by_identifier[plugin.id] = plugin.id
                for alias in plugin.aliases:
                    canonical_by_identifier[alias] = plugin.id

        matches = get_close_matches(
            identifier, canonical_by_identifier.keys(), n=limit, cutoff=0.5
        )
        suggestions: list[str] = []
        for match in matches:
            canonical_id = canonical_by_identifier[match]
            if canonical_id not in suggestions:
                suggestions.append(canonical_id)
        return suggestions

    def duplicate_aliases(self) -> list[str]:
        """Return identifiers claimed by more than one registered plugin.

        Re-derives collisions from the live catalog rather than only
        trusting `register()`'s own check, so `plugin doctor` can
        report catalog/alias consistency as a live diagnostic
        (EP-009.1 "Registry consistency").

        Returns:
            Sorted ids/aliases claimed by more than one plugin. Empty
            if the catalog is fully consistent.
        """
        with self._lock:
            owner_by_identifier: dict[str, str] = {}
            conflicts: set[str] = set()
            for plugin in self._plugins.values():
                for identifier in (plugin.id, *plugin.aliases):
                    owner = owner_by_identifier.get(identifier)
                    if owner is None:
                        owner_by_identifier[identifier] = plugin.id
                    elif owner != plugin.id:
                        conflicts.add(identifier)
        return sorted(conflicts)

    def _check_alias_collisions(self, plugin: Plugin) -> None:
        """Verify `plugin`'s id/aliases do not collide with the catalog.

        Must be called while `self._lock` is already held.

        Args:
            plugin: The plugin about to be registered.

        Raises:
            PluginRegistryError: If `plugin` declares a duplicate alias
                on itself, or its id/aliases collide with an already
                registered plugin's id/aliases.
        """
        if len(set(plugin.aliases)) != len(plugin.aliases):
            raise PluginRegistryError(f"Plugin '{plugin.id}' declares a duplicate alias.")

        claimed = {plugin.id, *plugin.aliases}
        for existing in self._plugins.values():
            collisions = claimed & {existing.id, *existing.aliases}
            if collisions:
                raise PluginRegistryError(
                    f"Plugin '{plugin.id}' id/alias collides with "
                    f"'{existing.id}': {', '.join(sorted(collisions))}."
                )
