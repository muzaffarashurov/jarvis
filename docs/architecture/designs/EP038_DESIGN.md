# EP038 — Design

Status: STEP 1 (Design / Investigation) -- not yet implemented.

Scope confirmed directly by the project owner (see conversation record); this
document designs against that confirmed scope rather than re-deriving it from
ambiguous repository evidence.

---

## Problem

Jarvis has no way to inspect the state of the git repository it is running
against or working on. `PROJECT_MANIFEST.md`'s own `DEFAULT_IGNORE_DIRECTORIES`
already special-cases `.git` (it is skipped, never read), and nothing in
`src/` shells out to the `git` CLI at all -- confirmed by a repository-wide
search finding zero git-related implementation. An agent, a workflow step, or
a future Tool Engine (EP-031) action has no way to ask "what changed",
"what's the current branch", "what does this commit look like", etc.

## Existing State

- No git-related service, module, config, or test exists anywhere in the
  repository.
- `docs/architecture/JARVIS_ARCHITECTURE_VISION.md` lists `Git` as one
  example entry in a flat list of "Tools" an agent might use, and separately
  states `Git push` is an irreversible action requiring human confirmation --
  a future constraint, not something this EP needs to implement (push is out
  of scope here).
- The project has no existing precedent for running a subprocess and
  capturing/parsing its output. Every current `subprocess.Popen(...)` call
  site (`ProcessExecutor`, `PythonExecutor`, `FileExecutor`) launches a
  detached, untracked-output process; none of them capture stdout. This EP
  introduces that capture-and-parse pattern for the first time in this
  codebase.
- `Tool` (`src/core/tool/tool.py`, EP-031) is already a generic
  "wrap an already-built subsystem service" abstraction -- registering a new
  subsystem as a `Tool` requires no change to Tool Engine itself, only a
  `Tool(...)` catalog entry built in Bootstrap with a handler closure bound
  to the new service. This confirms scope item 6 (Tool-Engine-ready without
  modifying EP-031) is achievable by construction, not something requiring a
  design decision.

## Desired State

A new, independent `GitService` exposes five read-only git operations
(`status`, `diff`, `log`, `branch`, `show`) against a configured repository
path, by shelling out to the system `git` executable via `subprocess`,
following this project's existing Windows-safety conventions (explicit
`encoding="utf-8"`, `errors="replace"`, never `text=True` without an
explicit encoding). A `git` CLI namespace exposes the same five operations
to the interactive shell, following the `worker`/`autoflow` precedent. No
remote or destructive operation (`push`, `pull`, `clone`, `commit`, ...) is
implemented.

## Architecture

```
Core                    src/core/git/git_result.py, git_error.py
  |                      (pure data: GitResult, GitError -- no subprocess
  |                       call here, matching Tool's own "pure data" split)
  v
Service                 src/services/git_service.py
  |                      (owns the one subprocess-invocation strategy;
  |                       resolves 'git.*' config; the only component that
  |                       ever calls subprocess.run(["git", ...]))
  v
Module                  src/modules/git_module.py
  |                      ("git" CLI namespace; thin CommandResult translation
  |                       layer only, exactly like BackgroundWorkerModule)
  v
Bootstrap               src/bootstrap.py
  |                      (constructs GitService, registers GitModule,
  |                       try/except around config validation)
  v
Config                  config/config.yaml ('git' section)
```

No Core-layer class holding business logic is needed beyond two small,
dependency-free data types (`GitResult`, `GitError`) -- there is no
multi-file "Pool"-style component here, because there is no persistent
resource, thread, or queue to own (unlike EP-036's `BackgroundWorkerPool`).
Each git operation is a single, synchronous, one-shot subprocess call with
no lifecycle of its own. This mirrors the project's own stated principle
("Only include layers that are actually relevant... do not add a layer
unless justified") -- a `GitPool`/`GitEngine` core class would be an empty
abstraction over a single subprocess call.

## Components

### `src/core/git/git_result.py`

```python
@dataclass(frozen=True)
class GitResult:
    command: str        # e.g. "status", for logging/debugging
    success: bool
    stdout: str          # decoded, errors="replace"
    stderr: str
    exit_code: int
```

### `src/core/git/git_error.py`

```python
class GitError(Exception):
    """Base class for every Git Integration exception."""

class GitNotFoundError(GitError):
    """The 'git' executable could not be located/executed."""

class GitRepositoryError(GitError):
    """The configured path is not inside a git working tree."""

class GitCommandError(GitError):
    """git exited non-zero for a reason other than a bad repository
    (e.g. an invalid ref passed to 'git show')."""
```

Matches the existing project convention of a small, flat domain-exception
hierarchy per subsystem (`BackgroundWorkerPoolError`,
`BackgroundWorkerServiceError`, `WorkflowEngineError`, ...).

### `src/services/git_service.py`

```python
class GitService:
    def __init__(self, config: Config, repository_path: Path | None = None) -> None: ...

    def status(self) -> GitResult: ...
    def diff(self, path: str | None = None) -> GitResult: ...
    def log(self, max_count: int = 10) -> GitResult: ...
    def branch(self) -> GitResult: ...
    def show(self, ref: str) -> GitResult: ...
```

Owns the one place `subprocess.run(["git", ...])` is ever called in this
subsystem, exactly matching the "one component owns the one real
invocation" discipline `BackgroundWorkerPool` established for
`WorkflowEngine.run()`. Every method:
- runs with `cwd=self._repository_path`;
- passes `encoding="utf-8", errors="replace"` explicitly (never
  `text=True` alone);
- applies a bounded `timeout` (config key `git.timeout_seconds`) so a
  hung `git` process (e.g. waiting on a credential prompt this EP never
  supplies, since no remote operation is in scope) cannot hang the
  calling thread indefinitely;
- translates a missing executable into `GitNotFoundError`, a non-git
  directory into `GitRepositoryError`, and any other non-zero exit into
  `GitCommandError` (carrying the `GitResult` for the caller to inspect),
  rather than letting a raw `subprocess.CalledProcessError`/`OSError`
  escape.

### `src/modules/git_module.py`

```python
class GitModule:
    def __init__(self, git_service: GitService) -> None: ...

    @property
    def name(self) -> str: return "git"

    def execute(self, action: str, arguments: list[str]) -> CommandResult: ...
```

Actions: `status`, `diff [path]`, `log [count]`, `branch`, `show <ref>`,
`help`. Pure translation layer, exactly like `BackgroundWorkerModule`:
calls `GitService`'s public methods unchanged and catches `GitError` (and
subclasses) to format `CommandResult(success=False, message=str(exc))`.

## File Changes

### Created (STEP 2)
```
src/core/git/__init__.py
src/core/git/git_result.py
src/core/git/git_error.py
src/services/git_service.py
src/modules/git_module.py
tests/EP038/__init__.py
tests/EP038/test_git_service.py
tests/EP038/test_git_module.py
```

### Modified (STEP 2)
```
src/bootstrap.py            (construct GitService, register GitModule)
config/config.yaml           ('git' section: enabled, repository_path, timeout_seconds)
src/modules/test_module.py   (register EP038 test suite)
```

### Explicitly protected / untouched
```
src/core/tool/                              (EP-031 -- no change needed, see Architecture)
src/core/background_workers/                (EP-036)
src/core/workflow_scheduler/                (EP-034)
src/core/automation_engine/                 (EP-035)
src/core/events.py                          (EP-037)
src/services/workflow_engine_service.py     (EP-033)
src/services/background_worker_service.py   (EP-036)
tests/EP033/, EP034/, EP035/, EP036/, EP037/
```

## Public APIs

| Method | Parameters | Returns | Raises |
|---|---|---|---|
| `GitService.status()` | none | `GitResult` (stdout = `git status --porcelain=v1` output) | `GitNotFoundError`, `GitRepositoryError` |
| `GitService.diff(path=None)` | optional path to scope the diff | `GitResult` | same, plus `GitCommandError` for a bad path |
| `GitService.log(max_count=10)` | max entries | `GitResult` (`git log -n <max_count> --oneline`) | same |
| `GitService.branch()` | none | `GitResult` (`git branch --list`) | same |
| `GitService.show(ref)` | a ref/commit-ish string | `GitResult` (`git show <ref>`) | same, plus `GitCommandError` for an unknown ref |

`--porcelain=v1` for `status` and `--oneline` for `log` are chosen for
stable, script-parseable output, consistent with returning raw `stdout` in
`GitResult` rather than a further-structured object -- STEP 2 should keep
parsing to a minimum unless a concrete consumer needs structured fields
(mirrors this project's general "don't build unused abstraction" bias, e.g.
EP-037's deferred `task_submitted`/`task_started` events).

## Configuration

New `git` section:

```yaml
git:
  enabled: true
  repository_path: null      # null -> defaults to Bootstrap's project root
  timeout_seconds: 10
```

- `enabled` defaults to `true`, matching every other soft-toggle subsystem
  (`workflow_engine.enabled`, ..., `background_workers.enabled`). An
  enabled `GitService` with no caller has zero observable effect (no
  thread, no background work -- unlike `BackgroundWorkerPool`, there is
  nothing to start).
- `repository_path` lets the configured repository differ from Jarvis's own
  project root (relevant since Jarvis may eventually inspect a *different*
  project's repository, matching `PROJECT_MANIFEST.md`'s general
  "Jarvis should automatically understand every software project" stance) --
  `null`/absent resolves to `Bootstrap._project_root`, mirroring how
  `plugins.plugin_directory` resolves relative to `PROJECT_ROOT`.
- `timeout_seconds` bounds every subprocess call (see Lifecycle/Error
  Handling) -- new to this subsystem since it is the first to actually
  capture subprocess output synchronously, but the same defensive instinct
  as `background_workers.shutdown_timeout`.
- Validation: `GitService.__init__` validates `repository_path` (if given)
  resolves to a directory containing `.git` (or is inside one), and that
  `timeout_seconds` is a positive number, raising `GitServiceError` (a
  fourth exception, config-specific like `BackgroundWorkerServiceError`)
  before ever attempting a subprocess call -- fail fast, matching every
  other subsystem's Bootstrap `try/except` gate.

## CLI / Module

Namespace: `git`

| Command | Arguments | Success | Error |
|---|---|---|---|
| `git status` | none | Porcelain status output | `GitError` message |
| `git diff` | `[path]` | Diff output | `GitError` message |
| `git log` | `[count]` (default 10) | One-line-per-commit log | `GitError` message, or "invalid count" for a non-integer argument |
| `git branch` | none | Branch list | `GitError` message |
| `git show` | `<ref>` (required) | Commit/object detail | `GitError` message, or "git show requires a ref" if omitted |
| `git help` | none | Static help text | n/a |

Disabled behavior: if `git.enabled` is `False` (or config validation
failed), Bootstrap never registers `GitModule` at all -- `git <anything>`
falls through to the router's existing "Unknown command" handling, exactly
matching how a disabled `BackgroundWorkerModule`/`AutomationModule` behaves
today (no module-specific "this subsystem is disabled" message is invented,
since no existing module does that either).

## Event Integration

None. No event is published or subscribed to. `EventBus`
(`src/core/events.py`, EP-037) is not touched or extended by this design --
a one-shot, synchronous, request/response git query has no
completion-notification concept analogous to `workflow.completed` or
`background_worker.task_completed`; there is no async dispatch, no
background thread, and therefore no "something finished, tell other
components" moment to publish. If a future EP wants git-triggered
automation (e.g. "on new commit, run X"), that would need a repository
*watcher*, which is explicitly out of this EP's scope (scope items 3-5:
read-only, on-demand operations only, no polling/watching implied).

## Lifecycle

- **Construction**: `GitService.__init__` validates config and resolves
  `repository_path`; no subprocess call happens at construction time
  (unlike `BackgroundWorkerPool`, which starts threads immediately).
- **Start**: none -- there is no persistent resource to start.
- **Normal operation**: each public method (`status`, `diff`, ...) is a
  single, blocking `subprocess.run(...)` call with `timeout=timeout_seconds`,
  on whichever thread the caller is on (the CLI's own thread for a `git`
  command; potentially a worker thread if a future Tool Engine entry calls
  it from there -- safe, since each call is self-contained and stateless,
  unlike `EventBus.publish()` there is no shared mutable state to guard
  with a lock).
- **Stop / shutdown**: none -- no thread, no queue, no `shutdown()` method
  needed. `subprocess.run(...)` (not `Popen`) already waits for the child
  process to exit or hit `timeout_seconds` before returning, so no
  process can ever outlive the call that spawned it.
- **Failure**: a `subprocess.TimeoutExpired` is caught and re-raised as
  `GitCommandError`; the child process is killed by `subprocess.run`'s own
  timeout handling (it terminates the process on timeout by default).
- **Process-exit behavior**: nothing to do -- no daemon thread, no
  in-flight background work of the kind AD-005 tracks for EP-036.

## Error Handling

| Failure | Exception | CLI-visible message |
|---|---|---|
| `git` executable not found (`FileNotFoundError` from `subprocess.run`) | `GitNotFoundError` | "git is not installed or not on PATH" |
| Configured/default path is not a git working tree (`git` exits with "not a git repository") | `GitRepositoryError` | "not a git repository: <path>" |
| Any other non-zero exit (bad ref, bad path, ...) | `GitCommandError` (carries the `GitResult`) | the captured `stderr`, trimmed |
| Subprocess exceeds `timeout_seconds` | `GitCommandError` | "git <op> timed out after Ns" |
| Invalid `git.*` configuration at construction | `GitServiceError` | (Bootstrap-level: subsystem disabled, logged, matching `BackgroundWorkerServiceError`'s handling) |

`GitModule` catches `GitError` (the common base of all but
`GitServiceError`, which can only ever be raised during Bootstrap
construction, never from a CLI call) and formats it as
`CommandResult(success=False, message=...)`, never letting a raw exception
reach the shell -- matching every other module's pattern.

## Test Strategy

New suite: `tests/EP038/test_git_service.py` + `tests/EP038/test_git_module.py`,
registered as `NAME = "EP038"` in `src/modules/test_module.py` (single
suite name, matching how EP-037's two files share one `"EP037"` suite).

Isolation strategy: **do not use this repository's own `.git`** as the
test fixture (its history/branches are unpredictable and would make
assertions brittle). Instead, each test creates a throwaway git
repository in a `tempfile.TemporaryDirectory()`, running `git init` and a
couple of real commits via `subprocess` directly in the test setup (not
through `GitService`, to keep fixture setup independent of the code under
test) -- this is a **project-level ownership** approach (a private,
disposable repo per test, never touching global state), directly
satisfying the "must not rely on scanning global `threading.enumerate()`
[or any other global state] if a more precise project-level ownership API
exists" instruction, adapted to this EP's non-threaded nature: precise
ownership here means each test owns its own private repository directory,
never inspects the real project repository or any shared global git
state.

Planned assertions:
- `status()` on a clean repo returns empty porcelain output, `success=True`.
- `status()` after modifying a tracked file reflects the change.
- `diff()` reflects an uncommitted change; `diff(path=...)` scopes correctly.
- `log()` returns the expected number of entries, respects `max_count`.
- `branch()` reflects the current/only branch.
- `show(ref)` returns the right commit; an invalid ref raises
  `GitCommandError`, not a raw `subprocess` exception.
- Constructing `GitService` against a non-repository directory raises
  `GitRepositoryError`.
- Constructing `GitService` with an invalid `timeout_seconds`
  (non-numeric/negative) raises `GitServiceError`.
- `timeout_seconds` actually bounds a call (simulate via a very small
  timeout against a real repo -- assert `GitCommandError`, not a hang).
- `GitModule`: each action dispatches to the right `GitService` method;
  `git show` with no argument returns a CLI-level error, not a crash;
  an unknown action returns `CommandResult(success=False, ...)` with the
  same "Unknown command" shape `BackgroundWorkerModule` uses.
- `git.enabled=False` -> Bootstrap never registers `GitModule` (a
  `git status` command falls through to "Unknown command").
- CLI/config enabled-disabled cases mirroring
  `_test_bootstrap_disabled_automation_never_fires`'s style from EP-037.

Regression suites to still pass unchanged: `EP033`, `EP034`, `EP035`,
`EP036`, `EP036-STEP2`, `EP036-STEP3`, `EP037`, `EP001`. None of them
touch git in any way, so no interaction is expected, but they remain the
standard regression set per this project's established validation
convention.

## Regression Safety

- **EP-033/034/035/036/037**: no file belonging to any of these EPs is
  modified by this design. `GitService` has no dependency on
  `WorkflowEngine`, `EventBus`, or any other prior EP's service --
  it is the first EP since EP-033 with *zero* cross-EP runtime
  dependency, which also means no "hard dependency" Bootstrap gate
  (`if X is not None`) is needed, unlike EP-034/035/036's pattern of
  depending on a live `WorkflowEngine`.
- **Compatibility risk**: none identified -- this is a wholly new,
  additive subsystem with no existing caller anywhere in the codebase.
- No earlier EP's public API changes.

## Risks

- **Windows `git` availability**: if `git` is not on `PATH`, every
  operation fails with `GitNotFoundError` -- acceptable (matches how a
  missing AI provider or missing `WorkflowEngine` degrades this project's
  other subsystems), but worth flagging: unlike Python itself, `git` is
  an external dependency this project doesn't currently require at all.
- **Large repository output**: `git log`/`git diff` on a large repository
  could return very large `stdout`. `GitResult.stdout` is returned as a
  plain string with no truncation in this design -- acceptable for the
  initial read-only scope (`log` already bounds itself via `max_count`;
  `diff`/`show` are left unbounded, deferring truncation to a future EP
  if this proves to be a real problem, rather than inventing a
  budget/truncation mechanism not requested in scope).
- **Alternative considered**: a Python git library (e.g. GitPython)
  instead of subprocess. Rejected per explicit scope constraint (no new
  third-party dependency) and because it would be the first non-`pip`-
  trivial dependency this subsystem needs, whereas `git` itself is
  already assumed present on any machine this project would inspect a
  repository on.
- **Alternative considered**: structured (parsed) results instead of raw
  `stdout` in `GitResult`. Rejected for the initial scope -- no concrete
  consumer need was identified (mirrors EP-037's own "avoid unnecessary
  events"/"avoid unnecessary abstraction" precedent); `--porcelain`/
  `--oneline` flags keep the raw text stable and easy to parse later if a
  real need appears.

## STEP 2 Implementation Plan

```
STEP 2.1 — src/core/git/git_result.py, git_error.py: GitResult dataclass,
            GitError hierarchy (GitError, GitNotFoundError,
            GitRepositoryError, GitCommandError).

STEP 2.2 — src/services/git_service.py: GitService with status/diff/log/
            branch/show, config resolution + validation (GitServiceError),
            subprocess.run(..., encoding="utf-8", errors="replace",
            timeout=...) as the sole invocation point.
            Tests: tests/EP038/test_git_service.py against disposable
            per-test repositories.

STEP 2.3 — src/modules/git_module.py: "git" CLI namespace, thin
            CommandResult translation, HELP_TEXT matching worker/autoflow
            style.
            Tests: tests/EP038/test_git_module.py.

STEP 2.4 — config/config.yaml: new 'git' section (enabled,
            repository_path, timeout_seconds), commented in the same
            style as the existing 'background_workers' section.

STEP 2.5 — src/bootstrap.py: construct GitService, register GitModule,
            try/except (GitServiceError) -> log + disable, matching the
            BackgroundWorkerService wiring template exactly (no
            cross-EP "if X is not None" gate needed, since GitService has
            no hard dependency on any other EP's service).

STEP 2.6 — src/modules/test_module.py: register the EP038 suite.

STEP 2.7 — Individual validation: test EP038, plus the full EP033-037 +
            EP001 regression set. Do not require test all.
```
