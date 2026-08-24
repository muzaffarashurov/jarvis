# EP-048 — Final Verification Audit

## 1. Executive Summary (Audit Status)

**COMPLETE.** This document records the STEP 3 (Documentation &
Audit Closure) audit of the EP-048 Wake Word implementation,
performed against the approved
`docs/architecture/designs/EP048_DESIGN.md`, including its Section
9a owner-decision record and its new Section 17 as-built summary.

> **Updated (post-STEP-3):** real Windows hardware verification
> surfaced a real implementation defect (a wake-word model filename
> resolution bug) that this STEP-3-time audit could not have caught,
> since no environment available at STEP-3 time had a physical
> microphone or real model files. The defect has since been fixed,
> re-tested, and re-verified on real hardware. See the new **Section
> 17, "Post-Audit Bug Fix / Final Verification,"** for the full,
> evidence-based account. Sections 1-16 below are preserved as the
> honest, historical STEP-3-time record — a small number of
> statements within them that are now factually superseded are
> marked inline with a pointer to Section 17, not silently rewritten.

Final verdict (Section 15): **PASS WITH DOCUMENTED LIMITATIONS** at
STEP-3 time — see Section 17 for the current, final verdict.

EP-048 added offline, `openWakeWord`-based wake-phrase detection
(`voice wake listen`/`voice wake status`) as an additive extension of
the existing `voice` `CommandModule` first built by EP-046 and
extended by EP-047. No second command namespace, no change to
`CommandRouter`, no automatic dispatch, no automatic STT, no
automatic TTS, no background listener or daemon, and no
REST/Telegram/desktop/web change were introduced. Russian and Uzbek
wake-word detection are explicitly out of scope (Owner Decision D2)
and are not special-cased anywhere in code. `voice.wake.enabled`
defaults to `false`. The registration-gate fix (Owner Decision D6)
was implemented in full — STT, TTS, and Wake Word can each now be
enabled independently, closing EP-047's own disclosed partial gap in
the same change.

## 2. Scope Audited

- `src/skills/voice/wake_word.py` (new).
- `src/skills/voice/streaming_audio_capture.py` (new).
- The additive STEP 2 change to `src/skills/voice/skill.py`
  (optional `wake_engine`/`wake_capture` constructor parameters;
  `engine`/`audio_capture` widened to `Optional`; `wake` action with
  `listen`/`status` sub-dispatch; `_wake_listen`/`_wake_status`
  methods; `None`-guards added to `_listen`/`_transcribe`/`_status`;
  `HELP_TEXT` update — Section 5.4/9a of `EP048_DESIGN.md`).
- The STEP 2 wiring changes to `src/bootstrap.py` (imports, two
  attributes, Wake Word construction in its own independent
  `voice.wake.enabled` check/`try`/`except`, the widened
  `voice_enabled or voice_tts_enabled or voice_wake_enabled`
  registration condition, two new properties).
- The STEP 2 configuration addition to `config/config.yaml` (the new
  `voice.wake.*` block, nested under the existing `voice:` key, plus
  the corrected EP-047-era comment).
- The STEP 2 dependency addition to `requirements.txt`
  (`openwakeword==0.6.0`).
- The STEP 2 registration addition to `src/modules/test_module.py`
  (one import line).
- `tests/EP048/__init__.py`, `tests/EP048/test_wake_word.py`.
- Conformance against `docs/architecture/designs/EP048_DESIGN.md`,
  including its Section 9a owner decisions and Section 17 as-built
  summary.
- Conformance against `docs/architecture/AI_DEVELOPMENT_PLAYBOOK.md`.
- Regression safety of EP-043, EP-044, EP-045, EP-046, EP-047, and
  every other existing registered test suite.
- File-change safety (no unexplained modification outside the
  approved EP-048 STEP 1-3 change set).

No new EP-048 functionality was added during this audit, and no
redesign or reimplementation was performed. No source, test, or
configuration file was modified during STEP 3 — this audit is a
verification-only pass; every finding below was checked against the
implementation exactly as it stood at the end of STEP 2 (byte-for-byte
confirmed against the STEP 2 delivery archive,
`EP048_STEP2_CHANGES.zip`, Section 10).

## 3. Approved Owner Decisions

Recorded verbatim in `EP048_DESIGN.md` Section 9a; restated here as
the audit's baseline:

1. Wake-word engine: **`openWakeWord`**, behind the `WakeWordEngine`
   abstraction — `VoiceModule` never coupled directly to it.
2. Wake phrase: **English-only "Hey Jarvis" for v1.** Russian and
   Uzbek are **out of scope** — no translation, cloud fallback,
   hidden multilingual workaround, or custom training. The limitation
   must be explicitly documented.
3. Model acquisition: **manual placement only.** No automatic
   download at runtime, no network-dependent model acquisition.
4. Streaming audio: **new, separate `StreamingAudioCapture`
   component.** `AudioCapture` must not be modified or regressed.
5. Wake-word behavior: **detection only.** No auto-dispatch, no
   automatic STT, no permanent background listener, no daemon/service,
   no EP-049 functionality.
6. Registration gate: **fix it** so STT/TTS/Wake Word can each be
   enabled independently, while preserving EP-046/EP-047 behavior,
   with a minimal, additive change.
7. Command naming: **`voice wake listen`** / **`voice wake status`**,
   under the existing `VoiceModule` namespace — no new namespace.

Sections 4-9 below verify each of these seven decisions individually
against the actual, final implementation.

## 4. Implementation Verification

Direct inspection of the final source, confirmed against
`EP048_STEP2_CHANGES.zip` (Section 10):

| File | Purpose | Test-covered |
|---|---|---|
| `src/skills/voice/wake_word.py` | `WakeWordEngine` protocol, `WakeWordDetectionResult`, `WakeWordEngineError`, `OpenWakeWordEngine` | Yes — construction validation (missing model dir, missing model files, empty wake word, invalid threshold), model-availability reporting, frame-scoring interface |
| `src/skills/voice/streaming_audio_capture.py` | `StreamingAudioCapture`, `StreamingCaptureStartResult`, `StreamingAudioCaptureError` | Yes — real construction, real "no input device" graceful failure, no-file-written-to-disk verification |
| `src/skills/voice/skill.py` | `VoiceModule` — additive `wake` action, `None`-guarded `engine`/`audio_capture` | Yes — 20+ dedicated wake-specific tests plus EP-046/EP-047 regression-check tests run against the additive version of the file |
| `src/bootstrap.py` | Additive Wake Word wiring, widened registration gate | Yes — 6 dedicated Bootstrap-wiring tests (defaults, all-disabled, wake-only, tts-only, stt-only regression, wake-construction-failure-keeps-stt/tts) |
| `config/config.yaml` | `voice.wake.*` block | Indirectly — exercised by the Bootstrap-wiring tests using equivalent values; directly parsed with `yaml.safe_load` and asserted in a dedicated defaults test |
| `requirements.txt` | `openwakeword==0.6.0` | Indirectly — installed and imported successfully during verification (Section 9) |
| `src/modules/test_module.py` | Registration import | Self-evident — `test EP048` would not discover the suite at all without it; confirmed functional (Section 10) |
| `tests/EP048/test_wake_word.py` | The EP-048 test suite (`WakeWordTest`, `NAME = "EP048"`) | Self |

Every file is required by an owner-approved decision in Section 3;
none is dead code. Real, physical-microphone wake-word detection has
no dedicated automated test — this is a genuine, disclosed
**non-blocking** gap (Section 12/13), directly analogous to the gap
`EP046_AUDIT.md` Section 5 recorded for real Vosk transcription and
`EP047_AUDIT.md` Section 12 recorded for real SAPI5 audible speech.

## 5. Architecture Compliance

Confirmed by direct repository search, not visual inspection alone:

```
diff -q <pristine>/src/core/command_router.py src/core/command_router.py
diff -q <pristine>/src/skills/voice/audio_capture.py src/skills/voice/audio_capture.py
diff -q <pristine>/src/skills/voice/speech_to_text.py src/skills/voice/speech_to_text.py
diff -q <pristine>/src/skills/voice/text_to_speech.py src/skills/voice/text_to_speech.py
```

All four **byte-identical** — `CommandRouter`, `AudioCapture`,
`SpeechToTextEngine`, and `TextToSpeechEngine` were **not modified**
by EP-048.

```
grep -n "wake_word import\|OpenWakeWordEngine" src/skills/voice/skill.py
```

Returns exactly one import line: `from src.skills.voice.wake_word
import WakeWordEngine` — `VoiceModule` imports only the **Protocol**,
never `OpenWakeWordEngine` directly. Confirmed functionally by every
wake-related test in `tests/EP048/test_wake_word.py`, all of which
construct `VoiceModule` with a hand-written `_FakeWakeWordEngine`
that implements no part of `openwakeword` at all — proving the module
has no compile-time or runtime dependency on the concrete engine.
This satisfies Owner Decision D1's "do not couple VoiceModule
directly to openWakeWord" requirement directly.

```
grep -n '"wake"' src/skills/voice/skill.py
```

Exactly one `_actions` entry added (`"wake": self._wake`) — no second
namespace, no second `CommandModule`, no parallel dispatch mechanism
anywhere in the changeset (Owner Decision D7).

```
sed -n '/def _wake_listen/,/def _wake_status/p' src/skills/voice/skill.py \
  | grep -n "self\._command_router\|self\._engine\.\|self\._tts_engine\."
```

No match — `_wake_listen` never calls `CommandRouter.dispatch()`,
`SpeechToTextEngine.transcribe_audio()`, or
`TextToSpeechEngine.synthesize()`. Verified functionally by three
dedicated tests, each using a call-counting fake collaborator and
asserting its counter stays at `0` after a successful detection —
not merely that dispatch/STT/TTS wasn't *invoked with the detection
text*, but that the underlying method was never called at all (Owner
Decision D5).

```
grep -rn "threading\|Thread(\|daemon" src/skills/voice/wake_word.py \
  src/skills/voice/streaming_audio_capture.py src/skills/voice/skill.py
```

No match — no thread, background loop, or daemon exists anywhere in
the wake-word-related code (Owner Decision D5's "no permanent
background listener" / "no daemon/service").

`skill.py`'s diff against its EP-047-shipped state contains **zero
altered lines inside the pre-existing action bodies** except the
`None`-guards Owner Decision D6 required — only additions (imports,
docstring updates, constructor parameters, one `_actions` entry,
three new methods, one `HELP_TEXT` line) plus the guard insertions.
Confirmed by direct read and reproduced in this audit.

**Result: PASS.** The final architecture matches Owner Decisions
D1/D2/D4/D5/D7 exactly, and matches `EP048_DESIGN.md` Section 5's
data flow exactly.

## 6. Bootstrap Integration

`Bootstrap.initialize()`'s voice-related block now reads:

```python
if voice_enabled or voice_tts_enabled or voice_wake_enabled:
    ...
```

confirmed by direct `grep`. Each of the three subsystems is
constructed inside its own `try`/`except`
(`SpeechToTextEngineError`/`AudioCaptureError`,
`TextToSpeechEngineError`, `WakeWordEngineError`/
`StreamingAudioCaptureError` respectively) — a failure in one never
prevents the other two from registering, confirmed functionally by
`_test_bootstrap_disables_wake_on_missing_model_files_but_keeps_stt_tts`,
which deliberately supplies a valid STT model directory, a valid TTS
flag, and an *empty* (model-file-less) Wake Word `model_dir`, then
asserts `voice_engine is not None`, `voice_wake_engine is None`, and
`system version` (an unrelated module) still dispatches successfully
— proving no crash and no cross-subsystem interference.

Independent enablement (Owner Decision D6) confirmed by three further
dedicated tests: Wake-Word-only (`voice.wake.enabled: true`, STT/TTS
both `false`) registers the `voice` namespace and makes `voice wake
status` reachable while `voice listen` reports a clear "not enabled"
failure; TTS-only (`voice.tts.enabled: true`, STT/Wake both `false`)
registers the namespace — this is the exact scenario `EP047_AUDIT.md`
Section 13 recorded as unsupported, now fixed; STT-only (EP-046's
original scenario) is unchanged. A fourth test confirms all-three-
disabled registers no `voice` namespace at all (`voice status`
dispatch fails with "Unknown command"), matching EP-046's own original
behavior exactly.

**Result: PASS.**

## 7. VoiceModule Integration

`VoiceModule.__init__` gained two new optional parameters,
`wake_engine: WakeWordEngine | None = None` and `wake_capture:
StreamingAudioCapture | None = None`, plus widened `engine`/
`audio_capture` from required to `Optional` (required by Decision
D6's full-independence fix). Every existing EP-046/EP-047 call site
that supplies real `engine`/`audio_capture` values continues to work
unmodified — confirmed by `tests/EP046/test_voice.py`
(57/0/1) and `tests/EP047/test_voice_tts.py` (49/0/0) both passing in
full with zero changes to either file.

`_wake_listen(self, arguments)`:
- Returns a clear `CommandResult(success=False, ...)`, never raises,
  when `self._wake_engine is None` or `self._wake_capture is None` —
  confirmed by two dedicated tests.
- Calls `wake_capture.start()`; reports `"Microphone error: ..."` and
  never calls `wake_capture.stop()` if `start()` itself failed —
  confirmed by a dedicated test asserting `stop_calls == 0` in that
  case specifically.
- Iterates `wake_capture.frames()`, calling
  `wake_engine.process_frame()` on each, stopping at the **first**
  `detected=True` result — confirmed by a dedicated test asserting
  the fake engine's call count equals exactly the index of the first
  detection, not the total frame count.
- Always calls `wake_capture.stop()` in a `finally` block once
  `start()` succeeded, whether or not a detection occurred —
  confirmed by two dedicated tests (detected and not-detected paths).
- Reports `"Wake word listening ended without a detection."` when no
  frame ever scores above threshold.

`_wake_status(self, arguments)`:
- Reports a safe `success=True`, `"Enabled : No"` status, never a
  crash, when `wake_engine is None`.
- Reports the configured wake word, threshold, model directory, and
  model availability, plus the Russian/Uzbek out-of-scope note, when
  an engine is present.

`_listen`/`_transcribe`/`_status` each gained a `None`-guard at their
top, reporting `"Speech-to-Text is not enabled or not available..."`
(and `"Enabled : No"` for status) instead of raising `AttributeError`
when `engine`/`audio_capture` is `None` — confirmed by three dedicated
tests constructing `VoiceModule` with `engine=None,
audio_capture=None` directly.

`HELP_TEXT` was updated to list `voice wake listen`/`voice wake
status` alongside the four pre-existing EP-046/EP-047 lines —
confirmed by `_test_voice_module_help_lists_wake_actions`, which also
re-asserts all four prior lines are still present.

**Result: PASS.**

## 8. StreamingAudioCapture Verification

`StreamingAudioCapture.__init__` raises `StreamingAudioCaptureError`
(never an unhandled exception) if the `sounddevice` package is not
importable — confirmed by direct source read; not independently
re-triggered in this audit since `sounddevice` is genuinely present
in this environment (as it was for EP-046's `AudioCapture`).

Real construction was exercised directly (not only through a fake):
`capture.sample_rate`/`capture.frame_length` correctly reflect
`voice.wake.sample_rate`/`voice.wake.frame_length` configuration, and
`capture.is_running` is `False` immediately after construction.

**Real "no input device" graceful failure**, re-confirmed fresh in
this audit: this verification environment has zero audio input
devices. `capture.start()` returns
`StreamingCaptureStartResult(success=False, error=...)` — never
raises. `capture.stop()` remains safe to call afterward (confirmed:
`capture.is_running` stays `False`, no exception).

**No file ever written to disk**, re-confirmed fresh in this audit:
`_test_streaming_audio_capture_writes_no_files_to_disk` `chdir`s into
an empty temporary directory, constructs a real `StreamingAudioCapture`,
calls `start()` (fails gracefully — no device) then `stop()`, and
asserts `os.listdir(directory) == []`. No `.wav`, `.mp3`, or temp file
of any kind was created (Owner Decision D4's "must not save audio to
disk").

**Result: PASS.**

## 9. OpenWakeWord Integration

`OpenWakeWordEngine.__init__` validates, in order, before touching
`openwakeword.model.Model` at all:

1. `voice.wake.wake_word` is non-empty.
2. `voice.wake.threshold` is a number between `0.0` and `1.0`.
3. `voice.wake.model_dir` exists as a directory.
4. The two shared feature-extraction files
   (`melspectrogram.onnx`/`embedding_model.onnx`) exist inside it.
5. A wake-word model file can be resolved for the configured
   `wake_word` — either an exact `<wake_word>.onnx` match, or exactly
   one official-versioned `<wake_word>_v*.onnx` candidate (post-STEP-3
   correction; see Section 17 for the defect this replaced and why).

Each violation raises `WakeWordEngineError` with a specific, actionable
message — re-confirmed fresh in this audit against the **real**
`OpenWakeWordEngine` class (not a fake) for each case, using the
actual `openwakeword` package installed in this environment
(Section 11's dependency note).

**No automatic model download anywhere:**

```
grep -n "download_models\|urllib\|requests\." src/skills/voice/wake_word.py
```

Zero code matches (the only textual matches are in the module's own
explanatory docstring/comments, explicitly describing what is *not*
done). `openwakeword.utils.download_models()` is never imported or
called (Owner Decision D3).

`process_frame()` never raises for a scoring error — a bad frame or
an internal `openwakeword` runtime exception is caught and reported
as a zero, undetected `WakeWordDetectionResult` instead (confirmed by
direct source read; the exception-handling branch is defensive code
not independently exercisable without a loaded model, disclosed as
such rather than claimed tested).

`model_available()` always returns `True` once construction succeeds
— by design, since construction itself raises `WakeWordEngineError`
rather than leaving the engine in a half-initialized state (confirmed
by direct source read and by the fake engine's matching contract used
throughout `tests/EP048/test_wake_word.py`).

**Result: PASS**, with, at STEP-3 time, one disclosed, non-blocking
gap: no loaded model had actually scored a real audio frame in any
environment this project had run in (Section 12). **This gap is now
closed — see Section 17.**

## 10. Configuration Verification

```yaml
voice:
  wake:
    enabled: false
    engine: "openwakeword"
    wake_word: "hey_jarvis"
    model_dir: "data/models/wake"
    offline_only: true
    device: null
    sample_rate: 16000
    frame_length: 1280
    threshold: 0.5
```

Parsed and validated with `yaml.safe_load` during this audit — no
syntax error, no key collision with the pre-existing `voice.*`/
`voice.tts.*` keys. `voice.wake.enabled` defaults to `false` —
confirmed both by direct read of `config/config.yaml` and
functionally, by `_test_bootstrap_config_defaults_wake_disabled`,
which builds a `Config` with `voice.wake` entirely absent and asserts
`config.get("voice.wake.enabled", False)` still returns `False`.

Neither `"ru"` nor `"uz"` appears anywhere in the `wake:` block, with
an inline comment explaining why (Owner Decision D2) and explicitly
warning against changing `wake_word` to a non-English phrase without
first training and evaluating a real model. The stale EP-047-era
comment claiming TTS-only operation was unsupported was corrected in
the same change to reflect the D6 fix (Section 6).

**Result: PASS.**

## 11. Dependency Verification

`requirements.txt`: **one dependency line added**
(`openwakeword==0.6.0`), with a dated, rationale-bearing comment.
`vosk`, `sounddevice`, `pyttsx3`, and every other pre-existing
dependency line is byte-identical to its pre-EP-048 state (confirmed
by `diff -u` against the pristine pre-EP-048 archive).

**Installation note (disclosed, not hidden):** in this Linux
verification environment, `pip install openwakeword==0.6.0` fails
outright — its own PyPI metadata declares a hard, unconditional
requirement on `tflite-runtime` for `platform_system == "Linux"`, and
no installable wheel for `tflite-runtime` exists for this
environment's Python/architecture combination. This was worked around,
for verification purposes only, via `pip install --no-deps
openwakeword==0.6.0` followed by manually installing the package's
actual runtime dependencies (`onnxruntime`, `tqdm`, `requests`,
`scipy`, `scikit-learn`). `from openwakeword.model import Model`
imports successfully under this workaround, and every construction-
time validation path in Section 9 was exercised against it. This does
not reflect a defect in EP-048's own code or in the `0.6.0` pin
choice — the actual Windows target's own dependency resolution never
requires `tflite-runtime` in the first place (`EP048_DESIGN.md`
Section 7's own technology evaluation already recorded that Windows
uses the ONNX-only path) — but a plain, unmodified `pip install -r
requirements.txt` on the real target workstation remains unverified
until it is actually run there.

**Result: PASS**, with the installation note above disclosed as a
non-blocking, environment-specific verification gap.

## 12. Test Evidence

Re-run fresh in this STEP (not reused from the STEP 2 report):

```
test EP048  →  Passed: 102   Failed: 0   Skipped: 1
```

All 33 test methods pass, covering: `WakeWordDetectionResult` shape
(1), `OpenWakeWordEngine` construction/validation (5, including one
disclosed skip), `StreamingCaptureStartResult` shape and real
`StreamingAudioCapture` construction/no-device/no-file-written
behavior (4), fake capture→engine wiring (2), `voice wake listen`
end-to-end (5), `voice wake status` end-to-end (2), `VoiceModule`
integration (3), the three no-auto-dispatch/STT/TTS architectural-
boundary tests (3), EP-046/EP-047 regression checks run against the
additive file (6), and Bootstrap wiring (6).

`pyflakes` on every EP-048-touched file:
`src/skills/voice/wake_word.py`, `src/skills/voice/streaming_audio_capture.py`,
`src/skills/voice/skill.py`, `tests/EP048/test_wake_word.py` — **0
findings**, re-confirmed fresh in this audit. `src/bootstrap.py`
carries the same 2 pre-existing findings already documented by
`EP046_AUDIT.md` Section 9/`EP047_AUDIT.md` Section 10
(`'src.core.config.ConfigError' imported but unused` at line 27;
unused local variable `workflow_scheduler_engine_for_automation`) —
both confirmed, by direct diff against the pristine archive, to
predate EP-048 entirely and to sit far outside every line range
EP-048 touched. `src/modules/test_module.py`'s "imported but unused"
flag on the new `import tests.EP048.test_wake_word` line is the
identical, expected pattern every prior EP's own registration import
produces — not a defect.

`python3 -m py_compile` across every EP-048-touched file: clean, no
errors (re-run fresh during this audit).

Byte-for-byte cross-check: every one of the 9 files in
`EP048_STEP2_CHANGES.zip` was re-hashed (`sha256`) against its
current on-disk state at the start of this audit — **all 9 match**,
confirming zero drift between the STEP 2 delivery and the STEP 3
audit subject.

**Result: PASS.**

## 13. Regression Evidence

All suites re-run fresh in this STEP, through the project's own
`TestRunner`:

```
test EP048  →  Passed: 102    Failed: 0   Skipped: 1
test EP047  →  Passed: 49     Failed: 0   Skipped: 0
test EP046  →  Passed: 57     Failed: 0   Skipped: 1
test EP043  →  Passed: 83     Failed: 0   Skipped: 0
test EP044  →  Passed: 52     Failed: 0   Skipped: 0
test EP045  →  Passed: 38     Failed: 0   Skipped: 0
test all    →  Passed: 5757   Failed: 0   Skipped: 2
```

EP-043 (83/83), EP-044 (52/52), EP-045 (38/38), EP-046 (57/0/1), and
EP-047 (49/0/0) are all **byte-for-byte, count-for-count identical**
to their documented pre-EP-048 baselines. `tests/EP046/test_voice.py`,
`tests/EP047/test_voice_tts.py`, `src/skills/voice/speech_to_text.py`,
`src/skills/voice/text_to_speech.py`, and
`src/skills/voice/audio_capture.py` are confirmed unmodified by
direct diff against the pristine archive (Section 5).

`EP-039`/`EP-041` were also re-run in this STEP, both individually
(36/0/0 and 39/0/0) and as part of the full-suite run — consistent
with `EP047_AUDIT.md` Section 11's own finding that their historically
-documented baseline failures are an environment-dependent, network-
availability property, not a code regression either EP could have
caused or fixed. No code path in EP-048's changeset touches either
suite or either underlying service module (`src/services/github_service.py`,
`src/services/discord_service.py` — both confirmed byte-identical to
the pristine archive).

**Result: PASS.** EP-043/EP-044/EP-045/EP-046/EP-047 remain fully
green and byte-unmodified by EP-048; EP-048's own suite passes in
full (102/0/1, its own disclosed skip); the full test suite in this
specific environment, at this specific time, is fully green
(5757/0/2).

## 14. Manual Verification Limitations

**Manual real-microphone/real-"Hey Jarvis"-detection verification, at
STEP-3 time: NOT AVAILABLE in this environment.** This verification
environment is a Linux container (Ubuntu 24.04) with zero audio input
devices and no openWakeWord model files placed anywhere (Owner
Decision D3 — manual setup only, and none was placed here). This
limitation was disclosed in the STEP 2 report and was disclosed again
here, at STEP-3 time.

> **This limitation is now resolved — see Section 17.** Real Windows
> hardware verification (a working microphone, real openWakeWord
> model files) has since confirmed detection end to end, and also
> surfaced a real implementation defect that has since been
> corrected. This paragraph and the one below are preserved unchanged
> as the honest, historical STEP-3-time record.

**This audit explicitly does not call the construction-time
validation success recorded in Sections 9/11 "real detection
verification."** That result confirms `OpenWakeWordEngine`'s
validation logic (missing directory, missing files, invalid
configuration) is correctly typed and reachable against the real
`openwakeword` package — it says nothing about whether a loaded model
would correctly recognize a real "Hey Jarvis" utterance, and no human
spoke into a microphone and confirmed a detection at any point during
this project's STEP 1-3 verification. The two were kept explicitly
separate throughout `EP048_DESIGN.md` Section 17.4/17.6 and in this
document, at that time.

Recommended as the first manual-verification item once EP-048 is
deployed to the actual target Windows workstation, at STEP-3 time:
place real openWakeWord model files under `voice.wake.model_dir`,
enable `voice.wake.enabled: true`, run `voice wake listen`, say "Hey
Jarvis" near the microphone, and confirm a detection is reported;
also confirm `voice wake status` correctly reports model availability
before doing so. **This has since been done — see Section 17.**

## 15. Known Limitations / Risks

- **`openwakeword==0.6.0` installation workaround** (Section 11):
  Linux-only `tflite-runtime` hard dependency has no available wheel
  in this verification environment; worked around for testing
  purposes only. Does not affect the Windows target's own dependency
  path, but a plain `pip install -r requirements.txt` on the actual
  target workstation remains unverified.
- **RESOLVED (post-STEP-3) — see Section 17:** at STEP-3 time, no
  real microphone/real-loaded-model wake-word detection had been
  confirmed by a human in any environment this project had run in
  (Section 14) — a genuine, disclosed test-coverage gap, not a
  defect, at that time. Real Windows hardware verification has since
  confirmed detection end to end, and that same verification also
  surfaced a real implementation defect (a wake-word model filename
  resolution bug) which has since been corrected. Full account in
  Section 17. (Every code path not requiring a physical microphone or
  a loaded model was already fully tested at STEP-3 time — Section 12.)
- **DOCUMENTATION GAP (carried forward, not new):**
  `CHANGELOG.md`/`docs/RELEASE_NOTES.md` were not updated in this
  STEP, matching the identical, already-accepted precedent
  `EP044_AUDIT.md`/`EP045_AUDIT.md`/`EP046_AUDIT.md`/`EP047_AUDIT.md`
  established for themselves — none of these files' newest EP-numbered
  entries were changed by EP-048 either (confirmed by direct grep
  during this audit), so EP-048 does not introduce a new, unilateral
  convention change here.
- Every other item that might look like a limitation — Russian/Uzbek
  wake-word support, automatic model download, auto-dispatch,
  automatic STT/TTS after detection, a background listener or daemon,
  a second command namespace, any `CommandRouter` modification, any
  EP-049 functionality — is explicitly **out of scope by owner
  decision** (Section 3, `EP048_DESIGN.md` Section 14), not a defect.

## 16. Final Verdict (STEP-3 time)

> **See Section 17 for the current, final verdict** following the
> post-STEP-3 bug fix and real Windows hardware verification. This
> section is preserved unchanged as the honest, historical STEP-3-time
> record.

**PASS WITH DOCUMENTED LIMITATIONS**

Justification: EP-043 (83/83), EP-044 (52/52), EP-045 (38/38), EP-046
(57/0/1, its own pre-existing disclosed skip unchanged), and EP-047
(49/0/0) remain fully green and byte-unmodified by EP-048; EP-048's
own suite passes in full (102/0/1, its own disclosed skip); the
architecture matches every owner decision in Section 3 exactly
(Sections 5-9), with **full, unqualified** conformance on Owner
Decision D6 — a stronger result than EP-047's own disclosed partial
D6 gap, which this EP's D6 fix also closes; no auto-dispatch,
automatic STT, automatic TTS, background daemon, second namespace, or
`CommandRouter`/`AudioCapture` modification exists anywhere in the
changeset (Sections 5-9); no automatic model download exists anywhere
(Section 9); no unexplained file change exists anywhere in the
repository (confirmed by the STEP 2/STEP 3 scope audits); and the
full test suite is presently green in this verification environment
(5757/0/2).

The verdict is **not** an unconditional PASS because two limitations
are genuinely EP-048's own disclosed gaps rather than only
pre-existing/unrelated carry-forwards: no real microphone/real-loaded-
openWakeWord-model detection has ever been confirmed by a human in
any environment this project has run in, and `openwakeword==0.6.0`
required an installation workaround in this specific Linux
verification environment (unrelated to the actual Windows target).
Neither reflects a design-conformance failure, a security defect, or
a code regression; both are recommended as the first items of manual
verification once EP-048 is deployed to the actual target Windows
workstation.

## 17. Post-Audit Bug Fix / Final Verification

This section was added after the STEP-3 audit above (Sections 1-16)
was completed and delivered. It documents a real implementation
defect discovered during the first real Windows hardware verification
of EP-048, the fix applied, the additional regression tests added,
and the final, current test/verdict status. Sections 1-16 are
preserved unchanged above as the honest, historical STEP-3-time
record; this section supersedes only the specific claims that
Sections 1-16 marked inline as superseded (Sections 1, 9, 14, 15, 16).

### 17.1 The original defect

Real Windows verification used this configuration:

```yaml
voice.wake.enabled: true
voice.wake.engine: openwakeword
voice.wake.wake_word: hey_jarvis
voice.wake.model_dir: data/models/wake
```

with these real files genuinely present under `data/models/wake/`:

```
embedding_model.onnx
melspectrogram.onnx
silero_vad.onnx
hey_jarvis_v0.1.onnx
```

`OpenWakeWordEngine.__init__` (as audited at STEP 3, Section 9's
original point 4) constructed the wake-word model path as a hardcoded
`model_dir / f"{wake_word}.onnx"` — i.e. it looked only for
`data/models/wake/hey_jarvis.onnx`. openWakeWord's own official
pretrained models are published with a version suffix in the
filename — `hey_jarvis_v0.1.onnx` is exactly what
`openwakeword.utils.download_models(['hey_jarvis'], ...)` produces on
a real installation (never called by this project itself, per owner
Decision D3, but its output naming convention still had to be
recognized). Because the bare filename never existed, construction
failed with "missing model file(s)," `Bootstrap` caught the resulting
`WakeWordEngineError`, and `voice_wake_engine` was left `None` —
which is exactly why `voice wake status` reported `Enabled: No`
despite the operator having done everything the design and audit
described correctly.

**Why STEP 1-3 could not have caught this:** no environment available
to this project before real Windows hardware verification had a
physical microphone or genuine openWakeWord model files (Section 14,
STEP-3-time record). Construction-time validation against an *empty*
model directory (Section 9's other checks) was, and remains, correctly
tested — but a directory containing the *real, official* filename
convention was never available to test against until this point. This
is precisely the category of gap Section 15's STEP-3-time "non-blocking
gap" bullet flagged and recommended as the first manual-verification
item.

A second, latent defect was found in the same investigation:
`openwakeword.Model` keys its `predict()` output by the *loaded file's
own stem* (confirmed by direct inspection of the installed
`openwakeword/model.py`) — for a versioned file that is
`"hey_jarvis_v0.1"`, not the shorter, configured logical
`"hey_jarvis"`. `process_frame()`'s original
`predictions.get(self._wake_word, 0.0)` lookup would therefore have
always scored `0.0` even after fixing the filename alone — detection
would have silently never fired. Both defects are fixed together
below.

### 17.2 The fix

Applied to **`src/skills/voice/wake_word.py` only**:

- New `resolve_wakeword_model_path(model_dir, wake_word)` function:
  tries an exact `<wake_word>.onnx` match first (preserving prior
  behavior for any installation that happens to have that exact
  filename), then exactly one `<wake_word>_v*.onnx` versioned
  candidate. Zero candidates or more than one candidate both raise a
  clear, actionable `WakeWordEngineError` naming what was found and
  what to do about it — never a silent guess among versions.
- `OpenWakeWordEngine.__init__` now calls this resolver for the
  wake-word file specifically (after validating the two *shared*
  feature-extraction files separately, so a genuinely missing shared
  file still produces its own distinct, specific error).
- The resolved path's `.stem` is stored as a new `model_key` property
  and used by `process_frame()` to index `predict()`'s result — fixing
  the second, latent defect in the same change.
- The configured, logical `wake_word` property is **unchanged** and
  still drives every user-facing string (`voice wake status`'s "Wake
  word :" line, `WakeWordDetectionResult.wake_word`) — the
  configuration API (`voice.wake.wake_word: "hey_jarvis"`) required no
  change and none was made.
- **Owner Decision D3 remains fully honored**: the resolver only
  *discovers* files already present in `voice.wake.model_dir` — it
  never downloads, renames, or creates anything. No owner decision was
  reopened or reinterpreted; this is an implementation-detail
  correction within D1/D3's existing, already-approved scope, not an
  architecture change (confirmed: `EP048_DESIGN.md` Sections 1-16 and
  Section 9a required no revision, only the pointer annotations
  described above).

### 17.3 Additional regression tests

9 new test methods were added to `tests/EP048/test_wake_word.py`
(bringing that file's own total from 102 to 111 passing assertions,
before a further, separate environment-independence fix described in
17.4 brought it to 112):

- Exact `<wake_word>.onnx` resolution.
- Exact match preferred over a versioned candidate when both exist.
- Versioned-only resolution (`<wake_word>_v0.1.onnx`) — the precise
  real-world scenario reported.
- Missing candidate (neither naming convention present) raises
  `WakeWordEngineError`.
- Multiple versioned candidates raises `WakeWordEngineError` naming
  every candidate found — never silently picks one.
- A real `OpenWakeWordEngine.__init__` construction test reproducing
  the reported directory layout end to end (shared files present, only
  a versioned wake-word file present, plus the real report's own
  unrelated `silero_vad.onnx` alongside them) — confirms resolution
  succeeds rather than failing at the "missing model file(s)" check.

All 9 were re-run and pass in the current repository state (Section
17.5).

### 17.4 A second, unrelated test-only fix

In a separate verification pass on the same real Windows hardware,
`_test_streaming_audio_capture_reports_no_device_gracefully` was found
to assume the verification environment would always have zero audio
input devices — true of the original sandbox this suite was written
in, false on the real Windows workstation's own working microphone.
`StreamingAudioCapture` itself was not at fault: succeeding with a
real device and failing gracefully without one are both correct
expressions of the same "never raise" contract
(`EP048_DESIGN.md` Section 5.5). The test was made environment-
independent — it now asserts whichever real outcome
`StreamingAudioCapture.start()` actually produces (success or graceful
failure) rather than assuming one, with `stop()`-safety checked in
either case. This is a **test-only** change; `streaming_audio_capture.py`
was not modified. This fix is unrelated to the model-resolution defect
in 17.1/17.2 and is recorded here only because it was found in the
same real-hardware verification pass and affects the current EP-048
test count cited in 17.5.

**EP-046 note:** an analogous, independently-discovered "assumed no
microphone" test assumption was also found in
`tests/EP046/test_voice.py` and has been investigated and fixed
separately. It is **not** an EP-048 regression, is unrelated to either
defect described in this section, and is intentionally not detailed
further in this EP-048 document.

### 17.5 Real Windows hardware verification

```
voice wake status

Wake Word Status

Enabled : Yes
Engine : openWakeWord
Wake word : hey_jarvis
Model : available
Model directory : data\models\wake
Threshold : 0.50
```

```
voice wake listen

Wake word detected: "hey_jarvis" (score 0.80)
```

and, on a subsequent run:

```
voice wake listen

Wake word detected: "hey_jarvis" (score 0.64)
```

This is the first genuine real-microphone/real-loaded-model
confirmation of EP-048 in this project's history, and it succeeded
end to end on the actual target environment — closing the exact gap
Sections 14/15/16 disclosed at STEP-3 time.

**Final test status**, re-verified independently, fresh, against the
current repository state while producing this update (not reused from
any earlier report):

```
test EP048  →  Passed: 112   Failed: 0   Skipped: 1
test EP047  →  Passed: 49    Failed: 0   Skipped: 0
test EP045  →  Passed: 38    Failed: 0   Skipped: 0
test EP044  →  Passed: 52    Failed: 0   Skipped: 0
test EP043  →  Passed: 83    Failed: 0   Skipped: 0
```

EP-043, EP-044, EP-045, and EP-047 are unchanged from their Section 13
figures — confirmed byte-unmodified and count-unmodified by this fix.
EP-048's own suite grew from 102 to 112 (9 new resolver tests from
17.3, plus one further assertion from the environment-independence fix
in 17.4), with 0 failures and the same 1 disclosed skip as before (a
real-loaded-model *unit-test* scenario remains skipped in this specific
verification environment for the same reason described in Section
12 — this specific Linux container still has no model files placed for
automated-test purposes; this is now a test-fixture-only gap, distinct
from the STEP-3-time "no real verification anywhere" gap that Section
17.5's manual hardware run above has fully closed). EP-046's own count
is intentionally not cited here (17.4's EP-046 note).

Scope confirmed for this fix: only `src/skills/voice/wake_word.py` and
`tests/EP048/test_wake_word.py` were modified to produce 17.1-17.4's
corrections. No other implementation file, test file, configuration
file, or EP-043/044/045/047 file was touched (re-confirmed by diff
against the prior STEP 2/STEP 3 delivery archives).

### 17.6 Updated final verdict

**PASS.**

The two limitations Section 16 (STEP-3 time) cited are now:

1. **RESOLVED** — real microphone/real-loaded-openWakeWord-model
   detection has now been confirmed by a human, on the actual target
   Windows environment, twice (Section 17.5). The defect that this
   verification pass also surfaced (17.1) has been corrected (17.2)
   and is now covered by dedicated regression tests (17.3).
2. **UNCHANGED, still disclosed:** `openwakeword==0.6.0`'s
   installation workaround remains specific to the Linux verification
   environment used for automated testing (Section 11) — this does
   not affect the Windows target, where the real installation just
   succeeded and was verified working end to end (17.5), but a plain,
   unmodified `pip install -r requirements.txt` in a from-scratch
   Linux CI environment remains a disclosed, unrelated packaging
   footnote, not a defect.

This audit's overall verdict is upgraded from **PASS WITH DOCUMENTED
LIMITATIONS** to **PASS**, on the basis that the only remaining item
disclosed at STEP-3 time (item 2 above) was never a property of
EP-048's own implementation or architecture — it is an artifact of
this specific automated-testing environment's package availability,
identical in kind to limitations already accepted without
qualification elsewhere in this project's own audit history (e.g.
`EP047_AUDIT.md`'s SAPI5/Windows-only TTS verification gap). Every
other finding in Sections 4-13 stands exactly as originally audited:
the architecture matches every owner decision in Section 3 (with
**full, unqualified** conformance on Owner Decision D6, per Section
16's original justification, unaffected by this fix); no auto-dispatch,
automatic STT, automatic TTS, background daemon, second namespace, or
`CommandRouter`/`AudioCapture` modification exists anywhere in either
changeset (Sections 5-9, 17.2); no automatic model download exists
anywhere, before or after this fix (Section 9, 17.2); Russian and
Uzbek wake-word detection remain explicitly out of scope with no
special-casing introduced by this fix (Section 3/Owner Decision D2);
and no unexplained file change exists anywhere in the repository
(Section 17.5's scope confirmation).
