"""Entry point for the Jarvis application."""

from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from loguru import logger  # noqa: E402

from src.bootstrap import Bootstrap  # noqa: E402
from src.core.config import ConfigError  # noqa: E402


def main() -> int:
    """Bootstrap Jarvis and hand control to the interactive shell.

    Runs the full startup sequence (configuration, logger, orchestrator,
    command router), then starts the InteractiveShell, which owns the
    application's main loop until the user exits, presses Ctrl+C, or
    sends EOF.

    Returns:
        Process exit code. 0 on success, non-zero on startup failure.
    """
    bootstrap = Bootstrap()

    try:
        bootstrap.run()
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"Filesystem error during startup: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 - top-level safety net
        logger.exception(f"Unexpected error during startup: {exc}")
        print(f"Unexpected error during startup: {exc}", file=sys.stderr)
        return 1

    shell = bootstrap.shell
    if shell is None:
        logger.error("Bootstrap completed without producing an interactive shell.")
        print("Internal error: interactive shell was not initialized.", file=sys.stderr)
        return 1

    shell.run()
    _save_memory_on_shutdown(bootstrap)
    return 0


def _save_memory_on_shutdown(bootstrap: Bootstrap) -> None:
    """Persist Memory to 'memory.storage_file' before the process exits.

    A no-op when the MemoryService was never built or when
    'memory.persistent' is False (RAM-only mode).

    Args:
        bootstrap: The completed Bootstrap instance, used to reach the
            MemoryService built during `bootstrap.run()`.
    """
    memory_service = bootstrap.memory_service
    if memory_service is None:
        return

    result = memory_service.save()
    if result.success:
        logger.info(f"Memory saved on shutdown: {result.message}")
    else:
        logger.debug(f"Memory not saved on shutdown: {result.message}")


if __name__ == "__main__":
    sys.exit(main())
