from __future__ import annotations

# Импортируй свои реальные классы
from src.core.command_router import CommandModule, CommandResult
from src.testing.runner import TestRunner

# Эти импорты нужны только для регистрации тестов.
# Они специально нигде не используются напрямую.
import tests.EP001.test_foundation
import tests.EP002.test_shell
import tests.EP003.test_execution_engine
import tests.EP018.test_unified_prompt_budget
import tests.EP019.test_project_index_engine
import tests.EP020.test_retrieval_engine
import tests.EP021.test_embedding_engine
import tests.EP022.test_rag_engine
import tests.EP023.test_memory_manager
import tests.EP024.test_knowledge_base
import tests.EP025.test_long_term_memory
import tests.EP026.test_semantic_search
import tests.EP027.test_context_compression
import tests.EP028.test_agent_framework
import tests.EP029.test_planning_engine
import tests.EP030.test_plan_execution_engine
import tests.EP031.test_tool_engine
import tests.EP032.test_collaboration_engine
import tests.EP033.test_workflow_engine
import tests.EP034.test_workflow_scheduler

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