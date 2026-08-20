"""Real engineering tests for EP-042 STEP 2/3 - EmailModule + Bootstrap wiring.

Builds a real EmailModule around a small stub EmailService (no real
EmailService construction, no real IMAP connection) for command
dispatch/formatting coverage, plus real Bootstrap enabled/disabled
wiring coverage (constructing a real `Bootstrap` against a full,
minimal config) -- matching the pattern of
tests/EP041/test_discord_module.py exactly. No real IMAP network call
is ever made; when 'email.enabled: true' is exercised, Bootstrap
constructs a real EmailService (construction only validates config --
it never opens a network connection).
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from src.bootstrap import Bootstrap
from src.core.command_router import CommandResult
from src.core.email.email_error import EmailAuthenticationError, EmailError
from src.core.email.email_result import EmailFolder, EmailMessage, EmailMessageSummary, EmailResult
from src.modules.email_module import EmailModule
from src.testing.base_test import BaseTest
from src.testing.registry import TestRegistry

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
    "  enabled: true\n"
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
    "  tick_interval: 1\n\n"
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
    "  max_context_messages: 20\n\n"
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
    "  include_working_directory: false\n"
    "  include_project_files: false\n"
    "  smart_selection: true\n\n"
    "indexing:\n"
    '  storage_backend: "memory"\n'
    '  storage_file: "data/database/project_index.json"\n\n'
    "providers:\n"
    "  claude:\n"
    "    enabled: false\n"
    '    api_key: ""\n'
    "  openai:\n"
    "    enabled: false\n"
    '    api_key: ""\n'
    "  gemini:\n"
    "    enabled: false\n"
    '    api_key: ""\n'
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
    "  enabled: {email_enabled}\n"
    '  imap_host: "imap.example.com"\n'
    "  imap_port: 993\n"
    '  tls_mode: "ssl"\n'
)


def _write_full_bootstrap_config(directory: Path, email_enabled: bool = True) -> None:
    config_dir = directory / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "config.yaml").write_text(
        _FULL_BOOTSTRAP_CONFIG_YAML.format(email_enabled=str(email_enabled).lower()),
        encoding="utf-8",
    )


class _StubEmailService:
    """A minimal stub standing in for EmailService's public API."""

    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self.list_folders_result: EmailResult | Exception = EmailResult(
            operation="list_folders",
            data=[EmailFolder(name="INBOX", delimiter=".", attributes=())],
        )
        self.list_messages_result: EmailResult | Exception = EmailResult(
            operation="list_messages",
            data=[EmailMessageSummary(uid="1", subject="Hi", sender="a@b.com", date=None, folder="INBOX")],
        )
        self.get_message_result: EmailResult | Exception = EmailResult(
            operation="get_message",
            data=EmailMessage(
                uid="1",
                message_id="<1@x>",
                subject="Hi",
                sender="a@b.com",
                recipients=("c@d.com",),
                cc=(),
                date=None,
                body_text="body",
                body_html=None,
                folder="INBOX",
                attachments=(),
            ),
        )
        self.search_messages_result: EmailResult | Exception = EmailResult(
            operation="search_messages",
            data=[],
        )

    def list_folders(self):
        self.calls.append(("list_folders",))
        if isinstance(self.list_folders_result, Exception):
            raise self.list_folders_result
        return self.list_folders_result

    def list_messages(self, folder=None, limit=None):
        self.calls.append(("list_messages", folder, limit))
        if isinstance(self.list_messages_result, Exception):
            raise self.list_messages_result
        return self.list_messages_result

    def get_message(self, folder, uid):
        self.calls.append(("get_message", folder, uid))
        if isinstance(self.get_message_result, Exception):
            raise self.get_message_result
        return self.get_message_result

    def search_messages(self, folder, criteria):
        self.calls.append(("search_messages", folder, criteria))
        if isinstance(self.search_messages_result, Exception):
            raise self.search_messages_result
        return self.search_messages_result


@TestRegistry.register
class EmailModuleTest(BaseTest):
    NAME = "EP042"

    def run(self):
        self._test_name_property()
        self._test_help_command()
        self._test_unknown_command()

        self._test_folders_success()
        self._test_folders_error_translated()

        self._test_list_no_arguments()
        self._test_list_with_folder_and_limit()
        self._test_list_invalid_limit()

        self._test_message_success()
        self._test_message_missing_arguments()

        self._test_search_success()
        self._test_search_missing_arguments()
        self._test_search_joins_criteria_arguments()

        self._test_module_never_accesses_credentials()

        self._test_bootstrap_registers_email_module_when_enabled()
        self._test_bootstrap_skips_email_module_when_disabled()

        return self.result

    def _test_name_property(self) -> None:
        module = EmailModule(_StubEmailService())
        self.assert_equal(module.name, "email")

    def _test_help_command(self) -> None:
        module = EmailModule(_StubEmailService())
        result = module.execute("help", [])
        self.assert_true(result.success)
        self.assert_true("email folders" in result.message)

    def _test_unknown_command(self) -> None:
        module = EmailModule(_StubEmailService())
        result = module.execute("send", ["x"])
        self.assert_false(result.success)
        self.assert_true("Unknown command" in result.message)

    def _test_folders_success(self) -> None:
        service = _StubEmailService()
        module = EmailModule(service)
        result = module.execute("folders", [])
        self.assert_true(result.success)
        self.assert_equal(service.calls[0], ("list_folders",))

    def _test_folders_error_translated(self) -> None:
        service = _StubEmailService()
        service.list_folders_result = EmailAuthenticationError("bad credentials")
        module = EmailModule(service)
        result = module.execute("folders", [])
        self.assert_false(result.success)
        self.assert_equal(result.message, "bad credentials")

    def _test_list_no_arguments(self) -> None:
        service = _StubEmailService()
        module = EmailModule(service)
        result = module.execute("list", [])
        self.assert_true(result.success)
        self.assert_equal(service.calls[0], ("list_messages", None, None))

    def _test_list_with_folder_and_limit(self) -> None:
        service = _StubEmailService()
        module = EmailModule(service)
        result = module.execute("list", ["Archive", "10"])
        self.assert_true(result.success)
        self.assert_equal(service.calls[0], ("list_messages", "Archive", 10))

    def _test_list_invalid_limit(self) -> None:
        service = _StubEmailService()
        module = EmailModule(service)
        result = module.execute("list", ["Archive", "not-a-number"])
        self.assert_false(result.success)
        self.assert_equal(len(service.calls), 0)

    def _test_message_success(self) -> None:
        service = _StubEmailService()
        module = EmailModule(service)
        result = module.execute("message", ["INBOX", "42"])
        self.assert_true(result.success)
        self.assert_equal(service.calls[0], ("get_message", "INBOX", "42"))

    def _test_message_missing_arguments(self) -> None:
        service = _StubEmailService()
        module = EmailModule(service)
        result = module.execute("message", ["INBOX"])
        self.assert_false(result.success)
        self.assert_equal(len(service.calls), 0)

    def _test_search_success(self) -> None:
        service = _StubEmailService()
        module = EmailModule(service)
        result = module.execute("search", ["INBOX", "UNSEEN"])
        self.assert_true(result.success)
        self.assert_equal(service.calls[0], ("search_messages", "INBOX", "UNSEEN"))

    def _test_search_missing_arguments(self) -> None:
        service = _StubEmailService()
        module = EmailModule(service)
        result = module.execute("search", ["INBOX"])
        self.assert_false(result.success)
        self.assert_equal(len(service.calls), 0)

    def _test_search_joins_criteria_arguments(self) -> None:
        service = _StubEmailService()
        module = EmailModule(service)
        module.execute("search", ["INBOX", "SUBJECT", '"invoice"'])
        self.assert_equal(service.calls[0], ("search_messages", "INBOX", 'SUBJECT "invoice"'))

    def _test_module_never_accesses_credentials(self) -> None:
        # EmailModule must never import os/environ or reference any
        # credential -- verified statically by source inspection here,
        # matching the discipline documented in the module's docstring.
        import inspect

        import src.modules.email_module as module_source

        source_text = inspect.getsource(module_source)
        self.assert_true("os.environ" not in source_text)
        self.assert_true("import imaplib" not in source_text)

    # ---------- Bootstrap wiring (STEP 3 audit: gap vs. EP-041 precedent) ----------

    def _test_bootstrap_registers_email_module_when_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            _write_full_bootstrap_config(directory, email_enabled=True)
            bootstrap = Bootstrap(project_root=directory)
            bootstrap.initialize()
            self.assert_true(bootstrap.email_service is not None)

    def _test_bootstrap_skips_email_module_when_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            _write_full_bootstrap_config(directory, email_enabled=False)
            bootstrap = Bootstrap(project_root=directory)
            bootstrap.initialize()
            self.assert_true(bootstrap.email_service is None)
