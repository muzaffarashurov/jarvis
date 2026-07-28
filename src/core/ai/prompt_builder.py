"""PromptBuilder for EP-017 Prompt Engine.

PromptBuilder assembles a single, immutable Prompt from its parts
(system prompt, user prompt, conversation context, memory, capability
context, additional instructions, metadata), always in EP-017's fixed
"Prompt Flow" order:

    System Prompt
    -> Conversation Context
    -> Memory (future)
    -> Capability Context (future)
    -> Additional Instructions
    -> User Prompt

It performs no persistence and no lifecycle management of its own (see
PromptManager) -- it is a disposable, per-request object, matching the
pattern already used by every other builder-shaped class in this
project (e.g. `src/core/execution/executor.py`'s executor chain).

This module has no dependency on any AI provider (Claude, Gemini,
OpenAI, Ollama, LM Studio, ...); it depends only on Config, to resolve
the prompt template directory ('paths.prompts', already reserved for
this exact purpose -- see config/config.yaml and
`src/bootstrap.py`'s REQUIRED_DIRECTORIES) and the maximum prompt size
('prompt.max_prompt_size'), matching EP-017's "Provider Independence".

EP-017.1 (stabilization): validation is centralized here and here
only -- `PromptManager.create()` and `PromptManager.build()` both
route through this class's `build()`/`_validate()`, so every Prompt
object is guaranteed to pass the same checks regardless of which
PromptManager method created it. Configuration mistakes (e.g. a
non-numeric 'prompt.max_prompt_size') are also resolved defensively
here, raising PromptValidationError instead of a raw ValueError.

EP-018.5 Unified Prompt Budget: PromptBuilder is the SOLE authority on
prompt sizing in the project -- 'prompt.max_prompt_size' is the only
size ceiling that exists. Nothing else (ContextLoader included) may
define an independent one. `resolve_max_prompt_size()` and
`resolve_document_budget()` are exposed as stateless, config-only
functions of this authority precisely so other EP-017/EP-018
components can *derive* a sub-budget from it via Dependency Injection
instead of re-declaring their own ceiling:

    Document Budget = Prompt Max Size - Reserved Space

...where Reserved Space is the configurable sum of everything else
"Prompt Flow" (see the module docstring above) will place alongside
the documents: System Prompt, Conversation History, User Prompt, and
Provider Overhead ('prompt.reserved_*', all generic/provider-agnostic
headroom, never a provider-specific figure). ContextLoader consumes
this exclusively through the `document_budget` callable injected into
`ContextManager`/`ContextLoader` (see `context_manager.py`,
`context_loader.py`) -- it never reads 'prompt.*' or any sizing key of
its own, so the two subsystems cannot drift out of sync again.

EP-018.6 Conversation Budget Enforcement: the "Reserved Conversation
History" figure above was, as of EP-018.5, spent only once, as
bookkeeping subtracted out of the document budget -- nothing actually
enforced it on the rendered Conversation Context itself, which is why
it could still grow unbounded and overflow the final prompt.
`resolve_conversation_budget()` exposes that exact same
'prompt.reserved_conversation_history' figure (not a new setting) as
its own budget, injected into `ContextLoader` alongside
`document_budget` so `_render_conversation()` can finally enforce it:
oldest messages are dropped first, newest are kept, chronological
order is preserved, and the rendered text never exceeds the budget.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from loguru import logger

from src.core.ai.prompt import Prompt
from src.core.config import Config

DEFAULT_TEMPLATE_DIRECTORY: str = "prompts"
DEFAULT_MAX_PROMPT_SIZE: int = 32000

# EP-018.5: default headroom reserved out of 'prompt.max_prompt_size'
# for each non-document "Prompt Flow" stage, used whenever the
# corresponding 'prompt.reserved_*' setting is not configured. These
# are fallback *defaults* for an operator-configurable value, not a
# hardcoded budget -- the actual reservation always comes from Config.
DEFAULT_RESERVED_SYSTEM_PROMPT: int = 2_000
DEFAULT_RESERVED_CONVERSATION_HISTORY: int = 8_000
DEFAULT_RESERVED_USER_PROMPT: int = 2_000
DEFAULT_RESERVED_PROVIDER_OVERHEAD: int = 1_000


class PromptBuilderError(Exception):
    """Base class for PromptBuilder errors."""


class PromptValidationError(PromptBuilderError):
    """Raised when `build()` is called with missing or invalid input."""


class PromptTemplateNotFoundError(PromptBuilderError):
    """Raised when `load_template()` references a template that does not exist."""


class PromptBuilder:
    """Assembles a single immutable Prompt via fluent method chaining.

    Responsibilities:
        - Hold the in-progress parts of one prompt (system, user,
          context, memory, capabilities, instructions, metadata).
        - Optionally load a reusable prompt template from disk.
        - Validate the assembled prompt before building it.
        - Compose the final Prompt, in EP-017's fixed order.
        - Reset itself so a single instance can be reused.

    Not thread-safe: a PromptBuilder is a short-lived, per-request
    object (matching EP-017's "Thread Safety" section, which requires
    only PromptManager to be thread-safe).
    """

    def __init__(self, config: Config) -> None:
        """Initialize an empty PromptBuilder.

        Args:
            config: Loaded application configuration, used to resolve
                the template directory and the maximum prompt size.
        """
        self._config = config
        self._system_prompt: str = ""
        self._user_prompt: str = ""
        self._context_parts: list[str] = []
        self._memory_parts: list[str] = []
        self._capability_parts: list[str] = []
        self._instruction_parts: list[str] = []
        self._metadata: dict[str, Any] = {}

    # ---------- Fluent setters ----------

    def set_system(self, text: str) -> "PromptBuilder":
        """Set (replacing any previous value) the system prompt.

        Args:
            text: The system/instruction preamble text.

        Returns:
            This PromptBuilder, for fluent chaining.
        """
        self._system_prompt = text or ""
        return self

    def set_user(self, text: str) -> "PromptBuilder":
        """Set (replacing any previous value) the user prompt.

        Args:
            text: The end user's request text.

        Returns:
            This PromptBuilder, for fluent chaining.
        """
        self._user_prompt = text or ""
        return self

    def append_context(self, text: str) -> "PromptBuilder":
        """Append one conversation-context block.

        Args:
            text: The context text to append.

        Returns:
            This PromptBuilder, for fluent chaining.
        """
        if text:
            self._context_parts.append(text)
        return self

    def append_instruction(self, text: str) -> "PromptBuilder":
        """Append one additional-instruction block.

        Args:
            text: The instruction text to append.

        Returns:
            This PromptBuilder, for fluent chaining.
        """
        if text:
            self._instruction_parts.append(text)
        return self

    def append_memory(self, text: str) -> "PromptBuilder":
        """Append one memory block (reserved for the future Memory Engine).

        Args:
            text: The memory text to append.

        Returns:
            This PromptBuilder, for fluent chaining.
        """
        if text:
            self._memory_parts.append(text)
        return self

    def append_capabilities(self, text: str) -> "PromptBuilder":
        """Append one capability-context block (reserved for the future Capability Registry).

        Args:
            text: The capability-context text to append.

        Returns:
            This PromptBuilder, for fluent chaining.
        """
        if text:
            self._capability_parts.append(text)
        return self

    def append_metadata(self, key: str, value: Any) -> "PromptBuilder":
        """Attach one metadata key/value pair to the prompt being built.

        Args:
            key: The metadata key.
            value: The metadata value.

        Returns:
            This PromptBuilder, for fluent chaining.
        """
        self._metadata[key] = value
        return self

    # ---------- Templates ----------

    def load_template(self, name: str) -> "PromptBuilder":
        """Load a reusable prompt template and append it as an instruction block.

        Templates live under the configured 'paths.prompts' directory
        (e.g. `prompts/coding.txt`, `prompts/review.txt`).

        Args:
            name: The template's file name, without the '.txt'
                extension (e.g. "coding").

        Returns:
            This PromptBuilder, for fluent chaining.

        Raises:
            PromptTemplateNotFoundError: If no template file exists
                for `name`.
        """
        path = self._template_path(name)
        if not path.is_file():
            raise PromptTemplateNotFoundError(f"Invalid prompt template: '{name}' (expected '{path}').")

        try:
            content = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise PromptTemplateNotFoundError(f"Invalid prompt template: '{name}' ({exc}).") from exc

        self.append_instruction(content.strip())
        logger.info(f"Template loaded: '{name}'.")
        return self

    # ---------- Build / reset ----------

    def build(self) -> Prompt:
        """Validate and assemble the final, immutable Prompt.

        Returns:
            The composed Prompt.

        Raises:
            PromptValidationError: If the user prompt is missing, or
                the assembled prompt is empty, or it exceeds
                'prompt.max_prompt_size'.
        """
        context = self._compose_context()
        self._validate(context)
        logger.info("Prompt validated.")

        prompt = Prompt(
            system_prompt=self._system_prompt,
            user_prompt=self._user_prompt,
            context=context,
            metadata=dict(self._metadata),
        )
        logger.info(f"Prompt built: '{prompt.prompt_id}'.")
        return prompt

    def clear(self) -> "PromptBuilder":
        """Reset every part of this builder so it can be reused.

        Returns:
            This PromptBuilder, for fluent chaining.
        """
        self._system_prompt = ""
        self._user_prompt = ""
        self._context_parts.clear()
        self._memory_parts.clear()
        self._capability_parts.clear()
        self._instruction_parts.clear()
        self._metadata.clear()
        logger.info("Prompt cleared.")
        return self

    # ---------- Internal helpers ----------

    def _compose_context(self) -> str:
        """Assemble every context block in EP-017's fixed order.

        Order: Conversation Context -> Memory -> Capability Context ->
        Additional Instructions.

        Returns:
            The composed context text, or "" if nothing was appended.
        """
        blocks = [
            *self._context_parts,
            *self._memory_parts,
            *self._capability_parts,
            *self._instruction_parts,
        ]
        return "\n\n".join(blocks)

    def _validate(self, context: str) -> None:
        """Validate the in-progress prompt before it is built.

        Args:
            context: The already-composed context text.

        Raises:
            PromptValidationError: If the user prompt is missing, or
                the assembled prompt is empty, or it exceeds
                'prompt.max_prompt_size'.
        """
        if not self._user_prompt.strip():
            raise PromptValidationError("Missing user input: 'user_prompt' is required.")

        rendered = "\n\n".join(
            part for part in (self._system_prompt, context, self._user_prompt) if part
        )
        if not rendered.strip():
            raise PromptValidationError("Prompt is empty.")

        max_size = self.resolve_max_prompt_size(self._config)
        if max_size > 0 and len(rendered) > max_size:
            raise PromptValidationError(
                f"Prompt exceeds maximum size ({len(rendered)} > {max_size} characters)."
            )

    @staticmethod
    def resolve_max_prompt_size(config: Config) -> int:
        """Resolve 'prompt.max_prompt_size' from configuration.

        This is PromptBuilder's ONE size ceiling for the whole project
        (EP-018.5's "Single Source of Truth"). It is a `@staticmethod`,
        not an instance method, precisely so other components (see
        `resolve_document_budget()` below, and `PromptManager.
        document_budget()`) can call it without constructing a
        PromptBuilder -- there is exactly one place this value is
        computed, regardless of who needs it.

        Configuration mistakes must never surface as raw Python
        exceptions (EP-017.1's "Error Handling"): a non-numeric or
        otherwise unconvertible value is reported as a clear
        PromptValidationError instead of letting `int()` raise
        ValueError/TypeError.

        Args:
            config: The Config to resolve 'prompt.max_prompt_size'
                from.

        Returns:
            The configured maximum prompt size, in characters.

        Raises:
            PromptValidationError: If 'prompt.max_prompt_size' is set
                to a value that cannot be interpreted as an integer.
        """
        raw_value = config.get("prompt.max_prompt_size", DEFAULT_MAX_PROMPT_SIZE)
        try:
            return int(raw_value)
        except (TypeError, ValueError) as exc:
            raise PromptValidationError(
                "Invalid configuration: 'prompt.max_prompt_size' must be an integer "
                f"(got {raw_value!r} of type '{type(raw_value).__name__}')."
            ) from exc

    @staticmethod
    def resolve_document_budget(config: Config) -> int:
        """Derive the usable document budget from the prompt max size.

        EP-018.5 "Unified Prompt Budget": this is the ONLY place the
        document budget is computed anywhere in the project. It is a
        pure function of Config -- no provider-specific logic, no
        second independent ceiling -- so ContextLoader can consume it
        by Dependency Injection (see `ContextManager.__init__`'s
        `document_budget` parameter and `PromptManager.
        document_budget()`) instead of maintaining a budget of its
        own:

            Document Budget = Prompt Max Size - Reserved Space

        Reserved Space is the configurable headroom left for every
        other stage of EP-017's "Prompt Flow" that will sit alongside
        the documents in the final prompt: the system prompt, the
        conversation history, the user prompt, and generic
        (provider-agnostic) provider overhead. Each is independently
        configurable via 'prompt.reserved_*' so operators can tune it
        without touching code, and each falls back to a DEFAULT_
        RESERVED_* constant above when unset.

        Args:
            config: The Config to resolve the budget from.

        Returns:
            The number of characters ContextLoader may spend on
            documents, never less than zero.

        Raises:
            PromptValidationError: If 'prompt.max_prompt_size' or any
                'prompt.reserved_*' setting cannot be interpreted as
                an integer.
        """
        max_prompt_size = PromptBuilder.resolve_max_prompt_size(config)

        reserved_settings = (
            ("prompt.reserved_system_prompt", DEFAULT_RESERVED_SYSTEM_PROMPT),
            ("prompt.reserved_conversation_history", DEFAULT_RESERVED_CONVERSATION_HISTORY),
            ("prompt.reserved_user_prompt", DEFAULT_RESERVED_USER_PROMPT),
            ("prompt.reserved_provider_overhead", DEFAULT_RESERVED_PROVIDER_OVERHEAD),
        )
        reserved_total = 0
        for key, default in reserved_settings:
            raw_value = config.get(key, default)
            try:
                reserved_total += int(raw_value)
            except (TypeError, ValueError) as exc:
                raise PromptValidationError(
                    f"Invalid configuration: '{key}' must be an integer "
                    f"(got {raw_value!r} of type '{type(raw_value).__name__}')."
                ) from exc

        return max(0, max_prompt_size - reserved_total)

    @staticmethod
    def resolve_conversation_budget(config: Config) -> int:
        """Resolve the conversation-history budget reserved out of the prompt max size.

        EP-018.6 "Conversation Budget Enforcement": this is
        'prompt.reserved_conversation_history' -- the exact same
        setting `resolve_document_budget()` above already subtracts
        when deriving the document budget. EP-018.5 introduced that
        subtraction as *bookkeeping* only (headroom set aside so the
        document budget wouldn't overclaim space); it was never
        exposed for anything to actually enforce as a ceiling on the
        rendered Conversation Context. This method exposes that same
        reserved figure, unchanged, as its own budget so ContextLoader
        can enforce it (see `ContextManager`'s injected
        `conversation_budget` and `ContextLoader._render_conversation()`)
        -- deliberately not a second, independent configuration key:
        it is the one already-defined value, just finally consumed by
        something.

        Args:
            config: The Config to resolve
                'prompt.reserved_conversation_history' from.

        Returns:
            The number of characters ContextLoader may spend on
            rendered conversation history.

        Raises:
            PromptValidationError: If
                'prompt.reserved_conversation_history' cannot be
                interpreted as an integer.
        """
        raw_value = config.get(
            "prompt.reserved_conversation_history", DEFAULT_RESERVED_CONVERSATION_HISTORY
        )
        try:
            return int(raw_value)
        except (TypeError, ValueError) as exc:
            raise PromptValidationError(
                "Invalid configuration: 'prompt.reserved_conversation_history' must be an integer "
                f"(got {raw_value!r} of type '{type(raw_value).__name__}')."
            ) from exc

    def _template_path(self, name: str) -> Path:
        """Resolve the file path for template `name`.

        Args:
            name: The template's file name, without the '.txt'
                extension.

        Returns:
            The resolved template file path.
        """
        directory = Path(str(self._config.get("paths.prompts", DEFAULT_TEMPLATE_DIRECTORY)))
        return directory / f"{name}.txt"
