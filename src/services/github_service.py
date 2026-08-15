"""Business logic that wires EP-039 GitHub Integration into the application.

GitHubService is a thin, config-driven wrapper around the GitHub REST
API, exposing eight read-only operations as its entire public API. It
owns the one place `requests.get(...)` is ever called in this
subsystem -- exactly matching the "one component owns the one real
invocation" discipline `GitService` (EP-038) established for
`subprocess.run(["git", ...])`.

Like GitService, GitHubService has no dependency on any other
Engineering Package's service or engine -- it depends only on `Config`
and, at call time, the process environment (`GITHUB_TOKEN`). It owns
no thread, queue, or other persistent resource: each public method is
a single, synchronous, blocking HTTP call that has fully returned (or
raised) before the method returns.

Authentication: `GITHUB_TOKEN` is read from `os.environ` at the start
of every operation call (never at `__init__`, never cached on `self`
beyond the duration of a single call, never logged). If unset or
blank, `GitHubAuthenticationError` is raised immediately, before any
HTTP call is attempted. The token is sent only as the `Authorization`
request header; it never appears in a log line, an exception message,
or a `GitHubResult` -- every error message in this module is built
from fixed text and/or the HTTP response, never from the token value.

No create, update, delete, comment, merge, release, or any other
write/mutating GitHub operation is implemented or callable through
this service.
"""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import quote

import requests
from loguru import logger

from src.core.config import Config
from src.core.github.github_error import (
    GitHubAPIError,
    GitHubAuthenticationError,
    GitHubNetworkError,
    GitHubNotFoundError,
    GitHubRateLimitError,
    GitHubTimeoutError,
)
from src.core.github.github_result import GitHubResult

_DEFAULT_API_BASE_URL = "https://api.github.com"
_DEFAULT_TIMEOUT_SECONDS = 30.0
_TOKEN_ENV_VAR = "GITHUB_TOKEN"


class GitHubServiceError(Exception):
    """Raised for invalid 'github.*' configuration.

    Can only ever be raised from `GitHubService.__init__`, before any
    HTTP call is attempted -- never from a running `get_repository()`/
    `list_repositories()`/etc. call, which instead raise `GitHubError`
    subclasses (see `src.core.github.github_error`). Never raised for
    a missing/invalid `GITHUB_TOKEN` -- that is checked per-call
    instead (see module docstring) and raises
    `GitHubAuthenticationError`. This mirrors `GitServiceError`'s split
    from `GitError` in EP-038.
    """


class GitHubService:
    """Config-driven, read-only wrapper around the GitHub REST API."""

    def __init__(self, config: Config, session: "requests.Session | None" = None) -> None:
        """Initialize the GitHubService.

        Args:
            config: Loaded application configuration, used to resolve
                'github.api_base_url' and 'github.timeout_seconds'.
                Never used to resolve GITHUB_TOKEN -- that is read
                directly from the process environment at call time.
            session: Optional `requests.Session`-like object used to
                perform every HTTP call. Must expose a `.get(url,
                headers=None, params=None, timeout=None)` method
                returning an object with `.status_code`, `.json()`,
                and `.headers`. Defaults to a real `requests.Session()`
                when omitted; tests supply a small duck-typed stub
                instead, so no real GitHub API call is ever made by
                this project's own test suite.

        Raises:
            GitHubServiceError: If 'github.api_base_url' is configured
                but empty/blank, or if 'github.timeout_seconds' is
                configured but is not a positive number.
        """
        self._config = config
        self._api_base_url = self._resolve_api_base_url()
        self._timeout_seconds = self._resolve_timeout_seconds()
        self._session = session if session is not None else requests.Session()
        logger.info(
            f"GitHub Service initialized (api_base_url: {self._api_base_url}, "
            f"timeout: {self._timeout_seconds}s)."
        )

    # ---------- Public API ----------

    def get_repository(self, owner: str, repo: str) -> GitHubResult:
        """Return metadata for a single repository.

        Args:
            owner: The repository owner (user or organization login).
            repo: The repository name.

        Returns:
            A GitHubResult whose `data` is the repository's JSON
            object, exactly as GitHub returns it.

        Raises:
            GitHubAuthenticationError: If GITHUB_TOKEN is missing/blank,
                or GitHub rejects it.
            GitHubNotFoundError: If the repository does not exist, or
                the token cannot see it.
            GitHubRateLimitError: If GitHub's rate limit was exceeded.
            GitHubTimeoutError: If the call exceeds
                'github.timeout_seconds'.
            GitHubNetworkError: If a connection-level failure occurs.
            GitHubAPIError: If GitHub returns any other non-2xx status,
                or an unparseable response body.
        """
        path = f"/repos/{quote(owner)}/{quote(repo)}"
        return self._get("get_repository", path)

    def list_repositories(self) -> GitHubResult:
        """Return the authenticated user's own repositories.

        Not org-scoped and not scoped to an arbitrary named user --
        this covers only the repositories owned by (or otherwise
        associated with) whichever account GITHUB_TOKEN belongs to.
        Returns only GitHub's default first page of results -- no
        pagination is implemented.

        Returns:
            A GitHubResult whose `data` is a list of repository JSON
            objects.

        Raises:
            GitHubAuthenticationError: If GITHUB_TOKEN is missing/blank,
                or GitHub rejects it.
            GitHubRateLimitError: If GitHub's rate limit was exceeded.
            GitHubTimeoutError: If the call exceeds
                'github.timeout_seconds'.
            GitHubNetworkError: If a connection-level failure occurs.
            GitHubAPIError: If GitHub returns any other non-2xx status,
                or an unparseable response body.
        """
        return self._get("list_repositories", "/user/repos")

    def list_issues(self, owner: str, repo: str) -> GitHubResult:
        """Return the first page of a repository's issues.

        Args:
            owner: The repository owner (user or organization login).
            repo: The repository name.

        Returns:
            A GitHubResult whose `data` is a list of issue JSON
            objects (per GitHub's API, this list may include pull
            requests -- GitHub itself models a pull request as a kind
            of issue; this method does not filter them out).

        Raises:
            GitHubAuthenticationError: If GITHUB_TOKEN is missing/blank,
                or GitHub rejects it.
            GitHubNotFoundError: If the repository does not exist, or
                the token cannot see it.
            GitHubRateLimitError: If GitHub's rate limit was exceeded.
            GitHubTimeoutError: If the call exceeds
                'github.timeout_seconds'.
            GitHubNetworkError: If a connection-level failure occurs.
            GitHubAPIError: If GitHub returns any other non-2xx status,
                or an unparseable response body.
        """
        path = f"/repos/{quote(owner)}/{quote(repo)}/issues"
        return self._get("list_issues", path)

    def get_issue(self, owner: str, repo: str, number: int) -> GitHubResult:
        """Return a single issue's detail.

        Args:
            owner: The repository owner (user or organization login).
            repo: The repository name.
            number: The issue number.

        Returns:
            A GitHubResult whose `data` is the issue's JSON object.

        Raises:
            GitHubAuthenticationError: If GITHUB_TOKEN is missing/blank,
                or GitHub rejects it.
            GitHubNotFoundError: If the issue does not exist, or the
                token cannot see it.
            GitHubRateLimitError: If GitHub's rate limit was exceeded.
            GitHubTimeoutError: If the call exceeds
                'github.timeout_seconds'.
            GitHubNetworkError: If a connection-level failure occurs.
            GitHubAPIError: If GitHub returns any other non-2xx status,
                or an unparseable response body.
        """
        path = f"/repos/{quote(owner)}/{quote(repo)}/issues/{quote(str(number))}"
        return self._get("get_issue", path)

    def list_pull_requests(self, owner: str, repo: str) -> GitHubResult:
        """Return the first page of a repository's pull requests.

        Args:
            owner: The repository owner (user or organization login).
            repo: The repository name.

        Returns:
            A GitHubResult whose `data` is a list of pull request JSON
            objects.

        Raises:
            GitHubAuthenticationError: If GITHUB_TOKEN is missing/blank,
                or GitHub rejects it.
            GitHubNotFoundError: If the repository does not exist, or
                the token cannot see it.
            GitHubRateLimitError: If GitHub's rate limit was exceeded.
            GitHubTimeoutError: If the call exceeds
                'github.timeout_seconds'.
            GitHubNetworkError: If a connection-level failure occurs.
            GitHubAPIError: If GitHub returns any other non-2xx status,
                or an unparseable response body.
        """
        path = f"/repos/{quote(owner)}/{quote(repo)}/pulls"
        return self._get("list_pull_requests", path)

    def get_pull_request(self, owner: str, repo: str, number: int) -> GitHubResult:
        """Return a single pull request's detail.

        Args:
            owner: The repository owner (user or organization login).
            repo: The repository name.
            number: The pull request number.

        Returns:
            A GitHubResult whose `data` is the pull request's JSON
            object.

        Raises:
            GitHubAuthenticationError: If GITHUB_TOKEN is missing/blank,
                or GitHub rejects it.
            GitHubNotFoundError: If the pull request does not exist, or
                the token cannot see it.
            GitHubRateLimitError: If GitHub's rate limit was exceeded.
            GitHubTimeoutError: If the call exceeds
                'github.timeout_seconds'.
            GitHubNetworkError: If a connection-level failure occurs.
            GitHubAPIError: If GitHub returns any other non-2xx status,
                or an unparseable response body.
        """
        path = f"/repos/{quote(owner)}/{quote(repo)}/pulls/{quote(str(number))}"
        return self._get("get_pull_request", path)

    def list_commits(self, owner: str, repo: str) -> GitHubResult:
        """Return the first page of a repository's commits.

        Args:
            owner: The repository owner (user or organization login).
            repo: The repository name.

        Returns:
            A GitHubResult whose `data` is a list of commit JSON
            objects.

        Raises:
            GitHubAuthenticationError: If GITHUB_TOKEN is missing/blank,
                or GitHub rejects it.
            GitHubNotFoundError: If the repository does not exist, or
                the token cannot see it.
            GitHubRateLimitError: If GitHub's rate limit was exceeded.
            GitHubTimeoutError: If the call exceeds
                'github.timeout_seconds'.
            GitHubNetworkError: If a connection-level failure occurs.
            GitHubAPIError: If GitHub returns any other non-2xx status,
                or an unparseable response body.
        """
        path = f"/repos/{quote(owner)}/{quote(repo)}/commits"
        return self._get("list_commits", path)

    def get_commit(self, owner: str, repo: str, sha: str) -> GitHubResult:
        """Return a single commit's detail.

        Args:
            owner: The repository owner (user or organization login).
            repo: The repository name.
            sha: The commit SHA (full or abbreviated).

        Returns:
            A GitHubResult whose `data` is the commit's JSON object.

        Raises:
            GitHubAuthenticationError: If GITHUB_TOKEN is missing/blank,
                or GitHub rejects it.
            GitHubNotFoundError: If the commit does not exist, or the
                token cannot see it.
            GitHubRateLimitError: If GitHub's rate limit was exceeded.
            GitHubTimeoutError: If the call exceeds
                'github.timeout_seconds'.
            GitHubNetworkError: If a connection-level failure occurs.
            GitHubAPIError: If GitHub returns any other non-2xx status,
                or an unparseable response body.
        """
        path = f"/repos/{quote(owner)}/{quote(repo)}/commits/{quote(sha)}"
        return self._get("get_commit", path)

    # ---------- Internal helpers ----------

    def _require_token(self) -> str:
        """Return GITHUB_TOKEN from the environment, or raise.

        Returns:
            The non-blank token value.

        Raises:
            GitHubAuthenticationError: If GITHUB_TOKEN is unset or
                blank.
        """
        token = os.environ.get(_TOKEN_ENV_VAR)
        if not token or not token.strip():
            raise GitHubAuthenticationError(
                f"{_TOKEN_ENV_VAR} environment variable is not set."
            )
        return token

    def _get(self, operation: str, path: str) -> GitHubResult:
        """Perform one authenticated GET call against the GitHub API.

        The sole place `requests.get(...)` is ever called in this
        subsystem. GITHUB_TOKEN is resolved first (see
        `_require_token`), so a missing token never attempts an HTTP
        call at all.

        Args:
            operation: The public method name (e.g. "get_repository"),
                used for `GitHubResult.operation` and log messages
                only.
            path: The API path, beginning with "/", already safely
                constructed (owner/repo/number/sha segments already
                URL-quoted by the caller).

        Returns:
            A GitHubResult describing a successful (2xx) response.

        Raises:
            GitHubAuthenticationError: If GITHUB_TOKEN is missing/blank,
                or the response is HTTP 401, or HTTP 403 without a
                rate-limit signal.
            GitHubNotFoundError: If the response is HTTP 404.
            GitHubRateLimitError: If the response is HTTP 403 with
                `X-RateLimit-Remaining: 0`, or HTTP 429.
            GitHubTimeoutError: If the call exceeds
                `self._timeout_seconds`.
            GitHubNetworkError: If a connection-level failure occurs.
            GitHubAPIError: If the response is any other non-2xx
                status, or the response body is not valid JSON.
        """
        token = self._require_token()
        url = f"{self._api_base_url}{path}"
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github+json",
        }

        try:
            response = self._session.get(url, headers=headers, timeout=self._timeout_seconds)
        except requests.exceptions.Timeout as exc:
            logger.error(f"GitHub request timed out (operation='{operation}').")
            raise GitHubTimeoutError(
                f"GitHub request timed out after {self._timeout_seconds}s."
            ) from exc
        except requests.exceptions.ConnectionError as exc:
            logger.error(f"GitHub request network failure (operation='{operation}'): {exc}")
            raise GitHubNetworkError("Could not reach the GitHub API.") from exc
        except requests.exceptions.RequestException as exc:
            logger.error(f"GitHub request failed (operation='{operation}'): {exc}")
            raise GitHubNetworkError(str(exc)) from exc

        return self._parse_response(operation, response)

    def _parse_response(self, operation: str, response: Any) -> GitHubResult:
        """Translate a raw response object into a GitHubResult or error.

        Args:
            operation: The public method name, for `GitHubResult.operation`.
            response: The raw response object (a real
                `requests.Response`, or a test stub exposing the same
                `.status_code`/`.json()`/`.headers` shape).

        Returns:
            The parsed GitHubResult, on a 2xx status.

        Raises:
            GitHubAuthenticationError: On HTTP 401, or HTTP 403 without
                a rate-limit signal.
            GitHubNotFoundError: On HTTP 404.
            GitHubRateLimitError: On HTTP 403 with
                `X-RateLimit-Remaining: 0`, or HTTP 429.
            GitHubAPIError: On any other non-2xx status, or an
                unparseable response body.
        """
        status_code = response.status_code

        if status_code == 401:
            raise GitHubAuthenticationError("GitHub rejected the configured token.")

        if status_code == 403:
            if str(response.headers.get("X-RateLimit-Remaining", "")) == "0":
                raise GitHubRateLimitError("GitHub API rate limit exceeded.")
            raise GitHubAuthenticationError("GitHub rejected the configured token.")

        if status_code == 404:
            raise GitHubNotFoundError(f"GitHub resource not found (operation='{operation}').")

        if status_code == 429:
            raise GitHubRateLimitError("GitHub API rate limit exceeded.")

        if status_code < 200 or status_code >= 300:
            raise GitHubAPIError(f"GitHub request failed (HTTP {status_code}).")

        try:
            data = response.json()
        except ValueError as exc:
            raise GitHubAPIError("GitHub returned an invalid (non-JSON) response body.") from exc

        return GitHubResult(operation=operation, status_code=status_code, data=data)

    def _resolve_api_base_url(self) -> str:
        """Resolve and validate 'github.api_base_url'.

        Returns:
            The configured base URL (default `_DEFAULT_API_BASE_URL`),
            with any trailing slash stripped.

        Raises:
            GitHubServiceError: If the configured value is present but
                empty/blank.
        """
        value = self._config.get("github.api_base_url", _DEFAULT_API_BASE_URL)
        if not isinstance(value, str) or not value.strip():
            raise GitHubServiceError(
                f"Invalid value for 'github.api_base_url': expected a non-empty string, got {value!r}."
            )
        return value.rstrip("/")

    def _resolve_timeout_seconds(self) -> float:
        """Resolve and validate 'github.timeout_seconds'.

        Returns:
            The configured timeout in seconds (default
            `_DEFAULT_TIMEOUT_SECONDS`).

        Raises:
            GitHubServiceError: If the configured value is not a
                positive number.
        """
        value = self._config.get("github.timeout_seconds", _DEFAULT_TIMEOUT_SECONDS)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
            raise GitHubServiceError(
                f"Invalid value for 'github.timeout_seconds': expected a positive number, got {value!r}."
            )
        return float(value)
