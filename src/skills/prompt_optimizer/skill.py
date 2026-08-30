"""EP-055 prompt optimizer module: the "prompt" command namespace (Prompt Optimizer).

Implements `CommandModule` (`src/core/command_router.py`), following
`DesktopModule`/`BrowserModule`/`FileModule`/`VisionModule`/
`ReflectionModule`'s reference-implementation pattern exactly (Owner
Decision D7, `EP055_DESIGN.md`). Bridges an on-demand prompt/template
improvement request (Owner Decision D1, "Candidate A") to the
"prompt" namespace, dispatched through the *existing*, unmodified
`CommandRouter.dispatch()` -- no new dispatch mechanism, and Tool
Engine is untouched.

Like `ReflectionModule` (EP-054) and unlike `desktop`/`browser`/
`file`/`vision`, EP-055 introduces no new external I/O surface beyond
what already exists and therefore no new backend Protocol
(`EP055_DESIGN.md` Section 6.2): `PromptOptimizerModule` composes one
already-existing, unmodified component directly via constructor
injection --

    - `ProviderManager` (EP-014) -- `ProviderManager.get_current()`
      returns the raw, currently-selected `AIProvider`, on which
      `PromptOptimizerModule` calls the existing, unmodified
      `AIProvider.ask()` (EP-015) directly. This deliberately bypasses
      `AIService`'s higher-level Conversation/Context/Prompt Engine
      pipeline (`src/services/ai_service.py`) -- going through
      `AIService.ask()` would both append the optimization request as
      a new conversation turn and recursively route it back through
      the very Prompt Engine (`PromptManager`/`PromptBuilder`) whose
      *template input* it is trying to improve, which
      `EP055_DESIGN.md` Section 6.4 explicitly rules out. No
      `AIProvider`/`ProviderManager` method is modified or extended --
      both are used exactly as EP-014/015 shipped them.

`PromptOptimizerModule` also reads (never writes, per Owner Decision
D4) the already-configured `paths.prompts` directory when
`--template <name>` is given, using the exact same file-lookup
convention `PromptBuilder.load_template()` (EP-017,
`src/core/ai/prompt_builder.py`) already establishes -- it reuses that
module's `PromptTemplateNotFoundError` exception type for a not-found
template (`EP055_DESIGN.md` Section 10's "reuse, not re-implement"
rule) but never imports, constructs, or calls `PromptBuilder` or
`PromptManager` themselves. `src/core/ai/prompt.py`,
`src/core/ai/prompt_builder.py`, and `src/core/ai/prompt_manager.py`
are all completely unmodified by EP-055 (`EP055_DESIGN.md` Section
14, DO NOT MODIFY).

EP-055 v1 is strictly return-only (Owner Decision D4,
`EP055_DESIGN.md`): `prompt optimize`'s output is returned as plain
text only -- it never writes to `paths.prompts` or anywhere else, and
never automatically changes any configuration, prompt, or behavior of
any other component. No `prompt save` action exists in v1. No
`AgentEngine.register_subsystem()` call exists in v1 (Owner Decision
D5 -- `CommandModule` only).

Safety model (`EP055_DESIGN.md` Section 7/20, Owner Decisions
D1/D3/D6):

    1. `prompt_optimizer.enabled` (default `false`) -- the master gate
       for the entire namespace, re-checked on every dispatched
       action, not only at registration time (mirrors
       `reflection.enabled`/`vision.enabled`/`file.enabled`/
       `browser.enabled`/`desktop.enabled` exactly).
       `PromptOptimizerModule` IS registered with `CommandRouter`
       regardless of this flag's value.
    2. `prompt_optimizer.max_input_size` -- caps how many characters
       of prompt/template text a single `prompt optimize` call may
       include. An input exceeding this cap is refused, never
       silently truncated (Owner Decision D6, mirroring
       `reflection.max_message_count`'s own "reject, never silently
       clamp/downscale" precedent).
    3. `prompt_optimizer.min_seconds_between_calls` -- a simple,
       in-process rate limit bounding how often `prompt optimize` may
       call the configured AI provider, protecting against rapid,
       repeated invocation running up provider cost (Owner Decision
       D6, identical in shape to `reflection.min_seconds_between_calls`).
       Reset on process restart -- not a durable, cross-restart limit,
       by design.

No shell/subprocess/arbitrary code execution of any kind exists in
this module, and no new third-party dependency was introduced
(`EP055_DESIGN.md` Section 9).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from loguru import logger

from src.core.ai.prompt_builder import DEFAULT_TEMPLATE_DIRECTORY, PromptTemplateNotFoundError
from src.core.ai.provider import ProviderError
from src.core.ai.provider_manager import ProviderManager
from src.core.command_router import CommandResult
from src.core.config import Config

_DEFAULT_MAX_INPUT_SIZE: int = 4000
_DEFAULT_MIN_SECONDS_BETWEEN_CALLS: float = 30.0

HELP_TEXT: str = (
    "Available prompt commands (Prompt Optimizer, EP-055)\n\n"
    "prompt help\n"
    "prompt optimize <text>\n"
    "prompt optimize --template <name>\n\n"
    "'prompt optimize' asks the currently configured AI provider to "
    "improve the clarity and structure of the given prompt text (or "
    "the content of an existing template under 'paths.prompts', with "
    "--template) without changing its intent. It never modifies the "
    "original template file, any configuration, or any other "
    "component's behavior -- output is returned as plain text only "
    "(Owner Decision D4 -- no 'prompt save' in v1)."
)

ActionHandler = Callable[[list[str]], CommandResult]

_DISABLED_MESSAGE: str = (
    "Prompt Optimizer is disabled ('prompt_optimizer.enabled: false' "
    "in config/config.yaml). Set it to true and restart to enable "
    "'prompt' actions."
)

_NO_PROVIDER_MESSAGE: str = (
    "No AI provider is currently available (check 'ai.enabled' and "
    "'ai.default_provider' in config/config.yaml)."
)

_OPTIMIZE_PROMPT_TEMPLATE: str = (
    "You are improving the following prompt so it is clearer and "
    "better structured for an AI provider to follow, without "
    "changing its intent, meaning, or the task it describes. Do not "
    "answer the prompt -- only rewrite it. Respond with the improved "
    "prompt only -- no preamble, no explanation.\n\n"
    "--- Original prompt ---\n"
    "{original}\n"
    "--- End of original prompt ---"
)


@dataclass
class _RateLimitState:
    """Tracks the wall-clock time of the last successful 'prompt optimize' call."""

    last_call_monotonic: float | None = None


class PromptOptimizerModule:
    """The "prompt" command namespace (EP-055, Prompt Optimizer).

    Responsibilities:
        - `prompt optimize <text>` / `prompt optimize --template
          <name>`: ask the configured AI provider to improve the
          clarity/structure of the given prompt text (or a named
          template's current content), returning the improved version
          as plain text.

    Never captures a screenshot, manages a file, interprets an image,
    or critiques a conversation (unrelated to any prior Phase 7/8/
    EP-054 skill), never writes to `paths.prompts` or anywhere else
    (Owner Decision D4 -- return-only in v1), never modifies
    `AIProvider`/`ProviderManager`/`PromptBuilder`/`PromptManager`
    behavior, and never autonomously changes any configuration,
    prompt, or behavior of any other component.
    """

    def __init__(
        self,
        config: Config,
        provider_manager: ProviderManager,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """Initialize the PromptOptimizerModule.

        Args:
            config: The application Config. Read at dispatch time for
                'prompt_optimizer.enabled',
                'prompt_optimizer.max_input_size',
                'prompt_optimizer.min_seconds_between_calls', and
                'paths.prompts' -- read fresh on every call, not
                cached, so a config reload/restart is the only way to
                change them (matching every other subsystem's
                flag-reading convention).
            provider_manager: The already-constructed `ProviderManager`
                (EP-014), used only via `get_current()` to reach the
                currently-selected `AIProvider`'s unmodified `ask()`.
            clock: A zero-argument callable returning a monotonically
                increasing float, used for the rate limit. Defaults to
                `time.monotonic`; tests inject a fake clock instead of
                sleeping for real (`EP055_DESIGN.md` Section 12).
        """
        self._config = config
        self._provider_manager = provider_manager
        self._clock = clock
        self._rate_limit_state = _RateLimitState()
        self._actions: dict[str, ActionHandler] = {
            "help": self._help,
            "optimize": self._optimize,
        }

    @property
    def name(self) -> str:
        """Return this module's command namespace.

        Returns:
            The literal string "prompt".
        """
        return "prompt"

    def execute(self, action: str, arguments: list[str]) -> CommandResult:
        """Execute a "prompt" action.

        Args:
            action: The requested action (e.g. "optimize"). May be
                empty if the user entered only "prompt".
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
                'Type "prompt help" for available commands.'
            )
            return CommandResult(success=False, message=message)

        return handler(arguments)

    # ---------- Safety gate (EP055_DESIGN.md Section 7/20) ----------

    def _is_enabled(self) -> bool:
        """Return whether 'prompt_optimizer.enabled' is currently true."""
        return bool(self._config.get("prompt_optimizer.enabled", False))

    def _max_input_size(self) -> int:
        """Return the configured 'prompt_optimizer.max_input_size' (default 4000)."""
        return int(self._config.get("prompt_optimizer.max_input_size", _DEFAULT_MAX_INPUT_SIZE))

    def _min_seconds_between_calls(self) -> float:
        """Return the configured 'prompt_optimizer.min_seconds_between_calls' (default 30)."""
        return float(
            self._config.get(
                "prompt_optimizer.min_seconds_between_calls",
                _DEFAULT_MIN_SECONDS_BETWEEN_CALLS,
            )
        )

    def _gate(self) -> CommandResult | None:
        """Return a failure CommandResult if no action may execute, else None.

        Called by every action handler *after* argument-shape
        validation and *before* any provider interaction -- guarantees
        zero downstream calls while disabled.
        """
        if not self._is_enabled():
            logger.info("prompt: action rejected, 'prompt_optimizer.enabled' is false.")
            return CommandResult(success=False, message=_DISABLED_MESSAGE)
        return None

    def _check_rate_limit(self) -> CommandResult | None:
        """Return a failure CommandResult if the rate limit has not elapsed, else None."""
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
                    f"prompt optimize: rate-limited -- wait "
                    f"{remaining:.1f} more second(s) "
                    f"('prompt_optimizer.min_seconds_between_calls={min_seconds}')."
                ),
            )
        return None

    # ---------- Action handlers ----------

    def _help(self, arguments: list[str]) -> CommandResult:
        """Return the list of available prompt commands."""
        return CommandResult(success=True, message=HELP_TEXT)

    def _optimize(self, arguments: list[str]) -> CommandResult:
        """Improve the clarity/structure of a prompt via the configured AI provider.

        Args:
            arguments: Either `["--template", "<name>"]` (load the
                named template's current content from 'paths.prompts')
                or one-or-more free-text words joined with a single
                space (matching the existing `" ".join(arguments)`
                convention already used elsewhere for free-text
                command arguments, e.g. `desktop type`,
                `src/skills/desktop/skill.py`).

        Ordering note (Owner Decision D10, `EP055_DESIGN.md` STEP 4 --
        resolves STEP 3 Findings 1/2): shape-only argument validation
        (`_validate_optimize_arguments()`, no filesystem access) runs
        first, then `self._gate()`, then the rate limit, and only then
        `self._resolve_input()` -- which is the one step that may read
        a template file from disk -- followed by the `max_input_size`
        check. This guarantees `prompt_optimizer.enabled=false` always
        short-circuits before any filesystem access, template-
        existence/path disclosure, or `max_input_size` value is
        revealed, matching the "gate first" ordering every other skill
        (`desktop`/`browser`/`file`/`vision`/`reflect`) already
        follows. This reordering changes no public behavior while
        enabled -- every check that previously ran still runs, in the
        same relative order relative to each other, only the position
        of the gate itself moved earlier.
        """
        shape_failure = self._validate_optimize_arguments(arguments)
        if shape_failure is not None:
            return shape_failure

        gate_failure = self._gate()
        if gate_failure is not None:
            return gate_failure

        rate_limit_failure = self._check_rate_limit()
        if rate_limit_failure is not None:
            return rate_limit_failure

        original, resolution_error = self._resolve_input(arguments)
        if resolution_error is not None:
            return resolution_error

        max_size = self._max_input_size()
        if len(original) > max_size:
            return CommandResult(
                success=False,
                message=(
                    f"prompt optimize: input is {len(original)} character(s), "
                    f"exceeding 'prompt_optimizer.max_input_size' ({max_size})."
                ),
            )

        provider = self._provider_manager.get_current()
        if provider is None:
            return CommandResult(success=False, message=_NO_PROVIDER_MESSAGE)

        prompt = _OPTIMIZE_PROMPT_TEMPLATE.format(original=original)

        try:
            response = provider.ask(prompt)
        except ProviderError as exc:
            logger.error(f"prompt optimize failed: {exc}")
            return CommandResult(success=False, message=f"prompt optimize failed: {exc}")

        self._rate_limit_state.last_call_monotonic = self._clock()

        logger.info(f"prompt optimize: generated an improved version of {len(original)} character(s) of input.")
        return CommandResult(success=True, message=response.text)

    # ---------- Input resolution ----------

    def _validate_optimize_arguments(self, arguments: list[str]) -> CommandResult | None:
        """Validate the shape of 'prompt optimize' arguments, with zero filesystem access.

        Deliberately separated from `_resolve_input()` (Owner Decision
        D10, `EP055_DESIGN.md` STEP 4) so it can run *before*
        `self._gate()`: this method never touches the filesystem and
        never discloses a template's existence, emptiness, or resolved
        path, or any configured resource limit -- it only checks the
        raw argument shape, which is safe to reveal regardless of
        `prompt_optimizer.enabled`, exactly like every other
        `CommandModule`'s own argument-count usage errors (e.g.
        `reflect summary` with too many arguments,
        `src/skills/reflection/skill.py`).

        Args:
            arguments: The raw arguments passed to `prompt optimize`.

        Returns:
            A failure CommandResult if `arguments` has an invalid
            shape, else None.
        """
        if not arguments:
            return _usage_error("prompt optimize <text> | prompt optimize --template <name>")

        if arguments[0] == "--template":
            if len(arguments) != 2:
                return _usage_error("prompt optimize --template <name>")
            return None

        if not " ".join(arguments).strip():
            return _usage_error("prompt optimize <text> | prompt optimize --template <name>")
        return None

    def _resolve_input(self, arguments: list[str]) -> tuple[str, None] | tuple[None, CommandResult]:
        """Resolve already shape-validated `arguments` into the prompt text to optimize.

        Must only be called after `_validate_optimize_arguments(arguments)`
        has already returned None -- this method assumes the argument
        shape is valid and performs no shape checking of its own. This
        is also the one step that may read a template file from disk
        (via `_load_template()`), which is why `_optimize()` calls this
        only after `self._gate()`/`self._check_rate_limit()` have
        already passed (Owner Decision D10).

        Args:
            arguments: The raw arguments passed to `prompt optimize`,
                already confirmed valid by
                `_validate_optimize_arguments()`.

        Returns:
            A `(text, None)` tuple on success, or a
            `(None, CommandResult)` tuple describing a template
            not-found/unreadable/empty failure.
        """
        if arguments[0] == "--template":
            try:
                return self._load_template(arguments[1]), None
            except PromptTemplateNotFoundError as exc:
                return None, CommandResult(success=False, message=f"prompt optimize: {exc}")

        return " ".join(arguments).strip(), None

    def _load_template(self, name: str) -> str:
        """Read a template's current content from 'paths.prompts'.

        Mirrors the exact file-lookup convention `PromptBuilder.
        load_template()` (`src/core/ai/prompt_builder.py`, EP-017)
        already establishes -- same directory setting
        ('paths.prompts'), same '<name>.txt' file naming, and reuses
        that module's own `PromptTemplateNotFoundError` exception type
        for the not-found/unreadable case (`EP055_DESIGN.md` Section
        10's "reuse, not re-implement" rule) -- but never constructs
        or calls `PromptBuilder` itself (`EP055_DESIGN.md` Section
        6.4/14).

        Args:
            name: The template's file name, without the '.txt'
                extension.

        Returns:
            The template's stripped text content.

        Raises:
            PromptTemplateNotFoundError: If no template file exists
                for `name`, it cannot be read, or it is empty.
        """
        directory = Path(str(self._config.get("paths.prompts", DEFAULT_TEMPLATE_DIRECTORY)))
        path = directory / f"{name}.txt"
        if not path.is_file():
            raise PromptTemplateNotFoundError(f"template not found: '{name}' (expected '{path}').")

        try:
            content = path.read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise PromptTemplateNotFoundError(f"could not read template '{name}': {exc}") from exc

        if not content:
            raise PromptTemplateNotFoundError(f"template '{name}' is empty.")
        return content


def _usage_error(usage: str) -> CommandResult:
    """Return a standard, non-crashing usage-error CommandResult."""
    return CommandResult(success=False, message=f"Invalid arguments. Usage: {usage}")
