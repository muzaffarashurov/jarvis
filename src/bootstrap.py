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
from src.core.api.api_router import ApiRouter
from src.core.api.rest_api_server import RestApiServer, RestApiServerError
from src.core.collaboration.collaboration_engine import CollaborationEngine
from src.core.collaboration.collaboration_manager import CollaborationManager
from src.core.collaboration.collaboration_provider import CollaborationError
from src.core.command_router import CommandRouter
from src.core.config import Config, ConfigError
from src.core.context_compression.compression_engine import CompressionEngine
from src.core.context_compression.compression_manager import CompressionManager
from src.core.context_compression.compression_provider import ContextCompressionError
from src.core.planning.ai_planning_provider import AIPlanningProvider
from src.core.planning.planning_engine import PlanningEngine
from src.core.planning.planning_manager import PlanningManager
from src.core.planning.planning_provider import PlanningError
from src.core.plan_execution.plan_execution_engine import PlanExecutionEngine
from src.core.plan_execution.plan_execution_manager import PlanExecutionManager
from src.core.plan_execution.plan_execution_provider import PlanExecutionError
from src.core.tool.tool import Tool
from src.core.tool.tool_engine import ToolEngine
from src.core.tool.tool_execution_provider import ToolExecutionProvider
from src.core.tool.tool_manager import ToolManager
from src.core.tool.tool_provider import ToolError
from src.core.workflow_engine.workflow_engine import WorkflowEngine
from src.core.workflow_engine.workflow_engine_manager import WorkflowEngineManager
from src.core.workflow_engine.workflow_run_provider import WorkflowEngineError
from src.core.workflow_scheduler.scheduled_workflow_registry import ScheduledWorkflowRegistry
from src.core.workflow_scheduler.workflow_scheduler_engine import (
    WorkflowSchedulerEngine,
    WorkflowSchedulerError,
)
from src.core.automation_engine.automation_engine import AutomationEngine, AutomationError
from src.core.automation_engine.automation_rule_registry import AutomationRuleRegistry
from src.core.background_workers.background_worker_pool import BackgroundWorkerPoolError
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
from src.modules.collaboration_module import CollaborationModule
from src.modules.context_compression_module import ContextCompressionModule
from src.modules.planning_module import PlanningModule
from src.modules.plan_execution_module import PlanExecutionModule
from src.modules.tool_module import ToolModule
from src.modules.workflow_engine_module import WorkflowEngineModule
from src.modules.workflow_scheduler_module import WorkflowSchedulerModule
from src.modules.automation_module import AutomationModule
from src.modules.background_worker_module import BackgroundWorkerModule
from src.modules.git_module import GitModule
from src.modules.github_module import GitHubModule
from src.modules.telegram_info_module import TelegramInfoModule
from src.modules.discord_module import DiscordModule
from src.modules.email_module import EmailModule
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
from src.services.collaboration_service import CollaborationService
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
from src.services.tool_service import ToolService
from src.services.workflow_engine_service import WorkflowEngineService
from src.services.workflow_scheduler_service import WorkflowSchedulerService
from src.services.automation_service import AutomationService
from src.services.background_worker_service import (
    BackgroundWorkerService,
    BackgroundWorkerServiceError,
)
from src.services.git_service import GitService, GitServiceError
from src.services.github_service import GitHubService, GitHubServiceError
from src.services.telegram_info_service import TelegramInfoService, TelegramInfoServiceError
from src.services.discord_service import DiscordService, DiscordServiceError
from src.services.email_service import EmailService, EmailServiceError
from src.skills.voice.audio_capture import AudioCapture, AudioCaptureError
from src.skills.voice.speech_to_text import SpeechToTextEngineError, VoskSpeechToTextEngine
from src.skills.voice.streaming_audio_capture import (
    StreamingAudioCapture,
    StreamingAudioCaptureError,
)
from src.skills.voice.text_to_speech import (
    Pyttsx3TextToSpeechEngine,
    TextToSpeechEngine,
    TextToSpeechEngineError,
)
from src.skills.voice.wake_word import OpenWakeWordEngine, WakeWordEngine, WakeWordEngineError
from src.skills.voice.skill import VoiceModule
from src.skills.desktop.backend import ComputerUseBackend
from src.skills.desktop.skill import DesktopModule
from src.skills.desktop.windows_backend import (
    WindowsComputerUseBackend,
    WindowsComputerUseBackendError,
)
from src.skills.browser.backend import BrowserBackend
from src.skills.browser.skill import BrowserModule
from src.skills.browser.playwright_backend import (
    PlaywrightBrowserBackend,
    PlaywrightBrowserBackendError,
)
from src.skills.files.backend import FileBackend
from src.skills.files.skill import FileModule
from src.skills.files.local_backend import LocalFileBackend
from src.skills.vision.backend import VisionBackend
from src.skills.vision.skill import VisionModule
from src.skills.vision.local_backend import LocalVisionBackend
from src.skills.reflection.skill import ReflectionModule
from src.skills.prompt_optimizer.skill import PromptOptimizerModule
from src.skills.capability_registry.skill import CapabilityRegistryModule
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
        self._tool_service: ToolService | None = None
        self._collaboration_service: CollaborationService | None = None
        self._workflow_engine_service: WorkflowEngineService | None = None
        self._workflow_scheduler_service: WorkflowSchedulerService | None = None
        self._automation_service: AutomationService | None = None
        self._background_worker_service: BackgroundWorkerService | None = None
        self._git_service: GitService | None = None
        self._github_service: GitHubService | None = None
        self._telegram_info_service: TelegramInfoService | None = None
        self._discord_service: DiscordService | None = None
        self._email_service: EmailService | None = None
        self._rest_api_server: RestApiServer | None = None
        self._voice_engine: VoskSpeechToTextEngine | None = None
        self._voice_tts_engine: TextToSpeechEngine | None = None
        self._voice_wake_engine: WakeWordEngine | None = None
        self._voice_wake_capture: StreamingAudioCapture | None = None
        self._desktop_backend: ComputerUseBackend | None = None
        self._browser_backend: BrowserBackend | None = None
        self._file_backend: FileBackend | None = None
        self._vision_backend: VisionBackend | None = None
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
        self._rest_api_server = self._build_rest_api_server(self._command_router, self._config)

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

        # EP-054 Self Reflection. On-demand session/conversation
        # self-critique (Owner Decision D1, "Candidate A") via the
        # "reflect" CommandRouter namespace (see
        # src/skills/reflection/), dispatched through the same,
        # unmodified CommandRouter.dispatch() every other skill
        # already uses (EP054_DESIGN.md Section 3.7/20, Owner Decision
        # D8) -- no new dispatch mechanism, and Tool Engine is
        # untouched.
        #
        # Introduces no new backend Protocol (EP054_DESIGN.md Section
        # 6.2): ReflectionModule composes three already-existing,
        # unmodified components directly -- ConversationManager and
        # ai_provider_manager (both already constructed above, for
        # AIService's own use) and, optionally, self._memory_service
        # (constructed earlier, for MemoryModule's own use; may be
        # None if the Memory subsystem is disabled/unavailable --
        # ReflectionModule handles that by reporting a clear failure
        # for 'reflect recall' only when persistence is actually
        # requested, never by crashing).
        #
        # Mirrors DesktopModule/BrowserModule/FileModule/VisionModule's
        # wiring exactly: ReflectionModule is registered
        # unconditionally -- 'reflection.enabled' (default false) is
        # re-checked on every dispatched action inside ReflectionModule
        # itself (EP054_DESIGN.md Section 7/20), not only at
        # registration time. No construction-failure branch is needed
        # here (unlike LocalVisionBackend's Tesseract-adjacent
        # precedent) since ReflectionModule performs no I/O of its own
        # at construction time -- it only stores references to
        # already-constructed managers.
        router.register(
            ReflectionModule(
                config=config,
                conversation_manager=conversation_manager,
                provider_manager=ai_provider_manager,
                memory_service=self._memory_service,
            )
        )

        # EP-055 Prompt Optimizer. On-demand prompt/template
        # improvement (Owner Decision D1, "Candidate A") via the
        # "prompt" CommandRouter namespace (see
        # src/skills/prompt_optimizer/), dispatched through the same,
        # unmodified CommandRouter.dispatch() every other skill
        # already uses (EP055_DESIGN.md Section 3.9/20, Owner Decision
        # D7) -- no new dispatch mechanism, and Tool Engine is
        # untouched.
        #
        # Introduces no new backend Protocol (EP055_DESIGN.md Section
        # 6.2): PromptOptimizerModule composes one already-existing,
        # unmodified component directly -- ai_provider_manager (already
        # constructed above, for AIService's and ReflectionModule's own
        # use). It deliberately never receives prompt_manager or
        # context_manager -- EP-017's Prompt Engine
        # (Prompt/PromptBuilder/PromptManager) is left completely
        # unmodified and un-called by EP-055 (EP055_DESIGN.md Section
        # 14, DO NOT MODIFY); PromptOptimizerModule reads
        # 'paths.prompts' independently, the same directory
        # PromptBuilder.load_template() already reads, but never
        # constructs or calls PromptBuilder/PromptManager themselves.
        #
        # Mirrors DesktopModule/BrowserModule/FileModule/VisionModule/
        # ReflectionModule's wiring exactly: PromptOptimizerModule is
        # registered unconditionally -- 'prompt_optimizer.enabled'
        # (default false) is re-checked on every dispatched action
        # inside PromptOptimizerModule itself (EP055_DESIGN.md Section
        # 7/20), not only at registration time. No construction-failure
        # branch is needed here since PromptOptimizerModule performs no
        # I/O of its own at construction time -- it only stores a
        # reference to the already-constructed ai_provider_manager.
        #
        # Owner Decision D4: return-only in v1 -- no 'prompt save'
        # action and no filesystem-write capability exist.
        router.register(
            PromptOptimizerModule(
                config=config,
                provider_manager=ai_provider_manager,
            )
        )

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
        # -- reached via `compress_query()`, which EP-057 exposed as
        # the "compression query <text>" CLI command wired here).
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
        # `agent_manager_for_collaboration` is captured here (rather
        # than reading `self._agent_service` back) so EP-032's
        # Multi-Agent Collaboration can optionally reuse the same
        # AgentManager instance through its public `list_providers()`
        # method only -- see the EP-032 wiring further below. It stays
        # None whenever the Agent Framework itself is unavailable this
        # run.
        agent_engine_for_planning: AgentEngine | None = None
        agent_manager_for_collaboration: AgentManager | None = None
        try:
            agent_manager = AgentManager(config=config)
            agent_engine = AgentEngine(manager=agent_manager)
            agent_service = AgentService(manager=agent_manager, engine=agent_engine)
            self._agent_service = agent_service
            router.register(AgentModule(agent_service))
            agent_engine_for_planning = agent_engine
            agent_manager_for_collaboration = agent_manager

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
        # EP-058: Autonomous Planning registers a second, AI-/LLM-backed
        # PlanningProvider (`AIPlanningProvider`, "ai") alongside --
        # never replacing -- the deterministic "planning" provider
        # below, through PlanningManager's already-existing, generic
        # `register_provider()` public method only (see
        # src/core/planning/ai_planning_provider.py). Reuses the
        # already-constructed `ai_provider_manager` (EP-014) directly;
        # constructs no second AI-client mechanism of its own.
        # 'planning.default_provider' is untouched and stays "planning"
        # -- an operator must explicitly run 'planning use ai' (or set
        # 'planning.default_provider: "ai"') to select it, exactly the
        # way EP-031's `ToolExecutionProvider` is registered as an
        # additional plan-execution provider without becoming the
        # default.
        planning_engine_for_plan_execution: PlanningEngine | None = None
        try:
            planning_manager = PlanningManager(config=config)
            planning_manager.register_provider(AIPlanningProvider(provider_manager=ai_provider_manager))
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
        # `plan_execution_manager_for_tool_bridge` is captured here
        # (rather than reading `self._plan_execution_service` back) so
        # EP-031's Tool Engine can register its bridge provider
        # (`ToolExecutionProvider`) with the same live
        # `PlanExecutionManager` instance, through its existing public
        # `register_provider()` method only -- see the EP-031 wiring
        # immediately below. It stays None whenever Plan Execution
        # Engine itself is unavailable this run.
        #
        # `plan_execution_engine_for_workflow` is captured the same
        # way so EP-033's Workflow Engine can reuse the same live
        # `PlanExecutionEngine` instance, through its existing public
        # `execute_request()` method only -- see the EP-033 wiring
        # further below. It stays None whenever Plan Execution Engine
        # itself is unavailable this run.
        plan_execution_manager_for_tool_bridge: PlanExecutionManager | None = None
        plan_execution_engine_for_workflow: PlanExecutionEngine | None = None
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
            plan_execution_manager_for_tool_bridge = plan_execution_manager
            plan_execution_engine_for_workflow = plan_execution_engine
        except PlanExecutionError as exc:
            logger.error(
                f"Plan Execution Engine disabled: invalid 'plan_execution.*' configuration "
                f"({exc}). Fix config/config.yaml and restart to re-enable it."
            )
            self._plan_execution_service = None

        # EP-031: Tool Engine. Turns an already-identified
        # (subsystem, action) reference into a real invocation of an
        # already-implemented Engineering Package's public API -- no
        # AI reasoning, no planning, no plan walking, and no dispatch-
        # order/failure-policy logic is performed here or anywhere in
        # this package (see src/core/tool/__init__.py). ToolManager
        # owns provider registration, active-provider selection,
        # configuration loading ('tool.*') and the tool catalog
        # (ToolRegistry); ToolEngine is the provider-independent
        # pipeline that resolves a tool (by id or by
        # `(subsystem, action)`) and dispatches it to the active
        # ToolProvider.
        #
        # Built-in tools wrap only the already-built subsystem
        # *Service* instances' parameter-free public methods -- Tool
        # Engine never instantiates a subsystem service itself
        # (Dependency Policy). Per this project's Unknown API Policy,
        # the four EP-029 actions that require a text parameter
        # PlanStep does not carry (`generate_embedding`,
        # `retrieve_context`, `semantic_search`, `compress_context`)
        # are deliberately left unregistered rather than invented --
        # dispatching one of those produces an honest FAILED result
        # (see src/core/tool/__init__.py's naming/scope note).
        #
        # `ToolExecutionProvider` (the EP-030-anticipated
        # "Tool-Engine-backed provider") is registered with the same
        # live PlanExecutionManager captured above, through its
        # existing public `register_provider()` method only -- no
        # file under src/core/plan_execution/ is modified. It is
        # registered but NOT selected as the default plan-execution
        # provider: 'plan_execution.default_provider' in
        # config/config.yaml remains "plan_execution" unless an
        # operator explicitly runs 'execution use tool_engine',
        # preserving EP-030's exact default behavior.
        try:
            tool_manager = ToolManager(config=config)

            built_in_tools: list[Tool] = []
            if self._memory_service is not None:
                built_in_tools.append(
                    Tool(
                        id="memory_recall",
                        name="Memory Recall",
                        description="Retrieve relevant entries from the Memory Manager (EP-023).",
                        subsystem="memory",
                        action="retrieve_from_memory",
                        handler=self._memory_service.list_entries,
                    )
                )
            if self._knowledge_service is not None:
                built_in_tools.append(
                    Tool(
                        id="knowledge_query",
                        name="Knowledge Base Query",
                        description="Query the Knowledge Base for relevant records (EP-024).",
                        subsystem="knowledge",
                        action="query_knowledge_base",
                        handler=self._knowledge_service.list_records,
                    )
                )
            if self._long_term_memory_service is not None:
                built_in_tools.append(
                    Tool(
                        id="long_term_memory_query",
                        name="Long-Term Memory Query",
                        description="Query Long-Term Memory for persisted records (EP-025).",
                        subsystem="long_term_memory",
                        action="query_long_term_memory",
                        handler=self._long_term_memory_service.list_memories,
                    )
                )
            if self._agent_service is not None:
                built_in_tools.append(
                    Tool(
                        id="agent_coordinate",
                        name="Agent Subsystem Coordination",
                        description="Coordinate subsystems via the Agent Framework (EP-028).",
                        subsystem="agent",
                        action="coordinate_subsystems",
                        handler=self._agent_service.list_subsystems,
                    )
                )
            built_in_tools.append(
                Tool(
                    id="acknowledge_request",
                    name="Acknowledge Request",
                    description="Acknowledge a request with no matched subsystem.",
                    subsystem=None,
                    action="acknowledge_request",
                    handler=lambda: "Request acknowledged. No subsystem action was required.",
                )
            )

            for built_in_tool in built_in_tools:
                try:
                    tool_manager.register_tool(built_in_tool)
                except ToolError as exc:
                    logger.warning(f"Tool Engine could not register tool '{built_in_tool.id}': {exc}")

            tool_engine = ToolEngine(manager=tool_manager)
            tool_service = ToolService(manager=tool_manager, engine=tool_engine)
            self._tool_service = tool_service
            router.register(ToolModule(tool_service))

            if plan_execution_manager_for_tool_bridge is not None:
                try:
                    plan_execution_manager_for_tool_bridge.register_provider(
                        ToolExecutionProvider(tool_engine=tool_engine)
                    )
                except PlanExecutionError as exc:
                    logger.warning(f"Could not register Tool Engine as a plan-execution provider: {exc}")
        except ToolError as exc:
            logger.error(
                f"Tool Engine disabled: invalid 'tool.*' configuration ({exc}). "
                "Fix config/config.yaml and restart to re-enable it."
            )
            self._tool_service = None

        # EP-032: Multi-Agent Collaboration. Implements the Multi-Agent
        # Coordinator explicitly deferred by EP-028 through EP-030's
        # own docstrings -- deterministic, broadcast distribution of a
        # single request across every agent currently registered with
        # EP-028's Agent Framework, with each agent's own outcome
        # collected and reported. No AI reasoning, no negotiation, no
        # inter-agent messaging, and no AI provider call is performed
        # here or anywhere in this package (see
        # src/core/collaboration/__init__.py).
        #
        # CollaborationManager owns provider registration,
        # active-provider selection, and configuration loading
        # ('collaboration.*'); CollaborationEngine reads the live agent
        # catalog from the same `AgentManager` instance built for
        # EP-028 above, through its public `list_providers()` method
        # only, and dispatches to the active CollaborationProvider.
        #
        # Multi-Agent Collaboration has a hard dependency on a live
        # `AgentManager` instance existing this run: without one there
        # is no agent catalog whatsoever to coordinate. Note this is
        # distinct from the Agent Framework being merely *disabled*
        # ('agent.enabled: false') -- a disabled Agent Framework still
        # constructs a valid `AgentManager` with its catalog intact
        # (e.g. "jarvis" still registered, just not selected/READY),
        # so Multi-Agent Collaboration still wires up in that case and
        # will honestly report every agent UNAVAILABLE. Only a genuine
        # `AgentFrameworkError` above (invalid 'agent.*' configuration)
        # leaves `agent_manager_for_collaboration` None and skips this
        # subsystem entirely (not merely degraded).
        if agent_manager_for_collaboration is not None:
            try:
                collaboration_manager = CollaborationManager(config=config)
                collaboration_engine = CollaborationEngine(
                    manager=collaboration_manager, agent_manager=agent_manager_for_collaboration
                )
                collaboration_service = CollaborationService(
                    manager=collaboration_manager, engine=collaboration_engine
                )
                self._collaboration_service = collaboration_service
                router.register(CollaborationModule(collaboration_service))
            except CollaborationError as exc:
                logger.error(
                    f"Multi-Agent Collaboration disabled: invalid 'collaboration.*' "
                    f"configuration ({exc}). Fix config/config.yaml and restart to "
                    "re-enable it."
                )
                self._collaboration_service = None
        else:
            logger.warning(
                "Multi-Agent Collaboration disabled: the Agent Framework (EP-028) "
                "is unavailable this run."
            )
            self._collaboration_service = None

        # EP-033: Workflow Engine. Runs a named, ordered sequence of
        # plain-text requests (a `WorkflowDefinition`) as a single,
        # repeatable unit: each step is planned and executed through
        # EP-030's already-existing `PlanExecutionEngine.execute_request()`
        # (which itself already optionally calls EP-029's
        # `PlanningEngine.plan()`), in order, halting on failure per
        # 'workflow_engine.stop_on_failure'. No AI reasoning, no new
        # planning logic, and no direct real-subsystem/tool invocation
        # is performed here or anywhere in this package (see
        # src/core/workflow_engine/__init__.py, which also documents
        # why this package is deliberately namespaced apart from
        # EP-007's dormant, unrelated `src/core/workflows/` --
        # `WorkflowService`/`WorkflowModule` remain untouched and
        # unregistered, exactly as before this EP).
        #
        # WorkflowEngineManager owns provider registration,
        # active-provider selection, the stop-on-failure policy, and
        # the workflow definition catalog
        # ('workflow_engine.*'); WorkflowEngine reuses the same live
        # `PlanExecutionEngine` instance built for EP-030 above,
        # through its public `execute_request()` method only, and
        # dispatches each step through the active `WorkflowRunProvider`.
        #
        # Workflow Engine has a hard dependency on a live
        # `PlanExecutionEngine` instance existing this run: without one
        # there is nothing to actually plan and execute a step's
        # request. Only a genuine `PlanExecutionError` above (invalid
        # 'plan_execution.*' configuration) leaves
        # `plan_execution_engine_for_workflow` None and skips this
        # subsystem entirely (not merely degraded).
        # `workflow_engine_for_scheduler` is captured here (rather than
        # reading `self._workflow_engine_service` back) so EP-034's
        # Workflow Scheduler can reuse the same live `WorkflowEngine`
        # instance, through its existing public `run()` method only --
        # see the EP-034 wiring further below. It stays None whenever
        # Workflow Engine itself is unavailable this run.
        workflow_engine_for_scheduler: WorkflowEngine | None = None
        if plan_execution_engine_for_workflow is not None:
            try:
                workflow_engine_manager = WorkflowEngineManager(config=config)
                workflow_engine = WorkflowEngine(
                    manager=workflow_engine_manager,
                    plan_execution_engine=plan_execution_engine_for_workflow,
                )
                workflow_engine_service = WorkflowEngineService(
                    manager=workflow_engine_manager,
                    engine=workflow_engine,
                    event_bus=self._event_bus,
                )
                self._workflow_engine_service = workflow_engine_service
                router.register(WorkflowEngineModule(workflow_engine_service))
                workflow_engine_for_scheduler = workflow_engine
            except WorkflowEngineError as exc:
                logger.error(
                    f"Workflow Engine disabled: invalid 'workflow_engine.*' "
                    f"configuration ({exc}). Fix config/config.yaml and restart to "
                    "re-enable it."
                )
                self._workflow_engine_service = None
        else:
            logger.warning(
                "Workflow Engine disabled: the Plan Execution Engine (EP-030) is "
                "unavailable this run."
            )
            self._workflow_engine_service = None

        # EP-034: Workflow Scheduler. Gives an EP-033 WorkflowDefinition
        # a time trigger: runs it automatically on a schedule, by
        # calling EP-033's already-existing `WorkflowEngine.run()`
        # exclusively. No AI reasoning, no planning, and no direct
        # subsystem/tool invocation is performed here or anywhere in
        # this package (see src/core/workflow_scheduler/__init__.py,
        # which also documents why this package is deliberately
        # namespaced apart from EP-011's active, unrelated
        # `src/core/scheduler/` -- `Scheduler`/`SchedulerModule`/the
        # "scheduler" CLI namespace/`scheduler.*` config remain
        # completely untouched and unaffected, exactly as before this
        # EP).
        #
        # WorkflowSchedulerEngine owns its own ScheduledWorkflowRegistry
        # and reuses the same live `WorkflowEngine` instance built for
        # EP-033 above, through its public `run()` method only.
        # WorkflowSchedulerService owns 'workflow_scheduler.*'
        # configuration and its own, entirely separate background tick
        # thread (no shared state with EP-011's Scheduler thread).
        #
        # Workflow Scheduler has a hard dependency on a live
        # `WorkflowEngine` instance existing this run: without one
        # there is nothing to actually run a scheduled entry's
        # referenced workflow. Only a genuine `WorkflowEngineError`
        # above (invalid 'workflow_engine.*' configuration) -- or the
        # Plan Execution Engine itself being unavailable -- leaves
        # `workflow_engine_for_scheduler` None and skips this subsystem
        # entirely (not merely degraded).
        # `workflow_scheduler_engine_for_automation` is captured here
        # (mirroring `workflow_engine_for_scheduler` above). EP-037
        # STEP 2 migrated Bootstrap's own production wiring to
        # `AutomationEngine.notify_run()` subscribing to the
        # `"workflow.completed"` event instead of using this engine's
        # `set_automation_hook()` directly (see the EP-035/EP-037
        # wiring further below), so this reference is currently unused
        # by Bootstrap; it is kept for parity with
        # `workflow_engine_for_scheduler` and as a stable extension
        # point. It stays None whenever Workflow Scheduler itself is
        # unavailable this run.
        workflow_scheduler_engine_for_automation: WorkflowSchedulerEngine | None = None
        if workflow_engine_for_scheduler is not None:
            try:
                scheduled_workflow_registry = ScheduledWorkflowRegistry()
                workflow_scheduler_engine = WorkflowSchedulerEngine(
                    registry=scheduled_workflow_registry,
                    workflow_engine=workflow_engine_for_scheduler,
                    event_bus=self._event_bus,
                )
                workflow_scheduler_service = WorkflowSchedulerService(
                    config=config, engine=workflow_scheduler_engine
                )
                self._workflow_scheduler_service = workflow_scheduler_service
                router.register(WorkflowSchedulerModule(workflow_scheduler_service))
                workflow_scheduler_engine_for_automation = workflow_scheduler_engine
            except WorkflowSchedulerError as exc:
                logger.error(
                    f"Workflow Scheduler disabled: invalid configuration ({exc}). "
                    "Fix config/config.yaml and restart to re-enable it."
                )
                self._workflow_scheduler_service = None
        else:
            logger.warning(
                "Workflow Scheduler disabled: the Workflow Engine (EP-033) is "
                "unavailable this run."
            )
            self._workflow_scheduler_service = None

        # EP-035: Automation Engine. Chains one EP-033 workflow's
        # completion (started on-demand via WorkflowEngineService.run(),
        # or automatically via EP-034's WorkflowSchedulerEngine.run_now()
        # / tick()) into a second workflow run, based on outcome
        # (ON_SUCCESS / ON_FAILURE / ON_ANY), by calling EP-033's
        # already-existing `WorkflowEngine.run()` exclusively. No AI
        # reasoning, no scheduling of its own, no event bus, no
        # recursive chaining (see
        # src/core/automation_engine/__init__.py). Purely reactive: it
        # owns no background thread and never decides that a workflow
        # should run -- it is only ever told, after the fact, that one
        # already did.
        #
        # AutomationEngine reuses the same live `WorkflowEngine`
        # instance built for EP-033 above, through its public `run()`
        # method only, to dispatch a matched rule's action workflow.
        #
        # EP-037 MIGRATION NOTE: production wiring now reaches
        # `AutomationEngine.notify_run()` by subscribing it to the
        # `"workflow.completed"` event on `self._event_bus`, instead of
        # via `WorkflowEngineService.set_automation_hook()`/
        # `WorkflowSchedulerEngine.set_automation_hook()`. Both engines
        # publish the same `"workflow.completed"` event (see
        # src/services/workflow_engine_service.py and
        # src/core/workflow_scheduler/workflow_scheduler_engine.py), so
        # a single subscription here covers both an on-demand `flow
        # run` and a scheduled/`tick()`-driven run -- previously this
        # required two separate `set_automation_hook()` calls, one per
        # engine. The `set_automation_hook()` API and its call sites in
        # both engines are left fully intact for backward compatibility
        # (existing/external callers can still use it directly); this
        # is a change to *production Bootstrap wiring* only, not to
        # either engine's public API. Neither
        # `WorkflowEngineService`/`WorkflowSchedulerEngine` imports
        # `AutomationEngine` or any EP-035 type -- the dependency
        # direction stays one-way. The subscription is skipped entirely
        # when 'automation.enabled' is False, so a disabled Automation
        # Engine can never fire a rule, matching the hook-based
        # wiring's exact same gating.
        #
        # Automation Engine has a hard dependency on a live
        # `WorkflowEngine` instance existing this run: without one
        # there is nothing to actually dispatch a matched rule's
        # action workflow. Only a genuine `WorkflowEngineError` above
        # (invalid 'workflow_engine.*' configuration) -- or the Plan
        # Execution Engine itself being unavailable -- leaves
        # `workflow_engine_for_scheduler` None and skips this
        # subsystem entirely (not merely degraded).
        if workflow_engine_for_scheduler is not None:
            try:
                automation_rule_registry = AutomationRuleRegistry()
                automation_engine = AutomationEngine(
                    registry=automation_rule_registry,
                    workflow_engine=workflow_engine_for_scheduler,
                )
                automation_service = AutomationService(config=config, engine=automation_engine)
                self._automation_service = automation_service
                router.register(AutomationModule(automation_service))

                if bool(config.get("automation.enabled", True)):
                    self._event_bus.subscribe("workflow.completed", automation_engine.notify_run)

                    # EP-037 STEP 3: BackgroundWorkerPool (EP-036) calls
                    # `WorkflowEngine.run()` directly, not through
                    # `WorkflowEngineService`, so a `worker submit` task
                    # never publishes `"workflow.completed"` and had no
                    # path to automation at all. This adapter closes that
                    # gap for a task's *successful* completion only, by
                    # re-keying `background_worker.task_completed`'s
                    # existing `workflow_id` kwarg (see
                    # src/core/background_workers/background_worker_pool.py)
                    # to the `definition_id` kwarg `notify_run()` expects --
                    # STEP 2's event payload contracts are left completely
                    # unchanged. Deliberately NOT subscribed to
                    # `"background_worker.task_failed"`: that event carries
                    # only `error: str`, never a `WorkflowRunResult`, which
                    # `notify_run()` requires and which a bare exception
                    # (e.g. a provider defect) never produces in the first
                    # place. A background task's own failure therefore
                    # cannot trigger automation, matching the same
                    # ON_SUCCESS/ON_FAILURE/ON_ANY semantics `notify_run()`
                    # already applies uniformly to every *successful* run
                    # dispatch, regardless of path.
                    #
                    # This cannot double-trigger a rule together with the
                    # `"workflow.completed"` subscription above: the two
                    # event names are disjoint, each has exactly one
                    # subscriber, and `BackgroundWorkerPool` never publishes
                    # `"workflow.completed"` -- a given task submission
                    # produces exactly one of `task_completed`/`task_failed`,
                    # never both, and never `workflow.completed` too.
                    def _on_background_worker_task_completed(**kwargs) -> None:
                        automation_engine.notify_run(
                            definition_id=kwargs["workflow_id"], result=kwargs["result"]
                        )

                    self._event_bus.subscribe(
                        "background_worker.task_completed", _on_background_worker_task_completed
                    )
            except AutomationError as exc:
                logger.error(
                    f"Automation Engine disabled: invalid configuration ({exc}). "
                    "Fix config/config.yaml and restart to re-enable it."
                )
                self._automation_service = None
        else:
            logger.warning(
                "Automation Engine disabled: the Workflow Engine (EP-033) is "
                "unavailable this run."
            )
            self._automation_service = None

        # EP-036 STEP 2: Background Worker Service. Owns configuration
        # resolution and the lifecycle of a single EP-036
        # `BackgroundWorkerPool` (STEP 1, unchanged) -- a pool of
        # daemon worker threads that run already-registered EP-033
        # workflows off the calling thread, by calling EP-033's
        # already-existing `WorkflowEngine.run()` exclusively. No AI
        # reasoning, no planning, and no direct real-subsystem/tool
        # invocation is performed here or anywhere in this package
        # (see src/services/background_worker_service.py).
        #
        # EP-036 STEP 3: registers `BackgroundWorkerModule` (the
        # "worker" CLI command namespace) below, once the service
        # itself is confirmed available -- STEP 2's own Service API
        # is unchanged; STEP 3 only adds this additive translation
        # layer on top of it (see
        # src/modules/background_worker_module.py).
        #
        # BackgroundWorkerService reuses the same live `WorkflowEngine`
        # instance built for EP-033 above, through its public `run()`
        # method only (reached exclusively via `BackgroundWorkerPool`).
        #
        # Background Worker Pool has a hard dependency on a live
        # `WorkflowEngine` instance existing this run: without one
        # there is nothing to actually run a submitted task's
        # workflow. Only a genuine `WorkflowEngineError` above
        # (invalid 'workflow_engine.*' configuration) -- or the Plan
        # Execution Engine itself being unavailable -- leaves
        # `workflow_engine_for_scheduler` None and skips this
        # subsystem entirely (not merely degraded), mirroring EP-034/
        # EP-035's own hard-dependency handling above.
        if workflow_engine_for_scheduler is not None:
            try:
                background_worker_service = BackgroundWorkerService(
                    config=config,
                    workflow_engine=workflow_engine_for_scheduler,
                    event_bus=self._event_bus,
                )
                self._background_worker_service = background_worker_service
                router.register(BackgroundWorkerModule(background_worker_service))
            except (BackgroundWorkerServiceError, BackgroundWorkerPoolError) as exc:
                logger.error(
                    f"Background Worker Service disabled: invalid "
                    f"'background_workers.*' configuration ({exc}). Fix "
                    "config/config.yaml and restart to re-enable it."
                )
                self._background_worker_service = None
        else:
            logger.warning(
                "Background Worker Service disabled: the Workflow Engine "
                "(EP-033) is unavailable this run."
            )
            self._background_worker_service = None

        # EP-038 Git Integration. Unlike every EP-034/035/036 subsystem
        # above, GitService has no dependency on any other Engineering
        # Package's service or engine -- it depends only on Config and
        # the filesystem -- so there is no "if <some other EP's engine>
        # is not None" hard-dependency gate here, just the same
        # 'enabled' + config-validation try/except every subsystem uses.
        if bool(config.get("git.enabled", True)):
            try:
                configured_repository_path = config.get("git.repository_path", None)
                git_service = GitService(
                    config=config,
                    repository_path=(
                        Path(configured_repository_path)
                        if configured_repository_path
                        else self._project_root
                    ),
                )
                self._git_service = git_service
                router.register(GitModule(git_service))
            except GitServiceError as exc:
                logger.error(
                    f"Git Service disabled: invalid 'git.*' configuration or "
                    f"repository ({exc}). Fix config/config.yaml and restart "
                    "to re-enable it."
                )
                self._git_service = None
        else:
            logger.info("Git Service disabled ('git.enabled: false').")
            self._git_service = None

        # EP-039 GitHub Integration. Like GitService, GitHubService has
        # no dependency on any other Engineering Package's service or
        # engine -- it depends only on Config and, at call time, the
        # process environment (GITHUB_TOKEN) -- so there is no
        # cross-EP hard-dependency gate here either, just the same
        # 'enabled' + config-validation try/except every subsystem
        # uses. GITHUB_TOKEN itself is never read here or anywhere in
        # Bootstrap -- GitHubService reads it directly from the
        # environment at call time (see src/services/github_service.py).
        if bool(config.get("github.enabled", True)):
            try:
                github_service = GitHubService(config=config)
                self._github_service = github_service
                router.register(GitHubModule(github_service))
            except GitHubServiceError as exc:
                logger.error(
                    f"GitHub Service disabled: invalid 'github.*' configuration "
                    f"({exc}). Fix config/config.yaml and restart to re-enable it."
                )
                self._github_service = None
        else:
            logger.info("GitHub Service disabled ('github.enabled: false').")
            self._github_service = None

        # EP-040 Telegram Info. Architecturally independent of EP-012
        # "Telegram Gateway" (src/core/telegram/, src/services/telegram_service.py,
        # src/modules/telegram_module.py) -- none of those files are
        # imported, modified, or referenced here or anywhere in
        # TelegramInfoService/TelegramInfoModule. This subsystem
        # constructs its own, separate telegram.Bot connection and
        # never calls fetch_updates()/get_updates() or touches EP-012's
        # update offset/cursor, so the two subsystems cannot race or
        # interfere with each other even when both are enabled at
        # once. The only thing shared with EP-012 is the existing
        # 'telegram.token' config value, read read-only by
        # TelegramInfoService itself -- never read or duplicated here.
        # No cross-EP hard-dependency gate is needed either, matching
        # GitService/GitHubService's own zero-dependency shape.
        if bool(config.get("telegram_info.enabled", True)):
            try:
                telegram_info_service = TelegramInfoService(config=config)
                self._telegram_info_service = telegram_info_service
                router.register(TelegramInfoModule(telegram_info_service))
            except TelegramInfoServiceError as exc:
                logger.error(
                    f"Telegram Info Service disabled: invalid configuration or "
                    f"missing token ({exc}). Fix config/config.yaml and restart "
                    "to re-enable it."
                )
                self._telegram_info_service = None
        else:
            logger.info("Telegram Info Service disabled ('telegram_info.enabled: false').")
            self._telegram_info_service = None

        # EP-041 Discord Integration. Like GitHubService, DiscordService
        # has no dependency on any other Engineering Package's service
        # or engine -- it depends only on Config and, at call time, the
        # process environment (DISCORD_TOKEN) -- so there is no
        # cross-EP hard-dependency gate here either, just the same
        # 'enabled' + config-validation try/except every subsystem
        # uses. DISCORD_TOKEN itself is never read here or anywhere in
        # Bootstrap -- DiscordService reads it directly from the
        # environment at call time (see src/services/discord_service.py).
        # DiscordService is stateless REST-only -- no Gateway/WebSocket,
        # no persistent connection, no cursor/offset -- so a future
        # Discord Gateway EP could coexist without sharing state.
        if bool(config.get("discord.enabled", True)):
            try:
                discord_service = DiscordService(config=config)
                self._discord_service = discord_service
                router.register(DiscordModule(discord_service))
            except DiscordServiceError as exc:
                logger.error(
                    f"Discord Service disabled: invalid 'discord.*' configuration "
                    f"({exc}). Fix config/config.yaml and restart to re-enable it."
                )
                self._discord_service = None
        else:
            logger.info("Discord Service disabled ('discord.enabled: false').")
            self._discord_service = None

        # EP-042 Email Integration. Read-only IMAP-only email access.
        # Like DiscordService/GitHubService, EmailService has no
        # dependency on any other Engineering Package's service or
        # engine. Credentials are never read here or anywhere in
        # Bootstrap -- EmailService reads them directly from the
        # environment (via the two configured environment-variable
        # names) at call time. EmailService opens/closes one
        # short-lived IMAP connection per operation call -- no
        # persistent connection, background thread, or polling is
        # started at construction time.
        #
        # Unlike discord/github/telegram_info above, "email.enabled"
        # defaults to false: IMAP has no safe universal default host
        # (unlike a fixed REST API root), so this subsystem stays off
        # until an operator supplies 'email.imap_host' and explicitly
        # enables it (see EP042_DESIGN.md, section 10).
        if bool(config.get("email.enabled", False)):
            try:
                email_service = EmailService(config=config)
                self._email_service = email_service
                router.register(EmailModule(email_service))
            except EmailServiceError as exc:
                logger.error(
                    f"Email Service disabled: invalid 'email.*' configuration "
                    f"({exc}). Fix config/config.yaml and restart to re-enable it."
                )
                self._email_service = None
        else:
            logger.info("Email Service disabled ('email.enabled: false').")
            self._email_service = None

        # EP-046 Speech-to-Text. Offline audio-to-text transcription
        # (Vosk, see src/skills/voice/speech_to_text.py) feeding
        # recognized text into the existing CommandRouter -- the same
        # dispatch() entry point InteractiveShell/TelegramRouter/
        # ApiRouter already use (see src/core/command_router.py). No
        # new dispatch mechanism; CommandRouter itself is unchanged.
        #
        # EP-047 Text-to-Speech. Offline text-to-audio (pyttsx3, see
        # src/skills/voice/text_to_speech.py), wired into the same
        # "voice" CommandModule above as an additive "speak" action --
        # no second namespace, no new dispatch mechanism
        # (EP047_DESIGN.md Section 5.3/9a, owner Decision D3).
        #
        # EP-048 Wake Word. Offline wake-phrase detection
        # (openWakeWord, see src/skills/voice/wake_word.py +
        # src/skills/voice/streaming_audio_capture.py), wired into the
        # same "voice" CommandModule as additive "wake listen"/
        # "wake status" actions -- again no second namespace, no new
        # dispatch mechanism, and no automatic dispatch/STT/TTS
        # triggered by a detection (EP048_DESIGN.md Section 5.4/9a,
        # owner Decision D5).
        #
        # Each of "voice.enabled" (STT), "voice.tts.enabled" (TTS),
        # and "voice.wake.enabled" (Wake Word) defaults to false and
        # is constructed independently, in its own try/except: a
        # failure or a disabled flag in one subsystem never disables
        # another, mirroring Email/DiscordService's own "not
        # registered when disabled" precedent. Each subsystem claims
        # a hardware resource (microphone) or a real dependency, so
        # each stays off until explicitly enabled (EP046_DESIGN.md
        # Section 6, owner Decision 7).
        #
        # The "voice" CommandModule itself is registered as soon as
        # *any* of the three flags is true (EP048_DESIGN.md Section
        # 9a, owner Decision D6) -- this widens EP-047's own as-built
        # gate, which required "voice.enabled" (STT) to also be true
        # before TTS-only operation was reachable at all
        # (EP047_DESIGN.md Section 6 as-built addendum). A subsystem
        # that is disabled or failed to construct is passed into
        # VoiceModule as None; every "voice" action already reports a
        # clear, non-crashing failure for its own None collaborator
        # (see skill.py) -- EP-046's and EP-047's existing, already-
        # shipped behavior is unchanged when their own flags are
        # enabled exactly as before.
        voice_enabled = bool(config.get("voice.enabled", False))
        voice_tts_enabled = bool(config.get("voice.tts.enabled", False))
        voice_wake_enabled = bool(config.get("voice.wake.enabled", False))

        if voice_enabled or voice_tts_enabled or voice_wake_enabled:
            voice_engine: VoskSpeechToTextEngine | None = None
            voice_audio_capture: AudioCapture | None = None
            if voice_enabled:
                try:
                    voice_engine = VoskSpeechToTextEngine(config=config)
                    voice_audio_capture = AudioCapture(config=config)
                except (SpeechToTextEngineError, AudioCaptureError) as exc:
                    logger.error(
                        f"Voice Speech-to-Text disabled: invalid 'voice.*' "
                        f"configuration or missing model/dependency ({exc}). "
                        f"Fix config/config.yaml, place the required Vosk "
                        f"models, and restart to re-enable it. "
                        f"Text-to-Speech/Wake Word are unaffected."
                    )
                    voice_engine = None
                    voice_audio_capture = None
            else:
                logger.info("Voice Speech-to-Text disabled ('voice.enabled: false').")
            self._voice_engine = voice_engine

            voice_tts_engine: TextToSpeechEngine | None = None
            if voice_tts_enabled:
                try:
                    voice_tts_engine = Pyttsx3TextToSpeechEngine(config=config)
                except TextToSpeechEngineError as tts_exc:
                    logger.error(
                        f"Voice Text-to-Speech disabled: invalid 'voice.tts.*' "
                        f"configuration or missing engine/dependency ({tts_exc}). "
                        f"'voice speak' will report failure until this is fixed; "
                        f"Speech-to-Text/Wake Word are unaffected."
                    )
                    voice_tts_engine = None
            else:
                logger.info(
                    "Voice Text-to-Speech disabled ('voice.tts.enabled: false')."
                )
            self._voice_tts_engine = voice_tts_engine

            voice_wake_engine: WakeWordEngine | None = None
            voice_wake_capture: StreamingAudioCapture | None = None
            if voice_wake_enabled:
                try:
                    voice_wake_engine = OpenWakeWordEngine(config=config)
                    voice_wake_capture = StreamingAudioCapture(config=config)
                except (WakeWordEngineError, StreamingAudioCaptureError) as wake_exc:
                    logger.error(
                        f"Voice Wake Word disabled: invalid 'voice.wake.*' "
                        f"configuration or missing model/dependency "
                        f"({wake_exc}). Fix config/config.yaml, place the "
                        f"required openWakeWord model files under "
                        f"'voice.wake.model_dir', and restart to re-enable "
                        f"it. Speech-to-Text/Text-to-Speech are unaffected."
                    )
                    voice_wake_engine = None
                    voice_wake_capture = None
            else:
                logger.info(
                    "Voice Wake Word disabled ('voice.wake.enabled: false')."
                )
            self._voice_wake_engine = voice_wake_engine
            self._voice_wake_capture = voice_wake_capture

            router.register(
                VoiceModule(
                    config=config,
                    command_router=router,
                    engine=voice_engine,
                    audio_capture=voice_audio_capture,
                    tts_engine=voice_tts_engine,
                    wake_engine=voice_wake_engine,
                    wake_capture=voice_wake_capture,
                )
            )
        else:
            logger.info(
                "Voice disabled ('voice.enabled', 'voice.tts.enabled', and "
                "'voice.wake.enabled' are all false)."
            )
            self._voice_engine = None
            self._voice_tts_engine = None
            self._voice_wake_engine = None
            self._voice_wake_capture = None

        # EP-050 Computer Use. Raw OS-level input control
        # (mouse/keyboard/clipboard/screenshot/window-focus) via
        # ComputerUseBackend (src/skills/desktop/backend.py),
        # dispatched through the same, unmodified
        # CommandRouter.dispatch() every other skill already uses
        # (EP050_DESIGN.md Section 9/32.2) -- no new dispatch
        # mechanism, and Tool Engine is untouched (EP050_DESIGN.md
        # Section 11/32.1: Tool Engine's Tool.handler is
        # zero-argument-only for every action already registered in
        # this project, not a gap EP-050 works around).
        #
        # Unlike Voice above, DesktopModule is registered
        # unconditionally when constructed -- 'desktop.enabled'
        # (default false) is re-checked on every dispatched action
        # inside DesktopModule itself (EP050_DESIGN.md Section 16/20,
        # Owner Decision D2), not only at registration time. The
        # *backend* is still only constructed when the flag is true,
        # matching every other subsystem's "don't do the work if it's
        # off" convention and avoiding an unconditional PyAutoGUI
        # import attempt on every single startup.
        if bool(config.get("desktop.enabled", False)):
            try:
                desktop_backend: ComputerUseBackend | None = WindowsComputerUseBackend(config=config)
            except WindowsComputerUseBackendError as exc:
                logger.error(
                    f"Computer Use backend unavailable: {exc}. 'desktop' "
                    f"actions will report failure until this is resolved "
                    f"and Jarvis is restarted."
                )
                desktop_backend = None
        else:
            logger.info("Computer Use disabled ('desktop.enabled: false').")
            desktop_backend = None
        self._desktop_backend = desktop_backend
        router.register(DesktopModule(config=config, backend=desktop_backend))

        # EP-051 Browser Automation. Controlled browser interaction
        # (launch, navigate, observe, and drive simple DOM
        # interactions) via BrowserBackend (src/skills/browser/
        # backend.py), dispatched through the same, unmodified
        # CommandRouter.dispatch() every other skill already uses
        # (EP051_DESIGN.md Section 9/11, Owner Decision D4) -- no new
        # dispatch mechanism, and Tool Engine is untouched.
        #
        # Mirrors DesktopModule's wiring exactly: BrowserModule is
        # registered unconditionally when constructed --
        # 'browser.enabled' (default false) is re-checked on every
        # dispatched action inside BrowserModule itself
        # (EP051_DESIGN.md Section 14, Owner Decision D2), not only at
        # registration time. The *backend* is still only constructed
        # when the flag is true, matching every other subsystem's
        # "don't do the work if it's off" convention and avoiding an
        # unconditional Playwright import attempt on every single
        # startup.
        if bool(config.get("browser.enabled", False)):
            try:
                browser_backend: BrowserBackend | None = PlaywrightBrowserBackend(config=config)
            except PlaywrightBrowserBackendError as exc:
                logger.error(
                    f"Browser Automation backend unavailable: {exc}. 'browser' "
                    f"actions will report failure until this is resolved "
                    f"and Jarvis is restarted."
                )
                browser_backend = None
        else:
            logger.info("Browser Automation disabled ('browser.enabled: false').")
            browser_backend = None
        self._browser_backend = browser_backend
        router.register(BrowserModule(config=config, backend=browser_backend))

        # EP-052 File Automation. Controlled local filesystem
        # automation (list/exists/stat/read/write/copy/move/mkdir/
        # delete) via FileBackend (src/skills/files/backend.py),
        # dispatched through the same, unmodified
        # CommandRouter.dispatch() every other skill already uses
        # (EP052_DESIGN.md Section 9, Owner Decision D9) -- no new
        # dispatch mechanism, and Tool Engine is untouched.
        #
        # Mirrors DesktopModule/BrowserModule's wiring exactly:
        # FileModule is registered unconditionally when constructed --
        # 'file.enabled' (default false) is re-checked on every
        # dispatched action inside FileModule itself (EP052_DESIGN.md
        # Section 16/20, Owner Decision D2), not only at registration
        # time. The *backend* is still only constructed when the flag
        # is true, matching every other subsystem's "don't do the
        # work if it's off" convention. Unlike WindowsComputerUseBackend/
        # PlaywrightBrowserBackend, LocalFileBackend has no real
        # construction-time dependency (no display, no browser
        # binary, no new third-party import, Owner Decision D1) so no
        # construction-failure branch is needed here.
        if bool(config.get("file.enabled", False)):
            file_backend: FileBackend | None = LocalFileBackend()
        else:
            logger.info("File Automation disabled ('file.enabled: false').")
            file_backend = None
        self._file_backend = file_backend
        router.register(FileModule(config=config, backend=file_backend))

        # EP-053 Vision Integration. Local, read-only image
        # interpretation (metadata + OCR text extraction) via
        # VisionBackend (src/skills/vision/backend.py), dispatched
        # through the same, unmodified CommandRouter.dispatch() every
        # other skill already uses (EP053_DESIGN.md Section 9, Owner
        # Decision D9) -- no new dispatch mechanism, and Tool Engine
        # is untouched.
        #
        # Mirrors DesktopModule/BrowserModule/FileModule's wiring
        # exactly: VisionModule is registered unconditionally when
        # constructed -- 'vision.enabled' (default false) is
        # re-checked on every dispatched action inside VisionModule
        # itself (EP053_DESIGN.md Section 11/20, Owner Decision D1),
        # not only at registration time. The *backend* is still only
        # constructed when the flag is true, matching every other
        # subsystem's "don't do the work if it's off" convention.
        # Like LocalFileBackend, LocalVisionBackend has no real
        # construction-time dependency (no display, no external
        # binary check at construction -- the Tesseract OCR binary is
        # only ever invoked lazily, per 'vision ocr' call, Owner
        # Decision D8) so no construction-failure branch is needed
        # here. v1 is local-only (Owner Decision D1): no AI-provider/
        # network path exists in this wiring.
        if bool(config.get("vision.enabled", False)):
            vision_backend: VisionBackend | None = LocalVisionBackend(config=config)
        else:
            logger.info("Vision Integration disabled ('vision.enabled: false').")
            vision_backend = None
        self._vision_backend = vision_backend
        router.register(VisionModule(config=config, backend=vision_backend))

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

        # EP-056 Capability Registry ("Capability Learning"). On-demand
        # composition of Jarvis's currently available capabilities
        # (Owner Decision D1, "Candidate A") via the "capability"
        # CommandRouter namespace (see src/skills/capability_registry/),
        # dispatched through the same, unmodified
        # CommandRouter.dispatch() every other skill already uses
        # (EP056_DESIGN.md Section 3.7/20, Owner Decision D7) -- no new
        # dispatch mechanism, and Tool Engine is untouched.
        #
        # Bootstrap ordering (Owner Decision D5, EP056_DESIGN.md
        # Section 3.8/14): CapabilityRegistryModule depends on
        # plugin_service, which is not constructed until here -- much
        # later than ai_provider_manager/prompt_manager above -- so
        # this registration deliberately sits immediately after
        # plugin_service's own construction and PluginModule's own
        # registration, not alongside the Prompt Engine's wiring.
        #
        # Introduces no new backend Protocol (EP056_DESIGN.md Section
        # 6.2): CapabilityRegistryModule composes three already-
        # existing, unmodified components directly -- plugin_service
        # (already constructed above, read-only via
        # running_plugins()), router.module_names (a bound method,
        # read-only), and prompt_manager (already constructed above,
        # for AIService's own use; "capability inject" calls its
        # existing, previously-unused build(capabilities=...) seam,
        # never modifying PromptManager/PromptBuilder themselves --
        # EP-017's Prompt Engine is left completely unmodified and
        # never autonomously invoked by EP-056, EP055_DESIGN.md
        # Section 14, DO NOT MODIFY, still applies to EP-056 too).
        #
        # Mirrors DesktopModule/BrowserModule/FileModule/VisionModule/
        # ReflectionModule/PromptOptimizerModule's wiring exactly:
        # CapabilityRegistryModule is registered unconditionally --
        # 'capability_registry.enabled' (default false) is re-checked
        # on every dispatched action inside CapabilityRegistryModule
        # itself (EP056_DESIGN.md Section 7/20), not only at
        # registration time. No construction-failure branch is needed
        # here since CapabilityRegistryModule performs no I/O of its
        # own at construction time -- it only stores references to
        # already-constructed collaborators.
        #
        # Owner Decision D3: no separate privacy/AI-provider gate --
        # "capability list"/"capability inject" make no AI-provider
        # call and disclose nothing "plugin status"/"plugin info"
        # do not already disclose today.
        #
        # STEP 4 fix (Owner Decision D8, EP056_ARCHITECTURE_AUDIT.md
        # Finding 1): `CommandRouter.module_names` is a @property, not
        # a plain method -- `router.module_names` alone evaluates it
        # immediately to a `list[str]` at construction time, not a
        # callable, which crashed every "capability list"/"capability
        # inject" call with `TypeError: 'list' object is not
        # callable`. Wrapping it in a lambda defers evaluation to
        # dispatch time, satisfying CapabilityRegistryModule's own
        # documented `Callable[[], list[str]]` contract and correctly
        # reflecting any namespace (e.g. "scheduler", "telegram",
        # "test") registered after this point in Bootstrap.
        router.register(
            CapabilityRegistryModule(
                config=config,
                plugin_service=plugin_service,
                module_names=lambda: router.module_names,
                prompt_manager=prompt_manager,
            )
        )

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

    def _build_rest_api_server(
        self, command_router: CommandRouter, config: Config
    ) -> RestApiServer | None:
        """Build and, if enabled, start the EP-043 REST API server.

        Follows the same '<name>.enabled' config-gating convention as
        every EP-038..EP-042 subsystem, but 'api.enabled' defaults to
        False -- unlike Discord/GitHub/Telegram Info's 'true' default.
        Those subsystems are stateless, per-call outbound clients with
        no observable effect when idle; RestApiServer is Jarvis's
        first component that binds and listens on a real network
        socket as a side effect of `initialize()`. Many existing tests
        across EP-001..EP-042 construct a real Bootstrap purely to
        verify dependency-injection wiring (calling `initialize()`
        without `run()`, and without ever calling `shutdown()`); none
        of their configs include an 'api' section, so they are
        unaffected either way, but defaulting new subsystems that open
        a socket to 'off' is the safe default going forward too.

        Args:
            command_router: The fully populated CommandRouter, shared
                unchanged with InteractiveShell and (if applicable)
                TelegramRouter -- see ApiRouter.
            config: The loaded application configuration.

        Returns:
            The started RestApiServer, or None if 'api.enabled' is
            False (the default) or the configured host/port could not
            be bound.
        """
        if not bool(config.get("api.enabled", False)):
            logger.info("REST API Server disabled ('api.enabled: false').")
            return None

        host = config.get("api.host", "127.0.0.1")
        port = config.get("api.port", 8080)
        static_dir = self._resolve_web_dashboard_dir(config)
        api_router = ApiRouter(command_router=command_router)
        server = RestApiServer(api_router=api_router, host=host, port=port, static_dir=static_dir)
        try:
            server.start()
        except RestApiServerError as exc:
            logger.error(
                f"REST API Server disabled: invalid 'api.*' configuration or the "
                f"configured host/port could not be bound ({exc}). Fix "
                f"config/config.yaml and restart to re-enable it."
            )
            return None
        return server

    def _resolve_web_dashboard_dir(self, config: Config) -> Path | None:
        """Resolve the EP-045 Web Dashboard's static-file directory, if configured.

        Returns None -- RestApiServer then behaves exactly as it did
        before EP-045, serving no static files -- when
        'api.web_dashboard_dir' is absent/empty, or when the
        configured directory does not exist on disk. A missing or
        misconfigured value degrades safely rather than crashing
        Bootstrap.initialize(), mirroring the same tolerant-degrade
        convention already used for 'api.enabled'/'api.port'
        (see `_build_rest_api_server`).

        Args:
            config: The loaded application configuration.

        Returns:
            The resolved, existing static-file directory, or None.
        """
        raw = config.get("api.web_dashboard_dir", "")
        if not raw:
            return None

        candidate = (self._project_root / raw).resolve()
        if not candidate.is_dir():
            logger.warning(
                f"'api.web_dashboard_dir' ({raw!r}) does not exist; the EP-045 "
                f"Web Dashboard will not be served."
            )
            return None
        return candidate

    def shutdown(self) -> None:
        """Stop any background component started by this Bootstrap.

        Currently only the EP-043 REST API server needs an explicit
        stop -- every other subsystem built by `initialize()` is a
        stateless, per-call client with no background thread or open
        socket. Safe to call multiple times, and safe to call even if
        the REST API server was never started/enabled.
        """
        if self._rest_api_server is not None:
            self._rest_api_server.stop()
            self._rest_api_server = None

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

    @property
    def tool_service(self) -> ToolService | None:
        """Return the ToolService built for EP-031, if available.

        Returns:
            The ToolService instance, or None if `run()`/`initialize()`
            has not completed (or the Tool Engine subsystem was
            disabled this run -- see `_build_command_router`'s EP-031
            wiring).
        """
        return self._tool_service

    @property
    def collaboration_service(self) -> CollaborationService | None:
        """Return the CollaborationService built for EP-032, if available.

        Returns:
            The CollaborationService instance, or None if
            `run()`/`initialize()` has not completed (or the
            Multi-Agent Collaboration subsystem was disabled this run,
            or the Agent Framework it depends on was unavailable this
            run -- see `_build_command_router`'s EP-032 wiring).
        """
        return self._collaboration_service

    @property
    def workflow_engine_service(self) -> WorkflowEngineService | None:
        """Return the WorkflowEngineService built for EP-033, if available.

        Returns:
            The WorkflowEngineService instance, or None if
            `run()`/`initialize()` has not completed (or the Workflow
            Engine subsystem was disabled this run, or the Plan
            Execution Engine it depends on was unavailable this run --
            see `_build_command_router`'s EP-033 wiring).
        """
        return self._workflow_engine_service

    @property
    def workflow_scheduler_service(self) -> WorkflowSchedulerService | None:
        """Return the WorkflowSchedulerService built for EP-034, if available.

        Returns:
            The WorkflowSchedulerService instance, or None if
            `run()`/`initialize()` has not completed (or the Workflow
            Scheduler subsystem was disabled this run, or the Workflow
            Engine it depends on was unavailable this run -- see
            `_build_command_router`'s EP-034 wiring).
        """
        return self._workflow_scheduler_service

    @property
    def automation_service(self) -> AutomationService | None:
        """Return the AutomationService built for EP-035, if available.

        Returns:
            The AutomationService instance, or None if
            `run()`/`initialize()` has not completed (or the
            Automation Engine subsystem was disabled this run, or the
            Workflow Engine it depends on was unavailable this run --
            see `_build_command_router`'s EP-035 wiring).
        """
        return self._automation_service

    @property
    def background_worker_service(self) -> BackgroundWorkerService | None:
        """Return the BackgroundWorkerService built for EP-036 STEP 2, if available.

        Returns:
            The BackgroundWorkerService instance, or None if
            `run()`/`initialize()` has not completed (or the
            Background Worker Service subsystem was disabled this
            run, or invalid 'background_workers.*' configuration was
            supplied, or the Workflow Engine it depends on was
            unavailable this run -- see `_build_command_router`'s
            EP-036 wiring).
        """
        return self._background_worker_service

    @property
    def git_service(self) -> GitService | None:
        """Return the GitService built for EP-038, if available.

        Returns:
            The GitService instance, or None if `run()`/`initialize()`
            has not completed (or the Git Service subsystem was
            disabled this run, or invalid 'git.*' configuration or
            repository path was supplied -- see
            `_build_command_router`'s EP-038 wiring).
        """
        return self._git_service

    @property
    def github_service(self) -> GitHubService | None:
        """Return the GitHubService built for EP-039, if available.

        Returns:
            The GitHubService instance, or None if
            `run()`/`initialize()` has not completed (or the GitHub
            Service subsystem was disabled this run, or invalid
            'github.*' configuration was supplied -- see
            `_build_command_router`'s EP-039 wiring).
        """
        return self._github_service

    @property
    def telegram_info_service(self) -> TelegramInfoService | None:
        """Return the TelegramInfoService built for EP-040, if available.

        Returns:
            The TelegramInfoService instance, or None if
            `run()`/`initialize()` has not completed (or the Telegram
            Info Service subsystem was disabled this run, or invalid
            configuration/a missing token was supplied -- see
            `_build_command_router`'s EP-040 wiring). Distinct from,
            and independent of, EP-012's own Telegram Gateway wiring.
        """
        return self._telegram_info_service

    @property
    def discord_service(self) -> DiscordService | None:
        """Return the DiscordService built for EP-041, if available.

        Returns:
            The DiscordService instance, or None if
            `run()`/`initialize()` has not completed (or the Discord
            Service subsystem was disabled this run, or invalid
            'discord.*' configuration was supplied -- see
            `_build_command_router`'s EP-041 wiring).
        """
        return self._discord_service

    @property
    def email_service(self) -> EmailService | None:
        """Return the EmailService built for EP-042, if available.

        Returns:
            The EmailService instance, or None if
            `run()`/`initialize()` has not completed (or the Email
            Service subsystem was disabled this run -- disabled by
            default -- or invalid 'email.*' configuration was supplied
            -- see `_build_command_router`'s EP-042 wiring).
        """
        return self._email_service

    @property
    def rest_api_server(self) -> RestApiServer | None:
        """Return the RestApiServer built for EP-043, if available.

        Returns:
            The RestApiServer instance, or None if
            `run()`/`initialize()` has not completed, the REST API
            subsystem was disabled this run (disabled by default --
            see `_build_rest_api_server`), or the configured
            host/port could not be bound.
        """
        return self._rest_api_server

    @property
    def voice_engine(self) -> VoskSpeechToTextEngine | None:
        """Return the VoskSpeechToTextEngine built for EP-046, if available.

        Returns:
            The VoskSpeechToTextEngine instance, or None if
            `run()`/`initialize()` has not completed (or the Voice
            subsystem was disabled this run -- disabled by default --
            or the 'vosk'/'sounddevice' dependency or configured
            'voice.model_dir' was invalid -- see
            `_build_command_router`'s EP-046 wiring).
        """
        return self._voice_engine

    @property
    def voice_tts_engine(self) -> TextToSpeechEngine | None:
        """Return the TextToSpeechEngine built for EP-047, if available.

        Returns:
            The Pyttsx3TextToSpeechEngine instance, or None if
            `run()`/`initialize()` has not completed, 'voice.enabled'
            (STT) or 'voice.tts.enabled' is false -- both default to
            false -- or the 'pyttsx3' dependency or configured
            'voice.tts.*' settings were invalid (see
            `_build_command_router`'s EP-047 wiring).
        """
        return self._voice_tts_engine

    @property
    def voice_wake_engine(self) -> WakeWordEngine | None:
        """Return the WakeWordEngine built for EP-048, if available.

        Returns:
            The OpenWakeWordEngine instance (behind the WakeWordEngine
            interface -- owner Decision D1), or None if
            `run()`/`initialize()` has not completed,
            'voice.wake.enabled' is false (defaults to false), or the
            'openwakeword' dependency or configured 'voice.wake.*'
            settings/model files were invalid (see
            `_build_command_router`'s EP-048 wiring).
        """
        return self._voice_wake_engine

    @property
    def voice_wake_capture(self) -> StreamingAudioCapture | None:
        """Return the StreamingAudioCapture built for EP-048, if available.

        Returns:
            The StreamingAudioCapture instance, or None under the
            same conditions as `voice_wake_engine`.
        """
        return self._voice_wake_capture

    @property
    def desktop_backend(self) -> ComputerUseBackend | None:
        """Return the ComputerUseBackend built for EP-050, if available.

        Returns:
            The `WindowsComputerUseBackend` instance, or None if
            'desktop.enabled' is false, or if construction failed
            (e.g. no display/windowing environment available) --
            `DesktopModule` is registered with `CommandRouter`
            regardless, and reports a clear failure message for every
            action in either case (EP050_DESIGN.md Section 10/16).
        """
        return self._desktop_backend

    @property
    def browser_backend(self) -> BrowserBackend | None:
        """Return the BrowserBackend built for EP-051, if available.

        Returns:
            The `PlaywrightBrowserBackend` instance, or None if
            'browser.enabled' is false, or if construction failed --
            `BrowserModule` is registered with `CommandRouter`
            regardless, and reports a clear failure message for every
            action in either case (EP051_DESIGN.md Section 10/14).
        """
        return self._browser_backend

    @property
    def file_backend(self) -> FileBackend | None:
        """Return the FileBackend built for EP-052, if available.

        Returns:
            The `LocalFileBackend` instance, or None if
            'file.enabled' is false -- `FileModule` is registered
            with `CommandRouter` regardless, and reports a clear
            failure message for every action in either case
            (EP052_DESIGN.md Section 10/16/20).
        """
        return self._file_backend

    @property
    def vision_backend(self) -> VisionBackend | None:
        """Return the VisionBackend built for EP-053, if available.

        Returns:
            The `LocalVisionBackend` instance, or None if
            'vision.enabled' is false -- `VisionModule` is registered
            with `CommandRouter` regardless, and reports a clear
            failure message for every action in either case
            (EP053_DESIGN.md Section 11/20).
        """
        return self._vision_backend
