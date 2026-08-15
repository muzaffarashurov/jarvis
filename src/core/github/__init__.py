"""EP-039 GitHub Integration -- read-only inspection of GitHub repositories.

Exposes eight read-only operations (repository info, list
repositories, list/get issue, list/get pull request, list/get commit)
against the GitHub REST API, using the project's existing `requests`
dependency directly -- no GitHub SDK. No create, update, delete,
comment, merge, release, or any other write/mutating operation is
implemented -- this package can only ever read from GitHub.

This package (`src/core/github/`) holds only pure, dependency-free
data types -- `GitHubResult` and the `GitHubError` hierarchy. The one
real `requests.get(...)` invocation point lives exclusively in
`GitHubService` (`src/services/github_service.py`), matching the "one
component owns the one real invocation" discipline `GitService`
(EP-038) already established for `subprocess.run(["git", ...])`.

This subsystem has no dependency on any other Engineering Package --
like EP-038, it depends only on `Config` and (at call time) the
process environment (`GITHUB_TOKEN`).

Public API:
    GitHubResult -- The outcome of one successful GitHub REST API call.
    GitHubError -- Base class for every exception an operation call can raise.
    GitHubAuthenticationError -- Missing/invalid GITHUB_TOKEN, or a
        non-rate-limited 401/403 from the API.
    GitHubNotFoundError -- The requested resource does not exist (HTTP 404).
    GitHubRateLimitError -- GitHub's rate limit was exceeded.
    GitHubTimeoutError -- The request exceeded 'github.timeout_seconds'.
    GitHubNetworkError -- A connection-level failure occurred.
    GitHubAPIError -- Any other non-2xx status, or an unparseable response body.
"""

from __future__ import annotations

from src.core.github.github_error import (
    GitHubAPIError,
    GitHubAuthenticationError,
    GitHubError,
    GitHubNetworkError,
    GitHubNotFoundError,
    GitHubRateLimitError,
    GitHubTimeoutError,
)
from src.core.github.github_result import GitHubResult

__all__ = [
    "GitHubResult",
    "GitHubError",
    "GitHubAuthenticationError",
    "GitHubNotFoundError",
    "GitHubRateLimitError",
    "GitHubTimeoutError",
    "GitHubNetworkError",
    "GitHubAPIError",
]
