"""Business logic that wires EP-038 Git Integration into the application.

GitService is a thin, config-driven wrapper around the system `git`
executable, exposing five read-only operations (`status`, `diff`,
`log`, `branch`, `show`) as its entire public API. It owns the one
place `subprocess.run(["git", ...])` is ever called in this subsystem
-- exactly matching the "one component owns the one real invocation"
discipline `BackgroundWorkerPool` (EP-036) established for
`WorkflowEngine.run()`.

Unlike every EP-033 through EP-036 service, GitService has no
dependency on any other Engineering Package's service or engine -- it
depends only on `Config` and the filesystem. It also owns no thread,
queue, or other persistent resource: each public method is a single,
synchronous, blocking `subprocess.run(...)` call that has fully
returned (or raised) before the method returns, so there is no
lifecycle to start or shut down (contrast with `BackgroundWorkerPool`,
which starts daemon threads at construction time and requires an
explicit `shutdown()`).

Windows-safety: every subprocess call passes `encoding="utf-8",
errors="replace"` explicitly -- never `text=True` alone, and never
relying on the platform's default code page for decoding.

No remote or destructive git operation (`push`, `pull`, `clone`,
`commit`, ...) is implemented or callable through this service.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from loguru import logger

from src.core.config import Config
from src.core.git.git_error import GitCommandError, GitNotFoundError, GitRepositoryError
from src.core.git.git_result import GitResult

_DEFAULT_TIMEOUT_SECONDS = 10.0
_DEFAULT_LOG_MAX_COUNT = 10


class GitServiceError(Exception):
    """Raised for invalid 'git.*' configuration.

    Can only ever be raised from `GitService.__init__`, before any
    subprocess call is attempted -- never from a running `status()`/
    `diff()`/`log()`/`branch()`/`show()` call, which instead raise
    `GitError` subclasses (see `src.core.git.git_error`). This mirrors
    `BackgroundWorkerServiceError`'s split from `BackgroundWorkerPoolError`.
    """


class GitService:
    """Config-driven, read-only wrapper around the system `git` executable."""

    def __init__(self, config: Config, repository_path: Path | None = None) -> None:
        """Initialize the GitService.

        Args:
            config: Loaded application configuration, used to resolve
                'git.repository_path' (if `repository_path` is not
                given explicitly) and 'git.timeout_seconds'.
            repository_path: Explicit repository path, overriding
                'git.repository_path' from config. Defaults to None,
                in which case 'git.repository_path' (or, if that is
                also absent/null, the caller-supplied fallback used by
                Bootstrap: its own project root) is used.

        Raises:
            GitServiceError: If the resolved repository path does not
                exist, is not a directory, or is not inside a git
                working tree (no `.git` found in it or any parent);
                or if 'git.timeout_seconds' is configured but is not a
                positive number.
        """
        self._config = config
        self._repository_path = self._resolve_repository_path(repository_path)
        self._timeout_seconds = self._resolve_timeout_seconds()
        logger.info(
            f"Git Service initialized for repository: {self._repository_path} "
            f"(timeout: {self._timeout_seconds}s)."
        )

    # ---------- Public API ----------

    def status(self) -> GitResult:
        """Return the working tree's status.

        Returns:
            A GitResult whose `stdout` is `git status --porcelain=v1`
            output (stable, script-parseable; empty string for a clean
            working tree).

        Raises:
            GitNotFoundError: If the `git` executable is not available.
            GitRepositoryError: If the repository path is not (or is
                no longer) a valid git working tree.
            GitCommandError: If `git` exits non-zero for any other
                reason, or the call exceeds 'git.timeout_seconds'.
        """
        return self._run("status", ["status", "--porcelain=v1"])

    def diff(self, path: str | None = None) -> GitResult:
        """Return the working tree's uncommitted diff.

        Args:
            path: Optional path to scope the diff to a single file or
                directory. None diffs the entire working tree.

        Returns:
            A GitResult whose `stdout` is unified diff text.

        Raises:
            GitNotFoundError: If the `git` executable is not available.
            GitRepositoryError: If the repository path is not (or is
                no longer) a valid git working tree.
            GitCommandError: If `git` exits non-zero (e.g. `path` does
                not exist), or the call exceeds 'git.timeout_seconds'.
        """
        args = ["diff"]
        if path:
            args.extend(["--", path])
        return self._run("diff", args)

    def log(self, max_count: int = _DEFAULT_LOG_MAX_COUNT) -> GitResult:
        """Return the commit log, most recent first.

        Args:
            max_count: Maximum number of commits to return. Must be a
                positive integer.

        Returns:
            A GitResult whose `stdout` is one line per commit
            (`git log --oneline`).

        Raises:
            GitNotFoundError: If the `git` executable is not available.
            GitRepositoryError: If the repository path is not (or is
                no longer) a valid git working tree.
            GitCommandError: If `max_count` is not a positive integer,
                if `git` exits non-zero for any other reason, or the
                call exceeds 'git.timeout_seconds'.
        """
        if isinstance(max_count, bool) or not isinstance(max_count, int) or max_count < 1:
            raise GitCommandError(
                f"Invalid max_count for 'git log': expected a positive integer, got {max_count!r}."
            )
        return self._run("log", ["log", f"-n{max_count}", "--oneline"])

    def branch(self) -> GitResult:
        """Return the list of local branches.

        Returns:
            A GitResult whose `stdout` is `git branch --list` output.

        Raises:
            GitNotFoundError: If the `git` executable is not available.
            GitRepositoryError: If the repository path is not (or is
                no longer) a valid git working tree.
            GitCommandError: If `git` exits non-zero for any other
                reason, or the call exceeds 'git.timeout_seconds'.
        """
        return self._run("branch", ["branch", "--list"])

    def show(self, ref: str) -> GitResult:
        """Return the details of a single commit/object.

        Args:
            ref: A commit-ish reference (e.g. a commit hash, branch
                name, or tag). Must be non-empty.

        Returns:
            A GitResult whose `stdout` is `git show <ref>` output.

        Raises:
            GitNotFoundError: If the `git` executable is not available.
            GitRepositoryError: If the repository path is not (or is
                no longer) a valid git working tree.
            GitCommandError: If `ref` is empty, `ref` does not resolve
                to a known object, or the call exceeds
                'git.timeout_seconds'.
        """
        if not ref or not ref.strip():
            raise GitCommandError("'git show' requires a non-empty ref.")
        return self._run("show", ["show", ref])

    # ---------- Internal helpers ----------

    def _run(self, command: str, args: list[str]) -> GitResult:
        """Run one `git` subprocess call and translate its outcome.

        The sole place `subprocess.run(["git", ...])` is ever called in
        this subsystem. Never holds any lock or shared mutable state --
        each call is fully self-contained.

        Args:
            command: The subcommand name (e.g. "status"), used for
                `GitResult.command` and log/error messages only.
            args: The full `git` argv, excluding the `git` executable
                name itself.

        Returns:
            A GitResult describing the outcome, if `git` ran and
            exited (whether zero or non-zero).

        Raises:
            GitNotFoundError: If the `git` executable could not be
                located/executed at all.
            GitRepositoryError: If `git` reports the configured path
                is not a git working tree.
            GitCommandError: If `git` exits non-zero for any other
                reason, or the call exceeds `self._timeout_seconds`.
        """
        try:
            completed = subprocess.run(
                ["git", *args],
                cwd=self._repository_path,
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=self._timeout_seconds,
            )
        except FileNotFoundError as exc:
            raise GitNotFoundError(
                "git is not installed or not on PATH."
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise GitCommandError(
                f"git {command} timed out after {self._timeout_seconds}s."
            ) from exc

        result = GitResult(
            command=command,
            success=completed.returncode == 0,
            stdout=completed.stdout or "",
            stderr=completed.stderr or "",
            exit_code=completed.returncode,
        )

        if result.success:
            return result

        if "not a git repository" in result.stderr.lower():
            raise GitRepositoryError(
                f"not a git repository: {self._repository_path}"
            )

        raise GitCommandError(result.stderr.strip() or f"git {command} failed (exit {result.exit_code}).")

    def _resolve_repository_path(self, repository_path: Path | None) -> Path:
        """Resolve and validate the repository path this service operates on.

        Args:
            repository_path: Explicit override, if given.

        Returns:
            The resolved, validated repository path.

        Raises:
            GitServiceError: If the resolved path does not exist, is
                not a directory, or contains no `.git` in itself or
                any parent directory.
        """
        if repository_path is not None:
            candidate = repository_path
        else:
            configured = self._config.get("git.repository_path", None)
            candidate = Path(configured) if configured else None

        if candidate is None:
            raise GitServiceError(
                "No repository path resolved: pass repository_path explicitly "
                "or set 'git.repository_path' (or its Bootstrap-supplied default)."
            )

        candidate = Path(candidate)
        if not candidate.exists() or not candidate.is_dir():
            raise GitServiceError(f"'git.repository_path' does not exist or is not a directory: {candidate}")

        if not self._find_git_dir(candidate):
            raise GitServiceError(f"'git.repository_path' is not inside a git working tree: {candidate}")

        return candidate

    @staticmethod
    def _find_git_dir(path: Path) -> bool:
        """Return True if `path` or any parent contains a `.git` entry."""
        current = path.resolve()
        for candidate in (current, *current.parents):
            if (candidate / ".git").exists():
                return True
        return False

    def _resolve_timeout_seconds(self) -> float:
        """Resolve and validate 'git.timeout_seconds'.

        Returns:
            The configured timeout in seconds (default
            `_DEFAULT_TIMEOUT_SECONDS`).

        Raises:
            GitServiceError: If the configured value is not a positive
                number.
        """
        value = self._config.get("git.timeout_seconds", _DEFAULT_TIMEOUT_SECONDS)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
            raise GitServiceError(
                f"Invalid value for 'git.timeout_seconds': expected a positive number, got {value!r}."
            )
        return float(value)
