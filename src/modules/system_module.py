# src/modules/system_module.py
"""System command module providing platform state operations and EP-004.1 Testing Framework access."""

import logging
from typing import Optional
from src.testing.runner import TestRunner

logger = logging.getLogger("Jarvis.SystemModule")


class SystemModule:
    """Core module providing standard utility actions and framework testing capabilities."""

    def __init__(self, router=None) -> None:
        self.router = router
        if self.router is not None:
            self._register_commands()

    def _register_commands(self) -> None:
        """Registers the specified module handling hooks directly into core framework routers."""
        self.router.register("test", self.handle_test_command)

    def handle_test_command(self, subcommand: Optional[str] = None, *args) -> str:
        """Routes command inputs targeted at the Test Framework suite execution system.
        
        Supported syntaxes:
            test list
            test EP001
            test EP002
            test EP003
            test all
        """
        if not subcommand:
            return "Usage: test [list|all|EP001|EP002|EP003]"

        runner = TestRunner()
        # Ensure discovery is triggered so decorators populate the central registry
        discovered_suites = runner.discover_tests()

        normalized_command = subcommand.strip().lower()

        if normalized_command == "list":
            lines = ["Available Test Suites", "EP001", "EP002", "EP003", "--------------------------------------"]
            return "\n".join(lines)

        elif normalized_command == "all":
            return runner.run_all()

        elif normalized_command in ["ep001", "ep002", "ep003"]:
            target_suite = subcommand.upper()
            if target_suite not in discovered_suites:
                return f"Error: Suite {target_suite} was not automatically discovered in test registries."
            
            output, _ = runner.run_suite(target_suite)
            return output

        else:
            return f"Unknown test target subcommand parameter: '{subcommand}'. Usage: test [list|all|EP001|EP002|EP003]"