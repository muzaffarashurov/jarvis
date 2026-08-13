"""GitError hierarchy for EP-038 Git Integration.

A small, flat domain-exception hierarchy per subsystem, matching this
project's existing convention (`BackgroundWorkerPoolError`,
`WorkflowEngineError`, ...). `GitServiceError` (raised only for invalid
'git.*' configuration, at `GitService.__init__` time) intentionally does
NOT subclass `GitError`: it can never occur from a CLI call, only from
Bootstrap construction, matching how `BackgroundWorkerServiceError` is
Bootstrap-only and distinct from the pool-level errors a running call
can raise. `GitService.__init__` raising `GitServiceError` is defined in
`src/services/git_service.py`, not here, since it concerns service-level
configuration validation rather than a `git` subprocess outcome.
"""

from __future__ import annotations

__all__ = [
    "GitError",
    "GitNotFoundError",
    "GitRepositoryError",
    "GitCommandError",
]


class GitError(Exception):
    """Base class for every Git Integration exception raised by a `git` call."""


class GitNotFoundError(GitError):
    """The 'git' executable could not be located/executed."""


class GitRepositoryError(GitError):
    """The configured path is not inside a git working tree."""


class GitCommandError(GitError):
    """git exited non-zero for a reason other than a bad repository.

    Also raised when the subprocess exceeds 'git.timeout_seconds'.
    """
