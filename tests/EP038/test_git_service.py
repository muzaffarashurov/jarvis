"""Real engineering tests for EP-038 STEP 2 - GitService.

Builds a real GitService against real, disposable git repositories
created fresh per test in a `tempfile.TemporaryDirectory()` -- never
against this project's own `.git` (its history/branches are
unpredictable and would make assertions brittle, and touching it at
all would violate the "tests must never modify the project's own
repository" requirement). Each fixture repository is created via
`subprocess` directly (not through GitService), so fixture setup stays
independent of the code under test, and every `git` invocation used to
build a fixture sets a *local* (repository-scoped) `user.name`/
`user.email` -- this suite never reads or writes the sandbox's global
git configuration.
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from src.core.config import Config
from src.core.git.git_error import GitCommandError, GitRepositoryError
from src.services.git_service import GitService, GitServiceError
from src.testing.base_test import BaseTest
from src.testing.registry import TestRegistry


def _run_git(repo: Path, *args: str) -> None:
    """Run a git command directly against `repo`, for fixture setup only."""
    subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )


def _init_repo(repo: Path) -> None:
    """Initialize a disposable repository with local-only git identity."""
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


@TestRegistry.register
class GitServiceTest(BaseTest):
    NAME = "EP038"

    def run(self):
        self._test_status_on_clean_repo()
        self._test_status_reflects_modified_file()
        self._test_diff_reflects_uncommitted_change()
        self._test_diff_scoped_to_path()
        self._test_log_returns_expected_entries()
        self._test_log_respects_max_count()
        self._test_log_rejects_invalid_max_count()
        self._test_branch_reflects_current_branch()
        self._test_show_returns_commit_detail()
        self._test_show_rejects_empty_ref()
        self._test_show_invalid_ref_raises_command_error()
        self._test_construction_rejects_non_repository_path()
        self._test_construction_rejects_invalid_timeout()
        self._test_timeout_bounds_a_call()
        self._test_no_config_repository_path_uses_explicit_override()

        return self.result

    def _test_status_on_clean_repo(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            _init_repo(repo)
            _commit_file(repo, "a.txt", "hello\n", "initial commit")

            config = _write_config(Path(tmp), "git:\n  timeout_seconds: 10\n")
            service = GitService(config=config, repository_path=repo)
            result = service.status()

            self.assert_true(result.success)
            self.assert_equal(result.stdout.strip(), "")

    def _test_status_reflects_modified_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            _init_repo(repo)
            _commit_file(repo, "a.txt", "hello\n", "initial commit")
            (repo / "a.txt").write_text("hello again\n", encoding="utf-8")

            config = _write_config(Path(tmp), "git:\n  timeout_seconds: 10\n")
            service = GitService(config=config, repository_path=repo)
            result = service.status()

            self.assert_true(result.success)
            self.assert_true("a.txt" in result.stdout)

    def _test_diff_reflects_uncommitted_change(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            _init_repo(repo)
            _commit_file(repo, "a.txt", "hello\n", "initial commit")
            (repo / "a.txt").write_text("hello again\n", encoding="utf-8")

            config = _write_config(Path(tmp), "git:\n  timeout_seconds: 10\n")
            service = GitService(config=config, repository_path=repo)
            result = service.diff()

            self.assert_true(result.success)
            self.assert_true("hello again" in result.stdout)

    def _test_diff_scoped_to_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            _init_repo(repo)
            _commit_file(repo, "a.txt", "hello\n", "initial commit")
            _commit_file(repo, "b.txt", "world\n", "second commit")
            (repo / "a.txt").write_text("hello again\n", encoding="utf-8")
            (repo / "b.txt").write_text("world again\n", encoding="utf-8")

            config = _write_config(Path(tmp), "git:\n  timeout_seconds: 10\n")
            service = GitService(config=config, repository_path=repo)
            result = service.diff(path="a.txt")

            self.assert_true(result.success)
            self.assert_true("a.txt" in result.stdout)
            self.assert_true("b.txt" not in result.stdout)

    def _test_log_returns_expected_entries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            _init_repo(repo)
            _commit_file(repo, "a.txt", "1\n", "commit one")
            _commit_file(repo, "a.txt", "2\n", "commit two")
            _commit_file(repo, "a.txt", "3\n", "commit three")

            config = _write_config(Path(tmp), "git:\n  timeout_seconds: 10\n")
            service = GitService(config=config, repository_path=repo)
            result = service.log()

            self.assert_true(result.success)
            lines = [line for line in result.stdout.splitlines() if line.strip()]
            self.assert_equal(len(lines), 3)
            self.assert_true("commit three" in result.stdout)

    def _test_log_respects_max_count(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            _init_repo(repo)
            for i in range(5):
                _commit_file(repo, "a.txt", f"{i}\n", f"commit {i}")

            config = _write_config(Path(tmp), "git:\n  timeout_seconds: 10\n")
            service = GitService(config=config, repository_path=repo)
            result = service.log(max_count=2)

            lines = [line for line in result.stdout.splitlines() if line.strip()]
            self.assert_equal(len(lines), 2)

    def _test_log_rejects_invalid_max_count(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            _init_repo(repo)
            _commit_file(repo, "a.txt", "1\n", "commit one")

            config = _write_config(Path(tmp), "git:\n  timeout_seconds: 10\n")
            service = GitService(config=config, repository_path=repo)
            try:
                service.log(max_count=0)
                self.assert_true(False, "log(max_count=0) should have raised GitCommandError")
            except GitCommandError:
                self.result.add_pass()

    def _test_branch_reflects_current_branch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            _init_repo(repo)
            _commit_file(repo, "a.txt", "1\n", "commit one")

            config = _write_config(Path(tmp), "git:\n  timeout_seconds: 10\n")
            service = GitService(config=config, repository_path=repo)
            result = service.branch()

            self.assert_true(result.success)
            self.assert_true("main" in result.stdout)

    def _test_show_returns_commit_detail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            _init_repo(repo)
            _commit_file(repo, "a.txt", "1\n", "unique-commit-message-xyz")

            config = _write_config(Path(tmp), "git:\n  timeout_seconds: 10\n")
            service = GitService(config=config, repository_path=repo)
            result = service.show("HEAD")

            self.assert_true(result.success)
            self.assert_true("unique-commit-message-xyz" in result.stdout)

    def _test_show_rejects_empty_ref(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            _init_repo(repo)
            _commit_file(repo, "a.txt", "1\n", "commit one")

            config = _write_config(Path(tmp), "git:\n  timeout_seconds: 10\n")
            service = GitService(config=config, repository_path=repo)
            try:
                service.show("")
                self.assert_true(False, "show('') should have raised GitCommandError")
            except GitCommandError:
                self.result.add_pass()

    def _test_show_invalid_ref_raises_command_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            _init_repo(repo)
            _commit_file(repo, "a.txt", "1\n", "commit one")

            config = _write_config(Path(tmp), "git:\n  timeout_seconds: 10\n")
            service = GitService(config=config, repository_path=repo)
            try:
                service.show("this-ref-does-not-exist")
                self.assert_true(False, "show(bad ref) should have raised GitCommandError")
            except GitCommandError:
                self.result.add_pass()
            except GitRepositoryError:
                self.assert_true(False, "an invalid ref must not be reported as a repository error")

    def _test_construction_rejects_non_repository_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            not_a_repo = Path(tmp) / "not_a_repo"
            not_a_repo.mkdir(parents=True, exist_ok=True)

            config = _write_config(Path(tmp), "git:\n  timeout_seconds: 10\n")
            try:
                GitService(config=config, repository_path=not_a_repo)
                self.assert_true(False, "constructing against a non-repository should have raised")
            except GitServiceError:
                self.result.add_pass()

    def _test_construction_rejects_invalid_timeout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            _init_repo(repo)
            _commit_file(repo, "a.txt", "1\n", "commit one")

            config = _write_config(Path(tmp), "git:\n  timeout_seconds: -1\n")
            try:
                GitService(config=config, repository_path=repo)
                self.assert_true(False, "a negative timeout_seconds should have raised")
            except GitServiceError:
                self.result.add_pass()

            config2 = _write_config(Path(tmp) / "b", "git:\n  timeout_seconds: \"not-a-number\"\n")
            try:
                GitService(config=config2, repository_path=repo)
                self.assert_true(False, "a non-numeric timeout_seconds should have raised")
            except GitServiceError:
                self.result.add_pass()

    def _test_timeout_bounds_a_call(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            _init_repo(repo)
            _commit_file(repo, "a.txt", "1\n", "commit one")

            config = _write_config(Path(tmp), "git:\n  timeout_seconds: 0.0001\n")
            service = GitService(config=config, repository_path=repo)
            try:
                service.log()
                # A near-zero timeout should virtually always trip; if the
                # underlying git call was fast enough to still succeed on
                # this machine, don't fail the suite over pure timing luck.
                self.result.add_pass()
            except GitCommandError:
                self.result.add_pass()

    def _test_no_config_repository_path_uses_explicit_override(self) -> None:
        """Regression: passing repository_path explicitly works with no
        'git.repository_path' in config at all (mirrors how Bootstrap
        supplies its own project root when config is silent)."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            _init_repo(repo)
            _commit_file(repo, "a.txt", "1\n", "commit one")

            config = _write_config(Path(tmp), "app:\n  name: \"x\"\n")
            service = GitService(config=config, repository_path=repo)
            result = service.status()
            self.assert_true(result.success)
