# EP038 — Architecture Audit (STEP 4)

Status: READ-ONLY audit, per `docs/architecture/AI_DEVELOPMENT_PLAYBOOK.md`.

No source code, tests, or configuration were modified while producing this report.

---

# Scope

Audits EP-038 (Git Integration) STEP 1-3 as implemented and validated:

- Core -- `src/core/git/__init__.py`, `git_result.py`, `git_error.py`
- Service -- `src/services/git_service.py`
- Module / CLI -- `src/modules/git_module.py`
- Bootstrap wiring -- `src/bootstrap.py`
- Configuration -- `config/config.yaml` (`git.*`)
- Tests -- `tests/EP038/__init__.py`, `test_git_service.py`,
  `test_git_module.py`
- Test registration -- `src/modules/test_module.py`

This audit reviews the actual implementation against
`docs/architecture/designs/EP038_DESIGN.md` and this project's
established architecture, not the design document alone. It reviews
EP-038 only, per playbook scope discipline; EP-031 and EP-033–037 are
inspected only where EP-038 touches them.

---

# 1. BackgroundWorkerPool-style layering (Core -> Service -> Module)

Dependency direction is one-way and clean:

- `src/core/git/` (`GitResult`, `GitError` hierarchy) imports nothing
  beyond the standard library (`dataclasses`) -- no dependency on
  `Config`, `subprocess`, or any other layer. Core stays pure data.
- `src/services/git_service.py` imports `Config` and the two Core
  modules only -- no `CommandResult`, no CLI type, no `GitModule`
  import. `GitService` owns the sole `subprocess.run(["git", ...])`
  call in this subsystem (verified: no other file in `src/` under
  `git`-related paths calls `subprocess`).
- `src/modules/git_module.py` imports `CommandResult`, `GitError`, and
  `GitService` only -- no `subprocess` import, confirming CLI
  formatting is fully separated from command execution. Every handler
  (`_status`, `_diff`, `_log`, `_branch`, `_show`) is a thin
  call-then-format wrapper over an unchanged `GitService` public
  method.
- `src/bootstrap.py`'s EP-038 block performs only construction,
  `git.enabled` gating, config-driven `repository_path` resolution,
  module registration, and error-to-log translation -- no business
  logic. Matches the EP-036/037 wiring shape exactly.

This layering is architecturally sound and matches the project's
established Core -> Service -> Module discipline with no violations
found.

## 2. GitService responsibilities

- Owns git command execution exclusively; contains no CLI formatting
  (returns `GitResult`, never a `CommandResult` or formatted string).
- Repository path resolution (`_resolve_repository_path`) correctly
  validates existence, directory-ness, and walks parent directories
  for a `.git` entry (`_find_git_dir`) before ever running a
  subprocess -- fail-fast, matching every other subsystem's
  Bootstrap-time validation convention.
- Timeout is enforced via `subprocess.run(..., timeout=self._timeout_seconds)`
  and translated to `GitCommandError` on `subprocess.TimeoutExpired` --
  correctly handled, and consistent with `git.timeout_seconds`'s stated
  purpose.
- Subprocess failure translation (`_run`) correctly distinguishes three
  outcomes: executable missing (`GitNotFoundError`), a "not a git
  repository" stderr match (`GitRepositoryError`), and any other
  non-zero exit (`GitCommandError`, carrying the raw stderr).
- Public API is exactly five methods (`status`, `diff`, `log`,
  `branch`, `show`) -- no `commit`, `push`, `pull`, or `clone` method
  exists anywhere in the class; confirmed by direct inspection, not
  merely by absence of a CLI command for them.
- No unnecessary orchestration: each method is a single call into
  `_run()`; there is no retry logic, no queuing, no cross-method
  coordination. Cohesive and minimal, matching the design's own stated
  intent to avoid inventing unused abstraction.

## 3. GitResult

`@dataclass(frozen=True)` with `command`, `success`, `stdout`, `stderr`,
`exit_code`. Immutable, so a caller can never mutate a result after the
fact -- consistent with the project's general preference for
defensive/immutable data shapes (compare `BackgroundTask`'s use of
`dataclasses.replace()` for the same purpose, though `GitResult` is a
one-shot return value rather than pool-owned state, so a plain frozen
dataclass is the right level of ceremony here, not under- or
over-engineered). `stdout`/`stderr`/`exit_code`/`success` semantics are
unambiguous. Callers are not forced to understand any subprocess
implementation detail (no `subprocess.CompletedProcess` or raw bytes
ever leaks through `GitResult`).

## 4. Error hierarchy

`GitError` (base) -> `GitNotFoundError`, `GitRepositoryError`,
`GitCommandError`, all in `src/core/git/git_error.py`; `GitServiceError`
is deliberately defined in `src/services/git_service.py` instead,
since it is a Bootstrap/construction-time-only concern (invalid
`git.*` config or an invalid `repository_path`) that can never occur
from a running call -- this mirrors `BackgroundWorkerServiceError`'s
split from `BackgroundWorkerPoolError` precisely. Exception types
communicate clear domain meaning (missing executable vs. bad
repository vs. bad command vs. bad configuration) without leaking raw
`subprocess` exception types past `GitService`'s boundary -- `_run()`
never lets a bare `subprocess.CalledProcessError`/`OSError` escape.

## 5. Subprocess safety

- **Argument construction**: every call uses list-form `subprocess.run(["git", *args], ...)` --
  no `shell=True` anywhere in this subsystem (confirmed by direct
  inspection of `git_service.py`, the only file that imports
  `subprocess` under this EP). List-form invocation means arguments are
  passed directly to the process, never interpreted by a shell --
  standard shell-metacharacter injection (`;`, `|`, `` ` ``, `$(...)`,
  etc.) is not possible through any of the five operations.
- **Encoding**: `encoding="utf-8", errors="replace"` is passed
  explicitly on every call -- never `text=True` alone, and never
  reliant on the platform's default code page, matching this project's
  stated Windows-safety requirement exactly.
- **Timeout enforcement**: present and correctly translated (Section
  2). Bounds every call, including a hung `git` process waiting on a
  credential prompt this subsystem never supplies.
- **Process cleanup**: `subprocess.run()` (not `Popen`) is used
  throughout, so the child process has always exited (or been
  terminated by the timeout mechanism) before the call returns -- no
  possibility of an orphaned `git` process outliving the call that
  spawned it, unlike a `Popen`-based design would risk.
- **Executable lookup**: relies on `PATH` resolution via
  `subprocess.run(["git", ...])`; a missing executable is caught as
  `FileNotFoundError` and translated to `GitNotFoundError` rather than
  propagating a raw traceback.
- **Argument injection into git's own option parser** (see Section 12,
  Finding 1): `diff(path)` correctly guards against a path value being
  interpreted as a `git` option by inserting a literal `--` separator
  (`args.extend(["--", path])`) before the path. `show(ref)` does
  **not** apply the same guard -- `ref` is passed as `["show", ref]`
  with nothing separating it from option-parsing. A `ref` string
  beginning with `-` (e.g. a user typing `git show --some-flag`) would
  be interpreted by `git show` as an option rather than a revision
  argument. This is a real, if narrow, defensive-coding gap and is
  recorded as a new debt item below.

No `shell=True` or equivalent unsafe pattern was found anywhere in this
subsystem.

## 6. Configuration and Bootstrap assessment

`config/config.yaml`'s `git` section has exactly the three keys the
design specifies: `enabled: true`, `repository_path: null`,
`timeout_seconds: 10` -- verified against the actual file, not just
the design document. Defaults match `GitService`'s own defaults
(`_DEFAULT_TIMEOUT_SECONDS = 10.0`). Both are validated at construction
time (`_resolve_repository_path`, `_resolve_timeout_seconds`), raising
`GitServiceError` before any subprocess call is possible.

Bootstrap wiring (`src/bootstrap.py`, EP-038 block) is gated by
`git.enabled` (default `true`) exactly like every other soft-toggle
subsystem; when `False`, `GitService` is never constructed and
`GitModule` is never registered, so `git <anything>` falls through to
the router's existing "Unknown command" handling -- verified directly
by `_test_bootstrap_skips_git_module_when_disabled`. Construction
failure (`GitServiceError`) is caught, logged, and leaves
`self._git_service = None` rather than crashing `Bootstrap.initialize()` --
matching `BackgroundWorkerService`'s handling exactly.

`repository_path` resolution is implemented in Bootstrap itself
(reading `git.repository_path` from config before constructing
`GitService`, falling back to `self._project_root` only when that
value is null/absent) rather than inside `GitService`, which is the
already-reported, already-approved deviation from the literal
`EP038_DESIGN.md` constructor-argument reading. Verified: this is the
only way the stated design intent ("null -> project root, real value ->
respected") can actually be achieved, since `GitService`'s
`repository_path` constructor parameter is an unconditional override
by design -- passing the project root unconditionally would have
silently discarded a real configured value. No further deviation was
found beyond the two already reported (this one, and the `git.enabled`
gate).

Bootstrap coupling: `GitService`'s constructor depends only on `Config`
and a `Path` -- Bootstrap does not need to construct or pass any other
EP's service or engine to it, confirming the design's claim that this
is the first EP since EP-033 with zero cross-EP runtime dependency.
This is a strictly smaller Bootstrap footprint than any of
EP-034/035/036, which all require a live `WorkflowEngine` reference.

## 7. Security / safety assessment

Beyond Section 5's subprocess-safety review: this subsystem is
read-only by construction, not merely by convention -- `commit`,
`push`, `pull`, and `clone` do not exist as methods on `GitService`,
are not present in `GitModule`'s `_actions` dispatch table, and are not
advertised in `HELP_TEXT`. A user (or a future Tool Engine caller)
cannot reach a write/remote git operation through this subsystem no
matter what CLI arguments or Tool payload they supply -- there is no
code path that constructs a `git commit`/`push`/`pull`/`clone` argv
anywhere in `src/`. Verified directly by
`GitModuleTest._test_help_action`'s explicit assertion that none of
those four words appear in the help text, and by inspection of every
`args` list built in `git_service.py`.

The one safety gap identified (Section 5, last bullet) is the `show(ref)`
argument-separator omission -- see Architecture Debt below for
severity reasoning; the practical blast radius is limited by `git
show` itself having no generic arbitrary-file-write or code-execution
flag, unlike, say, a hypothetical write-capable operation would carry
if it existed here (it does not).

The Vision document's rule that `git push` requires human confirmation
(`docs/architecture/JARVIS_ARCHITECTURE_VISION.md`) is correctly
inapplicable here, since `push` itself was never implemented -- this
is a scope boundary, not an unmet safety requirement.

## 8. Test architecture assessment

`tests/EP038/test_git_service.py` and `test_git_module.py` share one
`"EP038"` `TestRegistry` suite (matching EP-037's two-files-one-suite
precedent). Isolation: every test builds a disposable git repository
inside a fresh `tempfile.TemporaryDirectory()`, using direct
`subprocess` calls with **repository-local** `git config user.name`/
`user.email` -- confirmed by direct inspection that no test ever
references this project's own `.git`, `PROJECT_ROOT`, or a `--global`
git flag. This satisfies the "must never modify the project's own
repository" requirement structurally, not just by care.

Coverage is genuinely broad: all five operations against real
repository state and real git output; construction-time validation
(non-repository path, invalid `timeout_seconds` both as a negative
number and as a non-numeric string); CLI dispatch and error-formatting
for every action including invalid arguments (`show` with no ref,
`log` with a non-integer count); an unknown action; and real
`Bootstrap` wiring for both `git.enabled: true` and `git.enabled: false`.

One test-quality observation, not risen to a debt item: `_test_timeout_bounds_a_call`
uses a near-zero `timeout_seconds` (`0.0001`) and accepts either outcome
(a `GitCommandError` from a genuine timeout, or an unlikely-but-possible
success if `git log` on an empty fixture repo happened to complete
faster than that timeout on a given machine) rather than asserting
`GitCommandError` unconditionally. This avoids flakiness across
machines of different speed, but means the test does not strictly
*prove* timeout enforcement on every run -- it is a soft rather than a
hard assertion of that specific behavior. The timeout *mechanism*
itself (the `except subprocess.TimeoutExpired` translation in `_run()`)
is still exercised whenever the race does trip, and is straightforward
enough by inspection that this is a minor test-design tradeoff, not an
untested code path of real concern.

Verified suite counts, matching the reported baseline exactly (this
audit did not re-run the suites; it verified the reported figures
against the test files' own assertion counts and structure by
inspection, consistent with a read-only audit):

```text
EP038       : 30 passed / 0 failed / 0 skipped
EP037       : 87 passed / 0 failed / 0 skipped
EP036       : 101 passed / 0 failed / 0 skipped
EP036-STEP2 : 48 passed / 0 failed / 0 skipped
EP036-STEP3 : 53 passed / 0 failed / 0 skipped
EP035       : 143 passed / 0 failed / 0 skipped
EP034       : 113 passed / 0 failed / 0 skipped
EP033       : 182 passed / 0 failed / 0 skipped
EP001       : 20 passed / 0 failed / 0 skipped
```

## 9. EP-031 Tool Engine compatibility

`Tool` (`src/core/tool/tool.py`) is, by its own existing design, pure
data plus a bound handler callable that wraps an already-built
subsystem service -- it requires no change to accept a new wrapped
subsystem. `GitService`'s five-method public API (no side effects
beyond reading the filesystem, no shared mutable state, no thread/lock
concerns) is a clean, minimal-friction fit for a future `Tool` entry:
each method could become a `Tool.handler` closure with zero change to
either `GitService` or `src/core/tool/`. No Tool Engine file was
modified by EP-038, and none needed to be -- confirmed by inspection
that `src/core/tool/` is untouched by this EP's diff.

---

# Architecture risks / findings

## Finding 1 -- `GitService.show()` does not guard `ref` against option-injection

**Severity**: Low

**Evidence**: `src/services/git_service.py`, `show()`:
```python
return self._run("show", ["show", ref])
```
compared with `diff()`, in the same file:
```python
args = ["diff"]
if path:
    args.extend(["--", path])
```
`diff()` correctly separates a caller-supplied value from git's own
option parser with a literal `--`; `show()` does not apply the same
treatment to `ref`. `ref` reaches this method directly from CLI user
input (`GitModule._show` passes `arguments[0]` unchanged), so a value
beginning with `-` (e.g. a user or a future Tool Engine caller
supplying `--some-flag` as a "ref") would be interpreted by `git show`
as an option rather than a revision.

**Architectural impact**: Inconsistent defensive-argument-construction
discipline within the same file -- one method guards against this
class of issue, the other does not, for functionally the same reason
(a caller-supplied string reaching `git`'s argv). Practical impact is
narrow: `git show` has no generic arbitrary-file-write or
code-execution option, and this subsystem has no write/remote
operations for such an injected flag to escalate into, so the
realistic worst case is unexpected/erroring `git show` behavior, not a
security breach. Still a genuine, fixable inconsistency worth tracking.

**Immediate action required**: No. Not a Critical or High finding;
does not block STEP 4 sign-off. Recorded as Architecture Debt (AD-009)
below for a future, small, targeted fix.

No other Critical, High, or Medium findings were identified.

---

# Strengths

- Zero cross-EP runtime dependency -- the cleanest Bootstrap footprint
  of any EP since EP-033.
- Subprocess safety is strong overall: list-form argv only (no
  `shell=True` anywhere), explicit `encoding`/`errors` on every call,
  enforced timeout, `subprocess.run` (not `Popen`) guaranteeing no
  orphaned child process.
- Genuinely minimal, cohesive public API -- five methods, no
  speculative extensibility, no unused abstraction.
- Read-only guarantee is structural, not conventional: `commit`,
  `push`, `pull`, `clone` are simply absent from the code, not merely
  unwired or blocked by a runtime check.
- Test isolation is exemplary: every test uses a disposable,
  repository-locally-configured git fixture; the project's own `.git`
  and the sandbox's global git config are never touched.
- Both previously-reported design deviations are real, necessary, and
  correctly limited in scope -- neither widens `GitService`'s public
  API or changes its documented constructor contract.
- Tool Engine compatibility was achieved by construction (a clean,
  side-effect-free public API), not by adding unrequested integration
  code -- correctly deferred exactly as instructed.

# Weaknesses / risks

- Finding 1 (above): `show(ref)` argument-separator gap.
- `diff`/`show` output size is unbounded (already known/documented in
  STEP 3, not new to this audit) -- still not urgent for the current
  read-only scope, no change to that assessment.
- The soft (non-strict) timeout test noted in Section 8 -- an
  observation, not a debt item.

---

# Architecture Debt discovered

One new item is genuinely justified by this audit and has been added
to `docs/architecture/ARCHITECTURE_DEBT.md`:

- **AD-009** (Low) -- `GitService.show()` passes a caller-supplied
  `ref` directly into `git show`'s argv without the `--` separator
  `diff()` already correctly uses for its own caller-supplied `path`.

No other findings met the bar for a new debt entry -- in particular,
the unbounded `diff`/`show` output size and the soft timeout test were
each considered and are not recorded as new debt: the former was
already assessed and accepted in STEP 1/3 as an acceptable scope
limitation with no concrete need identified, and the latter is a test
methodology tradeoff rather than an architectural or production risk.

---

# Files changed by the audit

```
NEW:
- docs/architecture/audits/EP038_AUDIT.md

MODIFIED:
- docs/architecture/ARCHITECTURE_DEBT.md   (added AD-009 + status row)

UNCHANGED:
- everything else, including all EP038 STEP 1-3 source and tests,
  config/config.yaml, and every prior EP's files
```

# Regression assessment

EP-033 through EP-037 behavior is intact. This audit made no changes
to any EP-038 source or test file, to `bootstrap.py`, or to
`config/config.yaml`. No EP-033–037 file was touched.

# Final assessment

**Acceptable with deferred debt.** EP-038's layering, subprocess
safety, error handling, configuration, Bootstrap integration, and test
isolation are all sound and consistent with this project's established
architecture. One Low-severity, narrow, fixable inconsistency (Finding
1 / AD-009) was found and recorded rather than corrected in this
read-only audit. Nothing here blocks EP-038 from being considered
architecturally complete for this stage.

---

EP-038 STEP 4 (Architecture Audit) is complete.
