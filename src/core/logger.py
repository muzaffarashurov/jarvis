"""Logging infrastructure for Jarvis, built on Loguru."""

from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger as _loguru_logger

# Remove Loguru's default stderr handler immediately on import, so no
# unconfigured output can leak to the console before `Logger` explicitly
# sets up its own sinks (e.g. from log calls made while loading config).
_loguru_logger.remove()

CONSOLE_FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> "
    "- <level>{message}</level>"
)

FILE_FORMAT = (
    "{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | "
    "{name}:{function}:{line} - {message}"
)


class Logger:
    """Configures the application-wide Loguru logger for Jarvis.

    Responsibilities:
        - Ensure the logs directory exists.
        - Configure a daily rotating log file sink (always on).
        - Optionally configure a console sink at the requested level.

    A raw file sink is used for diagnostics regardless of console
    settings, so the pretty startup banner printed by Bootstrap is
    never interleaved with timestamped log lines unless explicitly
    enabled via configuration.

    Configuration is applied once per process; subsequent instantiations
    are no-ops to avoid duplicated sinks.
    """

    _configured: bool = False

    def __init__(
        self,
        logs_dir: Path,
        level: str = "INFO",
        retention_days: int = 30,
        console_enabled: bool = False,
    ) -> None:
        """Initialize and configure the logger.

        Args:
            logs_dir: Directory where log files will be stored.
            level: Minimum logging level for both console and file sinks.
            retention_days: Number of days to retain rotated log files.
            console_enabled: Whether log lines are also echoed to stdout.

        Raises:
            OSError: If the logs directory cannot be created.
        """
        self._logs_dir = logs_dir
        self._level = level.upper()
        self._retention_days = retention_days
        self._console_enabled = console_enabled
        self._configure()

    def _configure(self) -> None:
        """Configure Loguru file (and optionally console) sinks.

        Raises:
            OSError: If the logs directory cannot be created.
        """
        if Logger._configured:
            _loguru_logger.debug("Logger already configured; skipping reconfiguration.")
            return

        try:
            self._logs_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise OSError(
                f"Failed to create logs directory at '{self._logs_dir}': {exc}"
            ) from exc

        _loguru_logger.remove()

        if self._console_enabled:
            _loguru_logger.add(
                sys.stdout,
                level=self._level,
                colorize=True,
                format=CONSOLE_FORMAT,
            )

        log_file_pattern = self._logs_dir / "jarvis_{time:YYYY-MM-DD}.log"
        _loguru_logger.add(
            str(log_file_pattern),
            level=self._level,
            rotation="00:00",
            retention=f"{self._retention_days} days",
            encoding="utf-8",
            format=FILE_FORMAT,
        )

        Logger._configured = True
        _loguru_logger.info(
            f"Logger initialized (level={self._level}, dir='{self._logs_dir}', "
            f"console_enabled={self._console_enabled})"
        )

    @staticmethod
    def get_logger():
        """Return the process-wide configured Loguru logger.

        Returns:
            The configured Loguru logger instance.
        """
        return _loguru_logger
