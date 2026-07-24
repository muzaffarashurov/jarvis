"""ContextManager for EP-018 Context Loader.

ContextManager owns every Context object: it holds one ContextLoader
instance (so its project-files cache survives across requests -- see
`src/core/ai/context_loader.py`), drives it to compose a new Context,
and registers, looks up, lists, refreshes, and removes Context objects.
It performs no persistence of its own -- EP-018 describes no storage
file for contexts (unlike Conversations), so contexts live in memory
only, scoped to the process's lifetime.

This module has no dependency on any AI provider (Claude, Gemini,
OpenAI, Ollama, LM Studio, ...); it depends only on Config, Context and
ContextLoader. Only AIService is expected to bridge ContextManager and
PromptManager (EP-018's "Provider Independence").

Mirrors PromptManager/ConversationManager's thread-safety pattern,
since ContextManager is expected to be shared by the CLI, Telegram,
Desktop UI, REST API and Scheduler simultaneously (future EPs, per
EP-018's "Thread Safety" section).
"""

from __future__ import annotations

from threading import RLock

from loguru import logger

from src.core.ai.context import Context
from src.core.ai.context_loader import ContextLoader
from src.core.ai.conversation import Conversation
from src.core.config import Config

__all__ = [
    "ContextManager",
    "ContextManagerError",
    "ContextNotFoundError",
]


class ContextManagerError(Exception):
    """Base class for ContextManager errors."""


class ContextNotFoundError(ContextManagerError):
    """Raised when `refresh()` references a context_id that does not exist."""


class ContextManager:
    """Owns every Context object created by the Context Loader.

    Responsibilities:
        - Drive one shared ContextLoader (so its project-files cache is
          reused across requests) to compose a new Context.
        - Register, look up, list, refresh, and remove Context objects.
        - Remember each context's sources (conversation, active
          process) so `refresh()` can rebuild it later without the
          caller needing to resupply everything.

    Reads only its own settings from Config ('context.*', plus the
    settings ContextLoader itself resolves) and depends on no other
    Jarvis service, matching PromptManager's architecture.
    """

    def __init__(self, config: Config) -> None:
        """Initialize the ContextManager.

        Args:
            config: Loaded application configuration, used to resolve
                every 'context.*' setting (directly, and via the
                shared ContextLoader).
        """
        self._config = config
        self._loader = ContextLoader(config=config)
        self._contexts: dict[str, Context] = {}
        self._sources: dict[str, tuple[Conversation | None, str | None]] = {}
        self._lock = RLock()

    # ---------- Configuration ----------

    def is_enabled(self) -> bool:
        """Return whether the Context Loader subsystem is enabled ('context.enabled')."""
        return self._loader.is_enabled()

    # ---------- Lifecycle ----------

    def create(
        self,
        conversation: Conversation | None = None,
        active_process: str | None = None,
        additional: list[str] | None = None,
    ) -> Context:
        """Compose a new Context from its sources and register it.

        Args:
            conversation: The current Conversation (EP-016), for the
                "Conversation Context" stage. None if unavailable.
            active_process: A caller-supplied description of the
                active process, for the "Active Process" stage.
            additional: Extra "Additional Context" blocks to append,
                in order.

        Returns:
            The composed, registered Context.
        """
        with self._lock:
            self._loader.clear()
            for block in additional or []:
                self._loader.append(block)
            context = self._loader.load(conversation=conversation, active_process=active_process).build()
            self._contexts[context.context_id] = context
            self._sources[context.context_id] = (conversation, active_process)
        logger.info(f"Context created: '{context.context_id}'.")
        return context

    def get(self, context_id: str) -> Context | None:
        """Return a registered context, or None if not found.

        Args:
            context_id: The context identifier to look up.
        """
        with self._lock:
            return self._contexts.get(context_id)

    def exists(self, context_id: str) -> bool:
        """Return whether a context is registered under `context_id`."""
        with self._lock:
            return context_id in self._contexts

    def delete(self, context_id: str) -> bool:
        """Remove a registered context.

        Args:
            context_id: The context identifier to remove.

        Returns:
            True if a context was removed, False if it did not exist.
        """
        with self._lock:
            if context_id not in self._contexts:
                return False
            del self._contexts[context_id]
            self._sources.pop(context_id, None)
        logger.info(f"Context deleted: '{context_id}'.")
        return True

    def clear(self) -> int:
        """Remove every registered context.

        Returns:
            The number of contexts removed.
        """
        with self._lock:
            count = len(self._contexts)
            self._contexts.clear()
            self._sources.clear()
        logger.info(f"Context registry cleared ({count} contexts).")
        return count

    def list(self) -> list[Context]:
        """Return every registered context, in creation order."""
        with self._lock:
            return list(self._contexts.values())

    def refresh(
        self,
        context_id: str,
        conversation: Conversation | None = None,
        active_process: str | None = None,
    ) -> Context:
        """Rebuild a registered context from its (possibly updated) sources.

        Bypasses the project-files cache (so file changes are always
        picked up), then replaces the registered entry in place, in
        the same context_id. `conversation`/`active_process` override
        the values used at `create()` time (or the last `refresh()`);
        omit either to keep reusing the previous value.

        Args:
            context_id: The context identifier to refresh.
            conversation: A fresher Conversation to use, or None to
                keep reusing the previously supplied one.
            active_process: A fresher active-process description, or
                None to keep reusing the previously supplied one.

        Returns:
            The rebuilt Context, registered under the same context_id.

        Raises:
            ContextNotFoundError: If `context_id` is not registered.
        """
        with self._lock:
            if context_id not in self._contexts:
                raise ContextNotFoundError(f"Unknown context: '{context_id}'.")

            previous_conversation, previous_active_process = self._sources[context_id]
            resolved_conversation = conversation if conversation is not None else previous_conversation
            resolved_active_process = active_process if active_process is not None else previous_active_process

            self._loader.refresh()
            self._loader.clear()
            context = self._loader.load(
                conversation=resolved_conversation,
                active_process=resolved_active_process,
            ).build(context_id=context_id)

            self._contexts[context_id] = context
            self._sources[context_id] = (resolved_conversation, resolved_active_process)
        logger.info(f"Context refreshed: '{context_id}'.")
        return context
