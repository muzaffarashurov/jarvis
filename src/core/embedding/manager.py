"""EmbeddingManager for EP-021 Embedding Engine.

EmbeddingManager is the single place that knows which embedding
provider is currently active and how built-in providers are
constructed from 'embedding.*' configuration (see config/config.yaml),
matching EP-014's ProviderManager/ProviderRegistry/ProviderFactory
split -- combined here into one class since EP-021's task brief
assigns "selecting provider", "loading configuration" and "provider
lifecycle" to a single EmbeddingManager (no separate registry/factory
class was requested).

Keeps the current-provider choice entirely in memory so `embedding use
<provider>` takes effect immediately -- no restart required, and no
write back to config/config.yaml (Config exposes no write path; see
src/core/config.py).

The rest of Jarvis is expected to depend only on EmbeddingManager (via
EmbeddingEngine/EmbeddingService), never on a concrete EmbeddingProvider
directly, so the active provider can change without any other
component needing to know which one is active. New provider types can
be added at runtime via `register_provider()` without modifying this
class.
"""

from __future__ import annotations

from threading import Lock

from loguru import logger

from src.core.config import Config
from src.core.embedding.provider import (
    EmbeddingConfigurationError,
    EmbeddingError,
    EmbeddingProvider,
)
from src.core.embedding.providers.cloud_provider import CloudEmbeddingProvider
from src.core.embedding.providers.local_provider import LocalHashEmbeddingProvider


class EmbeddingProviderRegistryError(EmbeddingError):
    """Raised for invalid catalog operations (e.g. duplicate provider name)."""


class EmbeddingProviderNotFoundError(EmbeddingError):
    """Raised when an operation references a provider name not in the catalog."""


class EmbeddingManager:
    """Owns the currently active embedding provider and its enabled state.

    Responsibilities:
        - Build the known built-in providers ("local", "cloud") from
          'embedding.*' configuration.
        - Register a provider so it can later be selected.
        - Select and report the currently active provider.
        - List every registered provider.
        - Disable the Embedding subsystem as a whole.
    """

    def __init__(self, config: Config) -> None:
        """Initialize the EmbeddingManager and build its built-in providers.

        Args:
            config: Loaded application configuration. Read once, here,
                for 'embedding.enabled', 'embedding.default_provider'
                and every 'embedding.providers.<name>.*' built-in
                provider section.

        Raises:
            EmbeddingConfigurationError: If any 'embedding.*' value is
                present but malformed (wrong type, empty, or --
                for 'embedding.default_provider' -- a name that does
                not match any registered provider). Configuration
                values are validated, never silently replaced with a
                default.
        """
        self._providers: dict[str, EmbeddingProvider] = {}
        self._lock = Lock()
        self._enabled = self._validated_bool(config, "embedding.enabled", True)

        for provider in self._build_builtin_providers(config):
            self.register_provider(provider)

        self._current_name: str | None = self._resolve_default_provider(config)

    def _resolve_default_provider(self, config: Config) -> str | None:
        """Validate and resolve 'embedding.default_provider' against the built providers.

        Args:
            config: Loaded application configuration.

        Returns:
            The validated provider name to select as current, or None
            if 'embedding.default_provider' is explicitly "none"
            (case-insensitive).

        Raises:
            EmbeddingConfigurationError: If the configured value is not
                a non-empty string, or does not match any registered
                provider name (and is not "none").
        """
        raw_value = config.get("embedding.default_provider", "local")
        if not isinstance(raw_value, str) or not raw_value.strip():
            raise EmbeddingConfigurationError(
                "Invalid value for 'embedding.default_provider': expected a non-empty "
                f"string naming a provider (or \"none\"), got {raw_value!r}."
            )

        name = raw_value.strip()
        if name.lower() == "none":
            return None

        with self._lock:
            known_names = sorted(self._providers)
        if name not in known_names:
            available = ", ".join(known_names) if known_names else "none registered"
            raise EmbeddingConfigurationError(
                f"Invalid 'embedding.default_provider': '{name}' is not a registered "
                f"embedding provider. Available providers: {available}."
            )
        return name

    # ---------- Provider lifecycle ----------

    def register_provider(self, provider: EmbeddingProvider) -> None:
        """Register a provider so it can later be selected by `set_current()`.

        Args:
            provider: The EmbeddingProvider to register.

        Raises:
            EmbeddingProviderRegistryError: If a provider with the
                same name is already registered.
        """
        name = provider.provider_name()
        with self._lock:
            if name in self._providers:
                raise EmbeddingProviderRegistryError(
                    f"Embedding provider already registered: '{name}'."
                )
            self._providers[name] = provider
        logger.info(f"Embedding provider registered: '{name}'.")

    def get_provider(self, name: str) -> EmbeddingProvider:
        """Return a single registered provider by name.

        Args:
            name: The provider's registered name.

        Returns:
            The matching EmbeddingProvider.

        Raises:
            EmbeddingProviderNotFoundError: If `name` is not registered.
        """
        with self._lock:
            provider = self._providers.get(name)
            known_names = sorted(self._providers)
        if provider is None:
            available = ", ".join(known_names) if known_names else "none registered"
            raise EmbeddingProviderNotFoundError(
                f"Unknown embedding provider: '{name}'. Available providers: {available}."
            )
        return provider

    def set_current(self, name: str) -> None:
        """Select the currently active provider.

        Takes effect immediately in memory; no restart is required and
        no configuration file is written.

        Args:
            name: The registered provider name to activate.

        Raises:
            EmbeddingProviderNotFoundError: If `name` is not registered.
        """
        self.get_provider(name)  # raises EmbeddingProviderNotFoundError if unknown
        with self._lock:
            self._current_name = name
        logger.info(f"Embedding current provider set to '{name}'.")

    def get_current(self) -> EmbeddingProvider | None:
        """Return the currently active provider.

        Returns:
            The active EmbeddingProvider, or None if no provider is
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

    def list_providers(self) -> list[EmbeddingProvider]:
        """Return every registered provider, ordered by name."""
        with self._lock:
            return sorted(self._providers.values(), key=lambda provider: provider.provider_name())

    def current_provider_name(self) -> str | None:
        """Return the currently selected provider's name, or None if unselected."""
        with self._lock:
            return self._current_name

    # ---------- Embedding subsystem enable/disable ----------

    def is_enabled(self) -> bool:
        """Return whether the Embedding subsystem is currently enabled."""
        with self._lock:
            return self._enabled

    def disable(self) -> None:
        """Disable the Embedding subsystem and clear the current provider selection."""
        with self._lock:
            self._enabled = False
            self._current_name = None
        logger.info("Embedding subsystem disabled.")

    # ---------- Configuration loading ----------

    @staticmethod
    def _build_builtin_providers(config: Config) -> list[EmbeddingProvider]:
        """Build every built-in provider from 'embedding.providers.*' configuration.

        Args:
            config: Loaded application configuration.

        Returns:
            A LocalHashEmbeddingProvider and a CloudEmbeddingProvider,
            reflecting 'embedding.providers.local.*' and
            'embedding.providers.cloud.*' respectively.
        """
        return [
            EmbeddingManager._build_local(config),
            EmbeddingManager._build_cloud(config),
        ]

    @staticmethod
    def _build_local(config: Config) -> EmbeddingProvider:
        """Build the built-in local provider from 'embedding.providers.local' configuration.

        Raises:
            EmbeddingConfigurationError: If 'enabled', 'model', or
                'dimension' is present but malformed.
        """
        enabled = EmbeddingManager._validated_bool(
            config, "embedding.providers.local.enabled", True
        )
        model = EmbeddingManager._validated_model(
            config, "embedding.providers.local.model", "local-hash-v1"
        )
        dimension = EmbeddingManager._validated_dimension(
            config, "embedding.providers.local.dimension", 256
        )
        return LocalHashEmbeddingProvider(enabled=enabled, model=model, dimension=dimension)

    @staticmethod
    def _build_cloud(config: Config) -> EmbeddingProvider:
        """Build the built-in cloud provider from 'embedding.providers.cloud' configuration.

        Raises:
            EmbeddingConfigurationError: If 'enabled', 'api_key',
                'model', or 'dimension' is present but malformed.
        """
        enabled = EmbeddingManager._validated_bool(
            config, "embedding.providers.cloud.enabled", False
        )
        api_key = EmbeddingManager._validated_api_key(config, "embedding.providers.cloud.api_key")
        model = EmbeddingManager._validated_model(
            config, "embedding.providers.cloud.model", "text-embedding-cloud-v1"
        )
        dimension = EmbeddingManager._validated_dimension(
            config, "embedding.providers.cloud.dimension", 1536
        )
        return CloudEmbeddingProvider(
            enabled=enabled, api_key=api_key, model=model, dimension=dimension
        )

    @staticmethod
    def _validated_bool(config: Config, key_path: str, default: bool) -> bool:
        """Read `key_path` from `config`, validating it is a real boolean.

        Args:
            config: Loaded application configuration.
            key_path: Dotted configuration key (e.g. 'embedding.enabled').
            default: Value to use if `key_path` is absent from configuration.

        Returns:
            The validated boolean value.

        Raises:
            EmbeddingConfigurationError: If `key_path` is present but
                is not an actual boolean (e.g. a string like "true").
        """
        value = config.get(key_path, default)
        if not isinstance(value, bool):
            raise EmbeddingConfigurationError(
                f"Invalid value for '{key_path}': expected true/false, got {value!r} "
                f"({type(value).__name__})."
            )
        return value

    @staticmethod
    def _validated_model(config: Config, key_path: str, default: str) -> str:
        """Read `key_path` from `config`, validating it is a non-empty string.

        Args:
            config: Loaded application configuration.
            key_path: Dotted configuration key (e.g. 'embedding.providers.local.model').
            default: Value to use if `key_path` is absent from configuration.

        Returns:
            The validated, stripped model identifier.

        Raises:
            EmbeddingConfigurationError: If `key_path` is present but
                is not a non-empty string.
        """
        value = config.get(key_path, default)
        if not isinstance(value, str) or not value.strip():
            raise EmbeddingConfigurationError(
                f"Invalid value for '{key_path}': expected a non-empty string, got "
                f"{value!r} ({type(value).__name__})."
            )
        return value.strip()

    @staticmethod
    def _validated_api_key(config: Config, key_path: str) -> str:
        """Read `key_path` from `config`, validating it is a string (possibly empty).

        An empty string is valid here and means "not configured" --
        only the type is validated, matching CloudEmbeddingProvider's
        own configured/not-configured distinction.

        Args:
            config: Loaded application configuration.
            key_path: Dotted configuration key (e.g.
                'embedding.providers.cloud.api_key').

        Returns:
            The validated API key string (may be empty).

        Raises:
            EmbeddingConfigurationError: If `key_path` is present but
                is not a string at all (e.g. a number or boolean).
        """
        value = config.get(key_path, "")
        if not isinstance(value, str):
            raise EmbeddingConfigurationError(
                f"Invalid value for '{key_path}': expected a string, got {value!r} "
                f"({type(value).__name__})."
            )
        return value

    @staticmethod
    def _validated_dimension(config: Config, key_path: str, default: int) -> int:
        """Read `key_path` from `config`, validating it is a positive integer.

        Args:
            config: Loaded application configuration.
            key_path: Dotted configuration key (e.g.
                'embedding.providers.local.dimension').
            default: Value to use if `key_path` is absent from configuration.

        Returns:
            The validated positive integer dimension.

        Raises:
            EmbeddingConfigurationError: If `key_path` is present but
                is not a positive integer (e.g. a quoted string like
                "512", a float, or zero/negative).
        """
        value = config.get(key_path, default)
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise EmbeddingConfigurationError(
                f"Invalid value for '{key_path}': expected a positive integer, got "
                f"{value!r} ({type(value).__name__})."
            )
        return value
