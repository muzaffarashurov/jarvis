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

EP-048 (Wake Word) additive extension: `voice wake listen`/`voice
wake status`, wired to a `WakeWordEngine`/`StreamingAudioCapture`
pair the same way `voice speak` was wired to a `TextToSpeechEngine`
in EP-047 -- optional, defaulted constructor parameters, no change
to any existing action (EP048_DESIGN.md Section 5.4, owner Decision
D7). `voice wake listen` only ever *reports* a detection; per owner
Decision D5 it never calls `CommandRouter.dispatch()`, never starts
an STT cycle, and never runs as a background/always-on listener --
that full wake -> listen -> dispatch loop is explicitly EP-049's
scope, not this module's.

EP-049 (Voice Assistant) additive extension: `voice wake assist`,
wired into the existing `_wake()` sub-dispatcher alongside `wake
listen`/`wake status`. On a wake-word detection it stops the wake
stream and calls the existing `_listen()` method directly, unmodified
(EP049_DESIGN.md Section 23a, Owner Decision D3) -- it never
duplicates audio capture, transcription, confidence-gating, or
`CommandRouter.dispatch()`. Strictly one-shot (Owner Decision D2):
exactly one wake -> command -> result cycle per invocation, with no
loop, no background thread, and no automatic re-arming of wake
listening (Owner Decision D1). Reads its own configuration
(`voice.wake.assist.*`) directly from the existing `config` object;
no new constructor parameter was added (Owner Decision D4).
"""

from __future__ import annotations

from typing import Callable

from loguru import logger

from src.core.command_router import CommandResult, CommandRouter
from src.core.config import Config
from src.skills.voice.audio_capture import AudioCapture
from src.skills.voice.speech_to_text import SpeechToTextEngine
from src.skills.voice.streaming_audio_capture import StreamingAudioCapture
from src.skills.voice.text_to_speech import TextToSpeechEngine
from src.skills.voice.wake_word import WakeWordEngine

HELP_TEXT: str = (
    "Available voice commands\n\n"
    "voice listen [language]\n"
    "voice transcribe [language]\n"
    "voice status\n"
    "voice speak <text>\n"
    "voice wake listen\n"
    "voice wake status\n"
    "voice wake assist [language]"
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
        - `voice wake listen` (EP-048, additive): listen for the
          configured wake word and report a single detection. Never
          dispatches through `CommandRouter`, never starts an STT
          cycle, never speaks via TTS, and never runs as a
          background listener (owner Decision D5,
          EP048_DESIGN.md Section 9a).
        - `voice wake status` (EP-048, additive): report wake-word
          engine/model readiness.

    Never contains recognition logic (that is `SpeechToTextEngine`'s
    job), microphone logic (that is `AudioCapture`'s/
    `StreamingAudioCapture`'s job), synthesis logic (that is
    `TextToSpeechEngine`'s job), or wake-word detection logic (that
    is `WakeWordEngine`'s job) -- this class only orchestrates them
    and talks to `CommandRouter`.
    """

    def __init__(
        self,
        config: Config,
        command_router: CommandRouter,
        engine: SpeechToTextEngine | None,
        audio_capture: AudioCapture | None,
        tts_engine: TextToSpeechEngine | None = None,
        wake_engine: WakeWordEngine | None = None,
        wake_capture: StreamingAudioCapture | None = None,
    ) -> None:
        """Initialize the VoiceModule.

        Args:
            config: The application Config. Read once at dispatch time
                for 'voice.min_confidence' (already read once by
                `engine`, kept here too since `engine` exposes it as a
                read-only property -- see `_min_confidence`). Also
                stored as `self._config` and read directly by
                `_wake_assist` for `voice.wake.assist.*` (EP-049,
                owner Decision D4) -- no new constructor parameter was
                added for this.
            command_router: The existing, shared CommandRouter every
                other interface (shell, Telegram, REST API) also
                dispatches through. `voice listen` hands its
                transcript to this exact instance -- never a second
                router.
            engine: The STT engine used to transcribe captured audio.
                May be None (EP-048, owner Decision D6) when
                'voice.enabled' (STT) is false or STT construction
                failed -- `voice listen`/`voice transcribe`/`voice
                status` each report a clear failure (never a crash)
                in that case, so Text-to-Speech-only or Wake-Word-only
                operation is possible with STT fully disabled.
            audio_capture: The microphone capture component used by
                `voice listen`/`voice transcribe` when no explicit
                language-only argument path applies. May be None
                under the same conditions as `engine`.
            tts_engine: The TTS engine used by `voice speak` (EP-047).
                Optional and defaults to None so every existing
                EP-046 call site (and every existing EP-046 test)
                keeps working unmodified -- `voice speak` reports a
                clear failure (never a crash) when this is None,
                exactly as when 'voice.tts.enabled' is false or
                text-to-speech engine construction failed (see
                `_speak`, EP047_DESIGN.md Section 5.3).
            wake_engine: The wake-word engine used by `voice wake
                listen`/`voice wake status` (EP-048). Optional and
                defaults to None, following the exact same additive
                pattern `tts_engine` established in EP-047 -- every
                existing EP-046/EP-047 call site and test keeps
                working unmodified. `voice wake *` reports a clear
                failure (never a crash) when this is None (see
                `_wake_listen`/`_wake_status`,
                EP048_DESIGN.md Section 5.4/9a Decision D5).
            wake_capture: The streaming microphone capture component
                used by `voice wake listen`/`voice wake assist`.
                Optional, same reasoning as `wake_engine`. Independent
                from `audio_capture` (EP-046's fixed-duration capture)
                -- owner Decision D4.
        """
        self._config = config
        self._command_router = command_router
        self._engine = engine
        self._audio_capture = audio_capture
        self._tts_engine = tts_engine
        self._wake_engine = wake_engine
        self._wake_capture = wake_capture
        self._min_confidence = engine.min_confidence if hasattr(engine, "min_confidence") else (
            config.get("voice.min_confidence", None)
        )
        self._actions: dict[str, ActionHandler] = {
            "help": self._help,
            "listen": self._listen,
            "transcribe": self._transcribe,
            "status": self._status,
            "speak": self._speak,
            "wake": self._wake,
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

        if self._engine is None or self._audio_capture is None:
            return CommandResult(
                success=False,
                message=(
                    "Speech-to-Text is not enabled or not available. "
                    "Set 'voice.enabled: true' in config/config.yaml and "
                    "ensure a Vosk model is installed."
                ),
            )

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

        if self._engine is None or self._audio_capture is None:
            return CommandResult(
                success=False,
                message=(
                    "Speech-to-Text is not enabled or not available. "
                    "Set 'voice.enabled: true' in config/config.yaml and "
                    "ensure a Vosk model is installed."
                ),
            )

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
            Reports a safe, `success=True` "not enabled" status
            (never a crash) when no STT engine is configured
            (EP-048, owner Decision D6).
        """
        if self._engine is None:
            message = (
                "Voice Status\n\n"
                "Enabled : No\n\n"
                "Reason  : Speech-to-Text is not enabled or not "
                "available. Set 'voice.enabled: true' in "
                "config/config.yaml and ensure a Vosk model is "
                "installed."
            )
            return CommandResult(success=True, message=message)

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

    def _wake(self, arguments: list[str]) -> CommandResult:
        """Dispatch to a `voice wake` sub-action (EP-048/EP-049).

        Args:
            arguments: `arguments[0]` selects the sub-action
                ("listen", "status", or "assist"); remaining
                arguments are passed through to that sub-action.

        Returns:
            A CommandResult from the selected sub-action, or a usage
            message if no valid sub-action was given.
        """
        sub_action = arguments[0].lower() if arguments else ""
        sub_arguments = arguments[1:]

        if sub_action == "listen":
            return self._wake_listen(sub_arguments)
        if sub_action == "status":
            return self._wake_status(sub_arguments)
        if sub_action == "assist":
            return self._wake_assist(sub_arguments)

        return CommandResult(
            success=False,
            message='Usage: voice wake listen | voice wake status | voice wake assist',
        )

    def _wake_listen(self, arguments: list[str]) -> CommandResult:
        """Listen continuously for the configured wake word; report detection only.

        EP-048, owner Decision D5 (EP048_DESIGN.md Section 9a):
        detection only. This method never calls
        `CommandRouter.dispatch()`, never starts an STT/`voice
        listen` cycle, never speaks via `voice speak`/TTS, and never
        runs as a background/always-on listener -- it is a single,
        foreground, blocking call that returns as soon as one
        detection occurs (or the stream ends/fails).

        Args:
            arguments: Unused.

        Returns:
            A CommandResult. `success=True` with the detected wake
            word and score once detected. `success=False` (never a
            crash) if wake-word detection is not enabled/available,
            the microphone could not be opened, or listening ended
            (stream closed, interrupted) without a detection.
        """
        if self._wake_engine is None or self._wake_capture is None:
            return CommandResult(
                success=False,
                message=(
                    "Wake Word detection is not enabled or not available. "
                    "Set 'voice.wake.enabled: true' in config/config.yaml and "
                    "ensure openWakeWord model files are installed under "
                    "'voice.wake.model_dir'."
                ),
            )

        start_result = self._wake_capture.start()
        if not start_result.success:
            return CommandResult(success=False, message=f"Microphone error: {start_result.error}")

        try:
            for frame in self._wake_capture.frames():
                detection = self._wake_engine.process_frame(frame)
                if detection.detected:
                    message = (
                        f'Wake word detected: "{detection.wake_word}" '
                        f"(score {detection.score:.2f})"
                    )
                    return CommandResult(success=True, message=message)
        except KeyboardInterrupt:
            return CommandResult(success=False, message="Wake word listening interrupted.")
        finally:
            self._wake_capture.stop()

        return CommandResult(
            success=False,
            message="Wake word listening ended without a detection.",
        )

    def _wake_status(self, arguments: list[str]) -> CommandResult:
        """Report wake-word engine/model readiness.

        Args:
            arguments: Unused.

        Returns:
            A CommandResult summarizing whether Wake Word is enabled,
            the configured wake word, model availability, model
            directory, and detection threshold. Reports a safe,
            `success=True` "not enabled" status (never a crash) when
            no wake-word engine is configured.
        """
        if self._wake_engine is None:
            message = (
                "Wake Word Status\n\n"
                "Enabled : No\n\n"
                "Reason  : Wake Word detection is not enabled or not "
                "available. Set 'voice.wake.enabled: true' in "
                "config/config.yaml and ensure openWakeWord model files "
                "are installed under 'voice.wake.model_dir'."
            )
            return CommandResult(success=True, message=message)

        model_status = (
            "available"
            if hasattr(self._wake_engine, "model_available") and self._wake_engine.model_available()
            else "MISSING"
        )
        threshold = getattr(self._wake_engine, "threshold", None)
        threshold_text = f"{threshold:.2f}" if threshold is not None else "not configured"
        model_dir = getattr(self._wake_engine, "model_dir", "n/a")

        message = (
            "Wake Word Status\n\n"
            "Enabled : Yes\n\n"
            "Engine : openWakeWord\n\n"
            f"Wake word : {self._wake_engine.wake_word}\n\n"
            f"Model : {model_status}\n\n"
            f"Model directory : {model_dir}\n\n"
            f"Threshold : {threshold_text}\n\n"
            "Note: Russian and Uzbek wake-word detection are out of "
            "scope for EP-048 (English-only \"Hey Jarvis\")."
        )
        return CommandResult(success=True, message=message)

    def _wake_assist(self, arguments: list[str]) -> CommandResult:
        """Wake word -> one command capture -> STT -> dispatch -> optional TTS.

        EP-049 (EP049_DESIGN.md, Owner Decisions D1-D7, Section 23a).
        Strictly one-shot: exactly one wake detection leads to exactly
        one call to the existing, unmodified `_listen()` (owner
        Decision D3), then returns. There is no loop, no background
        thread, and no automatic re-arming of wake listening (owner
        Decisions D1/D2) -- a new invocation of `voice wake assist` is
        required for another cycle.

        Audio resource ownership (EP049_DESIGN.md Section 9): the
        wake stream (`StreamingAudioCapture`) is always fully stopped,
        via `finally`, before the existing fixed-duration
        `AudioCapture`/STT/dispatch path (`_listen()`) is ever
        invoked. The two are never open at the same time, and no new
        lock/semaphore is introduced -- this method is entirely
        sequential.

        Args:
            arguments: An optional single language code, forwarded
                unchanged to `_listen()` (same meaning as `voice
                listen [language]`).

        Returns:
            A CommandResult. `success=False` (never a crash) if
            EP-049 is disabled, wake-word detection or STT is not
            enabled/available, the wake microphone could not be
            opened, or wake listening ended without a detection.
            Otherwise, the exact CommandResult `_listen()` produced
            for the one captured command (dispatched result, or a
            reported failure such as empty/low-confidence
            transcription) -- optionally spoken first via the
            existing TTS engine if `voice.wake.assist.speak_result`
            is true (owner Decision D6).
        """
        if not self._config.get("voice.wake.assist.enabled", False):
            return CommandResult(
                success=False,
                message=(
                    "Wake Word Assist is not enabled. Set "
                    "'voice.wake.assist.enabled: true' in "
                    "config/config.yaml."
                ),
            )

        if self._wake_engine is None or self._wake_capture is None:
            return CommandResult(
                success=False,
                message=(
                    "Wake Word detection is not enabled or not available. "
                    "Set 'voice.wake.enabled: true' in config/config.yaml and "
                    "ensure openWakeWord model files are installed under "
                    "'voice.wake.model_dir'."
                ),
            )

        if self._engine is None or self._audio_capture is None:
            return CommandResult(
                success=False,
                message=(
                    "Speech-to-Text is not enabled or not available. "
                    "Set 'voice.enabled: true' in config/config.yaml and "
                    "ensure a Vosk model is installed."
                ),
            )

        start_result = self._wake_capture.start()
        if not start_result.success:
            return CommandResult(success=False, message=f"Microphone error: {start_result.error}")

        detected = False
        detection_message = ""
        try:
            for frame in self._wake_capture.frames():
                detection = self._wake_engine.process_frame(frame)
                if detection.detected:
                    detected = True
                    detection_message = (
                        f'Wake word detected: "{detection.wake_word}" '
                        f"(score {detection.score:.2f})"
                    )
                    break
        except KeyboardInterrupt:
            return CommandResult(success=False, message="Wake word listening interrupted.")
        finally:
            # Mandatory hand-off (EP049_DESIGN.md Section 9): the wake
            # stream must be fully stopped before _listen() -- which
            # owns AudioCapture -- is ever called below.
            self._wake_capture.stop()

        if not detected:
            return CommandResult(
                success=False,
                message="Wake word listening ended without a detection.",
            )

        logger.info(detection_message)

        # Reuse the existing _listen() directly and unmodified (owner
        # Decision D3) -- it already owns AudioCapture, STT,
        # confidence-gating, and CommandRouter.dispatch(). EP-049 does
        # not duplicate any of that here.
        listen_result = self._listen(arguments)

        if self._tts_engine is not None and self._config.get("voice.wake.assist.speak_result", False):
            # TTS-on-result is strictly optional (owner Decision D6):
            # a synthesis failure must never affect the command's own
            # outcome, so its result is intentionally not inspected.
            self._tts_engine.synthesize(listen_result.message)

        # One-shot termination (owner Decision D2): return immediately.
        # No restart of self._wake_capture, no loop.
        return listen_result

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
