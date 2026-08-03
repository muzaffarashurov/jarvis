"""Agent module: CLI command surface for EP-028 Agent Framework.

Exposes the "agent" command namespace (help, status, subsystems,
register, unregister, reset, initialize, shutdown) as thin
CommandModule handlers, following the same pattern as
ContextCompressionModule/SemanticModule. All orchestration logic lives
in AgentService; this module only formats CommandResult objects for
the shell. "agent execute"/"agent cancel" are intentionally not
exposed here -- EP-028's task brief lists no such CLI command, and
`AgentService.execute()`/`cancel()` remain available for future
programmatic callers (e.g. a future Planner).
"""

from __future__ import annotations

from typing import Callable

from src.core.command_router import CommandResult
from src.services.agent_service import AgentService, AgentStatus, SubsystemOutcome

HELP_TEXT: str = (
    "Available commands\n\n"
    "agent help\n"
    "agent status\n"
    "agent subsystems\n"
    "agent register <name>\n"
    "agent unregister <name>\n"
    "agent reset\n"
    "agent initialize\n"
    "agent shutdown"
)

ActionHandler = Callable[[list[str]], CommandResult]


class AgentModule:
    """Built-in "agent" command namespace for the Agent Framework."""

    def __init__(self, agent_service: AgentService) -> None:
        """Initialize the AgentModule.

        Args:
            agent_service: The service used to inspect and control the
                Agent Framework subsystem, its registered agents, and
                the current agent's subsystem registry.
        """
        self._service = agent_service
        self._actions: dict[str, ActionHandler] = {
            "help": self._help,
            "status": self._status,
            "subsystems": self._subsystems,
            "register": self._register,
            "unregister": self._unregister,
            "reset": self._reset,
            "initialize": self._initialize,
            "shutdown": self._shutdown,
        }

    @property
    def name(self) -> str:
        """Return this module's command namespace: "agent"."""
        return "agent"

    def execute(self, action: str, arguments: list[str]) -> CommandResult:
        """Execute an "agent" action.

        Args:
            action: The requested action (e.g. "status").
            arguments: Additional arguments (e.g. a subsystem name).

        Returns:
            A CommandResult describing the outcome.
        """
        handler = self._actions.get(action)
        if handler is None:
            command = f"{self.name} {action}".strip()
            message = f'Unknown command: {command}\nType "agent help" for available commands.'
            return CommandResult(success=False, message=message)

        return handler(arguments)

    def _help(self, arguments: list[str]) -> CommandResult:
        """Return the list of available agent commands."""
        return CommandResult(success=True, message=HELP_TEXT)

    def _status(self, arguments: list[str]) -> CommandResult:
        """Display the Agent Framework subsystem's overall status."""
        status: AgentStatus = self._service.status()
        lines = [
            "Agent Framework Status",
            f"Enabled : {self._mark(status.enabled)}",
            f"Current agent : {status.current_agent or 'none'}",
            f"State : {status.state.value if status.state is not None else 'none'}",
            f"Registered agents : {status.registered_agent_count}",
            f"Startup mode : {status.startup_mode or 'n/a'}",
            f"Registered subsystems : {status.subsystem_count}",
        ]
        return CommandResult(success=True, message="\n".join(lines))

    def _subsystems(self, arguments: list[str]) -> CommandResult:
        """List every subsystem registered with the current agent."""
        subsystems = self._service.list_subsystems()
        if not subsystems:
            return CommandResult(success=True, message="No subsystems registered.")

        header = f"{'Subsystem':<20}{'Available':<11}"
        lines = ["Agent Subsystems", "", header]
        for subsystem in subsystems:
            lines.append(f"{subsystem.name:<20}{self._mark(subsystem.available):<11}")
        return CommandResult(success=True, message="\n".join(lines))

    def _register(self, arguments: list[str]) -> CommandResult:
        """Register a subsystem, by name, with the current agent.

        Args:
            arguments: `[subsystem_name]`.

        Returns:
            A CommandResult reflecting whether the subsystem was registered.
        """
        if len(arguments) != 1:
            return CommandResult(success=False, message="Usage: agent register <name>")

        outcome: SubsystemOutcome = self._service.register_subsystem(arguments[0])
        return CommandResult(success=outcome.success, message=outcome.message)

    def _unregister(self, arguments: list[str]) -> CommandResult:
        """Remove a subsystem from the current agent's registry.

        Args:
            arguments: `[subsystem_name]`.

        Returns:
            A CommandResult reflecting whether the subsystem was removed.
        """
        if len(arguments) != 1:
            return CommandResult(success=False, message="Usage: agent unregister <name>")

        outcome: SubsystemOutcome = self._service.unregister_subsystem(arguments[0])
        return CommandResult(success=outcome.success, message=outcome.message)

    def _reset(self, arguments: list[str]) -> CommandResult:
        """Reset the current agent's transient request-tracking state."""
        return self._service.reset()

    def _initialize(self, arguments: list[str]) -> CommandResult:
        """Initialize the current agent."""
        return self._service.initialize()

    def _shutdown(self, arguments: list[str]) -> CommandResult:
        """Shut down the current agent."""
        return self._service.shutdown()

    @staticmethod
    def _mark(value: bool) -> str:
        """Format a boolean diagnostic check as "YES" or "NO"."""
        return "YES" if value else "NO"
