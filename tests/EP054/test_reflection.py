"""Real engineering tests for EP-054 STEP 2 - Self Reflection.

Single combined test suite (NAME = "EP054"), following the same
precedent EP-043 through EP-053 already established: this sidesteps
the pre-existing `TestRegistry` NAME-collision technical debt
(docs/BACKLOG.md) entirely rather than triggering it.

Per `EP054_DESIGN.md` Section 12/Owner Decision D9, no real-`AIProvider`
integration test exists for this EP (a live provider call is not
deterministic, unlike EP-053's real-Tesseract OCR check) -- every test
here runs against fakes for `ConversationManager`/`ProviderManager`/
`MemoryService`, plus real `Bootstrap` wiring tests using the
project's own minimal-bootstrap-config fixture (`tests/EP045`).

Covers:
    - Argument-shape validation (`reflect summary`/`reflect recall`
      reject the wrong argument count) -- rejected before any
      downstream call.
    - The `reflection.enabled` safety gate: every action is rejected
      while disabled, with zero downstream calls; both actions reach
      their dependencies once enabled.
    - `reflection.max_message_count`: an explicit `count` argument
      exceeding the cap is refused (never silently clamped); omitting
      `count` uses the cap as the default and includes only the last
      `max_message_count` messages, even when the conversation is
      longer.
    - `reflection.min_seconds_between_calls`: a rate-limit test using
      a fake, injected clock (never a real `time.sleep()`) -- a
      second call before the limit elapses is rejected; a call at or
      after the limit succeeds; `reflect recall` is never rate-limited.
    - Positive-path generation: the exact prompt constructed from the
      current conversation's messages, and the exact `CommandResult`
      produced from the fake provider's response.
    - Negative/security cases: no active provider, provider raises
      `ProviderError`, empty conversation (no messages).
    - `reflection.persist_to_memory`: a generated reflection is
      stored via a fake `MemoryService.set()` only when enabled;
      `reflect recall` returns `_RECALL_DISABLED_MESSAGE` when
      disabled or when the Memory subsystem is unavailable (`None`),
      and returns persisted entries, most recent first, when enabled.
    - `CommandRouter` dispatch equivalence.
    - `Bootstrap` wiring: `reflection.enabled` defaults to false when
      entirely absent from config; the 'reflect' namespace is
      registered with `CommandRouter` regardless of the flag's value;
      actions report the disabled message until the flag is set to
      true; other modules are unaffected.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from src.bootstrap import Bootstrap
from src.core.ai.conversation import Conversation
from src.core.ai.message import Message, MessageRole
from src.core.ai.provider import ProviderError, ProviderResponse
from src.core.command_router import CommandRouter, CommandResult
from src.core.config import Config
from src.core.memory.context import MemoryEntry
from src.skills.reflection.skill import HELP_TEXT, MEMORY_NAMESPACE, ReflectionModule
from src.testing.base_test import BaseTest
from src.testing.registry import TestRegistry
from tests.EP045.test_web_dashboard import (
    _MINIMAL_BOOTSTRAP_CONFIG_YAML,
    _ChdirGuard,
    _api_section,
)


# ---------- Fakes ----------


class _FakeConversationManager:
    """Deterministic, test-only stand-in for `ConversationManager`.

    Exposes only `current()`, matching the one method
    `ReflectionModule` actually calls.
    """

    def __init__(self, messages: list[Message] | None = None) -> None:
        self._conversation = Conversation(messages=messages or [])
        self.current_call_count = 0

    def current(self) -> Conversation:
        self.current_call_count += 1
        return self._conversation


class _FakeAIProvider:
    """Deterministic, test-only stand-in for a concrete `AIProvider`.

    Records every `ask()` call's prompt (`self.prompts`) so tests can
    assert exactly what `ReflectionModule` constructed, without
    calling any real AI provider.
    """

    def __init__(self, response_text: str = "critique", raise_error: Exception | None = None) -> None:
        self.prompts: list[str] = []
        self._response_text = response_text
        self._raise_error = raise_error

    def ask(self, prompt: str, max_tokens: int | None = None) -> ProviderResponse:
        self.prompts.append(prompt)
        if self._raise_error is not None:
            raise self._raise_error
        return ProviderResponse(text=self._response_text, model="fake-model", latency_ms=1.0)


class _FakeProviderManager:
    """Deterministic, test-only stand-in for `ProviderManager`.

    Exposes only `get_current()`, matching the one method
    `ReflectionModule` actually calls.
    """

    def __init__(self, provider: _FakeAIProvider | None) -> None:
        self._provider = provider
        self.get_current_call_count = 0

    def get_current(self):
        self.get_current_call_count += 1
        return self._provider


@dataclass
class _FakeMemoryService:
    """Deterministic, test-only stand-in for `MemoryService`.

    Exposes only `set()`/`list_entries()`, matching the two methods
    `ReflectionModule` actually calls.
    """

    entries: list[MemoryEntry] = field(default_factory=list)
    set_calls: list[tuple[str, object, str]] = field(default_factory=list)
    fail_set: bool = False

    def set(self, key: str, value, namespace: str = "default") -> CommandResult:
        self.set_calls.append((key, value, namespace))
        if self.fail_set:
            return CommandResult(success=False, message="simulated memory failure")
        self.entries.append(MemoryEntry(key=key, value=value, namespace=namespace))
        return CommandResult(success=True, message=f"Key '{key}' set in namespace '{namespace}'.")

    def list_entries(self, namespace: str | None = None) -> list[MemoryEntry]:
        if namespace is None:
            return list(self.entries)
        return [entry for entry in self.entries if entry.namespace == namespace]


class _FakeClock:
    """A deterministic, manually-advanced stand-in for `time.monotonic`."""

    def __init__(self, start: float = 1000.0) -> None:
        self._now = start

    def __call__(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += seconds


_UNSET = object()


def _config_with(overrides: dict) -> Config:
    """Build a Config whose in-memory data is exactly `overrides`."""
    config = Config(config_path=Path("unused.yaml"))
    config._data = overrides
    return config


def _reflection_config(
    *,
    enabled: bool = True,
    max_message_count: int = 20,
    min_seconds_between_calls: float = 30.0,
    persist_to_memory: bool = False,
) -> Config:
    """Build a Config with a single 'reflection:' section for ReflectionModule tests."""
    return _config_with(
        {
            "reflection": {
                "enabled": enabled,
                "max_message_count": max_message_count,
                "min_seconds_between_calls": min_seconds_between_calls,
                "persist_to_memory": persist_to_memory,
            }
        }
    )


def _messages(*texts: str) -> list[Message]:
    """Build a simple alternating user/assistant message list from plain strings."""
    result = []
    for index, text in enumerate(texts):
        role = MessageRole.USER if index % 2 == 0 else MessageRole.ASSISTANT
        result.append(Message(role=role, content=text))
    return result


def _write_reflection_bootstrap_config(directory: Path, reflection_section: str) -> None:
    """Write a minimal bootstrap config.yaml (EP-045's fixture) plus a 'reflection:' block."""
    config_dir = directory / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    base_yaml = _MINIMAL_BOOTSTRAP_CONFIG_YAML.format(
        api_section=_api_section(enabled=False, web_dashboard_dir=None)
    )
    (config_dir / "config.yaml").write_text(base_yaml + "\n" + reflection_section, encoding="utf-8")


@TestRegistry.register
class ReflectionTest(BaseTest):
    NAME = "EP054"

    def run(self):
        # ---------- Argument-shape validation ----------
        self._test_summary_rejects_wrong_argument_count()
        self._test_recall_rejects_wrong_argument_count()
        self._test_summary_rejects_non_integer_count()
        self._test_summary_rejects_zero_or_negative_count()

        # ---------- reflection.enabled gate ----------
        self._test_disabled_rejects_summary_with_zero_downstream_calls()
        self._test_disabled_rejects_recall()
        self._test_enabled_true_allows_summary_to_reach_provider()

        # ---------- max_message_count ----------
        self._test_explicit_count_exceeding_cap_rejected()
        self._test_omitted_count_defaults_to_cap()
        self._test_only_last_n_messages_included_in_prompt()

        # ---------- rate limit ----------
        self._test_rate_limit_blocks_immediate_second_call()
        self._test_rate_limit_allows_call_after_elapsed()
        self._test_recall_never_rate_limited()

        # ---------- positive path ----------
        self._test_summary_returns_provider_response_text()
        self._test_summary_prompt_contains_transcript()

        # ---------- negative/security cases ----------
        self._test_summary_no_provider_available()
        self._test_summary_provider_raises_error()
        self._test_summary_empty_conversation()

        # ---------- persistence ----------
        self._test_summary_persists_when_enabled()
        self._test_summary_does_not_persist_when_disabled()
        self._test_recall_disabled_when_persist_to_memory_false()
        self._test_recall_disabled_when_memory_service_none()
        self._test_recall_returns_entries_most_recent_first()
        self._test_recall_respects_count_argument()

        # ---------- HELP / unknown action ----------
        self._test_help_lists_commands()
        self._test_unknown_action_returns_failure()

        # ---------- CommandRouter integration ----------
        self._test_command_router_dispatch_matches_direct_execute()

        # ---------- Bootstrap wiring ----------
        self._test_bootstrap_config_defaults_reflection_disabled()
        self._test_bootstrap_registers_reflect_namespace_even_when_disabled()
        self._test_bootstrap_reflect_actions_report_disabled_message()
        self._test_bootstrap_other_modules_unaffected_when_reflection_absent()

        return self.result

    # ---------- Shared helper ----------

    def _build_module(
        self,
        *,
        config: Config | None = None,
        messages: list[Message] | None = None,
        provider: _FakeAIProvider | None = _UNSET,
        memory_service: _FakeMemoryService | None = None,
        clock: _FakeClock | None = None,
    ) -> tuple[ReflectionModule, _FakeConversationManager, _FakeProviderManager]:
        if config is None:
            config = _reflection_config()
        if provider is _UNSET:
            provider = _FakeAIProvider()
        conversation_manager = _FakeConversationManager(messages=messages)
        provider_manager = _FakeProviderManager(provider=provider)
        module = ReflectionModule(
            config=config,
            conversation_manager=conversation_manager,
            provider_manager=provider_manager,
            memory_service=memory_service,
            clock=clock if clock is not None else _FakeClock(),
        )
        return module, conversation_manager, provider_manager

    # ---------- Argument-shape validation ----------

    def _test_summary_rejects_wrong_argument_count(self) -> None:
        module, _, provider_manager = self._build_module()
        result = module.execute("summary", ["1", "2"])
        self.assert_false(result.success)
        self.assert_equal(provider_manager.get_current_call_count, 0)

    def _test_recall_rejects_wrong_argument_count(self) -> None:
        module, _, _ = self._build_module()
        result = module.execute("recall", ["1", "2"])
        self.assert_false(result.success)

    def _test_summary_rejects_non_integer_count(self) -> None:
        module, _, provider_manager = self._build_module()
        result = module.execute("summary", ["not-a-number"])
        self.assert_false(result.success)
        self.assert_equal(provider_manager.get_current_call_count, 0)

    def _test_summary_rejects_zero_or_negative_count(self) -> None:
        module, _, _ = self._build_module()
        for bad in ("0", "-5"):
            result = module.execute("summary", [bad])
            self.assert_false(result.success, f"count={bad} must be rejected")

    # ---------- reflection.enabled gate ----------

    def _test_disabled_rejects_summary_with_zero_downstream_calls(self) -> None:
        module, conversation_manager, provider_manager = self._build_module(
            config=_reflection_config(enabled=False),
            messages=_messages("hi"),
        )
        result = module.execute("summary", [])
        self.assert_false(result.success)
        self.assert_true("disabled" in result.message.lower())
        self.assert_equal(conversation_manager.current_call_count, 0)
        self.assert_equal(provider_manager.get_current_call_count, 0)

    def _test_disabled_rejects_recall(self) -> None:
        module, _, _ = self._build_module(config=_reflection_config(enabled=False))
        result = module.execute("recall", [])
        self.assert_false(result.success)
        self.assert_true("disabled" in result.message.lower())

    def _test_enabled_true_allows_summary_to_reach_provider(self) -> None:
        module, _, provider_manager = self._build_module(messages=_messages("hi", "hello"))
        result = module.execute("summary", [])
        self.assert_true(result.success)
        self.assert_equal(provider_manager.get_current_call_count, 1)

    # ---------- max_message_count ----------

    def _test_explicit_count_exceeding_cap_rejected(self) -> None:
        module, _, provider_manager = self._build_module(
            config=_reflection_config(max_message_count=5),
            messages=_messages(*[f"m{i}" for i in range(10)]),
        )
        result = module.execute("summary", ["6"])
        self.assert_false(result.success)
        self.assert_true("max_message_count" in result.message)
        self.assert_equal(provider_manager.get_current_call_count, 0)

    def _test_omitted_count_defaults_to_cap(self) -> None:
        provider = _FakeAIProvider()
        texts = [f"m{i}" for i in range(10)]
        module, _, _ = self._build_module(
            config=_reflection_config(max_message_count=3),
            messages=_messages(*texts),
            provider=provider,
        )
        module.execute("summary", [])
        self.assert_equal(len(provider.prompts), 1)
        # Only the last 3 messages' text should appear in the transcript.
        for text in texts[-3:]:
            self.assert_true(text in provider.prompts[0])
        for text in texts[:-3]:
            self.assert_false(text in provider.prompts[0], f"'{text}' should have been excluded")

    def _test_only_last_n_messages_included_in_prompt(self) -> None:
        provider = _FakeAIProvider()
        texts = [f"unique-{i}" for i in range(10)]
        module, _, _ = self._build_module(
            config=_reflection_config(max_message_count=20),
            messages=_messages(*texts),
            provider=provider,
        )
        module.execute("summary", ["2"])
        self.assert_true(texts[-1] in provider.prompts[0])
        self.assert_true(texts[-2] in provider.prompts[0])
        self.assert_false(texts[0] in provider.prompts[0])

    # ---------- rate limit ----------

    def _test_rate_limit_blocks_immediate_second_call(self) -> None:
        clock = _FakeClock()
        module, _, provider_manager = self._build_module(
            config=_reflection_config(min_seconds_between_calls=30.0),
            messages=_messages("hi", "hello"),
            clock=clock,
        )
        first = module.execute("summary", [])
        self.assert_true(first.success)
        clock.advance(5.0)  # well under the 30s limit
        second = module.execute("summary", [])
        self.assert_false(second.success)
        self.assert_true("rate-limited" in second.message.lower())
        self.assert_equal(provider_manager.get_current_call_count, 1, "the provider must not be called a second time")

    def _test_rate_limit_allows_call_after_elapsed(self) -> None:
        clock = _FakeClock()
        module, _, provider_manager = self._build_module(
            config=_reflection_config(min_seconds_between_calls=10.0),
            messages=_messages("hi", "hello"),
            clock=clock,
        )
        module.execute("summary", [])
        clock.advance(10.0)
        second = module.execute("summary", [])
        self.assert_true(second.success)
        self.assert_equal(provider_manager.get_current_call_count, 2)

    def _test_recall_never_rate_limited(self) -> None:
        memory_service = _FakeMemoryService()
        module, _, _ = self._build_module(
            config=_reflection_config(persist_to_memory=True),
            memory_service=memory_service,
        )
        first = module.execute("recall", [])
        second = module.execute("recall", [])
        self.assert_true(first.success)
        self.assert_true(second.success)

    # ---------- positive path ----------

    def _test_summary_returns_provider_response_text(self) -> None:
        provider = _FakeAIProvider(response_text="This went well; try X next time.")
        module, _, _ = self._build_module(messages=_messages("hi", "hello"), provider=provider)
        result = module.execute("summary", [])
        self.assert_true(result.success)
        self.assert_equal(result.message, "This went well; try X next time.")

    def _test_summary_prompt_contains_transcript(self) -> None:
        provider = _FakeAIProvider()
        module, _, _ = self._build_module(messages=_messages("user says hi", "assistant replies"), provider=provider)
        module.execute("summary", [])
        self.assert_true("user says hi" in provider.prompts[0])
        self.assert_true("assistant replies" in provider.prompts[0])
        self.assert_true("user:" in provider.prompts[0])
        self.assert_true("assistant:" in provider.prompts[0])

    # ---------- negative/security cases ----------

    def _test_summary_no_provider_available(self) -> None:
        module, _, provider_manager = self._build_module(messages=_messages("hi"), provider=None)
        result = module.execute("summary", [])
        self.assert_false(result.success)
        self.assert_true("provider" in result.message.lower())

    def _test_summary_provider_raises_error(self) -> None:
        provider = _FakeAIProvider(raise_error=ProviderError("simulated provider failure"))
        module, _, _ = self._build_module(messages=_messages("hi"), provider=provider)
        result = module.execute("summary", [])
        self.assert_false(result.success)
        self.assert_true("simulated provider failure" in result.message)

    def _test_summary_empty_conversation(self) -> None:
        module, _, provider_manager = self._build_module(messages=[])
        result = module.execute("summary", [])
        self.assert_true(result.success, "an empty conversation is not an error")
        self.assert_true("no messages" in result.message.lower())
        self.assert_equal(provider_manager.get_current_call_count, 0, "the provider must not be called for an empty conversation")

    # ---------- persistence ----------

    def _test_summary_persists_when_enabled(self) -> None:
        memory_service = _FakeMemoryService()
        module, _, _ = self._build_module(
            config=_reflection_config(persist_to_memory=True),
            messages=_messages("hi", "hello"),
            memory_service=memory_service,
        )
        result = module.execute("summary", [])
        self.assert_true(result.success)
        self.assert_equal(len(memory_service.set_calls), 1)
        self.assert_equal(memory_service.set_calls[0][2], MEMORY_NAMESPACE)

    def _test_summary_does_not_persist_when_disabled(self) -> None:
        memory_service = _FakeMemoryService()
        module, _, _ = self._build_module(
            config=_reflection_config(persist_to_memory=False),
            messages=_messages("hi", "hello"),
            memory_service=memory_service,
        )
        module.execute("summary", [])
        self.assert_equal(len(memory_service.set_calls), 0)

    def _test_recall_disabled_when_persist_to_memory_false(self) -> None:
        memory_service = _FakeMemoryService()
        module, _, _ = self._build_module(
            config=_reflection_config(persist_to_memory=False),
            memory_service=memory_service,
        )
        result = module.execute("recall", [])
        self.assert_false(result.success)
        self.assert_true("persist_to_memory" in result.message)

    def _test_recall_disabled_when_memory_service_none(self) -> None:
        module, _, _ = self._build_module(
            config=_reflection_config(persist_to_memory=True),
            memory_service=None,
        )
        result = module.execute("recall", [])
        self.assert_false(result.success)

    def _test_recall_returns_entries_most_recent_first(self) -> None:
        memory_service = _FakeMemoryService()
        module, _, _ = self._build_module(
            config=_reflection_config(persist_to_memory=True),
            memory_service=memory_service,
        )
        import time as _time

        memory_service.set(key="k1", value="first critique", namespace=MEMORY_NAMESPACE)
        _time.sleep(0.01)
        memory_service.set(key="k2", value="second critique", namespace=MEMORY_NAMESPACE)
        result = module.execute("recall", [])
        self.assert_true(result.success)
        self.assert_true(result.message.index("second critique") < result.message.index("first critique"))

    def _test_recall_respects_count_argument(self) -> None:
        memory_service = _FakeMemoryService()
        module, _, _ = self._build_module(
            config=_reflection_config(persist_to_memory=True),
            memory_service=memory_service,
        )
        for i in range(5):
            memory_service.set(key=f"k{i}", value=f"critique {i}", namespace=MEMORY_NAMESPACE)
        result = module.execute("recall", ["2"])
        self.assert_true(result.success)
        count_found = sum(1 for i in range(5) if f"critique {i}" in result.message)
        self.assert_equal(count_found, 2)

    # ---------- HELP / unknown action ----------

    def _test_help_lists_commands(self) -> None:
        module, _, _ = self._build_module()
        result = module.execute("help", [])
        self.assert_true(result.success)
        self.assert_true("reflect summary" in result.message)
        self.assert_true("reflect recall" in result.message)
        self.assert_equal(result.message, HELP_TEXT)

    def _test_unknown_action_returns_failure(self) -> None:
        module, _, _ = self._build_module()
        result = module.execute("optimize", [])
        self.assert_false(result.success, "'reflect optimize' does not exist in v1 (Owner Decision D3 -- descriptive only)")

    # ---------- CommandRouter integration ----------

    def _test_command_router_dispatch_matches_direct_execute(self) -> None:
        module, _, _ = self._build_module(messages=_messages("hi", "hello"))
        router = CommandRouter()
        router.register(module)
        direct = module.execute("help", [])
        dispatched = router.dispatch("reflect help")
        self.assert_equal(direct.success, dispatched.success)
        self.assert_equal(direct.message, dispatched.message)

    # ---------- Bootstrap wiring ----------

    def _test_bootstrap_config_defaults_reflection_disabled(self) -> None:
        config = _config_with({})
        self.assert_false(
            bool(config.get("reflection.enabled", False)),
            "'reflection.enabled' must default to false when entirely absent from config",
        )

    def _test_bootstrap_registers_reflect_namespace_even_when_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            directory = Path(tmp_dir)
            _write_reflection_bootstrap_config(directory, reflection_section="")
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                try:
                    bootstrap.initialize()
                    self.assert_true(
                        "reflect" in bootstrap.command_router.module_names,
                        "'reflect' namespace must be registered even when 'reflection.enabled' is absent/false",
                    )
                finally:
                    bootstrap.shutdown()

    def _test_bootstrap_reflect_actions_report_disabled_message(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            directory = Path(tmp_dir)
            _write_reflection_bootstrap_config(directory, reflection_section="")
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                try:
                    bootstrap.initialize()
                    result = bootstrap.command_router.dispatch("reflect summary")
                    self.assert_false(result.success)
                    self.assert_true("disabled" in result.message.lower())
                finally:
                    bootstrap.shutdown()

    def _test_bootstrap_other_modules_unaffected_when_reflection_absent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            directory = Path(tmp_dir)
            _write_reflection_bootstrap_config(directory, reflection_section="")
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                try:
                    bootstrap.initialize()
                    other = bootstrap.command_router.dispatch("system version")
                    self.assert_true(other.success, "Other modules must be unaffected by EP-054 wiring")
                finally:
                    bootstrap.shutdown()
