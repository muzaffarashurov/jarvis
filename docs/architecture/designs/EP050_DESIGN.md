# EP-050 — Computer Use — Design Specification (STEP 1)

**Status:** STEP 1 IN PROGRESS — ARCHITECTURE RESEARCH, DESIGN, AND
OWNER DECISIONS ONLY. No file under `src/`, `tests/`, or `config/`
was created or modified to produce this document, no dependency was
installed or added to `requirements.txt`/`pyproject.toml`, and no
previous Engineering Package was touched. This document is the
**only** file created in STEP 1, mirroring EP046/047/048/049's own
STEP 1 → Owner Decision → STEP 2 sequencing (see
`docs/architecture/designs/EP049_DESIGN.md`,
`docs/architecture/designs/EP048_DESIGN.md`). STEP 2
(implementation) has **not** started and will not start until the
project owner reviews Section 30 and gives explicit instruction.

---

## 1. Executive Summary

Per `docs/architecture/JARVIS_ROADMAP.md`'s Phase 8 sequencing
(EP-050 Computer Use → EP-051 Browser Automation → EP-052 File
Automation → EP-053 Vision Integration) and `docs/BACKLOG.md`'s own
"NOT STARTED" statement for EP-050, this document performs the
required STEP 1 research and design pass for **Computer Use**:
giving Jarvis the ability to control the local machine's mouse,
keyboard, clipboard, and window focus, and to observe basic screen
state, through the existing architecture.

Unlike EP-049 (which reused four already-complete subsystems end to
end), EP-050 has almost nothing to reuse at the implementation
level: `src/skills/desktop/{mouse,keyboard,clipboard,skill}.py` and
`src/skills/browser/{selenium_driver,skill}.py` are confirmed
**zero-byte placeholder files** — no existing input-control
abstraction, no existing keyboard/mouse wrapper, no existing
screenshot mechanism, and no existing OS-level safety-gating
mechanism exist anywhere in the repository today. `pyautogui` and
`selenium` are present in `requirements.txt` but are imported
nowhere in `src/` — pre-provisioned, not yet validated or approved
technology choices.

EP-050's own new work is therefore substantial relative to recent
voice EPs: one new `CommandModule` (`src/skills/desktop/skill.py`,
namespace `"desktop"`), one thin OS-input abstraction layer inside
`src/skills/desktop/` (fake-backed for automated tests, real-backed
via a Windows-capable library for the target machine), and — because
this capability can affect the real operating system — an explicit,
conservative safety boundary that this document defines rather than
assumes.

This document also resolves (or explicitly defers, as an Owner
Decision) seven architecture gaps identified during research:
parameterized Tool Engine support, the safety/confirmation
mechanism, the Computer Use technology backend, the
screenshot/observation boundary, Windows-only vs. cross-platform
abstraction, the Agent/Planning integration boundary, and the
`desktop/` vs. `src/skills/desktop/` naming collision.

---

## 2. Problem Statement

Jarvis's roadmap (`JARVIS_ROADMAP.md` Phase 8, `PROJECT_OVERVIEW.md`'s
high-level architecture) anticipates a "Computer Automation" phase
that lets Jarvis act on the operating system directly, not only
through already-integrated services (Git, GitHub, Telegram, Discord,
Email, REST API). Today, Jarvis has no way to move a mouse, type a
keystroke into an arbitrary application, read/write the system
clipboard, or observe what is currently on screen. `src/skills/
desktop/` and `src/skills/browser/` exist as placeholder packages
(confirmed empty), signalling this was already anticipated but never
built.

EP-050 must close the most fundamental part of this gap — raw input
control and basic observation — without prematurely absorbing
Browser Automation (EP-051), File Automation (EP-052), or Vision
Integration (EP-053), and without inventing a security model the
project does not actually have yet.

---

## 3. Roadmap Context

```
Phase 7 — Voice (COMPLETE)
  EP-046 Speech-to-Text ✓
  EP-047 Text-to-Speech ✓
  EP-048 Wake Word ✓
  EP-049 Voice Assistant ✓

Phase 8 — Computer Automation (ACTIVE, this document)
  EP-050 Computer Use            <- THIS DOCUMENT
  EP-051 Browser Automation      <- NOT STARTED, out of scope here
  EP-052 File Automation         <- NOT STARTED, out of scope here
  EP-053 Vision Integration      <- NOT STARTED, out of scope here

Phase 9 — Intelligence
  EP-054 … EP-058
```

No EP after EP-049 has any design, research, or implementation
artifact in the repository (`ls docs/architecture/designs/` ends at
`EP049_DESIGN.md`). EP-050 is confirmed the correct next package.

---

## 4. Goals

EP-050 delivers exactly the following, and no more:

1. A local, offline, provider-independent capability to:
   - move the mouse and click (left/right/double/scroll);
   - send keyboard input (text typing, single keys, hotkey
     combinations);
   - read and write the OS clipboard (text only);
   - capture a screenshot of the screen (raw pixel data only — no
     interpretation, no OCR, no vision model call);
   - report basic screen/window metadata (screen dimensions, cursor
     position, active window title) needed to make the above usable.
2. A `CommandModule` (`desktop`) exposing these actions through the
   existing, unmodified `CommandRouter.dispatch()` — the same entry
   point every interactive shell, Telegram, REST API, and voice
   command already goes through — so this capability is
   automatically available everywhere text commands already are,
   with zero changes to `CommandRouter`, `src/core/api/`, Telegram,
   Discord, `desktop/` (GUI), or `web/`.
3. A safety boundary appropriate to the *actual* current state of
   Jarvis's architecture (deterministic dispatch, no autonomous
   LLM-driven action loop yet) — not a speculative one built for an
   autonomy level Jarvis does not have.
4. A backend abstraction (`ComputerUseBackend` protocol) with one
   real Windows-capable implementation and one deterministic fake
   implementation, so the automated test suite never requires a
   physical mouse, keyboard, or screen.
5. Clear, explicit architectural boundaries against EP-051/052/053
   so none of their responsibilities are accidentally absorbed.

---

## 5. Non-Goals

EP-050 explicitly does **not** include:

- Browser automation, DOM interaction, or web scraping (Selenium is
  a declared dependency but is EP-051's concern; EP-050 does not
  import or configure it).
- File system automation (reading/writing/organizing files;
  EP-052's concern — distinct from clicking a File Explorer window,
  which EP-050 *does* cover as raw input).
- OCR or any text-from-image extraction.
- Visual reasoning, scene understanding, or any AI/vision-model call
  on a captured screenshot (EP-053's concern). A screenshot returned
  by EP-050 is an opaque image artifact; EP-050 never looks inside
  it.
- An autonomous computer-use agent, i.e. a loop where an AI decides
  and performs a sequence of computer actions on its own with no
  human in the loop per action. Today's Agent → Planning → Plan
  Execution chain is deterministic and keyword-rule-based (Section
  8.3); EP-050 exposes a *capability* through this existing chain
  and does not change that chain's autonomy level.
- Continuous/background automation loops, `Bootstrap`-managed
  daemons, or any hidden always-on input listener — every action is
  a single, explicit, operator- or dispatch-triggered invocation,
  mirroring EP-049 Owner Decision D1's "foreground only" precedent.
- Unrestricted shell/process execution — that already exists,
  narrowly, as EP-003's `ExecutionEngine` (Section 15) and is
  unrelated to and unmodified by EP-050.
- Cloud-dependent computer control of any kind. Every EP-050 action
  is 100% local and offline.
- A general-purpose confirmation/permission framework for all of
  Jarvis. EP-050 defines a narrow safety gate for its own action
  category only (Section 16), not a project-wide policy engine.
- Cross-platform parity. The real target is Windows (Section 9);
  EP-050 defines an abstraction that *could* grow other backends
  later but implements and verifies Windows only.

---

## 6. Existing Architecture (Repository Findings)

This section records what STEP 1 research actually found, following
`AI_GENERATION_STANDARD.md`'s "never invent APIs, never assume
capabilities exist" rule.

### 6.1 `PROJECT_MANIFEST.md` / governing documents

Read in full: `PROJECT_MANIFEST.md`, `AI_GENERATION_STANDARD.md`,
`docs/architecture/JARVIS_ROADMAP.md`,
`docs/architecture/JARVIS_ARCHITECTURE_VISION.md`,
`docs/architecture/NON_GOALS.md`,
`docs/architecture/PROJECT_OVERVIEW.md`,
`docs/architecture/ARCHITECTURE_DECISIONS.md`,
`docs/architecture/ARCHITECTURE_DEBT.md`,
`docs/engineering/ENGINEERING_GUIDE.md`, `docs/BACKLOG.md`.

Governing principles most relevant to EP-050:

- **Provider independence** (`JARVIS_ARCHITECTURE_VISION.md`,
  "Capability First"): Computer Use must be reachable as
  `Agent/Planner → Tool → Capability → OS`, never
  `<AI provider> → ComputerUse` directly. No file anywhere in the
  design may hardcode a specific AI provider.
- **Human Approval** (`JARVIS_ARCHITECTURE_VISION.md`, "Human
  Approval" section): *"Jarvis never performs irreversible actions
  automatically... Require user confirmation unless explicitly
  configured otherwise."* This is a real, standing architectural
  principle — but, per Section 6.4 below, **no mechanism currently
  implements it anywhere in the codebase**. EP-050 is the first
  package for which this principle has teeth, and must decide how
  far to go (Section 16/17).
- **Single Source of Truth / no duplicated state**
  (`ARCHITECTURE_DECISIONS.md` ADR-004/ADR-005): any new OS-input
  abstraction must not re-implement something `src/core/execution/`
  (EP-003) already owns (Section 15).
- **Documentation First** (ADR-014): this document precedes any
  code, matching every prior EP.
- **Unknown API Policy** (`AI_GENERATION_STANDARD.md`): confirmed
  followed throughout Section 6 — every gap below is stated as a
  gap, not silently worked around.

### 6.2 EP-049 Voice Assistant (most recent completed EP)

Read in full: `docs/architecture/designs/EP049_DESIGN.md` (1016
lines), `docs/architecture/audits/EP049_AUDIT.md` (481 lines), and
the real implementation files it describes
(`src/skills/voice/skill.py`, `speech_to_text.py`,
`text_to_speech.py`, `wake_word.py`, `streaming_audio_capture.py`,
`audio_capture.py`).

Patterns EP-050 directly inherits from EP-049 (and the voice EPs
generally):

- **One `CommandModule` per capability area**, registered under one
  namespace, with sub-actions dispatched by a private `_dispatch()`-
  style method (`VoiceModule` dispatches `listen`/`transcribe`/
  `status`/`wake ...`/`speak` this way). EP-050 will follow the same
  shape for a `desktop` namespace.
- **Reuse of existing objects via constructor injection**, never
  instantiated inside business logic (Dependency Policy).
  `VoiceModule.__init__` takes already-built engine/capture objects;
  `Bootstrap` is the only place that constructs them. EP-050's
  `DesktopModule` will follow the identical shape: it takes an
  already-built `ComputerUseBackend` instance, never constructs one
  itself.
- **Fakes, not mocking frameworks, for hardware-touching
  dependencies.** `tests/EP046/test_voice.py` defines
  `_FakeSpeechToTextEngine`/`_FakeAudioCapture` — plain classes
  implementing the same shape as the real engine, returning
  pre-canned results, never touching real hardware
  (`sounddevice`/Vosk). EP-050's automated tests will follow this
  exact pattern for mouse/keyboard/screen (Section 25).
- **No new permission/security layer invented per EP.** EP-049's own
  Section 17 states plainly: *"Does EP-049 add a new permission
  boundary? No... because no existing per-source authorization
  distinction... exists in `CommandRouter` today to extend."* This
  precedent supports EP-050 also *not* inventing a new
  general-purpose authorization framework — but EP-050's action
  category (real OS-level side effects) is materially different in
  kind from EP-049's (transcribe-and-dispatch text), so Section 16/17
  below designs a narrow, EP-050-specific safety gate rather than
  reusing this "no new layer" precedent wholesale.
- **`Bootstrap`, `CommandRouter`, and prior EPs' files are never
  modified beyond additive registration.** EP-049 confirmed this by
  direct diff (`_listen()`, `CommandRouter`, `Bootstrap` byte-
  identical pre/post). EP-050 commits to the same standard (Section
  27).
- **Owner Decisions are resolved by explicit table, before STEP 2,
  never silently.** EP-049 Section 23/23a is the template Section 30
  of this document follows.

### 6.3 Tool Engine (EP-031) — `src/core/tool/`

Read in full: `tool.py`, `tool_engine.py`, `tool_provider.py`,
`tool_manager.py`, `tool_registry.py`, `tool_execution_provider.py`,
`tool_result.py`, `__init__.py`.

Confirmed structure:

```python
@dataclass(frozen=True)
class Tool:
    id: str
    name: str
    description: str
    subsystem: str | None
    action: str
    handler: Callable[[], object]   # <-- zero-argument, confirmed
    enabled: bool = True
```

`ToolEngine.invoke(tool_id)` and `invoke_for_step(subsystem, action)`
call `provider.invoke_tool(tool)` → `DefaultToolProvider.invoke_tool`
calls `tool.handler()` with **no arguments**. There is no path,
anywhere in `src/core/tool/`, to pass a parameter (coordinates, text,
key name) into a tool invocation.

This is **not a new problem EP-050 introduces** — it is a
**pre-existing, already-disclosed gap**. `src/core/tool/__init__.py`
itself documents it for EP-029's own actions:

> *"several of EP-029's recognized actions (`generate_embedding`,
> `retrieve_context`, `semantic_search`, `compress_context`) require
> a text parameter that neither `PlanStep` nor
> `PlanExecutionProvider.execute_step()` currently carries... it
> registers real, built-in tools only for the parameter-free
> actions... and leaves the remaining four genuinely unregistered."*

So even today, **zero parameterized actions of any kind** are wired
through Tool Engine — this is not specific to Computer Use. Widening
`Tool`/`PlanStep`/`PlanExecutionProvider.execute_step()`'s schema to
carry a parameter is an EP-029/EP-030/EP-031 architecture change,
explicitly out of scope for a "reuse existing architecture, don't
redesign it" EP. See Section 12 and Owner Decision D1.

### 6.4 Agent Framework (EP-028) / Planning (EP-029) / Plan Execution (EP-030)

Read in full: `src/core/agent/__init__.py` (+ `agent_engine.py`,
`agent_provider.py`), `src/core/planning/__init__.py`,
`src/core/plan_execution/__init__.py`.

Confirmed:

- **Agent Framework (EP-028)** is lifecycle + subsystem registry +
  synchronous request acknowledgment *only*. Its own docstring: *"NOT
  ... a Planner, Reasoning Engine, Reflection Engine... Tool
  Executor."* It does not itself decide or perform any action.
- **Planning Engine (EP-029)**'s `DefaultPlanningProvider` builds a
  `Plan` using *"only deterministic, fixed keyword rules, and never
  AI reasoning, an AI provider call."* There is no LLM-driven,
  free-form planning in the codebase today.
- **Plan Execution Engine (EP-030)** dispatches `PlanStep`s in order,
  to a pluggable `PlanExecutionProvider` — again, *"must NOT call an
  AI provider... or invoke a real subsystem action"* itself; that is
  delegated further, to Tool Engine (Section 6.3) via
  `ToolExecutionProvider`.

**Conclusion:** Jarvis today has no autonomous "the AI decided to
click here" pathway of any kind — every action, voice or typed,
ultimately traces back to a human typing (or speaking) an explicit
command that `CommandRouter.dispatch()` resolves deterministically.
This materially changes what "security boundary" needs to mean for
EP-050 v1 (Section 16): the practical risk is *"an operator (or
whatever else can reach `CommandRouter.dispatch()`, e.g. Telegram,
REST API, voice) can trigger an OS input action,"* not *"an
autonomous AI loop can chain OS input actions unsupervised"* — the
latter genuinely does not exist yet and EP-050 must not design as if
it does (Section 8.3, Owner Decision D2 references this directly).

### 6.5 `CommandRouter` (`src/core/command_router.py`)

Read in full (158 lines). Confirmed:

- `CommandModule` is a `Protocol` with exactly `name: str` and
  `execute(action: str, arguments: list[str]) -> CommandResult`.
- `CommandResult` is `(success: bool, message: str, should_exit:
  bool = False)` — a plain two-state result model, no rich error
  taxonomy (no `TIMEOUT`, `UNAVAILABLE`, `PERMISSION_DENIED` as
  distinct types anywhere in the router or any existing module).
- Dispatch already carries **string arguments**
  (`dispatch("desktop click 500 300")` → `action="click"`,
  `arguments=["500", "300"]`), exactly the mechanism every existing
  module (`system`, `voice`, prospectively `desktop`) already uses
  for parameters. This is the key finding resolving most of the
  "parameterized" concern (Section 12): **`CommandRouter` already
  supports parameterized actions** — the zero-argument constraint is
  specific to Tool Engine's `Tool.handler`, not to command dispatch
  in general.
- `CommandRouter.dispatch()` never validates or authorizes an action
  beyond "does this module/action exist" — confirmed identical to
  EP-049's own finding (Section 6.2).
- Zero changes required to this file for EP-050 (Section 27).

### 6.6 `src/core/execution/` (EP-003) — pre-existing OS-level launcher

Read in full: `engine.py`, `executor.py`, `models.py`,
`process_registry.py`, `executors/`.

Confirmed: `ExecutionEngine.run(raw_target)` (via pluggable
`Executor`s) *opens* processes, scripts, files, and URLs, and tracks
them by PID through `ProcessRegistry`. This is **launching whole
programs/targets**, not driving input inside an already-running
program. It is a load-bearing dependency of Invoice, Process,
Scheduler, Workflow, and Plugin subsystems and is explicitly **not**
duplicated by EP-050 (Section 15 draws the exact boundary).

Notably, `src/core/plan_execution/__init__.py` itself flags a naming
collision risk with the *unrelated* roadmap "Execution Engine" name
— evidence this project already actively works to prevent
architecture-concept confusion. EP-050's `desktop/` vs.
`src/skills/desktop/` collision (Section 13) is the same category of
risk and is handled the same way: named and disambiguated explicitly
in this document and in code docstrings, never silently merged.

### 6.7 `src/skills/desktop/` (target package for EP-050)

`clipboard.py`, `keyboard.py`, `mouse.py`, `skill.py` — **all
confirmed 0 bytes.** No existing abstraction, no existing class, no
existing method signature to reuse or extend. EP-050 is filling this
package from a genuinely empty state — every class/method introduced
here is new (not a redesign of something existing), which is
architecturally permitted (`AI_GENERATION_STANDARD.md`'s "never
duplicate... never redesign" rules apply to *existing* things; there
is nothing existing here to redesign).

### 6.8 `src/skills/browser/`

`selenium_driver.py`, `skill.py` — **also confirmed 0 bytes.**
Confirms EP-051 (Browser Automation) is genuinely unstarted and
unrelated to `src/skills/desktop/`. EP-050 does not touch this
package (Section 27).

### 6.9 `desktop/` (root-level, EP-044 Desktop UI) — naming collision

See Section 13 for the full treatment. Summary: `desktop/` is a
PySide6 GUI *client* of the REST API (`desktop/__init__.py`:
*"communicates with Jarvis exclusively over HTTP... never imports
`src.core`, `src.services`, `src.modules`, or `src.bootstrap`"*). It
has no relationship to OS-level input control and is untouched by
EP-050.

### 6.10 Testing conventions (`src/testing/`, `tests/EP046`–`EP049`)

`src/testing/base_test.py` defines `BaseTest(ABC)` with a `run() ->
TestResult` contract and built-in assertion helpers — every EP's test
suite (`tests/EP0XX/test_*.py`) subclasses this. Hardware-touching
dependencies are never mocked with a mocking library; they are
replaced with small, explicit `_Fake*` classes matching the real
class's shape (confirmed in `tests/EP046/test_voice.py`,
`_FakeSpeechToTextEngine`/`_FakeAudioCapture`). EP-050 follows this
exact convention (Section 25).

### 6.11 Configuration / logging conventions

`config/config.yaml` is a single flat-ish YAML file with one
top-level key per subsystem (`agent:`, `planning:`, `tool:`, `voice:`,
etc.), each block commented with which EP owns it, what it does, and
what it explicitly does *not* do (mirroring the docstring style used
throughout `src/`). `config/logging.yaml` is confirmed empty — actual
logging configuration (`level`, `retention_days`, `console_enabled`)
lives under `config.yaml`'s `logging:` key and is read via `Config`,
not a separate logging config file. Every subsystem uses `loguru`
(`from loguru import logger`) directly — no separate logging
abstraction exists. `AI_GENERATION_STANDARD.md`'s Logging Policy
applies verbatim: log important events (started/stopped/failed
equivalents), never log secrets/passwords/tokens. EP-050 extends
this with a clipboard-specific rule (Section 19).

---

## 7. Existing Components Reused

| Component | Package | Reused as |
|---|---|---|
| `CommandModule` protocol | `src/core/command_router.py` | `DesktopModule` implements it, unchanged |
| `CommandRouter.dispatch()` | `src/core/command_router.py` | Sole dispatch path; zero changes |
| `CommandResult` | `src/core/command_router.py` | Return type for every `desktop ...` action |
| `Config` | `src/core/config.py` | `desktop.*` keys read the same way `voice.*` is |
| `BaseTest` / `TestResult` / assertions | `src/testing/` | `tests/EP050/test_desktop.py` base class |
| `loguru` logger | project-wide convention | Action/result logging (Section 19) |
| Fake-class testing pattern | `tests/EP046/test_voice.py` precedent | `_FakeComputerUseBackend` (Section 25) |
| `ToolEngine`/`Tool` (optionally, deferred) | `src/core/tool/` | Only for zero-argument, informational actions (Section 12) |

Nothing from `src/core/execution/` (EP-003), `src/skills/browser/`
(empty, unrelated), or `desktop/` (EP-044 GUI, unrelated) is reused
— each is a deliberate non-dependency, explained in Sections 6.6,
6.8, 6.9 respectively.

---

## 8. Computer Use Definition

Per the task's own framing, "Computer Use" is split into three
categories, each evaluated for EP-050 inclusion:

### 8.1 Input (state EP-050 reads to make decisions about *how* to act)

| Capability | In EP-050? | Reason |
|---|---|---|
| Cursor position | Yes | Needed to verify/report where an action occurred; trivial, offline, no privacy concern |
| Screen dimensions | Yes | Needed to validate coordinates before acting (bounds-checking, Section 17) |
| Active window title | Yes | Minimal window awareness needed for basic usability and logging context; does **not** require full window enumeration/management |
| Full window list / window management (move, resize, minimize, enumerate all windows) | **No — deferred** | Not required for raw input control; a real but separate capability, flagged as a possible EP-050.1 sub-package, not blocking v1 (Owner Decision D6 territory only if the owner wants it pulled in) |

### 8.2 Actions (what EP-050 can *do*)

| Capability | In EP-050? | Reason |
|---|---|---|
| Move mouse | Yes | Core capability |
| Click (left/right/double) | Yes | Core capability |
| Scroll | Yes | Core capability |
| Type text | Yes | Core capability |
| Press single key / hotkey combination | Yes | Core capability |
| Read clipboard | Yes | Core capability (Section 19 privacy treatment) |
| Write clipboard | Yes | Core capability |
| Screenshot (capture only) | Yes | Raw pixel capture, see Section 18 |
| Activate/focus a specific window by title | Yes, minimal | Needed to make click/type usable in practice; does not include resize/move/minimize |
| Launch/open an application or file | **No** | `src/core/execution/`'s job (Section 15) |
| Drag-and-drop (multi-step gesture) | **No — deferred** | Composable from move+press+move+release primitives EP-050 does provide; not itself a v1 primitive, to keep the action surface minimal per YAGNI (`AI_GENERATION_STANDARD.md`) |

### 8.3 Observation (what EP-050 returns *about* what happened)

| Capability | In EP-050? | Reason |
|---|---|---|
| Screenshot raw bytes/dimensions | Yes | Section 18 |
| Cursor position after action | Yes | Verification signal |
| Success/failure + message | Yes | Standard `CommandResult` shape |
| Any interpretation of screenshot content (OCR, "what's on screen", element detection) | **No** | EP-053's job, explicitly (Section 18/26) |

**What "Computer Use" means for EP-050, precisely:** a local,
synchronous, single-action-at-a-time capability to move/click/
scroll/type/press-keys/read-write-clipboard/screenshot/focus-a-
window, dispatched exactly like any other Jarvis command, with no
interpretation of what is observed and no autonomous chaining of
actions beyond what an existing deterministic Plan (Section 12) can
already express.

---

## 9. Architecture Proposal

```
CommandRouter.dispatch("desktop <action> [args...]")
        |
        v
DesktopModule (CommandModule, "desktop" namespace)
  src/skills/desktop/skill.py
        |
        v
ComputerUseBackend (Protocol / ABC)
  src/skills/desktop/backend.py
        |
        +---> WindowsComputerUseBackend   (real, Section 24)
        |       src/skills/desktop/windows_backend.py
        |
        +---> (tests only) _FakeComputerUseBackend
                tests/EP050/test_desktop.py
```

This mirrors the exact shape of `VoiceModule` → `SpeechToTextEngine`
(EP-046) and `VoiceModule` → `TextToSpeechEngine` (EP-047): one
`CommandModule` at the top, one narrow, swappable backend interface
underneath, constructed once at `Bootstrap` time and injected.

No new Manager/Provider/Engine trio (the `*Manager`/`*Provider`/
`*Engine` pattern used by EP-026 through EP-031 for **pluggable,
runtime-selectable strategies**, e.g. "which AI provider," "which
tool provider") is introduced. That pattern exists for genuinely
swappable *runtime* strategies selected via config (`tool
use <provider>`-style commands). EP-050 has exactly one meaningful
runtime backend (the real OS backend) plus a test-only fake — there
is no operator-facing "switch backend" use case analogous to
switching AI providers, so introducing a full Manager/Provider/Engine
trio here would be exactly the kind of premature, unrequested
architecture EP-049 Owner Decision D3's reasoning (and
`AI_GENERATION_STANDARD.md`'s YAGNI rule) warns against. A single
`Protocol`/ABC + constructor injection (the `VoiceModule` /
`SpeechToTextEngine` shape) is the smallest architecture-compatible
fit. If cross-platform (Owner Decision D5) or multiple real backends
per platform become a genuine need later, the same Manager/Provider/
Engine pattern remains available to retrofit without breaking this
design's public surface — but it is not manufactured speculatively
now.

---

## 10. Component Responsibilities

| Component | Responsibility | Must NOT do |
|---|---|---|
| `DesktopModule` (`skill.py`) | Parse `action`/`arguments` strings from `CommandRouter`, validate/convert them to typed values, call the injected `ComputerUseBackend`, translate its result into a `CommandResult` | Perform OS calls directly; construct a backend itself; decide safety policy beyond what Section 17 assigns it |
| `ComputerUseBackend` (Protocol, `backend.py`) | Define the structural contract every backend must implement (`move_mouse`, `click`, `scroll`, `type_text`, `press_key`, `read_clipboard`, `write_clipboard`, `screenshot`, `cursor_position`, `screen_size`, `active_window_title`, `focus_window`) | Contain any real OS logic itself (it is a pure interface, matching `ToolProvider`'s/`AgentProvider`'s ABC role) |
| `WindowsComputerUseBackend` (`windows_backend.py`) | Implement `ComputerUseBackend` against the chosen technology (Section 24) | Know about `CommandRouter`, `CommandResult`, or any Jarvis-specific concept — a pure OS-facing adapter, mirroring `VoskSpeechToTextEngine`'s isolation from `VoiceModule` |
| `_FakeComputerUseBackend` (test-only) | Implement `ComputerUseBackend` deterministically for automated tests, recording calls, never touching real hardware | Ship in `src/` — lives only under `tests/EP050/` |
| `Bootstrap` (existing file, additive change only) | Construct one `WindowsComputerUseBackend`, construct `DesktopModule(backend, config)`, register it via `router.register_modules([...])` | Change construction order of any other module; change any existing subsystem's wiring |

---

## 11. Tool Engine Integration

Per Section 6.3's finding, **zero parameterized actions of any kind
exist in Tool Engine today** — this is a pre-existing, already-
disclosed limitation, not something EP-050 introduces or is
responsible for fixing.

**EP-050 v1 registers no `Tool` entries in the Tool Engine catalog.**
Every `desktop ...` action requires at least one parameter
(coordinates, text, a key name) except pure observation actions
(`desktop screenshot`, `desktop cursor`, `desktop screen-size`,
`desktop active-window`), which *could* be registered as
zero-argument `Tool`s exactly like `retrieve_from_memory` is today.

Whether to register those few parameter-free, read-only actions is
small and optional — see Owner Decision D1 — but registering any of
the parameterized actions (`click`, `type`, `key`, `move`) would
require exactly the schema widening `src/core/tool/__init__.py`
already flags as out of scope for a single EP to invent
unilaterally. EP-050 does not invent it.

**Practical consequence:** Computer Use is reachable today through
`CommandRouter.dispatch()` (every dispatch surface: shell, Telegram,
Discord, REST API, voice) with full parameters, exactly like every
other skill. It is *not* reachable through a future autonomous
Agent → Planning → Tool chain until that chain itself gains
parameterized step support — which is a separate, larger, future
architectural decision belonging to EP-029/030/031's owners, not
EP-050's.

---

## 12. Agent / Planning Integration

Per Section 6.4's finding, there is no autonomous Agent/Planning loop
today capable of *deciding* to invoke a computer action on its own —
`DefaultPlanningProvider` only ever produces a `Plan` from
deterministic keyword rules applied to an already-typed/spoken
request, and every step still bottoms out at Tool Engine's
zero-argument constraint (Section 11).

**EP-050's integration boundary with Agent/Planning is therefore
intentionally minimal:** the read-only, zero-argument observation
actions (Owner Decision D1) *may* be registered as `Tool`s, making
them reachable the same way `retrieve_from_memory` is today — a
`Plan` step naming `subsystem="desktop"`, `action="screenshot"`
(etc.) could be dispatched through the existing chain with no schema
change. Parameterized actions remain reachable only via direct
`CommandRouter.dispatch()` (Section 11) until a future EP widens
`PlanStep`.

This document does **not** propose changes to `AgentEngine`,
`PlanningEngine`, or `PlanExecutionEngine` — none are needed for
EP-050's scope, and per Non-Goal 5 (Section 5), EP-050 is explicitly
not the EP that turns Jarvis into an autonomous computer-use agent.

---

## 13. Desktop Skill Integration — the naming collision

Two directories share the word "desktop." They are unrelated and
must never be merged, conflated, or cross-imported:

| | `desktop/` (root) | `src/skills/desktop/` |
|---|---|---|
| Owning EP | EP-044 Desktop UI | EP-050 Computer Use (this document) |
| What it is | A PySide6 GUI **client** of Jarvis's own REST API | An OS-input **capability** *inside* Jarvis's own core |
| Talks to | `Jarvis` over HTTP (`desktop/api/jarvis_api_client.py`) | The local OS directly (mouse/keyboard/clipboard/screen) |
| Imports `src.core`? | **Never** (`desktop/__init__.py`: *"never imports `src.core`... or `src.bootstrap`"*) | Yes — it *is* part of `src/`, wired into `CommandRouter` via `Bootstrap` |
| Direction of control | A human uses this GUI to control Jarvis | Jarvis (via a dispatched command) controls the OS |
| Touched by EP-050? | **No — confirmed zero changes** | Yes — this is where EP-050's implementation lives |

`EP044_DESIGN.md`'s own architecture note already establishes
`desktop/` as a strict, one-directional REST client with no
`src.core` dependency; EP-050 preserves that boundary exactly. Every
EP-050 source file's module docstring will state this distinction
explicitly (mirroring how `src/core/plan_execution/__init__.py`
already disambiguates its own "Execution Engine" name collision with
EP-003, Section 6.6).

---

## 14. Process Execution Boundary

| | `src/core/execution/` (EP-003) | `src/skills/desktop/` (EP-050) |
|---|---|---|
| Unit of action | A whole target: a script, a file, a URL, an application | A single input primitive: one click, one keystroke, one clipboard read |
| Owns | `ProcessRegistry` (PIDs of things it launched) | No process registry — it does not launch processes |
| Typical use | "Open Excel" / "Run this script" / "Open this URL" | "Click at (x, y)" / "Type this text into whatever has focus" / "Read the clipboard" |
| Interacts with an already-open window? | No — it starts new things | Yes — its entire purpose is interacting with what's already on screen |

**Explicit boundary rule:** EP-050 never launches a process, file, or
URL — if a future workflow needs "open Excel, then click a cell,"
that composition happens *above* both packages (via a `Plan`/script
that calls `execution ...` then `desktop ...` in sequence), not by
EP-050 reimplementing launch logic or by EP-003 growing input-control
methods. Each package keeps its single responsibility (ADR-004/005).

---

## 15. Security Boundary

Per Section 6.4, the realistic threat model for EP-050 v1 is: *"any
dispatch surface that can reach `CommandRouter.dispatch()`
(interactive shell, Telegram, Discord bot commands, the REST API,
voice) can trigger an OS input action,"* not an unsupervised
autonomous chaining loop (which does not exist yet).

**What EP-050 v1 implements itself (no Owner Decision needed):**

- **Bounds validation.** Every coordinate-taking action validates
  against `screen_size()` before dispatching to the backend and
  fails cleanly (`CommandResult(success=False, ...)`) if out of
  range — cheap, deterministic, no policy judgment required.
- **No shell/code execution of any kind.** `desktop type <text>`
  sends literal keystrokes; it never interprets `<text>` as a
  command, expression, or script. This is a hard, unconditional rule
  for the entire module, closing off the single largest realistic
  risk (command injection via typed text).
- **Structured, auditable logging of every action** (Section 19) —
  even without a confirmation gate, every invocation is traceable
  after the fact.
- **No hidden/background/daemon invocation path** (Non-Goal,
  Section 5) — every action is a single, explicit, synchronous
  dispatch; there is no way for an EP-050 action to trigger a further
  EP-050 action on its own.

**What requires an architectural extension EP-050 does not build
(flagged, not silently skipped):**

- A general per-source authorization mechanism ("Telegram may call
  `desktop click` but not `desktop type`") does not exist anywhere in
  `CommandRouter` today for *any* module (confirmed Section 6.5) —
  building one exclusively for `desktop` would be exactly the kind of
  new, EP-050-specific permission layer that has no precedent
  anywhere else in the project and would need to be judged against
  the whole `CommandRouter` design, not bolted on unilaterally.
- A confirmation/"are you sure" prompt for a specific action requires
  a synchronous request/response channel back to *whichever* caller
  issued the dispatch (interactive shell, Telegram, REST API, voice)
  — `CommandRouter.dispatch()` today is fire-and-forget, single-
  return-value, with no such channel for *any* existing module.

**Owner Decision required:** Section 30, Decision D2, resolves how
far EP-050 v1 goes on this axis — a config-level category
enable/disable gate (implementable today, no new mechanism needed) vs.
a true per-call confirmation prompt (requires the architectural
extension above, deferred).

**Explicitly deferred, not built:**

- Speaker/caller identity verification (mirrors EP-049's own
  disclosed, accepted limitation for voice — "any voice... can
  trigger dispatch").
- Rate limiting / action-frequency throttling.
- An allow-list/deny-list of specific coordinates or window titles.

None of these are silently dropped — they are explicit,
Section-30-tracked, deferred-by-design choices, matching
`AI_GENERATION_STANDARD.md`'s TODO Policy ("if something cannot be
implemented because architecture is missing, DO NOT invent it, leave
a TODO / flag it").

---

## 16. Human Approval / Safety Model

Directly addressing `JARVIS_ARCHITECTURE_VISION.md`'s "Human
Approval" principle (*"Jarvis never performs irreversible actions
automatically... require user confirmation unless explicitly
configured otherwise"*) against what is actually buildable today
(Section 15):

**Are Computer Use actions "irreversible"?** Mixed, and genuinely
category-dependent:

- `desktop screenshot`, `desktop cursor`, `desktop screen-size`,
  `desktop active-window` — fully reversible (read-only, no side
  effect at all).
- `desktop move`, `desktop click`, `desktop scroll`, `desktop key`,
  `desktop type`, `desktop write-clipboard` — side-effecting but
  *individually* no more "irreversible" than any keystroke a human
  makes; the *application receiving them* determines real-world
  reversibility (a click could open a harmless menu, or could confirm
  a destructive dialog — EP-050 cannot know which, because it does
  not interpret screen content, Section 8.3).

**Design decision for v1 (recommended, pending Owner Decision D2):**
treat the entire `desktop` namespace as one safety category, gated by
a single config flag (`desktop.enabled`, default `false` — mirroring
`voice.wake.enabled`'s and `voice.wake.assist.enabled`'s existing
"new capability defaults off" precedent), rather than trying to
individually classify each action's reversibility (which would
require the screen-content interpretation this document explicitly
keeps out of EP-050, Section 8.3/18). This is the smallest safety
model that (a) requires zero new architecture, (b) is consistent with
every prior EP's "risky new capability ships disabled by default"
precedent (`voice.wake.enabled: false`,
`voice.wake.assist.enabled: false`), and (c) gives the owner a single,
obvious switch.

A finer-grained, per-action or per-call confirmation model is
possible but requires the request/response channel gap named in
Section 15 — **not built in v1**, explicitly deferred to Owner
Decision D2's "reject" path.

---

## 17. Bounds / Input Validation (supplement to Section 15)

- Coordinates: validated against `screen_size()`; a request for
  `(x, y)` outside `[0, width) x [0, height)` fails with
  `CommandResult(success=False, message="...out of screen bounds...")`
  and performs no OS call.
- Key names / hotkey combinations: validated against a fixed,
  explicit allow-list of recognized key names the backend supports
  (not a free-form string passed straight to the OS) — an unknown key
  name fails cleanly rather than being silently ignored or
  misinterpreted by the underlying library.
- Typed text: no length limit imposed by EP-050 itself beyond what
  the backend library naturally supports; no content filtering
  (EP-050 does not interpret what is typed, matching Section 15's "no
  shell/code execution" rule — it types literally, it does not judge
  the content).

---

## 18. Observation Model

Per Section 8.3, "observation" in EP-050 is limited to: screenshot
raw bytes/dimensions, cursor position, screen size, active window
title, and standard success/failure reporting. **EP-050 never
interprets what a screenshot contains.** A `desktop screenshot`
action returns an opaque image (Section 19 defines exactly what
metadata is safe to log about it) — no OCR, no element detection, no
"what am I looking at" reasoning, no call to any AI/vision provider.
This line is the entire boundary against EP-053 Vision Integration
(Section 26): EP-053 consumes EP-050's screenshot capability as an
input; EP-050 does not reach into EP-053's territory itself.

---

## 19. Screenshot / Privacy Model

Screenshots and clipboard reads are the two EP-050 capabilities most
likely to contain sensitive information (passwords in a password
manager window, personal messages, financial data on screen). Per
`AI_GENERATION_STANDARD.md`'s Logging Policy (*"Never log secrets.
Never log passwords. Never log tokens"*), EP-050 extends this rule
explicitly to its own two riskiest actions:

**What EP-050 logs (via existing `loguru` convention):**

- Action name (`click`, `type`, `screenshot`, etc.), timestamp,
  success/failure, and non-sensitive parameters (coordinates, key
  names).
- For `screenshot`: dimensions and byte size only.
- For clipboard actions: that a read/write occurred, and its length
  in characters — **never** the clipboard content itself.
- For `type`: that a type action occurred and its length in
  characters — **never** the typed text itself (it may be a
  password).

**What EP-050 never logs, under any configuration:**

- Screenshot pixel/byte content.
- Clipboard content (read or written).
- Typed text content.

**Where screenshot bytes go:** returned directly in the
`CommandResult`/backend return value to whichever caller invoked
`desktop screenshot` (shell, REST API response, etc.) — the same
place any other command's output goes. EP-050 does not persist
screenshots to disk on its own initiative (no new `data/` write path
is introduced); if the caller (e.g. a REST API response, a future
workflow step) chooses to save it, that is the caller's existing
responsibility, not new EP-050 architecture.

**Screenshots are raw observations only** (Section 8.3) — EP-050
performs no analysis of a screenshot's content whatsoever; that
entire capability belongs to EP-053 (Section 26).

---

## 20. State Machine

```
IDLE
  |
  | dispatch("desktop <action> <args>")
  v
VALIDATING          -- parse/convert arguments, bounds-check (Section 17)
  |
  | invalid -> FAILED (CommandResult(success=False, ...)), back to IDLE
  | valid
  v
GATE_CHECK          -- desktop.enabled? (Section 16)
  |
  | disabled -> FAILED ("Computer Use is disabled"), back to IDLE
  | enabled
  v
EXECUTING           -- backend.<method>(...) call
  |
  | backend raises -> FAILED (message from exception, logged), back to IDLE
  | backend returns
  v
COMPLETED           -- CommandResult(success=True, ...), back to IDLE
```

This mirrors `EP049_DESIGN.md` Section 8's own state machine shape
(`IDLE → ... → COMPLETED`) at the granularity appropriate to
EP-050's *synchronous, single-call* nature — there is no
`OBSERVING` state distinct from `EXECUTING` because, unlike EP-049's
multi-second audio-capture pipeline, every EP-050 action (including
`screenshot`) completes and returns within a single backend call with
no separate observation phase. No `REQUESTED` state distinct from
`VALIDATING` either — dispatch is synchronous and single-threaded,
matching `CommandRouter.dispatch()`'s existing execution model
(there is no queue, so there is nothing "REQUESTED" is waiting on).

Every state transition happens within the single `DesktopModule`
method handling that dispatch; there is no background thread, no
persisted state between calls, and no timeout is needed beyond
whatever the backend library itself enforces (Section 21).

---

## 21. Error Model

Reusing the project's existing two-state result convention
(`CommandResult.success: bool` / `.message: str`, `ToolResult
.status: COMPLETED | FAILED`, Section 6.5) rather than inventing a
richer taxonomy (`TIMEOUT`, `UNAVAILABLE`, `PERMISSION_DENIED` as
distinct enum values) that exists nowhere else in the codebase today.

Every EP-050 failure surfaces as `CommandResult(success=False,
message="<specific reason>")`, with the reason distinguished in the
message text, not a new enum:

| Condition | `message` prefix (example) |
|---|---|
| Coordinates out of bounds | `"desktop click: out of screen bounds ..."` |
| Unknown key name | `"desktop key: unrecognized key name ..."` |
| `desktop.enabled: false` | `"Computer Use is disabled (desktop.enabled=false)."` |
| Backend raised an OS-level exception | `"desktop <action> failed: <exception message>"` |
| Malformed arguments (wrong count/type) | `"desktop <action>: invalid arguments, expected ..."` |

This matches `CommandRouter.dispatch()`'s own existing exception
handling (Section 6.5: it catches any exception a module raises and
converts it to a failed `CommandResult`) and `DefaultToolProvider`'s
identical pattern (Section 6.3) — no new error-handling architecture
is introduced. If a genuine need for a richer, typed error taxonomy
emerges across multiple subsystems later, that is a cross-cutting
change belonging to a dedicated cleanup effort (per
`ARCHITECTURE_DEBT.md`'s own rule: *"never fix architecture debt
during a normal EP"*), not something EP-050 introduces unilaterally
for itself alone.

---

## 22. Configuration

Following `config.yaml`'s existing per-subsystem block convention
(Section 6.11) exactly:

| Key | Type | Default | Purpose | Security implication |
|---|---|---|---|---|
| `desktop.enabled` | bool | `false` | Master gate for the entire `desktop` namespace (Section 16) | The single safety switch; off by default, matching `voice.wake.enabled`/`voice.wake.assist.enabled` precedent |
| `desktop.backend` | string | `"windows"` | Which `ComputerUseBackend` implementation `Bootstrap` constructs (only one real value exists in v1; validated the same way `tool.default_provider` is, Section 6.3) | None directly; exists so a future backend can be added without a code change to `Bootstrap`'s selection logic |
| `desktop.screenshot.max_dimension` | int | a sane bound (e.g. `4096`) | Caps returned screenshot size to avoid pathologically large payloads | Minor: bounds resource usage, not a security control |

No other keys are added "for the future" (`AI_GENERATION_STANDARD.md`
Configuration Policy — every key must have real, present necessity).
Explicitly **not** added in v1: any per-action enable/disable key
(mouse vs. keyboard vs. clipboard vs. screenshot) — Section 16's
single-category gate is the v1 design; splitting it further is
straightforward future work if Owner Decision D2 calls for it, not
built speculatively now.

---

## 23. Logging / Observability

Following `loguru`'s existing project-wide usage (Section 6.11), no
new logging abstraction. Per action, `DesktopModule` logs (at
`INFO` for success, `ERROR`/`WARNING` for failure, mirroring
`CommandRouter.dispatch()`'s own `logger.info`/`logger.error` split):

- action name, timestamp (via loguru's own timestamp), success/
  failure, duration.
- non-sensitive parameters only (Section 19's exclusions apply here
  identically — this section and Section 19 describe the same
  logging behavior from two angles: what's safe (here) and what's
  forbidden (Section 19)).

No new log file/sink is introduced — `config.yaml`'s existing
`logging.*` keys (`level`, `retention_days`, `console_enabled`)
govern EP-050's log output identically to every other subsystem.

---

## 24. Technology Evaluation

Candidates evaluated for `WindowsComputerUseBackend`'s underlying
implementation, against the actual target (a real Windows
workstation, per the task's framing) and this project's architecture
(a single narrow backend behind a `Protocol`, Section 9):

| Criterion | PyAutoGUI | pynput | pywinauto | Windows UI Automation (via `pywinauto`'s `uia` backend / raw `comtypes`) |
|---|---|---|---|---|
| Already in `requirements.txt` | **Yes** | No | No | No |
| Windows mouse/keyboard control | Yes | Yes | Yes (via win32/uia backends) | Only via a wrapper (raw UIA is accessibility-tree-focused, not a general input-injection API) |
| Cross-platform | Yes (Win/Mac/Linux) | Yes (Win/Mac/Linux) | No (Windows-only) | No (Windows-only) |
| Screenshot support | Yes (built in) | No (needs a separate library, e.g. Pillow's `ImageGrab`) | Partial (window-level, via win32) | No (not its purpose) |
| Clipboard support | Yes (basic, via a dependency) | No | Yes (via win32 `pywin32`) | No |
| Active window / window title | Limited (`getActiveWindow()` on some platforms, Windows-only reliability varies) | No | Yes, strong (this is pywinauto's core purpose) | Yes, strong |
| Maintenance activity | Mature, stable, widely used, low churn | Mature, actively maintained, low churn | Mature, actively maintained, Windows-focused | N/A (not a packaged library for this purpose) |
| Dependency footprint | Small, pure-Python-ish | Small | Larger (pulls `pywin32`, `comtypes`) | N/A |
| Fits EP-050's scope (raw input primitives, not UI-tree automation) | **Very good fit** | Good fit (input only, no screenshot) | Overshoots EP-050's scope — pywinauto's real strength is finding/driving *specific UI elements by name*, which is closer to accessibility-based automation than raw input, and risks scope creep toward what EP-053/an accessibility-based automation EP might want | Overshoots similarly; UIA is accessibility-tree introspection, a different capability than raw input |
| Offline / local-only | Yes | Yes | Yes | Yes |

**Recommendation: PyAutoGUI**, for the following reasons:

1. It is the only candidate that already covers *every* EP-050 v1
   primitive (mouse, keyboard, screenshot, basic clipboard via its
   `pyperclip` dependency) in one library, minimizing the number of
   new third-party dependencies added — directly serving
   `AI_GENERATION_STANDARD.md`'s Existing Dependencies Policy ("never
   introduce a new third-party dependency unless explicitly
   requested... always reuse existing libraries already used by the
   project" — and PyAutoGUI is *already declared*, just unused).
2. It matches EP-050's actual scope precisely: raw input primitives,
   not UI-tree/accessibility-based element automation. `pywinauto`
   and raw UI Automation are better suited to a *future*,
   more targeted automation EP (finding "the Submit button" by name)
   — a materially different, larger capability EP-050 explicitly
   defers (Section 8.2, "no element detection").
3. Active window title support is a known PyAutoGUI weak point on
   some platforms — but since EP-050 targets Windows only (Owner
   Decision D5, and Section 26 below), this is mitigated by falling
   back to a small, targeted use of `pywin32` (already a transitive
   dependency of several mature Windows automation libraries and
   commonly bundled) *only* for the `active_window_title()` method,
   if PyAutoGUI's own Windows support proves insufficient during
   STEP 2 implementation — a narrow, justified exception documented
   inline, not a second general-purpose input library.

**Trade-off accepted:** PyAutoGUI is not the most "powerful" option
(pywinauto/UIA can locate and drive specific named UI elements
directly) — but that power is explicitly out of EP-050's scope
(Section 8.2) and would be scope creep toward a different, larger
capability. The smallest tool that fully covers the actual v1 goal
is preferred, per `AI_GENERATION_STANDARD.md`'s YAGNI principle.

**`selenium`** (also pre-provisioned, unused) is confirmed
irrelevant to EP-050 — it is a browser-automation library, squarely
EP-051's territory (Section 26), and EP-050 does not import it.

---

## 25. Testing Strategy

Following `src/testing/`'s existing `BaseTest` convention and
`tests/EP046/test_voice.py`'s fake-class precedent exactly (Section
6.10):

### Automated tests (`tests/EP050/test_desktop.py`, run in every CI/sandbox environment, no hardware)

- `_FakeComputerUseBackend` — a plain class implementing
  `ComputerUseBackend`'s full protocol, returning pre-canned
  deterministic values (fixed cursor position, fixed screen size,
  fixed screenshot placeholder bytes), recording every call made to
  it (mirroring `_RecordingModule`'s `call_count` pattern in
  `tests/EP046/test_voice.py`) so tests can assert *what* was called
  without touching a real screen.
- `DesktopModule` behavior against the fake:
  - argument parsing/conversion correctness (valid and invalid
    inputs for every action).
  - bounds validation (Section 17) rejects out-of-range coordinates
    *without* calling the backend.
  - `desktop.enabled: false` blocks every action *without* calling
    the backend (Section 16/20's `GATE_CHECK` state).
  - successful dispatch calls the correct backend method with the
    correct converted arguments exactly once.
  - a backend exception is translated into `CommandResult(success=
    False, ...)`, never propagated raw through `CommandRouter`
    (mirroring `CommandRouter.dispatch()`'s own existing top-level
    catch, Section 6.5).
  - logging never includes clipboard/typed/screenshot content
    (Section 19) — asserted by capturing log output in the test and
    checking the sensitive fixture value is absent.
- Integration: `DesktopModule` registered into a real `CommandRouter`
  instance, dispatched exactly like `tests/EP046/test_voice.py`'s
  `_test_voice_module_listen_matches_direct_dispatch` — confirms
  `desktop <action> <args>` string dispatch and direct
  `DesktopModule.execute(action, args)` calls produce identical
  results.

None of the above requires a physical mouse, keyboard, screen, or
real Windows GUI, satisfying the task's explicit hard constraint.

### Fake-backend coverage boundary

The fake backend is a **deterministic stand-in for the OS**, not a
test of PyAutoGUI itself — EP-050's automated suite verifies
`DesktopModule`'s own logic (parsing, validation, gating, error
translation, logging hygiene), not whether PyAutoGUI correctly moves
a real mouse. That correctness question belongs to the next
category.

### Optional Windows integration tests (not part of the default suite)

A small, separately-invoked test module (e.g. `tests/EP050/
test_desktop_windows_integration.py`, skipped by default / run only
with an explicit flag or on the real target machine — mirroring
EP-048's own precedent of a disclosed, sandbox-unavailable
`tflite-runtime` dependency needing real-hardware verification,
Section 6.2) that exercises `WindowsComputerUseBackend` against the
real OS: e.g. move the mouse to a known position and read it back,
capture a screenshot and verify non-zero dimensions.

### Manual verification (owner performs on the real target machine)

- `desktop click`/`desktop type` against a real, visible application
  window, confirmed by eye.
- `desktop screenshot` produces a visually correct image of the real
  screen.
- Clipboard round-trip (`write-clipboard` then `read-clipboard`)
  against the real OS clipboard, confirmed against another
  application (e.g. paste into Notepad).
- `desktop active-window` reports the correct title for a real,
  focused window.
- `desktop.enabled: false` genuinely blocks all of the above on the
  real machine, not just in the fake-backed test suite.

This three-tier split (automated / optional integration / manual)
mirrors EP-048's own "sandbox has an environment limitation, real
Windows verification closes it" precedent (Section 6.2) exactly.

---

## 26. EP-050 / EP-051 / EP-052 / EP-053 Boundaries

| Capability | EP-050 | EP-051 | EP-052 | EP-053 |
|---|---:|---:|---:|---:|
| Mouse control | **Yes** | — | — | — |
| Keyboard control | **Yes** | — | — | — |
| Clipboard (text) | **Yes** | — | — | — |
| Screenshot capture (raw) | **Yes** | — | — | — |
| Window focus/activation (by title) | **Yes**, minimal | — | — | — |
| Window management (move/resize/enumerate/minimize) | Deferred (possible EP-050.x) | — | — | — |
| Browser navigation | — | **Yes** | — | — |
| Browser DOM interaction | — | **Yes** | — | — |
| File operations (read/write/organize) | — | — | **Yes** | — |
| OCR | — | — | — | **Yes** |
| Visual/scene understanding | — | — | — | **Yes** |
| Vision model invocation | — | — | — | **Yes** |
| Process/application launching | (reuses existing EP-003, not owned by any of these) | | | |

This table is the authoritative scope fence for STEP 2. Any
implementation work that would add a checkmark outside EP-050's
column is out of scope for this Engineering Package.

---

## 27. Backward Compatibility

Explicitly verified against every named EP, following EP-049's own
Section 19 precedent of stating "unchanged" per file:

- **`CommandRouter` (`src/core/command_router.py`):** zero changes.
  `DesktopModule` registers via the existing, unmodified
  `register()`/`register_modules()` methods.
- **`Bootstrap` (`src/bootstrap.py`):** additive only — one new
  import, one new backend construction, one new
  `DesktopModule(...)` construction, added to whatever list is
  passed to `register_modules()`, following the exact pattern
  `VoiceModule` was added under (Section 6.2's citation of EP-049
  Owner Decision D4's "no change to construction order" precedent).
  No existing module's construction, order, or arguments changes.
- **`src/core/tool/` (EP-031):** zero changes (Section 11 — EP-050
  registers no parameterized tools; any zero-argument observation
  tool registration, if approved via Owner Decision D1, is additive
  registration only, exactly like every existing built-in tool).
- **`src/core/agent/`, `src/core/planning/`, `src/core/plan_execution/`
  (EP-028/029/030):** zero changes (Section 12).
- **`src/core/execution/` (EP-003):** zero changes (Section 14).
- **`desktop/` (EP-044 GUI):** zero changes (Section 13).
- **`src/skills/browser/` (EP-051's future territory):** zero
  changes — confirmed still empty/untouched.
- **`config/config.yaml`:** additive only — one new `desktop:` block
  (Section 22), no existing key's meaning, default, or validation
  changes.
- **`requirements.txt`:** no new dependency (`pyautogui` is already
  present, Section 24); `pyperclip` (PyAutoGUI's own clipboard
  dependency) is pulled in transitively by `pyautogui` already being
  declared — verified as an existing transitive dependency, not a
  new top-level one, during STEP 2, not assumed here.

---

## 28. Architecture Debt

Reviewed `docs/architecture/ARCHITECTURE_DEBT.md` in full (AD-001,
AD-002, AD-003, AD-005 through AD-009). None concern
`src/core/tool/`, `src/core/command_router.py`, `src/skills/`,
`src/core/execution/`, or `desktop/` — **no existing debt item
affects EP-050's scope**, and EP-050 introduces no fix for any of
them (per `ARCHITECTURE_DEBT.md`'s own rule: *"never fix architecture
debt during a normal EP"*).

**Does EP-050 introduce new architecture debt?** One item, disclosed
rather than silently created:

- Tool Engine's zero-argument-only constraint (Section 6.3/11) is
  *not new* — but EP-050 is the first EP for which this limitation
  concretely blocks a capability an owner might reasonably want
  Agent/Planning-reachable (parameterized computer actions). This is
  recorded here as a candidate future debt/roadmap item — **not**
  added to `ARCHITECTURE_DEBT.md` by this document (that file is
  reserved for audit-confirmed issues per its own stated process, and
  STEP 1 is design, not an audit) — but flagged for the owner's
  awareness in Section 30, Decision D1.

---

## 29. Proposed STEP 2 File Change Plan

**This is a plan only. No file below has been created or modified by
STEP 1.**

### CREATE

- `src/skills/desktop/skill.py` — `DesktopModule` (`CommandModule`
  implementation, `"desktop"` namespace).
- `src/skills/desktop/backend.py` — `ComputerUseBackend` Protocol/ABC.
- `src/skills/desktop/windows_backend.py` — `WindowsComputerUseBackend`
  (PyAutoGUI-based, Section 24).
- `tests/EP050/__init__.py` — empty, matching every other
  `tests/EP0XX/__init__.py`.
- `tests/EP050/test_desktop.py` — automated test suite (Section 25),
  including `_FakeComputerUseBackend`.
- `tests/EP050/test_desktop_windows_integration.py` — optional,
  skipped-by-default real-hardware integration tests (Section 25).
- `docs/architecture/audits/EP050_AUDIT.md` — created at STEP 3
  (architecture audit), not STEP 2; listed here only for
  completeness of the EP lifecycle, not part of the STEP 2 diff.

### MODIFY

- `src/bootstrap.py` — additive only: import `DesktopModule` and the
  chosen backend, construct one `WindowsComputerUseBackend`, construct
  `DesktopModule(backend, config)`, add it to the existing
  `register_modules([...])` call. No other line changes.
- `config/config.yaml` — additive only: new `desktop:` top-level
  block (Section 22). No existing key changes.
- `docs/architecture/JARVIS_ROADMAP.md` — update EP-050's line from
  "NOT STARTED" to reflect STEP 2 completion (matching every prior
  EP's own roadmap-update convention), once STEP 2 finishes.
- `docs/BACKLOG.md` — update the "Next Engineering Package" entry
  (matching prior EPs' own convention), once STEP 2 finishes.
- `CHANGELOG.md` / `docs/RELEASE_NOTES.md` — append EP-050 entry
  (matching prior EPs' own convention), once STEP 2 finishes.

### DO NOT MODIFY

- `src/core/command_router.py`
- `src/core/tool/` (any file)
- `src/core/agent/`, `src/core/planning/`, `src/core/plan_execution/`
  (any file)
- `src/core/execution/` (any file)
- `desktop/` (any file — the EP-044 GUI package)
- `src/skills/browser/` (any file — EP-051's future territory)
- `src/skills/voice/` (any file)
- Any file under `tests/EP001` through `tests/EP049`
- `pyproject.toml`

### DEPENDENCIES

- No new entry required in `requirements.txt` — `pyautogui` is
  already declared (Section 24/27). If STEP 2 implementation finds
  `pyautogui`'s own clipboard support (via its transitive `pyperclip`
  dependency) insufficient, or needs `pywin32` narrowly for
  `active_window_title()` (Section 24's disclosed fallback), that
  specific addition — and only that addition — will be raised
  explicitly at STEP 2 time with its own justification, per
  `AI_GENERATION_STANDARD.md`'s "if a new dependency is required,
  explain why... never silently add new packages" rule. It is not
  pre-approved by this document.

---

## 30. Owner Decisions

Per the task's explicit instruction, only genuine questions the
existing architecture and repository cannot answer are listed here —
mirroring EP-046 through EP-049's own Section 9/23 precedent format.

---

### D1

**Question:** Should EP-050 register any `Tool` entries in the
Tool Engine catalog (Section 11), specifically for the zero-argument,
read-only observation actions (`screenshot`, `cursor`, `screen-size`,
`active-window`)?

**Options:**
A. Register all four as `Tool`s under `subsystem="desktop"`,
   matching how `retrieve_from_memory` etc. are registered today —
   makes them reachable via a future `Plan` step with zero schema
   changes.
B. Register none — `desktop` actions are reachable only via direct
   `CommandRouter.dispatch()` in v1; revisit once/if Tool Engine's
   parameter limitation (Section 6.3/28) is ever addressed.

**Recommended:** B.

**Reason:** These four actions are the least useful in isolation —
Agent/Planning reachability matters most for the *parameterized*
actions (`click`, `type`), which cannot be registered regardless
(Section 11). Registering only the four read-only actions creates an
inconsistent surface (some `desktop` actions reachable via Plan, most
not) for marginal benefit, and adds catalog entries whose real
usefulness is unclear until a genuine consumer (e.g. a future Plan
step that wants a screenshot) exists. Cheap to add later (Option A)
with zero backward-compatibility risk if the owner's assessment
differs.

**Impact if rejected (i.e. owner picks A):** Four additional `Tool`
registrations added in `Bootstrap` alongside `DesktopModule`
construction (Section 29's MODIFY entry gains four more lines); no
other design change.

---

### D2

**Question:** What safety/confirmation model should EP-050 v1 ship
with (Section 15/16)?

**Options:**
A. Single category-level config gate only (`desktop.enabled`,
   default `false`) — no per-action confirmation, no per-source
   authorization. Buildable entirely within EP-050's own files, no
   architecture extension.
B. Category gate (A) plus a genuine per-call confirmation prompt for
   every `desktop` action, requiring a new synchronous request/
   response channel added to `CommandRouter`/each dispatch surface
   (shell, Telegram, REST API, voice) — a real architectural
   extension affecting files well outside `src/skills/desktop/`.
C. Category gate (A) now; explicitly flag per-call confirmation
   (B) as a fast-follow EP-050.1 or a dedicated future EP, once a
   concrete confirmation-channel design exists for `CommandRouter` in
   general (benefiting every future risky module, not just
   `desktop`).

**Recommended:** C.

**Reason:** Option B is architecturally the "most correct" reading of
`JARVIS_ARCHITECTURE_VISION.md`'s Human Approval principle, but it
requires a cross-cutting `CommandRouter`/dispatch-surface change this
task's own rules forbid EP-050 from making unilaterally ("never
redesign architecture," Rule 1). Option A alone under-delivers on a
real, named architectural principle. Option C ships a safe default
today (config-gated, off by default) while explicitly naming the gap
rather than pretending Option A fully satisfies Human Approval.

**Impact if rejected (i.e. owner picks A or B):** A: Section 16's
design is unchanged, no explicit follow-up commitment recorded, no
`docs/BACKLOG.md` entry describing the deferred confirmation channel.
B: STEP 1 is not actually complete — this document would need a
second design pass covering the `CommandRouter` extension itself
before STEP 2 could begin at all, since that extension is a
prerequisite, not an EP-050-internal detail.

---

### D3

**Question:** Confirmed technology backend — PyAutoGUI (Section 24's
recommendation), or a different candidate?

**Options:**
A. PyAutoGUI (already in `requirements.txt`), as recommended.
B. pynput (mouse/keyboard only; screenshot/clipboard would need
   additional libraries).
C. pywinauto (Windows-only, UI-tree/element-focused — likely
   overshoots EP-050's raw-input scope, better fit for a possible
   future EP).

**Recommended:** A.

**Reason:** Section 24 in full — smallest dependency footprint given
it is already declared, covers every v1 primitive in one library,
correctly scoped to raw input rather than UI-tree automation.

**Impact if rejected (i.e. owner picks B or C):** B: `screenshot`/
`clipboard` methods need an additional named dependency (e.g. Pillow
`ImageGrab` + a clipboard library), raised explicitly at STEP 2 per
the Dependencies Policy — a small addition to Section 29's DEPENDENCIES
list. C: `WindowsComputerUseBackend`'s implementation shape changes
materially (element-lookup-oriented API instead of raw coordinate/key
calls); Section 9's Protocol shape likely still holds, but Section 24's
whole evaluation and Section 8's action list would need
re-examination for fit.

---

### D4

**Question:** Screenshot/observation scope — confirmed as Section 18
defines it (raw capture only, zero interpretation), or should EP-050
include any minimal interpretation (e.g. basic image dimensions/
format metadata beyond what's already proposed)?

**Options:**
A. Exactly as designed: raw bytes + dimensions only, zero content
   interpretation, zero OCR, zero vision-model calls (Section 18).
B. Widen slightly to include e.g. dominant-color detection or basic
   image diffing between two screenshots (still not full OCR/vision,
   but a small step toward "interpretation").

**Recommended:** A.

**Reason:** The task's own instruction is explicit: *"Do not turn
EP-050 into a vision system."* Any interpretation, however minimal,
starts down a path that has no natural stopping point short of
EP-053's actual territory, and risks exactly the scope creep Section
20's roadmap table is designed to prevent.

**Impact if rejected (i.e. owner picks B):** Section 18/26 both need
revision to carve out the specific widened capability, and the
EP-050/EP-053 boundary table (Section 26) needs a new row — this
would meaningfully blur, not just adjust, the EP-050/EP-053 line the
rest of this document treats as firm.

---

### D5

**Question:** Windows-only vs. cross-platform abstraction (Section 9/24)?

**Options:**
A. Windows-only in v1 — `ComputerUseBackend` Protocol is designed to
   *permit* future backends, but only `WindowsComputerUseBackend` is
   implemented; `desktop.backend` config defaults to and currently
   only accepts `"windows"`.
B. Design and implement a genuinely cross-platform backend now (e.g.
   fully leaning on PyAutoGUI's own cross-platform support), even
   though only Windows is verified.

**Recommended:** A.

**Reason:** The task's own framing confirms the real target is a
Windows workstation (Section 24's premise) and explicitly warns
against "architecture [becoming] unnecessarily... Windows-only
*implementation*" while still treating Windows as the primary target
— read together, this means: keep the *abstraction* clean (which
Section 9's Protocol already does, at no extra cost) but do not spend
STEP 2 effort verifying non-Windows behavior nobody will run. PyAutoGUI
happens to work on other platforms "for free," but that is a
side-effect, not a v1 goal or test commitment.

**Impact if rejected (i.e. owner picks B):** Section 25's testing
strategy gains real macOS/Linux verification obligations (currently
explicitly out of scope), and `desktop.backend`'s validation (Section
22) would need to accept and meaningfully route to more than one real
backend value — a larger STEP 2 scope than currently planned.

---

### D6

**Question:** Should window management (move/resize/enumerate all
open windows/minimize — deferred in Section 8.1/8.2) be pulled into
EP-050 v1, or remain deferred?

**Options:**
A. Remain deferred (current design) — v1 ships only single-window
   *focus by title* as a supporting capability for click/type
   usability, nothing more.
B. Pull full window management into EP-050 v1.

**Recommended:** A.

**Reason:** Window management is a real, coherent capability in its
own right (arguably substantial enough to be its own future
sub-package, `EP-050.1`, if ever needed) that is not required to make
EP-050's core input primitives usable — `focus_window(title)` alone
is sufficient for the realistic "make sure the right app has focus
before clicking/typing" use case this document actually needs to
solve (Section 8.1).

**Impact if rejected (i.e. owner picks B):** Section 8.1/8.2/10's
action tables, Section 24's technology evaluation (pywinauto's window-
management strength becomes directly relevant, potentially changing
Section 24's recommendation), and Section 25's testing strategy would
all need material expansion — this is a meaningfully larger v1 scope,
not a small addition.

---

## 31. Definition of Done

STEP 1 (this document) is done when:

- [x] `PROJECT_MANIFEST.md` and every document it designates read in
      full.
- [x] `AI_GENERATION_STANDARD.md`, `ENGINEERING_GUIDE.md`,
      `PROJECT_OVERVIEW.md`, `JARVIS_ROADMAP.md`,
      `JARVIS_ARCHITECTURE_VISION.md`, `NON_GOALS.md`,
      `ARCHITECTURE_DECISIONS.md`, `ARCHITECTURE_DEBT.md`,
      `BACKLOG.md` read in full.
- [x] EP-049's design and audit documents, and its real
      implementation files, read and understood.
- [x] Tool Engine, Agent Framework, Planning Engine, Plan Execution
      Engine, `CommandRouter`, `src/core/execution/`,
      `src/skills/desktop/`, `src/skills/browser/`, and `desktop/`
      (root) all inspected directly against the real repository, not
      assumed.
- [x] Existing testing (`src/testing/`, `tests/EP046`–`EP049`) and
      configuration/logging (`config/config.yaml`,
      `config/logging.yaml`) conventions identified and followed in
      this design.
- [x] Every architecture gap found (parameterized Tool Engine,
      absence of a confirmation mechanism, `desktop/` naming
      collision, unused `pyautogui`/`selenium`) explicitly analyzed,
      not silently resolved.
- [x] EP-050 vs. EP-051/052/053 boundary table completed from actual
      findings.
- [x] Security boundary, Human Approval model, and screenshot/privacy
      model all explicitly defined, with what's deferred clearly
      marked.
- [x] Technology evaluation completed with a recommendation and
      stated trade-offs.
- [x] Testing strategy defined with no automated-suite dependency on
      physical hardware.
- [x] Owner Decisions section contains only genuine open questions
      (six), each with Options/Recommended/Reason/Impact.
- [x] STEP 2 file change plan (CREATE/MODIFY/DO NOT MODIFY/
      DEPENDENCIES) is a plan only — nothing in it has been created
      or modified.
- [x] No file under `src/`, `tests/`, or `config/` was created or
      modified. No dependency was installed or added. No previous EP
      was modified. `docs/architecture/designs/EP050_DESIGN.md` is
      the only file created.

STEP 2 (implementation) will be considered its own, separate unit of
work, beginning only once the owner has reviewed Section 30 and
issued explicit instruction to proceed — mirroring EP-046 through
EP-049's own STEP 1 → Owner Decision → STEP 2 sequencing exactly.

---

## 32. STEP 1 Final Review — CommandRouter vs. Tool Engine, and Safety Sufficiency

This section was added during a dedicated final design review of
Section 11/30 (D2/D3), performed before owner approval, at the
owner's explicit request. **No implementation file was touched to
produce this section** — it is analysis added to this document only.

### 32.1 Why can Computer Use not be represented through Tool Engine without an architectural extension?

Re-verified directly against `src/core/tool/tool.py`,
`tool_provider.py`, and `tool_execution_provider.py`:

```python
@dataclass(frozen=True)
class Tool:
    ...
    handler: Callable[[], object]   # zero parameters, structurally
```

`DefaultToolProvider.invoke_tool()` calls `tool.handler()` — no
arguments are passed anywhere in the call chain
(`ToolEngine.invoke()` → `ToolProvider.invoke_tool(tool)` →
`tool.handler()`). `PlanStep` (`src/core/planning/planning_result.py`,
consumed by `ToolExecutionProvider.execute_step()`) carries no
parameter payload either — this is confirmed by
`src/core/tool/__init__.py`'s own admission that four of EP-029's
recognized actions (`generate_embedding`, `retrieve_context`,
`semantic_search`, `compress_context`) are **already** unregisterable
today for exactly this reason, unrelated to Computer Use.

This is a **structural** limitation, not an incidental one: every
layer in the chain — `Tool.handler`'s type signature, `ToolProvider
.invoke_tool(tool: Tool)`'s signature, `PlanStep`'s field set, and
`PlanExecutionProvider.execute_step(step: PlanStep)`'s signature —
would need to change in concert to carry a parameter through. No
single file can be patched in isolation without touching at least
`src/core/tool/tool.py` and `src/core/tool/tool_provider.py`, both
completed EP-031 files `AI_GENERATION_STANDARD.md` forbids modifying
"unless explicitly requested" outside that EP's own change window.
**Conclusion: this is confirmed, not assumed** — Computer Use cannot
be represented through Tool Engine today without editing files that
belong to a different, already-shipped Engineering Package.

### 32.2 Would direct CommandRouter integration create a second tool execution path?

**No — and re-reading `src/bootstrap.py`'s existing EP-031 wiring
block (lines ~895-977) confirms two execution paths already coexist
today, entirely independent of EP-050:**

```python
Tool(
    id="memory_recall",
    ...
    handler=self._memory_service.list_entries,   # <- bound directly
)                                                  #    to a Service
                                                    #    method, NEVER
                                                    #    to
                                                    #    CommandRouter
                                                    #    .dispatch()
```

Every built-in `Tool` registered today (`memory_recall`,
`knowledge_query`, `long_term_memory_query`, `agent_coordinate`,
`acknowledge_request`) binds its `handler` straight to a subsystem
*Service* method — never to `CommandRouter.dispatch()`. Meanwhile,
the large majority of `CommandModule`s registered with
`CommandRouter` (`system`, `voice`, `git`, `github`, `telegram`,
`discord`, `email`, `invoice`, `excel`, `presentation`) have **no**
corresponding Tool Engine registration at all.

So the repository's actual, pre-existing architecture is: **two
independent, parallel front doors into subsystem functionality —
`CommandRouter` (universal, string-dispatched, used by every skill)
and Tool Engine (narrow, opt-in, used only where Agent/Planning
reachability was specifically wired up)** — not one canonical path
that Tool Engine represents and everything else "bypasses." EP-050
choosing `CommandRouter` integration is choosing the path the
majority of existing skills already use, not inventing a new,
competing mechanism. **Conclusion: no second tool execution path is
created — EP-050 uses the path most of the project already uses.**

### 32.3 Would Agent → Planning → Tool → Computer Use remain architecturally consistent if dispatched directly through CommandRouter?

Yes, in the precise sense that matters: **each component in that
chain continues to do exactly and only what its own docstring
promises** (Section 6.4) — `AgentEngine` still only forwards
lifecycle/request calls, `PlanningEngine` still only builds a `Plan`
from deterministic keyword rules, `PlanExecutionEngine` still only
walks and dispatches `PlanStep`s, and `ToolEngine` still only
resolves-and-invokes an already-registered `Tool`. None of these
components silently start doing more than they claim, and none is
modified.

What is true is narrower and more honest: **that chain simply does
not currently reach Computer Use**, in the same way it does not
currently reach the four unregistered EP-029 actions (Section 32.1).
This is not a violation of the chain's consistency — it is the chain
correctly refusing to claim a capability it structurally cannot
support yet, exactly as it already does elsewhere. **Conclusion:
architecturally consistent; the chain is honestly incomplete for
this one capability, not compromised.**

### 32.4 Does this create hidden coupling between Computer Use and CommandRouter?

No. `DesktopModule` depends on exactly one thing outside its own
package: the public `CommandModule` `Protocol` (`name`, `execute()`)
defined in `src/core/command_router.py` — the same, single,
structural dependency every other skill in the project already has.
This is the *least* coupled integration option available in this
codebase's existing vocabulary, not a special case: `CommandRouter`
was explicitly designed (its own docstring: *"New modules register
themselves via `register()`. This class never needs to change to
support new command namespaces"*) to be depended upon this way by an
open-ended number of modules. No EP-050 file reaches into
`CommandRouter`'s internals, and no coupling to Tool Engine's
internals is introduced by *not* using it either. **Conclusion: no
hidden coupling — this is the standard, intended coupling shape.**

### 32.5 Could EP-051 Browser Automation and EP-052 File Automation later need the same approach?

**Very likely, yes.** Both are inherently parameter-heavy by nature:
a browser action needs a URL/selector/text; a file action needs a
path/content. Neither can be expressed as a `Callable[[], object]`
any more than a `desktop click <x> <y>` action can. This was not
verified against EP-051/EP-052 implementation (neither exists —
`src/skills/browser/` is confirmed empty, and no `src/skills/files/`
or equivalent exists at all), but the *shape* of the problem —
"real-world actions need parameters; Tool Engine's `Tool.handler`
has none" — is generic to any EP requiring parameterized action
dispatch, not specific to Computer Use.

### 32.6 If yes, does that mean the real architectural fix belongs in Tool Engine, not in EP-050?

**Yes — this review's single clearest conclusion.** If three
consecutive future Engineering Packages (EP-050, EP-051, EP-052)
would each independently need to work around the same structural
limitation, that is direct evidence the fix belongs at the shared
layer (`src/core/tool/`) via a dedicated, cross-cutting Engineering
Package of its own — not something any *one* of EP-050/051/052
should invent unilaterally for itself, which would itself violate
ADR-005 ("if multiple modules need the same functionality, that
functionality must be extracted into a shared module") in reverse
(three modules independently inventing three incompatible
workarounds around the same gap). This strengthens, rather than
merely repeats, Section 28's existing "candidate future debt" note.

### 32.7 What is the smallest architecture-compatible solution — Option Comparison

| | **A. Direct `CommandRouter` integration** | **B. Extend Tool Engine to support parameterized tools** | **C. New Computer-Use-specific execution abstraction** |
|---|---|---|---|
| **Architectural impact** | None outside `src/skills/desktop/` — uses an existing, universal, unmodified extension point (Section 32.4) | Touches `Tool.handler`'s type signature, `ToolProvider.invoke_tool()`, `PlanStep`'s schema, and `PlanExecutionProvider.execute_step()` — four files across three completed EPs (EP-029/030/031) | Introduces a brand-new dispatch mechanism that duplicates what Tool Engine already exists to generalize — direct conflict with ADR-004 (Single Source of Truth) and ADR-005 (Shared Components) |
| **Backward compatibility** | Perfect — zero existing files change (Section 27) | Requires care: existing zero-argument `Tool`s and the four already-unregistered EP-029 actions must keep working; achievable but non-trivial, and is by definition a change to already-shipped EP-029/030/031 code `AI_GENERATION_STANDARD.md` reserves for "explicitly requested" work | Perfect for *existing* files (nothing shared is touched) but at the cost of a second, EP-050-only mechanism nothing else benefits from or is consistent with |
| **Implementation complexity** | Low — exactly the shape every prior skill (`voice`, `system`, etc.) already used | Medium-to-high — a real schema-widening exercise spanning three packages, needing its own STEP 1 design pass, own Owner Decisions, and its own audit | Medium — but all of that complexity is spent building something with a smaller blast radius of *usefulness* (Computer-Use-only) than B's would have |
| **Testability** | High — identical to every existing `CommandModule` test pattern (Section 25), no new test infrastructure concept needed | Medium — needs new test coverage for the widened `Tool`/`PlanStep` schema itself, on top of whatever consumes it | Medium — needs an entirely new, EP-050-specific test harness with no precedent elsewhere in the project to mirror |
| **Future EP compatibility** | Immediately usable by any future EP the same way (no special status) | **Directly benefits EP-051 and EP-052 too**, once built (Section 32.5/32.6) — the only option that actually closes the shared gap | Does **not** help EP-051/EP-052 at all unless each also builds its own bespoke abstraction — actively encourages the "three incompatible workarounds" outcome Section 32.6 warns against |
| **Risk of architectural drift** | Low — reinforces an existing, well-established pattern rather than adding a new one | Low-to-medium if done as its own dedicated, well-scoped EP with its own STEP 1 design; **high** if attempted as a rushed side-effect inside EP-050 | **High** — a parallel, single-purpose dispatch mechanism is close to the textbook definition of the "duplicated infrastructure" `NON_GOALS.md` and `ARCHITECTURE_DECISIONS.md` both warn against |

**Recommendation, confirmed unchanged from the original STEP 1 pass:
Option A for EP-050 v1.** Option B is very likely the *eventually*
correct architectural move — but only once justified across more
than one consuming EP and given its own dedicated STEP 1 design pass
(exactly the process this document itself is an example of), not
invented ad hoc inside EP-050. **Option C is rejected outright** — it
is the one choice that actively creates new architectural debt with
no corresponding shared benefit, and is inconsistent with
`ARCHITECTURE_DECISIONS.md` ADR-004/ADR-005 on its face.

**What EP-050 should implement now:** Option A exactly as designed
in Sections 9-12 — `DesktopModule` via `CommandRouter`, with the
narrow, optional zero-argument `Tool` registrations from Owner
Decision D1 as the *only* Tool Engine touchpoint, unchanged.

**What should be deferred to a future architectural EP:** Option B —
recorded here as a strengthened candidate for a future, dedicated
Engineering Package (tentatively "Parameterized Tool Support" or
similar), to be justified once EP-051 and/or EP-052 make the
cross-cutting need concrete rather than hypothetical. This document
does not assign it a number or schedule it — that is a roadmap
decision belonging to the project owner, not to this EP's STEP 1.

**Whether EP-050 can safely proceed without that change:** **Yes.**
Nothing in EP-050's goals (Section 4) requires Agent/Planning-level
reachability for the parameterized actions — Section 12 already
scoped Agent/Planning integration to "no changes proposed," and
Section 11 already reached this same conclusion independently before
this review. This review confirms, rather than revises, that
original scoping.

### 32.8 Safety review — is `desktop.enabled = false` sufficient for v1?

Re-reading `JARVIS_ARCHITECTURE_VISION.md`'s exact wording: *"Jarvis
never performs irreversible actions automatically... Require user
confirmation **unless explicitly configured otherwise**."*

Two findings from re-checking the rest of the repository against
this principle, neither noted with this level of precision in the
original STEP 1 pass:

1. **No other subsystem in the entire codebase currently implements
   real per-action confirmation for an irreversible action either.**
   `src/core/plan_execution/__init__.py` itself confirms *"No
   'commit', 'push', 'pull', or 'clone' command exists"* for Git — so
   the vision document's own named example of an irreversible action
   (git push) is not yet implemented at all, confirmation or
   otherwise. Email send (`src/skills/... email`) and production
   deployment are similarly not implemented with any confirmation
   step today. **This means "Human Approval" is currently an
   aspirational, project-wide principle that no existing EP has yet
   operationalized — EP-050 is not uniquely deficient relative to the
   rest of the project; it would be the *first* EP to even partially
   engage with this principle, via Section 16's category gate.**
2. The vision text's own escape clause — *"unless explicitly
   configured otherwise"* — directly anticipates a configuration-based
   waiver of the confirmation default. A deliberate, off-by-default
   flag (`desktop.enabled`, default `false`) that the owner must
   consciously set to `true` before any `desktop` action can execute
   at all *is* a legitimate instance of "explicit configuration" in
   the vision document's own terms — the owner's act of setting the
   flag is the explicit approval, given once for the category rather
   than once per call.

**Where the gate falls short of full Human Approval, honestly
stated:** a single category-level flag is coarser than true
per-action confirmation. Once `desktop.enabled: true` is set, *every*
subsequent `desktop click`/`desktop type`/etc. call executes
immediately with no further gate, for as long as the flag stays on
— materially different from asking "are you sure?" before each
individual action, which is what the vision document's own worked
examples (publishing, sending an email, git push, production
deployment) most naturally suggest for a *specific, high-consequence*
action. A category gate is a reasonable, honestly-scoped **v1**
compromise, not a complete realization of the principle.

**Explicit determination:** `desktop.enabled = false` (default) with
an explicit, deliberate opt-in to `true` is **architecturally
sufficient and consistent for EP-050 v1** — it does not violate the
vision document (the "explicit configuration" clause covers it), and
it is at least as rigorous as every other subsystem's current,
unimplemented state of Human Approval. It is **not** a complete or
final implementation of the Human Approval principle at the
per-action granularity the vision document's examples imply, and
this gap is not silently accepted — it remains exactly where the
original STEP 1 pass placed it: **Owner Decision D2 (Section 30)**,
whose Option C (ship the category gate now, explicitly flag per-call
confirmation as a deliberate, named future item) is **reaffirmed,
unchanged, as this review's recommendation** after the closer
reading above. No confirmation framework is invented by this review
or by Section 16/17 — the gap is marked, not filled.

### 32.9 Summary of this review's conclusions

- CommandRouter integration (Option A) does **not** create a second
  execution path — it uses the path most existing skills already
  use, and Tool Engine (a separate, narrower, opt-in path) already
  coexists with it today for unrelated reasons (Section 32.2).
- The Agent → Planning → Tool → Computer Use chain remains internally
  consistent; it is simply not extended to reach EP-050 in v1, on the
  same honest terms it already doesn't reach four pre-existing
  EP-029 actions (Section 32.3).
- No hidden coupling is introduced (Section 32.4).
- EP-051/EP-052 likely face the identical structural gap, which is
  evidence the real fix belongs in Tool Engine itself, as a future,
  separately-justified, separately-designed Engineering Package —
  not invented inside EP-050 (Section 32.5/32.6).
- Option A remains the smallest architecture-compatible solution for
  v1; Option B is the correct long-term direction but requires its
  own dedicated design process; Option C is rejected (Section 32.7).
- `desktop.enabled = false` is sufficient and architecturally
  consistent for EP-050 v1, under the vision document's own "explicit
  configuration" clause, but is explicitly **not** a complete
  per-action Human Approval implementation — that gap remains Owner
  Decision D2, unchanged in substance, now with a more rigorous
  justification (Section 32.8).

**No correction to Sections 1-31 was required by this review.** The
original recommendations (Option A for CommandRouter integration,
the category-level `desktop.enabled` gate, and Owner Decisions
D1-D6) are all reaffirmed, not revised — this section adds rigor and
explicit proof where the original document asserted conclusions
without walking through the comparison in this much depth.

---

## STEP 1 Final Conclusion

Computer Use is architecturally reachable today with minimal new
machinery: one `CommandModule` (`desktop`), one narrow backend
Protocol, one real Windows-backed implementation (PyAutoGUI-based,
Section 24), and one config-level safety gate (Section 16) — reusing
`CommandRouter.dispatch()`, `Config`, `loguru`, and the project's
existing fake-class testing convention exactly as every prior EP has.

No existing EP, file, or public API was redesigned, duplicated, or
silently reinterpreted. Every genuine architecture gap found
(Sections 6.3/11/32.1 Tool Engine's structural zero-argument
constraint, Section 15/32.8 the absent per-action confirmation
channel, Section 13 the `desktop/` naming collision) is explicitly
named rather than papered over, and six Owner Decisions (Section 30)
are raised where — and only where — the existing repository
genuinely does not already supply the answer.

Section 32's dedicated final review confirms, with direct evidence
from `src/bootstrap.py`'s existing Tool Engine wiring, that direct
`CommandRouter` integration is not a workaround but a use of the
project's own established, majority-used dispatch path — and that
extending Tool Engine to support parameterized actions (the
architecturally "correct" long-term fix) is real future work best
justified across EP-050, EP-051, and EP-052 together, as its own
dedicated Engineering Package, not invented unilaterally inside this
one.

**STEP 2 has NOT started.** No file under `src/`, `tests/`, or
`config/` has been created or modified; no dependency has been
installed or added; `requirements.txt`, `pyproject.toml`, and
`bootstrap.py` are untouched; no previous Engineering Package's
implementation was modified.

**STEP 1 status: READY FOR OWNER REVIEW (including final review, Section 32).**
