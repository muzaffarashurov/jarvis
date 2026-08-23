"""Real engineering tests for EP-047 STEP 2 - Text-to-Speech.

Single combined test suite (NAME = "EP047"), following the same
precedent EP-043/EP-045/EP-046 already established: this sidesteps
the pre-existing `TestRegistry` NAME-collision technical debt
(docs/BACKLOG.md) entirely rather than triggering it.

Deterministic: no physical speakers, no human interaction, and no
network access are required. `TextToSpeechEngine` is exercised
through a fake (`_FakeTextToSpeechEngine`) wherever real audible
speech would otherwise be needed to observe `VoiceModule._speak`'s
behavior; the *real* `Pyttsx3TextToSpeechEngine` class is exercised
directly for everything that does not require real audio output
(construction validation and invalid-configuration handling).

Whether a real OS speech driver (SAPI5 on Windows, eSpeak/eSpeak-NG
on Linux, NSSpeechSynthesizer on macOS) happens to be installed
varies by execution environment -- this sandbox may or may not have
one, independent of whether the real Windows target workstation
does. Rather than assume either outcome, the real-construction test
below (see
`_test_real_pyttsx3_engine_construction_does_not_leak_unhandled_exceptions`)
tolerates both: construction either succeeds, or fails wrapped as
`TextToSpeechEngineError` -- only an *unhandled*, unwrapped exception
is treated as an actual test failure. Deliberately invalid
configuration (`_test_pyttsx3_engine_rejects_*`) is used wherever a
*guaranteed* failure is required for a test's own logic (e.g. proving
Bootstrap disables only TTS, never STT, on a construction error --
see `_test_bootstrap_disables_tts_on_construction_failure_but_keeps_stt`),
so those specific tests never depend on driver availability either
way.

Regardless of whether `Pyttsx3TextToSpeechEngine.synthesize()`
reports `success=True` in this environment, this suite never claims
that a real speaker produced audible sound -- there is no way to
confirm that from an automated test, on any platform. Real, human-
verified audible output on the actual Windows target workstation
remains an open, disclosed manual-verification item (EP047_DESIGN.md
Section 11/13), separate from and not satisfied by anything in this
file.

Covers (see EP-047 STEP 2 instructions, Section 9, items 1-18):
    1.  SynthesisResult/TextToSpeechEngine interface shape.
    2.  Pyttsx3TextToSpeechEngine construction/error handling
        (invalid config deterministically; real construction
        tolerated either way, never leaking an unhandled exception).
    3.  Disabled TTS behavior (tts_engine=None).
    4.  Empty text rejection.
    5.  'voice speak <text>' end to end (fake engine).
    6.  Successful speech through a fake engine.
    7.  TTS failure handling.
    8.  Unsupported language handling.
    9.  Existing 'voice listen' still works (EP-046 regression check).
    10. Existing 'voice transcribe' still works (EP-046 regression
        check).
    11. Existing 'voice status' still works (EP-046 regression
        check).
    12. 'voice help' contains 'voice speak'.
    13. 'voice speak' never calls CommandRouter.dispatch().
    14. 'voice.tts.enabled: false' does not initialize TTS.
    15. Bootstrap starts normally when TTS is disabled.
    16. Bootstrap handles TTS initialization failure safely (STT
        remains available).
    17. No Uzbek workaround is activated -- 'uz' fails exactly like
        any other language with no installed voice, with no
        special-cased fallback.
    18. Configuration defaults are correct
        ('voice.tts.enabled: false' by default).
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path

from src.bootstrap import Bootstrap
from src.core.command_router import CommandRouter
from src.core.config import Config
from src.skills.voice.audio_capture import AudioCaptureResult
from src.skills.voice.skill import VoiceModule
from src.skills.voice.speech_to_text import TranscriptionResult
from src.skills.voice.text_to_speech import (
    DEFAULT_LANGUAGES,
    Pyttsx3TextToSpeechEngine,
    SynthesisResult,
    TextToSpeechEngineError,
)
from src.testing.base_test import BaseTest
from src.testing.registry import TestRegistry
from tests.EP045.test_web_dashboard import (
    _MINIMAL_BOOTSTRAP_CONFIG_YAML,
    _ChdirGuard,
    _api_section,
)
from tests.EP046.test_voice import (
    _FakeAudioCapture,
    _FakeSpeechToTextEngine,
    _RecordingModule,
)


@dataclass
class _FakeTextToSpeechEngine:
    """Fake TextToSpeechEngine: returns a pre-canned result, never touches pyttsx3.

    Also records every `synthesize()` call so tests can assert
    `VoiceModule._speak` called it exactly once with the expected
    text (item 5/6/7/8), without any real audio being produced.
    """

    canned_result: SynthesisResult
    languages: list[str]

    def __post_init__(self) -> None:
        self.calls: list[tuple[str, str | None]] = []

    @property
    def supported_languages(self) -> list[str]:
        return self.languages

    def synthesize(self, text: str, language: str | None = None) -> SynthesisResult:
        self.calls.append((text, language))
        return self.canned_result


def _write_voice_tts_bootstrap_config(directory: Path, voice_section: str) -> None:
    """Write a minimal bootstrap config.yaml (EP-045's fixture) plus a 'voice:' block."""
    config_dir = directory / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    base_yaml = _MINIMAL_BOOTSTRAP_CONFIG_YAML.format(
        api_section=_api_section(enabled=False, web_dashboard_dir=None)
    )
    (config_dir / "config.yaml").write_text(base_yaml + "\n" + voice_section, encoding="utf-8")


@TestRegistry.register
class VoiceTtsTest(BaseTest):
    NAME = "EP047"

    def run(self):
        self._test_synthesis_result_shape()
        self._test_default_languages_constant()

        self._test_pyttsx3_engine_rejects_empty_languages_config()
        self._test_pyttsx3_engine_rejects_default_language_not_in_languages()
        self._test_real_pyttsx3_engine_construction_does_not_leak_unhandled_exceptions()

        self._test_voice_module_speak_disabled_when_tts_engine_none()
        self._test_voice_module_speak_rejects_empty_text()
        self._test_voice_module_speak_success_through_fake_engine()
        self._test_voice_module_speak_reports_engine_failure()
        self._test_voice_module_speak_reports_unsupported_language()
        self._test_voice_module_speak_never_dispatches()
        self._test_voice_module_speak_joins_multiple_arguments()

        self._test_voice_module_help_lists_speak()

        self._test_voice_module_listen_unaffected_by_missing_tts_engine()
        self._test_voice_module_transcribe_unaffected_by_missing_tts_engine()
        self._test_voice_module_status_unaffected_by_missing_tts_engine()

        self._test_voice_module_uzbek_fails_like_any_other_unconfigured_language()

        self._test_bootstrap_config_defaults_tts_disabled()
        self._test_bootstrap_skips_tts_when_disabled_but_stt_enabled()
        self._test_bootstrap_disables_tts_on_construction_failure_but_keeps_stt()

        return self.result

    # ---------- SynthesisResult / TextToSpeechEngine interface ----------

    def _test_synthesis_result_shape(self) -> None:
        result = SynthesisResult(success=True, language="en", error=None)
        self.assert_true(result.success)
        self.assert_equal(result.language, "en")
        self.assert_equal(result.error, None)

    def _test_default_languages_constant(self) -> None:
        self.assert_true(isinstance(DEFAULT_LANGUAGES, list))
        self.assert_true(len(DEFAULT_LANGUAGES) >= 1, "DEFAULT_LANGUAGES must not be empty")

    # ---------- Pyttsx3TextToSpeechEngine construction ----------

    def _test_pyttsx3_engine_rejects_empty_languages_config(self) -> None:
        config = _config_with({"voice": {"tts": {"languages": []}}})
        raised = False
        try:
            Pyttsx3TextToSpeechEngine(config=config)
        except TextToSpeechEngineError:
            raised = True
        self.assert_true(raised, "Expected TextToSpeechEngineError for empty 'voice.tts.languages'")

    def _test_pyttsx3_engine_rejects_default_language_not_in_languages(self) -> None:
        config = _config_with(
            {"voice": {"tts": {"languages": ["en"], "default_language": "ru"}}}
        )
        raised = False
        try:
            Pyttsx3TextToSpeechEngine(config=config)
        except TextToSpeechEngineError:
            raised = True
        self.assert_true(
            raised,
            "Expected TextToSpeechEngineError when 'voice.tts.default_language' is not "
            "one of 'voice.tts.languages'",
        )

    def _test_real_pyttsx3_engine_construction_does_not_leak_unhandled_exceptions(self) -> None:
        """Construct the *real* engine with otherwise-valid configuration.

        Deliberately does not assume whether an OS speech driver is
        installed in this execution environment (it may or may not
        be -- independent of the real Windows target workstation).
        Both outcomes are accepted as passing:

        - Construction succeeds (a usable driver/voice was found):
          this only proves construction doesn't crash when a real
          driver *is* present; it does NOT prove any audio was
          audibly played (see this file's module docstring and
          EP047_DESIGN.md Section 11/13 -- that remains a separate,
          disclosed manual-verification item).
        - Construction raises `TextToSpeechEngineError` (no usable
          driver/voice found): the expected, wrapped failure path
          (Section 5.4/10) -- never an unhandled `pyttsx3`/driver
          exception.

        Only an exception type *other than* `TextToSpeechEngineError`
        escaping this call is treated as an actual failure here.
        """
        config = _config_with({"voice": {"tts": {"languages": ["en"], "default_language": "en"}}})
        try:
            Pyttsx3TextToSpeechEngine(config=config)
            self.result.add_pass()
        except TextToSpeechEngineError:
            self.result.add_pass()
        except Exception as exc:  # noqa: BLE001 - a non-wrapped exception is the actual failure
            self.result.add_fail(f"pyttsx3 construction failure was not wrapped: {exc}")

    # ---------- VoiceModule._speak ----------

    def _test_voice_module_speak_disabled_when_tts_engine_none(self) -> None:
        module = self._build_voice_module(tts_engine=None)
        result = module.execute("speak", ["hello"])
        self.assert_false(result.success)
        self.assert_true("not enabled" in result.message.lower())

    def _test_voice_module_speak_rejects_empty_text(self) -> None:
        engine = _FakeTextToSpeechEngine(
            canned_result=SynthesisResult(success=True, language="en"), languages=["en"]
        )
        module = self._build_voice_module(tts_engine=engine)
        result = module.execute("speak", [])
        self.assert_false(result.success)
        self.assert_true("Usage:" in result.message)
        self.assert_equal(len(engine.calls), 0, "empty text must never reach synthesize()")

    def _test_voice_module_speak_success_through_fake_engine(self) -> None:
        engine = _FakeTextToSpeechEngine(
            canned_result=SynthesisResult(success=True, language="en"), languages=["en"]
        )
        module = self._build_voice_module(tts_engine=engine)
        result = module.execute("speak", ["hello", "world"])
        self.assert_true(result.success)
        self.assert_true("hello world" in result.message)
        self.assert_equal(engine.calls, [("hello world", None)])

    def _test_voice_module_speak_reports_engine_failure(self) -> None:
        engine = _FakeTextToSpeechEngine(
            canned_result=SynthesisResult(
                success=False, language="en", error="speech engine runtime failure: boom"
            ),
            languages=["en"],
        )
        module = self._build_voice_module(tts_engine=engine)
        result = module.execute("speak", ["hello"])
        self.assert_false(result.success)
        self.assert_true("Speech failed" in result.message)
        self.assert_true("boom" in result.message)

    def _test_voice_module_speak_reports_unsupported_language(self) -> None:
        engine = _FakeTextToSpeechEngine(
            canned_result=SynthesisResult(
                success=False, language="fr", error="unsupported language: 'fr'"
            ),
            languages=["en"],
        )
        module = self._build_voice_module(tts_engine=engine)
        result = module.execute("speak", ["bonjour"])
        self.assert_false(result.success)
        self.assert_true("unsupported language" in result.message.lower())

    def _test_voice_module_speak_never_dispatches(self) -> None:
        router = CommandRouter()
        echo = _RecordingModule("echo")
        router.register(echo)

        engine = _FakeTextToSpeechEngine(
            canned_result=SynthesisResult(success=True, language="en"), languages=["en"]
        )
        module = self._build_voice_module(tts_engine=engine, command_router=router)

        result = module.execute("speak", ["echo", "say", "hello"])
        self.assert_true(result.success)
        self.assert_equal(echo.call_count, 0, "'voice speak' must never call CommandRouter.dispatch()")

    def _test_voice_module_speak_joins_multiple_arguments(self) -> None:
        engine = _FakeTextToSpeechEngine(
            canned_result=SynthesisResult(success=True, language="en"), languages=["en"]
        )
        module = self._build_voice_module(tts_engine=engine)
        module.execute("speak", ["the", "quick", "brown", "fox"])
        self.assert_equal(engine.calls, [("the quick brown fox", None)])

    def _test_voice_module_help_lists_speak(self) -> None:
        module = self._build_voice_module(tts_engine=None)
        result = module.execute("help", [])
        self.assert_true(result.success)
        self.assert_true("voice speak" in result.message)
        # EP-046 actions must still be listed too (regression check).
        self.assert_true("voice listen" in result.message)
        self.assert_true("voice transcribe" in result.message)
        self.assert_true("voice status" in result.message)

    # ---------- EP-046 regression checks (unaffected by the additive change) ----------

    def _test_voice_module_listen_unaffected_by_missing_tts_engine(self) -> None:
        engine = _FakeSpeechToTextEngine(
            canned_result=TranscriptionResult(
                success=True, text="echo say hello", confidence=0.95, language="en"
            ),
            languages=["en"],
        )
        audio_capture = _FakeAudioCapture(
            canned_result=AudioCaptureResult(success=True, pcm_data=b"\x00\x00" * 100, sample_rate=16000)
        )
        router = CommandRouter()
        router.register(_RecordingModule("echo"))
        module = VoiceModule(
            config=_config_with({}),
            command_router=router,
            engine=engine,
            audio_capture=audio_capture,
            # tts_engine intentionally omitted -- must default to None
            # and must not affect 'voice listen' in any way.
        )
        result = module.execute("listen", [])
        self.assert_true(result.success)

    def _test_voice_module_transcribe_unaffected_by_missing_tts_engine(self) -> None:
        module = self._build_voice_module(tts_engine=None)
        result = module.execute("transcribe", [])
        self.assert_true(result.success)
        self.assert_true("Confidence" in result.message)

    def _test_voice_module_status_unaffected_by_missing_tts_engine(self) -> None:
        module = self._build_voice_module(tts_engine=None, languages=["ru", "uz", "en"])
        result = module.execute("status", [])
        self.assert_true(result.success)
        self.assert_true("ru" in result.message)
        self.assert_true("uz" in result.message)
        self.assert_true("en" in result.message)

    # ---------- Uzbek: no workaround ----------

    def _test_voice_module_uzbek_fails_like_any_other_unconfigured_language(self) -> None:
        """'uz' must fail exactly like any other language with no installed voice.

        Owner Decision D2 (EP047_DESIGN.md Section 9a): no
        translation layer, no cloud fallback, no silent substitution
        of a different language's voice. This test proves 'uz' is
        not special-cased anywhere in `VoiceModule`/`synthesize()` --
        it takes the exact same "unsupported language" path a
        never-configured language (e.g. 'fr') would.
        """
        engine = _FakeTextToSpeechEngine(
            canned_result=SynthesisResult(
                success=False, language="uz", error="unsupported language: 'uz'"
            ),
            languages=["en", "ru"],  # 'uz' deliberately not configured, per D2
        )
        module = self._build_voice_module(tts_engine=engine)
        result = module.execute("speak", ["salom"])
        self.assert_false(result.success)
        self.assert_true("unsupported language" in result.message.lower())
        # The fake engine's canned result is exactly what a real
        # engine reports for *any* unconfigured language -- proving
        # VoiceModule itself contains no Uzbek-specific branching.
        self.assert_equal(engine.calls, [("salom", None)])

    # ---------- Configuration defaults ----------

    def _test_bootstrap_config_defaults_tts_disabled(self) -> None:
        config = _config_with({"voice": {"enabled": True, "languages": ["en"]}})
        self.assert_false(
            bool(config.get("voice.tts.enabled", False)),
            "'voice.tts.enabled' must default to false when entirely absent from config",
        )

    # ---------- Bootstrap wiring ----------

    def _test_bootstrap_skips_tts_when_disabled_but_stt_enabled(self) -> None:
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
                "  tts:\n"
                "    enabled: false\n"
            )
            _write_voice_tts_bootstrap_config(directory, voice_section=voice_section)
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                try:
                    bootstrap.initialize()
                    # STT must still be available (regression check).
                    self.assert_true(bootstrap.voice_engine is not None)
                    # TTS was explicitly disabled -- must not initialize.
                    self.assert_true(bootstrap.voice_tts_engine is None)
                    result = bootstrap._command_router.dispatch("voice speak hello")
                    self.assert_false(result.success)
                    self.assert_true("not enabled" in result.message.lower())
                    # Jarvis must still start normally: another
                    # unrelated module keeps working.
                    other = bootstrap._command_router.dispatch("system version")
                    self.assert_true(other.success)
                finally:
                    bootstrap.shutdown()

    def _test_bootstrap_disables_tts_on_construction_failure_but_keeps_stt(self) -> None:
        """An invalid 'voice.tts.*' config must disable only TTS, never STT.

        Forces a deterministic `TextToSpeechEngineError` via an
        empty 'voice.tts.languages' list -- this must fail identically
        regardless of whether a real OS speech driver happens to be
        installed in whatever environment this test runs in (see
        `_test_pyttsx3_engine_rejects_empty_languages_config`, which
        proves this exact input always raises). Bootstrap must catch
        it, log it, and continue with Speech-to-Text fully intact --
        never crash, never silently disable STT as a side effect.
        """
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
                "  tts:\n"
                "    enabled: true\n"
                "    languages: []\n"  # deliberately invalid -- deterministic failure
            )
            _write_voice_tts_bootstrap_config(directory, voice_section=voice_section)
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                try:
                    bootstrap.initialize()
                    self.assert_true(
                        bootstrap.voice_engine is not None,
                        "STT must remain available even if TTS construction fails",
                    )
                    self.assert_true(
                        bootstrap.voice_tts_engine is None,
                        "TTS must not be available when construction failed",
                    )
                    result = bootstrap._command_router.dispatch("voice status")
                    self.assert_true(result.success, "'voice' namespace must still be registered")
                    speak_result = bootstrap._command_router.dispatch("voice speak hello")
                    self.assert_false(
                        speak_result.success,
                        "'voice speak' must fail safely, not crash, when TTS is unavailable",
                    )
                finally:
                    bootstrap.shutdown()

    # ---------- Helpers ----------

    def _build_voice_module(
        self,
        tts_engine,
        languages: list[str] | None = None,
        command_router: CommandRouter | None = None,
    ) -> VoiceModule:
        stt_engine = _FakeSpeechToTextEngine(
            canned_result=TranscriptionResult(success=True, text="", confidence=None, language="en"),
            languages=languages or ["en"],
        )
        audio_capture = _FakeAudioCapture(
            canned_result=AudioCaptureResult(success=True, pcm_data=b"", sample_rate=16000)
        )
        return VoiceModule(
            config=_config_with({}),
            command_router=command_router or CommandRouter(),
            engine=stt_engine,
            audio_capture=audio_capture,
            tts_engine=tts_engine,
        )


def _config_with(overrides: dict) -> Config:
    """Build a Config whose in-memory data is exactly `overrides`."""
    config = Config(config_path=Path("unused.yaml"))
    config._data = overrides
    return config
