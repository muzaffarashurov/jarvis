"""GitHub module: CLI command surface for EP-039 GitHub Integration.

Exposes the "github" command namespace (repo, repos, issues, issue,
prs, pr, commits, commit, help) as thin CommandModule handlers,
following the same pattern as GitModule (EP-038). All GitHub-API
logic lives in GitHubService; this module only parses/validates CLI
arguments, calls GitHubService's existing public methods unchanged,
and formats CommandResult objects for the shell -- it never calls
`requests` itself and never reads GITHUB_TOKEN.

Catches `GitHubError` (the common base of every exception a running
operation call can raise) to format
`CommandResult(success=False, message=str(exc))`, never letting a raw
exception reach the shell, matching every other module's pattern.
`GitHubServiceError` is not caught here because it can only ever be
raised during Bootstrap construction of GitHubService, never from a
running CLI call -- if construction fails, Bootstrap never registers
this module at all (see src/bootstrap.py).

No "create", "comment", "merge", "close", "reopen", or any other
write/mutating command exists -- this subsystem is read-only by
design, matching the EP-039 design's explicit scope. GITHUB_TOKEN
never flows through this module at all (it is read directly from the
environment inside GitHubService), so there is no code path here that
could leak it into a CommandResult message.
"""

from __future__ import annotations

from typing import Callable

from src.core.command_router import CommandResult
from src.core.github.github_error import GitHubError
from src.services.github_service import GitHubService

HELP_TEXT: str = (
    "Available commands\n\n"
    "github repo <owner> <repo>\n"
    "github repos\n"
    "github issues <owner> <repo>\n"
    "github issue <owner> <repo> <number>\n"
    "github prs <owner> <repo>\n"
    "github pr <owner> <repo> <number>\n"
    "github commits <owner> <repo>\n"
    "github commit <owner> <repo> <sha>\n"
    "github help"
)

ActionHandler = Callable[[list[str]], CommandResult]


class GitHubModule:
    """Built-in "github" command namespace for EP-039 GitHub Integration."""

    def __init__(self, github_service: GitHubService) -> None:
        """Initialize the GitHubModule.

        Args:
            github_service: The service used to run read-only GitHub
                operations against the GitHub REST API.
        """
        self._service = github_service
        self._actions: dict[str, ActionHandler] = {
            "repo": self._repo,
            "repos": self._repos,
            "issues": self._issues,
            "issue": self._issue,
            "prs": self._prs,
            "pr": self._pr,
            "commits": self._commits,
            "commit": self._commit,
            "help": self._help,
        }

    @property
    def name(self) -> str:
        """Return this module's command namespace: "github"."""
        return "github"

    def execute(self, action: str, arguments: list[str]) -> CommandResult:
        """Execute a "github" action.

        Args:
            action: The requested action (e.g. "repo").
            arguments: Additional arguments (e.g. owner/repo/number/sha).

        Returns:
            A CommandResult describing the outcome.
        """
        handler = self._actions.get(action)
        if handler is None:
            command = f"{self.name} {action}".strip()
            message = f'Unknown command: {command}\nType "github help" for available commands.'
            return CommandResult(success=False, message=message)

        return handler(arguments)

    def _help(self, arguments: list[str]) -> CommandResult:
        """Return the list of available github commands."""
        return CommandResult(success=True, message=HELP_TEXT)

    def _repo(self, arguments: list[str]) -> CommandResult:
        """Handle "github repo <owner> <repo>"."""
        if len(arguments) < 2:
            return CommandResult(success=False, message="github repo requires <owner> <repo>.")
        try:
            result = self._service.get_repository(arguments[0], arguments[1])
        except GitHubError as exc:
            return CommandResult(success=False, message=str(exc))
        return CommandResult(success=True, message=str(result.data))

    def _repos(self, arguments: list[str]) -> CommandResult:
        """Handle "github repos"."""
        try:
            result = self._service.list_repositories()
        except GitHubError as exc:
            return CommandResult(success=False, message=str(exc))
        message = str(result.data) if result.data else "No repositories."
        return CommandResult(success=True, message=message)

    def _issues(self, arguments: list[str]) -> CommandResult:
        """Handle "github issues <owner> <repo>"."""
        if len(arguments) < 2:
            return CommandResult(success=False, message="github issues requires <owner> <repo>.")
        try:
            result = self._service.list_issues(arguments[0], arguments[1])
        except GitHubError as exc:
            return CommandResult(success=False, message=str(exc))
        message = str(result.data) if result.data else "No issues."
        return CommandResult(success=True, message=message)

    def _issue(self, arguments: list[str]) -> CommandResult:
        """Handle "github issue <owner> <repo> <number>"."""
        if len(arguments) < 3:
            return CommandResult(
                success=False, message="github issue requires <owner> <repo> <number>."
            )
        try:
            number = int(arguments[2])
        except ValueError:
            return CommandResult(
                success=False, message=f"Invalid number: {arguments[2]!r} is not an integer."
            )
        try:
            result = self._service.get_issue(arguments[0], arguments[1], number)
        except GitHubError as exc:
            return CommandResult(success=False, message=str(exc))
        return CommandResult(success=True, message=str(result.data))

    def _prs(self, arguments: list[str]) -> CommandResult:
        """Handle "github prs <owner> <repo>"."""
        if len(arguments) < 2:
            return CommandResult(success=False, message="github prs requires <owner> <repo>.")
        try:
            result = self._service.list_pull_requests(arguments[0], arguments[1])
        except GitHubError as exc:
            return CommandResult(success=False, message=str(exc))
        message = str(result.data) if result.data else "No pull requests."
        return CommandResult(success=True, message=message)

    def _pr(self, arguments: list[str]) -> CommandResult:
        """Handle "github pr <owner> <repo> <number>"."""
        if len(arguments) < 3:
            return CommandResult(
                success=False, message="github pr requires <owner> <repo> <number>."
            )
        try:
            number = int(arguments[2])
        except ValueError:
            return CommandResult(
                success=False, message=f"Invalid number: {arguments[2]!r} is not an integer."
            )
        try:
            result = self._service.get_pull_request(arguments[0], arguments[1], number)
        except GitHubError as exc:
            return CommandResult(success=False, message=str(exc))
        return CommandResult(success=True, message=str(result.data))

    def _commits(self, arguments: list[str]) -> CommandResult:
        """Handle "github commits <owner> <repo>"."""
        if len(arguments) < 2:
            return CommandResult(success=False, message="github commits requires <owner> <repo>.")
        try:
            result = self._service.list_commits(arguments[0], arguments[1])
        except GitHubError as exc:
            return CommandResult(success=False, message=str(exc))
        message = str(result.data) if result.data else "No commits."
        return CommandResult(success=True, message=message)

    def _commit(self, arguments: list[str]) -> CommandResult:
        """Handle "github commit <owner> <repo> <sha>"."""
        if len(arguments) < 3:
            return CommandResult(
                success=False, message="github commit requires <owner> <repo> <sha>."
            )
        try:
            result = self._service.get_commit(arguments[0], arguments[1], arguments[2])
        except GitHubError as exc:
            return CommandResult(success=False, message=str(exc))
        return CommandResult(success=True, message=str(result.data))
