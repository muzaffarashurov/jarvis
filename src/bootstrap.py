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
from src.core.orchestrator import Orchestrator
from src.core.shell import InteractiveShell
from src.modules.invoice_module import InvoiceModule
from src.services.invoice_service import InvoiceService
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

    @staticmethod
    def _build_command_router(orchestrator: Orchestrator, config: Config) -> CommandRouter:
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
        router.register(
            InvoiceModule(InvoiceService(config=config, execution_engine=execution_engine))
        )
        from src.modules.test_module import TestModule
        router.register(TestModule())
        return router

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
