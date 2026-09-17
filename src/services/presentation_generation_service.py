"""Standalone presentation-content generation for EP-086 Presentation
Generation Integration.

`PresentationGenerationService` is the actual EP-086 deliverable: a
standalone, non-conversational content-generation entry point over the
existing AI provider abstraction, mirroring `TextGenerationService`
(EP-082), `ImageGenerationService` (EP-083), `AudioGenerationService`
(EP-084), and `VideoGenerationService` (EP-085) exactly at the
service-layer control-flow level. It is the fifth and final slice of
Phase C (AI Content Platform); EP-087's combined pipeline is expected
to compose this service the same way it is expected to compose the
other four (`EP086_DESIGN.md` Section 20).

Content, not binary media (`EP086_DESIGN.md` Section 6/11): unlike
`ImageGenerationService`/`AudioGenerationService`/`VideoGenerationService`,
this service never handles bytes, base64 data, or a URI/reference of
any kind. Its result (`GeneratedPresentation`) is ordinary, in-memory
structured text content -- a title and an ordered list of slides. This
EP does not generate a `.pptx` file or any other rendered artifact
(`EP086_DESIGN.md` Section 4); that is an explicitly separate concern.

Non-conversational semantics (`EP086_DESIGN.md` Section 14, mirroring
every prior modality's own such section) -- this service deliberately:

    MUST NOT:
        - create or update conversation history;
        - call `ConversationManager` in any way;
        - implicitly load project or working-directory context;
        - call `ContextManager`;
        - create memory entries;
        - persist generated content in any form (no file writes, no
          database, no draft/versioning storage);
        - depend on, wrap, or call through `AIService.ask()`'s
          conversational pipeline;
        - perform any provider-specific request construction or
          response parsing -- that is `GeminiProvider`'s
          responsibility alone.

Fallback/retry execution is delegated to the same, shared
`ProviderRequestExecutor` (extended additively by EP-086 with
`execute_presentation()`) that every other generation service already
uses, so this service introduces no second implementation of EP-069's
fallback/cost-aware retry logic (`EP086_DESIGN.md` Section 7).
`ProviderManager` itself is untouched by this module: provider
selection, candidate discovery, and ordering remain entirely its
responsibility -- this service performs no presentation-specific
provider-selection logic of its own.

Capability filtering (`EP086_DESIGN.md` Section 5, mirroring every
prior modality): this service is responsible for checking the
*initial* provider's `supports_presentation_generation()` before ever
calling the executor -- a provider that is reachable and enabled but
simply does not support presentation generation is a configuration/
selection mismatch, not a transient failure, and is reported without
any executor or network call at all. Fallback *candidates* are
filtered by `ProviderRequestExecutor.execute_presentation()` itself.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.core.ai.provider import GeneratedPresentation, PresentationGenerationRequest
from src.core.ai.provider_manager import ProviderManager
from src.core.ai.provider_request_executor import ProviderRequestExecutor

__all__ = ["PresentationGenerationResult", "PresentationGenerationService"]

_NO_PROVIDER_SELECTED: str = "No AI provider is currently selected. Use 'ai use <provider>'."
_PRESENTATION_GENERATION_DISABLED: str = (
    "Presentation generation is disabled. Enable 'presentation_generation.enabled' "
    "in config.yaml to use it."
)
_AI_SUBSYSTEM_DISABLED: str = "AI subsystem is disabled. Enable 'ai.enabled' in config.yaml to use a provider."


@dataclass(frozen=True)
class PresentationGenerationResult:
    """Result of `PresentationGenerationService.generate()` (EP-086).

    Deliberately minimal, mirroring `SpeechGenerationResult`/
    `VideoGenerationResult` (service-level, EP-084/085): no
    conversation-related metadata, no persistence/versioning metadata,
    and no speculative fields.

    Every failure -- no provider selected, AI subsystem disabled,
    presentation generation disabled, current provider lacks the
    capability, a non-fallback-eligible provider error, or every
    fallback candidate exhausted -- is reported here as
    `success=False` with a user-friendly `error`; this service never
    raises a `ProviderError` to its caller, mirroring every prior
    modality's convention exactly.

    Attributes:
        success: Whether some provider produced generated presentation
            content.
        presentation: The generated presentation content
            (`GeneratedPresentation` from `src.core.ai.provider` -- a
            title and a tuple of slides, never bytes or a URI), or
            None on failure.
        provider_name: The provider that actually produced
            `presentation` (may differ from the originally selected
            provider if fallback occurred), or "" on failure.
        model_name: The model that produced `presentation`, or "" on
            failure.
        error: A user-friendly error message, or "" on success.
    """

    success: bool
    presentation: GeneratedPresentation | None
    provider_name: str
    model_name: str
    error: str


class PresentationGenerationService:
    """Standalone, non-conversational presentation-content-generation capability (EP-086).

    Delegates provider selection to `ProviderManager` and request
    execution/fallback to the shared `ProviderRequestExecutor`'s
    `execute_presentation()` -- it holds no provider state and
    implements no retry logic, request construction, or response
    parsing of its own.
    """

    def __init__(
        self,
        provider_manager: ProviderManager,
        request_executor: ProviderRequestExecutor,
        enabled: bool = False,
        fallback_enabled: bool = False,
    ) -> None:
        """Initialize the PresentationGenerationService.

        Args:
            provider_manager: The ProviderManager used to resolve the
                currently selected provider. Never mutated by this
                service.
            request_executor: The shared `ProviderRequestExecutor`
                this service delegates fallback/retry execution to --
                the same instance every other generation service
                uses, so there is exactly one fallback/retry
                implementation in the repository
                (`EP086_DESIGN.md` Section 7).
            enabled: Value of 'presentation_generation.enabled'.
                Defaults to False so presentation generation is
                opt-in.
            fallback_enabled: Value of
                'presentation_generation.fallback_enabled'. Defaults
                to False, the same baseline every modality defaults
                to -- unlike EP-085's especially firm justification
                (an expensive, multi-minute operation), presentation
                generation is a single, fast call, so this default is
                simply the platform's consistent baseline
                (`EP086_DESIGN.md` Section 13), not a heightened
                duplicate-generation concern. Independent of
                'ai.fallback_enabled'/every other modality's own
                fallback flag.
        """
        self._provider_manager = provider_manager
        self._request_executor = request_executor
        self._enabled = enabled
        self._fallback_enabled = fallback_enabled

    def generate(self, request: PresentationGenerationRequest) -> PresentationGenerationResult:
        """Generate standalone presentation content for `request`.

        No conversation, context, or persistence is involved (this
        module's docstring). `request` is sent to the provider exactly
        as given.

        Args:
            request: The provider-independent presentation-generation
                request.

        Returns:
            A PresentationGenerationResult describing the outcome.
        """
        if not self._enabled:
            return PresentationGenerationResult(
                success=False,
                presentation=None,
                provider_name="",
                model_name="",
                error=_PRESENTATION_GENERATION_DISABLED,
            )

        current = self._provider_manager.get_current()
        if current is None:
            return PresentationGenerationResult(
                success=False,
                presentation=None,
                provider_name="",
                model_name="",
                error=_NO_PROVIDER_SELECTED,
            )

        if not self._provider_manager.is_enabled():
            return PresentationGenerationResult(
                success=False,
                presentation=None,
                provider_name=current.name(),
                model_name="",
                error=_AI_SUBSYSTEM_DISABLED,
            )

        if not current.supports_presentation_generation():
            # A capability mismatch, not a transient failure -- never
            # reaches the executor or the network
            # (`EP086_DESIGN.md` Section 5).
            return PresentationGenerationResult(
                success=False,
                presentation=None,
                provider_name=current.name(),
                model_name="",
                error=f"Provider '{current.name()}' does not support presentation generation.",
            )

        outcome = self._request_executor.execute_presentation(
            current,
            request,
            fallback_enabled=self._fallback_enabled,
        )
        if not outcome.success:
            return PresentationGenerationResult(
                success=False,
                presentation=None,
                provider_name=outcome.initial_provider,
                model_name="",
                error=outcome.error,
            )

        result = outcome.result
        if result is None:
            # PresentationProviderRequestOutcome.success=True always
            # carries a non-None result by construction of
            # `execute_presentation()` -- an explicit guard rather
            # than a bare `assert`, so this invariant is enforced even
            # under Python's `-O` mode (EP-082 STEP 3 hardening
            # precedent, reused by every subsequent generation
            # service).
            return PresentationGenerationResult(
                success=False,
                presentation=None,
                provider_name=outcome.final_provider,
                model_name="",
                error="Internal error: successful outcome carried no result.",
            )
        return PresentationGenerationResult(
            success=True,
            presentation=result.presentation,
            provider_name=outcome.final_provider,
            model_name=result.model,
            error="",
        )
