"""Context domain model for EP-018 Context Loader.

Context is the smallest unit the Context Loader works with: a single,
immutable snapshot of everything the Prompt Engine should know about
the current situation (conversation history, project docs, working
directory, active process, and any additional caller-supplied
information). It owns no gathering logic (see ContextLoader) and no
registry/lifecycle logic (see ContextManager) -- it mirrors the role
of `src/core/ai/prompt.py` relative to `src/core/ai/prompt_builder.py`
and `src/core/ai/prompt_manager.py`.

This module has no dependency on any AI provider (Claude, Gemini,
OpenAI, Ollama, LM Studio, ...) and no dependency on Config. Providers
never see a Context object -- only `Context.rendered`, folded into the
Prompt Engine's "Conversation Context" stage (see
`src/services/ai_service.py`).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now() -> datetime:
    """Return the current time as a timezone-aware UTC datetime.

    Returns:
        The current UTC datetime.
    """
    return datetime.now(timezone.utc)


def new_context_id() -> str:
    """Return a new, unique context identifier.

    Returns:
        A UUID4 hex string.
    """
    return uuid.uuid4().hex


@dataclass(frozen=True)
class Context:
    """A single, immutable snapshot of the current execution context.

    Every field is optional and defaults to "empty" (EP-018's "Every
    source must be optional. Missing sources must never cause
    failures.") -- unlike Prompt, a Context with every field empty is
    perfectly valid.

    Attributes:
        context_id: Unique, stable identifier for this context.
        conversation_context: Prior conversation history, already
            rendered as text (excludes the just-appended current
            turn -- see ContextLoader). "" if unavailable/disabled.
        project_context: Content of detected project documentation
            files (e.g. README.md), already rendered as text. "" if
            no project files were found or the source is disabled.
        working_directory: A short, labeled line naming the current
            working directory. "" if the source is disabled.
        active_process: A short, labeled line naming the
            caller-supplied active process, if any. "" if none given.
        loaded_documents: Names of the project files that were
            actually loaded, for audit/cache purposes. Empty tuple if
            none were loaded.
        metadata: Everything else: 'configuration' and 'environment'
            text (EP-018's other two Loading Order stages, which have
            no dedicated field) plus any caller-supplied 'additional'
            text and arbitrary extra data. Empty dict if none given.
        created_at: When this context was built.
    """

    context_id: str = field(default_factory=new_context_id)
    conversation_context: str = ""
    project_context: str = ""
    working_directory: str = ""
    active_process: str = ""
    loaded_documents: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=utc_now)

    @property
    def rendered(self) -> str:
        """Return the final, flat context text handed to the Prompt Engine.

        Assembles every stage in EP-018's fixed "Loading Order":
        Conversation Context -> Project Context -> Working Directory
        -> Configuration -> Environment -> Active Process ->
        Additional Context, skipping any stage that is empty. This is
        what `Context` contributes as one block of the Prompt Engine's
        "Conversation Context" stage (EP-017) -- providers never see a
        Context object, only this text.

        Returns:
            The composed context text.
        """
        parts = [
            self.conversation_context,
            self.project_context,
            self.working_directory,
            str(self.metadata.get("configuration", "")),
            str(self.metadata.get("environment", "")),
            self.active_process,
            str(self.metadata.get("additional", "")),
        ]
        return "\n\n".join(part for part in parts if part)
