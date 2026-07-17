"""Real engineering tests for EP003 – Execution Engine.

Validates ExecutionEngine and ProcessRegistry construction, empty-state
behaviour, and correct handling of invalid process ids and invalid
executable targets using real objects (no mocked internals).
"""

from __future__ import annotations

import shutil
import traceback

from src.core.execution.engine import ExecutionEngine
from src.core.execution.executors.process_executor import ProcessExecutor
from src.core.execution.models import ExecutionResult
from src.core.execution.process_registry import ProcessRegistry
from src.testing.base_test import BaseTest
from src.testing.registry import TestRegistry


@TestRegistry.register
class ExecutionEngineTest(BaseTest):
    """Real tests covering the Execution Engine layer (EP003)."""

    NAME = "EP003"

    def run(self):
        """Execute all ExecutionEngine checks and return the aggregated result."""
        self._test_execution_engine_creation()
        self._test_process_registry_creation()
        self._test_registry_initially_empty()
        self._test_invalid_process_termination()
        self._test_invalid_executable_handled()
        self._test_engine_does_not_crash_on_invalid_input()
        self._test_execution_result_objects_are_valid()
        self._test_full_process_lifecycle()
        return self.result

    def _test_execution_engine_creation(self) -> None:
        """ExecutionEngine object can be created."""
        registry = ProcessRegistry()
        engine = ExecutionEngine(executors=[], registry=registry)
        self.assert_not_none(engine, "ExecutionEngine instance should not be None")

    def _test_process_registry_creation(self) -> None:
        """ProcessRegistry object can be created."""
        registry = ProcessRegistry()
        self.assert_not_none(registry, "ProcessRegistry instance should not be None")

    def _test_registry_initially_empty(self) -> None:
        """A freshly created ProcessRegistry has no running processes."""
        registry = ProcessRegistry()
        self.assert_equal(
            len(registry.list_running()), 0, "New ProcessRegistry should track zero processes"
        )
        self.assert_true(
            registry.get(1) is None, "Unknown process id should resolve to None"
        )

    def _test_invalid_process_termination(self) -> None:
        """Terminating an untracked process id is handled correctly."""
        registry = ProcessRegistry()
        engine = ExecutionEngine(executors=[], registry=registry)

        result = engine.stop_process(99999)

        self.assert_true(
            isinstance(result, ExecutionResult), "stop_process should return an ExecutionResult"
        )
        self.assert_false(result.success, "Stopping an unknown process id should not succeed")
        self.assert_equal(
            result.message, "Invalid process id.", "Message should report an invalid process id"
        )

    def _test_invalid_executable_handled(self) -> None:
        """Running a nonexistent executable is handled without crashing."""
        registry = ProcessRegistry()
        engine = ExecutionEngine(executors=[ProcessExecutor(registry)], registry=registry)

        result = engine.run("definitely_not_a_real_jarvis_executable_xyz.exe")

        self.assert_true(
            isinstance(result, ExecutionResult), "run() should return an ExecutionResult"
        )
        self.assert_false(result.success, "Launching a nonexistent executable should not succeed")
        self.assert_equal(
            len(registry.list_running()),
            0,
            "A failed launch should not register a running process",
        )

    def _test_engine_does_not_crash_on_invalid_input(self) -> None:
        """ExecutionEngine.run handles blank and unsupported input gracefully."""
        registry = ProcessRegistry()
        engine = ExecutionEngine(executors=[], registry=registry)

        try:
            blank_result = engine.run("")
            unsupported_result = engine.run("totally-unsupported-target-string")
        except Exception:  # noqa: BLE001 - engine must never raise, see class docstring
            self.assert_true(
                False, f"ExecutionEngine.run raised unexpectedly:\n{traceback.format_exc()}"
            )
            return

        self.assert_false(blank_result.success, "Blank target should not succeed")
        self.assert_false(unsupported_result.success, "Unsupported target should not succeed")

    def _test_execution_result_objects_are_valid(self) -> None:
        """Returned ExecutionResult objects have valid, well-typed fields."""
        registry = ProcessRegistry()
        engine = ExecutionEngine(executors=[], registry=registry)

        result = engine.run("some-target")

        self.assert_true(isinstance(result.success, bool), "success field should be a bool")
        self.assert_true(isinstance(result.message, str), "message field should be a str")
        self.assert_true(
            len(result.message) > 0, "message field should not be empty on failure"
        )

    def _test_full_process_lifecycle(self) -> None:
        """A real process is launched, tracked, then terminated end-to-end.

        This is the integration path the unit-level tests above don't
        cover: engine.run() must pick the ProcessExecutor for a known
        system command, actually launch it, register it in the
        ProcessRegistry, and engine.stop_process() must terminate it and
        remove it from the registry again. "python" is used because it
        is the one interpreter guaranteed to exist in this environment
        (it is currently running this test); if it is not on PATH the
        test is skipped rather than reported as a false failure.
        """
        if shutil.which("python") is None:
            self.skip()
            return

        registry = ProcessRegistry()
        engine = ExecutionEngine(executors=[ProcessExecutor(registry)], registry=registry)

        launch_result = engine.run("python")
        self.assert_true(launch_result.success, "Launching 'python' should succeed")
        self.assert_not_none(
            launch_result.process_id, "A successful launch should return a process_id"
        )

        process_id = launch_result.process_id
        if process_id is None:
            return

        try:
            self.assert_true(
                registry.get(process_id) is not None,
                "Launched process should be tracked in the registry",
            )
            self.assert_equal(
                len(registry.list_running()),
                1,
                "Registry should track exactly the one launched process",
            )

            stop_result = engine.stop_process(process_id)
            self.assert_true(stop_result.success, "Stopping the tracked process should succeed")
            self.assert_true(
                registry.get(process_id) is None,
                "Terminated process should be removed from the registry",
            )
            self.assert_equal(
                len(registry.list_running()),
                0,
                "Registry should be empty after the process is stopped",
            )
        finally:
            # Safety net: if an assertion above failed before stop_process
            # ran, make sure the spawned interpreter doesn't leak.
            record = registry.get(process_id)
            if record is not None:
                record.handle.terminate()
                registry.remove(process_id)
