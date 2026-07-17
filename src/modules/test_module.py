from __future__ import annotations

# Импортируй свои реальные классы
from src.core.command_router import CommandModule, CommandResult
from src.testing.runner import TestRunner

# Эти импорты нужны только для регистрации тестов.
# Они специально нигде не используются напрямую.
import tests.EP001.test_foundation
import tests.EP002.test_shell
import tests.EP003.test_execution_engine


class TestModule(CommandModule):

    NAME = "test"

    def __init__(self) -> None:
        self.runner = TestRunner()

    @property
    def name(self) -> str:
        return self.NAME

    def execute(self, command: str, args: list[str]) -> CommandResult:

        if not command:
            return CommandResult(
                success=False,
                message="Usage: test list | test all | test EP001"
            )

        action = command.upper()

        if action == "LIST":

            suites = self.runner.list()

            return CommandResult(
                success=True,
                message="\n".join(suites)
            )

        if action == "ALL":

            self.runner.run_all()

            return CommandResult(
                success=True,
                message="All tests completed."
            )

        self.runner.run(action)

        return CommandResult(
            success=True,
            message=f"{action} completed."
        )