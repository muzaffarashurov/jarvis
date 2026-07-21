"""Business logic that coordinates the AI Provider Manager (EP-014).

AIService is the entry point AIModule uses to inspect and control the
AI subsystem. It implements no provider-selection logic of its own --
that always lives in ProviderManager -- and no provider construction
(see ProviderFactory); it only translates ProviderManager state into
CLI-facing results, matching the pattern already used for the
Telegram Gateway (see src/services/telegram_service.py).

Per EP-014's "IMPORTANT" section, this service never performs network
requests, calls any AI API, or implements chat/streaming -- `doctor()`
and `providers()` diagnostics are derived entirely from configuration
and from each provider's own configuration-derived `health()`/
`is_available()` checks.
"""

from __future__ import annotations

from dataclasses import dataclass

from loguru import logger

from src.core.ai.provider_manager import ProviderManager
from src.core.ai.provider_registry import ProviderNotFoundError
from src.core.command_router import CommandResult
from src.core.config import Config

__all__ = ["AIDoctorReport", "AIService", "AIStatus", "ProviderInfo"]


@dataclass(frozen=True)
class AIStatus:
    """Result of `ai status` / `ai current`.

    Attributes:
        enabled: Whether the AI subsystem is currently enabled.
        current_provider: The active provider's name, or None if no
            provider is currently selected.
        registered_provider_count: Number of providers registered with
            the ProviderManager.
    """

    enabled: bool
    current_provider: str | None
    registered_provider_count: int


@dataclass(frozen=True)
class ProviderInfo:
    """A single row of `ai providers` output.

    Attributes:
        name: The provider's registered name (e.g. "ollama").
        enabled: Whether 'providers.<name>.enabled' is True.
        configured: Whether the provider has the configuration it
            needs to be usable (e.g. an API key or endpoint).
        available: Whether the provider is enabled and configured.
        is_current: Whether this provider is the active provider.
    """

    name: str
    enabled: bool
    configured: bool
    available: bool
    is_current: bool


@dataclass(frozen=True)
class AIDoctorReport:
    """Result of `ai doctor`'s diagnostic checks.

    Attributes:
        configuration_ok: Whether 'ai.enabled' and 'ai.default_provider'
            resolved to well-formed values in configuration.
        registry_ok: Whether the Provider Registry has at least one
            registered provider.
        current_provider_ok: Whether the currently selected provider
            (if any) is available. True when no provider is selected,
            since there is nothing to validate.
        connectivity_ok: Whether the currently selected provider's own
            configuration-derived `health()` check passed. True when
            no provider is selected. Never a network probe (EP-014).
        configuration_errors: Configuration problems found (e.g. an
            'ai.default_provider' that names an unregistered provider).
    """

    configuration_ok: bool
    registry_ok: bool
    current_provider_ok: bool
    connectivity_ok: bool
    configuration_errors: tuple[str, ...]

    @property
    def is_ready(self) -> bool:
        """Return True only if every diagnostic check passed."""
        return (
            self.configuration_ok
            and self.registry_ok
            and self.current_provider_ok
            and self.connectivity_ok
            and not self.configuration_errors
        )


class AIService:
    """Coordinates AI subsystem status, diagnostics, and provider selection.

    Depends only on ProviderManager (provider selection) and Config
    (its own 'ai.*' settings), matching EP-014's architecture.
    Implements no provider-specific or network logic of its own.
    """

    def __init__(self, config: Config, provider_manager: ProviderManager) -> None:
        """Initialize the AIService.

        Args:
            config: Loaded application configuration, used to resolve
                'ai.enabled' and 'ai.default_provider' for diagnostics.
            provider_manager: The ProviderManager used to select and
                inspect AI providers.
        """
        self._config = config
        self._provider_manager = provider_manager

    # ---------- Public API ----------

    def status(self) -> AIStatus:
        """Return the `ai status` / `ai current` snapshot."""
        current = self._provider_manager.get_current()
        return AIStatus(
            enabled=self._provider_manager.is_enabled(),
            current_provider=current.name() if current is not None else None,
            registered_provider_count=len(self._provider_manager.list_providers()),
        )

    def list_providers(self) -> list[ProviderInfo]:
        """Return `ai providers` catalog rows, ordered by provider name."""
        current = self._provider_manager.get_current()
        current_name = current.name() if current is not None else None

        rows: list[ProviderInfo] = []
        for provider in self._provider_manager.list_providers():
            config_snapshot = provider.configuration()
            rows.append(
                ProviderInfo(
                    name=provider.name(),
                    enabled=bool(config_snapshot.get("enabled", False)),
                    configured=bool(config_snapshot.get("configured", False)),
                    available=provider.is_available(),
                    is_current=provider.name() == current_name,
                )
            )
        return rows

    def use_provider(self, name: str) -> CommandResult:
        """Select `name` as the currently active AI provider.

        Args:
            name: The registered provider name to activate (e.g.
                "ollama").

        Returns:
            A CommandResult describing whether the provider was
            selected.
        """
        if not self._provider_manager.is_enabled():
            message = "AI subsystem is disabled. Enable 'ai.enabled' in config.yaml to use a provider."
            logger.error(f"AI use rejected: {message}")
            return CommandResult(success=False, message=message)

        try:
            self._provider_manager.set_current(name)
        except ProviderNotFoundError as exc:
            logger.error(f"AI use failed: {exc}")
            return CommandResult(success=False, message=str(exc))

        return CommandResult(success=True, message=f"AI provider set to '{name}'.")

    def disable(self) -> CommandResult:
        """Disable the AI subsystem and clear the current provider selection."""
        self._provider_manager.disable()
        return CommandResult(success=True, message="AI subsystem disabled.")

    def doctor(self) -> AIDoctorReport:
        """Run the `ai doctor` diagnostic checks."""
        configuration_errors: list[str] = []

        configuration_ok = isinstance(self._config.get("ai.enabled"), bool) and isinstance(
            self._config.get("ai.default_provider"), str
        )

        providers = self._provider_manager.list_providers()
        registry_ok = len(providers) > 0

        default_provider = self._config.get("ai.default_provider", "none")
        if (
            isinstance(default_provider, str)
            and default_provider.lower() != "none"
            and not any(provider.name() == default_provider for provider in providers)
        ):
            configuration_errors.append(
                f"'ai.default_provider' names an unregistered provider: '{default_provider}'."
            )

        current = self._provider_manager.get_current()
        current_provider_ok = current is None or current.is_available()
        connectivity_ok = current is None or current.health().available

        return AIDoctorReport(
            configuration_ok=configuration_ok,
            registry_ok=registry_ok,
            current_provider_ok=current_provider_ok,
            connectivity_ok=connectivity_ok,
            configuration_errors=tuple(configuration_errors),
        )
