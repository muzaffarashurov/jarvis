"""Plugin domain model for EP-009 Plugin SDK & Plugin Manager.

Defines the static catalog entry (`Plugin`), its lifecycle states
(`PluginStatus`), and the structural contract (`PluginInterface`) a
plugin's entry point must satisfy. This module owns no runtime
execution: it is pure data plus a structural contract, matching the
pattern already used for the Process Catalog (see
src/core/processes/process.py) and the Workflow Engine (see
src/core/workflows/workflow.py).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Callable, Protocol, runtime_checkable

if TYPE_CHECKING:
    from src.core.plugins.plugin_context import PluginContext


class PluginStatus(str, Enum):
    """Lifecycle states a registered plugin can report.

    Mirrors the five lifecycle stages required by EP-009: load,
    initialize, start, stop, unload.
    """

    REGISTERED = "REGISTERED"
    LOADED = "LOADED"
    INITIALIZED = "INITIALIZED"
    RUNNING = "RUNNING"
    STOPPED = "STOPPED"
    UNLOADED = "UNLOADED"
    FAILED = "FAILED"


@runtime_checkable
class PluginInterface(Protocol):
    """Structural contract a plugin's entry point instance must satisfy.

    Per EP-009's "Important Design Rules", a plugin instance receives
    only a PluginContext and must not know about the CLI, Telegram,
    Voice, Scheduler, or any future AI integration directly.
    """

    def initialize(self, context: "PluginContext") -> None:
        """Prepare the plugin using services exposed by `context`."""
        ...

    def start(self) -> None:
        """Start the plugin's runtime behavior."""
        ...

    def stop(self) -> None:
        """Stop the plugin's runtime behavior."""
        ...


@dataclass
class Plugin:
    """A single catalog entry describing a plugin known to Jarvis.

    Unlike the read-only catalog entries used by the Process Catalog
    (EP-008), a Plugin carries its own lifecycle `status`, since
    EP-009 explicitly requires the Plugin model to expose it.
    `PluginRegistry` is the single owner of this mutation (see
    `PluginRegistry.update_status`); no other component may assign to
    `status` directly, preserving the project's Single Source of Truth
    rule.

    Attributes:
        id: Unique, stable identifier for the plugin
            (e.g. "invoice_automation"). Used as the dependency key.
        name: Human-readable display name.
        version: Version string (e.g. "1.0.0").
        description: Short description shown by `plugin info`.
        author: Plugin author or owning team.
        enabled: Whether this plugin participates in auto-loading and
            `plugin status` reporting.
        entry_point: Factory that creates the plugin's runtime
            instance, or None for metadata-only plugins registered for
            catalog visibility without an executable implementation
            (see EP-009's "Default Plugins").
        dependencies: IDs of plugins that must be loaded before this
            one is loaded.
        capabilities: Free-form capability tags describing what this
            plugin provides (e.g. "invoice.automation").
        status: Current lifecycle state, owned by PluginRegistry.
    """

    id: str
    name: str
    version: str
    description: str
    author: str
    enabled: bool = True
    entry_point: Callable[[], PluginInterface] | None = None
    dependencies: tuple[str, ...] = field(default_factory=tuple)
    capabilities: tuple[str, ...] = field(default_factory=tuple)
    status: PluginStatus = PluginStatus.REGISTERED
