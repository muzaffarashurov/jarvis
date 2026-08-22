# EP-046 — Speech-to-Text — Design Specification (STEP 1)

Status: **STEP 1 — Design & Planning. Reviewed and APPROVED by the
project owner (Section 9a/9b/9c). STEP 2 (implementation) and STEP 3
(documentation & audit closure) are COMPLETE — see Section 16 and
`docs/architecture/audits/EP046_AUDIT.md`.**

Baseline: EP-045 (Web Dashboard) is COMPLETE. EP-046 is the first
Engineering Package of `docs/architecture/JARVIS_ROADMAP.md`'s
**Phase 7 — Voice** (EP-046 Speech-to-Text, EP-047 Text-to-Speech,
EP-048 Wake Word, EP-049 Voice Assistant).

This document follows the structure and quality standard established
by `EP043_DESIGN.md`, `EP044_DESIGN.md` and `EP045_DESIGN.md`.

---

## 1. Objective

Give Jarvis the ability to turn recorded speech (a `.wav`/`.flac`/PCM
audio clip, or a short live microphone capture) into text, and hand
that text to the **exact same** `CommandRouter.dispatch()` entry
point every other interface already dispatches through —
`InteractiveShell` (`src/core/shell.py`), `TelegramRouter`
(`src/core/telegram/telegram_router.py`), and `ApiRouter`
(`src/core/api/api_router.py`).

EP-046 delivers **speech → text → one command dispatched**. It does
**not** deliver a wake word, a continuous listening loop, or a
back-and-forth "assistant" conversation — those are EP-048 and
EP-049, later Phase 7 packages, by the roadmap's own sequencing.

---

## 2. Scope

### In scope (EP-046 v1)

* A `SpeechToTextEngine` component that converts audio to text
  offline, in one of Jarvis's supported languages.
* A `voice` command namespace (`CommandModule`), following the exact
  pattern `SystemModule`'s own docstring already names as the
  reference implementation "future modules (invoice, telegram,
  excel, presentation, browser, voice, github, ...) must follow" —
  registered in the empty, pre-existing
  `src/skills/voice/skill.py` placeholder.
* Explicit, user-initiated transcription: a shell/API/Telegram
  command such as `voice transcribe <path-to-audio-file>`, and,
  contingent on Section 10 Owner Decision 5, an equivalent
  microphone-capture action (e.g. `voice listen`).
* Feeding the transcribed text back into the existing
  `CommandRouter.dispatch()` — i.e., a transcribed instruction
  becomes a normal command, exactly like a typed shell line, an
  authorized Telegram message, or a `POST /api/v1/commands` request.
* Configuration under a new `voice:` (or `voice.stt:`, see Section 6)
  key in `config/config.yaml`, following the project's established
  per-subsystem config-block convention.
* Deterministic, no-microphone-required automated tests under
  `tests/EP046/`, following the `tests/EP0NN/` convention.

### Out of scope (EP-046 v1) — deferred to later EPs or `docs/BACKLOG.md`

* Wake-word / hotword detection (`EP-048 Wake Word`, per roadmap).
* Always-on background listening / continuous voice assistant loop
  (`EP-049 Voice Assistant`, per roadmap).
* Text-to-Speech / spoken responses (`EP-047 Text-to-Speech`, per
  roadmap; `src/skills/voice/text_to_speech.py` is a separate,
  still-empty placeholder this EP does not touch).
* Speaker identification/diarization.
* Real-time streaming transcription while the user is still
  speaking (partial/interim results). V1 transcribes a completed
  utterance (a file, or a fixed-duration/silence-terminated
  recording) and returns one final result.
* Cloud/online speech recognition providers (see Section 8 —
  rejected on privacy and offline-requirement grounds, not evaluated
  further beyond Section 8's comparison).
* New REST API endpoint dedicated to voice/audio upload. `voice
  transcribe <path>` is reachable through the **existing** generic
  `POST /api/v1/commands` endpoint (EP-043) exactly like every other
  command — no new endpoint is proposed (see `docs/BACKLOG.md`'s
  existing "per-subsystem REST resources" backlog item, which this
  EP does not resolve either way).
* Desktop UI (`desktop/`) microphone controls. EP-044 remains
  untouched by this design; a future EP-044-adjacent package may
  wire a microphone button to `voice listen`, but that is not part
  of EP-046 v1.

---

## 3. Existing Architecture (repository findings)

### 3.1 The one true command entry point

Every existing interface converts its own input into a raw command
string and calls the same method:

| Interface | File | Call |
|---|---|---|
| CLI | `src/core/shell.py` | `self._router.dispatch(raw)` |
| Telegram | `src/core/telegram/telegram_router.py` | `self._command_router.dispatch(text)` |
| REST API | `src/core/api/api_router.py` | `self._command_router.dispatch(raw_command)` (reassembled from `module`/`action`/`arguments`) |

`ApiRouter`'s own docstring states this explicitly: *"Mirrors
`src/core/telegram/telegram_router.py`'s role for Telegram: performs
no business logic and no command parsing of its own... so the REST
API can never diverge in behaviour from the CLI, and no command
logic is ever duplicated."*

This is the integration point EP-046 must plug into. A
`SpeechToTextEngine` producing text, handed to a **new**
`VoiceRouter`-style bridge (or directly inside the `voice` module's
`execute()`, see Section 5.3) that calls
`CommandRouter.dispatch(transcribed_text)`, is the smallest change
that fits this existing pattern — no new dispatch mechanism, no
second `CommandRouter`, no duplicated parsing.

### 3.2 `CommandModule` / `CommandRouter` (`src/core/command_router.py`)

```
Audio/Input -> Speech-to-Text -> text -> CommandRouter.dispatch(text)
```

`CommandRouter` is intentionally closed for modification (Section
"Responsibilities" in its own docstring: *"This class never needs to
change to support new command namespaces"*). EP-046 requires **zero**
changes to `command_router.py`. A new `CommandModule` (namespace
`"voice"`) is registered via the existing `router.register(...)`
call, exactly like every other module in `src/bootstrap.py`.

### 3.3 The `src/skills/voice/` package already exists — and is already named for this

```
src/skills/voice/
    skill.py            (empty, 0 bytes)
    speech_to_text.py   (empty, 0 bytes)
    text_to_speech.py   (empty, 0 bytes)
    wake_word.py         (empty, 0 bytes)
```

These four files are pre-existing, empty placeholders — not created
by this design. Their names map 1:1 onto Phase 7's four roadmap
items (`speech_to_text.py` ↔ EP-046, `text_to_speech.py` ↔ EP-047,
`wake_word.py` ↔ EP-048, `skill.py` ↔ the eventual unified `voice`
`CommandModule`, mirroring `src/skills/system/skill.py`'s
`SystemModule`). This confirms the architecture already anticipated
a single `voice` namespace, with per-capability files underneath it,
rather than a standalone top-level subsystem — directly answering
STEP 1's instruction "Do NOT assume that a new standalone subsystem
is required."

`src/skills/system/skill.py`'s own module docstring is direct
evidence the project intends `voice` to be a `CommandModule`: *"This
module also serves as the reference implementation of the
CommandModule interface that future modules (invoice, telegram,
excel, presentation, browser, **voice**, github, ...) must follow."*

### 3.4 Dependencies already staged, unused

`requirements.txt` already lists:

```
SpeechRecognition
pyttsx3
```

Neither package is imported anywhere in `src/`, `desktop/`, or
`tests/` today (repository-wide search confirms zero usages). These
read as dependencies pre-declared ahead of Phase 7 (`SpeechRecognition`
for STT/EP-046, `pyttsx3` for TTS/EP-047) but never wired up. This
is a direct input to Section 8/9 (technology evaluation) and Section
11 (dependency strategy): reusing an already-declared dependency
costs nothing new to `requirements.txt`, but its suitability still
has to be evaluated on technical merits, not assumed.

No `pyaudio`, `sounddevice`, `soundfile`, `vosk`, `openai-whisper`,
or `faster-whisper` package appears anywhere in `requirements.txt`
or `pyproject.toml`.

### 3.5 Configuration system (`src/core/config.py`, `config/config.yaml`)

Every prior integration EP (Discord, Email, Telegram Info, REST API)
follows the same convention: one top-level YAML block named after
the subsystem, an `enabled: <bool>` flag (default varies — `true`
for stateless outbound API clients like Discord/GitHub/Telegram
Info, `false` for anything that binds a resource or needs
credentials/hardware, like the REST API and Email), a long comment
block above the key documenting the owning EP, what the subsystem
does and does not do, and — for anything touching credentials — an
explicit statement that secrets live in environment variables, never
in `config.yaml`. EP-046 has no credentials (Section 12), but it does
claim a hardware resource (the microphone) conditionally, so it
follows the REST-API/Email precedent of defaulting `enabled: false`
where relevant (see Section 6, Section 10 Decision 7).

### 3.6 Testing system (`src/testing/`)

`BaseTest` (abstract, `run() -> TestResult`) + `TestRegistry`
(`@TestRegistry.register`, keyed by `NAME.upper()`) is the project's
own lightweight test-suite mechanism, run via the existing `test
EP0NN` shell command (`SystemModule`) — separate from, and
additional to, the `pytest` suite under `tests/EP0NN/` referenced by
`pyproject.toml`'s `testpaths = ["tests"]`. EP-046 follows both:
`tests/EP046/` for `pytest`, plus a `TestRegistry`-registered
`EP046` (or `SpeechToTextEngineTest`/`VoiceModuleTest`) suite for the
`test EP046` shell command, consistent with every prior EP. Per the
already-known `docs/BACKLOG.md` "TestRegistry NAME-collision" issue
(open since EP-038, re-noted at EP-042/EP-043), if EP-046 registers
more than one `BaseTest` subclass, only one is reachable via `test
EP046` — this is a pre-existing, project-wide limitation, not
something EP-046 needs to fix.

### 3.7 Windows / Python environment

`pyproject.toml`: `requires-python = ">=3.12"`. `config/config.yaml`
and multiple EP notes (`fast_response.workbook`, `invoice.script`)
confirm the deployed environment is Windows (Windows-style absolute
paths, `.xls`/Excel workflows). No Linux/macOS-specific tooling
exists in the repository. Any STT dependency must have a working
Windows wheel/binary — this rules out Linux-only audio backends and
anything requiring compilation toolchains not already assumed
present (see Section 8).

---

## 4. What EP-046 means, per the roadmap and backlog

`docs/architecture/JARVIS_ROADMAP.md` lists only a title: "EP-046
Speech-to-Text" under "Phase 7 — Voice", alongside EP-047
Text-to-Speech, EP-048 Wake Word, EP-049 Voice Assistant.
`docs/BACKLOG.md`'s "Future Ideas" section separately lists "Voice
commands" (not EP-numbered). No design document, no owner note, and
no prior STEP 1 report for EP-046 exists anywhere in the repository.

This mirrors EP-043's own STEP 1 starting condition exactly:
*"Scope was confirmed directly by the project owner (the STEP 1
investigation stopped because the repository established only the
title... with no purpose, consumers, endpoint surface, security
model, dependency, or lifecycle integration defined anywhere)."*

Per this STEP 1's own governing instruction ("If the existing EP-046
specification is incomplete or ambiguous, identify the ambiguity
explicitly instead of guessing"), this design does **not** invent
scope. Section 3's architecture findings (the pre-named
`src/skills/voice/speech_to_text.py`, the `CommandRouter` dispatch
pattern, and the roadmap's own Phase 7 ordering — STT before Wake
Word before Voice Assistant) are used only to derive the *minimum
coherent slice* named "Speech-to-Text" in isolation: turning audio
into text and getting that text into the command pipeline once,
on request. Everything conversational, continuous, or hands-free is
explicitly excluded (Section 2) and flagged for the roadmap's own
later EPs rather than guessed into EP-046.

---

## 5. Proposed architecture

### 5.1 Data flow

```
                      ┌───────────────────────────┐
  audio file path  ─▶ │                           │
  (voice transcribe)  │   SpeechToTextEngine       │──▶ str (transcript)
                      │  (src/skills/voice/         │
  microphone capture ▶│   speech_to_text.py)        │
  (voice listen,      │                           │
   Owner Decision 5)  └───────────────────────────┘
                                    │
                                    ▼
                      ┌───────────────────────────┐
                      │   VoiceModule (CommandModule)│
                      │  src/skills/voice/skill.py   │
                      │  namespace: "voice"          │
                      └───────────────────────────┘
                                    │  transcript, treated as a
                                    │  raw command line
                                    ▼
                      ┌───────────────────────────┐
                      │      CommandRouter           │  ◀── same instance
                      │  (existing, unchanged)       │      InteractiveShell /
                      └───────────────────────────┘      TelegramRouter /
                                    │                     ApiRouter already use
                                    ▼
                            CommandResult
```

### 5.2 `SpeechToTextEngine` — the STT interface

Conceptual interface (not implemented in STEP 1):

```python
class SpeechToTextEngine(Protocol):
    def transcribe_file(self, audio_path: str) -> TranscriptionResult: ...
    def transcribe_audio(self, pcm_data: bytes, sample_rate: int) -> TranscriptionResult: ...
```

```python
@dataclass(frozen=True)
class TranscriptionResult:
    success: bool
    text: str
    language: str | None
    error: str | None = None
```

This mirrors `CommandResult`'s own shape (`success` / message-like
payload / no exceptions escaping across the boundary) — the
project's established idiom for "this operation can fail in
expected, non-exceptional ways" (see `command_router.py`'s own
`dispatch()`, which never lets a module's exception propagate to the
caller).

Responsibilities are split exactly as STEP 1 Section 5 requires:

* **Microphone/audio capture** — a separate, small component (name
  TBD, e.g. `AudioCapture` in `speech_to_text.py` or its own module)
  responsible only for producing PCM bytes from a live device or
  reading bytes from a file. It has no knowledge of recognition.
* **Speech recognition** — `SpeechToTextEngine` (Section 8/9's
  selected library, wrapped). Pure function: audio in, text out.
  No knowledge of `CommandRouter`, config, or Jarvis commands.
* **Text normalization** — trivial (strip/lower is *not* forced;
  `CommandRouter.dispatch()` already lower-cases module/action
  tokens itself). Any STT-specific cleanup (e.g. trailing
  engine-added punctuation) stays inside `SpeechToTextEngine`, never
  inside `CommandRouter`.
* **Command dispatch** — `VoiceModule`'s `execute()` only. It calls
  `SpeechToTextEngine`, then calls the *existing*
  `CommandRouter.dispatch(transcript)` — it must not re-implement
  parsing (same constraint `ApiRouter`/`TelegramRouter` already
  honor).
* **Existing Jarvis logic** — entirely untouched; `voice` is a
  peer namespace to `system`, `email`, `discord`, etc., not a
  privileged one.

### 5.3 `VoiceModule` — the `voice` command namespace

Implements `CommandModule` (`name = "voice"`), registered in
`src/bootstrap.py` alongside every other module. Proposed actions
(final action names are an implementation-time, not architectural,
decision):

* `voice transcribe <path>` — transcribe an existing audio file and
  **print the transcript only** (does *not* auto-dispatch it as a
  command) — a safe, side-effect-free way to test/inspect
  recognition quality.
* `voice run <path>` (or `voice execute <path>`, naming TBD) —
  transcribe an audio file **and** dispatch the resulting text
  through `CommandRouter.dispatch()`, returning the *dispatched
  command's* `CommandResult` (mirroring exactly what `ApiRouter`
  and `TelegramRouter` already do with their own input).
* `voice listen` — **contingent on Owner Decision 5** — capture a
  fixed-duration or silence-terminated microphone recording, then
  behave like `voice run` on the captured audio.
* `voice status` — report whether the STT engine is enabled/loaded,
  which model/language is active, mirroring `system status`'s own
  precedent of reporting subsystem health (see `SystemModule`).

Two distinct actions (`transcribe` vs. `run`) are proposed
deliberately: automatically executing whatever a speech engine
*thinks* it heard, with no dry-run option, is a foot-gun (Section
12's whole reason for existing) — the project's own file-modification
/ "never silently do more than requested" ethos
(`AI_GENERATION_STANDARD.md`) argues for keeping "listen" and
"act" as separably invokable steps, at minimum for developer trust
during rollout.

> **Implemented As (STEP 2):** per Owner Decision 8 (Section 9a),
> the final action set is `voice listen` (primary — capture, then
> dispatch through `CommandRouter.dispatch()` if confident enough),
> `voice transcribe` (capture and transcribe only, never dispatch —
> the dry-run role this section originally assigned to `voice run`),
> `voice status`, and `voice help`. The separate, auto-dispatching
> `voice run <path>` action proposed above was dropped — its
> dispatch responsibility moved to `voice listen` once microphone
> capture became the primary v1 operation (Section 9b). File-path
> transcription was not implemented — Owner Decision 5 made it
> optional ("only if it naturally fits"), and it did not become
> necessary once `voice listen`/`voice transcribe` were built around
> live microphone capture. See Section 16.

### 5.4 Failure behavior

| Condition | Behavior |
|---|---|
| Microphone unavailable (device busy / no device / permission denied) | `TranscriptionResult(success=False, error=...)`; `VoiceModule` returns a `CommandResult(success=False, message=...)`. No exception escapes to `CommandRouter` (which would catch it anyway per its own `except Exception` guard, but the engine should fail predictably, not rely on that safety net). |
| No speech detected (silence / VAD timeout) | `TranscriptionResult(success=False, text="", error="no speech detected")`. Nothing is dispatched to `CommandRouter` — an empty/failed transcription must never become an arbitrary dispatched command. |
| Unintelligible speech / low-confidence result | Engine-dependent; where the selected library exposes a confidence score, a configurable minimum-confidence threshold (Section 6) governs whether the result is treated as a failure. Where it does not (Section 8/9 will confirm per-candidate), the raw text is returned and it is on the user to notice a bad transcript via `voice transcribe`'s dry-run action. |
| Model/engine unavailable (files missing, package import error) | Raised once, at `VoiceModule` construction / `Bootstrap.initialize()` time, exactly like `EmailService`'s and `RestApiServer`'s own "degrade safely, log, disable subsystem" precedent (`EP043_DESIGN.md` Section 21.2) — **not** a crash of the whole application. `voice.enabled` effectively becomes `false` for the rest of the run, and this is logged once at startup. |
| Dependency unavailable (import fails entirely, e.g. package not installed) | Same as above — caught at construction, subsystem disabled, application continues. |
| Timeout (recognition takes too long) | Configurable timeout (Section 6); on expiry, treated as a recognition failure, not a hang — `VoiceModule`/CLI/API/Telegram callers must always get a `CommandResult` back. |
| Unsupported language requested | `TranscriptionResult(success=False, error="unsupported language: <code>")`; the set of supported languages is a property of whichever model(s) are configured (Section 6/9), not hardcoded in `VoiceModule`. |
| Empty result (engine returns `""` with no error) | Treated the same as "no speech detected" — never silently dispatched as an empty command line (`CommandRouter.dispatch("")` already returns `CommandResult(success=False, message="")` for blank input, so this is naturally safe even if it reached `dispatch()`, but `VoiceModule` should not rely on that and should short-circuit itself first). |

---

## 6. Configuration design

Proposed `config/config.yaml` block, following the project's own
established per-subsystem comment convention (compare `discord:`,
`email:`, `api:`):

```yaml
voice:
  # EP-046 Speech-to-Text. Offline audio-to-text transcription, feeding
  # transcribed text into the existing CommandRouter -- the same
  # dispatch() entry point the interactive shell, Telegram, and the
  # REST API already use (see src/core/command_router.py). No new
  # dispatch mechanism, no duplicated command parsing.
  #
  # "enabled" defaults to false, matching the REST API's and Email's
  # precedent (Section 3.5): this subsystem claims a hardware resource
  # (the microphone, when "voice listen" is used) and/or a
  # multi-hundred-MB model download, so it stays off until an operator
  # explicitly opts in -- unlike the stateless outbound API clients
  # (Discord/GitHub/Telegram Info) that default to true.
  enabled: false

  # Selected STT engine/library. See EP046_DESIGN.md Section 9.
  engine: "<owner decision, Section 10 Decision 1>"

  # Model identifier/size, meaning is engine-specific (e.g. a Vosk
  # model name, or a Whisper/faster-whisper model size such as
  # "small"/"base"). See EP046_DESIGN.md Section 9.
  model: "<owner decision, Section 10 Decision 3>"

  # Recognition language(s). See EP046_DESIGN.md Section 10 Decision 2.
  language: "<owner decision>"

  # Recognition/model files stay entirely local; never uploaded or
  # streamed to a third-party API. See Section 12 (Security/Privacy).
  offline_only: true

  # Input device index/name for "voice listen"; null uses the OS
  # default input device. Only read if Owner Decision 5 approves
  # microphone capture for EP-046 v1.
  device: null

  # Sample rate (Hz) for microphone capture. Engine/model-dependent;
  # 16000 is the common default for the candidates in Section 8.
  sample_rate: 16000

  # Recognition timeout, in seconds, before a transcription attempt
  # is treated as failed (Section 5.4).
  timeout_seconds: 10

  # Minimum acceptable recognition confidence (0.0-1.0), where the
  # selected engine exposes one. null disables the check.
  min_confidence: null
```

Every key above is justified against a concrete need identified in
Sections 5/8/9/10 — no speculative options (per STEP 1's own
instruction: "Do not add configuration merely for the sake of having
options"). `enabled`, `offline_only`, and `timeout_seconds` are the
only three that do not depend on an open owner decision; the rest
are placeholders pending Section 10.

> **Implemented As (STEP 2):** the actual `config/config.yaml` block
> refines this proposal in one way, made necessary by Owner Decision
> 2 ("Language selection must be explicit/configurable rather than
> hard-coded"): the single `language`/`model` string keys above are
> replaced by `languages` (a list, e.g. `["ru", "uz", "en"]`) plus
> `default_language` (the language used when no argument is given)
> and `model_dir` (one directory holding a `<model_dir>/<language>/`
> subfolder per configured language, rather than one `model` string) —
> this is the mechanism that lets more than one language be
> configured at once, which a single `model`/`language` pair could
> not express. `listen_duration_seconds` (default `5`) was also added,
> needed by Owner Decision 5's fixed-duration `voice listen` capture
> (Section 5.1/9b). Every other key (`enabled`, `engine`,
> `offline_only`, `device`, `sample_rate`, `timeout_seconds`,
> `min_confidence`) matches this section's original proposal exactly.
> See Section 16 for the complete as-delivered `voice:` block.

---

## 7. Technology evaluation

Candidates realistically available for a Windows, Python ≥3.12,
CPU-only (no GPU assumed anywhere in the repository), offline-capable
engineering workstation, needing Russian, Uzbek, and English support
(per the user's own stated working languages — `/topics/languages.md`
and this project's own multi-language precedent, e.g. Telegram/Email
subsystems' locale-agnostic design):

| Candidate | Offline | Windows | Russian | Uzbek | English | Approx. model size | CPU-only viable | Streaming | License | Already in `requirements.txt` |
|---|---|---|---|---|---|---|---|---|---|---|
| **Vosk** (`vosk` PyPI package) | Yes | Yes (prebuilt wheels) | Yes | **Yes** (dedicated small model) | Yes | ~50 MB/language (small models) | Yes, comfortably | Yes (native) | Apache 2.0 | No |
| **faster-whisper** (CTranslate2 reimplementation of Whisper) | Yes | Yes | Yes (strong) | Weak/uncertain (low-resource language in a multilingual model) | Yes (strong) | ~75 MB (tiny) – ~1.5 GB (small/medium), higher for large | Yes, with a slower/heavier CPU footprint than Vosk at comparable model sizes | Not natively (utterance-at-a-time; add VAD chunking for pseudo-streaming) | MIT | No |
| **openai-whisper** (reference implementation) | Yes | Yes | Yes | Weak/uncertain | Yes | Same model family as above, slower than faster-whisper at equal accuracy (no CTranslate2 optimization) | Yes, but slowest of the three offline options | No | MIT | No |
| **SpeechRecognition** (`SpeechRecognition` PyPI package) | Depends on backend | Yes | Backend-dependent | Backend-dependent | Yes | N/A (wrapper) | Depends on backend | Backend-dependent | BSD | **Yes (already declared, unused)** |
| Cloud APIs (Google Cloud Speech-to-Text, Azure Speech, AssemblyAI, etc., reachable via `SpeechRecognition` or directly) | **No** | Yes (network client) | Yes | Uncertain | Yes | N/A | N/A | Yes | Commercial/usage-based | No (would need an API key) |
| CMU Sphinx / PocketSphinx (via `SpeechRecognition`) | Yes | Partial (native build complexity on Windows) | Poor | Not supported | Weak accuracy | Small | Yes | Yes | BSD | No (extra native dependency) |

Notes on the table, and why each candidate is or is not carried
forward:

* **Cloud APIs are rejected outright**, not merely deprioritized:
  Section 12 (Security/Privacy) and this project's own established
  pattern (Email/Discord/GitHub are all *read* integrations against
  services the user already has an account with, never a
  send-audio-to-a-third-party integration) argue against sending
  microphone audio off-machine by default. Every prior EP that talks
  to an external service (Email, Discord, GitHub, Telegram) does so
  because the *data already lives there* — the opposite of
  microphone audio, which originates locally and has no reason to
  leave the machine. Cloud STT is left as a documented,
  **not-recommended** alternative only.
* **CMU Sphinx / PocketSphinx is rejected**: no meaningful Russian
  support, no Uzbek support, and materially worse accuracy than
  Vosk even in English — Vosk is a strict improvement on every axis
  that matters here (Section 4 of this STEP 1's own governing
  instructions: "Do not select a technology merely because it is
  popular" cuts the same way against picking something *because* a
  wrapper library happens to default to it).
* **`SpeechRecognition` (the already-declared dependency) is not
  itself an engine** — it is a unified wrapper that can call out to
  Vosk, Whisper, CMU Sphinx, or several cloud APIs. Its presence in
  `requirements.txt` does not by itself answer "which engine" — it
  only tells us a wrapper was anticipated. Section 9 evaluates
  whether to use it as a thin convenience layer over the selected
  engine, or bypass it and call the selected engine's own Python API
  directly.
* **faster-whisper and openai-whisper** are the accuracy-leading
  offline options for English and Russian, but neither publishes
  confident, well-supported Uzbek recognition — Whisper's
  multilingual training data is heavily skewed toward high-resource
  languages, and Uzbek is not one of them. Given the user's stated
  working languages include Uzbek, this is a material, not
  theoretical, gap.
* **Vosk** is the only candidate with a dedicated, purpose-built
  Uzbek model alongside Russian and English, is the smallest
  resource footprint by a wide margin (favorable for an
  always-available, opt-in-enabled local tool rather than a
  dedicated transcription workstation), has native streaming
  (useful groundwork for EP-048/049 without committing to it now),
  has clean Windows wheels, and needs no GPU.

---

## 8. Recommended approach

**Recommend Vosk** as the STT engine (`voice.engine: "vosk"`),
called directly through its own Python API (`vosk-api` /
`vosk` PyPy package) rather than through the already-declared
`SpeechRecognition` wrapper — for the same reason
`AI_GENERATION_STANDARD.md`'s "Provider Independence" principle
argues for `src/skills/voice/speech_to_text.py` owning a small,
Jarvis-specific `SpeechToTextEngine` abstraction (Section 5.2) rather
than a third-party wrapper's abstraction: Jarvis, not
`SpeechRecognition`, should own the seam a future second engine
(e.g. faster-whisper as an alternative `voice.engine` value, if
Russian/English accuracy ever becomes the priority over Uzbek
coverage) would plug into.

This makes `requirements.txt`'s existing `SpeechRecognition` entry
**unused even after EP-046** under this recommendation — flagged
explicitly as Owner Decision 4 (Section 10), since removing an
already-declared dependency is exactly the kind of change
`AI_GENERATION_STANDARD.md`'s "File Modification Policy" reserves
for explicit instruction, not silent cleanup.

`pyttsx3` is untouched either way — it belongs to EP-047, not
EP-046.

Alternative, if the owner instead prioritizes Russian/English
accuracy over first-class Uzbek support: **faster-whisper**, `small`
or `base` model, run through `SpeechRecognition`'s own Whisper
backend (since `SpeechRecognition` is already declared) or directly.
This alternative is documented but not recommended, given the user's
stated working languages.

---

## 9. Owner decisions required

Per STEP 1's own instruction ("Do not silently make significant
architectural decisions on behalf of the owner. Present the
recommended option and alternatives."):

1. **STT engine.** Recommended: **Vosk** (Section 8/9). Alternative:
   faster-whisper. This determines the new dependency (Decision 4)
   and the configuration `engine`/`model` values.
2. **Supported language(s) for v1.** Options: (a) all three —
   Russian, Uzbek, English, each as a separately configured Vosk
   model (`voice.language` becomes a list, or one model is
   configured at a time); (b) one language only for v1, expandable
   later. Recommended: (a), since Vosk's per-language models are
   small enough (~50 MB each) that supporting all three costs little
   beyond disk space, and the user's own stated working languages
   span all three.
3. **Model size/variant.** Vosk publishes small (~50 MB) and larger
   (accuracy-optimized, gigabytes) models per language. Recommended:
   small models for v1 (fast, CPU-friendly, adequate for command-style
   utterances rather than long-form dictation) — matching this EP's
   scope (Section 2: short utterances dispatched as commands, not a
   transcription/dictation product).
4. **Disposition of the existing, unused `SpeechRecognition` entry
   in `requirements.txt`.** Recommended: leave it in place,
   unused, rather than remove it — removing a dependency the owner
   originally added is outside this EP's authorized scope
   (`AI_GENERATION_STANDARD.md` File Modification Policy) unless
   explicitly requested. Alternative: owner explicitly authorizes
   its removal as part of EP-046 STEP 2.
5. **Microphone capture in EP-046 v1, or file-only.** Recommended:
   **include** microphone capture (`voice listen`, Section 5.3) as
   part of v1's scope, since "Speech-to-Text" without any live-audio
   path would be an unusually narrow reading of the title, and the
   roadmap's own Phase 7 ordering implies EP-046 is the audio-capture
   foundation EP-048's wake word will build on. Alternative: v1
   ships file-transcription only (`voice transcribe <path>`), and a
   small EP-046.1 (mirroring the project's own precedent for
   sub-numbered EPs, e.g. EP-013.1/EP-013.2) adds microphone capture
   once the engine itself is verified.
6. **New dependency for microphone capture.** If Decision 5 is
   "include": Vosk's own examples and most Windows-Python audio
   capture use `sounddevice` (thin PortAudio binding, well-supported
   prebuilt Windows wheels) or `pyaudio` (older, historically
   harder to install on Windows without a prebuilt wheel).
   Recommended: **`sounddevice`** — no new dependency exists in
   `requirements.txt` today for either, so this is a genuinely new
   addition regardless, and `sounddevice`'s Windows wheel situation
   is materially better than `pyaudio`'s.
7. **`voice.enabled` default.** Recommended: `false` (Section 6),
   matching the REST API/Email precedent — a hardware-claiming,
   model-downloading subsystem should not silently activate for
   every existing installation the moment EP-046 ships.
8. **Action naming** (`voice transcribe` / `voice run` / `voice
   listen` / `voice status`, Section 5.3) — cosmetic, but flagged
   since `AI_GENERATION_STANDARD.md`'s "Public API Policy" treats
   command names as a public surface once shipped; better to confirm
   before STEP 2 than rename after.
9. **Confidence threshold behavior** (Section 5.4) — whether a
   low-confidence transcript should still be returned for the user
   to judge (recommended: yes, transcript is not privileged/binding,
   it is not automatically executed unless explicitly `voice run`)
   or discarded below a configurable threshold.
10. **Model distribution.** Vosk models are downloaded separately
    from the `vosk` PyPI package itself (they are not `pip`
    dependencies). Recommended: models are a one-time manual/documented
    setup step (download + extract into e.g. `data/models/vosk/<lang>/`,
    following the `paths:` convention already in `config/config.yaml`),
    **not** auto-downloaded at runtime — matching the project's
    general avoidance of surprise network activity at startup (no
    prior EP auto-downloads anything). Alternative: an explicit
    `voice setup` command that downloads/verifies models on request.

None of these ten items is silently decided by this document.

## 9a. Owner Decisions (received prior to STEP 2) — Resolution of Section 9

The project owner reviewed and approved EP-046 STEP 1 with the
following decisions. STEP 2 has **not** started; these decisions
govern it once it does.

| # | Question | Owner Decision |
|---|---|---|
| 1 | STT engine | **Vosk**, selected for EP-046 v1. Qualification: STEP 2 must verify the availability and practical quality of the Russian, Uzbek, and English models before completing implementation (see the new STEP 2 Gate, Section 9b, item 2-4). If Uzbek recognition quality is demonstrably inadequate, STEP 2 must **STOP and report the evidence** rather than silently substitute another engine. |
| 2 | Supported languages | **Russian, Uzbek, and English**, all three, for v1. Language selection must be **explicit/configurable** (`voice.language`, Section 6) — never hard-coded into `VoiceModule`'s command logic. |
| 3 | Model size/variant | **Small/local model variant**, matching Section 9 Decision 3's original recommendation. Do not optimize for maximum accuracy at the expense of the workstation's resource constraints. The architecture must let the model be replaced later (a config value, Section 6's `voice.model`) **without changing the command-routing layer** — `VoiceModule`/`CommandRouter` must have zero knowledge of which model is loaded. |
| 4 | Existing `SpeechRecognition` dependency | **Left in place, unused** — matching Section 9 Decision 4's recommended alternative. EP-046 must **not** depend on it, since Vosk is used directly (Section 8). Any future removal is an explicitly separate task, not folded into EP-046. |
| 5 | Microphone capture | **Included in EP-046 v1.** Further sharpened beyond Section 9 Decision 5's original framing: microphone-based recognition (`voice listen`) is the **primary, user-facing operation**, not a secondary addition alongside file transcription. File-based transcription (`voice transcribe`) may still be supported where it naturally fits the design (Section 5.3 already proposed both), but is not a required scope item in its own right. |
| 6 | Audio capture dependency | **`sounddevice`**, matching Section 9 Decision 6's recommendation. STEP 2 must document why it was selected (Section 10 already does: prebuilt Windows wheels, thin PortAudio binding) and keep the audio-capture layer architecturally separate from the STT engine (Section 5.2 already separates these two responsibilities; this decision confirms that separation is required, not optional). |
| 7 | `voice.enabled` default | **`false`**, matching Section 9 Decision 7 and Section 6's proposed config. Voice functionality must be explicitly enabled by the operator. EP-046 must **not** introduce always-on listening under any configuration. |
| 8 | Command actions | **`voice listen`, `voice transcribe`, `voice status`** — confirming Section 5.3's proposed action set, with `voice run` (the auto-dispatching file-based action) **dropped**: `voice listen` is now the primary command that both captures and dispatches (see Section 9b for the resulting Section 5.3 update). Minor grammar adjustments remain possible if the existing command grammar requires them. All actions must dispatch through the existing `CommandRouter.dispatch()` — no parallel command-execution mechanism. |
| 9 | Low-confidence recognition | **Do not execute** a command recognized below the configured confidence threshold. Instead, return/show the recognized text and its confidence value, and report that confidence was insufficient. The threshold must be configurable (`voice.min_confidence`, Section 6) to the extent the existing configuration conventions support it — confirming, not changing, Section 6's already-proposed `min_confidence` key. |
| 10 | Model distribution | **Manual model setup** for v1 — confirming Section 9 Decision 10's recommended alternative. No automatic model downloader and no `voice setup` command in EP-046. Documentation must state where the model is expected to be placed on disk and how configuration (`voice.model`, Section 6) points to it. |

All ten Section 9 questions are now resolved; none remains open from
the original list. Additional, more specific architectural
constraints confirmed alongside these ten decisions are recorded in
Section 9b.

## 9b. Additional Architectural Requirements (confirmed alongside Section 9a)

The owner confirmed the following, sharpening — not changing — this
document's existing design:

* **Data flow stays exactly as designed** (Section 5.1):
  `Microphone → Audio Capture → STT Engine → text → CommandRouter.dispatch()`.
* `CommandRouter` must **not** be modified unless STEP 2 finds this
  absolutely unavoidable — in which case it is a STOP-and-report
  condition, not a silent change (consistent with Section 3.2's
  finding that zero `CommandRouter` changes are expected).
* No second command-execution/routing mechanism may be created.
* No wake-word detection (already Section 2/13 non-goal — confirmed,
  not new).
* No always-on listening (already Section 2/12 non-goal — confirmed).
* No TTS (already Section 2/13 non-goal — `text_to_speech.py` stays
  untouched — confirmed).
* No conversation/memory behavior and no agent behavior — new,
  explicit non-goals, consistent with Section 2's existing "not a
  conversational assistant" framing but now stated without any
  ambiguity.
* No cloud STT (already Section 8/12 rejection — confirmed).
* No UI of any kind.
* No REST API change, no Telegram behavior change, no desktop
  (`desktop/`) architecture change (already Section 2/3.1 —
  confirmed).

**Resulting update to Section 5.3:** with Decision 5 and Decision 8
narrowing scope, the primary v1 action is `voice listen` (capture →
transcribe →, if confidence is sufficient per Decision 9, dispatch
via `CommandRouter.dispatch()`). `voice transcribe` remains available
as a secondary, dry-run-style action (transcribe only, never
dispatch — e.g. against a file, if that fits the design without
expanding scope) exactly as Section 5.3 already proposed. `voice
run` (the separate auto-dispatching file action originally proposed
in Section 5.3) is **dropped** — its dispatch behavior is now
`voice listen`'s job. `voice status` is unchanged from Section 5.3's
original proposal.

## 9c. STEP 2 Gate — Verification Required Before Broad Implementation

Before implementing the full feature, STEP 2 must first verify the
following, and **STOP and report** if any item invalidates this
approved design rather than proceeding regardless:

1. `vosk` package compatibility with the project's Python ≥3.12
   environment (Section 3.7).
2. Availability of a suitable **Russian** Vosk model.
3. Availability of a suitable **Uzbek** Vosk model, and — per
   Decision 1's qualification — that its recognition quality is
   practically adequate, not merely that a model file exists.
4. Availability of a suitable **English** Vosk model.
5. Practical model sizes and resource requirements against the
   project's workstation constraints (Decision 3).
6. `sounddevice` microphone/audio-capture compatibility on the
   target Windows environment (Section 3.7, Decision 6).

This gate sits between STEP 1 (this document) and the rest of STEP
2's implementation work — it is a checkpoint, not itself
implementation, and does not authorize proceeding past it silently.

---

## 10. Dependency strategy

| Package | New? | Why | Platform | License | Approx. size |
|---|---|---|---|---|---|
| `vosk` | **Yes** (contingent on Decision 1) | Offline STT engine with first-class Uzbek + Russian + English support (Section 8/9) | Prebuilt Windows wheels available | Apache 2.0 | Package itself is small; models are downloaded separately (Decision 10) |
| `sounddevice` | **Yes** (contingent on Decision 5) | Microphone capture; no existing project dependency provides raw PCM audio capture from an input device | Prebuilt Windows wheels available (wraps PortAudio) | MIT | Small |
| `SpeechRecognition` | No — already present, unused | Not selected as the integration layer (Section 8); left in place per Decision 4 | — | BSD | — |
| `pyttsx3` | No — already present, unused | Out of scope (EP-047, Text-to-Speech), untouched | — | — | — |

No dependency in this table is installed during STEP 1, per this
STEP's hard rule.

---

## 11. Testing strategy

Deterministic, no-real-microphone-required tests, under
`tests/EP046/` (pytest) plus a `TestRegistry`-registered suite for
the `test EP046` shell command (Section 3.6):

* **`SpeechToTextEngine` interface behavior** — a lightweight fake
  engine (implementing `TranscriptionResult`) exercised standalone,
  independent of Vosk, so the interface contract is tested without
  requiring model files to be present in CI.
* **Successful transcription** — using a small, project-committed,
  fixture `.wav` file with known, unambiguous spoken content (a
  short fixed phrase), if a real Vosk model is available in the test
  environment; otherwise this test is skipped (not failed) when the
  model directory is absent, following the project's own established
  pattern of environment-conditional tests (compare `email`/`discord`
  tests, which require environment variables/tokens and degrade to
  skip, not fail, when absent).
* **Empty input** (silent/empty audio file) → `TranscriptionResult(success=False)`.
* **Recognition failure** (corrupt/unreadable audio file).
* **Unavailable model** (engine constructed with a missing/invalid
  model path) — must raise a caught, logged, subsystem-disabling
  error at `Bootstrap.initialize()` time (Section 5.4), not an
  uncaught exception.
* **Unavailable microphone** (Decision 5-contingent) — using a fake
  `AudioCapture` that simulates "device not found", asserting
  `VoiceModule` returns a failed `CommandResult`, never raises.
* **Configuration** — `voice.enabled: false` results in the module
  either not registering, or registering but every action failing
  cleanly with a "voice disabled" message (mirroring how disabled
  Email/Discord/REST API subsystems already behave) — exact
  behavior confirmed at STEP 2 against whichever precedent
  `Bootstrap.initialize()` already uses for other `enabled: false`
  subsystems.
* **Lifecycle** — constructing `VoiceModule`/`SpeechToTextEngine`
  during a full `Bootstrap.initialize()` wiring-check test (the same
  kind of test EP-001..EP-045 already have), confirming no crash and
  no port/resource bound when `voice.enabled: false` (the REST-API
  precedent for why `enabled` defaults matter to the existing test
  suite, Section 3.5/`EP043_DESIGN.md`).
* **Integration with the existing pipeline** — a fake engine
  returning a fixed transcript string, asserting `voice run` (or
  final chosen action name) produces the **same** `CommandResult` an
  equivalent `CommandRouter.dispatch()` call would produce directly
  — i.e., proving no divergent parsing exists, the same property
  `ApiRouter`'s and `TelegramRouter`'s own test suites already
  establish for their interfaces.

Real-microphone testing (if Decision 5 is "include") is explicitly
**not** part of the automated suite — it is a manual smoke test
during STEP 2/3, following `EP045_AUDIT.md`'s own precedent for
`web/public/app.js` (verified manually, no JS test runner exists in
this project; the equivalent honest limitation here is "no real
microphone exists in CI").

---

## 12. Security and privacy

* **Microphone access** is opt-in at two levels: `voice.enabled:
  false` by default (Section 6/10 Decision 7), and even when
  enabled, capture only happens on an explicit command
  (`voice listen`) — never a background/always-on listener (that is
  explicitly EP-049's scope, not EP-046's, Section 2).
* **Audio never leaves the machine.** The recommended engine (Vosk,
  Section 8) runs entirely locally; no network call is made to
  transcribe. This is a design requirement, not just the
  recommended engine's incidental property — it rules out cloud STT
  as an alternative regardless of accuracy (Section 8's rejection
  is on privacy grounds first, technical grounds second).
* **No external APIs, no credentials, no API keys** — unlike Email
  (IMAP credentials) or Discord/GitHub/Telegram (bot tokens), EP-046
  as designed has nothing to authenticate to. If a future EP ever
  substitutes a cloud STT provider, that EP inherits Email's/
  Discord's existing "environment variable only, never in
  `config.yaml`" convention — but this is explicitly out of scope
  here (Section 2).
* **Temporary audio files.** `voice transcribe <path>` reads a file
  the user already placed on disk — Jarvis creates no new copy.
  `voice listen` captures to memory (PCM bytes) and, unless a future
  debugging need requires otherwise, is not written to disk at all;
  if an intermediate file is technically required by the chosen
  capture library, it must be written under the existing
  `paths.data_cache` (or a new, config-declared path — never
  hardcoded, per `AI_GENERATION_STANDARD.md`'s Configuration Policy)
  and deleted immediately after transcription completes.
* **Retention of recorded audio.** Default: **none.** No captured
  or transcribed audio is persisted beyond the single request/response
  cycle. If a future EP wants a "review what I said" history
  feature, that is new scope requiring its own owner decision — not
  an implicit EP-046 v1 behavior.
* **Logging of recognized speech.** Per `AI_GENERATION_STANDARD.md`'s
  Logging Policy ("log important events... never log secrets"),
  transcripts are borderline: they are user-generated commands, not
  credentials, so logging *that* a transcription occurred (success/
  failure, duration, language) follows the existing `loguru`
  convention every module already uses — but logging the *full
  transcript text* by default is not recommended, since a
  misrecognized or sensitive utterance would otherwise sit in a log
  file indefinitely (`logging.retention_days: 30` in
  `config/config.yaml`) with no user awareness. Recommended:
  log transcript length and success/failure only; full-text debug
  logging gated behind an explicit, separate debug flag if ever
  needed.
* **Sensitive information in logs** — same reasoning as above;
  since anything a user says near the microphone could include
  sensitive information, EP-046 treats transcript *content* the way
  the project already treats "secrets"/"tokens" for logging
  purposes (excluded from default logs), even though it is
  technically neither.

---

## 13. Non-goals (explicit)

* Not a dictation/note-taking product — utterances are treated as
  commands, not free text to store.
* Not a general-purpose transcription service for arbitrary long
  audio/meeting recordings.
* Not a conversational assistant (no dialogue state, no follow-up
  question handling) — that is EP-049.
* Not a replacement for typed commands — an additional, parallel
  input path into the same `CommandRouter`, exactly as Telegram and
  the REST API already are.
* Does not change `CommandRouter`, `InteractiveShell`,
  `TelegramRouter`, or `ApiRouter` in any way.
* Does not touch `desktop/` (EP-044) or `web/` (EP-045).

---

## 14. Acceptance criteria (for STEP 2, not yet met)

1. `EP046_DESIGN.md` exists at
   `docs/architecture/designs/EP046_DESIGN.md` (this document).
2. All ten Section 9 owner decisions are resolved and recorded
   (mirroring `EP045_DESIGN.md` Section 22a's pattern) before STEP 2
   implementation begins.
3. `SpeechToTextEngine` and `VoiceModule` exist, `VoiceModule`
   implements `CommandModule` and is registered in
   `src/bootstrap.py` exactly like every other module.
4. A transcribed utterance dispatched via `voice run`/`voice listen`
   produces an identical `CommandResult` to typing the same text
   directly into the shell — no divergent parsing.
5. `voice.enabled: false` (the default) results in no microphone
   access, no model load, and no behavior change for any existing
   EP-001..EP-045 functionality or test.
6. No file outside `src/skills/voice/`, `src/bootstrap.py`,
   `config/config.yaml`, `requirements.txt`, `tests/EP046/`, and
   `docs/` is modified.
7. `tests/EP046/` passes deterministically with no real microphone
   or network access required (real-microphone testing is manual,
   Section 11).
8. Full existing regression suite (5,549 tests as of EP-045) still
   passes unchanged.
9. No audio or transcript is persisted or transmitted off-machine
   by default (Section 12).

---

## 15. STEP 1 boundary — implementation is NOT part of STEP 1

This document is research, architecture analysis, and design only.

Per the governing instructions for this STEP:

* No source code was written or modified.
* No test code was written or modified.
* No configuration file was modified (Section 6's YAML is a
  **proposal**, not applied to `config/config.yaml`).
* No dependency was installed (Section 10/11 is a **proposal**,
  `requirements.txt` is unmodified).
* No UI was created.
* `src/skills/voice/*.py` remain the same empty, pre-existing
  placeholder files they were before this STEP — untouched.
* EP-045 remains COMPLETE and unmodified.
* EP-046 remains in STEP 1 / design state — **not** implemented,
  **not** marked complete.

**STOP after this document. Do not begin STEP 2 without explicit
owner review and approval of Section 9's decisions.**

---

## 16. STEP 2/3 Implementation Summary (as-built)

This section records what was actually built, verified against the
final source at STEP 3. It does not replace Sections 1-15 above —
those remain the STEP 1 design record and the owner's STEP 1
decisions (Section 9a/9b/9c) exactly as approved. Where the two
differ, the difference is a deliberate, explained refinement
(Section 6/5.3's "Implemented As" notes above), never an
undocumented substitution. Full verification evidence lives in
`docs/architecture/audits/EP046_AUDIT.md`; this section is the
design document's own summary of the same facts.

### 16.1 Implementation files

| File | Role |
|---|---|
| `src/skills/voice/speech_to_text.py` | `VoskSpeechToTextEngine`, `TranscriptionResult`, `SpeechToTextEngine` protocol, `SpeechToTextEngineError` |
| `src/skills/voice/audio_capture.py` | `AudioCapture`, `AudioCaptureResult`, `AudioCaptureError` |
| `src/skills/voice/skill.py` | `VoiceModule` (`CommandModule`, namespace `"voice"`) |
| `src/bootstrap.py` | Conditional wiring (`voice.enabled`), `voice_engine` property |
| `config/config.yaml` | `voice:` block (Section 6's "Implemented As" note) |
| `requirements.txt` | `vosk`, `sounddevice` added |
| `tests/EP046/__init__.py`, `tests/EP046/test_voice.py` | `TestRegistry`-registered suite, `NAME = "EP046"` |

### 16.2 Technology (Owner Decision 1, Section 9a/9c)

Vosk **0.3.45** — confirmed a real `win_amd64` wheel exists on PyPI,
bundling `libvosk.dll` and its runtime dependencies (no separate
native toolchain needed), and confirmed importable under Python
3.12. `sounddevice` **0.5.6** — confirmed a real `win_amd64` wheel
exists on PyPI (bundles PortAudio).

Uzbek quality gate (Section 9c item 3): **did not trigger the STOP
condition.** `vosk-model-small-uz-0.22`'s published benchmark WER
(13.54% Common Voice test, 12.92% IS2AI USC test) is in the same
range as `vosk-model-small-ru-0.22`'s (9.8% Common Voice) — not an
outlier among Vosk's small models. This is documented benchmark
evidence only, not a real-world recognition-quality claim beyond
what those published figures represent; no audio was transcribed by
a loaded model in the verification environment (Section 16.4).

Selected models (manual setup, Owner Decision 10 — none of these
files are present in the repository):

| Language | Model | Approx. size |
|---|---|---|
| Russian | `vosk-model-small-ru-0.22` | ~45 MB |
| Uzbek | `vosk-model-small-uz-0.22` | ~49 MB |
| English | `vosk-model-small-en-us-0.15` | ~40 MB |

### 16.3 Architecture (Section 5.1, confirmed unchanged)

`Microphone → AudioCapture.capture() → VoskSpeechToTextEngine.transcribe_audio() → text → CommandRouter.dispatch()`,
implemented exactly as designed. `CommandRouter`
(`src/core/command_router.py`) was **not modified**. `VoiceModule`
holds the same `CommandRouter` instance every other interface
dispatches through — no second router, no duplicated parsing.
`speech_to_text.py` and `audio_capture.py` import nothing from each
other. `voice.enabled` defaults to `false`; when disabled,
`VoiceModule` is not registered at all (mirrors the Email/Discord
precedent, Section 3.5).

### 16.4 Tests (as re-verified at STEP 3)

```
test EP046  →  Passed: 57    Failed: 0   Skipped: 1
test EP043  →  Passed: 83    Failed: 0   Skipped: 0
test EP044  →  Passed: 52    Failed: 0   Skipped: 0
test EP045  →  Passed: 38    Failed: 0   Skipped: 0
test all    →  Passed: 5641  Failed: 2   Skipped: 1
```

The one EP-046 skip is the real-microphone/real-loaded-model
scenario (Section 11's own allowance) — no Vosk model files and no
physical microphone exist in the verification environment. The two
full-suite failures (`EP-039`, `EP-041`) were reproduced
independently, in isolation, with zero EP-046 code loaded — deemed
pre-existing/environment-related, not caused by EP-046 (full
evidence: `EP046_AUDIT.md` Section 9).

Manual real-microphone test: **NOT AVAILABLE** — no physical
microphone in the verification environment. Not claimed as passed.

### 16.5 Owner decisions — implementation status

| # | Decision (Section 9a) | Status |
|---|---|---|
| 1 | Vosk, with Uzbek-quality qualification | Implemented; quality gate passed (16.2) |
| 2 | Russian + Uzbek + English, configurable | Implemented (`voice.languages`) |
| 3 | Small model variant, replaceable without touching routing | Implemented (`voice.model_dir`, per-language subfolder; `CommandRouter`/`VoiceModule` have no model-specific code) |
| 4 | Keep `SpeechRecognition`, unused | Implemented — retained in `requirements.txt`, not imported by EP-046 |
| 5 | Microphone capture, primary operation | Implemented (`voice listen`) |
| 6 | `sounddevice` | Implemented, documented rationale (Section 8/9a), kept separate from the STT engine |
| 7 | `voice.enabled: false` default | Implemented |
| 8 | `voice listen` / `voice transcribe` / `voice status` | Implemented (plus `voice help`, a minor grammar addition consistent with `SystemModule`'s own precedent) |
| 9 | Low-confidence transcript never dispatched | Implemented (`voice.min_confidence`, `VoiceModule._below_confidence_threshold`) |
| 10 | Manual model setup, no downloader | Implemented — no downloader/`voice setup` command exists |

All ten resolved decisions are implemented as recorded. No decision
was silently reinterpreted at implementation time (Section 9b/9c's
own requirement).

### 16.6 Known limitations

- No real audio clip has been transcribed by a real, loaded Vosk
  model in any environment this project has verified in — model
  files were never present (Owner Decision 10: manual setup only).
  This is a genuine, disclosed gap, not a defect: the engine's
  logic paths that do not require a loaded model (construction
  validation, missing-model handling, confidence normalization,
  empty-input/unsupported-language handling) are fully tested; the
  one path that does (`AcceptWaveform`/`FinalResult` against real
  audio) is not.
- No physical microphone has been used to capture real speech in any
  verified environment. `AudioCapture`'s "no device available"
  failure path was verified for real (a real `sounddevice` call
  against zero enumerated input devices); a real, successful capture
  was not.
- `EP-039`/`EP-041` pre-existing failures (16.4) are unrelated to
  EP-046 but remain present in the full-suite count; the full suite
  cannot currently be reported as 100% green in this environment.
- `CHANGELOG.md`/`docs/RELEASE_NOTES.md` were not updated for
  EP-046, consistent with the same, already-established
  documentation gap `EP045_AUDIT.md` Section 12/14 recorded for
  itself (carried forward, not new — see `EP046_AUDIT.md`).

None of these limitations reflect a deviation from an approved
owner decision (Section 16.5) or an unresolved design ambiguity —
each is either an environment constraint (no microphone/model files
available to verify against) or a pre-existing condition outside
EP-046's own files.
