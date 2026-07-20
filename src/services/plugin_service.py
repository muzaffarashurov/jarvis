"""Plugin Manager service for EP-009 Plugin SDK & Plugin Manager.

PluginService is the entry point CLI modules use to manage plugins. It
implements no plugin lifecycle logic of its own: loading, unloading,
and reloading are always delegated to PluginLoader, and catalog data
is always read from PluginRegistry, matching this project's Single
Source of Truth rule.

EP-009.1 adds id/alias resolution ahead of every lookup and lifecycle
call, so `plugin info/load/unload/reload` accept either a plugin's
canonical id or one of its declared aliases, plus a "Did you mean"
suggestion when neither matches.

EP-010 adds an optional PluginDiscovery collaborator: `discover_plugins()`
registers every manifest PluginDiscovery finds under the configured
plugin directory, reusing PluginRegistry.register() for duplicate-id
detection and PluginLoader.resolve_dependencies() for dependency
validation rather than re-implementing either check here. `load_all()`
and `reload_all()` reuse the existing single-plugin methods so newly
discovered plugins are picked up by Bootstrap's auto-load step without
Bootstrap or PluginService needing to know about them individually.
"""

from __future__ import annotations

from dataclasses import dataclass

from loguru import logger

from src.core.command_router import CommandResult
from src.core.config import Config
from src.core.plugins.plugin import Plugin, PluginStatus
from src.core.plugins.plugin_discovery import PluginDiscovery, PluginDiscoveryError
from src.core.plugins.plugin_loader import (
    DependencyCycleError,
    MissingDependencyError,
    PluginAlreadyLoadedError,
    PluginInitializationError,
    PluginLoader,
    VersionMismatchError,
)
from src.core.plugins.plugin_registry import (
    PluginNotFoundError,
    PluginRegistry,
    PluginRegistryError,
)

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
        aliases_ok: Whether no id/alias is claimed by more than one
            registered plugin (EP-009.1 "Duplicate aliases" /
            "Duplicate plugins" / "Registry consistency").
        discovery_ok: Whether auto-discovery is healthy. True when no
            PluginDiscovery is configured (discovery is optional) or
            when the configured plugin directory could be scanned
            without error (EP-010 "Discovery").
        context_ok: Whether the PluginLoader's PluginContext exposes a
            configuration and execution engine reference.
    """

    registry_ok: bool
    loader_ok: bool
    dependencies_ok: bool
    configuration_ok: bool
    aliases_ok: bool
    discovery_ok: bool
    context_ok: bool

    @property
    def is_ready(self) -> bool:
        """Return True only if every diagnostic check passed."""
        return (
            self.registry_ok
            and self.loader_ok
            and self.dependencies_ok
            and self.configuration_ok
            and self.aliases_ok
            and self.discovery_ok
            and self.context_ok
        )


class PluginService:
    """Coordinates plugin discovery, lifecycle, and diagnostics.

    Responsibilities:
        - Resolve a plugin id or alias to a canonical plugin id.
        - Discover and register plugins from the configured plugin
            directory (EP-010).
        - Load / unload / reload a registered plugin, individually or
            for every enabled plugin at once.
        - List all registered plugins.
        - Return a single plugin's metadata for `plugin info`.
        - Report plugins currently RUNNING for `plugin status`.
        - Run the `plugin doctor` readiness checks.
    """

    def __init__(
        self,
        registry: PluginRegistry,
        loader: PluginLoader,
        config: Config,
        discovery: PluginDiscovery | None = None,
    ) -> None:
        """Initialize the PluginService.

        Args:
            registry: Catalog of known plugins.
            loader: Loader used to drive plugin lifecycle transitions.
            config: Loaded application configuration ('plugins.*').
            discovery: Scanner used by `discover_plugins()` to find
                plugins under the configured plugin directory (EP-010).
                Optional: when None, `discover_plugins()` is a no-op,
                so auto-discovery remains an opt-in capability.
        """
        self._registry = registry
        self._loader = loader
        self._config = config
        self._discovery = discovery

    # ---------- Public API ----------

    def list_plugins(self) -> list[Plugin]:
        """Return every registered plugin."""
        return self._registry.list()

    def get_plugin(self, plugin_id: str) -> Plugin:
        """Return a single registered plugin's metadata.

        Args:
            plugin_id: The plugin's canonical id or one of its aliases.

        Returns:
            The matching Plugin.

        Raises:
            PluginNotFoundError: If `plugin_id` matches no known
                plugin, with a "Did you mean" suggestion when a close
                match exists.
        """
        canonical_id = self._resolve_id(plugin_id)
        return self._registry.get(canonical_id)

    def running_plugins(self) -> list[Plugin]:
        """Return every plugin currently reporting RUNNING status."""
        return [plugin for plugin in self._registry.list() if plugin.status == PluginStatus.RUNNING]

    def load_plugin(self, plugin_id: str) -> CommandResult:
        """Load a plugin by id or alias, resolving dependencies first.

        Args:
            plugin_id: The plugin's canonical id or one of its aliases.

        Returns:
            A CommandResult describing the outcome.
        """
        try:
            canonical_id = self._resolve_id(plugin_id)
            self._loader.load(canonical_id)
        except _LOAD_ERRORS as exc:
            logger.error(f"Failed to load plugin '{plugin_id}': {exc}")
            return CommandResult(success=False, message=str(exc))

        return CommandResult(success=True, message=f"Plugin '{canonical_id}' loaded.")

    def unload_plugin(self, plugin_id: str) -> CommandResult:
        """Unload a plugin by id or alias.

        Args:
            plugin_id: The plugin's canonical id or one of its aliases.

        Returns:
            A CommandResult describing the outcome.
        """
        try:
            canonical_id = self._resolve_id(plugin_id)
            self._loader.unload(canonical_id)
        except (PluginNotFoundError, PluginInitializationError) as exc:
            logger.error(f"Failed to unload plugin '{plugin_id}': {exc}")
            return CommandResult(success=False, message=str(exc))

        return CommandResult(success=True, message=f"Plugin '{canonical_id}' unloaded.")

    def reload_plugin(self, plugin_id: str) -> CommandResult:
        """Reload a plugin by id or alias (unload, then load).

        Args:
            plugin_id: The plugin's canonical id or one of its aliases.

        Returns:
            A CommandResult describing the outcome.
        """
        try:
            canonical_id = self._resolve_id(plugin_id)
            self._loader.reload(canonical_id)
        except _LOAD_ERRORS as exc:
            logger.error(f"Failed to reload plugin '{plugin_id}': {exc}")
            return CommandResult(success=False, message=str(exc))

        return CommandResult(success=True, message=f"Plugin '{canonical_id}' reloaded.")

    def run_doctor(self) -> PluginDoctorReport:
        """Run the `plugin doctor` readiness checks."""
        return PluginDoctorReport(
            registry_ok=len(self._registry.list()) > 0,
            loader_ok=self._loader is not None,
            dependencies_ok=self._validate_dependencies(),
            configuration_ok=self._config.get("plugins.enabled") is not None,
            aliases_ok=not self._registry.duplicate_aliases(),
            discovery_ok=self._check_discovery(),
            context_ok=self._loader.context_is_ready(),
        )

    # ---------- Bulk lifecycle (EP-010) ----------

    def load_all(self) -> list[CommandResult]:
        """Attempt to load every enabled, registered plugin.

        Reuses `load_plugin()` per plugin rather than re-implementing
        active-state checks, so an already-active plugin is reported
        as a failed CommandResult (PluginAlreadyLoadedError) exactly
        as it would be through a single `plugin load` call.

        Returns:
            One CommandResult per enabled plugin, in catalog order.
        """
        return [self.load_plugin(plugin.id) for plugin in self._registry.list() if plugin.enabled]

    def reload_all(self) -> list[CommandResult]:
        """Reload every enabled, registered plugin.

        Returns:
            One CommandResult per enabled plugin, in catalog order.
        """
        return [self.reload_plugin(plugin.id) for plugin in self._registry.list() if plugin.enabled]

    def discover_plugins(self) -> list[str]:
        """Discover plugins and register every one that validates.

        Each discovered manifest is registered, then its dependency
        chain is immediately checked by reusing PluginLoader's
        existing `resolve_dependencies()` (never duplicating that
        check here, per this project's rules). A plugin whose
        dependencies do not resolve is unregistered again, so only
        fully valid plugins remain in the catalog (EP-010 "Validate
        dependencies before registration").

        Returns:
            Canonical ids of plugins newly registered this call.
            Manifests that fail structural validation, duplicate an
            existing id, or fail dependency resolution are skipped and
            logged rather than raised, per EP-010 "Ignore invalid
            plugins". Returns an empty list if no PluginDiscovery was
            configured.
        """
        if self._discovery is None:
            logger.info("Plugin auto-discovery is not configured; skipping.")
            return []

        registered: list[str] = []
        for manifest in self._discovery.discover():
            plugin = manifest.to_plugin()
            try:
                self._registry.register(plugin)
            except PluginRegistryError as exc:
                logger.error(f"Plugin skipped: '{plugin.id}': {exc}")
                continue

            try:
                self._loader.resolve_dependencies(plugin.id)
            except (PluginNotFoundError, MissingDependencyError, DependencyCycleError) as exc:
                logger.error(f"Plugin skipped: '{plugin.id}': {exc}")
                self._registry.unregister(plugin.id)
                continue

            registered.append(plugin.id)
            logger.info(f"Plugin registered: '{plugin.id}'.")

        return registered

    # ---------- Default Plugins ----------

    @staticmethod
    def default_plugins() -> list[Plugin]:
        """Return metadata-only Plugin entries for existing Jarvis modules.

        Registers Invoice Automation, Fast Response Board, and
        Workflow Engine as plugins by metadata only, per EP-009's
        "Default Plugins" ("Do NOT rewrite their implementation.").
        Each has `entry_point=None`: PluginLoader treats that as a
        metadata-only plugin and performs lifecycle status bookkeeping
        without invoking any implementation. EP-009.1 adds short
        aliases so `plugin` commands can address each one without
        typing its full id.

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
                aliases=("invoice", "inv"),
            ),
            Plugin(
                id="fast_response_board",
                name="Fast Response Board",
                version="1.0.0",
                description="Fast Response Board Excel workbook (EP-006).",
                author="Jarvis",
                capabilities=("fast_response.board",),
                aliases=("frb", "board"),
            ),
            Plugin(
                id="workflow_engine",
                name="Workflow Engine",
                version="1.0.0",
                description="Workflow Engine (EP-007).",
                author="Jarvis",
                dependencies=("invoice_automation", "fast_response_board"),
                capabilities=("workflow.orchestration",),
                aliases=("workflow", "wf"),
            ),
        ]

    # ---------- Internal helpers ----------

    def _resolve_id(self, identifier: str) -> str:
        """Resolve a plugin id or alias to a canonical plugin id.

        Args:
            identifier: A plugin id or one of its declared aliases.

        Returns:
            The canonical plugin id.

        Raises:
            PluginNotFoundError: If `identifier` matches no known
                plugin. The message includes a "Did you mean"
                suggestion when a close match exists (EP-009.1
                "Improve CLI error messages").
        """
        try:
            return self._registry.resolve_id(identifier)
        except PluginNotFoundError:
            suggestions = self._registry.suggest(identifier)
            if suggestions:
                raise PluginNotFoundError(
                    f"Unknown plugin: {identifier}\nDid you mean\n"
                    f"{', '.join(suggestions)}"
                ) from None
            raise

    def _validate_dependencies(self) -> bool:
        """Return True if every registered plugin resolves a valid load order."""
        for plugin in self._registry.list():
            try:
                self._loader.resolve_dependencies(plugin.id)
            except (PluginNotFoundError, MissingDependencyError, DependencyCycleError) as exc:
                logger.error(f"Dependency check failed for '{plugin.id}': {exc}")
                return False
        return True

    def _check_discovery(self) -> bool:
        """Return whether auto-discovery is healthy.

        Auto-discovery is optional: this reports True when no
        PluginDiscovery is configured, and also True when the
        configured plugin directory is simply absent (PluginDiscovery
        itself treats a missing directory as "nothing to discover",
        not an error). It only reports False if the plugin directory
        exists but could not be scanned.

        Returns:
            True if discovery is either unconfigured or scannable.
        """
        if self._discovery is None:
            return True
        try:
            self._discovery.discover()
        except PluginDiscoveryError as exc:
            logger.error(f"Discovery check failed: {exc}")
            return False
        return True
