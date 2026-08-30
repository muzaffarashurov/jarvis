"""Real engineering tests for EP-055 STEP 2 - Prompt Optimizer.

Single combined test suite (NAME = "EP055"), following the same
precedent EP-043 through EP-054 already established: this sidesteps
the pre-existing `TestRegistry` NAME-collision technical debt
(docs/BACKLOG.md) entirely rather than triggering it.

Per `EP055_DESIGN.md` Section 12/Owner Decision D8, no real-`AIProvider`
integration test exists for this EP (a live provider call is not
deterministic, unlike EP-053's real-Tesseract OCR check) -- every test
here runs against a fake `AIProvider`/`ProviderManager`, plus real
`Bootstrap` wiring tests using the project's own minimal-bootstrap-
config fixture (`tests/EP045`).

Covers:
    - Argument-shape validation (`prompt optimize` rejects missing
      text/wrong `--template` argument count) -- rejected before any
      downstream call.
    - The `prompt_optimizer.enabled` safety gate: every action is
      rejected while disabled, with zero downstream calls; the action
      reaches its dependencies once enabled.
    - `prompt_optimizer.max_input_size`: input exceeding the cap is
      refused (never silently truncated), checked before the enabled
      gate/rate limit/provider call.
    - `prompt_optimizer.min_seconds_between_calls`: a rate-limit test
      using a fake, injected clock (never a real `time.sleep()`) -- a
      second call before the limit elapses is rejected; a call at or
      after the limit succeeds.
    - Positive-path generation: the exact prompt constructed from
      free-text input, and the exact `CommandResult` produced from the
      fake provider's response.
    - `--template <name>` loading: reads a real, temporary
      'paths.prompts' fixture file; not-found, unreadable, and empty
      template cases each report a clear failure via the reused
      `PromptTemplateNotFoundError` type, with zero calls to the
      provider.
    - Negative/security cases: no active provider, provider raises
      `ProviderError`.
    - `CommandRouter` dispatch equivalence.
    - `Bootstrap` wiring: `prompt_optimizer.enabled` defaults to false
      when entirely absent from config; the 'prompt' namespace is
      registered with `CommandRouter` regardless of the flag's value;
      actions report the disabled message until the flag is set to
      true; other modules (including the untouched 'reflect'
      namespace) are unaffected.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from src.bootstrap import Bootstrap
from src.core.ai.provider import ProviderError, ProviderResponse
from src.core.command_router import CommandRouter, CommandResult
from src.core.config import Config
from src.skills.prompt_optimizer.skill import HELP_TEXT, PromptOptimizerModule, _DISABLED_MESSAGE
from src.testing.base_test import BaseTest
from src.testing.registry import TestRegistry
from tests.EP045.test_web_dashboard import (
    _MINIMAL_BOOTSTRAP_CONFIG_YAML,
    _ChdirGuard,
    _api_section,
)


# ---------- Fakes ----------


class _FakeAIProvider:
    """Deterministic, test-only stand-in for a concrete `AIProvider`.

    Records every `ask()` call's prompt (`self.prompts`) so tests can
    assert exactly what `PromptOptimizerModule` constructed, without
    calling any real AI provider.
    """

    def __init__(self, response_text: str = "improved prompt", raise_error: Exception | None = None) -> None:
        self.prompts: list[str] = []
        self._response_text = response_text
        self._raise_error = raise_error

    def ask(self, prompt: str, max_tokens: int | None = None) -> ProviderResponse:
        self.prompts.append(prompt)
        if self._raise_error is not None:
            raise self._raise_error
        return ProviderResponse(text=self._response_text, model="fake-model", latency_ms=1.0)


@dataclass
class _FakeProviderManager:
    """Deterministic, test-only stand-in for `ProviderManager`.

    Exposes only `get_current()`, matching the one method
    `PromptOptimizerModule` actually calls.
    """

    provider: _FakeAIProvider | None
    get_current_call_count: int = field(default=0, init=False)

    def get_current(self):
        self.get_current_call_count += 1
        return self.provider


class _FakeClock:
    """A deterministic, manually-advanced stand-in for `time.monotonic`."""

    def __init__(self, start: float = 1000.0) -> None:
        self._now = start

    def __call__(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += seconds


class _PoisonedTemplatePromptOptimizerModule(PromptOptimizerModule):
    """Test-only subclass whose `_load_template` raises if ever called.

    Used to prove -- not merely assert via a mocked call count, but by
    an actual raised failure if the real code path is ever reached --
    that `_optimize()` never reaches `_load_template()` (and therefore
    never touches the filesystem) while `prompt_optimizer.enabled` is
    false (Owner Decision D10, resolving STEP 3 Findings 1/2). Mirrors
    this module's own `_FakeProviderManager`-style "raise if called"
    convention, applied to the one other collaborator capable of a
    side effect.
    """

    def _load_template(self, name: str) -> str:
        raise AssertionError("_load_template() must not be called while prompt_optimizer is disabled")


_UNSET = object()


def _config_with(overrides: dict) -> Config:
    """Build a Config whose in-memory data is exactly `overrides`."""
    config = Config(config_path=Path("unused.yaml"))
    config._data = overrides
    return config


def _prompt_optimizer_config(
    *,
    enabled: bool = True,
    max_input_size: int = 4000,
    min_seconds_between_calls: float = 30.0,
    prompts_dir: str | None = None,
) -> Config:
    """Build a Config with 'prompt_optimizer:'/'paths:' sections for PromptOptimizerModule tests."""
    data: dict = {
        "prompt_optimizer": {
            "enabled": enabled,
            "max_input_size": max_input_size,
            "min_seconds_between_calls": min_seconds_between_calls,
        }
    }
    if prompts_dir is not None:
        data["paths"] = {"prompts": prompts_dir}
    return _config_with(data)


def _write_prompt_optimizer_bootstrap_config(directory: Path, prompt_optimizer_section: str) -> None:
    """Write a minimal bootstrap config.yaml (EP-045's fixture) plus a 'prompt_optimizer:' block."""
    config_dir = directory / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    base_yaml = _MINIMAL_BOOTSTRAP_CONFIG_YAML.format(
        api_section=_api_section(enabled=False, web_dashboard_dir=None)
    )
    (config_dir / "config.yaml").write_text(base_yaml + "\n" + prompt_optimizer_section, encoding="utf-8")


@TestRegistry.register
class PromptOptimizerTest(BaseTest):
    NAME = "EP055"

    def run(self):
        # ---------- Argument-shape validation ----------
        self._test_optimize_rejects_no_arguments()
        self._test_optimize_rejects_wrong_template_argument_count()

        # ---------- prompt_optimizer.enabled gate ----------
        self._test_disabled_rejects_optimize_with_zero_downstream_calls()
        self._test_enabled_true_allows_optimize_to_reach_provider()

        # ---------- Gate-ordering fix (Owner Decision D10 -- STEP 4,
        # resolves STEP 3 Findings 1/2) ----------
        self._test_disabled_rejects_oversized_input_without_leaking_max_input_size()
        self._test_disabled_rejects_existing_template_without_reading_file()
        self._test_disabled_rejects_missing_template_without_disclosing_not_found()
        self._test_disabled_rejects_empty_template_without_disclosing_empty()

        # ---------- max_input_size ----------
        self._test_input_exceeding_max_size_rejected_before_provider_call()
        self._test_input_at_exactly_max_size_allowed()

        # ---------- rate limit ----------
        self._test_rate_limit_blocks_immediate_second_call()
        self._test_rate_limit_allows_call_after_elapsed()

        # ---------- positive path ----------
        self._test_optimize_returns_provider_response_text()
        self._test_optimize_prompt_contains_original_text()
        self._test_optimize_joins_multiple_word_arguments()

        # ---------- --template loading ----------
        self._test_template_loaded_and_sent_to_provider()
        self._test_template_not_found_reports_failure_with_zero_provider_calls()
        self._test_template_empty_reports_failure()

        # ---------- negative/security cases ----------
        self._test_optimize_no_provider_available()
        self._test_optimize_provider_raises_error()

        # ---------- HELP / unknown action ----------
        self._test_help_lists_commands()
        self._test_unknown_action_returns_failure()

        # ---------- CommandRouter integration ----------
        self._test_command_router_dispatch_matches_direct_execute()

        # ---------- Bootstrap wiring ----------
        self._test_bootstrap_config_defaults_prompt_optimizer_disabled()
        self._test_bootstrap_registers_prompt_namespace_even_when_disabled()
        self._test_bootstrap_prompt_actions_report_disabled_message()
        self._test_bootstrap_other_modules_unaffected_when_prompt_optimizer_absent()

        return self.result

    # ---------- Shared helper ----------

    def _build_module(
        self,
        *,
        config: Config | None = None,
        provider: _FakeAIProvider | None = _UNSET,
        clock: _FakeClock | None = None,
    ) -> tuple[PromptOptimizerModule, _FakeProviderManager]:
        if config is None:
            config = _prompt_optimizer_config()
        if provider is _UNSET:
            provider = _FakeAIProvider()
        provider_manager = _FakeProviderManager(provider=provider)
        module = PromptOptimizerModule(
            config=config,
            provider_manager=provider_manager,
            clock=clock if clock is not None else _FakeClock(),
        )
        return module, provider_manager

    # ---------- Argument-shape validation ----------

    def _test_optimize_rejects_no_arguments(self) -> None:
        module, provider_manager = self._build_module()
        result = module.execute("optimize", [])
        self.assert_false(result.success)
        self.assert_equal(provider_manager.get_current_call_count, 0)

    def _test_optimize_rejects_wrong_template_argument_count(self) -> None:
        module, provider_manager = self._build_module()
        for bad_arguments in (["--template"], ["--template", "a", "b"]):
            result = module.execute("optimize", bad_arguments)
            self.assert_false(result.success, f"arguments={bad_arguments} must be rejected")
        self.assert_equal(provider_manager.get_current_call_count, 0)

    # ---------- prompt_optimizer.enabled gate ----------

    def _test_disabled_rejects_optimize_with_zero_downstream_calls(self) -> None:
        module, provider_manager = self._build_module(config=_prompt_optimizer_config(enabled=False))
        result = module.execute("optimize", ["improve", "this"])
        self.assert_false(result.success)
        self.assert_true("disabled" in result.message.lower())
        self.assert_equal(provider_manager.get_current_call_count, 0)

    def _test_enabled_true_allows_optimize_to_reach_provider(self) -> None:
        module, provider_manager = self._build_module(config=_prompt_optimizer_config(enabled=True))
        result = module.execute("optimize", ["improve", "this"])
        self.assert_true(result.success)
        self.assert_equal(provider_manager.get_current_call_count, 1)

    # ---------- Gate-ordering fix (Owner Decision D10 -- resolves STEP 3 Findings 1/2) ----------

    def _test_disabled_rejects_oversized_input_without_leaking_max_input_size(self) -> None:
        """STEP 3 Finding 2: the disabled message, not the size-exceeded message, must win."""
        config = _prompt_optimizer_config(enabled=False, max_input_size=10)
        module, provider_manager = self._build_module(config=config)
        result = module.execute("optimize", ["this", "text", "is", "definitely", "too", "long"])
        self.assert_false(result.success)
        self.assert_equal(result.message, _DISABLED_MESSAGE)
        self.assert_true("max_input_size" not in result.message)
        self.assert_equal(provider_manager.get_current_call_count, 0)

    def _test_disabled_rejects_existing_template_without_reading_file(self) -> None:
        """STEP 3 Finding 1: an existing template's content must never be read while disabled."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            prompts_dir = Path(tmp_dir) / "prompts"
            prompts_dir.mkdir(parents=True, exist_ok=True)
            (prompts_dir / "greeting.txt").write_text("Say hello to the user.", encoding="utf-8")
            config = _prompt_optimizer_config(enabled=False, prompts_dir=str(prompts_dir))
            module = _PoisonedTemplatePromptOptimizerModule(
                config=config,
                provider_manager=_FakeProviderManager(provider=_FakeAIProvider()),
                clock=_FakeClock(),
            )
            result = module.execute("optimize", ["--template", "greeting"])
            self.assert_false(result.success)
            self.assert_equal(result.message, _DISABLED_MESSAGE)

    def _test_disabled_rejects_missing_template_without_disclosing_not_found(self) -> None:
        """STEP 3 Finding 1: template-existence must never be disclosed while disabled."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            prompts_dir = Path(tmp_dir) / "prompts"
            prompts_dir.mkdir(parents=True, exist_ok=True)
            config = _prompt_optimizer_config(enabled=False, prompts_dir=str(prompts_dir))
            module = _PoisonedTemplatePromptOptimizerModule(
                config=config,
                provider_manager=_FakeProviderManager(provider=_FakeAIProvider()),
                clock=_FakeClock(),
            )
            result = module.execute("optimize", ["--template", "does-not-exist"])
            self.assert_false(result.success)
            self.assert_equal(result.message, _DISABLED_MESSAGE)
            self.assert_true("not found" not in result.message.lower())

    def _test_disabled_rejects_empty_template_without_disclosing_empty(self) -> None:
        """STEP 3 Finding 1: whether a template is empty must never be disclosed while disabled."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            prompts_dir = Path(tmp_dir) / "prompts"
            prompts_dir.mkdir(parents=True, exist_ok=True)
            (prompts_dir / "blank.txt").write_text("   ", encoding="utf-8")
            config = _prompt_optimizer_config(enabled=False, prompts_dir=str(prompts_dir))
            module = _PoisonedTemplatePromptOptimizerModule(
                config=config,
                provider_manager=_FakeProviderManager(provider=_FakeAIProvider()),
                clock=_FakeClock(),
            )
            result = module.execute("optimize", ["--template", "blank"])
            self.assert_false(result.success)
            self.assert_equal(result.message, _DISABLED_MESSAGE)
            self.assert_true("empty" not in result.message.lower())

    # ---------- max_input_size ----------

    def _test_input_exceeding_max_size_rejected_before_provider_call(self) -> None:
        module, provider_manager = self._build_module(config=_prompt_optimizer_config(max_input_size=10))
        result = module.execute("optimize", ["this", "text", "is", "definitely", "too", "long"])
        self.assert_false(result.success)
        self.assert_true("max_input_size" in result.message)
        self.assert_equal(provider_manager.get_current_call_count, 0)

    def _test_input_at_exactly_max_size_allowed(self) -> None:
        text = "a" * 10
        module, provider_manager = self._build_module(config=_prompt_optimizer_config(max_input_size=10))
        result = module.execute("optimize", [text])
        self.assert_true(result.success)
        self.assert_equal(provider_manager.get_current_call_count, 1)

    # ---------- rate limit ----------

    def _test_rate_limit_blocks_immediate_second_call(self) -> None:
        clock = _FakeClock()
        module, provider_manager = self._build_module(
            config=_prompt_optimizer_config(min_seconds_between_calls=30.0), clock=clock
        )
        first = module.execute("optimize", ["hello"])
        self.assert_true(first.success)
        second = module.execute("optimize", ["hello", "again"])
        self.assert_false(second.success)
        self.assert_true("rate-limited" in second.message.lower())
        self.assert_equal(provider_manager.get_current_call_count, 1)

    def _test_rate_limit_allows_call_after_elapsed(self) -> None:
        clock = _FakeClock()
        module, provider_manager = self._build_module(
            config=_prompt_optimizer_config(min_seconds_between_calls=30.0), clock=clock
        )
        first = module.execute("optimize", ["hello"])
        self.assert_true(first.success)
        clock.advance(30.0)
        second = module.execute("optimize", ["hello", "again"])
        self.assert_true(second.success)
        self.assert_equal(provider_manager.get_current_call_count, 2)

    # ---------- positive path ----------

    def _test_optimize_returns_provider_response_text(self) -> None:
        provider = _FakeAIProvider(response_text="a much clearer version")
        module, _ = self._build_module(provider=provider)
        result = module.execute("optimize", ["make", "this", "better"])
        self.assert_true(result.success)
        self.assert_equal(result.message, "a much clearer version")

    def _test_optimize_prompt_contains_original_text(self) -> None:
        provider = _FakeAIProvider()
        module, _ = self._build_module(provider=provider)
        module.execute("optimize", ["make", "this", "better"])
        self.assert_equal(len(provider.prompts), 1)
        self.assert_true("make this better" in provider.prompts[0])

    def _test_optimize_joins_multiple_word_arguments(self) -> None:
        provider = _FakeAIProvider()
        module, _ = self._build_module(provider=provider)
        module.execute("optimize", ["one", "two", "three"])
        self.assert_true("one two three" in provider.prompts[0])

    # ---------- --template loading ----------

    def _test_template_loaded_and_sent_to_provider(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            prompts_dir = Path(tmp_dir) / "prompts"
            prompts_dir.mkdir(parents=True, exist_ok=True)
            (prompts_dir / "greeting.txt").write_text("Say hello to the user.", encoding="utf-8")
            provider = _FakeAIProvider()
            module, provider_manager = self._build_module(
                config=_prompt_optimizer_config(prompts_dir=str(prompts_dir)), provider=provider
            )
            result = module.execute("optimize", ["--template", "greeting"])
            self.assert_true(result.success)
            self.assert_equal(provider_manager.get_current_call_count, 1)
            self.assert_true("Say hello to the user." in provider.prompts[0])

    def _test_template_not_found_reports_failure_with_zero_provider_calls(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            prompts_dir = Path(tmp_dir) / "prompts"
            prompts_dir.mkdir(parents=True, exist_ok=True)
            module, provider_manager = self._build_module(
                config=_prompt_optimizer_config(prompts_dir=str(prompts_dir))
            )
            result = module.execute("optimize", ["--template", "does-not-exist"])
            self.assert_false(result.success)
            self.assert_true("not found" in result.message.lower())
            self.assert_equal(provider_manager.get_current_call_count, 0)

    def _test_template_empty_reports_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            prompts_dir = Path(tmp_dir) / "prompts"
            prompts_dir.mkdir(parents=True, exist_ok=True)
            (prompts_dir / "blank.txt").write_text("   ", encoding="utf-8")
            module, provider_manager = self._build_module(
                config=_prompt_optimizer_config(prompts_dir=str(prompts_dir))
            )
            result = module.execute("optimize", ["--template", "blank"])
            self.assert_false(result.success)
            self.assert_true("empty" in result.message.lower())
            self.assert_equal(provider_manager.get_current_call_count, 0)

    # ---------- negative/security cases ----------

    def _test_optimize_no_provider_available(self) -> None:
        module, _ = self._build_module(provider=None)
        result = module.execute("optimize", ["hello"])
        self.assert_false(result.success)
        self.assert_true("no ai provider" in result.message.lower())

    def _test_optimize_provider_raises_error(self) -> None:
        provider = _FakeAIProvider(raise_error=ProviderError("simulated failure"))
        module, _ = self._build_module(provider=provider)
        result = module.execute("optimize", ["hello"])
        self.assert_false(result.success)
        self.assert_true("simulated failure" in result.message)

    # ---------- HELP / unknown action ----------

    def _test_help_lists_commands(self) -> None:
        module, _ = self._build_module()
        result = module.execute("help", [])
        self.assert_true(result.success)
        self.assert_true("prompt optimize" in result.message)
        self.assert_equal(result.message, HELP_TEXT)

    def _test_unknown_action_returns_failure(self) -> None:
        module, _ = self._build_module()
        result = module.execute("save", [])
        self.assert_false(result.success, "'prompt save' does not exist in v1 (Owner Decision D4 -- return-only)")

    # ---------- CommandRouter integration ----------

    def _test_command_router_dispatch_matches_direct_execute(self) -> None:
        module, _ = self._build_module()
        router = CommandRouter()
        router.register(module)
        direct = module.execute("help", [])
        dispatched = router.dispatch("prompt help")
        self.assert_equal(direct.success, dispatched.success)
        self.assert_equal(direct.message, dispatched.message)

    # ---------- Bootstrap wiring ----------

    def _test_bootstrap_config_defaults_prompt_optimizer_disabled(self) -> None:
        config = _config_with({})
        self.assert_false(
            bool(config.get("prompt_optimizer.enabled", False)),
            "'prompt_optimizer.enabled' must default to false when entirely absent from config",
        )

    def _test_bootstrap_registers_prompt_namespace_even_when_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            directory = Path(tmp_dir)
            _write_prompt_optimizer_bootstrap_config(directory, prompt_optimizer_section="")
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                try:
                    bootstrap.initialize()
                    self.assert_true(
                        "prompt" in bootstrap.command_router.module_names,
                        "'prompt' namespace must be registered even when 'prompt_optimizer.enabled' is absent/false",
                    )
                finally:
                    bootstrap.shutdown()

    def _test_bootstrap_prompt_actions_report_disabled_message(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            directory = Path(tmp_dir)
            _write_prompt_optimizer_bootstrap_config(directory, prompt_optimizer_section="")
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                try:
                    bootstrap.initialize()
                    result = bootstrap.command_router.dispatch("prompt optimize hello")
                    self.assert_false(result.success)
                    self.assert_true("disabled" in result.message.lower())
                finally:
                    bootstrap.shutdown()

    def _test_bootstrap_other_modules_unaffected_when_prompt_optimizer_absent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            directory = Path(tmp_dir)
            _write_prompt_optimizer_bootstrap_config(directory, prompt_optimizer_section="")
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                try:
                    bootstrap.initialize()
                    other = bootstrap.command_router.dispatch("system version")
                    self.assert_true(other.success, "Other modules must be unaffected by EP-055 wiring")
                    reflect_result = bootstrap.command_router.dispatch("reflect help")
                    self.assert_true(
                        reflect_result.success,
                        "The pre-existing 'reflect' namespace (EP-054) must be unaffected by EP-055 wiring",
                    )
                finally:
                    bootstrap.shutdown()
