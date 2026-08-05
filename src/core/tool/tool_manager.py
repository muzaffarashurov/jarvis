"""ToolManager for EP-031 Tool Engine.

ToolManager is the single place that knows which tool provider is
currently active, owns the `ToolRegistry` catalog, and resolves the
built-in "tool_engine" provider from 'tool.*' configuration (see
config/config.yaml) -- matching EP-026 through EP-030's split between
provider lifecycle (here) and pipeline orchestration (`ToolEngine`).

Keeps the current-provider choice entirely in memory, so a future
'tool use <provider>' takes effect immediately -- no restart required,
and no write back to config/config.yaml (`Config` exposes no write
path; see `src/core/config.py`).

The rest of Jarvis is expected to depend only on `ToolManager` (via
`ToolEngine`/`ToolService`), never on a concrete `ToolProvider`
directly, so the active provider can change without any other
component needing to know which one is active.
"""

from __future__ import annotations

from threading import Lock

from loguru import logger

from src.core.config import Config
from src.core.tool.tool import Tool
from src.core.tool.tool_provider import (
    DefaultToolProvider,
    ToolConfigurationError,
    ToolError,
    ToolProvider,
)
from src.core.tool.tool_registry import ToolRegistry

__all__ = [
    "ToolManager",
    "ToolProviderRegistryError",
    "ToolProviderNotFoundError",
]


class ToolProviderRegistryError(ToolError):
    """Raised for invalid catalog operations (e.g. duplicate provider name)."""


class ToolProviderNotFoundError(ToolError):
    """Raised when an operation references a provider name not in the catalog."""


class ToolManager:
    """Owns the currently active tool provider, its enabled state, and the tool catalog.

    Responsibilities:
        - Build the built-in "tool_engine" provider (`DefaultToolProvider`).
        - Own the `ToolRegistry` catalog of registered tools.
        - Register a provider so it can later be selected.
        - Select and report the currently active provider.
        - List every registered provider.
        - Disable the Tool Engine subsystem as a whole.
    """

    def __init__(self, config: Config) -> None:
        """Initialize the ToolManager, its registry, and its built-in provider.

        Args:
            config: Loaded application configuration. Read once, here,
                for 'tool.enabled' and 'tool.default_provider'.

        Raises:
            ToolConfigurationError: If any 'tool.*' value is present
                but malformed (wrong type, empty, or -- for
                'tool.default_provider' -- a name that does not match
                any registered provider). Configuration values are
                validated, never silently replaced with a default.
        """
        self._registry = ToolRegistry()
        self._providers: dict[str, ToolProvider] = {}
        self._lock = Lock()
        self._enabled = self._validated_bool(config, "tool.enabled", True)

        self.register_provider(DefaultToolProvider())

        self._current_name: str | None = self._resolve_default_provider(config)

    def _resolve_default_provider(self, config: Config) -> str | None:
        """Validate and resolve 'tool.default_provider' against the catalog.

        Args:
            config: Loaded application configuration.

        Returns:
            The validated provider name to select as current, or None
            if 'tool.default_provider' is explicitly "none"
            (case-insensitive).

        Raises:
            ToolConfigurationError: If the configured value is not a
                non-empty string, or does not match any registered
                provider name (and is not "none").
        """
        raw_value = config.get("tool.default_provider", "tool_engine")
        if not isinstance(raw_value, str) or not raw_value.strip():
            raise ToolConfigurationError(
                "Invalid value for 'tool.default_provider': expected a "
                f'non-empty string naming a provider (or "none"), got {raw_value!r}.'
            )

        name = raw_value.strip()
        if name.lower() == "none":
            return None

        with self._lock:
            known_names = sorted(self._providers)
        if name not in known_names:
            available = ", ".join(known_names) if known_names else "none registered"
            raise ToolConfigurationError(
                f"Invalid 'tool.default_provider': '{name}' is not a "
                f"registered tool provider. Available providers: {available}."
            )
        return name

    # ---------- Provider lifecycle ----------

    def register_provider(self, provider: ToolProvider) -> None:
        """Register a provider so it can later be selected by `set_current()`.

        Args:
            provider: The ToolProvider to register.

        Raises:
            ToolProviderRegistryError: If a provider with the same
                name is already registered.
        """
        name = provider.provider_name()
        with self._lock:
            if name in self._providers:
                raise ToolProviderRegistryError(f"Tool provider already registered: '{name}'.")
            self._providers[name] = provider
        logger.info(f"Tool provider registered: '{name}'.")

    def get_provider(self, name: str) -> ToolProvider:
        """Return a single registered provider by name.

        Args:
            name: The provider's registered name.

        Returns:
            The matching ToolProvider.

        Raises:
            ToolProviderNotFoundError: If `name` is not registered.
        """
        with self._lock:
            provider = self._providers.get(name)
            known_names = sorted(self._providers)
        if provider is None:
            available = ", ".join(known_names) if known_names else "none registered"
            raise ToolProviderNotFoundError(
                f"Unknown tool provider: '{name}'. Available providers: {available}."
            )
        return provider

    def set_current(self, name: str) -> None:
        """Select the currently active provider.

        Takes effect immediately in memory; no restart is required and
        no configuration file is written.

        Args:
            name: The registered provider name to activate.

        Raises:
            ToolProviderNotFoundError: If `name` is not registered.
        """
        self.get_provider(name)  # raises ToolProviderNotFoundError if unknown
        with self._lock:
            self._current_name = name
        logger.info(f"Tool current provider set to '{name}'.")

    def get_current(self) -> ToolProvider | None:
        """Return the currently active provider.

        Returns:
            The active ToolProvider, or None if no provider is
            selected (including when the subsystem is disabled).
        """
        if not self.is_enabled():
            return None
        with self._lock:
            current_name = self._current_name
        if current_name is None:
            return None
        with self._lock:
            return self._providers.get(current_name)

    def list_providers(self) -> list[ToolProvider]:
        """Return every registered provider, ordered by name."""
        with self._lock:
            return sorted(self._providers.values(), key=lambda provider: provider.provider_name())

    def current_provider_name(self) -> str | None:
        """Return the currently selected provider's name, or None if unselected.

        Returns None whenever `is_enabled()` is False, keeping this
        method consistent with `get_current()`.
        """
        if not self.is_enabled():
            return None
        with self._lock:
            return self._current_name

    # ---------- Tool catalog ----------

    def register_tool(self, tool: Tool) -> None:
        """Register a tool in the catalog owned by this manager.

        Args:
            tool: The Tool to add.

        Raises:
            ToolRegistryError: If a tool with the same id is already
                registered.
        """
        self._registry.register(tool)

    @property
    def registry(self) -> ToolRegistry:
        """Return the ToolRegistry owned by this manager.

        Returns:
            The ToolRegistry instance. Exposed read-mostly so
            `ToolEngine` and `ToolExecutionProvider` can look tools up
            through its public API -- this manager remains the only
            component that adds/removes entries via `register_tool()`.
        """
        return self._registry

    # ---------- Tool Engine subsystem enable/disable ----------

    def is_enabled(self) -> bool:
        """Return whether the Tool Engine subsystem is currently enabled."""
        with self._lock:
            return self._enabled

    def disable(self) -> None:
        """Disable the Tool Engine subsystem and clear the current provider selection."""
        with self._lock:
            self._enabled = False
            self._current_name = None
        logger.info("Tool Engine subsystem disabled.")

    # ---------- Configuration loading ----------

    @staticmethod
    def _validated_bool(config: Config, key_path: str, default: bool) -> bool:
        """Read `key_path` from `config`, validating it is a real boolean.

        Args:
            config: Loaded application configuration.
            key_path: Dotted configuration key (e.g. 'tool.enabled').
            default: Value to use if `key_path` is absent from configuration.

        Returns:
            The validated boolean value.

        Raises:
            ToolConfigurationError: If `key_path` is present but is
                not an actual boolean (e.g. a string like "true").
        """
        value = config.get(key_path, default)
        if not isinstance(value, bool):
            raise ToolConfigurationError(
                f"Invalid value for '{key_path}': expected true/false, got {value!r} "
                f"({type(value).__name__})."
            )
        return value
