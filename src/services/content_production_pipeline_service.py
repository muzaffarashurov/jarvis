"""Content Production Pipeline orchestration for EP-087 Content
Production Pipeline.

`ContentProductionPipelineService` is the actual EP-087 deliverable: a
standalone orchestration/composition layer that combines the five
already-built, independent content-generation capabilities --
`TextGenerationService` (EP-082), `ImageGenerationService` (EP-083),
`AudioGenerationService` (EP-084), `VideoGenerationService` (EP-085),
and `PresentationGenerationService` (EP-086) -- into a single,
coherent production request, per `EP087_DESIGN.md`.

Architectural boundary (`EP087_DESIGN.md` Section 3/7/9): this module
is purely an orchestration layer over the five existing services. It
MUST NOT and does not:

    - call `ProviderManager`, `ProviderRequestExecutor`, `AIProvider`,
      or `GeminiProvider` directly (Section 9/14) -- every actual
      generation call is delegated to the matching existing service's
      own public `generate()` method, so there is exactly one place
      in the repository that performs provider selection, capability
      checking, and fallback for each modality;
    - render, assemble, or persist any artifact (no `.pptx`, no image
      files, no video downloads, no document assembly -- Section 7,
      that is EP-076's territory);
    - introduce a second exception hierarchy, a generic workflow
      engine, or a DAG (Section 4/25) -- execution is purely
      sequential, in the fixed order documented below;
    - modify `TextGenerationService`, `ImageGenerationService`,
      `AudioGenerationService`, `VideoGenerationService`, or
      `PresentationGenerationService` in any way.

Owner Decisions implemented (`EP087_DESIGN.md` Section 27, approved
2026):

    - **D1** -- at most one requested step per modality per pipeline
      request (`ContentProductionPipelineRequest` has exactly one
      optional field per modality, never a list/tuple).
    - **D2** -- no cross-step data substitution in v1: each step's
      request is fully caller-supplied before `generate()` is called;
      this service never reads one step's result to build another
      step's request.
    - **D3** -- `ContentProductionPipelineResult.success` means "the
      pipeline completed its dispatch without an internal
      orchestration error", independent of each individual step's own
      `success`/`failure`. Each `PipelineStepResult` carries its own
      independent outcome.
    - **D4** -- fixed execution order: text, then image, then audio,
      then video, then presentation (Section 12) -- hard-coded in
      `generate()` below, never derived from
      `dataclasses.fields()`/the order fields happen to be set on the
      request, so field order can never silently become execution
      order by accident.

Partial-failure semantics (`EP087_DESIGN.md` Section 13/19): steps are
independent in v1 -- a failure in one requested step never prevents
any other independently requested step from still being attempted.
Two failure categories exist:

    - **Per-step failure**: the underlying service's own `generate()`
      call returned `success=False`. Captured verbatim (its `error`
      string) into that step's own `PipelineStepResult` -- this is a
      normal, already-handled outcome for every existing service, not
      a pipeline-level error.
    - **Unexpected per-step exception**: an exception escaping a
      service's `generate()` call that is not that service's own
      normal `success=False` contract (every existing service's own
      tests confirm this should not happen, but defensive code here
      does not assume it never will). Caught locally, per step, and
      converted into that step's own failed `PipelineStepResult`
      rather than allowed to abort the whole pipeline and silently
      skip every subsequent, independent step.

No new configuration is introduced (Section 21): the fixed step
order, the one-step-per-modality limit, and the empty-request
rejection are all deterministic architectural constants, not tunable
operational knobs.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.core.ai.provider import (
    ImageGenerationRequest,
    PresentationGenerationRequest,
    SpeechGenerationRequest,
    VideoGenerationRequest,
)
from src.services.audio_generation_service import (
    AudioGenerationService,
    SpeechGenerationResult,
)
from src.services.image_generation_service import (
    ImageGenerationResult,
    ImageGenerationService,
)
from src.services.presentation_generation_service import (
    PresentationGenerationResult,
    PresentationGenerationService,
)
from src.services.text_generation_service import (
    TextGenerationResult,
    TextGenerationService,
)
from src.services.video_generation_service import (
    VideoGenerationResult,
    VideoGenerationService,
)

__all__ = [
    "ContentProductionPipelineError",
    "ContentProductionPipelineRequest",
    "ContentProductionPipelineResult",
    "ContentProductionPipelineService",
    "PipelineStepResult",
    "TextStepRequest",
]

_EMPTY_REQUEST_ERROR: str = (
    "ContentProductionPipelineRequest must request at least one modality "
    "(text, image, audio, video, or presentation)."
)


class ContentProductionPipelineError(Exception):
    """Raised for a caller-input error to
    `ContentProductionPipelineService.generate()` (EP-087).

    Reserved exclusively for request-shape errors caught before any of
    the five existing services is ever called (`EP087_DESIGN.md`
    Section 18) -- never raised for an individual step's own
    generation failure, which is always reported through that step's
    `PipelineStepResult` instead (Section 19), never as an exception.
    """


@dataclass(frozen=True)
class TextStepRequest:
    """A pipeline request's text step (EP-087).

    Exists solely to give text generation the same "one dataclass per
    step" shape every other modality already has, without changing
    `TextGenerationService.generate()`'s own keyword-argument signature
    (`EP087_DESIGN.md` Section 4/11, Risk in Section 26) --
    `ContentProductionPipelineService` unpacks this dataclass into the
    matching keyword arguments internally.

    Attributes:
        prompt: The final prompt/instruction text to send. Required.
        max_tokens: Optional override for the reply's maximum token
            count. None uses `TextGenerationService`'s own default.
        temperature: Optional per-request override. None uses
            `TextGenerationService`'s own default.
    """

    prompt: str
    max_tokens: int | None = None
    temperature: float | None = None


@dataclass(frozen=True)
class ContentProductionPipelineRequest:
    """A single content-production request spanning up to five modalities (EP-087).

    Every field defaults to `None` ("this modality was not
    requested"). At least one field must be non-`None`
    (`ContentProductionPipelineService.generate()` rejects an
    all-`None` request -- Section 18).

    Per Owner Decision D1, each field holds at most one step -- there
    is no list/tuple field for requesting, e.g., two images in one
    pipeline call; a caller wanting multiple instances of the same
    modality calls the pipeline (or the underlying service) more than
    once.

    Attributes:
        text: The text step to run, or None to skip it.
        image: The image step to run, or None to skip it.
        audio: The audio/speech step to run, or None to skip it.
        video: The video step to run, or None to skip it.
        presentation: The presentation-content step to run, or None to
            skip it.
    """

    text: TextStepRequest | None = None
    image: ImageGenerationRequest | None = None
    audio: SpeechGenerationRequest | None = None
    video: VideoGenerationRequest | None = None
    presentation: PresentationGenerationRequest | None = None


@dataclass(frozen=True)
class PipelineStepResult:
    """The independent outcome of one requested pipeline step (EP-087).

    Attributes:
        modality: Which modality this step ran --
            "text" | "image" | "audio" | "video" | "presentation".
        success: Whether this step's underlying service call produced
            a usable result.
        error: A user-friendly error message, or "" on success.
        text_result: The underlying `TextGenerationResult`, populated
            only when `modality == "text"` and `success` is True; None
            otherwise.
        image_result: The underlying `ImageGenerationResult`,
            populated only when `modality == "image"` and `success` is
            True; None otherwise.
        audio_result: The underlying `SpeechGenerationResult`,
            populated only when `modality == "audio"` and `success` is
            True; None otherwise.
        video_result: The underlying `VideoGenerationResult`,
            populated only when `modality == "video"` and `success` is
            True; None otherwise.
        presentation_result: The underlying
            `PresentationGenerationResult`, populated only when
            `modality == "presentation"` and `success` is True; None
            otherwise.
    """

    modality: str
    success: bool
    error: str
    text_result: TextGenerationResult | None = None
    image_result: ImageGenerationResult | None = None
    audio_result: SpeechGenerationResult | None = None
    video_result: VideoGenerationResult | None = None
    presentation_result: PresentationGenerationResult | None = None


@dataclass(frozen=True)
class ContentProductionPipelineResult:
    """The aggregate result of one `ContentProductionPipelineService.generate()` call (EP-087).

    Attributes:
        steps: Every requested step's independent
            `PipelineStepResult`, in the fixed execution order (text,
            image, audio, video, presentation) -- never including a
            step that was not requested (a `None` field on the
            request produces no corresponding entry here).
        success: Owner Decision D3 -- `True` means the pipeline itself
            completed its dispatch without an internal/orchestration
            error, **independent** of each individual step's own
            `success`/`failure`. This is deliberately not "every
            requested step individually succeeded" -- inspect `steps`
            for that. `False` only if the pipeline's own dispatch
            logic hit a genuine internal error before it could finish
            attempting every requested step.
    """

    steps: tuple[PipelineStepResult, ...]
    success: bool


class ContentProductionPipelineService:
    """Sequential, fixed-order composition of the five content-generation services (EP-087).

    Depends on the five existing service instances directly
    (constructor-injected) -- never on `ProviderManager`/
    `ProviderRequestExecutor`/`AIProvider`/`GeminiProvider`
    (`EP087_DESIGN.md` Section 9). Owns request validation, the fixed
    step order, and result aggregation; owns nothing about *how* any
    individual modality is generated -- every generation call is
    delegated to the matching existing service unchanged.
    """

    def __init__(
        self,
        text_generation_service: TextGenerationService,
        image_generation_service: ImageGenerationService,
        audio_generation_service: AudioGenerationService,
        video_generation_service: VideoGenerationService,
        presentation_generation_service: PresentationGenerationService,
    ) -> None:
        """Initialize the ContentProductionPipelineService.

        Args:
            text_generation_service: The shared `TextGenerationService`
                instance (EP-082) -- never mutated by this service.
            image_generation_service: The shared
                `ImageGenerationService` instance (EP-083) -- never
                mutated by this service.
            audio_generation_service: The shared
                `AudioGenerationService` instance (EP-084) -- never
                mutated by this service.
            video_generation_service: The shared
                `VideoGenerationService` instance (EP-085) -- never
                mutated by this service.
            presentation_generation_service: The shared
                `PresentationGenerationService` instance (EP-086) --
                never mutated by this service.
        """
        self._text_generation_service = text_generation_service
        self._image_generation_service = image_generation_service
        self._audio_generation_service = audio_generation_service
        self._video_generation_service = video_generation_service
        self._presentation_generation_service = presentation_generation_service

    def generate(self, request: ContentProductionPipelineRequest) -> ContentProductionPipelineResult:
        """Run every requested step of `request`, in the fixed order.

        Execution order is always text, then image, then audio, then
        video, then presentation (Owner Decision D4) -- regardless of
        the order fields happen to be set on `request`. A step that
        was not requested (its field is `None`) is never attempted and
        never appears in the returned `steps`.

        No cross-step data substitution occurs (Owner Decision D2):
        each requested step's request object is passed to its
        underlying service exactly as the caller supplied it.

        Args:
            request: The pipeline request describing which modalities
                to generate and with what per-modality parameters.

        Returns:
            A ContentProductionPipelineResult with one
            `PipelineStepResult` per requested step, in execution
            order.

        Raises:
            ContentProductionPipelineError: If `request` requests zero
                modalities (every field is `None`).
        """
        if (
            request.text is None
            and request.image is None
            and request.audio is None
            and request.video is None
            and request.presentation is None
        ):
            raise ContentProductionPipelineError(_EMPTY_REQUEST_ERROR)

        steps: list[PipelineStepResult] = []

        if request.text is not None:
            steps.append(self._run_text_step(request.text))
        if request.image is not None:
            steps.append(self._run_image_step(request.image))
        if request.audio is not None:
            steps.append(self._run_audio_step(request.audio))
        if request.video is not None:
            steps.append(self._run_video_step(request.video))
        if request.presentation is not None:
            steps.append(self._run_presentation_step(request.presentation))

        return ContentProductionPipelineResult(steps=tuple(steps), success=True)

    # ---------- Per-modality step dispatch ----------
    #
    # Each `_run_*_step()` below follows the same shape (`EP087_DESIGN.md`
    # Section 19): call the matching existing service's own `generate()`
    # exactly once; an unexpected exception is caught here and converted
    # into a failed `PipelineStepResult` rather than allowed to escape
    # and abort every subsequent, independent step.

    def _run_text_step(self, step_request: TextStepRequest) -> PipelineStepResult:
        try:
            result = self._text_generation_service.generate(
                step_request.prompt,
                max_tokens=step_request.max_tokens,
                temperature=step_request.temperature,
            )
        except Exception as exc:  # noqa: BLE001 -- defensive orchestration boundary (Section 19)
            return PipelineStepResult(modality="text", success=False, error=str(exc))
        if not result.success:
            return PipelineStepResult(modality="text", success=False, error=result.error)
        return PipelineStepResult(modality="text", success=True, error="", text_result=result)

    def _run_image_step(self, step_request: ImageGenerationRequest) -> PipelineStepResult:
        try:
            result = self._image_generation_service.generate(step_request)
        except Exception as exc:  # noqa: BLE001 -- defensive orchestration boundary (Section 19)
            return PipelineStepResult(modality="image", success=False, error=str(exc))
        if not result.success:
            return PipelineStepResult(modality="image", success=False, error=result.error)
        return PipelineStepResult(modality="image", success=True, error="", image_result=result)

    def _run_audio_step(self, step_request: SpeechGenerationRequest) -> PipelineStepResult:
        try:
            result = self._audio_generation_service.generate(step_request)
        except Exception as exc:  # noqa: BLE001 -- defensive orchestration boundary (Section 19)
            return PipelineStepResult(modality="audio", success=False, error=str(exc))
        if not result.success:
            return PipelineStepResult(modality="audio", success=False, error=result.error)
        return PipelineStepResult(modality="audio", success=True, error="", audio_result=result)

    def _run_video_step(self, step_request: VideoGenerationRequest) -> PipelineStepResult:
        try:
            result = self._video_generation_service.generate(step_request)
        except Exception as exc:  # noqa: BLE001 -- defensive orchestration boundary (Section 19)
            return PipelineStepResult(modality="video", success=False, error=str(exc))
        if not result.success:
            return PipelineStepResult(modality="video", success=False, error=result.error)
        return PipelineStepResult(modality="video", success=True, error="", video_result=result)

    def _run_presentation_step(
        self, step_request: PresentationGenerationRequest
    ) -> PipelineStepResult:
        try:
            result = self._presentation_generation_service.generate(step_request)
        except Exception as exc:  # noqa: BLE001 -- defensive orchestration boundary (Section 19)
            return PipelineStepResult(modality="presentation", success=False, error=str(exc))
        if not result.success:
            return PipelineStepResult(modality="presentation", success=False, error=result.error)
        return PipelineStepResult(
            modality="presentation", success=True, error="", presentation_result=result
        )
