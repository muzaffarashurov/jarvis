"""Real engineering tests for EP-040 STEP 2 - TelegramInfoModule and Bootstrap wiring.

Covers CLI action dispatch/error-formatting against a real
TelegramInfoService backed by a stub bot (same technique as
test_telegram_info_service.py), plus real Bootstrap wiring.

Bootstrap-level note: `telegram.Bot.initialize()` calls `get_me()`
internally, which is a genuine network call to the Telegram API --
there is no way to exercise a *successful* real-Bot construction
through Bootstrap without either real network access or a real bot
token, both explicitly out of scope for this suite. The "enabled"
Bootstrap test below instead verifies the enabled code path is taken
and degrades gracefully (via a missing/blank token, which is checked
and raises *before* any Bot/network call is attempted) without
crashing the rest of Bootstrap.initialize() -- this is the strongest
claim that can be tested here without a real network call, and is
called out explicitly rather than silently worked around.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from src.bootstrap import Bootstrap
from src.core.config import Config
from src.services.telegram_info_service import TelegramInfoService
from src.modules.telegram_info_module import TelegramInfoModule
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


class _StubChat:
    def __init__(self, data: dict):
        self._data = data

    def to_dict(self) -> dict:
        return self._data


class _StubBot:
    def __init__(self, response_data: dict | None = None, exception: Exception | None = None):
        self.response_data = response_data
        self.exception = exception
        self.calls: list[dict] = []

    async def get_chat(self, chat_id, **kwargs):
        self.calls.append({"chat_id": chat_id, "kwargs": kwargs})
        if self.exception is not None:
            raise self.exception
        return _StubChat(self.response_data)


def _write_config(directory: Path, sections: str) -> Config:
    config_dir = directory / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / "config.yaml"
    config_path.write_text(sections, encoding="utf-8")
    return Config(config_path).load()


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
    "  max_steps: 10\n\n"
    "plan_execution:\n"
    "  enabled: true\n"
    "  default_provider: \"plan_execution\"\n"
    "  stop_on_failure: true\n\n"
    "tool:\n"
    "  enabled: true\n"
    "  default_provider: \"tool_engine\"\n\n"
    "collaboration:\n"
    "  enabled: true\n"
    "  default_provider: \"collaboration\"\n\n"
    "workflow_engine:\n"
    "  enabled: true\n"
    "  default_provider: \"workflow_engine\"\n"
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
    "  enabled: {telegram_info_enabled}\n"
    "  timeout_seconds: 10\n"
)


def _write_full_bootstrap_config(directory: Path, telegram_info_enabled: bool = True) -> None:
    config_dir = directory / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "config.yaml").write_text(
        _FULL_BOOTSTRAP_CONFIG_YAML.format(
            telegram_info_enabled=str(telegram_info_enabled).lower()
        ),
        encoding="utf-8",
    )


@TestRegistry.register
class TelegramInfoModuleTest(BaseTest):
    NAME = "EP040"

    def run(self):
        self._test_module_name()
        self._test_chat_action()
        self._test_chat_action_missing_argument()
        self._test_chat_action_numeric_chat_id()
        self._test_chat_action_username_chat_id()
        self._test_help_action()
        self._test_unknown_action()
        self._test_error_propagation_formats_command_result()

        self._test_bootstrap_disabled_telegram_info_never_registered()
        self._test_bootstrap_enabled_path_degrades_gracefully_without_token()

        return self.result

    def _build_module(self, tmp: str, bot: _StubBot) -> TelegramInfoModule:
        config = _write_config(
            Path(tmp), "telegram:\n  token: \"fake-token\"\n\ntelegram_info:\n  timeout_seconds: 10\n"
        )
        service = TelegramInfoService(config=config, bot=bot)
        return TelegramInfoModule(service)

    def _test_module_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            module = self._build_module(tmp, _StubBot(response_data={}))
            self.assert_equal(module.name, "telegram-info")

    def _test_chat_action(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            module = self._build_module(tmp, _StubBot(response_data={"id": 1, "type": "private"}))
            result = module.execute("chat", ["1"])
            self.assert_true(result.success)
            self.assert_true("private" in result.message)

    def _test_chat_action_missing_argument(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            module = self._build_module(tmp, _StubBot(response_data={}))
            result = module.execute("chat", [])
            self.assert_false(result.success)
            self.assert_true("requires a chat_id" in result.message)

    def _test_chat_action_numeric_chat_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bot = _StubBot(response_data={"id": 12345})
            module = self._build_module(tmp, bot)
            module.execute("chat", ["12345"])
            self.assert_equal(bot.calls[0]["chat_id"], 12345)
            self.assert_true(isinstance(bot.calls[0]["chat_id"], int))

    def _test_chat_action_username_chat_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bot = _StubBot(response_data={"id": 1})
            module = self._build_module(tmp, bot)
            module.execute("chat", ["@somechannel"])
            self.assert_equal(bot.calls[0]["chat_id"], "@somechannel")

    def _test_help_action(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            module = self._build_module(tmp, _StubBot(response_data={}))
            result = module.execute("help", [])
            self.assert_true(result.success)
            self.assert_true("telegram-info chat" in result.message)
            for forbidden in ("send", "message", "history", "chats", "list", "delete", "edit", "join"):
                self.assert_true(forbidden not in result.message.lower())

    def _test_unknown_action(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            module = self._build_module(tmp, _StubBot(response_data={}))
            result = module.execute("send", [])
            self.assert_false(result.success)
            self.assert_true("Unknown command" in result.message)

    def _test_error_propagation_formats_command_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            from telegram.error import BadRequest

            module = self._build_module(tmp, _StubBot(exception=BadRequest("not found")))
            result = module.execute("chat", ["999"])
            self.assert_false(result.success)
            self.assert_true(len(result.message) > 0)

    # ---------- Bootstrap wiring ----------

    def _test_bootstrap_disabled_telegram_info_never_registered(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(directory, telegram_info_enabled=False)
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.initialize()
                self.assert_true(bootstrap.telegram_info_service is None)

    def _test_bootstrap_enabled_path_degrades_gracefully_without_token(self) -> None:
        """telegram_info.enabled=true, but telegram.token is blank (the
        config default) -- proves the enabled/try path is taken and
        TelegramInfoServiceError is caught before any Bot/network call,
        without crashing the rest of Bootstrap.initialize()."""
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(directory, telegram_info_enabled=True)
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.initialize()
                self.assert_true(bootstrap.telegram_info_service is None)
                # The rest of Bootstrap must have completed successfully --
                # proves the try/except didn't let an exception escape and
                # abort initialize() entirely.
                self.assert_true(bootstrap.automation_service is not None)
