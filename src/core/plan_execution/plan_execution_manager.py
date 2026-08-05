"""PlanExecutionManager for EP-030 Plan Execution Engine.

PlanExecutionManager is the single place that knows which
plan-execution provider is currently active, and how the built-in
"plan_execution" provider and the default 'stop_on_failure' policy are
resolved from 'plan_execution.*' configuration (see
config/config.yaml) -- matching EP-026 through EP-029's split between
provider lifecycle (here) and pipeline orchestration
(`PlanExecutionEngine`).

Keeps the current-provider choice and the current failure policy
entirely in memory, so a future 'execution use <provider>' takes
effect immediately -- no restart required, and no write back to
config/config.yaml (`Config` exposes no write path; see
`src/core/config.py`).

The rest of Jarvis is expected to depend only on `PlanExecutionManager`
(via `PlanExecutionEngine`/`PlanExecutionService`), never on a
concrete `PlanExecutionProvider` directly, so the active provider can
change without any other component needing to know which one is
active. New provider types (e.g. a future Tool-Engine-backed provider)
can be added at runtime via `register_provider()` without modifying
this class.
"""

from __future__ import annotations

from threading import Lock

from loguru import logger

from src.core.config import Config
from src.core.plan_execution.plan_execution_provider import (
    DefaultPlanExecutionProvider,
    PlanExecutionConfigurationError,
    PlanExecutionError,
    PlanExecutionProvider,
)

__all__ = [
    "PlanExecutionManager",
    "PlanExecutionProviderRegistryError",
    "PlanExecutionProviderNotFoundError",
]

DEFAULT_STOP_ON_FAILURE: bool = True


class PlanExecutionProviderRegistryError(PlanExecutionError):
    """Raised for invalid catalog operations (e.g. duplicate provider name)."""


class PlanExecutionProviderNotFoundError(PlanExecutionError):
    """Raised when an operation references a provider name not in the catalog."""


class PlanExecutionManager:
    """Owns the currently active plan-execution provider, its enabled state and failure policy.

    Responsibilities:
        - Build the built-in "plan_execution" provider
          (`DefaultPlanExecutionProvider`).
        - Register a provider so it can later be selected.
        - Select and report the currently active provider.
        - List every registered provider.
        - Expose the default `stop_on_failure` policy read from
          'plan_execution.*' configuration.
        - Disable the Plan Execution Engine subsystem as a whole.
    """

    def __init__(self, config: Config) -> None:
        """Initialize the PlanExecutionManager and build its built-in provider.

        Args:
            config: Loaded application configuration. Read once, here,
                for 'plan_execution.enabled',
                'plan_execution.default_provider' and
                'plan_execution.stop_on_failure'.

        Raises:
            PlanExecutionConfigurationError: If any 'plan_execution.*'
                value is present but malformed (wrong type, empty, or
                -- for 'plan_execution.default_provider' -- a name
                that does not match any registered provider).
                Configuration values are validated, never silently
                replaced with a default.
        """
        self._providers: dict[str, PlanExecutionProvider] = {}
        self._lock = Lock()
        self._enabled = self._validated_bool(config, "plan_execution.enabled", True)
        self._stop_on_failure = self._validated_bool(
            config, "plan_execution.stop_on_failure", DEFAULT_STOP_ON_FAILURE
        )

        self.register_provider(DefaultPlanExecutionProvider())

        self._current_name: str | None = self._resolve_default_provider(config)

    def _resolve_default_provider(self, config: Config) -> str | None:
        """Validate and resolve 'plan_execution.default_provider' against the catalog.

        Args:
            config: Loaded application configuration.

        Returns:
            The validated provider name to select as current, or None
            if 'plan_execution.default_provider' is explicitly "none"
            (case-insensitive).

        Raises:
            PlanExecutionConfigurationError: If the configured value is
                not a non-empty string, or does not match any
                registered provider name (and is not "none").
        """
        raw_value = config.get("plan_execution.default_provider", "plan_execution")
        if not isinstance(raw_value, str) or not raw_value.strip():
            raise PlanExecutionConfigurationError(
                "Invalid value for 'plan_execution.default_provider': expected a "
                f'non-empty string naming a provider (or "none"), got {raw_value!r}.'
            )

        name = raw_value.strip()
        if name.lower() == "none":
            return None

        with self._lock:
            known_names = sorted(self._providers)
        if name not in known_names:
            available = ", ".join(known_names) if known_names else "none registered"
            raise PlanExecutionConfigurationError(
                f"Invalid 'plan_execution.default_provider': '{name}' is not a "
                f"registered plan-execution provider. Available providers: {available}."
            )
        return name

    # ---------- Provider lifecycle ----------

    def register_provider(self, provider: PlanExecutionProvider) -> None:
        """Register a provider so it can later be selected by `set_current()`.

        Args:
            provider: The PlanExecutionProvider to register.

        Raises:
            PlanExecutionProviderRegistryError: If a provider with the
                same name is already registered.
        """
        name = provider.provider_name()
        with self._lock:
            if name in self._providers:
                raise PlanExecutionProviderRegistryError(
                    f"Plan-execution provider already registered: '{name}'."
                )
            self._providers[name] = provider
        logger.info(f"Plan-execution provider registered: '{name}'.")

    def get_provider(self, name: str) -> PlanExecutionProvider:
        """Return a single registered provider by name.

        Args:
            name: The provider's registered name.

        Returns:
            The matching PlanExecutionProvider.

        Raises:
            PlanExecutionProviderNotFoundError: If `name` is not registered.
        """
        with self._lock:
            provider = self._providers.get(name)
            known_names = sorted(self._providers)
        if provider is None:
            available = ", ".join(known_names) if known_names else "none registered"
            raise PlanExecutionProviderNotFoundError(
                f"Unknown plan-execution provider: '{name}'. Available providers: {available}."
            )
        return provider

    def set_current(self, name: str) -> None:
        """Select the currently active provider.

        Takes effect immediately in memory; no restart is required and
        no configuration file is written.

        Args:
            name: The registered provider name to activate.

        Raises:
            PlanExecutionProviderNotFoundError: If `name` is not registered.
        """
        self.get_provider(name)  # raises PlanExecutionProviderNotFoundError if unknown
        with self._lock:
            self._current_name = name
        logger.info(f"Plan-execution current provider set to '{name}'.")

    def get_current(self) -> PlanExecutionProvider | None:
        """Return the currently active provider.

        Returns:
            The active PlanExecutionProvider, or None if no provider
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

    def list_providers(self) -> list[PlanExecutionProvider]:
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

    # ---------- Plan Execution Engine subsystem enable/disable ----------

    def is_enabled(self) -> bool:
        """Return whether the Plan Execution Engine subsystem is currently enabled."""
        with self._lock:
            return self._enabled

    def disable(self) -> None:
        """Disable the Plan Execution Engine subsystem and clear the current provider selection."""
        with self._lock:
            self._enabled = False
            self._current_name = None
        logger.info("Plan Execution Engine subsystem disabled.")

    # ---------- Default failure policy ----------

    def stop_on_failure(self) -> bool:
        """Return whether execution halts the remaining plan after a step fails."""
        with self._lock:
            return self._stop_on_failure

    def set_stop_on_failure(self, value: bool) -> None:
        """Set whether execution halts the remaining plan after a step fails.

        Takes effect immediately in memory; no restart is required and
        no configuration file is written.

        Args:
            value: The new default.

        Raises:
            PlanExecutionConfigurationError: If `value` is not an
                actual boolean.
        """
        if not isinstance(value, bool):
            raise PlanExecutionConfigurationError(
                f"Invalid value for 'stop_on_failure': expected true/false, got {value!r} "
                f"({type(value).__name__})."
            )
        with self._lock:
            self._stop_on_failure = value
        logger.info(f"Plan Execution Engine stop_on_failure set to {value}.")

    # ---------- Configuration loading ----------

    @staticmethod
    def _validated_bool(config: Config, key_path: str, default: bool) -> bool:
        """Read `key_path` from `config`, validating it is a real boolean.

        Args:
            config: Loaded application configuration.
            key_path: Dotted configuration key (e.g.
                'plan_execution.enabled').
            default: Value to use if `key_path` is absent from configuration.

        Returns:
            The validated boolean value.

        Raises:
            PlanExecutionConfigurationError: If `key_path` is present
                but is not an actual boolean (e.g. a string like "true").
        """
        value = config.get(key_path, default)
        if not isinstance(value, bool):
            raise PlanExecutionConfigurationError(
                f"Invalid value for '{key_path}': expected true/false, got {value!r} "
                f"({type(value).__name__})."
            )
        return value
