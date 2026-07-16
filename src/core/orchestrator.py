"""Core orchestrator responsible for coordinating Jarvis skills and lifecycle."""

from __future__ import annotations

from typing import Any

from loguru import logger

from src.core.config import Config
from src.core.events import EventBus


class Orchestrator:
    """Coordinates skill loading and manages the application lifecycle.

    Responsibilities:
        - Hold references to configuration and the event bus.
        - Discover and load available skills.
        - Track and expose the running state of the application.

    Console presentation (banners, status lines) is intentionally kept
    out of this class; Orchestrator only logs and publishes events, so
    it stays reusable outside of an interactive CLI context.
    """

    def __init__(self, config: Config, event_bus: EventBus) -> None:
        """Initialize the Orchestrator.

        Args:
            config: The loaded application configuration.
            event_bus: The application-wide event bus.
        """
        self._config = config
        self._event_bus = event_bus
        self._skills: list[Any] = []
        self._is_running: bool = False

    def load_skills(self) -> int:
        """Discover and load all available skills.

        Publishes a 'skills.loaded' event with the resulting count once
        loading completes, regardless of whether any skills were found.

        Returns:
            The number of skills successfully loaded.
        """
        logger.info("Loading Skills...")

        try:
            self._skills = self._discover_skills()
        except Exception as exc:  # noqa: BLE001 - skill discovery must not crash boot
            logger.error(f"Failed to load skills: {exc}")
            self._skills = []

        skill_count = len(self._skills)
        logger.info(f"{skill_count} Skills loaded")
        self._event_bus.publish("skills.loaded", count=skill_count)
        return skill_count

    def _discover_skills(self) -> list[Any]:
        """Discover and instantiate skill implementations.

        Returns:
            A list of instantiated skill objects. Always empty at
            Foundation v0.1, since no skills have been implemented yet.
        """
        enabled = self._config.get("orchestrator.skills_enabled", [])
        if enabled:
            logger.debug(f"Skills configured but not yet implemented: {enabled}")
        return []

    def start(self) -> None:
        """Start the orchestrator, loading skills and marking it as running."""
        if self._is_running:
            logger.warning("Orchestrator.start() called while already running.")
            return

        self.load_skills()
        self._is_running = True
        logger.info("Orchestrator started. Jarvis is running.")
        self._event_bus.publish("orchestrator.started")

    def stop(self) -> None:
        """Stop the orchestrator and mark it as no longer running."""
        if not self._is_running:
            logger.debug("Orchestrator.stop() called while not running.")
            return

        self._is_running = False
        logger.info("Orchestrator stopped.")
        self._event_bus.publish("orchestrator.stopped")

    @property
    def is_running(self) -> bool:
        """Return whether the orchestrator is currently running.

        Returns:
            True if the orchestrator has been started and not stopped.
        """
        return self._is_running

    @property
    def skills(self) -> list[Any]:
        """Return the list of currently loaded skills.

        Returns:
            A list of loaded skill instances (empty at Foundation v0.1).
        """
        return self._skills
