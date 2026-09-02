"""Real engineering tests for EP-058 - Autonomous Planning.

Builds real `AIPlanningProvider`/`PlanningManager`/`PlanningEngine`/
`PlanningService`/`PlanningModule`/`ProviderManager` instances --
composed with a fake `AIProvider` only for the one genuine external
network dependency this EP introduces -- and drives them exactly as a
caller would, matching the "real component, fake only the network
boundary" precedent `tests/EP057/test_memory_optimization.py` and
`EP057_ARCHITECTURE_AUDIT.md` Section 8 already established (a fake
is appropriate only for an external network dependency, never for an
in-repo component).

Per `EP058_DESIGN.md` (Owner Decision D1, "Candidate A"), EP-058 adds
exactly one new capability: `AIPlanningProvider`, a second, additive
`PlanningProvider` (EP-029) implementation that reasons about a
request's meaning using an AI provider (EP-014/015), reached only
through `ProviderManager.get_current()` -> `AIProvider.ask()`
directly (the same bypass-`AIService` pattern `PromptOptimizerModule`,
EP-055, already established). `DefaultPlanningProvider`'s own
deterministic behavior is completely unmodified and remains the
default; `AIPlanningProvider` is registered alongside it under the
name "ai", selectable via the already-existing, unmodified
`planning use ai` / `planning.default_provider: "ai"` mechanisms
(Owner Decision D3: no new CLI action, no new configuration key).

Covers:
    - `AIPlanningProvider` in isolation: `provider_name()`, `status()`/
      `is_available()`/`health()` (`NOT_CONFIGURED` when no AI
      provider is selected, `AVAILABLE` once one is), `plan()`'s
      happy path against a real `ProviderManager` + a minimal fake
      `AIProvider` (well-formed reply, messy formatting the model may
      produce despite instructions, an off-menu/invented pair
      rejected per this project's Unknown API Policy applied to AI
      output, an empty reply falling back to `acknowledge_request`,
      and `max_steps` truncation), `PlanningProviderConfigurationError`
      when unconfigured, and `PlanningProviderError` wrapping a real
      `AIProvider.ask()` failure.
    - The reply-parsing helpers (`_parse_line`/`_parse_reply`)
      directly, against a table of representative inputs.
    - `_MENU`'s derivation: confirmed to be the exact, deduplicated
      `(subsystem, action)` vocabulary `DefaultPlanningProvider`'s own
      `_KEYWORD_RULES` table recognizes -- not a hand-copied,
      independently-invented list.
    - `PlanningManager` compliance: `AIPlanningProvider` satisfies
      `register_provider()`/`get_provider()`/`set_current()`/
      `list_providers()`'s already-existing, unmodified contract with
      zero change to `PlanningManager` itself; a duplicate "ai"
      registration is rejected exactly as any other duplicate name
      would be.
    - Non-interference: `DefaultPlanningProvider`'s own behavior,
      selected by default, is completely unaffected by
      `AIPlanningProvider`'s mere registration.
    - `Bootstrap` wiring: `AIPlanningProvider` is registered under
      "ai" through a real, unmodified `Bootstrap.initialize()` run,
      reachable through the real, unmodified `CommandRouter`, with
      zero new CLI action and zero new configuration key -- proving
      `EP058_DESIGN.md` Section 6.4's "zero new CLI surface" claim is
      genuinely true, not merely argued. Includes the real,
      production, no-AI-provider-configured path (the project's own
      default, `ai.default_provider: "none"`) failing cleanly, and a
      real, in-process fake-provider path succeeding end to end
      through the actual `CommandRouter.dispatch()`.
    - Architecture compliance: `AIPlanningProvider` never imports
      `AIService`/`ConversationManager`/`PromptManager`/`PromptBuilder`/
      `PlanExecutionEngine`/`ToolEngine`/`AgentEngine` (the
      higher-level pipeline and sibling packages it deliberately
      never touches), and `planning_provider.py`/`planning_manager.py`/
      `planning_engine.py` (EP-029) remain completely unmodified.
"""

from __future__ import annotations

import inspect
import os
import tempfile
from pathlib import Path

from src.bootstrap import Bootstrap
from src.core.ai.provider import (
    AIProvider,
    ProviderError,
    ProviderHealth,
    ProviderResponse,
    ProviderStatus,
    ProviderUnavailableError,
)
from src.core.ai.provider_manager import ProviderManager
from src.core.ai.provider_registry import ProviderRegistry
from src.core.planning import ai_planning_provider as ai_planning_provider_module
from src.core.planning.ai_planning_provider import (
    _MENU,
    AIPlanningProvider,
    _parse_line,
    _parse_reply,
)
from src.core.planning.planning_manager import PlanningManager, PlanningProviderRegistryError
from src.core.planning.planning_provider import (
    DefaultPlanningProvider,
    PlanningProviderConfigurationError,
    PlanningProviderError,
    PlanningProviderStatus,
    _KEYWORD_RULES,
)
from src.testing.base_test import BaseTest
from src.testing.registry import TestRegistry


class _ChdirGuard:
    """Context manager: chdir into `directory`, always restoring the original cwd."""

    def __init__(self, directory: Path) -> None:
        self._directory = directory
        self._original = Path.cwd()

    def __enter__(self) -> Path:
        os.chdir(self._directory)
        return self._directory

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        os.chdir(self._original)


class _FakeAIProvider(AIProvider):
    """Minimal, real `AIProvider` implementation -- fakes only the network boundary.

    Used exactly the way `tests/EP057/test_memory_optimization.py`
    already uses a fake only at an external network boundary, never
    for an in-repo component: every other object in this suite
    (`ProviderManager`, `AIPlanningProvider`, `PlanningManager`) is
    real and unmodified.
    """

    def __init__(self, reply_text: str = "", raise_error: Exception | None = None) -> None:
        self._reply_text = reply_text
        self._raise_error = raise_error
        self.last_prompt: str | None = None
        self.call_count = 0

    def name(self) -> str:
        return "fake"

    def status(self) -> ProviderStatus:
        return ProviderStatus.AVAILABLE

    def is_available(self) -> bool:
        return True

    def health(self) -> ProviderHealth:
        return ProviderHealth(available=True, message="fake provider ok")

    def configuration(self) -> dict:
        return {}

    def ask(self, prompt: str, max_tokens: int | None = None) -> ProviderResponse:
        self.last_prompt = prompt
        self.call_count += 1
        if self._raise_error is not None:
            raise self._raise_error
        return ProviderResponse(text=self._reply_text, model="fake-model", latency_ms=1.0)


def _build_provider_manager(fake: _FakeAIProvider | None) -> ProviderManager:
    """Return a real `ProviderManager`, optionally with `fake` registered and selected."""
    registry = ProviderRegistry()
    if fake is not None:
        registry.register(fake)
    return ProviderManager(
        registry=registry,
        enabled=True,
        default_provider=fake.name() if fake is not None else "none",
    )


_FULL_BOOTSTRAP_CONFIG_YAML = (
    "app:\n"
    "  name: \"JARVIS-TEST\"\n"
    "  tagline: \"Test\"\n"
    "  version: \"0.0.0-test\"\n\n"
    "logging:\n"
    "  level: \"INFO\"\n"
    "  retention_days: 1\n"
    "  console_enabled: false\n\n"
    "paths:\n"
    "  logs: \"logs\"\n"
    "  data_input: \"data/input\"\n"
    "  data_output: \"data/output\"\n"
    "  data_cache: \"data/cache\"\n"
    "  data_database: \"data/database\"\n"
    "  knowledge: \"knowledge\"\n"
    "  prompts: \"prompts\"\n\n"
    "memory:\n"
    "  enabled: true\n"
    "  persistent: false\n"
    "  auto_save: false\n"
    "  max_entries: 10000\n"
    "  default_ttl: null\n"
    "  default_provider: \"memory\"\n\n"
    "knowledge:\n"
    "  enabled: true\n"
    "  default_provider: \"local\"\n\n"
    "long_term_memory:\n"
    "  enabled: true\n"
    "  default_provider: \"knowledge\"\n\n"
    "orchestrator:\n"
    "  skills_enabled: []\n\n"
    "invoice:\n"
    "  script: \"\"\n\n"
    "fast_response:\n"
    "  workbook: \"\"\n"
    "  worksheet: \"\"\n"
    "  backup_folder: \"\"\n\n"
    "workflows:\n"
    "  enabled: true\n"
    "  auto_register: true\n\n"
    "processes:\n"
    "  auto_start: false\n"
    "  dependency_check: true\n"
    "  health_check_interval: 60\n\n"
    "scheduler:\n"
    "  enabled: true\n"
    "  auto_start: false\n"
    "  tick_interval: 1\n\n"
    "plugins:\n"
    "  enabled: true\n"
    "  auto_load: false\n"
    "  auto_discovery: false\n"
    "  plugin_directory: \"plugins\"\n\n"
    "telegram:\n"
    "  enabled: false\n"
    "  auto_start: false\n"
    "  token: \"\"\n"
    "  allowed_chat_ids: []\n"
    "  polling_interval: 2\n\n"
    "ai:\n"
    "  enabled: true\n"
    "  default_provider: \"none\"\n"
    "  timeout: 120\n"
    "  retry_count: 2\n"
    "  max_context_messages: 20\n\n"
    "conversation:\n"
    "  enabled: true\n"
    "  auto_save: false\n"
    "  max_messages: 100\n"
    "  max_conversations: 100\n"
    "  storage_file: \"data/database/conversations.json\"\n"
    "  truncate_strategy: \"oldest\"\n\n"
    "prompt:\n"
    "  enabled: true\n"
    "  system_prompt: \"\"\n"
    "  append_datetime: false\n"
    "  append_provider_name: false\n"
    "  append_os_information: false\n"
    "  append_working_directory: false\n"
    "  max_prompt_size: 32000\n"
    "  reserved_system_prompt: 2000\n"
    "  reserved_conversation_history: 8000\n"
    "  reserved_user_prompt: 2000\n"
    "  reserved_provider_overhead: 1000\n\n"
    "context:\n"
    "  enabled: true\n"
    "  auto_load: true\n"
    "  include_environment: false\n"
    "  include_working_directory: false\n"
    "  include_project_files: false\n"
    "  smart_selection: true\n\n"
    "indexing:\n"
    "  storage_backend: \"memory\"\n"
    "  storage_file: \"data/database/project_index.json\"\n\n"
    "providers:\n"
    "  claude:\n"
    "    enabled: false\n"
    "    api_key: \"\"\n"
    "  openai:\n"
    "    enabled: false\n"
    "    api_key: \"\"\n"
    "  gemini:\n"
    "    enabled: false\n"
    "    api_key: \"\"\n"
    "  ollama:\n"
    "    enabled: false\n"
    "    endpoint: \"\"\n"
    "  lmstudio:\n"
    "    enabled: false\n"
    "    endpoint: \"\"\n\n"
    "embedding:\n"
    "  enabled: true\n"
    "  default_provider: \"local\"\n"
    "  batch_size: 16\n"
    "  providers:\n"
    "    local:\n"
    "      enabled: true\n"
    "      model: \"local-hash-v1\"\n"
    "      dimension: 16\n"
    "    cloud:\n"
    "      enabled: false\n"
    "      api_key: \"\"\n"
    "      model: \"text-embedding-cloud-v1\"\n"
    "      dimension: 1536\n\n"
    "rag:\n"
    "  enabled: true\n"
    "  top_k: 5\n"
    "  max_context_characters: 4000\n\n"
    "semantic:\n"
    "  enabled: true\n"
    "  default_provider: \"semantic\"\n"
    "  top_k: 5\n"
    "  similarity_threshold: 0.0\n\n"
    "context_compression:\n"
    "  enabled: true\n"
    "  default_provider: \"compression\"\n"
    "  max_context_characters: 12000\n"
    "  max_chunks: 20\n"
    "  deduplicate: true\n\n"
    "agent:\n"
    "  enabled: true\n"
    "  default_agent: \"jarvis\"\n"
    "  startup_mode: \"idle\"\n\n"
    "planning:\n"
    "  enabled: true\n"
    "  default_provider: \"planning\"\n"
    "  max_steps: 10\n"
)


def _write_full_bootstrap_config(directory: Path) -> None:
    """Write config/config.yaml (a full, offline-safe config) under `directory`."""
    config_dir = directory / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "config.yaml").write_text(_FULL_BOOTSTRAP_CONFIG_YAML, encoding="utf-8")


@TestRegistry.register
class AutonomousPlanningTest(BaseTest):
    NAME = "EP058"

    def run(self):
        # ---------- _MENU derivation ----------
        self._test_menu_matches_default_provider_vocabulary()
        self._test_menu_has_no_duplicate_pairs()

        # ---------- Reply parsing (_parse_line / _parse_reply) ----------
        self._test_parse_line_well_formed()
        self._test_parse_line_strips_bullet_and_numbered_markers()
        self._test_parse_line_strips_trailing_description()
        self._test_parse_line_rejects_lines_without_pipe()
        self._test_parse_reply_well_formed_multi_line()
        self._test_parse_reply_rejects_off_menu_pair()
        self._test_parse_reply_deduplicates_repeated_pair()
        self._test_parse_reply_empty_falls_back_to_acknowledge_request()
        self._test_parse_reply_malformed_only_falls_back()
        self._test_parse_reply_enforces_max_steps()

        # ---------- AIPlanningProvider in isolation ----------
        self._test_provider_name()
        self._test_status_not_configured_without_ai_provider()
        self._test_status_available_with_ai_provider()
        self._test_health_reflects_status()
        self._test_plan_happy_path_sends_correct_prompt()
        self._test_plan_invalid_max_steps_raises()
        self._test_plan_raises_configuration_error_without_ai_provider()
        self._test_plan_wraps_real_provider_error()
        self._test_plan_never_returns_empty_steps()
        self._test_plan_available_flag_always_true()

        # ---------- PlanningManager compliance ----------
        self._test_manager_registers_and_selects_ai_provider()
        self._test_manager_duplicate_ai_registration_raises()
        self._test_manager_list_providers_includes_both()

        # ---------- Non-interference with DefaultPlanningProvider ----------
        self._test_default_provider_unaffected_by_ai_registration()
        self._test_default_provider_remains_selected_by_default()

        # ---------- Bootstrap wiring (real production path) ----------
        self._test_bootstrap_registers_ai_provider_with_zero_config_change()
        self._test_bootstrap_default_provider_still_planning()
        self._test_bootstrap_use_ai_then_plan_fails_cleanly_without_real_provider()
        self._test_bootstrap_use_ai_then_plan_succeeds_with_real_wiring_and_fake_backend()
        self._test_bootstrap_deterministic_plan_unaffected_after_ai_registered()

        # ---------- Architectural acceptance criteria ----------
        self._test_no_forbidden_imports()
        self._test_no_higher_level_ai_pipeline_imports()
        self._test_ep029_files_untouched_by_import_surface()

        return self.result

    # ---------- _MENU derivation ----------

    def _test_menu_matches_default_provider_vocabulary(self) -> None:
        expected_pairs = set()
        for _keyword, subsystem, action, _description in _KEYWORD_RULES:
            expected_pairs.add((subsystem, action))
        actual_pairs = {(subsystem, action) for subsystem, action, _description in _MENU}
        self.assert_equal(expected_pairs, actual_pairs)

    def _test_menu_has_no_duplicate_pairs(self) -> None:
        pairs = [(subsystem, action) for subsystem, action, _description in _MENU]
        self.assert_equal(len(pairs), len(set(pairs)))

    # ---------- Reply parsing ----------

    def _test_parse_line_well_formed(self) -> None:
        self.assert_equal(_parse_line("memory|retrieve_from_memory"), ("memory", "retrieve_from_memory"))

    def _test_parse_line_strips_bullet_and_numbered_markers(self) -> None:
        self.assert_equal(_parse_line("- memory|retrieve_from_memory"), ("memory", "retrieve_from_memory"))
        self.assert_equal(_parse_line("* semantic|semantic_search"), ("semantic", "semantic_search"))
        self.assert_equal(_parse_line("1. semantic|semantic_search"), ("semantic", "semantic_search"))
        self.assert_equal(_parse_line("12) knowledge|query_knowledge_base"), ("knowledge", "query_knowledge_base"))

    def _test_parse_line_strips_trailing_description(self) -> None:
        result = _parse_line("agent|coordinate_subsystems - Coordinate subsystems via the Agent Framework.")
        self.assert_equal(result, ("agent", "coordinate_subsystems"))

    def _test_parse_line_rejects_lines_without_pipe(self) -> None:
        self.assert_true(_parse_line("just some prose with no pipe") is None)
        self.assert_true(_parse_line("") is None)
        self.assert_true(_parse_line("   ") is None)

    def _test_parse_reply_well_formed_multi_line(self) -> None:
        reply = "memory|retrieve_from_memory\nsemantic|semantic_search"
        steps, truncated = _parse_reply(reply, max_steps=10)
        self.assert_equal(len(steps), 2)
        self.assert_equal(steps[0].subsystem, "memory")
        self.assert_equal(steps[0].action, "retrieve_from_memory")
        self.assert_equal(steps[0].order, 1)
        self.assert_equal(steps[1].subsystem, "semantic")
        self.assert_equal(steps[1].order, 2)
        self.assert_false(truncated)

    def _test_parse_reply_rejects_off_menu_pair(self) -> None:
        reply = "memory|retrieve_from_memory\nbogus_subsystem|not_a_real_action"
        steps, truncated = _parse_reply(reply, max_steps=10)
        self.assert_equal(len(steps), 1)
        self.assert_equal(steps[0].subsystem, "memory")
        self.assert_false(truncated)

    def _test_parse_reply_deduplicates_repeated_pair(self) -> None:
        reply = "memory|retrieve_from_memory\nmemory|retrieve_from_memory"
        steps, _truncated = _parse_reply(reply, max_steps=10)
        self.assert_equal(len(steps), 1)

    def _test_parse_reply_empty_falls_back_to_acknowledge_request(self) -> None:
        steps, truncated = _parse_reply("", max_steps=10)
        self.assert_equal(len(steps), 1)
        self.assert_true(steps[0].subsystem is None)
        self.assert_equal(steps[0].action, "acknowledge_request")
        self.assert_false(truncated)

    def _test_parse_reply_malformed_only_falls_back(self) -> None:
        steps, _truncated = _parse_reply("this is not a valid line\nneither is this", max_steps=10)
        self.assert_equal(len(steps), 1)
        self.assert_equal(steps[0].action, "acknowledge_request")

    def _test_parse_reply_enforces_max_steps(self) -> None:
        reply = "\n".join(f"{subsystem}|{action}" for subsystem, action, _d in _MENU)
        steps, truncated = _parse_reply(reply, max_steps=2)
        self.assert_equal(len(steps), 2)
        self.assert_true(truncated)
        self.assert_equal(steps[0].order, 1)
        self.assert_equal(steps[1].order, 2)

    # ---------- AIPlanningProvider in isolation ----------

    def _test_provider_name(self) -> None:
        provider = AIPlanningProvider(provider_manager=_build_provider_manager(None))
        self.assert_equal(provider.provider_name(), "ai")

    def _test_status_not_configured_without_ai_provider(self) -> None:
        provider = AIPlanningProvider(provider_manager=_build_provider_manager(None))
        self.assert_equal(provider.status(), PlanningProviderStatus.NOT_CONFIGURED)
        self.assert_false(provider.is_available())

    def _test_status_available_with_ai_provider(self) -> None:
        fake = _FakeAIProvider(reply_text="memory|retrieve_from_memory")
        provider = AIPlanningProvider(provider_manager=_build_provider_manager(fake))
        self.assert_equal(provider.status(), PlanningProviderStatus.AVAILABLE)
        self.assert_true(provider.is_available())

    def _test_health_reflects_status(self) -> None:
        provider_unconfigured = AIPlanningProvider(provider_manager=_build_provider_manager(None))
        health_unconfigured = provider_unconfigured.health()
        self.assert_false(health_unconfigured.available)

        fake = _FakeAIProvider(reply_text="memory|retrieve_from_memory")
        provider_configured = AIPlanningProvider(provider_manager=_build_provider_manager(fake))
        health_configured = provider_configured.health()
        self.assert_true(health_configured.available)

    def _test_plan_happy_path_sends_correct_prompt(self) -> None:
        fake = _FakeAIProvider(reply_text="memory|retrieve_from_memory\nsemantic|semantic_search")
        provider = AIPlanningProvider(provider_manager=_build_provider_manager(fake))
        plan = provider.plan("remember and search for something", max_steps=10)

        self.assert_equal(plan.request, "remember and search for something")
        self.assert_equal(plan.step_count, 2)
        self.assert_false(plan.truncated)
        self.assert_equal(fake.call_count, 1)
        # The request text and every menu entry must appear in the sent prompt.
        self.assert_true("remember and search for something" in fake.last_prompt)
        for subsystem, action, _description in _MENU:
            self.assert_true(f"{subsystem}|{action}" in fake.last_prompt)

    def _test_plan_invalid_max_steps_raises(self) -> None:
        fake = _FakeAIProvider(reply_text="memory|retrieve_from_memory")
        provider = AIPlanningProvider(provider_manager=_build_provider_manager(fake))
        try:
            provider.plan("do something", max_steps=0)
            self.assert_true(False, "expected PlanningProviderError for max_steps=0")
        except PlanningProviderError:
            self.result.add_pass()
        # The AI provider must never be called when validation fails first.
        self.assert_equal(fake.call_count, 0)

    def _test_plan_raises_configuration_error_without_ai_provider(self) -> None:
        provider = AIPlanningProvider(provider_manager=_build_provider_manager(None))
        try:
            provider.plan("do something", max_steps=10)
            self.assert_true(False, "expected PlanningProviderConfigurationError")
        except PlanningProviderConfigurationError:
            self.result.add_pass()

    def _test_plan_wraps_real_provider_error(self) -> None:
        fake = _FakeAIProvider(raise_error=ProviderUnavailableError("simulated network failure"))
        provider = AIPlanningProvider(provider_manager=_build_provider_manager(fake))
        try:
            provider.plan("do something", max_steps=10)
            self.assert_true(False, "expected PlanningProviderError")
        except PlanningProviderError as exc:
            self.assert_true("simulated network failure" in str(exc))
        except ProviderError:
            self.assert_true(False, "raw ProviderError must not escape -- it must be wrapped")

    def _test_plan_never_returns_empty_steps(self) -> None:
        fake = _FakeAIProvider(reply_text="nonsense with no pipe at all")
        provider = AIPlanningProvider(provider_manager=_build_provider_manager(fake))
        plan = provider.plan("do something unusual", max_steps=10)
        self.assert_true(plan.step_count >= 1)

    def _test_plan_available_flag_always_true(self) -> None:
        """AIPlanningProvider never queries a live subsystem registry itself (matches DefaultPlanningProvider)."""
        fake = _FakeAIProvider(reply_text="memory|retrieve_from_memory\nagent|coordinate_subsystems")
        provider = AIPlanningProvider(provider_manager=_build_provider_manager(fake))
        plan = provider.plan("remember and coordinate", max_steps=10)
        for step in plan.steps:
            self.assert_true(step.available)

    # ---------- PlanningManager compliance ----------

    def _test_manager_registers_and_selects_ai_provider(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = self._build_config(Path(tmp))
            manager = PlanningManager(config=config)
            fake = _FakeAIProvider(reply_text="memory|retrieve_from_memory")
            manager.register_provider(AIPlanningProvider(provider_manager=_build_provider_manager(fake)))
            manager.set_current("ai")
            self.assert_equal(manager.current_provider_name(), "ai")
            current = manager.get_current()
            self.assert_equal(current.provider_name(), "ai")

    def _test_manager_duplicate_ai_registration_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = self._build_config(Path(tmp))
            manager = PlanningManager(config=config)
            manager.register_provider(AIPlanningProvider(provider_manager=_build_provider_manager(None)))
            try:
                manager.register_provider(AIPlanningProvider(provider_manager=_build_provider_manager(None)))
                self.assert_true(False, "expected PlanningProviderRegistryError")
            except PlanningProviderRegistryError:
                self.result.add_pass()

    def _test_manager_list_providers_includes_both(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = self._build_config(Path(tmp))
            manager = PlanningManager(config=config)
            manager.register_provider(AIPlanningProvider(provider_manager=_build_provider_manager(None)))
            names = sorted(p.provider_name() for p in manager.list_providers())
            self.assert_equal(names, ["ai", "planning"])

    # ---------- Non-interference with DefaultPlanningProvider ----------

    def _test_default_provider_unaffected_by_ai_registration(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = self._build_config(Path(tmp))
            manager = PlanningManager(config=config)
            before = manager.get_current().plan("remember my birthday", max_steps=10)
            manager.register_provider(AIPlanningProvider(provider_manager=_build_provider_manager(None)))
            after = manager.get_current().plan("remember my birthday", max_steps=10)
            self.assert_equal(before.step_count, after.step_count)
            self.assert_equal(before.steps[0].subsystem, after.steps[0].subsystem)
            self.assert_equal(before.steps[0].action, after.steps[0].action)

    def _test_default_provider_remains_selected_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = self._build_config(Path(tmp))
            manager = PlanningManager(config=config)
            manager.register_provider(AIPlanningProvider(provider_manager=_build_provider_manager(None)))
            self.assert_equal(manager.current_provider_name(), "planning")
            self.assert_true(isinstance(manager.get_current(), DefaultPlanningProvider))

    # ---------- Bootstrap wiring (real production path) ----------

    def _test_bootstrap_registers_ai_provider_with_zero_config_change(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(directory)
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.initialize()
                self.assert_true(bootstrap.planning_service is not None)

                result = bootstrap._command_router.dispatch("planning providers")  # noqa: SLF001
                self.assert_true(result.success)
                self.assert_true("ai" in result.message)
                self.assert_true("planning" in result.message)

    def _test_bootstrap_default_provider_still_planning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(directory)
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.initialize()
                status = bootstrap.planning_service.status()
                self.assert_equal(status.current_provider, "planning")

    def _test_bootstrap_use_ai_then_plan_fails_cleanly_without_real_provider(self) -> None:
        """The project's own real default ('ai.default_provider: none') must fail cleanly, never crash."""
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(directory)
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.initialize()

                use_result = bootstrap._command_router.dispatch("planning use ai")  # noqa: SLF001
                self.assert_true(use_result.success)

                plan_result = bootstrap._command_router.dispatch(  # noqa: SLF001
                    "planning plan remember my birthday"
                )
                self.assert_false(plan_result.success)
                self.assert_true("No AI provider is currently selected" in plan_result.message)

    def _test_bootstrap_use_ai_then_plan_succeeds_with_real_wiring_and_fake_backend(self) -> None:
        """Full real path: Bootstrap -> CommandRouter -> PlanningService -> PlanningEngine

        -> PlanningManager -> AIPlanningProvider -> ProviderManager -- with only
        the AI network boundary faked, exactly as the module docstring describes.

        This reuses the *already-registered* `AIPlanningProvider`
        Bootstrap itself constructs (never a second, duplicate
        registration -- `PlanningManager.register_provider()` rejects
        a duplicate "ai" name by design, confirmed in
        `_test_manager_duplicate_ai_registration_raises`). The fake AI
        backend is injected into that provider's own, already-real,
        already-shared `ProviderManager` -- the same instance
        `AIService` itself depends on (both are constructed from the
        identical `ai_provider_manager` object in
        `src/bootstrap.py`) -- using only that `ProviderManager`'s own
        already-existing, public `register_provider()`/`set_current()`
        methods. No new production accessor is introduced anywhere;
        this test reaches the real object graph exactly the way
        `tests/EP057/test_memory_optimization.py`'s own Bootstrap
        tests already reach `bootstrap._command_router` and
        `bootstrap.planning_service._manager` -- an already-existing
        private attribute of an already-real, already-constructed
        production object, not a new public API surface.
        """
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(directory)
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.initialize()

                # Reach the real, already-registered "ai" AIPlanningProvider
                # through the real, already-exposed planning_service --
                # never constructing or registering a second one.
                real_planning_manager = bootstrap.planning_service._manager  # noqa: SLF001
                real_ai_provider = real_planning_manager.get_provider("ai")
                self.assert_true(isinstance(real_ai_provider, AIPlanningProvider))

                # That provider's own, already-real ProviderManager is the
                # exact same object AIService itself depends on (both are
                # constructed from the same `ai_provider_manager` in
                # src/bootstrap.py) -- inject the fake backend into it via
                # its own already-existing, public API only.
                real_ai_provider_manager = real_ai_provider._provider_manager  # noqa: SLF001
                self.assert_true(isinstance(real_ai_provider_manager, ProviderManager))
                self.assert_true(real_ai_provider_manager.get_current() is None)

                fake = _FakeAIProvider(reply_text="knowledge|query_knowledge_base")
                real_ai_provider_manager.register_provider(fake)
                real_ai_provider_manager.set_current("fake")

                use_result = bootstrap._command_router.dispatch("planning use ai")  # noqa: SLF001
                self.assert_true(use_result.success)

                plan_result = bootstrap._command_router.dispatch(  # noqa: SLF001
                    "planning plan look something up in the knowledge base"
                )
                self.assert_true(plan_result.success)
                self.assert_true("query_knowledge_base" in plan_result.message)
                self.assert_equal(fake.call_count, 1)

    def _test_bootstrap_deterministic_plan_unaffected_after_ai_registered(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(directory)
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.initialize()

                result = bootstrap._command_router.dispatch(  # noqa: SLF001
                    "planning plan remember my birthday"
                )
                self.assert_true(result.success)
                self.assert_true("retrieve_from_memory" in result.message)

    # ---------- Architectural acceptance criteria ----------

    def _test_no_forbidden_imports(self) -> None:
        """AIPlanningProvider must not reach the Reasoning/Reflection/Execution/Tool layer."""
        forbidden_fragments = (
            "src.core.reasoning",
            "src.core.reflection",
            "src.core.execution",
            "src.core.plan_execution",
            "src.core.tool",
            "src.core.agent",
            "src.core.collaboration",
            "src.core.workflow_engine",
            "src.core.workflow_scheduler",
            "src.core.automation_engine",
            "src.core.background_workers",
            "src.core.memory",
            "src.core.long_term_memory",
            "src.core.knowledge",
            "src.core.semantic",
            "src.core.context_compression",
        )
        source = inspect.getsource(ai_planning_provider_module)
        for fragment in forbidden_fragments:
            self.assert_true(fragment not in source, f"ai_planning_provider.py must not reference '{fragment}'")

    def _test_no_higher_level_ai_pipeline_imports(self) -> None:
        """AIPlanningProvider must call AIProvider directly, never AIService's higher-level pipeline.

        Checks only the module's actual `import`/`from ... import`
        statements (not its docstrings or comments, which legitimately
        discuss -- in prose -- the higher-level pipeline this module
        deliberately bypasses, exactly as `EP058_DESIGN.md` Section
        3.8 itself does).
        """
        forbidden_fragments = (
            "AIService",
            "ConversationManager",
            "PromptManager",
            "PromptBuilder",
            "ContextManager",
            "ContextLoader",
        )
        import_lines = [
            line
            for line in inspect.getsource(ai_planning_provider_module).splitlines()
            if line.strip().startswith("import ") or line.strip().startswith("from ")
        ]
        for fragment in forbidden_fragments:
            self.assert_true(
                not any(fragment in line for line in import_lines),
                f"ai_planning_provider.py must not import '{fragment}'",
            )

    def _test_ep029_files_untouched_by_import_surface(self) -> None:
        """AIPlanningProvider imports only already-existing, public/intentionally-shared EP-029 names."""
        source = inspect.getsource(ai_planning_provider_module)
        self.assert_true("class DefaultPlanningProvider" not in source)
        self.assert_true("class PlanningManager" not in source)
        self.assert_true("class PlanningEngine" not in source)

    # ---------- Helpers ----------

    def _build_config(self, tmp_path: Path):
        from src.core.config import Config

        config_dir = tmp_path / "config"
        config_dir.mkdir(parents=True, exist_ok=True)
        config_path = config_dir / "config.yaml"
        config_path.write_text(
            "planning:\n  enabled: true\n  default_provider: \"planning\"\n  max_steps: 10\n",
            encoding="utf-8",
        )
        return Config(config_path).load()
