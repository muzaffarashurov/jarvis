"""Real engineering tests for EP-085 STEP 2 - Video Generation Provider Integration.

Single combined test suite (NAME = "EP085"), following the same
precedent tests/EP082, tests/EP083, and tests/EP084 already
established. Self-contained -- no import from any other
`tests/EP0NN/` package.

Covers, per `EP085_DESIGN.md` Section 17:
    - `AIProvider.supports_video_generation()`/`generate_video()`
      base defaults (False / always raises), confirmed on both
      `ClaudeProvider` and the `ConfigDrivenProvider` placeholders.
    - `ProviderRequestExecutor.execute_video()`: primary success,
      fallback disabled, fallback-eligible retry (skipping
      non-capable candidates), non-eligible immediate failure,
      fallback exhaustion -- mirroring tests/EP084's own
      `_test_executor_speech_*` structure.
    - `VideoGenerationService`: success path, disabled config, no
      provider selected, AI subsystem disabled, current provider
      lacks the capability (fails fast), fallback success,
      non-conversational structural check.
    - `GeminiProvider.generate_video()`/`supports_video_generation()`:
      the full initiate -> poll -> complete lifecycle, mocked at the
      HTTP boundary -- single-poll and multi-poll success, correct
      request body construction, 404, malformed/missing operation
      name, operation-level error, missing/malformed video reference,
      malformed poll response, empty prompt, unconfigured model,
      invalid poll/wait configuration, and a deterministic (mocked
      `time.sleep`) timeout when an operation never completes.
    - Adversarial: the poll loop's sleep interval is exercised without
      ever waiting in real wall-clock time; a repeatedly-"still
      running" operation is confirmed not to be treated as failure or
      success prematurely; and an explicit retry/duplicate-generation
      test confirms that, with `fallback_enabled=False` (the
      approved, deliberate default -- `EP085_DESIGN.md` Section 13),
      a failed video generation is never silently retried/duplicated.

Regression coverage for `execute()`/`execute_image()`/
`execute_speech()` themselves is NOT duplicated here -- that is the
responsibility of, and already covered by, `tests/EP082`,
`tests/EP083`, `tests/EP084`, `tests/EP069`, `tests/EP069_3`, and
`tests/EP069_4`, which this EP's STEP 2 requires to keep passing
unmodified.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from unittest.mock import patch

from src.core.ai.claude_provider import ClaudeProvider
from src.core.ai.provider import (
    AIProvider,
    GeneratedVideo,
    ProviderAuthenticationError,
    ProviderConfigurationError,
    ProviderHealth,
    ProviderResponse,
    ProviderStatus,
    ProviderTimeoutError,
    ProviderUnavailableError,
    VideoGenerationRequest,
    VideoGenerationResult,
)
from src.core.ai.provider_factory import ConfigDrivenProvider
from src.core.ai.provider_request_executor import ProviderRequestExecutor
from src.core.ai.providers.gemini_provider import GeminiProvider
from src.services.video_generation_service import (
    VideoGenerationResult as ServiceVideoGenerationResult,
)
from src.services.video_generation_service import VideoGenerationService
from src.testing.base_test import BaseTest
from src.testing.registry import TestRegistry

_DEFAULT_TEST_VIDEO = GeneratedVideo(uri="https://example.com/video.mp4", mime_type="video/mp4")


# ---------- Fakes (mirrors tests/EP083/EP084's precedent) ----------


class _FakeAIProvider(AIProvider):
    """Deterministic, test-only concrete `AIProvider` (EP-085).

    `generate_video()` either returns a fixed successful
    `VideoGenerationResult` or raises a fixed exception, and records
    every call's arguments so tests can assert exactly what was sent
    and, critically, exactly how many times generation was actually
    attempted (the retry/duplication test below depends on this).
    """

    def __init__(
        self,
        name: str,
        *,
        available: bool = True,
        video_capable: bool = True,
        video: GeneratedVideo = _DEFAULT_TEST_VIDEO,
        raise_error: Exception | None = None,
    ) -> None:
        self._name = name
        self._available = available
        self._video_capable = video_capable
        self._video = video
        self._raise_error = raise_error
        self.generate_video_calls: list[VideoGenerationRequest] = []

    def name(self) -> str:
        return self._name

    def status(self) -> ProviderStatus:
        return ProviderStatus.AVAILABLE if self._available else ProviderStatus.NOT_CONFIGURED

    def is_available(self) -> bool:
        return self._available

    def configuration(self) -> dict:
        return {"enabled": self._available, "configured": self._available}

    def health(self) -> ProviderHealth:
        return ProviderHealth(available=self._available, message="")

    def ask(self, prompt: str, max_tokens=None, temperature=None, system_prompt=None) -> ProviderResponse:
        raise ProviderUnavailableError(f"Provider '{self._name}' does not support chat requests.")

    def supports_video_generation(self) -> bool:
        return self._video_capable

    def generate_video(self, request: VideoGenerationRequest) -> VideoGenerationResult:
        self.generate_video_calls.append(request)
        if self._raise_error is not None:
            raise self._raise_error
        return VideoGenerationResult(
            video=self._video, model=f"{self._name}-video-model", latency_ms=1.0
        )


class _FakeProviderManager:
    """Deterministic, test-only stand-in for `ProviderManager` (EP-085)."""

    def __init__(
        self,
        ordered_providers: list[_FakeAIProvider],
        current: _FakeAIProvider | None,
        enabled: bool = True,
    ) -> None:
        self._ordered_providers = ordered_providers
        self._current = current
        self._enabled = enabled
        self.list_fallback_candidates_calls: list[set[str]] = []

    def get_current(self):
        return self._current

    def is_enabled(self) -> bool:
        return self._enabled

    def list_fallback_candidates(self, exclude) -> list[_FakeAIProvider]:
        excluded = set(exclude)
        self.list_fallback_candidates_calls.append(excluded)
        return [
            provider
            for provider in self._ordered_providers
            if provider.name() not in excluded and provider.is_available()
        ]


@dataclass
class _FakeHTTPResponse:
    """Minimal stand-in for `requests.Response` (mirrors tests/EP082-084)."""

    status_code: int
    _json: dict
    text: str = ""

    def json(self) -> dict:
        return self._json


def _done_response(uri: str = "https://example.com/video.mp4", mime_type: str | None = "video/mp4") -> _FakeHTTPResponse:
    video: dict = {"uri": uri}
    if mime_type is not None:
        video["mimeType"] = mime_type
    return _FakeHTTPResponse(
        status_code=200,
        _json={
            "done": True,
            "response": {"generateVideoResponse": {"generatedSamples": [{"video": video}]}},
        },
    )


def _not_done_response() -> _FakeHTTPResponse:
    return _FakeHTTPResponse(status_code=200, _json={"done": False})


def _initiate_response(name: str = "operations/generate_123") -> _FakeHTTPResponse:
    return _FakeHTTPResponse(status_code=200, _json={"name": name})


@TestRegistry.register
class VideoGenerationProviderIntegrationTest(BaseTest):
    NAME = "EP085"

    def run(self):
        # ---------- AIProvider base defaults ----------
        self._test_claude_provider_does_not_support_video_generation()
        self._test_config_driven_provider_does_not_support_video_generation()

        # ---------- ProviderRequestExecutor.execute_video() ----------
        self._test_executor_video_primary_success_no_fallback_attempted()
        self._test_executor_video_fallback_disabled_fails_immediately()
        self._test_executor_video_fallback_skips_non_capable_candidates()
        self._test_executor_video_non_eligible_failure_never_retries()
        self._test_executor_video_exhausted_fallback_reports_all_failures()
        self._test_executor_text_image_speech_paths_unaffected_by_video_addition()

        # ---------- VideoGenerationService ----------
        self._test_service_disabled_by_default()
        self._test_service_success_path()
        self._test_service_no_provider_selected()
        self._test_service_ai_subsystem_disabled()
        self._test_service_current_provider_lacks_capability_fails_fast()
        self._test_service_fallback_success()
        self._test_service_never_receives_conversation_or_context_dependency()

        # ---------- GeminiProvider / Veo lifecycle ----------
        self._test_gemini_supports_video_generation_reflects_video_model()
        self._test_gemini_generate_video_success_single_poll()
        self._test_gemini_generate_video_success_multi_poll()
        self._test_gemini_generate_video_sends_correct_request_body()
        self._test_gemini_generate_video_model_not_found_404()
        self._test_gemini_generate_video_missing_operation_name()
        self._test_gemini_generate_video_malformed_initiate_response()
        self._test_gemini_generate_video_operation_error()
        self._test_gemini_generate_video_missing_video_uri()
        self._test_gemini_generate_video_empty_uri_rejected()
        self._test_gemini_generate_video_malformed_poll_response()
        self._test_gemini_generate_video_empty_prompt_raises_configuration_error()
        self._test_gemini_generate_video_not_configured_raises_configuration_error()
        self._test_gemini_generate_video_invalid_poll_interval_rejected()
        self._test_gemini_generate_video_invalid_max_wait_rejected()
        self._test_gemini_generate_video_default_mime_type_when_missing()

        # ---------- STEP 3 hardening: transient poll-failure tolerance ----------
        self._test_gemini_generate_video_poll_transient_failure_then_success()
        self._test_gemini_generate_video_poll_persistent_transient_failure_times_out()
        self._test_gemini_generate_video_poll_auth_failure_propagates_immediately()

        # ---------- Adversarial: polling / timeout hardening ----------
        self._test_gemini_generate_video_timeout_when_never_completes()
        self._test_gemini_generate_video_poll_uses_configured_sleep_interval()
        self._test_gemini_generate_video_never_downloads_bytes()

        # ---------- Retry / duplicate-generation safety ----------
        self._test_executor_video_default_config_never_retries_failed_generation()
        self._test_service_default_config_never_duplicates_video_generation()

        return self.result

    # ---------- AIProvider base defaults ----------

    def _test_claude_provider_does_not_support_video_generation(self) -> None:
        provider = ClaudeProvider(
            enabled=True, api_key="k", model="claude-test", timeout=10, max_tokens=256, temperature=0.2
        )
        self.assert_false(provider.supports_video_generation())
        try:
            provider.generate_video(VideoGenerationRequest(prompt="hello"))
            self.assert_true(False, "ClaudeProvider.generate_video() must raise.")
        except ProviderUnavailableError:
            self.assert_true(True)

    def _test_config_driven_provider_does_not_support_video_generation(self) -> None:
        provider = ConfigDrivenProvider(
            name="openai", enabled=True, credential_key="api_key", credential_value="k"
        )
        self.assert_false(provider.supports_video_generation())
        try:
            provider.generate_video(VideoGenerationRequest(prompt="hello"))
            self.assert_true(False, "ConfigDrivenProvider.generate_video() must raise.")
        except ProviderUnavailableError:
            self.assert_true(True)

    # ---------- ProviderRequestExecutor.execute_video() ----------

    def _test_executor_video_primary_success_no_fallback_attempted(self) -> None:
        primary = _FakeAIProvider("gemini", video_capable=True)
        fallback = _FakeAIProvider("other", video_capable=True)
        manager = _FakeProviderManager([fallback, primary], current=primary)
        executor = ProviderRequestExecutor(manager)
        request = VideoGenerationRequest(prompt="a cat playing piano")

        outcome = executor.execute_video(primary, request, fallback_enabled=True)

        self.assert_true(outcome.success)
        self.assert_equal(outcome.initial_provider, "gemini")
        self.assert_equal(outcome.final_provider, "gemini")
        self.assert_not_none(outcome.result)
        self.assert_equal(len(fallback.generate_video_calls), 0)
        self.assert_equal(primary.generate_video_calls[0].prompt, "a cat playing piano")

    def _test_executor_video_fallback_disabled_fails_immediately(self) -> None:
        primary = _FakeAIProvider("gemini", raise_error=ProviderUnavailableError("down"))
        fallback = _FakeAIProvider("other", video_capable=True)
        manager = _FakeProviderManager([fallback, primary], current=primary)
        executor = ProviderRequestExecutor(manager)

        outcome = executor.execute_video(
            primary, VideoGenerationRequest(prompt="x"), fallback_enabled=False
        )

        self.assert_false(outcome.success)
        self.assert_equal(len(fallback.generate_video_calls), 0)
        self.assert_equal(len(manager.list_fallback_candidates_calls), 0)

    def _test_executor_video_fallback_skips_non_capable_candidates(self) -> None:
        primary = _FakeAIProvider("gemini", raise_error=ProviderUnavailableError("down"))
        not_capable = _FakeAIProvider("claude", video_capable=False)
        capable_fallback = _FakeAIProvider("other-video-provider", video_capable=True)
        manager = _FakeProviderManager([not_capable, capable_fallback, primary], current=primary)
        executor = ProviderRequestExecutor(manager)

        outcome = executor.execute_video(
            primary, VideoGenerationRequest(prompt="x"), fallback_enabled=True
        )

        self.assert_true(outcome.success)
        self.assert_equal(outcome.final_provider, "other-video-provider")
        self.assert_equal(
            len(not_capable.generate_video_calls), 0, "Non-capable candidate must never be attempted."
        )

    def _test_executor_video_non_eligible_failure_never_retries(self) -> None:
        primary = _FakeAIProvider("gemini", raise_error=ProviderConfigurationError("bad config"))
        fallback = _FakeAIProvider("other", video_capable=True)
        manager = _FakeProviderManager([fallback, primary], current=primary)
        executor = ProviderRequestExecutor(manager)

        outcome = executor.execute_video(
            primary, VideoGenerationRequest(prompt="x"), fallback_enabled=True
        )

        self.assert_false(outcome.success)
        self.assert_equal(len(fallback.generate_video_calls), 0)

    def _test_executor_video_exhausted_fallback_reports_all_failures(self) -> None:
        primary = _FakeAIProvider("gemini", raise_error=ProviderUnavailableError("down"))
        fallback = _FakeAIProvider(
            "other", video_capable=True, raise_error=ProviderTimeoutError("timeout")
        )
        manager = _FakeProviderManager([fallback, primary], current=primary)
        executor = ProviderRequestExecutor(manager)

        outcome = executor.execute_video(
            primary, VideoGenerationRequest(prompt="x"), fallback_enabled=True
        )

        self.assert_false(outcome.success)
        self.assert_true("gemini" in outcome.error and "other" in outcome.error)
        self.assert_true("ProviderUnavailableError" in outcome.error and "ProviderTimeoutError" in outcome.error)

    def _test_executor_text_image_speech_paths_unaffected_by_video_addition(self) -> None:
        # Light-touch confirmation within EP-085's own suite that the
        # _run() reuse did not disturb execute()/execute_image()/
        # execute_speech()'s own paths (full regression ownership
        # remains tests/EP082/EP083/EP084).
        primary = _FakeAIProvider("gemini")
        manager = _FakeProviderManager([primary], current=primary)
        executor = ProviderRequestExecutor(manager)

        text_outcome = executor.execute(primary, "hello", fallback_enabled=False)
        self.assert_false(text_outcome.success)
        self.assert_equal(len(primary.generate_video_calls), 0)

        from src.core.ai.provider import ImageGenerationRequest, SpeechGenerationRequest

        image_outcome = executor.execute_image(
            primary, ImageGenerationRequest(prompt="x"), fallback_enabled=False
        )
        self.assert_false(image_outcome.success)

        speech_outcome = executor.execute_speech(
            primary, SpeechGenerationRequest(text="x"), fallback_enabled=False
        )
        self.assert_false(speech_outcome.success)
        self.assert_equal(len(primary.generate_video_calls), 0)

    # ---------- VideoGenerationService ----------

    def _make_service(
        self,
        *,
        provider: _FakeAIProvider | None,
        ordered_providers: list[_FakeAIProvider] | None = None,
        enabled: bool = True,
        ai_enabled: bool = True,
        fallback_enabled: bool = False,
    ) -> tuple[VideoGenerationService, _FakeProviderManager]:
        manager = _FakeProviderManager(
            ordered_providers or ([provider] if provider else []),
            current=provider,
            enabled=ai_enabled,
        )
        executor = ProviderRequestExecutor(manager)
        service = VideoGenerationService(
            provider_manager=manager,
            request_executor=executor,
            enabled=enabled,
            fallback_enabled=fallback_enabled,
        )
        return service, manager

    def _test_service_disabled_by_default(self) -> None:
        provider = _FakeAIProvider("gemini")
        service, _ = self._make_service(provider=provider, enabled=False)

        result = service.generate(VideoGenerationRequest(prompt="hi"))

        self.assert_false(result.success)
        self.assert_true("disabled" in result.error.lower())
        self.assert_equal(len(provider.generate_video_calls), 0)

    def _test_service_success_path(self) -> None:
        provider = _FakeAIProvider("gemini")
        service, _ = self._make_service(provider=provider, enabled=True)

        result = service.generate(VideoGenerationRequest(prompt="hi"))

        self.assert_true(result.success)
        self.assert_not_none(result.video)
        self.assert_equal(result.provider_name, "gemini")
        self.assert_equal(result.model_name, "gemini-video-model")
        self.assert_equal(result.error, "")
        self.assert_true(isinstance(result, ServiceVideoGenerationResult))

    def _test_service_no_provider_selected(self) -> None:
        service, _ = self._make_service(provider=None, enabled=True)

        result = service.generate(VideoGenerationRequest(prompt="hi"))

        self.assert_false(result.success)
        self.assert_true("No AI provider" in result.error)

    def _test_service_ai_subsystem_disabled(self) -> None:
        provider = _FakeAIProvider("gemini")
        service, _ = self._make_service(provider=provider, enabled=True, ai_enabled=False)

        result = service.generate(VideoGenerationRequest(prompt="hi"))

        self.assert_false(result.success)
        self.assert_true("AI subsystem is disabled" in result.error)
        self.assert_equal(len(provider.generate_video_calls), 0)

    def _test_service_current_provider_lacks_capability_fails_fast(self) -> None:
        provider = _FakeAIProvider("claude", video_capable=False)
        service, _ = self._make_service(provider=provider, enabled=True)

        result = service.generate(VideoGenerationRequest(prompt="hi"))

        self.assert_false(result.success)
        self.assert_true("does not support video generation" in result.error)
        self.assert_equal(
            len(provider.generate_video_calls), 0, "Must fail before any executor/provider call."
        )

    def _test_service_fallback_success(self) -> None:
        primary = _FakeAIProvider("gemini", raise_error=ProviderUnavailableError("down"))
        fallback = _FakeAIProvider("other", video_capable=True)
        service, _ = self._make_service(
            provider=primary,
            ordered_providers=[fallback, primary],
            enabled=True,
            fallback_enabled=True,
        )

        result = service.generate(VideoGenerationRequest(prompt="hi"))

        self.assert_true(result.success)
        self.assert_equal(result.provider_name, "other")

    def _test_service_never_receives_conversation_or_context_dependency(self) -> None:
        signature = inspect.signature(VideoGenerationService.__init__)
        forbidden_names = {"conversation_manager", "context_manager", "prompt_manager"}
        actual_names = set(signature.parameters.keys())
        self.assert_true(
            forbidden_names.isdisjoint(actual_names),
            f"VideoGenerationService must not depend on {forbidden_names}, "
            f"found overlap: {forbidden_names & actual_names}",
        )

    # ---------- GeminiProvider / Veo lifecycle ----------

    def _make_gemini_provider(
        self,
        video_model: str | None = "veo-3.1-generate-preview",
        poll_interval_seconds: float = 0.001,
        max_wait_seconds: float = 0.05,
    ) -> GeminiProvider:
        return GeminiProvider(
            enabled=True,
            api_key="test-key",
            model="gemini-test-model",
            timeout=10,
            max_tokens=256,
            temperature=0.2,
            video_model=video_model,
            video_poll_interval_seconds=poll_interval_seconds,
            video_max_wait_seconds=max_wait_seconds,
        )

    def _test_gemini_supports_video_generation_reflects_video_model(self) -> None:
        configured = self._make_gemini_provider(video_model="veo-3.1-generate-preview")
        unconfigured = self._make_gemini_provider(video_model=None)
        self.assert_true(configured.supports_video_generation())
        self.assert_false(unconfigured.supports_video_generation())

    def _test_gemini_generate_video_success_single_poll(self) -> None:
        provider = self._make_gemini_provider()
        with (
            patch(
                "src.core.ai.providers.gemini_provider.requests.request",
                side_effect=[_initiate_response(), _done_response()],
            ) as mock_request,
            patch("src.core.ai.providers.gemini_provider.time.sleep") as mock_sleep,
        ):
            result = provider.generate_video(VideoGenerationRequest(prompt="a cat"))

        self.assert_equal(result.video.uri, "https://example.com/video.mp4")
        self.assert_equal(result.video.mime_type, "video/mp4")
        self.assert_equal(result.model, "veo-3.1-generate-preview")
        self.assert_equal(mock_sleep.call_count, 0, "Must not sleep if done on the first poll.")
        self.assert_equal(mock_request.call_count, 2)

    def _test_gemini_generate_video_success_multi_poll(self) -> None:
        provider = self._make_gemini_provider()
        responses = [_initiate_response(), _not_done_response(), _not_done_response(), _done_response()]
        with (
            patch(
                "src.core.ai.providers.gemini_provider.requests.request", side_effect=responses
            ) as mock_request,
            patch("src.core.ai.providers.gemini_provider.time.sleep") as mock_sleep,
        ):
            result = provider.generate_video(VideoGenerationRequest(prompt="a cat"))

        self.assert_true(result.video.uri == "https://example.com/video.mp4")
        self.assert_equal(mock_sleep.call_count, 2, "Must sleep once between each not-done poll.")
        self.assert_equal(mock_request.call_count, 4)

    def _test_gemini_generate_video_sends_correct_request_body(self) -> None:
        provider = self._make_gemini_provider()
        with patch(
            "src.core.ai.providers.gemini_provider.requests.request",
            side_effect=[_initiate_response(), _done_response()],
        ) as mock_request, patch("src.core.ai.providers.gemini_provider.time.sleep"):
            provider.generate_video(
                VideoGenerationRequest(
                    prompt="a cat playing piano",
                    aspect_ratio="16:9",
                    duration_seconds=8,
                    negative_prompt="blurry",
                    seed=42,
                )
            )

        initiate_call = mock_request.call_args_list[0]
        payload = initiate_call.kwargs["json"]
        self.assert_equal(payload["instances"][0]["prompt"], "a cat playing piano")
        self.assert_equal(payload["parameters"]["aspectRatio"], "16:9")
        self.assert_equal(payload["parameters"]["durationSeconds"], 8)
        self.assert_equal(payload["parameters"]["negativePrompt"], "blurry")
        self.assert_equal(payload["parameters"]["seed"], 42)
        called_url = initiate_call[0][1] if len(initiate_call[0]) > 1 else initiate_call.args[1]
        self.assert_true("veo-3.1-generate-preview" in called_url and "predictLongRunning" in called_url)

        # Poll call must hit the operation name verbatim, not a
        # reconstructed URL.
        poll_call = mock_request.call_args_list[1]
        poll_url = poll_call[0][1] if len(poll_call[0]) > 1 else poll_call.args[1]
        self.assert_true(poll_url.endswith("operations/generate_123"))
        self.assert_true("/models/" not in poll_url)

    def _test_gemini_generate_video_model_not_found_404(self) -> None:
        provider = self._make_gemini_provider(video_model="veo-does-not-exist")
        fake_response = _FakeHTTPResponse(status_code=404, _json={})
        with patch("src.core.ai.providers.gemini_provider.requests.request", return_value=fake_response):
            try:
                provider.generate_video(VideoGenerationRequest(prompt="x"))
                self.assert_true(False, "HTTP 404 must raise ProviderUnavailableError.")
            except ProviderUnavailableError as exc:
                self.assert_true("video_model" in str(exc) or "veo-does-not-exist" in str(exc))

    def _test_gemini_generate_video_missing_operation_name(self) -> None:
        provider = self._make_gemini_provider()
        fake_response = _FakeHTTPResponse(status_code=200, _json={"unexpected": "shape"})
        with patch("src.core.ai.providers.gemini_provider.requests.request", return_value=fake_response):
            try:
                provider.generate_video(VideoGenerationRequest(prompt="x"))
                self.assert_true(False, "Missing operation name must raise ProviderUnavailableError.")
            except ProviderUnavailableError:
                self.assert_true(True)

    def _test_gemini_generate_video_malformed_initiate_response(self) -> None:
        provider = self._make_gemini_provider()

        class _BadJSONResponse:
            status_code = 200

            def json(self):
                raise ValueError("not valid json")

        with patch(
            "src.core.ai.providers.gemini_provider.requests.request", return_value=_BadJSONResponse()
        ):
            try:
                provider.generate_video(VideoGenerationRequest(prompt="x"))
                self.assert_true(False, "Malformed initiate JSON must raise ProviderUnavailableError.")
            except ProviderUnavailableError:
                self.assert_true(True)
            except Exception as exc:  # noqa: BLE001 - explicitly asserting this must NOT happen
                self.assert_true(False, f"Must not escape as a raw {type(exc).__name__}: {exc}")

    def _test_gemini_generate_video_operation_error(self) -> None:
        provider = self._make_gemini_provider()
        error_response = _FakeHTTPResponse(
            status_code=200, _json={"done": True, "error": {"message": "content policy violation"}}
        )
        with patch(
            "src.core.ai.providers.gemini_provider.requests.request",
            side_effect=[_initiate_response(), error_response],
        ):
            try:
                provider.generate_video(VideoGenerationRequest(prompt="x"))
                self.assert_true(False, "Operation-level error must raise ProviderUnavailableError.")
            except ProviderUnavailableError as exc:
                self.assert_true("content policy violation" in str(exc))

    def _test_gemini_generate_video_missing_video_uri(self) -> None:
        provider = self._make_gemini_provider()
        # done=true, no error, but zero usable samples (e.g. every
        # sample filtered by the provider's own content policy).
        empty_response = _FakeHTTPResponse(
            status_code=200,
            _json={"done": True, "response": {"generateVideoResponse": {"generatedSamples": []}}},
        )
        with patch(
            "src.core.ai.providers.gemini_provider.requests.request",
            side_effect=[_initiate_response(), empty_response],
        ):
            try:
                provider.generate_video(VideoGenerationRequest(prompt="x"))
                self.assert_true(False, "Missing video URI must raise ProviderUnavailableError.")
            except ProviderUnavailableError:
                self.assert_true(True)

    def _test_gemini_generate_video_empty_uri_rejected(self) -> None:
        # Adversarial Scenario E (STEP 3): a sample IS present, but its
        # video.uri is an empty string -- must be treated identically
        # to a missing URI, never accepted as a usable reference.
        provider = self._make_gemini_provider()
        empty_uri_response = _done_response(uri="")
        with patch(
            "src.core.ai.providers.gemini_provider.requests.request",
            side_effect=[_initiate_response(), empty_uri_response],
        ):
            try:
                provider.generate_video(VideoGenerationRequest(prompt="x"))
                self.assert_true(False, "An empty video URI must raise ProviderUnavailableError.")
            except ProviderUnavailableError:
                self.assert_true(True)

    def _test_gemini_generate_video_malformed_poll_response(self) -> None:
        provider = self._make_gemini_provider()

        class _BadPollJSONResponse:
            status_code = 200

            def json(self):
                raise ValueError("not valid json")

        with patch(
            "src.core.ai.providers.gemini_provider.requests.request",
            side_effect=[_initiate_response(), _BadPollJSONResponse()],
        ):
            try:
                provider.generate_video(VideoGenerationRequest(prompt="x"))
                self.assert_true(False, "Malformed poll JSON must raise ProviderUnavailableError.")
            except ProviderUnavailableError:
                self.assert_true(True)
            except Exception as exc:  # noqa: BLE001
                self.assert_true(False, f"Must not escape as a raw {type(exc).__name__}: {exc}")

    def _test_gemini_generate_video_empty_prompt_raises_configuration_error(self) -> None:
        provider = self._make_gemini_provider()
        try:
            provider.generate_video(VideoGenerationRequest(prompt="   "))
            self.assert_true(False, "Empty/blank 'prompt' must raise ProviderConfigurationError.")
        except ProviderConfigurationError:
            self.assert_true(True)

    def _test_gemini_generate_video_not_configured_raises_configuration_error(self) -> None:
        provider = self._make_gemini_provider(video_model=None)
        try:
            provider.generate_video(VideoGenerationRequest(prompt="x"))
            self.assert_true(False, "Unconfigured video_model must raise ProviderConfigurationError.")
        except ProviderConfigurationError:
            self.assert_true(True)

    def _test_gemini_generate_video_invalid_poll_interval_rejected(self) -> None:
        for bad_value in (0, -1, -0.5):
            provider = self._make_gemini_provider(poll_interval_seconds=bad_value)
            try:
                provider.generate_video(VideoGenerationRequest(prompt="x"))
                self.assert_true(False, f"poll_interval_seconds={bad_value} must be rejected.")
            except ProviderConfigurationError:
                self.assert_true(True)

    def _test_gemini_generate_video_invalid_max_wait_rejected(self) -> None:
        for bad_value in (0, -1, -100):
            provider = self._make_gemini_provider(max_wait_seconds=bad_value)
            try:
                provider.generate_video(VideoGenerationRequest(prompt="x"))
                self.assert_true(False, f"max_wait_seconds={bad_value} must be rejected.")
            except ProviderConfigurationError:
                self.assert_true(True)

    def _test_gemini_generate_video_default_mime_type_when_missing(self) -> None:
        provider = self._make_gemini_provider()
        response_no_mime = _done_response(mime_type=None)
        with patch(
            "src.core.ai.providers.gemini_provider.requests.request",
            side_effect=[_initiate_response(), response_no_mime],
        ), patch("src.core.ai.providers.gemini_provider.time.sleep"):
            result = provider.generate_video(VideoGenerationRequest(prompt="x"))
        self.assert_equal(result.video.mime_type, "video/mp4")

    # ---------- STEP 3 hardening: transient poll-failure tolerance ----------

    def _test_gemini_generate_video_poll_transient_failure_then_success(self) -> None:
        # STEP 3 audit finding F1: a single transient poll failure
        # (here, an HTTP 500 -> ProviderUnavailableError) must not
        # discard an otherwise-successful video generation -- it is
        # treated like an ordinary "not done yet" response and
        # retried.
        provider = self._make_gemini_provider(poll_interval_seconds=0.001, max_wait_seconds=60)
        transient_failure = _FakeHTTPResponse(status_code=500, _json={})
        responses = [_initiate_response(), transient_failure, _done_response()]
        with (
            patch("src.core.ai.providers.gemini_provider.requests.request", side_effect=responses),
            patch("src.core.ai.providers.gemini_provider.time.sleep") as mock_sleep,
        ):
            result = provider.generate_video(VideoGenerationRequest(prompt="x"))
        self.assert_equal(result.video.uri, "https://example.com/video.mp4")
        self.assert_equal(
            mock_sleep.call_count, 1, "Must sleep once after the transient failure, then succeed."
        )

    def _test_gemini_generate_video_poll_persistent_transient_failure_times_out(self) -> None:
        # A persistently failing (but transient-classified) poll must
        # still deterministically surface as ProviderTimeoutError once
        # the deadline is exceeded -- never hang, never silently
        # succeed, and never propagate the raw transient error instead
        # of the timeout.
        provider = self._make_gemini_provider(poll_interval_seconds=1, max_wait_seconds=10)
        transient_failure = _FakeHTTPResponse(status_code=503, _json={})
        with (
            patch(
                "src.core.ai.providers.gemini_provider.requests.request",
                side_effect=[_initiate_response()] + [transient_failure] * 10,
            ),
            patch("src.core.ai.providers.gemini_provider.time.sleep"),
            patch(
                "src.core.ai.providers.gemini_provider.time.monotonic",
                side_effect=[0.0, 0.0, 100.0],
            ),
        ):
            try:
                provider.generate_video(VideoGenerationRequest(prompt="x"))
                self.assert_true(
                    False, "Persistent transient poll failure must eventually raise ProviderTimeoutError."
                )
            except ProviderTimeoutError:
                self.assert_true(True)

    def _test_gemini_generate_video_poll_auth_failure_propagates_immediately(self) -> None:
        # A non-transient failure (here, HTTP 401 ->
        # ProviderAuthenticationError) must NOT be tolerated/retried
        # the way transient failures are -- it propagates immediately,
        # and polling must stop (no further HTTP calls after it).
        provider = self._make_gemini_provider(poll_interval_seconds=0.001, max_wait_seconds=60)
        auth_failure = _FakeHTTPResponse(status_code=401, _json={})
        with (
            patch(
                "src.core.ai.providers.gemini_provider.requests.request",
                side_effect=[_initiate_response(), auth_failure],
            ) as mock_request,
            patch("src.core.ai.providers.gemini_provider.time.sleep") as mock_sleep,
        ):
            try:
                provider.generate_video(VideoGenerationRequest(prompt="x"))
                self.assert_true(
                    False, "Auth failure during polling must raise ProviderAuthenticationError."
                )
            except ProviderAuthenticationError:
                self.assert_true(True)
        self.assert_equal(mock_request.call_count, 2, "Must not retry after a non-transient auth failure.")
        self.assert_equal(
            mock_sleep.call_count, 0, "Must not sleep/retry after a non-transient auth failure."
        )

    # ---------- Adversarial: polling / timeout hardening ----------

    def _test_gemini_generate_video_timeout_when_never_completes(self) -> None:
        # Deterministic by construction, not by timing: time.monotonic
        # is patched with a controlled sequence (deadline computed
        # from the first call; the second call already reports the
        # deadline as passed) so this test's outcome never depends on
        # how fast this machine actually executes the poll loop --
        # exactly the requirement EP085_DESIGN.md Section 17 and STEP
        # 2 Phase 4 impose ("tests must not actually sleep for real
        # minutes"; the same principle extends to not *depending* on
        # real elapsed wall-clock time at all).
        provider = self._make_gemini_provider(poll_interval_seconds=1, max_wait_seconds=10)
        with (
            patch(
                "src.core.ai.providers.gemini_provider.requests.request",
                side_effect=[_initiate_response(), _not_done_response()],
            ),
            patch("src.core.ai.providers.gemini_provider.time.sleep"),
            patch(
                "src.core.ai.providers.gemini_provider.time.monotonic",
                side_effect=[0.0, 0.0, 100.0],
            ),
        ):
            try:
                provider.generate_video(VideoGenerationRequest(prompt="x"))
                self.assert_true(
                    False, "An operation that never completes must raise ProviderTimeoutError."
                )
            except ProviderTimeoutError:
                        self.assert_true(True)

    def _test_gemini_generate_video_poll_uses_configured_sleep_interval(self) -> None:
        provider = self._make_gemini_provider(poll_interval_seconds=3.5, max_wait_seconds=60)
        responses = [_initiate_response(), _not_done_response(), _done_response()]
        with (
            patch("src.core.ai.providers.gemini_provider.requests.request", side_effect=responses),
            patch("src.core.ai.providers.gemini_provider.time.sleep") as mock_sleep,
        ):
            provider.generate_video(VideoGenerationRequest(prompt="x"))
        mock_sleep.assert_called_once_with(3.5)

    def _test_gemini_generate_video_never_downloads_bytes(self) -> None:
        # Owner Decision D2 confirmation: GeneratedVideo carries only
        # a uri/mime_type reference -- never bytes, never base64 data.
        video = GeneratedVideo(uri="https://example.com/video.mp4", mime_type="video/mp4")
        field_names = {f for f in video.__dataclass_fields__}
        self.assert_equal(field_names, {"uri", "mime_type"})
        self.assert_true(not hasattr(video, "data_base64"))
        self.assert_true(not hasattr(video, "bytes"))

    # ---------- Retry / duplicate-generation safety ----------

    def _test_executor_video_default_config_never_retries_failed_generation(self) -> None:
        # The approved, deliberate default (EP085_DESIGN.md Section
        # 13): with fallback_enabled=False, a failed video generation
        # is attempted exactly once, on exactly one provider -- never
        # silently retried/duplicated, regardless of how many other
        # candidates ProviderManager could offer.
        primary = _FakeAIProvider("gemini", raise_error=ProviderUnavailableError("down mid-poll"))
        fallback = _FakeAIProvider("other", video_capable=True)
        manager = _FakeProviderManager([fallback, primary], current=primary)
        executor = ProviderRequestExecutor(manager)

        outcome = executor.execute_video(
            primary, VideoGenerationRequest(prompt="x"), fallback_enabled=False
        )

        self.assert_false(outcome.success)
        self.assert_equal(
            len(primary.generate_video_calls), 1, "Exactly one generation attempt, never duplicated."
        )
        self.assert_equal(
            len(fallback.generate_video_calls), 0, "No second generation must ever be started."
        )
        self.assert_equal(
            len(manager.list_fallback_candidates_calls),
            0,
            "ProviderManager must not even be asked for fallback candidates.",
        )

    def _test_service_default_config_never_duplicates_video_generation(self) -> None:
        # Same guarantee, exercised through VideoGenerationService
        # with its actual bootstrap-matching default
        # (fallback_enabled=False).
        primary = _FakeAIProvider("gemini", raise_error=ProviderUnavailableError("down mid-poll"))
        fallback = _FakeAIProvider("other", video_capable=True)
        service, _manager = self._make_service(
            provider=primary,
            ordered_providers=[fallback, primary],
            enabled=True,
            fallback_enabled=False,  # the actual default in bootstrap.py
        )

        result = service.generate(VideoGenerationRequest(prompt="x"))

        self.assert_false(result.success)
        self.assert_equal(len(primary.generate_video_calls), 1)
        self.assert_equal(len(fallback.generate_video_calls), 0)
