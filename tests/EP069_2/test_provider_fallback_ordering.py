"""Real engineering tests for EP-069.2 STEP 2 - Configured AI Provider Fallback Ordering.

Single combined test suite (NAME = "EP069_2"), following the same
per-EP convention already established (EP-054 through EP-069.1) --
kept in its own package/NAME rather than reusing "EP069" so this
suite cannot collide with (or silently overwrite)
`tests.EP069.test_ai_provider_fallback`'s own `TestRegistry`
registration (`TestRegistry.register()` keys purely by `NAME`, so two
classes sharing one `NAME` would have the second import silently win
-- this repository's own known `TestRegistry` NAME-collision technical
debt, `docs/BACKLOG.md`). Self-contained -- no import from
`tests/EP069/`.

Per `docs/architecture/designs/EP069_2_DESIGN.md`, covers:
    - Backward compatibility: absent/empty `fallback_order` reproduces
      EP-069.1's original alphabetical `list_fallback_candidates()`
      order exactly.
    - Configured ordering: a full `fallback_order` is followed
      exactly.
    - Partial ordering: listed providers first (in configured order),
      unlisted providers appended afterward in alphabetical order.
    - Unknown provider names in `fallback_order` are inert -- no
      error, no fabricated candidate, no registry mutation.
    - Availability filtering is preserved: an unavailable provider
      named in `fallback_order` is still excluded.
    - Exclusion filtering is preserved: an already-attempted/excluded
      provider named in `fallback_order` never reappears.
    - No duplicates: a provider named more than once in
      `fallback_order` (or once in `fallback_order` and also present
      in the unlisted remainder) appears at most once in the result.
    - Determinism: repeated calls against the same registry/config
      produce identical ordering.
    - Fallback integration: `AIService.ask()`'s existing EP-069.1
      fallback loop actually follows the configured order, with zero
      `AIService` modification required to do so.
    - `ai.fallback_enabled: false` continues to disable fallback
      entirely, regardless of `fallback_order`.
    - `AIProvider`'s abstract contract is unaffected.
    - Bootstrap/config wiring: a real `Bootstrap` correctly threads
      `ai.fallback_order` from `config.yaml` into the real
      `ProviderManager` it constructs, including the invalid-type
      fallback (Section 14 of the design).
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from src.bootstrap import Bootstrap
from src.core.ai.provider import (
    AIProvider,
    ProviderHealth,
    ProviderResponse,
    ProviderStatus,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from src.core.ai.provider_manager import ProviderManager
from src.core.ai.provider_registry import ProviderRegistry
from src.services.ai_service import AIService
from src.testing.base_test import BaseTest
from src.testing.registry import TestRegistry


# ---------- Fakes (independent copies of tests/EP069's own shapes) ----------


class _FakeAIProvider(AIProvider):
    """Deterministic, test-only concrete `AIProvider` (mirrors EP-069.1's own fake)."""

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


class _FakeConfig:
    """Deterministic, test-only stand-in for `Config` (mirrors EP-069.1's own fake)."""

    def __init__(self, values: dict | None = None) -> None:
        self._values = values if values is not None else {"conversation.enabled": False}

    def get(self, key: str, default=None):
        return self._values.get(key, default)


class _FakeContext:
    rendered: str = ""


class _FakeContextManager:
    def create(self, conversation, query: str) -> _FakeContext:
        return _FakeContext()


class _FakeBuiltPrompt:
    def __init__(self, rendered: str) -> None:
        self.rendered = rendered


class _FakePromptManager:
    def __init__(self) -> None:
        self.build_calls = 0

    def build(self, *, user_prompt: str, context, provider_name: str) -> _FakeBuiltPrompt:
        self.build_calls += 1
        return _FakeBuiltPrompt(rendered=f"RENDERED::{user_prompt}")


def _make_registry(*providers: _FakeAIProvider) -> ProviderRegistry:
    registry = ProviderRegistry()
    for provider in providers:
        registry.register(provider)
    return registry


def _make_service(
    *,
    provider_manager: ProviderManager,
    prompt_manager: _FakePromptManager,
    fallback_enabled: bool,
) -> AIService:
    return AIService(
        config=_FakeConfig(),
        provider_manager=provider_manager,
        conversation_manager=None,
        prompt_manager=prompt_manager,
        context_manager=_FakeContextManager(),
        fallback_enabled=fallback_enabled,
    )


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


# A minimal, self-contained, offline-safe full config.yaml -- every key
# not directly relevant to this suite resolves to a value `Bootstrap
# .initialize()` can build a working AI subsystem from without any
# network access. `providers.claude`/`providers.gemini` use a
# non-empty, fake `api_key` purely so `is_available()` is True (no
# network request is made to determine availability -- see
# `ClaudeProvider.is_available()`/`GeminiProvider.is_available()`).
_FULL_BOOTSTRAP_CONFIG_YAML = (
    "app:\n"
    '  name: "JARVIS-TEST"\n'
    '  tagline: "Test"\n'
    '  version: "0.0.0-test"\n\n'
    "logging:\n"
    '  level: "INFO"\n'
    "  retention_days: 1\n"
    "  console_enabled: false\n\n"
    "paths:\n"
    '  logs: "logs"\n'
    '  data_input: "data/input"\n'
    '  data_output: "data/output"\n'
    '  data_cache: "data/cache"\n'
    '  data_database: "data/database"\n'
    '  knowledge: "knowledge"\n'
    '  prompts: "prompts"\n\n'
    "memory:\n"
    "  enabled: false\n"
    "  persistent: false\n"
    "  auto_save: false\n"
    "  max_entries: 10000\n"
    "  default_ttl: null\n"
    '  default_provider: "memory"\n\n'
    "knowledge:\n"
    "  enabled: true\n"
    '  default_provider: "local"\n\n'
    "long_term_memory:\n"
    "  enabled: true\n"
    '  default_provider: "knowledge"\n\n'
    "orchestrator:\n"
    "  skills_enabled: []\n\n"
    "invoice:\n"
    '  script: ""\n\n'
    "fast_response:\n"
    '  workbook: ""\n'
    '  worksheet: ""\n'
    '  backup_folder: ""\n\n'
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
    "  tick_interval: 3600\n\n"
    "plugins:\n"
    "  enabled: true\n"
    "  auto_load: false\n"
    "  auto_discovery: false\n"
    '  plugin_directory: "plugins"\n\n'
    "telegram:\n"
    "  enabled: false\n"
    "  auto_start: false\n"
    '  token: ""\n'
    "  allowed_chat_ids: []\n"
    "  polling_interval: 2\n\n"
    "ai:\n"
    "  enabled: true\n"
    '  default_provider: "none"\n'
    "  timeout: 120\n"
    "  retry_count: 2\n"
    "  max_context_messages: 20\n"
    "  fallback_enabled: true\n"
    "{fallback_order_section}"
    "conversation:\n"
    "  enabled: true\n"
    "  auto_save: false\n"
    "  max_messages: 100\n"
    "  max_conversations: 100\n"
    '  storage_file: "data/database/conversations.json"\n'
    '  truncate_strategy: "oldest"\n\n'
    "prompt:\n"
    "  enabled: true\n"
    '  system_prompt: ""\n'
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
    '  storage_backend: "memory"\n'
    '  storage_file: "data/database/project_index.json"\n\n'
    "providers:\n"
    "  claude:\n"
    "    enabled: true\n"
    '    api_key: "test-fake-key"\n'
    "  openai:\n"
    "    enabled: false\n"
    '    api_key: ""\n'
    "  gemini:\n"
    "    enabled: true\n"
    '    api_key: "test-fake-key"\n'
    "  ollama:\n"
    "    enabled: false\n"
    '    endpoint: ""\n'
    "  lmstudio:\n"
    "    enabled: false\n"
    '    endpoint: ""\n\n'
    "embedding:\n"
    "  enabled: true\n"
    '  default_provider: "local"\n'
    "  batch_size: 16\n"
    "  providers:\n"
    "    local:\n"
    "      enabled: true\n"
    '      model: "local-hash-v1"\n'
    "      dimension: 16\n"
    "    cloud:\n"
    "      enabled: false\n"
    '      api_key: ""\n'
    '      model: "text-embedding-cloud-v1"\n'
    "      dimension: 1536\n\n"
    "rag:\n"
    "  enabled: true\n"
    "  top_k: 5\n"
    "  max_context_characters: 4000\n\n"
    "semantic:\n"
    "  enabled: true\n"
    '  default_provider: "semantic"\n'
    "  top_k: 5\n"
    "  similarity_threshold: 0.0\n\n"
    "context_compression:\n"
    "  enabled: true\n"
    '  default_provider: "compression"\n'
    "  max_context_characters: 12000\n"
    "  max_chunks: 20\n"
    "  deduplicate: true\n\n"
    "agent:\n"
    "  enabled: true\n"
    '  default_agent: "jarvis"\n'
    '  startup_mode: "idle"\n\n'
    "planning:\n"
    "  enabled: true\n"
    '  default_provider: "planning"\n'
    "  max_steps: 10\n\n"
    "plan_execution:\n"
    "  enabled: true\n"
    '  default_provider: "plan_execution"\n'
    "  stop_on_failure: true\n\n"
    "tool:\n"
    "  enabled: true\n"
    '  default_provider: "tool_engine"\n\n'
    "collaboration:\n"
    "  enabled: true\n"
    '  default_provider: "collaboration"\n\n'
    "workflow_engine:\n"
    "  enabled: true\n"
    '  default_provider: "workflow_engine"\n'
    "  stop_on_failure: true\n\n"
    "workflow_scheduler:\n"
    "  enabled: true\n"
    "  auto_start: false\n"
    "  tick_interval: 5\n\n"
    "automation:\n"
    "  enabled: true\n\n"
    "git:\n"
    "  enabled: false\n\n"
    "github:\n"
    "  enabled: false\n\n"
    "telegram_info:\n"
    "  enabled: false\n\n"
    "discord:\n"
    "  enabled: false\n\n"
    "email:\n"
    "  enabled: false\n\n"
    "api:\n"
    "  enabled: false\n"
    '  host: "127.0.0.1"\n'
    "  port: 0\n"
)


def _write_full_bootstrap_config(directory: Path, fallback_order_section: str = "") -> None:
    """Write config/config.yaml (a full, offline-safe config) under `directory`."""
    config_dir = directory / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "config.yaml").write_text(
        _FULL_BOOTSTRAP_CONFIG_YAML.format(fallback_order_section=fallback_order_section),
        encoding="utf-8",
    )


@TestRegistry.register
class ProviderFallbackOrderingTest(BaseTest):
    NAME = "EP069_2"

    def run(self):
        # ---------- ProviderManager.list_fallback_candidates() ordering ----------
        self._test_absent_order_preserves_alphabetical()
        self._test_empty_order_preserves_alphabetical()
        self._test_full_order_is_respected()
        self._test_partial_order_lists_first_then_alphabetical_remainder()
        self._test_unknown_names_are_inert()
        self._test_unavailable_configured_provider_still_excluded()
        self._test_excluded_provider_remains_excluded_even_if_configured()
        self._test_duplicate_names_produce_no_duplicate_candidates()
        self._test_repeated_calls_are_deterministic()

        # ---------- AIService fallback-loop integration ----------
        self._test_fallback_loop_follows_configured_order()
        self._test_fallback_disabled_ignores_configured_order()

        # ---------- AIProvider contract ----------
        self._test_provider_contract_unaffected()

        # ---------- Bootstrap / configuration wiring ----------
        self._test_bootstrap_wires_configured_fallback_order()
        self._test_bootstrap_absent_fallback_order_preserves_alphabetical()
        self._test_bootstrap_invalid_type_fallback_order_is_ignored()

        return self.result

    # ---------- ProviderManager.list_fallback_candidates() ordering ----------

    def _test_absent_order_preserves_alphabetical(self) -> None:
        registry = _make_registry(
            _FakeAIProvider("openai"), _FakeAIProvider("claude"), _FakeAIProvider("gemini")
        )
        manager = ProviderManager(registry=registry, enabled=True, default_provider="none")

        candidates = manager.list_fallback_candidates(exclude=[])

        self.assert_equal(
            [p.name() for p in candidates],
            ["claude", "gemini", "openai"],
            "Absent 'fallback_order' must preserve EP-069.1's original alphabetical order.",
        )

    def _test_empty_order_preserves_alphabetical(self) -> None:
        registry = _make_registry(
            _FakeAIProvider("openai"), _FakeAIProvider("claude"), _FakeAIProvider("gemini")
        )
        manager = ProviderManager(
            registry=registry, enabled=True, default_provider="none", fallback_order=[]
        )

        candidates = manager.list_fallback_candidates(exclude=[])

        self.assert_equal(
            [p.name() for p in candidates],
            ["claude", "gemini", "openai"],
            "Empty 'fallback_order' must behave identically to it being absent.",
        )

    def _test_full_order_is_respected(self) -> None:
        registry = _make_registry(_FakeAIProvider("claude"), _FakeAIProvider("gemini"))
        manager = ProviderManager(
            registry=registry,
            enabled=True,
            default_provider="none",
            fallback_order=["gemini", "claude"],
        )

        candidates = manager.list_fallback_candidates(exclude=[])

        self.assert_equal(
            [p.name() for p in candidates],
            ["gemini", "claude"],
            "A full 'fallback_order' covering every eligible candidate must be followed exactly.",
        )

    def _test_partial_order_lists_first_then_alphabetical_remainder(self) -> None:
        registry = _make_registry(
            _FakeAIProvider("claude"), _FakeAIProvider("gemini"), _FakeAIProvider("openai")
        )
        manager = ProviderManager(
            registry=registry, enabled=True, default_provider="none", fallback_order=["gemini"]
        )

        candidates = manager.list_fallback_candidates(exclude=[])

        self.assert_equal(
            [p.name() for p in candidates],
            ["gemini", "claude", "openai"],
            "A partial 'fallback_order' must list configured providers first, then the "
            "remaining eligible providers in alphabetical order.",
        )

    def _test_unknown_names_are_inert(self) -> None:
        registry = _make_registry(_FakeAIProvider("claude"), _FakeAIProvider("gemini"))
        manager = ProviderManager(
            registry=registry,
            enabled=True,
            default_provider="none",
            fallback_order=["ghost-provider", "gemini"],
        )

        candidates = manager.list_fallback_candidates(exclude=[])

        self.assert_equal(
            [p.name() for p in candidates],
            ["gemini", "claude"],
            "An unregistered name in 'fallback_order' must be silently ignored, never an error "
            "and never a fabricated candidate.",
        )
        self.assert_equal(len(registry.list()), 2, "An unknown name must never mutate the registry.")

    def _test_unavailable_configured_provider_still_excluded(self) -> None:
        registry = _make_registry(
            _FakeAIProvider("claude", available=True),
            _FakeAIProvider("gemini", available=False),
        )
        manager = ProviderManager(
            registry=registry,
            enabled=True,
            default_provider="none",
            fallback_order=["gemini", "claude"],
        )

        candidates = manager.list_fallback_candidates(exclude=[])

        self.assert_equal(
            [p.name() for p in candidates],
            ["claude"],
            "Configured ordering must never bypass the existing is_available() filter.",
        )

    def _test_excluded_provider_remains_excluded_even_if_configured(self) -> None:
        registry = _make_registry(_FakeAIProvider("claude"), _FakeAIProvider("gemini"))
        manager = ProviderManager(
            registry=registry,
            enabled=True,
            default_provider="none",
            fallback_order=["claude", "gemini"],
        )

        candidates = manager.list_fallback_candidates(exclude=["claude"])

        self.assert_equal(
            [p.name() for p in candidates],
            ["gemini"],
            "A provider passed via 'exclude' must never reappear merely because it is also "
            "named in 'fallback_order'.",
        )

    def _test_duplicate_names_produce_no_duplicate_candidates(self) -> None:
        registry = _make_registry(
            _FakeAIProvider("claude"), _FakeAIProvider("gemini"), _FakeAIProvider("openai")
        )
        manager = ProviderManager(
            registry=registry,
            enabled=True,
            default_provider="none",
            fallback_order=["gemini", "gemini", "claude"],
        )

        candidates = manager.list_fallback_candidates(exclude=[])
        names = [p.name() for p in candidates]

        self.assert_equal(
            names, ["gemini", "claude", "openai"], "The first occurrence of a duplicate name must win."
        )
        self.assert_equal(len(names), len(set(names)), "No provider may appear twice in the result.")

    def _test_repeated_calls_are_deterministic(self) -> None:
        registry = _make_registry(
            _FakeAIProvider("claude"), _FakeAIProvider("gemini"), _FakeAIProvider("openai")
        )
        manager = ProviderManager(
            registry=registry, enabled=True, default_provider="none", fallback_order=["openai"]
        )

        first = [p.name() for p in manager.list_fallback_candidates(exclude=[])]
        second = [p.name() for p in manager.list_fallback_candidates(exclude=[])]

        self.assert_equal(
            first, second, "Repeated calls against an unchanged registry/config must be identical."
        )
        self.assert_equal(first, ["openai", "claude", "gemini"])

    # ---------- AIService fallback-loop integration ----------

    def _test_fallback_loop_follows_configured_order(self) -> None:
        claude = _FakeAIProvider("claude", raise_error=ProviderUnavailableError("claude down"))
        gemini = _FakeAIProvider("gemini", raise_error=ProviderTimeoutError("gemini slow"))
        openai = _FakeAIProvider("openai", response_text="openai reply")
        registry = _make_registry(claude, gemini, openai)
        manager = ProviderManager(
            registry=registry,
            enabled=True,
            default_provider="claude",
            fallback_order=["openai", "gemini"],
        )
        manager.set_current("claude")
        prompt_manager = _FakePromptManager()
        service = _make_service(
            provider_manager=manager, prompt_manager=prompt_manager, fallback_enabled=True
        )

        result = service.ask("hello")

        self.assert_true(result.success, "The configured-order fallback candidate must be attempted.")
        self.assert_equal(
            result.provider, "openai", "The first configured candidate ('openai') must serve the request."
        )
        self.assert_equal(len(gemini.ask_calls), 0, "'gemini' must never be attempted once 'openai' succeeds.")

    def _test_fallback_disabled_ignores_configured_order(self) -> None:
        claude = _FakeAIProvider("claude", raise_error=ProviderUnavailableError("claude down"))
        gemini = _FakeAIProvider("gemini", response_text="should never be used")
        registry = _make_registry(claude, gemini)
        manager = ProviderManager(
            registry=registry, enabled=True, default_provider="claude", fallback_order=["gemini"]
        )
        manager.set_current("claude")
        prompt_manager = _FakePromptManager()
        service = _make_service(
            provider_manager=manager, prompt_manager=prompt_manager, fallback_enabled=False
        )

        result = service.ask("hello")

        self.assert_false(result.success, "With fallback disabled, the primary's failure must still be final.")
        self.assert_equal(
            len(gemini.ask_calls),
            0,
            "'ai.fallback_order' must have zero effect while 'ai.fallback_enabled' is false.",
        )

    # ---------- AIProvider contract ----------

    def _test_provider_contract_unaffected(self) -> None:
        # EP-069.2 adds no new abstract method and changes no existing
        # one -- constructing and fully exercising a concrete
        # AIProvider subclass with the exact pre-existing method set
        # confirms the contract is unchanged.
        provider = _FakeAIProvider("claude")
        self.assert_equal(provider.name(), "claude")
        self.assert_true(provider.is_available())
        self.assert_true(isinstance(provider.status(), ProviderStatus))
        self.assert_true(isinstance(provider.health(), ProviderHealth))
        self.assert_true(isinstance(provider.configuration(), dict))
        response = provider.ask("hi")
        self.assert_true(isinstance(response, ProviderResponse))

    # ---------- Bootstrap / configuration wiring ----------

    def _test_bootstrap_wires_configured_fallback_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(
                directory,
                fallback_order_section='  fallback_order: ["gemini", "claude"]\n\n',
            )
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.initialize()
                try:
                    ai_module = bootstrap.command_router._modules["ai"]
                    provider_manager = ai_module._service._provider_manager
                    candidates = provider_manager.list_fallback_candidates(exclude=[])
                    self.assert_equal(
                        [p.name() for p in candidates],
                        ["gemini", "claude"],
                        "A real Bootstrap must thread 'ai.fallback_order' from config.yaml "
                        "into the real ProviderManager it constructs.",
                    )
                finally:
                    bootstrap.shutdown()

    def _test_bootstrap_absent_fallback_order_preserves_alphabetical(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(directory, fallback_order_section="")
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.initialize()
                try:
                    ai_module = bootstrap.command_router._modules["ai"]
                    provider_manager = ai_module._service._provider_manager
                    candidates = provider_manager.list_fallback_candidates(exclude=[])
                    self.assert_equal(
                        [p.name() for p in candidates],
                        ["claude", "gemini"],
                        "Absent 'ai.fallback_order' in a real config.yaml must preserve "
                        "alphabetical order end-to-end.",
                    )
                finally:
                    bootstrap.shutdown()

    def _test_bootstrap_invalid_type_fallback_order_is_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(
                directory,
                fallback_order_section='  fallback_order: "gemini"\n\n',
            )
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.initialize()
                try:
                    ai_module = bootstrap.command_router._modules["ai"]
                    provider_manager = ai_module._service._provider_manager
                    candidates = provider_manager.list_fallback_candidates(exclude=[])
                    self.assert_equal(
                        [p.name() for p in candidates],
                        ["claude", "gemini"],
                        "A non-list 'ai.fallback_order' must be treated as absent, never crash "
                        "startup, and never partially apply.",
                    )
                finally:
                    bootstrap.shutdown()
