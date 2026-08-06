"""CollaborationManager for EP-032 Multi-Agent Collaboration.

CollaborationManager is the single place that knows which collaboration
provider is currently active, and resolves the built-in "collaboration"
provider from 'collaboration.*' configuration (see config/config.yaml)
-- matching EP-028 through EP-031's split between provider lifecycle
(here) and pipeline orchestration (`CollaborationEngine`).

Keeps the current-provider choice entirely in memory, so a future
'collaborate use <provider>' takes effect immediately -- no restart
required, and no write back to config/config.yaml (`Config` exposes no
write path; see `src/core/config.py`).

The rest of Jarvis is expected to depend only on `CollaborationManager`
(via `CollaborationEngine`/`CollaborationService`), never on a concrete
`CollaborationProvider` directly, so the active provider can change
without any other component needing to know which one is active.

This manager owns no reference to `AgentManager` (EP-028) or its
catalog -- reaching the currently registered agents is
`CollaborationEngine`'s concern, supplied at construction time. This
manager owns provider selection and configuration loading only,
exactly mirroring `PlanningManager`/`PlanExecutionManager`/`ToolManager`.
"""

from __future__ import annotations

from threading import Lock

from loguru import logger

from src.core.collaboration.collaboration_provider import (
    CollaborationConfigurationError,
    CollaborationError,
    CollaborationProvider,
    DefaultCollaborationProvider,
)
from src.core.config import Config

__all__ = [
    "CollaborationManager",
    "CollaborationProviderRegistryError",
    "CollaborationProviderNotFoundError",
]


class CollaborationProviderRegistryError(CollaborationError):
    """Raised for invalid catalog operations (e.g. duplicate provider name)."""


class CollaborationProviderNotFoundError(CollaborationError):
    """Raised when an operation references a provider name not in the catalog."""


class CollaborationManager:
    """Owns the currently active collaboration provider and its enabled state.

    Responsibilities:
        - Build the built-in "collaboration" provider
          (`DefaultCollaborationProvider`).
        - Register a provider so it can later be selected.
        - Select and report the currently active provider.
        - List every registered provider.
        - Disable the Multi-Agent Collaboration subsystem as a whole.
    """

    def __init__(self, config: Config) -> None:
        """Initialize the CollaborationManager and build its built-in provider.

        Args:
            config: Loaded application configuration. Read once, here,
                for 'collaboration.enabled' and
                'collaboration.default_provider'.

        Raises:
            CollaborationConfigurationError: If any 'collaboration.*'
                value is present but malformed (wrong type, empty, or
                -- for 'collaboration.default_provider' -- a name that
                does not match any registered provider). Configuration
                values are validated, never silently replaced with a
                default.
        """
        self._providers: dict[str, CollaborationProvider] = {}
        self._lock = Lock()
        self._enabled = self._validated_bool(config, "collaboration.enabled", True)

        self.register_provider(DefaultCollaborationProvider())

        self._current_name: str | None = self._resolve_default_provider(config)

    def _resolve_default_provider(self, config: Config) -> str | None:
        """Validate and resolve 'collaboration.default_provider' against the catalog.

        Args:
            config: Loaded application configuration.

        Returns:
            The validated provider name to select as current, or None
            if 'collaboration.default_provider' is explicitly "none"
            (case-insensitive).

        Raises:
            CollaborationConfigurationError: If the configured value is
                not a non-empty string, or does not match any
                registered provider name (and is not "none").
        """
        raw_value = config.get("collaboration.default_provider", "collaboration")
        if not isinstance(raw_value, str) or not raw_value.strip():
            raise CollaborationConfigurationError(
                "Invalid value for 'collaboration.default_provider': expected a "
                f'non-empty string naming a provider (or "none"), got {raw_value!r}.'
            )

        name = raw_value.strip()
        if name.lower() == "none":
            return None

        with self._lock:
            known_names = sorted(self._providers)
        if name not in known_names:
            available = ", ".join(known_names) if known_names else "none registered"
            raise CollaborationConfigurationError(
                f"Invalid 'collaboration.default_provider': '{name}' is not a "
                f"registered collaboration provider. Available providers: {available}."
            )
        return name

    # ---------- Provider lifecycle ----------

    def register_provider(self, provider: CollaborationProvider) -> None:
        """Register a provider so it can later be selected by `set_current()`.

        Args:
            provider: The CollaborationProvider to register.

        Raises:
            CollaborationProviderRegistryError: If a provider with the
                same name is already registered.
        """
        name = provider.provider_name()
        with self._lock:
            if name in self._providers:
                raise CollaborationProviderRegistryError(
                    f"Collaboration provider already registered: '{name}'."
                )
            self._providers[name] = provider
        logger.info(f"Collaboration provider registered: '{name}'.")

    def get_provider(self, name: str) -> CollaborationProvider:
        """Return a single registered provider by name.

        Args:
            name: The provider's registered name.

        Returns:
            The matching CollaborationProvider.

        Raises:
            CollaborationProviderNotFoundError: If `name` is not registered.
        """
        with self._lock:
            provider = self._providers.get(name)
            known_names = sorted(self._providers)
        if provider is None:
            available = ", ".join(known_names) if known_names else "none registered"
            raise CollaborationProviderNotFoundError(
                f"Unknown collaboration provider: '{name}'. Available providers: {available}."
            )
        return provider

    def set_current(self, name: str) -> None:
        """Select the currently active provider.

        Takes effect immediately in memory; no restart is required and
        no configuration file is written.

        Args:
            name: The registered provider name to activate.

        Raises:
            CollaborationProviderNotFoundError: If `name` is not registered.
        """
        self.get_provider(name)  # raises CollaborationProviderNotFoundError if unknown
        with self._lock:
            self._current_name = name
        logger.info(f"Collaboration current provider set to '{name}'.")

    def get_current(self) -> CollaborationProvider | None:
        """Return the currently active provider.

        Returns:
            The active CollaborationProvider, or None if no provider
            is selected (including when the subsystem is disabled).
        """
        if not self.is_enabled():
            return None
        with self._lock:
            current_name = self._current_name
        if current_name is None:
            return None
        with self._lock:
            return self._providers.get(current_name)

    def list_providers(self) -> list[CollaborationProvider]:
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

    # ---------- Multi-Agent Collaboration subsystem enable/disable ----------

    def is_enabled(self) -> bool:
        """Return whether the Multi-Agent Collaboration subsystem is currently enabled."""
        with self._lock:
            return self._enabled

    def disable(self) -> None:
        """Disable the Multi-Agent Collaboration subsystem and clear the current provider selection."""
        with self._lock:
            self._enabled = False
            self._current_name = None
        logger.info("Multi-Agent Collaboration subsystem disabled.")

    # ---------- Configuration loading ----------

    @staticmethod
    def _validated_bool(config: Config, key_path: str, default: bool) -> bool:
        """Read `key_path` from `config`, validating it is a real boolean.

        Args:
            config: Loaded application configuration.
            key_path: Dotted configuration key (e.g. 'collaboration.enabled').
            default: Value to use if `key_path` is absent from configuration.

        Returns:
            The validated boolean value.

        Raises:
            CollaborationConfigurationError: If `key_path` is present
                but is not an actual boolean (e.g. a string like "true").
        """
        value = config.get(key_path, default)
        if not isinstance(value, bool):
            raise CollaborationConfigurationError(
                f"Invalid value for '{key_path}': expected true/false, got {value!r} "
                f"({type(value).__name__})."
            )
        return value
