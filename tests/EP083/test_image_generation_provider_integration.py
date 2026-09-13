"""Real engineering tests for EP-083 STEP 2 - Image Generation Provider Integration.

Single combined test suite (NAME = "EP083"), following the same
precedent tests/EP082 already established. Self-contained -- no
import from any other `tests/EP0NN/` package.

Covers, per `EP083_DESIGN.md` Section 18:
    - `AIProvider.supports_image_generation()`/`generate_image()` base
      defaults (False / always raises), confirmed on both
      `ClaudeProvider` and the `ConfigDrivenProvider` placeholders --
      neither is modified by EP-083 and neither silently gains image
      support.
    - `ProviderRequestExecutor.execute_image()`: primary success,
      fallback disabled, fallback-eligible retry (skipping
      non-capable candidates), non-eligible immediate failure,
      fallback exhaustion -- mirroring tests/EP082's own
      `_test_executor_*` structure so the two suites are directly
      comparable.
    - `ImageGenerationService`: success path, disabled config, no
      provider selected, AI subsystem disabled, current provider
      lacks the capability (fails fast, zero executor/provider
      calls), fallback success, non-conversational structural check.
    - `GeminiProvider.generate_image()`/`supports_image_generation()`:
      additive-parameter/contract tests via mocked HTTP, mirroring
      tests/EP082's own Claude/Gemini mocking precedent.

Regression coverage for `ProviderRequestExecutor.execute()`
(text, EP-082) and `AIService.ask()`/`TextGenerationService` itself is
NOT duplicated here -- it is the responsibility of, and already
covered by, `tests/EP082`, `tests/EP069`, `tests/EP069_2`, and
`tests/EP069_3`, which this EP's STEP 2 requires to keep passing
unmodified.
"""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import patch

from src.core.ai.claude_provider import ClaudeProvider
from src.core.ai.provider import (
    AIProvider,
    GeneratedImage,
    ImageGenerationRequest,
    ImageGenerationResult,
    ProviderConfigurationError,
    ProviderHealth,
    ProviderResponse,
    ProviderStatus,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from src.core.ai.provider_factory import ConfigDrivenProvider
from src.core.ai.provider_request_executor import ProviderRequestExecutor
from src.core.ai.providers.gemini_provider import GeminiProvider
from src.services.image_generation_service import (
    ImageGenerationResult as ServiceImageGenerationResult,
)
from src.services.image_generation_service import ImageGenerationService
from src.testing.base_test import BaseTest
from src.testing.registry import TestRegistry


# ---------- Fakes (mirrors tests/EP082's precedent) ----------


class _FakeAIProvider(AIProvider):
    """Deterministic, test-only concrete `AIProvider` (EP-083).

    `generate_image()` either returns a fixed successful
    `ImageGenerationResult` or raises a fixed exception, and records
    every call's arguments so tests can assert exactly what was sent.
    `image_capable` controls `supports_image_generation()`
    independently of availability, so tests can exercise "available
    but not image-capable" providers explicitly.
    """

    def __init__(
        self,
        name: str,
        *,
        available: bool = True,
        image_capable: bool = True,
        images: tuple[GeneratedImage, ...] = (GeneratedImage(data_base64="ZmFrZQ==", mime_type="image/png"),),
        raise_error: Exception | None = None,
    ) -> None:
        self._name = name
        self._available = available
        self._image_capable = image_capable
        self._images = images
        self._raise_error = raise_error
        self.generate_image_calls: list[ImageGenerationRequest] = []

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

    def supports_image_generation(self) -> bool:
        return self._image_capable

    def generate_image(self, request: ImageGenerationRequest) -> ImageGenerationResult:
        self.generate_image_calls.append(request)
        if self._raise_error is not None:
            raise self._raise_error
        return ImageGenerationResult(images=self._images, model=f"{self._name}-image-model", latency_ms=1.0)


class _FakeProviderManager:
    """Deterministic, test-only stand-in for `ProviderManager` (EP-083).

    Exposes exactly the methods `ProviderRequestExecutor` and
    `ImageGenerationService` call: `get_current()`, `is_enabled()`,
    `list_fallback_candidates()`. Mirrors
    `tests/EP082`'s own fake exactly.
    """

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
    """Minimal stand-in for `requests.Response` (mirrors tests/EP082)."""

    status_code: int
    _json: dict
    text: str = ""

    def json(self) -> dict:
        return self._json


@TestRegistry.register
class ImageGenerationProviderIntegrationTest(BaseTest):
    NAME = "EP083"

    def run(self):
        # ---------- AIProvider base defaults ----------
        self._test_claude_provider_does_not_support_image_generation()
        self._test_config_driven_provider_does_not_support_image_generation()

        # ---------- ProviderRequestExecutor.execute_image() ----------
        self._test_executor_image_primary_success_no_fallback_attempted()
        self._test_executor_image_fallback_disabled_fails_immediately()
        self._test_executor_image_fallback_skips_non_capable_candidates()
        self._test_executor_image_non_eligible_failure_never_retries()
        self._test_executor_image_exhausted_fallback_reports_all_failures()
        self._test_executor_text_path_unaffected_by_image_addition()

        # ---------- ImageGenerationService ----------
        self._test_service_disabled_by_default()
        self._test_service_success_path()
        self._test_service_no_provider_selected()
        self._test_service_ai_subsystem_disabled()
        self._test_service_current_provider_lacks_capability_fails_fast()
        self._test_service_fallback_success()
        self._test_service_never_receives_conversation_or_context_dependency()

        # ---------- GeminiProvider image support ----------
        self._test_gemini_supports_image_generation_reflects_image_model()
        self._test_gemini_generate_image_success()
        self._test_gemini_generate_image_multiple_images_and_mixed_parts()
        self._test_gemini_generate_image_model_not_found_404()
        self._test_gemini_generate_image_empty_response_fails()
        self._test_gemini_generate_image_invalid_count_raises_configuration_error()
        self._test_gemini_generate_image_not_configured_raises_configuration_error()

        return self.result

    # ---------- AIProvider base defaults ----------

    def _test_claude_provider_does_not_support_image_generation(self) -> None:
        provider = ClaudeProvider(
            enabled=True, api_key="k", model="claude-test", timeout=10, max_tokens=256, temperature=0.2
        )
        self.assert_false(provider.supports_image_generation())
        try:
            provider.generate_image(ImageGenerationRequest(prompt="a cat"))
            self.assert_true(False, "ClaudeProvider.generate_image() must raise.")
        except ProviderUnavailableError:
            self.assert_true(True)

    def _test_config_driven_provider_does_not_support_image_generation(self) -> None:
        provider = ConfigDrivenProvider(
            name="openai", enabled=True, credential_key="api_key", credential_value="k"
        )
        self.assert_false(provider.supports_image_generation())
        try:
            provider.generate_image(ImageGenerationRequest(prompt="a cat"))
            self.assert_true(False, "ConfigDrivenProvider.generate_image() must raise.")
        except ProviderUnavailableError:
            self.assert_true(True)

    # ---------- ProviderRequestExecutor.execute_image() ----------

    def _test_executor_image_primary_success_no_fallback_attempted(self) -> None:
        primary = _FakeAIProvider("gemini", image_capable=True)
        fallback = _FakeAIProvider("other", image_capable=True)
        manager = _FakeProviderManager([fallback, primary], current=primary)
        executor = ProviderRequestExecutor(manager)
        request = ImageGenerationRequest(prompt="a red bicycle")

        outcome = executor.execute_image(primary, request, fallback_enabled=True)

        self.assert_true(outcome.success)
        self.assert_equal(outcome.initial_provider, "gemini")
        self.assert_equal(outcome.final_provider, "gemini")
        self.assert_equal(len(outcome.result.images), 1)
        self.assert_equal(len(fallback.generate_image_calls), 0)
        self.assert_equal(primary.generate_image_calls[0].prompt, "a red bicycle")

    def _test_executor_image_fallback_disabled_fails_immediately(self) -> None:
        primary = _FakeAIProvider("gemini", raise_error=ProviderUnavailableError("down"))
        fallback = _FakeAIProvider("other", image_capable=True)
        manager = _FakeProviderManager([fallback, primary], current=primary)
        executor = ProviderRequestExecutor(manager)

        outcome = executor.execute_image(primary, ImageGenerationRequest(prompt="x"), fallback_enabled=False)

        self.assert_false(outcome.success)
        self.assert_equal(len(fallback.generate_image_calls), 0)
        self.assert_equal(len(manager.list_fallback_candidates_calls), 0)

    def _test_executor_image_fallback_skips_non_capable_candidates(self) -> None:
        primary = _FakeAIProvider("gemini", raise_error=ProviderUnavailableError("down"))
        not_capable = _FakeAIProvider("claude", image_capable=False)
        capable_fallback = _FakeAIProvider("other-image-provider", image_capable=True)
        # ProviderManager ordering returns the non-capable candidate
        # first -- the executor must skip it and reach the capable one.
        manager = _FakeProviderManager([not_capable, capable_fallback, primary], current=primary)
        executor = ProviderRequestExecutor(manager)

        outcome = executor.execute_image(primary, ImageGenerationRequest(prompt="x"), fallback_enabled=True)

        self.assert_true(outcome.success)
        self.assert_equal(outcome.final_provider, "other-image-provider")
        self.assert_equal(len(not_capable.generate_image_calls), 0, "Non-capable candidate must never be attempted.")

    def _test_executor_image_non_eligible_failure_never_retries(self) -> None:
        primary = _FakeAIProvider("gemini", raise_error=ProviderConfigurationError("bad config"))
        fallback = _FakeAIProvider("other", image_capable=True)
        manager = _FakeProviderManager([fallback, primary], current=primary)
        executor = ProviderRequestExecutor(manager)

        outcome = executor.execute_image(primary, ImageGenerationRequest(prompt="x"), fallback_enabled=True)

        self.assert_false(outcome.success)
        self.assert_equal(len(fallback.generate_image_calls), 0)

    def _test_executor_image_exhausted_fallback_reports_all_failures(self) -> None:
        primary = _FakeAIProvider("gemini", raise_error=ProviderUnavailableError("down"))
        fallback = _FakeAIProvider(
            "other", image_capable=True, raise_error=ProviderTimeoutError("timeout")
        )
        manager = _FakeProviderManager([fallback, primary], current=primary)
        executor = ProviderRequestExecutor(manager)

        outcome = executor.execute_image(primary, ImageGenerationRequest(prompt="x"), fallback_enabled=True)

        self.assert_false(outcome.success)
        self.assert_true("gemini" in outcome.error and "other" in outcome.error)
        self.assert_true("ProviderUnavailableError" in outcome.error and "ProviderTimeoutError" in outcome.error)

    def _test_executor_text_path_unaffected_by_image_addition(self) -> None:
        # Light-touch confirmation within EP-083's own suite that the
        # _run() factoring did not disturb execute()'s text path (full
        # regression ownership remains tests/EP082).
        primary = _FakeAIProvider("gemini")
        manager = _FakeProviderManager([primary], current=primary)
        executor = ProviderRequestExecutor(manager)

        outcome = executor.execute(primary, "hello", fallback_enabled=False)

        # _FakeAIProvider.ask() always raises here (image-focused fake);
        # this only confirms execute() still routes through .ask(),
        # not .generate_image(), and never touches capability filtering.
        self.assert_false(outcome.success)
        self.assert_equal(len(primary.generate_image_calls), 0)

    # ---------- ImageGenerationService ----------

    def _make_service(
        self,
        *,
        provider: _FakeAIProvider | None,
        ordered_providers: list[_FakeAIProvider] | None = None,
        enabled: bool = True,
        ai_enabled: bool = True,
        fallback_enabled: bool = False,
    ) -> tuple[ImageGenerationService, _FakeProviderManager]:
        manager = _FakeProviderManager(
            ordered_providers or ([provider] if provider else []),
            current=provider,
            enabled=ai_enabled,
        )
        executor = ProviderRequestExecutor(manager)
        service = ImageGenerationService(
            provider_manager=manager,
            request_executor=executor,
            enabled=enabled,
            fallback_enabled=fallback_enabled,
        )
        return service, manager

    def _test_service_disabled_by_default(self) -> None:
        provider = _FakeAIProvider("gemini")
        service, _ = self._make_service(provider=provider, enabled=False)

        result = service.generate(ImageGenerationRequest(prompt="a cat"))

        self.assert_false(result.success)
        self.assert_true("disabled" in result.error.lower())
        self.assert_equal(len(provider.generate_image_calls), 0)

    def _test_service_success_path(self) -> None:
        provider = _FakeAIProvider("gemini")
        service, _ = self._make_service(provider=provider, enabled=True)

        result = service.generate(ImageGenerationRequest(prompt="a cat"))

        self.assert_true(result.success)
        self.assert_equal(len(result.images), 1)
        self.assert_equal(result.provider_name, "gemini")
        self.assert_equal(result.model_name, "gemini-image-model")
        self.assert_equal(result.error, "")
        self.assert_true(isinstance(result, ServiceImageGenerationResult))

    def _test_service_no_provider_selected(self) -> None:
        service, _ = self._make_service(provider=None, enabled=True)

        result = service.generate(ImageGenerationRequest(prompt="a cat"))

        self.assert_false(result.success)
        self.assert_true("No AI provider" in result.error)

    def _test_service_ai_subsystem_disabled(self) -> None:
        provider = _FakeAIProvider("gemini")
        service, _ = self._make_service(provider=provider, enabled=True, ai_enabled=False)

        result = service.generate(ImageGenerationRequest(prompt="a cat"))

        self.assert_false(result.success)
        self.assert_true("AI subsystem is disabled" in result.error)
        self.assert_equal(len(provider.generate_image_calls), 0)

    def _test_service_current_provider_lacks_capability_fails_fast(self) -> None:
        provider = _FakeAIProvider("claude", image_capable=False)
        service, _ = self._make_service(provider=provider, enabled=True)

        result = service.generate(ImageGenerationRequest(prompt="a cat"))

        self.assert_false(result.success)
        self.assert_true("does not support image generation" in result.error)
        self.assert_equal(len(provider.generate_image_calls), 0, "Must fail before any executor/provider call.")

    def _test_service_fallback_success(self) -> None:
        primary = _FakeAIProvider("gemini", raise_error=ProviderUnavailableError("down"))
        fallback = _FakeAIProvider("other", image_capable=True)
        service, _ = self._make_service(
            provider=primary,
            ordered_providers=[fallback, primary],
            enabled=True,
            fallback_enabled=True,
        )

        result = service.generate(ImageGenerationRequest(prompt="a cat"))

        self.assert_true(result.success)
        self.assert_equal(result.provider_name, "other")

    def _test_service_never_receives_conversation_or_context_dependency(self) -> None:
        # EP083_DESIGN.md Section 9: ImageGenerationService's
        # constructor accepts no ConversationManager/ContextManager/
        # PromptManager argument at all -- verified structurally,
        # mirroring tests/EP082's own equivalent check.
        import inspect

        signature = inspect.signature(ImageGenerationService.__init__)
        forbidden_names = {"conversation_manager", "context_manager", "prompt_manager"}
        actual_names = set(signature.parameters.keys())
        self.assert_true(
            forbidden_names.isdisjoint(actual_names),
            f"ImageGenerationService must not depend on {forbidden_names}, "
            f"found overlap: {forbidden_names & actual_names}",
        )

    # ---------- GeminiProvider image support ----------

    def _make_gemini_provider(self, image_model: str | None = "gemini-3.1-flash-image") -> GeminiProvider:
        return GeminiProvider(
            enabled=True,
            api_key="test-key",
            model="gemini-test-model",
            timeout=10,
            max_tokens=256,
            temperature=0.2,
            image_model=image_model,
        )

    def _test_gemini_supports_image_generation_reflects_image_model(self) -> None:
        configured = self._make_gemini_provider(image_model="gemini-3.1-flash-image")
        unconfigured = self._make_gemini_provider(image_model=None)
        self.assert_true(configured.supports_image_generation())
        self.assert_false(unconfigured.supports_image_generation())

    def _test_gemini_generate_image_success(self) -> None:
        provider = self._make_gemini_provider()
        fake_response = _FakeHTTPResponse(
            status_code=200,
            _json={
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {"inlineData": {"mimeType": "image/png", "data": "ZmFrZQ=="}},
                            ]
                        }
                    }
                ]
            },
        )
        with patch(
            "src.core.ai.providers.gemini_provider.requests.request", return_value=fake_response
        ) as mock_request:
            result = provider.generate_image(ImageGenerationRequest(prompt="a red bicycle"))

        self.assert_equal(len(result.images), 1)
        self.assert_equal(result.images[0].mime_type, "image/png")
        self.assert_equal(result.images[0].data_base64, "ZmFrZQ==")
        self.assert_equal(result.model, "gemini-3.1-flash-image")
        payload = mock_request.call_args.kwargs["json"]
        self.assert_equal(payload["generationConfig"]["responseModalities"], ["IMAGE"])
        # _send_request(method, url, ...) passes url positionally;
        # confirm the image model (not the text model) was used.
        called_url = mock_request.call_args[0][1] if len(mock_request.call_args[0]) > 1 else ""
        self.assert_true("gemini-3.1-flash-image" in called_url)

    def _test_gemini_generate_image_multiple_images_and_mixed_parts(self) -> None:
        # EP-083 STEP 3 audit (Section 15): confirm multiple inlineData
        # parts are all extracted, and a non-image ("text") part mixed
        # into the same response is silently skipped rather than
        # crashing or being mistaken for image data.
        provider = self._make_gemini_provider()
        fake_response = _FakeHTTPResponse(
            status_code=200,
            _json={
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {"text": "Here are two variations:"},
                                {"inlineData": {"mimeType": "image/png", "data": "Zmlyc3Q="}},
                                {"inlineData": {"mimeType": "image/jpeg", "data": "c2Vjb25k"}},
                            ]
                        }
                    }
                ]
            },
        )
        with patch("src.core.ai.providers.gemini_provider.requests.request", return_value=fake_response):
            result = provider.generate_image(ImageGenerationRequest(prompt="two cats", number_of_images=2))

        self.assert_equal(len(result.images), 2)
        self.assert_equal(result.images[0].data_base64, "Zmlyc3Q=")
        self.assert_equal(result.images[0].mime_type, "image/png")
        self.assert_equal(result.images[1].data_base64, "c2Vjb25k")
        self.assert_equal(result.images[1].mime_type, "image/jpeg")

    def _test_gemini_generate_image_model_not_found_404(self) -> None:
        # EP-083 STEP 3 audit (Section 9): the image path's own 404
        # handling is new code, not shared with ask()'s
        # _build_model_not_found_error() -- must name 'image_model'.
        provider = self._make_gemini_provider(image_model="gemini-does-not-exist")
        fake_response = _FakeHTTPResponse(status_code=404, _json={})
        with patch("src.core.ai.providers.gemini_provider.requests.request", return_value=fake_response):
            try:
                provider.generate_image(ImageGenerationRequest(prompt="x"))
                self.assert_true(False, "HTTP 404 must raise ProviderUnavailableError.")
            except ProviderUnavailableError as exc:
                self.assert_true("image_model" in str(exc) or "gemini-does-not-exist" in str(exc))

    def _test_gemini_generate_image_empty_response_fails(self) -> None:
        provider = self._make_gemini_provider()
        fake_response = _FakeHTTPResponse(
            status_code=200,
            _json={"candidates": [{"content": {"parts": [{"text": "no image here"}]}}]},
        )
        with patch("src.core.ai.providers.gemini_provider.requests.request", return_value=fake_response):
            try:
                provider.generate_image(ImageGenerationRequest(prompt="x"))
                self.assert_true(False, "Empty image response must raise ProviderUnavailableError.")
            except ProviderUnavailableError:
                self.assert_true(True)

    def _test_gemini_generate_image_invalid_count_raises_configuration_error(self) -> None:
        provider = self._make_gemini_provider()
        try:
            provider.generate_image(ImageGenerationRequest(prompt="x", number_of_images=0))
            self.assert_true(False, "number_of_images=0 must raise ProviderConfigurationError.")
        except ProviderConfigurationError:
            self.assert_true(True)

    def _test_gemini_generate_image_not_configured_raises_configuration_error(self) -> None:
        provider = self._make_gemini_provider(image_model=None)
        try:
            provider.generate_image(ImageGenerationRequest(prompt="x"))
            self.assert_true(False, "Unconfigured image_model must raise ProviderConfigurationError.")
        except ProviderConfigurationError:
            self.assert_true(True)
