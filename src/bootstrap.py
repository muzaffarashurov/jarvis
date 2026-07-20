"""Application bootstrap sequence for Jarvis."""

from __future__ import annotations

from pathlib import Path

import pyfiglet
from colorama import Style
from colorama import init as colorama_init
from loguru import logger

from src.core.command_router import CommandRouter
from src.core.config import Config, ConfigError
from src.core.events import EventBus
from src.core.execution.engine import ExecutionEngine
from src.core.execution.executors.file_executor import FileExecutor
from src.core.execution.executors.process_executor import ProcessExecutor
from src.core.execution.executors.python_executor import PythonExecutor
from src.core.execution.executors.url_executor import UrlExecutor
from src.core.execution.process_registry import ProcessRegistry
from src.core.logger import Logger
from src.core.memory.memory_store import MemoryStore
from src.core.orchestrator import Orchestrator
from src.core.plugins.plugin_context import PluginContext
from src.core.plugins.plugin_discovery import PluginDiscovery
from src.core.plugins.plugin_loader import PluginLoader
from src.core.plugins.plugin_registry import PluginRegistry
from src.core.processes.process import Process, RestartPolicy
from src.core.processes.process_registry import ProcessRegistry as ProcessCatalogRegistry
from src.core.scheduler.job import Job, Schedule, ScheduleType
from src.core.scheduler.job_registry import JobRegistry
from src.core.scheduler.scheduler import Scheduler
from src.core.shell import InteractiveShell
from src.core.telegram.telegram_client import TelegramClient
from src.core.telegram.telegram_router import TelegramRouter
from src.modules.fast_response_module import FastResponseModule
from src.modules.invoice_module import InvoiceModule
from src.modules.memory_module import MemoryModule
from src.modules.plugin_module import PluginModule
from src.modules.process_module import ProcessModule
from src.modules.scheduler_module import SchedulerModule
from src.modules.telegram_module import TelegramModule
from src.services.fast_response_service import FastResponseService
from src.services.invoice_service import InvoiceService
from src.services.memory_service import MemoryService
from src.services.plugin_service import PluginService
from src.services.process_service import ProcessService
from src.services.scheduler_service import SchedulerService
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

    Responsibilities:
        - Create required runtime folders.
        - Print the colored ASCII startup banner.
        - Load application configuration.
        - Initialize the logger.
        - Initialize and start the orchestrator.
    """

    def __init__(self, project_root: Path | None = None) -> None:
        """Initialize the Bootstrap sequence.

        Args:
            project_root: Root path of the project. Defaults to the
                directory containing the 'src' package.
        """
        self._project_root = project_root or PROJECT_ROOT
        self._config: Config | None = None
        self._event_bus = EventBus()
        self._orchestrator: Orchestrator | None = None
        self._command_router: CommandRouter | None = None
        self._shell: InteractiveShell | None = None
        self._memory_service: MemoryService | None = None
        colorama_init(autoreset=True)

    def run(self) -> Orchestrator:
        """Execute the full bootstrap sequence.

        Returns:
            The started Orchestrator instance.

        Raises:
            ConfigError: If configuration cannot be loaded.
            OSError: If required directories cannot be created.
        """
        self._create_required_directories()
        self._print_banner()

        print("Loading configuration...")
        self._config = self._load_configuration()

        self._initialize_logger()
        print("Logger initialized...")

        print("Loading skills...")
        self._orchestrator = Orchestrator(config=self._config, event_bus=self._event_bus)
        self._orchestrator.start()

        self._command_router = self._build_command_router(self._orchestrator, self._config)
        self._shell = InteractiveShell(router=self._command_router)

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
        memory_store = MemoryStore()
        memory_service = MemoryService(config=config, store=memory_store)
        self._memory_service = memory_service
        router.register(MemoryModule(memory_service))

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
