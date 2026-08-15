"""Real engineering tests for EP-039 STEP 2 - GitHubService.

Builds a real GitHubService with a small, duck-typed stub `session`
object standing in for `requests.Session` -- no real GitHub API call
is ever made anywhere in this suite. `GITHUB_TOKEN` is set/unset
directly via `os.environ` around each test that needs it, always
restored afterward, so this suite never depends on (or leaks into) the
real process environment beyond the duration of a single test.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import requests

from src.core.config import Config
from src.core.github.github_error import (
    GitHubAPIError,
    GitHubAuthenticationError,
    GitHubNetworkError,
    GitHubNotFoundError,
    GitHubRateLimitError,
    GitHubTimeoutError,
)
from src.services.github_service import GitHubService, GitHubServiceError
from src.testing.base_test import BaseTest
from src.testing.registry import TestRegistry

_TOKEN_ENV_VAR = "GITHUB_TOKEN"
_FAKE_TOKEN = "fake-token-for-tests-xyz123"


class _TokenGuard:
    """Context manager: set GITHUB_TOKEN for the duration of a `with`
    block (or unset it entirely if `value` is None), always restoring
    whatever was present before."""

    def __init__(self, value: str | None) -> None:
        self._value = value
        self._original: str | None = None
        self._was_set = False

    def __enter__(self) -> None:
        self._was_set = _TOKEN_ENV_VAR in os.environ
        self._original = os.environ.get(_TOKEN_ENV_VAR)
        if self._value is None:
            os.environ.pop(_TOKEN_ENV_VAR, None)
        else:
            os.environ[_TOKEN_ENV_VAR] = self._value

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        if self._was_set:
            os.environ[_TOKEN_ENV_VAR] = self._original
        else:
            os.environ.pop(_TOKEN_ENV_VAR, None)


class _StubResponse:
    """A minimal duck-typed stand-in for `requests.Response`."""

    def __init__(self, status_code: int, json_data=None, headers=None, invalid_json: bool = False):
        self.status_code = status_code
        self._json_data = json_data
        self.headers = headers or {}
        self._invalid_json = invalid_json

    def json(self):
        if self._invalid_json:
            raise ValueError("Expecting value: line 1 column 1 (char 0)")
        return self._json_data


class _StubSession:
    """A minimal duck-typed stand-in for `requests.Session`.

    Returns a scripted `_StubResponse` (or raises a scripted
    exception) on every `.get()` call, and records every call made so
    tests can assert a call did/did not happen and inspect its
    headers/timeout.
    """

    def __init__(self, response: _StubResponse | None = None, exception: Exception | None = None):
        self.response = response
        self.exception = exception
        self.calls: list[dict] = []

    def get(self, url, headers=None, params=None, timeout=None):
        self.calls.append({"url": url, "headers": headers, "timeout": timeout})
        if self.exception is not None:
            raise self.exception
        return self.response


def _write_config(directory: Path, sections: str) -> Config:
    config_dir = directory / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / "config.yaml"
    config_path.write_text(sections, encoding="utf-8")
    return Config(config_path).load()


def _default_config(tmp: str) -> Config:
    return _write_config(
        Path(tmp),
        "github:\n  api_base_url: \"https://api.github.com\"\n  timeout_seconds: 30\n",
    )


@TestRegistry.register
class GitHubServiceTest(BaseTest):
    NAME = "EP039"

    def run(self):
        self._test_get_repository_success()
        self._test_list_repositories_success()
        self._test_list_issues_success()
        self._test_get_issue_success()
        self._test_list_pull_requests_success()
        self._test_get_pull_request_success()
        self._test_list_commits_success()
        self._test_get_commit_success()

        self._test_missing_token_raises_and_never_calls_session()
        self._test_blank_token_raises()
        self._test_401_raises_authentication_error()
        self._test_403_with_rate_limit_header_raises_rate_limit_error()
        self._test_403_without_rate_limit_header_raises_authentication_error()
        self._test_404_raises_not_found_error()
        self._test_429_raises_rate_limit_error()
        self._test_500_raises_api_error()
        self._test_timeout_raises_timeout_error()
        self._test_connection_error_raises_network_error()
        self._test_other_request_exception_raises_network_error()
        self._test_malformed_json_raises_api_error()

        self._test_construction_rejects_invalid_timeout()
        self._test_construction_rejects_empty_api_base_url()
        self._test_construction_defaults_applied()

        self._test_token_never_leaks_into_exception_messages()
        self._test_authorization_header_sent_correctly()
        self._test_path_segments_are_url_quoted()

        return self.result

    # ---------- Successful operations ----------

    def _test_get_repository_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _default_config(tmp)
            session = _StubSession(response=_StubResponse(200, {"full_name": "octocat/hello"}))
            service = GitHubService(config=config, session=session)
            with _TokenGuard(_FAKE_TOKEN):
                result = service.get_repository("octocat", "hello")
            self.assert_equal(result.status_code, 200)
            self.assert_equal(result.data["full_name"], "octocat/hello")
            self.assert_equal(result.operation, "get_repository")

    def _test_list_repositories_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _default_config(tmp)
            session = _StubSession(response=_StubResponse(200, [{"name": "repo1"}, {"name": "repo2"}]))
            service = GitHubService(config=config, session=session)
            with _TokenGuard(_FAKE_TOKEN):
                result = service.list_repositories()
            self.assert_equal(len(result.data), 2)
            self.assert_equal(session.calls[0]["url"], "https://api.github.com/user/repos")

    def _test_list_issues_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _default_config(tmp)
            session = _StubSession(response=_StubResponse(200, [{"number": 1, "title": "bug"}]))
            service = GitHubService(config=config, session=session)
            with _TokenGuard(_FAKE_TOKEN):
                result = service.list_issues("octocat", "hello")
            self.assert_equal(result.data[0]["number"], 1)

    def _test_get_issue_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _default_config(tmp)
            session = _StubSession(response=_StubResponse(200, {"number": 42, "title": "feature"}))
            service = GitHubService(config=config, session=session)
            with _TokenGuard(_FAKE_TOKEN):
                result = service.get_issue("octocat", "hello", 42)
            self.assert_equal(result.data["number"], 42)
            self.assert_true(session.calls[0]["url"].endswith("/issues/42"))

    def _test_list_pull_requests_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _default_config(tmp)
            session = _StubSession(response=_StubResponse(200, [{"number": 7}]))
            service = GitHubService(config=config, session=session)
            with _TokenGuard(_FAKE_TOKEN):
                result = service.list_pull_requests("octocat", "hello")
            self.assert_equal(result.data[0]["number"], 7)
            self.assert_true(session.calls[0]["url"].endswith("/pulls"))

    def _test_get_pull_request_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _default_config(tmp)
            session = _StubSession(response=_StubResponse(200, {"number": 7, "merged": False}))
            service = GitHubService(config=config, session=session)
            with _TokenGuard(_FAKE_TOKEN):
                result = service.get_pull_request("octocat", "hello", 7)
            self.assert_equal(result.data["number"], 7)
            self.assert_true(session.calls[0]["url"].endswith("/pulls/7"))

    def _test_list_commits_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _default_config(tmp)
            session = _StubSession(response=_StubResponse(200, [{"sha": "abc123"}]))
            service = GitHubService(config=config, session=session)
            with _TokenGuard(_FAKE_TOKEN):
                result = service.list_commits("octocat", "hello")
            self.assert_equal(result.data[0]["sha"], "abc123")
            self.assert_true(session.calls[0]["url"].endswith("/commits"))

    def _test_get_commit_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _default_config(tmp)
            session = _StubSession(response=_StubResponse(200, {"sha": "abc123", "commit": {}}))
            service = GitHubService(config=config, session=session)
            with _TokenGuard(_FAKE_TOKEN):
                result = service.get_commit("octocat", "hello", "abc123")
            self.assert_equal(result.data["sha"], "abc123")
            self.assert_true(session.calls[0]["url"].endswith("/commits/abc123"))

    # ---------- Authentication ----------

    def _test_missing_token_raises_and_never_calls_session(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _default_config(tmp)
            session = _StubSession(response=_StubResponse(200, {}))
            service = GitHubService(config=config, session=session)
            with _TokenGuard(None):
                try:
                    service.get_repository("octocat", "hello")
                    self.assert_true(False, "missing token should have raised")
                except GitHubAuthenticationError:
                    self.result.add_pass()
            self.assert_equal(len(session.calls), 0, "no HTTP call should be attempted without a token")

    def _test_blank_token_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _default_config(tmp)
            session = _StubSession(response=_StubResponse(200, {}))
            service = GitHubService(config=config, session=session)
            with _TokenGuard("   "):
                try:
                    service.get_repository("octocat", "hello")
                    self.assert_true(False, "blank token should have raised")
                except GitHubAuthenticationError:
                    self.result.add_pass()

    def _test_401_raises_authentication_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _default_config(tmp)
            session = _StubSession(response=_StubResponse(401, {"message": "Bad credentials"}))
            service = GitHubService(config=config, session=session)
            with _TokenGuard(_FAKE_TOKEN):
                try:
                    service.get_repository("octocat", "hello")
                    self.assert_true(False, "401 should have raised GitHubAuthenticationError")
                except GitHubAuthenticationError:
                    self.result.add_pass()

    # ---------- Rate limiting ----------

    def _test_403_with_rate_limit_header_raises_rate_limit_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _default_config(tmp)
            session = _StubSession(
                response=_StubResponse(403, {}, headers={"X-RateLimit-Remaining": "0"})
            )
            service = GitHubService(config=config, session=session)
            with _TokenGuard(_FAKE_TOKEN):
                try:
                    service.list_repositories()
                    self.assert_true(False, "403 with X-RateLimit-Remaining=0 should raise GitHubRateLimitError")
                except GitHubRateLimitError:
                    self.result.add_pass()

    def _test_403_without_rate_limit_header_raises_authentication_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _default_config(tmp)
            session = _StubSession(response=_StubResponse(403, {"message": "Forbidden"}))
            service = GitHubService(config=config, session=session)
            with _TokenGuard(_FAKE_TOKEN):
                try:
                    service.list_repositories()
                    self.assert_true(False, "plain 403 should raise GitHubAuthenticationError")
                except GitHubAuthenticationError:
                    self.result.add_pass()

    def _test_429_raises_rate_limit_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _default_config(tmp)
            session = _StubSession(response=_StubResponse(429, {}))
            service = GitHubService(config=config, session=session)
            with _TokenGuard(_FAKE_TOKEN):
                try:
                    service.list_repositories()
                    self.assert_true(False, "429 should raise GitHubRateLimitError")
                except GitHubRateLimitError:
                    self.result.add_pass()

    # ---------- Not found / generic API errors ----------

    def _test_404_raises_not_found_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _default_config(tmp)
            session = _StubSession(response=_StubResponse(404, {"message": "Not Found"}))
            service = GitHubService(config=config, session=session)
            with _TokenGuard(_FAKE_TOKEN):
                try:
                    service.get_issue("octocat", "hello", 99999)
                    self.assert_true(False, "404 should raise GitHubNotFoundError")
                except GitHubNotFoundError:
                    self.result.add_pass()

    def _test_500_raises_api_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _default_config(tmp)
            session = _StubSession(response=_StubResponse(500, {}))
            service = GitHubService(config=config, session=session)
            with _TokenGuard(_FAKE_TOKEN):
                try:
                    service.list_repositories()
                    self.assert_true(False, "500 should raise GitHubAPIError")
                except GitHubAPIError:
                    self.result.add_pass()

    # ---------- Network / timeout ----------

    def _test_timeout_raises_timeout_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _default_config(tmp)
            session = _StubSession(exception=requests.exceptions.Timeout("timed out"))
            service = GitHubService(config=config, session=session)
            with _TokenGuard(_FAKE_TOKEN):
                try:
                    service.list_repositories()
                    self.assert_true(False, "a Timeout exception should raise GitHubTimeoutError")
                except GitHubTimeoutError:
                    self.result.add_pass()

    def _test_connection_error_raises_network_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _default_config(tmp)
            session = _StubSession(exception=requests.exceptions.ConnectionError("refused"))
            service = GitHubService(config=config, session=session)
            with _TokenGuard(_FAKE_TOKEN):
                try:
                    service.list_repositories()
                    self.assert_true(False, "a ConnectionError should raise GitHubNetworkError")
                except GitHubNetworkError:
                    self.result.add_pass()

    def _test_other_request_exception_raises_network_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _default_config(tmp)
            session = _StubSession(exception=requests.exceptions.RequestException("weird"))
            service = GitHubService(config=config, session=session)
            with _TokenGuard(_FAKE_TOKEN):
                try:
                    service.list_repositories()
                    self.assert_true(False, "a generic RequestException should raise GitHubNetworkError")
                except GitHubNetworkError:
                    self.result.add_pass()

    def _test_malformed_json_raises_api_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _default_config(tmp)
            session = _StubSession(response=_StubResponse(200, invalid_json=True))
            service = GitHubService(config=config, session=session)
            with _TokenGuard(_FAKE_TOKEN):
                try:
                    service.list_repositories()
                    self.assert_true(False, "malformed JSON should raise GitHubAPIError")
                except GitHubAPIError:
                    self.result.add_pass()

    # ---------- Construction / configuration ----------

    def _test_construction_rejects_invalid_timeout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _write_config(Path(tmp), "github:\n  timeout_seconds: -5\n")
            try:
                GitHubService(config=config, session=_StubSession())
                self.assert_true(False, "a negative timeout_seconds should have raised")
            except GitHubServiceError:
                self.result.add_pass()

            config2 = _write_config(Path(tmp) / "b", "github:\n  timeout_seconds: \"nope\"\n")
            try:
                GitHubService(config=config2, session=_StubSession())
                self.assert_true(False, "a non-numeric timeout_seconds should have raised")
            except GitHubServiceError:
                self.result.add_pass()

    def _test_construction_rejects_empty_api_base_url(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _write_config(Path(tmp), "github:\n  api_base_url: \"\"\n")
            try:
                GitHubService(config=config, session=_StubSession())
                self.assert_true(False, "an empty api_base_url should have raised")
            except GitHubServiceError:
                self.result.add_pass()

    def _test_construction_defaults_applied(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _write_config(Path(tmp), "app:\n  name: \"x\"\n")
            session = _StubSession(response=_StubResponse(200, {"ok": True}))
            service = GitHubService(config=config, session=session)
            with _TokenGuard(_FAKE_TOKEN):
                service.list_repositories()
            self.assert_equal(session.calls[0]["url"], "https://api.github.com/user/repos")
            self.assert_equal(session.calls[0]["timeout"], 30.0)

    # ---------- Security ----------

    def _test_token_never_leaks_into_exception_messages(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _default_config(tmp)

            scenarios = [
                (_StubSession(response=_StubResponse(401, {})), GitHubAuthenticationError),
                (_StubSession(response=_StubResponse(404, {})), GitHubNotFoundError),
                (_StubSession(response=_StubResponse(429, {})), GitHubRateLimitError),
                (_StubSession(response=_StubResponse(500, {})), GitHubAPIError),
                (_StubSession(exception=requests.exceptions.Timeout()), GitHubTimeoutError),
                (_StubSession(exception=requests.exceptions.ConnectionError()), GitHubNetworkError),
            ]
            for session, expected_exc in scenarios:
                service = GitHubService(config=config, session=session)
                with _TokenGuard(_FAKE_TOKEN):
                    try:
                        service.list_repositories()
                        self.assert_true(False, f"expected {expected_exc.__name__}")
                    except expected_exc as exc:
                        self.assert_true(
                            _FAKE_TOKEN not in str(exc),
                            f"token leaked into {expected_exc.__name__} message",
                        )

            # And the missing-token case itself must not somehow echo a
            # previously-set token value either.
            service = GitHubService(config=config, session=_StubSession(response=_StubResponse(200, {})))
            with _TokenGuard(None):
                try:
                    service.list_repositories()
                    self.assert_true(False, "missing token should have raised")
                except GitHubAuthenticationError as exc:
                    self.assert_true(_FAKE_TOKEN not in str(exc))

    def _test_authorization_header_sent_correctly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _default_config(tmp)
            session = _StubSession(response=_StubResponse(200, {}))
            service = GitHubService(config=config, session=session)
            with _TokenGuard(_FAKE_TOKEN):
                service.list_repositories()
            self.assert_equal(session.calls[0]["headers"]["Authorization"], f"token {_FAKE_TOKEN}")

    def _test_path_segments_are_url_quoted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _default_config(tmp)
            session = _StubSession(response=_StubResponse(200, {}))
            service = GitHubService(config=config, session=session)
            with _TokenGuard(_FAKE_TOKEN):
                service.get_repository("octo cat", "hello/world")
            url = session.calls[0]["url"]
            self.assert_true("octo%20cat" in url or "octo+cat" in url)
            self.assert_true("hello%2Fworld" in url)
