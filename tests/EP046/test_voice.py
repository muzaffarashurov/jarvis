"""Real engineering tests for EP-046 STEP 2 - Speech-to-Text.

Single combined test suite (NAME = "EP046"), following the same
precedent EP-043 (tests/EP043/test_rest_api.py) and EP-045
(tests/EP045/test_web_dashboard.py) already established: this
sidesteps the pre-existing `TestRegistry` NAME-collision technical
debt (docs/BACKLOG.md) entirely rather than triggering it.

Deterministic: no real microphone and no real Vosk model files are
required. `SpeechToTextEngine`/`AudioCapture` are exercised through
fakes wherever a real model/microphone would otherwise be needed (see
`_FakeSpeechToTextEngine`/`_FakeAudioCapture` below); the *real*
`VoskSpeechToTextEngine`/`AudioCapture` classes are exercised directly
wherever their behavior does not require a loaded model
(construction validation, missing-model-directory handling,
confidence normalization). `AudioCapture.capture()`'s real,
physical-device behavior is exercised environment-independently: this
suite makes no assumption about whether a microphone is present in
the environment it runs in (a device-less CI sandbox and a real
workstation with a working microphone are both valid, and both are
asserted against correctly -- see
`_test_audio_capture_reports_no_device_gracefully`).

One scenario (an actual audio clip transcribed by a real Vosk model)
is not exercised here: no Vosk model files exist in this environment
(EP046_DESIGN.md Section 9a Decision 10 -- manual model setup only,
no automatic downloader, and none was placed here). That case is
reported via `self.skip()`, matching EP046_DESIGN.md Section 11's own
"skipped, not failed, when the model directory is absent" precedent
-- not silently omitted.

Covers:
    - TranscriptionResult/SpeechToTextEngine interface shape.
    - VoskSpeechToTextEngine construction validation and per-language
      lazy model loading/error handling.
    - Vosk confidence normalization (mean of per-word `conf` values).
    - AudioCapture construction and real device-availability handling
      (environment-independent: accepts either a real device's
      successful capture or a real "no input device" failure --
      never a raised exception either way).
    - VoiceModule: listen / transcribe / status / unknown action.
    - Low-confidence transcripts are reported, never dispatched.
    - Integration: a dispatched voice transcript produces the exact
      same CommandResult direct CommandRouter.dispatch() would.
    - Bootstrap wiring: voice.enabled false/absent/invalid-model_dir
      all degrade safely with no crash and no VoiceModule registered.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path

from src.bootstrap import Bootstrap
from src.core.command_router import CommandResult, CommandRouter
from src.core.config import Config
from src.skills.voice.audio_capture import AudioCapture, AudioCaptureResult
from src.skills.voice.skill import VoiceModule
from src.skills.voice.speech_to_text import (
    SpeechToTextEngineError,
    TranscriptionResult,
    VoskSpeechToTextEngine,
)
from src.testing.base_test import BaseTest
from src.testing.registry import TestRegistry
from tests.EP045.test_web_dashboard import (
    _MINIMAL_BOOTSTRAP_CONFIG_YAML,
    _ChdirGuard,
    _api_section,
)


class _RecordingModule:
    """Minimal CommandModule stub that records how many times it ran.

    Used to prove a low-confidence or dry-run ("voice transcribe")
    path never reaches CommandRouter.dispatch() -- if it did, this
    module's call count would increase.
    """

    def __init__(self, namespace: str = "echo") -> None:
        self._namespace = namespace
        self.call_count = 0

    @property
    def name(self) -> str:
        return self._namespace

    def execute(self, action: str, arguments: list[str]) -> CommandResult:
        self.call_count += 1
        if action != "say":
            return CommandResult(success=False, message=f"Unknown command: {self._namespace} {action}")
        return CommandResult(success=True, message=" ".join(arguments))


@dataclass
class _FakeSpeechToTextEngine:
    """Fake SpeechToTextEngine: returns a pre-canned result, never touches Vosk."""

    canned_result: TranscriptionResult
    languages: list[str]
    default_language_value: str = "en"
    min_confidence_value: float | None = 0.5

    @property
    def supported_languages(self) -> list[str]:
        return self.languages

    @property
    def default_language(self) -> str:
        return self.default_language_value

    @property
    def min_confidence(self) -> float | None:
        return self.min_confidence_value

    def model_available(self, language: str) -> bool:
        return language in self.languages

    def transcribe_audio(
        self, pcm_data: bytes, sample_rate: int, language: str | None = None
    ) -> TranscriptionResult:
        return self.canned_result


@dataclass
class _FakeAudioCapture:
    """Fake AudioCapture: returns a pre-canned result, never touches sounddevice."""

    canned_result: AudioCaptureResult

    def capture(self) -> AudioCaptureResult:
        return self.canned_result


def _write_voice_bootstrap_config(directory: Path, voice_section: str) -> None:
    """Write a minimal bootstrap config.yaml (EP-045's fixture) plus a 'voice:' block."""
    config_dir = directory / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    base_yaml = _MINIMAL_BOOTSTRAP_CONFIG_YAML.format(
        api_section=_api_section(enabled=False, web_dashboard_dir=None)
    )
    (config_dir / "config.yaml").write_text(base_yaml + "\n" + voice_section, encoding="utf-8")


@TestRegistry.register
class VoiceTest(BaseTest):
    NAME = "EP046"

    def run(self):
        self._test_transcription_result_shape()
        self._test_vosk_engine_rejects_empty_languages_config()
        self._test_vosk_engine_rejects_missing_model_dir()
        self._test_vosk_engine_constructs_with_existing_empty_model_dir()
        self._test_vosk_engine_transcribe_missing_language_model_returns_failure()
        self._test_vosk_engine_transcribe_empty_audio_returns_no_speech_detected()
        self._test_vosk_engine_transcribe_unsupported_language_returns_failure()
        self._test_normalize_confidence_averages_word_confidences()
        self._test_normalize_confidence_returns_none_when_no_words()
        self._test_real_transcription_with_loaded_model_not_available_in_this_environment()

        self._test_audio_capture_constructs_with_real_sounddevice()
        self._test_audio_capture_reports_no_device_gracefully()

        self._test_voice_module_name_is_voice()
        self._test_voice_module_unknown_action_returns_failure()
        self._test_voice_module_help_lists_commands()
        self._test_voice_module_listen_dispatches_through_command_router()
        self._test_voice_module_listen_matches_direct_dispatch()
        self._test_voice_module_listen_blocks_low_confidence_and_does_not_dispatch()
        self._test_voice_module_listen_microphone_failure_returns_failure()
        self._test_voice_module_listen_recognition_failure_returns_failure()
        self._test_voice_module_transcribe_never_dispatches()
        self._test_voice_module_status_reports_languages_and_models()

        self._test_bootstrap_skips_voice_when_config_absent()
        self._test_bootstrap_starts_voice_when_enabled_and_model_dir_exists()
        self._test_bootstrap_disables_voice_on_invalid_model_dir()

        return self.result

    # ---------- TranscriptionResult / SpeechToTextEngine interface ----------

    def _test_transcription_result_shape(self) -> None:
        result = TranscriptionResult(
            success=True, text="system version", confidence=0.9, language="en", error=None
        )
        self.assert_true(result.success)
        self.assert_equal(result.text, "system version")
        self.assert_equal(result.confidence, 0.9)
        self.assert_equal(result.language, "en")
        self.assert_equal(result.error, None)

    def _test_vosk_engine_rejects_empty_languages_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = _config_with({"voice": {"languages": [], "model_dir": tmp_dir}})
            raised = False
            try:
                VoskSpeechToTextEngine(config=config)
            except SpeechToTextEngineError:
                raised = True
            self.assert_true(raised, "Expected SpeechToTextEngineError for empty 'voice.languages'")

    def _test_vosk_engine_rejects_missing_model_dir(self) -> None:
        config = _config_with(
            {"voice": {"languages": ["en"], "model_dir": "/nonexistent/EP046/model/dir"}}
        )
        raised = False
        try:
            VoskSpeechToTextEngine(config=config)
        except SpeechToTextEngineError:
            raised = True
        self.assert_true(raised, "Expected SpeechToTextEngineError for missing 'voice.model_dir'")

    def _test_vosk_engine_constructs_with_existing_empty_model_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = _config_with(
                {"voice": {"languages": ["ru", "uz", "en"], "default_language": "en", "model_dir": tmp_dir}}
            )
            engine = VoskSpeechToTextEngine(config=config)
            self.assert_equal(engine.supported_languages, ["ru", "uz", "en"])
            self.assert_equal(engine.default_language, "en")
            self.assert_false(engine.model_available("en"), "No language subdirectory exists yet")

    def _test_vosk_engine_transcribe_missing_language_model_returns_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = _config_with({"voice": {"languages": ["en"], "model_dir": tmp_dir}})
            engine = VoskSpeechToTextEngine(config=config)
            result = engine.transcribe_audio(pcm_data=b"\x00\x00" * 100, sample_rate=16000, language="en")
            self.assert_false(result.success)
            self.assert_true("No Vosk model found" in (result.error or ""))

    def _test_vosk_engine_transcribe_empty_audio_returns_no_speech_detected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = _config_with({"voice": {"languages": ["en"], "model_dir": tmp_dir}})
            engine = VoskSpeechToTextEngine(config=config)
            result = engine.transcribe_audio(pcm_data=b"", sample_rate=16000, language="en")
            self.assert_false(result.success)
            self.assert_equal(result.error, "no speech detected")

    def _test_vosk_engine_transcribe_unsupported_language_returns_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = _config_with({"voice": {"languages": ["en"], "model_dir": tmp_dir}})
            engine = VoskSpeechToTextEngine(config=config)
            result = engine.transcribe_audio(pcm_data=b"\x00\x00" * 100, sample_rate=16000, language="fr")
            self.assert_false(result.success)
            self.assert_true("unsupported language" in (result.error or ""))

    def _test_normalize_confidence_averages_word_confidences(self) -> None:
        confidence = VoskSpeechToTextEngine._normalize_confidence(
            {"result": [{"conf": 0.8, "word": "a"}, {"conf": 0.6, "word": "b"}]}
        )
        self.assert_not_none(confidence)
        self.assert_true(abs(confidence - 0.7) < 1e-9, f"Expected 0.7, got {confidence}")

    def _test_normalize_confidence_returns_none_when_no_words(self) -> None:
        self.assert_equal(VoskSpeechToTextEngine._normalize_confidence({}), None)
        self.assert_equal(VoskSpeechToTextEngine._normalize_confidence({"result": []}), None)

    def _test_real_transcription_with_loaded_model_not_available_in_this_environment(self) -> None:
        # No Vosk model files exist in this environment (owner Decision 10:
        # manual setup only). This is the one scenario EP046_DESIGN.md
        # Section 11 itself allows to be skipped rather than failed.
        self.skip()

    # ---------- AudioCapture ----------

    def _test_audio_capture_constructs_with_real_sounddevice(self) -> None:
        config = _config_with({"voice": {"sample_rate": 16000, "listen_duration_seconds": 1}})
        capture = AudioCapture(config=config)
        self.assert_equal(capture.sample_rate, 16000)

    def _test_audio_capture_reports_no_device_gracefully(self) -> None:
        # Environment-independent: this suite makes no assumption
        # about whether a microphone is physically present. Real
        # hardware verification (Windows/Realtek microphone) confirmed
        # a genuine input device makes capture() succeed
        # (result.success=True, result.error=None, non-empty
        # result.pcm_data); a device-less sandbox makes it fail
        # gracefully instead (result.success=False, result.error is
        # not None, result.pcm_data empty). Both are the same
        # underlying contract (EP046_DESIGN.md Section 5.4: never
        # raise) -- this test asserts whichever real outcome this
        # environment's real sounddevice/PortAudio call actually
        # produces, rather than assuming one. Mirrors the identical,
        # already-applied fix for EP-048's
        # `_test_streaming_audio_capture_reports_no_device_gracefully`.
        config = _config_with(
            {"voice": {"sample_rate": 16000, "listen_duration_seconds": 0.1, "device": None}}
        )
        capture = AudioCapture(config=config)
        result = capture.capture()

        if result.success:
            # A real input device is available in this environment.
            self.assert_true(result.success)
            self.assert_equal(result.error, None)
            self.assert_true(len(result.pcm_data) > 0, "Successful capture must return non-empty PCM data")
        else:
            # No input device is available in this environment.
            self.assert_false(result.success)
            self.assert_not_none(result.error)
            self.assert_equal(result.pcm_data, b"")

    # ---------- VoiceModule ----------

    def _test_voice_module_name_is_voice(self) -> None:
        module = self._build_voice_module()
        self.assert_equal(module.name, "voice")

    def _test_voice_module_unknown_action_returns_failure(self) -> None:
        module = self._build_voice_module()
        result = module.execute("dance", [])
        self.assert_false(result.success)
        self.assert_true("Unknown command" in result.message)

    def _test_voice_module_help_lists_commands(self) -> None:
        module = self._build_voice_module()
        result = module.execute("help", [])
        self.assert_true(result.success)
        self.assert_true("voice listen" in result.message)
        self.assert_true("voice transcribe" in result.message)
        self.assert_true("voice status" in result.message)

    def _test_voice_module_listen_dispatches_through_command_router(self) -> None:
        router = CommandRouter()
        echo = _RecordingModule("echo")
        router.register(echo)

        engine = _FakeSpeechToTextEngine(
            canned_result=TranscriptionResult(
                success=True, text="echo say hello", confidence=0.95, language="en"
            ),
            languages=["en"],
        )
        audio_capture = _FakeAudioCapture(
            canned_result=AudioCaptureResult(success=True, pcm_data=b"\x00\x00" * 100, sample_rate=16000)
        )
        module = VoiceModule(
            config=_config_with({}), command_router=router, engine=engine, audio_capture=audio_capture
        )

        result = module.execute("listen", [])
        self.assert_true(result.success)
        self.assert_equal(echo.call_count, 1)
        self.assert_true("hello" in result.message)

    def _test_voice_module_listen_matches_direct_dispatch(self) -> None:
        router = CommandRouter()
        router.register(_RecordingModule("echo"))

        direct = router.dispatch("echo say hello world")

        engine = _FakeSpeechToTextEngine(
            canned_result=TranscriptionResult(
                success=True, text="echo say hello world", confidence=0.95, language="en"
            ),
            languages=["en"],
        )
        audio_capture = _FakeAudioCapture(
            canned_result=AudioCaptureResult(success=True, pcm_data=b"\x00\x00" * 100, sample_rate=16000)
        )
        module = VoiceModule(
            config=_config_with({}), command_router=router, engine=engine, audio_capture=audio_capture
        )
        via_voice = module.execute("listen", [])

        # No divergent parsing: the dispatched CommandResult's own
        # success/should_exit must be identical to typing the same
        # text directly into the shell (EP046_DESIGN.md Section 14 #4).
        self.assert_equal(via_voice.success, direct.success)
        self.assert_equal(via_voice.should_exit, direct.should_exit)
        self.assert_true(direct.message in via_voice.message)

    def _test_voice_module_listen_blocks_low_confidence_and_does_not_dispatch(self) -> None:
        router = CommandRouter()
        echo = _RecordingModule("echo")
        router.register(echo)

        engine = _FakeSpeechToTextEngine(
            canned_result=TranscriptionResult(
                success=True, text="echo say hello", confidence=0.10, language="en"
            ),
            languages=["en"],
            min_confidence_value=0.5,
        )
        audio_capture = _FakeAudioCapture(
            canned_result=AudioCaptureResult(success=True, pcm_data=b"\x00\x00" * 100, sample_rate=16000)
        )
        module = VoiceModule(
            config=_config_with({}), command_router=router, engine=engine, audio_capture=audio_capture
        )

        result = module.execute("listen", [])
        self.assert_false(result.success)
        self.assert_equal(echo.call_count, 0, "Low-confidence transcript must never reach CommandRouter.dispatch()")
        self.assert_true("not executed" in result.message)

    def _test_voice_module_listen_microphone_failure_returns_failure(self) -> None:
        engine = _FakeSpeechToTextEngine(
            canned_result=TranscriptionResult(success=True, text="x", confidence=0.9, language="en"),
            languages=["en"],
        )
        audio_capture = _FakeAudioCapture(
            canned_result=AudioCaptureResult(
                success=False, pcm_data=b"", sample_rate=16000, error="microphone unavailable: no device"
            )
        )
        module = VoiceModule(
            config=_config_with({}),
            command_router=CommandRouter(),
            engine=engine,
            audio_capture=audio_capture,
        )
        result = module.execute("listen", [])
        self.assert_false(result.success)
        self.assert_true("Microphone error" in result.message)

    def _test_voice_module_listen_recognition_failure_returns_failure(self) -> None:
        engine = _FakeSpeechToTextEngine(
            canned_result=TranscriptionResult(
                success=False, text="", confidence=None, language="en", error="no speech detected"
            ),
            languages=["en"],
        )
        audio_capture = _FakeAudioCapture(
            canned_result=AudioCaptureResult(success=True, pcm_data=b"\x00\x00" * 100, sample_rate=16000)
        )
        module = VoiceModule(
            config=_config_with({}),
            command_router=CommandRouter(),
            engine=engine,
            audio_capture=audio_capture,
        )
        result = module.execute("listen", [])
        self.assert_false(result.success)
        self.assert_true("Recognition failed" in result.message)

    def _test_voice_module_transcribe_never_dispatches(self) -> None:
        router = CommandRouter()
        echo = _RecordingModule("echo")
        router.register(echo)

        engine = _FakeSpeechToTextEngine(
            canned_result=TranscriptionResult(
                success=True, text="echo say hello", confidence=0.95, language="en"
            ),
            languages=["en"],
        )
        audio_capture = _FakeAudioCapture(
            canned_result=AudioCaptureResult(success=True, pcm_data=b"\x00\x00" * 100, sample_rate=16000)
        )
        module = VoiceModule(
            config=_config_with({}), command_router=router, engine=engine, audio_capture=audio_capture
        )

        result = module.execute("transcribe", [])
        self.assert_true(result.success)
        self.assert_equal(echo.call_count, 0, "'voice transcribe' must never dispatch")
        self.assert_true("hello" in result.message)
        self.assert_true("Confidence" in result.message)

    def _test_voice_module_status_reports_languages_and_models(self) -> None:
        module = self._build_voice_module(languages=["ru", "uz", "en"])
        result = module.execute("status", [])
        self.assert_true(result.success)
        self.assert_true("ru" in result.message)
        self.assert_true("uz" in result.message)
        self.assert_true("en" in result.message)

    def _build_voice_module(self, languages: list[str] | None = None) -> VoiceModule:
        engine = _FakeSpeechToTextEngine(
            canned_result=TranscriptionResult(success=True, text="", confidence=None, language="en"),
            languages=languages or ["en"],
        )
        audio_capture = _FakeAudioCapture(
            canned_result=AudioCaptureResult(success=True, pcm_data=b"", sample_rate=16000)
        )
        return VoiceModule(
            config=_config_with({}),
            command_router=CommandRouter(),
            engine=engine,
            audio_capture=audio_capture,
        )

    # ---------- Bootstrap wiring ----------

    def _test_bootstrap_skips_voice_when_config_absent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            directory = Path(tmp_dir)
            _write_voice_bootstrap_config(directory, voice_section="")
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                try:
                    bootstrap.initialize()
                    self.assert_true(bootstrap.voice_engine is None)
                    result = bootstrap._command_router.dispatch("voice status")
                    self.assert_false(result.success, "'voice' must not be a registered namespace")
                finally:
                    bootstrap.shutdown()

    def _test_bootstrap_starts_voice_when_enabled_and_model_dir_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            directory = Path(tmp_dir)
            model_dir = directory / "data" / "models" / "voice"
            model_dir.mkdir(parents=True, exist_ok=True)
            voice_section = (
                "voice:\n"
                "  enabled: true\n"
                '  languages: ["en"]\n'
                '  default_language: "en"\n'
                f'  model_dir: "{model_dir.as_posix()}"\n'
            )
            _write_voice_bootstrap_config(directory, voice_section=voice_section)
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                try:
                    bootstrap.initialize()
                    self.assert_true(bootstrap.voice_engine is not None)
                    result = bootstrap._command_router.dispatch("voice status")
                    self.assert_true(result.success)
                finally:
                    bootstrap.shutdown()

    def _test_bootstrap_disables_voice_on_invalid_model_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            directory = Path(tmp_dir)
            voice_section = (
                "voice:\n"
                "  enabled: true\n"
                '  languages: ["en"]\n'
                '  default_language: "en"\n'
                '  model_dir: "does/not/exist"\n'
            )
            _write_voice_bootstrap_config(directory, voice_section=voice_section)
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                try:
                    bootstrap.initialize()
                    self.assert_true(bootstrap.voice_engine is None)
                    # Bootstrap.initialize() must not crash, and every
                    # other subsystem (e.g. "system") must be unaffected.
                    result = bootstrap._command_router.dispatch("system version")
                    self.assert_true(result.success)
                finally:
                    bootstrap.shutdown()


def _config_with(overrides: dict) -> Config:
    """Build a Config whose in-memory data is exactly `overrides`."""
    config = Config(config_path=Path("unused.yaml"))
    config._data = overrides
    return config
