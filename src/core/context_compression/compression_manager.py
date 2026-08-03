"""CompressionManager for EP-027 Context Compression.

CompressionManager is the single place that knows which compression
provider is currently active, and how the built-in "compression"
provider and the default limits ('context_compression.max_context_characters',
'context_compression.max_chunks', 'context_compression.deduplicate')
are resolved from 'context_compression.*' configuration (see
config/config.yaml) -- matching EP-026's `SemanticManager` split
between provider lifecycle (here) and pipeline orchestration
(`CompressionEngine`).

Keeps the current-provider choice and the current limits entirely in
memory, so `compression use <provider>` takes effect immediately -- no
restart required, and no write back to config/config.yaml (`Config`
exposes no write path; see `src/core/config.py`).

The rest of Jarvis is expected to depend only on `CompressionManager`
(via `CompressionEngine`/`CompressionService`), never on a concrete
`CompressionProvider` directly, so the active provider can change
without any other component needing to know which one is active. New
provider types can be added at runtime via `register_provider()`
without modifying this class.
"""

from __future__ import annotations

from threading import Lock

from loguru import logger

from src.core.config import Config
from src.core.context_compression.compression_provider import (
    CompressionConfigurationError,
    CompressionProvider,
    ContextCompressionError,
    DefaultCompressionProvider,
)

__all__ = [
    "CompressionManager",
    "CompressionProviderRegistryError",
    "CompressionProviderNotFoundError",
]

DEFAULT_MAX_CONTEXT_CHARACTERS: int = 12000
DEFAULT_MAX_CHUNKS: int = 20
DEFAULT_DEDUPLICATE: bool = True


class CompressionProviderRegistryError(ContextCompressionError):
    """Raised for invalid catalog operations (e.g. duplicate provider name)."""


class CompressionProviderNotFoundError(ContextCompressionError):
    """Raised when an operation references a provider name not in the catalog."""


class CompressionManager:
    """Owns the currently active compression provider, its enabled state and limits.

    Responsibilities:
        - Build the built-in "compression" provider (`DefaultCompressionProvider`).
        - Register a provider so it can later be selected.
        - Select and report the currently active provider.
        - List every registered provider.
        - Expose the default `max_context_characters` / `max_chunks` /
          `deduplicate` limits read from 'context_compression.*'
          configuration.
        - Disable the Context Compression subsystem as a whole.
    """

    def __init__(self, config: Config) -> None:
        """Initialize the CompressionManager and build its built-in provider.

        Args:
            config: Loaded application configuration. Read once, here,
                for 'context_compression.enabled',
                'context_compression.default_provider',
                'context_compression.max_context_characters',
                'context_compression.max_chunks' and
                'context_compression.deduplicate'.

        Raises:
            CompressionConfigurationError: If any
                'context_compression.*' value is present but malformed
                (wrong type, empty, out of range, or -- for
                'context_compression.default_provider' -- a name that
                does not match any registered provider). Configuration
                values are validated, never silently replaced with a
                default.
        """
        self._providers: dict[str, CompressionProvider] = {}
        self._lock = Lock()
        self._enabled = self._validated_bool(config, "context_compression.enabled", True)
        self._max_context_characters = self._validated_positive_int(
            config,
            "context_compression.max_context_characters",
            DEFAULT_MAX_CONTEXT_CHARACTERS,
        )
        self._max_chunks = self._validated_positive_int(
            config, "context_compression.max_chunks", DEFAULT_MAX_CHUNKS
        )
        self._deduplicate = self._validated_bool(
            config, "context_compression.deduplicate", DEFAULT_DEDUPLICATE
        )

        self.register_provider(DefaultCompressionProvider())

        self._current_name: str | None = self._resolve_default_provider(config)

    def _resolve_default_provider(self, config: Config) -> str | None:
        """Validate and resolve 'context_compression.default_provider' against the catalog.

        Args:
            config: Loaded application configuration.

        Returns:
            The validated provider name to select as current, or None
            if 'context_compression.default_provider' is explicitly
            "none" (case-insensitive).

        Raises:
            CompressionConfigurationError: If the configured value is
                not a non-empty string, or does not match any
                registered provider name (and is not "none").
        """
        raw_value = config.get("context_compression.default_provider", "compression")
        if not isinstance(raw_value, str) or not raw_value.strip():
            raise CompressionConfigurationError(
                "Invalid value for 'context_compression.default_provider': expected a "
                f"non-empty string naming a provider (or \"none\"), got {raw_value!r}."
            )

        name = raw_value.strip()
        if name.lower() == "none":
            return None

        with self._lock:
            known_names = sorted(self._providers)
        if name not in known_names:
            available = ", ".join(known_names) if known_names else "none registered"
            raise CompressionConfigurationError(
                f"Invalid 'context_compression.default_provider': '{name}' is not a "
                f"registered compression provider. Available providers: {available}."
            )
        return name

    # ---------- Provider lifecycle ----------

    def register_provider(self, provider: CompressionProvider) -> None:
        """Register a provider so it can later be selected by `set_current()`.

        Args:
            provider: The CompressionProvider to register.

        Raises:
            CompressionProviderRegistryError: If a provider with the
                same name is already registered.
        """
        name = provider.provider_name()
        with self._lock:
            if name in self._providers:
                raise CompressionProviderRegistryError(
                    f"Compression provider already registered: '{name}'."
                )
            self._providers[name] = provider
        logger.info(f"Compression provider registered: '{name}'.")

    def get_provider(self, name: str) -> CompressionProvider:
        """Return a single registered provider by name.

        Args:
            name: The provider's registered name.

        Returns:
            The matching CompressionProvider.

        Raises:
            CompressionProviderNotFoundError: If `name` is not registered.
        """
        with self._lock:
            provider = self._providers.get(name)
            known_names = sorted(self._providers)
        if provider is None:
            available = ", ".join(known_names) if known_names else "none registered"
            raise CompressionProviderNotFoundError(
                f"Unknown compression provider: '{name}'. Available providers: {available}."
            )
        return provider

    def set_current(self, name: str) -> None:
        """Select the currently active provider.

        Takes effect immediately in memory; no restart is required and
        no configuration file is written.

        Args:
            name: The registered provider name to activate.

        Raises:
            CompressionProviderNotFoundError: If `name` is not registered.
        """
        self.get_provider(name)  # raises CompressionProviderNotFoundError if unknown
        with self._lock:
            self._current_name = name
        logger.info(f"Compression current provider set to '{name}'.")

    def get_current(self) -> CompressionProvider | None:
        """Return the currently active provider.

        Returns:
            The active CompressionProvider, or None if no provider is
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

    def list_providers(self) -> list[CompressionProvider]:
        """Return every registered provider, ordered by name."""
        with self._lock:
            return sorted(self._providers.values(), key=lambda provider: provider.provider_name())

    def current_provider_name(self) -> str | None:
        """Return the currently selected provider's name, or None if unselected.

        Returns None whenever `is_enabled()` is False, regardless of
        whether the subsystem was disabled via `disable()` (which also
        clears the in-memory selection) or is disabled from the start
        via 'context_compression.enabled: false' in configuration
        (where a selection was still resolved internally at
        construction time, but must never be reported as "current"
        while disabled) -- keeping this method consistent with
        `get_current()`, which already applies the same rule.
        """
        if not self.is_enabled():
            return None
        with self._lock:
            return self._current_name

    # ---------- Context Compression subsystem enable/disable ----------

    def is_enabled(self) -> bool:
        """Return whether the Context Compression subsystem is currently enabled."""
        with self._lock:
            return self._enabled

    def disable(self) -> None:
        """Disable the Context Compression subsystem and clear the current provider selection."""
        with self._lock:
            self._enabled = False
            self._current_name = None
        logger.info("Context Compression subsystem disabled.")

    # ---------- Default limits ----------

    def max_context_characters(self) -> int:
        """Return the default maximum total character count for compressed context."""
        with self._lock:
            return self._max_context_characters

    def max_chunks(self) -> int:
        """Return the default maximum number of chunks a compressed result may contain."""
        with self._lock:
            return self._max_chunks

    def deduplicate(self) -> bool:
        """Return whether deduplication is applied by default."""
        with self._lock:
            return self._deduplicate

    def set_max_context_characters(self, value: int) -> None:
        """Set the default maximum total character count for compressed context.

        Takes effect immediately in memory; no restart is required and
        no configuration file is written.

        Args:
            value: The new default maximum, a positive integer.

        Raises:
            CompressionConfigurationError: If `value` is not a
                positive integer.
        """
        validated = self._validate_positive_int_value(value, "max_context_characters")
        with self._lock:
            self._max_context_characters = validated
        logger.info(f"Compression max_context_characters set to {validated}.")

    def set_max_chunks(self, value: int) -> None:
        """Set the default maximum number of chunks a compressed result may contain.

        Takes effect immediately in memory; no restart is required and
        no configuration file is written.

        Args:
            value: The new default maximum, a positive integer.

        Raises:
            CompressionConfigurationError: If `value` is not a
                positive integer.
        """
        validated = self._validate_positive_int_value(value, "max_chunks")
        with self._lock:
            self._max_chunks = validated
        logger.info(f"Compression max_chunks set to {validated}.")

    def set_deduplicate(self, value: bool) -> None:
        """Set whether deduplication is applied by default.

        Args:
            value: The new default.

        Raises:
            CompressionConfigurationError: If `value` is not an actual
                boolean.
        """
        if not isinstance(value, bool):
            raise CompressionConfigurationError(
                f"Invalid value for 'deduplicate': expected true/false, got {value!r} "
                f"({type(value).__name__})."
            )
        with self._lock:
            self._deduplicate = value
        logger.info(f"Compression deduplicate set to {value}.")

    # ---------- Configuration loading ----------

    @staticmethod
    def _validated_bool(config: Config, key_path: str, default: bool) -> bool:
        """Read `key_path` from `config`, validating it is a real boolean.

        Args:
            config: Loaded application configuration.
            key_path: Dotted configuration key (e.g.
                'context_compression.enabled').
            default: Value to use if `key_path` is absent from configuration.

        Returns:
            The validated boolean value.

        Raises:
            CompressionConfigurationError: If `key_path` is present but
                is not an actual boolean (e.g. a string like "true").
        """
        value = config.get(key_path, default)
        if not isinstance(value, bool):
            raise CompressionConfigurationError(
                f"Invalid value for '{key_path}': expected true/false, got {value!r} "
                f"({type(value).__name__})."
            )
        return value

    @classmethod
    def _validated_positive_int(cls, config: Config, key_path: str, default: int) -> int:
        """Read `key_path` from `config`, validating it is a positive integer.

        Args:
            config: Loaded application configuration.
            key_path: Dotted configuration key (e.g.
                'context_compression.max_chunks').
            default: Value to use if `key_path` is absent from configuration.

        Returns:
            The validated positive integer.

        Raises:
            CompressionConfigurationError: If `key_path` is present but
                is not a positive integer (e.g. a quoted string, a
                float, or zero/negative).
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
            CompressionConfigurationError: If `value` is not a
                positive integer.
        """
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise CompressionConfigurationError(
                f"Invalid value for '{key_path}': expected a positive integer, got "
                f"{value!r} ({type(value).__name__})."
            )
        return value
