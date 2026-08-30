"""EP-054 reflection module: the "reflect" command namespace (Self Reflection).

Implements `CommandModule` (`src/core/command_router.py`), following
`DesktopModule`/`BrowserModule`/`FileModule`/`VisionModule`'s
reference-implementation pattern exactly (Owner Decision D8,
`EP054_DESIGN.md`). Bridges an on-demand, session/conversation
self-critique (Owner Decision D1, "Candidate A") to the "reflect"
namespace, dispatched through the *existing*, unmodified
`CommandRouter.dispatch()` -- no new dispatch mechanism, and Tool
Engine is untouched.

Unlike `desktop`/`browser`/`file`/`vision`, EP-054 introduces no new
external I/O surface and therefore no new backend Protocol
(`EP054_DESIGN.md` Section 6.2): `ReflectionModule` composes three
already-existing, unmodified components directly via constructor
injection --

    - `ConversationManager` (EP-016) -- read-only source of the
      current conversation's recent messages. `ReflectionModule`
      never appends to, mutates, or selects a different conversation;
      it only reads `ConversationManager.current().messages()`.
    - `ProviderManager` (EP-014) -- `ProviderManager.get_current()`
      returns the raw, currently-selected `AIProvider`, on which
      `ReflectionModule` calls the existing, unmodified
      `AIProvider.ask()` (EP-015) directly. This deliberately bypasses
      `AIService`'s higher-level Conversation/Context/Prompt Engine
      pipeline (`src/services/ai_service.py`) -- going through
      `AIService.ask()` would itself append the reflection request as
      a new turn in the very conversation being reflected upon, which
      `EP054_DESIGN.md` Section 6.4 explicitly rules out
      ("`ReflectionModule` never mutates a conversation"). No
      `AIProvider`/`ProviderManager` method is modified or extended --
      both are used exactly as EP-014/015 shipped them.
    - `MemoryService` (EP-023), optional -- if `reflection
      .persist_to_memory` is enabled, `reflect summary` also stores
      its result via `MemoryService.set()` under a dedicated
      "reflection" namespace, and `reflect recall` reads it back via
      `MemoryService.list_entries("reflection")`. `ReflectionModule`
      depends on the already-established `MemoryService` wrapper (not
      the raw `MemoryManager`), matching how every other Bootstrap-
      wired consumer of the EP-023 subsystem is already composed
      (`src/bootstrap.py`'s own `self._memory_service`).

EP-054 v1 is strictly descriptive (Owner Decision D3,
`EP054_DESIGN.md`): `reflect summary`'s output is returned as plain
text and, optionally, persisted for later recall -- it never
automatically changes any configuration, prompt, or behavior of any
other component. No `Scheduler` integration exists in v1 (Owner
Decision D5 -- manual-only), and no `AgentEngine.register_subsystem()`
call exists in v1 (Owner Decision D6 -- `CommandModule` only).

Safety model (`EP054_DESIGN.md` Section 7/20, Owner Decisions
D1-D2/D7):

    1. `reflection.enabled` (default `false`) -- the master gate for
       the entire namespace, re-checked on every dispatched action,
       not only at registration time (mirrors `desktop.enabled`/
       `browser.enabled`/`file.enabled`/`vision.enabled` exactly).
       `ReflectionModule` IS registered with `CommandRouter`
       regardless of this flag's value.
    2. `reflection.max_message_count` -- caps how many of the current
       conversation's most recent messages a single `reflect summary`
       call may include. An explicit `count` argument exceeding this
       cap is refused, never silently clamped (Owner Decision D7,
       mirroring `vision.max_dimension`'s own "reject, never silently
       downscale" precedent, `EP053_DESIGN.md`/`config/config.yaml`).
    3. `reflection.min_seconds_between_calls` -- a simple, in-process
       rate limit bounding how often `reflect summary` may call the
       configured AI provider, protecting against rapid, repeated
       invocation running up provider cost (Owner Decision D7). Reset
       on process restart -- this is not a durable, cross-restart
       limit, by design (`EP054_DESIGN.md` Section 7 describes it as
       "a simple, in-process rate limit").

No shell/subprocess/arbitrary code execution of any kind exists in
this module, and no new third-party dependency was introduced
(`EP054_DESIGN.md` Section 9).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from loguru import logger

from src.core.ai.conversation_manager import ConversationManager
from src.core.ai.message import Message
from src.core.ai.provider import ProviderError
from src.core.ai.provider_manager import ProviderManager
from src.core.command_router import CommandResult
from src.core.config import Config
from src.services.memory_service import MemoryService

MEMORY_NAMESPACE: str = "reflection"
_DEFAULT_MAX_MESSAGE_COUNT: int = 20
_DEFAULT_MIN_SECONDS_BETWEEN_CALLS: float = 30.0
_DEFAULT_RECALL_COUNT: int = 5

HELP_TEXT: str = (
    "Available reflect commands (Self Reflection, EP-054)\n\n"
    "reflect help\n"
    "reflect summary [count]\n"
    "reflect recall [count]\n\n"
    "'reflect summary' asks the currently configured AI provider to "
    "critique the last [count] messages of the current conversation "
    "(default and cap: 'reflection.max_message_count'). It never "
    "modifies the conversation, any configuration, or any other "
    "component's behavior -- output is descriptive only. 'reflect "
    "recall' returns previously generated reflections, and requires "
    "'reflection.persist_to_memory: true'."
)

ActionHandler = Callable[[list[str]], CommandResult]

_DISABLED_MESSAGE: str = (
    "Self Reflection is disabled ('reflection.enabled: false' in "
    "config/config.yaml). Set it to true and restart to enable "
    "'reflect' actions."
)

_NO_PROVIDER_MESSAGE: str = (
    "No AI provider is currently available (check 'ai.enabled' and "
    "'ai.default_provider' in config/config.yaml)."
)

_RECALL_DISABLED_MESSAGE: str = (
    "'reflect recall' requires 'reflection.persist_to_memory: true' "
    "in config/config.yaml (and the Memory subsystem to be enabled "
    "and available)."
)

_REFLECTION_PROMPT_TEMPLATE: str = (
    "You are reviewing the following conversation exchange, as a "
    "brief self-critique exercise. Read the transcript below and "
    "respond with:\n"
    "1. What went well.\n"
    "2. What could be improved.\n"
    "3. One concrete thing to remember for next time.\n\n"
    "Keep the whole response short and direct. Respond with the "
    "critique only -- no preamble.\n\n"
    "--- Transcript ---\n"
    "{transcript}\n"
    "--- End of transcript ---"
)


@dataclass
class _RateLimitState:
    """Tracks the wall-clock time of the last successful 'reflect summary' call."""

    last_call_monotonic: float | None = None


class ReflectionModule:
    """The "reflect" command namespace (EP-054, Self Reflection).

    Responsibilities:
        - `reflect summary [count]`: ask the configured AI provider to
          critique the last `count` messages of the current
          conversation, returning the critique as plain text and,
          optionally, persisting it for later recall.
        - `reflect recall [count]`: return previously persisted
          reflections, most recent first.

    Never captures a screenshot, manages a file, or interprets an
    image (unrelated to any prior Phase 7/8 skill), never mutates the
    conversation it reads from, never modifies `AIProvider`/
    `ProviderManager`/`ConversationManager`/`MemoryService` behavior,
    and never autonomously changes any configuration, prompt, or
    behavior of any other component in v1 (Owner Decision D3).
    """

    def __init__(
        self,
        config: Config,
        conversation_manager: ConversationManager,
        provider_manager: ProviderManager,
        memory_service: MemoryService | None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """Initialize the ReflectionModule.

        Args:
            config: The application Config. Read at dispatch time for
                'reflection.enabled', 'reflection.max_message_count',
                'reflection.min_seconds_between_calls', and
                'reflection.persist_to_memory' -- read fresh on every
                call, not cached, so a config reload/restart is the
                only way to change them (matching every other
                subsystem's flag-reading convention).
            conversation_manager: The already-constructed
                `ConversationManager` (EP-016), used read-only.
            provider_manager: The already-constructed `ProviderManager`
                (EP-014), used only via `get_current()` to reach the
                currently-selected `AIProvider`'s unmodified `ask()`.
            memory_service: The already-constructed `MemoryService`
                (EP-023), or None if the Memory subsystem is disabled/
                unavailable. Only consulted when
                'reflection.persist_to_memory' is true; every action
                reports a clear, non-crashing failure if persistence
                is requested but this is None.
            clock: A zero-argument callable returning a monotonically
                increasing float, used for the rate limit. Defaults to
                `time.monotonic`; tests inject a fake clock instead of
                sleeping for real (`EP054_DESIGN.md` Section 12).
        """
        self._config = config
        self._conversation_manager = conversation_manager
        self._provider_manager = provider_manager
        self._memory_service = memory_service
        self._clock = clock
        self._rate_limit_state = _RateLimitState()
        self._actions: dict[str, ActionHandler] = {
            "help": self._help,
            "summary": self._summary,
            "recall": self._recall,
        }

    @property
    def name(self) -> str:
        """Return this module's command namespace.

        Returns:
            The literal string "reflect".
        """
        return "reflect"

    def execute(self, action: str, arguments: list[str]) -> CommandResult:
        """Execute a "reflect" action.

        Args:
            action: The requested action (e.g. "summary"). May be
                empty if the user entered only "reflect".
            arguments: Additional arguments, meaning depends on the
                action (see `HELP_TEXT`).

        Returns:
            A CommandResult describing the outcome.
        """
        handler = self._actions.get(action)
        if handler is None:
            command = f"{self.name} {action}".strip()
            logger.info(f"Unknown command: {command}")
            message = (
                f"Unknown command: {command}\n"
                'Type "reflect help" for available commands.'
            )
            return CommandResult(success=False, message=message)

        return handler(arguments)

    # ---------- Safety gate (EP054_DESIGN.md Section 7/20) ----------

    def _is_enabled(self) -> bool:
        """Return whether 'reflection.enabled' is currently true."""
        return bool(self._config.get("reflection.enabled", False))

    def _max_message_count(self) -> int:
        """Return the configured 'reflection.max_message_count' (default 20)."""
        return int(self._config.get("reflection.max_message_count", _DEFAULT_MAX_MESSAGE_COUNT))

    def _min_seconds_between_calls(self) -> float:
        """Return the configured 'reflection.min_seconds_between_calls' (default 30)."""
        return float(
            self._config.get(
                "reflection.min_seconds_between_calls", _DEFAULT_MIN_SECONDS_BETWEEN_CALLS
            )
        )

    def _persist_to_memory(self) -> bool:
        """Return whether 'reflection.persist_to_memory' is currently true."""
        return bool(self._config.get("reflection.persist_to_memory", False))

    def _gate(self) -> CommandResult | None:
        """Return a failure CommandResult if no action may execute, else None.

        Called by every action handler *after* argument-shape
        validation and *before* any provider/conversation/memory
        interaction -- guarantees zero downstream calls while
        disabled.
        """
        if not self._is_enabled():
            logger.info("reflect: action rejected, 'reflection.enabled' is false.")
            return CommandResult(success=False, message=_DISABLED_MESSAGE)
        return None

    def _check_rate_limit(self) -> CommandResult | None:
        """Return a failure CommandResult if the rate limit has not elapsed, else None.

        Only applies to 'reflect summary' (the only action that calls
        the AI provider) -- 'reflect recall' reads already-persisted
        data and is not rate-limited.
        """
        min_seconds = self._min_seconds_between_calls()
        last_call = self._rate_limit_state.last_call_monotonic
        if last_call is None:
            return None
        elapsed = self._clock() - last_call
        if elapsed < min_seconds:
            remaining = min_seconds - elapsed
            return CommandResult(
                success=False,
                message=(
                    f"reflect summary: rate-limited -- wait "
                    f"{remaining:.1f} more second(s) "
                    f"('reflection.min_seconds_between_calls={min_seconds}')."
                ),
            )
        return None

    # ---------- Action handlers ----------

    def _help(self, arguments: list[str]) -> CommandResult:
        """Return the list of available reflect commands."""
        return CommandResult(success=True, message=HELP_TEXT)

    def _summary(self, arguments: list[str]) -> CommandResult:
        """Generate a self-critique of the current conversation's recent messages.

        Args:
            arguments: [] or [count] -- an optional message count,
                defaulting to and capped by
                'reflection.max_message_count'.
        """
        if len(arguments) not in (0, 1):
            return _usage_error("reflect summary [count]")

        max_count = self._max_message_count()
        if arguments:
            parsed_count, count_error = _parse_positive_int(arguments[0], "count")
            if count_error is not None:
                return count_error
            if parsed_count > max_count:
                return CommandResult(
                    success=False,
                    message=(
                        f"reflect summary: requested count {parsed_count} exceeds "
                        f"'reflection.max_message_count' ({max_count})."
                    ),
                )
            count = parsed_count
        else:
            count = max_count

        gate_failure = self._gate()
        if gate_failure is not None:
            return gate_failure

        rate_limit_failure = self._check_rate_limit()
        if rate_limit_failure is not None:
            return rate_limit_failure

        conversation = self._conversation_manager.current()
        messages = conversation.messages()
        if not messages:
            return CommandResult(
                success=True,
                message="reflect summary: the current conversation has no messages yet -- nothing to reflect on.",
            )

        provider = self._provider_manager.get_current()
        if provider is None:
            return CommandResult(success=False, message=_NO_PROVIDER_MESSAGE)

        recent_messages = messages[-count:]
        transcript = _render_transcript(recent_messages)
        prompt = _REFLECTION_PROMPT_TEMPLATE.format(transcript=transcript)

        try:
            response = provider.ask(prompt)
        except ProviderError as exc:
            logger.error(f"reflect summary failed: {exc}")
            return CommandResult(success=False, message=f"reflect summary failed: {exc}")

        self._rate_limit_state.last_call_monotonic = self._clock()

        if self._persist_to_memory():
            persist_failure = self._persist(response.text)
            if persist_failure is not None:
                # The critique itself was generated successfully; a
                # persistence failure is reported but does not discard
                # the critique the caller asked for.
                logger.warning(f"reflect summary: persistence failed: {persist_failure.message}")

        logger.info(f"reflect summary: generated critique of {len(recent_messages)} message(s).")
        return CommandResult(success=True, message=response.text)

    def _recall(self, arguments: list[str]) -> CommandResult:
        """Return previously persisted reflections, most recent first.

        Args:
            arguments: [] or [count] -- an optional number of
                reflections to return (default 5).
        """
        if len(arguments) not in (0, 1):
            return _usage_error("reflect recall [count]")

        count = _DEFAULT_RECALL_COUNT
        if arguments:
            parsed_count, count_error = _parse_positive_int(arguments[0], "count")
            if count_error is not None:
                return count_error
            count = parsed_count

        gate_failure = self._gate()
        if gate_failure is not None:
            return gate_failure

        if not self._persist_to_memory() or self._memory_service is None:
            return CommandResult(success=False, message=_RECALL_DISABLED_MESSAGE)

        entries = self._memory_service.list_entries(MEMORY_NAMESPACE)
        entries_sorted = sorted(entries, key=lambda entry: entry.created_at, reverse=True)
        selected = entries_sorted[:count]

        if not selected:
            return CommandResult(success=True, message="reflect recall: no reflections stored yet.")

        lines = [f"[{entry.created_at}] {entry.value}" for entry in selected]
        return CommandResult(success=True, message="\n\n".join(lines))

    # ---------- Persistence helper ----------

    def _persist(self, text: str) -> CommandResult | None:
        """Persist a generated reflection to MemoryService, if available.

        Returns:
            None on success, or the failing CommandResult if
            persistence could not be completed (never raised).
        """
        if self._memory_service is None:
            return CommandResult(
                success=False,
                message="reflect summary: 'reflection.persist_to_memory' is true but the Memory subsystem is unavailable.",
            )
        key = datetime.now(timezone.utc).isoformat()
        result = self._memory_service.set(key=key, value=text, namespace=MEMORY_NAMESPACE)
        if not result.success:
            return result
        return None


def _usage_error(usage: str) -> CommandResult:
    """Return a standard, non-crashing usage-error CommandResult."""
    return CommandResult(success=False, message=f"Invalid arguments. Usage: {usage}")


def _parse_positive_int(raw: str, label: str) -> tuple[int, None] | tuple[None, CommandResult]:
    """Parse `raw` as a positive integer, returning a usage-error CommandResult on failure."""
    try:
        value = int(raw)
    except ValueError:
        return None, CommandResult(success=False, message=f"'{label}' must be a positive integer, got '{raw}'.")
    if value <= 0:
        return None, CommandResult(success=False, message=f"'{label}' must be a positive integer, got '{raw}'.")
    return value, None


def _render_transcript(messages: list[Message]) -> str:
    """Render a list of Messages as a plain-text transcript, one line per message."""
    return "\n".join(f"{message.role.value}: {message.content}" for message in messages)
