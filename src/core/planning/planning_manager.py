"""PlanningManager for EP-029 Planning Engine.

PlanningManager is the single place that knows which planning provider
is currently active, and how the built-in "planning" provider and the
default `max_steps` limit are resolved from 'planning.*' configuration
(see config/config.yaml) -- matching EP-026/EP-027/EP-028's split
between provider lifecycle (here) and pipeline orchestration
(`PlanningEngine`).

Keeps the current-provider choice and the current limit entirely in
memory, so a future 'planning use <provider>' takes effect immediately
-- no restart required, and no write back to config/config.yaml
(`Config` exposes no write path; see `src/core/config.py`).

The rest of Jarvis is expected to depend only on `PlanningManager` (via
`PlanningEngine`/`PlanningService`), never on a concrete
`PlanningProvider` directly, so the active provider can change without
any other component needing to know which one is active. New provider
types (e.g. a future AI-backed planner) can be added at runtime via
`register_provider()` without modifying this class.
"""

from __future__ import annotations

from threading import Lock

from loguru import logger

from src.core.config import Config
from src.core.planning.planning_provider import (
    DefaultPlanningProvider,
    PlanningConfigurationError,
    PlanningError,
    PlanningProvider,
)

__all__ = [
    "PlanningManager",
    "PlanningProviderRegistryError",
    "PlanningProviderNotFoundError",
]

DEFAULT_MAX_STEPS: int = 10


class PlanningProviderRegistryError(PlanningError):
    """Raised for invalid catalog operations (e.g. duplicate provider name)."""


class PlanningProviderNotFoundError(PlanningError):
    """Raised when an operation references a provider name not in the catalog."""


class PlanningManager:
    """Owns the currently active planning provider, its enabled state and step limit.

    Responsibilities:
        - Build the built-in "planning" provider (`DefaultPlanningProvider`).
        - Register a provider so it can later be selected.
        - Select and report the currently active provider.
        - List every registered provider.
        - Expose the default `max_steps` limit read from 'planning.*'
          configuration.
        - Disable the Planning Engine subsystem as a whole.
    """

    def __init__(self, config: Config) -> None:
        """Initialize the PlanningManager and build its built-in provider.

        Args:
            config: Loaded application configuration. Read once, here,
                for 'planning.enabled', 'planning.default_provider' and
                'planning.max_steps'.

        Raises:
            PlanningConfigurationError: If any 'planning.*' value is
                present but malformed (wrong type, empty, out of
                range, or -- for 'planning.default_provider' -- a name
                that does not match any registered provider).
                Configuration values are validated, never silently
                replaced with a default.
        """
        self._providers: dict[str, PlanningProvider] = {}
        self._lock = Lock()
        self._enabled = self._validated_bool(config, "planning.enabled", True)
        self._max_steps = self._validated_positive_int(config, "planning.max_steps", DEFAULT_MAX_STEPS)

        self.register_provider(DefaultPlanningProvider())

        self._current_name: str | None = self._resolve_default_provider(config)

    def _resolve_default_provider(self, config: Config) -> str | None:
        """Validate and resolve 'planning.default_provider' against the catalog.

        Args:
            config: Loaded application configuration.

        Returns:
            The validated provider name to select as current, or None
            if 'planning.default_provider' is explicitly "none"
            (case-insensitive).

        Raises:
            PlanningConfigurationError: If the configured value is not
                a non-empty string, or does not match any registered
                provider name (and is not "none").
        """
        raw_value = config.get("planning.default_provider", "planning")
        if not isinstance(raw_value, str) or not raw_value.strip():
            raise PlanningConfigurationError(
                "Invalid value for 'planning.default_provider': expected a "
                f'non-empty string naming a provider (or "none"), got {raw_value!r}.'
            )

        name = raw_value.strip()
        if name.lower() == "none":
            return None

        with self._lock:
            known_names = sorted(self._providers)
        if name not in known_names:
            available = ", ".join(known_names) if known_names else "none registered"
            raise PlanningConfigurationError(
                f"Invalid 'planning.default_provider': '{name}' is not a "
                f"registered planning provider. Available providers: {available}."
            )
        return name

    # ---------- Provider lifecycle ----------

    def register_provider(self, provider: PlanningProvider) -> None:
        """Register a provider so it can later be selected by `set_current()`.

        Args:
            provider: The PlanningProvider to register.

        Raises:
            PlanningProviderRegistryError: If a provider with the same
                name is already registered.
        """
        name = provider.provider_name()
        with self._lock:
            if name in self._providers:
                raise PlanningProviderRegistryError(f"Planning provider already registered: '{name}'.")
            self._providers[name] = provider
        logger.info(f"Planning provider registered: '{name}'.")

    def get_provider(self, name: str) -> PlanningProvider:
        """Return a single registered provider by name.

        Args:
            name: The provider's registered name.

        Returns:
            The matching PlanningProvider.

        Raises:
            PlanningProviderNotFoundError: If `name` is not registered.
        """
        with self._lock:
            provider = self._providers.get(name)
            known_names = sorted(self._providers)
        if provider is None:
            available = ", ".join(known_names) if known_names else "none registered"
            raise PlanningProviderNotFoundError(
                f"Unknown planning provider: '{name}'. Available providers: {available}."
            )
        return provider

    def set_current(self, name: str) -> None:
        """Select the currently active provider.

        Takes effect immediately in memory; no restart is required and
        no configuration file is written.

        Args:
            name: The registered provider name to activate.

        Raises:
            PlanningProviderNotFoundError: If `name` is not registered.
        """
        self.get_provider(name)  # raises PlanningProviderNotFoundError if unknown
        with self._lock:
            self._current_name = name
        logger.info(f"Planning current provider set to '{name}'.")

    def get_current(self) -> PlanningProvider | None:
        """Return the currently active provider.

        Returns:
            The active PlanningProvider, or None if no provider is
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

    def list_providers(self) -> list[PlanningProvider]:
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

    # ---------- Planning Engine subsystem enable/disable ----------

    def is_enabled(self) -> bool:
        """Return whether the Planning Engine subsystem is currently enabled."""
        with self._lock:
            return self._enabled

    def disable(self) -> None:
        """Disable the Planning Engine subsystem and clear the current provider selection."""
        with self._lock:
            self._enabled = False
            self._current_name = None
        logger.info("Planning Engine subsystem disabled.")

    # ---------- Default limit ----------

    def max_steps(self) -> int:
        """Return the default maximum number of steps a plan may contain."""
        with self._lock:
            return self._max_steps

    def set_max_steps(self, value: int) -> None:
        """Set the default maximum number of steps a plan may contain.

        Takes effect immediately in memory; no restart is required and
        no configuration file is written.

        Args:
            value: The new default maximum, a positive integer.

        Raises:
            PlanningConfigurationError: If `value` is not a positive integer.
        """
        validated = self._validate_positive_int_value(value, "max_steps")
        with self._lock:
            self._max_steps = validated
        logger.info(f"Planning max_steps set to {validated}.")

    # ---------- Configuration loading ----------

    @staticmethod
    def _validated_bool(config: Config, key_path: str, default: bool) -> bool:
        """Read `key_path` from `config`, validating it is a real boolean.

        Args:
            config: Loaded application configuration.
            key_path: Dotted configuration key (e.g. 'planning.enabled').
            default: Value to use if `key_path` is absent from configuration.

        Returns:
            The validated boolean value.

        Raises:
            PlanningConfigurationError: If `key_path` is present but is
                not an actual boolean (e.g. a string like "true").
        """
        value = config.get(key_path, default)
        if not isinstance(value, bool):
            raise PlanningConfigurationError(
                f"Invalid value for '{key_path}': expected true/false, got {value!r} "
                f"({type(value).__name__})."
            )
        return value

    @classmethod
    def _validated_positive_int(cls, config: Config, key_path: str, default: int) -> int:
        """Read `key_path` from `config`, validating it is a positive integer.

        Args:
            config: Loaded application configuration.
            key_path: Dotted configuration key (e.g. 'planning.max_steps').
            default: Value to use if `key_path` is absent from configuration.

        Returns:
            The validated positive integer.

        Raises:
            PlanningConfigurationError: If `key_path` is present but is
                not a positive integer (e.g. a quoted string, a float,
                or zero/negative).
        """
        value = config.get(key_path, default)
        return cls._validate_positive_int_value(value, key_path)

    @staticmethod
    def _validate_positive_int_value(value: object, key_path: str) -> int:
        """Validate that `value` is a positive integer.

        Args:
            value: The candidate value.
            key_path: Dotted configuration key (or field name) used in
                error messages.

        Returns:
            `value`, unchanged.

        Raises:
            PlanningConfigurationError: If `value` is not a positive integer.
        """
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise PlanningConfigurationError(
                f"Invalid value for '{key_path}': expected a positive integer, got "
                f"{value!r} ({type(value).__name__})."
            )
        return value
