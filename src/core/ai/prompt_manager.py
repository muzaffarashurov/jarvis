"""PromptManager for EP-017 Prompt Engine.

PromptManager owns every Prompt object: it resolves the configurable
default system prompt ('prompt.*'), drives PromptBuilder (including
optional template loading) to compose a new Prompt, and registers,
looks up, lists, and removes Prompt objects. It performs no persistence
of its own -- EP-017 describes no storage file for prompts (unlike
Conversations, see `src/core/ai/conversation_manager.py`), so prompts
live in memory only, scoped to the process's lifetime.

EP-017.1 (stabilization): every public entry point that produces a
Prompt (`create()` and `build()`) routes through PromptBuilder, so
there is exactly one validation pipeline -- no Prompt can be
registered without passing PromptBuilder's checks (see
`src/core/ai/prompt_builder.py`).

This module has no dependency on any AI provider (Claude, Gemini,
OpenAI, Ollama, LM Studio, ...); it only knows about Prompt and
PromptBuilder. Only AIService is expected to bridge PromptManager and
ProviderManager (EP-017's "Provider Independence"). Callers may pass a
`provider_name` string into `build()` for the optional
'prompt.append_provider_name' setting -- this is plain caller-supplied
data, not an import of any provider module, so provider independence
is preserved.

Mirrors ConversationManager's thread-safety pattern, since
PromptManager is expected to be shared by the CLI, Telegram, Desktop
UI, REST API and Scheduler simultaneously (future EPs, per EP-017's
"Thread Safety" section).
"""

from __future__ import annotations

import os
import platform
from datetime import datetime
from threading import RLock
from typing import Any

from loguru import logger

from src.core.ai.prompt import Prompt
from src.core.ai.prompt_builder import PromptBuilder
from src.core.config import Config

__all__ = [
    "PromptManager",
    "PromptManagerError",
    "PromptNotFoundError",
]


class PromptManagerError(Exception):
    """Base class for PromptManager errors."""


class PromptNotFoundError(PromptManagerError):
    """Raised when an operation references a prompt_id that does not exist."""


class PromptManager:
    """Owns every Prompt object created by the Prompt Engine.

    Responsibilities:
        - Resolve the configurable default system prompt
          ('prompt.enabled', 'prompt.system_prompt',
          'prompt.append_datetime', 'prompt.append_provider_name',
          'prompt.append_os_information',
          'prompt.append_working_directory').
        - Drive a PromptBuilder to compose a new Prompt, in EP-017's
          fixed "Prompt Flow" order.
        - Register, look up, list, and remove Prompt objects.

    Reads only its own settings from Config ('prompt.*', plus
    'paths.prompts' which PromptBuilder resolves) and depends on no
    other Jarvis service, matching ConversationManager's architecture.
    """

    def __init__(self, config: Config) -> None:
        """Initialize the PromptManager.

        Args:
            config: Loaded application configuration, used to resolve
                every 'prompt.*' setting.
        """
        self._config = config
        self._prompts: dict[str, Prompt] = {}
        self._lock = RLock()

    # ---------- Configuration ----------

    def is_enabled(self) -> bool:
        """Return whether the configurable default system prompt is applied ('prompt.enabled')."""
        return bool(self._config.get("prompt.enabled", True))

    # ---------- Build ----------

    def build(
        self,
        user_prompt: str,
        context: list[str] | None = None,
        memory: list[str] | None = None,
        capabilities: list[str] | None = None,
        instructions: list[str] | None = None,
        system_prompt: str | None = None,
        template: str | None = None,
        provider_name: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Prompt:
        """Compose a new Prompt and register it.

        Applies the configurable default system prompt first, then
        `system_prompt` (if given) as an additional system-prompt
        block, then loads `template` (if given), then appends every
        context/memory/capabilities/instructions block, in EP-017's
        fixed order, then sets `user_prompt` last.

        Args:
            user_prompt: The end user's request text.
            context: Conversation-context blocks to append, in order.
            memory: Memory blocks to append, in order (reserved for
                the future Memory Engine).
            capabilities: Capability-context blocks to append, in
                order (reserved for the future Capability Registry).
            instructions: Additional-instruction blocks to append, in
                order.
            system_prompt: Extra system-prompt text, appended after
                the configurable default system prompt.
            template: Name of a reusable prompt template to load (see
                PromptBuilder.load_template()).
            provider_name: The active provider's name, used only when
                'prompt.append_provider_name' is enabled. Plain
                caller-supplied text -- PromptManager never imports a
                provider module.
            metadata: Arbitrary metadata to attach to the Prompt.

        Returns:
            The composed, registered Prompt.

        Raises:
            PromptValidationError: If `user_prompt` is missing/empty,
                the assembled prompt is empty, or it exceeds
                'prompt.max_prompt_size'.
            PromptTemplateNotFoundError: If `template` does not exist.
        """
        builder = PromptBuilder(config=self._config)

        system_parts = [part for part in (self._default_system_prompt(provider_name), system_prompt) if part]
        if system_parts:
            builder.set_system("\n\n".join(system_parts))

        if template:
            builder.load_template(template)

        for block in context or []:
            builder.append_context(block)
        for block in memory or []:
            builder.append_memory(block)
        for block in capabilities or []:
            builder.append_capabilities(block)
        for block in instructions or []:
            builder.append_instruction(block)
        for key, value in (metadata or {}).items():
            builder.append_metadata(key, value)

        builder.set_user(user_prompt)

        prompt = builder.build()
        return self._register(prompt)

    # ---------- Lifecycle ----------

    def create(
        self,
        system_prompt: str,
        user_prompt: str,
        context: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> Prompt:
        """Create and register a Prompt from already-composed parts.

        Useful when the caller has already fully composed the parts of
        a prompt (e.g. tests, or callers with no need for templates or
        the configurable default system prompt). Still routes through
        PromptBuilder (EP-017.1): `system_prompt`/`context` are passed
        through unchanged (this method applies neither the
        configurable default system prompt nor a template), but the
        resulting Prompt passes the exact same validation as `build()`
        -- there is only one prompt-creation/validation pipeline.

        Args:
            system_prompt: The system/instruction preamble text.
            user_prompt: The end user's request text.
            context: Already-composed context text.
            metadata: Arbitrary metadata to attach to the Prompt.

        Returns:
            The registered Prompt.

        Raises:
            PromptValidationError: If `user_prompt` is missing/empty,
                the assembled prompt is empty, or it exceeds
                'prompt.max_prompt_size'.
        """
        builder = PromptBuilder(config=self._config)
        if system_prompt:
            builder.set_system(system_prompt)
        if context:
            builder.append_context(context)
        for key, value in (metadata or {}).items():
            builder.append_metadata(key, value)
        builder.set_user(user_prompt)

        prompt = builder.build()
        return self._register(prompt)

    def get(self, prompt_id: str) -> Prompt | None:
        """Return a registered prompt, or None if not found.

        Args:
            prompt_id: The prompt identifier to look up.
        """
        with self._lock:
            return self._prompts.get(prompt_id)

    def exists(self, prompt_id: str) -> bool:
        """Return whether a prompt is registered under `prompt_id`."""
        with self._lock:
            return prompt_id in self._prompts

    def delete(self, prompt_id: str) -> bool:
        """Remove a registered prompt.

        Args:
            prompt_id: The prompt identifier to remove.

        Returns:
            True if a prompt was removed, False if it did not exist.
        """
        with self._lock:
            if prompt_id not in self._prompts:
                return False
            del self._prompts[prompt_id]
        logger.info(f"Prompt deleted: '{prompt_id}'.")
        return True

    def clear(self) -> int:
        """Remove every registered prompt.

        Returns:
            The number of prompts removed.
        """
        with self._lock:
            count = len(self._prompts)
            self._prompts.clear()
        logger.info(f"Prompt registry cleared ({count} prompts).")
        return count

    def list(self) -> list[Prompt]:
        """Return every registered prompt, in creation order."""
        with self._lock:
            return list(self._prompts.values())

    # ---------- Internal helpers ----------

    def _register(self, prompt: Prompt) -> Prompt:
        """Register `prompt` under its `prompt_id`.

        Args:
            prompt: The Prompt to register.

        Returns:
            `prompt`, unchanged.
        """
        with self._lock:
            self._prompts[prompt.prompt_id] = prompt
        logger.info(f"Prompt created: '{prompt.prompt_id}'.")
        return prompt

    def _default_system_prompt(self, provider_name: str | None) -> str:
        """Resolve the configurable default system prompt.

        Args:
            provider_name: The active provider's name, appended only
                when 'prompt.append_provider_name' is enabled.

        Returns:
            The composed default system prompt text, or "" if
            'prompt.enabled' is False or nothing is configured.
        """
        if not self.is_enabled():
            return ""

        parts: list[str] = []

        configured = str(self._config.get("prompt.system_prompt", "") or "")
        if configured:
            parts.append(configured)

        if bool(self._config.get("prompt.append_datetime", False)):
            parts.append(f"Current datetime: {datetime.now().isoformat()}")

        if bool(self._config.get("prompt.append_provider_name", False)) and provider_name:
            parts.append(f"Provider: {provider_name}")

        if bool(self._config.get("prompt.append_os_information", False)):
            parts.append(f"Operating system: {platform.platform()}")

        if bool(self._config.get("prompt.append_working_directory", False)):
            parts.append(f"Working directory: {os.getcwd()}")

        return "\n".join(parts)
