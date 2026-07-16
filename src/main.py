"""Entry point for the Jarvis application."""

from __future__ import annotations

import sys
import time
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from loguru import logger  # noqa: E402

from src.bootstrap import Bootstrap  # noqa: E402
from src.core.config import ConfigError  # noqa: E402

IDLE_POLL_SECONDS = 1.0


def main() -> int:
    """Bootstrap and run the Jarvis application.

    Performs the full bootstrap sequence, then keeps the process alive
    while the orchestrator reports itself as running. The loop exits
    cleanly on Ctrl+C or when the orchestrator stops itself.

    Returns:
        Process exit code. 0 on success, non-zero on failure.
    """
    bootstrap = Bootstrap()

    try:
        orchestrator = bootstrap.run()
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

    try:
        while orchestrator.is_running:
            time.sleep(IDLE_POLL_SECONDS)
    except KeyboardInterrupt:
        logger.info("Shutdown requested via keyboard interrupt.")
        print("\nShutting down Jarvis...")
        orchestrator.stop()

    return 0


if __name__ == "__main__":
    sys.exit(main())
