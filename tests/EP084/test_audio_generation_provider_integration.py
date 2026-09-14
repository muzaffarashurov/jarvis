"""Real engineering tests for EP-084 STEP 2 - Audio & Speech Generation Integration.

Single combined test suite (NAME = "EP084"), following the same
precedent tests/EP082 and tests/EP083 already established.
Self-contained -- no import from any other `tests/EP0NN/` package.

Covers, per `EP084_DESIGN.md` Section 22:
    - `AIProvider.supports_speech_generation()`/`generate_speech()`
      base defaults (False / always raises), confirmed on both
      `ClaudeProvider` and the `ConfigDrivenProvider` placeholders --
      neither is modified by EP-084 and neither silently gains speech
      support.
    - `ProviderRequestExecutor.execute_speech()`: primary success,
      fallback disabled, fallback-eligible retry (skipping
      non-capable candidates), non-eligible immediate failure,
      fallback exhaustion -- mirroring tests/EP083's own
      `_test_executor_image_*` structure so the three suites are
      directly comparable.
    - `AudioGenerationService`: success path, disabled config, no
      provider selected, AI subsystem disabled, current provider
      lacks the capability (fails fast, zero executor/provider
      calls), fallback success, non-conversational structural check.
    - `GeminiProvider.generate_speech()`/`supports_speech_generation()`:
      request-shape/contract tests via mocked HTTP, mirroring
      tests/EP083's own Gemini image-generation mocking precedent.
    - `GeminiProvider._pcm_to_wav()`: PCM-to-WAV conversion (Owner
      Decision D2) -- valid WAV header, correct sample width/channels/
      rate, exact PCM payload preservation, and the documented
      default-rate fallback when a `mimeType` string cannot be parsed.
    - A light-touch, structural confirmation that `src.bootstrap`
      still imports cleanly and wires `AudioGenerationService`
      alongside the pre-existing `text_generation_service`/
      `image_generation_service` attributes.

Regression coverage for `ProviderRequestExecutor.execute()`/
`execute_image()` (text/image) and `AIService.ask()`/
`TextGenerationService`/`ImageGenerationService` themselves is NOT
duplicated here -- it is the responsibility of, and already covered
by, `tests/EP082`, `tests/EP083`, `tests/EP069`, `tests/EP069_2`,
`tests/EP069_3`, and `tests/EP069_4`, which this EP's STEP 2 requires
to keep passing unmodified.
"""

from __future__ import annotations

import base64
import inspect
import wave
from dataclasses import dataclass
from io import BytesIO
from unittest.mock import patch

from src.core.ai.claude_provider import ClaudeProvider
from src.core.ai.provider import (
    AIProvider,
    GeneratedAudio,
    ProviderConfigurationError,
    ProviderHealth,
    ProviderResponse,
    ProviderStatus,
    ProviderTimeoutError,
    ProviderUnavailableError,
    SpeechGenerationRequest,
    SpeechGenerationResult,
)
from src.core.ai.provider_factory import ConfigDrivenProvider
from src.core.ai.provider_request_executor import ProviderRequestExecutor
from src.core.ai.providers.gemini_provider import GeminiProvider
from src.services.audio_generation_service import AudioGenerationService
from src.services.audio_generation_service import (
    SpeechGenerationResult as ServiceSpeechGenerationResult,
)
from src.testing.base_test import BaseTest
from src.testing.registry import TestRegistry

# ---------- Fakes (mirrors tests/EP083's precedent) ----------


_DEFAULT_TEST_AUDIO = GeneratedAudio(data_base64="ZmFrZQ==", mime_type="audio/wav")


class _FakeAIProvider(AIProvider):
    """Deterministic, test-only concrete `AIProvider` (EP-084).

    `generate_speech()` either returns a fixed successful
    `SpeechGenerationResult` or raises a fixed exception, and records
    every call's arguments so tests can assert exactly what was sent.
    `speech_capable` controls `supports_speech_generation()`
    independently of availability, so tests can exercise "available
    but not speech-capable" providers explicitly.
    """

    def __init__(
        self,
        name: str,
        *,
        available: bool = True,
        speech_capable: bool = True,
        audio: GeneratedAudio = _DEFAULT_TEST_AUDIO,
        raise_error: Exception | None = None,
    ) -> None:
        self._name = name
        self._available = available
        self._speech_capable = speech_capable
        self._audio = audio
        self._raise_error = raise_error
        self.generate_speech_calls: list[SpeechGenerationRequest] = []

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

    def supports_speech_generation(self) -> bool:
        return self._speech_capable

    def generate_speech(self, request: SpeechGenerationRequest) -> SpeechGenerationResult:
        self.generate_speech_calls.append(request)
        if self._raise_error is not None:
            raise self._raise_error
        return SpeechGenerationResult(
            audio=self._audio, model=f"{self._name}-speech-model", latency_ms=1.0
        )


class _FakeProviderManager:
    """Deterministic, test-only stand-in for `ProviderManager` (EP-084).

    Exposes exactly the methods `ProviderRequestExecutor` and
    `AudioGenerationService` call: `get_current()`, `is_enabled()`,
    `list_fallback_candidates()`. Mirrors tests/EP083's own fake
    exactly.
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
    """Minimal stand-in for `requests.Response` (mirrors tests/EP082/EP083)."""

    status_code: int
    _json: dict
    text: str = ""

    def json(self) -> dict:
        return self._json


@TestRegistry.register
class AudioGenerationProviderIntegrationTest(BaseTest):
    NAME = "EP084"

    def run(self):
        # ---------- AIProvider base defaults ----------
        self._test_claude_provider_does_not_support_speech_generation()
        self._test_config_driven_provider_does_not_support_speech_generation()

        # ---------- ProviderRequestExecutor.execute_speech() ----------
        self._test_executor_speech_primary_success_no_fallback_attempted()
        self._test_executor_speech_fallback_disabled_fails_immediately()
        self._test_executor_speech_fallback_skips_non_capable_candidates()
        self._test_executor_speech_non_eligible_failure_never_retries()
        self._test_executor_speech_exhausted_fallback_reports_all_failures()
        self._test_executor_text_and_image_paths_unaffected_by_speech_addition()

        # ---------- AudioGenerationService ----------
        self._test_service_disabled_by_default()
        self._test_service_success_path()
        self._test_service_no_provider_selected()
        self._test_service_ai_subsystem_disabled()
        self._test_service_current_provider_lacks_capability_fails_fast()
        self._test_service_fallback_success()
        self._test_service_never_receives_conversation_or_context_dependency()

        # ---------- GeminiProvider speech support ----------
        self._test_gemini_supports_speech_generation_reflects_audio_model()
        self._test_gemini_generate_speech_success_wraps_pcm_as_wav()
        self._test_gemini_generate_speech_with_voice_and_seed_sent_correctly()
        self._test_gemini_generate_speech_language_hint_prepended_to_text()
        self._test_gemini_generate_speech_model_not_found_404()
        self._test_gemini_generate_speech_empty_response_fails()
        self._test_gemini_generate_speech_empty_text_raises_configuration_error()
        self._test_gemini_generate_speech_not_configured_raises_configuration_error()
        self._test_gemini_generate_speech_malformed_base64_raises_provider_error()

        # ---------- PCM -> WAV conversion (Owner Decision D2) ----------
        self._test_pcm_to_wav_produces_valid_header_and_preserves_payload()
        self._test_pcm_to_wav_parses_sample_rate_from_mime_type()
        self._test_pcm_to_wav_falls_back_to_default_rate_when_unparseable()

        # ---------- Bootstrap wiring ----------
        self._test_bootstrap_module_imports_and_wires_audio_generation_service()

        return self.result

    # ---------- AIProvider base defaults ----------

    def _test_claude_provider_does_not_support_speech_generation(self) -> None:
        provider = ClaudeProvider(
            enabled=True, api_key="k", model="claude-test", timeout=10, max_tokens=256, temperature=0.2
        )
        self.assert_false(provider.supports_speech_generation())
        try:
            provider.generate_speech(SpeechGenerationRequest(text="hello"))
            self.assert_true(False, "ClaudeProvider.generate_speech() must raise.")
        except ProviderUnavailableError:
            self.assert_true(True)

    def _test_config_driven_provider_does_not_support_speech_generation(self) -> None:
        provider = ConfigDrivenProvider(
            name="openai", enabled=True, credential_key="api_key", credential_value="k"
        )
        self.assert_false(provider.supports_speech_generation())
        try:
            provider.generate_speech(SpeechGenerationRequest(text="hello"))
            self.assert_true(False, "ConfigDrivenProvider.generate_speech() must raise.")
        except ProviderUnavailableError:
            self.assert_true(True)

    # ---------- ProviderRequestExecutor.execute_speech() ----------

    def _test_executor_speech_primary_success_no_fallback_attempted(self) -> None:
        primary = _FakeAIProvider("gemini", speech_capable=True)
        fallback = _FakeAIProvider("other", speech_capable=True)
        manager = _FakeProviderManager([fallback, primary], current=primary)
        executor = ProviderRequestExecutor(manager)
        request = SpeechGenerationRequest(text="hello there")

        outcome = executor.execute_speech(primary, request, fallback_enabled=True)

        self.assert_true(outcome.success)
        self.assert_equal(outcome.initial_provider, "gemini")
        self.assert_equal(outcome.final_provider, "gemini")
        self.assert_not_none(outcome.result)
        self.assert_equal(len(fallback.generate_speech_calls), 0)
        self.assert_equal(primary.generate_speech_calls[0].text, "hello there")

    def _test_executor_speech_fallback_disabled_fails_immediately(self) -> None:
        primary = _FakeAIProvider("gemini", raise_error=ProviderUnavailableError("down"))
        fallback = _FakeAIProvider("other", speech_capable=True)
        manager = _FakeProviderManager([fallback, primary], current=primary)
        executor = ProviderRequestExecutor(manager)

        outcome = executor.execute_speech(
            primary, SpeechGenerationRequest(text="x"), fallback_enabled=False
        )

        self.assert_false(outcome.success)
        self.assert_equal(len(fallback.generate_speech_calls), 0)
        self.assert_equal(len(manager.list_fallback_candidates_calls), 0)

    def _test_executor_speech_fallback_skips_non_capable_candidates(self) -> None:
        primary = _FakeAIProvider("gemini", raise_error=ProviderUnavailableError("down"))
        not_capable = _FakeAIProvider("claude", speech_capable=False)
        capable_fallback = _FakeAIProvider("other-speech-provider", speech_capable=True)
        # ProviderManager ordering returns the non-capable candidate
        # first -- the executor must skip it and reach the capable one.
        manager = _FakeProviderManager([not_capable, capable_fallback, primary], current=primary)
        executor = ProviderRequestExecutor(manager)

        outcome = executor.execute_speech(
            primary, SpeechGenerationRequest(text="x"), fallback_enabled=True
        )

        self.assert_true(outcome.success)
        self.assert_equal(outcome.final_provider, "other-speech-provider")
        self.assert_equal(
            len(not_capable.generate_speech_calls), 0, "Non-capable candidate must never be attempted."
        )

    def _test_executor_speech_non_eligible_failure_never_retries(self) -> None:
        primary = _FakeAIProvider("gemini", raise_error=ProviderConfigurationError("bad config"))
        fallback = _FakeAIProvider("other", speech_capable=True)
        manager = _FakeProviderManager([fallback, primary], current=primary)
        executor = ProviderRequestExecutor(manager)

        outcome = executor.execute_speech(
            primary, SpeechGenerationRequest(text="x"), fallback_enabled=True
        )

        self.assert_false(outcome.success)
        self.assert_equal(len(fallback.generate_speech_calls), 0)

    def _test_executor_speech_exhausted_fallback_reports_all_failures(self) -> None:
        primary = _FakeAIProvider("gemini", raise_error=ProviderUnavailableError("down"))
        fallback = _FakeAIProvider(
            "other", speech_capable=True, raise_error=ProviderTimeoutError("timeout")
        )
        manager = _FakeProviderManager([fallback, primary], current=primary)
        executor = ProviderRequestExecutor(manager)

        outcome = executor.execute_speech(
            primary, SpeechGenerationRequest(text="x"), fallback_enabled=True
        )

        self.assert_false(outcome.success)
        self.assert_true("gemini" in outcome.error and "other" in outcome.error)
        self.assert_true("ProviderUnavailableError" in outcome.error and "ProviderTimeoutError" in outcome.error)

    def _test_executor_text_and_image_paths_unaffected_by_speech_addition(self) -> None:
        # Light-touch confirmation within EP-084's own suite that the
        # `_run()` reuse did not disturb execute()'s text path or
        # execute_image()'s image path (full regression ownership
        # remains tests/EP082/tests/EP083).
        primary = _FakeAIProvider("gemini")
        manager = _FakeProviderManager([primary], current=primary)
        executor = ProviderRequestExecutor(manager)

        text_outcome = executor.execute(primary, "hello", fallback_enabled=False)
        # _FakeAIProvider.ask() always raises here (speech-focused
        # fake); this only confirms execute() still routes through
        # .ask(), not .generate_speech(), and never touches capability
        # filtering.
        self.assert_false(text_outcome.success)
        self.assert_equal(len(primary.generate_speech_calls), 0)

        from src.core.ai.provider import ImageGenerationRequest

        image_outcome = executor.execute_image(
            primary, ImageGenerationRequest(prompt="x"), fallback_enabled=False
        )
        # _FakeAIProvider does not override generate_image(), so the
        # base AIProvider always-raises default applies -- this only
        # confirms execute_image() still routes through
        # .generate_image(), untouched by the speech addition.
        self.assert_false(image_outcome.success)

    # ---------- AudioGenerationService ----------

    def _make_service(
        self,
        *,
        provider: _FakeAIProvider | None,
        ordered_providers: list[_FakeAIProvider] | None = None,
        enabled: bool = True,
        ai_enabled: bool = True,
        fallback_enabled: bool = False,
    ) -> tuple[AudioGenerationService, _FakeProviderManager]:
        manager = _FakeProviderManager(
            ordered_providers or ([provider] if provider else []),
            current=provider,
            enabled=ai_enabled,
        )
        executor = ProviderRequestExecutor(manager)
        service = AudioGenerationService(
            provider_manager=manager,
            request_executor=executor,
            enabled=enabled,
            fallback_enabled=fallback_enabled,
        )
        return service, manager

    def _test_service_disabled_by_default(self) -> None:
        provider = _FakeAIProvider("gemini")
        service, _ = self._make_service(provider=provider, enabled=False)

        result = service.generate(SpeechGenerationRequest(text="hi"))

        self.assert_false(result.success)
        self.assert_true("disabled" in result.error.lower())
        self.assert_equal(len(provider.generate_speech_calls), 0)

    def _test_service_success_path(self) -> None:
        provider = _FakeAIProvider("gemini")
        service, _ = self._make_service(provider=provider, enabled=True)

        result = service.generate(SpeechGenerationRequest(text="hi"))

        self.assert_true(result.success)
        self.assert_not_none(result.audio)
        self.assert_equal(result.provider_name, "gemini")
        self.assert_equal(result.model_name, "gemini-speech-model")
        self.assert_equal(result.error, "")
        self.assert_true(isinstance(result, ServiceSpeechGenerationResult))

    def _test_service_no_provider_selected(self) -> None:
        service, _ = self._make_service(provider=None, enabled=True)

        result = service.generate(SpeechGenerationRequest(text="hi"))

        self.assert_false(result.success)
        self.assert_true("No AI provider" in result.error)

    def _test_service_ai_subsystem_disabled(self) -> None:
        provider = _FakeAIProvider("gemini")
        service, _ = self._make_service(provider=provider, enabled=True, ai_enabled=False)

        result = service.generate(SpeechGenerationRequest(text="hi"))

        self.assert_false(result.success)
        self.assert_true("AI subsystem is disabled" in result.error)
        self.assert_equal(len(provider.generate_speech_calls), 0)

    def _test_service_current_provider_lacks_capability_fails_fast(self) -> None:
        provider = _FakeAIProvider("claude", speech_capable=False)
        service, _ = self._make_service(provider=provider, enabled=True)

        result = service.generate(SpeechGenerationRequest(text="hi"))

        self.assert_false(result.success)
        self.assert_true("does not support speech generation" in result.error)
        self.assert_equal(
            len(provider.generate_speech_calls), 0, "Must fail before any executor/provider call."
        )

    def _test_service_fallback_success(self) -> None:
        primary = _FakeAIProvider("gemini", raise_error=ProviderUnavailableError("down"))
        fallback = _FakeAIProvider("other", speech_capable=True)
        service, _ = self._make_service(
            provider=primary,
            ordered_providers=[fallback, primary],
            enabled=True,
            fallback_enabled=True,
        )

        result = service.generate(SpeechGenerationRequest(text="hi"))

        self.assert_true(result.success)
        self.assert_equal(result.provider_name, "other")

    def _test_service_never_receives_conversation_or_context_dependency(self) -> None:
        # EP084_DESIGN.md Section 14: AudioGenerationService's
        # constructor accepts no ConversationManager/ContextManager/
        # PromptManager argument at all -- verified structurally,
        # mirroring tests/EP083's own equivalent check.
        signature = inspect.signature(AudioGenerationService.__init__)
        forbidden_names = {"conversation_manager", "context_manager", "prompt_manager"}
        actual_names = set(signature.parameters.keys())
        self.assert_true(
            forbidden_names.isdisjoint(actual_names),
            f"AudioGenerationService must not depend on {forbidden_names}, "
            f"found overlap: {forbidden_names & actual_names}",
        )

    # ---------- GeminiProvider speech support ----------

    def _make_gemini_provider(self, audio_model: str | None = "gemini-2.5-flash-preview-tts") -> GeminiProvider:
        return GeminiProvider(
            enabled=True,
            api_key="test-key",
            model="gemini-test-model",
            timeout=10,
            max_tokens=256,
            temperature=0.2,
            audio_model=audio_model,
        )

    @staticmethod
    def _fake_pcm_base64(pattern: bytes = b"\x01\x02", repeat: int = 100) -> str:
        return base64.b64encode(pattern * repeat).decode("ascii")

    def _test_gemini_supports_speech_generation_reflects_audio_model(self) -> None:
        configured = self._make_gemini_provider(audio_model="gemini-2.5-flash-preview-tts")
        unconfigured = self._make_gemini_provider(audio_model=None)
        self.assert_true(configured.supports_speech_generation())
        self.assert_false(unconfigured.supports_speech_generation())

    def _test_gemini_generate_speech_success_wraps_pcm_as_wav(self) -> None:
        provider = self._make_gemini_provider()
        pcm_base64 = self._fake_pcm_base64()
        fake_response = _FakeHTTPResponse(
            status_code=200,
            _json={
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "inlineData": {
                                        "mimeType": "audio/L16;codec=pcm;rate=24000",
                                        "data": pcm_base64,
                                    }
                                },
                            ]
                        }
                    }
                ]
            },
        )
        with patch(
            "src.core.ai.providers.gemini_provider.requests.request", return_value=fake_response
        ) as mock_request:
            result = provider.generate_speech(SpeechGenerationRequest(text="Say hello"))

        # Result contract: always a WAV container, never the raw
        # provider mimeType (Owner Decision D2).
        self.assert_equal(result.audio.mime_type, "audio/wav")
        self.assert_equal(result.model, "gemini-2.5-flash-preview-tts")

        wav_bytes = base64.b64decode(result.audio.data_base64)
        with wave.open(BytesIO(wav_bytes), "rb") as wav_file:
            self.assert_equal(wav_file.getnchannels(), 1)
            self.assert_equal(wav_file.getsampwidth(), 2)
            self.assert_equal(wav_file.getframerate(), 24000)
            frames = wav_file.readframes(wav_file.getnframes())
        self.assert_equal(frames, base64.b64decode(pcm_base64), "PCM payload must survive WAV wrapping exactly.")

        payload = mock_request.call_args.kwargs["json"]
        self.assert_equal(payload["generationConfig"]["responseModalities"], ["AUDIO"])
        called_url = mock_request.call_args[0][1] if len(mock_request.call_args[0]) > 1 else ""
        self.assert_true("gemini-2.5-flash-preview-tts" in called_url)

    def _test_gemini_generate_speech_with_voice_and_seed_sent_correctly(self) -> None:
        provider = self._make_gemini_provider()
        pcm_base64 = self._fake_pcm_base64()
        fake_response = _FakeHTTPResponse(
            status_code=200,
            _json={
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {"inlineData": {"mimeType": "audio/L16;rate=24000", "data": pcm_base64}}
                            ]
                        }
                    }
                ]
            },
        )
        with patch(
            "src.core.ai.providers.gemini_provider.requests.request", return_value=fake_response
        ) as mock_request:
            provider.generate_speech(SpeechGenerationRequest(text="Say hello", voice="Kore", seed=42))

        payload = mock_request.call_args.kwargs["json"]
        self.assert_equal(
            payload["generationConfig"]["speechConfig"]["voiceConfig"]["prebuiltVoiceConfig"]["voiceName"],
            "Kore",
        )
        self.assert_equal(payload["generationConfig"]["seed"], 42)

    def _test_gemini_generate_speech_language_hint_prepended_to_text(self) -> None:
        # EP084_DESIGN.md Section 10: no structured Gemini language
        # parameter exists, so `language` is applied as a best-effort
        # natural-language instruction prepended to the request text.
        provider = self._make_gemini_provider()
        pcm_base64 = self._fake_pcm_base64()
        fake_response = _FakeHTTPResponse(
            status_code=200,
            _json={
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {"inlineData": {"mimeType": "audio/L16;rate=24000", "data": pcm_base64}}
                            ]
                        }
                    }
                ]
            },
        )
        with patch(
            "src.core.ai.providers.gemini_provider.requests.request", return_value=fake_response
        ) as mock_request:
            provider.generate_speech(SpeechGenerationRequest(text="Bonjour", language="French"))

        payload = mock_request.call_args.kwargs["json"]
        sent_text = payload["contents"][0]["parts"][0]["text"]
        self.assert_true("French" in sent_text and "Bonjour" in sent_text)

    def _test_gemini_generate_speech_model_not_found_404(self) -> None:
        # EP-084 mirrors EP-083 STEP 3's precedent: the speech path's
        # own 404 handling is new code, not shared with ask()'s
        # _build_model_not_found_error() -- must name 'audio_model'.
        provider = self._make_gemini_provider(audio_model="gemini-does-not-exist")
        fake_response = _FakeHTTPResponse(status_code=404, _json={})
        with patch("src.core.ai.providers.gemini_provider.requests.request", return_value=fake_response):
            try:
                provider.generate_speech(SpeechGenerationRequest(text="x"))
                self.assert_true(False, "HTTP 404 must raise ProviderUnavailableError.")
            except ProviderUnavailableError as exc:
                self.assert_true("audio_model" in str(exc) or "gemini-does-not-exist" in str(exc))

    def _test_gemini_generate_speech_empty_response_fails(self) -> None:
        provider = self._make_gemini_provider()
        fake_response = _FakeHTTPResponse(
            status_code=200,
            _json={"candidates": [{"content": {"parts": [{"text": "no audio here"}]}}]},
        )
        with patch("src.core.ai.providers.gemini_provider.requests.request", return_value=fake_response):
            try:
                provider.generate_speech(SpeechGenerationRequest(text="x"))
                self.assert_true(False, "Empty audio response must raise ProviderUnavailableError.")
            except ProviderUnavailableError:
                self.assert_true(True)

    def _test_gemini_generate_speech_empty_text_raises_configuration_error(self) -> None:
        provider = self._make_gemini_provider()
        try:
            provider.generate_speech(SpeechGenerationRequest(text="   "))
            self.assert_true(False, "Empty/blank 'text' must raise ProviderConfigurationError.")
        except ProviderConfigurationError:
            self.assert_true(True)

    def _test_gemini_generate_speech_not_configured_raises_configuration_error(self) -> None:
        provider = self._make_gemini_provider(audio_model=None)
        try:
            provider.generate_speech(SpeechGenerationRequest(text="x"))
            self.assert_true(False, "Unconfigured audio_model must raise ProviderConfigurationError.")
        except ProviderConfigurationError:
            self.assert_true(True)

    def _test_gemini_generate_speech_malformed_base64_raises_provider_error(self) -> None:
        # EP-084 STEP 3 audit finding (fixed in STEP 3): a corrupt/
        # malformed 'data' field previously escaped as a raw,
        # uncaught `binascii.Error` -- a non-`ProviderError` exception
        # that `ProviderRequestExecutor._run()`'s
        # `except ProviderError` clause cannot catch, crashing the
        # whole request path instead of producing a clean failure.
        # Confirms `_parse_speech_response()` now normalizes this into
        # `ProviderUnavailableError`.
        provider = self._make_gemini_provider()
        fake_response = _FakeHTTPResponse(
            status_code=200,
            _json={
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {"inlineData": {"mimeType": "audio/L16;rate=24000", "data": "not-valid-base64!!!"}}
                            ]
                        }
                    }
                ]
            },
        )
        with patch("src.core.ai.providers.gemini_provider.requests.request", return_value=fake_response):
            try:
                provider.generate_speech(SpeechGenerationRequest(text="x"))
                self.assert_true(False, "Malformed base64 audio data must raise ProviderUnavailableError.")
            except ProviderUnavailableError:
                self.assert_true(True)
            except Exception as exc:  # noqa: BLE001 - explicitly asserting this must NOT happen
                self.assert_true(
                    False, f"Malformed base64 must not escape as a raw {type(exc).__name__}: {exc}"
                )

    # ---------- PCM -> WAV conversion (Owner Decision D2) ----------

    def _test_pcm_to_wav_produces_valid_header_and_preserves_payload(self) -> None:
        pcm_bytes = b"\x10\x20\x30\x40" * 50
        pcm_base64 = base64.b64encode(pcm_bytes).decode("ascii")

        wav_base64 = GeminiProvider._pcm_to_wav(pcm_base64, "audio/L16;codec=pcm;rate=16000")
        wav_bytes = base64.b64decode(wav_base64)

        with wave.open(BytesIO(wav_bytes), "rb") as wav_file:
            self.assert_equal(wav_file.getnchannels(), 1)
            self.assert_equal(wav_file.getsampwidth(), 2)
            self.assert_equal(wav_file.getframerate(), 16000)
            frames = wav_file.readframes(wav_file.getnframes())
        self.assert_equal(frames, pcm_bytes)
        # A valid WAV container always begins with the RIFF/WAVE
        # header magic bytes.
        self.assert_equal(wav_bytes[0:4], b"RIFF")
        self.assert_equal(wav_bytes[8:12], b"WAVE")

    def _test_pcm_to_wav_parses_sample_rate_from_mime_type(self) -> None:
        pcm_base64 = self._fake_pcm_base64()
        wav_base64 = GeminiProvider._pcm_to_wav(pcm_base64, "audio/L16;codec=pcm;rate=48000")
        wav_bytes = base64.b64decode(wav_base64)
        with wave.open(BytesIO(wav_bytes), "rb") as wav_file:
            self.assert_equal(wav_file.getframerate(), 48000)

    def _test_pcm_to_wav_falls_back_to_default_rate_when_unparseable(self) -> None:
        # EP084_DESIGN.md Section 15: an unexpected/future mimeType
        # shape must fall back to Gemini's own current default (24000
        # Hz) rather than discarding an otherwise-successful response.
        pcm_base64 = self._fake_pcm_base64()
        wav_base64 = GeminiProvider._pcm_to_wav(pcm_base64, "audio/unexpected-format")
        wav_bytes = base64.b64decode(wav_base64)
        with wave.open(BytesIO(wav_bytes), "rb") as wav_file:
            self.assert_equal(wav_file.getframerate(), 24000)

    # ---------- Bootstrap wiring ----------

    def _test_bootstrap_module_imports_and_wires_audio_generation_service(self) -> None:
        # Lightweight, import-level compatibility check (mirrors this
        # repository's existing precedent of not constructing a full
        # `Bootstrap` instance in unit tests, which would require a
        # complete application config/database/etc.): confirm the
        # module still imports cleanly with EP-084's changes present,
        # and confirm `Bootstrap._build_command_router()`'s source
        # wires `_audio_generation_service` using the shared
        # `ai_request_executor`, exactly like
        # `_text_generation_service`/`_image_generation_service`.
        import src.bootstrap as bootstrap_module

        self.assert_true(hasattr(bootstrap_module, "Bootstrap"))
        self.assert_true(hasattr(bootstrap_module, "AudioGenerationService"))

        source = inspect.getsource(bootstrap_module.Bootstrap._build_command_router)
        self.assert_true("self._audio_generation_service = AudioGenerationService(" in source)
        self.assert_true('"audio_generation.enabled"' in source)
        self.assert_true('"audio_generation.fallback_enabled"' in source)
        # Confirm the pre-existing text/image wiring lines are still
        # present and unmodified in shape (EP-084 must not disturb
        # them).
        self.assert_true("self._text_generation_service = TextGenerationService(" in source)
        self.assert_true("self._image_generation_service = ImageGenerationService(" in source)
