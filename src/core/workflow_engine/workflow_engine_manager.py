"""WorkflowEngineManager for EP-033 Workflow Engine.

WorkflowEngineManager is the single place that knows which
workflow-run provider is currently active, owns the
`WorkflowDefinitionRegistry` catalog, and resolves the built-in
"workflow_engine" provider and the default 'stop_on_failure' policy
from 'workflow_engine.*' configuration (see config/config.yaml) --
matching EP-026 through EP-032's split between provider lifecycle
(here) and pipeline orchestration (`WorkflowEngine`).

Keeps the current-provider choice and the current failure policy
entirely in memory, so a future 'flow use <provider>' takes effect
immediately -- no restart required, and no write back to
config/config.yaml (`Config` exposes no write path; see
`src/core/config.py`).

The rest of Jarvis is expected to depend only on
`WorkflowEngineManager` (via `WorkflowEngine`/`WorkflowEngineService`),
never on a concrete `WorkflowRunProvider` directly, so the active
provider can change without any other component needing to know which
one is active.
"""

from __future__ import annotations

from threading import Lock

from loguru import logger

from src.core.config import Config
from src.core.workflow_engine.workflow_definition import WorkflowDefinition
from src.core.workflow_engine.workflow_definition_registry import WorkflowDefinitionRegistry
from src.core.workflow_engine.workflow_run_provider import (
    DefaultWorkflowRunProvider,
    WorkflowEngineConfigurationError,
    WorkflowEngineError,
    WorkflowRunProvider,
)

__all__ = [
    "WorkflowEngineManager",
    "WorkflowRunProviderRegistryError",
    "WorkflowRunProviderNotFoundError",
]

DEFAULT_STOP_ON_FAILURE: bool = True


class WorkflowRunProviderRegistryError(WorkflowEngineError):
    """Raised for invalid catalog operations (e.g. duplicate provider name)."""


class WorkflowRunProviderNotFoundError(WorkflowEngineError):
    """Raised when an operation references a provider name not in the catalog."""


class WorkflowEngineManager:
    """Owns the currently active workflow-run provider, its enabled state, failure
    policy, and the workflow definition catalog.

    Responsibilities:
        - Build the built-in "workflow_engine" provider
          (`DefaultWorkflowRunProvider`).
        - Own the `WorkflowDefinitionRegistry` catalog of registered
          workflow definitions.
        - Register a provider so it can later be selected.
        - Select and report the currently active provider.
        - List every registered provider.
        - Expose the default `stop_on_failure` policy read from
          'workflow_engine.*' configuration.
        - Disable the Workflow Engine subsystem as a whole.
    """

    def __init__(self, config: Config) -> None:
        """Initialize the WorkflowEngineManager, its registry, and its built-in provider.

        Args:
            config: Loaded application configuration. Read once, here,
                for 'workflow_engine.enabled',
                'workflow_engine.default_provider' and
                'workflow_engine.stop_on_failure'.

        Raises:
            WorkflowEngineConfigurationError: If any 'workflow_engine.*'
                value is present but malformed (wrong type, empty, or
                -- for 'workflow_engine.default_provider' -- a name
                that does not match any registered provider).
                Configuration values are validated, never silently
                replaced with a default.
        """
        self._registry = WorkflowDefinitionRegistry()
        self._providers: dict[str, WorkflowRunProvider] = {}
        self._lock = Lock()
        self._enabled = self._validated_bool(config, "workflow_engine.enabled", True)
        self._stop_on_failure = self._validated_bool(
            config, "workflow_engine.stop_on_failure", DEFAULT_STOP_ON_FAILURE
        )

        self.register_provider(DefaultWorkflowRunProvider())

        self._current_name: str | None = self._resolve_default_provider(config)

    def _resolve_default_provider(self, config: Config) -> str | None:
        """Validate and resolve 'workflow_engine.default_provider' against the catalog.

        Args:
            config: Loaded application configuration.

        Returns:
            The validated provider name to select as current, or None
            if 'workflow_engine.default_provider' is explicitly "none"
            (case-insensitive).

        Raises:
            WorkflowEngineConfigurationError: If the configured value
                is not a non-empty string, or does not match any
                registered provider name (and is not "none").
        """
        raw_value = config.get("workflow_engine.default_provider", "workflow_engine")
        if not isinstance(raw_value, str) or not raw_value.strip():
            raise WorkflowEngineConfigurationError(
                "Invalid value for 'workflow_engine.default_provider': expected a "
                f'non-empty string naming a provider (or "none"), got {raw_value!r}.'
            )

        name = raw_value.strip()
        if name.lower() == "none":
            return None

        with self._lock:
            known_names = sorted(self._providers)
        if name not in known_names:
            available = ", ".join(known_names) if known_names else "none registered"
            raise WorkflowEngineConfigurationError(
                f"Invalid 'workflow_engine.default_provider': '{name}' is not a "
                f"registered workflow-run provider. Available providers: {available}."
            )
        return name

    # ---------- Provider lifecycle ----------

    def register_provider(self, provider: WorkflowRunProvider) -> None:
        """Register a provider so it can later be selected by `set_current()`.

        Args:
            provider: The WorkflowRunProvider to register.

        Raises:
            WorkflowRunProviderRegistryError: If a provider with the
                same name is already registered.
        """
        name = provider.provider_name()
        with self._lock:
            if name in self._providers:
                raise WorkflowRunProviderRegistryError(
                    f"Workflow-run provider already registered: '{name}'."
                )
            self._providers[name] = provider
        logger.info(f"Workflow-run provider registered: '{name}'.")

    def get_provider(self, name: str) -> WorkflowRunProvider:
        """Return a single registered provider by name.

        Args:
            name: The provider's registered name.

        Returns:
            The matching WorkflowRunProvider.

        Raises:
            WorkflowRunProviderNotFoundError: If `name` is not registered.
        """
        with self._lock:
            provider = self._providers.get(name)
            known_names = sorted(self._providers)
        if provider is None:
            available = ", ".join(known_names) if known_names else "none registered"
            raise WorkflowRunProviderNotFoundError(
                f"Unknown workflow-run provider: '{name}'. Available providers: {available}."
            )
        return provider

    def set_current(self, name: str) -> None:
        """Select the currently active provider.

        Takes effect immediately in memory; no restart is required and
        no configuration file is written.

        Args:
            name: The registered provider name to activate.

        Raises:
            WorkflowRunProviderNotFoundError: If `name` is not registered.
        """
        self.get_provider(name)  # raises WorkflowRunProviderNotFoundError if unknown
        with self._lock:
            self._current_name = name
        logger.info(f"Workflow Engine current provider set to '{name}'.")

    def get_current(self) -> WorkflowRunProvider | None:
        """Return the currently active provider.

        Returns:
            The active WorkflowRunProvider, or None if no provider is
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

    def list_providers(self) -> list[WorkflowRunProvider]:
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

    # ---------- Workflow definition catalog ----------

    def register_definition(self, definition: WorkflowDefinition) -> None:
        """Register a workflow definition in the catalog owned by this manager.

        Args:
            definition: The WorkflowDefinition to add.

        Raises:
            WorkflowDefinitionRegistryError: If a definition with the
                same id is already registered.
        """
        self._registry.register(definition)

    @property
    def registry(self) -> WorkflowDefinitionRegistry:
        """Return the WorkflowDefinitionRegistry owned by this manager.

        Returns:
            The WorkflowDefinitionRegistry instance. Exposed
            read-mostly so `WorkflowEngine` can look definitions up
            through its public API -- this manager remains the only
            component that adds/removes entries via
            `register_definition()`.
        """
        return self._registry

    # ---------- Workflow Engine subsystem enable/disable ----------

    def is_enabled(self) -> bool:
        """Return whether the Workflow Engine subsystem is currently enabled."""
        with self._lock:
            return self._enabled

    def disable(self) -> None:
        """Disable the Workflow Engine subsystem and clear the current provider selection."""
        with self._lock:
            self._enabled = False
            self._current_name = None
        logger.info("Workflow Engine subsystem disabled.")

    # ---------- Default failure policy ----------

    def stop_on_failure(self) -> bool:
        """Return whether a run halts the remaining workflow after a step fails."""
        with self._lock:
            return self._stop_on_failure

    def set_stop_on_failure(self, value: bool) -> None:
        """Set whether a run halts the remaining workflow after a step fails.

        Takes effect immediately in memory; no restart is required and
        no configuration file is written.

        Args:
            value: The new default.

        Raises:
            WorkflowEngineConfigurationError: If `value` is not an
                actual boolean.
        """
        if not isinstance(value, bool):
            raise WorkflowEngineConfigurationError(
                f"Invalid value for 'stop_on_failure': expected true/false, got {value!r} "
                f"({type(value).__name__})."
            )
        with self._lock:
            self._stop_on_failure = value
        logger.info(f"Workflow Engine stop_on_failure set to {value}.")

    # ---------- Configuration loading ----------

    @staticmethod
    def _validated_bool(config: Config, key_path: str, default: bool) -> bool:
        """Read `key_path` from `config`, validating it is a real boolean.

        Args:
            config: Loaded application configuration.
            key_path: Dotted configuration key (e.g.
                'workflow_engine.enabled').
            default: Value to use if `key_path` is absent from configuration.

        Returns:
            The validated boolean value.

        Raises:
            WorkflowEngineConfigurationError: If `key_path` is present
                but is not an actual boolean (e.g. a string like "true").
        """
        value = config.get(key_path, default)
        if not isinstance(value, bool):
            raise WorkflowEngineConfigurationError(
                f"Invalid value for '{key_path}': expected true/false, got {value!r} "
                f"({type(value).__name__})."
            )
        return value
