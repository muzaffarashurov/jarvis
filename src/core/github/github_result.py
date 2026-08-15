"""GitHubResult domain model for EP-039 GitHub Integration.

Pure data describing the outcome of one GitHub REST API call -- no HTTP
call happens in this module, matching the pattern already used by
`GitResult` (`src/core/git/git_result.py`, EP-038): a small,
dependency-free data type owned by Core, with the one real invocation
(`requests.get(...)`) living exclusively in `GitHubService`
(`src/services/github_service.py`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

__all__ = ["GitHubResult"]


@dataclass(frozen=True)
class GitHubResult:
    """The outcome of one successful GitHub REST API call.

    Attributes:
        operation: The GitHubService method that produced this result
            (e.g. "get_issue"), for logging/debugging -- not the full
            request URL.
        status_code: The raw HTTP status code (always 2xx -- a non-2xx
            response is translated into a GitHubError subclass instead
            of a GitHubResult; see `src.core.github.github_error`).
        data: The parsed JSON response body, exactly as GitHub
            returned it -- a dict for a single-resource endpoint (e.g.
            `get_repository`), a list for a list endpoint (e.g.
            `list_issues`). No further structure/typing is imposed.
    """

    operation: str
    status_code: int
    data: Any
