"""SemanticManager for EP-026 Semantic Search.

SemanticManager is the single place that knows which semantic search
provider is currently active, and how the built-in "semantic" provider
and the default search parameters ('semantic.top_k',
'semantic.similarity_threshold') are resolved from 'semantic.*'
configuration (see config/config.yaml) -- matching EP-021's
`EmbeddingManager` split between provider lifecycle (here) and
pipeline orchestration (`SemanticEngine`).

Keeps the current-provider choice and the current threshold entirely
in memory, so `semantic use <provider>` takes effect immediately -- no
restart required, and no write back to config/config.yaml (`Config`
exposes no write path; see `src/core/config.py`).

The rest of Jarvis is expected to depend only on `SemanticManager` (via
`SemanticEngine`/`SemanticService`), never on a concrete
`SemanticProvider` directly, so the active provider can change without
any other component needing to know which one is active. New provider
types can be added at runtime via `register_provider()` without
modifying this class.
"""

from __future__ import annotations

from threading import Lock

from loguru import logger

from src.core.config import Config
from src.core.semantic.semantic_provider import (
    DefaultSemanticProvider,
    SemanticConfigurationError,
    SemanticError,
    SemanticProvider,
)

__all__ = [
    "SemanticManager",
    "SemanticProviderRegistryError",
    "SemanticProviderNotFoundError",
]

DEFAULT_TOP_K: int = 5
DEFAULT_SIMILARITY_THRESHOLD: float = 0.70


class SemanticProviderRegistryError(SemanticError):
    """Raised for invalid catalog operations (e.g. duplicate provider name)."""


class SemanticProviderNotFoundError(SemanticError):
    """Raised when an operation references a provider name not in the catalog."""


class SemanticManager:
    """Owns the currently active semantic provider, its enabled state and defaults.

    Responsibilities:
        - Build the built-in "semantic" provider (`DefaultSemanticProvider`).
        - Register a provider so it can later be selected.
        - Select and report the currently active provider.
        - List every registered provider.
        - Expose the default `top_k` / `similarity_threshold` search
          parameters read from 'semantic.*' configuration.
        - Disable the Semantic Search subsystem as a whole.
    """

    def __init__(self, config: Config) -> None:
        """Initialize the SemanticManager and build its built-in provider.

        Args:
            config: Loaded application configuration. Read once, here,
                for 'semantic.enabled', 'semantic.default_provider',
                'semantic.top_k' and 'semantic.similarity_threshold'.

        Raises:
            SemanticConfigurationError: If any 'semantic.*' value is
                present but malformed (wrong type, empty, out of
                range, or -- for 'semantic.default_provider' -- a name
                that does not match any registered provider).
                Configuration values are validated, never silently
                replaced with a default.
        """
        self._providers: dict[str, SemanticProvider] = {}
        self._lock = Lock()
        self._enabled = self._validated_bool(config, "semantic.enabled", True)
        self._top_k = self._validated_positive_int(config, "semantic.top_k", DEFAULT_TOP_K)
        self._similarity_threshold = self._validated_threshold(
            config, "semantic.similarity_threshold", DEFAULT_SIMILARITY_THRESHOLD
        )

        self.register_provider(DefaultSemanticProvider())

        self._current_name: str | None = self._resolve_default_provider(config)

    def _resolve_default_provider(self, config: Config) -> str | None:
        """Validate and resolve 'semantic.default_provider' against the registered providers.

        Args:
            config: Loaded application configuration.

        Returns:
            The validated provider name to select as current, or None
            if 'semantic.default_provider' is explicitly "none"
            (case-insensitive).

        Raises:
            SemanticConfigurationError: If the configured value is not
                a non-empty string, or does not match any registered
                provider name (and is not "none").
        """
        raw_value = config.get("semantic.default_provider", "semantic")
        if not isinstance(raw_value, str) or not raw_value.strip():
            raise SemanticConfigurationError(
                "Invalid value for 'semantic.default_provider': expected a non-empty "
                f"string naming a provider (or \"none\"), got {raw_value!r}."
            )

        name = raw_value.strip()
        if name.lower() == "none":
            return None

        with self._lock:
            known_names = sorted(self._providers)
        if name not in known_names:
            available = ", ".join(known_names) if known_names else "none registered"
            raise SemanticConfigurationError(
                f"Invalid 'semantic.default_provider': '{name}' is not a registered "
                f"semantic provider. Available providers: {available}."
            )
        return name

    # ---------- Provider lifecycle ----------

    def register_provider(self, provider: SemanticProvider) -> None:
        """Register a provider so it can later be selected by `set_current()`.

        Args:
            provider: The SemanticProvider to register.

        Raises:
            SemanticProviderRegistryError: If a provider with the same
                name is already registered.
        """
        name = provider.provider_name()
        with self._lock:
            if name in self._providers:
                raise SemanticProviderRegistryError(
                    f"Semantic provider already registered: '{name}'."
                )
            self._providers[name] = provider
        logger.info(f"Semantic provider registered: '{name}'.")

    def get_provider(self, name: str) -> SemanticProvider:
        """Return a single registered provider by name.

        Args:
            name: The provider's registered name.

        Returns:
            The matching SemanticProvider.

        Raises:
            SemanticProviderNotFoundError: If `name` is not registered.
        """
        with self._lock:
            provider = self._providers.get(name)
            known_names = sorted(self._providers)
        if provider is None:
            available = ", ".join(known_names) if known_names else "none registered"
            raise SemanticProviderNotFoundError(
                f"Unknown semantic provider: '{name}'. Available providers: {available}."
            )
        return provider

    def set_current(self, name: str) -> None:
        """Select the currently active provider.

        Takes effect immediately in memory; no restart is required and
        no configuration file is written.

        Args:
            name: The registered provider name to activate.

        Raises:
            SemanticProviderNotFoundError: If `name` is not registered.
        """
        self.get_provider(name)  # raises SemanticProviderNotFoundError if unknown
        with self._lock:
            self._current_name = name
        logger.info(f"Semantic current provider set to '{name}'.")

    def get_current(self) -> SemanticProvider | None:
        """Return the currently active provider.

        Returns:
            The active SemanticProvider, or None if no provider is
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

    def list_providers(self) -> list[SemanticProvider]:
        """Return every registered provider, ordered by name."""
        with self._lock:
            return sorted(self._providers.values(), key=lambda provider: provider.provider_name())

    def current_provider_name(self) -> str | None:
        """Return the currently selected provider's name, or None if unselected.

        Returns None whenever `is_enabled()` is False, regardless of
        whether the subsystem was disabled via `disable()` (which also
        clears the in-memory selection) or is disabled from the start
        via 'semantic.enabled: false' in configuration (where a
        selection was still resolved internally at construction time,
        but must never be reported as "current" while disabled) --
        keeping this method consistent with `get_current()`, which
        already applies the same rule.
        """
        if not self.is_enabled():
            return None
        with self._lock:
            return self._current_name

    # ---------- Semantic Search subsystem enable/disable ----------

    def is_enabled(self) -> bool:
        """Return whether the Semantic Search subsystem is currently enabled."""
        with self._lock:
            return self._enabled

    def disable(self) -> None:
        """Disable the Semantic Search subsystem and clear the current provider selection."""
        with self._lock:
            self._enabled = False
            self._current_name = None
        logger.info("Semantic Search subsystem disabled.")

    # ---------- Default search parameters ----------

    def top_k(self) -> int:
        """Return the default maximum number of results per search."""
        with self._lock:
            return self._top_k

    def similarity_threshold(self) -> float:
        """Return the default minimum similarity score a result must reach."""
        with self._lock:
            return self._similarity_threshold

    def set_similarity_threshold(self, value: float) -> None:
        """Set the default minimum similarity score a result must reach.

        Takes effect immediately in memory; no restart is required and
        no configuration file is written.

        Args:
            value: The new default threshold.

        Raises:
            SemanticConfigurationError: If `value` is not a real
                number in the inclusive range [0.0, 1.0].
        """
        validated = self._validate_threshold_value(value, "similarity_threshold")
        with self._lock:
            self._similarity_threshold = validated
        logger.info(f"Semantic similarity threshold set to {validated}.")

    # ---------- Configuration loading ----------

    @staticmethod
    def _validated_bool(config: Config, key_path: str, default: bool) -> bool:
        """Read `key_path` from `config`, validating it is a real boolean.

        Args:
            config: Loaded application configuration.
            key_path: Dotted configuration key (e.g. 'semantic.enabled').
            default: Value to use if `key_path` is absent from configuration.

        Returns:
            The validated boolean value.

        Raises:
            SemanticConfigurationError: If `key_path` is present but is
                not an actual boolean (e.g. a string like "true").
        """
        value = config.get(key_path, default)
        if not isinstance(value, bool):
            raise SemanticConfigurationError(
                f"Invalid value for '{key_path}': expected true/false, got {value!r} "
                f"({type(value).__name__})."
            )
        return value

    @staticmethod
    def _validated_positive_int(config: Config, key_path: str, default: int) -> int:
        """Read `key_path` from `config`, validating it is a positive integer.

        Args:
            config: Loaded application configuration.
            key_path: Dotted configuration key (e.g. 'semantic.top_k').
            default: Value to use if `key_path` is absent from configuration.

        Returns:
            The validated positive integer.

        Raises:
            SemanticConfigurationError: If `key_path` is present but is
                not a positive integer (e.g. a quoted string, a float,
                or zero/negative).
        """
        value = config.get(key_path, default)
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise SemanticConfigurationError(
                f"Invalid value for '{key_path}': expected a positive integer, got "
                f"{value!r} ({type(value).__name__})."
            )
        return value

    @classmethod
    def _validated_threshold(cls, config: Config, key_path: str, default: float) -> float:
        """Read `key_path` from `config`, validating it is a number in [0.0, 1.0].

        Args:
            config: Loaded application configuration.
            key_path: Dotted configuration key (e.g.
                'semantic.similarity_threshold').
            default: Value to use if `key_path` is absent from configuration.

        Returns:
            The validated threshold, as a float.

        Raises:
            SemanticConfigurationError: If `key_path` is present but is
                not a real number in the inclusive range [0.0, 1.0].
        """
        value = config.get(key_path, default)
        return cls._validate_threshold_value(value, key_path)

    @staticmethod
    def _validate_threshold_value(value: object, key_path: str) -> float:
        """Validate that `value` is a real number in the inclusive range [0.0, 1.0].

        Args:
            value: The candidate threshold value.
            key_path: Dotted configuration key (or field name) used in
                error messages.

        Returns:
            `value` as a float.

        Raises:
            SemanticConfigurationError: If `value` is not a real number
                in the inclusive range [0.0, 1.0].
        """
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise SemanticConfigurationError(
                f"Invalid value for '{key_path}': expected a number between 0.0 and "
                f"1.0, got {value!r} ({type(value).__name__})."
            )
        if not 0.0 <= float(value) <= 1.0:
            raise SemanticConfigurationError(
                f"Invalid value for '{key_path}': expected a number between 0.0 and "
                f"1.0, got {value!r}."
            )
        return float(value)
