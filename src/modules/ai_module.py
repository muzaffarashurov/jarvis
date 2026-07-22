"""AI module: CLI command surface for EP-014 AI Provider Manager.

Exposes the "ai" command namespace (status, doctor, providers, current,
use, disable, help) as thin CommandModule handlers, following the same
pattern as TelegramModule/PluginModule. All orchestration logic lives
in AIService; this module only formats CommandResult objects for the
shell and owns the provider display names shown in `ai providers`
(presentation only, per this project's "Module - CLI only" rule).
"""

from __future__ import annotations

from typing import Callable

from src.core.command_router import CommandResult
from src.services.ai_service import (
    AIDoctorReport,
    AIService,
    AIStatus,
    AskResult,
    ModelsResult,
    PingReport,
    ProviderInfo,
    ProviderSelectionResult,
)

HELP_TEXT: str = (
    "Available commands\n\n"
    "ai status\n"
    "ai doctor\n"
    "ai providers\n"
    "ai current\n"
    "ai use <provider>\n"
    "ai disable\n"
    "ai ask <prompt>\n"
    "ai ping\n"
    "ai models\n"
    "ai test\n"
    "ai help"
)

# Display names for known provider identifiers (EP-014). Purely
# cosmetic: `ai use <provider>` and the Provider Registry always key
# providers by their lowercase identifier (e.g. "lmstudio").
_DISPLAY_NAMES: dict[str, str] = {
    "claude": "Claude",
    "gemini": "Gemini",
    "openai": "OpenAI",
    "ollama": "Ollama",
    "lmstudio": "LM Studio",
}

ActionHandler = Callable[[list[str]], CommandResult]


class AIModule:
    """Built-in "ai" command namespace for the AI Provider Manager."""

    def __init__(self, ai_service: AIService) -> None:
        """Initialize the AIModule.

        Args:
            ai_service: The service used to inspect and control the AI
                subsystem and its registered providers.
        """
        self._service = ai_service
        self._actions: dict[str, ActionHandler] = {
            "status": self._status,
            "doctor": self._doctor,
            "providers": self._providers,
            "current": self._current,
            "use": self._use,
            "disable": self._disable,
            "ask": self._ask,
            "ping": self._ping,
            "models": self._models,
            "test": self._test,
            "help": self._help,
        }

    @property
    def name(self) -> str:
        """Return this module's command namespace: "ai"."""
        return "ai"

    def execute(self, action: str, arguments: list[str]) -> CommandResult:
        """Execute an "ai" action.

        Args:
            action: The requested action (e.g. "status").
            arguments: Additional arguments (e.g. a provider name).

        Returns:
            A CommandResult describing the outcome.
        """
        handler = self._actions.get(action)
        if handler is None:
            command = f"{self.name} {action}".strip()
            message = f'Unknown command: {command}\nType "ai help" for available commands.'
            return CommandResult(success=False, message=message)

        return handler(arguments)

    def _help(self, arguments: list[str]) -> CommandResult:
        """Return the list of available ai commands."""
        return CommandResult(success=True, message=HELP_TEXT)

    def _status(self, arguments: list[str]) -> CommandResult:
        """Display the AI subsystem's overall status."""
        status: AIStatus = self._service.status()
        lines = [
            "AI Status",
            f"Enabled : {'YES' if status.enabled else 'NO'}",
            f"Current provider : {self._display_name(status.current_provider)}",
            f"Registered providers : {status.registered_provider_count}",
        ]
        return CommandResult(success=True, message="\n\n".join(lines))

    def _current(self, arguments: list[str]) -> CommandResult:
        """Display the currently active AI provider."""
        status: AIStatus = self._service.status()
        return CommandResult(
            success=True, message=f"Current provider: {self._display_name(status.current_provider)}"
        )

    def _providers(self, arguments: list[str]) -> CommandResult:
        """List every registered AI provider and its diagnostic flags."""
        providers: list[ProviderInfo] = self._service.list_providers()
        if not providers:
            return CommandResult(success=True, message="No AI providers registered.")

        header = f"{'Provider':<12}{'Enabled':<10}{'Configured':<12}{'Available':<11}{'Current':<8}"
        lines = ["AI Providers", "", header]
        for provider in providers:
            lines.append(
                f"{self._display_name(provider.name):<12}"
                f"{self._mark(provider.enabled):<10}"
                f"{self._mark(provider.configured):<12}"
                f"{self._mark(provider.available):<11}"
                f"{self._mark(provider.is_current):<8}"
            )
        return CommandResult(success=True, message="\n".join(lines))

    def _use(self, arguments: list[str]) -> CommandResult:
        """Select an AI provider as the currently active provider.

        On success, also shows the outcome of the model validation
        `AIService.use_provider()` runs immediately after selection
        (EP-015.3): the configured model and whether it was confirmed
        usable, or the provider's diagnostic (available models and
        closest match) if not.

        Args:
            arguments: `[provider_name]`.

        Returns:
            A CommandResult reflecting whether the provider was selected.
        """
        if len(arguments) != 1:
            return CommandResult(success=False, message="Usage: ai use <provider>")

        result: ProviderSelectionResult = self._service.use_provider(arguments[0].lower())
        if not result.success:
            return CommandResult(success=False, message=result.message)

        lines = [f"Provider: {self._display_name(result.provider)}"]
        validation = result.validation
        if validation is not None and validation.configured_model:
            lines.append(f"Configured model: {validation.configured_model}")
        if validation is not None:
            if validation.valid:
                lines.append("Status: OK")
            else:
                lines.append("Status: NOT FOUND")
                available = ", ".join(validation.available_models) or "(none returned)"
                lines.append(f"Available models: {available}")
                if validation.suggested_model:
                    lines.append(f"Closest match: {validation.suggested_model}")
                lines.append(f"Message: {validation.message}")
        lines.append(result.message)

        return CommandResult(success=True, message="\n".join(lines))

    def _disable(self, arguments: list[str]) -> CommandResult:
        """Disable the AI subsystem."""
        return self._service.disable()

    def _doctor(self, arguments: list[str]) -> CommandResult:
        """Run full AI Provider Manager diagnostics."""
        report: AIDoctorReport = self._service.doctor()
        lines = [
            "AI Doctor",
            f"Configuration : {self._mark(report.configuration_ok)}",
            f"Provider Registry : {self._mark(report.registry_ok)}",
            f"Current Provider : {self._mark(report.current_provider_ok)}",
            f"Connectivity : {self._mark(report.connectivity_ok)}",
        ]
        if report.configuration_errors:
            lines.append("Configuration errors :")
            lines.extend(f"  - {error}" for error in report.configuration_errors)
        else:
            lines.append("Configuration errors : NONE")
        lines.append(f"Result : {'READY' if report.is_ready else 'FAILED'}")
        return CommandResult(success=report.is_ready, message="\n\n".join(lines))

    def _ask(self, arguments: list[str]) -> CommandResult:
        """Send a prompt to the currently active AI provider.

        Args:
            arguments: The prompt words (joined with spaces).

        Returns:
            A CommandResult with the provider's reply, or a
            user-friendly error message.
        """
        if not arguments:
            return CommandResult(success=False, message="Usage: ai ask <prompt>")

        prompt = " ".join(arguments)
        result: AskResult = self._service.ask(prompt)
        if not result.success:
            return CommandResult(success=False, message=result.error)

        message = f"{self._display_name(result.provider)}:\n{result.text}"
        return CommandResult(success=True, message=message)

    def _ping(self, arguments: list[str]) -> CommandResult:
        """Check reachability, latency, model and authentication for the active provider."""
        report: PingReport = self._service.ping()
        if not report.provider:
            return CommandResult(success=False, message=report.message)

        lines = [
            "AI Ping",
            f"Provider : {self._display_name(report.provider)}",
            f"Reachable : {self._mark(report.reachable)}",
            f"Latency : {report.latency_ms:.0f} ms",
            f"Model : {report.model or 'n/a'}",
            f"Authentication : {self._mark(report.authenticated)}",
        ]
        if report.message:
            lines.append(f"Message : {report.message}")

        success = report.reachable and report.authenticated
        return CommandResult(success=success, message="\n".join(lines))

    def _models(self, arguments: list[str]) -> CommandResult:
        """List the models available from the active provider's own configuration."""
        result: ModelsResult = self._service.models()
        if result.error:
            return CommandResult(success=False, message=result.error)
        if not result.models:
            return CommandResult(
                success=True, message=f"No models configured for '{self._display_name(result.provider)}'."
            )

        lines = [f"Models ({self._display_name(result.provider)})", ""]
        lines.extend(f"- {model}" for model in result.models)
        return CommandResult(success=True, message="\n".join(lines))

    def _test(self, arguments: list[str]) -> CommandResult:
        """Send a fixed "Hello" prompt to verify successful communication."""
        result: AskResult = self._service.test()
        if not result.success:
            return CommandResult(success=False, message=f"Test failed: {result.error}")

        message = (
            f"Test successful.\n\n"
            f"{self._display_name(result.provider)} ({result.model}):\n{result.text}"
        )
        return CommandResult(success=True, message=message)

    @staticmethod
    def _mark(value: bool) -> str:
        """Format a boolean diagnostic check as "YES" or "NO"."""
        return "YES" if value else "NO"

    @staticmethod
    def _display_name(name: str | None) -> str:
        """Map a provider identifier to its human-readable display name.

        Args:
            name: A registered provider name, or None if no provider
                is currently selected.

        Returns:
            The display name for `name` (falling back to `name`
            itself for an unrecognized identifier), or "none" if
            `name` is None.
        """
        if name is None:
            return "none"
        return _DISPLAY_NAMES.get(name, name)
