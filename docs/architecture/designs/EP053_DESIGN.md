# EP-053 — Vision Integration — Design Specification (STEP 1)

Status: **STEP 1 — DESIGN COMPLETE / OWNER APPROVAL REQUIRED**

**STEP 2 implementation has NOT begun.**

No source file, test file, configuration file, dependency file, or
Bootstrap file has been created or modified as part of producing this
document. The only artifact created by EP-053 STEP 1 is this document
itself, `docs/architecture/designs/EP053_DESIGN.md`.

---

## 1. Metadata

- **Engineering Package:** EP-053 — Vision Integration
- **Phase:** Phase 8 — Computer Automation (`JARVIS_ROADMAP.md`)
- **Predecessors:** EP-050 Computer Use (complete), EP-051 Browser
  Automation (complete), EP-052 File Automation (complete)
- **Successor:** Phase 9 — Intelligence (EP-054 Self Reflection, not
  started)
- **This document's scope:** STEP 1 only — Architecture Discovery,
  Technology Evaluation, Design, and Owner Decision preparation. No
  code, test, configuration, or dependency file has been created or
  modified as part of producing this document.
- **File created by STEP 1:** this document,
  `docs/architecture/designs/EP053_DESIGN.md`, only.
- **Files modified by STEP 1:** none.

---

## 2. Problem Statement

Jarvis can already **produce** raw image bytes — `desktop screenshot
<path>` (EP-050, `src/skills/desktop/skill.py`) and `browser
screenshot <path>` (EP-051, `src/skills/browser/skill.py`) both
capture a screen/page and write undecoded image bytes to a
caller-supplied path — but by explicit, repeated, audited design
decision, **neither ever interprets that content**
(`EP050_DESIGN.md` Section 18, `EP051_DESIGN.md` Section 6, both
independently stating "EP-050/EP-051 never inspects a screenshot's
content"). EP-052 File Automation's `file read` action (Section 5.6
below) is UTF-8 text only (Owner Decision D6,
`EP052_DESIGN.md`) and explicitly excludes binary content.

The result: **Jarvis has no way, anywhere in the repository, to look
at the pixel content of an image and report anything about it** —
not the text printed on a screenshot, not a photograph's dimensions,
not what an image shows. Every prior Phase 8 EP deliberately reserved
this gap for EP-053. `JARVIS_ROADMAP.md` sequences EP-053 Vision
Integration directly after EP-052, and `docs/BACKLOG.md` independently
confirms EP-053 is "NOT STARTED. No design, research, or
implementation work has begun."

EP-053 STEP 1's job is to determine, from direct repository evidence
(not assumption), what a minimal, safe, testable v1 Vision
capability should look like: what already exists and can be reused,
what must be built, what stays explicitly out of scope, and what
questions only the owner can answer.

---

## 3. Goals

- Investigate the existing repository thoroughly enough to answer,
  with cited evidence, every question this task poses (Sections
  5–19 below).
- Determine precisely what "vision" can mean for Jarvis today without
  duplicating or reaching into EP-050's screen capture, EP-051's page
  capture, or EP-052's file access — EP-053 **interprets** image
  bytes; it does not capture or manage them.
- Propose a minimal, coherent v1 capability set — not a general
  computer-vision platform — following the same "small, reliable
  action set" precedent EP-050 (13 actions), EP-051 (15 actions), and
  EP-052 (9 CRUD actions + `help`) already established.
- Perform a serious, evidence-grounded analysis of the one genuinely
  new architectural question this EP raises that none of EP-050/051/
  052 had to answer: whether image *understanding* should be done
  locally (OCR/metadata only) or by sending image bytes to a
  configured AI provider (semantic description), and what that
  implies for `AIProvider`'s existing, text-only contract
  (`src/core/ai/provider.py`) and for privacy.
- Evaluate implementation technology, preferring the smallest
  dependency footprint consistent with the capability actually
  requested, and state plainly what (if anything) is new.
- Reuse the `CommandModule` / `CommandRouter` / Protocol-backend /
  fake-backend-testing / config-gate pattern EP-050, EP-051, and
  EP-052 all already established, unless the repository shows a
  concrete reason a different design fits Vision Integration better.
- Produce this design document only. No implementation, test,
  refactor, or dependency change.

---

## 4. Non-Goals

Explicitly out of scope for EP-053 v1, regardless of what a
third-party vision library or AI provider technically supports:

- **Screen or page capture of any kind.** Capturing pixels remains
  entirely EP-050's (`desktop screenshot`) and EP-051's (`browser
  screenshot`) territory (Section 7). EP-053 only ever *reads and
  interprets* image bytes that already exist as a file on disk — it
  never triggers a new capture itself.
- **Live/streaming/real-time vision** (webcam feed, continuously
  watching the screen, "observe and act" agent loops). EP-053 v1
  exposes single, explicit, synchronous, one-image-at-a-time actions
  dispatched through `CommandRouter.dispatch()`, identical to
  EP-050/051/052's model. There is no background watcher, no polling
  loop, and no self-directed re-dispatch.
- **Video** of any kind (recording, playback, frame extraction).
  Nothing in `requirements.txt` or `src/` references any video
  library today (confirmed by direct inspection, Section 6).
- **Face recognition, biometric identification, or any
  person-identifying capability.** Not requested by the roadmap, and
  a materially different (and materially more sensitive) privacy
  category than OCR/metadata/general description — deferred
  indefinitely, not merely to a future sub-package.
- **Object detection with bounding boxes, image segmentation, or
  pose estimation.** These require a machine-learning model runtime
  (e.g. a YOLO/torch-based pipeline) that is a qualitatively larger
  dependency than anything Phase 8 has installed so far
  (`requirements.txt`, Section 6) and is not justified by any goal
  Section 3 states. OCR word/line bounding boxes (a `pytesseract`
  built-in, Section 10) are the one exception already covered by
  Section 9's proposed action set, not a general object-detection
  capability.
- **Image *generation*.** `JARVIS_ARCHITECTURE_VISION.md`'s own
  example workflow ("how to generate images") describes a
  *different*, output-direction capability that is not this EP's
  concern; EP-053 is exclusively about interpreting images Jarvis
  already has, never about creating new ones.
- **A general-purpose, always-on cloud vision API integration**
  (Google Cloud Vision, AWS Rekognition, Azure Computer Vision) as a
  first-class, separately-configured provider. Section 10/11 evaluate
  whether *the AI provider Jarvis is already configured to use*
  (`ClaudeProvider` et al., Section 5.9) should be extended for image
  input — a materially different, much smaller decision (Owner
  Decision D1) than standing up an entirely new provider category.
- **Autonomous "look at the screen and click" agent loops** that
  chain `vision` output back into `desktop`/`browser` actions without
  a human in the loop. That composition, if ever built, is Agent
  Framework/Planning Engine territory (Phase 9, EP-054+), not
  something `VisionModule` does or calls into itself. `VisionModule`
  has no dependency on `src/core/agent/`, `src/core/planning/`,
  `src/skills/desktop/`, or `src/skills/browser/` in this design.
- **A general per-action human-confirmation/permission mechanism** —
  this is the same pre-existing, cross-cutting `CommandRouter`
  limitation EP-050/051/052 all already disclosed and did not fix
  themselves; EP-053 does not fix it either (Section 13).
- **Modifying `AIProvider`'s existing `ask()`/`ping()`/
  `list_models()` signatures**, or any existing provider's behavior,
  under any circumstance in this document. If Owner Decision D1
  selects AI-provider-based description, Section 8.3 proposes this as
  a strictly *additive* new method, never a change to an existing one
  — mirroring how EP-015 itself additively extended the base
  `AIProvider` class without altering `AIProvider.name()`/`status()`/
  `is_available()`/`configuration()`/`health()`.

---

## 5. Existing Architecture Analysis

Direct inspection of the repository (`jarvis-main`), not assumption:

### 5.1 Project discovery / governance documents

- `PROJECT_MANIFEST.md` — the single source of truth for project
  discovery. Does not itself define Vision Integration.
- `AI_GENERATION_STANDARD.md` — mandatory rules for any AI generating
  code for this project: never redesign architecture, never invent
  APIs/imports, reuse existing classes/services/interfaces, one class
  one responsibility, PEP8/SOLID/DRY/KISS/YAGNI, type hints,
  docstrings, 300-line-recommended/500-line-soft-limit files, 30-line
  recommended/60-line hard-limit functions, dependency injection, no
  hardcoded paths/URLs/credentials, "when in doubt, leave a TODO."
  This EP's design and, later, its implementation, are bound by all
  of the above exactly as EP-050/051/052 were.
- `docs/architecture/JARVIS_ROADMAP.md` — confirms EP-053 Vision
  Integration is the immediate next Engineering Package after EP-052
  (Phase 8), "NOT STARTED. No EP-053 design, research, or
  implementation work has begun" (stated verbatim at EP-052
  completion time).
- `docs/BACKLOG.md` — independently confirms the same.
- `docs/architecture/AI_DEVELOPMENT_PLAYBOOK.md` — defines the
  four-STEP process (STEP 1 Design, STEP 2 Implementation, STEP 3
  Architecture Audit, STEP 4 Documentation Completion) and the Prompt
  Strategy rule this task itself follows: "Never continue
  automatically. Always wait for the user's approval." This document
  is STEP 1 only.
- `docs/architecture/JARVIS_ARCHITECTURE_VISION.md` Section "Human
  Approval" (already cited by `EP052_DESIGN.md` Section 5.1) does not
  name any vision-specific irreversible action — EP-053 v1, as
  scoped below, is entirely read-only/observational (it never writes
  to, moves, or deletes anything), so this document's own risk
  profile is closer to EP-051's page-observation actions than to
  EP-052's file-mutation actions.

### 5.2 EP-050/051/052 as direct precedent

All three prior Phase 8 EPs are **COMPLETE** and independently
converged on the same architecture:

| Element | EP-050 (Computer Use) | EP-051 (Browser Automation) | EP-052 (File Automation) |
|---|---|---|---|
| Namespace | `desktop` `CommandModule` | `browser` `CommandModule` | `file` `CommandModule` |
| Backend contract | `ComputerUseBackend` Protocol | `BrowserBackend` Protocol | `FileBackend` Protocol |
| Real implementation | `WindowsComputerUseBackend` (PyAutoGUI) | `PlaywrightBrowserBackend` (Playwright sync API) | `LocalFileBackend` (stdlib) |
| Test-only implementation | `_FakeComputerUseBackend` | `_FakeBrowserBackend` | `_FakeFileBackend` |
| Dispatch mechanism | `CommandRouter.dispatch()`, unmodified | `CommandRouter.dispatch()`, unmodified | `CommandRouter.dispatch()`, unmodified |
| Safety gate | `desktop.enabled` (default `false`), re-checked every dispatch | `browser.enabled` (default `false`), re-checked every dispatch | `file.enabled` (default `false`), re-checked every dispatch |
| Wiring | `Bootstrap` constructs backend conditionally, injects into module, registers module unconditionally | identical pattern | identical pattern |

This is a three-times-independently-confirmed pattern, not a
one-off. Section 8 below proposes EP-053 follow it a fourth time
unless a concrete reason argues otherwise; Section 8.4 states why no
such reason was found.

### 5.3 `CommandRouter` (`src/core/command_router.py`)

Unmodified since EP-052 STEP 3's narrowly-scoped, owner-approved
tokenizer fix (Owner Decision D11, `EP052_DESIGN.md`). Its public
API — `register()`, `register_modules()`, `dispatch()`,
`module_names`, `CommandResult`, `CommandModule` — is exactly what
`VisionModule` needs and nothing more: `CommandModule.execute(action,
arguments) -> CommandResult` already accepts an arbitrary
string-argument list, which is all a `vision <action> <path>` call
requires.

### 5.4 `src/core/tool/` (Tool Engine, EP-031)

Confirmed unchanged by EP-050/051/052; `Tool.handler` remains
zero-argument-only for every action already registered in the
project (`EP050_DESIGN.md` Section 11/32, `EP051_DESIGN.md` Section
11, `EP052_DESIGN.md` Section 20/D9 — three independent EPs already
reached the identical conclusion). A `vision ocr <path>` action
needs at least one path argument, so this limitation applies to
EP-053 exactly as it applied to its three predecessors (Section 9.1
below, Owner Decision D9).

### 5.5 `src/core/ai/` (AI Provider Manager, EP-014/015)

- `src/core/ai/provider.py` — `AIProvider` is an `ABC` whose
  `ask(prompt: str, max_tokens: int | None = None) ->
  ProviderResponse` is **text-only**: `prompt` is a `str`, and
  nothing in `AIProvider`, `ProviderResponse`, `ProviderManager`, or
  `ClaudeProvider` (`src/core/ai/claude_provider.py`) accepts or
  transmits image bytes anywhere in the current codebase (confirmed
  by direct inspection — no `image`, `bytes`, `base64`, or
  `multimodal` parameter exists on this contract today). This is the
  single most consequential finding of this document (Section 8.3,
  Owner Decision D1): today, **no code path in Jarvis can send image
  content to any AI provider**, regardless of whether the
  provider's own remote API supports it.
- `AIProvider`'s own docstring records that EP-015 *additively*
  extended the EP-014 base contract with `ask()`/`ping()`/
  `list_models()` — a real precedent for adding a new,
  optional-to-override method to `AIProvider` without touching its
  existing methods, should Owner Decision D1 select that path.

### 5.6 `src/skills/files/` (EP-052, File Automation) — closest existing precedent for path-based, read-only actions

- `backend.py` defines `FileBackend` (Protocol), `FileBackendError`,
  and `FileEntry`; `local_backend.py`'s `LocalFileBackend` is the
  sole real implementation; `skill.py`'s `FileModule` dispatches
  `list`/`exists`/`stat`/`read`/`write`/`copy`/`move`/`mkdir`/
  `delete`/`help`.
- `FileModule.execute()`'s gate check (`file.enabled`, re-checked on
  every dispatch, not cached) and its layered safety model
  (`file.allowed_roots` — an explicit, default-empty allow-list of
  permitted root directories; `file.denied_paths`; path-traversal/
  absolute-path rejection) is the single most relevant existing
  mechanism for EP-053: **any `vision` action that reads a path off
  the local filesystem raises exactly the same "which paths may this
  capability touch" question EP-052 already answered** (Section 11
  below proposes reusing this pattern, not reinventing it, Owner
  Decision D4).
- `file read` is explicitly UTF-8-text-only (`EP052_DESIGN.md`
  Section 12/D6) — it cannot be reused to read image bytes, and
  EP-053 does not modify it to try.

### 5.7 `src/skills/desktop/backend.py` and `src/skills/browser/backend.py` — the `Screenshot` dataclass precedent

Both `ComputerUseBackend.screenshot()` and
`BrowserBackend.screenshot()` return a `Screenshot` dataclass
(`width: int, height: int, format: str, data: bytes`) — opaque,
undecoded bytes, by explicit design (Section 4 above). Neither
`DesktopModule` nor `BrowserModule` ever decodes `data`; both simply
write it to a caller-given path (`desktop screenshot <path>`,
`browser screenshot <path>`). This confirms Section 2's problem
statement precisely: **the `Screenshot.data` bytes these two EPs
already produce are exactly the kind of content EP-053 exists to
interpret** — via the file it was written to, not via any direct
coupling between `VisionModule` and `ComputerUseBackend`/
`BrowserBackend` (Section 7 explains why no such coupling is
proposed).

### 5.8 `src/core/execution/` (EP-003)

`FileExecutor` launches files/URLs with the OS default application;
it does not decode or interpret file content of any kind and is
unaffected by, and irrelevant to, EP-053.

### 5.9 `requirements.txt` — no image-processing dependency exists today

Confirmed by direct inspection: no `Pillow`/`PIL`, no `opencv-python`,
no `pytesseract`/`easyocr`/`paddleocr`, no `numpy`, and no ML/vision
runtime (`torch`, `tensorflow`, `onnxruntime` is present only as
`openWakeWord`'s own transitive dependency for audio wake-word
detection, EP-048 — unrelated to images) appears anywhere in the
dependency list. Section 10 evaluates what, if anything, EP-053 must
add.

### 5.10 `src/core/telegram/`, `src/skills/telegram/` (EP-040)

Confirmed, by direct inspection of `telegram_client.py`,
`telegram_router.py`, and `src/skills/telegram/`, that the existing
Telegram integration handles text messages dispatched through
`CommandRouter`; it does not currently receive, download, or forward
photo/image messages to any command module. **EP-053 v1 does not
change this** — Section 4 already excludes any new input-channel
work from this EP's scope; `vision` actions in v1 take a local file
path exactly like `file read`/`file write` do, so a photo received
over Telegram would need to already be saved to a path a `vision`
action can read (itself a separate, un-scoped integration question,
Owner Decision D3 below records why this is deferred rather than
silently assumed).

### 5.11 `config/config.yaml` — existing gate/allow-list conventions

`desktop:`, `browser:`, and `file:` blocks each follow an identical
documentation and structuring convention: a heading comment
explaining the EP and file(s) involved, an `enabled` gate defaulting
to `false` with a rationale comment referencing the sibling gates by
name, and (for `file:` only) a nested `allowed_roots` allow-list.
Section 21 proposes a new `vision:` block following this exact
convention.

### 5.12 `Bootstrap` (`src/bootstrap.py`)

Confirmed, by direct inspection, that `DesktopModule`, `BrowserModule`,
and `FileModule` are each wired identically: import the backend
Protocol and real implementation, construct the real backend only if
`<namespace>.enabled` is `true` (catching a construction failure and
falling back to `None` with a logged warning), store the backend on
a private `Bootstrap` attribute, expose it via a read-only property
(`desktop_backend`, `browser_backend`, `file_backend`), and register
the module with `CommandRouter` **unconditionally** — the module
itself, not `Bootstrap`, is responsible for refusing every action
while its own backend is `None` or its gate is `false` (Section 12).
Section 21 proposes `VisionModule`/`LocalVisionBackend`/
`vision_backend` follow this exactly.

---

## 6. Existing Vision/Image Capabilities (Explicit Inventory)

To directly answer "what does the repository already support":

| Capability | Exists today? | Owner |
|---|---|---|
| Capture the screen as raw image bytes | Yes | `desktop screenshot` (EP-050) |
| Capture a browser page as raw image bytes | Yes | `browser screenshot` (EP-051) |
| Read/write UTF-8 text files | Yes | `file read`/`file write` (EP-052) |
| Read/write arbitrary binary files | No | — (EP-052 D6 explicitly excluded) |
| Decode an image file's pixel data | **No** | — (no image library imported anywhere in `src/`) |
| Extract text printed inside an image (OCR) | **No** | — |
| Report an image's dimensions/format/basic metadata | **No** | — |
| Describe what an image depicts (semantic/AI-based) | **No** | — (`AIProvider.ask()` is text-only, Section 5.5) |
| Object detection / face recognition / video | No | — (Section 4, explicitly out of scope) |

This confirms the gap Section 2 describes is real and total: **zero**
image-interpretation capability exists anywhere in the current
repository.

---

## 7. EP-053 Boundary

To avoid duplicating or reaching into a predecessor EP's territory:

- **Screen/page capture remains EP-050's/EP-051's job entirely.**
  `VisionModule` never calls `ComputerUseBackend.screenshot()` or
  `BrowserBackend.screenshot()` directly, and has no constructor
  dependency on either. If a user wants to interpret a live
  screenshot, the existing two-step flow applies: `desktop
  screenshot <path>` (or `browser screenshot <path>`) followed by
  `vision <action> <path>` against the file just written — the same
  "compose existing, single-purpose actions" pattern the roadmap
  already uses elsewhere (e.g. `file write` followed by `file read`
  operate on the same path independently).
- **General file management remains EP-052's job entirely.**
  `VisionModule` reads bytes from a path the caller supplies; it does
  not list directories, copy, move, or delete anything, and has no
  constructor dependency on `FileBackend`. (Section 11 proposes
  reusing EP-052's *allow-list pattern*, config-only, not reusing
  `FileBackend` or `LocalFileBackend` as a runtime dependency —
  avoiding the hidden-coupling `AI_GENERATION_STANDARD.md` forbids.)
- **AI orchestration/agent behavior remains Phase 4's (Agent
  Framework, EP-028-032) and Phase 9's (Intelligence, EP-054+) job.**
  `VisionModule` never plans, chains, or autonomously re-dispatches
  based on its own output; it performs exactly one, synchronous,
  caller-requested interpretation per call, identical to
  `desktop`/`browser`/`file`'s own one-action-per-dispatch model.
- **AI Provider Manager (EP-014/015) remains the sole owner of
  provider selection, credentials, and communication.** If Owner
  Decision D1 authorizes AI-provider-based description,
  `VisionModule` depends only on the existing `ProviderManager`/
  `AIProvider` abstraction (via whatever additive method Section 8.3
  proposes) — it never talks to a provider's HTTP API directly, and
  never introduces a second, parallel provider-selection mechanism.

---

## 8. Proposed Architecture

### 8.1 Namespace and module

A new `vision` `CommandModule` (`src/skills/vision/skill.py`,
`VisionModule`), dispatched through the *existing*, unmodified
`CommandRouter.dispatch()` — the fourth `CommandModule` in Phase 8,
following `desktop`/`browser`/`file`'s identical pattern (Section
5.2/5.12). No second dispatch mechanism, no change to
`src/core/command_router.py`.

### 8.2 Backend abstraction

A new `VisionBackend` Protocol (`src/skills/vision/backend.py`)
defines the vision-interpretation contract, mirroring
`ComputerUseBackend`/`BrowserBackend`/`FileBackend`'s own
Protocol-based design exactly:

```python
@runtime_checkable
class VisionBackend(Protocol):
    def image_info(self, path: str) -> ImageInfo: ...
    def extract_text(self, path: str, language: str | None = None) -> OcrResult: ...
```

- `ImageInfo` — a frozen dataclass: `width: int, height: int, format:
  str, mode: str, size_bytes: int` (mirrors `ScreenSize`/
  `Screenshot`'s own plain-data-only style).
- `OcrResult` — a frozen dataclass: `text: str, confidence: float |
  None, language: str` (confidence/language reflect OCR-engine
  Owner Decision D2 below; declared here for shape only, not to
  presuppose D2's outcome).
- `VisionBackendError(Exception)` — the one exception type
  `VisionModule` catches from every backend call, mirroring
  `ComputerUseBackendError`/`BrowserBackendError`/`FileBackendError`'s
  own single-exception-type convention exactly.

`LocalVisionBackend` (`src/skills/vision/local_backend.py`) is
proposed as the sole real implementation for v1 (Owner Decision D1
scopes whether an AI-provider-based second implementation also ships
in v1 or is deferred).

### 8.3 The AI-provider question (Owner Decision D1)

Unlike EP-050/051/052, EP-053 raises a genuine architectural fork
Section 5.5 already surfaced: local, deterministic interpretation
(OCR text extraction, image metadata) vs. semantic description via
whichever AI provider is currently configured (`ProviderManager`,
EP-014). Both are legitimate readings of "Vision Integration"; the
repository does not decide between them on its own. This document
proposes, **subject to Owner Decision D1**, that if AI-provider-based
description is authorized, it be implemented as:

- One new, purely additive method on `AIProvider`
  (`src/core/ai/provider.py`), e.g. `describe_image(self, image:
  bytes, image_format: str, prompt: str | None = None) ->
  ProviderResponse`, with a base implementation that raises
  `ProviderUnavailableError` (identical in spirit to `ask()`'s own
  base implementation) so every provider that does not override it
  remains a fully valid `AIProvider` with zero behavior change —
  exactly how EP-015 added `ask()`/`ping()`/`list_models()` to
  EP-014's base contract without touching `name()`/`status()`/
  `is_available()`/`configuration()`/`health()`.
  - **This is presented as a proposal for explicit owner review, not
    an assumed decision** — extending a Phase 2 core contract
    (`AIProvider`) from a Phase 8 EP is exactly the kind of
    cross-cutting change `AI_GENERATION_STANDARD.md`'s "never
    redesign architecture" rule requires surfacing rather than
    silently making, mirroring how EP-050/051/052 each surfaced (and
    did not silently resolve) the analogous "should `Tool.handler`
    become parameterized" question (Section 5.4, Owner Decision D9
    below).
  - A second `VisionBackend` implementation,
    `ProviderVisionBackend` (or equivalent), would wrap
    `ProviderManager`'s active provider and call this new method —
    itself a separate, later implementation detail, not something
    this document authorizes STEP 2 to build unless D1 selects it.
- If D1 instead scopes v1 to local-only interpretation (OCR +
  metadata), **no `AIProvider` change of any kind occurs in EP-053**,
  and `LocalVisionBackend` is the only backend implementation this EP
  produces.

### 8.4 Why `CommandRouter`, again

Restated from Section 5.4/9.1 (Owner Decision D9): every `vision`
action needs at least one path argument; `Tool.handler`'s
zero-argument-only signature (unchanged since EP-031, confirmed
unchanged by EP-050/051/052) still cannot express this without the
same cross-cutting change three prior EPs already declined to make
unilaterally. This is presented again for explicit owner
confirmation per EP-050/051/052's own precedent of not silently
assuming the answer stays the same forever.

---

## 9. Proposed V1 Capabilities

| Action | Arguments | Description | Requires |
|---|---|---|---|
| `vision help` | none | List available actions. | (always available) |
| `vision info <path>` | image path | Report `ImageInfo` (dimensions, format, mode, file size) — no interpretation, pure metadata. | `vision.enabled` |
| `vision ocr <path> [language]` | image path, optional language code | Extract printed/typed text from the image via OCR (Section 10). | `vision.enabled` |
| `vision describe <path> [prompt]` | image path, optional custom prompt | **Only if Owner Decision D1 authorizes AI-provider-based description** — ask the configured AI provider to describe the image's content. | `vision.enabled` **and** `vision.ai_description.enabled` (Section 11.3) |

This mirrors EP-050/051/052's own "small, explicit action set, plus
`help`" precedent (13/15/9+help actions respectively). `vision
describe` is listed conditionally: Section 20/D1 governs whether it
ships in v1 at all.

### 9.1 What is deliberately NOT an action

No `vision compare` (image diffing), no `vision detect` (object
detection, Section 4), no `vision watch`/`vision monitor` (Section
4's "no live/streaming vision" rule), no `vision crop`/`vision
resize`/any image-*editing* action — EP-053 interprets images, it
never produces or modifies one (that would be a distinct, unrequested
capability with its own security profile, e.g. write-path safety
identical to EP-052's, not something this document's roadmap-driven
scope includes).

---

## 10. Technology Evaluation

### 10.1 Image decoding (required regardless of Owner Decisions)

**Pillow (`PIL`)** is the standard, de-facto Python image-decoding
library: pure-Python-installable (bundles its own C decoders via
wheels, no separate system binary to install, unlike Section 10.2),
BSD-style licensed, and already the obvious, minimal choice for
`vision info`'s metadata extraction (`Image.open(path).size`,
`.format`, `.mode`) regardless of which way Owner Decision D1/D2
resolve. No standard-library alternative exists (`struct`-level
manual header parsing would be a materially worse, more fragile
reimplementation of what Pillow already does correctly and is
explicitly discouraged by `AI_GENERATION_STANDARD.md`'s "never
invent" spirit). **This is a new dependency** (Section 5.9 confirmed
none exists today) — flagged for Owner Decision D7.

### 10.2 OCR engine (required only if Owner Decision D1/D2 select
local OCR)

Three realistic options, evaluated on dependency weight and
offline-capability (matching this project's consistent "offline
first" precedent: Vosk/openWakeWord for STT/wake-word, PyAutoGUI for
desktop, all local):

| Option | Dependency weight | Offline? | Notes |
|---|---|---|---|
| `pytesseract` | Small Python wrapper + **external system binary** (Tesseract OCR, not pip-installable) | Yes | Mirrors Playwright's own "`pip install` + one manual post-install step (`playwright install chromium`)" precedent (`EP051_DESIGN.md` Section 8/22) almost exactly — a system-level OCR engine binary in place of a managed browser binary. |
| `easyocr` | Large — pulls in `torch` (PyTorch) as a transitive dependency | Yes (after first-run model download) | A categorically heavier dependency than anything in Phase 7/8 today; `torch` alone is commonly hundreds of MB. |
| A cloud OCR API (Google Vision OCR, AWS Textract) | Small client library | **No** — network + third-party account/credentials required | Reintroduces exactly the "new external provider/credential" concern Section 4 already excludes from this EP's scope. |

**Recommendation (Section 20, D2): `pytesseract`**, matching
Playwright's own already-accepted "small Python wrapper + one-time
external binary install" pattern rather than introducing a
`torch`-scale dependency or a new cloud credential.

### 10.3 AI-provider-based description (required only if Owner
Decision D1 selects it)

No new dependency: this path reuses the existing `ProviderManager`/
`AIProvider`/`ClaudeProvider` infrastructure (Section 5.5) plus one
additive method (Section 8.3). The image bytes themselves are read
via Pillow (Section 10.1) or directly via `pathlib`, then
base64-encoded/attached per the active provider's own existing HTTP
client conventions inside `ClaudeProvider` — no new HTTP library.

---

## 11. Security Model

### 11.1 Risk profile compared to EP-050/051/052

EP-053 v1, as scoped by Section 9, is **read-only with respect to the
filesystem** — no `vision` action ever creates, modifies, or deletes
a file or directory. Its risk profile is therefore structurally
closer to EP-051's page-observation actions (`page-text`,
`current-url`) than to EP-052's file-mutation actions. The two
genuinely new risks EP-053 introduces are:

1. **Arbitrary local file read** (the same class of risk `file read`
   already has, and already solved, Section 11.2).
2. **Third-party data exfiltration** — *only* if Owner Decision D1
   authorizes `vision describe`: image bytes would leave the local
   machine and be sent to whichever AI provider is currently
   configured (Section 11.3).

### 11.2 Path safety — reuse EP-052's allow-list pattern

Rather than reinvent path safety, this document proposes `vision`
actions be gated by their own `vision.allowed_roots` allow-list,
**configured independently from `file.allowed_roots`** (no runtime
coupling to `FileBackend`, Section 7) but following an identical
default-empty, default-deny structure and the identical
path-traversal/absolute-path rejection logic `LocalFileBackend`
already implements — as a self-contained duplication of a proven,
audited pattern (a `LocalVisionBackend`-owned path-validation helper),
not a shared/imported dependency on `src/skills/files/`. This keeps
`VisionModule` fully decoupled from `FileModule` (Section 7) while
not discarding EP-052's already-reviewed safety design.

### 11.3 AI-provider description — a materially different privacy
category (only relevant if D1 authorizes it)

Sending image bytes to a third-party AI provider is qualitatively
different from every prior Phase 8 privacy consideration
(`EP050_DESIGN.md`/`EP051_DESIGN.md`'s "raw input logging" findings
are about *local* log files, never about data leaving the machine at
all). This document proposes, if D1 authorizes `vision describe`,
that it be gated by a **second, independent flag**,
`vision.ai_description.enabled` (default `false`), separate from
`vision.enabled` — mirroring EP-052's own D3 precedent of a narrower,
separately-gated flag for its own higher-risk action subset
(`file.allow_destructive`). An owner who enables `vision.enabled`
(for local OCR/metadata only) would not thereby also authorize any
image leaving the machine.

### 11.4 No shell/code execution

Consistent with every prior Phase 8 EP's identical rule: `vision`
actions never construct or execute a shell command, and Pillow/
`pytesseract` are invoked strictly through their own Python APIs, not
via `subprocess` wrapping a CLI tool (`pytesseract` itself calls the
Tesseract binary internally via `subprocess`, which is that library's
own, already-widely-audited implementation detail — `VisionModule`
does not add a second such call site).

---

## 12. Human Approval Analysis

`JARVIS_ARCHITECTURE_VISION.md`'s Human Approval principle names
"Deleting files," "Publishing," "Sending emails," "Git push," and
"Production deployment" as irreversible actions requiring
confirmation (already cited by `EP052_DESIGN.md` Section 5.1) — it
names **no** vision-specific example. Since Section 9's proposed v1
action set is entirely read-only (Section 11.1), this document finds
no action here rises to that document's "irreversible action" bar
the way `file delete` did for EP-052. The one exception worth the
owner's explicit attention is `vision describe` (if authorized by
D1): while not "irreversible" in the filesystem sense, sending data
off-machine to a third party is also not something a silent default
should ever do — Section 11.3's separate `vision.ai_description
.enabled` gate is this document's proposed mitigation, not a
per-call confirmation prompt (no such mechanism exists anywhere in
the project today, Section 4, and this EP does not build one either).

---

## 13. Path Safety Model

(Restated/specialized from Section 11.2.) Every `vision` action that
accepts a path argument must, before any Pillow/OCR call:

1. Confirm `vision.enabled` is `true` (re-checked on every dispatch,
   never cached — identical to `desktop.enabled`/`browser.enabled`/
   `file.enabled`'s own convention).
2. Resolve the supplied path to an absolute, normalized form and
   reject any path containing a parent-directory traversal segment
   (`..`) — identical logic to `LocalFileBackend`'s own, already-
   audited implementation (Section 11.2 — duplicated, not imported).
3. Confirm the resolved path falls under at least one entry of
   `vision.allowed_roots` (default empty — `vision.enabled: true`
   alone permits nothing until the owner configures at least one
   root, mirroring `file.allowed_roots`' own D5 precedent exactly).
4. Confirm the resolved path exists and is a file (not a directory)
   before attempting to decode it.

---

## 14. Input/Output (Data/Result) Formats

- **Input:** a local filesystem path (string), exactly like `file
  read`'s own argument shape. No raw bytes, base64 payload, or URL is
  accepted as an argument in v1 (Owner Decision D3).
- **`vision info` output:** a human-readable `CommandResult.message`
  summarizing `ImageInfo` (e.g. `"1920x1080 PNG (RGB), 482,113
  bytes"`), mirroring `desktop screen-size`'s own plain-text
  formatting convention.
- **`vision ocr` output:** the extracted text itself as
  `CommandResult.message` (mirroring `browser page-text`'s own
  "return the extracted content directly" convention), with a
  logged, non-fatal note if no text was detected (not an error —
  "no text found" is a normal, observable outcome, mirroring
  `active_window_title()`'s own "empty string is not a failure"
  precedent, Section 5.7/`desktop/backend.py`).
- **`vision describe` output (if authorized):** the AI provider's
  free-text description as `CommandResult.message`, with the
  provider's own identifying model name included (mirroring `ai use
  <provider>`'s existing "state which provider/model produced this"
  convention referenced by `AIProvider.validate_configured_model()`'s
  docstring, Section 5.5).

---

## 15. Error Handling

- Every `VisionBackend` implementation raises `VisionBackendError`
  (only) for any failure — `VisionModule` catches this one exception
  type, exactly as `DesktopModule`/`BrowserModule`/`FileModule` each
  catch exactly one backend-specific exception type.
- A corrupt, truncated, empty, or unsupported-format image file
  (Section 17) is a `VisionBackendError`, not an uncaught exception —
  translated into a failed `CommandResult` with a clear message,
  never a stack trace surfaced to the caller.
- If `vision.enabled` is `false`, or the backend failed to construct
  at startup (e.g. Tesseract binary genuinely missing from `PATH`,
  Owner Decision D8), every `vision` action returns a clear,
  actionable failed `CommandResult` — mirroring
  `_DISABLED_MESSAGE`/`_UNAVAILABLE_MESSAGE`'s existing wording
  convention in `src/skills/desktop/skill.py` exactly, adapted for
  `vision`.
- `CommandRouter.dispatch()`'s own top-level `except Exception` catch
  remains the final backstop exactly as it already is for every
  other module (Section 5.3) — unchanged, unmodified.

---

## 16. Testability

Mirrors `tests/EP050/test_desktop.py`/`tests/EP051/test_browser.py`/
`tests/EP052/test_file.py`'s own two-tier convention exactly:

- **`tests/EP053/test_vision.py`** — the primary, fully deterministic
  suite, run by default (`test EP053`): argument-shape, gate,
  path-safety, and dispatch-behavior tests against a
  `_FakeVisionBackend` (no real Pillow/Tesseract call), plus a
  smaller set of real-`LocalVisionBackend` tests using a handful of
  tiny, checked-in or programmatically-generated (via Pillow itself,
  in the test file) sample images — never a screenshot of the
  repository owner's actual screen.
- A separate, intentionally **unregistered** manual/integration
  suite (e.g. `tests/EP053/test_vision_ocr_integration.py`) for
  genuine, real-Tesseract-binary OCR accuracy verification —
  following `tests/EP051/test_browser_integration.py`'s own
  precedent of a deliberately-excluded-from-`test all` script for
  environment-dependent verification. **Disclosed limitation, same
  shape as EP-051's:** the development sandbox used for STEP 1-3 may
  not have network egress to install the Tesseract system binary
  (mirroring `EP051_DESIGN.md`'s own disclosed "Playwright's CDN is
  outside the sandbox's allowed network egress list" finding) — this
  would need to be verified during STEP 2 and disclosed exactly as
  transparently as EP-051 disclosed its own equivalent limitation,
  not hidden or assumed away.

---

## 17. Cross-Platform Strategy

Pillow is genuinely cross-platform (pure Python + platform wheels,
no OS-specific branching required — closer to EP-052's
`pathlib`/`shutil` precedent, Owner Decision D10 in `EP052_DESIGN.md`,
than to EP-050's Windows-coupled PyAutoGUI backend). `pytesseract`
itself is also cross-platform, but its **external Tesseract binary**
is installed differently per OS (a system package on Linux, a
separate installer on Windows/macOS) — genuinely analogous to
Playwright's own `playwright install chromium` post-install step
(`EP051_DESIGN.md` Section 8/22), not a code-level platform branch.
`LocalVisionBackend` itself contains no `platform.system()` branching
under this proposal (Owner Decision D10-equivalent question is folded
into D8 below, since it is really about binary availability, not
code paths).

---

## 18. Failure and Fallback Behavior

- **Missing Tesseract binary at startup** (Owner Decision D8): mirrors
  `WindowsComputerUseBackend`'s and `PlaywrightBrowserBackend`'s own
  precedent exactly (`Bootstrap` catches the construction failure,
  logs a warning, falls back to `backend=None`, and `VisionModule`
  reports `_UNAVAILABLE_MESSAGE`-equivalent text for every `vision
  ocr`/`vision describe` call while `vision info` — which needs only
  Pillow, not Tesseract — could still function). This split-
  availability question (does a missing OCR binary disable the whole
  `vision` namespace, or only OCR-dependent actions) is recorded as
  part of Owner Decision D8, since the repository's own precedent
  (`desktop`/`browser`/`file`'s single-flag-disables-everything model)
  does not by itself resolve a namespace with two backends of
  different weight.
- **AI provider unavailable/misconfigured** (only relevant if D1
  authorizes `vision describe`): `ProviderManager`'s existing
  `ProviderUnavailableError`/`ProviderConfigurationError` (Section
  5.5) propagate up through the new additive method exactly as they
  already do for `ask()` today — no new exception-handling pattern
  needed.

---

## 19. Deferred Capabilities

Recorded here, not implemented, not silently assumed:

- Direct Telegram-photo-to-`vision` integration (Section 5.10) — a
  separate, un-scoped input-channel question.
- `ProviderVisionBackend` as a second, always-available
  `VisionBackend` implementation alongside `LocalVisionBackend`
  (Section 8.3) — contingent entirely on Owner Decision D1.
- Any object-detection, face-recognition, video, or live/streaming
  capability (Section 4).
- A `.bak`/soft-delete-style safety net — not applicable, since v1
  performs no mutation at all (Section 11.1).
- A dedicated, louder-named confirmation step before `vision
  describe` sends an image off-machine, beyond the config-gate model
  Section 11.3 proposes — recorded as a reasonable future enhancement
  once this project's "parameterized Tool support"/general
  confirmation-mechanism gap (Section 5.4, and every prior EP's own
  disclosed limitation) is eventually addressed, not a v1 requirement.

---

## 20. Owner Decisions

Per the task's explicit instruction, only genuine questions the
existing architecture and repository cannot answer on their own are
listed here, mirroring `EP050_DESIGN.md`/`EP051_DESIGN.md`/
`EP052_DESIGN.md`'s own Owner Decision format exactly. **None of the
following are approved. STEP 2 will not begin until they are
explicitly reviewed.**

### D1 — Vision engine scope: local-only vs. AI-provider-based description

**Question:** Should EP-053 v1 ship (a) local-only interpretation
(image metadata + OCR text extraction, no data ever leaves the
machine), (b) local interpretation plus AI-provider-based semantic
description (`vision describe`, Section 8.3/9), or (c) AI-provider-
based description only, with no local OCR at all?
**Options:** (a) local-only; (b) both, `vision describe` gated by its
own separate flag (Section 11.3); (c) AI-provider-only.
**Recommended option:** (a) for an initial v1, with (b)'s
`ProviderVisionBackend`/`AIProvider.describe_image()` addition
proposed as a well-defined, ready-to-approve follow-up once D1(a)
has shipped and been verified — **not** because (b) is architecturally
unsound (Section 8.3 shows exactly how it would fit), but because it
is the one part of this design that requires touching a Phase 2 core
contract (`AIProvider`) from a Phase 8 EP, which this document
believes deserves to be reviewed and approved on its own, not bundled
into the same approval as a zero-new-core-contract local-OCR v1.
**Technical reasoning:** (a) requires zero changes outside
`src/skills/vision/`; (b)/(c) require an additive `AIProvider` method
(Section 8.3) plus network calls to a third-party provider for every
`vision describe` invocation.
**Security impact:** (a) has no data-exfiltration surface at all
(Section 11.1); (b)/(c) introduce one, mitigated by Section 11.3's
separate gate.
**Compatibility impact:** none for (a); (b) is purely additive to
`AIProvider` (no existing method's signature changes, Section 4's
explicit prohibition); (c) still requires the same additive method,
so its compatibility impact is identical to (b)'s.
**What changes in STEP 2:** (a) → build only `LocalVisionBackend`
and `vision info`/`vision ocr`. (b) → additionally build
`AIProvider.describe_image()`, `ProviderVisionBackend`, and `vision
describe`, plus `vision.ai_description.enabled` (Section 11.3). (c)
→ build only the AI-provider path, dropping `vision ocr`/D2 entirely
(not recommended — discards OCR's zero-dependency-risk, zero-privacy-
risk value for no stated benefit).

### D2 — OCR engine choice

**Question:** If D1 includes local OCR, should EP-053 use `pytesseract`
(wraps an external Tesseract binary), `easyocr` (bundles/downloads its
own ML models via `torch`), or defer OCR to a cloud API?
**Options:** (a) `pytesseract`; (b) `easyocr`; (c) a cloud OCR API.
**Recommended option:** (a) — Section 10.2's evaluation.
**Rationale:** Matches Playwright's own already-accepted "small
wrapper + one-time external binary install" precedent
(`EP051_DESIGN.md` D1) instead of introducing a `torch`-scale
dependency (b) or a new third-party network credential (c, which
would also reopen the exact privacy question Section 11.3 raises for
D1(b) — for a materially worse trade, since OCR does not need
semantic understanding at all).
**Security impact:** (a)/(b) are both fully offline (no data leaves
the machine for OCR itself); (c) is not.
**Compatibility impact:** none of the three touches any existing
file — this is purely a new-dependency choice.
**What changes in STEP 2:** (a) adds `pytesseract` + `Pillow` to
`requirements.txt` with an `EP-053`-labeled comment (mirroring
Playwright's own labeled-comment precedent) and documents the
one-time system Tesseract install step in the same file; (b) instead
adds `easyocr`/`torch` (much larger install footprint, longer STEP 2
verification); (c) adds a cloud-SDK dependency plus new credential
configuration (a materially different, larger STEP 2 scope this
document does not recommend).

### D3 — Image input source

**Question:** Should `vision` actions accept only a local filesystem
path (mirroring `file read`), or also raw bytes/base64/a URL
directly (e.g. for a future Telegram-photo integration, Section 19)?
**Options:** (a) path only; (b) path or base64-encoded bytes as an
alternate argument form; (c) path or a remote URL Jarvis fetches
itself.
**Recommended option:** (a).
**Rationale:** (b) reopens a command-line-length/encoding concern
`CommandRouter`'s simple whitespace-tokenized dispatch (Section 5.3)
is not designed for (a multi-megabyte base64 string as a single
shell-style argument); (c) would require EP-053 to perform its own
network fetch, introducing a URL-based SSRF-shaped risk with no
existing precedent or safety review anywhere in this project's prior
EPs. Path-only keeps EP-053 exactly as simple, and exactly as
consistent with `file read`'s own argument shape, as EP-052 already
established.
**Security impact:** (a) inherits only Section 13's already-reviewed
path-safety model; (b)/(c) would each need their own, new safety
review this document does not attempt.
**Compatibility impact:** none — this only affects what `vision`
actions accept, not any existing code.
**What changes in STEP 2:** (a) → `vision info <path>`/`vision ocr
<path>` exactly as Section 9 proposes. (b)/(c) → additional argument-
parsing and validation logic, and (for c) a new outbound-network
safety analysis this document has not performed and would need to be
requested as a STEP 1 revision, not assumed into STEP 2.

### D4 — Path safety model

**Question:** Should `vision` actions reuse `file.allowed_roots`
directly (a runtime dependency on `FileBackend`/`FileModule`), define
their own, independent `vision.allowed_roots` (Section 11.2's
proposal), or apply no path restriction at all beyond OS
permissions (matching `desktop`/`browser`'s own simpler, single-flag
model)?
**Options:** (a) independent `vision.allowed_roots`, duplicating
`LocalFileBackend`'s validation logic (Section 11.2); (b) a direct
runtime dependency on the existing `FileBackend`/`file_backend`
Bootstrap property for path validation; (c) `vision.enabled` alone,
no allow-list.
**Recommended option:** (a).
**Rationale:** (b) creates exactly the kind of cross-module hidden
coupling `AI_GENERATION_STANDARD.md`'s "No Hidden Coupling" rule
warns against — `VisionModule` would depend on `file.enabled` being
configured correctly (or `FileModule`'s internals) for a capability
that has nothing to do with file management; it would also mean
`vision` becomes unusable whenever `file.enabled` is `false`, an
unrelated-seeming coupling an owner would not expect. (c) discards a
review-proven safety mechanism for no benefit — arbitrary local file
read is a genuine risk (Section 11.1) regardless of `vision`'s
read-only status. (a) costs a small amount of intentional code
duplication (the same trade-off `EP052_DESIGN.md` itself weighed
under its own D4) in exchange for `VisionModule` remaining fully
self-contained and independently configurable.
**Security impact:** (a)/(c) — see above. (b) is not meaningfully
less secure than (a), only architecturally worse.
**Compatibility impact:** none — `vision.allowed_roots` is a new,
independent config key regardless of which option is chosen.
**What changes in STEP 2:** (a) → `LocalVisionBackend` implements its
own path-validation helper (Section 13). (b) → `VisionModule`'s
constructor gains a `FileBackend` parameter, and `Bootstrap`'s
`vision` wiring block must run after (and depend on) `file`'s. (c) →
Section 13's steps 2-3 are dropped entirely.

### D5 — Supported image formats and resource limits

**Question:** Which image formats should v1 accept, and should there
be an explicit maximum file size/resolution before `vision info`/
`vision ocr` refuses to process an image (to bound memory/CPU use)?
**Options considered:** (a) accept whatever Pillow's default-installed
plugins support (PNG, JPEG, BMP, GIF, TIFF, WEBP) with no explicit
size/resolution cap beyond what Pillow itself enforces internally
(Pillow's own `Image.MAX_IMAGE_PIXELS` decompression-bomb guard,
already on by default); (b) as (a), plus an explicit,
configurable `vision.max_file_size_mb`/`vision.max_dimension` pair
this project defines itself (mirroring `desktop.screenshot
.max_dimension`'s own existing precedent, Section 5.7's `Screenshot`
dataclass docstring); (c) a narrower, explicit allow-list of formats
(e.g. PNG/JPEG only).
**Recommendation:** (b) — an explicit, project-owned limit is more
predictable and auditable than relying solely on Pillow's own
internal default, and directly mirrors an already-accepted precedent
in this exact codebase (`desktop.screenshot.max_dimension`).
**Rationale:** Section 18's failure-mode discussion benefits from a
single, clear "input too large, refused" `CommandResult` rather than
an unhandled `MemoryError`/decompression-bomb condition; (c) is
unnecessarily restrictive given Pillow supports the broader set
safely.
**Security impact:** (b) directly mitigates a decompression-bomb/
resource-exhaustion risk that is realistic for any image-decoding
capability, local-file-based or not.
**Compatibility impact:** none — new, independent config keys.
**What changes in STEP 2:** (b) → `LocalVisionBackend` checks file
size and, after opening with Pillow, pixel dimensions, before OCR/
full decode proceeds, returning `VisionBackendError` with a clear
message if exceeded.

### D6 — CPU/GPU expectations

**Question:** Should EP-053 v1 assume CPU-only execution (matching
every prior Phase 7/8 EP's own local-hardware assumptions — Vosk,
openWakeWord, and PyAutoGUI are all CPU-only today), or should GPU
acceleration be evaluated for OCR/description?
**Options:** (a) CPU-only, no GPU code path of any kind; (b) optional
GPU acceleration if available.
**Recommendation:** (a).
**Rationale:** `pytesseract`/Tesseract (D2's recommended option) is
CPU-only by nature; GPU acceleration is only a meaningful question
for `easyocr`'s `torch` backend (D2's non-recommended option) or a
future, heavier vision-model runtime this document does not propose
(Section 4). Introducing GPU-detection code for a capability that
does not need it would be exactly the kind of speculative
abstraction `AI_GENERATION_STANDARD.md`'s Clean Code Policy (YAGNI)
forbids.
**Security impact:** none either way.
**Compatibility impact:** none.
**What changes in STEP 2:** (a) → no GPU-related code anywhere in
`src/skills/vision/`. (b) → would only become relevant if D2 selects
`easyocr` instead of `pytesseract`, which this document does not
recommend.

### D7 — New dependency approval (Pillow, and OCR engine per D2)

**Question:** `AI_GENERATION_STANDARD.md`'s "Existing Dependencies
Policy" requires new third-party dependencies to be explicitly
justified and never silently added. Does the owner approve adding
Pillow (required regardless of D1/D2, Section 10.1) and, if D1/D2
select local OCR, `pytesseract` plus the external Tesseract system
binary (Section 10.2)?
**Options:** (a) approve both; (b) approve Pillow only (if D1 selects
AI-provider-description-only, `pytesseract` becomes unnecessary); (c)
approve neither (blocks this EP entirely — no viable path to any
image interpretation without at least Pillow).
**Recommendation:** (a), or (b) if D1 selects option (c) from D1's
own choice set.
**Rationale:** Section 10.1/10.2 already show no viable alternative
achieves this EP's stated goals (Section 3) without at least Pillow;
(c) would leave EP-053 unable to satisfy Section 2's problem
statement at all.
**Security impact:** Pillow and `pytesseract` are both widely used,
actively maintained libraries; no known systemic security concern
beyond the decompression-bomb class Section 20/D5 already addresses.
**Compatibility impact:** none — purely additive `requirements.txt`
entries, following the exact labeled-comment convention every prior
EP's own dependency addition already established.
**What changes in STEP 2:** the approved subset of `Pillow==<pinned>`
and `pytesseract==<pinned>` (version pins to be selected at STEP 2,
matching `playwright==1.62.0`/`openwakeword==0.6.0`'s own pinning
precedent for anything format/version-sensitive) is added to
`requirements.txt` with an EP-053-labeled comment documenting the
one-time Tesseract system-binary install step, exactly as
`playwright==1.62.0`'s own comment documents `playwright install
chromium`.

### D8 — Missing-binary fallback behavior

**Question:** If `pytesseract` is installed but the underlying
Tesseract system binary is not present on `PATH` at startup (Section
18), should this disable the entire `vision` namespace (matching
`desktop`/`browser`/`file`'s own single-backend, single-flag "all or
nothing" model), or should `vision info` (Pillow-only, no Tesseract
dependency) remain available while only `vision ocr`/`vision
describe` report unavailable?
**Options:** (a) all-or-nothing — `LocalVisionBackend` construction
fails entirely if Tesseract is missing, disabling `vision info` too,
for maximum consistency with EP-050/051/052's precedent; (b)
split availability — `vision info` remains usable via a
Pillow-only code path even when OCR is unavailable.
**Recommendation:** (b).
**Rationale:** Unlike `desktop`/`browser`/`file`, which each have
exactly one backend implementation with uniform capability, `vision`
is the first Phase 8 EP whose real backend has two internally
different dependency weights (Pillow, always available once
installed via pip, vs. Tesseract, a separate system binary that may
genuinely be absent) — collapsing that distinction into "all or
nothing" would make `vision info` needlessly unavailable for a
reason (a missing OCR engine) that has nothing to do with reading an
image's dimensions.
**Security impact:** none either way.
**Compatibility impact:** none — this only affects `LocalVisionBackend`'s
own internal construction/dispatch logic.
**What changes in STEP 2:** (b) → `LocalVisionBackend.extract_text()`
raises `VisionBackendError` specifically when Tesseract is
unavailable (checked lazily, on first OCR call, or eagerly at
construction and cached as a boolean — an implementation detail for
STEP 2), while `image_info()` never depends on Tesseract at all. (a)
→ a single construction-time check gates both methods identically.

### D9 — CommandRouter vs. Tool Engine

**Question:** Should `VisionModule` dispatch through `CommandRouter`
(as this document proposes, Section 8.4) or attempt to use/extend
Tool Engine?
**Options:** (a) `CommandRouter`, matching EP-050/051/052 exactly; (b)
extend Tool Engine to support parameterized handlers first, then
build `VisionModule` on top of it; (c) a bespoke vision-specific
dispatch abstraction.
**Recommended option:** (a).
**Rationale:** Restated from Section 5.4/8.4 — this is the fourth
independent EP to reach the same conclusion for the same reason
(`Tool.handler`'s zero-argument-only signature), presented again for
explicit confirmation rather than silently assumed to still hold,
per this project's own established practice.
**Security impact:** none either way — a pure dispatch-mechanism
choice.
**Compatibility impact:** (a) requires no `src/core/tool/` change at
all; (b) would require a cross-cutting Tool Engine change this EP is
not authorized to make unilaterally.
**What changes in STEP 2:** (a) → `VisionModule` registers with
`CommandRouter` exactly like `DesktopModule`/`BrowserModule`/
`FileModule`. (b)/(c) are not planned by this document at all.

### D10 — Test strategy for the OCR-dependent path

**Question:** Given Section 16's disclosed sandbox-Tesseract-
availability uncertainty (mirroring EP-051's own disclosed
Playwright/Chromium sandbox limitation), how should the primary,
always-run `tests/EP053/test_vision.py` suite be structured so it
does not silently depend on an environment-specific binary being
present?
**Options:** (a) the primary suite tests `VisionModule`'s dispatch/
gate/path-safety logic entirely against `_FakeVisionBackend` (no real
Pillow/Tesseract call at all) — real-`LocalVisionBackend`-against-
real-Tesseract tests live only in the separate, unregistered
integration script (Section 16); (b) the primary suite includes real
Pillow-based `image_info()` tests (Pillow has no external binary
dependency, Section 10.1, so this is always safe to run) but keeps
real-Tesseract-based `extract_text()` tests in the separate,
unregistered script only; (c) the primary suite attempts real
Tesseract calls and is allowed to report disclosed skips if the
binary is absent, mirroring `tests/EP049`'s own one disclosed-skip
precedent.
**Recommendation:** (b).
**Rationale:** (a) needlessly excludes `image_info()`'s real-Pillow
path from `test EP053`'s default, always-green run even though
Pillow has no external-binary risk at all (Section 10.1); (c) risks
`test EP053` reporting a non-zero skip count by default, which
`AI_DEVELOPMENT_PLAYBOOK.md`'s own Phase 3 testing rule explicitly
treats as a condition to "repeat until ... Skipped = 0 (unless
intentionally skipped)" — (b) keeps the default suite's skip count at
zero unconditionally by design, not by hoping the sandbox happens to
have Tesseract installed.
**Security impact:** none.
**Compatibility impact:** none.
**What changes in STEP 2:** (b) → `tests/EP053/test_vision.py`
contains fake-backend tests (dispatch/gate/path-safety/argument-
shape) plus real-Pillow `image_info()` tests using small,
programmatically-generated sample images; `tests/EP053/
test_vision_ocr_integration.py` (unregistered) contains real-
Tesseract `extract_text()` accuracy tests, with any sandbox
limitation disclosed exactly as transparently as `EP051_AUDIT.md`
already disclosed its own equivalent Playwright/Chromium finding.

---

## 21. STEP 2 Proposed Scope

Not authorized by this document — presented only so the owner can
evaluate what approving Section 20's decisions would actually
authorize, per `EP050_DESIGN.md`/`EP051_DESIGN.md`/`EP052_DESIGN.md`'s
own "plan only" precedent for this section. **Exact contents depend
on D1/D2/D4/D8's final answers**; the set below assumes the
recommended options throughout.

### CREATE

- `src/skills/vision/backend.py` — `VisionBackend` Protocol,
  `VisionBackendError`, `ImageInfo`, `OcrResult` (Section 8.2).
- `src/skills/vision/local_backend.py` — `LocalVisionBackend`, the
  sole real implementation under the recommended options (Section
  8.2/10).
- `src/skills/vision/skill.py` — `VisionModule` (Section 8.1).
- `tests/EP053/test_vision.py` — primary automated suite (Section
  16/D10).
- `tests/EP053/test_vision_ocr_integration.py` — separate,
  intentionally unregistered real-Tesseract verification script
  (Section 16/D10).

**If, and only if, Owner Decision D1 selects option (b) or (c)**
(AI-provider-based description), additionally:

- `src/skills/vision/provider_backend.py` — `ProviderVisionBackend`
  (Section 8.3/19).
- One new, purely additive method on the existing
  `src/core/ai/provider.py` (`AIProvider.describe_image()`, Section
  8.3) — the only change to an existing file this larger scope would
  require.

### MODIFY

- `src/bootstrap.py` — additive only: one new import block, one new
  conditional `LocalVisionBackend` construction (gated on
  `vision.enabled`, mirroring `desktop.enabled`/`browser.enabled`/
  `file.enabled`'s wiring exactly, Section 5.12), one new
  `VisionModule(...)` construction added to `register_modules()`'s
  call list, one new read-only `vision_backend` property. No
  existing module's construction, order, or arguments changes.
- `config/config.yaml` — additive only: one new `vision:` block
  (`vision.enabled` default `false`, `vision.allowed_roots` default
  `[]` per D4, `vision.max_file_size_mb`/`vision.max_dimension` per
  D5, plus `vision.ai_description.enabled` default `false` only if
  D1 authorizes it, Section 11.3). No existing key's meaning,
  default, or validation changes.
- `requirements.txt` — additive only: `Pillow==<pinned>` (always),
  `pytesseract==<pinned>` (if D1/D2 select local OCR), each with an
  EP-053-labeled comment matching every prior EP's own convention
  (Section 20/D7).

### DO NOT MODIFY

- `src/core/command_router.py` — zero changes (Section 5.3/9, D9).
- `src/core/tool/` — zero changes (Section 5.4/9, D9).
- `src/core/execution/` (EP-003) — zero changes (Section 5.8).
- `src/skills/desktop/`, `src/skills/browser/`, `src/skills/files/`
  — zero changes (Section 7); `desktop screenshot`/`browser
  screenshot`'s existing behavior is left exactly as EP-050/EP-051
  shipped and audited it, and `file read`'s UTF-8-only behavior is
  left exactly as EP-052 shipped it.
- `src/core/ai/provider.py`'s **existing** methods
  (`name()`/`status()`/`is_available()`/`configuration()`/
  `health()`/`ask()`/`ping()`/`list_models()`/
  `validate_configured_model()`) and every existing `AIProvider`
  subclass's existing behavior — unchanged under every option of
  every Owner Decision in this document; the *only* possible change
  to this file, gated entirely behind Owner Decision D1, is one new,
  purely additive method with a safe, no-op-raising base
  implementation (Section 8.3/21).
- Every prior EP's design/audit document.

### Dependencies that would need to change

- `Pillow` (new, always required under the recommended options,
  Section 10.1/D7).
- `pytesseract` (new, required only if D1/D2 select local OCR,
  Section 10.2/D7) plus a one-time, documented external Tesseract
  system-binary install step (not expressible purely through
  `requirements.txt`, mirroring `playwright install chromium`'s own
  precedent).

### Tests to be added

- `tests/EP053/test_vision.py` (Section 16/D10).
- `tests/EP053/test_vision_ocr_integration.py`, unregistered
  (Section 16/D10).

### Configuration changes

- New `vision:` block in `config/config.yaml` (Section 21/D4/D5/D8/D9
  pending final values).

### Documentation changes that should happen later (STEP 3/4, not now)

- `docs/architecture/JARVIS_ROADMAP.md` — update EP-053's status line
  once STEP 2 begins/completes, following EP-050/051/052's own
  status-line format precedent exactly.
- `docs/BACKLOG.md` — update EP-053's entry analogously.
- `docs/architecture/audits/EP053_AUDIT.md` — created at STEP 4
  (Architecture Audit), not before.

None of the above has been performed during STEP 1. This section is
a plan only, per the task's explicit instruction.

---

## 22. STEP 1 Acceptance Criteria

This document satisfies STEP 1 completion when:

- [x] The repository was directly inspected (not assumed) for every
  document and code area the task listed as a minimum (Sections
  5–7).
- [x] All 22 required design questions (Sections 2–19, this
  section) are answered with cited, repository-grounded evidence.
- [x] Every genuinely open question requiring owner judgment —
  distinct from the roadmap's own already-settled architecture — is
  captured as a numbered Owner Decision (Section 20), each with
  Options, a Recommended option, Technical reasoning, Security
  impact, Compatibility impact, and what changes in STEP 2.
- [x] No Owner Decision is marked APPROVED.
- [x] No source, test, configuration, dependency, or Bootstrap file
  was created or modified.
- [x] STEP 2 has not begun, and this document does not assume any
  Owner Decision's outcome when describing Section 21's proposed
  scope (each item is explicitly conditioned on the relevant
  decision).
- [x] The document's status is explicitly marked "STEP 1 — DESIGN
  COMPLETE / OWNER APPROVAL REQUIRED," and explicitly states "STEP 2
  implementation has NOT begun."

---

## Owner Approval Checklist

The following Owner Decisions (Section 20) require explicit,
itemized review before STEP 2 (Implementation) may begin, per
`AI_DEVELOPMENT_PLAYBOOK.md`'s Prompt Strategy ("Never continue
automatically. Always wait for the user's approval."):

- [ ] **D1** — Vision engine scope: local-only vs. AI-provider-based
  description (recommended: local-only v1, AI-provider-description
  as a defined follow-up).
- [ ] **D2** — OCR engine choice (recommended: `pytesseract`).
- [ ] **D3** — Image input source (recommended: local file path
  only).
- [ ] **D4** — Path safety model (recommended: independent
  `vision.allowed_roots`, no runtime `FileBackend` coupling).
- [ ] **D5** — Supported image formats and resource limits
  (recommended: Pillow's default formats + explicit, configurable
  size/dimension caps).
- [ ] **D6** — CPU/GPU expectations (recommended: CPU-only, no GPU
  code path).
- [ ] **D7** — New dependency approval: Pillow (+ `pytesseract` if
  D1/D2 select local OCR) plus the external Tesseract system binary.
- [ ] **D8** — Missing-binary fallback behavior (recommended: split
  availability — `vision info` remains usable without Tesseract).
- [ ] **D9** — `CommandRouter` vs. Tool Engine (recommended:
  `CommandRouter`, matching EP-050/051/052).
- [ ] **D10** — Test strategy for the OCR-dependent path
  (recommended: fake-backend suite + real-Pillow tests in the
  primary suite; real-Tesseract tests in a separate, unregistered
  integration script).

**STEP 2 (Implementation) will not begin until these are reviewed and
approved, revised, or rejected by the owner in a separate prompt.**

End of document.
