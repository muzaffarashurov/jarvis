"""GitHubError hierarchy for EP-039 GitHub Integration.

A flat domain-exception hierarchy per subsystem, matching this
project's existing convention (`GitError` in EP-038, `ProviderError` in
the AI provider subsystem). Modeled directly on
`src/core/ai/claude_provider.py`'s
`ProviderAuthenticationError`/`ProviderRateLimitError`/`ProviderTimeoutError`/
`ProviderNetworkError`/`ProviderUnavailableError`/`ProviderError` split,
with `GitHubNotFoundError` added since "resource does not exist" is a
common, expected outcome for `get_issue`/`get_pull_request`/
`get_commit` specifically.

`GitHubServiceError` (raised only for invalid 'github.*' configuration,
at `GitHubService.__init__` time) intentionally does NOT subclass
`GitHubError`: it can never occur from a running operation call, only
from Bootstrap construction, matching how `GitServiceError` (EP-038) is
distinct from `GitError`. `GitHubServiceError` is defined in
`src/services/github_service.py`, not here, for the same reason.
"""

from __future__ import annotations

__all__ = [
    "GitHubError",
    "GitHubAuthenticationError",
    "GitHubNotFoundError",
    "GitHubRateLimitError",
    "GitHubTimeoutError",
    "GitHubNetworkError",
    "GitHubAPIError",
]


class GitHubError(Exception):
    """Base class for every GitHub Integration exception raised by an operation call."""


class GitHubAuthenticationError(GitHubError):
    """GITHUB_TOKEN is missing/blank, or the GitHub API rejected it
    (HTTP 401, or HTTP 403 that is not a rate-limit response)."""


class GitHubNotFoundError(GitHubError):
    """The requested repository/issue/pull request/commit does not
    exist, or the token cannot see it (HTTP 404)."""


class GitHubRateLimitError(GitHubError):
    """GitHub's rate limit was exceeded (HTTP 403 with
    X-RateLimit-Remaining: 0, or HTTP 429)."""


class GitHubTimeoutError(GitHubError):
    """The request exceeded 'github.timeout_seconds'."""


class GitHubNetworkError(GitHubError):
    """A connection-level failure occurred (DNS, TLS, refused, ...)."""


class GitHubAPIError(GitHubError):
    """GitHub returned any other non-2xx status not covered above, or
    an unparseable (non-JSON) response body."""
