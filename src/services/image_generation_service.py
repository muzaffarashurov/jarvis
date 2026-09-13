"""Standalone image generation for EP-083 Image Generation Provider Integration.

`ImageGenerationService` is the actual EP-083 deliverable: a
standalone, non-conversational content-generation entry point over the
existing AI provider abstraction, mirroring `TextGenerationService`
(EP-082) exactly. It is the second slice of Phase C (AI Content
Platform); later EPs (EP-084 audio, EP-085 video, EP-086
presentations, EP-087's combined pipeline) are expected to follow the
same pattern (`EP083_DESIGN.md` Section 3, 20).

Non-conversational semantics (`EP083_DESIGN.md` Section 9, mirroring
`EP082_DESIGN.md` Section 9) -- this service deliberately:

    MUST NOT:
        - create or update conversation history;
        - call `ConversationManager` in any way;
        - implicitly load project or working-directory context;
        - call `ContextManager`;
        - create memory entries;
        - persist generated images in any form (no file writes, no
          database, no draft/versioning storage -- images are
          returned in-memory only);
        - depend on, wrap, or call through `AIService.ask()`'s
          conversational pipeline.

Fallback/retry execution is delegated to the same, shared
`ProviderRequestExecutor` (extended additively by EP-083 with
`execute_image()`) that `AIService.ask()`/`TextGenerationService`
already use, so this service introduces no second implementation of
EP-069's fallback/cost-aware retry logic (`EP083_DESIGN.md` Section 8,
Owner Decision 1). `ProviderManager` itself is untouched by this
module: provider selection, candidate discovery, and ordering remain
entirely its responsibility.

Capability filtering (`EP083_DESIGN.md` Section 9, point 7): this
service is responsible for checking the *initial* provider's
`supports_image_generation()` before ever calling the executor -- a
provider that is reachable and enabled but simply does not support
image generation is a configuration/selection mismatch, not a
transient failure, and is reported without any executor or network
call at all. Fallback *candidates* are filtered by
`ProviderRequestExecutor.execute_image()` itself.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.core.ai.provider import GeneratedImage, ImageGenerationRequest
from src.core.ai.provider_manager import ProviderManager
from src.core.ai.provider_request_executor import ProviderRequestExecutor

__all__ = ["ImageGenerationResult", "ImageGenerationService"]

_NO_PROVIDER_SELECTED: str = "No AI provider is currently selected. Use 'ai use <provider>'."
_IMAGE_GENERATION_DISABLED: str = (
    "Image generation is disabled. Enable 'image_generation.enabled' in config.yaml to use it."
)
_AI_SUBSYSTEM_DISABLED: str = "AI subsystem is disabled. Enable 'ai.enabled' in config.yaml to use a provider."


@dataclass(frozen=True)
class ImageGenerationResult:
    """Result of `ImageGenerationService.generate()` (EP-083).

    Deliberately minimal, mirroring `TextGenerationResult` (EP-082):
    no conversation-related metadata, no persistence/versioning
    metadata, and no speculative fields -- those are DEFERRED until a
    concrete consumer needs them (`EP083_DESIGN.md` Section 4, 13).

    Every failure -- no provider selected, AI subsystem disabled,
    image generation disabled, current provider lacks the capability,
    a non-fallback-eligible provider error, or every fallback
    candidate exhausted -- is reported here as `success=False` with a
    user-friendly `error`; this service never raises a `ProviderError`
    to its caller, mirroring `TextGenerationResult`'s own convention
    exactly rather than introducing a second failure-reporting policy.

    Attributes:
        success: Whether some provider produced generated image(s).
        images: The generated image(s) as `(data_base64, mime_type)`
            pairs (`GeneratedImage` from `src.core.ai.provider`), or
            an empty tuple on failure.
        provider_name: The provider that actually produced `images`
            (may differ from the originally selected provider if
            fallback occurred), or "" on failure.
        model_name: The model that produced `images`, or "" on
            failure.
        error: A user-friendly error message, or "" on success.
    """

    success: bool
    images: tuple[GeneratedImage, ...]
    provider_name: str
    model_name: str
    error: str


class ImageGenerationService:
    """Standalone, non-conversational image-generation capability (EP-083).

    Delegates provider selection to `ProviderManager` and request
    execution/fallback to the shared `ProviderRequestExecutor`'s
    `execute_image()` -- it holds no provider state and implements no
    retry logic of its own.
    """

    def __init__(
        self,
        provider_manager: ProviderManager,
        request_executor: ProviderRequestExecutor,
        enabled: bool = False,
        fallback_enabled: bool = False,
    ) -> None:
        """Initialize the ImageGenerationService.

        Args:
            provider_manager: The ProviderManager used to resolve the
                currently selected provider. Never mutated by this
                service (no `set_current()`/`disable()` calls).
            request_executor: The shared `ProviderRequestExecutor`
                this service delegates fallback/retry execution to --
                the same instance `AIService`/`TextGenerationService`
                use, so there is exactly one fallback/retry
                implementation in the repository
                (`EP083_DESIGN.md` Section 8).
            enabled: Value of 'image_generation.enabled'. Defaults to
                False so image generation is opt-in.
            fallback_enabled: Value of
                'image_generation.fallback_enabled' -- independent of
                'ai.fallback_enabled'/'content_generation.
                fallback_enabled', since image-generation requests are
                a distinct calling context (`EP083_DESIGN.md` Section
                15).
        """
        self._provider_manager = provider_manager
        self._request_executor = request_executor
        self._enabled = enabled
        self._fallback_enabled = fallback_enabled

    def generate(self, request: ImageGenerationRequest) -> ImageGenerationResult:
        """Generate standalone image(s) for `request`.

        No conversation, context, or persistence is involved (this
        module's docstring). `request` is sent to the provider exactly
        as given.

        Args:
            request: The provider-independent image-generation
                request.

        Returns:
            An ImageGenerationResult describing the outcome.
        """
        if not self._enabled:
            return ImageGenerationResult(
                success=False,
                images=(),
                provider_name="",
                model_name="",
                error=_IMAGE_GENERATION_DISABLED,
            )

        current = self._provider_manager.get_current()
        if current is None:
            return ImageGenerationResult(
                success=False,
                images=(),
                provider_name="",
                model_name="",
                error=_NO_PROVIDER_SELECTED,
            )

        if not self._provider_manager.is_enabled():
            return ImageGenerationResult(
                success=False,
                images=(),
                provider_name=current.name(),
                model_name="",
                error=_AI_SUBSYSTEM_DISABLED,
            )

        if not current.supports_image_generation():
            # A capability mismatch, not a transient failure -- never
            # reaches the executor or the network
            # (`EP083_DESIGN.md` Section 9, point 7; Section 14).
            return ImageGenerationResult(
                success=False,
                images=(),
                provider_name=current.name(),
                model_name="",
                error=f"Provider '{current.name()}' does not support image generation.",
            )

        outcome = self._request_executor.execute_image(
            current,
            request,
            fallback_enabled=self._fallback_enabled,
        )
        if not outcome.success:
            return ImageGenerationResult(
                success=False,
                images=(),
                provider_name=outcome.initial_provider,
                model_name="",
                error=outcome.error,
            )

        result = outcome.result
        if result is None:
            # ImageProviderRequestOutcome.success=True always carries a
            # non-None result by construction of `execute_image()` --
            # an explicit guard rather than a bare `assert`, so this
            # invariant is enforced even under Python's `-O` mode
            # (EP-082 STEP 3 hardening precedent).
            return ImageGenerationResult(
                success=False,
                images=(),
                provider_name=outcome.final_provider,
                model_name="",
                error="Internal error: successful outcome carried no result.",
            )
        return ImageGenerationResult(
            success=True,
            images=result.images,
            provider_name=outcome.final_provider,
            model_name=result.model,
            error="",
        )
