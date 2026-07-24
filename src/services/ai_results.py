"""Plain-data result types returned by AIService (EP-014/EP-015).

Extracted out of `src/services/ai_service.py` purely to keep that file
under AI_GENERATION_STANDARD.md's 500-line hard file-size limit --
EP-018 pushed it over after four EPs' (014/015/016/017/018) worth of
accumulated docstrings. No behavior, naming, or public import path
changed: `ai_service.py` re-exports every name here (see its `__all__`),
so existing imports like `from src.services.ai_service import AskResult`
(e.g. `src/modules/ai_module.py`) continue to work unmodified.

These are pure data containers -- no logic, no dependency on any AI
provider, ProviderManager, or Config. AIService is solely responsible
for populating them.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.core.ai.provider import ModelValidationResult

__all__ = [
    "AIDoctorReport",
    "AIStatus",
    "AskResult",
    "ModelsResult",
    "PingReport",
    "ProviderInfo",
    "ProviderSelectionResult",
]


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
        authenticated: Whether the configured credentials were accepted.
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
        success: Whether `name` was selected as the current provider. False if
            the AI subsystem is disabled or `name` is not a registered
            provider; `validation` is always None in that case, since no
            provider was selected to validate.
        provider: The provider name that was requested.
        message: A short, human-friendly status line -- the selection error on
            failure, or "AI provider set to '<name>'." on success.
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
        configuration_ok: Whether 'ai.enabled' and 'ai.default_provider' resolved
            to well-formed values in configuration.
        registry_ok: Whether the Provider Registry has at least one registered
            provider.
        current_provider_ok: Whether the currently selected provider (if any) is
            available. True when no provider is selected, since there is
            nothing to validate.
        connectivity_ok: Whether the currently selected provider's own
            configuration-derived `health()` check passed. True when no
            provider is selected. Never a network probe (EP-014).
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
