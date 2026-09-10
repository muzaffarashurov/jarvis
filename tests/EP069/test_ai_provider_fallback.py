"""Real engineering tests for EP-069.1 STEP 2 - Automatic AI Provider Fallback.

Single combined test suite (NAME = "EP069"), following the same
precedent EP-054 through EP-068 already established: this sidesteps
the pre-existing `TestRegistry` NAME-collision technical debt
(docs/BACKLOG.md) entirely rather than triggering it. Self-contained
-- no import from any other `tests/EP0NN/` package (matching
`tests/EP067/test_telegram_poll_loop_resilience.py`'s precedent).

Per `EP069_DESIGN.md` Section 25, covers:
    - Primary provider succeeds -> no fallback provider is ever
      called.
    - Fallback disabled ('ai.fallback_enabled' False/absent) -> a
      fallback-eligible primary failure is reported exactly as it was
      before EP-069.1, with zero fallback candidates queried.
    - A fallback-eligible primary failure, with fallback enabled ->
      the next candidate is attempted with the identical rendered
      prompt.
    - A non-eligible primary failure -> fallback is never attempted,
      regardless of whether it is enabled.
    - A fallback candidate that succeeds -> its response is returned,
      with `AskResult.provider` naming the fallback provider, not the
      original.
    - Multiple candidates: the first fallback also fails, the second
      succeeds -> deterministic order is respected and the second
      candidate's response is returned.
    - Every eligible candidate fails -> bounded execution (no
      infinite loop), with every attempted provider and its failure
      type preserved in the final `AskResult.error`.
    - `ProviderManager.list_fallback_candidates()` itself (the real
      implementation, against a real `ProviderRegistry`): returns
      candidates in deterministic, name-sorted order; excludes
      unavailable providers and every excluded name.
    - EP-068 log-redaction alignment: fallback/failure logging never
      contains the prompt text, the response text, or a raw
      exception message -- only provider names and exception class
      names.
    - Backward compatibility: `AIProvider`'s abstract contract,
      `ProviderRegistry`, `ProviderFactory`, `ClaudeProvider`, and
      `GeminiProvider` are unaffected; every existing concrete
      provider still satisfies the (unchanged) `AIProvider` contract.
"""

from __future__ import annotations

from dataclasses import dataclass

from loguru import logger

from src.core.ai.provider import (
    AIProvider,
    ProviderAuthenticationError,
    ProviderConfigurationError,
    ProviderError,
    ProviderHealth,
    ProviderNetworkError,
    ProviderRateLimitError,
    ProviderResponse,
    ProviderStatus,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from src.core.ai.provider_factory import ConfigDrivenProvider
from src.core.ai.provider_manager import ProviderManager
from src.core.ai.provider_registry import ProviderRegistry
from src.services.ai_service import AIService, AskResult
from src.testing.base_test import BaseTest
from src.testing.registry import TestRegistry


# ---------- Fakes ----------


class _FakeAIProvider(AIProvider):
    """Deterministic, test-only concrete `AIProvider` (EP-069.1).

    `ask()` either returns a fixed successful `ProviderResponse` or
    raises a fixed exception, and records every prompt it was called
    with, so tests can assert exactly what was sent and how many
    times each fake was actually invoked.
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
        self.ask_calls: list[str] = []

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

    def ask(self, prompt: str, max_tokens: int | None = None) -> ProviderResponse:
        self.ask_calls.append(prompt)
        if self._raise_error is not None:
            raise self._raise_error
        return ProviderResponse(text=self._response_text, model=f"{self._name}-model", latency_ms=1.0)


class _FakeProviderManager:
    """Deterministic, test-only stand-in for `ProviderManager`.

    Exposes exactly the three methods `AIService.ask()` calls:
    `get_current()`, `is_enabled()`, `list_fallback_candidates()`.
    Backed by a fixed, ordered provider list (mirroring
    `ProviderRegistry.list()`'s deterministic, name-sorted order) so
    tests can assert exactly which candidates are considered and in
    which order, without depending on the real registry/manager
    (that integration is covered separately -- see
    `_test_list_fallback_candidates_*` below, which use the real
    `ProviderManager`/`ProviderRegistry`).
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
class _FakeContext:
    rendered: str = ""


class _FakeContextManager:
    """Deterministic, test-only stand-in for `ContextManager`."""

    def create(self, conversation, query: str) -> _FakeContext:
        return _FakeContext(rendered="")


@dataclass
class _FakeBuiltPrompt:
    rendered: str


class _FakePromptManager:
    """Deterministic, test-only stand-in for `PromptManager`.

    Renders the prompt as `f"RENDERED::{user_prompt}"` so tests can
    assert every attempted candidate received the exact same rendered
    prompt (`EP069_DESIGN.md` Section 16, Owner Decision D2), never
    calling `build()` more than once per `ask()` call.
    """

    def __init__(self) -> None:
        self.build_calls = 0

    def build(self, *, user_prompt: str, context, provider_name: str) -> _FakeBuiltPrompt:
        self.build_calls += 1
        return _FakeBuiltPrompt(rendered=f"RENDERED::{user_prompt}")


class _FakeConfig:
    """Deterministic, test-only stand-in for `Config`.

    Always reports 'conversation.enabled' as False so `ask()`'s
    `_begin_turn()`/`_complete_turn()` never touch a
    `ConversationManager` (untested here -- EP-016 territory, not
    EP-069.1's concern), letting every test below pass `None` for
    `conversation_manager` safely.
    """

    def __init__(self, values: dict | None = None) -> None:
        self._values = values if values is not None else {"conversation.enabled": False}

    def get(self, key: str, default=None):
        return self._values.get(key, default)


def _capture_logs():
    """Attach a fresh loguru sink capturing formatted messages.

    Returns the list that will be appended to, and the sink id (to be
    removed with `logger.remove(sink_id)` when the caller is done).
    Mirrors `tests/EP068/test_command_router_log_redaction.py`'s own
    helper exactly.
    """
    lines: list[str] = []
    sink_id = logger.add(lambda message: lines.append(message.record["message"]), level="DEBUG")
    return lines, sink_id


def _make_service(
    *,
    ordered_providers: list[_FakeAIProvider],
    current: _FakeAIProvider | None,
    fallback_enabled: bool,
    enabled: bool = True,
) -> tuple[AIService, _FakeProviderManager, _FakePromptManager]:
    provider_manager = _FakeProviderManager(ordered_providers, current, enabled=enabled)
    prompt_manager = _FakePromptManager()
    service = AIService(
        config=_FakeConfig(),
        provider_manager=provider_manager,
        conversation_manager=None,
        prompt_manager=prompt_manager,
        context_manager=_FakeContextManager(),
        fallback_enabled=fallback_enabled,
    )
    return service, provider_manager, prompt_manager


@TestRegistry.register
class AIProviderFallbackTest(BaseTest):
    NAME = "EP069"

    def run(self):
        # ---------- AIService.ask() fallback control flow ----------
        self._test_primary_success_no_fallback_attempted()
        self._test_fallback_disabled_preserves_existing_behavior()
        self._test_eligible_failure_triggers_fallback_attempt()
        self._test_non_eligible_failure_never_triggers_fallback()
        self._test_fallback_provider_success_returns_its_response()
        self._test_multiple_fallback_providers_deterministic_order()
        self._test_all_eligible_providers_fail_bounded_and_reported()
        self._test_fallback_candidate_receives_identical_rendered_prompt()
        self._test_no_provider_selected_unaffected_by_fallback()
        self._test_disabled_subsystem_unaffected_by_fallback()

        # ---------- ProviderManager.list_fallback_candidates() (real) ----------
        self._test_list_fallback_candidates_orders_by_name()
        self._test_list_fallback_candidates_excludes_unavailable_and_named()

        # ---------- EP-068 logging alignment ----------
        self._test_fallback_logging_never_contains_prompt_or_response_text()
        self._test_exhausted_fallback_logging_uses_exception_type_names_only()

        # ---------- Backward compatibility ----------
        self._test_concrete_providers_still_satisfy_unchanged_contract()

        return self.result

    # ---------- AIService.ask() fallback control flow ----------

    def _test_primary_success_no_fallback_attempted(self) -> None:
        primary = _FakeAIProvider("claude", response_text="primary reply")
        fallback = _FakeAIProvider("gemini", response_text="fallback reply")
        service, provider_manager, prompt_manager = _make_service(
            ordered_providers=[fallback, primary],
            current=primary,
            fallback_enabled=True,
        )

        result = service.ask("hello")

        self.assert_true(result.success, "Primary success should report success=True.")
        self.assert_equal(result.provider, "claude", "Successful AskResult should name the primary provider.")
        self.assert_equal(result.text, "primary reply", "Successful AskResult should carry the primary's reply.")
        self.assert_equal(len(primary.ask_calls), 1, "Primary should be called exactly once.")
        self.assert_equal(len(fallback.ask_calls), 0, "Fallback must never be called when the primary succeeds.")
        self.assert_equal(
            len(provider_manager.list_fallback_candidates_calls),
            0,
            "list_fallback_candidates() must never be queried when the primary succeeds.",
        )
        self.assert_equal(prompt_manager.build_calls, 1, "The prompt must be built exactly once.")

    def _test_fallback_disabled_preserves_existing_behavior(self) -> None:
        primary = _FakeAIProvider(
            "claude", raise_error=ProviderUnavailableError("claude is down")
        )
        fallback = _FakeAIProvider("gemini", available=True, response_text="fallback reply")
        service, provider_manager, _ = _make_service(
            ordered_providers=[fallback, primary],
            current=primary,
            fallback_enabled=False,
        )

        result = service.ask("hello")

        self.assert_false(result.success, "A primary failure with fallback disabled must still fail.")
        self.assert_equal(result.provider, "claude", "Failure AskResult must name the original provider.")
        self.assert_equal(result.error, "claude is down", "Failure error text must be unchanged pre-EP-069.1 shape.")
        self.assert_equal(len(fallback.ask_calls), 0, "Fallback must never be attempted while disabled.")
        self.assert_equal(
            len(provider_manager.list_fallback_candidates_calls),
            0,
            "list_fallback_candidates() must never be queried while fallback is disabled.",
        )

    def _test_eligible_failure_triggers_fallback_attempt(self) -> None:
        primary = _FakeAIProvider("claude", raise_error=ProviderTimeoutError("claude timed out"))
        fallback = _FakeAIProvider("gemini", response_text="fallback reply")
        service, provider_manager, _ = _make_service(
            ordered_providers=[fallback, primary],
            current=primary,
            fallback_enabled=True,
        )

        result = service.ask("hello")

        self.assert_true(result.success, "A fallback-eligible failure with an available candidate should succeed.")
        self.assert_equal(len(fallback.ask_calls), 1, "The fallback candidate must be attempted exactly once.")
        self.assert_equal(
            provider_manager.list_fallback_candidates_calls[0],
            {"claude"},
            "The first fallback lookup must exclude only the already-attempted primary.",
        )

    def _test_non_eligible_failure_never_triggers_fallback(self) -> None:
        non_eligible_errors = [
            ProviderConfigurationError("claude is disabled"),
            ProviderAuthenticationError("claude rejected credentials"),
            ProviderError("uncategorized failure"),
        ]
        for exc in non_eligible_errors:
            primary = _FakeAIProvider("claude", raise_error=exc)
            fallback = _FakeAIProvider("gemini", response_text="fallback reply")
            service, provider_manager, _ = _make_service(
                ordered_providers=[fallback, primary],
                current=primary,
                fallback_enabled=True,
            )

            result = service.ask("hello")

            self.assert_false(
                result.success,
                f"{type(exc).__name__} must never be masked by a successful fallback.",
            )
            self.assert_equal(
                len(fallback.ask_calls),
                0,
                f"{type(exc).__name__} must never trigger a fallback attempt.",
            )
            self.assert_equal(
                len(provider_manager.list_fallback_candidates_calls),
                0,
                f"{type(exc).__name__} must never query list_fallback_candidates().",
            )

    def _test_fallback_provider_success_returns_its_response(self) -> None:
        primary = _FakeAIProvider("claude", raise_error=ProviderNetworkError("claude unreachable"))
        fallback = _FakeAIProvider("gemini", response_text="fallback reply")
        service, _, _ = _make_service(
            ordered_providers=[fallback, primary],
            current=primary,
            fallback_enabled=True,
        )

        result = service.ask("hello")

        self.assert_true(result.success, "Fallback success must be reported as success.")
        self.assert_equal(
            result.provider,
            "gemini",
            "AskResult.provider must name the fallback provider that actually served the request, not the original.",
        )
        self.assert_equal(result.text, "fallback reply", "AskResult.text must carry the fallback's reply.")
        self.assert_equal(result.model, "gemini-model", "AskResult.model must carry the fallback's model.")

    def _test_multiple_fallback_providers_deterministic_order(self) -> None:
        primary = _FakeAIProvider("claude", raise_error=ProviderUnavailableError("claude down"))
        first_fallback = _FakeAIProvider("gemini", raise_error=ProviderUnavailableError("gemini down"))
        second_fallback = _FakeAIProvider("openai", response_text="second fallback reply")
        # `_FakeProviderManager` filters its `ordered_providers` list in
        # the order given -- it is a direct stand-in for whatever order
        # `ProviderManager.list_fallback_candidates()` already returns
        # (name-sorted -- see `_test_list_fallback_candidates_orders_by_name`
        # below, which tests that sorting against the real
        # `ProviderRegistry`). Here the fixture is supplied in that same
        # already-sorted order ("gemini" before "openai") so this test
        # can focus on proving `AIService.ask()` itself respects
        # whatever order it is given and stops at the first success.
        service, _, _ = _make_service(
            ordered_providers=[first_fallback, second_fallback, primary],
            current=primary,
            fallback_enabled=True,
        )

        result = service.ask("hello")

        self.assert_true(result.success, "The second, working fallback candidate should eventually succeed.")
        self.assert_equal(result.provider, "openai", "AskResult.provider must name the final successful candidate.")
        self.assert_equal(len(primary.ask_calls), 1, "Primary must be attempted exactly once.")
        self.assert_equal(len(first_fallback.ask_calls), 1, "First fallback must be attempted exactly once.")
        self.assert_equal(len(second_fallback.ask_calls), 1, "Second fallback must be attempted exactly once.")

    def _test_all_eligible_providers_fail_bounded_and_reported(self) -> None:
        primary = _FakeAIProvider("claude", raise_error=ProviderUnavailableError("claude down"))
        fallback_one = _FakeAIProvider("gemini", raise_error=ProviderTimeoutError("gemini timed out"))
        fallback_two = _FakeAIProvider("openai", raise_error=ProviderRateLimitError("openai rate limited"))
        service, provider_manager, _ = _make_service(
            ordered_providers=[fallback_one, fallback_two, primary],
            current=primary,
            fallback_enabled=True,
        )

        result = service.ask("hello")

        self.assert_false(result.success, "Every eligible provider failing must report failure.")
        self.assert_equal(result.provider, "claude", "Failure AskResult must name the originally selected provider.")
        self.assert_true(
            "claude: ProviderUnavailableError" in result.error,
            "The final error must preserve the primary's failure type for diagnostics.",
        )
        self.assert_true(
            "gemini: ProviderTimeoutError" in result.error,
            "The final error must preserve the first fallback's failure type for diagnostics.",
        )
        self.assert_true(
            "openai: ProviderRateLimitError" in result.error,
            "The final error must preserve the second fallback's failure type for diagnostics.",
        )
        self.assert_equal(len(primary.ask_calls), 1, "Each provider must be attempted at most once (bounded).")
        self.assert_equal(len(fallback_one.ask_calls), 1, "Each provider must be attempted at most once (bounded).")
        self.assert_equal(len(fallback_two.ask_calls), 1, "Each provider must be attempted at most once (bounded).")
        # Bounded by construction: exactly 3 registered providers here,
        # so at most 3 total ask() calls are possible -- no infinite
        # loop regardless of how many times fallback fires.
        total_attempts = len(primary.ask_calls) + len(fallback_one.ask_calls) + len(fallback_two.ask_calls)
        self.assert_equal(total_attempts, 3, "Total attempts must equal the number of registered providers.")
        # Every fallback lookup must have excluded every already-attempted name.
        self.assert_equal(provider_manager.list_fallback_candidates_calls[0], {"claude"})
        self.assert_equal(provider_manager.list_fallback_candidates_calls[1], {"claude", "gemini"})

    def _test_fallback_candidate_receives_identical_rendered_prompt(self) -> None:
        primary = _FakeAIProvider("claude", raise_error=ProviderUnavailableError("claude down"))
        fallback = _FakeAIProvider("gemini", response_text="fallback reply")
        service, _, prompt_manager = _make_service(
            ordered_providers=[fallback, primary],
            current=primary,
            fallback_enabled=True,
        )

        service.ask("a distinctive prompt")

        self.assert_equal(prompt_manager.build_calls, 1, "The prompt must be built exactly once, not once per candidate.")
        self.assert_equal(
            primary.ask_calls[0],
            "RENDERED::a distinctive prompt",
            "The primary must receive the rendered prompt.",
        )
        self.assert_equal(
            fallback.ask_calls[0],
            primary.ask_calls[0],
            "The fallback candidate must receive the exact same rendered prompt as the primary.",
        )

    def _test_no_provider_selected_unaffected_by_fallback(self) -> None:
        service, provider_manager, _ = _make_service(
            ordered_providers=[],
            current=None,
            fallback_enabled=True,
        )

        result = service.ask("hello")

        self.assert_false(result.success, "No provider selected must still fail.")
        self.assert_equal(result.provider, "", "No provider selected must report an empty provider name.")
        self.assert_equal(
            len(provider_manager.list_fallback_candidates_calls),
            0,
            "list_fallback_candidates() must never be queried when no provider is selected.",
        )

    def _test_disabled_subsystem_unaffected_by_fallback(self) -> None:
        primary = _FakeAIProvider("claude")
        service, provider_manager, _ = _make_service(
            ordered_providers=[primary],
            current=primary,
            fallback_enabled=True,
            enabled=False,
        )

        result = service.ask("hello")

        self.assert_false(result.success, "A disabled AI subsystem must still fail ask().")
        self.assert_equal(len(primary.ask_calls), 0, "A disabled AI subsystem must never call any provider.")
        self.assert_equal(
            len(provider_manager.list_fallback_candidates_calls),
            0,
            "list_fallback_candidates() must never be queried when the AI subsystem is disabled.",
        )

    # ---------- ProviderManager.list_fallback_candidates() (real) ----------

    def _test_list_fallback_candidates_orders_by_name(self) -> None:
        registry = ProviderRegistry()
        # Registered deliberately out of alphabetical order.
        openai_provider = _FakeAIProvider("openai")
        claude_provider = _FakeAIProvider("claude")
        gemini_provider = _FakeAIProvider("gemini")
        registry.register(openai_provider)
        registry.register(claude_provider)
        registry.register(gemini_provider)
        manager = ProviderManager(registry=registry, enabled=True, default_provider="none")

        candidates = manager.list_fallback_candidates(exclude=[])

        self.assert_equal(
            [p.name() for p in candidates],
            ["claude", "gemini", "openai"],
            "list_fallback_candidates() must return candidates in deterministic, name-sorted order.",
        )
        # Run a second time to rule out any hidden non-determinism
        # (e.g. relying on dict iteration order).
        candidates_again = manager.list_fallback_candidates(exclude=[])
        self.assert_equal(
            [p.name() for p in candidates_again],
            ["claude", "gemini", "openai"],
            "list_fallback_candidates() ordering must be stable across repeated calls.",
        )

    def _test_list_fallback_candidates_excludes_unavailable_and_named(self) -> None:
        registry = ProviderRegistry()
        claude_provider = _FakeAIProvider("claude", available=True)
        gemini_provider = _FakeAIProvider("gemini", available=False)
        openai_provider = _FakeAIProvider("openai", available=True)
        registry.register(claude_provider)
        registry.register(gemini_provider)
        registry.register(openai_provider)
        manager = ProviderManager(registry=registry, enabled=True, default_provider="none")

        candidates = manager.list_fallback_candidates(exclude=["openai"])

        self.assert_equal(
            [p.name() for p in candidates],
            ["claude"],
            "An unavailable provider ('gemini') and an explicitly excluded one ('openai') must both be omitted.",
        )

    # ---------- EP-068 logging alignment ----------

    def _test_fallback_logging_never_contains_prompt_or_response_text(self) -> None:
        sentinel_prompt = "SENTINEL-PROMPT-8f2c1a"
        sentinel_reply = "SENTINEL-REPLY-9d4e2b"
        primary = _FakeAIProvider("claude", raise_error=ProviderUnavailableError("claude down"))
        fallback = _FakeAIProvider("gemini", response_text=sentinel_reply)
        service, _, _ = _make_service(
            ordered_providers=[fallback, primary],
            current=primary,
            fallback_enabled=True,
        )

        lines, sink_id = _capture_logs()
        try:
            service.ask(sentinel_prompt)
        finally:
            logger.remove(sink_id)

        for line in lines:
            self.assert_false(
                sentinel_prompt in line,
                f"Prompt text must never appear in logs. Leaked in: {line!r}",
            )
            self.assert_false(
                sentinel_reply in line,
                f"Response text must never appear in logs. Leaked in: {line!r}",
            )

    def _test_exhausted_fallback_logging_uses_exception_type_names_only(self) -> None:
        secret_detail = "SECRET-CONNECTION-DETAIL-7a1c"
        primary = _FakeAIProvider(
            "claude", raise_error=ProviderUnavailableError(f"claude down: {secret_detail}")
        )
        fallback = _FakeAIProvider(
            "gemini", raise_error=ProviderTimeoutError(f"gemini timeout: {secret_detail}")
        )
        service, _, _ = _make_service(
            ordered_providers=[fallback, primary],
            current=primary,
            fallback_enabled=True,
        )

        lines, sink_id = _capture_logs()
        try:
            service.ask("hello")
        finally:
            logger.remove(sink_id)

        exhausted_lines = [line for line in lines if "failed on every eligible provider" in line]
        self.assert_true(
            len(exhausted_lines) == 1,
            "Exactly one aggregated 'all providers failed' log line must be emitted.",
        )
        for line in exhausted_lines:
            self.assert_true(
                "ProviderUnavailableError" in line and "ProviderTimeoutError" in line,
                "The aggregated log line must name each failure's exception type.",
            )
            self.assert_false(
                secret_detail in line,
                "The aggregated log line must never include a raw exception message.",
            )

    # ---------- Backward compatibility ----------

    def _test_concrete_providers_still_satisfy_unchanged_contract(self) -> None:
        # EP-069.1 must add no new abstract method to AIProvider and
        # must not modify any concrete provider -- constructing each
        # one via ConfigDrivenProvider (the shared base for the
        # openai/ollama/lmstudio placeholders) confirms the contract
        # is still satisfiable unchanged. ClaudeProvider/GeminiProvider
        # require live API configuration to construct and are
        # exercised by their own existing tests/`ai doctor`, not here.
        placeholder = ConfigDrivenProvider(
            name="openai", enabled=False, credential_key="api_key", credential_value=""
        )
        self.assert_equal(placeholder.name(), "openai")
        self.assert_false(placeholder.is_available())
        self.assert_true(isinstance(placeholder.health(), ProviderHealth))
        self.assert_true(isinstance(placeholder.configuration(), dict))
        try:
            placeholder.ask("hello")
            self.assert_true(False, "The base ask() implementation must still raise unchanged.")
        except ProviderUnavailableError:
            self.assert_true(True)
