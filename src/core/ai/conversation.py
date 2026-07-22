"""Conversation domain model for EP-016 Conversation Engine.

Conversation owns a single ordered list of Message objects plus the
small amount of metadata (id, title, timestamps) describing it. It
performs no persistence of its own (see ConversationManager) and no
provider-specific formatting -- providers are responsible for
converting `messages()` into their own API format, matching this
project's Single Source Of Truth rule and EP-016's "Provider
Independence".

Mirrors MemoryStore's self-contained thread-safety pattern (see
src/core/memory/memory_store.py), since a single Conversation can be
mutated concurrently by multiple callers (CLI, Telegram, Desktop UI,
REST API, Scheduler) sharing the same conversation_id.
"""

from __future__ import annotations

import uuid
from threading import RLock
from typing import Any

from loguru import logger

from src.core.ai.message import Message, MessageRole, _parse_timestamp, utc_now

DEFAULT_TITLE: str = "Untitled Conversation"


class Conversation:
    """A single, ordered, thread-safe sequence of Message objects.

    Responsibilities:
        - Own an ordered list of Message objects.
        - Append new messages for each supported role.
        - Enforce an optional maximum message count, truncating the
          oldest messages first once exceeded.
        - Serialize/deserialize itself to/from a plain dict snapshot.
    """

    def __init__(
        self,
        conversation_id: str | None = None,
        title: str | None = None,
        created_at: Any = None,
        updated_at: Any = None,
        messages: list[Message] | None = None,
        max_messages: int | None = None,
    ) -> None:
        """Initialize a Conversation.

        Args:
            conversation_id: Stable, unique identifier. A new UUID4
                hex string is generated if not given.
            title: Human-readable display name. Defaults to
                DEFAULT_TITLE if not given.
            created_at: When this conversation was first created.
                Defaults to now (UTC).
            updated_at: When this conversation was last modified.
                Defaults to `created_at`.
            messages: Initial messages, in order. Defaults to empty.
            max_messages: Maximum number of messages to retain. When
                exceeded, the oldest messages are dropped first
                ('conversation.truncate_strategy'). None means
                unbounded; owned and supplied by ConversationManager
                from 'conversation.max_messages' so this class never
                depends on Config directly.
        """
        now = created_at or utc_now()
        self._conversation_id = conversation_id or uuid.uuid4().hex
        self._title = title or DEFAULT_TITLE
        self._created_at = now
        self._updated_at = updated_at or now
        self._messages: list[Message] = list(messages) if messages else []
        self._max_messages = max_messages
        self._lock = RLock()
        self._truncate_locked()

    # ---------- Identity / metadata ----------

    @property
    def conversation_id(self) -> str:
        """Return this conversation's stable, unique identifier."""
        return self._conversation_id

    @property
    def title(self) -> str:
        """Return this conversation's human-readable display name."""
        with self._lock:
            return self._title

    @title.setter
    def title(self, value: str) -> None:
        """Rename this conversation's display name.

        Args:
            value: The new title.
        """
        with self._lock:
            self._title = value
            self._updated_at = utc_now()

    @property
    def created_at(self) -> Any:
        """Return when this conversation was first created."""
        return self._created_at

    @property
    def updated_at(self) -> Any:
        """Return when this conversation was last modified."""
        with self._lock:
            return self._updated_at

    @property
    def max_messages(self) -> int | None:
        """Return the configured maximum message count, or None if unbounded."""
        return self._max_messages

    # ---------- Append ----------

    def append_user(self, content: str, metadata: dict[str, Any] | None = None) -> Message:
        """Append a USER message.

        Args:
            content: The message text.
            metadata: Optional caller-supplied metadata.

        Returns:
            The appended Message.
        """
        return self._append(MessageRole.USER, content, metadata)

    def append_assistant(self, content: str, metadata: dict[str, Any] | None = None) -> Message:
        """Append an ASSISTANT message.

        Args:
            content: The message text.
            metadata: Optional caller-supplied metadata.

        Returns:
            The appended Message.
        """
        return self._append(MessageRole.ASSISTANT, content, metadata)

    def append_system(self, content: str, metadata: dict[str, Any] | None = None) -> Message:
        """Append a SYSTEM message.

        Args:
            content: The message text.
            metadata: Optional caller-supplied metadata.

        Returns:
            The appended Message.
        """
        return self._append(MessageRole.SYSTEM, content, metadata)

    def append_tool(self, content: str, metadata: dict[str, Any] | None = None) -> Message:
        """Append a TOOL message.

        Reserved for future MCP / Tool Calling support (EP-018).

        Args:
            content: The message text.
            metadata: Optional caller-supplied metadata.

        Returns:
            The appended Message.
        """
        return self._append(MessageRole.TOOL, content, metadata)

    # ---------- Read / mutate ----------

    def clear(self) -> int:
        """Remove every message from this conversation.

        Returns:
            The number of messages removed.
        """
        with self._lock:
            count = len(self._messages)
            self._messages.clear()
            self._updated_at = utc_now()
        logger.info(f"Conversation cleared: '{self._conversation_id}' ({count} messages).")
        return count

    def size(self) -> int:
        """Return the number of messages currently stored."""
        with self._lock:
            return len(self._messages)

    def last_message(self) -> Message | None:
        """Return the most recently appended message, or None if empty."""
        with self._lock:
            return self._messages[-1] if self._messages else None

    def messages(self) -> list[Message]:
        """Return a copy of every message, in chronological order."""
        with self._lock:
            return list(self._messages)

    # ---------- Serialization ----------

    def to_dict(self) -> dict[str, Any]:
        """Serialize this conversation to a plain, JSON-ready dictionary.

        Returns:
            A dictionary representation suitable for `json.dump`.
        """
        with self._lock:
            return {
                "conversation_id": self._conversation_id,
                "title": self._title,
                "created_at": self._created_at.isoformat(),
                "updated_at": self._updated_at.isoformat(),
                "messages": [message.to_dict() for message in self._messages],
            }

    @classmethod
    def from_dict(cls, data: dict[str, Any], max_messages: int | None = None) -> "Conversation":
        """Reconstruct a Conversation from a dictionary produced by `to_dict`.

        Args:
            data: A dictionary as produced by `to_dict` (e.g. loaded
                from the conversations storage file).
            max_messages: Maximum number of messages to retain, as
                resolved by ConversationManager from
                'conversation.max_messages'.

        Returns:
            The reconstructed Conversation.

        Raises:
            KeyError: If a required field is missing.
            ValueError: If a message's `role` is unsupported, or a
                timestamp is not valid ISO-8601.
            TypeError: If a field has an unexpected type.
        """
        raw_messages = data.get("messages", [])
        if not isinstance(raw_messages, list):
            raise TypeError("'messages' must be a list.")

        return cls(
            conversation_id=str(data["conversation_id"]),
            title=str(data.get("title") or DEFAULT_TITLE),
            created_at=_parse_timestamp(data.get("created_at") or utc_now()),
            updated_at=_parse_timestamp(data.get("updated_at") or utc_now()),
            messages=[Message.from_dict(raw) for raw in raw_messages],
            max_messages=max_messages,
        )

    # ---------- Internal helpers ----------

    def _append(self, role: MessageRole, content: str, metadata: dict[str, Any] | None) -> Message:
        """Append a message with the given role, enforcing `max_messages`.

        Caller must not already hold `self._lock`.

        Args:
            role: The role authoring this message.
            content: The message text.
            metadata: Optional caller-supplied metadata.

        Returns:
            The appended Message.
        """
        message = Message(role=role, content=content, metadata=metadata)
        with self._lock:
            self._messages.append(message)
            self._updated_at = utc_now()
            self._truncate_locked()
        return message

    def _truncate_locked(self) -> None:
        """Drop the oldest messages once `max_messages` is exceeded.

        Caller must already hold `self._lock`. No-op when
        `max_messages` is None (unbounded).
        """
        if self._max_messages is None or self._max_messages <= 0:
            return
        overflow = len(self._messages) - self._max_messages
        if overflow > 0:
            del self._messages[:overflow]
