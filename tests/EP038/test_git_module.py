"""Real engineering tests for EP-038 STEP 2 - GitModule and Bootstrap wiring.

Covers CLI action dispatch/error-formatting against a real GitService
(backed by a disposable repository, same fixture technique as
test_git_service.py), plus real Bootstrap enabled/disabled wiring --
never against this project's own `.git`.
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from src.bootstrap import Bootstrap
from src.core.config import Config
from src.services.git_service import GitService
from src.modules.git_module import GitModule
from src.testing.base_test import BaseTest
from src.testing.registry import TestRegistry


class _ChdirGuard:
    """Context manager: chdir into `directory`, always restoring the original cwd."""

    def __init__(self, directory: Path) -> None:
        self._directory = directory
        self._original = Path.cwd()

    def __enter__(self) -> Path:
        import os

        os.chdir(self._directory)
        return self._directory

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        import os

        os.chdir(self._original)


def _run_git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )


def _init_repo(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    _run_git(repo, "-c", "init.defaultBranch=main", "init")
    _run_git(repo, "config", "user.name", "EP038 Test")
    _run_git(repo, "config", "user.email", "ep038-test@example.invalid")


def _commit_file(repo: Path, name: str, content: str, message: str) -> None:
    (repo / name).write_text(content, encoding="utf-8")
    _run_git(repo, "add", name)
    _run_git(repo, "commit", "-m", message)


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
    "  enabled: {git_enabled}\n"
    "  repository_path: null\n"
    "  timeout_seconds: 10\n"
)


def _write_full_bootstrap_config(directory: Path, git_enabled: bool = True) -> None:
    config_dir = directory / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "config.yaml").write_text(
        _FULL_BOOTSTRAP_CONFIG_YAML.format(git_enabled=str(git_enabled).lower()),
        encoding="utf-8",
    )


@TestRegistry.register
class GitModuleTest(BaseTest):
    NAME = "EP038"

    def run(self):
        self._test_status_action()
        self._test_status_action_clean_repo_message()
        self._test_diff_action_with_path_argument()
        self._test_log_action_default_count()
        self._test_log_action_invalid_count_argument()
        self._test_branch_action()
        self._test_show_action_requires_ref()
        self._test_show_action_with_ref()
        self._test_show_action_invalid_ref_returns_error_result()
        self._test_help_action()
        self._test_unknown_action()
        self._test_module_name()

        self._test_bootstrap_registers_git_module_when_enabled()
        self._test_bootstrap_skips_git_module_when_disabled()

        return self.result

    def _build_module(self, tmp: str) -> tuple[GitModule, Path]:
        repo = Path(tmp) / "repo"
        _init_repo(repo)
        _commit_file(repo, "a.txt", "hello\n", "initial commit")
        config = _write_config(Path(tmp), "git:\n  timeout_seconds: 10\n")
        service = GitService(config=config, repository_path=repo)
        return GitModule(service), repo

    def _test_module_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            module, _ = self._build_module(tmp)
            self.assert_equal(module.name, "git")

    def _test_status_action(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            module, repo = self._build_module(tmp)
            (repo / "a.txt").write_text("changed\n", encoding="utf-8")
            result = module.execute("status", [])
            self.assert_true(result.success)
            self.assert_true("a.txt" in result.message)

    def _test_status_action_clean_repo_message(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            module, _ = self._build_module(tmp)
            result = module.execute("status", [])
            self.assert_true(result.success)
            self.assert_equal(result.message, "Working tree clean.")

    def _test_diff_action_with_path_argument(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            module, repo = self._build_module(tmp)
            (repo / "a.txt").write_text("changed\n", encoding="utf-8")
            result = module.execute("diff", ["a.txt"])
            self.assert_true(result.success)
            self.assert_true("changed" in result.message)

    def _test_log_action_default_count(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            module, _ = self._build_module(tmp)
            result = module.execute("log", [])
            self.assert_true(result.success)
            self.assert_true("initial commit" in result.message)

    def _test_log_action_invalid_count_argument(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            module, _ = self._build_module(tmp)
            result = module.execute("log", ["not-a-number"])
            self.assert_false(result.success)
            self.assert_true("Invalid count" in result.message)

    def _test_branch_action(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            module, _ = self._build_module(tmp)
            result = module.execute("branch", [])
            self.assert_true(result.success)
            self.assert_true("main" in result.message)

    def _test_show_action_requires_ref(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            module, _ = self._build_module(tmp)
            result = module.execute("show", [])
            self.assert_false(result.success)
            self.assert_true("requires a ref" in result.message)

    def _test_show_action_with_ref(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            module, _ = self._build_module(tmp)
            result = module.execute("show", ["HEAD"])
            self.assert_true(result.success)
            self.assert_true("initial commit" in result.message)

    def _test_show_action_invalid_ref_returns_error_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            module, _ = self._build_module(tmp)
            result = module.execute("show", ["no-such-ref"])
            self.assert_false(result.success)

    def _test_help_action(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            module, _ = self._build_module(tmp)
            result = module.execute("help", [])
            self.assert_true(result.success)
            self.assert_true("git status" in result.message)
            self.assert_true("git show" in result.message)
            # No destructive/remote command should ever be advertised.
            self.assert_true("commit" not in result.message.lower())
            self.assert_true("push" not in result.message.lower())
            self.assert_true("pull" not in result.message.lower())
            self.assert_true("clone" not in result.message.lower())

    def _test_unknown_action(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            module, _ = self._build_module(tmp)
            result = module.execute("push", [])
            self.assert_false(result.success)
            self.assert_true("Unknown command" in result.message)

    # ---------- Bootstrap wiring ----------

    def _test_bootstrap_registers_git_module_when_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _init_repo(directory)
            _commit_file(directory, "a.txt", "hello\n", "initial commit")
            _write_full_bootstrap_config(directory, git_enabled=True)
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.initialize()
                self.assert_true(bootstrap.git_service is not None)

                result = bootstrap.git_service.status()
                self.assert_true(result.success)

    def _test_bootstrap_skips_git_module_when_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _init_repo(directory)
            _commit_file(directory, "a.txt", "hello\n", "initial commit")
            _write_full_bootstrap_config(directory, git_enabled=False)
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.initialize()
                self.assert_true(bootstrap.git_service is None)
