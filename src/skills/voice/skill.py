"""EP-046 voice module: the "voice" command namespace.

Implements `CommandModule` (`src/core/command_router.py`), following
`SystemModule`'s own reference-implementation pattern
(`src/skills/system/skill.py`). Bridges microphone/file audio to text
(via `speech_to_text.py`/`audio_capture.py`) and hands that text to
the *existing*, unmodified `CommandRouter.dispatch()` -- the same
entry point `InteractiveShell`, `TelegramRouter`, and `ApiRouter`
already dispatch through (EP046_DESIGN.md Section 3.1/9b). This
module never re-implements command parsing and never creates a
second dispatch mechanism.

Target architecture (EP046_DESIGN.md Section 5.1, confirmed
unchanged in Section 9b):

    Microphone -> AudioCapture -> SpeechToTextEngine -> text -> CommandRouter.dispatch()
"""

from __future__ import annotations

from typing import Callable

from loguru import logger

from src.core.command_router import CommandResult, CommandRouter
from src.core.config import Config
from src.skills.voice.audio_capture import AudioCapture
from src.skills.voice.speech_to_text import SpeechToTextEngine
from src.skills.voice.text_to_speech import TextToSpeechEngine

HELP_TEXT: str = (
    "Available voice commands\n\n"
    "voice listen [language]\n"
    "voice transcribe [language]\n"
    "voice status\n"
    "voice speak <text>"
)

ActionHandler = Callable[[list[str]], CommandResult]


class VoiceModule:
    """The "voice" command namespace (EP-046).

    Responsibilities:
        - `voice listen`: capture from the microphone, transcribe, and
          -- only if recognition confidence is sufficient (owner
          Decision 9) -- dispatch the transcript through the existing
          CommandRouter. This is the primary, user-facing operation
          (owner Decision 5).
        - `voice transcribe`: capture and transcribe only, never
          dispatch -- a safe way to inspect recognition quality.
        - `voice status`: report engine/model/microphone readiness.
        - `voice speak <text>` (EP-047, additive): speak `<text>`
          aloud via a `TextToSpeechEngine`. Never dispatches through
          `CommandRouter` (owner Decision D4, EP047_DESIGN.md Section
          9a) -- it only speaks its own literal argument text.

    Never contains recognition logic (that is `SpeechToTextEngine`'s
    job), microphone logic (that is `AudioCapture`'s job), or
    synthesis logic (that is `TextToSpeechEngine`'s job) -- this
    class only orchestrates them and talks to `CommandRouter`.
    """

    def __init__(
        self,
        config: Config,
        command_router: CommandRouter,
        engine: SpeechToTextEngine,
        audio_capture: AudioCapture,
        tts_engine: TextToSpeechEngine | None = None,
    ) -> None:
        """Initialize the VoiceModule.

        Args:
            config: The application Config, used only to read
                'voice.min_confidence' at dispatch time (already read
                once by `engine`, kept here too since `engine`
                exposes it as a read-only property -- see
                `_min_confidence`).
            command_router: The existing, shared CommandRouter every
                other interface (shell, Telegram, REST API) also
                dispatches through. `voice listen` hands its
                transcript to this exact instance -- never a second
                router.
            engine: The STT engine used to transcribe captured audio.
            audio_capture: The microphone capture component used by
                `voice listen`/`voice transcribe` when no explicit
                language-only argument path applies.
            tts_engine: The TTS engine used by `voice speak` (EP-047).
                Optional and defaults to None so every existing
                EP-046 call site (and every existing EP-046 test)
                keeps working unmodified -- `voice speak` reports a
                clear failure (never a crash) when this is None,
                exactly as when 'voice.tts.enabled' is false or
                text-to-speech engine construction failed (see
                `_speak`, EP047_DESIGN.md Section 5.3).
        """
        self._command_router = command_router
        self._engine = engine
        self._audio_capture = audio_capture
        self._tts_engine = tts_engine
        self._min_confidence = engine.min_confidence if hasattr(engine, "min_confidence") else (
            config.get("voice.min_confidence", None)
        )
        self._actions: dict[str, ActionHandler] = {
            "help": self._help,
            "listen": self._listen,
            "transcribe": self._transcribe,
            "status": self._status,
            "speak": self._speak,
        }

    @property
    def name(self) -> str:
        """Return this module's command namespace.

        Returns:
            The literal string "voice".
        """
        return "voice"

    def execute(self, action: str, arguments: list[str]) -> CommandResult:
        """Execute a "voice" action.

        Args:
            action: The requested action (e.g. "listen"). May be
                empty if the user entered only "voice".
            arguments: Additional arguments -- currently, an optional
                single language code (e.g. "ru", "uz", "en").

        Returns:
            A CommandResult describing the outcome.
        """
        handler = self._actions.get(action)
        if handler is None:
            command = f"{self.name} {action}".strip()
            logger.info(f"Unknown command: {command}")
            message = (
                f"Unknown command: {command}\n"
                'Type "voice help" for available commands.'
            )
            return CommandResult(success=False, message=message)

        return handler(arguments)

    def _help(self, arguments: list[str]) -> CommandResult:
        """Return the list of available voice commands."""
        return CommandResult(success=True, message=HELP_TEXT)

    def _listen(self, arguments: list[str]) -> CommandResult:
        """Capture from the microphone, transcribe, and (if confident) dispatch.

        Args:
            arguments: An optional single language code. Defaults to
                the engine's configured default language.

        Returns:
            A CommandResult. On successful, sufficiently confident
            recognition, this is the *dispatched command's own*
            CommandResult (prefixed with the recognized text) -- the
            same result typing that text into the shell would have
            produced. On low confidence or any failure, no dispatch
            occurs and `success` is False.
        """
        language = arguments[0] if arguments else None

        capture_result = self._audio_capture.capture()
        if not capture_result.success:
            return CommandResult(success=False, message=f"Microphone error: {capture_result.error}")

        transcription = self._engine.transcribe_audio(
            capture_result.pcm_data, capture_result.sample_rate, language
        )
        if not transcription.success:
            return CommandResult(success=False, message=f"Recognition failed: {transcription.error}")

        if self._below_confidence_threshold(transcription.confidence):
            message = (
                f'Heard: "{transcription.text}"\n\n'
                f"Confidence {transcription.confidence:.2f} is below the configured "
                f"threshold ({self._min_confidence:.2f}) -- not executed."
            )
            return CommandResult(success=False, message=message)

        dispatched = self._command_router.dispatch(transcription.text)
        prefix = f'Heard: "{transcription.text}"\n\n'
        return CommandResult(
            success=dispatched.success,
            message=prefix + dispatched.message,
            should_exit=dispatched.should_exit,
        )

    def _transcribe(self, arguments: list[str]) -> CommandResult:
        """Capture from the microphone and transcribe only -- never dispatch.

        Args:
            arguments: An optional single language code. Defaults to
                the engine's configured default language.

        Returns:
            A CommandResult reporting the recognized text and
            confidence (if any). Always `should_exit=False`; never
            calls `CommandRouter.dispatch()`.
        """
        language = arguments[0] if arguments else None

        capture_result = self._audio_capture.capture()
        if not capture_result.success:
            return CommandResult(success=False, message=f"Microphone error: {capture_result.error}")

        transcription = self._engine.transcribe_audio(
            capture_result.pcm_data, capture_result.sample_rate, language
        )
        if not transcription.success:
            return CommandResult(success=False, message=f"Recognition failed: {transcription.error}")

        confidence_text = (
            f"{transcription.confidence:.2f}" if transcription.confidence is not None else "n/a"
        )
        message = f'Heard: "{transcription.text}"\n\nConfidence: {confidence_text}'
        return CommandResult(success=True, message=message)

    def _status(self, arguments: list[str]) -> CommandResult:
        """Report engine/model/microphone readiness.

        Args:
            arguments: Unused.

        Returns:
            A CommandResult summarizing configured languages, model
            availability per language, and the confidence threshold.
        """
        languages = self._engine.supported_languages
        default_language = getattr(self._engine, "default_language", languages[0] if languages else "n/a")

        if hasattr(self._engine, "model_available"):
            model_lines = "\n".join(
                f"  {language}: {'available' if self._engine.model_available(language) else 'MISSING'}"
                for language in languages
            )
        else:
            model_lines = "  (model availability not reported by this engine)"

        threshold_text = (
            f"{self._min_confidence:.2f}" if self._min_confidence is not None else "not configured"
        )

        message = (
            "Voice Status\n\n"
            "Enabled : Yes\n\n"
            f"Languages : {', '.join(languages) if languages else '(none configured)'}\n\n"
            f"Default language : {default_language}\n\n"
            f"Models :\n{model_lines}\n\n"
            f"Minimum confidence : {threshold_text}"
        )
        return CommandResult(success=True, message=message)

    def _speak(self, arguments: list[str]) -> CommandResult:
        """Speak `arguments` (joined) aloud via the configured TTS engine.

        EP-047, owner Decisions D3/D4/D8 (EP047_DESIGN.md Section
        9a): additive to the existing "voice" namespace, explicit
        user-supplied text only, never automatically speaks a
        dispatched `CommandResult` and never itself calls
        `CommandRouter.dispatch()`.

        Args:
            arguments: The words to speak, joined with a single space
                -- e.g. `voice speak hello there` speaks "hello
                there". Matches the existing `" ".join(arguments)`
                convention already used elsewhere in the project for
                free-text command arguments (e.g.
                `src/skills/system/skill.py`).

        Returns:
            A CommandResult. `success=False` (never a crash, never a
            dispatch) if text-to-speech is not enabled/available, no
            text was given, or synthesis failed for any reason (see
            `TextToSpeechEngine.synthesize`).
        """
        if self._tts_engine is None:
            return CommandResult(
                success=False,
                message=(
                    "Text-to-Speech is not enabled or not available. "
                    "Set 'voice.tts.enabled: true' in config/config.yaml and "
                    "ensure a text-to-speech engine (pyttsx3) is installed."
                ),
            )

        text = " ".join(arguments).strip()
        if not text:
            return CommandResult(success=False, message="Usage: voice speak <text>")

        result = self._tts_engine.synthesize(text)
        if not result.success:
            return CommandResult(success=False, message=f"Speech failed: {result.error}")

        return CommandResult(success=True, message=f'Spoke: "{text}"')

    def _below_confidence_threshold(self, confidence: float | None) -> bool:
        """Return whether `confidence` is below the configured minimum.

        A None threshold (not configured) or a None confidence (the
        engine does not expose one) never blocks dispatch -- only an
        explicit, known confidence below an explicit, configured
        threshold does (owner Decision 9).
        """
        if self._min_confidence is None or confidence is None:
            return False
        return confidence < self._min_confidence
