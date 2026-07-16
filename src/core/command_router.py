"""Command routing infrastructure for the Jarvis interactive shell."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from loguru import logger


@dataclass(frozen=True)
class CommandResult:
    """Represents the outcome of executing a single command.

    Attributes:
        success: Whether the command executed successfully.
        message: Human-readable output to display to the user. May be
            empty when a command has no textual output (e.g. "clear").
        should_exit: Whether the shell should terminate after this result.
    """

    success: bool
    message: str
    should_exit: bool = False


@runtime_checkable
class CommandModule(Protocol):
    """Interface every command module (Skill) must implement.

    Each module owns a single namespace (e.g. "system", "invoice") and
    knows how to execute the actions available under that namespace.
    Implementing this protocol is all that is required to plug a new
    module into the CommandRouter, with no changes to routing logic.
    """

    @property
    def name(self) -> str:
        """Return the module's command namespace (e.g. "system")."""
        ...

    def execute(self, action: str, arguments: list[str]) -> CommandResult:
        """Execute an action belonging to this module.

        Args:
            action: The action name (e.g. "status"). Empty string if the
                user supplied only the module name.
            arguments: Additional positional arguments after the action.

        Returns:
            A CommandResult describing the outcome.
        """
        ...


class CommandRouter:
    """Parses raw shell input and dispatches it to registered modules.

    Responsibilities:
        - Maintain a registry of CommandModule instances keyed by namespace.
        - Parse raw input into <module> <action> [arguments...].
        - Validate that the target module exists before dispatching.
        - Delegate execution to the resolved module and return its result.

    New modules register themselves via `register()`. This class never
    needs to change to support new command namespaces, keeping it
    open for extension and closed for modification.
    """

    def __init__(self) -> None:
        """Initialize an empty CommandRouter with no registered modules."""
        self._modules: dict[str, CommandModule] = {}

    def register(self, module: CommandModule) -> None:
        """Register a command module under its namespace.

        The namespace is stored in lowercase so lookups in `dispatch()`
        remain case-insensitive regardless of how a module reports its
        own `name`.

        Args:
            module: The module to register.

        Raises:
            ValueError: If a module is already registered under the same
                namespace.
        """
        key = module.name.lower()
        if key in self._modules:
            raise ValueError(f"A module named '{module.name}' is already registered.")

        self._modules[key] = module
        logger.debug(f"Registered command module: '{module.name}'")

    def dispatch(self, raw_input: str) -> CommandResult:
        """Parse and execute a raw command line entered by the user.

        Module and action names are matched case-insensitively (e.g.
        "SYSTEM HELP", "System Help" and "system help" are equivalent),
        while any additional arguments preserve their original casing.

        Args:
            raw_input: The raw text entered by the user.

        Returns:
            A CommandResult describing the outcome of execution. Returns
            an empty, unsuccessful result for blank input.
        """
        tokens = raw_input.strip().split()
        if not tokens:
            return CommandResult(success=False, message="")

        module_name, *rest = tokens
        module = self._modules.get(module_name.lower())

        if module is None:
            logger.info(f"Unknown module: {module_name}")
            message = (
                f"Unknown module: {module_name}\n"
                'Type "system help" for available commands.'
            )
            return CommandResult(success=False, message=message)

        action = rest[0].lower() if rest else ""
        arguments = rest[1:]

        try:
            result = module.execute(action, arguments)
        except Exception as exc:  # noqa: BLE001 - a module must never crash the shell
            logger.error(f"Error executing '{raw_input.strip()}': {exc}")
            return CommandResult(
                success=False,
                message=f"Internal error while executing '{raw_input.strip()}'.",
            )

        if result.success:
            logger.info(f"Command executed: {raw_input.strip()}")

        return result

    @property
    def module_names(self) -> list[str]:
        """Return the namespaces of all currently registered modules.

        Returns:
            A list of registered module names.
        """
        return list(self._modules.keys())
