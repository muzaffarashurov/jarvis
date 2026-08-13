"""Git module: CLI command surface for EP-038 Git Integration.

Exposes the "git" command namespace (status, diff, log, branch, show,
help) as thin CommandModule handlers, following the same pattern as
BackgroundWorkerModule/AutomationModule/WorkflowSchedulerModule. All
git-invocation logic lives in GitService; this module only parses CLI
arguments, calls GitService's existing public methods unchanged, and
formats CommandResult objects for the shell -- it never calls
`subprocess` itself.

Catches `GitError` (the common base of `GitNotFoundError`,
`GitRepositoryError`, `GitCommandError`) to format
`CommandResult(success=False, message=str(exc))`, never letting a raw
exception reach the shell, matching every other module's pattern.
`GitServiceError` is not caught here because it can only ever be
raised during Bootstrap construction of GitService, never from a
running CLI call -- if construction fails, Bootstrap never registers
this module at all (see src/bootstrap.py).

No "commit", "push", "pull", or "clone" command exists -- this
subsystem is read-only by design, matching the EP-038 STEP 1 design's
explicit scope.
"""

from __future__ import annotations

from typing import Callable

from src.core.command_router import CommandResult
from src.core.git.git_error import GitError
from src.services.git_service import GitService

HELP_TEXT: str = (
    "Available commands\n\n"
    "git status\n"
    "git diff [path]\n"
    "git log [count]\n"
    "git branch\n"
    "git show <ref>\n"
    "git help"
)

ActionHandler = Callable[[list[str]], CommandResult]


class GitModule:
    """Built-in "git" command namespace for EP-038 Git Integration."""

    def __init__(self, git_service: GitService) -> None:
        """Initialize the GitModule.

        Args:
            git_service: The service used to run read-only git
                operations against the configured repository.
        """
        self._service = git_service
        self._actions: dict[str, ActionHandler] = {
            "status": self._status,
            "diff": self._diff,
            "log": self._log,
            "branch": self._branch,
            "show": self._show,
            "help": self._help,
        }

    @property
    def name(self) -> str:
        """Return this module's command namespace: "git"."""
        return "git"

    def execute(self, action: str, arguments: list[str]) -> CommandResult:
        """Execute a "git" action.

        Args:
            action: The requested action (e.g. "status").
            arguments: Additional arguments (e.g. a ref for "show").

        Returns:
            A CommandResult describing the outcome.
        """
        handler = self._actions.get(action)
        if handler is None:
            command = f"{self.name} {action}".strip()
            message = f'Unknown command: {command}\nType "git help" for available commands.'
            return CommandResult(success=False, message=message)

        return handler(arguments)

    def _help(self, arguments: list[str]) -> CommandResult:
        """Return the list of available git commands."""
        return CommandResult(success=True, message=HELP_TEXT)

    def _status(self, arguments: list[str]) -> CommandResult:
        """Handle "git status"."""
        try:
            result = self._service.status()
        except GitError as exc:
            return CommandResult(success=False, message=str(exc))
        message = result.stdout.strip() or "Working tree clean."
        return CommandResult(success=True, message=message)

    def _diff(self, arguments: list[str]) -> CommandResult:
        """Handle "git diff [path]"."""
        path = arguments[0] if arguments else None
        try:
            result = self._service.diff(path=path)
        except GitError as exc:
            return CommandResult(success=False, message=str(exc))
        message = result.stdout.strip() or "No differences."
        return CommandResult(success=True, message=message)

    def _log(self, arguments: list[str]) -> CommandResult:
        """Handle "git log [count]"."""
        max_count = None
        if arguments:
            try:
                max_count = int(arguments[0])
            except ValueError:
                return CommandResult(
                    success=False,
                    message=f"Invalid count: {arguments[0]!r} is not an integer.",
                )

        try:
            result = self._service.log(max_count) if max_count is not None else self._service.log()
        except GitError as exc:
            return CommandResult(success=False, message=str(exc))
        message = result.stdout.strip() or "No commits."
        return CommandResult(success=True, message=message)

    def _branch(self, arguments: list[str]) -> CommandResult:
        """Handle "git branch"."""
        try:
            result = self._service.branch()
        except GitError as exc:
            return CommandResult(success=False, message=str(exc))
        message = result.stdout.strip() or "No branches."
        return CommandResult(success=True, message=message)

    def _show(self, arguments: list[str]) -> CommandResult:
        """Handle "git show <ref>"."""
        if not arguments:
            return CommandResult(success=False, message="git show requires a ref.")
        try:
            result = self._service.show(arguments[0])
        except GitError as exc:
            return CommandResult(success=False, message=str(exc))
        return CommandResult(success=True, message=result.stdout.strip())
