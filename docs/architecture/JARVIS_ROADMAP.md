# Jarvis Development Roadmap

Version: 2.0

Status: Active Development

---

# Vision

Jarvis is not a chatbot.

Jarvis is not a single Large Language Model.

Jarvis is an AI Operating System.

Its purpose is to orchestrate AI providers, project knowledge, memory, workflows, tools and autonomous agents through a unified architecture.

Every Engineering Package (EP) contributes one reusable architectural building block.

---

# Engineering Principles

Every EP must:

- extend the existing architecture
- preserve backward compatibility
- follow PROJECT_MANIFEST.md
- follow AI_GENERATION_STANDARD.md
- remain provider independent
- avoid duplicated functionality
- reuse existing infrastructure
- include automated tests
- deliver production-quality code

Large EPs may be implemented incrementally using sub-packages:

- EP-018.1
- EP-018.2
- EP-018.3
- ...

Sub-packages never replace the main EP number.

---

# Current Progress

## Completed

EP-001 Core Foundation

EP-002 Interactive Shell

EP-003 Process Manager

EP-004 Quality & Testing Framework

EP-005 Invoice Automation

EP-006 Fast Response Board

EP-007 Core Improvements

EP-008 Process Aliases

EP-009 Process Catalog

EP-010 Configuration Improvements

EP-011 Logging Improvements

EP-012 Core Refactoring

EP-013 AI Infrastructure Preparation

EP-014 AI Provider Manager

EP-015 AI Provider Integration

EP-016 Conversation Engine

EP-017 Prompt Engine

EP-018 Universal Context Engine

Completed sub-packages:

- EP-018.1 Context Engine Foundation
- EP-018.2 PROJECT_MANIFEST Integration
- EP-018.3 Repository Detection
- EP-018.4 Document Budget
- EP-018.5 Unified Prompt Budget
- EP-018.6 Conversation Budget
- EP-019 Project Index Engine
- EP-020 Retrieval Engine
- EP-021 Embedding Engine
- EP-022 RAG Engine
- EP-023 Memory Manager
- EP-024 Knowledge Base
- EP-025 Long-Term Memory
- EP-026 Semantic Search
- EP-027 Context Compression
- EP-028 Agent Framework
- EP-029 Planning Engine
- EP-030 Execution Engine
- EP-031 Tool Engine
- EP-032 Multi-Agent Collaboration
- EP-033 Workflow Engine
- EP-034 Scheduler
- EP-035 Automation Engine
- EP-036 Background Workers
- EP-037 Event Bus
- EP-038 Git Integration
- EP-039 GitHub Integration
- EP-040 Telegram Integration
- EP-041 Discord Integration
- EP-042 Email Integration

---

## Current

EP-051 Browser Automation — **COMPLETE** (STEP 1 Architecture
Discovery, Technology Evaluation & Design, STEP 2 Implementation &
Testing, STEP 3 Architecture Audit, STEP 4 Documentation Completion
all complete -- see docs/architecture/designs/EP051_DESIGN.md
(including its Section 21 owner-decision record, D1-D12) and
docs/architecture/audits/EP051_AUDIT.md. Verdict: **PASS WITH
FINDINGS** (one HIGH, three MEDIUM, three LOW -- see below; none
blocking, none fixed during STEP 4 per the audit's own "document, do
not fix" rule). Built as a new `browser` `CommandModule`
(`src/skills/browser/skill.py`) providing fifteen actions -- `launch`,
`close`, `goto`, `back`, `forward`, `reload`, `title`, `current-url`,
`page-text`, `exists`, `click`, `type`, `clear`, `press`,
`screenshot` -- plus `help`, for controlled browser lifecycle,
navigation, and single-element DOM interaction, dispatched through the
*existing*, unmodified `CommandRouter.dispatch()`, exactly as every
prior skill (`desktop`, `voice`, `system`, ...) already is: no second
dispatch mechanism, no change to `src/core/command_router.py`. A new
`BrowserBackend` protocol (`src/skills/browser/backend.py`) defines
the browser-automation contract; `PlaywrightBrowserBackend`
(`src/skills/browser/playwright_backend.py`, Owner Decision D1) is the
sole real implementation, built on Playwright's synchronous API
(`playwright==1.62.0`, replacing the previously-declared, unpinned,
and confirmed-unused `selenium` entry -- zero migration cost, since
nothing in the repository imported Selenium before EP-051). Genuinely
cross-platform by design (Owner Decision D11) -- no Windows-only guard
exists in `PlaywrightBrowserBackend`, unlike EP-050's own
`WindowsComputerUseBackend`, though Windows remains the intended
manual-verification target. `browser.enabled` defaults to `false`,
re-checked on every dispatched action (not only at registration),
guaranteeing zero backend interaction while disabled -- confirmed by
dedicated tests. No per-action human-confirmation framework was built
(Owner Decision D2), no domain allow-list exists (Owner Decision D6,
a disclosed, accepted v1 limitation), and no JavaScript execution,
download, upload, multi-session, or multi-tab capability exists
anywhere (Owner Decisions D7/D8/D5/D12) -- confirmed absent by direct
code inspection during the architecture audit, not merely by design
intent. `src/skills/desktop/` (EP-050), Tool Engine (`src/core/tool/`),
`src/core/command_router.py`, Agent Framework, Planning Engine, and
Plan Execution Engine are all confirmed byte-identical to their
pre-EP-051 state. `CommandRouter` was chosen over Tool Engine for the
same, now twice-independently-confirmed reason EP-050 already
established: `Tool.handler` remains zero-argument-only for every
action registered in the project. Tests: EP-051 105/0/0, entirely
deterministic against a `_FakeBrowserBackend`, no real browser process
required; a separate, intentionally unregistered
`tests/EP051/test_browser_integration.py` exists for manual,
real-browser verification, but the architecture audit found this
script itself misreports its own skip condition (see findings below)
and confirmed real Chromium execution remains unverified in the
development sandbox (`playwright install chromium` cannot complete
there -- the Playwright CDN is outside the sandbox's allowed network
egress list). Focused regression check: EP-031/044/045/050 all pass
unchanged; EP-046/049 reproduce the same pre-existing, sandbox-only
conditions already disclosed against EP-048/049 above, confirmed
unrelated to and unmodified by EP-051.

**Audit findings (verdict PASS WITH FINDINGS, none blocking, none
fixed during EP-051 -- see `EP051_AUDIT.md` Section 17 for full detail
and Section 21 for recommended follow-up):**

- **HIGH** -- the same pre-existing `CommandRouter.dispatch()` raw-
  input logging (`src/core/command_router.py`) EP050_AUDIT.md already
  documented for `desktop type`/`desktop write-clipboard` was
  independently re-confirmed for `browser type`'s typed text and
  `browser goto`'s URL (which may embed a token/credential as a query
  parameter) -- undermining EP051_DESIGN.md Section 12's "never
  logged" commitment end-to-end, even though `BrowserModule` itself
  never logs this content. Not introduced by EP-051; tracked as a
  follow-up item below, not fixed during EP-051.
- **MEDIUM (x3)** -- `PlaywrightBrowserBackend._call()`'s exception
  catch is narrower than `launch()`'s own, better-justified broad
  catch, risking an unnormalized exception on an in-session action
  failure (contained by `CommandRouter`'s own top-level catch-all, no
  crash); a `close()` failure may skip stopping the underlying
  Playwright driver subprocess while internal state is reset
  regardless; the unregistered real-browser integration script reports
  "FAILED" rather than "SKIPPED" when Playwright is installed but no
  browser binary has been downloaded -- the exact state of the
  development sandbox -- correcting the STEP 2 report's original
  "skips gracefully" claim.
- **LOW (x3)** -- no explicitly-named "double close"/"action after
  close" test scenario (the underlying code path is correct by
  inspection); raw Playwright exception message text (not type)
  reaches `CommandResult.message`, mirroring an already-accepted
  EP-050 precedent; `src/skills/browser/selenium_driver.py` (a 0-byte
  placeholder predating EP-051) was not deleted as
  EP051_DESIGN.md Section 22 proposed, and remains present, empty, and
  unimported.

EP-050 Computer Use — **COMPLETE** (STEP 1 Architecture Research,
Design & Owner Decisions, STEP 2 Implementation & Testing, STEP 3
Architecture Audit, STEP 4 Documentation Completion all complete --
see docs/architecture/designs/EP050_DESIGN.md (including its Section
30 owner-decision record, D1-D6, and its Section 32 STEP 1 Final
Review of the CommandRouter-vs-Tool-Engine decision) and
docs/architecture/audits/EP050_AUDIT.md. Verdict: **PASS WITH
FINDINGS** (one HIGH, one MEDIUM, four LOW, four INFO -- see below;
none blocking, none fixed during STEP 4 per the audit's own "document,
do not fix" rule). Built as a new `desktop` `CommandModule`
(`src/skills/desktop/skill.py`) providing raw, local, offline OS-level
input control -- `help`, `move`, `click`, `scroll`, `type`, `key`,
`read-clipboard`, `write-clipboard`, `screenshot`, `cursor`,
`screen-size`, `active-window`, `focus` -- dispatched through the
*existing*, unmodified `CommandRouter.dispatch()`, exactly as every
prior skill (`voice`, `system`, ...) already is: no second dispatch
mechanism, no change to `src/core/command_router.py`. A new
`ComputerUseBackend` protocol (`src/skills/desktop/backend.py`)
defines the OS-input contract; `WindowsComputerUseBackend`
(`src/skills/desktop/windows_backend.py`, PyAutoGUI-based, Owner
Decision D3) is the sole real implementation, honestly scoped as
Windows v1 (Owner Decision D5) rather than claiming cross-platform
support. `desktop.enabled` defaults to `false`, re-checked on every
dispatched action (not only at registration), guaranteeing zero
backend interaction -- including no `screen_size()` call for bounds
validation -- while disabled; a general per-action human-confirmation
framework was deliberately not built (no such mechanism exists
anywhere in the project today), a disclosed limitation carried
forward from Owner Decision D2, not fixed by EP-050. Tool Engine
(`src/core/tool/`), Agent Framework, Planning Engine, Plan Execution
Engine, `src/core/execution/` (EP-003's process/application launcher),
the EP-044 `desktop/` PySide6 GUI client (a distinct, unrelated
directory from `src/skills/desktop/` -- the two are never merged), and
`src/skills/browser/` (still empty, confirmed reserved for EP-051) are
all confirmed byte-identical to their pre-EP-050 state. `CommandRouter`
was deliberately chosen over Tool Engine for v1 because Tool Engine's
`Tool.handler` is zero-argument-only for every action already
registered in the project (a pre-existing, already-disclosed
limitation, not introduced by EP-050) -- this is documented as a
deferred architectural evolution (a future, dedicated "parameterized
Tool support" Engineering Package, left unscheduled and unnumbered by
this EP), not a permanent rejection. Tests: EP-050 112/0/0, entirely
deterministic against a fake backend, no real mouse/keyboard/screen/
PyAutoGUI/display required; a separate, intentionally unregistered
`tests/EP050/test_desktop_windows_integration.py` exists for manual,
real-hardware verification and correctly self-skips in a headless
environment. The architecture audit's one HIGH finding: `CommandRouter
.dispatch()`'s own pre-existing, unmodified raw-input logging
(`src/core/command_router.py`) logs the full command line on every
dispatch, including `desktop type`/`desktop write-clipboard`'s
sensitive argument content -- a shared-infrastructure behavior
pre-dating and extending beyond EP-050 (equally true of, e.g., `email
send`'s body or `git commit -m`'s message), not a defect in EP-050's
own code, but one that undermines EP050_DESIGN.md Section 19's
explicit "never logged" privacy commitment end-to-end; tracked as a
recommended follow-up (see docs/BACKLOG.md), not fixed during EP-050.
One MEDIUM finding (`WindowsComputerUseBackend.active_window_title()`
over-broadly swallows all exceptions into an empty-string return
rather than raising for genuine failures) and four LOW/four INFO
findings (click-argument ambiguity, no literal `'+'`-key support, no
partial-file cleanup on a failed screenshot write, no runtime
Windows-platform guard, a `runtime_checkable` Protocol signature-
checking limitation, `desktop.backend`'s intentional omission,
active-window-title logging) are recorded in full in
`EP050_AUDIT.md` Section 22 -- none blocking.)

EP-049 Voice Assistant — **COMPLETE** (STEP 1 Design & Owner
Decisions, STEP 2 Implementation & Verification, STEP 3 Architecture
Audit / Final Verification all complete -- see
docs/architecture/designs/EP049_DESIGN.md (including its Section 23a
final owner-decision record) and
docs/architecture/audits/EP049_AUDIT.md. Verdict: **PASS WITH
PRE-EXISTING ENVIRONMENT LIMITATION** (the limitation being an
EP-048-owned, sandbox-only `openwakeword`/`tflite-runtime` Linux
packaging quirk, unrelated to and unmodified by EP-049 -- see below).
Built as a strictly one-shot `voice wake assist` action, composed
into the *existing* `voice` `CommandModule`
(`src/skills/voice/skill.py`) alongside EP-048's `wake
listen`/`wake status` -- no second namespace, no new dispatch
mechanism, no change to `src/core/command_router.py`,
`src/core/api/`, Telegram, `desktop/`, or `web/`. On a wake-word
detection, `voice wake assist` stops the existing
`StreamingAudioCapture` wake stream and calls the existing, unmodified
`_listen()` directly -- the same method `voice listen` already
calls -- which owns EP-046's `AudioCapture`/STT, EP-046's existing
confidence gate, and `CommandRouter.dispatch()`. An optional TTS step
(EP-047's existing `TextToSpeechEngine`) may speak the dispatched
result. `_listen()`, `CommandRouter`, and `Bootstrap` are all
confirmed byte-identical to their pre-EP-049 state -- EP-049
introduces no second STT/wake/dispatch implementation, no new
`VoiceModule` constructor parameter, and no new dependency
(`requirements.txt` unchanged). Strictly one-shot by owner decision:
exactly one wake -> command -> result cycle per invocation, with no
loop, no repeat/continuous-listening configuration, no
Bootstrap-managed background thread or daemon, and no automatic
re-arming of wake listening -- a new invocation of `voice wake
assist` is required for another cycle. New configuration:
`voice.wake.assist.enabled` and `voice.wake.assist.speak_result`,
both defaulting to `false`; no `one_shot` key exists. Automated
tests: EP-049 87/0/1 (one disclosed skip -- the real-hardware
scenario, see below); EP-046 58/0/1 and EP-047 49/0/0 both fully
unchanged. On the real target Windows workstation, where
`openwakeword`'s `tflite-runtime` Linux-only constraint does not
apply, EP-048's own suite has been independently verified by the
project owner at **112 passed / 0 failed / 1 skipped** -- the two
failures seen in the Linux sandbox used for STEP 1-3 development
(`tflite-runtime` has no published distribution for that
platform/Python combination, confirmed unfixable from within the
sandbox) do not reproduce on the actual target machine and are not
an EP-049 regression. Manual, real-microphone/real-loaded-model
wake-to-dispatch verification (the full `voice wake assist` pipeline
end to end, not just EP-048's own wake-detection step) remains an
outstanding, disclosed item -- see `EP049_AUDIT.md` Section 14 for
the exact checklist.) EP-048
Wake Word remains **COMPLETE** (STEP 1-3 plus a post-STEP-3 real-
Windows-hardware bug fix, unchanged by EP-049 --
`src/skills/voice/wake_word.py` and
`src/skills/voice/streaming_audio_capture.py` confirmed byte-identical
to their EP-048-shipped state -- see
docs/architecture/designs/EP048_DESIGN.md (including its Section 9a
owner-decision record, Section 17 as-built summary, and Section 17.7
post-STEP-3 bug-fix account) and
docs/architecture/audits/EP048_AUDIT.md (Section 17, "Post-Audit Bug
Fix / Final Verification"). Verdict: **PASS** (updated from STEP 3's
original "PASS WITH DOCUMENTED LIMITATIONS" once real Windows
hardware verification closed the one limitation that was actually
EP-048's own -- an `openwakeword==0.6.0` Linux packaging quirk in the
automated-testing environment remains disclosed, unrelated to the
Windows target). Built as offline, `openWakeWord`-based
wake-phrase detection (`src/skills/voice/wake_word.py`) fed by a new,
separate `StreamingAudioCapture` component
(`src/skills/voice/streaming_audio_capture.py`, kept apart from
EP-046's existing fixed-duration `AudioCapture`, which was not
modified), composed into the *existing* `voice` `CommandModule`
(`src/skills/voice/skill.py`) as additive `wake listen`/`wake status`
actions -- no second namespace, no new dispatch mechanism, no change
to `src/core/command_router.py`, `src/core/api/`, Telegram,
`desktop/`, or `web/`. `voice wake listen` only ever reports a
detection: it never dispatches through `CommandRouter`, never starts
an STT (`voice listen`) cycle, never speaks via TTS, and never runs
as a background listener or daemon -- confirmed by dedicated
call-counting tests, not only by design. Supports English ("Hey
Jarvis") only; Russian and Uzbek wake-word detection are explicitly
out of scope (no offline wake-word model evaluated has first-class
support for either) and receive no special-case handling anywhere in
code. Model files are never downloaded automatically -- manual
placement only, mirroring EP-046's own Vosk precedent.
`voice.wake.enabled` defaults to `false`. This EP also **fully**
closed EP-047's own disclosed registration-gating limitation: STT,
TTS, and Wake Word can now each be enabled independently, with the
`voice` namespace registering whenever any one of the three is
enabled (previously, TTS-only operation was not reachable -- see the
audit document's Known Limitations for what remains disclosed).
Real microphone/real-loaded-model wake-word detection has since been
verified by a human on the actual target Windows workstation --
`voice wake status` reported the model available and `voice wake
listen` correctly detected "hey_jarvis" (scores 0.80 and 0.64 across
two runs). That same verification pass also surfaced and led to the
correction of a real model-filename-resolution defect (the
implementation originally looked only for a bare `hey_jarvis.onnx`
file; openWakeWord's own official models ship as
`hey_jarvis_v0.1.onnx` -- now resolved deterministically without any
automatic download) -- see the audit document's Section 17 for full
detail.) EP-047
Text-to-Speech remains **COMPLETE** (STEP 1-3, unchanged by
EP-048/EP-049 -- `src/skills/voice/text_to_speech.py` confirmed
byte-identical to its EP-047-shipped state; its own disclosed
TTS-only registration limitation is now resolved by EP-048's D6 fix,
recorded in both EPs' audit documents -- see
docs/architecture/designs/EP047_DESIGN.md and
docs/architecture/audits/EP047_AUDIT.md.) EP-046 Speech-to-Text
remains **COMPLETE** (STEP 1-3, unchanged by EP-047/EP-048/EP-049 --
`src/skills/voice/speech_to_text.py` and
`src/skills/voice/audio_capture.py` confirmed byte-identical to their
EP-046-shipped state -- see
docs/architecture/designs/EP046_DESIGN.md and
docs/architecture/audits/EP046_AUDIT.md.) EP-045 Web Dashboard
remains **COMPLETE** (STEP 1-3, unchanged by
EP-046/EP-047/EP-048/EP-049, `web/` confirmed absent from the EP-049
changeset -- see
docs/architecture/designs/EP045_DESIGN.md and
docs/architecture/audits/EP045_AUDIT.md.) EP-044 Desktop UI remains
**COMPLETE** (STEP 1-3, unchanged by
EP-045/EP-046/EP-047/EP-048/EP-049, `desktop/` confirmed absent from
the EP-049 changeset -- see
docs/architecture/designs/EP044_DESIGN.md and
docs/architecture/audits/EP044_AUDIT.md.) EP-043 REST API remains
**COMPLETE** (STEP 1-4, unchanged by
EP-044/EP-045/EP-046/EP-047/EP-048/EP-049 -- see
docs/architecture/designs/EP043_DESIGN.md and
docs/RELEASE_NOTES.md.)

**Next Engineering Package: EP-052 File Automation — NOT STARTED.**
No EP-052 design, research, or implementation work has begun.

---

# Roadmap

## Phase 1 — Core Platform

EP-001 Core Foundation

EP-002 Interactive Shell

EP-003 Process Manager

EP-004 Testing Framework

EP-005 Invoice Automation

EP-006 Fast Response Board

EP-007 Core Improvements

EP-008 Process Aliases

EP-009 Process Catalog

EP-010 Configuration

EP-011 Logging

EP-012 Refactoring

EP-013 AI Infrastructure

---

## Phase 2 — AI Core

✓ EP-014 AI Provider Manager

✓ EP-015 AI Provider Integration

✓ EP-016 Conversation Engine

✓ EP-017 Prompt Engine

✓ EP-018 Universal Context Engine

✓ EP-019 Project Index Engine

✓ EP-020 Retrieval Engine

✓ EP-021 Embedding Engine

✓ EP-022 RAG Engine

---

## Phase 3 — Memory

✓ EP-023 Memory Manager

✓ EP-024 Knowledge Base

✓ EP-025 Long-Term Memory

✓ EP-026 Semantic Search

✓ EP-027 Context Compression

---

## Phase 4 — Agent Framework

✓ EP-028 Agent Framework

✓ EP-029 Planning Engine

✓ EP-030 Execution Engine

✓ EP-031 Tool Engine

✓ EP-032 Multi-Agent Collaboration

---

## Phase 5 — Workflow Automation

✓ EP-033 Workflow Engine

✓ EP-034 Scheduler

✓ EP-035 Automation Engine

✓ EP-036 Background Workers

✓ EP-037 Event Bus

---

## Phase 6 — Integrations

✓ EP-038 Git Integration

✓ EP-039 GitHub Integration

✓ EP-040 Telegram Integration

✓ EP-041 Discord Integration

✓ EP-042 Email Integration

✓ EP-043 REST API

✓ EP-044 Desktop UI

✓ EP-045 Web Dashboard

---

## Phase 7 — Voice

✓ EP-046 Speech-to-Text

✓ EP-047 Text-to-Speech

✓ EP-048 Wake Word

✓ EP-049 Voice Assistant

---

## Phase 8 — Computer Automation

✓ EP-050 Computer Use

EP-051 Browser Automation

EP-052 File Automation

EP-053 Vision Integration

---

## Phase 9 — Intelligence

EP-054 Self Reflection

EP-055 Prompt Optimizer

EP-056 Capability Learning

EP-057 Memory Optimization

EP-058 Autonomous Planning

---

## Phase 10 — Jarvis Operating System

EP-059 Distributed Runtime

EP-060 Jarvis Operating System

---

# Architecture Evolution

Core Platform

↓

AI Provider Layer

↓

Conversation Engine

↓

Prompt Engine

↓

Universal Context Engine

↓

Project Index

↓

Retrieval

↓

Embeddings

↓

RAG

↓

Memory

↓

Agent Framework

↓

Tool Engine

↓

Workflow Engine

↓

Automation

↓

Voice

↓

User Interfaces

↓

Jarvis Operating System

---

# Engineering Package Policy

Large Engineering Packages should be implemented in multiple incremental iterations.

Example:

EP-018 Universal Context Engine

- EP-018.1 Foundation
- EP-018.2 Manifest Integration
- EP-018.3 Repository Detection
- EP-018.4 Document Budget
- EP-018.5 Unified Prompt Budget
- EP-018.6 Conversation Budget

EP-019 Project Index Engine

- EP-019.1 Repository Scanner
- EP-019.2 File Index
- EP-019.3 Chunk Generator
- EP-019.4 Metadata Builder
- EP-019.5 Incremental Index
- EP-019.6 Testing
- Status: Completed

This approach allows large architectural modules to evolve without changing the long-term roadmap.

---

# Current Objective

Jarvis evolves incrementally through Engineering Packages.

Only one major Engineering Package should be actively implemented at a time.

Each completed Engineering Package becomes a permanent architectural building block for future development.

The implementation order is defined by this roadmap.

The currently active Engineering Package is tracked separately by the engineering process and project documentation.

# Long-Term Goal

Build a provider-independent AI Operating System capable of:

- understanding software projects
- maintaining engineering knowledge
- retrieving relevant information
- planning complex tasks
- executing tools
- coordinating multiple AI providers
- orchestrating autonomous agents
- automating engineering workflows

The ultimate goal is to create a modular, reusable and extensible AI Operating System that remains independent of any single AI provider or technology.

# Notes

This roadmap defines the official long-term engineering direction of Jarvis.

The numbering of Engineering Packages is stable.

New functionality should normally be implemented as sub-packages (EP-XXX.Y) rather than renumbering the roadmap.

Completed EPs should not be redesigned unless an explicit architectural decision requires it.

End of document.