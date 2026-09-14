"""Standalone speech generation for EP-084 Audio & Speech Generation Integration.

`AudioGenerationService` is the actual EP-084 deliverable: a
standalone, non-conversational content-generation entry point over the
existing AI provider abstraction, mirroring `TextGenerationService`
(EP-082) and `ImageGenerationService` (EP-083) exactly. It is the
third slice of Phase C (AI Content Platform); later EPs (EP-085 video,
EP-086 presentations, EP-087's combined pipeline) are expected to
follow the same pattern (`EP084_DESIGN.md` Section 21).

Non-conversational semantics (`EP084_DESIGN.md` Section 14, mirroring
`EP082_DESIGN.md` Section 9 / `EP083_DESIGN.md` Section 9) -- this
service deliberately:

    MUST NOT:
        - create or update conversation history;
        - call `ConversationManager` in any way;
        - implicitly load project or working-directory context;
        - call `ContextManager`;
        - create memory entries;
        - persist generated audio in any form (no file writes, no
          database, no draft/versioning storage -- audio is returned
          in-memory only);
        - depend on, wrap, or call through `AIService.ask()`'s
          conversational pipeline.

Fallback/retry execution is delegated to the same, shared
`ProviderRequestExecutor` (extended additively by EP-084 with
`execute_speech()`) that `AIService.ask()`/`TextGenerationService`/
`ImageGenerationService` already use, so this service introduces no
second implementation of EP-069's fallback/cost-aware retry logic
(`EP084_DESIGN.md` Section 13). `ProviderManager` itself is untouched
by this module: provider selection, candidate discovery, and ordering
remain entirely its responsibility.

Capability filtering (`EP084_DESIGN.md` Section 14, mirroring
`EP083_DESIGN.md` Section 9 point 7): this service is responsible for
checking the *initial* provider's `supports_speech_generation()`
before ever calling the executor -- a provider that is reachable and
enabled but simply does not support speech generation is a
configuration/selection mismatch, not a transient failure, and is
reported without any executor or network call at all. Fallback
*candidates* are filtered by `ProviderRequestExecutor.
execute_speech()` itself.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.core.ai.provider import GeneratedAudio, SpeechGenerationRequest
from src.core.ai.provider_manager import ProviderManager
from src.core.ai.provider_request_executor import ProviderRequestExecutor

__all__ = ["AudioGenerationService", "SpeechGenerationResult"]

_NO_PROVIDER_SELECTED: str = "No AI provider is currently selected. Use 'ai use <provider>'."
_AUDIO_GENERATION_DISABLED: str = (
    "Speech generation is disabled. Enable 'audio_generation.enabled' in config.yaml to use it."
)
_AI_SUBSYSTEM_DISABLED: str = "AI subsystem is disabled. Enable 'ai.enabled' in config.yaml to use a provider."


@dataclass(frozen=True)
class SpeechGenerationResult:
    """Result of `AudioGenerationService.generate()` (EP-084).

    Deliberately minimal, mirroring `ImageGenerationResult` (EP-083)
    and `TextGenerationResult` (EP-082): no conversation-related
    metadata, no persistence/versioning metadata, and no speculative
    fields -- those are DEFERRED until a concrete consumer needs them
    (`EP084_DESIGN.md` Section 11, 20).

    Every failure -- no provider selected, AI subsystem disabled,
    speech generation disabled, current provider lacks the capability,
    a non-fallback-eligible provider error, or every fallback
    candidate exhausted -- is reported here as `success=False` with a
    user-friendly `error`; this service never raises a `ProviderError`
    to its caller, mirroring `ImageGenerationResult`'s own convention
    exactly rather than introducing a second failure-reporting policy.

    Attributes:
        success: Whether some provider produced generated audio.
        audio: The generated audio as a `(data_base64, mime_type)`
            pair (`GeneratedAudio` from `src.core.ai.provider`), or
            None on failure.
        provider_name: The provider that actually produced `audio`
            (may differ from the originally selected provider if
            fallback occurred), or "" on failure.
        model_name: The model that produced `audio`, or "" on failure.
        error: A user-friendly error message, or "" on success.
    """

    success: bool
    audio: GeneratedAudio | None
    provider_name: str
    model_name: str
    error: str


class AudioGenerationService:
    """Standalone, non-conversational speech-generation capability (EP-084).

    Delegates provider selection to `ProviderManager` and request
    execution/fallback to the shared `ProviderRequestExecutor`'s
    `execute_speech()` -- it holds no provider state and implements no
    retry logic of its own.
    """

    def __init__(
        self,
        provider_manager: ProviderManager,
        request_executor: ProviderRequestExecutor,
        enabled: bool = False,
        fallback_enabled: bool = False,
    ) -> None:
        """Initialize the AudioGenerationService.

        Args:
            provider_manager: The ProviderManager used to resolve the
                currently selected provider. Never mutated by this
                service (no `set_current()`/`disable()` calls).
            request_executor: The shared `ProviderRequestExecutor`
                this service delegates fallback/retry execution to --
                the same instance `AIService`/`TextGenerationService`/
                `ImageGenerationService` use, so there is exactly one
                fallback/retry implementation in the repository
                (`EP084_DESIGN.md` Section 13).
            enabled: Value of 'audio_generation.enabled'. Defaults to
                False so speech generation is opt-in.
            fallback_enabled: Value of
                'audio_generation.fallback_enabled' -- independent of
                'ai.fallback_enabled'/'content_generation.
                fallback_enabled'/'image_generation.fallback_enabled',
                since speech-generation requests are a distinct
                calling context (`EP084_DESIGN.md` Section 16).
        """
        self._provider_manager = provider_manager
        self._request_executor = request_executor
        self._enabled = enabled
        self._fallback_enabled = fallback_enabled

    def generate(self, request: SpeechGenerationRequest) -> SpeechGenerationResult:
        """Generate standalone speech audio for `request`.

        No conversation, context, or persistence is involved (this
        module's docstring). `request` is sent to the provider exactly
        as given.

        Args:
            request: The provider-independent speech-generation
                request.

        Returns:
            A SpeechGenerationResult describing the outcome.
        """
        if not self._enabled:
            return SpeechGenerationResult(
                success=False,
                audio=None,
                provider_name="",
                model_name="",
                error=_AUDIO_GENERATION_DISABLED,
            )

        current = self._provider_manager.get_current()
        if current is None:
            return SpeechGenerationResult(
                success=False,
                audio=None,
                provider_name="",
                model_name="",
                error=_NO_PROVIDER_SELECTED,
            )

        if not self._provider_manager.is_enabled():
            return SpeechGenerationResult(
                success=False,
                audio=None,
                provider_name=current.name(),
                model_name="",
                error=_AI_SUBSYSTEM_DISABLED,
            )

        if not current.supports_speech_generation():
            # A capability mismatch, not a transient failure -- never
            # reaches the executor or the network
            # (`EP084_DESIGN.md` Section 14).
            return SpeechGenerationResult(
                success=False,
                audio=None,
                provider_name=current.name(),
                model_name="",
                error=f"Provider '{current.name()}' does not support speech generation.",
            )

        outcome = self._request_executor.execute_speech(
            current,
            request,
            fallback_enabled=self._fallback_enabled,
        )
        if not outcome.success:
            return SpeechGenerationResult(
                success=False,
                audio=None,
                provider_name=outcome.initial_provider,
                model_name="",
                error=outcome.error,
            )

        result = outcome.result
        if result is None:
            # SpeechProviderRequestOutcome.success=True always carries
            # a non-None result by construction of `execute_speech()`
            # -- an explicit guard rather than a bare `assert`, so this
            # invariant is enforced even under Python's `-O` mode
            # (EP-082 STEP 3 hardening precedent, reused by
            # ImageGenerationService and here).
            return SpeechGenerationResult(
                success=False,
                audio=None,
                provider_name=outcome.final_provider,
                model_name="",
                error="Internal error: successful outcome carried no result.",
            )
        return SpeechGenerationResult(
            success=True,
            audio=result.audio,
            provider_name=outcome.final_provider,
            model_name=result.model,
            error="",
        )
