"""ContextLoader for EP-018 Context Loader.

Assembles a single, immutable Context from every optional source, in
EP-018's fixed "Loading Order": Conversation Context -> Project
Context -> Working Directory -> Configuration -> Environment ->
Active Process -> Additional Context.

Every source is optional: a missing or unreadable source is skipped
(logged, never raised) -- EP-018's "Every source must be optional.
Missing sources must never cause failures." This is deliberately
different from the Prompt Engine (`prompt_builder.py`), which
*rejects* invalid input: an incomplete Context is still useful, an
invalid Prompt is not.

Unlike PromptBuilder, ContextLoader is not purely disposable:
ContextManager (`context_manager.py`) holds and reuses ONE instance so
its project-files cache survives across requests ("Caching": "Reload
only when files change."). `clear()` resets only per-request buffers;
the cache is untouched by `clear()`, only invalidated by `refresh()`.
ContextLoader itself need not be thread-safe (only ContextManager
must be) -- it is always used while ContextManager's lock is held.

No dependency on any AI provider; depends only on Config and on
Conversation (a fellow Core module) to render prior history -- moving
that responsibility out of AIService, which rendered it directly in
EP-017.

Security: "Configuration"/"Environment" expose only a small, safe,
hard-coded whitelist (app name/tagline/version; OS/Python version) --
never raw Config (can hold provider API keys) or raw `os.environ`
(can hold secrets), since this text reaches an external AI provider.
"""

from __future__ import annotations

import os
import platform
from dataclasses import replace
from pathlib import Path
from typing import Any

from loguru import logger

from src.core.ai.context import Context
from src.core.ai.conversation import Conversation
from src.core.config import Config

DEFAULT_MAX_CONTEXT_SIZE: int = 50000

# EP-018's "Project Context" section, in the exact order specified.
_PROJECT_FILES: tuple[str, ...] = (
    "README.md",
    "PROJECT_MANIFEST.md",
    "PROJECT_RULES.md",
    "JARVIS_ROADMAP.md",
    "AI_GENERATION_STANDARD.md",
    "PROCESS_CATALOG.md",
)


def _detect_repository_root() -> Path:
    """Locate the repo root by walking up from this file for 'pyproject.toml'.

    Independent of the process's cwd (future callers like the REST API
    or Scheduler may not run from the repository root). Falls back to
    the current working directory if no marker is found; never raises.
    """
    try:
        current = Path(__file__).resolve()
        for candidate in current.parents:
            if (candidate / "pyproject.toml").is_file():
                return candidate
    except OSError:
        pass
    return Path.cwd()


class ContextLoader:
    """Assembles a single immutable Context from every optional source.

    Responsibilities: hold in-progress context parts; gather every
    enabled source, tolerating any that is missing/unreadable; cache
    project documentation by modification time; compose the final
    Context in EP-018's fixed order, trimming low-priority stages
    first past 'context.max_context_size'; reset its per-request
    buffers for reuse (the project-files cache survives `clear()`).
    """

    def __init__(self, config: Config) -> None:
        """Initialize an empty ContextLoader.

        Args:
            config: Loaded application configuration, used to resolve
                every 'context.*' setting.
        """
        self._config = config
        self._repository_root: Path | None = None
        # path -> (mtime, content); persists across clear(), only
        # invalidated by refresh() (EP-018's "Caching").
        self._project_cache: dict[str, tuple[float, str]] = {}
        self._reset_buffers()

    # ---------- Configuration ----------

    def is_enabled(self) -> bool:
        """Return whether the Context Loader subsystem is enabled ('context.enabled')."""
        return bool(self._config.get("context.enabled", True))

    def is_auto_load(self) -> bool:
        """Return whether `load()` automatically gathers sources ('context.auto_load')."""
        return bool(self._config.get("context.auto_load", True))

    # ---------- Loading ----------

    def load(
        self,
        conversation: Conversation | None = None,
        active_process: str | None = None,
    ) -> "ContextLoader":
        """Gather every enabled context source, in the fixed loading order.

        A no-op if 'context.enabled' or 'context.auto_load' is False,
        so callers relying purely on `append()`/`merge()` still work.
        `active_process` is caller-supplied only -- never fetched
        automatically, since ContextLoader has no Service dependency.

        Returns:
            This ContextLoader, for fluent chaining.
        """
        if not self.is_enabled() or not self.is_auto_load():
            return self

        self._conversation_context = self._load_conversation_context(conversation)

        if bool(self._config.get("context.include_project_files", True)):
            self._project_context = self._load_project_context()

        if bool(self._config.get("context.include_working_directory", True)):
            self._working_directory = self._load_working_directory()

        self._configuration_text = self._load_configuration()

        if bool(self._config.get("context.include_environment", False)):
            self._environment_text = self._load_environment()

        if active_process:
            self._active_process = f"Active process: {active_process}"

        logger.info("Context loaded.")
        return self

    def append(self, text: str) -> "ContextLoader":
        """Append one Additional Context block (EP-018's final loading stage).

        Returns:
            This ContextLoader, for fluent chaining.
        """
        if text:
            self._additional_parts.append(text)
        return self

    def merge(self, other: Context) -> "ContextLoader":
        """Fill any not-yet-populated field from an existing Context.

        Never overwrites a value already staged by `load()`/`append()`
        -- only fills gaps left empty.

        Returns:
            This ContextLoader, for fluent chaining.
        """
        self._conversation_context = self._conversation_context or other.conversation_context
        self._project_context = self._project_context or other.project_context
        self._working_directory = self._working_directory or other.working_directory
        self._active_process = self._active_process or other.active_process
        for document in other.loaded_documents:
            if document not in self._loaded_documents:
                self._loaded_documents.append(document)
        for key, value in other.metadata.items():
            self._metadata.setdefault(key, value)
        logger.info(f"Context merged: '{other.context_id}'.")
        return self

    def build(self, context_id: str | None = None) -> Context:
        """Compose the final, immutable Context.

        Args:
            context_id: An explicit id to assign (so ContextManager.refresh()
                can replace a context while keeping its id stable). A new
                id is generated if omitted.

        Returns:
            The composed Context, trimmed to 'context.max_context_size'
            if necessary.
        """
        metadata: dict[str, Any] = dict(self._metadata)
        if self._configuration_text:
            metadata["configuration"] = self._configuration_text
        if self._environment_text:
            metadata["environment"] = self._environment_text
        if self._additional_parts:
            metadata["additional"] = "\n\n".join(self._additional_parts)

        context = Context(
            conversation_context=self._conversation_context,
            project_context=self._project_context,
            working_directory=self._working_directory,
            active_process=self._active_process,
            loaded_documents=tuple(self._loaded_documents),
            metadata=metadata,
        )
        if context_id:
            context = replace(context, context_id=context_id)

        context = self._enforce_max_size(context)
        logger.info(f"Context built: '{context.context_id}'.")
        return context

    def clear(self) -> "ContextLoader":
        """Reset every per-request buffer (not the project-files cache; see `refresh()`)."""
        self._reset_buffers()
        logger.info("Context cleared.")
        return self

    def refresh(self) -> "ContextLoader":
        """Invalidate the project-files cache so the next `load()` re-reads from disk."""
        self._project_cache.clear()
        logger.info("Cache refreshed.")
        return self

    # ---------- Internal helpers: buffers ----------

    def _reset_buffers(self) -> None:
        """Reset every per-request composition buffer (not the project-files cache)."""
        self._conversation_context: str = ""
        self._project_context: str = ""
        self._working_directory: str = ""
        self._configuration_text: str = ""
        self._environment_text: str = ""
        self._active_process: str = ""
        self._loaded_documents: list[str] = []
        self._additional_parts: list[str] = []
        self._metadata: dict[str, Any] = {}

    # ---------- Internal helpers: sources (each tolerates failure -- see module docstring) ----------

    def _load_conversation_context(self, conversation: Conversation | None) -> str:
        """Render prior conversation history (excluding the just-appended current turn) as text.

        Bounded by 'ai.max_context_messages' (EP-014, reused rather
        than a new key). Returns "" if `conversation` is None/empty.
        """
        if conversation is None:
            return ""
        try:
            limit = int(self._config.get("ai.max_context_messages", 20))
        except (TypeError, ValueError):
            limit = 20
        history = conversation.messages()[:-1]
        if limit > 0:
            history = history[-limit:]
        if not history:
            return ""
        return "\n".join(f"{message.role.value.capitalize()}: {message.content}" for message in history)

    def _load_project_context(self) -> str:
        """Load and concatenate every detected project documentation file.

        Uses `self._project_cache` (keyed by modification time) so
        unchanged files are never re-read. Missing files are silently
        skipped -- never an error.
        """
        root = self._repository_root or _detect_repository_root()
        if self._repository_root is None:
            self._repository_root = root
            logger.info(f"Project detected: '{root}'.")

        blocks: list[str] = []
        for name in _PROJECT_FILES:
            content = self._load_project_file(root / name, name)
            if content is not None:
                blocks.append(f"## {name}\n\n{content}")
                self._loaded_documents.append(name)

        if blocks:
            logger.info(f"Files loaded: {', '.join(self._loaded_documents)}.")
        return "\n\n".join(blocks)

    def _load_project_file(self, path: Path, name: str) -> str | None:
        """Load one project file via the modification-time cache; None if missing/unreadable."""
        key = str(path)
        try:
            if not path.is_file():
                self._project_cache.pop(key, None)
                return None
            mtime = path.stat().st_mtime
        except OSError as exc:
            logger.warning(f"Project file unavailable, skipping: '{name}' ({exc}).")
            return None

        cached = self._project_cache.get(key)
        if cached is not None and cached[0] == mtime:
            logger.info(f"Cache hit: '{name}'.")
            return cached[1]

        try:
            content = path.read_text(encoding="utf-8", errors="replace").strip()
        except OSError as exc:
            logger.warning(f"Project file unreadable, skipping: '{name}' ({exc}).")
            return None

        self._project_cache[key] = (mtime, content)
        return content

    def _load_working_directory(self) -> str:
        """Return "Working directory: <cwd>", or "" if the cwd cannot be resolved."""
        try:
            return f"Working directory: {os.getcwd()}"
        except OSError:
            return ""

    def _load_configuration(self) -> str:
        """Return a small, safe summary of Jarvis's own identity (app name/version/tagline only).

        Never the raw Config data -- see module docstring's security note.
        """
        name = str(self._config.get("app.name", "") or "")
        if not name:
            return ""
        version = str(self._config.get("app.version", "") or "")
        tagline = str(self._config.get("app.tagline", "") or "")
        summary = f"Application: {name}"
        if version:
            summary += f" v{version}"
        if tagline:
            summary += f" -- {tagline}"
        return summary

    def _load_environment(self) -> str:
        """Return a safe OS/Python version summary only -- never raw `os.environ`."""
        return f"Operating system: {platform.platform()}\nPython: {platform.python_version()}"

    # ---------- Internal helpers: size enforcement ----------

    def _resolve_max_context_size(self) -> int:
        """Resolve 'context.max_context_size', falling back to the default on bad config.

        Unlike PromptBuilder (which rejects invalid configuration
        outright), Context Loader never fails: an unparsable value is
        logged and the default used instead (EP-018's "never fail"
        philosophy, extended to configuration itself).
        """
        raw_value = self._config.get("context.max_context_size", DEFAULT_MAX_CONTEXT_SIZE)
        try:
            return int(raw_value)
        except (TypeError, ValueError):
            logger.warning(
                f"Invalid configuration: 'context.max_context_size' must be an integer "
                f"(got {raw_value!r}); using default ({DEFAULT_MAX_CONTEXT_SIZE})."
            )
            return DEFAULT_MAX_CONTEXT_SIZE

    def _enforce_max_size(self, context: Context) -> Context:
        """Trim `context` to 'context.max_context_size', least-current content first.

        Drop order: project documentation, configuration, working
        directory, environment. `conversation_context`, `active_process`,
        and any 'additional' metadata are never trimmed -- they are the
        most current/relevant information (EP-018's "Never truncate
        the active user request").
        """
        max_size = self._resolve_max_context_size()
        if max_size <= 0 or len(context.rendered) <= max_size:
            return context

        trimmed = context
        for drop in ("project_context", "configuration", "working_directory", "environment"):
            if len(trimmed.rendered) <= max_size:
                break
            if drop == "project_context":
                trimmed = replace(trimmed, project_context="", loaded_documents=())
            elif drop == "working_directory":
                trimmed = replace(trimmed, working_directory="")
            else:
                metadata = dict(trimmed.metadata)
                if metadata.pop(drop, None) is not None:
                    trimmed = replace(trimmed, metadata=metadata)

        if len(trimmed.rendered) > max_size:
            logger.warning(
                f"Context exceeds 'context.max_context_size' ({len(trimmed.rendered)} > {max_size}) "
                "even after trimming; keeping conversation/active-process/additional content intact."
            )
        return trimmed
