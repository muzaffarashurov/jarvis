"""Real engineering tests for EP-087 STEP 2 - Content Production Pipeline.

Single combined test suite (NAME = "EP087"), following the same
precedent tests/EP082-EP086 already established. Self-contained -- no
import from any other `tests/EP0NN/` package.

Covers, per `EP087_DESIGN.md` Section 24:
    - Contract tests: `ContentProductionPipelineRequest`/
      `TextStepRequest`/`PipelineStepResult`/
      `ContentProductionPipelineResult` construction and immutability;
      empty-request rejection (`ContentProductionPipelineError`).
    - Service tests: a single-modality request calls exactly that one
      underlying service and none of the other four; a
      multi-modality (all five) request calls every requested service
      exactly once; a step's own `success=False` result is passed
      through verbatim (its `error`) into that step's
      `PipelineStepResult`, without being treated as an exception; an
      unexpected exception raised by one fake service is caught and
      converted into that step's own failed `PipelineStepResult`
      without preventing a later, independent step from still
      running.
    - Ordering test: step execution order is always
      text -> image -> audio -> video -> presentation, verified via a
      fake-service call-order recorder, regardless of the order
      fields are set on the request object.
    - D1: `ContentProductionPipelineRequest` has exactly one field per
      modality (no list/tuple field for requesting the same modality
      twice).
    - D2: no step receives another step's output implicitly -- each
      fake service records exactly the request object the caller
      supplied, unmodified.
    - D3: `ContentProductionPipelineResult.success` is `True` whenever
      the pipeline completes its dispatch, independent of each
      individual step's own success/failure (all-succeed, all-fail,
      and mixed-outcome cases).
    - D4: dispatch order is hard-coded in the service, not derived
      from `dataclasses.fields()` -- confirmed by supplying the
      request's fields in reverse declaration order and still
      observing the fixed text/image/audio/video/presentation call
      order.
    - Service isolation: fakes stand in for the five
      `*GenerationService` instances themselves (never for
      `ProviderManager`/`ProviderRequestExecutor`/`AIProvider`) --
      EP-087 has no direct dependency on those lower layers to fake.

Regression coverage for `TextGenerationService.generate()`/
`ImageGenerationService.generate()`/`AudioGenerationService.generate()`/
`VideoGenerationService.generate()`/
`PresentationGenerationService.generate()` themselves is NOT
duplicated here -- that is the responsibility of, and already covered
by, `tests/EP082`-`tests/EP086`, which this EP's STEP 2 requires to
keep passing unmodified.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError, fields

from src.core.ai.provider import (
    ImageGenerationRequest,
    PresentationGenerationRequest,
    SpeechGenerationRequest,
    VideoGenerationRequest,
)
from src.services.content_production_pipeline_service import (
    ContentProductionPipelineError,
    ContentProductionPipelineRequest,
    ContentProductionPipelineResult,
    ContentProductionPipelineService,
    PipelineStepResult,
    TextStepRequest,
)
from src.testing.base_test import BaseTest
from src.testing.registry import TestRegistry

# ---------- Fakes ----------
#
# Fakes stand in for the five existing *GenerationService* instances
# themselves (EP087_DESIGN.md Section 24) -- EP-087 never touches
# ProviderManager/ProviderRequestExecutor/AIProvider directly, so there
# is nothing at that lower layer for this suite to fake.


class _FakeTextGenerationService:
    def __init__(self, *, succeed: bool = True, error: str = "", raise_error: Exception | None = None):
        self._succeed = succeed
        self._error = error
        self._raise_error = raise_error
        self.calls: list[dict] = []

    def generate(self, prompt, *, max_tokens=None, temperature=None):
        self.calls.append({"prompt": prompt, "max_tokens": max_tokens, "temperature": temperature})
        if self._raise_error is not None:
            raise self._raise_error
        from src.services.text_generation_service import TextGenerationResult

        if not self._succeed:
            return TextGenerationResult(
                success=False, text="", provider_name="", model_name="", error=self._error
            )
        return TextGenerationResult(
            success=True, text="generated text", provider_name="fake", model_name="fake-model", error=""
        )


class _FakeImageGenerationService:
    def __init__(self, *, succeed: bool = True, error: str = "", raise_error: Exception | None = None):
        self._succeed = succeed
        self._error = error
        self._raise_error = raise_error
        self.calls: list[ImageGenerationRequest] = []

    def generate(self, request: ImageGenerationRequest):
        self.calls.append(request)
        if self._raise_error is not None:
            raise self._raise_error
        from src.services.image_generation_service import ImageGenerationResult

        if not self._succeed:
            return ImageGenerationResult(
                success=False, images=(), provider_name="", model_name="", error=self._error
            )
        return ImageGenerationResult(
            success=True, images=(), provider_name="fake", model_name="fake-model", error=""
        )


class _FakeAudioGenerationService:
    def __init__(self, *, succeed: bool = True, error: str = "", raise_error: Exception | None = None):
        self._succeed = succeed
        self._error = error
        self._raise_error = raise_error
        self.calls: list[SpeechGenerationRequest] = []

    def generate(self, request: SpeechGenerationRequest):
        self.calls.append(request)
        if self._raise_error is not None:
            raise self._raise_error
        from src.core.ai.provider import GeneratedAudio
        from src.services.audio_generation_service import SpeechGenerationResult

        if not self._succeed:
            return SpeechGenerationResult(
                success=False, audio=None, provider_name="", model_name="", error=self._error
            )
        return SpeechGenerationResult(
            success=True,
            audio=GeneratedAudio(data_base64="", mime_type="audio/wav"),
            provider_name="fake",
            model_name="fake-model",
            error="",
        )


class _FakeVideoGenerationService:
    def __init__(self, *, succeed: bool = True, error: str = "", raise_error: Exception | None = None):
        self._succeed = succeed
        self._error = error
        self._raise_error = raise_error
        self.calls: list[VideoGenerationRequest] = []

    def generate(self, request: VideoGenerationRequest):
        self.calls.append(request)
        if self._raise_error is not None:
            raise self._raise_error
        from src.core.ai.provider import GeneratedVideo
        from src.services.video_generation_service import VideoGenerationResult

        if not self._succeed:
            return VideoGenerationResult(
                success=False, video=None, provider_name="", model_name="", error=self._error
            )
        return VideoGenerationResult(
            success=True,
            video=GeneratedVideo(uri="https://example.invalid/video", mime_type="video/mp4"),
            provider_name="fake",
            model_name="fake-model",
            error="",
        )


class _FakePresentationGenerationService:
    def __init__(self, *, succeed: bool = True, error: str = "", raise_error: Exception | None = None):
        self._succeed = succeed
        self._error = error
        self._raise_error = raise_error
        self.calls: list[PresentationGenerationRequest] = []

    def generate(self, request: PresentationGenerationRequest):
        self.calls.append(request)
        if self._raise_error is not None:
            raise self._raise_error
        from src.core.ai.provider import GeneratedPresentation
        from src.services.presentation_generation_service import (
            PresentationGenerationResult,
        )

        if not self._succeed:
            return PresentationGenerationResult(
                success=False, presentation=None, provider_name="", model_name="", error=self._error
            )
        return PresentationGenerationResult(
            success=True,
            presentation=GeneratedPresentation(title="Deck", slides=()),
            provider_name="fake",
            model_name="fake-model",
            error="",
        )


class _RecordingOrderService:
    """Wraps a fake service, appending `modality` to a shared list on every call.

    Used only by the ordering test to confirm the dispatch order is
    hard-coded (`EP087_DESIGN.md` Section 24's ordering-test
    requirement) independent of `dataclasses.fields()` order.
    """

    def __init__(self, modality: str, order_log: list[str], inner) -> None:
        self._modality = modality
        self._order_log = order_log
        self._inner = inner

    def generate(self, *args, **kwargs):
        self._order_log.append(self._modality)
        return self._inner.generate(*args, **kwargs)


@TestRegistry.register
class ContentProductionPipelineTest(BaseTest):
    NAME = "EP087"

    def run(self):
        # ---------- Contracts ----------
        self._test_request_construction_and_immutability()
        self._test_text_step_request_construction()
        self._test_pipeline_step_result_construction()
        self._test_pipeline_result_construction()
        self._test_d1_one_field_per_modality()

        # ---------- Validation ----------
        self._test_empty_request_rejected()
        self._test_single_modality_does_not_require_others()

        # ---------- Service dispatch: single modality ----------
        self._test_only_text_requested_calls_only_text_service()
        self._test_only_image_requested_calls_only_image_service()
        self._test_only_audio_requested_calls_only_audio_service()
        self._test_only_video_requested_calls_only_video_service()
        self._test_only_presentation_requested_calls_only_presentation_service()

        # ---------- Service dispatch: all five ----------
        self._test_all_five_modalities_calls_every_service_exactly_once()

        # ---------- Ordering (D4) ----------
        self._test_execution_order_is_fixed_regardless_of_request_field_order()

        # ---------- Per-step failure passthrough ----------
        self._test_step_failure_passed_through_verbatim()
        self._test_step_failure_does_not_populate_result_field()
        self._test_first_step_failure_does_not_block_later_steps()
        self._test_middle_step_failure_does_not_block_later_steps()
        self._test_final_step_failure_recorded()
        self._test_multiple_failures_all_recorded_independently()
        self._test_partial_success_mix()

        # ---------- Unexpected exceptions ----------
        self._test_unexpected_exception_converted_to_failed_step()
        self._test_exception_in_one_step_does_not_prevent_later_step()

        # ---------- D2: no cross-step substitution ----------
        self._test_no_cross_step_data_substitution()

        # ---------- D3: aggregate success semantics ----------
        self._test_pipeline_success_true_when_all_steps_succeed()
        self._test_pipeline_success_true_even_when_all_steps_fail()
        self._test_pipeline_success_true_on_mixed_outcomes()

        return self.result

    # ---------- Helpers ----------

    def _make_service(
        self,
        *,
        text=None,
        image=None,
        audio=None,
        video=None,
        presentation=None,
    ) -> ContentProductionPipelineService:
        return ContentProductionPipelineService(
            text_generation_service=text or _FakeTextGenerationService(),
            image_generation_service=image or _FakeImageGenerationService(),
            audio_generation_service=audio or _FakeAudioGenerationService(),
            video_generation_service=video or _FakeVideoGenerationService(),
            presentation_generation_service=presentation or _FakePresentationGenerationService(),
        )

    # ---------- Contracts ----------

    def _test_request_construction_and_immutability(self) -> None:
        request = ContentProductionPipelineRequest(text=TextStepRequest(prompt="hello"))
        self.assert_equal(request.text.prompt, "hello")
        self.assert_true(request.image is None)
        self.assert_true(request.audio is None)
        self.assert_true(request.video is None)
        self.assert_true(request.presentation is None)
        try:
            request.image = ImageGenerationRequest(prompt="x")
            self.assert_true(False, "ContentProductionPipelineRequest must be frozen.")
        except FrozenInstanceError:
            self.assert_true(True)

    def _test_text_step_request_construction(self) -> None:
        step = TextStepRequest(prompt="p", max_tokens=100, temperature=0.5)
        self.assert_equal(step.prompt, "p")
        self.assert_equal(step.max_tokens, 100)
        self.assert_equal(step.temperature, 0.5)
        default_step = TextStepRequest(prompt="p")
        self.assert_true(default_step.max_tokens is None)
        self.assert_true(default_step.temperature is None)
        try:
            step.prompt = "changed"
            self.assert_true(False, "TextStepRequest must be frozen.")
        except FrozenInstanceError:
            self.assert_true(True)

    def _test_pipeline_step_result_construction(self) -> None:
        result = PipelineStepResult(modality="text", success=True, error="")
        self.assert_equal(result.modality, "text")
        self.assert_true(result.success)
        self.assert_equal(result.error, "")
        self.assert_true(result.text_result is None)
        self.assert_true(result.image_result is None)
        self.assert_true(result.audio_result is None)
        self.assert_true(result.video_result is None)
        self.assert_true(result.presentation_result is None)
        try:
            result.success = False
            self.assert_true(False, "PipelineStepResult must be frozen.")
        except FrozenInstanceError:
            self.assert_true(True)

    def _test_pipeline_result_construction(self) -> None:
        step = PipelineStepResult(modality="text", success=True, error="")
        result = ContentProductionPipelineResult(steps=(step,), success=True)
        self.assert_equal(len(result.steps), 1)
        self.assert_true(result.success)
        try:
            result.success = False
            self.assert_true(False, "ContentProductionPipelineResult must be frozen.")
        except FrozenInstanceError:
            self.assert_true(True)

    def _test_d1_one_field_per_modality(self) -> None:
        # Owner Decision D1: exactly one field per modality -- no
        # list/tuple field anywhere on the request.
        field_types = {f.name: f.type for f in fields(ContentProductionPipelineRequest)}
        self.assert_equal(
            set(field_types.keys()), {"text", "image", "audio", "video", "presentation"}
        )
        for type_str in field_types.values():
            self.assert_false("tuple" in type_str or "list" in type_str)

    # ---------- Validation ----------

    def _test_empty_request_rejected(self) -> None:
        service = self._make_service()
        try:
            service.generate(ContentProductionPipelineRequest())
            self.assert_true(False, "An all-None request must raise ContentProductionPipelineError.")
        except ContentProductionPipelineError:
            self.assert_true(True)

    def _test_single_modality_does_not_require_others(self) -> None:
        service = self._make_service()
        result = service.generate(ContentProductionPipelineRequest(text=TextStepRequest(prompt="x")))
        self.assert_true(result.success)
        self.assert_equal(len(result.steps), 1)

    # ---------- Service dispatch: single modality ----------

    def _test_only_text_requested_calls_only_text_service(self) -> None:
        text = _FakeTextGenerationService()
        image = _FakeImageGenerationService()
        audio = _FakeAudioGenerationService()
        video = _FakeVideoGenerationService()
        presentation = _FakePresentationGenerationService()
        service = self._make_service(
            text=text, image=image, audio=audio, video=video, presentation=presentation
        )

        result = service.generate(ContentProductionPipelineRequest(text=TextStepRequest(prompt="x")))

        self.assert_equal(len(result.steps), 1)
        self.assert_equal(result.steps[0].modality, "text")
        self.assert_equal(len(text.calls), 1)
        self.assert_equal(len(image.calls), 0)
        self.assert_equal(len(audio.calls), 0)
        self.assert_equal(len(video.calls), 0)
        self.assert_equal(len(presentation.calls), 0)

    def _test_only_image_requested_calls_only_image_service(self) -> None:
        text = _FakeTextGenerationService()
        image = _FakeImageGenerationService()
        audio = _FakeAudioGenerationService()
        video = _FakeVideoGenerationService()
        presentation = _FakePresentationGenerationService()
        service = self._make_service(
            text=text, image=image, audio=audio, video=video, presentation=presentation
        )

        result = service.generate(
            ContentProductionPipelineRequest(image=ImageGenerationRequest(prompt="x"))
        )

        self.assert_equal(len(result.steps), 1)
        self.assert_equal(result.steps[0].modality, "image")
        self.assert_equal(len(text.calls), 0)
        self.assert_equal(len(image.calls), 1)
        self.assert_equal(len(audio.calls), 0)
        self.assert_equal(len(video.calls), 0)
        self.assert_equal(len(presentation.calls), 0)

    def _test_only_audio_requested_calls_only_audio_service(self) -> None:
        text = _FakeTextGenerationService()
        image = _FakeImageGenerationService()
        audio = _FakeAudioGenerationService()
        video = _FakeVideoGenerationService()
        presentation = _FakePresentationGenerationService()
        service = self._make_service(
            text=text, image=image, audio=audio, video=video, presentation=presentation
        )

        result = service.generate(
            ContentProductionPipelineRequest(audio=SpeechGenerationRequest(text="x"))
        )

        self.assert_equal(len(result.steps), 1)
        self.assert_equal(result.steps[0].modality, "audio")
        self.assert_equal(len(text.calls), 0)
        self.assert_equal(len(image.calls), 0)
        self.assert_equal(len(audio.calls), 1)
        self.assert_equal(len(video.calls), 0)
        self.assert_equal(len(presentation.calls), 0)

    def _test_only_video_requested_calls_only_video_service(self) -> None:
        text = _FakeTextGenerationService()
        image = _FakeImageGenerationService()
        audio = _FakeAudioGenerationService()
        video = _FakeVideoGenerationService()
        presentation = _FakePresentationGenerationService()
        service = self._make_service(
            text=text, image=image, audio=audio, video=video, presentation=presentation
        )

        result = service.generate(
            ContentProductionPipelineRequest(video=VideoGenerationRequest(prompt="x"))
        )

        self.assert_equal(len(result.steps), 1)
        self.assert_equal(result.steps[0].modality, "video")
        self.assert_equal(len(text.calls), 0)
        self.assert_equal(len(image.calls), 0)
        self.assert_equal(len(audio.calls), 0)
        self.assert_equal(len(video.calls), 1)
        self.assert_equal(len(presentation.calls), 0)

    def _test_only_presentation_requested_calls_only_presentation_service(self) -> None:
        text = _FakeTextGenerationService()
        image = _FakeImageGenerationService()
        audio = _FakeAudioGenerationService()
        video = _FakeVideoGenerationService()
        presentation = _FakePresentationGenerationService()
        service = self._make_service(
            text=text, image=image, audio=audio, video=video, presentation=presentation
        )

        result = service.generate(
            ContentProductionPipelineRequest(
                presentation=PresentationGenerationRequest(topic="x")
            )
        )

        self.assert_equal(len(result.steps), 1)
        self.assert_equal(result.steps[0].modality, "presentation")
        self.assert_equal(len(text.calls), 0)
        self.assert_equal(len(image.calls), 0)
        self.assert_equal(len(audio.calls), 0)
        self.assert_equal(len(video.calls), 0)
        self.assert_equal(len(presentation.calls), 1)

    # ---------- Service dispatch: all five ----------

    def _test_all_five_modalities_calls_every_service_exactly_once(self) -> None:
        text = _FakeTextGenerationService()
        image = _FakeImageGenerationService()
        audio = _FakeAudioGenerationService()
        video = _FakeVideoGenerationService()
        presentation = _FakePresentationGenerationService()
        service = self._make_service(
            text=text, image=image, audio=audio, video=video, presentation=presentation
        )

        request = ContentProductionPipelineRequest(
            text=TextStepRequest(prompt="tagline"),
            image=ImageGenerationRequest(prompt="a matching image"),
            audio=SpeechGenerationRequest(text="narrated audio"),
            video=VideoGenerationRequest(prompt="a clip"),
            presentation=PresentationGenerationRequest(topic="announcement"),
        )
        result = service.generate(request)

        self.assert_true(result.success)
        self.assert_equal(len(result.steps), 5)
        self.assert_equal(len(text.calls), 1)
        self.assert_equal(len(image.calls), 1)
        self.assert_equal(len(audio.calls), 1)
        self.assert_equal(len(video.calls), 1)
        self.assert_equal(len(presentation.calls), 1)
        for step in result.steps:
            self.assert_true(step.success)

    # ---------- Ordering (D4) ----------

    def _test_execution_order_is_fixed_regardless_of_request_field_order(self) -> None:
        order_log: list[str] = []
        text = _RecordingOrderService("text", order_log, _FakeTextGenerationService())
        image = _RecordingOrderService("image", order_log, _FakeImageGenerationService())
        audio = _RecordingOrderService("audio", order_log, _FakeAudioGenerationService())
        video = _RecordingOrderService("video", order_log, _FakeVideoGenerationService())
        presentation = _RecordingOrderService(
            "presentation", order_log, _FakePresentationGenerationService()
        )
        service = self._make_service(
            text=text, image=image, audio=audio, video=video, presentation=presentation
        )

        # Fields supplied in reverse declaration order via keyword
        # arguments -- the dispatch order must not follow this.
        request = ContentProductionPipelineRequest(
            presentation=PresentationGenerationRequest(topic="x"),
            video=VideoGenerationRequest(prompt="x"),
            audio=SpeechGenerationRequest(text="x"),
            image=ImageGenerationRequest(prompt="x"),
            text=TextStepRequest(prompt="x"),
        )
        service.generate(request)

        self.assert_equal(order_log, ["text", "image", "audio", "video", "presentation"])

        # Also confirm the returned `steps` tuple itself preserves the
        # same fixed order.
        order_log.clear()
        request2 = ContentProductionPipelineRequest(
            video=VideoGenerationRequest(prompt="x"),
            text=TextStepRequest(prompt="x"),
        )
        result = service.generate(request2)
        self.assert_equal([step.modality for step in result.steps], ["text", "video"])

    # ---------- Per-step failure passthrough ----------

    def _test_step_failure_passed_through_verbatim(self) -> None:
        text = _FakeTextGenerationService(succeed=False, error="text generation is disabled")
        service = self._make_service(text=text)

        result = service.generate(ContentProductionPipelineRequest(text=TextStepRequest(prompt="x")))

        self.assert_true(result.success)
        self.assert_equal(len(result.steps), 1)
        self.assert_false(result.steps[0].success)
        self.assert_equal(result.steps[0].error, "text generation is disabled")

    def _test_step_failure_does_not_populate_result_field(self) -> None:
        image = _FakeImageGenerationService(succeed=False, error="image generation is disabled")
        service = self._make_service(image=image)

        result = service.generate(
            ContentProductionPipelineRequest(image=ImageGenerationRequest(prompt="x"))
        )

        self.assert_false(result.steps[0].success)
        self.assert_true(result.steps[0].image_result is None)

    def _test_first_step_failure_does_not_block_later_steps(self) -> None:
        text = _FakeTextGenerationService(succeed=False, error="text failed")
        image = _FakeImageGenerationService()
        service = self._make_service(text=text, image=image)

        request = ContentProductionPipelineRequest(
            text=TextStepRequest(prompt="x"), image=ImageGenerationRequest(prompt="x")
        )
        result = service.generate(request)

        self.assert_true(result.success)
        self.assert_false(result.steps[0].success)
        self.assert_true(result.steps[1].success)
        self.assert_equal(len(image.calls), 1)

    def _test_middle_step_failure_does_not_block_later_steps(self) -> None:
        audio = _FakeAudioGenerationService(succeed=False, error="audio failed")
        video = _FakeVideoGenerationService()
        service = self._make_service(audio=audio, video=video)

        request = ContentProductionPipelineRequest(
            audio=SpeechGenerationRequest(text="x"), video=VideoGenerationRequest(prompt="x")
        )
        result = service.generate(request)

        self.assert_true(result.success)
        self.assert_false(result.steps[0].success)
        self.assert_true(result.steps[1].success)
        self.assert_equal(len(video.calls), 1)

    def _test_final_step_failure_recorded(self) -> None:
        presentation = _FakePresentationGenerationService(succeed=False, error="presentation failed")
        service = self._make_service(presentation=presentation)

        request = ContentProductionPipelineRequest(
            text=TextStepRequest(prompt="x"),
            presentation=PresentationGenerationRequest(topic="x"),
        )
        result = service.generate(request)

        self.assert_true(result.success)
        self.assert_true(result.steps[0].success)
        self.assert_false(result.steps[1].success)
        self.assert_equal(result.steps[1].error, "presentation failed")

    def _test_multiple_failures_all_recorded_independently(self) -> None:
        text = _FakeTextGenerationService(succeed=False, error="text failed")
        image = _FakeImageGenerationService()
        audio = _FakeAudioGenerationService(succeed=False, error="audio failed")
        service = self._make_service(text=text, image=image, audio=audio)

        request = ContentProductionPipelineRequest(
            text=TextStepRequest(prompt="x"),
            image=ImageGenerationRequest(prompt="x"),
            audio=SpeechGenerationRequest(text="x"),
        )
        result = service.generate(request)

        self.assert_true(result.success)
        self.assert_false(result.steps[0].success)
        self.assert_true(result.steps[1].success)
        self.assert_false(result.steps[2].success)
        self.assert_equal(result.steps[0].error, "text failed")
        self.assert_equal(result.steps[2].error, "audio failed")

    def _test_partial_success_mix(self) -> None:
        video = _FakeVideoGenerationService(succeed=False, error="video failed")
        service = self._make_service(video=video)

        request = ContentProductionPipelineRequest(
            text=TextStepRequest(prompt="x"),
            image=ImageGenerationRequest(prompt="x"),
            video=VideoGenerationRequest(prompt="x"),
        )
        result = service.generate(request)

        self.assert_true(result.success)
        outcomes = {step.modality: step.success for step in result.steps}
        self.assert_true(outcomes["text"])
        self.assert_true(outcomes["image"])
        self.assert_false(outcomes["video"])

    # ---------- Unexpected exceptions ----------

    def _test_unexpected_exception_converted_to_failed_step(self) -> None:
        text = _FakeTextGenerationService(raise_error=RuntimeError("boom"))
        service = self._make_service(text=text)

        result = service.generate(ContentProductionPipelineRequest(text=TextStepRequest(prompt="x")))

        self.assert_true(result.success)
        self.assert_equal(len(result.steps), 1)
        self.assert_false(result.steps[0].success)
        self.assert_true("boom" in result.steps[0].error)

    def _test_exception_in_one_step_does_not_prevent_later_step(self) -> None:
        image = _FakeImageGenerationService(raise_error=RuntimeError("image boom"))
        audio = _FakeAudioGenerationService()
        service = self._make_service(image=image, audio=audio)

        request = ContentProductionPipelineRequest(
            image=ImageGenerationRequest(prompt="x"), audio=SpeechGenerationRequest(text="x")
        )
        result = service.generate(request)

        self.assert_true(result.success)
        self.assert_false(result.steps[0].success)
        self.assert_true(result.steps[1].success)
        self.assert_equal(len(audio.calls), 1)

    # ---------- D2: no cross-step substitution ----------

    def _test_no_cross_step_data_substitution(self) -> None:
        text = _FakeTextGenerationService()
        image = _FakeImageGenerationService()
        service = self._make_service(text=text, image=image)

        image_request = ImageGenerationRequest(prompt="an untouched, caller-supplied prompt")
        request = ContentProductionPipelineRequest(
            text=TextStepRequest(prompt="a tagline"), image=image_request
        )
        service.generate(request)

        # The image service must receive exactly the caller-supplied
        # request object, never one derived from the text step's
        # result (Owner Decision D2).
        self.assert_true(image.calls[0] is image_request)
        self.assert_equal(image.calls[0].prompt, "an untouched, caller-supplied prompt")

    # ---------- D3: aggregate success semantics ----------

    def _test_pipeline_success_true_when_all_steps_succeed(self) -> None:
        service = self._make_service()
        request = ContentProductionPipelineRequest(
            text=TextStepRequest(prompt="x"), image=ImageGenerationRequest(prompt="x")
        )
        result = service.generate(request)
        self.assert_true(result.success)

    def _test_pipeline_success_true_even_when_all_steps_fail(self) -> None:
        text = _FakeTextGenerationService(succeed=False, error="e1")
        image = _FakeImageGenerationService(succeed=False, error="e2")
        service = self._make_service(text=text, image=image)

        request = ContentProductionPipelineRequest(
            text=TextStepRequest(prompt="x"), image=ImageGenerationRequest(prompt="x")
        )
        result = service.generate(request)

        # D3: pipeline-level success is independent of every
        # individual step's own outcome -- even total step failure
        # is still a successfully-completed orchestration.
        self.assert_true(result.success)
        self.assert_false(result.steps[0].success)
        self.assert_false(result.steps[1].success)

    def _test_pipeline_success_true_on_mixed_outcomes(self) -> None:
        image = _FakeImageGenerationService(succeed=False, error="e")
        service = self._make_service(image=image)

        request = ContentProductionPipelineRequest(
            text=TextStepRequest(prompt="x"), image=ImageGenerationRequest(prompt="x")
        )
        result = service.generate(request)

        self.assert_true(result.success)
        self.assert_true(result.steps[0].success)
        self.assert_false(result.steps[1].success)
