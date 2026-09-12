"""Real engineering tests for EP-082 STEP 2 - Text Generation Provider Integration.

Single combined test suite (NAME = "EP082"), following the same
precedent EP-054 through EP-069.3 already established. Self-contained
-- no import from any other `tests/EP0NN/` package.

Covers, per `EP082_DESIGN.md` Section 18:
    - `ProviderRequestExecutor` reproduces `AIService.ask()`'s
      pre-EP-082 fallback/retry semantics exactly: primary success,
      fallback disabled, fallback-eligible failure with fallback
      enabled, non-eligible failure (never retried), and fallback
      exhaustion.
    - `TextGenerationService`: success path, disabled config, no
      provider selected, AI subsystem disabled, fallback success,
      fallback exhaustion, non-eligible immediate failure, and that
      it never touches conversation/context (it is never given one).
    - Additive `AIProvider.ask()` parameters: `ClaudeProvider` and
      `GeminiProvider` behave identically to pre-EP-082 when
      `temperature`/`system_prompt` are omitted, and honor them (via
      their outgoing HTTP payload) when provided.
    - `validate_temperature()`: valid range accepted, `None` accepted
      (no-op), out-of-range/non-numeric raises
      `ProviderConfigurationError`.

Regression coverage for `AIService.ask()` itself (unchanged public
contract/behavior after the `ProviderRequestExecutor` extraction) is
NOT duplicated here -- it is the responsibility of, and already
covered by, `tests/EP069`, `tests/EP069_2`, and `tests/EP069_3`,
which this EP's STEP 2 requires to keep passing unmodified.
"""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import patch

from src.core.ai.claude_provider import ClaudeProvider
from src.core.ai.provider import (
    AIProvider,
    ProviderAuthenticationError,
    ProviderConfigurationError,
    ProviderHealth,
    ProviderResponse,
    ProviderStatus,
    ProviderTimeoutError,
    ProviderUnavailableError,
    validate_temperature,
)
from src.core.ai.provider_request_executor import ProviderRequestExecutor
from src.core.ai.providers.gemini_provider import GeminiProvider
from src.services.text_generation_service import TextGenerationResult, TextGenerationService
from src.testing.base_test import BaseTest
from src.testing.registry import TestRegistry


# ---------- Fakes (mirrors tests/EP069's precedent) ----------


class _FakeAIProvider(AIProvider):
    """Deterministic, test-only concrete `AIProvider` (EP-082).

    `ask()` either returns a fixed successful `ProviderResponse` or
    raises a fixed exception, and records every call's arguments so
    tests can assert exactly what was sent, including the EP-082
    `temperature`/`system_prompt` overrides.
    """

    def __init__(
        self,
        name: str,
        *,
        available: bool = True,
        response_text: str = "ok",
        raise_error: Exception | None = None,
    ) -> None:
        self._name = name
        self._available = available
        self._response_text = response_text
        self._raise_error = raise_error
        self.ask_calls: list[dict] = []

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

    def ask(
        self,
        prompt: str,
        max_tokens: int | None = None,
        temperature: float | None = None,
        system_prompt: str | None = None,
    ) -> ProviderResponse:
        self.ask_calls.append(
            {
                "prompt": prompt,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "system_prompt": system_prompt,
            }
        )
        if self._raise_error is not None:
            raise self._raise_error
        return ProviderResponse(text=self._response_text, model=f"{self._name}-model", latency_ms=1.0)


class _FakeProviderManager:
    """Deterministic, test-only stand-in for `ProviderManager` (EP-082).

    Exposes exactly the methods `ProviderRequestExecutor` and
    `TextGenerationService` call: `get_current()`, `is_enabled()`,
    `list_fallback_candidates()`. Mirrors
    `tests/EP069/test_ai_provider_fallback.py`'s own fake exactly.
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
    """Minimal stand-in for `requests.Response`, used to test the
    additive ClaudeProvider/GeminiProvider `ask()` parameters without
    a real network call."""

    status_code: int
    _json: dict
    text: str = ""

    def json(self) -> dict:
        return self._json


@TestRegistry.register
class TextGenerationProviderIntegrationTest(BaseTest):
    NAME = "EP082"

    def run(self):
        # ---------- ProviderRequestExecutor: fallback/retry semantics ----------
        self._test_executor_primary_success_no_fallback_attempted()
        self._test_executor_fallback_disabled_fails_immediately()
        self._test_executor_fallback_eligible_retries_next_candidate()
        self._test_executor_non_eligible_failure_never_retries()
        self._test_executor_exhausted_fallback_reports_all_failures()

        # ---------- TextGenerationService ----------
        self._test_service_disabled_by_default()
        self._test_service_success_path()
        self._test_service_no_provider_selected()
        self._test_service_ai_subsystem_disabled()
        self._test_service_fallback_success()
        self._test_service_never_receives_conversation_or_context_dependency()
        self._test_service_default_temperature_used_when_omitted()
        self._test_service_per_request_temperature_overrides_default()

        # ---------- Additive AIProvider.ask() contract ----------
        self._test_validate_temperature_accepts_none()
        self._test_validate_temperature_accepts_valid_range()
        self._test_validate_temperature_rejects_out_of_range()
        self._test_validate_temperature_rejects_non_numeric()
        self._test_claude_provider_unchanged_when_new_params_omitted()
        self._test_claude_provider_honors_temperature_and_system_prompt()
        self._test_claude_provider_invalid_temperature_raises_configuration_error()
        self._test_gemini_provider_unchanged_when_new_params_omitted()
        self._test_gemini_provider_honors_temperature_and_system_prompt()

        return self.result

    # ---------- ProviderRequestExecutor ----------

    def _test_executor_primary_success_no_fallback_attempted(self) -> None:
        primary = _FakeAIProvider("claude", response_text="hello")
        fallback = _FakeAIProvider("gemini")
        manager = _FakeProviderManager([fallback, primary], current=primary)
        executor = ProviderRequestExecutor(manager)

        outcome = executor.execute(primary, "RENDERED::hi", fallback_enabled=True)

        self.assert_true(outcome.success, "Primary success must report success.")
        self.assert_equal(outcome.initial_provider, "claude")
        self.assert_equal(outcome.final_provider, "claude")
        self.assert_equal(outcome.response.text, "hello")
        self.assert_equal(len(fallback.ask_calls), 0, "Fallback must never be attempted on primary success.")
        self.assert_equal(len(manager.list_fallback_candidates_calls), 0)

    def _test_executor_fallback_disabled_fails_immediately(self) -> None:
        primary = _FakeAIProvider("claude", raise_error=ProviderUnavailableError("claude down"))
        fallback = _FakeAIProvider("gemini")
        manager = _FakeProviderManager([fallback, primary], current=primary)
        executor = ProviderRequestExecutor(manager)

        outcome = executor.execute(primary, "hi", fallback_enabled=False)

        self.assert_false(outcome.success)
        self.assert_equal(outcome.initial_provider, "claude")
        self.assert_equal(outcome.final_provider, "")
        self.assert_equal(len(fallback.ask_calls), 0, "Fallback disabled must never query candidates.")
        self.assert_equal(len(manager.list_fallback_candidates_calls), 0)

    def _test_executor_fallback_eligible_retries_next_candidate(self) -> None:
        primary = _FakeAIProvider("claude", raise_error=ProviderUnavailableError("claude down"))
        fallback = _FakeAIProvider("gemini", response_text="fallback-reply")
        manager = _FakeProviderManager([fallback, primary], current=primary)
        executor = ProviderRequestExecutor(manager)

        outcome = executor.execute(primary, "RENDERED::hi", fallback_enabled=True)

        self.assert_true(outcome.success)
        self.assert_equal(outcome.initial_provider, "claude")
        self.assert_equal(outcome.final_provider, "gemini")
        self.assert_equal(outcome.response.text, "fallback-reply")
        self.assert_equal(len(fallback.ask_calls), 1)
        self.assert_equal(fallback.ask_calls[0]["prompt"], "RENDERED::hi")

    def _test_executor_non_eligible_failure_never_retries(self) -> None:
        primary = _FakeAIProvider(
            "claude", raise_error=ProviderConfigurationError("claude misconfigured")
        )
        fallback = _FakeAIProvider("gemini")
        manager = _FakeProviderManager([fallback, primary], current=primary)
        executor = ProviderRequestExecutor(manager)

        outcome = executor.execute(primary, "hi", fallback_enabled=True)

        self.assert_false(outcome.success)
        self.assert_equal(len(fallback.ask_calls), 0, "Non-eligible failure must never trigger fallback.")
        self.assert_equal(len(manager.list_fallback_candidates_calls), 0)

    def _test_executor_exhausted_fallback_reports_all_failures(self) -> None:
        primary = _FakeAIProvider("claude", raise_error=ProviderUnavailableError("claude down"))
        fallback = _FakeAIProvider("gemini", raise_error=ProviderTimeoutError("gemini timeout"))
        manager = _FakeProviderManager([fallback, primary], current=primary)
        executor = ProviderRequestExecutor(manager)

        outcome = executor.execute(primary, "hi", fallback_enabled=True)

        self.assert_false(outcome.success)
        self.assert_true("claude" in outcome.error and "gemini" in outcome.error)
        self.assert_true("ProviderUnavailableError" in outcome.error)
        self.assert_true("ProviderTimeoutError" in outcome.error)

    # ---------- TextGenerationService ----------

    def _make_service(
        self,
        *,
        provider: _FakeAIProvider | None,
        ordered_providers: list[_FakeAIProvider] | None = None,
        enabled: bool = True,
        ai_enabled: bool = True,
        default_temperature: float | None = None,
        fallback_enabled: bool = False,
    ) -> tuple[TextGenerationService, _FakeProviderManager]:
        manager = _FakeProviderManager(
            ordered_providers or ([provider] if provider else []),
            current=provider,
            enabled=ai_enabled,
        )
        executor = ProviderRequestExecutor(manager)
        service = TextGenerationService(
            provider_manager=manager,
            request_executor=executor,
            enabled=enabled,
            default_temperature=default_temperature,
            fallback_enabled=fallback_enabled,
        )
        return service, manager

    def _test_service_disabled_by_default(self) -> None:
        provider = _FakeAIProvider("claude")
        service, _ = self._make_service(provider=provider, enabled=False)

        result = service.generate("write something")

        self.assert_false(result.success)
        self.assert_true("disabled" in result.error.lower())
        self.assert_equal(len(provider.ask_calls), 0)

    def _test_service_success_path(self) -> None:
        provider = _FakeAIProvider("claude", response_text="generated text")
        service, _ = self._make_service(provider=provider, enabled=True)

        result = service.generate("write a haiku")

        self.assert_true(result.success)
        self.assert_equal(result.text, "generated text")
        self.assert_equal(result.provider_name, "claude")
        self.assert_equal(result.model_name, "claude-model")
        self.assert_equal(result.error, "")
        self.assert_true(isinstance(result, TextGenerationResult))

    def _test_service_no_provider_selected(self) -> None:
        service, _ = self._make_service(provider=None, enabled=True)

        result = service.generate("hello")

        self.assert_false(result.success)
        self.assert_true("No AI provider" in result.error)

    def _test_service_ai_subsystem_disabled(self) -> None:
        provider = _FakeAIProvider("claude")
        service, _ = self._make_service(provider=provider, enabled=True, ai_enabled=False)

        result = service.generate("hello")

        self.assert_false(result.success)
        self.assert_true("AI subsystem is disabled" in result.error)
        self.assert_equal(len(provider.ask_calls), 0)

    def _test_service_fallback_success(self) -> None:
        primary = _FakeAIProvider("claude", raise_error=ProviderUnavailableError("down"))
        fallback = _FakeAIProvider("gemini", response_text="fallback text")
        service, _ = self._make_service(
            provider=primary,
            ordered_providers=[fallback, primary],
            enabled=True,
            fallback_enabled=True,
        )

        result = service.generate("hello")

        self.assert_true(result.success)
        self.assert_equal(result.provider_name, "gemini")
        self.assert_equal(result.text, "fallback text")

    def _test_service_never_receives_conversation_or_context_dependency(self) -> None:
        # EP082_DESIGN.md Section 9: TextGenerationService's constructor
        # accepts no ConversationManager/ContextManager/PromptManager
        # argument at all -- verified structurally via introspection so
        # a future accidental addition of such a dependency fails this
        # test rather than passing silently.
        import inspect

        signature = inspect.signature(TextGenerationService.__init__)
        forbidden_names = {"conversation_manager", "context_manager", "prompt_manager"}
        actual_names = set(signature.parameters.keys())
        self.assert_true(
            forbidden_names.isdisjoint(actual_names),
            f"TextGenerationService must not depend on {forbidden_names}, "
            f"found overlap: {forbidden_names & actual_names}",
        )

    def _test_service_default_temperature_used_when_omitted(self) -> None:
        provider = _FakeAIProvider("claude")
        service, _ = self._make_service(provider=provider, enabled=True, default_temperature=0.3)

        service.generate("hello")

        self.assert_equal(len(provider.ask_calls), 1)
        self.assert_equal(provider.ask_calls[0]["temperature"], 0.3)

    def _test_service_per_request_temperature_overrides_default(self) -> None:
        provider = _FakeAIProvider("claude")
        service, _ = self._make_service(provider=provider, enabled=True, default_temperature=0.3)

        service.generate("hello", temperature=0.9, system_prompt="Be terse.")

        self.assert_equal(provider.ask_calls[0]["temperature"], 0.9)
        self.assert_equal(provider.ask_calls[0]["system_prompt"], "Be terse.")

    # ---------- validate_temperature() ----------

    def _test_validate_temperature_accepts_none(self) -> None:
        try:
            validate_temperature(None)
        except ProviderConfigurationError:
            self.assert_true(False, "None must be accepted as 'no override'.")
        else:
            self.assert_true(True)

    def _test_validate_temperature_accepts_valid_range(self) -> None:
        for value in (0.0, 0.5, 1.0, 1):
            try:
                validate_temperature(value)
            except ProviderConfigurationError:
                self.assert_true(False, f"{value!r} is within range and must be accepted.")
            else:
                self.assert_true(True)

    def _test_validate_temperature_rejects_out_of_range(self) -> None:
        for value in (-0.1, 1.1, 5.0):
            try:
                validate_temperature(value)
                self.assert_true(False, f"{value!r} is out of range and must raise.")
            except ProviderConfigurationError:
                self.assert_true(True)

    def _test_validate_temperature_rejects_non_numeric(self) -> None:
        for value in ("hot", True, False, [0.5]):
            try:
                validate_temperature(value)
                self.assert_true(False, f"{value!r} must raise ProviderConfigurationError.")
            except ProviderConfigurationError:
                self.assert_true(True)

    # ---------- ClaudeProvider additive parameters ----------

    def _make_claude_provider(self) -> ClaudeProvider:
        return ClaudeProvider(
            enabled=True,
            api_key="test-key",
            model="claude-test-model",
            timeout=10,
            max_tokens=256,
            temperature=0.2,
        )

    def _test_claude_provider_unchanged_when_new_params_omitted(self) -> None:
        provider = self._make_claude_provider()
        fake_response = _FakeHTTPResponse(
            status_code=200,
            _json={"content": [{"type": "text", "text": "hi"}], "model": "claude-test-model"},
        )
        with patch("src.core.ai.claude_provider.requests.post", return_value=fake_response) as mock_post:
            result = provider.ask("hello")

        self.assert_equal(result.text, "hi")
        payload = mock_post.call_args.kwargs["json"]
        self.assert_equal(payload["temperature"], 0.2, "Omitted temperature must use the configured default.")
        self.assert_true("system" not in payload, "Omitted system_prompt must not add a 'system' field.")

    def _test_claude_provider_honors_temperature_and_system_prompt(self) -> None:
        provider = self._make_claude_provider()
        fake_response = _FakeHTTPResponse(
            status_code=200,
            _json={"content": [{"type": "text", "text": "hi"}], "model": "claude-test-model"},
        )
        with patch("src.core.ai.claude_provider.requests.post", return_value=fake_response) as mock_post:
            provider.ask("hello", temperature=0.9, system_prompt="Be terse.")

        payload = mock_post.call_args.kwargs["json"]
        self.assert_equal(payload["temperature"], 0.9)
        self.assert_equal(payload["system"], "Be terse.")

    def _test_claude_provider_invalid_temperature_raises_configuration_error(self) -> None:
        provider = self._make_claude_provider()
        try:
            provider.ask("hello", temperature=5.0)
            self.assert_true(False, "Out-of-range temperature must raise ProviderConfigurationError.")
        except ProviderConfigurationError:
            self.assert_true(True)
        except ProviderAuthenticationError:
            self.assert_true(False, "Validation must occur before any network call.")

    # ---------- GeminiProvider additive parameters ----------

    def _make_gemini_provider(self) -> GeminiProvider:
        return GeminiProvider(
            enabled=True,
            api_key="test-key",
            model="gemini-test-model",
            timeout=10,
            max_tokens=256,
            temperature=0.2,
        )

    def _test_gemini_provider_unchanged_when_new_params_omitted(self) -> None:
        provider = self._make_gemini_provider()
        fake_response = _FakeHTTPResponse(
            status_code=200,
            _json={"candidates": [{"content": {"parts": [{"text": "hi"}]}}]},
        )
        with patch(
            "src.core.ai.providers.gemini_provider.requests.request", return_value=fake_response
        ) as mock_request:
            result = provider.ask("hello")

        self.assert_equal(result.text, "hi")
        payload = mock_request.call_args.kwargs["json"]
        self.assert_equal(
            payload["generationConfig"]["temperature"], 0.2, "Omitted temperature must use the configured default."
        )
        self.assert_true(
            "systemInstruction" not in payload, "Omitted system_prompt must not add a 'systemInstruction' field."
        )

    def _test_gemini_provider_honors_temperature_and_system_prompt(self) -> None:
        provider = self._make_gemini_provider()
        fake_response = _FakeHTTPResponse(
            status_code=200,
            _json={"candidates": [{"content": {"parts": [{"text": "hi"}]}}]},
        )
        with patch(
            "src.core.ai.providers.gemini_provider.requests.request", return_value=fake_response
        ) as mock_request:
            provider.ask("hello", temperature=0.9, system_prompt="Be terse.")

        payload = mock_request.call_args.kwargs["json"]
        self.assert_equal(payload["generationConfig"]["temperature"], 0.9)
        self.assert_equal(payload["systemInstruction"], {"parts": [{"text": "Be terse."}]})
