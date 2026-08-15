"""Real engineering tests for EP-039 STEP 2 - GitHubModule and Bootstrap wiring.

Covers CLI action dispatch/error-formatting against a real
GitHubService backed by a stub session (same technique as
test_github_service.py), plus real Bootstrap enabled/disabled wiring.
No real GitHub network call is ever made -- the Bootstrap-level tests
only verify wiring existence, since exercising a live call would
require real network access.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from src.bootstrap import Bootstrap
from src.core.config import Config
from src.services.github_service import GitHubService
from src.modules.github_module import GitHubModule
from src.testing.base_test import BaseTest
from src.testing.registry import TestRegistry

_TOKEN_ENV_VAR = "GITHUB_TOKEN"
_FAKE_TOKEN = "fake-token-for-tests-xyz123"


class _TokenGuard:
    """Context manager: set GITHUB_TOKEN for the duration of a `with`
    block, always restoring whatever was present before."""

    def __init__(self, value: str | None) -> None:
        self._value = value
        self._original: str | None = None
        self._was_set = False

    def __enter__(self) -> None:
        self._was_set = _TOKEN_ENV_VAR in os.environ
        self._original = os.environ.get(_TOKEN_ENV_VAR)
        if self._value is None:
            os.environ.pop(_TOKEN_ENV_VAR, None)
        else:
            os.environ[_TOKEN_ENV_VAR] = self._value

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        if self._was_set:
            os.environ[_TOKEN_ENV_VAR] = self._original
        else:
            os.environ.pop(_TOKEN_ENV_VAR, None)


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


class _StubResponse:
    def __init__(self, status_code: int, json_data=None, headers=None):
        self.status_code = status_code
        self._json_data = json_data
        self.headers = headers or {}

    def json(self):
        return self._json_data


class _StubSession:
    def __init__(self, response: _StubResponse | None = None):
        self.response = response
        self.calls: list[dict] = []

    def get(self, url, headers=None, params=None, timeout=None):
        self.calls.append({"url": url, "headers": headers, "timeout": timeout})
        return self.response


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
    "  enabled: {github_enabled}\n"
    "  api_base_url: \"https://api.github.com\"\n"
    "  timeout_seconds: 30\n"
)


def _write_full_bootstrap_config(directory: Path, github_enabled: bool = True) -> None:
    config_dir = directory / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "config.yaml").write_text(
        _FULL_BOOTSTRAP_CONFIG_YAML.format(github_enabled=str(github_enabled).lower()),
        encoding="utf-8",
    )


@TestRegistry.register
class GitHubModuleTest(BaseTest):
    NAME = "EP039"

    def run(self):
        self._test_module_name()
        self._test_repo_action()
        self._test_repo_action_missing_arguments()
        self._test_repos_action()
        self._test_issues_action()
        self._test_issue_action()
        self._test_issue_action_invalid_number()
        self._test_issue_action_missing_arguments()
        self._test_prs_action()
        self._test_pr_action()
        self._test_commits_action()
        self._test_commit_action()
        self._test_commit_action_missing_arguments()
        self._test_help_action()
        self._test_unknown_action()
        self._test_error_propagation_formats_command_result()

        self._test_bootstrap_registers_github_module_when_enabled()
        self._test_bootstrap_skips_github_module_when_disabled()

        return self.result

    def _build_module(self, tmp: str, response: _StubResponse) -> tuple[GitHubModule, _StubSession]:
        config = _write_config(Path(tmp), "github:\n  timeout_seconds: 30\n")
        session = _StubSession(response=response)
        service = GitHubService(config=config, session=session)
        return GitHubModule(service), session

    def _test_module_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            module, _ = self._build_module(tmp, _StubResponse(200, {}))
            self.assert_equal(module.name, "github")

    def _test_repo_action(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            module, _ = self._build_module(tmp, _StubResponse(200, {"full_name": "octocat/hello"}))
            with _TokenGuard(_FAKE_TOKEN):
                result = module.execute("repo", ["octocat", "hello"])
            self.assert_true(result.success)
            self.assert_true("octocat/hello" in result.message)

    def _test_repo_action_missing_arguments(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            module, _ = self._build_module(tmp, _StubResponse(200, {}))
            result = module.execute("repo", ["octocat"])
            self.assert_false(result.success)
            self.assert_true("requires" in result.message)

    def _test_repos_action(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            module, _ = self._build_module(tmp, _StubResponse(200, [{"name": "a"}]))
            with _TokenGuard(_FAKE_TOKEN):
                result = module.execute("repos", [])
            self.assert_true(result.success)

    def _test_issues_action(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            module, _ = self._build_module(tmp, _StubResponse(200, [{"number": 1}]))
            with _TokenGuard(_FAKE_TOKEN):
                result = module.execute("issues", ["octocat", "hello"])
            self.assert_true(result.success)

    def _test_issue_action(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            module, _ = self._build_module(tmp, _StubResponse(200, {"number": 42}))
            with _TokenGuard(_FAKE_TOKEN):
                result = module.execute("issue", ["octocat", "hello", "42"])
            self.assert_true(result.success)
            self.assert_true("42" in result.message)

    def _test_issue_action_invalid_number(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            module, _ = self._build_module(tmp, _StubResponse(200, {}))
            result = module.execute("issue", ["octocat", "hello", "not-a-number"])
            self.assert_false(result.success)
            self.assert_true("Invalid number" in result.message)

    def _test_issue_action_missing_arguments(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            module, _ = self._build_module(tmp, _StubResponse(200, {}))
            result = module.execute("issue", ["octocat", "hello"])
            self.assert_false(result.success)
            self.assert_true("requires" in result.message)

    def _test_prs_action(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            module, _ = self._build_module(tmp, _StubResponse(200, [{"number": 7}]))
            with _TokenGuard(_FAKE_TOKEN):
                result = module.execute("prs", ["octocat", "hello"])
            self.assert_true(result.success)

    def _test_pr_action(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            module, _ = self._build_module(tmp, _StubResponse(200, {"number": 7}))
            with _TokenGuard(_FAKE_TOKEN):
                result = module.execute("pr", ["octocat", "hello", "7"])
            self.assert_true(result.success)

    def _test_commits_action(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            module, _ = self._build_module(tmp, _StubResponse(200, [{"sha": "abc"}]))
            with _TokenGuard(_FAKE_TOKEN):
                result = module.execute("commits", ["octocat", "hello"])
            self.assert_true(result.success)

    def _test_commit_action(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            module, _ = self._build_module(tmp, _StubResponse(200, {"sha": "abc123"}))
            with _TokenGuard(_FAKE_TOKEN):
                result = module.execute("commit", ["octocat", "hello", "abc123"])
            self.assert_true(result.success)
            self.assert_true("abc123" in result.message)

    def _test_commit_action_missing_arguments(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            module, _ = self._build_module(tmp, _StubResponse(200, {}))
            result = module.execute("commit", ["octocat", "hello"])
            self.assert_false(result.success)
            self.assert_true("requires" in result.message)

    def _test_help_action(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            module, _ = self._build_module(tmp, _StubResponse(200, {}))
            result = module.execute("help", [])
            self.assert_true(result.success)
            self.assert_true("github repo" in result.message)
            self.assert_true("github commit" in result.message)
            # No write/mutating command should ever be advertised.
            for forbidden in ("create", "comment", "merge", "close", "reopen", "delete", "release"):
                self.assert_true(forbidden not in result.message.lower())

    def _test_unknown_action(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            module, _ = self._build_module(tmp, _StubResponse(200, {}))
            result = module.execute("merge", [])
            self.assert_false(result.success)
            self.assert_true("Unknown command" in result.message)

    def _test_error_propagation_formats_command_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            module, _ = self._build_module(tmp, _StubResponse(404, {"message": "Not Found"}))
            with _TokenGuard(_FAKE_TOKEN):
                result = module.execute("repo", ["octocat", "does-not-exist"])
            self.assert_false(result.success)
            self.assert_true(len(result.message) > 0)

    # ---------- Bootstrap wiring ----------

    def _test_bootstrap_registers_github_module_when_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(directory, github_enabled=True)
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.initialize()
                self.assert_true(bootstrap.github_service is not None)

    def _test_bootstrap_skips_github_module_when_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(directory, github_enabled=False)
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.initialize()
                self.assert_true(bootstrap.github_service is None)
