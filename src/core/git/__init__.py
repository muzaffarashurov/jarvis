"""EP-038 Git Integration -- read-only inspection of a git working tree.

Exposes five read-only operations (`status`, `diff`, `log`, `branch`,
`show`) by shelling out to the system `git` executable via
`subprocess`, with no third-party git library dependency. No remote or
destructive operation (`push`, `pull`, `clone`, `commit`, ...) is
implemented -- this package can only ever read the repository it is
pointed at.

This package (`src/core/git/`) holds only pure, dependency-free data
types -- `GitResult` and the `GitError` hierarchy. The one real
`subprocess.run(["git", ...])` invocation point lives exclusively in
`GitService` (`src/services/git_service.py`), matching the "one
component owns the one real invocation" discipline `BackgroundWorkerPool`
(EP-036) already established for `WorkflowEngine.run()`.

This subsystem has no dependency on any other Engineering Package --
it is the first EP since EP-033 with zero cross-EP runtime dependency.

Public API:
    GitResult -- The outcome of one `git` subprocess invocation.
    GitError -- Base class for every exception a `git` call can raise.
    GitNotFoundError -- The 'git' executable could not be located/executed.
    GitRepositoryError -- The configured path is not a git working tree.
    GitCommandError -- git exited non-zero, or the call timed out.
"""

from __future__ import annotations

from src.core.git.git_error import (
    GitCommandError,
    GitError,
    GitNotFoundError,
    GitRepositoryError,
)
from src.core.git.git_result import GitResult

__all__ = [
    "GitResult",
    "GitError",
    "GitNotFoundError",
    "GitRepositoryError",
    "GitCommandError",
]
