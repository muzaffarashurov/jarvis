"""Message domain model for EP-016 Conversation Engine.

Message is the smallest unit the Conversation Engine works with: a
single, immutable turn in a conversation. It owns no storage and no
business logic -- it mirrors the role of `src/core/scheduler/job.py`
and `src/core/memory/context.py` relative to their respective
registries/stores.

This module has no dependency on any AI provider (Claude, Gemini,
OpenAI, Ollama, LM Studio, ...) and no dependency on Config. Providers
are responsible for converting Message objects into their own API
format (see EP-016's "Provider Independence").
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


def utc_now() -> datetime:
    """Return the current time as a timezone-aware UTC datetime.

    Returns:
        The current UTC datetime.
    """
    return datetime.now(timezone.utc)


def new_message_id() -> str:
    """Return a new, unique message identifier.

    Returns:
        A UUID4 hex string.
    """
    return uuid.uuid4().hex


def _parse_timestamp(value: Any) -> datetime:
    """Parse an ISO-8601 string (or pass through a datetime) into a datetime.

    Args:
        value: An ISO-8601 timestamp string or an existing datetime.

    Returns:
        The parsed datetime.

    Raises:
        ValueError: If `value` is a string that is not valid ISO-8601.
        TypeError: If `value` is neither a string nor a datetime.
    """
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    raise TypeError(f"Expected a datetime or ISO-8601 string, got {type(value).__name__}.")


class MessageRole(str, Enum):
    """Supported roles a Message can be authored by.

    Attributes:
        SYSTEM: A system/instruction message.
        USER: A message authored by the end user.
        ASSISTANT: A reply authored by an AI provider.
        TOOL: Reserved for future MCP / Tool Calling support (EP-018).
    """

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass(frozen=True)
class Message:
    """A single, immutable turn in a Conversation.

    Attributes:
        message_id: Unique, stable identifier for this message.
        role: Who authored this message (see MessageRole).
        content: The message text.
        timestamp: When this message was created.
        metadata: Optional, arbitrary caller-supplied metadata (e.g.
            provider name, latency, token counts). None if not given.
    """

    role: MessageRole
    content: str
    message_id: str = field(default_factory=new_message_id)
    timestamp: datetime = field(default_factory=utc_now)
    metadata: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize this message to a plain, JSON-ready dictionary.

        Returns:
            A dictionary representation suitable for `json.dump`.
        """
        return {
            "message_id": self.message_id,
            "role": self.role.value,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Message":
        """Reconstruct a Message from a dictionary produced by `to_dict`.

        Args:
            data: A dictionary as produced by `to_dict` (e.g. loaded
                from the conversations storage file).

        Returns:
            The reconstructed Message.

        Raises:
            KeyError: If a required field is missing.
            ValueError: If `role` is not a supported MessageRole, or
                `timestamp` is not valid ISO-8601.
            TypeError: If a field has an unexpected type.
        """
        metadata = data.get("metadata")
        return cls(
            role=MessageRole(str(data["role"])),
            content=str(data["content"]),
            message_id=str(data.get("message_id") or new_message_id()),
            timestamp=_parse_timestamp(data.get("timestamp") or utc_now()),
            metadata=dict(metadata) if isinstance(metadata, dict) else None,
        )
