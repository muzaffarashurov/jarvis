"""Real engineering tests for EP-086 STEP 2 - Presentation Generation Integration.

Single combined test suite (NAME = "EP086"), following the same
precedent tests/EP082-EP085 already established. Self-contained -- no
import from any other `tests/EP0NN/` package.

Covers, per `EP086_DESIGN.md` Section 19:
    - `AIProvider.supports_presentation_generation()`/
      `generate_presentation()` base defaults (False / always raises),
      confirmed on both `ClaudeProvider` and the `ConfigDrivenProvider`
      placeholders -- neither is modified by EP-086.
    - `ProviderRequestExecutor.execute_presentation()`: primary
      success, fallback disabled, fallback-eligible retry (skipping
      non-capable candidates), non-eligible immediate failure,
      fallback exhaustion, and an explicit same-provider-exclusion
      (duplicate-generation-safety) check -- mirroring
      tests/EP084/EP085's own executor test structure.
    - `PresentationGenerationService`: success path, disabled config,
      no provider selected, AI subsystem disabled, current provider
      lacks the capability (fails fast), fallback success,
      non-conversational structural check.
    - `GeminiProvider.generate_presentation()`/
      `supports_presentation_generation()`: request-shape (model,
      endpoint, responseMimeType, responseSchema, prompt content)
      verified via mocked HTTP; extensive adversarial parsing coverage
      (missing/malformed candidates, content, parts, text, invalid
      JSON, wrong top-level type, missing/malformed title, slides,
      slide fields, bullet points, speaker notes, and the STEP 2
      correction confirming an over-30-slide response is REJECTED,
      never silently truncated).
    - `slide_count` boundary enforcement: 0, negative, 30 (valid), 31
      (rejected) -- enforced on the request BEFORE any HTTP call.
    - Provider error passthrough (auth/rate-limit/timeout/network).
    - Configuration: `presentation_generation:` namespace defaults,
      `providers.gemini.presentation_model` threading and empty-string
      normalization.

Regression coverage for `execute()`/`execute_image()`/
`execute_speech()`/`execute_video()` themselves is NOT duplicated
here -- that is the responsibility of, and already covered by,
`tests/EP082`-`tests/EP085`, `tests/EP069`, `tests/EP069_2`,
`tests/EP069_3`, and `tests/EP069_4`, which this EP's STEP 2 requires
to keep passing unmodified.
"""

from __future__ import annotations

import inspect
import json
from dataclasses import dataclass
from unittest.mock import patch

from src.core.ai.claude_provider import ClaudeProvider
from src.core.ai.provider import (
    AIProvider,
    PresentationGenerationRequest,
    ProviderAuthenticationError,
    ProviderConfigurationError,
    ProviderHealth,
    ProviderNetworkError,
    ProviderRateLimitError,
    ProviderResponse,
    ProviderStatus,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from src.core.ai.provider_factory import ConfigDrivenProvider
from src.core.ai.provider_request_executor import ProviderRequestExecutor
from src.core.ai.providers.gemini_provider import GeminiProvider
from src.services.presentation_generation_service import (
    PresentationGenerationResult as ServicePresentationGenerationResult,
)
from src.services.presentation_generation_service import PresentationGenerationService
from src.testing.base_test import BaseTest
from src.testing.registry import TestRegistry


def _valid_presentation_payload(num_slides: int = 2) -> dict:
    return {
        "title": "Introduction to AI",
        "slides": [
            {
                "title": f"Slide {i}",
                "bullet_points": ["Point A", "Point B"],
                "speaker_notes": "Some notes." if i % 2 == 0 else None,
            }
            for i in range(num_slides)
        ],
    }


def _response_with_text(text: str, status_code: int = 200) -> _FakeHTTPResponse:
    return _FakeHTTPResponse(
        status_code=status_code,
        _json={"candidates": [{"content": {"parts": [{"text": text}]}}]},
    )


# ---------- Fakes (mirrors tests/EP083-EP085's precedent) ----------


class _FakeAIProvider(AIProvider):
    """Deterministic, test-only concrete `AIProvider` (EP-086)."""

    def __init__(
        self,
        name: str,
        *,
        available: bool = True,
        presentation_capable: bool = True,
        title: str = "Fake Title",
        raise_error: Exception | None = None,
    ) -> None:
        self._name = name
        self._available = available
        self._presentation_capable = presentation_capable
        self._title = title
        self._raise_error = raise_error
        self.generate_presentation_calls: list[PresentationGenerationRequest] = []

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

    def supports_presentation_generation(self) -> bool:
        return self._presentation_capable

    def generate_presentation(self, request: PresentationGenerationRequest):
        from src.core.ai.provider import (
            GeneratedPresentation,
            PresentationGenerationResult,
            PresentationSlide,
        )

        self.generate_presentation_calls.append(request)
        if self._raise_error is not None:
            raise self._raise_error
        presentation = GeneratedPresentation(
            title=self._title,
            slides=(PresentationSlide(title="S1", bullet_points=("a",), speaker_notes=None),),
        )
        return PresentationGenerationResult(
            presentation=presentation, model=f"{self._name}-presentation-model", latency_ms=1.0
        )


class _FakeProviderManager:
    """Deterministic, test-only stand-in for `ProviderManager` (EP-086)."""

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
    """Minimal stand-in for `requests.Response` (mirrors tests/EP082-085)."""

    status_code: int
    _json: dict
    text: str = ""

    def json(self) -> dict:
        return self._json


@TestRegistry.register
class PresentationGenerationProviderIntegrationTest(BaseTest):
    NAME = "EP086"

    def run(self):
        # ---------- Contracts ----------
        self._test_request_and_result_construction()

        # ---------- AIProvider base defaults ----------
        self._test_claude_provider_does_not_support_presentation_generation()
        self._test_config_driven_provider_does_not_support_presentation_generation()

        # ---------- ProviderRequestExecutor.execute_presentation() ----------
        self._test_executor_presentation_primary_success_no_fallback_attempted()
        self._test_executor_presentation_fallback_disabled_fails_immediately()
        self._test_executor_presentation_fallback_skips_non_capable_candidates()
        self._test_executor_presentation_non_eligible_failure_never_retries()
        self._test_executor_presentation_exhausted_fallback_reports_all_failures()
        self._test_executor_presentation_same_provider_never_retried_twice()
        self._test_executor_text_image_speech_video_paths_unaffected()

        # ---------- PresentationGenerationService ----------
        self._test_service_disabled_by_default()
        self._test_service_success_path()
        self._test_service_no_provider_selected()
        self._test_service_ai_subsystem_disabled()
        self._test_service_current_provider_lacks_capability_fails_fast()
        self._test_service_fallback_success()
        self._test_service_never_receives_conversation_or_context_dependency()

        # ---------- GeminiProvider request shape ----------
        self._test_gemini_supports_presentation_generation_reflects_presentation_model()
        self._test_gemini_generate_presentation_success_sends_correct_request()
        self._test_gemini_generate_presentation_audience_hint_included_in_prompt()
        self._test_gemini_generate_presentation_model_not_found_404()
        self._test_gemini_generate_presentation_not_configured_raises_configuration_error()
        self._test_gemini_generate_presentation_empty_topic_raises_configuration_error()
        self._test_gemini_generate_presentation_invalid_temperature_rejected()

        # ---------- slide_count boundary enforcement ----------
        self._test_gemini_generate_presentation_slide_count_zero_rejected()
        self._test_gemini_generate_presentation_slide_count_negative_rejected()
        self._test_gemini_generate_presentation_slide_count_30_accepted()
        self._test_gemini_generate_presentation_slide_count_31_rejected()

        # ---------- Adversarial parsing ----------
        self._test_gemini_parse_empty_object()
        self._test_gemini_parse_missing_candidates()
        self._test_gemini_parse_empty_candidates()
        self._test_gemini_parse_missing_content()
        self._test_gemini_parse_missing_parts()
        self._test_gemini_parse_empty_parts()
        self._test_gemini_parse_missing_text()
        self._test_gemini_parse_invalid_json_text()
        self._test_gemini_parse_json_array_instead_of_object()
        self._test_gemini_parse_missing_title()
        self._test_gemini_parse_missing_slides()
        self._test_gemini_parse_slides_not_an_array()
        self._test_gemini_parse_slide_not_an_object()
        self._test_gemini_parse_missing_slide_title()
        self._test_gemini_parse_bullet_points_not_an_array()
        self._test_gemini_parse_bullet_point_not_a_string()
        self._test_gemini_parse_invalid_speaker_notes_tolerated()
        self._test_gemini_parse_more_than_30_slides_rejected_not_truncated()
        self._test_gemini_parse_exactly_30_slides_accepted()
        self._test_gemini_parse_valid_response_success()

        # ---------- Provider error passthrough ----------
        self._test_gemini_generate_presentation_auth_failure()
        self._test_gemini_generate_presentation_rate_limit_failure()
        self._test_gemini_generate_presentation_network_failure()
        self._test_gemini_generate_presentation_timeout_failure()

        # ---------- Configuration ----------
        self._test_config_presentation_generation_defaults()
        self._test_config_presentation_model_empty_string_normalized_to_none()

        return self.result

    # ---------- Contracts ----------

    def _test_request_and_result_construction(self) -> None:
        from src.core.ai.provider import GeneratedPresentation, PresentationSlide

        slide = PresentationSlide(title="T", bullet_points=("a", "b"), speaker_notes="notes")
        self.assert_equal(slide.title, "T")
        self.assert_equal(slide.bullet_points, ("a", "b"))
        self.assert_equal(slide.speaker_notes, "notes")

        request = PresentationGenerationRequest(topic="AI", slide_count=5, audience="engineers")
        self.assert_equal(request.topic, "AI")
        self.assert_equal(request.slide_count, 5)
        self.assert_equal(request.audience, "engineers")
        self.assert_true(request.temperature is None)

        presentation = GeneratedPresentation(title="Deck", slides=(slide,))
        self.assert_equal(presentation.title, "Deck")
        self.assert_equal(len(presentation.slides), 1)
        # Content-only confirmation (EP086_DESIGN.md Section 6/11):
        # never bytes, never a URI.
        field_names = set(presentation.__dataclass_fields__)
        self.assert_equal(field_names, {"title", "slides"})

    # ---------- AIProvider base defaults ----------

    def _test_claude_provider_does_not_support_presentation_generation(self) -> None:
        provider = ClaudeProvider(
            enabled=True, api_key="k", model="claude-test", timeout=10, max_tokens=256, temperature=0.2
        )
        self.assert_false(provider.supports_presentation_generation())
        try:
            provider.generate_presentation(PresentationGenerationRequest(topic="hello"))
            self.assert_true(False, "ClaudeProvider.generate_presentation() must raise.")
        except ProviderUnavailableError:
            self.assert_true(True)

    def _test_config_driven_provider_does_not_support_presentation_generation(self) -> None:
        provider = ConfigDrivenProvider(
            name="openai", enabled=True, credential_key="api_key", credential_value="k"
        )
        self.assert_false(provider.supports_presentation_generation())
        try:
            provider.generate_presentation(PresentationGenerationRequest(topic="hello"))
            self.assert_true(False, "ConfigDrivenProvider.generate_presentation() must raise.")
        except ProviderUnavailableError:
            self.assert_true(True)

    # ---------- ProviderRequestExecutor.execute_presentation() ----------

    def _test_executor_presentation_primary_success_no_fallback_attempted(self) -> None:
        primary = _FakeAIProvider("gemini", presentation_capable=True)
        fallback = _FakeAIProvider("other", presentation_capable=True)
        manager = _FakeProviderManager([fallback, primary], current=primary)
        executor = ProviderRequestExecutor(manager)
        request = PresentationGenerationRequest(topic="machine learning basics")

        outcome = executor.execute_presentation(primary, request, fallback_enabled=True)

        self.assert_true(outcome.success)
        self.assert_equal(outcome.initial_provider, "gemini")
        self.assert_equal(outcome.final_provider, "gemini")
        self.assert_not_none(outcome.result)
        self.assert_equal(len(fallback.generate_presentation_calls), 0)
        self.assert_equal(primary.generate_presentation_calls[0].topic, "machine learning basics")

    def _test_executor_presentation_fallback_disabled_fails_immediately(self) -> None:
        primary = _FakeAIProvider("gemini", raise_error=ProviderUnavailableError("down"))
        fallback = _FakeAIProvider("other", presentation_capable=True)
        manager = _FakeProviderManager([fallback, primary], current=primary)
        executor = ProviderRequestExecutor(manager)

        outcome = executor.execute_presentation(
            primary, PresentationGenerationRequest(topic="x"), fallback_enabled=False
        )

        self.assert_false(outcome.success)
        self.assert_equal(len(fallback.generate_presentation_calls), 0)
        self.assert_equal(len(manager.list_fallback_candidates_calls), 0)

    def _test_executor_presentation_fallback_skips_non_capable_candidates(self) -> None:
        primary = _FakeAIProvider("gemini", raise_error=ProviderUnavailableError("down"))
        not_capable = _FakeAIProvider("claude", presentation_capable=False)
        capable_fallback = _FakeAIProvider("other-presentation-provider", presentation_capable=True)
        manager = _FakeProviderManager([not_capable, capable_fallback, primary], current=primary)
        executor = ProviderRequestExecutor(manager)

        outcome = executor.execute_presentation(
            primary, PresentationGenerationRequest(topic="x"), fallback_enabled=True
        )

        self.assert_true(outcome.success)
        self.assert_equal(outcome.final_provider, "other-presentation-provider")
        self.assert_equal(
            len(not_capable.generate_presentation_calls),
            0,
            "Non-capable candidate must never be attempted.",
        )

    def _test_executor_presentation_non_eligible_failure_never_retries(self) -> None:
        primary = _FakeAIProvider("gemini", raise_error=ProviderConfigurationError("bad config"))
        fallback = _FakeAIProvider("other", presentation_capable=True)
        manager = _FakeProviderManager([fallback, primary], current=primary)
        executor = ProviderRequestExecutor(manager)

        outcome = executor.execute_presentation(
            primary, PresentationGenerationRequest(topic="x"), fallback_enabled=True
        )

        self.assert_false(outcome.success)
        self.assert_equal(len(fallback.generate_presentation_calls), 0)

    def _test_executor_presentation_exhausted_fallback_reports_all_failures(self) -> None:
        primary = _FakeAIProvider("gemini", raise_error=ProviderUnavailableError("down"))
        fallback = _FakeAIProvider(
            "other", presentation_capable=True, raise_error=ProviderTimeoutError("timeout")
        )
        manager = _FakeProviderManager([fallback, primary], current=primary)
        executor = ProviderRequestExecutor(manager)

        outcome = executor.execute_presentation(
            primary, PresentationGenerationRequest(topic="x"), fallback_enabled=True
        )

        self.assert_false(outcome.success)
        self.assert_true("gemini" in outcome.error and "other" in outcome.error)
        self.assert_true(
            "ProviderUnavailableError" in outcome.error and "ProviderTimeoutError" in outcome.error
        )

    def _test_executor_presentation_same_provider_never_retried_twice(self) -> None:
        # Duplicate-generation safety (mirrors tests/EP085's own such
        # test): a provider that already failed must never be
        # attempted a second time by _run()'s exclude-based candidate
        # selection, regardless of how many times fallback triggers.
        primary = _FakeAIProvider("gemini", raise_error=ProviderUnavailableError("down"))
        manager = _FakeProviderManager([primary], current=primary)
        executor = ProviderRequestExecutor(manager)

        outcome = executor.execute_presentation(
            primary, PresentationGenerationRequest(topic="x"), fallback_enabled=True
        )

        self.assert_false(outcome.success)
        self.assert_equal(
            len(primary.generate_presentation_calls),
            1,
            "The same provider must never be attempted twice.",
        )

    def _test_executor_text_image_speech_video_paths_unaffected(self) -> None:
        # Light-touch confirmation within EP-086's own suite that the
        # _run() reuse did not disturb execute()/execute_image()/
        # execute_speech()/execute_video()'s own paths (full regression
        # ownership remains tests/EP082-EP085).
        primary = _FakeAIProvider("gemini")
        manager = _FakeProviderManager([primary], current=primary)
        executor = ProviderRequestExecutor(manager)

        text_outcome = executor.execute(primary, "hello", fallback_enabled=False)
        self.assert_false(text_outcome.success)

        from src.core.ai.provider import (
            ImageGenerationRequest,
            SpeechGenerationRequest,
            VideoGenerationRequest,
        )

        image_outcome = executor.execute_image(
            primary, ImageGenerationRequest(prompt="x"), fallback_enabled=False
        )
        self.assert_false(image_outcome.success)

        speech_outcome = executor.execute_speech(
            primary, SpeechGenerationRequest(text="x"), fallback_enabled=False
        )
        self.assert_false(speech_outcome.success)

        video_outcome = executor.execute_video(
            primary, VideoGenerationRequest(prompt="x"), fallback_enabled=False
        )
        self.assert_false(video_outcome.success)
        self.assert_equal(len(primary.generate_presentation_calls), 0)

    # ---------- PresentationGenerationService ----------

    def _make_service(
        self,
        *,
        provider: _FakeAIProvider | None,
        ordered_providers: list[_FakeAIProvider] | None = None,
        enabled: bool = True,
        ai_enabled: bool = True,
        fallback_enabled: bool = False,
    ) -> tuple[PresentationGenerationService, _FakeProviderManager]:
        manager = _FakeProviderManager(
            ordered_providers or ([provider] if provider else []),
            current=provider,
            enabled=ai_enabled,
        )
        executor = ProviderRequestExecutor(manager)
        service = PresentationGenerationService(
            provider_manager=manager,
            request_executor=executor,
            enabled=enabled,
            fallback_enabled=fallback_enabled,
        )
        return service, manager

    def _test_service_disabled_by_default(self) -> None:
        provider = _FakeAIProvider("gemini")
        service, _ = self._make_service(provider=provider, enabled=False)

        result = service.generate(PresentationGenerationRequest(topic="hi"))

        self.assert_false(result.success)
        self.assert_true("disabled" in result.error.lower())
        self.assert_equal(len(provider.generate_presentation_calls), 0)

    def _test_service_success_path(self) -> None:
        provider = _FakeAIProvider("gemini")
        service, _ = self._make_service(provider=provider, enabled=True)

        result = service.generate(PresentationGenerationRequest(topic="hi"))

        self.assert_true(result.success)
        self.assert_not_none(result.presentation)
        self.assert_equal(result.provider_name, "gemini")
        self.assert_equal(result.model_name, "gemini-presentation-model")
        self.assert_equal(result.error, "")
        self.assert_true(isinstance(result, ServicePresentationGenerationResult))

    def _test_service_no_provider_selected(self) -> None:
        service, _ = self._make_service(provider=None, enabled=True)

        result = service.generate(PresentationGenerationRequest(topic="hi"))

        self.assert_false(result.success)
        self.assert_true("No AI provider" in result.error)

    def _test_service_ai_subsystem_disabled(self) -> None:
        provider = _FakeAIProvider("gemini")
        service, _ = self._make_service(provider=provider, enabled=True, ai_enabled=False)

        result = service.generate(PresentationGenerationRequest(topic="hi"))

        self.assert_false(result.success)
        self.assert_true("AI subsystem is disabled" in result.error)
        self.assert_equal(len(provider.generate_presentation_calls), 0)

    def _test_service_current_provider_lacks_capability_fails_fast(self) -> None:
        provider = _FakeAIProvider("claude", presentation_capable=False)
        service, _ = self._make_service(provider=provider, enabled=True)

        result = service.generate(PresentationGenerationRequest(topic="hi"))

        self.assert_false(result.success)
        self.assert_true("does not support presentation generation" in result.error)
        self.assert_equal(
            len(provider.generate_presentation_calls), 0, "Must fail before any executor/provider call."
        )

    def _test_service_fallback_success(self) -> None:
        primary = _FakeAIProvider("gemini", raise_error=ProviderUnavailableError("down"))
        fallback = _FakeAIProvider("other", presentation_capable=True)
        service, _ = self._make_service(
            provider=primary,
            ordered_providers=[fallback, primary],
            enabled=True,
            fallback_enabled=True,
        )

        result = service.generate(PresentationGenerationRequest(topic="hi"))

        self.assert_true(result.success)
        self.assert_equal(result.provider_name, "other")

    def _test_service_never_receives_conversation_or_context_dependency(self) -> None:
        signature = inspect.signature(PresentationGenerationService.__init__)
        forbidden_names = {"conversation_manager", "context_manager", "prompt_manager"}
        actual_names = set(signature.parameters.keys())
        self.assert_true(
            forbidden_names.isdisjoint(actual_names),
            f"PresentationGenerationService must not depend on {forbidden_names}, "
            f"found overlap: {forbidden_names & actual_names}",
        )

    # ---------- GeminiProvider request shape ----------

    def _make_gemini_provider(self, presentation_model: str | None = "gemini-3.1-flash") -> GeminiProvider:
        return GeminiProvider(
            enabled=True,
            api_key="test-key",
            model="gemini-test-model",
            timeout=10,
            max_tokens=256,
            temperature=0.2,
            presentation_model=presentation_model,
        )

    def _test_gemini_supports_presentation_generation_reflects_presentation_model(self) -> None:
        configured = self._make_gemini_provider(presentation_model="gemini-3.1-flash")
        unconfigured = self._make_gemini_provider(presentation_model=None)
        self.assert_true(configured.supports_presentation_generation())
        self.assert_false(unconfigured.supports_presentation_generation())

    def _test_gemini_generate_presentation_success_sends_correct_request(self) -> None:
        provider = self._make_gemini_provider()
        fake_response = _response_with_text(json.dumps(_valid_presentation_payload()))
        with patch(
            "src.core.ai.providers.gemini_provider.requests.request", return_value=fake_response
        ) as mock_request:
            result = provider.generate_presentation(
                PresentationGenerationRequest(topic="Intro to AI", slide_count=5)
            )

        self.assert_equal(result.model, "gemini-3.1-flash")
        self.assert_equal(result.presentation.title, "Introduction to AI")
        self.assert_equal(len(result.presentation.slides), 2)

        call = mock_request.call_args
        called_url = call[0][1] if len(call[0]) > 1 else call.args[1]
        self.assert_true("gemini-3.1-flash" in called_url and "generateContent" in called_url)

        payload = call.kwargs["json"]
        self.assert_equal(payload["generationConfig"]["responseMimeType"], "application/json")
        schema = payload["generationConfig"]["responseSchema"]
        self.assert_equal(schema["type"], "object")
        self.assert_true("title" in schema["properties"])
        self.assert_true("slides" in schema["properties"])
        self.assert_equal(schema["properties"]["slides"]["type"], "array")
        self.assert_equal(schema["properties"]["slides"]["maxItems"], 5)
        self.assert_equal(schema["required"], ["title", "slides"])

        prompt_text = payload["contents"][0]["parts"][0]["text"]
        self.assert_true("Intro to AI" in prompt_text)
        self.assert_true("5 slides" in prompt_text)

    def _test_gemini_generate_presentation_audience_hint_included_in_prompt(self) -> None:
        provider = self._make_gemini_provider()
        fake_response = _response_with_text(json.dumps(_valid_presentation_payload()))
        with patch(
            "src.core.ai.providers.gemini_provider.requests.request", return_value=fake_response
        ) as mock_request:
            provider.generate_presentation(
                PresentationGenerationRequest(topic="AI", audience="executives")
            )
        payload = mock_request.call_args.kwargs["json"]
        prompt_text = payload["contents"][0]["parts"][0]["text"]
        self.assert_true("executives" in prompt_text)

    def _test_gemini_generate_presentation_model_not_found_404(self) -> None:
        provider = self._make_gemini_provider(presentation_model="gemini-does-not-exist")
        fake_response = _FakeHTTPResponse(status_code=404, _json={})
        with patch("src.core.ai.providers.gemini_provider.requests.request", return_value=fake_response):
            try:
                provider.generate_presentation(PresentationGenerationRequest(topic="x"))
                self.assert_true(False, "HTTP 404 must raise ProviderUnavailableError.")
            except ProviderUnavailableError as exc:
                self.assert_true(
                    "presentation_model" in str(exc) or "gemini-does-not-exist" in str(exc)
                )

    def _test_gemini_generate_presentation_not_configured_raises_configuration_error(self) -> None:
        provider = self._make_gemini_provider(presentation_model=None)
        try:
            provider.generate_presentation(PresentationGenerationRequest(topic="x"))
            self.assert_true(
                False, "Unconfigured presentation_model must raise ProviderConfigurationError."
            )
        except ProviderConfigurationError:
            self.assert_true(True)

    def _test_gemini_generate_presentation_empty_topic_raises_configuration_error(self) -> None:
        provider = self._make_gemini_provider()
        try:
            provider.generate_presentation(PresentationGenerationRequest(topic="   "))
            self.assert_true(False, "Empty/blank 'topic' must raise ProviderConfigurationError.")
        except ProviderConfigurationError:
            self.assert_true(True)

    def _test_gemini_generate_presentation_invalid_temperature_rejected(self) -> None:
        provider = self._make_gemini_provider()
        try:
            provider.generate_presentation(PresentationGenerationRequest(topic="x", temperature=5.0))
            self.assert_true(False, "Out-of-range temperature must raise ProviderConfigurationError.")
        except ProviderConfigurationError:
            self.assert_true(True)

    # ---------- slide_count boundary enforcement ----------

    def _test_gemini_generate_presentation_slide_count_zero_rejected(self) -> None:
        provider = self._make_gemini_provider()
        try:
            provider.generate_presentation(PresentationGenerationRequest(topic="x", slide_count=0))
            self.assert_true(False, "slide_count=0 must be rejected.")
        except ProviderConfigurationError:
            self.assert_true(True)

    def _test_gemini_generate_presentation_slide_count_negative_rejected(self) -> None:
        provider = self._make_gemini_provider()
        try:
            provider.generate_presentation(PresentationGenerationRequest(topic="x", slide_count=-3))
            self.assert_true(False, "Negative slide_count must be rejected.")
        except ProviderConfigurationError:
            self.assert_true(True)

    def _test_gemini_generate_presentation_slide_count_30_accepted(self) -> None:
        provider = self._make_gemini_provider()
        fake_response = _response_with_text(json.dumps(_valid_presentation_payload(num_slides=1)))
        with patch("src.core.ai.providers.gemini_provider.requests.request", return_value=fake_response):
            try:
                provider.generate_presentation(PresentationGenerationRequest(topic="x", slide_count=30))
                self.assert_true(True)
            except ProviderConfigurationError:
                self.assert_true(False, "slide_count=30 (the approved maximum) must be accepted.")

    def _test_gemini_generate_presentation_slide_count_31_rejected(self) -> None:
        provider = self._make_gemini_provider()
        try:
            provider.generate_presentation(PresentationGenerationRequest(topic="x", slide_count=31))
            self.assert_true(False, "slide_count=31 must be rejected.")
        except ProviderConfigurationError:
            self.assert_true(True)

    # ---------- Adversarial parsing ----------

    def _assert_rejected(self, fake_response: _FakeHTTPResponse) -> None:
        provider = self._make_gemini_provider()
        with patch("src.core.ai.providers.gemini_provider.requests.request", return_value=fake_response):
            try:
                provider.generate_presentation(PresentationGenerationRequest(topic="x"))
                self.assert_true(False, "Malformed response must raise ProviderUnavailableError.")
            except ProviderUnavailableError:
                self.assert_true(True)
            except Exception as exc:  # noqa: BLE001 - explicitly asserting this must NOT happen
                self.assert_true(False, f"Must not escape as a raw {type(exc).__name__}: {exc}")

    def _test_gemini_parse_empty_object(self) -> None:
        self._assert_rejected(_FakeHTTPResponse(status_code=200, _json={}))

    def _test_gemini_parse_missing_candidates(self) -> None:
        self._assert_rejected(_FakeHTTPResponse(status_code=200, _json={"other": "field"}))

    def _test_gemini_parse_empty_candidates(self) -> None:
        self._assert_rejected(_FakeHTTPResponse(status_code=200, _json={"candidates": []}))

    def _test_gemini_parse_missing_content(self) -> None:
        self._assert_rejected(_FakeHTTPResponse(status_code=200, _json={"candidates": [{}]}))

    def _test_gemini_parse_missing_parts(self) -> None:
        self._assert_rejected(
            _FakeHTTPResponse(status_code=200, _json={"candidates": [{"content": {}}]})
        )

    def _test_gemini_parse_empty_parts(self) -> None:
        self._assert_rejected(
            _FakeHTTPResponse(status_code=200, _json={"candidates": [{"content": {"parts": []}}]})
        )

    def _test_gemini_parse_missing_text(self) -> None:
        self._assert_rejected(
            _FakeHTTPResponse(
                status_code=200, _json={"candidates": [{"content": {"parts": [{"notText": "x"}]}}]}
            )
        )

    def _test_gemini_parse_invalid_json_text(self) -> None:
        self._assert_rejected(_response_with_text("this is not valid json {{{"))

    def _test_gemini_parse_json_array_instead_of_object(self) -> None:
        self._assert_rejected(_response_with_text(json.dumps(["not", "an", "object"])))

    def _test_gemini_parse_missing_title(self) -> None:
        payload = _valid_presentation_payload()
        del payload["title"]
        self._assert_rejected(_response_with_text(json.dumps(payload)))

    def _test_gemini_parse_missing_slides(self) -> None:
        self._assert_rejected(_response_with_text(json.dumps({"title": "T"})))

    def _test_gemini_parse_slides_not_an_array(self) -> None:
        self._assert_rejected(_response_with_text(json.dumps({"title": "T", "slides": "not-a-list"})))

    def _test_gemini_parse_slide_not_an_object(self) -> None:
        self._assert_rejected(
            _response_with_text(json.dumps({"title": "T", "slides": ["not-an-object"]}))
        )

    def _test_gemini_parse_missing_slide_title(self) -> None:
        self._assert_rejected(
            _response_with_text(
                json.dumps({"title": "T", "slides": [{"bullet_points": ["a"]}]})
            )
        )

    def _test_gemini_parse_bullet_points_not_an_array(self) -> None:
        self._assert_rejected(
            _response_with_text(
                json.dumps({"title": "T", "slides": [{"title": "S1", "bullet_points": "not-a-list"}]})
            )
        )

    def _test_gemini_parse_bullet_point_not_a_string(self) -> None:
        # Non-string bullet points are filtered out individually, not
        # treated as a fatal slide error -- but a slide with zero
        # SURVIVING bullet points after filtering (all non-strings)
        # still yields a valid slide with an empty bullet_points tuple
        # (a title-only slide is legitimate, EP086_DESIGN.md Section
        # 9), so this must succeed, not be rejected.
        provider = self._make_gemini_provider()
        payload = {
            "title": "T",
            "slides": [{"title": "S1", "bullet_points": [1, 2, 3]}],
        }
        fake_response = _response_with_text(json.dumps(payload))
        with patch("src.core.ai.providers.gemini_provider.requests.request", return_value=fake_response):
            result = provider.generate_presentation(PresentationGenerationRequest(topic="x"))
        self.assert_equal(result.presentation.slides[0].bullet_points, ())

    def _test_gemini_parse_invalid_speaker_notes_tolerated(self) -> None:
        # A non-string speaker_notes value is treated as absent
        # (None), not a fatal error -- it is an optional field
        # (EP086_DESIGN.md Section 9).
        provider = self._make_gemini_provider()
        payload = {
            "title": "T",
            "slides": [{"title": "S1", "bullet_points": ["a"], "speaker_notes": 12345}],
        }
        fake_response = _response_with_text(json.dumps(payload))
        with patch("src.core.ai.providers.gemini_provider.requests.request", return_value=fake_response):
            result = provider.generate_presentation(PresentationGenerationRequest(topic="x"))
        self.assert_true(result.presentation.slides[0].speaker_notes is None)

    def _test_gemini_parse_more_than_30_slides_rejected_not_truncated(self) -> None:
        # STEP 2 correction: a response violating the 30-slide bound
        # is REJECTED as malformed provider output, never silently
        # truncated to fit.
        payload = {
            "title": "Too Many",
            "slides": [{"title": f"S{i}", "bullet_points": ["x"]} for i in range(31)],
        }
        self._assert_rejected(_response_with_text(json.dumps(payload)))

    def _test_gemini_parse_exactly_30_slides_accepted(self) -> None:
        provider = self._make_gemini_provider()
        payload = {
            "title": "Exactly 30",
            "slides": [{"title": f"S{i}", "bullet_points": ["x"]} for i in range(30)],
        }
        fake_response = _response_with_text(json.dumps(payload))
        with patch("src.core.ai.providers.gemini_provider.requests.request", return_value=fake_response):
            result = provider.generate_presentation(PresentationGenerationRequest(topic="x"))
        self.assert_equal(len(result.presentation.slides), 30)

    def _test_gemini_parse_valid_response_success(self) -> None:
        provider = self._make_gemini_provider()
        fake_response = _response_with_text(json.dumps(_valid_presentation_payload(num_slides=3)))
        with patch("src.core.ai.providers.gemini_provider.requests.request", return_value=fake_response):
            result = provider.generate_presentation(PresentationGenerationRequest(topic="x"))
        self.assert_equal(result.presentation.title, "Introduction to AI")
        self.assert_equal(len(result.presentation.slides), 3)
        self.assert_equal(result.presentation.slides[0].title, "Slide 0")
        self.assert_equal(result.presentation.slides[0].speaker_notes, "Some notes.")
        self.assert_true(result.presentation.slides[1].speaker_notes is None)

    # ---------- Provider error passthrough ----------

    def _test_gemini_generate_presentation_auth_failure(self) -> None:
        provider = self._make_gemini_provider()
        fake_response = _FakeHTTPResponse(status_code=401, _json={})
        with patch("src.core.ai.providers.gemini_provider.requests.request", return_value=fake_response):
            try:
                provider.generate_presentation(PresentationGenerationRequest(topic="x"))
                self.assert_true(False, "HTTP 401 must raise ProviderAuthenticationError.")
            except ProviderAuthenticationError:
                self.assert_true(True)

    def _test_gemini_generate_presentation_rate_limit_failure(self) -> None:
        provider = self._make_gemini_provider()
        fake_response = _FakeHTTPResponse(status_code=429, _json={})
        with patch("src.core.ai.providers.gemini_provider.requests.request", return_value=fake_response):
            try:
                provider.generate_presentation(PresentationGenerationRequest(topic="x"))
                self.assert_true(False, "HTTP 429 must raise ProviderRateLimitError.")
            except ProviderRateLimitError:
                self.assert_true(True)

    def _test_gemini_generate_presentation_network_failure(self) -> None:
        provider = self._make_gemini_provider()
        with patch(
            "src.core.ai.providers.gemini_provider.requests.request",
            side_effect=ProviderNetworkError("connection failed"),
        ):
            try:
                provider.generate_presentation(PresentationGenerationRequest(topic="x"))
                self.assert_true(False, "A network failure must raise ProviderNetworkError.")
            except ProviderNetworkError:
                self.assert_true(True)

    def _test_gemini_generate_presentation_timeout_failure(self) -> None:
        provider = self._make_gemini_provider()
        with patch(
            "src.core.ai.providers.gemini_provider.requests.request",
            side_effect=ProviderTimeoutError("timed out"),
        ):
            try:
                provider.generate_presentation(PresentationGenerationRequest(topic="x"))
                self.assert_true(False, "A timeout must raise ProviderTimeoutError.")
            except ProviderTimeoutError:
                self.assert_true(True)

    # ---------- Configuration ----------

    def _test_config_presentation_generation_defaults(self) -> None:
        import yaml

        with open("config/config.yaml", encoding="utf-8") as f:
            config = yaml.safe_load(f)
        presentation_generation = config.get("presentation_generation")
        self.assert_not_none(presentation_generation)
        self.assert_equal(presentation_generation.get("enabled"), False)
        self.assert_equal(presentation_generation.get("fallback_enabled"), False)

    def _test_config_presentation_model_empty_string_normalized_to_none(self) -> None:
        provider = GeminiProvider(
            enabled=True,
            api_key="k",
            model="m",
            timeout=10,
            max_tokens=100,
            temperature=0.2,
            presentation_model="",
        )
        self.assert_false(provider.supports_presentation_generation())
