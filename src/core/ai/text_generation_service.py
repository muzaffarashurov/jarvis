"""Standalone text generation for EP-082 Text Generation Provider Integration.

`TextGenerationService` is the actual EP-082 deliverable: a standalone,
non-conversational content-generation entry point over the existing AI
provider abstraction (`AIProvider`/`ProviderRegistry`/`ProviderManager`
-- EP-014/015, extended by EP-069.1/.2/.3's fallback and cost-aware
selection). It is the foundational slice of Phase C (AI Content
Platform) that later EPs (EP-083 image, EP-084 audio, EP-085 video,
EP-086 presentations, EP-087's combined pipeline) are expected to
follow the same pattern of (`EP082_DESIGN.md` Section 3, 7).

Non-conversational semantics (`EP082_DESIGN.md` Section 9) -- this
service deliberately:

    MUST NOT:
        - create or update conversation history;
        - call `ConversationManager` in any way;
        - implicitly load project or working-directory context;
        - call `ContextManager`;
        - create memory entries;
        - persist generated content in any form;
        - depend on, wrap, or call through `AIService.ask()`'s
          conversational pipeline.

Fallback/retry execution is delegated to the same, shared
`ProviderRequestExecutor` (EP-082) that `AIService.ask()` uses, so
this service introduces no second implementation of EP-069's
fallback/cost-aware retry logic (`EP082_DESIGN.md` Section 6, 11.1,
Rule 3/Rule 4). `ProviderManager` itself is untouched by this module:
provider selection, candidate discovery, and ordering remain entirely
its responsibility.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.core.ai.provider_manager import ProviderManager
from src.core.ai.provider_request_executor import ProviderRequestExecutor

__all__ = ["TextGenerationResult", "TextGenerationService"]

_NO_PROVIDER_SELECTED: str = "No AI provider is currently selected. Use 'ai use <provider>'."
_TEXT_GENERATION_DISABLED: str = (
    "Text generation is disabled. Enable 'content_generation.enabled' in config.yaml to use it."
)
_AI_SUBSYSTEM_DISABLED: str = "AI subsystem is disabled. Enable 'ai.enabled' in config.yaml to use a provider."


@dataclass(frozen=True)
class TextGenerationResult:
    """Result of `TextGenerationService.generate()` (EP-082).

    Deliberately minimal (`EP082_DESIGN.md` Section 14): no
    conversation-related metadata (no turn IDs, no history
    references), no persistence/versioning metadata, and no
    speculative content-type fields -- those are DEFERRED until a
    concrete consumer needs them.

    Every failure -- no provider selected, AI subsystem disabled,
    text generation disabled, a non-fallback-eligible provider error,
    or every fallback candidate exhausted -- is reported here as
    `success=False` with a user-friendly `error`; this service never
    raises a `ProviderError` to its caller, mirroring
    `AIService.ask()`'s own existing `AskResult` convention exactly
    rather than introducing a second failure-reporting policy.

    Attributes:
        success: Whether some provider produced generated text.
        text: The generated text, or "" on failure.
        provider_name: The provider that actually produced `text`
            (may differ from the originally selected provider if
            fallback occurred), or "" on failure.
        model_name: The model that produced `text`, or "" on failure.
        error: A user-friendly error message, or "" on success.
    """

    success: bool
    text: str
    provider_name: str
    model_name: str
    error: str


class TextGenerationService:
    """Standalone, non-conversational content-generation capability (EP-082).

    Delegates provider selection to `ProviderManager` and request
    execution/fallback to the shared `ProviderRequestExecutor` --
    it holds no provider state and implements no retry logic of its
    own.
    """

    def __init__(
        self,
        provider_manager: ProviderManager,
        request_executor: ProviderRequestExecutor,
        enabled: bool = False,
        default_temperature: float | None = None,
        fallback_enabled: bool = False,
    ) -> None:
        """Initialize the TextGenerationService.

        Args:
            provider_manager: The ProviderManager used to resolve the
                currently selected provider. Never mutated by this
                service (no `set_current()`/`disable()` calls) --
                content generation shares, but never changes, the
                same provider selection `AIService` uses.
            request_executor: The shared `ProviderRequestExecutor`
                (EP-082) this service delegates fallback/retry
                execution to -- the same instance `AIService` uses,
                so there is exactly one fallback/retry implementation
                in the repository (`EP082_DESIGN.md` Section 6).
            enabled: Value of 'content_generation.enabled'. Defaults
                to False so text generation is opt-in.
            default_temperature: Value of
                'content_generation.default_temperature', used when a
                caller's `generate()` does not supply a per-request
                `temperature` override. None means no default
                override is applied (providers use their own
                'providers.<name>.temperature').
            fallback_enabled: Value of
                'content_generation.fallback_enabled' -- independent
                of 'ai.fallback_enabled', since content-generation
                requests are a distinct calling context from chat
                (`EP082_DESIGN.md` Section 15).
        """
        self._provider_manager = provider_manager
        self._request_executor = request_executor
        self._enabled = enabled
        self._default_temperature = default_temperature
        self._fallback_enabled = fallback_enabled

    def generate(
        self,
        prompt: str,
        *,
        max_tokens: int | None = None,
        temperature: float | None = None,
        system_prompt: str | None = None,
    ) -> TextGenerationResult:
        """Generate standalone text for `prompt`.

        No conversation, context, or persistence is involved (Section
        9 of `EP082_DESIGN.md` / this module's docstring). `prompt` is
        sent to the provider exactly as given -- unlike
        `AIService.ask()`, this service performs no Prompt Engine
        rendering and no project/conversation context injection, per
        its non-conversational scope.

        Args:
            prompt: The final prompt/instruction text to send.
            max_tokens: Optional override for the reply's maximum
                token count. None uses the provider's configured
                default.
            temperature: Optional per-request override. None falls
                back to `default_temperature` (from
                'content_generation.default_temperature'), which
                itself may be None (provider's own configured
                default). Must be within the valid 0.0-1.0 range if
                provided -- an invalid value results in a failed
                `TextGenerationResult`, not a raised exception
                (Section 14).
            system_prompt: Optional per-request system-prompt/style
                override. None omits it.

        Returns:
            A TextGenerationResult describing the outcome.
        """
        if not self._enabled:
            return TextGenerationResult(
                success=False, text="", provider_name="", model_name="", error=_TEXT_GENERATION_DISABLED
            )

        current = self._provider_manager.get_current()
        if current is None:
            return TextGenerationResult(
                success=False, text="", provider_name="", model_name="", error=_NO_PROVIDER_SELECTED
            )

        if not self._provider_manager.is_enabled():
            return TextGenerationResult(
                success=False,
                text="",
                provider_name=current.name(),
                model_name="",
                error=_AI_SUBSYSTEM_DISABLED,
            )

        effective_temperature = temperature if temperature is not None else self._default_temperature

        outcome = self._request_executor.execute(
            current,
            prompt,
            fallback_enabled=self._fallback_enabled,
            max_tokens=max_tokens,
            temperature=effective_temperature,
            system_prompt=system_prompt,
        )
        if not outcome.success:
            return TextGenerationResult(
                success=False,
                text="",
                provider_name=outcome.initial_provider,
                model_name="",
                error=outcome.error,
            )

        response = outcome.response
        if response is None:
            # ProviderRequestOutcome.success=True always carries a
            # non-None response by construction of `execute()` -- this
            # is a defensive guard against that invariant ever being
            # violated (e.g. under `-O`, where a bare `assert` would
            # silently no-op instead of surfacing the defect), not a
            # reachable code path in normal operation.
            return TextGenerationResult(
                success=False,
                text="",
                provider_name=outcome.final_provider,
                model_name="",
                error="Internal error: successful outcome carried no response.",
            )
        return TextGenerationResult(
            success=True,
            text=response.text,
            provider_name=outcome.final_provider,
            model_name=response.model,
            error="",
        )
