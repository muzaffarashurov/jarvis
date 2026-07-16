"""Configuration loading for Jarvis."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from loguru import logger


class ConfigError(Exception):
    """Raised when the application configuration cannot be loaded or parsed."""


class Config:
    """Loads and provides typed access to application configuration.

    Responsibilities:
        - Load YAML configuration from disk.
        - Validate that the configuration file exists and is well-formed.
        - Provide safe, dotted-path access to nested configuration values.
    """

    def __init__(self, config_path: Path) -> None:
        """Initialize the Config loader.

        Args:
            config_path: Path to the YAML configuration file.
        """
        self._config_path = config_path
        self._data: dict[str, Any] = {}

    def load(self) -> "Config":
        """Load configuration from the YAML file on disk.

        Returns:
            This Config instance, to allow method chaining.

        Raises:
            ConfigError: If the file does not exist, cannot be read,
                contains invalid YAML, or does not resolve to a mapping.
        """
        if not self._config_path.exists():
            raise ConfigError(
                f"Configuration file not found at '{self._config_path}'. "
                "Please ensure 'config/config.yaml' exists before starting Jarvis."
            )

        try:
            with self._config_path.open("r", encoding="utf-8") as file:
                loaded = yaml.safe_load(file)
        except yaml.YAMLError as exc:
            raise ConfigError(
                f"Configuration file '{self._config_path}' contains invalid YAML: {exc}"
            ) from exc
        except OSError as exc:
            raise ConfigError(
                f"Unable to read configuration file '{self._config_path}': {exc}"
            ) from exc

        if not isinstance(loaded, dict):
            raise ConfigError(
                f"Configuration file '{self._config_path}' must contain a top-level "
                "YAML mapping (key: value pairs)."
            )

        self._data = loaded
        logger.debug(f"Configuration loaded from '{self._config_path}'")
        return self

    def get(self, key: str, default: Any = None) -> Any:
        """Retrieve a configuration value using a dot-separated key path.

        Args:
            key: Dot-separated key path (e.g. "app.name" or "logging.level").
            default: Value returned if the key path is not found.

        Returns:
            The resolved configuration value, or `default` if not found.
        """
        parts = key.split(".")
        value: Any = self._data
        for part in parts:
            if isinstance(value, dict) and part in value:
                value = value[part]
            else:
                return default
        return value

    @property
    def data(self) -> dict[str, Any]:
        """Return the full configuration mapping.

        Returns:
            The loaded configuration as a dictionary. Empty if `load()`
            has not yet been called successfully.
        """
        return self._data

    @property
    def config_path(self) -> Path:
        """Return the path this Config instance loads from.

        Returns:
            The configuration file path.
        """
        return self._config_path
