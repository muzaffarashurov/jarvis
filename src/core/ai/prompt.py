"""Prompt domain model for EP-017 Prompt Engine.

Prompt is the smallest unit the Prompt Engine works with: a single,
immutable, fully-composed request ready to be handed to a provider. It
owns no composition logic (see PromptBuilder) and no registry/lifecycle
logic (see PromptManager) -- it mirrors the role of
`src/core/ai/message.py` relative to `src/core/ai/conversation.py`.

This module has no dependency on any AI provider (Claude, Gemini,
OpenAI, Ollama, LM Studio, ...) and no dependency on Config, matching
EP-017's "Provider Independence". Providers are responsible for
sending `Prompt.rendered` -- Prompt itself never talks to a provider.
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


def new_prompt_id() -> str:
    """Return a new, unique prompt identifier.

    Returns:
        A UUID4 hex string.
    """
    return uuid.uuid4().hex


@dataclass(frozen=True)
class Prompt:
    """A single, immutable, fully-composed prompt.

    Attributes:
        system_prompt: The system/instruction preamble, already
            resolved from configuration and/or caller input.
        user_prompt: The end user's request text.
        context: Everything assembled between the system prompt and
            the user prompt, already ordered per EP-017's fixed
            "Prompt Flow": Conversation Context, then Memory (future),
            then Capability Context (future), then Additional
            Instructions. Empty string if nothing was appended.
        prompt_id: Unique, stable identifier for this prompt.
        metadata: Optional, arbitrary caller-supplied metadata (e.g.
            provider name, template used). Empty dict if none given.
        created_at: When this prompt was built.
    """

    system_prompt: str
    user_prompt: str
    context: str = ""
    prompt_id: str = field(default_factory=new_prompt_id)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=utc_now)

    @property
    def rendered(self) -> str:
        """Return the final, flat prompt text sent to a provider.

        Assembles `system_prompt`, `context` and `user_prompt`, in
        that fixed order (EP-017's "Prompt Flow"), skipping any part
        that is empty. This is the "one final prompt" providers
        receive -- providers never see the individual parts.

        Returns:
            The composed prompt text.
        """
        parts = [part for part in (self.system_prompt, self.context, self.user_prompt) if part]
        return "\n\n".join(parts)
