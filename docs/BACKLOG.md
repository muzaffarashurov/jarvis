# BACKLOG.md

Version: 1.0

Status: Active

---

# Current Backlog

## Next Engineering Package

### EP-055 — Prompt Optimizer

**NOT STARTED.** Per `docs/architecture/JARVIS_ROADMAP.md`'s Phase 9
sequencing, EP-055 (Prompt Optimizer) is the next Engineering Package
after EP-054's completion. No design, research, or implementation
work has begun.

### EP-054 — Self Reflection

STEP 1 (Architecture Discovery & Design), STEP 2 (Implementation &
Testing), STEP 3 (Architecture Audit), and STEP 4 (Finalization) all
complete. EP-054 is marked **COMPLETE / PASSED WITH FINDINGS** --
STEP 3's final verdict is **AUDIT PASSED WITH FINDINGS** (one
non-blocking MEDIUM finding and one non-blocking LOW finding,
documented and not fixed -- see below), not a clean, zero-finding
pass -- see `docs/architecture/audits/EP054_ARCHITECTURE_AUDIT.md`.
Full design, including Owner Decisions D1-D9 (Section 20):
`docs/architecture/designs/EP054_DESIGN.md`.

Unlike EP-050 through EP-053, EP-054's roadmap entry was a bare title
("Self Reflection") with no functional specification anywhere in the
repository beyond Phase 9's one-sentence, five-EP-wide goal. STEP 1
disclosed this gap explicitly and surveyed the existing architecture
(Conversation Engine, AI Provider Manager, Memory Manager, Agent
Framework's subsystem registry, Scheduler) to derive several
grounded candidate interpretations, recommending Owner Decision D1
= "Candidate A": on-demand session/conversation self-critique.

Built as a new `reflect` `CommandModule`
(`src/skills/reflection/skill.py`) providing `summary [count]` (ask
the configured AI provider to critique the last `count` messages of
the current conversation) and `recall [count]` (return previously
persisted critiques, most recent first) -- plus `help`, dispatched
through the *existing*, unmodified `CommandRouter.dispatch()` -- no
new dispatch mechanism, no Tool Engine change. Unlike
`desktop`/`browser`/`file`/`vision`, EP-054 introduces no new external
I/O surface and therefore no new backend Protocol (Owner Decision
D1) -- `ReflectionModule` instead composes three already-existing,
unmodified components directly via constructor injection:
`ConversationManager` (read-only -- `ReflectionModule` never appends
to or mutates a conversation), `ProviderManager`/`AIProvider` (via
`ProviderManager.get_current().ask()`, deliberately bypassing
`AIService`'s higher-level pipeline so a reflection request never
appends itself as a new turn in the very conversation being reflected
upon), and, optionally, `MemoryService` (only consulted when
`reflection.persist_to_memory` is enabled; `reflect recall` reports a
clear failure if persistence is requested but the Memory subsystem is
unavailable). v1 is strictly descriptive (Owner Decision D3): it
never autonomously changes any configuration, prompt, or other
component's behavior -- that remains explicitly reserved for later
Phase 9 EPs (Prompt Optimizer, Capability Learning, Autonomous
Planning) by the roadmap's own sequencing. No `Scheduler` integration
and no `AgentEngine.register_subsystem()` call exist in v1 (Owner
Decisions D5/D6 -- manual-only, `CommandModule` only). No new
dependency was introduced (Owner Decision D9's sibling finding in
Section 9 of the design).

Gated by `reflection.enabled` (default `false`, re-checked on every
dispatched action, matching `desktop.enabled`/`browser.enabled`/
`file.enabled`/`vision.enabled`'s own precedent), `reflection
.max_message_count` (default and cap: 20 -- an explicit `count`
argument exceeding it is refused, never silently reduced, mirroring
`vision.max_dimension`'s own "reject, never silently downscale"
convention), and `reflection.min_seconds_between_calls` (default 30
-- a simple, in-process rate limit bounding AI-provider cost from
rapid, repeated invocation; reset on restart, not a durable
cross-restart limit).

Owner Decisions D1-D9 are all confirmed correctly implemented, aside
from the two findings below: Candidate A scope, no new backend
Protocol (D1); no separate AI-provider/privacy gate beyond
`reflection.enabled` itself (D2); strictly descriptive output, no
autonomous effect on anything (D3); opt-in `MemoryService` persistence,
default `false` (D4); manual-only triggering, no `Scheduler`
integration in v1 (D5); no `AgentEngine` subsystem registration in v1
(D6); `max_message_count: 20`/`min_seconds_between_calls: 30` resource/
rate-limit defaults (D7); `CommandRouter` dispatch, no Tool Engine
redesign (D8); and no real-`AIProvider` integration test, since a live
provider call is not deterministic the way EP-053's real-Tesseract OCR
check was (D9).

Tests: **EP-054 76 passed / 0 failed / 0 skipped**, covering
argument-shape validation, the `reflection.enabled` gate (zero
downstream calls while disabled), `max_message_count` cap enforcement,
`min_seconds_between_calls` rate-limiting (using a fake, injected
clock, never a real `time.sleep()`), positive-path prompt/response
generation, negative cases (no provider available, provider raises an
error, empty conversation), `persist_to_memory` behavior, `help`/
unknown-action handling, `CommandRouter` dispatch equivalence, and
`Bootstrap` wiring -- all against fake `ConversationManager`/
`ProviderManager`/`MemoryService` stand-ins (Owner Decision D10's
sibling reasoning in the design: a real AI-provider call's
non-deterministic output makes it unsuitable for the primary,
always-green suite).

Full regression: **6339 passed / 2 failed / 3 skipped**. The 2
failures and 3 skips are the same, already-documented, pre-existing
EP-046/EP-048/EP-049 voice-stack/sandbox limitations recorded at
EP-053's own completion, independently re-verified during the STEP 3
audit and confirmed unrelated to, and unmodified by, EP-054.

**STEP 3 findings (documented, not fixed):**

1. **(MEDIUM, non-blocking)** `EP054_DESIGN.md`'s own Section 12
   explicitly committed to adding a real, non-fake `MemoryService`
   -backed test to the primary suite once Owner Decision D4 (opt-in
   Memory persistence) was approved. No such test exists in the
   registered suite -- every persistence-related test uses a fake
   `MemoryService` only. The STEP 3 audit independently built and ran
   a real `MemoryService`/`MemoryStore` integration probe and
   confirmed the actual integration (`reflect summary` persisting,
   `reflect recall` retrieving) works correctly end-to-end -- the
   finding is a test-coverage gap against a self-imposed design
   commitment, not a functional defect.
2. **(LOW, non-blocking)** `ReflectionModule._summary()`'s
   `max_message_count`-exceeded check currently runs *before* the
   `reflection.enabled` gate, so a caller can observe the configured
   cap's numeric value via an error message even while Self Reflection
   is disabled. The STEP 3 audit confirmed, using dummy
   `ConversationManager`/`ProviderManager` objects that raise on any
   call, that zero downstream calls occur in this case -- no gate or
   resource-limit bypass exists; only a non-secret, already-visible
   config value can be observed out of order.

Per the STEP 3 audit's own "record, do not fix" rule, and per this
STEP 4's instruction to write and update documentation only, no code
change was made to address either finding. See
`docs/architecture/audits/EP054_ARCHITECTURE_AUDIT.md` Section 15 for
full detail and evidence on both.

`src/core/command_router.py`, `src/core/tool/`,
`src/core/ai/provider.py`, `src/core/ai/provider_manager.py`,
`src/core/ai/conversation_manager.py`, `src/core/ai/conversation.py`,
`src/core/memory/`, `src/core/agent/`, `src/core/planning/`,
`src/core/scheduler/`, `src/services/ai_service.py`,
`src/services/memory_service.py`, and every Phase 7/8 skill
(`desktop`, `browser`, `files`, `vision`) are all confirmed unmodified
by EP-054.

### EP-053 — Vision Integration

STEP 1 (Architecture Discovery, Technology Evaluation & Design), STEP
2 (Implementation & Testing), STEP 3 (Architecture Audit), and STEP 4
(Finalization) all complete. EP-053 is marked **COMPLETE / PASSED
WITH FINDINGS** -- STEP 3's final verdict is **AUDIT PASSED WITH
FINDINGS** (one non-blocking MEDIUM finding, documented and not
fixed -- see below), not a clean, zero-finding pass -- see
`docs/architecture/audits/EP053_ARCHITECTURE_AUDIT.md`. Full design,
including Owner Decisions D1-D10 (Section 20):
`docs/architecture/designs/EP053_DESIGN.md`.

Built as a new `vision` `CommandModule` (`src/skills/vision/skill.py`)
providing local, read-only image interpretation -- `info` (image
metadata: width, height, format, color mode, file size) and `ocr`
(text extraction) -- plus `help`, dispatched through the *existing*,
unmodified `CommandRouter.dispatch()` -- no new dispatch mechanism, no
Tool Engine change. A new `VisionBackend` protocol
(`src/skills/vision/backend.py`) is the only interface `VisionModule`
depends on; `LocalVisionBackend` (`src/skills/vision/local_backend.py`)
is the sole real implementation, built on Pillow (image decoding) and
`pytesseract` (OCR, wrapping an external Tesseract binary). v1 is
local-only and CPU-only: no AI-provider/network path exists anywhere
in `src/skills/vision/`, and `src/core/ai/provider.py` is entirely
unmodified. Gated by `vision.enabled` (default `false`, re-checked on
every dispatched action) and an independent `vision.allowed_roots`
allow-list (empty blocks everything; no runtime coupling to
`file.allowed_roots`/`FileBackend`), plus resource limits
(`vision.max_file_size_mb`, `vision.max_dimension`) enforced inside
`LocalVisionBackend`. `info` never depends on the Tesseract binary
being installed (split availability, Owner Decision D8); only `ocr`
does.

Owner Decisions D1-D10 are all confirmed correctly implemented:
local-only scope/no AI-provider path (D1), `pytesseract` OCR engine
(D2), path-only image input (D3), independent path-safety model (D4),
`max_file_size_mb`/`max_dimension` resource limits (D5), CPU-only
operation (D6), `Pillow==12.1.1`/`pytesseract==0.3.13` dependency
approval (D7), split availability (D8), `CommandRouter` dispatch, no
Tool Engine redesign (D9), and fake-backend + real-Pillow testing with
real-Tesseract integration handled separately (D10).

Tests: **EP-053 58 passed / 0 failed / 0 skipped**, covering protocol
conformance and argument-shape/gate/path-safety/dispatch behavior
against a `_FakeVisionBackend`, plus real-Pillow filesystem/image
behavior (including resource-limit enforcement) against
`LocalVisionBackend`. A separate, intentionally unregistered
real-Tesseract OCR check (`tests/EP053/test_vision_ocr_integration.py`)
independently verified genuine end-to-end text recognition against a
freshly rendered image -- it is never imported by `test_vision.py`,
`test_module.py`, or `TestRegistry`.

Full regression: **6263 passed / 2 failed / 3 skipped**. The 2
failures and 3 skips are pre-existing EP-046/EP-048/EP-049
voice-stack/sandbox limitations (`openwakeword`/`tflite-runtime`
having no Linux wheel in this environment, and real-hardware-only
scenarios each EP's own design already documented as skippable),
independently re-traced to their root causes during the STEP 3 audit
and confirmed unrelated to, and unmodified by, EP-053.

**STEP 3 finding (MEDIUM, non-blocking, documented, not fixed):**
`LocalVisionBackend` currently enforces its `max_dimension` resource
limit *after* Pillow fully decodes the image (`image.load()`), rather
than before, as `EP053_DESIGN.md`'s own Owner Decision D5 specified.
The limit is still always enforced, and no oversized result is ever
returned to a caller -- the finding is a decode-cost-ordering
inefficiency, not a path-safety bypass, a limit that fails to apply,
or an unsafe result. Per the STEP 3 audit's own "record, do not fix"
rule, and per this STEP 4's explicit instruction not to modify source
code without an already-documented, approved remediation, no code
change was made to address this finding during STEP 4. See
`docs/architecture/audits/EP053_ARCHITECTURE_AUDIT.md` Section 15,
Finding 1, for full detail and evidence.

`src/core/command_router.py`, `src/core/tool/`,
`src/core/ai/provider.py`, `src/skills/desktop/`,
`src/skills/browser/`, and `src/skills/files/` are all confirmed
unmodified by EP-053.

### EP-052 — File Automation

STEP 1 (Architecture Discovery, Technology Evaluation & Design), STEP
2 (Implementation & Testing), STEP 3 (Architecture Audit with one
narrowly-scoped remediation), and STEP 4 (Finalization) all complete.
EP-052 is marked COMPLETE with verdict **PASS AFTER REMEDIATION** --
see `docs/architecture/audits/EP052_ARCHITECTURE_AUDIT.md`. Full
design, including Owner Decisions D1-D11 (Section 20):
`docs/architecture/designs/EP052_DESIGN.md`.

Built as a new `file` `CommandModule` (`src/skills/files/skill.py`)
providing 9 CRUD actions -- `list`, `exists`, `stat`, `read`, `write`,
`copy`, `move`, `mkdir`, `delete` -- plus `help`, dispatched through
the *existing*, unmodified `CommandRouter.dispatch()` -- no new
dispatch mechanism. A new `FileBackend` protocol
(`src/skills/files/backend.py`) is the only interface `FileModule`
depends on; `LocalFileBackend` (`src/skills/files/local_backend.py`)
is the sole real implementation, operating directly on the local
filesystem behind a layered security model: `file.enabled` (default
`false`, re-checked on every dispatched action), `file.allow_destructive`
(gating `move`/`delete`/overwrite separately from non-destructive
actions), `file.allowed_roots` (an explicit allow-list -- empty blocks
everything), `file.denied_paths` (excludes specific paths inside an
allowed root), path-traversal/absolute-path rejection, non-recursive
`delete`, and UTF-8-only file content.

Owner Decision D11 authorized one narrowly-scoped remediation during
the STEP 3 Architecture Audit: `src/core/command_router.py`'s command
tokenizer corrupted Windows-style backslash paths before they reached
`FileModule`; the minimal fix preserves them. This is the only source
file EP-052 modified outside `src/skills/files/`,

`src/bootstrap.py`, and `src/modules/test_module.py`.

Tests: EP-052 135/0/0 (`tests/EP052/test_file.py`) -- protocol
conformance and argument-shape/gate/path-safety/dispatch tests against
a `_FakeFileBackend`, plus real CRUD/overwrite/non-recursive-delete/
UTF-8 behavior against `LocalFileBackend` in a disposable
`tempfile.TemporaryDirectory()`, never the repository root or an
operator's home directory.

### EP-051 — Browser Automation

STEP 1 (Architecture Discovery, Technology Evaluation & Design), STEP
2 (Implementation & Testing), STEP 3 (Architecture Audit), and STEP 4
(Documentation Completion) all complete. EP-051 is marked COMPLETE
with verdict **PASS WITH FINDINGS** (one HIGH, three MEDIUM, three
LOW -- none blocking; see below and
`docs/architecture/audits/EP051_AUDIT.md` Section 17 for the full,
verbatim finding list). Full design:
`docs/architecture/designs/EP051_DESIGN.md` (including Section 21's
record of the twelve owner decisions, D1-D12). Full audit:
`docs/architecture/audits/EP051_AUDIT.md`.

Built as a new `browser` `CommandModule`
(`src/skills/browser/skill.py`) providing 15 actions -- `launch`,
`close`, `goto`, `back`, `forward`, `reload`, `title`, `current-url`,
`page-text`, `exists`, `click`, `type`, `clear`, `press`,
`screenshot` -- plus `help`, for controlled browser lifecycle,
navigation, observation, and single-element DOM interaction,
dispatched through the *existing*, unmodified
`CommandRouter.dispatch()` -- no new dispatch mechanism, no change to
`src/core/command_router.py`, `src/core/api/`, Telegram, `desktop/`
(the EP-044 PySide6 GUI client, a distinct, unrelated directory), or
`web/`. A new `BrowserBackend` protocol
(`src/skills/browser/backend.py`, 15 methods, exactly the v1 action
set) is the only interface `BrowserModule` depends on --
`PlaywrightBrowserBackend` (`src/skills/browser/playwright_backend.py`)
is the sole real implementation, built on Playwright's synchronous API
(Owner Decision D1). This replaced a previously-declared, unpinned
`selenium` dependency confirmed, by direct repository inspection, to
be entirely unused (zero imports anywhere in the project) --
`requirements.txt` now pins `playwright==1.62.0`, and the swap is a
from-scratch technology choice rather than a migration away from
working infrastructure, since nothing was ever built on Selenium.
Genuinely cross-platform by design (Owner Decision D11) -- no
`sys.platform`/OS-conditional branch exists anywhere in
`PlaywrightBrowserBackend`, unlike EP-050's own, deliberately
Windows-scoped `WindowsComputerUseBackend` -- though Windows remains
the intended v1 manual-verification target and no artificial
cross-platform complexity (extra config keys, per-OS test scaffolding)
was added.

`browser.enabled` defaults to `false` and is re-checked on every
dispatched action, not only at registration -- confirmed by dedicated
tests that zero backend calls occur while disabled, across all 14
backend-touching actions. No general per-action human-confirmation
framework exists or was added (Owner Decision D2, the same disclosed
gap EP-050 already carries forward, now independently reaffirmed
rather than resolved) -- disabled-by-default plus a single category
gate is v1's only safety mechanism. No domain allow-list exists (Owner
Decision D6) -- `browser.enabled: true` permits navigation to any
reachable URL, an explicitly approved and explicitly documented v1
limitation, not an oversight. No JavaScript execution, download,
upload, multi-session, or multi-tab/window-management capability
exists anywhere in `src/skills/browser/` (Owner Decisions
D7/D8/D5/D12) -- confirmed absent by direct grep during the
architecture audit, not assumed from design intent alone. Page text
extracted via `browser page-text` is returned as inert string data,
never re-interpreted as a command -- the audit confirmed no
observe-to-dispatch loop exists anywhere in the current codebase
(`src/core/agent/`, `src/core/planning/`, and
`src/core/plan_execution/` call `CommandRouter.dispatch()` nowhere at
all today), so the prompt-injection trust boundary EP051_DESIGN.md
Section 13 describes has no live enforcement gap to close in v1.

`Tool Engine` (`src/core/tool/`), `Agent Framework`, `Planning
Engine`, `Plan Execution Engine`, `src/core/execution/` (EP-003), and
`src/skills/desktop/` (EP-050) are all confirmed byte-identical to
their pre-EP-051 state -- EP-051 introduces no second Tool-execution
path and does not touch EP-050's own OS-input capability in any way.
`CommandRouter` was chosen over Tool Engine for the same reason
EP-050 already established, now independently re-confirmed by a
second EP: `Tool.handler` remains zero-argument-only for every action
already registered in the project -- recorded again as a deferred
architectural evolution, not a permanent rejection, and not something
EP-051 attempted to fix unilaterally.

Tests: EP-051 105/0/0, entirely deterministic against a
`_FakeBrowserBackend` (`tests/EP051/test_browser.py`), no real browser
process required anywhere in the normal suite. A separate,
intentionally unregistered `tests/EP051/test_browser_integration.py`
exists for manual, real-browser verification against a local, static
`file://` fixture page -- but the architecture audit found this
script's own environment-detection logic incomplete (see findings
below) and confirmed **real Chromium execution remains unverified**
in the development sandbox: `playwright install chromium` cannot
complete there because the Playwright CDN is outside the sandbox's
allowed network egress list. Focused regression check: EP-031/044/045/
050 all pass unchanged; EP-046 (a `vosk` import error) and EP-049 (one
pre-existing assertion failure) both reproduce identically against the
pristine, pre-EP-051 upload itself, confirming both are pre-existing,
sandbox-only conditions fully unrelated to EP-051.

**Audit findings (verdict PASS WITH FINDINGS, none blocking, none
fixed during EP-051 -- see `EP051_AUDIT.md` Section 17 for full detail
and Section 21 for recommended follow-up):**

- **HIGH** -- `CommandRouter.dispatch()`'s own pre-existing,
  EP-051-unmodified raw-input logging (`src/core/command_router.py`)
  logs the entire command line on every successful dispatch, including
  `browser type`'s typed text and `browser goto`'s URL (which may
  embed a session token or credential as a query parameter) --
  undermining EP051_DESIGN.md Section 12's "never logged" privacy
  commitment end-to-end, even though `BrowserModule` itself never logs
  this content. This is the identical defect class
  `EP050_AUDIT.md` already documented as HIGH for `desktop type`/
  `desktop write-clipboard` -- independently re-confirmed here rather
  than assumed EP-050-specific, and now affecting two EPs. Tracked as
  a follow-up item below, not fixed during EP-051.
- **MEDIUM** -- `PlaywrightBrowserBackend._call()` (used by 11 of 15
  actions) catches only Playwright's own `Error`/`TimeoutError` types,
  narrower than `launch()`'s own, deliberately broader
  `except Exception` catch and narrower than `backend.py`'s own stated
  "raise only `BrowserBackendError`" contract -- contained by
  `CommandRouter`'s top-level catch-all (no crash), but an
  inconsistency the class's own `launch()` method already shows
  awareness of without applying uniformly.
- **MEDIUM** -- `PlaywrightBrowserBackend.close()`'s failure path may
  leave the underlying Playwright driver subprocess unstopped while
  internal session state is unconditionally reset, permitting an
  uninformed `browser launch` retry with no indication a previous
  browser process may still be running.
- **MEDIUM** -- `tests/EP051/test_browser_integration.py` reports
  "FAILED" (exit code 1), not "SKIPPED", when Playwright's Python
  package is installed but no browser binary has been downloaded --
  the exact state STEP 2's own verification work left the development
  sandbox in. This corrects the STEP 2 report's original claim that
  the script "skips gracefully"; the underlying CDN-blocking
  limitation itself was accurately disclosed, but the script's own
  reporting of that specific state was not.
- **LOW (x3)** -- "double close" and "action after close" are not
  separately, explicitly named test scenarios, though the shared
  underlying code path is correct by direct inspection; raw Playwright
  exception message text (not type) reaches `CommandResult.message`,
  mirroring an already-accepted EP-050 precedent
  (`ComputerUseBackendError`'s identical construction) rather than a
  new pattern; `src/skills/browser/selenium_driver.py` (a 0-byte
  placeholder predating EP-051, superseded by Owner Decision D1's
  choice of Playwright) was not deleted as EP051_DESIGN.md Section 22
  proposed, and remains present, empty, and unimported.

### EP-050 — Computer Use

STEP 1 (Architecture Research, Design & Owner Decisions), STEP 2
(Implementation & Testing), STEP 3 (Architecture Audit), and STEP 4
(Documentation Completion) all complete. EP-050 is marked COMPLETE
with verdict **PASS WITH FINDINGS** (one HIGH, one MEDIUM, four LOW,
four INFO -- none blocking; see below and
`docs/architecture/audits/EP050_AUDIT.md` Section 22 for the full,
verbatim finding list). Full design:
`docs/architecture/designs/EP050_DESIGN.md` (including Section 30's
record of the six owner decisions, D1-D6, and Section 32's dedicated
STEP 1 Final Review of the CommandRouter-vs-Tool-Engine choice). Full
audit: `docs/architecture/audits/EP050_AUDIT.md`.

Built as a new `desktop` `CommandModule`
(`src/skills/desktop/skill.py`) providing 13 actions -- `help`,
`move`, `click`, `scroll`, `type`, `key`, `read-clipboard`,
`write-clipboard`, `screenshot`, `cursor`, `screen-size`,
`active-window`, `focus` -- for raw, local, offline OS-level mouse,
keyboard, clipboard, screenshot, and window-focus control, dispatched
through the *existing*, unmodified `CommandRouter.dispatch()` -- no
new dispatch mechanism, no change to `src/core/command_router.py`,
`src/core/api/`, Telegram, `desktop/` (the EP-044 PySide6 GUI client,
a distinct, unrelated directory never merged with
`src/skills/desktop/`), or `web/`. A new `ComputerUseBackend` protocol
(`src/skills/desktop/backend.py`, 12 methods, exactly the v1 primitive
set) is the only interface `DesktopModule` depends on;
`WindowsComputerUseBackend` (`src/skills/desktop/windows_backend.py`)
is the sole real implementation, PyAutoGUI-based (Owner Decision D3,
already declared in `requirements.txt` before EP-050, unused until
now -- no new top-level dependency added) and honestly scoped as
Windows v1 (Owner Decision D5) with every PyAutoGUI/pygetwindow/
pyperclip import deferred to `__init__` (confirmed necessary: a
top-level import crashes with `KeyError: 'DISPLAY'` in a headless
sandbox).

`desktop.enabled` defaults to `false` and is re-checked on every
dispatched action, not only at registration -- confirmed by dedicated
tests that zero backend calls occur while disabled, including that
`screen_size()` is never called for bounds validation before the gate
passes. No general per-action human-confirmation framework exists or
was added (Owner Decision D2, reaffirmed unfixed) -- disabled-by-
default is v1's only safety mechanism beyond argument/bounds
validation. `Tool Engine` (`src/core/tool/`), `Agent Framework`,
`Planning Engine`, `Plan Execution Engine`, `src/core/execution/`
(EP-003), and `src/skills/browser/` (confirmed still empty, reserved
for EP-051) are all confirmed byte-identical to their pre-EP-050
state -- EP-050 introduces no second Tool-execution path.
`CommandRouter` was chosen over Tool Engine specifically because
`Tool.handler` is zero-argument-only for every action already
registered in the project (a pre-existing, already-disclosed
limitation predating EP-050, confirmed by `src/core/tool/__init__.py`'s
own admission about four already-unregistered EP-029 actions) --
recorded as a deferred architectural evolution (a future, dedicated,
still-unscheduled "parameterized Tool support" Engineering Package),
not a permanent rejection.

Tests: EP-050 112/0/0, entirely deterministic against a
`_FakeComputerUseBackend` (`tests/EP050/test_desktop.py`), no real
mouse/keyboard/screen/PyAutoGUI/display required anywhere in the
normal suite; a separate, intentionally unregistered
`tests/EP050/test_desktop_windows_integration.py` exists for manual,
real-hardware verification on the actual target Windows workstation
and correctly self-skips (exit code 0) in a headless environment.
Focused regression check: EP-031/043/044/045/046/047/049 all pass
unchanged; EP-048 has 2 pre-existing, sandbox-only failures
(`openwakeword`'s `tflite-runtime` has no Linux wheel in the
development sandbox -- the same, already-disclosed condition recorded
against EP-049 above), confirmed unrelated to and unmodified by
EP-050.

**Audit findings (verdict PASS WITH FINDINGS, none blocking, none
fixed during EP-050 -- see `EP050_AUDIT.md` Section 22 for full
detail and Section 23 for recommended follow-up):**

- **HIGH** -- `CommandRouter.dispatch()`'s own pre-existing,
  EP-050-unmodified raw-input logging
  (`src/core/command_router.py`) logs the entire command line on every
  successful/errored dispatch, including `desktop type`/`desktop
  write-clipboard`'s sensitive argument content -- undermining
  EP050_DESIGN.md Section 19's "never logged" privacy commitment
  end-to-end, even though `DesktopModule` itself never logs this
  content. Shared-infrastructure behavior, equally true of every other
  module with a free-text argument (e.g. `email send`, `git commit
  -m`); tracked as a follow-up item below, not fixed during EP-050.
- **MEDIUM** -- `WindowsComputerUseBackend.active_window_title()`
  catches every exception (not only the documented "no active window"
  case) and silently returns `""`, deviating from `backend.py`'s own
  documented Protocol contract.
- **LOW (x4)** -- no literal `'+'`-key support in `desktop key`;
  `desktop click`'s trailing-argument parser silently resolves
  conflicting button names instead of rejecting them; no partial-file
  cleanup if a `desktop screenshot` write fails mid-way; no runtime
  `platform.system() == "Windows"` guard in
  `WindowsComputerUseBackend`.
- **INFO (x4)** -- `runtime_checkable` Protocol conformance checks
  verify method names only, not signatures (a Python language
  characteristic); `WindowsComputerUseBackend._call()` lacks an
  explicit return-type annotation; `desktop.backend` (a config key
  described in EP050_DESIGN.md Section 22) was intentionally not
  implemented since v1 has no backend-selection logic for it to feed;
  active window titles are logged in full (consistent with Section
  19's actual scope, which never listed window titles as a "never
  log" category).

### EP-049 — Voice Assistant

STEP 1 (Design & Owner Decisions), STEP 2 (Implementation &
Verification), and STEP 3 (Architecture Audit / Final Verification)
all complete. EP-049 is marked COMPLETE with verdict **PASS WITH
PRE-EXISTING ENVIRONMENT LIMITATION** (the limitation being an
EP-048-owned, sandbox-only `openwakeword`/`tflite-runtime` Linux
packaging quirk -- see below; not an EP-049 defect). Full design:
`docs/architecture/designs/EP049_DESIGN.md` (including Section 23a's
record of the seven owner decisions, D1-D7, that resolved STEP 1's
open questions). Full audit:
`docs/architecture/audits/EP049_AUDIT.md`.

Built as a strictly one-shot `voice wake assist` action, composed
into the *existing* `voice` `CommandModule`
(`src/skills/voice/skill.py`) as an additive sub-action alongside
EP-048's `wake listen`/`wake status` -- no new dispatch mechanism, no
second namespace, no change to `src/core/command_router.py`,
`src/core/api/`, Telegram, `desktop/`, or `web/`. On a wake-word
detection, `voice wake assist` stops EP-048's existing
`StreamingAudioCapture` wake stream (mandatory hand-off, confirmed by
a dedicated ordering test, not just by design) and calls the
existing, unmodified `_listen()` method directly -- the exact same
method `voice listen` already calls -- which owns EP-046's
`AudioCapture`/STT, EP-046's existing confidence gate, and
`CommandRouter.dispatch()`. An optional final step speaks the
dispatched result aloud via EP-047's existing `TextToSpeechEngine`,
off by default. `_listen()`, `CommandRouter`, and `Bootstrap` are all
confirmed byte-identical to their pre-EP-049 state by direct diff --
EP-049 introduces no second STT/wake/dispatch implementation, no new
`VoiceModule` constructor parameter (EP-049 configuration is read
directly from the existing `config` object), and no new dependency
(`requirements.txt` unchanged).

Strictly one-shot by owner decision (D2): exactly one wake -> command
-> result cycle per invocation, with no loop, no repeat/continuous-
listening configuration, no Bootstrap-managed background thread or
daemon (D1), and no automatic re-arming of wake listening -- a new
invocation of `voice wake assist` is required for another cycle. New
configuration: `voice.wake.assist.enabled` and
`voice.wake.assist.speak_result`, both defaulting to `false`; no
`one_shot` key exists (a loop/repeat mode was explicitly considered
and explicitly rejected for v1 -- see Owner Decision D2). A failed,
rejected, misunderstood, or low-confidence command is handled purely
through the existing `CommandResult`/`TranscriptionResult` error
mechanisms already established by EP-046 -- no retry loop,
confirmation dialog, or failure counter was added (Owner Decision
D7).

Tests: EP-049 87/0/1 (one disclosed, expected skip -- the real
end-to-end hardware scenario, no physical microphone or loaded model
available in the Linux sandbox used for STEP 1-3 development, exactly
mirroring EP-046/047/048's own precedent for their own real-hardware
scenarios); EP-046 58/0/1 and EP-047 49/0/0 both unchanged.

**Target-environment vs. sandbox test results.** All EP-049 STEP 1-3
work was performed in a Linux (Python 3.12) sandbox in which
`openwakeword==0.6.0` cannot be installed at all: its PyPI metadata
hard-requires `tflite-runtime` on Linux, and no distribution of
`tflite-runtime` exists for this platform/Python combination
(confirmed unfixable from within the sandbox, both via `pip install`
and via `pip index versions`). This causes exactly 2 of EP-048's own,
pre-existing tests (`test_wake_word.py`'s two model-file-error-message
assertions) to fail in that sandbox with 110/2/1 instead of clean --
a condition that already existed before any EP-049 code was written
and is fully unrelated to EP-049's own changeset (`requirements.txt`,
`wake_word.py`, and `streaming_audio_capture.py` are all confirmed
byte-identical to their pre-EP-049 state). On the real target Windows
workstation, where `tflite-runtime`'s Linux-only platform marker does
not apply, `openwakeword` installs and runs cleanly, and the project
owner has independently verified EP-048's suite there at **112 passed
/ 0 failed / 1 skipped** -- matching EP-048's own original,
pre-sandbox-limitation verified state (see `EP048_DESIGN.md`'s
"Current verified state" and `EP048_AUDIT.md`). A full-project
regression count on that same target environment has not yet been
independently reported to reconcile against this project's own
sandbox-verified full-suite count (5853 passed / 2 failed / 3
skipped, all 5853 successes and all 3 skips identical across both
environments, with the difference confined entirely to the same 2
EP-048 assertions above); arithmetically, closing those 2 on the
target environment would be expected to yield 5855 passed / 0 failed
/ 3 skipped, but this specific figure is a derived expectation, not
an owner-verified target-environment measurement, and is recorded
here as such rather than as a confirmed result.

Manual, real-microphone/real-loaded-model wake-to-dispatch
verification -- the full `voice wake assist` pipeline end to end (a
real "Hey Jarvis" utterance leading to a real transcribed command,
real dispatch, and optionally real spoken output), not just
EP-048's own already-verified wake-detection step in isolation --
remains an outstanding, disclosed item. See `EP049_AUDIT.md` Section
14 for the exact manual verification checklist.

*(EP-049's test suite (`tests/EP049/test_voice_assistant.py`) uses
deterministic fakes exclusively for wake-word scoring and audio
capture, precisely so its own 87/0/1 result is entirely unaffected by
the sandbox's `openwakeword` limitation described above -- none of
EP-049's own passing assertions depend on a real, loaded wake-word or
STT model.)*

### EP-048 — Wake Word

STEP 1 (Design & Research), STEP 2 (Implementation & Verification),
and STEP 3 (Documentation & Audit Closure) all complete, plus a
post-STEP-3 bug fix from real Windows hardware verification (see
below). EP-048 is marked COMPLETE with verdict **PASS** (updated from
STEP 3's original **PASS WITH DOCUMENTED LIMITATIONS** once real
hardware verification closed the one limitation that was actually
EP-048's own — see `EP048_AUDIT.md` Section 17). Full design:
`docs/architecture/designs/EP048_DESIGN.md` (including Section 9a's
record of the owner decisions that resolved STEP 1's open questions,
Section 17's as-built summary, and Section 17.7's account of the
post-STEP-3 fix). Full audit: `docs/architecture/audits/EP048_AUDIT.md`
(Section 17, "Post-Audit Bug Fix / Final Verification").

Built as offline, `openWakeWord`-based wake-phrase detection
(`src/skills/voice/wake_word.py`) fed by a new, separate
`StreamingAudioCapture` component
(`src/skills/voice/streaming_audio_capture.py`, kept apart from
EP-046's existing, fixed-duration `AudioCapture`, which was not
modified), composed into the *existing* `voice` `CommandModule`
(`src/skills/voice/skill.py`) as additive `wake listen`/`wake status`
actions -- no new dispatch mechanism, no second namespace, no change
to `src/core/command_router.py`, `src/core/api/`, Telegram,
`desktop/`, or `web/`. Actions: `voice wake listen` (starts
continuous detection, reports a single detection or a graceful
failure -- never dispatches, never starts STT, never speaks via TTS,
never runs as a background listener or daemon), `voice wake status`.
Supports English ("Hey Jarvis") only -- Russian and Uzbek wake-word
detection are explicitly out of scope (no offline wake-word model
evaluated has first-class support for either) and receive no
special-case handling anywhere in code. Model files are never
downloaded automatically -- manual placement under
`voice.wake.model_dir` only, mirroring EP-046's own Vosk precedent.
`voice.wake.enabled` defaults to `false`. This EP also fully resolved
EP-047's own disclosed registration-gating limitation
(Owner Decision D6): `Bootstrap` now registers the `voice` namespace
whenever any of `voice.enabled` (STT) / `voice.tts.enabled` /
`voice.wake.enabled` is true, so STT-only, TTS-only, and
Wake-Word-only operation are all independently reachable -- this
required widening `VoiceModule`'s `engine`/`audio_capture`
constructor parameters to `Optional`, with `voice listen`/`voice
transcribe`/`voice status` each reporting a clear failure (never a
crash) when STT is disabled. Tests: EP-048 112/0/1 (one disclosed,
expected skip -- see below); EP-043 83/83, EP-044 52/52, EP-045
38/38, EP-047 49/0/0 all unchanged.

**Post-STEP-3 bug fix (real Windows hardware verification):** the
first real-microphone/real-model verification of EP-048 found that
`OpenWakeWordEngine` looked only for a bare `<wake_word>.onnx` model
filename, while openWakeWord's own official pretrained models are
published with a version suffix (e.g. `hey_jarvis_v0.1.onnx`) -- so a
correctly installed, real model directory was still reported as
unavailable. A second, latent issue was found in the same pass:
prediction lookup needs the resolved model file's own key
(`"hey_jarvis_v0.1"`), not the shorter configured `wake_word`
(`"hey_jarvis"`). Both are fixed in `src/skills/voice/wake_word.py`
via a new, deterministic `resolve_wakeword_model_path()` (exact name
preferred, else exactly one versioned candidate; zero or multiple
candidates raise a clear error -- never a silent guess), with 9 new
regression tests. The configured logical wake word
(`voice.wake.wake_word: "hey_jarvis"`) did not change, and owner
Decision D3 (manual model placement, no automatic download) remains
fully honored. Real Windows verification subsequently confirmed
`voice wake status` reporting `Enabled: Yes`/`Model: available` and
`voice wake listen` correctly detecting "hey_jarvis" (scores 0.80 and
0.64 across two runs) -- the first genuine real-hardware confirmation
of EP-048 in this project's history. Only `src/skills/voice/wake_word.py`
and `tests/EP048/test_wake_word.py` were modified for this fix.

The one limitation that remains disclosed is unrelated to EP-048's
own implementation: `openwakeword==0.6.0` required a Linux-specific
installation workaround in the automated-testing environment used
across STEP 1-3 (its own PyPI metadata hard-requires `tflite-runtime`
on Linux, unavailable there); the actual Windows target never depends
on `tflite-runtime` and installed and ran correctly. See
`EP048_AUDIT.md` Section 17.6 for the updated final verdict and full
detail.

*(A separate, unrelated environment-dependent test issue was also
found and fixed in `tests/EP046/test_voice.py` during the same
real-hardware verification pass -- it is not an EP-048 regression and
is tracked under EP-046's own entry below, not here.)*

### EP-047 — Text-to-Speech

STEP 1 (Design & Research), STEP 2 (Implementation & Verification),
and STEP 3 (Documentation & Audit Closure) all complete. EP-047 is
now marked COMPLETE with verdict **PASS WITH DOCUMENTED
LIMITATIONS**. Full design: `docs/architecture/designs/EP047_DESIGN.md`
(including Section 9a's record of the owner decisions that resolved
STEP 1's open questions, and Section 17's as-built summary). Full
audit: `docs/architecture/audits/EP047_AUDIT.md`.

Built as an offline `pyttsx3`-based TTS engine
(`src/skills/voice/text_to_speech.py`) that speaks text through the
OS's native speech driver (SAPI5 on Windows), composed into the
*existing* `voice` `CommandModule` (`src/skills/voice/skill.py`) as
an additive `speak` action -- no new dispatch mechanism, no second
namespace, no change to `src/core/command_router.py`,
`src/core/api/`, Telegram, `desktop/`, or `web/`. Action: `voice
speak <text>`, joined from its arguments and spoken via a blocking
`engine.say()`/`engine.runAndWait()` call; never dispatches through
`CommandRouter` and never automatically speaks another command's
result. Supports English and Russian, contingent on a matching OS
voice being installed -- Uzbek is explicitly out of scope (no offline
TTS engine evaluated has a first-class Uzbek voice) and receives no
special-case handling anywhere in code: an unconfigured or
voice-less language always fails the same generic path, whether
that language is Uzbek or any other. `voice.tts.enabled` defaults to
`false`, independent of `voice.enabled` (STT) for failure-mode
purposes (a TTS construction failure never disables STT, and vice
versa) -- though the `voice` namespace itself remains registered only
when `voice.enabled` (STT) is also true, a disclosed, as-built
limitation (see `EP047_AUDIT.md` Known Limitations). Tests: EP-047
49/0/0; EP-043 83/83, EP-044 52/52, EP-045 38/38, EP-046 57/0/1 all
unchanged; full suite 5,655 passed / 0 failed / 1 skipped in this
verification run (an earlier-documented two-failure baseline for
EP-039/EP-041 was re-investigated and found to be an
environment-dependent, network-availability difference, not a code
regression -- see `EP047_AUDIT.md` Section 11 for detail).

Two disclosed, non-blocking gaps remain: no real Windows/SAPI5
audible speech has been confirmed by a human in any environment this
project has run in, and TTS-only operation (with STT/microphone
fully disabled) is not currently supported, due to the
registration-gating limitation above. Recommended as the first
manual-verification item, and a candidate small follow-up design
decision, once EP-047 reaches the actual target Windows workstation.
See `EP047_AUDIT.md` Section 13 for full detail.

### EP-046 — Speech-to-Text

STEP 1 (Design & Planning), STEP 2 (Implementation & Verification),
and STEP 3 (Documentation & Audit Closure) all complete. EP-046 is
now marked COMPLETE with verdict **PASS WITH DOCUMENTED
LIMITATIONS**. Full design: `docs/architecture/designs/EP046_DESIGN.md`
(including Section 9a/9b/9c's record of the owner decisions that
resolved STEP 1's open questions, and Section 16's as-built summary).
Full audit: `docs/architecture/audits/EP046_AUDIT.md`.

Built as an offline Vosk-based STT engine
(`src/skills/voice/speech_to_text.py`) plus a separate `sounddevice`
audio-capture layer (`src/skills/voice/audio_capture.py`), composed
by a new `voice` `CommandModule` (`src/skills/voice/skill.py`) that
dispatches recognized text through the existing, unmodified
`CommandRouter` -- no new dispatch mechanism, no `src/core/api/`,
Telegram, or `desktop/`/`web/` change. Actions: `voice listen`
(primary -- capture, transcribe, and dispatch if confident enough),
`voice transcribe` (capture and transcribe only, never dispatch),
`voice status`, `voice help`. Supports Russian, Uzbek, and English
via Vosk small models (`vosk-model-small-ru-0.22`,
`vosk-model-small-uz-0.22`, `vosk-model-small-en-us-0.15`), manually
installed under `voice.model_dir` -- none bundled in the repository.
`voice.enabled` defaults to `false`; low-confidence transcripts are
never auto-executed. Tests: EP-046 57/0/1 (one disclosed, expected
skip); EP-043 83/83, EP-044 52/52, EP-045 38/38 all unchanged; full
suite 5,641 passed / 2 failed (EP-039/EP-041, pre-existing and
independently confirmed unrelated to EP-046) / 1 skipped.

Two disclosed, non-blocking gaps remain, both stemming from the same
cause -- no Vosk model files and no physical microphone exist in any
environment this project has run in: no real audio has been
transcribed by a loaded model, and no real microphone capture has
been verified. Recommended as the first manual-verification item
once EP-046 reaches the actual target workstation. See
`EP046_AUDIT.md` Section 14 for full detail.

### EP-045 — Web Dashboard

STEP 1 (Design & Architecture Investigation), STEP 2
(Implementation), and STEP 3 (Documentation & Audit Closure) all
complete. EP-045 is now marked COMPLETE with verdict **PASS**. Full
design: `docs/architecture/designs/EP045_DESIGN.md` (including
Section 22a's record of the owner decisions that resolved STEP 1's
open questions). Full audit:
`docs/architecture/audits/EP045_AUDIT.md`.

As built: `web/public/{index.html, app.js, styles.css}` is a plain
HTML/CSS/JavaScript dashboard -- no framework, no build step, no new
dependency -- consuming EP-043's REST API exclusively, over
same-origin `fetch()` calls to `GET /health`, `GET /api/v1/status`,
and `POST /api/v1/commands` using relative URLs (no dashboard-side
API base URL configuration is needed, a direct consequence of
same-origin serving). Same-origin serving was implemented by adding
an **optional** `static_dir` capability to the existing
`RestApiServer` (`src/core/api/rest_api_server.py`) -- off by
default, gated by a new, opt-in `api.web_dashboard_dir` config key
(`config/config.yaml`) resolved in `src/bootstrap.py`. This was the
one `src/core/api/` change made in this EP, demonstrated as
technically necessary before being made (only one process can bind
`api.host:api.port`, and a CORS policy was ruled out by owner
decision) -- see `EP045_AUDIT.md` Section 6/7 for the verification.
No CORS policy, no authentication, and no network-exposure change
were introduced; EP-043's three existing routes and their behavior
are byte-identical to before this EP.

DEFERRED (see Non-Goals in `EP045_DESIGN.md`, and Future Ideas
below): chat, memory browser, agent management, workflow editor,
voice control, file management, notifications, authentication UI,
periodic health-check polling, command history, CLI-syntax command
input.

NON-BLOCKING LIMITATION (see `EP045_AUDIT.md` Section 5/14 for
detail): `web/public/app.js` and `styles.css` have no dedicated
automated unit test -- no JavaScript test runner exists in this
project. Both were verified working via a manual functional smoke
test during STEP 2. This does not affect correctness, security,
architecture, or any passing `test EP045` assertion.

OWNER DECISION REQUIRED (carried from STEP 1, still open): explicit
target-browser sign-off (STEP 1 proposed "current evergreen browsers
only"; STEP 2 implemented against that assumption but the owner has
not explicitly re-confirmed it as final).

Note: EP-044 — Desktop UI is now fully complete through STEP 3 (see
`docs/architecture/designs/EP044_DESIGN.md` and
`docs/architecture/audits/EP044_AUDIT.md`), and remains marked
complete in `docs/architecture/JARVIS_ROADMAP.md`, unchanged by
EP-045 (`desktop/` confirmed byte-identical to its pre-EP-045 state).
STEP 1 (Design & Architecture Investigation), STEP 2
(Implementation), and STEP 3 (Final Verification, Architectural
Audit & Documentation) all complete. EP-044 is now marked COMPLETE
with verdict **PASS WITH DOCUMENTED LIMITATIONS**. Full design:
`docs/architecture/designs/EP044_DESIGN.md`. Full audit:
`docs/architecture/audits/EP044_AUDIT.md`.

As built: `desktop/` is a new top-level package (a PySide6 MVVM
client, not nested under `src/`), consuming EP-043's REST API
exclusively over HTTP -- `desktop/api/jarvis_api_client.py` (built on
the already-existing `requests` dependency) is the only component
that talks to Jarvis, calling `GET /health`, `GET /api/v1/status`,
and `POST /api/v1/commands` unchanged. No file under `src/core/`,
`src/services/`, or `src/modules/` is imported by `desktop/`
business logic. Network calls run on a worker `QThread`
(`desktop/viewmodels/api_worker.py`) with results delivered back to
the UI thread via Qt signals, so the GUI event loop is never blocked.
Desktop configuration (host/port/timeout) is stored separately from
`config/config.yaml`, in a per-user YAML file
(`desktop/config/desktop_config.py`), matching the design's required
separation of client and server configuration. `PySide6==6.11.2` was
added to `requirements.txt` as the project's first-ever GUI
dependency; no other dependency changed.

DEFERRED (see Non-Goals in `EP044_DESIGN.md`, and Future Ideas
below): tray integration, desktop notifications, command history,
CLI-syntax command input, packaging/installer/executable generation,
authentication UI, chat/memory/agent browsers, workflow editor,
voice control, file management.

NON-BLOCKING LIMITATION (see `EP044_AUDIT.md` Section 5 for detail):
`EP044_DESIGN.md` Section 20 (Logging) specifies reusing the
project's `loguru` convention for connection attempts, state
transitions, and command submissions/results; the STEP 2
implementation does not yet call `loguru` anywhere in `desktop/`.
This does not affect correctness, security, architecture, or any
passing test, and is left for a small, separate follow-up rather
than folded into the STEP 3 audit gate.

OWNER DECISION REQUIRED (carried from STEP 1, still open): automatic
health-check polling cadence (STEP 2 implemented manual-only,
consistent with the design leaving this unresolved); target
platform(s) for future packaging (Windows/Linux/macOS); packaging
scope (own EP vs. EP-044 sub-package); ownership of the three
pre-existing, empty `src/ui/dashboard.py` / `tray.py` /
`notifications.py` placeholder files, which STEP 1, STEP 2, and
STEP 3 all confirmed remain untouched and byte-identical to their
pre-EP-044 state.

Note: EP-043 — REST API is now fully complete through STEP 4 (see
CHANGELOG.md / docs/RELEASE_NOTES.md), and remains marked complete in
docs/architecture/JARVIS_ROADMAP.md, unchanged by EP-044. STEP 1
(Investigation), STEP 2 (Implementation), STEP 3 (API Contract
Hardening), and STEP 4 (Finalization & Release Readiness) all
complete. Scope was confirmed directly by the project owner (the
STEP 1 investigation stopped because the repository established only
the title "REST API," with no purpose, consumers, endpoint surface,
security model, dependency, or lifecycle integration defined anywhere
-- see `EP043_STEP1_REPORT.md`). Full design:
`docs/architecture/designs/EP043_DESIGN.md`.

As built: `RestApiServer` (`src/core/api/rest_api_server.py`) is a
Bootstrap-level sibling of `InteractiveShell` -- not a
Core -> Service -> Module subsystem -- built entirely on the Python
standard library (`http.server`), with no new `requirements.txt`
dependency (at the time of EP-043; EP-044 subsequently added
`PySide6` for its own, separate Desktop client). It binds
`127.0.0.1:8080` by default and exposes three endpoints:
`GET /health`, `GET /api/v1/status`, `POST /api/v1/commands`.
`ApiRouter` (`src/core/api/api_router.py`) dispatches every command
request through the exact same `CommandRouter` instance
`InteractiveShell` and `TelegramRouter` already use -- no business
logic was added or duplicated. `api.enabled` defaults to `false`
(unlike EP-039/040/041's `true` default), a deliberate deviation from
the implementation prompt's illustrative `enabled: true` example:
unlike those stateless outbound clients, enabling this subsystem
binds and listens on a real network socket as a side effect of
`Bootstrap.initialize()`, so it stays off by default for safety and
to avoid port conflicts in the many existing EP-001..042 tests that
construct a real `Bootstrap` for wiring checks alone.

DEFERRED (see Non-goals in `EP043_DESIGN.md`, and Future Ideas below):
authentication/authorization, TLS, CORS, rate limiting, OpenAPI/Swagger
generation, WebSocket support, per-subsystem REST resources (v1 has
one generic command endpoint instead of e.g. dedicated
`/api/v1/email/...` routes).

STEP 3 (contract hardening, see `EP043_STEP3_REPORT.md`) added a
`415 Unsupported Media Type` response for `POST /api/v1/commands`
when `Content-Type` is present and not `application/json` (a missing
header is still treated leniently), and fixed a robustness gap where a
malformed `api.port` (wrong type or out of range) could raise an
uncaught exception during `Bootstrap.initialize()` instead of
degrading safely to "REST API disabled." No endpoint, status-code
policy, or configuration default changed.

Note: EP-042 — Email Integration is now fully complete through
STEP 4 (see CHANGELOG.md / docs/RELEASE_NOTES.md), and is now marked
complete in docs/architecture/JARVIS_ROADMAP.md. It is a new,
independent Core -> Service -> Module subsystem
(`src/core/email/`, `src/services/email_service.py`,
`src/modules/email_module.py`) exposing exactly four read-only
operations -- `list_folders()`, `list_messages(folder, limit)`,
`get_message(folder, uid)`, `search_messages(folder, criteria)` --
against a standard, provider-independent IMAP server, using the
Python standard library (`imaplib` + `email`) directly. No
send/reply/forward/delete/move/flag operation, no provider-specific
API (Gmail API, Microsoft Graph, Outlook API), no OAuth, and no
background polling exists anywhere in this subsystem.
Authentication uses two configurable environment-variable names
(default `EMAIL_IMAP_USERNAME`/`EMAIL_IMAP_PASSWORD`), read per-call
and never placed in config. `email.enabled` defaults to `false`
(unlike EP-039/040/041's `true` default), since IMAP has no safe
universal default host. `EmailService` has no dependency on any
other Engineering Package's service or engine.

SCOPE NOTE: EP-042 STEP 3 was a Deep Audit and returned a final
verdict of PASS WITH NOTES. Three defects were found and fixed (see
CHANGELOG.md "Fixed" section for v0.1.9-ep042), and no P0
(security/data-mutation) issue was identified. One pre-existing,
out-of-scope technical-debt item was recorded but deliberately left
unfixed: `TestRegistry`'s `NAME.upper()` keying means only one of
`EmailServiceTest`/`EmailModuleTest` is reachable via the CLI
`test EP042` command -- this predates EP-042, affects every prior
integration EP's Service/Module test pair as well, and should be
handled by a separate future maintenance EP. EP-043 deliberately
sidesteps this collision by registering a single `EP043` test suite
rather than a same-named Service/Module pair.

---

# Purpose

This document contains ideas, improvements, feature requests and future work that are not yet assigned to an Engineering Package.

Items in this document are not commitments.

They serve as a pool of potential future work.

---

# Rules

Items may be added at any time.

Items may be removed.

Items may later become Engineering Packages.

Priority may change.

---

# Current Backlog

## AI

- Improve project retrieval quality
- Support hybrid search
- Support code embeddings
- Improve provider selection
- Feed EP-022's assembled RAG context into the AI Provider Framework
  for chat completion (deliberately out of scope for EP-022 itself)

---

## User Experience

- Better shell autocomplete
- Command history search
- Improved progress indicators

---

## Tools

- Git integration improvements
- Local file watcher
- Background indexing
- REST API authentication/authorization (API keys, JWT, OAuth, RBAC) -- deferred from EP-043 v1
- REST API TLS/HTTPS support -- deferred from EP-043 v1
- REST API CORS configuration -- deferred from EP-043 v1
- REST API rate limiting -- deferred from EP-043 v1
- REST API OpenAPI/Swagger schema generation -- deferred from EP-043 v1
- Per-subsystem REST resources (e.g. dedicated /api/v1/email/... routes) -- deferred from EP-043 v1, which ships one generic /api/v1/commands endpoint instead
- TestRegistry NAME-collision fix (Service/Module test pairs sharing a NAME are only partially reachable via `test EP0NN`) -- pre-existing since EP-038, tracked again during EP-042 and EP-043
- `CommandRouter.dispatch()` raw-input logging exposes sensitive command arguments in full (e.g. `desktop type`/`desktop write-clipboard`'s text) -- HIGH finding from `EP050_AUDIT.md`, deferred from EP-050 v1; needs its own architectural decision on how a `CommandModule` can mark specific actions as sensitive before this is fixed at the `CommandRouter` level
- `WindowsComputerUseBackend.active_window_title()` should distinguish "no active window" from a genuine backend failure instead of swallowing all exceptions into an empty string -- MEDIUM finding from `EP050_AUDIT.md`, deferred from EP-050 v1

---

## Future Ideas

- Voice commands

- Browser automation

- Desktop assistant

- Plugin marketplace

---

End of document.