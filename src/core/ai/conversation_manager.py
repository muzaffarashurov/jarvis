"""ConversationManager for EP-016 Conversation Engine.

ConversationManager owns every active Conversation: creation, lookup,
renaming, deletion, current-conversation selection, and disk-backed
persistence. It reuses the same JSON-file persistence approach already
established by MemoryService (see src/services/memory_service.py) --
`json.dump`/`json.load` against a single configured file -- rather
than introducing a new persistence layer, per EP-016's "Reuse the
existing persistence architecture. Do NOT duplicate persistence code."

This module has no dependency on any AI provider (Claude, Gemini,
OpenAI, Ollama, LM Studio, ...); it only knows about Message and
Conversation. Only AIService is expected to bridge ConversationManager
and ProviderManager (EP-016's "Provider Independence").

Mirrors ProviderRegistry's thread-safety pattern (see
src/core/ai/provider_registry.py), since ConversationManager is
expected to be shared by the CLI, Telegram, Desktop UI, REST API and
Scheduler simultaneously (future EPs).
"""

from __future__ import annotations

import json
from pathlib import Path
from threading import RLock
from typing import Any

from loguru import logger

from src.core.ai.conversation import Conversation
from src.core.config import Config

DEFAULT_STORAGE_FILE: str = "data/database/conversations.json"
DEFAULT_EXPORT_FILE: str = "data/output/conversation.json"
DEFAULT_CONVERSATION_NAME: str = "default"


class ConversationManagerError(Exception):
    """Base class for ConversationManager errors."""


class ConversationNotFoundError(ConversationManagerError):
    """Raised when an operation references a conversation name that does not exist."""


class ConversationAlreadyExistsError(ConversationManagerError):
    """Raised when creating or renaming a conversation to a name already in use."""


class ConversationLimitExceededError(ConversationManagerError):
    """Raised when creating a conversation would exceed 'conversation.max_conversations'."""


class ConversationManager:
    """Owns every active Conversation and its disk-backed persistence.

    Responsibilities:
        - Create, look up, rename, and delete conversations by name.
        - Track and resolve the currently selected conversation,
          defaulting to "default" when none has been explicitly
          selected (EP-016's "Default Conversation").
        - Load conversations from 'conversation.storage_file' on
          startup, and save them back whenever 'conversation.auto_save'
          is enabled.
        - Export/import a single conversation to/from a JSON file.

    Reads only its own settings from Config ('conversation.*') and
    depends on no other Jarvis service, matching MemoryStore's
    architecture (src/core/memory/memory_store.py).
    """

    def __init__(self, config: Config) -> None:
        """Initialize the ConversationManager and load persisted conversations.

        Args:
            config: Loaded application configuration, used to resolve
                every 'conversation.*' setting.
        """
        self._config = config
        self._conversations: dict[str, Conversation] = {}
        self._current_name: str | None = None
        self._lock = RLock()

        if self.is_enabled():
            self.load()
            with self._lock:
                if DEFAULT_CONVERSATION_NAME not in self._conversations:
                    self._create_locked(DEFAULT_CONVERSATION_NAME)
            self._autosave()

    # ---------- Configuration ----------

    def is_enabled(self) -> bool:
        """Return whether the Conversation Engine is enabled ('conversation.enabled')."""
        return bool(self._config.get("conversation.enabled", True))

    def is_auto_save(self) -> bool:
        """Return whether automatic persistence is on ('conversation.auto_save')."""
        return bool(self._config.get("conversation.auto_save", True))

    def max_messages(self) -> int:
        """Resolve the per-conversation message cap ('conversation.max_messages')."""
        return int(self._config.get("conversation.max_messages", 100))

    def max_conversations(self) -> int:
        """Resolve the maximum number of conversations allowed ('conversation.max_conversations')."""
        return int(self._config.get("conversation.max_conversations", 100))

    def truncate_strategy(self) -> str:
        """Resolve the configured truncation strategy ('conversation.truncate_strategy')."""
        return str(self._config.get("conversation.truncate_strategy", "oldest"))

    def storage_path(self) -> Path:
        """Resolve the configured persistence file ('conversation.storage_file')."""
        return Path(str(self._config.get("conversation.storage_file", DEFAULT_STORAGE_FILE)))

    # ---------- Lifecycle ----------

    def create(self, name: str) -> Conversation:
        """Create and register a new, empty conversation.

        Args:
            name: The unique name to register the conversation under.

        Returns:
            The newly created Conversation.

        Raises:
            ConversationAlreadyExistsError: If `name` is already registered.
            ConversationLimitExceededError: If 'conversation.max_conversations'
                would be exceeded.
        """
        with self._lock:
            if name in self._conversations:
                raise ConversationAlreadyExistsError(f"Conversation already exists: '{name}'.")
            if len(self._conversations) >= self.max_conversations():
                raise ConversationLimitExceededError(
                    f"Conversation limit exceeded (max={self.max_conversations()})."
                )
            conversation = self._create_locked(name)
        self._autosave()
        return conversation

    def get(self, name: str) -> Conversation | None:
        """Return a registered conversation, or None if not found.

        Args:
            name: The conversation name to look up.
        """
        with self._lock:
            return self._conversations.get(name)

    def exists(self, name: str) -> bool:
        """Return whether a conversation is registered under `name`."""
        with self._lock:
            return name in self._conversations

    def delete(self, name: str) -> bool:
        """Remove a registered conversation.

        Args:
            name: The conversation name to remove.

        Returns:
            True if a conversation was removed, False if it did not exist.
        """
        with self._lock:
            if name not in self._conversations:
                return False
            del self._conversations[name]
            if self._current_name == name:
                self._current_name = None
        logger.info(f"Conversation deleted: '{name}'.")
        self._autosave()
        return True

    def clear(self, name: str | None = None) -> int:
        """Remove every message from a conversation.

        Args:
            name: The conversation to clear. Defaults to the current
                conversation (EP-016's "Default Conversation").

        Returns:
            The number of messages removed.

        Raises:
            ConversationNotFoundError: If `name` does not exist.
        """
        with self._lock:
            target = name if name is not None else self._resolve_current_name_locked()
            conversation = self._conversations.get(target)
            if conversation is None:
                raise ConversationNotFoundError(f"Unknown conversation: '{target}'.")
        count = conversation.clear()
        self._autosave()
        return count

    def rename(self, old_name: str, new_name: str) -> Conversation:
        """Rename a registered conversation.

        Args:
            old_name: The conversation's current name.
            new_name: The name to rename it to.

        Returns:
            The renamed Conversation.

        Raises:
            ConversationNotFoundError: If `old_name` does not exist.
            ConversationAlreadyExistsError: If `new_name` is already in use.
        """
        with self._lock:
            if old_name not in self._conversations:
                raise ConversationNotFoundError(f"Unknown conversation: '{old_name}'.")
            if new_name in self._conversations:
                raise ConversationAlreadyExistsError(f"Conversation already exists: '{new_name}'.")
            conversation = self._conversations.pop(old_name)
            conversation.title = new_name
            self._conversations[new_name] = conversation
            if self._current_name == old_name:
                self._current_name = new_name
        logger.info(f"Conversation renamed: '{old_name}' -> '{new_name}'.")
        self._autosave()
        return conversation

    def list(self) -> list[Conversation]:
        """Return every registered conversation, ordered by name.

        Returns:
            A list of Conversation instances sorted by their (current) title.
        """
        with self._lock:
            return sorted(self._conversations.values(), key=lambda conversation: conversation.title)

    def current(self) -> Conversation:
        """Return the currently selected conversation.

        Falls back to (and lazily creates, if needed) "default" when
        no conversation has been explicitly selected, per EP-016's
        "Default Conversation".

        Returns:
            The currently active Conversation.
        """
        with self._lock:
            name = self._resolve_current_name_locked()
            conversation = self._conversations.get(name)
            if conversation is None:
                conversation = self._create_locked(name)
                created = True
            else:
                created = False
        if created:
            self._autosave()
        return conversation

    def set_current(self, name: str) -> None:
        """Select `name` as the currently active conversation.

        Args:
            name: The conversation name to select.

        Raises:
            ConversationNotFoundError: If `name` does not exist.
        """
        with self._lock:
            if name not in self._conversations:
                raise ConversationNotFoundError(f"Unknown conversation: '{name}'.")
            self._current_name = name
        logger.info(f"Conversation selected: '{name}'.")
        self._autosave()

    # ---------- Export / Import ----------

    def export(self, name: str | None = None, path: str | None = None) -> Path:
        """Write a single conversation to a JSON file.

        Args:
            name: The conversation to export. Defaults to the current
                conversation.
            path: Destination file path. Defaults to
                'data/output/conversation.json'.

        Returns:
            The path the conversation was written to.

        Raises:
            ConversationNotFoundError: If `name` does not exist.
        """
        with self._lock:
            target = name if name is not None else self._resolve_current_name_locked()
            conversation = self._conversations.get(target)
            if conversation is None:
                raise ConversationNotFoundError(f"Unknown conversation: '{target}'.")
            data = conversation.to_dict()

        destination = Path(path) if path else Path(DEFAULT_EXPORT_FILE)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("w", encoding="utf-8") as file:
            json.dump(data, file, indent=2)
        logger.info(f"Conversation exported: '{target}' -> '{destination}'.")
        return destination

    def import_(self, path: str | None = None) -> Conversation:
        """Load a previously exported conversation from a JSON file.

        An existing conversation with the same name is overwritten.

        Args:
            path: Source file path. Defaults to
                'data/output/conversation.json'.

        Returns:
            The imported Conversation.

        Raises:
            FileNotFoundError: If the source file does not exist.
            ConversationManagerError: If the file does not contain a
                valid conversation snapshot.
        """
        source = Path(path) if path else Path(DEFAULT_EXPORT_FILE)
        if not source.exists():
            raise FileNotFoundError(f"Import file not found: '{source}'.")

        try:
            with source.open("r", encoding="utf-8") as file:
                raw = json.load(file)
        except (OSError, json.JSONDecodeError) as exc:
            raise ConversationManagerError(f"Conversation import failed: {exc}") from exc

        if not isinstance(raw, dict):
            raise ConversationManagerError(
                f"Conversation import failed: '{source}' must contain a JSON object."
            )

        try:
            conversation = Conversation.from_dict(raw, max_messages=self.max_messages())
        except (KeyError, TypeError, ValueError) as exc:
            raise ConversationManagerError(f"Conversation import failed: invalid data ({exc}).") from exc

        with self._lock:
            self._conversations[conversation.title] = conversation
        logger.info(f"Conversation imported: '{conversation.title}' from '{source}'.")
        self._autosave()
        return conversation

    # ---------- Persistence ----------

    def save(self) -> bool:
        """Write every conversation to 'conversation.storage_file'.

        No-op (returns False) if the Conversation Engine is disabled.

        Returns:
            True if the save succeeded, False otherwise.
        """
        if not self.is_enabled():
            return False

        target = self.storage_path()
        with self._lock:
            payload: dict[str, Any] = {
                "current": self._current_name,
                "conversations": {
                    name: conversation.to_dict() for name, conversation in self._conversations.items()
                },
            }

        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("w", encoding="utf-8") as file:
                json.dump(payload, file, indent=2)
        except OSError as exc:
            logger.error(f"Conversation storage save failed: {exc}")
            return False

        logger.info(
            f"Conversation storage saved: {len(payload['conversations'])} conversations to '{target}'."
        )
        return True

    def load(self) -> None:
        """Load conversations from 'conversation.storage_file', if present.

        A missing or invalid storage file is logged and skipped rather
        than raised, since a first run has no prior storage file yet.
        """
        path = self.storage_path()
        if not path.exists():
            return

        try:
            with path.open("r", encoding="utf-8") as file:
                raw = json.load(file)
        except (OSError, json.JSONDecodeError) as exc:
            logger.error(f"Conversation storage load failed: {exc}")
            return

        if not isinstance(raw, dict):
            logger.error(f"Conversation storage load failed: '{path}' must contain a JSON object.")
            return

        raw_conversations = raw.get("conversations", {})
        if not isinstance(raw_conversations, dict):
            logger.error(
                f"Conversation storage load failed: '{path}' has an invalid 'conversations' section."
            )
            return

        loaded: dict[str, Conversation] = {}
        for name, data in raw_conversations.items():
            if not isinstance(data, dict):
                logger.error(f"Conversation storage load failed for '{name}': entry is not an object.")
                continue
            try:
                loaded[str(name)] = Conversation.from_dict(data, max_messages=self.max_messages())
            except (KeyError, TypeError, ValueError) as exc:
                logger.error(f"Conversation storage load failed for '{name}': {exc}")

        current = raw.get("current")
        with self._lock:
            self._conversations = loaded
            self._current_name = current if isinstance(current, str) and current in loaded else None

        logger.info(f"Conversation storage loaded: {len(loaded)} conversations from '{path}'.")

    # ---------- Internal helpers ----------

    def _create_locked(self, name: str) -> Conversation:
        """Create and register a conversation. Caller must already hold `self._lock`.

        Args:
            name: The unique name to register the conversation under.

        Returns:
            The newly created Conversation.
        """
        conversation = Conversation(title=name, max_messages=self.max_messages())
        self._conversations[name] = conversation
        logger.info(f"Conversation created: '{name}'.")
        return conversation

    def _resolve_current_name_locked(self) -> str:
        """Resolve the effective current conversation name. Caller must hold `self._lock`.

        Returns:
            `self._current_name` if it is set and still registered,
            otherwise DEFAULT_CONVERSATION_NAME.
        """
        if self._current_name is not None and self._current_name in self._conversations:
            return self._current_name
        return DEFAULT_CONVERSATION_NAME

    def _autosave(self) -> None:
        """Persist to disk if the Conversation Engine and auto-save are both enabled."""
        if self.is_enabled() and self.is_auto_save():
            self.save()
