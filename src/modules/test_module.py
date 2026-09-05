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
import tests.EP035.test_automation_engine
import tests.EP036.test_background_worker_pool
import tests.EP036.test_background_worker_service
import tests.EP036.test_background_worker_module
import tests.EP037.test_event_bus
import tests.EP038.test_git_service
import tests.EP038.test_git_module
import tests.EP039.test_github_service
import tests.EP039.test_github_module
import tests.EP040.test_telegram_info_service
import tests.EP040.test_telegram_info_module
import tests.EP041.test_discord_service
import tests.EP041.test_discord_module
import tests.EP042.test_email_service
import tests.EP042.test_email_module
import tests.EP043.test_rest_api
import tests.EP044.test_desktop_ui
import tests.EP045.test_web_dashboard
import tests.EP046.test_voice
import tests.EP047.test_voice_tts
import tests.EP048.test_wake_word
import tests.EP049.test_voice_assistant
import tests.EP050.test_desktop
import tests.EP051.test_browser
import tests.EP052.test_file
import tests.EP053.test_vision
import tests.EP054.test_reflection
import tests.EP055.test_prompt_optimizer
import tests.EP056.test_capability_registry
import tests.EP057.test_memory_optimization
import tests.EP058.test_autonomous_planning
import tests.EP059.test_runtime
import tests.EP060.test_runtime_lifecycle
import tests.EP061.test_scheduler_shutdown

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