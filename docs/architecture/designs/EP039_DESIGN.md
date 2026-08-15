# EP039 — Design

Status: STEP 1 (Design / Investigation) -- not yet implemented.

Scope confirmed directly by the project owner (see conversation record); this
document designs against that confirmed scope rather than re-deriving it from
ambiguous repository evidence. Follows `EP038_DESIGN.md`'s structure and
terminology, since GitHub Integration is the direct architectural sibling of
Git Integration (EP-038), one phase later in Phase 6 (Integrations).

---

## Problem

Jarvis has no way to read information from GitHub -- repository metadata,
issues, pull requests, or commits. Before this EP, no GitHub-related
implementation existed anywhere in the codebase (confirmed by a
repository-wide search; the only hit was an incidental "github" mention in
an example-skill-category comment). Unlike EP-038's `git`, which operates on
a local working tree via subprocess, GitHub is a remote, authenticated web
service -- inspecting it requires an HTTP client, credential handling, and
translation of a much larger space of network/HTTP failure modes.

## Existing State

- No GitHub client, service, module, config, or test exists anywhere in the
  repository.
- `requests` is already a project dependency, already used for authenticated
  outbound HTTP calls with an established, reusable pattern:
  `src/core/ai/claude_provider.py`'s `ask()`/`_parse_response()` -- a
  `requests.post(..., timeout=...)` call wrapped in
  `except requests.exceptions.Timeout` /
  `except requests.exceptions.ConnectionError` /
  `except requests.exceptions.RequestException`, followed by explicit
  HTTP-status-code-to-domain-exception mapping (401/403 ->
  `ProviderAuthenticationError`, 429 -> `ProviderRateLimitError`, 5xx ->
  `ProviderUnavailableError`, other non-2xx -> `ProviderError`). This EP
  reuses that exact shape rather than inventing a new one.
- `providers.claude.api_key` is this project's only existing precedent for
  secret handling, and it stores the secret directly in `config.yaml`
  (plaintext). EP-039 deliberately does **not** follow that precedent --
  per confirmed scope, `GITHUB_TOKEN` must come from an environment
  variable, never from config. This is a new pattern for this codebase:
  a repository-wide search found no existing `os.environ`/`os.getenv` usage
  anywhere in `src/`, despite `python-dotenv` being listed in
  `requirements.txt` -- that dependency is currently unused by any file in
  the project (see Risks).
- EP-038's Core -> Service -> Module -> Bootstrap -> Config shape is the
  direct, freshly-established, and explicitly confirmed architectural
  template for this EP.

## Desired State

A new, independent `GitHubService` exposes eight read-only operations
(repository info, list repositories, list/get issue, list/get pull request,
list/get commit) against the GitHub REST API, authenticated via the
`GITHUB_TOKEN` environment variable, using the project's existing `requests`
dependency directly (no GitHub SDK). A `github` CLI namespace exposes the
same eight operations, following the `git`/`worker`/`autoflow` precedent. No
write, mutating, or destructive GitHub operation exists anywhere in this
subsystem.

## Scope

Included:
- Repository info (single repo) and list-repositories (authenticated user).
- List issues, get single issue.
- List pull requests, get single pull request.
- List commits, get single commit.
- `GITHUB_TOKEN` environment-variable authentication.
- `github` CLI namespace exposing exactly these eight operations.
- `github.enabled` / `github.api_base_url` / `github.timeout_seconds`
  configuration.
- Bootstrap wiring, following the EP-038 pattern exactly.
- Tool-Engine-readiness by construction (clean, minimal public API), with no
  EP-031 file touched.

## Non-goals

Explicitly out of scope for this EP (per confirmed scope) -- none of the
following exist anywhere in `GitHubService` or `GitHubModule`:
- Create, update, delete, comment on, close, or reopen an issue.
- Create, merge, close, or reopen a pull request.
- Create, update, or delete a repository.
- Any release, branch-creation/deletion, or GitHub Actions/workflow
  operation.
- Any other write or destructive GitHub API call.
- Pagination beyond the first page GitHub's API returns by default (an
  explicit, acknowledged limitation of the initial read-only scope, not an
  oversight -- see Risks).
- Org-scoped or arbitrary-user-scoped repository listing (`list_repositories`
  covers the authenticated user's own repositories only -- see Components).

## Architecture

```
Core                    src/core/github/github_result.py, github_error.py
  |                      (pure data: GitHubResult, GitHubError hierarchy --
  |                       no HTTP call here, matching GitResult/GitError's
  |                       split in EP-038)
  v
Service                 src/services/github_service.py
  |                      (owns the one HTTP-invocation strategy; resolves
  |                       'github.*' config and GITHUB_TOKEN; the only
  |                       component that ever calls requests.get(...))
  v
Module                  src/modules/github_module.py
  |                      ("github" CLI namespace; thin CommandResult
  |                       translation layer only, exactly like GitModule)
  v
Bootstrap               src/bootstrap.py
  |                      (constructs GitHubService, registers GitHubModule,
  |                       gated by 'github.enabled', try/except around
  |                       config validation -- mirrors the EP-038 block)
  v
Config                  config/config.yaml ('github' section, no secret)
```

Like `GitService`, no Core-layer class holds business logic beyond two
small, dependency-free data types. There is no persistent resource, thread,
connection pool, or queue to own beyond an optionally-injected
`requests.Session` (see Components) -- each operation is a single,
synchronous, one-shot HTTP call.

**EventBus**: not used. A one-shot, synchronous, request/response GitHub
query has no completion-notification concept analogous to
`workflow.completed` -- identical reasoning to EP-038's own "Event
Integration: None" conclusion, for the same reason (no async dispatch, no
background thread, nothing for another component to react to).

**Tool Engine (EP-031)**: not modified. `Tool` (`src/core/tool/tool.py`)
already wraps an already-built subsystem service without requiring any
change to Tool Engine itself -- confirmed during EP-038's design and true
again here. `GitHubService`'s eight-method public API is a clean fit for
future `Tool` entries, exactly like `GitService`'s five.

## Components

### `src/core/github/github_result.py`

```python
@dataclass(frozen=True)
class GitHubResult:
    operation: str        # e.g. "get_issue", for logging/debugging
    status_code: int
    data: dict | list      # parsed JSON body -- dict for a single
                            # resource, list for a list endpoint
```

Mirrors `GitResult`'s "raw passthrough, no premature structure" philosophy:
`data` is the parsed JSON body as GitHub returns it, not a further-modeled
`Repository`/`Issue`/`PullRequest`/`Commit` type. No concrete consumer need
for deeper structure was identified, matching the same reasoning EP-038
applied to `GitResult.stdout`.

### `src/core/github/github_error.py`

```python
class GitHubError(Exception):
    """Base class for every GitHub Integration exception."""

class GitHubAuthenticationError(GitHubError):
    """GITHUB_TOKEN is missing, or the GitHub API rejected it (401/403
    where the response is not a rate limit)."""

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
    """GitHub returned any other non-2xx status not covered above."""
```

A flat hierarchy per this project's existing per-subsystem convention,
directly modeled on `claude_provider.py`'s
`ProviderAuthenticationError`/`ProviderRateLimitError`/`ProviderTimeoutError`/
`ProviderNetworkError`/`ProviderUnavailableError`/`ProviderError` split, with
`GitHubNotFoundError` added since "resource does not exist" is a common,
meaningful, and expected outcome for `get_issue`/`get_pull_request`/
`get_commit` specifically (unlike EP-038, where "not found" and "not a
repository" are the same underlying condition).

**Deliberately, `GitHubAuthenticationError` covers both a missing
`GITHUB_TOKEN` and a real 401/403-not-rate-limited API response.** The
confirmed scope's own wording -- "a clear domain-level GitHub
authentication/configuration error" -- treats these as one concept; adding
a second, separate "missing token" exception type would not add real value
for a caller, who needs to do the same thing in both cases (tell the user
their GitHub credential setup is incomplete or wrong).

### `src/services/github_service.py`

```python
class GitHubServiceError(Exception):
    """Raised only for invalid 'github.*' configuration (bad
    timeout_seconds, bad api_base_url), at __init__ time. Never for a
    missing/invalid GITHUB_TOKEN -- see below."""

class GitHubService:
    def __init__(
        self,
        config: Config,
        session: "requests.Session | None" = None,
    ) -> None: ...

    def get_repository(self, owner: str, repo: str) -> GitHubResult: ...
    def list_repositories(self) -> GitHubResult: ...
    def list_issues(self, owner: str, repo: str) -> GitHubResult: ...
    def get_issue(self, owner: str, repo: str, number: int) -> GitHubResult: ...
    def list_pull_requests(self, owner: str, repo: str) -> GitHubResult: ...
    def get_pull_request(self, owner: str, repo: str, number: int) -> GitHubResult: ...
    def list_commits(self, owner: str, repo: str) -> GitHubResult: ...
    def get_commit(self, owner: str, repo: str, sha: str) -> GitHubResult: ...
```

Design notes:
- **`session` is an injectable, optional `requests.Session`-like object**,
  defaulting to a real `requests.Session()` when omitted. This is the
  mechanism that satisfies "tests MUST NOT depend on the user's real GitHub
  account... do not make real GitHub API calls" without adding any new
  third-party test/mocking dependency -- a test passes a small duck-typed
  stub object exposing `.get(url, headers=..., params=..., timeout=...)`
  and returning a fake response object (`.status_code`, `.json()`,
  `.headers`), the same "duck-typed stand-in" technique
  `tests/EP035/test_automation_engine.py`'s `_StubPlanExecutionEngine`
  already uses for `WorkflowEngine`'s dependency.
- **`GITHUB_TOKEN` is read from `os.environ` at call time, inside each
  operation method (via a shared `_require_token()` helper), not at
  `__init__`.** Construction never touches the environment and never fails
  due to a missing token -- only `git.repository_path`/`timeout_seconds`
  -analogous config validation happens at construction (`api_base_url`
  non-empty, `timeout_seconds` a positive number), raising
  `GitHubServiceError`. This matches the confirmed scope's own phrasing --
  "if the token is missing **when a GitHub operation is requested**" --
  and is deliberately more lenient than `GitService`'s fail-fast
  construction-time validation, since an environment variable can
  legitimately be exported/removed without restarting the process, unlike a
  repository path.
- **`list_repositories()` covers the authenticated user's own repositories
  only** (`GET /user/repos`), not an arbitrary owner/org. GitHub's API
  distinguishes "repos for the authenticated user" from "repos for a named
  user" from "repos for a named org" -- the confirmed scope says only "list
  repositories" with no further qualifier, and `GET /user/repos` is the
  only one of the three that requires no additional parameter, making it
  the least-ambiguous reading. Listing another owner's/org's repositories
  is a natural, low-risk future extension, not implemented here.
- No retry logic, no caching, no pagination handling (see Non-goals) --
  cohesive and minimal, matching `GitService`'s own restraint.

### `src/modules/github_module.py`

```python
class GitHubModule:
    def __init__(self, github_service: GitHubService) -> None: ...

    @property
    def name(self) -> str: return "github"

    def execute(self, action: str, arguments: list[str]) -> CommandResult: ...
```

Actions: `repo <owner> <repo>`, `repos`, `issues <owner> <repo>`,
`issue <owner> <repo> <number>`, `prs <owner> <repo>`,
`pr <owner> <repo> <number>`, `commits <owner> <repo>`,
`commit <owner> <repo> <sha>`, `help`. Pure translation layer, exactly like
`GitModule`: calls `GitHubService`'s public methods unchanged, parses/
validates CLI arguments (e.g. `<number>` must be an integer), and catches
`GitHubError` to format `CommandResult(success=False, message=str(exc))`.
**Never logs, prints, or includes `GITHUB_TOKEN` in any `CommandResult`
message** -- since the token never flows through `GitHubModule` at all (it
is read directly from the environment inside `GitHubService`), there is no
code path in this layer that could leak it.

## Public APIs

| Method | Parameters | GitHub endpoint | Raises |
|---|---|---|---|
| `get_repository(owner, repo)` | both required | `GET /repos/{owner}/{repo}` | `GitHubAuthenticationError`, `GitHubNotFoundError`, `GitHubRateLimitError`, `GitHubTimeoutError`, `GitHubNetworkError`, `GitHubAPIError` |
| `list_repositories()` | none | `GET /user/repos` | same set |
| `list_issues(owner, repo)` | both required | `GET /repos/{owner}/{repo}/issues` | same set |
| `get_issue(owner, repo, number)` | all required | `GET /repos/{owner}/{repo}/issues/{number}` | same set |
| `list_pull_requests(owner, repo)` | both required | `GET /repos/{owner}/{repo}/pulls` | same set |
| `get_pull_request(owner, repo, number)` | all required | `GET /repos/{owner}/{repo}/pulls/{number}` | same set |
| `list_commits(owner, repo)` | both required | `GET /repos/{owner}/{repo}/commits` | same set |
| `get_commit(owner, repo, sha)` | all required | `GET /repos/{owner}/{repo}/commits/{sha}` | same set |

Every method is a thin wrapper over one shared internal `_get(operation,
path, params=None)` helper (mirroring `GitService._run`'s "one component
owns the one real invocation" role), which builds the full URL from
`github.api_base_url` + `path`, attaches the `Authorization: token
<GITHUB_TOKEN>` header, and performs the actual `requests.get(...)` call.

## Configuration

New `github` section:

```yaml
github:
  enabled: true
  api_base_url: "https://api.github.com"
  timeout_seconds: 30
```

- `enabled` defaults to `true`, matching every other soft-toggle subsystem.
- `api_base_url` defaults to the real GitHub REST API root; overridable for
  GitHub Enterprise Server deployments (a real, common need for a REST
  client) without requiring a code change -- validated non-empty at
  construction.
- `timeout_seconds` defaults to `30` (per the confirmed scope's own
  example -- longer than `git.timeout_seconds`'s `10`, since a network
  round-trip to a remote API has materially different latency
  characteristics than a local subprocess call) -- validated as a positive
  number at construction, identical style to `git.timeout_seconds`.
- **`GITHUB_TOKEN` is never read from, written to, or validated against
  `config/config.yaml` anywhere in this design.** It exists only as an
  environment variable, read directly via `os.environ.get("GITHUB_TOKEN")`
  inside `GitHubService`.
- Disabled behavior: identical to EP-038 -- when `github.enabled` is
  `False`, Bootstrap never constructs `GitHubService` and never registers
  `GitHubModule`; `github <anything>` falls through to the router's
  existing "Unknown command" handling.

## CLI

Namespace: `github`

| Command | Arguments | Success | Error |
|---|---|---|---|
| `github repo` | `<owner> <repo>` | Repository JSON summary | `GitHubError` message, or "requires owner and repo" if omitted |
| `github repos` | none | List of the authenticated user's repositories | `GitHubError` message |
| `github issues` | `<owner> <repo>` | List of issues | `GitHubError` message, or "requires owner and repo" |
| `github issue` | `<owner> <repo> <number>` | Single issue detail | `GitHubError` message, or "requires owner, repo, and number" / "number must be an integer" |
| `github prs` | `<owner> <repo>` | List of pull requests | same shape as `issues` |
| `github pr` | `<owner> <repo> <number>` | Single pull request detail | same shape as `issue` |
| `github commits` | `<owner> <repo>` | List of commits | same shape as `issues` |
| `github commit` | `<owner> <repo> <sha>` | Single commit detail | `GitHubError` message, or "requires owner, repo, and sha" |
| `github help` | none | Static help text listing only the eight read-only commands above | n/a |

No `create`/`comment`/`merge`/`close`/`reopen` command exists anywhere in
`GitHubModule`'s action table -- not merely unadvertised in `help`, absent
from the dispatch dictionary entirely, matching EP-038's "genuinely
unreachable, not just unwired" standard.

## Authentication / Security

- `GITHUB_TOKEN` is read via `os.environ.get("GITHUB_TOKEN")` at the start
  of every `GitHubService` operation method, never cached on `self` beyond
  the duration of a single call, and never logged. If unset (or blank),
  `GitHubAuthenticationError` is raised immediately, before any HTTP call
  is attempted.
- The token is sent only as the `Authorization` request header on the
  single outbound `requests.get(...)` call; it never appears in a
  `CommandResult` message, a log line, an exception message, or test
  output -- every error message in this design is constructed from
  fixed text and/or the *response* (status code, GitHub's own error body),
  never from the token value itself.
- No write/mutating GitHub operation exists in this EP, so the Vision
  document's "irreversible actions require human confirmation" rule has no
  operation to apply to yet -- correctly deferred, not overlooked, exactly
  as the confirmed scope states.
- `api_base_url` is operator-configured (not user/CLI-supplied per call),
  so there is no per-request URL-injection surface from CLI arguments --
  `owner`/`repo`/`number`/`sha` are interpolated into a URL *path*, not
  used to construct the base URL itself. STEP 2 should URL-quote path
  segments (`urllib.parse.quote`) defensively, the network-request analog
  of `GitService.diff()`'s `--` argument separator.

## Error Handling

| Failure | Exception | CLI-visible message |
|---|---|---|
| `GITHUB_TOKEN` unset/blank | `GitHubAuthenticationError` | "GITHUB_TOKEN environment variable is not set." |
| HTTP 401, or 403 without a rate-limit signal | `GitHubAuthenticationError` | "GitHub rejected the configured token." |
| HTTP 404 | `GitHubNotFoundError` | "not found: &lt;owner&gt;/&lt;repo&gt;..." |
| HTTP 403 with `X-RateLimit-Remaining: 0`, or HTTP 429 | `GitHubRateLimitError` | "GitHub API rate limit exceeded." |
| `requests.exceptions.Timeout` | `GitHubTimeoutError` | "GitHub request timed out after Ns." |
| `requests.exceptions.ConnectionError` | `GitHubNetworkError` | "Could not reach the GitHub API." |
| Any other non-2xx | `GitHubAPIError` | "GitHub request failed (HTTP &lt;code&gt;)." |
| Invalid `github.*` configuration at construction | `GitHubServiceError` | (Bootstrap-level: subsystem disabled, logged) |

`GitHubModule` catches `GitHubError` (the common base of the first six) and
formats it as `CommandResult(success=False, message=str(exc))`, identical
to `GitModule`'s pattern. `GitHubServiceError` can only be raised during
Bootstrap construction, never from a running CLI call, mirroring
`GitServiceError`'s split exactly.

## Testing Strategy

New suite: `tests/EP039/test_github_service.py` +
`tests/EP039/test_github_module.py`, one shared `"EP039"` suite (matching
the EP-037/038 precedent of multiple files sharing one suite name).

**Isolation strategy**: no real GitHub API call is ever made. Every test
constructs `GitHubService` with a small, duck-typed **stub session object**
in place of a real `requests.Session` -- a plain Python object exposing a
`.get(url, headers=None, params=None, timeout=None)` method that returns a
scripted fake response object (`.status_code`, `.json()`, `.headers`),
matching exactly the technique `_StubPlanExecutionEngine`
(`tests/EP035/test_automation_engine.py`) already uses for a different
dependency. No `unittest.mock`, no new mocking/HTTP-recording library, no
network access, no dependency on any real or test GitHub account or token
required to run the suite. `GITHUB_TOKEN` is set to a fixed fake value
(e.g. `"fake-token-for-tests"`) via `monkeypatch`-free direct
`os.environ` manipulation scoped to each test (set before, restored after)
where a test needs a token to be present; a separate test explicitly
`del`s/unsets it to cover the missing-token path.

Planned assertions:
- Each of the eight operations, given a stub session returning a
  realistic-shaped 200 JSON body, returns a `GitHubResult` with the right
  `status_code`/`data`.
- Missing `GITHUB_TOKEN` -> `GitHubAuthenticationError`, and the stub
  session's `.get()` is never called (fail fast, no wasted network attempt).
- Stub response 401 -> `GitHubAuthenticationError`; 404 ->
  `GitHubNotFoundError`; 403 with `X-RateLimit-Remaining: 0` ->
  `GitHubRateLimitError`; 429 -> `GitHubRateLimitError`; 500 ->
  `GitHubAPIError`.
- Stub session raising `requests.exceptions.Timeout` ->
  `GitHubTimeoutError`; raising `requests.exceptions.ConnectionError` ->
  `GitHubNetworkError`.
- A malformed (non-JSON) response body is translated to `GitHubAPIError`
  rather than letting a raw `ValueError`/`JSONDecodeError` escape.
- Constructing `GitHubService` with an invalid `timeout_seconds` or an
  empty `api_base_url` raises `GitHubServiceError`.
- `GitHubModule`: each action dispatches to the right `GitHubService`
  method with the right arguments; missing/invalid arguments (`issue`
  with a non-integer number, `repo` with only one argument) return a
  CLI-level error, not a crash; an unknown action returns the same
  "Unknown command" shape `GitModule` uses.
- `github.enabled=False` -> Bootstrap never registers `GitHubModule`.
- A test asserting the token never appears in any exception message or
  `CommandResult.message` produced by this suite (a direct, explicit
  safety assertion, not just an implicit property).

Regression suites to still pass unchanged: `EP038`, `EP037`, `EP036`,
`EP036-STEP2`, `EP036-STEP3`, `EP035`, `EP034`, `EP033`, `EP001`.

## Bootstrap Wiring

Mirrors the EP-038 block exactly:

```python
if bool(config.get("github.enabled", True)):
    try:
        github_service = GitHubService(config=config)
        self._github_service = github_service
        router.register(GitHubModule(github_service))
    except GitHubServiceError as exc:
        logger.error(f"GitHub Service disabled: invalid 'github.*' configuration ({exc}).")
        self._github_service = None
else:
    logger.info("GitHub Service disabled ('github.enabled: false').")
    self._github_service = None
```

No cross-EP hard-dependency gate is needed -- like `GitService`,
`GitHubService` depends only on `Config` and (indirectly, at call time) the
process environment, not on any other EP's engine/service. A `github_service`
property is added to `Bootstrap`, mirroring `git_service` exactly.

## Tool Engine Integration Strategy

Identical reasoning to EP-038: `Tool` already wraps an already-built
subsystem service with zero required change to `src/core/tool/`.
`GitHubService`'s eight methods, each free of side effects beyond a single
outbound read, are individually clean candidates for future `Tool` entries.
No Tool Engine file is touched by this EP; registering `GitHubService`'s
operations as `Tool` entries is left for a future EP, exactly as EP-038 left
its own five operations unregistered.

## File-Level Implementation Plan for STEP 2

### Created
```
src/core/github/__init__.py
src/core/github/github_result.py
src/core/github/github_error.py
src/services/github_service.py
src/modules/github_module.py
tests/EP039/__init__.py
tests/EP039/test_github_service.py
tests/EP039/test_github_module.py
```

### Modified
```
src/bootstrap.py            (construct GitHubService, register GitHubModule, github_service property)
config/config.yaml           ('github' section: enabled, api_base_url, timeout_seconds -- no token)
src/modules/test_module.py   (register EP039 test suite)
```

### Explicitly protected / untouched
```
src/core/tool/                              (EP-031)
src/core/git/, src/services/git_service.py, src/modules/git_module.py  (EP-038)
src/core/background_workers/                (EP-036)
src/core/workflow_scheduler/                (EP-034)
src/core/automation_engine/                 (EP-035)
src/core/events.py                          (EP-037)
src/services/workflow_engine_service.py     (EP-033)
requirements.txt                            (no new dependency)
tests/EP033/, EP034/, EP035/, EP036/, EP037/, EP038/
```

## Risks

- **`python-dotenv` is listed in `requirements.txt` but is not imported
  anywhere in the codebase.** This design does not add a `load_dotenv()`
  call anywhere (out of the confirmed scope) -- `GITHUB_TOKEN` must
  therefore be present in the actual process environment Jarvis is started
  with (e.g. via shell export), not merely placed in a `.env` file, unless
  a future EP wires dotenv loading. Worth flagging to the project owner
  since it may not match the expectation implied by that dependency's
  presence.
- **GitHub API rate limiting**: the authenticated rate limit (5,000
  requests/hour as of GitHub's current published limits) is generous for
  interactive CLI use but is a real constraint a heavy automated caller
  (e.g. a future Tool Engine consumer) could hit; `GitHubRateLimitError`
  surfaces this clearly but this design does not implement backoff/retry,
  consistent with `GitService`'s own "no retry logic" restraint.
- **No pagination**: list operations return only GitHub's default first
  page. Acceptable for the initial read-only scope; a repository/org with
  many issues/PRs/commits would only see the most recent page. Deferred
  rather than solved, matching `GitResult`'s own "avoid unnecessary
  abstraction" precedent from EP-038.
- **Alternative considered**: PyGithub (or another GitHub SDK). Rejected
  per explicit scope constraint, and because `requests` already has a
  proven, reusable pattern in this codebase (`claude_provider.py`) that a
  new SDK would duplicate rather than complement.
- **Alternative considered**: storing the token in `config.yaml` like
  `providers.claude.api_key`. Rejected per explicit scope constraint,
  favoring the more common "secret via environment variable, non-secret
  settings via config" separation for a service whose credential grants
  broad account-level read access.
- **Compatibility risk**: none identified -- wholly new, additive
  subsystem with no existing caller anywhere in the codebase, and no
  dependency on any other EP's service, identical in this respect to
  EP-038.
