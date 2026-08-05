"""Application bootstrap sequence for Jarvis."""

from __future__ import annotations

from pathlib import Path

import pyfiglet
from colorama import Style
from colorama import init as colorama_init
from loguru import logger

from src.core.ai.context_manager import ContextManager
from src.core.ai.conversation_manager import ConversationManager
from src.core.ai.prompt_manager import PromptManager
from src.core.ai.provider_factory import ProviderFactory
from src.core.ai.provider_manager import ProviderManager
from src.core.ai.provider_registry import ProviderRegistry as AIProviderRegistry
from src.core.agent.agent_engine import AgentEngine
from src.core.agent.agent_manager import AgentManager
from src.core.agent.agent_provider import AgentFrameworkError
from src.core.command_router import CommandRouter
from src.core.config import Config, ConfigError
from src.core.context_compression.compression_engine import CompressionEngine
from src.core.context_compression.compression_manager import CompressionManager
from src.core.context_compression.compression_provider import ContextCompressionError
from src.core.planning.planning_engine import PlanningEngine
from src.core.planning.planning_manager import PlanningManager
from src.core.planning.planning_provider import PlanningError
from src.core.plan_execution.plan_execution_engine import PlanExecutionEngine
from src.core.plan_execution.plan_execution_manager import PlanExecutionManager
from src.core.plan_execution.plan_execution_provider import PlanExecutionError
from src.core.embedding.engine import EmbeddingEngine
from src.core.embedding.manager import EmbeddingManager
from src.core.embedding.provider import EmbeddingConfigurationError, EmbeddingError
from src.core.events import EventBus
from src.core.execution.engine import ExecutionEngine
from src.core.execution.executors.file_executor import FileExecutor
from src.core.execution.executors.process_executor import ProcessExecutor
from src.core.execution.executors.python_executor import PythonExecutor
from src.core.execution.executors.url_executor import UrlExecutor
from src.core.execution.process_registry import ProcessRegistry
from src.core.indexing import IndexStorage, JsonIndexStorage, MemoryIndexStorage, ProjectIndexer
from src.core.knowledge.knowledge_provider import KnowledgeProviderError
from src.core.logger import Logger
from src.core.long_term_memory.long_term_provider import LongTermProviderError
from src.core.memory.memory_provider import MemoryProviderError
from src.core.memory.memory_store import MemoryStore
from src.core.orchestrator import Orchestrator
from src.core.plugins.plugin_context import PluginContext
from src.core.plugins.plugin_discovery import PluginDiscovery
from src.core.plugins.plugin_loader import PluginLoader
from src.core.plugins.plugin_registry import PluginRegistry
from src.core.processes.process import Process, RestartPolicy
from src.core.processes.process_registry import ProcessRegistry as ProcessCatalogRegistry
from src.core.rag.rag_manager import RagManager, RagManagerError
from src.core.scheduler.job import Job, Schedule, ScheduleType
from src.core.scheduler.job_registry import JobRegistry
from src.core.scheduler.scheduler import Scheduler
from src.core.semantic.semantic_engine import SemanticEngine
from src.core.semantic.semantic_manager import SemanticManager
from src.core.semantic.semantic_provider import SemanticError
from src.core.shell import InteractiveShell
from src.core.telegram.telegram_client import TelegramClient
from src.core.telegram.telegram_router import TelegramRouter
from src.modules.ai_module import AIModule
from src.modules.agent_module import AgentModule
from src.modules.context_compression_module import ContextCompressionModule
from src.modules.planning_module import PlanningModule
from src.modules.plan_execution_module import PlanExecutionModule
from src.modules.conversation_module import ConversationModule
from src.modules.embedding_module import EmbeddingModule
from src.modules.fast_response_module import FastResponseModule
from src.modules.index_module import IndexModule
from src.modules.invoice_module import InvoiceModule
from src.modules.knowledge_module import KnowledgeModule
from src.modules.long_term_memory_module import LongTermMemoryModule
from src.modules.memory_module import MemoryModule
from src.modules.plugin_module import PluginModule
from src.modules.process_module import ProcessModule
from src.modules.rag_module import RagModule
from src.modules.scheduler_module import SchedulerModule
from src.modules.semantic_module import SemanticModule
from src.modules.telegram_module import TelegramModule
from src.services.agent_service import AgentService
from src.services.ai_service import AIService
from src.services.context_compression_service import CompressionService
from src.services.embedding_service import EmbeddingService
from src.services.fast_response_service import FastResponseService
from src.services.index_service import IndexService
from src.services.invoice_service import InvoiceService
from src.services.knowledge_service import KnowledgeService
from src.services.long_term_memory_service import LongTermMemoryService
from src.services.memory_service import MemoryService
from src.services.planning_service import PlanningService
from src.services.plan_execution_service import PlanExecutionService
from src.services.plugin_service import PluginService
from src.services.process_service import ProcessService
from src.services.rag_service import RagService
from src.services.scheduler_service import SchedulerService
from src.services.semantic_service import SemanticService
from src.services.telegram_service import TelegramService
from src.skills.system.skill import SystemModule
from src.utils.constants import (
    APP_NAME,
    APP_TAGLINE,
    APP_VERSION,
    BANNER_FONT,
    BANNER_PALETTE,
    BANNER_WIDTH,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent

REQUIRED_DIRECTORIES: tuple[str, ...] = (
    "logs",
    "data/input",
    "data/output",
    "data/cache",
    "data/database",
    "knowledge",
    "prompts",
)


class Bootstrap:
    """Bootstraps the Jarvis application before the orchestrator takes over.

    Lifecycle:

        Construction  ->  initialize()  ->  run()

    `__init__()` only allocates the EventBus and initializes colorama --
    no configuration is read and no service is built yet. `initialize()`
    performs every dependency-injection responsibility -- loading
    configuration, initializing the logger, starting the orchestrator,
    and building the fully wired CommandRouter/InteractiveShell -- and
    is idempotent (calling it more than once is a no-op after the
    first call). It prints no banner and starts no runtime; it exists
    so callers that only need initialized services and a populated
    CommandRouter (in particular, tests verifying dependency-injection
    wiring) never have to pay for -- or see the console output of --
    the interactive-session startup sequence. `run()` is a thin
    wrapper: it calls `initialize()` (a no-op if already initialized),
    then prints the colored ASCII startup banner and status lines.
    This split does not change `run()`'s own behavior or return value
    for any existing caller -- `src/main.py`'s real interactive launch
    still calls only `run()` and sees identical console output.

    Responsibilities (performed by `initialize()`, reported by `run()`):
        - Create required runtime folders.
        - Load application configuration.
        - Initialize the logger.
        - Initialize and start the orchestrator.
        - Build the CommandRouter and InteractiveShell.

    Responsibility of `run()` alone:
        - Print the colored ASCII startup banner and status lines.
    """

    def __init__(self, project_root: Path | None = None) -> None:
        """Initialize the Bootstrap sequence.

        Args:
            project_root: Root path of the project. Defaults to the
                directory containing the 'src' package.
        """
        self._project_root = project_root or PROJECT_ROOT
        self._initialized = False
        self._config: Config | None = None
        self._event_bus = EventBus()
        self._orchestrator: Orchestrator | None = None
        self._command_router: CommandRouter | None = None
        self._shell: InteractiveShell | None = None
        self._memory_service: MemoryService | None = None
        self._knowledge_service: KnowledgeService | None = None
        self._long_term_memory_service: LongTermMemoryService | None = None
        self._index_service: IndexService | None = None
        self._embedding_service: EmbeddingService | None = None
        self._rag_service: RagService | None = None
        self._semantic_service: SemanticService | None = None
        self._compression_service: CompressionService | None = None
        self._agent_service: AgentService | None = None
        self._planning_service: PlanningService | None = None
        self._plan_execution_service: PlanExecutionService | None = None
        colorama_init(autoreset=True)

    def initialize(self) -> Orchestrator:
        """Build every service, register every module, and prepare the CommandRouter.

        Idempotent: calling this more than once on the same instance
        only performs the work once -- every subsequent call returns
        the already-built Orchestrator without rebuilding anything or
        re-running any startup step. Prints no banner and starts no
        interactive runtime -- see `run()` for that.

        Returns:
            The started Orchestrator instance.

        Raises:
            ConfigError: If configuration cannot be loaded.
            OSError: If required directories cannot be created.
        """
        if self._initialized:
            return self._orchestrator

        self._create_required_directories()

        self._config = self._load_configuration()
        self._initialize_logger()

        self._orchestrator = Orchestrator(config=self._config, event_bus=self._event_bus)
        self._orchestrator.start()

        self._command_router = self._build_command_router(self._orchestrator, self._config)
        self._shell = InteractiveShell(router=self._command_router)

        self._initialized = True
        return self._orchestrator

    def run(self) -> Orchestrator:
        """Initialize (if needed) and announce the start of an interactive session.

        Calls `initialize()` -- a no-op if this instance was already
        initialized -- then prints the colored ASCII startup banner
        and status lines. Every existing caller of `run()` (in
        particular `src/main.py`) sees identical behavior and console
        output to before this method was split from `initialize()`.

        Returns:
            The started Orchestrator instance.

        Raises:
            ConfigError: If configuration cannot be loaded.
            OSError: If required directories cannot be created.
        """
        self._print_banner()
        print("Loading configuration...")

        self.initialize()

        print("Logger initialized...")
        print("Loading skills...")
        print("Ready.")
        print()
        print("Jarvis is running.")
        logger.info("Jarvis is running.")
        print()

        return self._orchestrator

    def _build_command_router(self, orchestrator: Orchestrator, config: Config) -> CommandRouter:
        """Build and populate the CommandRouter with built-in modules.

        Args:
            orchestrator: The running Orchestrator, passed to modules
                that need to report on application state.
            config: The loaded application configuration, passed to
                modules that need to resolve their own settings (e.g.
                InvoiceModule's 'invoice.script').

        Returns:
            A CommandRouter with all built-in command modules registered.
        """
        router = CommandRouter()

        registry = ProcessRegistry()
        execution_engine = ExecutionEngine(
            executors=[
                UrlExecutor(),
                ProcessExecutor(registry),
                PythonExecutor(registry),
                FileExecutor(),
            ],
            registry=registry,
        )

        router.register(SystemModule(orchestrator=orchestrator, execution_engine=execution_engine))

        # EP-013: Memory & Context Manager. Depends only on Config; has
        # no dependency on any LLM or other business-logic module, so it
        # is wired before everything else and is available for Invoice,
        # FastResponse, Process, Plugin, Scheduler and Telegram to reuse.
        #
        # EP-023: MemoryService now also builds a MemoryManager
        # internally (registering `memory_store` as the "memory"
        # provider per 'memory.default_provider'). An invalid
        # 'memory.default_provider' disables the Memory subsystem for
        # this run rather than crashing the whole application --
        # consistent with how every other optional subsystem in this
        # file degrades (see the Embedding/RAG try/except below).
        try:
            memory_store = MemoryStore()
            memory_service = MemoryService(config=config, store=memory_store)
            self._memory_service = memory_service
            router.register(MemoryModule(memory_service))
        except MemoryProviderError as exc:
            logger.error(
                f"Memory subsystem disabled: invalid 'memory.*' configuration ({exc}). "
                "Fix config/config.yaml and restart to re-enable it."
            )
            self._memory_service = None

        # EP-024: Knowledge Base. Depends only on Config -- no
        # dependency on MemoryStore/MemoryManager (EP-013/EP-023),
        # ProjectIndexer (EP-019), Embedding (EP-021), or RAG (EP-022).
        # KnowledgeService builds a KnowledgeManager internally,
        # registering a fresh KnowledgeCollection wrapped in a
        # KnowledgeCollectionProvider as the default provider per
        # 'knowledge.default_provider'. An invalid
        # 'knowledge.default_provider' disables the Knowledge
        # subsystem for this run rather than crashing the whole
        # application -- consistent with how every other optional
        # subsystem in this file degrades (see the Memory/Embedding/
        # RAG try/except blocks).
        try:
            knowledge_service = KnowledgeService(config=config)
            self._knowledge_service = knowledge_service
            router.register(KnowledgeModule(knowledge_service))
        except KnowledgeProviderError as exc:
            logger.error(
                f"Knowledge subsystem disabled: invalid 'knowledge.*' configuration "
                f"({exc}). Fix config/config.yaml and restart to re-enable it."
            )
            self._knowledge_service = None

        # EP-025: Long-Term Memory. Persistence is delegated entirely
        # to EP-024's KnowledgeService (a dedicated "long_term_memory"
        # collection) -- Knowledge Base is a hard dependency, so if it
        # is unavailable this run (see the EP-024 block above),
        # Long-Term Memory disables itself too rather than building a
        # second storage engine. If Memory is available, this also
        # registers a LongTermMemoryProvider with MemoryService
        # (`memory providers`/`memory use long_term`), extending
        # EP-023's Memory Manager per EP-025's brief -- entirely
        # through MemoryService's public `register_provider` API, and
        # best-effort (a failure there never disables Long-Term Memory
        # itself; see LongTermMemoryService._try_register_with_memory_manager).
        if self._knowledge_service is None:
            logger.error(
                "Long-term memory subsystem disabled: Knowledge Base (EP-024) is "
                "unavailable this run."
            )
            self._long_term_memory_service = None
        else:
            try:
                long_term_memory_service = LongTermMemoryService(
                    config=config,
                    knowledge_service=self._knowledge_service,
                    memory_service=self._memory_service,
                )
                self._long_term_memory_service = long_term_memory_service
                router.register(LongTermMemoryModule(long_term_memory_service))
            except LongTermProviderError as exc:
                logger.error(
                    f"Long-term memory subsystem disabled: invalid "
                    f"'long_term_memory.*' configuration ({exc}). Fix "
                    "config/config.yaml and restart to re-enable it."
                )
                self._long_term_memory_service = None

        # EP-019: Project Index Engine integration. Depends only on
        # Config (to resolve 'indexing.*') and ProjectIndexer itself
        # (EP-019, untouched) -- no dependency on ContextLoader,
        # PromptBuilder, PromptManager, ContextManager or any AI
        # provider, matching EP-019's own architectural constraint.
        # Wired here, alongside MemoryService above, since both are
        # independent of the AI-facing EP-016/017/018 wiring below.
        index_storage_backend = str(config.get("indexing.storage_backend", "json")).lower()
        index_storage: IndexStorage
        if index_storage_backend == "memory":
            index_storage = MemoryIndexStorage()
        else:
            index_storage = JsonIndexStorage(
                self._project_root
                / str(config.get("indexing.storage_file", "data/database/project_index.json"))
            )
        project_indexer = ProjectIndexer(storage=index_storage)
        index_service = IndexService(indexer=project_indexer, storage=index_storage)
        self._index_service = index_service
        router.register(IndexModule(index_service))

        # EP-016: Conversation Engine. Depends only on Config, matching
        # MemoryStore/ProviderRegistry above; provider-independent
        # (no import of Claude/Gemini/OpenAI/Ollama/LM Studio). Wired
        # before AIService so it can be injected into it.
        conversation_manager = ConversationManager(config=config)
        router.register(ConversationModule(conversation_manager))

        # EP-017: Prompt Engine. Depends only on Config, matching
        # ConversationManager above; provider-independent (no import
        # of Claude/Gemini/OpenAI/Ollama/LM Studio). Wired before
        # AIService so it can be injected into it.
        prompt_manager = PromptManager(config=config)

        # EP-018: Context Engine. Depends only on Config, matching
        # ConversationManager/PromptManager above; provider-independent
        # (no import of Claude/Gemini/OpenAI/Ollama/LM Studio). Wired
        # before AIService so it can be injected into it. Only one
        # ContextManager instance may exist, so its ContextLoader's
        # project-files cache is reused across every request.
        #
        # EP-018.5 Unified Prompt Budget: PromptBuilder's
        # 'prompt.max_prompt_size' is the project's ONE prompt-size
        # authority. ContextManager/ContextLoader maintain no size
        # configuration of their own -- here, in the composition root,
        # we inject PromptManager's public `document_budget()` (which
        # simply forwards to PromptBuilder.resolve_document_budget())
        # as the callable ContextLoader must consult on every load().
        # This is why PromptManager is (and must remain) wired before
        # ContextManager.
        #
        # EP-018.6 Conversation Budget Enforcement: same pattern, for
        # the conversation-history side of the budget --
        # `conversation_budget` forwards PromptManager's
        # `conversation_budget()` (= 'prompt.reserved_conversation_history',
        # the exact figure `document_budget()` already reserves) so
        # ContextLoader can finally enforce it on Conversation Context.
        context_manager = ContextManager(
            config=config,
            document_budget=prompt_manager.document_budget,
            conversation_budget=prompt_manager.conversation_budget,
        )

        # EP-014: AI Provider Manager. Depends only on Config; has no
        # dependency on any other business-logic module, matching
        # MemoryService above. Every provider is a config-driven
        # placeholder (see ProviderFactory) -- no network requests, no
        # AI API calls, no chat/streaming (EP-014's "IMPORTANT" section).
        ai_provider_registry = AIProviderRegistry()
        ai_provider_manager = ProviderManager(
            registry=ai_provider_registry,
            enabled=bool(config.get("ai.enabled", False)),
            default_provider=str(config.get("ai.default_provider", "none")),
        )
        provider_factory = ProviderFactory(config=config)
        for provider in provider_factory.build_all():
            ai_provider_manager.register_provider(provider)
        ai_service = AIService(
            config=config,
            provider_manager=ai_provider_manager,
            conversation_manager=conversation_manager,
            prompt_manager=prompt_manager,
            context_manager=context_manager,
        )
        router.register(AIModule(ai_service))

        # EP-021: Provider-Independent Embedding Engine. Depends only on
        # Config -- no dependency on RetrievalEngine (EP-020) or any
        # AI chat provider (EP-014/015/015.1); the Embedding Engine
        # transforms text into vectors only. EmbeddingManager owns
        # provider selection, configuration loading ('embedding.*')
        # and provider lifecycle; EmbeddingEngine owns batching,
        # vector validation and error handling.
        #
        # Chosen failure mode: invalid 'embedding.*' configuration
        # (e.g. a malformed dimension, or a 'default_provider' that
        # does not match any registered provider) disables the
        # Embedding subsystem for this run rather than crashing the
        # whole application -- consistent with how every other
        # optional subsystem in this file degrades (e.g. 'ai.enabled:
        # false' does not prevent Jarvis from starting). The exact
        # reason is always logged so an operator can fix
        # config/config.yaml and restart to re-enable it.
        try:
            embedding_manager = EmbeddingManager(config=config)
            embedding_batch_size = config.get("embedding.batch_size", 16)
            if isinstance(embedding_batch_size, bool) or not isinstance(
                embedding_batch_size, int
            ) or embedding_batch_size <= 0:
                raise EmbeddingConfigurationError(
                    "Invalid value for 'embedding.batch_size': expected a positive "
                    f"integer, got {embedding_batch_size!r}."
                )
            embedding_engine = EmbeddingEngine(
                manager=embedding_manager, batch_size=embedding_batch_size
            )
            embedding_service = EmbeddingService(manager=embedding_manager, engine=embedding_engine)
            self._embedding_service = embedding_service
            router.register(EmbeddingModule(embedding_service))
        except EmbeddingError as exc:
            logger.error(
                f"Embedding Engine disabled: invalid 'embedding.*' configuration ({exc}). "
                "Fix config/config.yaml and restart to re-enable it."
            )
            self._embedding_service = None

        # EP-022: Provider-Independent RAG Engine. Combines
        # ProjectIndexer (EP-019), RetrievalEngine (EP-020, built
        # internally by RagManager over the current ProjectIndex) and
        # EmbeddingEngine/EmbeddingManager (EP-021) into a reusable
        # context-generation pipeline. Never calls an AI provider --
        # no import of src.core.ai.* anywhere in src/core/rag.
        #
        # Requires a working Embedding Engine (see the try/except
        # above): if 'embedding.*' configuration was invalid and
        # EmbeddingService could not be built, the RAG Engine is
        # disabled for this run too, for the same reason -- consistent
        # with how every other optional subsystem in this file
        # degrades rather than crashing the whole application.
        if self._embedding_service is not None:
            try:
                rag_manager = RagManager(
                    indexer=project_indexer,
                    embedding_manager=embedding_manager,
                    embedding_engine=embedding_engine,
                    config=config,
                )
                rag_service = RagService(manager=rag_manager)
                self._rag_service = rag_service
                router.register(RagModule(rag_service))
            except RagManagerError as exc:
                logger.error(
                    f"RAG Engine disabled: invalid 'rag.*' configuration ({exc}). "
                    "Fix config/config.yaml and restart to re-enable it."
                )
                self._rag_service = None
        else:
            logger.warning(
                "RAG Engine disabled: the Embedding Engine is unavailable this run "
                "(see the preceding log entry)."
            )
            self._rag_service = None

        # EP-026: Semantic Search. Provider-independent meaning-based
        # similarity search over Knowledge Base (EP-024) and Long-Term
        # Memory (EP-025) records, using EmbeddingEngine (EP-021) to
        # generate vectors. Never calls an AI provider, builds a
        # prompt, or reasons -- no import of src.core.rag, src.core.ai,
        # or any future Agent Framework component anywhere in
        # src/core/semantic. SemanticManager owns provider selection,
        # configuration loading ('semantic.*') and provider lifecycle;
        # SemanticEngine owns the query -> candidates -> ranked-results
        # pipeline, reaching Knowledge Base and Long-Term Memory only
        # through their public KnowledgeService.list_records() /
        # LongTermMemoryService.list_memories() APIs.
        #
        # Requires a working Embedding Engine (see the EP-021
        # try/except above): if 'embedding.*' configuration was
        # invalid and EmbeddingService could not be built, Semantic
        # Search is disabled for this run too, for the same reason.
        # Knowledge Base and Long-Term Memory are soft dependencies --
        # either (or both) being unavailable this run only narrows
        # what Semantic Search can find; it never disables the
        # subsystem itself, since a search with zero candidates is a
        # valid (empty) result, not an error.
        #
        # `semantic_engine_for_compression` is captured here (rather
        # than reading `self._semantic_service` back) so EP-027's
        # Context Compression can optionally reuse the same
        # SemanticEngine instance through its public `search()` method
        # only -- see the EP-027 wiring immediately below. It stays
        # None whenever Semantic Search itself is unavailable this run.
        semantic_engine_for_compression: SemanticEngine | None = None
        if self._embedding_service is not None:
            try:
                semantic_manager = SemanticManager(config=config)
                semantic_engine = SemanticEngine(
                    manager=semantic_manager,
                    embedding_engine=embedding_engine,
                    embedding_manager=embedding_manager,
                    knowledge_service=self._knowledge_service,
                    long_term_memory_service=self._long_term_memory_service,
                )
                semantic_service = SemanticService(manager=semantic_manager, engine=semantic_engine)
                self._semantic_service = semantic_service
                router.register(SemanticModule(semantic_service))
                semantic_engine_for_compression = semantic_engine
            except SemanticError as exc:
                logger.error(
                    f"Semantic Search disabled: invalid 'semantic.*' configuration "
                    f"({exc}). Fix config/config.yaml and restart to re-enable it."
                )
                self._semantic_service = None
        else:
            logger.warning(
                "Semantic Search disabled: the Embedding Engine is unavailable this "
                "run (see the preceding log entry)."
            )
            self._semantic_service = None

        # EP-027: Context Compression. Provider-independent shrinking
        # of already-assembled context (raw text, or EP-026
        # SemanticResult instances) down to a configured
        # character/chunk budget -- no AI reasoning, no summarization,
        # no LLM calls, no prompt construction (see
        # src/core/context_compression/__init__.py). CompressionManager
        # owns provider selection, configuration loading
        # ('context_compression.*') and provider lifecycle;
        # CompressionEngine owns the context -> chunks ->
        # compressed-result pipeline, reaching Semantic Search only
        # through SemanticEngine's public `search()` method (optional
        # -- used only by `compression`'s future callers via
        # `compress_query()`, never by the CLI commands wired here).
        #
        # Context Compression has no hard dependency on Semantic
        # Search, the Embedding Engine, Knowledge Base, or Long-Term
        # Memory: `compress_text()`/`compress_chunks()` work on raw
        # text/chunks alone. Semantic Search being unavailable this run
        # only means `compress_query()` cannot be used -- it never
        # disables the subsystem itself, matching the soft-dependency
        # precedent set by EP-026 for Knowledge Base/Long-Term Memory.
        try:
            compression_manager = CompressionManager(config=config)
            compression_engine = CompressionEngine(
                manager=compression_manager,
                semantic_engine=semantic_engine_for_compression,
            )
            compression_service = CompressionService(
                manager=compression_manager, engine=compression_engine
            )
            self._compression_service = compression_service
            router.register(ContextCompressionModule(compression_service))
        except ContextCompressionError as exc:
            logger.error(
                f"Context Compression disabled: invalid 'context_compression.*' "
                f"configuration ({exc}). Fix config/config.yaml and restart to "
                "re-enable it."
            )
            self._compression_service = None

        # EP-028: Agent Framework. The central orchestration layer
        # coordinating already-implemented Engineering Packages --
        # agent lifecycle, a subsystem registry, and request
        # acknowledgment only (see src/core/agent/__init__.py). No
        # planning, reasoning, tool execution, prompt construction, or
        # AI provider call is performed here or anywhere in this
        # package. AgentManager owns agent registration, active-agent
        # selection, configuration loading ('agent.*') and the
        # resolved 'agent.startup_mode'; AgentEngine forwards every
        # lifecycle/subsystem-registry/request call to the currently
        # selected AgentProvider (built-in: "jarvis").
        #
        # Every subsystem service already built above (Embedding, RAG,
        # Memory, Knowledge Base, Long-Term Memory, Semantic Search,
        # Context Compression) is registered here, by name, with a
        # live status-check callable bound to that service's own
        # public `status().enabled` -- read-only, no private access.
        # A subsystem unavailable this run (its service is None) is
        # simply skipped -- exactly like every soft dependency
        # elsewhere in this method, it narrows what the Agent
        # Framework can currently see, it never disables the Agent
        # Framework subsystem itself. One subsystem's registration
        # failing (e.g. a duplicate name) is logged and skipped rather
        # than aborting the whole Agent Framework build.
        # `agent_engine_for_planning` is captured here (rather than
        # reading `self._agent_service` back) so EP-029's Planning
        # Engine can optionally reuse the same AgentEngine instance
        # through its public `list_subsystems()` method only -- see
        # the EP-029 wiring immediately below. It stays None whenever
        # the Agent Framework itself is unavailable this run.
        agent_engine_for_planning: AgentEngine | None = None
        try:
            agent_manager = AgentManager(config=config)
            agent_engine = AgentEngine(manager=agent_manager)
            agent_service = AgentService(manager=agent_manager, engine=agent_engine)
            self._agent_service = agent_service
            router.register(AgentModule(agent_service))
            agent_engine_for_planning = agent_engine

            available_subsystems: list[tuple[str, object | None]] = [
                ("embedding", self._embedding_service),
                ("rag", self._rag_service),
                ("memory", self._memory_service),
                ("knowledge", self._knowledge_service),
                ("long_term_memory", self._long_term_memory_service),
                ("semantic", self._semantic_service),
                ("compression", self._compression_service),
            ]
            for subsystem_name, subsystem_service in available_subsystems:
                if subsystem_service is None:
                    continue
                try:
                    agent_engine.register_subsystem(
                        subsystem_name,
                        status_check=lambda service=subsystem_service: service.status().enabled,
                    )
                except AgentFrameworkError as exc:
                    logger.warning(
                        f"Agent Framework could not register subsystem "
                        f"'{subsystem_name}': {exc}"
                    )
        except AgentFrameworkError as exc:
            logger.error(
                f"Agent Framework disabled: invalid 'agent.*' configuration "
                f"({exc}). Fix config/config.yaml and restart to re-enable it."
            )
            self._agent_service = None

        # EP-029: Planning Engine. Decomposes a request into an ordered
        # Plan of steps referencing already-implemented Engineering
        # Packages by name -- deterministic, fixed keyword rules only
        # (see src/core/planning/__init__.py). No AI reasoning, no AI
        # provider call, no prompt construction, and no task execution
        # is performed here or anywhere in this package.
        # PlanningManager owns provider registration, active-provider
        # selection, configuration loading ('planning.*') and the
        # default `max_steps` limit; PlanningEngine builds a Plan via
        # the active PlanningProvider and, when the Agent Framework is
        # available this run, reconciles each step's availability
        # against `AgentEngine.list_subsystems()` (public API only).
        #
        # Planning Engine has no hard dependency on the Agent
        # Framework: `plan()` works standalone with every step reported
        # available. Agent Framework being unavailable this run only
        # narrows what Planning Engine can see (per-step availability
        # is left unreconciled); it never disables the Planning Engine
        # subsystem itself.
        # `planning_engine_for_plan_execution` is captured here (rather
        # than reading `self._planning_service` back) so EP-030's Plan
        # Execution Engine can optionally reuse the same PlanningEngine
        # instance through its public `plan()` method only -- see the
        # EP-030 wiring immediately below. It stays None whenever
        # Planning Engine itself is unavailable this run.
        planning_engine_for_plan_execution: PlanningEngine | None = None
        try:
            planning_manager = PlanningManager(config=config)
            planning_engine = PlanningEngine(
                manager=planning_manager, agent_engine=agent_engine_for_planning
            )
            planning_service = PlanningService(manager=planning_manager, engine=planning_engine)
            self._planning_service = planning_service
            router.register(PlanningModule(planning_service))
            planning_engine_for_plan_execution = planning_engine
        except PlanningError as exc:
            logger.error(
                f"Planning Engine disabled: invalid 'planning.*' configuration "
                f"({exc}). Fix config/config.yaml and restart to re-enable it."
            )
            self._planning_service = None

        # EP-030: Plan Execution Engine. Dispatches an EP-029 Plan's
        # steps, in order -- deterministic, recognized-action dispatch
        # only (see src/core/plan_execution/__init__.py). No AI
        # reasoning, no AI provider call, no prompt construction, and
        # no real subsystem invocation is performed here or anywhere
        # in this package. NOTE: this is unrelated to the local
        # `execution_engine` variable used a few lines below for
        # InvoiceService/ProcessService/etc. -- that is the pre-existing,
        # unrelated OS-level target launcher from EP-003
        # (`src/core/execution/`); see the naming-disambiguation note
        # in `src/core/plan_execution/__init__.py`. Local variable
        # names here are deliberately prefixed `plan_execution_*` to
        # avoid any confusion with, or accidental shadowing of, that
        # variable.
        #
        # PlanExecutionManager owns provider registration,
        # active-provider selection, configuration loading
        # ('plan_execution.*') and the default `stop_on_failure`
        # policy; PlanExecutionEngine walks a Plan's steps and
        # dispatches each available one to the active
        # PlanExecutionProvider, optionally planning a request itself
        # first via EP-029's PlanningEngine (public `plan()` method
        # only).
        #
        # Plan Execution Engine has no hard dependency on Planning
        # Engine: `execute_plan()` works standalone given an
        # already-built Plan. Planning Engine being unavailable this
        # run only means `execute_request()` (and so `execution run`)
        # cannot be used; it never disables the Plan Execution Engine
        # subsystem itself.
        try:
            plan_execution_manager = PlanExecutionManager(config=config)
            plan_execution_engine = PlanExecutionEngine(
                manager=plan_execution_manager, planning_engine=planning_engine_for_plan_execution
            )
            plan_execution_service = PlanExecutionService(
                manager=plan_execution_manager, engine=plan_execution_engine
            )
            self._plan_execution_service = plan_execution_service
            router.register(PlanExecutionModule(plan_execution_service))
        except PlanExecutionError as exc:
            logger.error(
                f"Plan Execution Engine disabled: invalid 'plan_execution.*' configuration "
                f"({exc}). Fix config/config.yaml and restart to re-enable it."
            )
            self._plan_execution_service = None

        invoice_service = InvoiceService(config=config, execution_engine=execution_engine)
        router.register(InvoiceModule(invoice_service))

        fast_response_service = FastResponseService(
            config=config, execution_engine=execution_engine
        )
        router.register(FastResponseModule(fast_response_service))

        process_catalog = ProcessCatalogRegistry()
        for process in Bootstrap._default_processes():
            process_catalog.register(process)
        process_service = ProcessService(
            registry=process_catalog,
            execution_engine=execution_engine,
            config=config,
            invoice_service=invoice_service,
            fast_response_service=fast_response_service,
        )
        router.register(ProcessModule(process_service))

        plugin_registry = PluginRegistry()
        plugin_context = PluginContext(
            config=config,
            logger=logger,
            execution_engine=execution_engine,
            # TODO:
            # No component currently instantiates WorkflowService in
            # this file (see src/services/workflow_service.py's module
            # docstring for the documented architecture gap). Left as
            # None rather than fabricating a WorkflowService here.
            workflow_service=None,
            process_service=process_service,
        )
        plugin_loader = PluginLoader(registry=plugin_registry, context=plugin_context)
        for default_plugin in PluginService.default_plugins():
            plugin_registry.register(default_plugin)

        # EP-010: discovery is optional (plugins.auto_discovery) and the
        # configured directory need not exist yet -- PluginDiscovery
        # itself treats an absent directory as "nothing to discover".
        plugin_discovery = (
            PluginDiscovery(
                plugin_directory=PROJECT_ROOT / str(config.get("plugins.plugin_directory", "plugins"))
            )
            if bool(config.get("plugins.auto_discovery", True))
            else None
        )
        plugin_service = PluginService(
            registry=plugin_registry,
            loader=plugin_loader,
            config=config,
            discovery=plugin_discovery,
        )
        router.register(PluginModule(plugin_service))

        if plugin_discovery is not None:
            plugin_service.discover_plugins()

        if bool(config.get("plugins.enabled", True)) and bool(
            config.get("plugins.auto_load", True)
        ):
            # load_all() covers every registered plugin -- default and
            # discovered alike -- so newly discovered plugins are
            # picked up automatically without touching this file again.
            for load_result in plugin_service.load_all():
                if not load_result.success:
                    logger.error(f"Failed to auto-load plugin: {load_result.message}")

        job_registry = JobRegistry()
        scheduler = Scheduler(registry=job_registry, execution_engine=execution_engine)
        scheduler_service = SchedulerService(config=config, scheduler=scheduler)
        for default_job in Bootstrap._default_jobs(config):
            scheduler_service.register(default_job)
        router.register(SchedulerModule(scheduler_service))

        telegram_token = config.get("telegram.token")
        telegram_client = (
            TelegramClient(token=telegram_token.strip())
            if isinstance(telegram_token, str) and telegram_token.strip()
            else None
        )
        telegram_allowed_chat_ids = config.get("telegram.allowed_chat_ids", [])
        telegram_router = TelegramRouter(
            command_router=router,
            allowed_chat_ids=telegram_allowed_chat_ids
            if isinstance(telegram_allowed_chat_ids, list)
            else [],
        )
        telegram_service = TelegramService(
            config=config, client=telegram_client, router=telegram_router
        )
        router.register(TelegramModule(telegram_service))

        from src.modules.test_module import TestModule
        router.register(TestModule())
        return router

    @staticmethod
    def _default_processes() -> list[Process]:
        """Return the default Process Catalog entries registered at startup.

        Returns:
            Invoice Automation, Fast Response Board, and Workflow
            Engine, with Workflow Engine depending on the other two
            (see 'Dependency Resolution' in the EP-008 task).

            NOTE: "workflow_engine" is registered for catalog
            visibility only; no WorkflowService backs it yet (see the
            TODO in src/services/process_service.py), so its
            start/stop/restart operations currently report failure.
        """
        return [
            Process(
                id="invoice_automation",
                name="Invoice Automation",
                description="External Invoice Automation script (EP-005).",
                restart_policy=RestartPolicy.MANUAL,
            ),
            Process(
                id="fast_response_board",
                name="Fast Response Board",
                description="Fast Response Board Excel workbook (EP-006).",
                restart_policy=RestartPolicy.MANUAL,
            ),
            Process(
                id="workflow_engine",
                name="Workflow Engine",
                description="Workflow Engine (EP-007).",
                dependencies=("invoice_automation", "fast_response_board"),
                restart_policy=RestartPolicy.NEVER,
            ),
        ]

    @staticmethod
    def _default_jobs(config: Config) -> list[Job]:
        """Return the default Job Scheduler entries registered at startup.

        Registered as examples only, per EP-011's task brief ("Register
        only as examples ... No business logic"). Each job's `command`
        is resolved from the same configuration entries InvoiceService
        ('invoice.script') and FastResponseService
        ('fast_response.workbook') already use as their single source
        of truth, so `scheduler run <job>` hands the ExecutionEngine a
        real, executable target and the Scheduler's own job status
        (SUCCESS/FAILED) stays consistent with the target those
        services operate on, instead of duplicating or inventing a
        separate name for it. Each uses a MANUAL schedule so the
        automatic tick loop never attempts to run them on its own.

        NOTE: "Daily Backup" (listed alongside these two in EP-011's
        task brief, annotated "(TODO)") is intentionally not
        registered here: no backup script/target exists anywhere in
        this project's configuration, so registering it would mean
        inventing one -- forbidden by AI_GENERATION_STANDARD.md's
        Unknown API Policy.

        # TODO:
        # Register a real "Daily Backup" job once a backup script/target
        # is defined in configuration.

        Args:
            config: Loaded application configuration, used to resolve
                'invoice.script' and 'fast_response.workbook'.

        Returns:
            The Invoice Automation and Fast Response Board example jobs.
        """
        invoice_script = config.get("invoice.script")
        fast_response_workbook = config.get("fast_response.workbook")

        jobs: list[Job] = []

        if isinstance(invoice_script, str) and invoice_script.strip():
            jobs.append(
                Job(
                    id="invoice_automation",
                    name="Invoice Automation",
                    description="Example scheduled job for Invoice Automation (EP-005).",
                    command=invoice_script.strip(),
                    schedule=Schedule(type=ScheduleType.MANUAL),
                )
            )
        else:
            # TODO:
            # 'invoice.script' is missing or invalid in config/config.yaml,
            # so the Invoice Automation example job cannot be registered
            # with a real ExecutionEngine target.
            pass

        if isinstance(fast_response_workbook, str) and fast_response_workbook.strip():
            jobs.append(
                Job(
                    id="fast_response_board",
                    name="Fast Response Board",
                    description="Example scheduled job for Fast Response Board (EP-006).",
                    command=fast_response_workbook.strip(),
                    schedule=Schedule(type=ScheduleType.MANUAL),
                )
            )
        else:
            # TODO:
            # 'fast_response.workbook' is missing or invalid in
            # config/config.yaml, so the Fast Response Board example job
            # cannot be registered with a real ExecutionEngine target.
            pass

        return jobs

    def _create_required_directories(self) -> None:
        """Create all directories required by the application at runtime.

        Raises:
            OSError: If any required directory cannot be created.
        """
        for relative_dir in REQUIRED_DIRECTORIES:
            directory = self._project_root / relative_dir
            try:
                directory.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                raise OSError(
                    f"Failed to create required directory '{directory}': {exc}"
                ) from exc

    def _load_configuration(self) -> Config:
        """Load the application configuration from disk.

        Returns:
            The loaded Config instance.

        Raises:
            ConfigError: If the configuration file is missing or invalid.
        """
        config_path = self._project_root / "config" / "config.yaml"
        return Config(config_path).load()

    def _initialize_logger(self) -> None:
        """Initialize the application-wide logger using loaded configuration."""
        logs_dir = self._project_root / "logs"
        level = "INFO"
        retention_days = 30
        console_enabled = False
        if self._config is not None:
            level = str(self._config.get("logging.level", "INFO"))
            retention_days = int(self._config.get("logging.retention_days", 30))
            console_enabled = bool(self._config.get("logging.console_enabled", False))
        Logger(
            logs_dir=logs_dir,
            level=level,
            retention_days=retention_days,
            console_enabled=console_enabled,
        )

    def _print_banner(self) -> None:
        """Print the colored ASCII logo, tagline and version to the console."""
        print()
        print(self._render_ascii_logo(APP_NAME))
        print()
        print(Style.BRIGHT + APP_TAGLINE.center(BANNER_WIDTH) + Style.RESET_ALL)
        print()
        print(f"Version : {APP_VERSION}")
        print()

    @staticmethod
    def _render_ascii_logo(text: str) -> str:
        """Render `text` as a multi-colored ASCII block logo.

        Each character is rendered individually with Pyfiglet and then
        stitched back together horizontally, coloring every letter with
        the next color in `BANNER_PALETTE` so the logo reads as a
        continuous, colorful block banner.

        Args:
            text: The text to render as an ASCII logo (e.g. "JARVIS").

        Returns:
            A multi-line string containing ANSI color codes, ready to
            be printed directly to the console.
        """
        letter_lines: list[list[str]] = []
        height = 0

        for char in text:
            art = pyfiglet.figlet_format(char, font=BANNER_FONT)
            lines = art.rstrip("\n").split("\n")
            letter_lines.append(lines)
            height = max(height, len(lines))

        for lines in letter_lines:
            while len(lines) < height:
                lines.append("")
            width = max((len(line) for line in lines), default=0)
            for i, line in enumerate(lines):
                lines[i] = line.ljust(width)

        rows: list[str] = []
        for row_index in range(height):
            segments: list[str] = []
            for letter_index, lines in enumerate(letter_lines):
                color = BANNER_PALETTE[letter_index % len(BANNER_PALETTE)]
                segments.append(f"{color}{lines[row_index]}{Style.RESET_ALL}")
            rows.append("".join(segments))

        return "\n".join(rows)

    @property
    def config(self) -> Config | None:
        """Return the loaded configuration, if available.

        Returns:
            The Config instance, or None if `run()` has not completed.
        """
        return self._config

    @property
    def event_bus(self) -> EventBus:
        """Return the application-wide event bus.

        Returns:
            The EventBus instance shared across the application.
        """
        return self._event_bus

    @property
    def orchestrator(self) -> Orchestrator | None:
        """Return the initialized orchestrator, if available.

        Returns:
            The Orchestrator instance, or None if `run()` has not completed.
        """
        return self._orchestrator

    @property
    def command_router(self) -> CommandRouter | None:
        """Return the populated command router, if available.

        Returns:
            The CommandRouter instance, or None if `run()` has not completed.
        """
        return self._command_router

    @property
    def shell(self) -> InteractiveShell | None:
        """Return the interactive shell, ready to run.

        Returns:
            The InteractiveShell instance, or None if `run()` has not
            completed.
        """
        return self._shell

    @property
    def memory_service(self) -> MemoryService | None:
        """Return the MemoryService built for EP-013, if available.

        Returns:
            The MemoryService instance, or None if `run()` has not
            completed.
        """
        return self._memory_service

    @property
    def knowledge_service(self) -> KnowledgeService | None:
        """Return the KnowledgeService built for EP-024, if available.

        Returns:
            The KnowledgeService instance, or None if `run()` has not
            completed (or the Knowledge subsystem was disabled this
            run -- see `_build_command_router`'s EP-024 wiring).
        """
        return self._knowledge_service

    @property
    def long_term_memory_service(self) -> LongTermMemoryService | None:
        """Return the LongTermMemoryService built for EP-025, if available.

        Returns:
            The LongTermMemoryService instance, or None if `run()` has
            not completed (or the Long-Term Memory subsystem was
            disabled this run -- see `_build_command_router`'s EP-025
            wiring).
        """
        return self._long_term_memory_service

    @property
    def index_service(self) -> IndexService | None:
        """Return the IndexService built for EP-019, if available.

        Returns:
            The IndexService instance, or None if `run()` has not
            completed.
        """
        return self._index_service

    @property
    def embedding_service(self) -> EmbeddingService | None:
        """Return the EmbeddingService built for EP-021, if available.

        Returns:
            The EmbeddingService instance, or None if `run()` has not
            completed.
        """
        return self._embedding_service

    @property
    def rag_service(self) -> RagService | None:
        """Return the RagService built for EP-022, if available.

        Returns:
            The RagService instance, or None if `run()` has not
            completed (or the RAG Engine was disabled this run -- see
            `_build_command_router`'s EP-022 wiring).
        """
        return self._rag_service

    @property
    def semantic_service(self) -> SemanticService | None:
        """Return the SemanticService built for EP-026, if available.

        Returns:
            The SemanticService instance, or None if `run()` has not
            completed (or the Semantic Search subsystem was disabled
            this run -- see `_build_command_router`'s EP-026 wiring).
        """
        return self._semantic_service

    @property
    def compression_service(self) -> CompressionService | None:
        """Return the CompressionService built for EP-027, if available.

        Returns:
            The CompressionService instance, or None if `run()` has
            not completed (or the Context Compression subsystem was
            disabled this run -- see `_build_command_router`'s EP-027
            wiring).
        """
        return self._compression_service

    @property
    def agent_service(self) -> AgentService | None:
        """Return the AgentService built for EP-028, if available.

        Returns:
            The AgentService instance, or None if `run()` has not
            completed (or the Agent Framework subsystem was disabled
            this run -- see `_build_command_router`'s EP-028 wiring).
        """
        return self._agent_service

    @property
    def planning_service(self) -> PlanningService | None:
        """Return the PlanningService built for EP-029, if available.

        Returns:
            The PlanningService instance, or None if `run()`/`initialize()`
            has not completed (or the Planning Engine subsystem was
            disabled this run -- see `_build_command_router`'s EP-029
            wiring).
        """
        return self._planning_service

    @property
    def plan_execution_service(self) -> PlanExecutionService | None:
        """Return the PlanExecutionService built for EP-030, if available.

        Returns:
            The PlanExecutionService instance, or None if
            `run()`/`initialize()` has not completed (or the Plan
            Execution Engine subsystem was disabled this run -- see
            `_build_command_router`'s EP-030 wiring).
        """
        return self._plan_execution_service
