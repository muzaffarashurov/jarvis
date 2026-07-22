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

from src.core.ai.provider import ModelValidationResult, ProviderError
from src.core.ai.provider_manager import ProviderManager
from src.core.ai.provider_registry import ProviderNotFoundError
from src.core.command_router import CommandResult
from src.core.config import Config

__all__ = [
    "AIDoctorReport",
    "AIService",
    "AIStatus",
    "AskResult",
    "ModelsResult",
    "PingReport",
    "ProviderInfo",
    "ProviderSelectionResult",
]

_NO_PROVIDER_SELECTED: str = "No AI provider is currently selected. Use 'ai use <provider>'."


@dataclass(frozen=True)
class AskResult:
    """Result of `ai ask <prompt>` / `ai test` (EP-015).

    Attributes:
        success: Whether communication with the provider succeeded.
        provider: The provider name queried (e.g. "claude"), or "" if
            no provider was selected.
        model: The model that produced the reply, or "" on failure.
        text: The reply text, or "" on failure.
        error: A user-friendly error message, or "" on success.
    """

    success: bool
    provider: str
    model: str
    text: str
    error: str


@dataclass(frozen=True)
class PingReport:
    """Result of `ai ping` (EP-015).

    Attributes:
        provider: The provider name checked, or "" if none selected.
        reachable: Whether the provider's API could be reached.
        latency_ms: Round-trip time for the check, in milliseconds.
        model: The model identifier used for the check.
        authenticated: Whether the configured credentials were
            accepted.
        message: Human-readable detail, especially on failure.
    """

    provider: str
    reachable: bool
    latency_ms: float
    model: str
    authenticated: bool
    message: str


@dataclass(frozen=True)
class ModelsResult:
    """Result of `ai models` (EP-015).

    Attributes:
        provider: The provider name queried, or "" if none selected.
        models: The models available from this provider's own
            configuration (never discovered online).
        error: A user-friendly error message, or "" on success.
    """

    provider: str
    models: tuple[str, ...]
    error: str


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
class ProviderSelectionResult:
    """Result of `ai use <provider>` (EP-015.3).

    Attributes:
        success: Whether `name` was selected as the current provider.
            False if the AI subsystem is disabled or `name` is not a
            registered provider; `validation` is always None in that
            case, since no provider was selected to validate.
        provider: The provider name that was requested.
        message: A short, human-friendly status line -- the selection
            error on failure, or "AI provider set to '<name>'." on
            success.
        validation: The result of calling `provider.validate_configured_model()`
            immediately after selection, or None if selection failed.
    """

    success: bool
    provider: str
    message: str
    validation: ModelValidationResult | None


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

    def use_provider(self, name: str) -> ProviderSelectionResult:
        """Select `name` as the currently active AI provider.

        Immediately after selection, this calls
        `provider.validate_configured_model()` (EP-015.3) so a
        misconfigured model (e.g. a typo in 'providers.gemini.model')
        is reported right away instead of only surfacing on the next
        `ask()`/`ping()`. Every provider supports this call: providers
        that can verify their model against a live model list (e.g.
        GeminiProvider) override it with a real check; every other
        provider falls back to `AIProvider`'s configuration-derived
        default (see src/core/ai/provider.py) -- so existing providers
        (OpenAI, Claude, Ollama, LM Studio) work unmodified. Never
        raises: `validate_configured_model()` maps every failure into
        `ModelValidationResult`, never a raw provider exception.

        Args:
            name: The registered provider name to activate (e.g.
                "ollama").

        Returns:
            A ProviderSelectionResult describing whether `name` was
            selected and, on success, the model validation outcome.
        """
        if not self._provider_manager.is_enabled():
            message = "AI subsystem is disabled. Enable 'ai.enabled' in config.yaml to use a provider."
            logger.error(f"AI use rejected: {message}")
            return ProviderSelectionResult(success=False, provider=name, message=message, validation=None)

        logger.info(f"Provider selected: '{name}'.")
        try:
            self._provider_manager.set_current(name)
        except ProviderNotFoundError as exc:
            logger.error(f"AI use failed: {exc}")
            return ProviderSelectionResult(success=False, provider=name, message=str(exc), validation=None)

        logger.info(f"Current provider changed: '{name}'.")

        provider = self._provider_manager.get_current()
        validation: ModelValidationResult | None = None
        if provider is not None:
            logger.info(f"Model validation started (provider='{name}').")
            validation = provider.validate_configured_model()
            if validation.valid:
                logger.info(
                    f"Model validation passed (provider='{name}', "
                    f"model='{validation.configured_model}')."
                )
            else:
                logger.warning(
                    f"Model validation failed (provider='{name}', "
                    f"model='{validation.configured_model}'): {validation.message}"
                )

        return ProviderSelectionResult(
            success=True,
            provider=name,
            message=f"AI provider set to '{name}'.",
            validation=validation,
        )

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

    # ---------- EP-015: real communication ----------

    def ask(self, prompt: str) -> AskResult:
        """Send `prompt` to the currently active provider and return its reply.

        Each call is independent -- no conversation history is kept
        or sent (EP-015: memory integration is left to a future EP).

        Args:
            prompt: The user prompt to send.

        Returns:
            An AskResult describing the reply, or a user-friendly
            error if communication failed.
        """
        current = self._provider_manager.get_current()
        if current is None:
            return AskResult(success=False, provider="", model="", text="", error=_NO_PROVIDER_SELECTED)

        if not self._provider_manager.is_enabled():
            message = "AI subsystem is disabled. Enable 'ai.enabled' in config.yaml to use a provider."
            return AskResult(success=False, provider=current.name(), model="", text="", error=message)

        name = current.name()
        try:
            response = current.ask(prompt)
        except ProviderError as exc:
            logger.error(f"AI request failed (provider='{name}'): {exc}")
            return AskResult(success=False, provider=name, model="", text="", error=str(exc))

        return AskResult(success=True, provider=name, model=response.model, text=response.text, error="")

    def test(self) -> AskResult:
        """Send a fixed "Hello" prompt to verify successful communication.

        Returns:
            The same AskResult shape as `ask()`.
        """
        return self.ask("Hello")

    def ping(self) -> PingReport:
        """Check reachability, latency, model and authentication for the active provider.

        Returns:
            A PingReport describing the connectivity check.
        """
        current = self._provider_manager.get_current()
        if current is None:
            return PingReport(
                provider="",
                reachable=False,
                latency_ms=0.0,
                model="",
                authenticated=False,
                message=_NO_PROVIDER_SELECTED,
            )

        result = current.ping()
        logger.info(
            f"AI ping (provider='{current.name()}', reachable={result.reachable}, "
            f"latency={result.latency_ms:.0f}ms)."
        )
        return PingReport(
            provider=current.name(),
            reachable=result.reachable,
            latency_ms=result.latency_ms,
            model=result.model,
            authenticated=result.authenticated,
            message=result.message,
        )

    def models(self) -> ModelsResult:
        """List the models available from the active provider's own configuration.

        Never performs online discovery (EP-015).

        Returns:
            A ModelsResult describing the available models.
        """
        current = self._provider_manager.get_current()
        if current is None:
            return ModelsResult(provider="", models=(), error=_NO_PROVIDER_SELECTED)

        return ModelsResult(provider=current.name(), models=tuple(current.list_models()), error="")
