"""ContextLoader for EP-018 Context Engine.

ContextLoader is a **universal**, project-independent context gathering
engine. The only file name it ever hardcodes is `PROJECT_MANIFEST.md`,
the single entry point every other piece of project knowledge is
discovered through (identity, which documents belong in context and in
what priority, ignore rules, which EP-018 sections are active, ...).
Point this same class at a different `PROJECT_MANIFEST.md` and it
drives a completely different project without any code change.

Composes a `Context` (see `src/core/ai/context.py`) from up to seven
independently-gated sources, always in this fixed order: Project
Identity -> Project Documents -> Working Directory -> Configuration ->
Environment -> Conversation -> Active Process, plus any caller-appended
"Additional Context" blocks.

EP-018.4 Context Budget: every document listed under the manifest's
"Context Documents" heading is loaded strictly in priority order
(critical -> high -> medium -> low, manifest declaration order breaks
ties), one at a time, until the document budget is used. The document
that does not fully fit is truncated to exactly fill the remaining
budget and loading then stops -- lower-priority documents are simply
not loaded that request, so the assembled Project Documents text (and
therefore `Context.rendered`) never exceeds the budget, whatever the
project's documentation set grows to. This is priority + budget
management, not retrieval: no keyword or semantic matching is ever
used to choose which documents load (that is EP-019's concern, out of
scope here).

EP-018.5 Unified Prompt Budget: ContextLoader maintains NO size
ceiling of its own -- there is exactly one prompt-size authority in
the project, PromptBuilder's 'prompt.max_prompt_size' (see
`src/core/ai/prompt_builder.py`). ContextLoader's document budget is
*derived* from it (Prompt Max Size - Reserved Space) and handed in
here via Dependency Injection as the `document_budget` callable
(constructor parameter below, threaded through from `ContextManager`
and ultimately from `PromptManager.document_budget()`). ContextLoader
never reads 'prompt.*', 'context.max_size', or 'context.
max_context_size' -- those keys no longer exist anywhere in this
project. This keeps the two subsystems from being able to drift out
of sync again, without ContextLoader needing to import PromptBuilder
or know anything about how the budget was computed.

A missing manifest, a missing document, or an unreadable file is
recorded inline (and logged) rather than raised -- ContextLoader never
crashes over project *content*. A misconfigured injected budget
(negative) raises `ValueError` instead of silently falling back, since
that is an operator/wiring mistake, not routine data variance.

EP-018.6 Conversation Budget Enforcement: Conversation Context is
budgeted the same way Project Context has been since EP-018.4 --
within a caller-injected ceiling, never past it -- via a second
callable, `conversation_budget` (also threaded through from
`ContextManager`, ultimately from `PromptManager.
conversation_budget()`). Unlike documents, which are truncated
mid-file, conversation history is budgeted at message granularity:
`_render_conversation()` keeps the newest messages, in their original
chronological order, and drops the oldest ones first -- never a
partial message -- until what remains fits. A truncation is logged at
debug level with the number of messages omitted; the injected budget
being negative raises `ValueError`, exactly like `document_budget`.

No dependency on any AI provider and no Jarvis-specific logic; only on
Config (the remaining 'context.*' settings, none of which concern
sizing), the injected `document_budget`/`conversation_budget`
callables, and the provider-independent Conversation/Message models.
Lifecycle/registry concerns (holding multiple Context objects,
refreshing them by id) belong to ContextManager, not here.
"""

from __future__ import annotations

import platform
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any

from loguru import logger

from src.core.ai.context import Context
from src.core.ai.conversation import Conversation
from src.core.config import Config
from src.core.project_manifest import (
    DEFAULT_PRIORITY,
    DocumentCache,
    ManifestDocument,
    ManifestLoader,
    ProjectManifest,
    expand_document_entries,
    priority_weight,
)

__all__ = ["ContextLoader", "ContextStatusReport"]

# Fixed, project-independent EP-018 section names.
_SECTION_IDENTITY = "project identity"
_SECTION_DOCUMENTS = "project documents"
_SECTION_WORKING_DIRECTORY = "working directory"
_SECTION_CONFIGURATION = "configuration"
_SECTION_ENVIRONMENT = "environment"
_SECTION_CONVERSATION = "conversation"
_SECTION_ACTIVE_PROCESS = "active process"
_DEFAULT_SECTIONS: frozenset[str] = frozenset(
    {
        _SECTION_IDENTITY, _SECTION_DOCUMENTS, _SECTION_WORKING_DIRECTORY,
        _SECTION_CONFIGURATION, _SECTION_ENVIRONMENT, _SECTION_CONVERSATION,
        _SECTION_ACTIVE_PROCESS,
    }
)


def _utc_now() -> datetime:
    """Return the current time as a timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class ContextStatusReport:
    """A diagnostic snapshot of the most recent `ContextLoader.load()`.

    Attributes:
        repository_root: Detected/declared repository root, None if no
            manifest could be found.
        working_directory: Working-directory label shown to the Prompt
            Engine, None if that source is disabled.
        loaded_documents: Documents actually read into context.
        selected_documents: Every candidate document, in the priority
            order they were considered (before budget cutoff).
        missing_documents: Candidate documents that could not be found
            or read.
        cached_documents: Loaded documents served from cache.
        total_context_size: Size, in characters, of the assembled
            project-context text.
        document_sizes: Size, in characters, of each loaded document
            (post-truncation, if truncated).
        budget_exceeded: Whether the context budget was exhausted
            before every candidate document could be loaded.
        generated_at: When this report was produced.
        token_estimate: A rough token-count estimate.
    """

    repository_root: str | None = None
    working_directory: str | None = None
    loaded_documents: tuple[str, ...] = ()
    selected_documents: tuple[str, ...] = ()
    missing_documents: tuple[str, ...] = ()
    cached_documents: tuple[str, ...] = ()
    total_context_size: int = 0
    document_sizes: dict[str, int] = field(default_factory=dict)
    budget_exceeded: bool = False
    generated_at: datetime = field(default_factory=_utc_now)
    token_estimate: int = 0


@dataclass(frozen=True)
class _DocumentsResult:
    """The outcome of resolving the Project Documents section for one `load()`."""

    text: str = ""
    loaded: tuple[str, ...] = ()
    selected: tuple[str, ...] = ()
    missing: tuple[str, ...] = ()
    cached: tuple[str, ...] = ()
    sizes: dict[str, int] = field(default_factory=dict)
    budget_exceeded: bool = False


@dataclass(frozen=True)
class _PendingContext:
    """The fully-gathered, not-yet-built state produced by `load()`."""

    conversation_context: str = ""
    project_context: str = ""
    working_directory: str = ""
    active_process: str = ""
    loaded_documents: tuple[str, ...] = ()
    metadata: dict[str, str] = field(default_factory=dict)


class ContextLoader:
    """Composes a `Context` from a `PROJECT_MANIFEST.md`-driven set of sources.

    Responsibilities:
        - Locate and parse `PROJECT_MANIFEST.md`, caching it until the
          file changes on disk.
        - Resolve "Context Documents" into an on-disk file list,
          honoring ignore rules and text/binary safety rules, caching
          each document's content until it changes.
        - Gather every EP-018 section, each independently gated by the
          manifest's "Context Sections" and by `Config`.
        - Load documents strictly in priority order within the
          injected document budget, truncating (and stopping) the
          first document that does not fully fit -- EP-018.4 Context
          Budget.
        - Track "Additional Context" blocks appended by the caller.
        - Report diagnostics about its most recent `load()`.

    Thread-safe: every read/write of shared state is guarded by one
    re-entrant lock, since ContextManager shares a single ContextLoader
    across the CLI, Telegram, Desktop UI, REST API and Scheduler.
    """

    def __init__(
        self,
        config: Config,
        document_budget: Callable[[], int],
        conversation_budget: Callable[[], int],
    ) -> None:
        """Initialize an empty ContextLoader.

        Args:
            config: Loaded application configuration, used to resolve
                every remaining 'context.*' setting (none of them
                concern sizing -- see EP-018.5, EP-018.6).
            document_budget: A zero-argument callable returning the
                current document budget, in characters. Injected
                rather than resolved from `config` directly so
                ContextLoader can never define a size ceiling of its
                own; the only prompt-size authority in the project is
                PromptBuilder's 'prompt.max_prompt_size' (see
                `PromptManager.document_budget()`, wired in
                `src/bootstrap.py`). Called fresh on every `load()`,
                so it always reflects the live configuration.
            conversation_budget: A zero-argument callable returning the
                current conversation-history budget, in characters,
                enforced by `_render_conversation()` (EP-018.6). Same
                injection contract as `document_budget` -- see
                `PromptManager.conversation_budget()`.
        """
        self._config = config
        self._document_budget = document_budget
        self._conversation_budget = conversation_budget
        self._lock = RLock()
        self._manifest_loader = ManifestLoader()
        self._document_cache = DocumentCache()
        self._additional_blocks: list[str] = []
        self._pending: _PendingContext = _PendingContext()
        self._status = ContextStatusReport()

    # ---------- Configuration ----------

    def is_enabled(self) -> bool:
        """Return whether the Context Loader subsystem is enabled ('context.enabled')."""
        return bool(self._config.get("context.enabled", True))

    # ---------- Additional context blocks ----------

    def append(self, text: str) -> "ContextLoader":
        """Append one caller-supplied "Additional Context" block. Returns self, for chaining."""
        with self._lock:
            if text:
                self._additional_blocks.append(text)
        return self

    def clear(self) -> "ContextLoader":
        """Remove every previously appended "Additional Context" block. Returns self, for chaining."""
        with self._lock:
            self._additional_blocks.clear()
        return self

    # ---------- Cache ----------

    def refresh(self) -> "ContextLoader":
        """Invalidate every cache so the next `load()` rereads all files from disk."""
        with self._lock:
            self._manifest_loader.refresh()
            self._document_cache.clear()
        logger.info("Context Loader cache cleared; manifest and documents will be reread.")
        return self

    # ---------- Gather / build ----------

    def load(
        self,
        conversation: Conversation | None = None,
        active_process: str | None = None,
        query: str | None = None,
    ) -> "ContextLoader":
        """Gather every enabled EP-018 section into this loader's pending state.

        Args:
            conversation: Current Conversation, for "Conversation
                Context". None if unavailable.
            active_process: Caller-supplied active-process description.
                Falls back to the manifest's "Active Processes" hint
                when not given.
            query: The user's request text. Accepted for interface
                stability with `ContextManager.create()` only --
                EP-018.4 scopes query/keyword-based document selection
                out (see module docstring); "Project Documents" is
                always the same priority + budget selection regardless
                of `query`.

        Returns:
            This ContextLoader, for chaining into `build()`.
        """
        del query  # Intentionally unused -- see the Args note above.
        with self._lock:
            if not self.is_enabled():
                self._pending = _PendingContext()
                self._status = ContextStatusReport(generated_at=_utc_now())
                return self

            manifest = self._manifest_loader.get()
            repository_root = manifest.repository_root if manifest else Path.cwd()
            sections = (manifest.sections if manifest and manifest.sections else _DEFAULT_SECTIONS)
            auto_load = bool(self._config.get("context.auto_load", True))

            def enabled(section: str) -> bool:
                return auto_load and self._section_enabled(section, sections)

            conversation_text = (
                self._render_conversation(conversation, self._resolve_conversation_budget())
                if enabled(_SECTION_CONVERSATION)
                else ""
            )

            identity_text = ""
            if manifest and enabled(_SECTION_IDENTITY):
                identity_text = self._render_identity(manifest)

            documents = _DocumentsResult()
            include_documents = bool(self._config.get("context.include_project_files", True))
            if manifest and include_documents and enabled(_SECTION_DOCUMENTS):
                budget = self._resolve_document_budget()
                identity_overhead = len(identity_text) + 2 if identity_text else 0
                documents = self._load_documents(manifest, max(0, budget - identity_overhead))

            project_context = "\n\n".join(part for part in (identity_text, documents.text) if part)
            if documents.text and len(project_context) > budget:
                # Defensive final clamp: the reserved-overhead arithmetic above
                # is exact, so this should never trigger -- it exists only as
                # an absolute guarantee that Context.rendered's dominant
                # contributor never exceeds the configured budget.
                project_context = project_context[:budget]

            working_directory_text = ""
            include_working_directory = bool(self._config.get("context.include_working_directory", True))
            if include_working_directory and enabled(_SECTION_WORKING_DIRECTORY):
                working_directory_text = f"Working Directory: {repository_root}"

            configuration_text = ""
            if manifest and enabled(_SECTION_CONFIGURATION):
                configuration_text = self._render_configuration(manifest)

            environment_text = ""
            if bool(self._config.get("context.include_environment", False)) and enabled(_SECTION_ENVIRONMENT):
                environment_text = self._render_environment()

            resolved_active_process = active_process or ""
            if not resolved_active_process and manifest and enabled(_SECTION_ACTIVE_PROCESS):
                resolved_active_process = manifest.active_process_hint
            active_process_text = f"Active Process: {resolved_active_process}" if resolved_active_process else ""

            metadata: dict[str, str] = {}
            if configuration_text:
                metadata["configuration"] = configuration_text
            if environment_text:
                metadata["environment"] = environment_text

            self._pending = _PendingContext(
                conversation_context=conversation_text,
                project_context=project_context,
                working_directory=working_directory_text,
                active_process=active_process_text,
                loaded_documents=documents.loaded,
                metadata=metadata,
            )
            self._status = ContextStatusReport(
                repository_root=str(repository_root) if manifest else None,
                working_directory=str(repository_root) if working_directory_text else None,
                loaded_documents=documents.loaded,
                selected_documents=documents.selected,
                missing_documents=documents.missing,
                cached_documents=documents.cached,
                total_context_size=len(project_context),
                document_sizes=documents.sizes,
                budget_exceeded=documents.budget_exceeded,
                generated_at=_utc_now(),
                token_estimate=_estimate_tokens(project_context),
            )
        return self

    def build(self, context_id: str | None = None) -> Context:
        """Assemble the final, immutable Context from this loader's pending state.

        Args:
            context_id: An existing identifier to rebuild the Context
                under (see `ContextManager.refresh()`), or None to
                generate a new one.

        Returns:
            The composed Context.
        """
        with self._lock:
            pending = self._pending
            additional_text = "\n\n".join(self._additional_blocks)
            metadata: dict[str, Any] = dict(pending.metadata)
            if additional_text:
                metadata["additional"] = additional_text

            kwargs: dict[str, Any] = {"context_id": context_id} if context_id else {}
            context = Context(
                conversation_context=pending.conversation_context,
                project_context=pending.project_context,
                working_directory=pending.working_directory,
                active_process=pending.active_process,
                loaded_documents=pending.loaded_documents,
                metadata=metadata,
                **kwargs,
            )
        logger.info(f"Context built: '{context.context_id}' ({len(context.rendered)} characters).")
        return context

    def status(self) -> ContextStatusReport:
        """Return the last diagnostic report produced by `load()` (empty if never called)."""
        with self._lock:
            return self._status

    # ---------- Section rendering ----------

    @staticmethod
    def _section_enabled(name: str, sections: frozenset[str]) -> bool:
        """Return whether section `name` is active per the manifest's "Context Sections"."""
        return name in sections

    @staticmethod
    def _render_identity(manifest: ProjectManifest) -> str:
        """Render the "Project Identity" section, or "" if the manifest carries none."""
        lines = ["Project Identity", ""]
        if manifest.project_name:
            lines.append(f"Name: {manifest.project_name}")
        if manifest.version:
            lines.append(f"Version: {manifest.version}")
        if manifest.project_type:
            lines.append(f"Type: {manifest.project_type}")
        if manifest.description:
            lines.append("")
            lines.append(manifest.description)
        return "\n".join(lines) if len(lines) > 2 else ""

    @staticmethod
    def _render_configuration(manifest: ProjectManifest) -> str:
        """Render "Configuration" as a file-name list only -- never file content.

        Configuration files commonly hold secrets/credentials, which
        must never be logged or forwarded to a provider.
        """
        if not manifest.configuration_files:
            return ""
        return "Configuration Files: " + ", ".join(manifest.configuration_files)

    @staticmethod
    def _render_environment() -> str:
        """Render "Environment" from a safe, whitelisted platform summary (never raw env vars)."""
        return f"Environment\n\nOS: {platform.system()} {platform.release()}\nPython: {platform.python_version()}"

    @staticmethod
    def _render_conversation(conversation: Conversation | None, budget: int) -> str:
        """Render "Conversation Context" from prior history, within `budget` characters.

        EP-018.6: messages are kept newest-first until the budget is
        used, then re-assembled in their original chronological order
        -- the oldest messages are the ones dropped, never the newest,
        and a message is either kept whole or dropped whole (never
        partially rendered, unlike documents -- see `_load_documents()`).
        `budget` is the caller-resolved conversation budget (from the
        injected `conversation_budget` callable, itself
        'prompt.reserved_conversation_history' -- EP-018.6).

        Args:
            conversation: The conversation to render, or None.
            budget: The maximum number of characters the returned text
                may occupy.

        Returns:
            "" if there is no conversation/no messages, or if `budget`
            is too small to fit even the single newest message.
            Otherwise the rendered "Conversation Context" text,
            guaranteed not to exceed `budget` characters.
        """
        if conversation is None:
            return ""
        messages = conversation.messages()
        if not messages:
            return ""

        header = ["Conversation Context", ""]
        lines = [f"{message.role.value}: {message.content}" for message in messages]

        kept = len(lines)
        while kept > 0 and len("\n".join(header + lines[-kept:])) > budget:
            kept -= 1

        omitted = len(lines) - kept
        if omitted:
            logger.debug(
                f"Conversation Context truncated to fit the reserved conversation budget "
                f"({budget} characters): {omitted} oldest message(s) omitted."
            )

        if kept == 0:
            return ""
        return "\n".join(header + lines[-kept:])

    # ---------- Project documents ----------

    def _load_documents(self, manifest: ProjectManifest, budget: int) -> _DocumentsResult:
        """Load "Context Documents" strictly in priority order, within `budget` characters.

        Ties within the same priority break by manifest declaration
        order. See the module docstring for the full budget algorithm.
        `budget` is the caller-resolved document budget (from the
        injected `document_budget` callable, itself derived from
        PromptBuilder's 'prompt.max_prompt_size' -- EP-018.5), already
        reduced by whatever other sections precede "Project Documents"
        in `Context.rendered`.
        """
        entries = expand_document_entries(manifest)
        ordered = [
            entry
            for _, entry in sorted(
                enumerate(entries), key=lambda pair: (priority_weight(pair[1][1].priority), pair[0])
            )
        ]
        return self._materialize_documents(manifest.repository_root, ordered, budget)

    def _materialize_documents(
        self, repository_root: Path, ordered: list[tuple[str, ManifestDocument]], budget: int
    ) -> _DocumentsResult:
        """Read documents in `ordered`, stopping once `budget` is exhausted.

        A missing file records "Missing document: <path>" and an
        unreadable file records "Could not load: <path> <reason>" in
        place of its content; either way loading continues to the next
        document. A document that cannot fully fit the remaining
        budget is truncated to fill exactly what remains, and loading
        stops there -- lower-priority documents are not loaded.
        """
        header_prefix = "Project Documents\n\n"
        remaining = max(0, budget - len(header_prefix))

        loaded: list[str] = []
        missing: list[str] = []
        cached: list[str] = []
        sizes: dict[str, int] = {}
        blocks: list[str] = []
        budget_exceeded = False

        for relative_path, document in ordered:
            if remaining <= 0:
                budget_exceeded = True
                logger.warning("Context budget reached before every candidate document could be loaded.")
                break

            full_path = repository_root / relative_path
            if not full_path.is_file():
                note = f"Missing document:\n{relative_path}"
                blocks.append(note)
                remaining -= len(note) + 2
                missing.append(relative_path)
                logger.warning(f"Project document not found: '{relative_path}'.")
                continue

            try:
                content, was_cached = self._document_cache.read(full_path)
            except OSError as exc:
                note = f"Could not load:\n{relative_path}\n{exc}"
                blocks.append(note)
                remaining -= len(note) + 2
                missing.append(relative_path)
                logger.warning(f"Unable to read project document '{relative_path}': {exc}")
                continue

            if was_cached:
                cached.append(relative_path)

            priority_label = (document.priority.strip() or DEFAULT_PRIORITY).title()
            block, truncated, loaded_size = _render_document_block(relative_path, priority_label, content, remaining)
            blocks.append(block)
            remaining -= len(block) + 2
            loaded.append(relative_path)
            sizes[relative_path] = loaded_size

            if truncated:
                budget_exceeded = True
                logger.warning(
                    f"Context budget reached. Document truncated: '{relative_path}'. "
                    f"Remaining budget: {max(remaining, 0)} chars."
                )
                break

        text = ""
        if blocks:
            text = header_prefix + "\n\n".join(blocks)
            if len(text) > budget:
                text = text[:budget]

        return _DocumentsResult(
            text=text,
            loaded=tuple(loaded),
            selected=tuple(relative_path for relative_path, _ in ordered),
            missing=tuple(missing),
            cached=tuple(cached),
            sizes=sizes,
            budget_exceeded=budget_exceeded,
        )

    def _resolve_document_budget(self) -> int:
        """Resolve the document budget from the injected `document_budget` callable.

        EP-018.5 "Unified Prompt Budget": ContextLoader has no size
        configuration of its own to fall back to -- this method exists
        only to call the injected callable and validate its result.
        The callable itself is `PromptManager.document_budget()`,
        which derives the value from PromptBuilder's single
        'prompt.max_prompt_size' authority (see `prompt_builder.py`).

        Raises:
            ValueError: If the injected callable returns a negative
                value (zero is valid -- it simply means no documents
                fit within the remaining budget this request).
        """
        value = int(self._document_budget())
        if value < 0:
            raise ValueError(
                f"Invalid document_budget: {value} must not be negative "
                "(check the 'document_budget' callable injected into ContextLoader)."
            )
        return value

    def _resolve_conversation_budget(self) -> int:
        """Resolve the conversation budget from the injected `conversation_budget` callable.

        EP-018.6 "Conversation Budget Enforcement": mirrors
        `_resolve_document_budget()` exactly, for the same reasons --
        ContextLoader has no size configuration of its own to fall
        back to. The callable itself is `PromptManager.
        conversation_budget()`, which resolves
        'prompt.reserved_conversation_history' (see
        `prompt_builder.py`).

        Raises:
            ValueError: If the injected callable returns a negative
                value (zero is valid -- it simply means no
                conversation history fits this request).
        """
        value = int(self._conversation_budget())
        if value < 0:
            raise ValueError(
                f"Invalid conversation_budget: {value} must not be negative "
                "(check the 'conversation_budget' callable injected into ContextLoader)."
            )
        return value


# ---------- Document block rendering (module-level: no instance state needed) ----------


def _estimate_tokens(text: str) -> int:
    """Roughly estimate the token count of `text` (~4 characters per token)."""
    return len(text) // 4 if text else 0


def _render_document_block(relative_path: str, priority_label: str, content: str, budget: int) -> tuple[str, bool, int]:
    """Render one document's "===== path =====" block, fitted within `budget` characters.

    Includes the required metadata (path, priority, original/loaded
    size, truncated flag). If `content` does not fit in full, it is
    truncated (never mid-character, since Python strings are sequences
    of whole Unicode code points) to exactly fill what remains and a
    "[DOCUMENT TRUNCATED]" marker is appended.

    Returns:
        (block_text, was_truncated, loaded_size). `block_text` is
        always <= `budget` characters, even in the degenerate case
        where `budget` is too small to hold the metadata alone.
    """
    original_size = len(content)

    def build(body: str, truncated: bool) -> str:
        header = (
            f"===== {relative_path} =====\n\n"
            f"Priority: {priority_label}\n"
            f"Original: {original_size} chars\n"
            f"Loaded: {len(body)} chars\n"
            f"Truncated: {'Yes' if truncated else 'No'}\n\n"
        )
        footer = ("\n\n[DOCUMENT TRUNCATED]" if truncated else "") + "\n\n====================="
        return header + body + footer

    block = build(content, truncated=False)
    if len(block) <= budget:
        return block, False, original_size

    body = content
    for _ in range(6):
        block = build(body, truncated=True)
        overflow = len(block) - budget
        if overflow <= 0:
            return block, True, len(body)
        body = body[: max(0, len(body) - overflow)]

    # Degenerate case (budget smaller than the metadata scaffold itself):
    # the loop above cannot shrink further -- hard-clamp as a last resort
    # so the "never exceed the configured limit" guarantee always holds.
    return build(body, truncated=True)[:budget], True, len(body)

