"""RagManager for the EP-022 RAG Engine.

RagManager owns the RAG Engine's lifecycle -- everything `RagEngine`
itself must not know about (matching EP-021's own
`EmbeddingManager`/`EmbeddingEngine` split):

    - Which `ProjectIndex` (EP-019) is currently built, read via the
      injected `ProjectIndexer.index()` -- never via `build()`/
      `rebuild()`/`save()`/`load()`/`clear()`, which remain
      exclusively `IndexService`'s concern.
    - Which `RetrievalEngine` (EP-020) currently wraps that index,
      rebuilt only when the underlying `ProjectIndex` instance
      actually changes (e.g. after `index rebuild`).
    - Which embedding provider (EP-021) is currently selected,
      delegated entirely to the injected `EmbeddingManager` --
      `register_provider`/`set_current`/`disable` remain exclusively
      `EmbeddingManager`'s concern; this class only reads
      `get_current()` and forwards `set_current()`.
    - Whether the RAG subsystem itself is enabled.

Never performs retrieval, embedding, or context assembly itself --
every one of those stays inside `RetrievalEngine`/`EmbeddingEngine`/
`RagEngine` exactly as implemented for EP-020/EP-021/EP-022; this
class only builds a `RagEngine` from its current dependencies and
enriches its `RagResult` with provider identity.
"""

from __future__ import annotations

from dataclasses import replace
from threading import Lock

from loguru import logger

from src.core.config import Config
from src.core.embedding.engine import EmbeddingEngine
from src.core.embedding.manager import EmbeddingManager, EmbeddingProviderNotFoundError
from src.core.indexing import ProjectIndex, ProjectIndexer
from src.core.rag.rag_engine import DEFAULT_MAX_CONTEXT_CHARACTERS, DEFAULT_TOP_K, RagEngine
from src.core.rag.rag_provider import NoEmbeddingProviderError, RagProviderInfo
from src.core.rag.rag_result import RagResult
from src.core.retrieval import RetrievalEngine

__all__ = [
    "RagManager",
    "RagManagerError",
    "RagConfigurationError",
    "RagDisabledError",
    "IndexNotBuiltError",
]


class RagManagerError(Exception):
    """Base class for errors raised by the RagManager itself."""


class RagConfigurationError(RagManagerError):
    """Raised when 'rag.*' configuration is present but malformed."""


class RagDisabledError(RagManagerError):
    """Raised when a RAG operation is requested while the RAG subsystem is disabled."""


class IndexNotBuiltError(RagManagerError):
    """Raised when a RAG operation is requested but no ProjectIndex has been built yet."""


class RagManager:
    """Owns the RAG Engine's lifecycle: current index, retrieval engine, and embedding provider.

    Responsibilities:
        - Build a `RagEngine` from the current `ProjectIndex` (EP-019),
          reusing its internal `RetrievalEngine` (EP-020) while the
          underlying index is unchanged.
        - Report and select which embedding provider (EP-021)
          currently backs the RAG pipeline.
        - Enable/disable the RAG subsystem as a whole.
        - Orchestrate `query()`/`context()` calls end-to-end, filling
          in the provider identity `RagEngine` itself cannot resolve.
    """

    def __init__(
        self,
        indexer: ProjectIndexer,
        embedding_manager: EmbeddingManager,
        embedding_engine: EmbeddingEngine,
        config: Config | None = None,
        top_k: int = DEFAULT_TOP_K,
        max_context_characters: int = DEFAULT_MAX_CONTEXT_CHARACTERS,
    ) -> None:
        """Initialize the RagManager.

        Args:
            indexer: The ProjectIndexer (EP-019) whose current
                `index()` this manager reads. Never mutated: `build`/
                `rebuild`/`save`/`load`/`clear` remain exclusively
                `IndexService`'s concern.
            embedding_manager: The EmbeddingManager (EP-021) this
                manager reports on and selects providers through.
                Never mutated beyond forwarding `set_current()`.
            embedding_engine: The EmbeddingEngine (EP-021) injected
                into every `RagEngine` this manager builds.
            config: Loaded application configuration, read once for
                'rag.enabled', 'rag.top_k' and
                'rag.max_context_characters'. May be None, in which
                case the RAG subsystem defaults to enabled and
                `top_k`/`max_context_characters` are used as given.
            top_k: Default number of chunks assembled into context.
                Overridden by 'rag.top_k' if `config` sets it.
            max_context_characters: Default maximum assembled context
                size (characters). Overridden by
                'rag.max_context_characters' if `config` sets it.

        Raises:
            RagConfigurationError: If any 'rag.*' value from `config`
                is present but malformed.
        """
        self._indexer = indexer
        self._embedding_manager = embedding_manager
        self._embedding_engine = embedding_engine
        self._lock = Lock()

        self._enabled = self._validated_bool(config, "rag.enabled", True)
        self._top_k = self._validated_positive_int(config, "rag.top_k", top_k)
        self._max_context_characters = self._validated_positive_int(
            config, "rag.max_context_characters", max_context_characters
        )

        self._cached_index_identity: int | None = None
        self._cached_retrieval_engine: RetrievalEngine | None = None

    # ---------- Subsystem lifecycle ----------

    def is_enabled(self) -> bool:
        """Return whether the RAG subsystem is currently enabled."""
        with self._lock:
            return self._enabled

    def disable(self) -> None:
        """Disable the RAG subsystem. Future `query()`/`context()` calls will raise."""
        with self._lock:
            self._enabled = False
        logger.info("RAG subsystem disabled.")

    @property
    def top_k(self) -> int:
        """Return the default number of chunks assembled into context."""
        return self._top_k

    @property
    def max_context_characters(self) -> int:
        """Return the default maximum assembled context size, in characters."""
        return self._max_context_characters

    # ---------- Index / RetrievalEngine lifecycle ----------

    def current_index(self) -> ProjectIndex | None:
        """Return the current ProjectIndex (EP-019), or None if none has been built yet."""
        return self._indexer.index()

    def build_engine(self) -> RagEngine:
        """Build a RagEngine reflecting the current ProjectIndex and embedding engine.

        Reuses the cached RetrievalEngine while the underlying
        ProjectIndex instance is unchanged; only constructs a new one
        after `index build`/`index rebuild` produces a fresh
        ProjectIndex.

        Returns:
            A RagEngine wired to the current ProjectIndex,
            RetrievalEngine, and EmbeddingEngine.

        Raises:
            IndexNotBuiltError: If no ProjectIndex has been built yet
                (`index build` has never been run).
        """
        index = self._indexer.index()
        if index is None:
            raise IndexNotBuiltError(
                "No project index has been built yet. Run 'index build' first."
            )
        retrieval_engine = self._retrieval_engine_for(index)
        return RagEngine(
            index=index,
            retrieval_engine=retrieval_engine,
            embedding_engine=self._embedding_engine,
            top_k=self._top_k,
            max_context_characters=self._max_context_characters,
        )

    def _retrieval_engine_for(self, index: ProjectIndex) -> RetrievalEngine:
        """Return a RetrievalEngine over `index`, rebuilding it only when `index` has changed."""
        with self._lock:
            if self._cached_retrieval_engine is None or self._cached_index_identity != id(index):
                self._cached_retrieval_engine = RetrievalEngine(index)
                self._cached_index_identity = id(index)
            return self._cached_retrieval_engine

    # ---------- Provider selection (delegated to EmbeddingManager) ----------

    def provider_info(self) -> RagProviderInfo:
        """Return a read-only snapshot of the embedding provider currently backing RAG.

        Returns:
            A RagProviderInfo describing the currently selected
            embedding provider (EP-021).

        Raises:
            NoEmbeddingProviderError: If no embedding provider is
                currently selected (or the Embedding subsystem is
                disabled).
        """
        current = self._embedding_manager.get_current()
        if current is None:
            raise NoEmbeddingProviderError(
                "No embedding provider is currently selected. Use 'rag use <provider>'."
            )
        return RagProviderInfo(
            name=current.provider_name(),
            model=current.model_name(),
            dimension=current.dimension(),
            available=current.is_available(),
        )

    def use_provider(self, name: str) -> None:
        """Select the embedding provider (EP-021) used for future RAG queries.

        Args:
            name: The registered embedding provider name to activate.

        Raises:
            EmbeddingProviderNotFoundError: If `name` is not registered.
        """
        self._embedding_manager.set_current(name)

    # ---------- Query orchestration ----------

    def query(self, text: str, top_k: int | None = None) -> RagResult:
        """Run the full RAG pipeline for `text`, with provider identity filled in.

        Args:
            text: The user's query text.
            top_k: Maximum number of chunks to assemble into context.
                Defaults to this manager's configured `top_k`.

        Returns:
            A RagResult with `provider`/`model` filled in from the
            currently selected embedding provider.

        Raises:
            RagDisabledError: If the RAG subsystem is currently disabled.
            IndexNotBuiltError: If no ProjectIndex has been built yet.
            NoEmbeddingProviderError: If no embedding provider is
                currently selected.
            EmptyQueryError: If `text` is empty or whitespace-only.
            ValueError: If `top_k` is given and is not positive.
            EmbeddingUnavailableError: If `text`'s embedding cannot be
                obtained.
        """
        if not self.is_enabled():
            raise RagDisabledError("The RAG subsystem is currently disabled.")

        provider = self.provider_info()
        engine = self.build_engine()
        result = engine.query(text, top_k=top_k)
        return replace(result, provider=provider.name, model=provider.model)

    def context(self, text: str, top_k: int | None = None) -> str:
        """Run the full RAG pipeline for `text` and return only the assembled context text.

        Equivalent to `query(text, top_k).context`.

        Args:
            text: The user's query text.
            top_k: Maximum number of chunks to assemble into context.

        Returns:
            The assembled context text; "" if nothing matched.

        Raises:
            RagDisabledError: If the RAG subsystem is currently disabled.
            IndexNotBuiltError: If no ProjectIndex has been built yet.
            NoEmbeddingProviderError: If no embedding provider is
                currently selected.
            EmptyQueryError: If `text` is empty or whitespace-only.
            ValueError: If `top_k` is given and is not positive.
            EmbeddingUnavailableError: If `text`'s embedding cannot be
                obtained.
        """
        return self.query(text, top_k=top_k).context

    # ---------- Configuration loading ----------

    @staticmethod
    def _validated_bool(config: Config | None, key_path: str, default: bool) -> bool:
        """Read `key_path` from `config`, validating it is a real boolean.

        Args:
            config: Loaded application configuration, or None to use
                `default` unconditionally.
            key_path: Dotted configuration key (e.g. 'rag.enabled').
            default: Value to use if `config` is None or `key_path` is
                absent from configuration.

        Returns:
            The validated boolean value.

        Raises:
            RagConfigurationError: If `key_path` is present but is not
                an actual boolean (e.g. a string like "true").
        """
        if config is None:
            return default
        value = config.get(key_path, default)
        if not isinstance(value, bool):
            raise RagConfigurationError(
                f"Invalid value for '{key_path}': expected true/false, got {value!r} "
                f"({type(value).__name__})."
            )
        return value

    @staticmethod
    def _validated_positive_int(config: Config | None, key_path: str, default: int) -> int:
        """Read `key_path` from `config`, validating it is a positive integer.

        Args:
            config: Loaded application configuration, or None to use
                `default` unconditionally.
            key_path: Dotted configuration key (e.g. 'rag.top_k').
            default: Value to use if `config` is None or `key_path` is
                absent from configuration.

        Returns:
            The validated positive integer.

        Raises:
            RagConfigurationError: If `key_path` is present but is not
                a positive integer (e.g. a quoted string, a float, or
                zero/negative).
        """
        if config is None:
            return default
        value = config.get(key_path, default)
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise RagConfigurationError(
                f"Invalid value for '{key_path}': expected a positive integer, got "
                f"{value!r} ({type(value).__name__})."
            )
        return value
