# EP-047 — Text-to-Speech — Design Specification (STEP 1) & As-Built Record (STEP 2/3)

Status: **STEP 1 (Design & Research) — APPROVED. STEP 2
(Implementation) — COMPLETE, verified. STEP 3 (Documentation & Audit
Closure) — this update. See Section 9a for the resolved owner
decisions and Section 17 for the as-built summary. Full audit:
`docs/architecture/audits/EP047_AUDIT.md`.**

Baseline: EP-046 (Speech-to-Text) is COMPLETE — see
`docs/architecture/designs/EP046_DESIGN.md` and
`docs/architecture/audits/EP046_AUDIT.md`. EP-047 is the second
Engineering Package of `docs/architecture/JARVIS_ROADMAP.md`'s
**Phase 7 — Voice** (EP-046 Speech-to-Text ✓, EP-047 Text-to-Speech,
EP-048 Wake Word, EP-049 Voice Assistant).

This document follows the structure and quality standard established
by `EP045_DESIGN.md` and `EP046_DESIGN.md`. It intentionally mirrors
EP046_DESIGN.md's section numbering and idiom wherever the two EPs
share the same architectural situation (same package, same
predecessor pattern, same command-routing constraint).

**Sections 1-16 below are the original STEP 1 design record and do
not implement anything themselves** — no `src/`, `tests/`,
`config/`, or `requirements.txt` file was modified to *produce
STEP 1* (see Section 12's own STEP 1/STEP 2 boundary statement,
preserved unchanged below). Implementation happened afterward, in
STEP 2, following owner approval (Section 9a) — its as-built record
is Section 17.

---

## 1. Purpose

Give Jarvis the ability to turn text — a literal string the user
supplies, or (contingent on an owner decision, Section 9 D4) the
`message` of a `CommandResult` already produced by
`CommandRouter.dispatch()` — into audible speech, played through the
workstation's audio output device, entirely offline.

EP-047 delivers **text → speech → audio played**. It does **not**
deliver a wake word, a continuous listening/speaking loop, or a
back-and-forth "assistant" conversation — those are EP-048 and
EP-049, later Phase 7 packages, by the roadmap's own sequencing
(exactly the same boundary EP046_DESIGN.md Section 1 already drew for
Speech-to-Text).

---

## 2. Scope

### In scope (EP-047 v1)

* A `TextToSpeechEngine` component that converts text to speech
  offline and plays it (or saves it) via the OS's native TTS
  facility, in at least one of Jarvis's existing voice languages
  (English at minimum — see Section 7/9 for the Russian/Uzbek
  gap analysis).
* A new action added to the **existing** `voice` command namespace
  (`src/skills/voice/skill.py`) — not a new namespace — following
  EP046_DESIGN.md Section 3.3's own finding that `src/skills/voice/`
  was pre-structured for a single unified `voice` `CommandModule`
  with one file per capability (`speech_to_text.py` ↔ EP-046,
  `text_to_speech.py` ↔ EP-047, `wake_word.py` ↔ EP-048). This is
  the central architectural fact this design is built around; see
  Section 5.3 and Owner Decision D3.
* Explicit, user-initiated synthesis: a shell/API/Telegram command
  such as `voice speak <text>` (naming per Owner Decision D8,
  mirroring EP-046's own "action naming" decision).
* Configuration under the **existing** `voice:` key in
  `config/config.yaml` (a nested `tts:` block — see Section 8),
  following the same per-subsystem convention EP-046 already used.
* Deterministic, no-real-audio-output-required automated tests under
  `tests/EP047/`, following the `tests/EP0NN/` convention and the
  `_Fake*` idiom `tests/EP046/test_voice.py` already established.

### Out of scope (EP-047 v1) — deferred to later EPs or `docs/BACKLOG.md`

See Section 14 for the complete, itemized list. In summary: wake-word
detection (EP-048), always-on/conversational voice loop (EP-049),
automatically speaking every dispatched command's result by default,
a new REST API endpoint, Desktop UI (`desktop/`) or Web Dashboard
(`web/`) speaker controls, cloud/online TTS providers, streaming
synthesis, SSML, voice cloning, and any change to EP-046's STT
behavior.

---

## 3. Current architecture (repository findings)

### 3.1 The one true command entry point (unchanged from EP-046)

Every existing interface still converts its own input into a raw
command string and calls the same method — `CommandRouter.dispatch()`
— exactly as EP046_DESIGN.md Section 3.1 documented. Nothing about
this changed during EP-046's implementation. EP-047 requires **zero**
changes to `src/core/command_router.py`; this remains the integration
point EP-047 must plug into, just as it was for EP-046.

### 3.2 `src/skills/voice/` today (as EP-046 left it)

```
src/skills/voice/
    skill.py            251 lines — VoiceModule (CommandModule, namespace "voice")
    speech_to_text.py   386 lines — SpeechToTextEngine protocol + VoskSpeechToTextEngine
    audio_capture.py    161 lines — AudioCapture (sounddevice-based microphone capture)
    text_to_speech.py     0 bytes — still empty, exactly as EP046_DESIGN.md left it
    wake_word.py           0 bytes — still empty (EP-048's placeholder, not touched)
```

`VoiceModule` (`skill.py`) currently exposes four actions —
`help`/`listen`/`transcribe`/`status` — none of which produce audio
output. Its constructor is:

```python
def __init__(
    self,
    config: Config,
    command_router: CommandRouter,
    engine: SpeechToTextEngine,
    audio_capture: AudioCapture,
) -> None:
```

`engine` is currently a single, STT-specific dependency. There is
**no existing seam** for a second, TTS-specific engine — adding one
means adding a parameter (or an equivalent composition point) to
`VoiceModule.__init__`, and a new branch to its `_actions` dict. This
is a real, non-cosmetic touch to a file `EP-046` already shipped and
tested (57/0/1). It is the single most important architectural fact
in this document — see Section 5.3 and Owner Decision D3 for how
this is proposed to be handled, and why it is **additive**, not a
rewrite.

### 3.3 `text_to_speech.py` was already earmarked for this EP

EP046_DESIGN.md Section 3.3 documented this explicitly at STEP 1 and
it remains true, unchanged, today:

> "These four files are pre-existing, empty placeholders... Their
> names map 1:1 onto Phase 7's four roadmap items
> (`speech_to_text.py` ↔ EP-046, `text_to_speech.py` ↔ EP-047,
> `wake_word.py` ↔ EP-048, `skill.py` ↔ the eventual unified `voice`
> `CommandModule`)."

This directly answers this document's own instruction not to assume
a new standalone subsystem is required: the architecture already
anticipated EP-047 living inside `src/skills/voice/`, not as a new
top-level package.

### 3.4 Dependencies already staged, unused — for this exact EP

`requirements.txt` (as EP-046 left it) reads:

```
SpeechRecognition
pyttsx3

# EP-046 Speech-to-Text. Vosk (offline STT engine) + sounddevice
# (microphone capture). Neither uses SpeechRecognition/pyttsx3 above --
# those remain unused per EP046_DESIGN.md Section 9a Decision 4 (kept,
# not removed; not EP-046's dependency; any future cleanup is a
# separate task).
vosk
sounddevice
```

`pyttsx3` has never been imported anywhere in `src/`, `desktop/`, or
`tests/` (confirmed by repository-wide search). EP046_DESIGN.md
Section 8 states, verbatim: *"`pyttsx3` is untouched either way — it
belongs to EP-047, not EP-046."* This is a direct, explicit input to
Section 7 (technology evaluation) below: reusing an already-declared
dependency costs nothing new to `requirements.txt`'s dependency
surface, but — exactly as EP-046 itself insisted for Vosk — its
suitability still has to be evaluated on technical merits, not
assumed just because it is already listed.

`sounddevice` (added by EP-046, currently used only for microphone
**capture**) can also perform output **playback**
(`sounddevice.play()`), which is relevant to Owner Decision D5
(playback mechanism).

### 3.5 Configuration system — the existing `voice:` block

```yaml
voice:
  enabled: false
  engine: "vosk"
  languages: ["ru", "uz", "en"]
  default_language: "en"
  model_dir: "data/models/voice"
  offline_only: true
  device: null
  sample_rate: 16000
  listen_duration_seconds: 5
  timeout_seconds: 10
  min_confidence: 0.5
```

Every key here is STT-specific (`model_dir`, `min_confidence`,
`listen_duration_seconds` describe recognition, not synthesis).
Section 8 proposes a nested `tts:` sub-block rather than new
top-level `voice.*` keys or a `tts:` top-level block, precisely so
`voice:` remains the single configuration home for the entire Phase 7
"voice" package — mirroring the single-namespace, single-package
architecture Section 3.2/3.3 already established.

### 3.6 Testing convention (unchanged)

`tests/EP046/test_voice.py` is a single combined suite
(`NAME = "EP046"`), sidestepping the pre-existing `TestRegistry`
NAME-collision technical debt exactly as EP-043/EP-045 did before it.
It exercises `VoiceModule`, `VoskSpeechToTextEngine`, and
`AudioCapture` entirely through fakes plus narrow real-object
construction/validation checks, and reports "no real Vosk model in
this environment" as a `self.skip()`, not a silent omission and not
a failure. Section 11 proposes the identical pattern for EP-047.

### 3.7 Windows / Python environment (unchanged from EP-046)

Confirmed again: the target deployment environment is Windows,
Python ≥3.12 (`pyproject.toml`), offline-first, CPU-only, no GPU
assumed. This constrains Section 7's technology evaluation exactly as
it did EP-046's.

---

## 4. EP-047 objectives

1. Convert arbitrary text into audible speech, offline, through the
   workstation's default (or configured) audio output device.
2. Reuse, not duplicate, EP-046's established patterns: one
   `TextToSpeechEngine` interface (mirroring `SpeechToTextEngine`'s
   Protocol shape) implemented by one concrete engine class; a
   `SynthesisResult` dataclass (mirroring `TranscriptionResult`'s
   "always returns a result object, never raises for an expected
   failure" idiom); wiring through the **existing** `voice`
   `CommandModule`, not a second command-routing mechanism.
3. Keep synthesis (turning text into audio) architecturally separate
   from playback (getting audio to the speakers) wherever the chosen
   engine allows it — mirroring EP-046's own separation of
   recognition (`speech_to_text.py`) from capture (`audio_capture.py`).
4. Make the feature opt-in and fail safe: disabled by default,
   never crashes `Bootstrap` if the OS has no usable TTS voice
   installed, never blocks or interferes with EP-046 STT behavior
   when both are enabled together.
5. Explicitly do **not** re-open, redesign, or expand EP-046 STT
   behavior while doing this — Section 3.2's necessary touch to
   `skill.py` is scoped to be additive-only (see Section 5.3).

---

## 5. Proposed architecture

### 5.1 Data flow

```
text (from a command argument, e.g. "voice speak <text>")
    -> TextToSpeechEngine.synthesize(text, language)
    -> SynthesisResult (success, error, language, [audio_path])
    -> audio played through the output device
       (mechanism: Owner Decision D5)
```

This is the mirror image of EP-046's
`Microphone -> AudioCapture -> SpeechToTextEngine -> text -> CommandRouter.dispatch()`
flow (EP046_DESIGN.md Section 5.1) — text goes in, audio comes out,
instead of audio in, text out. `CommandRouter.dispatch()` is not
part of this flow at all for the base case (`voice speak <text>`
speaks its argument; it does not route anywhere) — it only becomes
relevant if Owner Decision D4 opts into "auto-speak a dispatched
command's result", in which case the flow becomes
`CommandRouter.dispatch(text) -> CommandResult.message -> TextToSpeechEngine.synthesize(...)`,
chained **after**, never instead of, normal dispatch.

### 5.2 `TextToSpeechEngine` — the TTS interface

Proposed shape (mirroring `SpeechToTextEngine`, `speech_to_text.py`):

```python
class TextToSpeechEngineError(Exception):
    """Construction-time failure only (e.g. no usable OS voice found).
    Never raised by synthesize() itself — see SynthesisResult."""


@dataclass(frozen=True)
class SynthesisResult:
    success: bool
    language: str | None
    error: str | None = None


class TextToSpeechEngine(Protocol):
    @property
    def supported_languages(self) -> list[str]: ...

    def synthesize(self, text: str, language: str | None = None) -> SynthesisResult:
        """Speak (or fail to speak) `text`. Never raises for an
        expected failure (empty text, unsupported language, no voice
        installed for that language, engine error)."""
```

Only one concrete implementation is proposed for v1:
`Pyttsx3TextToSpeechEngine` (Section 7/9 D1), living in
`src/skills/voice/text_to_speech.py` — the same empty file
EP046_DESIGN.md Section 3.3 already earmarked for it. Exactly as
`SpeechToTextEngine` left room for a second STT engine behind
`voice.engine` without touching `VoiceModule`, this Protocol leaves
room for a second TTS engine behind a `voice.tts.engine` config key
(Section 8) without touching `VoiceModule` again.

### 5.3 `VoiceModule` — additive extension, not a rewrite

This is the section STEP 1's own instructions (and this document's
Section 3.2 finding) require to be spelled out precisely, because it
is the one place EP-047 must touch a file EP-046 already shipped.

Proposed change, described as a diff against the **current**
`skill.py` (Section 3.2), not a redesign:

* `__init__` gains one additional, **optional** parameter:
  `tts_engine: TextToSpeechEngine | None = None`. `None` (the
  default) preserves EP-046's exact existing constructor behavior for
  every call site that does not pass it — i.e., unit tests and any
  future code that constructs `VoiceModule` STT-only keep working
  unmodified.
* `_actions` gains one additional entry: `"speak": self._speak`
  (name per Owner Decision D8).
* One new private method, `_speak(self, arguments)`, calls
  `self._tts_engine.synthesize(...)` — following the exact
  `if not result.success: return CommandResult(success=False, ...)`
  pattern `_listen`/`_transcribe` already use. If `tts_engine` is
  `None` (TTS disabled or unavailable), `_speak` returns a
  `CommandResult(success=False, message="Text-to-Speech is not
  enabled...")` — never an exception, never a crash.
* `HELP_TEXT` gains one additional line (`voice speak <text>`).

No existing method (`_listen`, `_transcribe`, `_status`,
`execute()`, `__init__`'s existing four parameters, the `_actions`
dict's three existing entries) changes behavior. This is the
technical basis for calling this "additive," consistent with this
document's own hard boundary against modifying/rewriting/refactoring
EP-046's implementation (Section 12) — STEP 1 asserts the *shape* of
the change is additive-only; STEP 2, if approved, must be held to
that shape, and any deviation from it is itself a decision requiring
owner sign-off (Owner Decision D3 records this explicitly).

**Alternative considered and not recommended:** a second
`CommandModule` under its own namespace (e.g. `"speak"` or `"tts"`).
This would avoid touching `skill.py` at all, but directly contradicts
EP046_DESIGN.md Section 3.3's own finding that the architecture
already anticipated one unified `voice` namespace — it would fragment
Phase 7 into two competing namespaces, duplicate `help`/action-dispatch
boilerplate, and give a future EP-049 "Voice Assistant" two
`CommandModule`s to coordinate instead of one. See Owner Decision D3.

### 5.4 Failure behavior

Mirrors EP-046 Section 5.4 exactly: construction-time failures
(`sounddevice`/`vosk` not importable, in EP-046's case; "no usable
OS TTS voice found," in EP-047's case) raise a dedicated exception
type once, at `Bootstrap` wiring time, and are handled there (Section
6) by disabling the feature and logging — never at call time.
Per-call failures (`synthesize()`) always return `SynthesisResult`,
never raise.

---

## 6. Integration points

* **`src/bootstrap.py`** — the existing
  `if bool(config.get("voice.enabled", False)):` block (currently
  constructing `VoskSpeechToTextEngine` + `AudioCapture` +
  `VoiceModule`) is the natural place to also construct a
  `Pyttsx3TextToSpeechEngine` and pass it into the same
  `VoiceModule(...)` call as the new `tts_engine=` argument — subject
  to Owner Decision D6 on whether TTS uses the same `voice.enabled`
  gate as STT, or its own independent `voice.tts.enabled` gate. A TTS
  construction failure must not prevent STT from initializing (and
  vice versa) — each engine's failure is caught and handled
  independently, exactly as `except (SpeechToTextEngineError,
  AudioCaptureError)` already does today, extended with
  `TextToSpeechEngineError` in its own independent `try`/`except`.
* **`config/config.yaml`** — new nested `voice.tts.*` keys only
  (Section 8). No existing `voice.*` key changes meaning or default.
* **`src/core/command_router.py`** — unchanged (Section 3.1).
* **`src/skills/voice/skill.py`** — one additive change (Section
  5.3).
* **`src/skills/voice/text_to_speech.py`** — currently empty; this is
  where all new synthesis logic lives.
* **`requirements.txt`** — no new dependency line if Owner Decision
  D1 selects `pyttsx3` (already present); only its explanatory
  comment changes, from "reserved for EP-047" to "used by EP-047."
* **Untouched, explicitly:** `src/core/api/` (REST API), `desktop/`,
  `web/`, `src/core/telegram/` — matching EP-046's own precedent of
  making zero changes to any of these (EP046_AUDIT.md, `BACKLOG.md`
  EP-046 entry).

> **Implemented As (STEP 2):** Owner Decision D6 (Section 9a)
> resolved "independent `voice.tts.enabled` flag, default `false`."
> As actually wired, `voice.tts.enabled` *is* independent of
> `voice.enabled` in the sense the decision cared about — a TTS
> construction failure never disables STT, and vice versa, each
> under its own `try`/`except` exactly as this section specified.
> However, `VoiceModule` itself (the `"voice"` namespace) is still
> registered only inside the existing `if voice.enabled:` block
> (Section 3.2's constructor still requires an STT `engine` and
> `audio_capture` — Section 5.3 kept that shape additive-only, not
> reopened). Consequence: `voice.tts.enabled: true` with
> `voice.enabled: false` has no effect — TTS-only operation with STT
> fully disabled is **not** supported in EP-047. This is a disclosed
> implementation-level detail, not a reversal of D6 (both engines'
> *failure modes* remain independent, exactly as decided) — see
> Section 17.5 for its "known limitation" classification and the
> code-level comment in `src/bootstrap.py` where this is also noted.

---

## 6a. Manual Verification Findings — pyttsx3 real behavior (STEP 2, informational)

Recorded here, ahead of Section 17, because it directly affects how
Section 7's technology evaluation reads once real behavior was
observed (not merely researched): in the Linux verification
environment used for STEP 2 (no SAPI5, obviously — SAPI5 is
Windows-only), `pyttsx3.init()` initially failed with a driver error
until the OS-level `eSpeak`/`eSpeak-NG` package was installed
separately (not a Python dependency, not something `pip install
pyttsx3` provides) — after which real construction, real voice
enumeration, and a real `synthesize()` call all completed without
raising. This is consistent with Section 3.7/7's own framing
(`pyttsx3` wraps *whatever* OS speech driver is present — SAPI5 on
Windows, eSpeak on Linux) and confirms `Pyttsx3TextToSpeechEngine`'s
construction-failure/success paths both behave as designed
(`TextToSpeechEngineError` wraps a missing/failed driver; a present
driver is used transparently) — but it does **not** constitute
Windows/SAPI5 verification, and is not claimed as such anywhere in
this document (Section 17.4).

---

## 7. Technology evaluation

Candidates realistically available for a Windows, Python ≥3.12,
offline-only, CPU-only target (Section 3.7):

| Candidate | Offline | Windows | License | Russian | Uzbek | Already staged | Extra runtime deps | Notes |
|---|---|---|---|---|---|---|---|---|
| **pyttsx3** | Yes | Yes (wraps SAPI5) | MPL-2.0 | Depends on installed Windows SAPI5 voice | **No known SAPI5 voice** | **Yes** (`requirements.txt`, unused, earmarked for this EP) | `pywin32`/`comtypes` (transitive, Windows) | Thin wrapper around the OS's own native speech engine; no model download; actively maintained wrapper project. |
| Piper TTS (`piper-tts`) | Yes | Yes | Upstream `rhasspy/piper` archived Oct 2025; active fork now **GPL-3.0** (was MIT) | Yes (neural voice available) | **No known voice** | No | `onnxruntime` + per-language downloaded `.onnx` voice model (tens of MB each) | Materially better voice quality than SAPI5; heavier install; a genuinely new dependency; recent license change on the maintained fork is a real evaluation input, not a footnote. |
| Coqui TTS / other deep-learning TTS stacks | Yes (with a local model) | Partial — historically dependency-fragile on Windows; project largely unmaintained upstream | Mixed (MPL-2.0 core, some voice models non-commercial) | Varies by model | No | No | Large ML stack (PyTorch or similar) | Rejected on installation-complexity and maintainability grounds alone, independent of language coverage — same category of rejection EP046_DESIGN.md Section 7 applied to heavier STT alternatives. |
| Cloud TTS (Azure/Google/AWS Polly, etc.) | **No** | Yes | Commercial | Yes | Generally no first-class Uzbek voice either | No | Network dependency, API key/credential management | Rejected on the same offline/privacy/no-network-dependency grounds EP046_DESIGN.md Section 8 already established for cloud STT — not re-litigated here. |

Key finding, and the one Section 9 must resolve explicitly:
**Uzbek text-to-speech output has no readily available offline
option** in any candidate surveyed above. This is not symmetric with
EP-046's Uzbek situation — EP-046 found a dedicated small Vosk model
for Uzbek recognition; no comparably first-class Uzbek *synthesis*
voice exists in the pyttsx3 (SAPI5), Piper, or Coqui ecosystems as
surveyed. This is flagged as Owner Decision D2, not silently worked
around (e.g. by falling back to Russian or English speech for Uzbek
text, which would be a real, user-visible product decision, not a
technical default).

Russian is available in both pyttsx3 (as a SAPI5 voice, contingent on
the target Windows installation having a Russian language pack with
speech support installed — not verifiable from this repository;
STEP 2 must verify on the actual target workstation, exactly as
EP-046's own STEP 2 gate required for Vosk model files, EP046_DESIGN.md
Section 9c) and Piper (as a downloadable neural voice model).

---

## 8. Recommended approach

**Recommend `pyttsx3`** (Owner Decision D1) for the same category of
reason EP-046 recommended Vosk over heavier alternatives: it is
already staged in `requirements.txt` specifically for this EP
(Section 3.4), requires no model download, adds no new native Windows
build/runtime complexity beyond what `pywin32`/`comtypes` already
provide as its own transitive dependencies, and matches the project's
established preference (`AI_GENERATION_STANDARD.md`, `sounddevice`'s
own precedent) for dependencies with a clean, prebuilt Windows story.

This recommendation is explicitly **not** a recommendation to accept
the Uzbek voice-output gap silently — see Owner Decision D2, which
must be resolved on its own terms, independent of the engine choice.

**Alternative, if the owner prioritizes voice *quality* over the
staged-dependency and Uzbek-parity considerations above:** Piper TTS,
accepting a new dependency, a new per-language model-management story
(mirroring EP-046's own manual Vosk model setup, Section 9 Decision
10 precedent), and the GPL-3.0 licensing question on the currently
maintained fork. Documented, not recommended, given the user's
stated preference (matching EP-046 STEP 1's own framing) for reusing
already-evaluated, already-staged project infrastructure where it is
technically adequate.

---

## 9. Owner decisions required

Per this task's own instruction ("Do not silently make significant
architectural decisions on behalf of the owner. Present the
recommended option and alternatives."):

| # | Decision | Options | Recommended | Reason | Impact |
|---|---|---|---|---|---|
| D1 | TTS engine | `pyttsx3` (SAPI5-backed) vs. Piper TTS vs. other | **`pyttsx3`** | Already staged specifically for this EP (Section 3.4/EP046_DESIGN.md Section 8); no model download; matches Windows-first, offline-first, CPU-only constraints with the least new surface area. | Determines `text_to_speech.py`'s implementation and the `voice.tts.engine` config value. |
| D2 | Uzbek voice-output gap | (a) Ship v1 with English/Russian TTS only, explicitly documented as not covering Uzbek; (b) invest in evaluating a neural engine specifically for Uzbek voice-output coverage before shipping v1; (c) fall back to speaking Uzbek text with a Russian or English voice | **(a)** | No offline engine surveyed (Section 7) has a first-class Uzbek voice; (b) is open-ended research with no guaranteed outcome; (c) silently produces mispronounced/incorrect-sounding output for a language the project explicitly supports elsewhere (STT) and would need to be an explicit, disclosed limitation if chosen, not a quiet default. | Determines `voice.tts.languages`' contents and a disclosed, documented v1 limitation either way. |
| D3 | How `speak` integrates | (a) Extend the existing `VoiceModule` with an additive `speak` action (Section 5.3); (b) create a second `CommandModule`/namespace dedicated to TTS | **(a)** | Matches the architecture EP046_DESIGN.md Section 3.3 already found pre-built for this; avoids fragmenting Phase 7 into two namespaces the eventual EP-049 Voice Assistant would otherwise have to coordinate. | Determines whether `src/skills/voice/skill.py` is touched at all during STEP 2, and how (Section 5.3 specifies the shape if (a)). |
| D4 | Auto-speak scope | (a) `voice speak <text>` only — explicit, user-supplied text; (b) also add an opt-in `voice.tts.auto_speak_results` config flag that speaks every dispatched `CommandResult.message` | **(a)** for v1 | Keeps v1's surface area minimal and matches EP-046's own "v1 is command-style, not continuous" framing (EP046_DESIGN.md Section 1); (b) is a reasonable, self-contained follow-up once (a) is verified working on real hardware. | (b), if chosen, requires `VoiceModule` (or `Bootstrap`) to observe *every* dispatch, not just `voice`-namespace ones — a materially larger integration than (a). |
| D5 | Playback mechanism | (a) `pyttsx3`'s own built-in blocking playback (`engine.say()` + `engine.runAndWait()`); (b) synthesize to a file and play it back separately via `sounddevice` (mirroring the `voice.device` output-device-selection precedent capture already has) | **(a)** | Simplest, requires no new "audio file lifecycle" (temp file creation/cleanup) and no new dependency interaction between `pyttsx3` and `sounddevice`; matches `AudioCapture.capture()`'s own blocking, synchronous `sounddevice.wait()` precedent. | (b) would be needed only if a future EP wants explicit output-device selection independent of the OS default, or non-blocking speech during a longer operation — not required for v1's scope. |
| D6 | `voice.tts.enabled` gate | (a) Reuse the existing `voice.enabled` flag (TTS and STT always on/off together); (b) an independent `voice.tts.enabled` flag | **(b)** | TTS and STT claim different hardware (output vs. input device) and can fail independently (Section 6); an operator may reasonably want spoken output without ever enabling the microphone, or vice versa — exactly as EP-046 kept the microphone (`AudioCapture`) and recognition (`SpeechToTextEngine`) architecturally, and now configurably, separate. | Determines `Bootstrap`'s wiring shape (Section 6) — two independent `try`/`except` blocks under two independent config checks, both still nested under the parent `voice:` block. |
| D7 | `requirements.txt` disposition of `pyttsx3` | (a) Leave the comment as "reserved for EP-047, unused" (no change) until STEP 2 actually wires it in; (b) update the comment now, during STEP 1, to reflect the plan | **(a)** | STEP 1 must not modify `requirements.txt` at all (Section 12) — this decision only governs STEP 2's eventual comment wording, recorded here so STEP 2 does not have to re-derive it. | Cosmetic; recorded for completeness, per Section 9's own "keep the number of decisions reasonable, but do not hide architectural choices" instruction. |
| D8 | Action naming | `voice speak <text>` (recommended) vs. `voice say <text>` vs. `voice tts <text>` | **`voice speak <text>`** | Reads naturally next to `voice listen`/`voice transcribe`; avoids `say`'s macOS-specific-command connotation; avoids `tts` as a user-facing verb where `AI_GENERATION_STANDARD.md`'s "Public API Policy" treats the name as a public surface once shipped. | Cosmetic but flagged for the same reason EP-046 Owner Decision 8 flagged its own action names — cheaper to confirm now than rename after STEP 2. |

None of these eight items is silently decided by this document.

---

## 9a. Owner Decisions (received prior to STEP 2) — Resolution of Section 9

The project owner reviewed and approved EP-047 STEP 1 with the
following decisions. STEP 2 has **not** started; these decisions
govern it once it does.

| # | Question | Owner Decision |
|---|---|---|
| D1 | TTS engine | **`pyttsx3`**, confirming Section 9's recommendation. No further engine evaluation is required before STEP 2. |
| D2 | Uzbek voice-output gap | **Uzbek TTS is out of scope for EP-047.** No workaround, translation layer, cloud TTS, or second/hidden engine may be introduced to cover it. The limitation must be **explicitly documented** (in `config/config.yaml`'s comments and this design document's as-built summary at STEP 2/3 close), not silently absent. `TextToSpeechEngine` (Section 5.2) must remain an interface, and `voice.tts.languages`/`voice.tts.engine` (Section 8) must remain configurable, specifically so that a future EP can add Uzbek support (e.g. via a different engine) **without changing `VoiceModule` or `CommandRouter`** — the same "engine is a config value, not a hard-coded assumption" property Section 9c's EP-046 precedent already required for STT. |
| D3 | Architecture | **Extend the existing `voice` `CommandModule`** (Section 5.3), confirming Section 9's recommendation. No second command namespace and no parallel routing mechanism may be created. `CommandRouter.dispatch()` remains the only dispatch path, exactly as Section 3.1/5.1 already establish. |
| D4 | Command behavior | **Implement only `voice speak <text>`** for EP-047. Automatically speaking every `CommandRouter` result (the auto-speak alternative Section 9 also described) is **not** part of EP-047 and is not to be implemented, even as an opt-in flag, in this EP. |
| D5 | Playback | **Blocking `pyttsx3` playback** (`engine.say()` + `engine.runAndWait()`), confirming Section 9's recommendation. No decoupled synthesize-to-file-then-play mechanism, and no non-blocking/asynchronous playback, in EP-047. |
| D6 | Configuration | **An independent `voice.tts.enabled` flag**, separate from `voice.enabled`, confirming Section 9's recommendation. Default is **`false`**. TTS and STT must remain independently enable-able, matching Section 6's rationale (different hardware resource, independent failure modes). |
| D7 | `requirements.txt` disposition | **Follow the recommended convention** from Section 9/16 Step 6: at STEP 2, update only the existing `pyttsx3` comment (from "reserved for EP-047, unused" to "used by EP-047"), with no version/line change and no change to `SpeechRecognition`'s own, separate, still-unresolved status. |
| D8 | Command name | **`voice speak`**, confirming Section 9's recommendation. `HELP_TEXT` and any user-facing documentation must use this exact name. |

All eight Section 9 questions are now resolved; none remains open
from the original list.

**Confirmed non-goals (restated, not new — consistent with Section
14):** no wake-word detection, no always-on/continuous voice loop, no
auto-speak-by-default, no second command namespace, no cloud TTS, no
change to `CommandRouter`, `src/core/api/`, `desktop/`, or `web/`, and
no Uzbek TTS workaround of any kind (D2). `src/skills/voice/skill.py`
is touched only in the additive shape Section 5.3 already specifies;
any deviation from that shape discovered during STEP 2 is a
STOP-and-report condition, not a silent expansion of scope.

**STEP 1 boundary maintained while resolving these decisions:** no
file under `src/`, `tests/`, or `config/` was modified, and
`requirements.txt` was not modified, to produce this resolution.
STEP 2 has not started.

---

## 10. Security and reliability

* **No network activity.** `pyttsx3` wraps a fully local OS API
  (SAPI5 on Windows); Piper (if D1 selects it instead) synthesizes
  from a locally stored model file. Neither candidate makes a network
  call to produce speech, matching `voice.offline_only: true`'s
  existing intent (Section 3.5) and `AI_GENERATION_STANDARD.md`'s
  offline/privacy posture that EP046_DESIGN.md Section 12 already
  established for this same `voice:` config block.
* **No new attack surface on arbitrary input.** `synthesize(text,
  ...)` only ever speaks `text` — it is never parsed, evaluated, or
  executed as a command by the TTS engine itself. (If Owner Decision
  D4 later adds "speak the result of a dispatched command," the
  *dispatch* step already goes through `CommandRouter`'s own existing
  validation; the TTS step downstream of it only ever receives an
  already-produced `CommandResult.message` string.)
* **Construction-time vs. per-call failure**, mirroring
  `SpeechToTextEngineError`/`AudioCaptureError` exactly (Section 5.4):
  `TextToSpeechEngineError` is raised only when no usable engine/voice
  can be constructed at all; every subsequent `synthesize()` call
  reports failure via `SynthesisResult(success=False, ...)`, never an
  exception — so a transient failure (e.g., audio device momentarily
  busy) cannot crash a shell/API/Telegram session.
* **Resource ownership.** TTS claims the audio **output** device,
  which — unlike EP-046's microphone (input) claim — is not typically
  an exclusive-lock resource on Windows (multiple applications can
  usually play audio concurrently), so the reliability profile here
  is materially lower-risk than EP-046's own microphone-contention
  discussion (EP046_DESIGN.md Section 12).
* **Lifecycle.** A `Pyttsx3TextToSpeechEngine` instance should be
  constructed once (at `Bootstrap` wiring time, mirroring
  `self._voice_engine`'s existing pattern) and reused, not
  re-constructed per call — `pyttsx3`'s own documentation and common
  usage pattern discourage repeated `pyttsx3.init()` calls within one
  process. This is a STEP 2 implementation detail flagged here so it
  is not rediscovered as a bug later.

---

## 11. Testing strategy

Proposed `tests/EP047/test_voice_tts.py` (or an extension of the
existing `tests/EP046/test_voice.py`'s combined-suite pattern — the
exact filename/registration approach is a STEP 2 detail, not a STEP 1
decision, since it does not change architecture), following
`tests/EP046/test_voice.py`'s own documented precedent exactly:

* `SynthesisResult`/`TextToSpeechEngine` interface shape.
* `Pyttsx3TextToSpeechEngine` construction validation (e.g., "no
  SAPI5 voices installed at all" handled via `TextToSpeechEngineError`
  at construction, not a crash).
* `VoiceModule._speak` (via a fake `TextToSpeechEngine`, following
  `_FakeSpeechToTextEngine`'s precedent exactly): success, failure,
  and "TTS not enabled" (`tts_engine=None`) paths.
* Bootstrap wiring: `voice.tts.enabled` false/absent/invalid all
  degrade safely with no crash and no `speak` action reachable —
  mirroring EP-046's own `voice.enabled` degrade-safely tests.
* **Anticipated gap, disclosed in advance**: exactly as EP-046 could
  not verify a real Vosk model transcribing real audio in this
  environment (no model files present), EP-047 cannot verify real
  audio actually being produced/audible in this environment (no
  physical speakers, and no guarantee any SAPI5 voice is installed in
  whatever environment STEP 2 runs in). This must be reported via
  `self.skip()`, not silently omitted — the same "skipped, not
  failed" precedent `tests/EP046/test_voice.py`'s own docstring
  states.

Default validation per `AI_DEVELOPMENT_PLAYBOOK.md`: `test EP047`
only. `test all` (full regression, currently 5,641 passed / 2
pre-existing failures / 1 skipped per the EP-046 baseline) only if
explicitly requested once STEP 2 exists.

---

## 12. STEP 1 / STEP 2 boundary

This document is the entirety of STEP 1. Confirmed, by direct
inspection immediately before finalizing this document (Section 13
below repeats this as part of the required final report):

* No file under `src/` was modified.
* No file under `tests/` was modified.
* No file under `config/` was modified.
* `requirements.txt` was not modified.
* No file belonging to EP-046 (`src/skills/voice/skill.py`,
  `speech_to_text.py`, `audio_capture.py`, `tests/EP046/test_voice.py`,
  the `voice:` block in `config/config.yaml`) was modified.
* No EP-048 (Wake Word) or EP-049 (Voice Assistant) work was
  introduced — `src/skills/voice/wake_word.py` was not touched, and
  nothing in this document proposes a continuous listening loop.
* No `docs/architecture/audits/EP047_AUDIT.md` was created (STEP 4 is
  not reached until STEP 2/3 complete, per
  `AI_DEVELOPMENT_PLAYBOOK.md`'s own Phase sequencing).
* EP-047 is **not** marked complete anywhere.

STEP 2 (Implementation), once separately approved, is scoped to
exactly: resolve Section 9's eight owner decisions; implement
`TextToSpeechEngine`/`SynthesisResult`/`Pyttsx3TextToSpeechEngine` in
the currently-empty `text_to_speech.py`; make the additive change to
`skill.py` described in Section 5.3 (and only that change); add the
`voice.tts.*` config block (Section 8/9); wire `Bootstrap` (Section
6); write `tests/EP047/`; run `test EP047` (and `test EP046` as a
targeted regression check, given the shared file — not full `test
all` unless requested).

---

## 13. Acceptance criteria (for STEP 2, not yet met)

* `test EP047`: Passed > 0, Failed = 0, Skipped = 0 unless the
  anticipated no-real-audio-output gap (Section 11) is the only
  skip, disclosed exactly as EP-046's own Vosk-model gap was.
* `test EP046`: unchanged (57 passed / 0 failed / 1 skipped, or
  whatever EP-046's count is at STEP 2 time) — proof the additive
  change to `skill.py` (Section 5.3) did not alter EP-046 behavior.
* `voice.tts.enabled` (or `voice.enabled`, per Owner Decision D6)
  defaults to `false`; an unconfigured installation sees no behavior
  change, matching every prior hardware-claiming subsystem's
  precedent.
* `VoiceModule`'s diff against its EP-046-shipped state is limited to
  exactly the items enumerated in Section 5.3 — no unrelated
  refactor, rename, or behavior change to `_listen`/`_transcribe`/
  `_status`/`execute()`.
* At least one language (English, at minimum) produces real, audible
  speech on the actual target Windows workstation — a manual
  verification step, mirroring EP-046's own disclosed "no real
  microphone/model verified in any environment this project has run
  in" limitation (`EP046_AUDIT.md` Section 14). This is expected to
  remain an open, disclosed item at STEP 2/3 close, not a blocker to
  marking EP-047 complete with documented limitations — exactly as
  EP-046 itself closed with **PASS WITH DOCUMENTED LIMITATIONS**.
* Section 9's Uzbek gap (D2) is resolved by an explicit owner choice
  and documented in `config/config.yaml`'s comments and the
  as-built design document — not silently absent.
* `docs/architecture/designs/EP047_DESIGN.md` (this document) is
  updated at STEP 2/3 close with an as-built summary section,
  following EP046_DESIGN.md Section 16's own precedent.

---

## 14. Out-of-scope items (explicit)

* Wake-word / hotword detection (`EP-048 Wake Word`, per roadmap;
  `src/skills/voice/wake_word.py` is not touched).
* Always-on background listening or a continuous voice
  conversation loop (`EP-049 Voice Assistant`, per roadmap).
* Automatically speaking every dispatched command's result by
  default (Owner Decision D4 — even if approved as an opt-in flag,
  it defaults off).
* A new REST API endpoint dedicated to speech/audio output. If
  `voice speak <text>` is ever reachable remotely, it is through the
  **existing** generic `POST /api/v1/commands` endpoint (EP-043),
  exactly as `voice transcribe`/`voice listen` already are — no new
  endpoint is proposed.
* Desktop UI (`desktop/`) or Web Dashboard (`web/`) speaker/mute
  controls. Both remain untouched by this design, exactly as EP-046
  left them untouched.
* Cloud/online TTS providers (Section 7 — rejected on the same
  offline/privacy grounds as EP-046's cloud-STT rejection).
* Streaming/incremental synthesis (speaking a sentence as it is still
  being generated/typed). V1 synthesizes one complete string and
  returns one result, mirroring EP-046's own "one completed utterance,
  one final result" v1 scope (EP046_DESIGN.md Section 2).
* SSML (Speech Synthesis Markup Language) or any rich-markup input —
  v1 speaks plain text only.
* Speaker/voice cloning or custom voice training.
* Uzbek voice output, pending Owner Decision D2 (Section 9) —
  explicitly flagged as a known, disclosed gap rather than silently
  worked around.
* Removal of the still-unused `SpeechRecognition` entry in
  `requirements.txt` — an unrelated, separate decision
  (EP046_DESIGN.md Owner Decision 4), not reopened by this EP.
* Any EP-048/EP-049 functionality of any kind.

---

## 15. Risks / limitations

* **Uzbek voice-output gap** (Section 7/9 D2) — the single largest
  open risk. No offline engine surveyed has a first-class Uzbek
  voice; this is a genuine product gap, not an implementation detail,
  and needs an explicit owner-level answer before or at STEP 2 close.
* **Unverifiable Windows SAPI5 voice availability.** Whether the
  actual target workstation has a Russian-capable SAPI5 voice
  installed (it requires an optional Windows language pack with
  speech support, not installed by default) cannot be confirmed from
  this repository/environment — exactly the same category of gap
  EP-046 disclosed for Vosk model files and physical microphones
  (`EP046_AUDIT.md` Section 14). This is expected to remain open
  until STEP 2/3 manual verification on real hardware.
* **`pyttsx3` engine lifecycle/threading caveats.** Community
  documentation and issue trackers note `pyttsx3` engines are not
  designed to be freely re-initialized or driven from multiple
  threads concurrently; STEP 2 must respect a single, reused engine
  instance (Section 10) rather than rediscover this as a bug.
* **License posture of the Piper alternative** (if Owner Decision D1
  ever revisits pyttsx3 in favor of it): the actively maintained fork
  of Piper is GPL-3.0-licensed following the original MIT-licensed
  `rhasspy/piper` repository's archival — a materially different
  licensing posture than the rest of this project's dependency list,
  and a real input to any future re-evaluation, not merely a footnote.
* **Blocking playback and future EP-049.** D5's recommended
  synchronous playback (mirroring `AudioCapture`'s own blocking
  `sounddevice.wait()`) is adequate for v1's command-style scope but
  would need revisiting if EP-049's eventual conversational loop
  requires speaking while simultaneously listening — flagged here as
  a forward-looking note, not a EP-047 blocker.
* **Shared-file risk.** Section 5.3's additive change to
  `src/skills/voice/skill.py` is the one place STEP 2 touches a file
  EP-046 already shipped and fully tested. The risk is contained by
  Section 5.3's explicit "diff, not redesign" framing and by Section
  13's requirement that `test EP046` remain unchanged, but it is a
  materially different risk profile than EP-046's own STEP 1 (which
  touched zero pre-existing non-empty files).

---

## 16. Recommended implementation sequence (for STEP 2, contingent on owner approval)

1. Obtain owner resolution of Section 9's eight decisions (D1–D8).
2. Implement `TextToSpeechEngineError`, `SynthesisResult`,
   `TextToSpeechEngine` (Protocol), and `Pyttsx3TextToSpeechEngine`
   in `src/skills/voice/text_to_speech.py` (currently empty).
3. Apply the additive change to `src/skills/voice/skill.py` described
   in Section 5.3 exactly (new optional constructor parameter, one
   new `_actions` entry, one new private method, one `HELP_TEXT`
   line) — no other change to this file.
4. Add the `voice.tts.*` block to `config/config.yaml` (Section 8),
   nested under the existing `voice:` key, defaulting to disabled
   (Owner Decision D6).
5. Wire `src/bootstrap.py`: construct `Pyttsx3TextToSpeechEngine`
   under its own independent config/try-except gate (Section 6),
   passing it into the existing `VoiceModule(...)` call.
6. Update `requirements.txt`'s `pyttsx3` comment from "reserved for
   EP-047" to "used by EP-047" (Owner Decision D7) — no version/line
   change otherwise.
7. Write `tests/EP047/` (Section 11); run `test EP047`; run `test
   EP046` as a targeted regression check for the shared file.
8. Manually verify real audible speech on the actual target Windows
   workstation, in whichever language(s) Owner Decision D2 selected;
   disclose any language that could not be verified, exactly as
   EP-046 disclosed its own unmet manual-verification items.
9. STEP 3: update this document with an as-built summary (mirroring
   EP046_DESIGN.md Section 16), create
   `docs/architecture/audits/EP047_AUDIT.md`, and update
   `docs/BACKLOG.md`/`docs/architecture/JARVIS_ROADMAP.md` following
   the EP-045/EP-046 precedent.

---

## 17. STEP 2/3 Implementation Summary (as-built)

This section records what was actually built, verified fresh at
STEP 3. It does not replace Sections 1-16 above — those remain the
STEP 1 design record and the owner's Section 9a decisions exactly as
approved. Where the two differ, the difference is a deliberate,
explained refinement (Section 6/6a's "Implemented As"/manual-finding
notes above), never an undocumented substitution. Full verification
evidence lives in `docs/architecture/audits/EP047_AUDIT.md`; this
section is the design document's own summary of the same facts.

### 17.1 Implementation files

| File | Role |
|---|---|
| `src/skills/voice/text_to_speech.py` | `TextToSpeechEngine` protocol, `SynthesisResult`, `TextToSpeechEngineError`, `Pyttsx3TextToSpeechEngine` (new) |
| `src/skills/voice/skill.py` | `VoiceModule` — additive: optional `tts_engine` parameter, `speak` action, `_speak()` method, updated `HELP_TEXT` (Section 5.3's diff, unchanged in shape from STEP 1) |
| `src/bootstrap.py` | Additive: `TextToSpeechEngine`-related imports, `self._voice_tts_engine` attribute, TTS construction nested inside the existing `voice.enabled` block under its own independent `voice.tts.enabled` check/`try`/`except` (Section 6's "Implemented As" note), `voice_tts_engine` property |
| `config/config.yaml` | New `voice.tts.*` block (Section 8), nested under the existing `voice:` key |
| `requirements.txt` | Comment-only change on the pre-existing, already-present `pyttsx3` line (Owner Decision D7) — no dependency added, removed, or version-changed |
| `src/modules/test_module.py` | One registration import line (`import tests.EP047.test_voice_tts`), the same mechanical addition every prior EP's test suite required |
| `tests/EP047/__init__.py`, `tests/EP047/test_voice_tts.py` | `TestRegistry`-registered suite, `NAME = "EP047"`, 20 test methods |

### 17.2 Technology (Owner Decision D1, Section 9a)

`pyttsx3` **2.99** — already present in `requirements.txt` since
EP-046 (Section 3.4), confirmed importable under Python 3.12 in the
verification environment. No new dependency was added to
`requirements.txt`.

As documented in Section 6a: `pyttsx3` wraps whichever OS speech
driver is present. On the Linux verification environment used for
STEP 2, this is eSpeak/eSpeak-NG (an OS package, not a Python
dependency) rather than SAPI5 — construction and a real
`synthesize()` call both completed successfully once that OS package
was installed, confirming the engine's design (wrap the OS driver
transparently, wrap absence/failure as `TextToSpeechEngineError`)
without constituting Windows/SAPI5 verification (Section 17.4).

Languages actually configured (`config/config.yaml`,
`voice.tts.languages`): **English (`en`) and Russian (`ru`)** —
matching Section 8's original proposal. **Uzbek (`uz`) is
deliberately absent**, per Owner Decision D2: no offline TTS engine
evaluated in Section 7 has a first-class Uzbek voice. This is
documented in `config/config.yaml`'s own comments, in
`text_to_speech.py`'s module docstring, and exercised by a dedicated
test (`_test_voice_module_uzbek_fails_like_any_other_unconfigured_language`)
proving `"uz"` takes the exact same "unsupported language"/"no
installed voice" path any other unconfigured language would — no
Uzbek-specific branch exists anywhere in the implementation.

### 17.3 Architecture (Section 5, confirmed unchanged)

`text (command argument) → TextToSpeechEngine.synthesize() → SynthesisResult → audio played (blocking pyttsx3 playback)`,
implemented exactly as designed (Owner Decisions D1/D3/D5).
`src/core/command_router.py` was **not modified** (confirmed
byte-identical against the pre-EP-047 archive). `VoiceModule` remains
the only `CommandModule` for the `"voice"` namespace — no second
namespace, no parallel routing mechanism (Owner Decision D3).
`VoiceModule` depends only on the `TextToSpeechEngine` **protocol**,
never on `Pyttsx3TextToSpeechEngine` directly (confirmed by direct
import inspection) — the engine remains swappable via
`voice.tts.engine`-style configuration and `Bootstrap` wiring alone,
satisfying Owner Decision D2's "architecture must remain replaceable"
requirement for a future Uzbek-capable engine.

Only `voice speak <text>` was added (Owner Decision D4/D8) — it never
calls `CommandRouter.dispatch()` (confirmed by a dedicated test using
a call-counting fake downstream module) and there is no code path
that automatically speaks a dispatched command's result. `voice
listen`, `voice transcribe`, `voice status`, and `voice help` are
unchanged in behavior (confirmed: `skill.py`'s diff against its
STEP-1/EP-046-shipped state contains zero altered existing lines —
only additions and two doc-comment rewordings) and are covered by
regression-check tests in `tests/EP047/test_voice_tts.py` in addition
to their own, still-passing `tests/EP046/test_voice.py` suite.

`voice.tts.enabled` defaults to `false` (`config/config.yaml`,
confirmed by a dedicated test reading the key's absence-default).
No wake word, always-on listening, conversation mode, or cloud TTS
was implemented — confirmed by repository-wide search for
loop/wake-word/network patterns in the voice package (none found)
and by `wake_word.py` being confirmed byte-identical/untouched.

### 17.4 Tests (as re-verified at STEP 3)

```
test EP047  →  Passed: 49    Failed: 0   Skipped: 0
test EP046  →  Passed: 57    Failed: 0   Skipped: 1
test EP043  →  Passed: 83    Failed: 0   Skipped: 0
test EP044  →  Passed: 52    Failed: 0   Skipped: 0
test EP045  →  Passed: 38    Failed: 0   Skipped: 0
test all    →  Passed: 5655  Failed: 0   Skipped: 1
```

The single skip across the full suite remains EP-046's own
disclosed, pre-existing real-microphone/real-loaded-model gap
(unrelated to EP-047, unchanged by it). `EP-039`/`EP-041` — reported
as pre-existing baseline failures at earlier points in this project's
history — reported **0 failures** in this STEP's fresh full-suite
run; both suites were also re-run in complete isolation (36/0 and
39/0 respectively) with zero EP-047 code loaded, and both files
(`tests/EP039/`, `tests/EP041/`, plus `src/services/github_service.py`
and `src/services/discord_service.py`) were confirmed byte-identical
to their pre-EP-047 state. This is treated as an **environment
difference** (this verification environment has outbound network
access those suites depend on; the network availability of any given
verification environment is outside any single EP's control), not a
regression fixed or caused by EP-047 — see `EP047_AUDIT.md` Section
11 for the full explanation.

Manual real-Windows/SAPI5-audible-speech test: **NOT AVAILABLE** — no
Windows workstation, no SAPI5, and no physical speakers exist in the
verification environment used across STEP 1-3 of this EP. Not
claimed as passed, and not satisfied by the eSpeak-based construction
success recorded in Section 6a/17.2, which is a different driver on
a different OS.

### 17.5 Owner decisions — implementation status

| # | Decision (Section 9a) | Status |
|---|---|---|
| D1 | `pyttsx3` | Implemented — no new dependency, already-present package used |
| D2 | Uzbek out of scope, no workaround, architecture replaceable | Implemented — `uz` absent from config, no special-casing in code (17.2), `TextToSpeechEngine` protocol seam intact (17.3) |
| D3 | Extend existing `voice` `CommandModule` | Implemented — no second namespace, no parallel routing (17.3) |
| D4 | Only `voice speak <text>`, no auto-speak | Implemented — confirmed no-dispatch by dedicated test (17.3) |
| D5 | Blocking `pyttsx3` playback (`say()`/`runAndWait()`) | Implemented, exactly as decided |
| D6 | Independent `voice.tts.enabled`, default `false` | Implemented for failure-mode independence; **partial** for registration independence — see Section 6's "Implemented As" note and Section 17.6 |
| D7 | `requirements.txt` comment convention | Implemented — comment-only change, no version/line change |
| D8 | Command name `voice speak` | Implemented |

Seven of eight decisions are implemented exactly as recorded, with no
silent reinterpretation. D6 is implemented as decided with respect to
*failure-mode* independence (its own stated rationale in Section 9a)
but carries one disclosed, as-built limitation regarding
*registration* independence — recorded honestly below rather than
marked simply "Implemented," per this STEP's own instruction not to
overstate conformance.

### 17.6 Known limitations

- **Registration-gating limitation (Section 6's "Implemented As"
  note):** `voice.tts.enabled: true` has no effect while
  `voice.enabled` (STT) is `false` — the `"voice"` namespace itself
  is only registered inside the outer STT gate. TTS-only operation
  (spoken output with the microphone fully disabled) is not
  supported in EP-047. This does not violate Owner Decision D6's own
  stated rationale (independent *failure modes* for STT/TTS), but is
  a narrower scope than "fully independent enablement" might imply,
  and is disclosed here rather than silently accepted as full
  conformance.
- **No real Windows/SAPI5 audible-speech verification** has been
  performed in any environment this project has run in (Section
  17.4) — the eSpeak-based construction/synthesis success recorded
  in Section 6a/17.2 confirms the engine's driver-wrapping design
  works against *a* real OS driver, but not against SAPI5
  specifically, and not with a human confirming audible sound.
- **Russian SAPI5 voice availability on the actual target Windows
  workstation remains unverified** (Section 7's own disclosed risk)
  — whether the target machine has the optional Windows language
  pack with Russian speech support installed cannot be determined
  from any environment used across STEP 1-3.
- `EP-039`/`EP-041` full-suite baseline discrepancy (Section 17.4) is
  environment-related, not caused or fixed by EP-047.
- `CHANGELOG.md`/`docs/RELEASE_NOTES.md` were not updated for EP-047,
  consistent with the same, already-established documentation gap
  `EP045_AUDIT.md`/`EP046_AUDIT.md` recorded for themselves (carried
  forward, not new — see `EP047_AUDIT.md` Section 12).

None of these limitations reflect an unresolved design ambiguity or a
scope violation (Sections 13/14 remain fully honored) — each is
either an environment constraint (no Windows/SAPI5/speakers
available to verify against) or a disclosed, narrower-than-implied
reading of D6, recorded honestly rather than silently smoothed over.

---

*(End of EP-047 STEP 1/2/3 design record. Sections 1-16 are the
original STEP 1 design and Section 9a's STEP 1 owner-decision
resolution, preserved unchanged except for the two inline
"Implemented As"/manual-finding notes in Section 6/6a. Section 17 is
the STEP 3 as-built summary. No implementation, test, or
configuration file was modified to produce this STEP 3 documentation
update.)*
