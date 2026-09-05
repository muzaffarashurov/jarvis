"""Real engineering tests for EP-062 - BackgroundWorkerService status fix.

Per `EP062_DESIGN.md`, EP-062 makes a single, narrow correction:
`BackgroundWorkerService.status().running` now reflects the owned
pool's own already-existing, already-public `is_shutdown` property
(`running = not self._pool.is_shutdown`) instead of being hard-set to
`True` whenever a pool object merely exists. No new infrastructure is
introduced -- `BackgroundWorkerPool.is_shutdown` (EP-036) already
existed and already had the correct semantics; this EP only wires it
into `status()`.

This suite is deliberately self-contained (does not import from
`tests/EP036/`, `tests/EP059/`, `tests/EP060/`, or `tests/EP061/`),
matching this repository's own per-EP test-suite self-containment
precedent -- local builder functions below are near-identical to (but
independent copies of) the ones those suites already use for the same
real objects.

Covers, per `EP062_DESIGN.md` Section 12:
    1. `BackgroundWorkerService.status()` in isolation -- disabled,
       never shut down, shut down with `wait=True`/`wait=False`,
       called twice after shutdown, and `worker_count`/`task_count`
       unaffected by shutdown state.
    2. `RuntimeService`'s corrected behavior -- `status()` and
       `shutdown()` (including a second `shutdown()` call) now report
       the Background Worker subsystem's true state; `runtime status`
       CLI output reflects the correction.
    3. `BackgroundWorkerModule` CLI (`worker status`/`worker stop`)
       consistency -- "Running : NO" after "worker stop", and
       `worker submit` still raises after a stop (regression guard,
       untouched by this EP).
    4. Public-surface guards -- `BackgroundWorkerService`'s method set
       and `BackgroundWorkerStatus`'s field set are both unchanged by
       this EP.
"""

from __future__ import annotations

import inspect
import os
import tempfile
from dataclasses import fields
from pathlib import Path

from src.core.config import Config
from src.core.plan_execution.plan_execution_result import PlanExecutionResult
from src.core.workflow_engine.workflow_definition import (
    WorkflowDefinition,
    WorkflowRequestStep,
)
from src.core.workflow_engine.workflow_engine import WorkflowEngine
from src.core.workflow_engine.workflow_engine_manager import WorkflowEngineManager
from src.modules.background_worker_module import BackgroundWorkerModule
from src.modules.runtime_module import RuntimeModule
from src.services.background_worker_service import (
    BackgroundWorkerService,
    BackgroundWorkerStatus,
)
from src.services.runtime_service import RuntimeService
from src.testing.base_test import BaseTest
from src.testing.registry import TestRegistry

# ================= Shared local builders =================


class _ChdirGuard:
    """Context manager: chdir into `directory`, always restoring the original cwd."""

    def __init__(self, directory: Path) -> None:
        self._directory = directory
        self._original = Path.cwd()

    def __enter__(self) -> Path:
        os.chdir(self._directory)
        return self._directory

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        os.chdir(self._original)


class _StubPlanExecutionEngine:
    """Minimal, real `PlanExecutionEngine`-shaped stub -- always succeeds.

    Kept local and self-contained, matching `tests/EP059/test_runtime.py`,
    `tests/EP060/test_runtime_lifecycle.py`, and `tests/EP061/
    test_scheduler_shutdown.py`'s own precedent.
    """

    def execute_request(self, request: str) -> PlanExecutionResult:
        return PlanExecutionResult(
            plan=None,
            step_results=[],
            completed_count=1,
            failed_count=0,
            skipped_count=0,
            success=True,
        )


def _build_real_workflow_engine(tmp_path: Path, workflow_id: str = "noop") -> WorkflowEngine:
    """Build a real, minimal WorkflowEngine with one single-step definition."""
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "config.yaml").write_text(
        'workflow_engine:\n  enabled: true\n  default_provider: "workflow_engine"\n'
        "  stop_on_failure: true\n",
        encoding="utf-8",
    )
    config = Config(config_dir / "config.yaml").load()
    manager = WorkflowEngineManager(config=config)
    manager.register_definition(
        WorkflowDefinition(
            id=workflow_id,
            name=workflow_id,
            description="",
            enabled=True,
            steps=(WorkflowRequestStep(name="only", request=workflow_id),),
        )
    )
    return WorkflowEngine(manager=manager, plan_execution_engine=_StubPlanExecutionEngine())


def _build_real_background_worker_service(
    tmp_path: Path, worker_count: int = 1, enabled: bool = True
) -> BackgroundWorkerService:
    """Build a real, minimal BackgroundWorkerService."""
    engine = _build_real_workflow_engine(tmp_path)
    (tmp_path / "config" / "config.yaml").write_text(
        'workflow_engine:\n  enabled: true\n  default_provider: "workflow_engine"\n'
        "  stop_on_failure: true\n\n"
        f"background_workers:\n  enabled: {str(enabled).lower()}\n  worker_count: {worker_count}\n",
        encoding="utf-8",
    )
    config = Config(tmp_path / "config" / "config.yaml").load()
    return BackgroundWorkerService(config=config, workflow_engine=engine)


@TestRegistry.register
class BackgroundWorkerStatusTest(BaseTest):
    NAME = "EP062"

    def run(self):
        # ---------- BackgroundWorkerService.status() in isolation ----------
        self._test_status_disabled_unaffected()
        self._test_status_running_true_before_shutdown()
        self._test_status_running_false_after_shutdown_wait_true()
        self._test_status_running_false_after_shutdown_wait_false()
        self._test_status_running_false_called_twice_after_shutdown()
        self._test_worker_and_task_count_unaffected_by_shutdown()

        # ---------- RuntimeService corrected behavior ----------
        self._test_runtime_status_reflects_shutdown_background_workers()
        self._test_runtime_shutdown_second_call_reports_false()
        self._test_runtime_status_cli_omits_active_after_shutdown()

        # ---------- BackgroundWorkerModule CLI ----------
        self._test_worker_status_cli_reports_running_no_after_stop()
        self._test_worker_submit_still_raises_after_stop()

        # ---------- Public-surface guards ----------
        self._test_background_worker_service_public_surface_unchanged()
        self._test_background_worker_status_fields_unchanged()

        return self.result

    # ================= BackgroundWorkerService.status() in isolation =================

    def _test_status_disabled_unaffected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = _build_real_background_worker_service(Path(tmp), enabled=False)
            status = service.status()
            self.assert_false(status.enabled)
            self.assert_false(status.running)
            self.assert_equal(status.worker_count, 0)
            self.assert_equal(status.task_count, 0)
            # shutdown() on a disabled service is a trivial success; running
            # stays False -- the disabled branch is untouched by this EP.
            self.assert_true(service.shutdown())
            self.assert_false(service.status().running)

    def _test_status_running_true_before_shutdown(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = _build_real_background_worker_service(Path(tmp), worker_count=2)
            try:
                status = service.status()
                self.assert_true(status.enabled)
                self.assert_true(status.running)
                self.assert_equal(status.worker_count, 2)
            finally:
                service.shutdown(wait=True, timeout=2)

    def _test_status_running_false_after_shutdown_wait_true(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = _build_real_background_worker_service(Path(tmp), worker_count=1)
            self.assert_true(service.status().running)
            result = service.shutdown(wait=True, timeout=2)
            self.assert_true(result)
            self.assert_false(service.status().running)

    def _test_status_running_false_after_shutdown_wait_false(self) -> None:
        """`is_shutdown` (and now `status().running`) flips immediately,
        without waiting for worker threads to actually join -- matching
        `EP062_DESIGN.md` Section 8's disclosed edge case."""
        with tempfile.TemporaryDirectory() as tmp:
            service = _build_real_background_worker_service(Path(tmp), worker_count=1)
            self.assert_true(service.status().running)
            service.shutdown(wait=False)
            self.assert_false(service.status().running)

    def _test_status_running_false_called_twice_after_shutdown(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = _build_real_background_worker_service(Path(tmp), worker_count=1)
            service.shutdown(wait=True, timeout=2)
            self.assert_false(service.status().running)
            # Idempotent observation -- no new state introduced that could
            # make this flicker between calls.
            self.assert_false(service.status().running)
            # A second shutdown() call itself remains safe/idempotent too
            # (BackgroundWorkerPool.shutdown()'s own pre-existing guarantee,
            # untouched by this EP).
            self.assert_true(service.shutdown(wait=True, timeout=2))
            self.assert_false(service.status().running)

    def _test_worker_and_task_count_unaffected_by_shutdown(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = _build_real_background_worker_service(Path(tmp), worker_count=3)
            before = service.status()
            self.assert_equal(before.worker_count, 3)
            service.shutdown(wait=True, timeout=2)
            after = service.status()
            self.assert_equal(after.worker_count, 3)
            self.assert_equal(after.task_count, before.task_count)

    # ================= RuntimeService corrected behavior =================

    def _test_runtime_status_reflects_shutdown_background_workers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bg_service = _build_real_background_worker_service(Path(tmp), worker_count=1)
            runtime = RuntimeService(
                started_at=0.0,
                rest_api_server=None,
                background_worker_service=bg_service,
                shell=None,
            )
            self.assert_true(runtime.status().background_workers_active)
            bg_service.shutdown(wait=True, timeout=2)
            self.assert_false(runtime.status().background_workers_active)

    def _test_runtime_shutdown_second_call_reports_false(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bg_service = _build_real_background_worker_service(Path(tmp), worker_count=1)
            runtime = RuntimeService(
                started_at=0.0,
                rest_api_server=None,
                background_worker_service=bg_service,
                shell=None,
            )
            first_report = runtime.shutdown()
            self.assert_true(first_report.background_workers_was_active)
            self.assert_true(first_report.background_workers_stopped)
            second_report = runtime.shutdown()
            # Corrected by EP-062: the pool was already shut down before
            # this second call, so it genuinely "was not active".
            self.assert_false(second_report.background_workers_was_active)
            self.assert_true(second_report.background_workers_stopped)

    def _test_runtime_status_cli_omits_active_after_shutdown(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bg_service = _build_real_background_worker_service(Path(tmp), worker_count=2)
            runtime = RuntimeService(
                started_at=0.0,
                rest_api_server=None,
                background_worker_service=bg_service,
                shell=None,
            )
            module = RuntimeModule(runtime_service=runtime)

            before = module.execute("status", [])
            self.assert_true("Background Workers : ACTIVE" in before.message)
            self.assert_true("Background worker threads : 2" in before.message)

            bg_service.shutdown(wait=True, timeout=2)

            after = module.execute("status", [])
            self.assert_true("Background Workers : INACTIVE" in after.message)
            self.assert_false("Background worker threads" in after.message)
            self.assert_false("Background tasks submitted" in after.message)

    # ================= BackgroundWorkerModule CLI =================

    def _test_worker_status_cli_reports_running_no_after_stop(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = _build_real_background_worker_service(Path(tmp), worker_count=1)
            module = BackgroundWorkerModule(background_worker_service=service)

            before = module.execute("status", [])
            self.assert_true("Running : YES" in before.message)

            stop_result = module.execute("stop", [])
            self.assert_true(stop_result.success)

            after = module.execute("status", [])
            self.assert_true(
                "Running : NO" in after.message,
                "Expected 'worker status' to report 'Running : NO' after "
                "'worker stop' -- this is the exact, disclosed, CLI-reachable "
                "inconsistency EP-062 fixes (EP062_DESIGN.md Section 1/7).",
            )
            self.assert_false("Running : YES" in after.message)

    def _test_worker_submit_still_raises_after_stop(self) -> None:
        """Regression guard: `submit()`'s own, independent shutdown guard
        (`PoolShutDownError`) is untouched by this EP -- `worker submit`
        after `worker stop` still fails, exactly as before."""
        with tempfile.TemporaryDirectory() as tmp:
            service = _build_real_background_worker_service(Path(tmp), worker_count=1)
            module = BackgroundWorkerModule(background_worker_service=service)
            module.execute("stop", [])
            result = module.execute("submit", ["noop"])
            self.assert_false(result.success)

    # ================= Public-surface guards =================

    def _test_background_worker_service_public_surface_unchanged(self) -> None:
        """`EP062_DESIGN.md` Section 2.1/9: still exactly 5 public methods."""
        public_methods = {
            name
            for name, member in inspect.getmembers(BackgroundWorkerService)
            if not name.startswith("_") and inspect.isfunction(member)
        }
        self.assert_equal(
            public_methods,
            {"status", "submit", "get_task", "list_tasks", "shutdown"},
        )

    def _test_background_worker_status_fields_unchanged(self) -> None:
        """`EP062_DESIGN.md` Section 9: `BackgroundWorkerStatus`'s shape
        is unchanged -- only the value assigned to `running` changed."""
        field_names = {f.name for f in fields(BackgroundWorkerStatus)}
        self.assert_equal(
            field_names, {"enabled", "running", "worker_count", "task_count"}
        )
