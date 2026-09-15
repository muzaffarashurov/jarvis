"""Standalone video generation for EP-085 Video Generation Provider Integration.

`VideoGenerationService` is the actual EP-085 deliverable: a
standalone, non-conversational content-generation entry point over the
existing AI provider abstraction, mirroring `TextGenerationService`
(EP-082), `ImageGenerationService` (EP-083), and `AudioGenerationService`
(EP-084) exactly at the service-layer control-flow level. It is the
fourth slice of Phase C (AI Content Platform); EP-086 (presentations)
and EP-087 (the combined pipeline) are expected to follow the same
pattern (`EP085_DESIGN.md` Section 21).

Non-conversational semantics (`EP085_DESIGN.md` Section 9, mirroring
every prior modality's own such section) -- this service deliberately:

    MUST NOT:
        - create or update conversation history;
        - call `ConversationManager` in any way;
        - implicitly load project or working-directory context;
        - call `ContextManager`;
        - create memory entries;
        - persist generated video in any form (no file writes, no
          database, no draft/versioning storage). Per Owner Decision
          D2, this service never even holds video *bytes* in memory --
          it returns a reference to where Google is hosting the
          result (`GeneratedVideo.uri`), nothing more.
        - depend on, wrap, or call through `AIService.ask()`'s
          conversational pipeline.

Fallback/retry execution is delegated to the same, shared
`ProviderRequestExecutor` (extended additively by EP-085 with
`execute_video()`) that every other generation service already uses,
so this service introduces no second implementation of EP-069's
fallback/cost-aware retry logic (`EP085_DESIGN.md` Section 7).
`ProviderManager` itself is untouched by this module.

Long-running-call note (`EP085_DESIGN.md` Section 6/22, Owner Decision
D1): a single `generate()` call here may take minutes, not seconds --
`GeminiProvider.generate_video()`'s concrete implementation performs
an internal initiate-then-poll cycle before ever returning. This
service does not attempt to hide or shorten that; it is a deliberate,
approved architectural trade-off (keeping the caller-facing contract
synchronous rather than inventing a new asynchronous job/queue
framework), not an oversight.

Capability filtering (`EP085_DESIGN.md` Section 5, mirroring every
prior modality): this service is responsible for checking the
*initial* provider's `supports_video_generation()` before ever calling
the executor -- a provider that is reachable and enabled but simply
does not support video generation is a configuration/selection
mismatch, not a transient failure, and is reported without any
executor or network call at all. Fallback *candidates* are filtered by
`ProviderRequestExecutor.execute_video()` itself.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.core.ai.provider import GeneratedVideo, VideoGenerationRequest
from src.core.ai.provider_manager import ProviderManager
from src.core.ai.provider_request_executor import ProviderRequestExecutor

__all__ = ["VideoGenerationResult", "VideoGenerationService"]

_NO_PROVIDER_SELECTED: str = "No AI provider is currently selected. Use 'ai use <provider>'."
_VIDEO_GENERATION_DISABLED: str = (
    "Video generation is disabled. Enable 'video_generation.enabled' in config.yaml to use it."
)
_AI_SUBSYSTEM_DISABLED: str = "AI subsystem is disabled. Enable 'ai.enabled' in config.yaml to use a provider."


@dataclass(frozen=True)
class VideoGenerationResult:
    """Result of `VideoGenerationService.generate()` (EP-085).

    Deliberately minimal, mirroring `SpeechGenerationResult` (EP-084,
    service-level)/`ImageGenerationResult` (EP-083, service-level):
    no conversation-related metadata, no persistence/versioning
    metadata, and no speculative fields.

    Every failure -- no provider selected, AI subsystem disabled,
    video generation disabled, current provider lacks the capability,
    a non-fallback-eligible provider error, operation timeout,
    operation failure, or every fallback candidate exhausted -- is
    reported here as `success=False` with a user-friendly `error`;
    this service never raises a `ProviderError` to its caller,
    mirroring every prior modality's convention exactly.

    Attributes:
        success: Whether some provider produced a generated video.
        video: The generated video reference (`GeneratedVideo` from
            `src.core.ai.provider` -- a `uri`/`mime_type` pair, never
            raw bytes; see Owner Decision D2), or None on failure.
        provider_name: The provider that actually produced `video`
            (may differ from the originally selected provider if
            fallback occurred), or "" on failure.
        model_name: The model that produced `video`, or "" on failure.
        error: A user-friendly error message, or "" on success.
    """

    success: bool
    video: GeneratedVideo | None
    provider_name: str
    model_name: str
    error: str


class VideoGenerationService:
    """Standalone, non-conversational video-generation capability (EP-085).

    Delegates provider selection to `ProviderManager` and request
    execution/fallback to the shared `ProviderRequestExecutor`'s
    `execute_video()` -- it holds no provider state and implements no
    retry logic, and no polling logic, of its own (polling lives
    entirely inside `GeminiProvider.generate_video()`).
    """

    def __init__(
        self,
        provider_manager: ProviderManager,
        request_executor: ProviderRequestExecutor,
        enabled: bool = False,
        fallback_enabled: bool = False,
    ) -> None:
        """Initialize the VideoGenerationService.

        Args:
            provider_manager: The ProviderManager used to resolve the
                currently selected provider. Never mutated by this
                service.
            request_executor: The shared `ProviderRequestExecutor`
                this service delegates fallback/retry execution to --
                the same instance every other generation service
                uses, so there is exactly one fallback/retry
                implementation in the repository
                (`EP085_DESIGN.md` Section 7).
            enabled: Value of 'video_generation.enabled'. Defaults to
                False so video generation is opt-in.
            fallback_enabled: Value of
                'video_generation.fallback_enabled'. Defaults to False
                -- deliberately, more firmly than for any prior
                modality (`EP085_DESIGN.md` Section 13): retrying a
                video request against a fallback candidate means
                paying the full multi-minute initiate-then-poll cost
                again, on a request that may have already run for
                minutes before failing. Independent of
                'ai.fallback_enabled'/every other modality's own
                fallback flag.
        """
        self._provider_manager = provider_manager
        self._request_executor = request_executor
        self._enabled = enabled
        self._fallback_enabled = fallback_enabled

    def generate(self, request: VideoGenerationRequest) -> VideoGenerationResult:
        """Generate a standalone video reference for `request`.

        No conversation, context, or persistence is involved (this
        module's docstring). `request` is sent to the provider exactly
        as given. This call may block for several minutes -- see this
        module's Long-running-call note.

        Args:
            request: The provider-independent video-generation
                request.

        Returns:
            A VideoGenerationResult describing the outcome.
        """
        if not self._enabled:
            return VideoGenerationResult(
                success=False,
                video=None,
                provider_name="",
                model_name="",
                error=_VIDEO_GENERATION_DISABLED,
            )

        current = self._provider_manager.get_current()
        if current is None:
            return VideoGenerationResult(
                success=False,
                video=None,
                provider_name="",
                model_name="",
                error=_NO_PROVIDER_SELECTED,
            )

        if not self._provider_manager.is_enabled():
            return VideoGenerationResult(
                success=False,
                video=None,
                provider_name=current.name(),
                model_name="",
                error=_AI_SUBSYSTEM_DISABLED,
            )

        if not current.supports_video_generation():
            # A capability mismatch, not a transient failure -- never
            # reaches the executor or the network
            # (`EP085_DESIGN.md` Section 5).
            return VideoGenerationResult(
                success=False,
                video=None,
                provider_name=current.name(),
                model_name="",
                error=f"Provider '{current.name()}' does not support video generation.",
            )

        outcome = self._request_executor.execute_video(
            current,
            request,
            fallback_enabled=self._fallback_enabled,
        )
        if not outcome.success:
            return VideoGenerationResult(
                success=False,
                video=None,
                provider_name=outcome.initial_provider,
                model_name="",
                error=outcome.error,
            )

        result = outcome.result
        if result is None:
            # VideoProviderRequestOutcome.success=True always carries
            # a non-None result by construction of `execute_video()`
            # -- an explicit guard rather than a bare `assert`, so this
            # invariant is enforced even under Python's `-O` mode
            # (EP-082 STEP 3 hardening precedent, reused by every
            # subsequent generation service).
            return VideoGenerationResult(
                success=False,
                video=None,
                provider_name=outcome.final_provider,
                model_name="",
                error="Internal error: successful outcome carried no result.",
            )
        return VideoGenerationResult(
            success=True,
            video=result.video,
            provider_name=outcome.final_provider,
            model_name=result.model,
            error="",
        )
