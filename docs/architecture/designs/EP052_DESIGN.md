# EP-052 — File Automation — Design Specification (STEP 1)

Status: STEP 1 — REVISED (Architecture Discovery, Technology
Evaluation & Design) — Owner Decisions D1–D11 (Section 20) are all
**APPROVED**. EP-052 v1 shall include both read-only and
controlled-mutation file operations, subject to the layered security
model this document defines. STEP 2 (Implementation) has been
explicitly authorized and completed — see the STEP 2 implementation
report for verification details. STEP 3 (Architecture Audit) has been
completed, with one narrowly-scoped remediation (Owner Decision D11 —
a Windows-path tokenization fix to `src/core/command_router.py`) —
see `docs/architecture/audits/EP052_ARCHITECTURE_AUDIT.md`.

---

## 1. Metadata

- **Engineering Package:** EP-052 — File Automation
- **Phase:** Phase 8 — Computer Automation (`JARVIS_ROADMAP.md`)
- **Predecessors:** EP-050 Computer Use (complete), EP-051 Browser
  Automation (complete)
- **Successor:** EP-053 Vision Integration (not started)
- **This document's scope:** STEP 1 only — Architecture Discovery,
  Technology Evaluation, Design. No code, test, configuration, or
  dependency file has been created or modified as part of producing
  this document.
- **File created by STEP 1:** this document,
  `docs/architecture/designs/EP052_DESIGN.md`, only.
- **Files modified by STEP 1:** none.

---

## 2. Problem Statement

Jarvis can already launch/open files and folders with the OS default
application (`src/core/execution/executors/file_executor.py`, EP-003)
and can write arbitrary bytes to an owner-supplied path as a side
effect of one specific action (`desktop screenshot <path>`, EP-050).
Neither of these is general file management: Jarvis has no way to
list a directory's contents, inspect a file's metadata, read or write
text, copy, move, rename, create a directory, delete a path, or check
whether a path exists, as an explicit, first-class capability with
its own safety model.

`JARVIS_ROADMAP.md` Phase 8 sequences EP-052 File Automation directly
after EP-051 Browser Automation, and EP051_DESIGN.md Section 20
already reserves "general file management (organize/move/rename)" as
EP-052's territory while explicitly excluding it from EP-051's own
scope. `docs/BACKLOG.md` confirms EP-052 is next and NOT STARTED — no
design, research, or implementation work exists yet.

EP-052 STEP 1's job is to determine, from direct repository evidence
(not assumption), what a minimal, safe, testable v1 File Automation
capability should look like: what already exists and can be reused,
what must be built, what stays explicitly out of scope, and what
questions only the owner can answer.

---

## 3. Goals

- Investigate the existing repository thoroughly enough to answer,
  with cited evidence, every question this task poses (Sections 5–19
  below).
- Determine precisely where EP-050 (OS-level Computer Use) ends and
  EP-052 (File Automation) begins, so EP-052 does not duplicate
  process-launching or desktop capability EP-050 already owns.
- Propose a minimal, coherent v1 capability set — not a complete file
  manager — following the same "small, reliable action set" precedent
  EP-050 (13 actions) and EP-051 (15 actions) already established.
- Perform a serious, evidence-grounded security analysis of direct
  filesystem manipulation, since this is qualitatively riskier than
  EP-050's raw input or EP-051's browser-scoped DOM interaction: a
  filesystem action can reach *any* path on the machine, including
  ones with no relationship to a browser tab or an on-screen window.
- Evaluate implementation technology, preferring the Python standard
  library, and state plainly if no new dependency is required.
- Reuse the `CommandModule` / `CommandRouter` / Protocol-backend /
  fake-backend-testing / config-gate pattern EP-050 and EP-051 both
  already established, unless the repository shows a concrete reason
  a different design fits File Automation better.
- Produce this design document only. No implementation, test,
  refactor, or dependency change.

---

## 4. Non-Goals

Explicitly out of scope for EP-052 v1, regardless of what the Python
standard library or a third-party library technically supports:

- **Shell execution, subprocess execution, or arbitrary code
  execution** — no `file exec`/`file run` action of any kind. This is
  the file-automation analogue of EP-050's "no shell/code execution"
  rule (`EP050_DESIGN.md` Section 15) and EP-051's "no JavaScript
  execution" rule (`EP051_DESIGN.md` Section 6/D8). Process/script
  launching is, and remains, `src/core/execution/`'s (EP-003's) job
  (Section 7 below), not EP-052's.
- **Browser automation** — remains entirely EP-051's territory
  (Section 7).
- **OCR / vision / "what does this image look like"** — remains
  entirely EP-053's territory (`EP051_DESIGN.md` Section 20 already
  reserves this).
- **Autonomous filesystem agents** — EP-052 exposes single, explicit,
  synchronous actions dispatched one at a time through
  `CommandRouter.dispatch()`, identical to EP-050/EP-051's model.
  There is no "reorganize this folder tree" loop, no multi-step
  planning, no self-directed re-dispatch.
- **Cloud storage** (Google Drive, S3, Dropbox, OneDrive, etc.) — v1
  is local filesystem only. Nothing in the repository (`config.yaml`,
  `requirements.txt`, `src/`) references any cloud-storage SDK or
  credential today.
- **Network filesystem automation** (SMB shares, FTP/SFTP, WebDAV) —
  same reasoning; v1 operates only on paths already reachable through
  the local filesystem the Jarvis process runs on. Whether a given
  path happens to resolve to a mapped network drive is outside EP-052
  v1's own knowledge or control.
- **Archive extraction/creation** (zip, tar, 7z, ...) — not justified
  by any goal below; no existing code imports `zipfile`, `tarfile`, or
  a third-party archive library anywhere in `src/` (confirmed by
  direct `grep`, Section 6). Deferred (Section 18).
- **Document parsing** (PDF, DOCX, XLSX, images) — `openpyxl`/`pandas`
  are already project dependencies (`requirements.txt`), used today
  only by `src/services/invoice_service.py` and
  `src/services/fast_response_service.py` for their own domain-
  specific spreadsheet logic, not by any general file abstraction.
  EP-052 v1 does not introduce a general document-parsing capability;
  that belongs to future, specialized capabilities layered on top of
  EP-052's primitives, not EP-052 itself.
- **Credential management** — EP-052 does not read, store, export, or
  manage credentials of any kind. Section 12/16 explicitly restrict
  EP-052 v1 away from credential-shaped locations (SSH keys, browser
  profiles, `.env` files) rather than granting any special handling
  of them.
- **Binary file read/write in v1** — deferred (Section 12/D6); see
  Section 12 for the reasoning.
- **A general per-action human-confirmation/permission mechanism** —
  this is a pre-existing, cross-cutting `CommandRouter` limitation
  EP-050 and EP-051 both already disclosed and did not fix
  themselves; EP-052 does not fix it either (Section 13).

---

## 5. Existing Architecture Analysis

Direct inspection of the repository (`jarvis-main`), not assumption:

### 5.1 Project discovery / governance documents

- `PROJECT_MANIFEST.md` — the single source of truth for project
  discovery; lists context/architecture/configuration documents. Does
  not itself define File Automation.
- `AI_GENERATION_STANDARD.md` — mandatory rules for any AI generating
  code for this project: never redesign architecture, never invent
  APIs/imports, reuse existing classes/services/interfaces, one class
  one responsibility, PEP8/SOLID/DRY/KISS/YAGNI, type hints,
  docstrings, 300-line-recommended/500-line-soft-limit files, 30-line
  recommended/60-line hard-limit functions, dependency injection, no
  hardcoded paths/URLs/credentials, "when in doubt, leave a TODO."
  This EP's design and, later, its implementation, are bound by all
  of the above exactly as EP-050/EP-051 were.
- `docs/architecture/JARVIS_ROADMAP.md` — confirms EP-052 File
  Automation is the immediate next Engineering Package after EP-051
  (Phase 8), "NOT STARTED. No EP-052 design, research, or
  implementation work has begun" (stated verbatim at EP-051
  completion time).
- `docs/BACKLOG.md` — independently confirms the same: EP-052 "NOT
  STARTED... No design, research, or implementation work has begun."
- `docs/architecture/AI_DEVELOPMENT_PLAYBOOK.md` — defines the
  four-STEP process (STEP 1 Design, STEP 2 Implementation, STEP 3
  Architecture Audit, STEP 4 Documentation Completion) and the Prompt
  Strategy rule this task itself follows: "Never continue
  automatically. Always wait for the user's approval," "Do not
  regenerate architecture after STEP 1." This document is STEP 1 only.
- `docs/architecture/JARVIS_ARCHITECTURE_VISION.md` Section "Human
  Approval": *"Jarvis never performs irreversible actions
  automatically. Examples: Publishing, Sending emails, **Deleting
  files**, Git push, Production deployment. Require user confirmation
  unless explicitly configured otherwise."* — **"Deleting files" is
  named explicitly**, by the project's own founding vision document,
  as an example irreversible action requiring confirmation. This is a
  materially stronger, more specific signal than existed for EP-050's
  keystrokes/clicks or EP-051's browser clicks, and is treated with
  correspondingly more weight in Section 13.

### 5.2 EP-050 and EP-051 as direct precedent

Both prior Phase 8 EPs are **COMPLETE**, verdict **PASS WITH
FINDINGS** in both cases (`EP050_AUDIT.md`, `EP051_AUDIT.md`), and
both independently converged on the same architecture:

| Element | EP-050 (Computer Use) | EP-051 (Browser Automation) |
|---|---|---|
| Namespace | `desktop` `CommandModule` | `browser` `CommandModule` |
| Backend contract | `ComputerUseBackend` Protocol | `BrowserBackend` Protocol |
| Real implementation | `WindowsComputerUseBackend` (PyAutoGUI) | `PlaywrightBrowserBackend` (Playwright sync API) |
| Test-only implementation | `_FakeComputerUseBackend` | `_FakeBrowserBackend` |
| Dispatch mechanism | `CommandRouter.dispatch()`, unmodified | `CommandRouter.dispatch()`, unmodified |
| Safety gate | `desktop.enabled` (default `false`), re-checked every dispatch | `browser.enabled` (default `false`), re-checked every dispatch |
| Wiring | `Bootstrap` constructs backend conditionally, injects into module, registers module unconditionally | identical pattern |
| Tool Engine used? | No (`Tool.handler` is zero-argument-only, confirmed unchanged) | No (same reason, second independent confirmation) |
| Human-confirmation framework built? | No (disclosed gap, Owner Decision D2) | No (same disclosed gap, Owner Decision D2) |
| Tests | 112/0/0, fake-backend only, deterministic | 105/0/0, fake-backend only, deterministic |
| Audit verdict | PASS WITH FINDINGS (1 HIGH, 1 MEDIUM, 4 LOW, 4 INFO) | PASS WITH FINDINGS (1 HIGH, 3 MEDIUM, 3 LOW) |

Both audits' shared HIGH finding is the same pre-existing
infrastructure behavior (Section 5.4 below), not a defect either EP
introduced itself. EP-052 inherits this same, still-open condition —
it is not EP-052's job to fix it, but its existence must be
acknowledged in Section 12/16 rather than silently assumed away, as
both prior EPs' designs and audits already did for themselves.

### 5.3 `CommandRouter` / `CommandModule` (`src/core/command_router.py`)

158 lines. `CommandModule` is a `Protocol` requiring only `name`
(the namespace) and `execute(action: str, arguments: list[str]) ->
CommandResult`. `CommandRouter.dispatch(raw_input)` tokenizes with
`shlex.split`, looks up the module by the first token
(case-insensitive), and calls `module.execute(action, arguments)`
inside a `try/except Exception` that never lets a module crash the
shell. This is the exact, unmodified entry point `InteractiveShell`,
`TelegramRouter`, and `ApiRouter` all already dispatch through
(confirmed by EP-050/EP-051's own designs and re-confirmed here by
direct inspection — no second dispatch mechanism exists anywhere in
`src/`).

### 5.4 `CommandRouter.dispatch()`'s raw-input logging (pre-existing, unrelated to EP-052)

`CommandRouter.dispatch()` line 148:
`logger.info(f"Command executed: {raw_input.strip()}")` — logs the
**entire raw command line** verbatim on every successful dispatch.
This is the same pre-existing behavior `EP050_AUDIT.md` and
`EP051_AUDIT.md` both already flagged as their shared HIGH finding
(`desktop type`'s typed text, `browser type`'s typed text, `browser
goto`'s URL, which may embed a token as a query parameter). It applies
identically, unmodified, to any `file` action EP-052 v1 might add —
e.g. `file write <path> <text>` would have its full text content
logged verbatim by this pre-existing line, exactly as `desktop type`'s
argument already is. **This is not introduced by EP-052 and is not
EP-052's to fix** (fixing `CommandRouter` is out of scope for this EP,
per Section 4/13), but it means any "never logs file content" claim
this document might otherwise be tempted to make would be false
end-to-end, for the same reason EP-050/EP-051's identical claims about
typed text/URLs already turned out to be false end-to-end. Recorded
here explicitly rather than silently assumed away.

### 5.5 `src/core/tool/` (Tool Engine, EP-031)

`Tool.handler` is declared `Callable[[], object]` — a strictly
zero-argument callable, pre-bound as a closure over an already-
constructed service at registration time (`src/core/tool/tool.py`
docstring, `src/core/tool/__init__.py`). Confirmed unchanged since
EP-050's and EP-051's own identical findings: **no tool registered
anywhere in the project today accepts a parameter.** This is a
pre-existing, cross-cutting limitation, not something EP-052
introduces or can fix unilaterally (Section 9).

### 5.6 `src/core/execution/` (EP-003) — process/application/file launching

- `engine.py` (`ExecutionEngine`): holds an ordered list of
  `Executor`s; the first whose `supports(raw_target)` returns `True`
  handles a target. Never itself opens, reads, or writes a file's
  contents — it only decides *how to launch* a target and delegates.
- `executors/file_executor.py` (`FileExecutor`): the only executor
  relevant to "files" today. `supports()` returns `True` for any
  existing path whose suffix is not `.exe`/`.py`. `run()` opens the
  path with the OS's own default application/handler —
  `os.startfile()` on Windows, `open` on macOS, `xdg-open` on Linux —
  and returns success/failure. **It never reads, writes, copies,
  moves, deletes, lists, or inspects the file** — it only launches
  the OS's own handler for it, exactly like double-clicking the file
  in a file browser. This is confirmed, by direct code reading, to be
  the entire extent of the project's existing "file capability."
- `executors/process_executor.py`, `python_executor.py`,
  `url_executor.py`: handle `.exe`, `.py`, and URL targets
  respectively — launching processes/scripts/browsers, never file
  content manipulation.
- `models.py`: `TargetType` enum (`PROCESS`, `PYTHON_SCRIPT`, `FILE`,
  `URL`), `ExecutionRequest`/`ExecutionResult` frozen dataclasses.
  `ExecutionResult` has no path-list, metadata, or content field —
  it is a launch-outcome model, not a file-content model, and is not
  reused for EP-052 (Section 14).
- `process_registry.py`: tracks *processes Jarvis itself launched*
  (PID, name, handle) so `system`/`desktop`-adjacent commands can list
  or terminate them. Not file-related at all.

**Conclusion:** `src/core/execution/` owns "launch this target with
the right handler" — an orthogonal concern to "read/write/organize
this file's bytes or metadata," which is what EP-052 actually needs
to add. EP-052 does not duplicate `FileExecutor`'s job (opening with
the OS default app remains exclusively `FileExecutor`'s, Section 7),
and `FileExecutor` does not and should not grow file-content
operations itself (that would violate its single-responsibility scope
and AI_GENERATION_STANDARD.md's "one class, one responsibility" rule).

### 5.7 `src/skills/desktop/` (EP-050) — the direct architectural precedent

- `backend.py` (`ComputerUseBackend` Protocol, `Screenshot`/
  `CursorPosition`/`ScreenSize` frozen dataclasses,
  `ComputerUseBackendError`): the pattern EP-052's own backend
  contract should mirror (Section 8).
- `skill.py` (`DesktopModule`, 617 lines): implements `CommandModule`,
  is constructed with `(config: Config, backend: ComputerUseBackend |
  None)`, re-checks `config.get("desktop.enabled", False)` on *every*
  dispatched action (not only at registration), returns a clear
  "disabled" message when the gate is closed, and never imports a
  concrete backend class itself.
- `desktop screenshot <path>` (`skill.py` lines ~423–465) is the
  **one existing precedent for writing an owner-supplied path to
  disk** anywhere in the project: `path = arguments[0]`, then
  `with open(path, "wb") as file: file.write(image.data)` — **with no
  path validation, no allow-list, no traversal check, and no
  overwrite confirmation of any kind.** This is confirmed by direct
  code reading, not assumption. It means EP-052 is not introducing
  "arbitrary local path write" as a wholly new risk category to the
  project — that capability already exists, today, unrestricted, via
  `desktop screenshot` — but EP-052 is the first EP to make general
  path-based filesystem access an explicit, first-class,
  intentionally-designed capability with its own security model,
  rather than an incidental side effect of one narrow action. Section
  12/16 treat this as important context, not license to skip a real
  security analysis.
- `windows_backend.py` (`WindowsComputerUseBackend`, PyAutoGUI-based):
  confirmed to have no file-content methods at all (only
  mouse/keyboard/clipboard/screenshot/window-focus, Section 8 of
  `EP050_DESIGN.md`, re-confirmed here).
- `clipboard.py`, `keyboard.py`, `mouse.py`: all **0 bytes** —
  placeholders, unused, not part of `ComputerUseBackend`'s actual
  implementation (which lives entirely in `windows_backend.py`).

### 5.8 `src/skills/browser/` (EP-051) — the second precedent

`backend.py` (`BrowserBackend` Protocol), `skill.py` (`BrowserModule`,
20917 bytes), `playwright_backend.py` (`PlaywrightBrowserBackend`,
11393 bytes) — confirmed to contain zero file-content operations
(`browser` actions are lifecycle/navigation/DOM-observation/DOM-
interaction only, per `EP051_DESIGN.md` Section 19's own 15-action
table). `selenium_driver.py` remains a 0-byte placeholder, confirmed
still present, still unimported, exactly as `EP051_AUDIT.md`'s LOW
finding already recorded (not deleted during EP-051 STEP 4 as its own
design proposed — an EP-051 housekeeping item, not EP-052's to fix).

### 5.9 `src/skills/system/` (`SystemModule`) — the original reference pattern

`skill.py` (7657 bytes) is the module both `EP050_DESIGN.md` and
`EP051_DESIGN.md` cite as the original `CommandModule` reference
implementation their own `desktop`/`browser` modules followed.
`backup.py` and `updater.py` are **0 bytes** — placeholders, like
`browser/selenium_driver.py`, confirming this project's convention of
pre-reserving filenames for not-yet-built future capability inside a
namespace, without pre-committing to what they will contain.

### 5.10 `src/bootstrap.py` (2512 lines)

Confirmed wiring pattern for both `desktop` and `browser` (lines
~1642–1708): construct the real backend only if
`config.get("<namespace>.enabled", False)` is true (inside a
`try/except <Backend>Error`, logging a warning and falling back to
`None` on construction failure); register the module
**unconditionally** either way (`router.register(<Module>(config=...,
backend=<backend-or-None>))`); expose the constructed backend via a
read-only property (`desktop_backend`, `browser_backend`) for test/
introspection use, mirroring the constructor-injection Dependency
Policy `AI_GENERATION_STANDARD.md` mandates. This exact three-part
pattern (conditional backend construction → unconditional module
registration → read-only property) is the one EP-052's own
`Bootstrap` wiring should reuse (Section 21, STEP 2 Proposed Scope).

### 5.11 `config/config.yaml`

`desktop:` (line 379) and `browser:` (line 405) blocks both follow an
identical documented shape: a heading comment naming the owning EP
and its design document, an `enabled` key defaulting to `false` with
an explanatory comment citing the specific Owner Decision that set the
default, and a note that the flag is "re-checked on every dispatched
action... not only at startup." No `file:` block exists yet. EP-052's
own configuration block (Section 16, STEP 2 scope) should follow this
exact documented-YAML convention.

### 5.12 `src/utils/`

`constants.py` (781 bytes, populated); `helpers.py`, `paths.py`,
`validators.py` — all **0 bytes**, placeholders. **`paths.py` in
particular is a pre-reserved, currently-empty file whose name
strongly suggests it is where path-handling/validation utilities are
meant to eventually live** (Section 21 considers, but does not
mandate, whether EP-052 should be the EP that finally populates it).

### 5.13 Existing use of `shutil`/`tempfile`/`zipfile` project-wide

`grep -rn "shutil\.\|tempfile\.\|zipfile\." src/` returns exactly one
match: `src/services/fast_response_service.py:224`,
`shutil.copy2(workbook_path, backup_path)` — a single, narrow,
domain-specific backup call inside the Fast Response Board's own
invoice-workbook service, not a general file abstraction and not
built on any shared file-management layer. **No file anywhere in
`src/` imports `tempfile` or `zipfile` at all.** This confirms no
existing general-purpose file-copy/backup/archive abstraction exists
to reuse or duplicate.

---

## 6. Existing File Capabilities (Explicit Inventory)

Per the task's required checklist, each capability's current state,
confirmed by direct repository inspection:

| Capability | Exists today? | Where | Notes |
|---|---|---|---|
| File opening (OS default app) | **Yes** | `FileExecutor` (EP-003) | Launches OS handler only; no content access |
| URL/file launching | **Yes** | `URLExecutor`, `FileExecutor`, `ProcessExecutor`, `PythonExecutor` (EP-003) | Launch-only, not EP-052's concern (Section 7) |
| Process execution | **Yes** | `ProcessExecutor`, `ProcessRegistry` (EP-003) | Explicitly out of scope (Section 4) |
| Filesystem access (general) | **No** | — | No general read/write/list abstraction exists |
| Path handling | **Partial** | `FileExecutor` (`Path(...).exists()`, `.suffix`), `desktop screenshot` (`arguments[0]` as a raw path string) | No validation, no allow-list, no traversal check anywhere |
| Reading files (text) | **No** | — | Not implemented anywhere as a general capability |
| Writing files (text) | **No** | — | `desktop screenshot` writes *binary* bytes to a path, but is not a text-write capability and is scoped to one action |
| Copying | **Partial** | `fast_response_service.py`'s `shutil.copy2` | Domain-specific (invoice backups only), not general-purpose |
| Moving | **No** | — | Not implemented anywhere |
| Deleting | **No** | — | Not implemented anywhere |
| Directory listing | **No** | — | Not implemented anywhere |
| Directory creation | **No** | — | Not implemented anywhere |
| File metadata (size, mtime, type) | **No** | — | Not implemented anywhere |
| Searching (filename/content) | **No** | — | Not implemented anywhere |
| Temporary files | **No** | — | `tempfile` is imported nowhere in `src/` |
| Archive handling | **No** | — | `zipfile` is imported nowhere in `src/` |
| Encoding handling | **No** | — | No text-encoding decision point exists yet (nothing reads text files today) |
| Error handling (file-specific) | **Partial** | `FileExecutor`'s broad `except Exception` around the OS launch call only | No file-operation-specific exception hierarchy exists (unlike `ComputerUseBackendError`/`BrowserBackendError`) |
| Permission handling | **No** | — | Not implemented anywhere |

**Conclusion, directly answering the task's Section 3 instruction:**
almost nothing can be reused as-is. `FileExecutor`'s launch capability
is complementary to, not reusable for, EP-052's actual job (Section
7). `fast_response_service.py`'s `shutil.copy2` call is too narrow
and domain-coupled (a hardcoded invoice-backup flow) to lift out as a
general primitive without a redesign of that service, which is
outside EP-052's scope (`AI_GENERATION_STANDARD.md`: "never modify
unrelated files"). EP-052 must build a new abstraction — but a small
one, following the `ComputerUseBackend`/`BrowserBackend` Protocol
shape exactly (Section 8), not a novel design.

---

## 7. EP-052 Boundary

### 7.1 EP-050 / EP-052 boundary (the task's specific concern)

| Capability | EP-050 (Computer Use) | EP-052 (File Automation) |
|---|---:|---:|
| Launch/open a file with the OS default app | — (never did this; that's EP-003's job) | — (remains EP-003/`FileExecutor`'s job, not duplicated here either) |
| Raw mouse/keyboard/clipboard input | **Yes** | — |
| Screen/window observation | **Yes** | — |
| Write raw screenshot bytes to a caller-given path | **Yes** (`desktop screenshot <path>`) | — (EP-052 does not reach into `desktop`'s one existing path-write action; it stays exactly as EP-050 built it) |
| Read a text file's contents | — | **Yes** (v1 candidate, Section 9) |
| Write a text file's contents | — | **Yes** (v1 candidate, Section 9) |
| Copy / move / rename / delete a path | — | **Yes** (v1 candidates, Section 9) |
| List a directory / create a directory | — | **Yes** (v1 candidates, Section 9) |
| File metadata / existence check | — | **Yes** (v1 candidates, Section 9) |
| Process/application launching | — (never launches, only launches its *own* backend's OS input calls) | — (remains EP-003's job) |

**EP-052 does not duplicate EP-050.** `EP050_DESIGN.md` Section 4
already reserved raw OS input (mouse/keyboard/clipboard/screenshot/
window-focus) as exclusively EP-050's; nothing in that set overlaps
general file-content management. The one point of superficial
overlap — `desktop screenshot`'s path-write — is a single,
already-shipped, already-audited EP-050 action; EP-052 neither
absorbs it nor rebuilds it. If a future EP wants `desktop screenshot`
routed through EP-052's own write primitive for consistency, that is
an explicit, separate, future decision (not proposed here — see
Section 18) requiring its own review of `EP050_AUDIT.md`'s findings
about that action, not something EP-052 STEP 1 silently assumes.

### 7.2 EP-051 / EP-052 boundary (already drawn by EP-051 itself)

`EP051_DESIGN.md` Section 20 already states the boundary from the
other side, and this document does not reopen it: EP-051's downloads
and uploads are **Non-Goals**, not merely restricted, and are
described as "conceptually adjacent to general file management, which
is EP-052's territory." EP-052 v1, per Section 4/18 below, does
**not** itself implement browser-download or browser-upload handling
— it provides the general file primitives (write, list, exists, move)
that *could*, in a later, deliberate joint design, be composed with a
future EP-051.x's download/upload actions. EP-052 v1 does not assume
or half-build that composition itself.

### 7.3 EP-052 / EP-053 boundary (already drawn by EP-051 itself)

`EP051_DESIGN.md` Section 20 also already states: OCR and visual/
scene understanding are exclusively EP-053's. EP-052 reads/writes
file *bytes and metadata* — it never interprets an image's visual
content, a document's semantic structure, or performs any vision-
model invocation. A future EP-053 that needs to load an image file's
raw bytes from disk before performing OCR on it may reasonably depend
on an EP-052 primitive (`file read-bytes <path>`, if ever added,
Section 12/D6) exactly as `EP051_DESIGN.md` Section 20 already
anticipates EP-053 consuming EP-050/EP-051 screenshot output — but
EP-052 v1 does not build that consumer relationship itself; it is
future work for EP-053 to define when it exists.

---

## 8. Proposed Architecture

Reusing the `ComputerUseBackend`/`BrowserBackend` pattern exactly,
per Section 5.2/5.7's precedent, and per this task's own Section 8
prompt:

```
FileModule ("file" CommandRouter namespace)
    ↓
CommandRouter.dispatch()      (existing, unmodified)
    ↓
FileBackend (Protocol)        (new — the only interface FileModule depends on)
    ↓
LocalFileBackend              (new — the sole real implementation, stdlib-only, Section 10)
    ↓
Local filesystem (pathlib / os / shutil)
```

This is not a blind copy of EP-051's shape for its own sake — it is
the same shape *because* the same evaluation `EP050_DESIGN.md`
Section 11/32 and `EP051_DESIGN.md` Section 11 both already performed
(Tool Engine's zero-argument limitation, Section 9 below) applies
identically to EP-052, and because `Bootstrap`'s existing conditional-
construction/unconditional-registration wiring (Section 5.10) already
has an established slot for exactly this pattern with zero changes to
`CommandRouter` itself.

**Why not a different design:** EP-052 is not stateful across
dispatches the way EP-051's browser session is (Section 5.2 —
`PlaywrightBrowserBackend` holds a live `Browser`/`Page` between
calls). Every `file` action is a single, self-contained,
independently-completable filesystem call, closer to EP-050's model
(Section 5.2/EP050_DESIGN.md Section 20's State Machine) than
EP-051's. `LocalFileBackend` therefore needs **no session/lifecycle
state at all** — no `launch`/`close` pair, unlike `browser`. This is
a genuine, evidence-based difference from EP-051's shape, not an
oversight: EP-052's proposed action list (Section 9) accordingly has
no lifecycle actions, only direct, one-shot filesystem operations.

`FileModule` (mirroring `DesktopModule`/`BrowserModule` exactly):

- Implements `CommandModule` (`name = "file"`,
  `execute(action, arguments) -> CommandResult`).
- Constructed with `(config: Config, backend: FileBackend | None)` —
  constructor-injected, never imports `LocalFileBackend` itself.
- Re-checks `config.get("file.enabled", False)` on every dispatched
  action, not only at registration (Section 13/16).
- Never contains filesystem logic itself — parses/validates
  `CommandRouter` arguments, enforces the safety gate and path-safety
  checks (Section 14), and translates a `FileBackend` call/exception
  into a `CommandResult`.

`FileBackend` (Protocol, mirroring `ComputerUseBackend`/
`BrowserBackend` exactly):

- Defines the filesystem contract: `list_dir`, `stat`, `read_text`,
  `write_text`, `copy`, `move`, `create_dir`, `delete`, `exists`
  (exact v1 method set determined by Section 9's capability
  decisions).
- Raises a single `FileBackendError` (only) for any failure, mirroring
  `ComputerUseBackendError`/`BrowserBackendError`'s "one exception
  type to catch" rule.
- `LocalFileBackend` is the sole real implementation, built entirely
  on the standard library (`pathlib`, `shutil`, `os`, Section 10) — no
  new third-party dependency.
- A test-only `_FakeFileBackend`, following `_FakeComputerUseBackend`/
  `_FakeBrowserBackend`'s established convention, operating against
  an in-memory structure or a `tmp_path`-rooted real temporary
  directory (Section 15).

---

## 9. Proposed V1 Capabilities

For every candidate, per the task's explicit instruction: why it
belongs, security implications, testability, whether it already
exists, and v1-vs-deferred status.

| Action | Belongs in v1? | Why | Security | Testability | Already exists? |
|---|---|---|---|---|---|
| `file list <dir>` | **Yes** | Minimum useful "what's here" observation; needed before most other operations are usable at all | Read-only; still subject to path-safety gate (Section 14) since directory *names* themselves may be sensitive | Trivial against a fake/temp directory | No |
| `file exists <path>` | **Yes** | Cheapest possible pre-check; explicitly requested by the task's own Section 4 list | Read-only, minimal risk (reveals only a boolean) | Trivial | No |
| `file stat <path>` (metadata: size, mtime, is-dir/is-file) | **Yes** | Needed to make informed decisions before a destructive action (e.g. confirm size before overwrite) | Read-only; metadata itself could be considered mildly sensitive information about paths outside allowed roots, hence still gated (Section 14) | Trivial | No |
| `file read <path>` (text only, Section 12/D6) | **Yes** | Core, minimum-useful "get file content" capability | Could read a sensitive file's contents (secrets, `.env`, SSH keys) if path-safety (Section 14) is not enforced — **this is why Section 14's model matters most for this action** | Deterministic against fixture files | No |
| `file write <path> <text>` | **Yes** | Core, minimum-useful "produce file content" capability; symmetric with `read` | Can overwrite existing content; subject to Section 14's overwrite-behavior decision (D8) | Deterministic against a temp directory | No (only `desktop screenshot`'s narrow binary-write precedent, Section 5.7) |
| `file copy <src> <dst>` | **Yes** | Explicitly requested by the task; common, useful, no more dangerous than `write` (creates, does not destroy, the source) | Same path-safety concerns as `write` for the destination; source is read-only | Deterministic | Partial (`fast_response_service.py`'s narrow domain-specific `shutil.copy2`, Section 5.13 — not reusable as-is) |
| `file move <src> <dst>` / `file rename <src> <dst>` | **Yes**, as one action (`move`; "rename" is `move` within the same directory, no separate verb needed) | Explicitly requested; genuinely useful; but destructive with respect to the source path | **Destructive** — the source ceases to exist at its old path; Human Approval analysis applies with full force (Section 13) | Deterministic | No |
| `file mkdir <path>` | **Yes** | Explicitly requested (create directory); low-risk, purely additive, easy to reverse (delete the newly-created, still-empty directory) | Low — cannot overwrite existing content; may still create directories outside intended roots without Section 14's gate | Deterministic | No |
| `file delete <path>` | **Yes, but see Section 13** | Explicitly requested; the single most dangerous action in the entire v1 set — named explicitly in `JARVIS_ARCHITECTURE_VISION.md`'s Human Approval principle | **Destructive and irreversible** at the filesystem level (no OS trash/recycle-bin integration proposed for v1, Section 12/D7) | Deterministic against a temp directory; must include recursive-directory-deletion test cases if D9 allows it | No |
| `file search <root> <pattern>` | **Deferred** | Genuinely useful but not minimum-viable; `pathlib.Path.glob`/`rglob` make it cheap to add later without any redesign; deferring keeps v1 smaller per this task's "minimal, coherent" instruction | Read-only, but a recursive search could be a resource-exhaustion vector on a very large/deep tree with no depth/result-count limit — a reason to design it carefully later, not to rush it into v1 | N/A (deferred) | No |
| `file read-bytes` / `file write-bytes` (binary) | **Deferred** | Section 12/D6 — text covers the realistic v1 need (config files, logs, source files); binary read/write reopens the "should EP-052 also handle document parsing" question this document's Non-Goals (Section 4) deliberately close off | Binary write to an arbitrary path is exactly what `desktop screenshot` already does, unrestricted (Section 5.7) — deferring EP-052's own binary support does not remove that existing capability, it just declines to add a second one before Section 14's path-safety model is actually built and proven | N/A (deferred) | Partial precedent exists (`desktop screenshot`) but outside EP-052 |
| Archive extraction/creation | **Deferred (Non-Goal)** | Section 4/6 — no existing import, no demonstrated need | Archive extraction is a well-known path-traversal vector ("zip slip") if ever added — a reason for a dedicated future design, not a v1 afterthought | N/A (deferred) | No |
| Temporary-file creation as a caller-facing action | **Deferred** | Not requested by any concrete v1 goal; `LocalFileBackend`'s own *test* fixtures may use `tempfile` internally (Section 15) without exposing a `file tmp` action to callers | N/A (deferred) | N/A (deferred) | No |

**Proposed v1 action set (10 actions, plus `help`):** `list`, `exists`,
`stat`, `read`, `write`, `copy`, `move`, `mkdir`, `delete`, plus
`help` — smaller than EP-050's 13 and EP-051's 15, reflecting File
Automation's narrower, more foundational v1 goal relative to those
two EPs' own already-broad "small but complete" surfaces.

**Explicitly NOT included in v1** (Section 4/18 restate this list in
full): shell/process/code execution of any kind; browser automation;
OCR/vision; autonomous filesystem agents; cloud storage; network
filesystem automation; archive extraction/creation; document parsing;
credential management; binary file read/write; recursive directory
search; a general per-action human-confirmation mechanism.

---

## 10. Technology Evaluation

Per the task's explicit instruction, standard library first:

| Requirement | `pathlib` | `os` | `shutil` | Third-party alternative |
|---|---|---|---|---|
| Path representation, existence, metadata | `Path.exists()`, `Path.stat()`, `Path.is_dir()`/`is_file()` — sufficient for every v1 need | `os.path` equivalents also available but `pathlib` is the modern, already-project-wide convention (used throughout `src/`, e.g. `FileExecutor`) | — | Not needed |
| Directory listing | `Path.iterdir()` — sufficient | — | — | Not needed |
| Directory creation | `Path.mkdir()` — sufficient, including `parents=`/`exist_ok=` control needed for D8/D9 decisions | — | — | Not needed |
| Text read/write | `Path.read_text()`/`Path.write_text()` (with explicit `encoding=`, Section 12/D6) — sufficient | — | — | Not needed |
| Copy | — | — | `shutil.copy2` — sufficient, already the exact call `fast_response_service.py` already uses elsewhere in the project (Section 5.13), so this is a genuinely *consistent* choice, not merely "available" | Not needed |
| Move/rename | — | — | `shutil.move` — sufficient | Not needed |
| Delete (file) | `Path.unlink()` — sufficient | — | — | Not needed |
| Delete (directory, if D9 allows) | — | — | `shutil.rmtree` — sufficient, but see Section 13's Human Approval concern before this is wired to a v1 action | Not needed |

**No third-party filesystem library is genuinely necessary.**
`pathlib`, `os`, and `shutil` are all already part of the Python
standard library shipped with every Python interpreter capable of
running this project — no new `requirements.txt` entry, no new
`pip install`, no new post-install step (unlike EP-051's `playwright
install`, `EP051_DESIGN.md` Section 8/23). This is stated explicitly,
per the task's Section 7 instruction: **EP-052 v1 requires zero new
dependencies.**

---

## 11. Security Model

### 11.1 Considerations from the task's checklist, each addressed

| Risk | v1 disposition |
|---|---|
| Arbitrary path access | The central risk this whole section addresses — see 11.2/Section 14 |
| Absolute paths | Allowed, but subject to whatever allow/deny-root model D5 selects |
| Relative paths | Resolved against the Jarvis process's current working directory unless D5's model specifies a different base; must be canonicalized (`Path.resolve()`) before any safety check, or the check itself can be bypassed |
| Path traversal (`../..`) | Must be defeated by resolving to an absolute, canonical path **before** any allow/deny-root comparison — comparing an un-resolved string containing `..` against a root prefix is not a valid check (Section 14) |
| Symbolic links | A resolved symlink can point *outside* an otherwise-allowed root even though the link itself lives inside one; `Path.resolve()` follows symlinks by default, which is the correct behavior for the safety check to see the *real* destination, but this must be a deliberate implementation detail, not an accident, at STEP 2 |
| Junctions (Windows) | Same class of risk as symlinks; `pathlib.Path.resolve()` on Windows follows junctions/reparse points at the OS level, so the same resolve-before-check discipline applies |
| Deleting important files | The single highest-severity concern in this document; addressed by Section 13 (Human Approval) and Section 14 (path safety), not by technology alone |
| Overwriting files | Addressed by Owner Decision D8 (Section 20) |
| Directory deletion (recursive) | Addressed by Owner Decision D9 (Section 20) — `shutil.rmtree` deleting an entire tree is categorically more dangerous than `Path.unlink()` deleting one file |
| Hidden/system files | v1 proposes no special-casing of dotfiles/hidden attributes — an allowed-root model (D5) that is too permissive would let `file delete` reach a hidden config file exactly as easily as a visible one; this is an argument for a conservative D5 default, not for a separate "hidden file" rule |
| Permissions (OS-level) | v1 relies entirely on the OS's own permission enforcement — a `PermissionError` from `pathlib`/`shutil` must be caught and translated into a clean `FileBackendError`/failed `CommandResult`, never allowed to propagate raw or crash the module (mirroring `CommandRouter.dispatch()`'s own top-level catch-all, Section 5.3, as the last line of defense either way) |
| Credential files (SSH keys, `.env`, browser profiles, app data) | These are exactly the kind of path a permissive allow-root or no-deny-list model would leave fully exposed to `file read`/`file delete`; Section 14/D5 treats this as a first-class deny-by-default consideration, not an edge case |
| Protected OS directories (`C:\Windows`, `/etc`, `/System`, etc.) | Same reasoning — the OS's own permission model provides *some* protection (most such paths require elevated privileges to modify), but read access and non-privileged subpaths are often still reachable, so relying on OS permissions alone is not a substitute for EP-052's own root model |

### 11.2 Safety mechanisms evaluated (per the task's explicit list)

| Mechanism | Description | Fit for EP-052 v1 |
|---|---|---|
| Global enabled gate | `file.enabled` (default `false`), re-checked every dispatch — identical to `desktop.enabled`/`browser.enabled` | **Adopt, as the baseline** — consistent with both prior EPs, zero new precedent needed. Alone, however, this is a *category* gate, not path-level protection: once enabled, it says nothing about *which* paths are safe (Section 13's Human Approval gap applies with full force here, more so than for EP-050/EP-051, given Section 5.1's "deleting files" citation). |
| Per-action confirmation | An interactive "are you sure?" prompt before a destructive action | **Not buildable in v1** — no such mechanism exists anywhere in `CommandRouter`/`CommandModule` today (Section 13); this is the same disclosed, unresolved gap EP-050's D2 and EP-051's D2 both already recorded, now compounding for a third, independent EP. |
| Allowed roots (allow-list) | A configured list of directory roots (e.g. a "Jarvis workspace" folder) outside of which no `file` action may operate | **Strong candidate** — directly addresses path-traversal, credential-file, and protected-OS-directory risks at their source, and is a genuinely new mechanism neither `desktop` nor `browser` needed (browser addressing is DOM-selector-based, not filesystem-based; desktop's one path-write action, `screenshot`, has no such check today, Section 5.7 — EP-052 need not repeat that omission just because a precedent for skipping it exists). |
| Denied roots (deny-list) | A configured list of paths that are always off-limits regardless of the allow-list | **Complementary to allow-list**, not a substitute for it — a deny-list alone cannot anticipate every sensitive location on every machine (Section 11.1), whereas an allow-list is safe by construction (anything not explicitly listed is refused). |
| Read-only mode | A flag permitting `list`/`exists`/`stat`/`read` while refusing `write`/`copy`/`move`/`mkdir`/`delete` | **Worth offering as an additional, independent gate** alongside the enabled flag and root model — lets an owner enable file *observation* without also enabling file *mutation*, a meaningfully different risk profile the single `file.enabled` flag alone cannot express. |
| Destructive-action gate | A narrower flag/config specifically for `move`/`delete` (and `write` when it would overwrite, Section 11.1/D8) | **Worth offering**, layered on top of the general enabled flag — mirrors "read-only mode" but scoped even more narrowly to the small number of genuinely destructive actions, directly answering `JARVIS_ARCHITECTURE_VISION.md`'s "deleting files" concern (Section 5.1) with something concrete rather than deferring to the still-unbuilt general confirmation mechanism. |
| Path validation (canonicalize + compare against allow/deny roots) | The mechanical implementation `LocalFileBackend`/`FileModule` must perform for allow/deny roots to mean anything (Section 11.1's traversal/symlink discussion) | **Required, not optional**, if D5 selects any root-based model at all — without it, an allow-list is a false sense of security. |
| Sandboxing (OS-level, e.g. a container or restricted user account) | Running the entire Jarvis process itself inside a sandbox | **Out of scope for EP-052's own design** — this is a deployment/operations decision about how the whole Jarvis process is run, not something `FileModule`/`FileBackend` can control from inside the application; noted for completeness, not recommended as part of this EP's own mechanism. |

**Recommendation (not yet an Owner Decision — see D5):** combine a
global `file.enabled` gate (baseline, matching precedent) with an
**allow-list of permitted root directories** (the strongest, most
directly evidence-justified mechanism against Section 11.1's
traversal/credential/protected-directory risks) and a **separate,
narrower gate for destructive actions** (`move`, `delete`, and
overwriting `write`/`copy`) — layering three independent, cheap
mechanisms rather than relying on any single one. This recommendation
is deliberately not selected merely for convenience: Section 11.2's
table shows each alternative's actual trade-off, and the deny-list-
only and "no root model at all" alternatives are rejected specifically
because they cannot prevent traversal to an unanticipated sensitive
path, whereas an allow-list is safe by construction.

---

## 12. Human Approval Analysis

`JARVIS_ARCHITECTURE_VISION.md`'s Human Approval principle applies to
EP-052 with **more direct force than it did to EP-050 or EP-051**,
because "Deleting files" is the vision document's own explicitly
named example of an irreversible action requiring confirmation
(Section 5.1) — unlike EP-050's clicks/keystrokes or EP-051's browser
interactions, which required inference from the general principle
rather than a literal, named match.

**The same underlying architectural gap EP-050's D2 and EP-051's D2
both already disclosed still exists, confirmed unchanged by direct
inspection:** `CommandRouter`/`CommandModule` has no general
per-action human-confirmation/permission mechanism anywhere in the
codebase. EP-052 cannot build one unilaterally without violating
`AI_GENERATION_STANDARD.md`'s "never redesign architecture" /"never
introduce a second implementation of existing functionality" rules —
a bespoke, EP-052-only confirmation prompt would itself be exactly
that kind of unauthorized architectural addition, and would set a
third, inconsistent precedent alongside `desktop`/`browser`'s
already-shipped "no confirmation, only a category flag" model.

**What EP-052 v1 can do without touching `CommandRouter`:**

- Adopt Section 11.2's recommended layered gates (`file.enabled` +
  allow-list + a separate destructive-action flag) as the *closest
  available approximation* to per-action confirmation achievable
  entirely within `FileModule`'s own scope, exactly as `desktop.enabled`
  and `browser.enabled` were each EP-050/EP-051's own closest
  achievable approximation.
- Document, explicitly and without hedging, that this is **not**
  equivalent to the "require user confirmation" language
  `JARVIS_ARCHITECTURE_VISION.md` calls for — a config flag set once
  is not a per-invocation prompt. This gap is recorded here as an
  architectural dependency/follow-up (Section 19), exactly as
  `EP050_DESIGN.md`'s D2 and `EP051_DESIGN.md`'s D2 both already did,
  now compounding for a third time.
- Optionally (Owner Decision D7) require `move`/`delete` and
  overwriting `write`/`copy` to be gated by a *second*, narrower flag
  (e.g. `file.allow_destructive`, defaulting to `false` independently
  of `file.enabled`) so that enabling file *observation* does not
  silently also enable file *deletion* — a strictly stronger posture
  than either `desktop.enabled` or `browser.enabled` offers today,
  motivated directly by Section 5.1's explicit "deleting files"
  citation.

**What EP-052 v1 explicitly does not do:** modify
`src/core/command_router.py`; invent a bespoke confirmation prompt
inside `FileModule` that no other module shares; claim, anywhere in
this document or a future implementation, that the layered-flags
model "satisfies" the Human Approval principle — it mitigates the
same category of risk EP-050/EP-051 already accepted living with, at
a finer granularity than either of them, but does not close the gap.

---

## 13. Path Safety Model

(Combining the task's Section 5/Section 13 numbering into one
coherent model, since the task's own Section headings for "Security
Model" and "Path / Data Model" overlap substantially for a filesystem
EP — restated here as its own section per the task's Section 18
document-structure requirement.)

**Representation:** every path argument accepted by any `file` action
is, at the `FileModule` boundary, immediately wrapped in a `pathlib.Path`
and resolved to its absolute, canonical form via `Path.resolve()`
(which follows symlinks/junctions, Section 11.1) *before* any
allow/deny-root comparison or backend call — never compared as a raw
string, and never resolved *after* a check that could itself be
bypassed by an unresolved `..` segment.

**Allow-list evaluation (pending Owner Decision D5):** if adopted, a
resolved path is permitted only if it is equal to, or a descendant
of, at least one configured allowed root (also itself resolved once
at startup/config-load time, not re-resolved per call in a way that
could race with a filesystem change). Any resolved path that is not
a descendant of any allowed root is refused before `LocalFileBackend`
is ever called — mirroring `DesktopModule`'s "argument shape
validation may run before the enabled gate, but the actual backend
call never happens until every gate passes" discipline (Section 5.7).

**Denied roots (if adopted alongside the allow-list, D5):** evaluated
after allow-list matching, as an explicit additional exclusion even
within an otherwise-allowed root (e.g. an allowed "Jarvis workspace"
root that happens to contain a `.git/` or `.env` subpath the owner
wants excluded regardless).

**Directories vs. files vs. unknown paths:** `file stat`/`file exists`
work uniformly on any resolved path type; `file list` requires the
resolved path to be an existing directory (a clean, typed failure
otherwise); `file read`/`file write` require the resolved path to be
(or, for `write`, to *become*) a regular file, never a directory,
device file, or other special path type — `LocalFileBackend` must
reject non-regular-file targets explicitly rather than letting
`pathlib`/`shutil` behave unpredictably against them.

---

## 14. Data / Result Model

Per the task's Section 10 instruction — determine whether a dedicated
model is necessary, and avoid over-engineering:

- **Reuse `CommandResult`** (`src/core/command_router.py`) as the
  outer result type for every `file` action, exactly as `desktop`/
  `browser` both already do — no new top-level result wrapper needed.
- **A small number of new, `FileBackend`-internal dataclasses are
  justified**, mirroring `Screenshot`/`CursorPosition`/`ScreenSize`'s
  precedent (Section 5.7) — e.g. a `FileEntry` (name, is_dir, size,
  modified-time) for `list`/`stat` results, kept as a plain,
  frozen dataclass with no behavior. This is not over-engineering; it
  is the same proportionate, precedent-following amount of structure
  `ComputerUseBackend`/`BrowserBackend` already introduced for their
  own observation results.
- **No dedicated "file content" wrapper type is needed for v1** — a
  read text result is simply a `str`; a write's outcome is simply
  success/failure plus a message, expressed through `CommandResult`
  exactly as every existing action already does. Introducing a
  bespoke `FileContent` object with no behavior beyond holding a
  string would be over-engineering for what `str` already expresses.
- **`ExecutionResult`/`TargetType` (EP-003, Section 5.6) are not
  reused** — they model *launch* outcomes, not file-content outcomes,
  and forcing EP-052 through the wrong model to avoid "creating a new
  type" would itself violate `AI_GENERATION_STANDARD.md`'s Single
  Source Of Truth principle (each model owns the data shape it was
  designed for; `ExecutionResult` was designed for EP-003's job, not
  EP-052's).

---

## 15. Error Handling

Following `ComputerUseBackendError`/`BrowserBackendError`'s established
one-exception-type-per-backend convention exactly:

- `LocalFileBackend` raises a single `FileBackendError` (only) for
  every failure — a missing path, a permission error, a path-safety
  rejection, a type mismatch (e.g. `list` on a file, not a
  directory) — never letting a raw `OSError`/`PermissionError`/
  `FileNotFoundError` propagate out of the backend.
- `FileModule` catches `FileBackendError` (and only that type) from
  every backend call and translates it into a failed `CommandResult`
  with a clear, non-leaking message — mirroring
  `AI_GENERATION_STANDARD.md`'s "never silently ignore exceptions...
  catch only expected exceptions... unexpected exceptions must
  propagate" rule: an unexpected exception type is a genuine bug and
  should surface (caught only by `CommandRouter.dispatch()`'s own
  top-level catch-all, Section 5.3, as the last line of defense,
  exactly as it already is for every other module).
- Path-safety rejections (Section 13) are raised as `FileBackendError`
  too, with a distinct, clearly-worded message ("path is outside the
  allowed workspace") — not silently treated the same as "file not
  found," so a caller/owner can tell the difference between "this
  doesn't exist" and "this was refused for safety reasons."

---

## 16. Testability

Following `_FakeComputerUseBackend`/`_FakeBrowserBackend`'s
established convention (Section 5.2), with the added consideration
that filesystem operations, unlike OS input or a Playwright session,
have a natural, safe, real-but-isolated substitute available:

- **A `_FakeFileBackend`** (in-memory dict-of-paths, or a thin wrapper
  around Python's `tempfile.TemporaryDirectory`) for pure unit tests
  needing no real disk I/O at all — the fastest tier, mirroring
  `_FakeComputerUseBackend`'s "no real hardware" role.
- **`LocalFileBackend` itself can also be exercised directly and
  deterministically against `tmp_path`** (pytest's built-in temporary-
  directory fixture) — unlike `WindowsComputerUseBackend` (needs a
  real display) or `PlaywrightBrowserBackend` (needs a real browser
  binary), `LocalFileBackend`'s *real* implementation is itself fully
  testable without any special hardware, display, or network access,
  since it is pure standard-library filesystem code operating on an
  ordinary, disposable temp directory. This is a meaningful
  difference from both prior EPs worth stating plainly: EP-052's
  "real backend" tests can run in the same default, fully-automated
  suite as its fake-backend tests, with no separate, unregistered,
  manual-verification-only integration module required for the *core*
  read/write/copy/move/mkdir/delete logic (Section 15's
  `desktop`/`browser` precedent for a separate integration suite
  applied only because *their* real backends needed real hardware/
  network — EP-052's does not).
- **No real user filesystem is touched by the automated suite** — every
  test operates inside a fresh `tmp_path` created and destroyed by
  pytest itself, never the developer's home directory, the repository
  root, or any path outside the test's own sandbox.
- **Cases to cover:** missing path, permission error (where the test
  environment can simulate one), path-traversal attempt (`../../etc/
  passwd`-shaped input against a configured allow-list), symlink
  pointing outside an allowed root, destructive-action gate closed vs.
  open, overwrite-behavior per D8, encoding errors on `read`/`write`
  (Section 12/D6's scope — malformed/non-UTF-8 text), `file.enabled:
  false` genuinely blocking every action before any backend call
  (mirroring `desktop`/`browser`'s own "zero backend interaction while
  disabled" tests exactly), and `CommandRouter` string-dispatch
  (`"file <action> <args>"`) producing results identical to direct
  `FileModule.execute()` calls (the same dispatch-equality assertion
  both prior EPs' suites already include).
- **A separate, optional, real-machine manual-verification pass** is
  still appropriate for genuinely OS-specific edge cases (Windows
  junctions, actual filesystem permission ACLs, very long paths) even
  though the *core* logic does not require it — a smaller version of
  EP-050/EP-051's three-tier split, not the full weight of it.

---

## 17. Cross-Platform Strategy

`EP051_DESIGN.md` retained a cross-platform architecture with Windows
as the v1 manual-verification target (Section 5.2). EP-052 should
follow the **same approach, with even less platform-specific risk
than either prior EP**: `pathlib`, `os.path`, and `shutil` are all
already cross-platform by design in the Python standard library
itself — `pathlib.Path` transparently handles both `WindowsPath` and
`PosixPath` semantics, and none of `shutil.copy2`/`shutil.move`/
`Path.unlink`/`Path.mkdir` require any `platform.system()` branch to
function correctly on Windows, macOS, or Linux. This is a stronger
position than `WindowsComputerUseBackend`'s honest Windows-only v1
scoping (PyAutoGUI's OS-input primitives are genuinely OS-specific)
and matches `PlaywrightBrowserBackend`'s genuinely-cross-platform-by-
design precedent (`EP051_DESIGN.md` Owner Decision D11) — **no
`sys.platform`/`platform.system()` conditional branch should be
necessary anywhere in `LocalFileBackend`** for the v1 action set,
though Windows remains the intended manual-verification target,
matching every prior EP's own precedent.

---

## 18. Threat Model

```
User → Jarvis (any dispatch surface: shell, Telegram, REST API, voice)
     → CommandRouter.dispatch("file <action> <args>")
     → FileModule
     → FileBackend (LocalFileBackend)
     → Local filesystem
```

**Clearly separated categories, per the task's explicit instruction:**

- **Data:** file contents read by `file read`, directory listings
  from `file list`, metadata from `file stat`. This is always
  returned to the caller as inert information — `FileModule` never
  feeds a `file read` result back into `CommandRouter.dispatch()`,
  an AI provider prompt, or an Agent/Planning decision point itself,
  mirroring `EP051_DESIGN.md` Section 13's identical trust-boundary
  reasoning for `browser page-text`: file content is untrusted data
  the moment it did not originate from the user or Jarvis's own
  configuration, and must never be treated as an instruction even if
  it contains text that looks like one.
- **Commands:** the `file <action> <args>` dispatch itself, which
  originates from whatever caller reached `CommandRouter.dispatch()`
  — the same trust surface every other module already shares
  (Section 12's core observation).
- **Filesystem operations:** the actual `LocalFileBackend` calls,
  gated by Section 11/13's layered model before they ever touch a
  real path.

**Malicious/untrusted input examples, per the task's list:**

- **Path traversal** — `file read ../../.env` or similar; defeated by
  Section 13's resolve-then-compare discipline, assuming Owner
  Decision D5 adopts an allow-list.
- **Malicious filenames** — a filename containing shell-metacharacter-
  looking content (`; rm -rf /`) is inert to EP-052, since no `file`
  action ever passes a path through a shell — `pathlib`/`shutil`
  operate on the path as data, never as a command string. This is a
  structural, not incidental, protection: EP-052 has no shell-
  execution code path at all (Section 4).
- **Symlink attacks** — a symlink inside an allowed root pointing
  outside it; defeated by resolving before comparing (Section 13).
- **Accidental deletion** — the realistic, common-case risk, more
  likely than deliberate attack for a personal-use system like this
  one; addressed by Section 12's destructive-action gate
  recommendation, not solved outright (the gap is disclosed, not
  closed, per Section 12's own honesty requirement).
- **Overwrite of sensitive files** — addressed by Owner Decision D8.
- **Malicious content being interpreted as instructions** — the
  `file read` trust-boundary point above; structurally prevented by
  EP-052 v1 having no feedback loop from file content back into
  dispatch, identical in shape to `EP051_DESIGN.md` Section 13's
  reasoning for `browser page-text`. Exactly as that document noted,
  **this boundary becomes load-bearing, not merely documented, the
  moment a future EP feeds `file read` output toward another
  dispatch or AI call** — recorded now for that future consumer.

---

## 19. Deferred Capabilities

Per the task's explicit instruction not to let future possibilities
inflate the v1 architecture — restating Section 9's per-capability
table as a single list, plus cross-cutting deferrals:

- `file search <root> <pattern>` (recursive filename/content search).
- Binary file read/write (`file read-bytes`/`file write-bytes`).
- Archive extraction/creation (zip/tar/7z).
- Temporary-file management exposed as a caller-facing action (vs.
  internal test-only use).
- A general per-action human-confirmation framework spanning
  `desktop`/`browser`/`file` uniformly — the same still-unscheduled
  "future, dedicated Engineering Package" `EP050_DESIGN.md`'s D2 and
  `EP051_DESIGN.md`'s D2 both already flagged, now with a third
  independent EP's evidence behind it.
- Parameterized Tool Engine support — same still-unscheduled item
  `EP050_DESIGN.md` Section 28/`EP051_DESIGN.md` Section 21 (D4) both
  already flagged; EP-052 is a third, independent confirmation that
  `Tool.handler`'s zero-argument limitation blocks any project skill
  needing parameters, not an EP-050/EP-051-specific accident.
- Cloud storage / network filesystem integration.
- Populating `src/utils/paths.py` (currently a 0-byte placeholder,
  Section 5.12) with general path-handling helpers, if a future EP
  determines shared utilities belong there rather than staying
  private to `FileBackend`.
- Wiring `desktop screenshot`'s existing path-write through a future
  shared write primitive for consistency (Section 7.1) — an explicit
  future decision, not proposed by this document.
- File-download/upload composition with a future EP-051.x (Section
  7.2) — requires a joint design, not an EP-052-unilateral extension.

---

## 20. Owner Decisions

Per the task's explicit instruction, only genuine questions the
existing architecture and repository cannot answer on their own are
listed here, mirroring `EP050_DESIGN.md`/`EP051_DESIGN.md`'s own
Owner Decision format exactly.

**Approval status: all of D1–D11 are APPROVED**, per the owner's
explicit, itemized Owner Approval (recommended options accepted as
reviewed for D1, D3–D10; D2 previously approved with the revised text
below). STEP 2 (Implementation) was authorized and has been
completed. **D11 was added, and approved, during STEP 3 (Architecture
Audit) remediation** to authorize one specific, narrowly-scoped
exception to Section 21's "DO NOT MODIFY" list, documented in full
under D11 below.

### D1 — File technology / standard library — **APPROVED — Owner Decision**

**Question:** Should EP-052 use only the Python standard library
(`pathlib`, `os`, `shutil`), or is a third-party filesystem library
justified?
**Options considered:** (a) standard library only; (b) a third-party
library (e.g. `send2trash` for OS-trash-integrated deletion, discussed
under D7).
**Recommendation:** (a) — Section 10's evaluation found no genuine
need unmet by the standard library for the proposed v1 action set.
**Rationale:** Zero new dependency cost, zero new post-install step
(unlike EP-051's Playwright), and `shutil.copy2` is already the exact
call used elsewhere in the project (Section 5.13) — the most
consistent possible choice, not merely the cheapest.

### D2 — v1 capability scope — **APPROVED — Owner Decision**

**Question:** Is Section 9's proposed ten-action set (`list`,
`exists`, `stat`, `read`, `write`, `copy`, `move`, `mkdir`, `delete`,
`help`) the right v1 scope, or should some be deferred further (e.g.
ship read-only v1 first, add mutation actions in a v1.1)?
**Options considered:** (a) the full ten-action set together — both
read-only observation (`list`, `exists`, `stat`, `read`) and
controlled mutation (`write`, `copy`, `move`, `mkdir`, `delete`) ship
in v1, with every mutation action gated by Section 11/13's layered
security model (D3–D5, D7, D8) rather than excluded outright; (b) a
read-only-first v1, deferring all mutation actions to a v1.1 once the
path-safety model has been proven in production; (c) an even smaller
set (drop `move`, keep only `copy` + manual delete-of-source).
**Decision — APPROVED:** (a). EP-052 v1 **shall** include both the
read-only and the controlled-mutation action sets together:

- **Read-only:** `list`, `exists`, `stat`, `read`.
- **Controlled mutation:** `write`, `copy`, `move`, `mkdir`, `delete`.

**Rationale:** The owner has explicitly reviewed and overridden this
document's earlier (b) recommendation. Mutation is not deferred to a
v1.1 — it ships in v1, but strictly as *controlled* mutation, never
as unrestricted filesystem access: every mutation action remains
subject to the full layered security model this document already
defines (`file.enabled` required, default `false`, Section 13; an
explicit, default-empty allow-list of permitted root directories,
Section 11.2/D4/D5; a separate `file.allow_destructive` gate for
`move`/`delete`/overwrite, D3; overwrite refused by default, D7;
recursive directory deletion excluded from v1, D8; no shell
execution, no arbitrary command execution, no subprocess-based
filesystem manipulation, no bypass of these boundaries under any
configuration; no new external dependency unless proven genuinely
necessary, Section 10/D1). This makes EP-052 v1 a **controlled
filesystem automation capability, not a read-only filesystem
viewer** — read-only actions require only `file.enabled: true` plus
an allowed root; mutation actions additionally require
`file.allow_destructive: true` (for `move`/`delete`/overwrite) and
are refused entirely for any path outside the configured allow-list,
regardless of which flags are set. Section 9's originally-proposed
ten-action v1 set is unchanged; what changes is that it is no longer
treated as an option to be narrowed — it is now the approved v1
scope in full.

### D3 — Destructive operations — **APPROVED — Owner Decision**

**Question:** Should `move`/`delete` (and overwriting `write`/`copy`)
be gated by a separate, narrower flag from the general `file.enabled`
gate?
**Options considered:** (a) one single `file.enabled` flag governs
everything, mirroring `desktop`/`browser`'s precedent exactly; (b) a
second, independent `file.allow_destructive` flag (default `false`)
required in addition to `file.enabled` for `move`/`delete`/overwriting
`write`/`copy`, per Section 12's recommendation.
**Recommendation:** (b).
**Rationale:** Section 5.1's "deleting files" citation and Section
12's analysis both argue this EP's risk profile is not uniform across
its own action set the way `desktop`/`browser`'s mostly-similar-risk
actions arguably are — separating observation from destruction is a
cheap, config-only mechanism that meaningfully narrows the blast
radius of an accidentally-enabled `file.enabled: true`.

### D4 — Filesystem safety model — **APPROVED — Owner Decision**

**Question:** Which combination of Section 11.2's mechanisms should
EP-052 v1 actually implement?
**Options considered:** (a) global enabled gate alone (matching
`desktop`/`browser` exactly, i.e. no path-level restriction beyond OS
permissions); (b) global gate + allow-list of permitted roots
(Section 11.2's recommendation); (c) global gate + deny-list only
(protect a fixed, hardcoded set of sensitive paths, allow everything
else); (d) global gate + both allow-list and deny-list.
**Recommendation:** (d) — Section 11.2's reasoning: an allow-list is
safe by construction (default-deny), and a supplementary deny-list
lets an owner exclude a sensitive subpath *within* an otherwise-
allowed root without having to restructure the allow-list itself.
**Rationale:** Restated from Section 11.2 — (a) leaves every risk in
Section 11.1's table fully open once enabled; (c) cannot anticipate
every sensitive path on every machine and degrades to (a)'s risk
profile for anything the owner didn't think to list.

### D5 — Allowed roots / unrestricted paths — **APPROVED — Owner Decision**

**Question:** If D4 selects an allow-list (option b or d), what
should the actual default allowed root(s) be — e.g. a dedicated
"Jarvis workspace" directory the owner explicitly configures, the
repository root itself, the current working directory, or no default
(empty list, meaning `file.enabled: true` alone still permits
nothing until the owner explicitly configures at least one root)?
**Options considered:** (a) no default — an empty allow-list, so
`file.enabled: true` alone is inert until the owner adds at least one
root, mirroring `browser.enabled`'s own "opt-in with no further
default" model as closely as a root-based system can; (b) default to
the repository root (`.`, per `PROJECT_MANIFEST.md`'s own "Repository
Root" convention); (c) default to a new, dedicated config value with
no built-in default path at all, requiring explicit owner input
before the config file is even considered complete.
**Recommendation:** (a) — safest possible default, and consistent
with every prior risky-capability flag in this project defaulting to
the *most* conservative behavior, not merely `false`.
**Rationale:** This question cannot be answered from the repository
alone — it depends entirely on how the owner actually intends to use
File Automation (a scratch/output folder? the whole project tree?
somewhere else entirely?), which only the owner can specify.

### D6 — Text vs. binary support — **APPROVED — Owner Decision**

**Question:** Should EP-052 v1 support binary file read/write at all,
or text only?
**Options considered:** (a) text only (UTF-8, with explicit, clean
error handling for non-UTF-8/malformed content, per Section 15); (b)
text and binary both, from v1.
**Recommendation:** (a).
**Rationale:** Section 9's table — text covers the realistic v1 need
(config, logs, source, notes); binary reopens exactly the "should
EP-052 also do document/image handling" question Section 4's
Non-Goals deliberately close off, and `desktop screenshot`'s existing,
narrow, already-audited binary-write action (Section 5.7) already
covers the one binary-write case that exists in the project today.

### D7 — Overwrite behavior — **APPROVED — Owner Decision**

**Question:** Should `file write`/`file copy` silently overwrite an
existing destination, refuse by default and require an explicit
`--force`-style flag, or something else (e.g. `send2trash`-style
soft-delete of the previous content before overwriting)?
**Options considered:** (a) silently overwrite, matching `open(path,
"wb")`'s own current, unrestricted behavior in `desktop screenshot`
(Section 5.7); (b) refuse by default, require an explicit additional
argument/flag to confirm intent to overwrite; (c) as (b), but also
back up the previous content (e.g. to a `.bak` sibling file or an OS
trash/recycle-bin-integrated library such as `send2trash`) before
overwriting.
**Recommendation:** (b), with (c)'s backup behavior specifically for
`file delete` (not `write`/`copy`) recorded as a reasonable v1.1
enhancement, not a v1 requirement.
**Rationale:** `desktop screenshot`'s existing silent-overwrite
precedent (a) was accepted for one narrow, already-audited action; it
should not be treated as blanket license for `write`/`copy`'s wider
surface without the owner's explicit, fresh sign-off, given Section
12's stronger Human Approval framing for this EP specifically.

### D8 — Recursive directory operations — **APPROVED — Owner Decision**

**Question:** Should `file delete` support deleting a non-empty
directory recursively (`shutil.rmtree`), or should v1 restrict
`delete` to files and empty directories only, requiring the caller to
empty a directory first?
**Options considered:** (a) support recursive directory deletion in
v1, gated behind D3's destructive flag; (b) restrict v1's `delete` to
single files and already-empty directories only, deferring recursive
deletion to a later, more deliberately-designed action (e.g. a
separate, more loudly-named `file delete-tree` requiring extra
confirmation) once the safety model has more production experience
behind it.
**Recommendation:** (b).
**Rationale:** Recursive directory deletion is categorically more
dangerous than single-file deletion (one mistaken path argument can
destroy an entire subtree, not one file) — the same conservatism
this document applies throughout the mutation actions D2 approved
(layered gating, default-deny, no silent overwrite) applies here with
even more force, since this is the single most severe possible
mistake in the entire v1 action set.

### D9 — CommandRouter vs. Tool Engine — **APPROVED — Owner Decision**

**Question:** Should `FileModule` dispatch through `CommandRouter`
(as this document proposes) or attempt to use/extend Tool Engine?
**Options considered:** (a) `CommandRouter`, matching EP-050/EP-051
exactly; (b) extend Tool Engine to support parameterized handlers
first, then build `FileModule` on top of it; (c) a bespoke
file-specific dispatch abstraction.
**Recommendation:** (a) — for the same reasons Section 9/`EP050_DESIGN.md`
Section 11/32 and `EP051_DESIGN.md` Section 11 both already concluded,
now reinforced by a third independent EP reaching an identical result.
**Rationale:** Every `file` action needs at least one path argument;
`Tool.handler`'s zero-argument-only signature (Section 5.5) cannot
express this at all without a cross-cutting change this EP is not
authorized to make unilaterally (`AI_GENERATION_STANDARD.md`: "never
redesign architecture"). This decision is presented for explicit
owner confirmation, not silently assumed, in case the owner wishes to
finally schedule the "parameterized Tool support" EP that would
change this answer.

### D10 — Cross-platform scope — **APPROVED — Owner Decision**

**Question:** Should EP-052 target genuine cross-platform support
from v1 (matching `PlaywrightBrowserBackend`'s precedent), or scope
itself to Windows-only like `WindowsComputerUseBackend` did?
**Options considered:** (a) genuine cross-platform support, no
`platform.system()` branching in `LocalFileBackend` (Section 17); (b)
Windows-only v1, matching `WindowsComputerUseBackend`'s honest scoping
precedent even though nothing technical requires it here.
**Recommendation:** (a).
**Rationale:** Unlike EP-050's PyAutoGUI-based OS input (genuinely
platform-coupled), `pathlib`/`shutil` are cross-platform by design in
the standard library itself (Section 17) — there is no technical
reason to artificially restrict EP-052 to Windows the way EP-050 had
a real one to restrict itself. Windows remains the intended manual-
verification target regardless, matching every prior EP.

### D11 — CommandRouter tokenizer remediation (Windows path corruption) — **APPROVED — Owner Decision**

**Question:** During EP-052 STEP 2 test verification, a real defect
was discovered in `CommandRouter.dispatch()` (`src/core/command_router.py`,
explicitly listed under Section 21's "DO NOT MODIFY" and asserted
"byte-identical" by Section 22's original Final Conclusion): its
tokenizer, `shlex.split(raw_input.strip())`, runs in POSIX mode, which
treats `\` as an escape character and silently strips it from
unquoted arguments. On Windows, this corrupts any dispatched path
argument containing backslashes (e.g. `D:\Temp\tmp6anxti4f\dispatch-test.txt`
becomes `D:Temptmp6anxti4fdispatch-test.txt`) *before* `FileModule`
ever receives it — causing `file.allowed_roots` to correctly reject
the now-corrupted path, and causing `CommandRouter`-dispatched `file`
actions to behave differently from the same action called directly
against `FileModule.execute()`. Should this pre-existing,
EP-052-independent `CommandRouter` defect be fixed as part of EP-052
remediation, given Section 21 otherwise reserves this file as
out of scope?
**Options considered:** (a) leave `CommandRouter` unmodified and
require every EP-052 caller on Windows to avoid backslash path
separators (impractical — Windows paths are backslash-separated by
default, and no such workaround is available to a Telegram/REST/voice
caller who cannot control how their input is tokenized); (b) a
narrowly-scoped, isolated fix to `CommandRouter`'s tokenizer that
preserves backslashes while leaving every other aspect of dispatch
unchanged; (c) work around the defect entirely inside `FileModule`
(rejected — `FileModule` never sees the raw, pre-tokenized input, so
it structurally cannot repair a corruption that already happened
upstream inside `CommandRouter.dispatch()`).
**Decision — APPROVED:** (b). The owner explicitly authorizes the
already-made, minimal change to `src/core/command_router.py`:
replacing the direct `shlex.split(raw_input.strip())` call with a
private, static `CommandRouter._tokenize()` helper that constructs a
`shlex.shlex(raw_input, posix=True)` lexer with `whitespace_split =
True` and `escape = ""` — disabling backslash-escape interpretation
while leaving POSIX quote-stripping (and therefore quoted arguments
containing spaces) fully intact.
**Scope constraints (binding on this fix, verified in
`EP052_ARCHITECTURE_AUDIT.md`):**
- The change is minimal and isolated — one new private static method
  plus a one-line call-site change in `dispatch()`; no other line of
  `CommandRouter` is touched.
- `CommandRouter`'s public API (`register`, `register_modules`,
  `dispatch`, `module_names`, `CommandResult`, `CommandModule`) is
  unchanged — `_tokenize()` is a private implementation detail.
- No redesign of `CommandRouter` or of Tool Engine (`src/core/tool/`,
  which remains completely untouched) occurs as part of this fix.
- No EP-052 security mechanism is weakened or bypassed by this
  change: `file.allowed_roots`, `file.denied_paths`,
  `file.allow_destructive`, and overwrite protection are all enforced
  entirely inside `FileModule`/`LocalFileBackend`, which this fix does
  not touch — it only ensures `FileModule` receives an uncorrupted
  path argument to evaluate against those gates in the first place.
- Existing tokenizer behavior for quoted arguments (e.g. `file write
  "C:\Program Files\Jarvis\file.txt" "some text"`) is preserved
  unchanged — verified directly (Section 9,
  `EP052_ARCHITECTURE_AUDIT.md`).
**Rationale:** The defect is real, silently corrupts every Windows
backslash path dispatched through `CommandRouter` (not only `file`
actions — though `file` is the first EP-052 v1 command whose test
suite actually exercises real Windows-style paths through the
dispatch path, since `desktop`/`browser` actions in EP-050/EP-051 do
not take arbitrary filesystem path arguments in the same way), and
cannot be fixed from inside `FileModule` because the corruption
happens upstream, inside `CommandRouter.dispatch()` itself, before
`FileModule.execute()` is ever called. Declining to fix it would
leave `CommandRouter`-dispatched `file` actions permanently broken on
Windows — the project's own primary manual-verification target
(Section 17/D10) — for no security benefit, since the fix narrows
(corrects) an accidental data-corruption bug rather than expanding
any capability or loosening any gate.
**This Owner Decision D11 supersedes, specifically and only for this
one narrowly-scoped fix, Section 21's original "DO NOT MODIFY:
`src/core/command_router.py` — zero changes" line and Section 22's
original "`src/core/command_router.py`... remain[s] byte-identical to
their pre-EP-052 state" statement. Every other "DO NOT MODIFY" item in
Section 21 (`src/core/tool/`, `src/core/execution/`, `src/skills/desktop/`,
`src/skills/browser/`, every prior EP's design/audit document) remains
fully in force, unmodified by D11.**

---

## 21. STEP 2 Proposed Scope

Not authorized by this document — presented only so the owner can
evaluate what approving Section 20's decisions would actually
authorize, per `EP050_DESIGN.md`/`EP051_DESIGN.md`'s own "plan only"
precedent for this section:

### CREATE

- `src/skills/files/backend.py` — `FileBackend` Protocol,
  `FileBackendError`, `FileEntry` dataclass (Section 8/14).
- `src/skills/files/local_backend.py` — `LocalFileBackend`, the sole
  real implementation (Section 8/10).
- `src/skills/files/skill.py` — `FileModule` (Section 8).
- `tests/EP052/test_file.py` — primary automated suite, fake-backend
  and `tmp_path`-based real-backend tests both included (Section 16).

(Namespace note: `src/skills/files/`, plural, is proposed rather than
`src/skills/file/` to avoid the Python-builtin-adjacent ambiguity of a
module literally named `file`; the `CommandRouter` namespace/verb
itself, `"file <action>"`, is unaffected either way and is what this
document's examples use throughout, per Section 9's proposed action
table — this naming detail is a STEP 2 implementation choice, not an
Owner Decision, and is noted here only for completeness.)

### MODIFY

- `src/bootstrap.py` — additive only: one new import block, one new
  conditional `LocalFileBackend` construction (gated on
  `file.enabled`, mirroring `desktop.enabled`/`browser.enabled`'s
  wiring exactly, Section 5.10), one new `FileModule(...)`
  construction added to `register_modules()`'s call list, one new
  read-only `file_backend` property. No existing module's
  construction, order, or arguments changes.
- `config/config.yaml` — additive only: one new `file:` block
  (`file.enabled` default `false`, `file.allow_destructive` default
  `false` per D3, `file.allowed_roots` default `[]` per D5, plus
  whatever D8/D9's final answers require). No existing key's meaning,
  default, or validation changes.

### DO NOT MODIFY

- `src/core/command_router.py` — zero changes (Section 5.3/9), **as
  originally scoped by this section. This blanket prohibition was
  later superseded, specifically and only for one narrowly-scoped
  Windows-path tokenization fix, by Owner Decision D11 (Section 20),
  approved during STEP 3 remediation — see `EP052_ARCHITECTURE_AUDIT.md`
  for the verified scope of that exception.**
- `src/core/tool/` — zero changes (Section 5.5/9, D9).
- `src/core/execution/` (EP-003) — zero changes; `FileExecutor`
  remains exactly as it is (Section 7.1).
- `src/skills/desktop/`, `src/skills/browser/` — zero changes
  (Section 7.1/7.2); in particular, `desktop screenshot`'s existing
  path-write behavior is left exactly as EP-050 shipped and audited
  it.
- Every prior EP's design/audit document.

### Dependencies that would need to change

- None (Section 10/D1) — `pathlib`/`os`/`shutil` are already part of
  the Python standard library; no `requirements.txt` change at all.

### Tests to be added

- `tests/EP052/test_file.py` (Section 16).
- Optionally, a small, separately-invoked
  `tests/EP052/test_file_platform_integration.py` for genuinely
  OS-specific manual verification (Windows junctions, real ACL
  permission errors) — smaller in scope than EP-050/EP-051's own
  integration suites, per Section 16's finding that most of
  `LocalFileBackend`'s logic needs no such separate tier at all.

### Configuration changes

- New `file:` block in `config/config.yaml` (Section 21/D3/D5/D8/D9
  pending final values).

### Documentation changes that should happen later (STEP 3/4, not now)

- `docs/architecture/JARVIS_ROADMAP.md` — update EP-052's status line
  once STEP 2 begins/completes, following EP-050/EP-051's own
  status-line format precedent exactly.
- `docs/BACKLOG.md` — update EP-052's entry analogously.
- `docs/architecture/audits/EP052_AUDIT.md` — created at STEP 4
  (Architecture Audit), not before.

None of the above has been performed during STEP 1. This section is a
plan only, per the task's explicit instruction.

---

## 22. Final Conclusion

EP-052 STEP 1 (Architecture Discovery, Technology Evaluation & Design)
is complete. This document found, by direct repository inspection,
that Jarvis today has almost no general file-management capability —
only `FileExecutor`'s OS-default-app launching (EP-003), one narrow,
unrestricted binary path-write inside `desktop screenshot` (EP-050),
and one domain-specific `shutil.copy2` backup call inside the
invoice/Fast-Response service — and that the `CommandModule`/
`CommandRouter`/Protocol-backend/fake-backend-testing/config-gate
pattern EP-050 and EP-051 both already established fits File
Automation's needs with no redesign, requiring zero new third-party
dependencies (Section 10/D1).

It also found that EP-052 is meaningfully riskier than either prior
Phase 8 EP in one specific respect the repository itself names
explicitly: `JARVIS_ARCHITECTURE_VISION.md`'s Human Approval principle
cites "Deleting files" by name (Section 5.1) — a materially stronger
signal than existed for EP-050's raw input or EP-051's browser
interaction. The owner has reviewed this finding and, in Owner
Decision D2, explicitly approved shipping controlled mutation
(`write`, `copy`, `move`, `mkdir`, `delete`) alongside read-only
observation (`list`, `exists`, `stat`, `read`) together in v1, rather
than deferring mutation to a later release. This document's
conservatism (Sections 11–13) is therefore expressed not by narrowing
the v1 action set, but by the layered security model every mutation
action remains subject to (Owner Decisions D3–D5, D7, D8): `file
.enabled` required and defaulting to `false`; an explicit,
default-empty allow-list of permitted root directories; a separate
`file.allow_destructive` gate for `move`/`delete`/overwrite; overwrite
refused by default; recursive directory deletion excluded from v1;
no shell execution, no arbitrary command execution, no subprocess-
based filesystem manipulation, and no bypass of any of these
boundaries under any configuration — without inventing a per-action
confirmation mechanism this EP is not authorized to build (Section
12). **EP-052 v1, as approved, is a controlled filesystem automation
capability, not a read-only filesystem viewer.**

**Owner Decision D2 (Section 20) is APPROVED**, as revised by the
owner in this review. **Owner Decisions D1 and D3–D10 remain
UNAPPROVED**, each with a stated recommendation and rationale, for
explicit owner review. No source file, test file, configuration file,
or dependency file has been created or modified as a result of
producing or revising this document — the only artifact created or
modified by EP-052 STEP 1 is this document itself,
`docs/architecture/designs/EP052_DESIGN.md`. `src/`, `tests/`,
`config/`, `requirements.txt`, `src/bootstrap.py`, `src/core/tool/`,
and every prior EP's design/audit document remain byte-identical to
their pre-EP-052 state. (This statement described the state of the
repository as of EP-052 STEP 1 only. It no longer applies to
`src/core/command_router.py`, which was modified during STEP 3
remediation under the explicit, narrowly-scoped authorization of
Owner Decision D11, Section 20 — see `EP052_ARCHITECTURE_AUDIT.md`
for the verified scope of that one exception.)

**STEP 2 (Implementation) has NOT begun** and will not begin until
Owner Decisions D1 and D3–D10 (Section 20) are also explicitly
reviewed and approved (or revised) in a separate prompt, per
`AI_DEVELOPMENT_PLAYBOOK.md`'s Prompt Strategy: "Never continue
automatically. Always wait for the user's approval." Approving D2
alone authorizes only what D2 itself governs (the v1 action set and
its read-only/mutation split); it does not authorize STEP 2 to begin
while D1/D3–D10 remain open.
