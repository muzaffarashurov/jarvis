"""EP-047 Text-to-Speech engine.

Converts text into audible speech, entirely offline, using `pyttsx3`
(see `docs/architecture/designs/EP047_DESIGN.md`, Section 8/9a
Decision D1). This module owns exactly one responsibility: text in,
speech played out. It has no knowledge of `CommandRouter`, of Jarvis
commands, of the microphone (`audio_capture.py`), or of speech
recognition (`speech_to_text.py`) -- that separation mirrors
EP-046's own STT/capture split (Section 5.2/5.3 of both design
documents) and is a STEP 1 design requirement (EP047_DESIGN.md
Section 4/5.2), confirmed unchanged by the owner's STEP 1 approval
(Section 9a).

Supported languages are configured, not hard-coded (owner Decision
D2's own "must remain replaceable" requirement): `voice.tts.languages`
in `config/config.yaml` lists the languages `voice speak` may be
asked to use. Unlike EP-046's STT side (Vosk models, one per
language, manually installed), `pyttsx3` has no per-language model
files to install -- language support here is instead limited to
whichever OS-native voices (SAPI5 on Windows, per Section 3.7/7) are
already installed on the workstation. This engine never falls back
to a different language's voice when the requested one is missing --
doing so was explicitly rejected by Owner Decision D2 ("The Uzbek
limitation must be explicit rather than silently selecting another
language") and is treated as a general principle for every
language, not only Uzbek: a missing voice is always reported as a
failure, never silently substituted.

Per Owner Decision D2, Uzbek text-to-speech is out of scope for
EP-047. No workaround (translation, cloud TTS, a second/hidden
engine, or a phonetic approximation) is implemented here. If "uz" is
ever requested, `synthesize()` reports a normal "no installed voice
for this language" failure -- the exact same path an operator would
hit for any other language with no matching installed voice. Nothing
in this file treats "uz" as a special case; the limitation is a
consequence of no Uzbek SAPI5 voice existing to be found; it is
documented here and in `config/config.yaml`, not encoded as a special
rule that would need separate maintenance.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from loguru import logger

from src.core.config import Config

DEFAULT_LANGUAGES: list[str] = ["en"]
DEFAULT_DEFAULT_LANGUAGE: str = "en"


class TextToSpeechEngineError(Exception):
    """Raised when the TTS engine cannot be constructed.

    Reserved for construction-time failures only (the `pyttsx3`
    package not importable, no OS speech driver available, invalid
    'voice.tts.*' configuration) -- never raised by `synthesize()`
    itself, which always returns a `SynthesisResult` instead (see
    EP047_DESIGN.md Section 5.4, mirroring EP-046's own
    `SpeechToTextEngineError`/`AudioCaptureError` idiom).
    """


@dataclass(frozen=True)
class SynthesisResult:
    """Outcome of a single text-to-speech synthesis attempt.

    Mirrors `TranscriptionResult`'s own shape (`speech_to_text.py`)
    and, through it, `CommandResult`'s (`src/core/command_router.py`)
    -- the project's established idiom for "this can fail in
    expected, non-exceptional ways": a caller checks `success`
    instead of catching an exception.

    Attributes:
        success: Whether `text` was spoken. False for empty text, an
            unsupported/unconfigured language, a language with no
            installed OS voice, or an engine runtime failure -- never
            raised as an exception.
        language: The language code actually used (or requested, on
            failure before a voice could be selected), if any.
        error: A short, human-readable failure reason. None on
            success.
    """

    success: bool
    language: str | None
    error: str | None = None


class TextToSpeechEngine(Protocol):
    """Interface every TTS engine implementation must satisfy.

    Only `Pyttsx3TextToSpeechEngine` implements this today (owner
    Decision D1). The interface exists so a future engine could be
    substituted -- per `voice.tts.engine` in configuration -- without
    any change to `VoiceModule` (`skill.py`) or `CommandRouter`. This
    is also the seam through which Uzbek support could be added later
    (Owner Decision D2's "must remain replaceable" requirement) by a
    future engine implementation, with no change to `VoiceModule`.
    """

    @property
    def supported_languages(self) -> list[str]:
        """Return the language codes this engine is configured for."""
        ...

    def synthesize(self, text: str, language: str | None = None) -> SynthesisResult:
        """Speak `text` aloud through the configured audio output device.

        Args:
            text: The text to speak.
            language: Language code to speak in. None uses the
                engine's configured default language.

        Returns:
            A SynthesisResult. Never raises for an expected failure
            (empty text, unsupported/unconfigured language, no
            installed voice for that language, engine runtime
            failure) -- those are reported via `success=False`.
        """
        ...


class Pyttsx3TextToSpeechEngine:
    """Offline text-to-speech via `pyttsx3` (owner Decision D1).

    On Windows, `pyttsx3` speaks through the native SAPI5 engine
    (EP047_DESIGN.md Section 3.7/7); this class has no SAPI5-specific
    code of its own -- it only talks to `pyttsx3`'s own
    cross-platform `Engine` API, exactly as `AudioCapture` only talks
    to `sounddevice`'s own API rather than a platform-specific one.

    Construction builds a language -> OS-voice-id map once, from
    whichever voices `pyttsx3` reports as installed, and reuses one
    `pyttsx3` engine instance for every `synthesize()` call (`pyttsx3`
    engines are not intended to be repeatedly re-initialized within
    one process). Playback is synchronous/blocking (`engine.say()` +
    `engine.runAndWait()`, owner Decision D5) -- the simplest option,
    matching `AudioCapture.capture()`'s own blocking
    `sounddevice.wait()` precedent.
    """

    def __init__(self, config: Config) -> None:
        """Initialize the TTS engine from `voice.tts.*` configuration.

        Args:
            config: The application Config.

        Raises:
            TextToSpeechEngineError: If the `pyttsx3` package is not
                importable, no usable OS speech driver/voice could be
                initialized, or 'voice.tts.*' configuration is
                invalid (e.g. an empty 'languages' list, or a
                'default_language' not present in 'languages').
        """
        try:
            import pyttsx3
        except ImportError as exc:
            raise TextToSpeechEngineError(
                "The 'pyttsx3' package is not usable (missing package, or its "
                "underlying OS speech driver dependency -- e.g. 'pywin32'/"
                "'comtypes' on Windows -- is not usable). Add/install it before "
                "enabling 'voice.tts.enabled' -- see requirements.txt."
            ) from exc

        languages = [
            str(language) for language in config.get("voice.tts.languages", DEFAULT_LANGUAGES) or []
        ]
        if not languages:
            raise TextToSpeechEngineError(
                "'voice.tts.languages' must list at least one language code."
            )

        default_language = str(config.get("voice.tts.default_language", languages[0]))
        if default_language not in languages:
            raise TextToSpeechEngineError(
                f"'voice.tts.default_language' ({default_language!r}) must be one "
                f"of 'voice.tts.languages' ({languages!r})."
            )

        rate = config.get("voice.tts.rate", None)
        volume = config.get("voice.tts.volume", None)

        try:
            engine = pyttsx3.init()
        except Exception as exc:  # noqa: BLE001 - driver/OS errors must never crash Bootstrap
            raise TextToSpeechEngineError(
                f"pyttsx3 could not initialize a text-to-speech engine ({exc}). "
                "This usually means no OS speech driver/voice is installed "
                "(SAPI5 on Windows, eSpeak on Linux, NSSpeechSynthesizer on "
                "macOS)."
            ) from exc

        if rate is not None:
            try:
                engine.setProperty("rate", rate)
            except Exception as exc:  # noqa: BLE001 - a bad config value must not crash Bootstrap
                logger.warning(f"Voice: could not apply 'voice.tts.rate' ({rate!r}): {exc}")

        if volume is not None:
            try:
                engine.setProperty("volume", volume)
            except Exception as exc:  # noqa: BLE001 - a bad config value must not crash Bootstrap
                logger.warning(f"Voice: could not apply 'voice.tts.volume' ({volume!r}): {exc}")

        self._engine = engine
        self._languages = languages
        self._default_language = default_language
        self._voice_id_by_language = self._discover_voices(engine)

    @property
    def supported_languages(self) -> list[str]:
        """Return the configured 'voice.tts.languages' language codes."""
        return list(self._languages)

    @property
    def default_language(self) -> str:
        """Return the configured 'voice.tts.default_language'."""
        return self._default_language

    def voice_available(self, language: str) -> bool:
        """Return whether an installed OS voice was found for `language`.

        Args:
            language: A language code from `supported_languages`.

        Returns:
            True if an installed voice matching `language` was found
            at construction time. Mirrors `VoskSpeechToTextEngine
            .model_available()`'s role for `voice status`
            (`skill.py`).
        """
        return language in self._voice_id_by_language

    def synthesize(self, text: str, language: str | None = None) -> SynthesisResult:
        """Speak `text` aloud. See `TextToSpeechEngine.synthesize`.

        Never raises: every expected failure (empty text, an
        unsupported/unconfigured language, no installed voice for
        that language, an engine runtime failure) is reported via
        `SynthesisResult(success=False, ...)`.
        """
        if not text or not text.strip():
            return SynthesisResult(success=False, language=language, error="no text to speak")

        target_language = language or self._default_language
        if target_language not in self._languages:
            return SynthesisResult(
                success=False,
                language=target_language,
                error=f"unsupported language: '{target_language}'",
            )

        voice_id = self._voice_id_by_language.get(target_language)
        if voice_id is None:
            # Deliberately never substitutes another language's voice
            # here (owner Decision D2) -- this is the exact path a
            # request for "uz" takes today, with no special-casing.
            return SynthesisResult(
                success=False,
                language=target_language,
                error=(
                    f"no installed text-to-speech voice available for language "
                    f"'{target_language}'"
                ),
            )

        try:
            self._engine.setProperty("voice", voice_id)
            self._engine.say(text)
            self._engine.runAndWait()
        except Exception as exc:  # noqa: BLE001 - engine/driver errors must never propagate
            logger.error(f"Voice: text-to-speech synthesis failed: {exc}")
            return SynthesisResult(
                success=False,
                language=target_language,
                error=f"speech engine runtime failure: {exc}",
            )

        return SynthesisResult(success=True, language=target_language, error=None)

    @staticmethod
    def _discover_voices(engine) -> dict[str, str]:
        """Build a best-effort {language_code: voice_id} map from installed voices.

        Never raises: an enumeration failure degrades to an empty
        map (every language then reports "no installed voice",
        Section 5.4's fail-safe idiom) rather than crashing
        construction.
        """
        voice_by_language: dict[str, str] = {}
        try:
            voices = engine.getProperty("voices") or []
        except Exception as exc:  # noqa: BLE001 - must never crash construction
            logger.warning(f"Voice: could not enumerate installed text-to-speech voices: {exc}")
            return voice_by_language

        for voice in voices:
            for tag in getattr(voice, "languages", None) or []:
                code = str(tag).split("-")[0].split("_")[0].strip().lower()
                if code and code not in voice_by_language:
                    voice_by_language[code] = voice.id
        return voice_by_language
