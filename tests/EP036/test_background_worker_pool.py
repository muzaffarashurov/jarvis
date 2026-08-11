"""Real engineering tests for EP-036 STEP 1 - Background Worker Pool.

Builds a real `WorkflowEngineManager` + real `WorkflowEngine`,
composed with a duck-typed `PlanExecutionEngine` stand-in (the same
technique EP-033/034/035's own test suites use -- see
`tests/EP033/test_workflow_engine.py`'s `_StubPlanExecutionEngine`),
and drives a real `BackgroundWorkerPool` exactly as a caller would, no
mocked internals.

This suite specifically guards against every pitfall called out in
the EP-036 STEP 1 prompt's "CRITICAL LESSONS FROM THE PREVIOUS EP036
ATTEMPT":

1. Test isolation: `_test_isolation_from_other_pools_in_process`
   builds two independent pools side by side, in the same process,
   with colliding worker names ("background-worker-0", ...), and
   proves each test assertion about "pool A's workers" only ever
   inspects the exact `Thread` objects `pool_a.worker_threads()`
   returns -- never `threading.enumerate()`. No test in this file
   scans `threading.enumerate()` for "background-worker-*" threads.
2. Shutdown race: `_test_shutdown_join_timeout_is_not_termination_proof`
   and `_test_shutdown_reports_false_when_task_still_running` submit a
   task that blocks past a short `shutdown(timeout=...)`, and assert
   `shutdown()` returns False (never claims success) while the worker
   is still finishing that task -- then release it and confirm the
   worker actually does stop shortly after.
3. Idle-worker polling: `_test_idle_shutdown_is_fast` asserts an idle
   pool's `shutdown()` completes well within one second (default
   `poll_interval=0.05`), and that this says nothing about a pool with
   a task in flight (covered by lesson 2's tests instead).
4. (Windows subprocess encoding -- not applicable to this in-process
   unit-test suite; no subprocess is used anywhere in this file.)
"""

from __future__ import annotations

import tempfile
import threading
import time
from pathlib import Path

from src.core.background_workers.background_worker_pool import (
    BackgroundTask,
    BackgroundWorkerPool,
    BackgroundWorkerPoolError,
    InvalidWorkerCountError,
    PoolShutDownError,
    TaskStatus,
)
from src.core.config import Config
from src.core.plan_execution.plan_execution_result import PlanExecutionResult
from src.core.workflow_engine.workflow_definition import WorkflowDefinition, WorkflowRequestStep
from src.core.workflow_engine.workflow_engine import WorkflowEngine
from src.core.workflow_engine.workflow_engine_manager import WorkflowEngineManager
from src.testing.base_test import BaseTest
from src.testing.registry import TestRegistry

_WORKFLOW_ENGINE_YAML = (
    "workflow_engine:\n"
    "  enabled: true\n"
    "  default_provider: \"workflow_engine\"\n"
    "  stop_on_failure: true\n"
)


def _write_config(directory: Path) -> Config:
    """Return a freshly loaded Config for `directory` (never cached/reused)."""
    config_dir = directory / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / "config.yaml"
    config_path.write_text(_WORKFLOW_ENGINE_YAML, encoding="utf-8")
    return Config(config_path).load()


class _ControllableStubPlanExecutionEngine:
    """A duck-typed PlanExecutionEngine stand-in with test-controllable behavior.

    `WorkflowEngine` only ever calls `execute_request()` on the object
    it is given (mirroring `tests/EP033/test_workflow_engine.py`'s
    `_StubPlanExecutionEngine`). This variant additionally supports:
      - `raising_requests`: requests whose execution raises, to
        exercise `BackgroundWorkerPool`'s "a workflow defect never
        kills the worker" handling.
      - `gate`: an optional `threading.Event` every call waits on
        before proceeding, letting tests deterministically observe a
        task in the `RUNNING` state (or hold `shutdown()` past its
        timeout) without relying on `time.sleep()` guesswork.
    """

    def __init__(
        self,
        failing_requests: frozenset = frozenset(),
        raising_requests: frozenset = frozenset(),
        gate: threading.Event | None = None,
    ) -> None:
        self._failing_requests = failing_requests
        self._raising_requests = raising_requests
        self._gate = gate
        self._calls_lock = threading.Lock()
        self.calls: list[str] = []

    def execute_request(self, request: str) -> PlanExecutionResult:
        with self._calls_lock:
            self.calls.append(request)
        if self._gate is not None:
            self._gate.wait()
        if request in self._raising_requests:
            raise RuntimeError(f"boom while executing '{request}'")
        success = request not in self._failing_requests
        return PlanExecutionResult(
            plan=None,  # not inspected by anything under test
            step_results=[],
            completed_count=1 if success else 0,
            failed_count=0 if success else 1,
            skipped_count=0,
            success=success,
        )


def _build_engine(
    tmp_path: Path,
    workflow_ids: list[str],
    failing_requests: frozenset = frozenset(),
    raising_requests: frozenset = frozenset(),
    gate: threading.Event | None = None,
) -> tuple[WorkflowEngine, _ControllableStubPlanExecutionEngine]:
    """Build a real WorkflowEngine with one single-step definition per workflow id.

    Each definition's one step's `request` text is the workflow id
    itself, so `failing_requests`/`raising_requests` can address a
    specific workflow by its id.
    """
    config = _write_config(tmp_path)
    manager = WorkflowEngineManager(config=config)
    for workflow_id in workflow_ids:
        manager.register_definition(
            WorkflowDefinition(
                id=workflow_id,
                name=workflow_id,
                description="",
                enabled=True,
                steps=(WorkflowRequestStep(name="only", request=workflow_id),),
            )
        )
    stub = _ControllableStubPlanExecutionEngine(
        failing_requests=failing_requests, raising_requests=raising_requests, gate=gate
    )
    engine = WorkflowEngine(manager=manager, plan_execution_engine=stub)
    return engine, stub


def _wait_until(predicate, timeout: float = 5.0, interval: float = 0.01) -> bool:
    """Poll `predicate()` until it returns truthy or `timeout` elapses."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


@TestRegistry.register
class BackgroundWorkerPoolTest(BaseTest):
    NAME = "EP036"

    def run(self):
        # ---------- Construction ----------
        self._test_pool_starts_expected_worker_count()
        self._test_worker_names_are_deterministic()
        self._test_invalid_worker_count_raises()

        # ---------- Task submission & execution ----------
        self._test_submit_returns_trackable_task_id()
        self._test_queued_tasks_execute()
        self._test_multiple_workers_execute_concurrently()
        self._test_task_status_transitions()
        self._test_failed_workflow_marks_task_failed()
        self._test_raising_workflow_does_not_kill_worker()
        self._test_pool_survives_workflow_engine_raising()
        self._test_unknown_task_id_returns_none()
        self._test_task_snapshots_are_copies()
        self._test_concurrent_submissions_are_thread_safe()

        # ---------- Shutdown ----------
        self._test_shutdown_stops_workers()
        self._test_shutdown_leaves_no_pool_workers_alive()
        self._test_submission_after_shutdown_raises()
        self._test_repeated_creation_and_shutdown_does_not_leak_threads()
        self._test_shutdown_reliable_under_repeated_execution()
        self._test_shutdown_join_timeout_is_not_termination_proof()
        self._test_shutdown_reports_false_when_task_still_running()
        self._test_idle_shutdown_is_fast()
        self._test_shutdown_wait_false_does_not_verify_termination()
        self._test_shutdown_is_idempotent()

        # ---------- Isolation from other pools in the process ----------
        self._test_isolation_from_other_pools_in_process()

        return self.result

    # ---------- Construction ----------

    def _test_pool_starts_expected_worker_count(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine, _ = _build_engine(Path(tmp), ["wf-a"])
            pool = BackgroundWorkerPool(workflow_engine=engine, worker_count=3)
            try:
                self.assert_equal(pool.worker_count, 3)
                self.assert_equal(len(pool.worker_threads()), 3)
                self.assert_true(
                    _wait_until(lambda: all(t.is_alive() for t in pool.worker_threads())),
                    "All 3 workers should be alive shortly after construction",
                )
            finally:
                pool.shutdown(wait=True, timeout=5)

    def _test_worker_names_are_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine, _ = _build_engine(Path(tmp), ["wf-a"])
            pool = BackgroundWorkerPool(workflow_engine=engine, worker_count=3)
            try:
                names = [t.name for t in pool.worker_threads()]
                self.assert_equal(
                    names, ["background-worker-0", "background-worker-1", "background-worker-2"]
                )
            finally:
                pool.shutdown(wait=True, timeout=5)

    def _test_invalid_worker_count_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine, _ = _build_engine(Path(tmp), ["wf-a"])
            try:
                BackgroundWorkerPool(workflow_engine=engine, worker_count=0)
                self.assert_true(False, "worker_count=0 should raise InvalidWorkerCountError")
            except InvalidWorkerCountError:
                self.result.add_pass()
            try:
                BackgroundWorkerPool(workflow_engine=engine, worker_count=-1)
                self.assert_true(False, "worker_count=-1 should raise InvalidWorkerCountError")
            except InvalidWorkerCountError:
                self.result.add_pass()

    # ---------- Task submission & execution ----------

    def _test_submit_returns_trackable_task_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine, _ = _build_engine(Path(tmp), ["wf-a"])
            pool = BackgroundWorkerPool(workflow_engine=engine, worker_count=1)
            try:
                task_id = pool.submit("wf-a")
                self.assert_true(isinstance(task_id, str) and len(task_id) > 0)
                task = pool.get_task(task_id)
                self.assert_not_none(task)
                self.assert_equal(task.workflow_id, "wf-a")
            finally:
                pool.shutdown(wait=True, timeout=5)

    def _test_queued_tasks_execute(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine, stub = _build_engine(Path(tmp), ["wf-a"])
            pool = BackgroundWorkerPool(workflow_engine=engine, worker_count=1)
            try:
                task_id = pool.submit("wf-a")
                self.assert_true(
                    _wait_until(lambda: pool.get_task(task_id).status == TaskStatus.COMPLETED),
                    "Task should reach COMPLETED",
                )
                task = pool.get_task(task_id)
                self.assert_not_none(task.result)
                self.assert_true(task.result.success)
                self.assert_equal(stub.calls, ["wf-a"])
            finally:
                pool.shutdown(wait=True, timeout=5)

    def _test_multiple_workers_execute_concurrently(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workflow_ids = ["wf-a", "wf-b", "wf-c"]
            gate = threading.Event()
            engine, stub = _build_engine(Path(tmp), workflow_ids, gate=gate)
            pool = BackgroundWorkerPool(workflow_engine=engine, worker_count=3)
            try:
                task_ids = [pool.submit(workflow_id) for workflow_id in workflow_ids]

                # All 3 workers should pick up their task and block on the
                # gate concurrently -- proving >1 worker can execute at once,
                # not just that the pool can execute 1-at-a-time serially.
                self.assert_true(
                    _wait_until(lambda: len(stub.calls) == 3),
                    "All 3 tasks should have started concurrently",
                )
                self.assert_true(
                    _wait_until(
                        lambda: all(
                            pool.get_task(tid).status == TaskStatus.RUNNING for tid in task_ids
                        )
                    ),
                    "All 3 tasks should be RUNNING concurrently",
                )

                gate.set()

                self.assert_true(
                    _wait_until(
                        lambda: all(
                            pool.get_task(tid).status == TaskStatus.COMPLETED for tid in task_ids
                        )
                    ),
                    "All 3 tasks should reach COMPLETED after the gate is released",
                )
            finally:
                pool.shutdown(wait=True, timeout=5)

    def _test_task_status_transitions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            gate = threading.Event()
            engine, _ = _build_engine(Path(tmp), ["wf-a"], gate=gate)
            pool = BackgroundWorkerPool(workflow_engine=engine, worker_count=1)
            try:
                task_id = pool.submit("wf-a")
                self.assert_true(
                    _wait_until(lambda: pool.get_task(task_id).status == TaskStatus.RUNNING),
                    "Task should reach RUNNING before the gate is released",
                )
                gate.set()
                self.assert_true(
                    _wait_until(lambda: pool.get_task(task_id).status == TaskStatus.COMPLETED),
                    "Task should reach COMPLETED after the gate is released",
                )
            finally:
                pool.shutdown(wait=True, timeout=5)

    def _test_failed_workflow_marks_task_failed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine, _ = _build_engine(
                Path(tmp), ["wf-a"], failing_requests=frozenset({"wf-a"})
            )
            pool = BackgroundWorkerPool(workflow_engine=engine, worker_count=1)
            try:
                task_id = pool.submit("wf-a")
                self.assert_true(
                    _wait_until(lambda: pool.get_task(task_id).status == TaskStatus.FAILED)
                )
                task = pool.get_task(task_id)
                self.assert_not_none(task.result)
                self.assert_false(task.result.success)
                self.assert_not_none(task.error)
            finally:
                pool.shutdown(wait=True, timeout=5)

    def _test_raising_workflow_does_not_kill_worker(self) -> None:
        """A step executor that raises is isolated by WorkflowRunProvider
        into a FAILED step outcome (see `DefaultWorkflowRunProvider.run_step`)
        -- WorkflowEngine.run() itself never raises for this. This test
        confirms that isolated failure still leaves the task FAILED (with
        the original exception text preserved in the step outcome) and
        the worker able to keep processing further work."""
        with tempfile.TemporaryDirectory() as tmp:
            engine, _ = _build_engine(
                Path(tmp), ["wf-bad", "wf-good"], raising_requests=frozenset({"wf-bad"})
            )
            pool = BackgroundWorkerPool(workflow_engine=engine, worker_count=1)
            try:
                bad_id = pool.submit("wf-bad")
                self.assert_true(
                    _wait_until(lambda: pool.get_task(bad_id).status == TaskStatus.FAILED)
                )
                bad_task = pool.get_task(bad_id)
                self.assert_not_none(bad_task.result)
                self.assert_false(bad_task.result.success)
                self.assert_true("boom" in bad_task.result.summary())

                # The single worker must still be alive and able to process
                # further work after a workflow it ran failed.
                self.assert_true(pool.worker_threads()[0].is_alive())
                good_id = pool.submit("wf-good")
                self.assert_true(
                    _wait_until(lambda: pool.get_task(good_id).status == TaskStatus.COMPLETED),
                    "Worker should still process new tasks after a prior task failed",
                )
            finally:
                pool.shutdown(wait=True, timeout=5)

    def _test_pool_survives_workflow_engine_raising(self) -> None:
        """Defense in depth: even if `workflow_engine.run()` itself raises
        an exception that is not a `WorkflowEngineError` (something the
        real `WorkflowEngine` never does -- see the test above -- but a
        non-standard engine-like object conceivably could), the worker
        thread must survive and the task must be recorded as FAILED, per
        `_execute_task`'s outer `except Exception` handling."""

        class _AlwaysRaisingWorkflowEngine:
            def run(self, workflow_id: str):
                raise RuntimeError(f"boom running '{workflow_id}'")

        pool = BackgroundWorkerPool(
            workflow_engine=_AlwaysRaisingWorkflowEngine(), worker_count=1
        )
        try:
            task_id = pool.submit("anything")
            self.assert_true(
                _wait_until(lambda: pool.get_task(task_id).status == TaskStatus.FAILED)
            )
            task = pool.get_task(task_id)
            self.assert_true(task.error is not None and "boom" in task.error)
            self.assert_true(pool.worker_threads()[0].is_alive())
        finally:
            pool.shutdown(wait=True, timeout=5)

    def _test_unknown_task_id_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine, _ = _build_engine(Path(tmp), ["wf-a"])
            pool = BackgroundWorkerPool(workflow_engine=engine, worker_count=1)
            try:
                self.assert_equal(pool.get_task("does-not-exist"), None)
            finally:
                pool.shutdown(wait=True, timeout=5)

    def _test_task_snapshots_are_copies(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            gate = threading.Event()
            engine, _ = _build_engine(Path(tmp), ["wf-a"], gate=gate)
            pool = BackgroundWorkerPool(workflow_engine=engine, worker_count=1)
            try:
                task_id = pool.submit("wf-a")
                snapshot: BackgroundTask = pool.get_task(task_id)
                # Mutate the returned copy only -- this must never reach
                # the pool's own internal task registry.
                snapshot.status = TaskStatus.FAILED
                snapshot.error = "mutated by caller, should not stick"

                gate.set()
                self.assert_true(
                    _wait_until(lambda: pool.get_task(task_id).status == TaskStatus.COMPLETED),
                    "Pool's internal state must be unaffected by mutating a returned snapshot",
                )
                self.assert_true(pool.get_task(task_id).error is None)
            finally:
                pool.shutdown(wait=True, timeout=5)

    def _test_concurrent_submissions_are_thread_safe(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine, _ = _build_engine(Path(tmp), ["wf-a"])
            pool = BackgroundWorkerPool(workflow_engine=engine, worker_count=4)
            try:
                submitted: list[str] = []
                submitted_lock = threading.Lock()

                def _submit_many() -> None:
                    for _ in range(25):
                        task_id = pool.submit("wf-a")
                        with submitted_lock:
                            submitted.append(task_id)

                submitters = [threading.Thread(target=_submit_many) for _ in range(4)]
                for t in submitters:
                    t.start()
                for t in submitters:
                    t.join()

                self.assert_equal(len(submitted), 100)
                self.assert_equal(len(set(submitted)), 100)  # every task id unique
                self.assert_true(
                    _wait_until(
                        lambda: all(
                            pool.get_task(tid).status == TaskStatus.COMPLETED
                            for tid in submitted
                        ),
                        timeout=10.0,
                    ),
                    "All 100 concurrently submitted tasks should complete",
                )
            finally:
                pool.shutdown(wait=True, timeout=5)

    # ---------- Shutdown ----------

    def _test_shutdown_stops_workers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine, _ = _build_engine(Path(tmp), ["wf-a"])
            pool = BackgroundWorkerPool(workflow_engine=engine, worker_count=2)
            stopped = pool.shutdown(wait=True, timeout=5)
            self.assert_true(stopped)
            self.assert_true(pool.is_shutdown)
            for worker in pool.worker_threads():
                self.assert_false(worker.is_alive())

    def _test_shutdown_leaves_no_pool_workers_alive(self) -> None:
        # Deliberately does NOT scan threading.enumerate() -- only this
        # pool's own worker_threads() are ever inspected, per the EP-036
        # STEP 1 prompt's test-isolation requirement.
        with tempfile.TemporaryDirectory() as tmp:
            engine, _ = _build_engine(Path(tmp), ["wf-a"])
            pool = BackgroundWorkerPool(workflow_engine=engine, worker_count=3)
            this_pool_workers = pool.worker_threads()
            pool.shutdown(wait=True, timeout=5)
            after_alive = {t.ident for t in this_pool_workers if t.is_alive()}
            self.assert_equal(after_alive, set())

    def _test_submission_after_shutdown_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine, _ = _build_engine(Path(tmp), ["wf-a"])
            pool = BackgroundWorkerPool(workflow_engine=engine, worker_count=1)
            pool.shutdown(wait=True, timeout=5)
            try:
                pool.submit("wf-a")
                self.assert_true(False, "submit() after shutdown should raise PoolShutDownError")
            except PoolShutDownError:
                self.result.add_pass()
            except BackgroundWorkerPoolError:
                self.assert_true(False, "wrong exception type raised")

    def _test_repeated_creation_and_shutdown_does_not_leak_threads(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine, _ = _build_engine(Path(tmp), ["wf-a"])
            baseline = threading.active_count()
            all_workers: list[threading.Thread] = []
            for _ in range(5):
                pool = BackgroundWorkerPool(workflow_engine=engine, worker_count=3)
                pool.submit("wf-a")
                all_workers.extend(pool.worker_threads())
                stopped = pool.shutdown(wait=True, timeout=5)
                self.assert_true(stopped)

            self.assert_true(
                _wait_until(lambda: threading.active_count() <= baseline),
                f"Thread count should return to baseline ({baseline}) after "
                "5 create/shutdown cycles",
            )
            self.assert_true(all(not w.is_alive() for w in all_workers))

    def _test_shutdown_reliable_under_repeated_execution(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine, _ = _build_engine(Path(tmp), ["wf-a"])
            for _ in range(10):
                pool = BackgroundWorkerPool(workflow_engine=engine, worker_count=2)
                for _ in range(3):
                    pool.submit("wf-a")
                stopped = pool.shutdown(wait=True, timeout=5)
                self.assert_true(stopped)
                for worker in pool.worker_threads():
                    self.assert_false(worker.is_alive())

    def _test_shutdown_join_timeout_is_not_termination_proof(self) -> None:
        """A short shutdown(timeout=...) must never be reported as success
        while a worker is still executing -- Thread.join(timeout=...)
        returning is not proof of termination (EP-036 lesson 2)."""
        with tempfile.TemporaryDirectory() as tmp:
            gate = threading.Event()
            engine, _ = _build_engine(Path(tmp), ["wf-a"], gate=gate)
            pool = BackgroundWorkerPool(workflow_engine=engine, worker_count=1)
            try:
                task_id = pool.submit("wf-a")
                self.assert_true(
                    _wait_until(lambda: pool.get_task(task_id).status == TaskStatus.RUNNING)
                )

                stopped = pool.shutdown(wait=True, timeout=0.1)
                self.assert_false(
                    stopped, "shutdown() must report False while a worker is still running"
                )
                self.assert_true(
                    any(w.is_alive() for w in pool.worker_threads()),
                    "The worker executing the gated task should still be alive",
                )
            finally:
                gate.set()
                self.assert_true(
                    _wait_until(lambda: all(not w.is_alive() for w in pool.worker_threads())),
                    "The worker should terminate shortly after the gate is released",
                )

    def _test_shutdown_reports_false_when_task_still_running(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            gate = threading.Event()
            engine, _ = _build_engine(Path(tmp), ["wf-a"], gate=gate)
            pool = BackgroundWorkerPool(workflow_engine=engine, worker_count=1)
            try:
                pool.submit("wf-a")
                self.assert_true(_wait_until(lambda: len(pool.list_tasks()) == 1))
                stopped = pool.shutdown(wait=True, timeout=0.05)
                self.assert_false(stopped)
            finally:
                gate.set()
                pool.shutdown(wait=True, timeout=5)

    def _test_idle_shutdown_is_fast(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine, _ = _build_engine(Path(tmp), ["wf-a"])
            pool = BackgroundWorkerPool(workflow_engine=engine, worker_count=4)
            self.assert_true(
                _wait_until(lambda: all(t.is_alive() for t in pool.worker_threads()))
            )
            start = time.monotonic()
            stopped = pool.shutdown(wait=True, timeout=5)
            elapsed = time.monotonic() - start
            self.assert_true(stopped)
            self.assert_true(
                elapsed < 1.0, f"Idle-pool shutdown took {elapsed:.3f}s, expected < 1.0s"
            )

    def _test_shutdown_wait_false_does_not_verify_termination(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine, _ = _build_engine(Path(tmp), ["wf-a"])
            pool = BackgroundWorkerPool(workflow_engine=engine, worker_count=2)
            result = pool.shutdown(wait=False)
            self.assert_false(result, "shutdown(wait=False) never claims verified termination")
            self.assert_true(pool.is_shutdown)
            # Clean up for real so the test process doesn't accumulate threads.
            self.assert_true(
                _wait_until(lambda: all(not w.is_alive() for w in pool.worker_threads()))
            )

    def _test_shutdown_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine, _ = _build_engine(Path(tmp), ["wf-a"])
            pool = BackgroundWorkerPool(workflow_engine=engine, worker_count=1)
            first = pool.shutdown(wait=True, timeout=5)
            second = pool.shutdown(wait=True, timeout=5)
            self.assert_true(first)
            self.assert_true(second)

    # ---------- Isolation from other pools in the process ----------

    def _test_isolation_from_other_pools_in_process(self) -> None:
        """Two pools, colliding worker names, coexisting in this process.

        Directly demonstrates the EP-036 STEP 1 prompt's required fix
        for the previous attempt's test-isolation bug: every assertion
        below about "pool A" uses only `pool_a.worker_threads()`, and
        every assertion about "pool B" uses only
        `pool_b.worker_threads()` -- never a blanket
        `threading.enumerate()` scan that could not distinguish them
        (both pools name their first worker "background-worker-0").
        """
        with tempfile.TemporaryDirectory() as tmp:
            engine, _ = _build_engine(Path(tmp), ["wf-a"])
            pool_a = BackgroundWorkerPool(workflow_engine=engine, worker_count=2)
            pool_b = BackgroundWorkerPool(workflow_engine=engine, worker_count=2)
            try:
                # Colliding names, distinct Thread identities.
                self.assert_equal(pool_a.worker_threads()[0].name, "background-worker-0")
                self.assert_equal(pool_b.worker_threads()[0].name, "background-worker-0")
                self.assert_true(
                    pool_a.worker_threads()[0].ident != pool_b.worker_threads()[0].ident
                )

                # Shutting down pool A must never affect pool B's workers,
                # even though a naive name-based scan could not tell them
                # apart.
                self.assert_true(pool_a.shutdown(wait=True, timeout=5))
                for worker in pool_a.worker_threads():
                    self.assert_false(worker.is_alive())
                self.assert_true(
                    _wait_until(lambda: all(t.is_alive() for t in pool_b.worker_threads())),
                    "Pool B's workers must remain alive after pool A's shutdown",
                )
            finally:
                pool_b.shutdown(wait=True, timeout=5)
