"""AgentManager for EP-028 Agent Framework.

AgentManager is the single place that knows which agent is currently
active, and how the built-in "jarvis" agent and the default
'agent.startup_mode' are resolved from 'agent.*' configuration (see
config/config.yaml) -- matching EP-026/EP-027's split between provider
lifecycle (here) and pipeline orchestration (`AgentEngine`).

Keeps the current-agent choice entirely in memory, so a future
'agent use <name>' would take effect immediately -- no restart
required, and no write back to config/config.yaml (`Config` exposes no
write path; see `src/core/config.py`).

The rest of Jarvis is expected to depend only on `AgentManager` (via
`AgentEngine`/`AgentService`), never on a concrete `AgentProvider`
directly, so the active agent can change without any other component
needing to know which one is active. New agent implementations (e.g. a
future Planner-backed agent) can be added at runtime via
`register_provider()` without modifying this class.
"""

from __future__ import annotations

from threading import Lock

from loguru import logger

from src.core.agent.agent_provider import (
    AgentConfigurationError,
    AgentFrameworkError,
    AgentProvider,
    DefaultAgentProvider,
)
from src.core.config import Config

__all__ = [
    "AgentManager",
    "AgentProviderRegistryError",
    "AgentProviderNotFoundError",
]

#: Valid values for 'agent.startup_mode'. "idle" leaves the selected
#: agent UNINITIALIZED until an explicit `agent initialize` call;
#: "auto" initializes it immediately once AgentEngine is constructed.
_VALID_STARTUP_MODES: frozenset[str] = frozenset({"idle", "auto"})


class AgentProviderRegistryError(AgentFrameworkError):
    """Raised for invalid catalog operations (e.g. duplicate agent name)."""


class AgentProviderNotFoundError(AgentFrameworkError):
    """Raised when an operation references an agent name not in the catalog."""


class AgentManager:
    """Owns the currently active agent, its enabled state, and startup mode.

    Responsibilities:
        - Build the built-in "jarvis" agent (`DefaultAgentProvider`).
        - Register an agent so it can later be selected.
        - Select and report the currently active agent.
        - List every registered agent.
        - Expose the resolved 'agent.startup_mode' ("idle"/"auto").
        - Disable the Agent Framework subsystem as a whole.
    """

    def __init__(self, config: Config) -> None:
        """Initialize the AgentManager and build its built-in agent.

        Args:
            config: Loaded application configuration. Read once, here,
                for 'agent.enabled', 'agent.default_agent' and
                'agent.startup_mode'.

        Raises:
            AgentConfigurationError: If any 'agent.*' value is present
                but malformed (wrong type, empty, out of range, or --
                for 'agent.default_agent' -- a name that does not
                match any registered agent, or -- for
                'agent.startup_mode' -- a value other than "idle" or
                "auto"). Configuration values are validated, never
                silently replaced with a default.
        """
        self._providers: dict[str, AgentProvider] = {}
        self._lock = Lock()
        self._enabled = self._validated_bool(config, "agent.enabled", True)
        self._startup_mode = self._validated_startup_mode(config)

        self.register_provider(DefaultAgentProvider())

        self._current_name: str | None = self._resolve_default_agent(config)

    def _resolve_default_agent(self, config: Config) -> str | None:
        """Validate and resolve 'agent.default_agent' against the catalog.

        Args:
            config: Loaded application configuration.

        Returns:
            The validated agent name to select as current, or None if
            'agent.default_agent' is explicitly "none"
            (case-insensitive).

        Raises:
            AgentConfigurationError: If the configured value is not a
                non-empty string, or does not match any registered
                agent name (and is not "none").
        """
        raw_value = config.get("agent.default_agent", "jarvis")
        if not isinstance(raw_value, str) or not raw_value.strip():
            raise AgentConfigurationError(
                "Invalid value for 'agent.default_agent': expected a non-empty "
                f'string naming an agent (or "none"), got {raw_value!r}.'
            )

        name = raw_value.strip()
        if name.lower() == "none":
            return None

        with self._lock:
            known_names = sorted(self._providers)
        if name not in known_names:
            available = ", ".join(known_names) if known_names else "none registered"
            raise AgentConfigurationError(
                f"Invalid 'agent.default_agent': '{name}' is not a registered "
                f"agent. Available agents: {available}."
            )
        return name

    def _validated_startup_mode(self, config: Config) -> str:
        """Validate 'agent.startup_mode' is one of the recognized values.

        Args:
            config: Loaded application configuration.

        Returns:
            The validated startup mode, "idle" or "auto".

        Raises:
            AgentConfigurationError: If 'agent.startup_mode' is present
                but is not "idle" or "auto".
        """
        raw_value = config.get("agent.startup_mode", "idle")
        if not isinstance(raw_value, str) or raw_value.strip().lower() not in _VALID_STARTUP_MODES:
            valid = ", ".join(sorted(_VALID_STARTUP_MODES))
            raise AgentConfigurationError(
                f"Invalid value for 'agent.startup_mode': expected one of "
                f"[{valid}], got {raw_value!r}."
            )
        return raw_value.strip().lower()

    # ---------- Provider lifecycle ----------

    def register_provider(self, provider: AgentProvider) -> None:
        """Register an agent so it can later be selected by `set_current()`.

        Args:
            provider: The AgentProvider to register.

        Raises:
            AgentProviderRegistryError: If an agent with the same name
                is already registered.
        """
        name = provider.agent_name()
        with self._lock:
            if name in self._providers:
                raise AgentProviderRegistryError(f"Agent already registered: '{name}'.")
            self._providers[name] = provider
        logger.info(f"Agent registered: '{name}'.")

    def get_provider(self, name: str) -> AgentProvider:
        """Return a single registered agent by name.

        Args:
            name: The agent's registered name.

        Returns:
            The matching AgentProvider.

        Raises:
            AgentProviderNotFoundError: If `name` is not registered.
        """
        with self._lock:
            provider = self._providers.get(name)
            known_names = sorted(self._providers)
        if provider is None:
            available = ", ".join(known_names) if known_names else "none registered"
            raise AgentProviderNotFoundError(f"Unknown agent: '{name}'. Available agents: {available}.")
        return provider

    def set_current(self, name: str) -> None:
        """Select the currently active agent.

        Takes effect immediately in memory; no restart is required and
        no configuration file is written.

        Args:
            name: The registered agent name to activate.

        Raises:
            AgentProviderNotFoundError: If `name` is not registered.
        """
        self.get_provider(name)  # raises AgentProviderNotFoundError if unknown
        with self._lock:
            self._current_name = name
        logger.info(f"Agent current selection set to '{name}'.")

    def get_current(self) -> AgentProvider | None:
        """Return the currently active agent.

        Returns:
            The active AgentProvider, or None if no agent is selected
            (including when the subsystem is disabled).
        """
        if not self.is_enabled():
            return None
        with self._lock:
            current_name = self._current_name
        if current_name is None:
            return None
        with self._lock:
            return self._providers.get(current_name)

    def list_providers(self) -> list[AgentProvider]:
        """Return every registered agent, ordered by name."""
        with self._lock:
            return sorted(self._providers.values(), key=lambda provider: provider.agent_name())

    def current_provider_name(self) -> str | None:
        """Return the currently selected agent's name, or None if unselected.

        Returns None whenever `is_enabled()` is False, keeping this
        method consistent with `get_current()`.
        """
        if not self.is_enabled():
            return None
        with self._lock:
            return self._current_name

    # ---------- Agent Framework subsystem enable/disable ----------

    def is_enabled(self) -> bool:
        """Return whether the Agent Framework subsystem is currently enabled."""
        with self._lock:
            return self._enabled

    def disable(self) -> None:
        """Disable the Agent Framework subsystem and clear the current agent selection."""
        with self._lock:
            self._enabled = False
            self._current_name = None
        logger.info("Agent Framework subsystem disabled.")

    # ---------- Startup mode ----------

    def startup_mode(self) -> str:
        """Return the resolved 'agent.startup_mode' ("idle" or "auto")."""
        return self._startup_mode

    # ---------- Configuration loading ----------

    @staticmethod
    def _validated_bool(config: Config, key_path: str, default: bool) -> bool:
        """Read `key_path` from `config`, validating it is a real boolean.

        Args:
            config: Loaded application configuration.
            key_path: Dotted configuration key (e.g. 'agent.enabled').
            default: Value to use if `key_path` is absent from configuration.

        Returns:
            The validated boolean value.

        Raises:
            AgentConfigurationError: If `key_path` is present but is
                not an actual boolean (e.g. a string like "true").
        """
        value = config.get(key_path, default)
        if not isinstance(value, bool):
            raise AgentConfigurationError(
                f"Invalid value for '{key_path}': expected true/false, got {value!r} "
                f"({type(value).__name__})."
            )
        return value
