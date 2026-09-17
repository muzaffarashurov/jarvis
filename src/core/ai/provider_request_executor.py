"""Shared provider-request execution for EP-082 Text Generation Provider
Integration, EP-083 Image Generation Provider Integration, EP-084
Audio & Speech Generation Integration, EP-085 Video Generation
Provider Integration, and EP-086 Presentation Generation Integration.

`ProviderRequestExecutor` extracts the fallback/retry loop that
`AIService.ask()` (EP-018) previously owned inline, so `AIService`,
`TextGenerationService` (EP-082), `ImageGenerationService` (EP-083),
`AudioGenerationService` (EP-084), `VideoGenerationService` (EP-085),
and now `PresentationGenerationService` (EP-086) can all execute a
provider request with EP-069.1/.2/.3 fallback and cost-aware provider
ordering, without any of them owning a second implementation of that
loop
(`EP082_DESIGN.md` Section 6, 11.2; `EP083_DESIGN.md` Section 8.2,
Owner Decision 1; `EP084_DESIGN.md` Section 13; `EP085_DESIGN.md`
Section 7; `EP086_DESIGN.md` Section 7 -- Rule 3/Rule 4: never
introduce a second implementation of existing functionality).

Responsibility boundaries (`EP082_DESIGN.md` Section 6, Owner Decision
1; unchanged by EP-083/EP-084/EP-085/EP-086) are deliberately narrow
and do not change `ProviderManager`:

    - `ProviderManager` remains the sole owner of provider
      registry/current-provider access, fallback candidate discovery,
      and cost-aware/fallback-order ordering (EP-069.1/.2/.3). Nothing
      in this module changes `ProviderManager`.
    - `ProviderRequestExecutor` (this module) owns only the mechanics
      of *executing* a request against a chosen provider and retrying
      eligible failures against `ProviderManager.list_fallback_
      candidates()`'s ordering -- it holds no provider state of its
      own and makes no selection decisions `ProviderManager` doesn't
      already make.
    - `AIService` continues to own conversation/context/prompt
      orchestration; it calls `execute()` instead of running its own
      inline loop, with its public method signature, `AskResult`
      contract, and all other observable behavior unchanged
      (`EP082_DESIGN.md` Section 19).
    - `TextGenerationService` (EP-082) calls `execute()` directly,
      with no conversation/context/prompt involvement.
    - `ImageGenerationService` (EP-083) calls the additive
      `execute_image()`, with the same non-conversational shape.
    - `AudioGenerationService` (EP-084) calls the additive
      `execute_speech()`, with the same non-conversational shape.
    - `VideoGenerationService` (EP-085) calls the additive
      `execute_video()`, with the same non-conversational shape --
      note that unlike the prior three, a single `execute_video()`
      attempt may take minutes rather than seconds, since
      `generate_video()`'s concrete implementation performs an
      internal initiate-then-poll cycle (`EP085_DESIGN.md` Section
      6). `_run()` itself required no change to accommodate this: it
      already treats `request_fn` as an opaque, blocking call.
    - `PresentationGenerationService` (EP-086) calls the additive
      `execute_presentation()`, with the same non-conversational
      shape -- back to a single, fast, synchronous call like
      `execute()`/`execute_image()`/`execute_speech()`, NOT
      `execute_video()`'s long-running shape
      (`EP086_DESIGN.md` Section 6/12).

EP-083 added `execute_image()` alongside the existing `execute()`
WITHOUT changing `execute()`'s public signature, behavior, or any log
line (`EP083_DESIGN.md` Section 8.2, Owner Decision 1, Option A).
EP-084 added `execute_speech()` the same way, changing neither
`execute()` nor `execute_image()` (`EP084_DESIGN.md` Section 13).
EP-085 added `execute_video()` the same way again, changing none of
the three prior methods (`EP085_DESIGN.md` Section 7). EP-086 adds
`execute_presentation()` the same way once more, changing none of the
four prior methods (`EP086_DESIGN.md` Section 7). All five methods
delegate to a single private `_run()` helper that is generic over
which provider method is invoked (`.ask()` for text,
`.generate_image()` for images, `.generate_speech()` for speech,
`.generate_video()` for video, `.generate_presentation()` for
presentations) and optionally filters fallback candidates by
capability (used by
`execute_image()`/`execute_speech()`/`execute_video()`/
`execute_presentation()`, via
`AIProvider.
supports_image_generation()`/`supports_speech_generation()`/
`supports_video_generation()`/`supports_presentation_generation()` --
`execute()` passes no filter, reproducing its pre-EP-083 behavior
exactly). There remains exactly ONE retry/fallback implementation in
this module.

Fallback eligibility and ordering exactly reproduce EP-069.1/.2/.3's
existing, already-shipped semantics (`EP069_DESIGN.md`,
`EP069_2_DESIGN.md`, `EP069_3_DESIGN.md`): only
`ProviderUnavailableError`, `ProviderNetworkError`,
`ProviderTimeoutError`, and `ProviderRateLimitError` are fallback-
eligible; `ProviderConfigurationError`, `ProviderAuthenticationError`,
and the base `ProviderError` are not, and stop retrying immediately.
This set is intentionally closed here, exactly as it was in
`ai_service.py` before the EP-082 extraction, and is not derived from
exception attributes or broadened by EP-083.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from loguru import logger

from src.core.ai.provider import (
    AIProvider,
    ImageGenerationRequest,
    ImageGenerationResult,
    PresentationGenerationRequest,
    PresentationGenerationResult,
    ProviderError,
    ProviderNetworkError,
    ProviderRateLimitError,
    ProviderResponse,
    ProviderTimeoutError,
    ProviderUnavailableError,
    SpeechGenerationRequest,
    SpeechGenerationResult,
    VideoGenerationRequest,
    VideoGenerationResult,
)
from src.core.ai.provider_manager import ProviderManager

__all__ = [
    "ImageProviderRequestOutcome",
    "PresentationProviderRequestOutcome",
    "ProviderRequestExecutor",
    "ProviderRequestOutcome",
    "SpeechProviderRequestOutcome",
    "VideoProviderRequestOutcome",
]

# Fallback-eligible ProviderError subtypes, unchanged from EP-069.1
# (`EP069_DESIGN.md` Section 15, Owner Decision D4) -- moved here
# verbatim as part of the EP-082 extraction. Only transient/
# provider-availability failures are eligible; a bad credential or
# missing configuration is an operator-visible defect, not a
# transient failure to silently route around. Unchanged by EP-083.
_FALLBACK_ELIGIBLE_ERRORS: tuple[type[ProviderError], ...] = (
    ProviderUnavailableError,
    ProviderNetworkError,
    ProviderTimeoutError,
    ProviderRateLimitError,
)


@dataclass(frozen=True)
class ProviderRequestOutcome:
    """Result of `ProviderRequestExecutor.execute()` (EP-082).

    Deliberately provider-level only: no conversation, context, or
    prompt-related field is present, so both `AIService` (which adds
    its own conversation/context handling around this outcome) and
    `TextGenerationService` (which adds none) can build their own
    caller-specific result type from the same underlying execution.

    Attributes:
        success: Whether some provider in the attempt chain produced
            a response.
        initial_provider: Name of the provider `execute()` was asked
            to start with -- the explicitly selected/current provider
            for this request, regardless of whether fallback occurred.
        final_provider: Name of the provider that actually produced
            the response (may differ from `initial_provider` when
            fallback occurred), or "" on failure.
        response: The successful `ProviderResponse`, or None on
            failure.
        error: A user-friendly error message, or "" on success.
    """

    success: bool
    initial_provider: str
    final_provider: str
    response: ProviderResponse | None
    error: str


@dataclass(frozen=True)
class ImageProviderRequestOutcome:
    """Result of `ProviderRequestExecutor.execute_image()` (EP-083).

    Mirrors `ProviderRequestOutcome`'s shape exactly, replacing
    `response: ProviderResponse | None` with
    `result: ImageGenerationResult | None` -- a dedicated type rather
    than a renamed/repurposed field on `ProviderRequestOutcome`, so
    neither outcome type's field name or shape needs to change for the
    other's sake.

    Attributes:
        success: Whether some capable provider in the attempt chain
            produced a result.
        initial_provider: Name of the provider `execute_image()` was
            asked to start with, regardless of whether fallback
            occurred.
        final_provider: Name of the provider that actually produced
            `result` (may differ from `initial_provider` when
            fallback occurred), or "" on failure.
        result: The successful `ImageGenerationResult`, or None on
            failure.
        error: A user-friendly error message, or "" on success.
    """

    success: bool
    initial_provider: str
    final_provider: str
    result: ImageGenerationResult | None
    error: str


@dataclass(frozen=True)
class SpeechProviderRequestOutcome:
    """Result of `ProviderRequestExecutor.execute_speech()` (EP-084).

    Mirrors `ImageProviderRequestOutcome`'s shape exactly, replacing
    `result: ImageGenerationResult | None` with
    `result: SpeechGenerationResult | None` -- a dedicated type rather
    than a renamed/repurposed field on either existing outcome type,
    so neither outcome type's field name or shape needs to change for
    the other's sake.

    Attributes:
        success: Whether some capable provider in the attempt chain
            produced a result.
        initial_provider: Name of the provider `execute_speech()` was
            asked to start with, regardless of whether fallback
            occurred.
        final_provider: Name of the provider that actually produced
            `result` (may differ from `initial_provider` when
            fallback occurred), or "" on failure.
        result: The successful `SpeechGenerationResult`, or None on
            failure.
        error: A user-friendly error message, or "" on success.
    """

    success: bool
    initial_provider: str
    final_provider: str
    result: SpeechGenerationResult | None
    error: str


@dataclass(frozen=True)
class VideoProviderRequestOutcome:
    """Result of `ProviderRequestExecutor.execute_video()` (EP-085).

    Mirrors `SpeechProviderRequestOutcome`'s shape exactly.

    Attributes:
        success: Whether some capable provider in the attempt chain
            produced a result.
        initial_provider: Name of the provider `execute_video()` was
            asked to start with, regardless of whether fallback
            occurred.
        final_provider: Name of the provider that actually produced
            `result` (may differ from `initial_provider` when
            fallback occurred), or "" on failure.
        result: The successful `VideoGenerationResult`, or None on
            failure.
        error: A user-friendly error message, or "" on success.
    """

    success: bool
    initial_provider: str
    final_provider: str
    result: VideoGenerationResult | None
    error: str


@dataclass(frozen=True)
class PresentationProviderRequestOutcome:
    """Result of `ProviderRequestExecutor.execute_presentation()` (EP-086).

    Mirrors `SpeechProviderRequestOutcome`'s/`VideoProviderRequestOutcome`'s
    shape exactly.

    Attributes:
        success: Whether some capable provider in the attempt chain
            produced a result.
        initial_provider: Name of the provider `execute_presentation()`
            was asked to start with, regardless of whether fallback
            occurred.
        final_provider: Name of the provider that actually produced
            `result` (may differ from `initial_provider` when
            fallback occurred), or "" on failure.
        result: The successful `PresentationGenerationResult`, or None
            on failure.
        error: A user-friendly error message, or "" on success.
    """

    success: bool
    initial_provider: str
    final_provider: str
    result: PresentationGenerationResult | None
    error: str


@dataclass(frozen=True)
class _RunResult:
    """Internal, generic outcome of `ProviderRequestExecutor._run()` (EP-083).

    Not part of this module's public surface (`__all__`) -- `execute()`
    and `execute_image()` each translate this into their own public,
    strongly-typed outcome type.
    """

    success: bool
    initial_provider: str
    final_provider: str
    value: object
    error: str


class ProviderRequestExecutor:
    """Executes a provider request with EP-069.1/.2/.3 fallback semantics.

    Holds no provider-selection state of its own: every call re-reads
    `ProviderManager.list_fallback_candidates()` fresh, exactly as
    `AIService.ask()` did before the EP-082 extraction, so eligibility
    and ordering can never go stale relative to provider
    registration/removal.
    """

    def __init__(self, provider_manager: ProviderManager) -> None:
        """Initialize the ProviderRequestExecutor.

        Args:
            provider_manager: The ProviderManager used to discover
                fallback candidates when the initial provider fails.
                This executor never calls `get_current()` or
                `set_current()` on it -- the caller supplies the
                provider to start with (`execute()`/`execute_image()`),
                so a fallback occurring mid-request never changes
                which provider is "current" for the next fresh
                request (EP-069.1 Owner Decision D1, preserved
                unchanged).
        """
        self._provider_manager = provider_manager

    def execute(
        self,
        provider: AIProvider,
        prompt: str,
        *,
        fallback_enabled: bool,
        max_tokens: int | None = None,
        temperature: float | None = None,
        system_prompt: str | None = None,
    ) -> ProviderRequestOutcome:
        """Send `prompt` to `provider`, retrying eligible failures via fallback.

        Reproduces `AIService.ask()`'s pre-EP-082 retry loop exactly:
        attempt `provider`; on a fallback-eligible `ProviderError`,
        and only when `fallback_enabled` is True, retry the next
        candidate from `ProviderManager.list_fallback_candidates()`
        (excluding every provider already attempted) until one
        succeeds or every eligible candidate has been tried. A
        non-eligible failure, or `fallback_enabled=False`, fails
        immediately with zero fallback candidates queried -- byte-
        identical to pre-EP-069.1 behavior. This method's public
        signature and behavior are unchanged by EP-083
        (`EP083_DESIGN.md` Section 8.2, Owner Decision 1): internally
        it now delegates to `_run()`, passing no `capability_filter`,
        which reproduces exactly what "no filtering" already meant.

        `max_tokens`/`temperature`/`system_prompt` are only passed to
        `provider.ask()` when not None, so a caller that omits them
        (e.g. `AIService.ask()`, which has no per-request concept of
        either) calls `provider.ask(prompt)` exactly as before this
        extraction -- preserving compatibility with any `AIProvider`
        implementation (including test fakes) that does not yet
        accept the EP-082 `temperature`/`system_prompt` parameters.

        Args:
            provider: The provider to attempt first (the caller's
                "current"/explicitly selected provider for this
                request).
            prompt: The final, already-rendered prompt to send.
            fallback_enabled: Whether a fallback-eligible failure may
                be retried against another candidate. Independent per
                caller (`AIService` uses 'ai.fallback_enabled';
                `TextGenerationService` uses
                'content_generation.fallback_enabled').
            max_tokens: Optional override forwarded to `provider.ask()`
                only when not None.
            temperature: Optional override forwarded to
                `provider.ask()` only when not None (EP-082).
            system_prompt: Optional override forwarded to
                `provider.ask()` only when not None (EP-082).

        Returns:
            A ProviderRequestOutcome describing the final result.
        """
        extra_kwargs: dict[str, object] = {}
        if max_tokens is not None:
            extra_kwargs["max_tokens"] = max_tokens
        if temperature is not None:
            extra_kwargs["temperature"] = temperature
        if system_prompt is not None:
            extra_kwargs["system_prompt"] = system_prompt

        def request_fn(candidate: AIProvider) -> ProviderResponse:
            return candidate.ask(prompt, **extra_kwargs)

        run_result = self._run(provider, request_fn, fallback_enabled=fallback_enabled)
        return ProviderRequestOutcome(
            success=run_result.success,
            initial_provider=run_result.initial_provider,
            final_provider=run_result.final_provider,
            response=run_result.value,  # type: ignore[arg-type]
            error=run_result.error,
        )

    def execute_image(
        self,
        provider: AIProvider,
        request: ImageGenerationRequest,
        *,
        fallback_enabled: bool,
    ) -> ImageProviderRequestOutcome:
        """Send `request` to `provider`, retrying eligible failures via fallback (EP-083).

        Identical retry/fallback semantics to `execute()` (same
        `_run()` helper, same fallback-eligible exception set, same
        `ProviderManager.list_fallback_candidates()` ordering), with
        one addition: every fallback candidate is filtered through
        `AIProvider.supports_image_generation()` before being
        attempted, so a provider that is merely unavailable is
        retried, but a provider that never supports image generation
        at all is silently skipped rather than attempted and logged
        as a wasted failure (`EP083_DESIGN.md` Section 9, point 6).
        The *initial* `provider` argument is never capability-checked
        here -- that is `ImageGenerationService`'s responsibility
        (`EP083_DESIGN.md` Section 9, point 7), so a request for an
        already-known-incapable current provider fails fast before
        this method is even called.

        Args:
            provider: The provider to attempt first.
            request: The provider-independent image-generation
                request.
            fallback_enabled: Whether a fallback-eligible failure may
                be retried against another image-capable candidate.

        Returns:
            An ImageProviderRequestOutcome describing the final
            result.
        """

        def request_fn(candidate: AIProvider) -> ImageGenerationResult:
            return candidate.generate_image(request)

        run_result = self._run(
            provider,
            request_fn,
            fallback_enabled=fallback_enabled,
            capability_filter=lambda candidate: candidate.supports_image_generation(),
        )
        return ImageProviderRequestOutcome(
            success=run_result.success,
            initial_provider=run_result.initial_provider,
            final_provider=run_result.final_provider,
            result=run_result.value,  # type: ignore[arg-type]
            error=run_result.error,
        )

    def execute_speech(
        self,
        provider: AIProvider,
        request: SpeechGenerationRequest,
        *,
        fallback_enabled: bool,
    ) -> SpeechProviderRequestOutcome:
        """Send `request` to `provider`, retrying eligible failures via fallback (EP-084).

        Identical retry/fallback semantics to `execute()`/
        `execute_image()` (same `_run()` helper, same fallback-eligible
        exception set, same `ProviderManager.list_fallback_
        candidates()` ordering), with one addition: every fallback
        candidate is filtered through `AIProvider.
        supports_speech_generation()` before being attempted, so a
        provider that is merely unavailable is retried, but a provider
        that never supports speech generation at all is silently
        skipped rather than attempted and logged as a wasted failure
        (`EP084_DESIGN.md` Section 13, mirroring `execute_image()`'s
        own `supports_image_generation()` filter exactly). The
        *initial* `provider` argument is never capability-checked
        here -- that is `AudioGenerationService`'s responsibility
        (`EP084_DESIGN.md` Section 14, mirroring
        `ImageGenerationService`'s own precedent), so a request for an
        already-known-incapable current provider fails fast before
        this method is even called.

        Args:
            provider: The provider to attempt first.
            request: The provider-independent speech-generation
                request.
            fallback_enabled: Whether a fallback-eligible failure may
                be retried against another speech-capable candidate.

        Returns:
            A SpeechProviderRequestOutcome describing the final
            result.
        """

        def request_fn(candidate: AIProvider) -> SpeechGenerationResult:
            return candidate.generate_speech(request)

        run_result = self._run(
            provider,
            request_fn,
            fallback_enabled=fallback_enabled,
            capability_filter=lambda candidate: candidate.supports_speech_generation(),
        )
        return SpeechProviderRequestOutcome(
            success=run_result.success,
            initial_provider=run_result.initial_provider,
            final_provider=run_result.final_provider,
            result=run_result.value,  # type: ignore[arg-type]
            error=run_result.error,
        )

    def execute_video(
        self,
        provider: AIProvider,
        request: VideoGenerationRequest,
        *,
        fallback_enabled: bool,
    ) -> VideoProviderRequestOutcome:
        """Send `request` to `provider`, retrying eligible failures via fallback (EP-085).

        Identical retry/fallback semantics and mechanical shape to
        `execute()`/`execute_image()`/`execute_speech()` (same
        `_run()` helper, same fallback-eligible exception set, same
        `ProviderManager.list_fallback_candidates()` ordering), with
        the usual addition: every fallback candidate is filtered
        through `AIProvider.supports_video_generation()` before being
        attempted (`EP085_DESIGN.md` Section 9/13). The *initial*
        `provider` argument is never capability-checked here -- that
        is `VideoGenerationService`'s responsibility, mirroring every
        prior modality's precedent.

        Retry/duplicate-generation note (`EP085_DESIGN.md` Section
        13, STEP 2 Phase 5): `request_fn` below calls the *entire*
        `generate_video()` cycle (initiate + poll + complete) as one
        unit. A fallback retry after a mid-poll failure therefore
        does start a genuinely new video-generation operation on the
        next candidate -- there is no partial-operation resumption.
        This executor does not invent special containment logic for
        that beyond what already exists: `video_generation.
        fallback_enabled` defaults to `false` (Owner Decision context,
        `EP085_DESIGN.md` Section 13), and only fallback-eligible
        exceptions (`_FALLBACK_ELIGIBLE_ERRORS`) trigger any retry at
        all -- a `ProviderConfigurationError` (e.g. missing
        `video_model`) never retries, exactly as for every other
        modality. In the default configuration (`fallback_enabled=
        False`), no retry of any kind occurs, so no duplicate
        generation can occur.

        Args:
            provider: The provider to attempt first.
            request: The provider-independent video-generation
                request.
            fallback_enabled: Whether a fallback-eligible failure may
                be retried against another video-capable candidate.

        Returns:
            A VideoProviderRequestOutcome describing the final
            result.
        """

        def request_fn(candidate: AIProvider) -> VideoGenerationResult:
            return candidate.generate_video(request)

        run_result = self._run(
            provider,
            request_fn,
            fallback_enabled=fallback_enabled,
            capability_filter=lambda candidate: candidate.supports_video_generation(),
        )
        return VideoProviderRequestOutcome(
            success=run_result.success,
            initial_provider=run_result.initial_provider,
            final_provider=run_result.final_provider,
            result=run_result.value,  # type: ignore[arg-type]
            error=run_result.error,
        )

    def execute_presentation(
        self,
        provider: AIProvider,
        request: PresentationGenerationRequest,
        *,
        fallback_enabled: bool,
    ) -> PresentationProviderRequestOutcome:
        """Send `request` to `provider`, retrying eligible failures via fallback (EP-086).

        Identical retry/fallback semantics and mechanical shape to
        `execute()`/`execute_image()`/`execute_speech()` (same `_run()`
        helper, same fallback-eligible exception set, same
        `ProviderManager.list_fallback_candidates()` ordering, single
        fast synchronous call) -- explicitly NOT `execute_video()`'s
        long-running shape, since `generate_presentation()` is a
        single `generateContent` call (`EP086_DESIGN.md` Section 6/12).
        Every fallback candidate is filtered through `AIProvider.
        supports_presentation_generation()` before being attempted.
        The *initial* `provider` argument is never capability-checked
        here -- that is `PresentationGenerationService`'s
        responsibility, mirroring every prior modality's precedent.

        Args:
            provider: The provider to attempt first.
            request: The provider-independent presentation-generation
                request.
            fallback_enabled: Whether a fallback-eligible failure may
                be retried against another presentation-capable
                candidate.

        Returns:
            A PresentationProviderRequestOutcome describing the final
            result.
        """

        def request_fn(candidate: AIProvider) -> PresentationGenerationResult:
            return candidate.generate_presentation(request)

        run_result = self._run(
            provider,
            request_fn,
            fallback_enabled=fallback_enabled,
            capability_filter=lambda candidate: candidate.supports_presentation_generation(),
        )
        return PresentationProviderRequestOutcome(
            success=run_result.success,
            initial_provider=run_result.initial_provider,
            final_provider=run_result.final_provider,
            result=run_result.value,  # type: ignore[arg-type]
            error=run_result.error,
        )

    def _run(
        self,
        provider: AIProvider,
        request_fn: Callable[[AIProvider], object],
        *,
        fallback_enabled: bool,
        capability_filter: Callable[[AIProvider], bool] | None = None,
    ) -> _RunResult:
        """Shared retry/fallback control flow for `execute()`/`execute_image()`/`execute_speech()`/`execute_video()`/`execute_presentation()`.

        This is the single, non-duplicated implementation of EP-069's
        fallback/retry semantics (`EP083_DESIGN.md` Section 8.2, Owner
        Decision 1; `EP084_DESIGN.md` Section 13; `EP085_DESIGN.md`
        Section 7; `EP086_DESIGN.md` Section 7) -- `execute()` passes
        `capability_filter=None` (no filtering, its pre-EP-083
        behavior exactly);
        `execute_image()`/`execute_speech()`/`execute_video()`/
        `execute_presentation()` each pass their own capability check.
        Every log line and every piece of `_FALLBACK_ELIGIBLE_ERRORS`
        classification logic here is identical to what `execute()`
        alone contained before the EP-083 refactor, and is unchanged
        again by EP-084/EP-085/EP-086.

        Args:
            provider: The provider to attempt first.
            request_fn: Called with each attempted provider in turn;
                returns that provider's successful result or raises a
                `ProviderError`. `.ask()`-wrapping for `execute()`,
                `.generate_image()`-wrapping for `execute_image()`,
                `.generate_speech()`-wrapping for `execute_speech()`,
                `.generate_video()`-wrapping for `execute_video()`,
                `.generate_presentation()`-wrapping for
                `execute_presentation()`.
            fallback_enabled: Whether a fallback-eligible failure may
                be retried against another candidate.
            capability_filter: If not None, every fallback candidate
                `ProviderManager.list_fallback_candidates()` returns
                is additionally required to satisfy this predicate
                before being attempted. None means no filtering
                (every returned candidate is attempted, reproducing
                `execute()`'s original, pre-EP-083 behavior exactly).

        Returns:
            A _RunResult describing the final outcome, generic over
            whatever `request_fn` returns on success.
        """
        candidate = provider
        initial_name = provider.name()
        attempted: list[str] = []
        failure_summary: list[str] = []

        while True:
            candidate_name = candidate.name()
            attempted.append(candidate_name)
            try:
                value = request_fn(candidate)
            except ProviderError as exc:
                # `exc` here is always a ProviderError instance whose
                # message is a static, code-authored string, never
                # user-supplied prompt content -- safe to log
                # verbatim, per EP069_DESIGN.md Section 9/11.
                logger.error(f"AI request failed (provider='{candidate_name}'): {exc}")
                failure_summary.append(f"{candidate_name}: {type(exc).__name__}")

                fallback_eligible = fallback_enabled and isinstance(
                    exc, _FALLBACK_ELIGIBLE_ERRORS
                )
                if not fallback_eligible:
                    return _RunResult(
                        success=False,
                        initial_provider=initial_name,
                        final_provider="",
                        value=None,
                        error=str(exc),
                    )

                remaining = self._provider_manager.list_fallback_candidates(exclude=attempted)
                if capability_filter is not None:
                    remaining = [p for p in remaining if capability_filter(p)]
                if not remaining:
                    # Every eligible candidate has been tried (bounded
                    # by construction). Only provider names and
                    # exception class names are aggregated here, never
                    # `str(exc)`, per EP-068's log-redaction precedent.
                    logger.error(
                        "AI request failed on every eligible provider: "
                        f"{', '.join(failure_summary)}."
                    )
                    return _RunResult(
                        success=False,
                        initial_provider=initial_name,
                        final_provider="",
                        value=None,
                        error=f"All providers failed. {'; '.join(failure_summary)}.",
                    )

                next_candidate = remaining[0]
                logger.info(
                    f"AI request falling back from provider='{candidate_name}' "
                    f"to provider='{next_candidate.name()}'."
                )
                candidate = next_candidate
                continue

            return _RunResult(
                success=True,
                initial_provider=initial_name,
                final_provider=candidate.name(),
                value=value,
                error="",
            )

