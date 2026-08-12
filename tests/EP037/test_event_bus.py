"""Real engineering tests for EP-037 STEP 2 - EventBus Enhancement & Cross-EP Decoupling.

Builds a real, thread-safe `EventBus` (`src/core/events.py`), composed
with real `WorkflowEngineService` (EP-033), `WorkflowSchedulerEngine`
(EP-034), `AutomationEngine` (EP-035), and `BackgroundWorkerPool`
(EP-036) instances -- and, for the full end-to-end cases, a real
`Bootstrap` -- exactly as a caller would, no mocked internals,
matching every other EP's test suite in this project (see
tests/EP035/test_automation_engine.py).

This suite covers:

1. `EventBus` itself: subscribe/publish/unsubscribe, multiple
   subscribers invoked in order, subscriber exception isolation,
   concurrent publish from multiple threads, concurrent
   subscribe/unsubscribe while publishing, and a handler that
   unsubscribes itself during its own invocation (no corruption, no
   deadlock).
2. `WorkflowEngineService.run()` / `WorkflowSchedulerEngine.run_now()`
   publishing `"workflow.completed"` additively, alongside the
   untouched `set_automation_hook()` API.
3. `BackgroundWorkerPool` publishing `"background_worker.task_completed"`
   / `"background_worker.task_failed"` at the existing COMPLETED/FAILED
   transitions, without changing task status/result/locking.
4. The resolved hook-vs-event conflict: a completed workflow produces
   *exactly one* automation notification through the EventBus path,
   `AutomationEngine.notify_run()` is never double-triggered, and real
   `Bootstrap` wiring no longer uses `set_automation_hook()` for
   production automation (the hook itself remains fully intact and
   independently usable).
"""

from __future__ import annotations

import tempfile
import threading
import time
from pathlib import Path

from src.bootstrap import Bootstrap
from src.core.automation_engine.automation_engine import AutomationEngine
from src.core.automation_engine.automation_rule import AutomationRule, AutomationTriggerCondition
from src.core.automation_engine.automation_rule_registry import AutomationRuleRegistry
from src.core.background_workers.background_worker_pool import BackgroundWorkerPool, TaskStatus
from src.core.config import Config
from src.core.events import EventBus
from src.core.plan_execution.plan_execution_result import PlanExecutionResult
from src.core.scheduler.job import Schedule, ScheduleType
from src.core.workflow_engine.workflow_definition import WorkflowDefinition, WorkflowRequestStep
from src.core.workflow_engine.workflow_engine import WorkflowEngine
from src.core.workflow_engine.workflow_engine_manager import WorkflowEngineManager
from src.core.workflow_scheduler.scheduled_workflow import ScheduledWorkflow
from src.core.workflow_scheduler.scheduled_workflow_registry import ScheduledWorkflowRegistry
from src.core.workflow_scheduler.workflow_scheduler_engine import WorkflowSchedulerEngine
from src.services.background_worker_service import BackgroundWorkerService
from src.services.workflow_engine_service import WorkflowEngineService
from src.testing.base_test import BaseTest
from src.testing.registry import TestRegistry


class _ChdirGuard:
    """Context manager: chdir into `directory`, always restoring the original cwd."""

    def __init__(self, directory: Path) -> None:
        self._directory = directory
        self._original = Path.cwd()

    def __enter__(self) -> Path:
        import os

        os.chdir(self._directory)
        return self._directory

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        import os

        os.chdir(self._original)


_WORKFLOW_ENGINE_ONLY_YAML = (
    "workflow_engine:\n"
    "  enabled: true\n"
    "  default_provider: \"workflow_engine\"\n"
    "  stop_on_failure: true\n"
)


def _write_config(directory: Path, sections: str) -> Config:
    config_dir = directory / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / "config.yaml"
    config_path.write_text(sections, encoding="utf-8")
    return Config(config_path).load()


class _StubPlanExecutionEngine:
    """A minimal, duck-typed stand-in for EP-030's PlanExecutionEngine.

    Identical technique to every other EP's test suite in this
    project -- WorkflowEngine only ever calls `execute_request()` on
    the object it is given.
    """

    def __init__(self, failing_requests: frozenset = frozenset()) -> None:
        self._failing_requests = failing_requests
        self.calls: list[str] = []
        self._lock = threading.Lock()

    def execute_request(self, request: str) -> PlanExecutionResult:
        with self._lock:
            self.calls.append(request)
        success = request not in self._failing_requests
        return PlanExecutionResult(
            plan=None,
            step_results=[],
            completed_count=1 if success else 0,
            failed_count=0 if success else 1,
            skipped_count=0,
            success=success,
        )


def _build_workflow_engine(
    tmp_path: Path, failing_requests: frozenset = frozenset()
) -> tuple[WorkflowEngine, WorkflowEngineManager, _StubPlanExecutionEngine]:
    """Build a real WorkflowEngine (EP-033) backed by a stub PlanExecutionEngine."""
    config = _write_config(tmp_path, _WORKFLOW_ENGINE_ONLY_YAML)
    manager = WorkflowEngineManager(config=config)
    stub = _StubPlanExecutionEngine(failing_requests=failing_requests)
    engine = WorkflowEngine(manager=manager, plan_execution_engine=stub)
    return engine, manager, stub


def _register_workflow(manager: WorkflowEngineManager, workflow_id: str, request: str) -> None:
    manager.register_definition(
        WorkflowDefinition(
            id=workflow_id,
            name=workflow_id,
            description="",
            enabled=True,
            steps=(WorkflowRequestStep(name="Step", request=request),),
        )
    )


def _automation_rule(
    rule_id: str,
    trigger_workflow_id: str,
    action_workflow_id: str,
    condition: AutomationTriggerCondition = AutomationTriggerCondition.ON_ANY,
) -> AutomationRule:
    return AutomationRule(
        id=rule_id,
        name=rule_id,
        description="A test automation rule.",
        trigger_workflow_id=trigger_workflow_id,
        trigger_condition=condition,
        action_workflow_id=action_workflow_id,
        enabled=True,
    )


_FULL_BOOTSTRAP_CONFIG_YAML = (
    "app:\n"
    "  name: \"JARVIS-TEST\"\n"
    "  tagline: \"Test\"\n"
    "  version: \"0.0.0-test\"\n\n"
    "logging:\n"
    "  level: \"INFO\"\n"
    "  retention_days: 1\n"
    "  console_enabled: false\n\n"
    "paths:\n"
    "  logs: \"logs\"\n"
    "  data_input: \"data/input\"\n"
    "  data_output: \"data/output\"\n"
    "  data_cache: \"data/cache\"\n"
    "  data_database: \"data/database\"\n"
    "  knowledge: \"knowledge\"\n"
    "  prompts: \"prompts\"\n\n"
    "memory:\n"
    "  enabled: true\n"
    "  persistent: false\n"
    "  auto_save: false\n"
    "  max_entries: 10000\n"
    "  default_ttl: null\n"
    "  default_provider: \"memory\"\n\n"
    "knowledge:\n"
    "  enabled: true\n"
    "  default_provider: \"local\"\n\n"
    "long_term_memory:\n"
    "  enabled: true\n"
    "  default_provider: \"knowledge\"\n\n"
    "orchestrator:\n"
    "  skills_enabled: []\n\n"
    "invoice:\n"
    "  script: \"\"\n\n"
    "fast_response:\n"
    "  workbook: \"\"\n"
    "  worksheet: \"\"\n"
    "  backup_folder: \"\"\n\n"
    "workflows:\n"
    "  enabled: true\n"
    "  auto_register: true\n\n"
    "processes:\n"
    "  auto_start: false\n"
    "  dependency_check: true\n"
    "  health_check_interval: 60\n\n"
    "scheduler:\n"
    "  enabled: true\n"
    "  auto_start: false\n"
    "  tick_interval: 1\n\n"
    "plugins:\n"
    "  enabled: true\n"
    "  auto_load: false\n"
    "  auto_discovery: false\n"
    "  plugin_directory: \"plugins\"\n\n"
    "telegram:\n"
    "  enabled: false\n"
    "  auto_start: false\n"
    "  token: \"\"\n"
    "  allowed_chat_ids: []\n"
    "  polling_interval: 2\n\n"
    "ai:\n"
    "  enabled: true\n"
    "  default_provider: \"none\"\n"
    "  timeout: 120\n"
    "  retry_count: 2\n"
    "  max_context_messages: 20\n\n"
    "conversation:\n"
    "  enabled: true\n"
    "  auto_save: false\n"
    "  max_messages: 100\n"
    "  max_conversations: 100\n"
    "  storage_file: \"data/database/conversations.json\"\n"
    "  truncate_strategy: \"oldest\"\n\n"
    "prompt:\n"
    "  enabled: true\n"
    "  system_prompt: \"\"\n"
    "  append_datetime: false\n"
    "  append_provider_name: false\n"
    "  append_os_information: false\n"
    "  append_working_directory: false\n"
    "  include_working_directory: false\n"
    "  include_project_files: false\n"
    "  smart_selection: true\n\n"
    "indexing:\n"
    "  storage_backend: \"memory\"\n"
    "  storage_file: \"data/database/project_index.json\"\n\n"
    "providers:\n"
    "  claude:\n"
    "    enabled: false\n"
    "    api_key: \"\"\n"
    "  openai:\n"
    "    enabled: false\n"
    "    api_key: \"\"\n"
    "  gemini:\n"
    "    enabled: false\n"
    "    api_key: \"\"\n"
    "  ollama:\n"
    "    enabled: false\n"
    "    endpoint: \"\"\n"
    "  lmstudio:\n"
    "    enabled: false\n"
    "    endpoint: \"\"\n\n"
    "embedding:\n"
    "  enabled: true\n"
    "  default_provider: \"local\"\n"
    "  batch_size: 16\n"
    "  providers:\n"
    "    local:\n"
    "      enabled: true\n"
    "      model: \"local-hash-v1\"\n"
    "      dimension: 16\n"
    "    cloud:\n"
    "      enabled: false\n"
    "      api_key: \"\"\n"
    "      model: \"text-embedding-cloud-v1\"\n"
    "      dimension: 1536\n\n"
    "rag:\n"
    "  enabled: true\n"
    "  top_k: 5\n"
    "  max_context_characters: 4000\n\n"
    "semantic:\n"
    "  enabled: true\n"
    "  default_provider: \"semantic\"\n"
    "  top_k: 5\n"
    "  similarity_threshold: 0.0\n\n"
    "context_compression:\n"
    "  enabled: true\n"
    "  default_provider: \"compression\"\n"
    "  max_context_characters: 12000\n"
    "  max_chunks: 20\n"
    "  deduplicate: true\n\n"
    "agent:\n"
    "  enabled: true\n"
    "  default_agent: \"jarvis\"\n"
    "  startup_mode: \"idle\"\n\n"
    "planning:\n"
    "  enabled: true\n"
    "  default_provider: \"planning\"\n"
    "  max_steps: 10\n\n"
    "plan_execution:\n"
    "  enabled: true\n"
    "  default_provider: \"plan_execution\"\n"
    "  stop_on_failure: true\n\n"
    "tool:\n"
    "  enabled: true\n"
    "  default_provider: \"tool_engine\"\n\n"
    "collaboration:\n"
    "  enabled: true\n"
    "  default_provider: \"collaboration\"\n\n"
    "workflow_engine:\n"
    "  enabled: true\n"
    "  default_provider: \"workflow_engine\"\n"
    "  stop_on_failure: true\n\n"
    "workflow_scheduler:\n"
    "  enabled: true\n"
    "  auto_start: false\n"
    "  tick_interval: 5\n\n"
    "automation:\n"
    "  enabled: {automation_enabled}\n"
)


def _write_full_bootstrap_config(directory: Path, automation_enabled: bool = True) -> None:
    config_dir = directory / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "config.yaml").write_text(
        _FULL_BOOTSTRAP_CONFIG_YAML.format(automation_enabled=str(automation_enabled).lower()),
        encoding="utf-8",
    )


def _wait_until(predicate, timeout: float = 5.0, interval: float = 0.01) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


@TestRegistry.register
class EventBusTest(BaseTest):
    NAME = "EP037"

    def run(self):
        # ---------- EventBus: core behavior ----------
        self._test_subscribe_publish_basic()
        self._test_multiple_subscribers_invoked_in_order()
        self._test_unsubscribe_removes_handler()
        self._test_subscriber_exception_isolated()
        self._test_publish_with_no_subscribers_is_noop()
        self._test_event_names_reflects_subscriptions()
        self._test_subscribe_rejects_empty_name()
        self._test_subscribe_rejects_non_callable()

        # ---------- EventBus: thread safety ----------
        self._test_concurrent_publish_from_multiple_threads()
        self._test_concurrent_subscribe_unsubscribe_during_publish()
        self._test_handler_self_unsubscribe_during_publish()
        self._test_handler_subscribe_during_publish_no_deadlock()

        # ---------- EP-033/034 publish "workflow.completed" ----------
        self._test_workflow_engine_service_publishes_workflow_completed()
        self._test_workflow_engine_service_no_publish_without_event_bus()
        self._test_workflow_scheduler_engine_publishes_workflow_completed()

        # ---------- EP-036 publish background_worker.* ----------
        self._test_background_worker_pool_publishes_task_completed()
        self._test_background_worker_pool_publishes_task_failed_on_result()
        self._test_background_worker_pool_publishes_task_failed_on_exception()
        self._test_background_worker_pool_task_state_unaffected_by_event_bus()

        # ---------- Hook vs event migration: exactly-once guarantee ----------
        self._test_on_demand_run_triggers_automation_exactly_once_via_event()
        self._test_scheduled_run_triggers_automation_exactly_once_via_event()
        self._test_set_automation_hook_still_works_directly()
        self._test_hook_and_event_together_would_double_fire_if_both_wired()

        # ---------- Bootstrap: production wiring uses the event, not the hook ----------
        self._test_bootstrap_on_demand_run_triggers_automation_via_event()
        self._test_bootstrap_production_wiring_does_not_use_hook()
        self._test_bootstrap_disabled_automation_never_fires()

        # ---------- STEP 3: background-worker completion -> automation adapter ----------
        self._test_background_worker_completion_adapter_triggers_automation_exactly_once()
        self._test_background_worker_task_failed_never_triggers_automation()
        self._test_background_worker_and_workflow_completed_do_not_double_fire()
        self._test_background_worker_pool_and_service_api_unchanged()
        self._test_bootstrap_background_worker_completion_triggers_automation()
        self._test_bootstrap_disabled_automation_also_skips_background_worker_adapter()

        return self.result

    # ---------- EventBus: core behavior ----------

    def _test_subscribe_publish_basic(self) -> None:
        bus = EventBus()
        received = []
        bus.subscribe("evt", lambda **kw: received.append(kw))
        bus.publish("evt", value=1)
        self.assert_equal(received, [{"value": 1}])

    def _test_multiple_subscribers_invoked_in_order(self) -> None:
        bus = EventBus()
        order = []
        bus.subscribe("evt", lambda: order.append("first"))
        bus.subscribe("evt", lambda: order.append("second"))
        bus.subscribe("evt", lambda: order.append("third"))
        bus.publish("evt")
        self.assert_equal(order, ["first", "second", "third"])

    def _test_unsubscribe_removes_handler(self) -> None:
        bus = EventBus()
        calls = []
        handler = lambda: calls.append(1)  # noqa: E731
        bus.subscribe("evt", handler)
        bus.unsubscribe("evt", handler)
        bus.publish("evt")
        self.assert_equal(calls, [])

    def _test_subscriber_exception_isolated(self) -> None:
        bus = EventBus()
        calls = []

        def bad_handler():
            raise RuntimeError("boom")

        def good_handler():
            calls.append("good")

        bus.subscribe("evt", bad_handler)
        bus.subscribe("evt", good_handler)
        # Must not raise, and the second handler must still run.
        bus.publish("evt")
        self.assert_equal(calls, ["good"])

    def _test_publish_with_no_subscribers_is_noop(self) -> None:
        bus = EventBus()
        # Must not raise.
        bus.publish("nobody.listening", value=1)
        self.assert_equal(bus.event_names, [])

    def _test_event_names_reflects_subscriptions(self) -> None:
        bus = EventBus()
        bus.subscribe("a", lambda: None)
        bus.subscribe("b", lambda: None)
        self.assert_equal(sorted(bus.event_names), ["a", "b"])
        # publish()/unsubscribe() on an unknown event must never
        # spuriously add it to event_names.
        bus.publish("c")
        bus.unsubscribe("d", lambda: None)
        self.assert_equal(sorted(bus.event_names), ["a", "b"])

    def _test_subscribe_rejects_empty_name(self) -> None:
        bus = EventBus()
        try:
            bus.subscribe("", lambda: None)
            self.assert_true(False, "subscribe('') should have raised ValueError")
        except ValueError:
            self.result.add_pass()

    def _test_subscribe_rejects_non_callable(self) -> None:
        bus = EventBus()
        try:
            bus.subscribe("evt", "not callable")  # type: ignore[arg-type]
            self.assert_true(False, "subscribe(non-callable) should have raised TypeError")
        except TypeError:
            self.result.add_pass()

    # ---------- EventBus: thread safety ----------

    def _test_concurrent_publish_from_multiple_threads(self) -> None:
        bus = EventBus()
        lock = threading.Lock()
        received: list[int] = []

        def handler(n: int) -> None:
            with lock:
                received.append(n)

        bus.subscribe("evt", handler)

        def publisher(n: int) -> None:
            bus.publish("evt", n=n)

        threads = [threading.Thread(target=publisher, args=(i,)) for i in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5.0)

        self.assert_true(all(not t.is_alive() for t in threads))
        self.assert_equal(sorted(received), list(range(50)))

    def _test_concurrent_subscribe_unsubscribe_during_publish(self) -> None:
        bus = EventBus()
        stop = threading.Event()
        errors: list[Exception] = []

        def churn() -> None:
            def h():
                return None

            while not stop.is_set():
                try:
                    bus.subscribe("evt", h)
                    bus.unsubscribe("evt", h)
                except Exception as exc:  # noqa: BLE001
                    errors.append(exc)

        def publish_loop() -> None:
            while not stop.is_set():
                try:
                    bus.publish("evt")
                except Exception as exc:  # noqa: BLE001
                    errors.append(exc)

        threads = [threading.Thread(target=churn), threading.Thread(target=publish_loop)]
        for t in threads:
            t.start()
        time.sleep(0.2)
        stop.set()
        for t in threads:
            t.join(timeout=5.0)

        self.assert_equal(errors, [])
        self.assert_true(all(not t.is_alive() for t in threads))

    def _test_handler_self_unsubscribe_during_publish(self) -> None:
        bus = EventBus()
        calls = []
        handler_holder: list = []

        def self_removing_handler():
            calls.append("ran")
            bus.unsubscribe("evt", handler_holder[0])

        handler_holder.append(self_removing_handler)
        bus.subscribe("evt", self_removing_handler)
        bus.subscribe("evt", lambda: calls.append("other"))

        # First publish: both handlers were subscribed at publish-time
        # (snapshot semantics), so both must still run once.
        bus.publish("evt")
        self.assert_equal(calls, ["ran", "other"])

        # Second publish: self_removing_handler unsubscribed itself
        # during the first publish, so only "other" fires now.
        calls.clear()
        bus.publish("evt")
        self.assert_equal(calls, ["other"])

    def _test_handler_subscribe_during_publish_no_deadlock(self) -> None:
        bus = EventBus()
        calls = []

        def handler_that_subscribes():
            calls.append("first")
            # Must not deadlock: publish() never holds the lock while
            # invoking a handler.
            bus.subscribe("evt2", lambda: calls.append("second"))

        bus.subscribe("evt", handler_that_subscribes)

        done = threading.Event()

        def run_publish():
            bus.publish("evt")
            done.set()

        t = threading.Thread(target=run_publish)
        t.start()
        finished = done.wait(timeout=5.0)
        t.join(timeout=5.0)

        self.assert_true(finished, "publish() deadlocked when a handler subscribed during dispatch")
        self.assert_equal(calls, ["first"])
        self.assert_true("evt2" in bus.event_names)

    # ---------- EP-033/034 publish "workflow.completed" ----------

    def _test_workflow_engine_service_publishes_workflow_completed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine, manager, _ = _build_workflow_engine(Path(tmp))
            _register_workflow(manager, "wf-a", "do-a")
            bus = EventBus()
            received = []
            bus.subscribe(
                "workflow.completed",
                lambda **kw: received.append(kw),
            )
            service = WorkflowEngineService(manager=manager, engine=engine, event_bus=bus)
            outcome = service.run("wf-a")

            self.assert_true(outcome.success)
            self.assert_equal(len(received), 1)
            self.assert_equal(received[0]["definition_id"], "wf-a")
            self.assert_true(received[0]["result"] is outcome.result)

    def _test_workflow_engine_service_no_publish_without_event_bus(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine, manager, _ = _build_workflow_engine(Path(tmp))
            _register_workflow(manager, "wf-b", "do-b")
            # Default event_bus=None must reproduce pre-EP-037 behavior exactly.
            service = WorkflowEngineService(manager=manager, engine=engine)
            outcome = service.run("wf-b")
            self.assert_true(outcome.success)

    def _test_workflow_scheduler_engine_publishes_workflow_completed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine, manager, _ = _build_workflow_engine(Path(tmp))
            _register_workflow(manager, "wf-c", "do-c")
            bus = EventBus()
            received = []
            bus.subscribe("workflow.completed", lambda **kw: received.append(kw))

            scheduler_engine = WorkflowSchedulerEngine(
                registry=ScheduledWorkflowRegistry(), workflow_engine=engine, event_bus=bus
            )
            scheduler_engine.register_entry(
                ScheduledWorkflow(
                    id="entry-c",
                    name="entry-c",
                    description="",
                    workflow_id="wf-c",
                    schedule=Schedule(type=ScheduleType.MANUAL),
                )
            )
            entry = scheduler_engine.run_now("entry-c")

            self.assert_true(entry.last_run is not None)
            self.assert_equal(len(received), 1)
            self.assert_equal(received[0]["definition_id"], "wf-c")

    # ---------- EP-036 publish background_worker.* ----------

    def _test_background_worker_pool_publishes_task_completed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine, manager, _ = _build_workflow_engine(Path(tmp))
            _register_workflow(manager, "bg-ok", "do-bg-ok")
            bus = EventBus()
            received = []
            bus.subscribe("background_worker.task_completed", lambda **kw: received.append(kw))
            bus.subscribe("background_worker.task_failed", lambda **kw: received.append(kw))

            pool = BackgroundWorkerPool(workflow_engine=engine, worker_count=1, event_bus=bus)
            try:
                task_id = pool.submit("bg-ok")
                ok = _wait_until(lambda: pool.get_task(task_id).status != TaskStatus.PENDING)
                ok = ok and _wait_until(
                    lambda: pool.get_task(task_id).status
                    in (TaskStatus.COMPLETED, TaskStatus.FAILED)
                )
                self.assert_true(ok, "task never reached a final status")
                self.assert_equal(pool.get_task(task_id).status, TaskStatus.COMPLETED)
                self.assert_equal(len(received), 1)
                self.assert_equal(received[0]["task_id"], task_id)
                self.assert_equal(received[0]["workflow_id"], "bg-ok")
                self.assert_true(received[0]["result"] is not None)
            finally:
                pool.shutdown(timeout=5.0)

    def _test_background_worker_pool_publishes_task_failed_on_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine, manager, _ = _build_workflow_engine(
                Path(tmp), failing_requests=frozenset({"do-bg-fail"})
            )
            _register_workflow(manager, "bg-fail", "do-bg-fail")
            bus = EventBus()
            received = []
            bus.subscribe("background_worker.task_failed", lambda **kw: received.append(kw))
            bus.subscribe("background_worker.task_completed", lambda **kw: received.append(kw))

            pool = BackgroundWorkerPool(workflow_engine=engine, worker_count=1, event_bus=bus)
            try:
                task_id = pool.submit("bg-fail")
                ok = _wait_until(
                    lambda: pool.get_task(task_id).status
                    in (TaskStatus.COMPLETED, TaskStatus.FAILED)
                )
                self.assert_true(ok, "task never reached a final status")
                self.assert_equal(pool.get_task(task_id).status, TaskStatus.FAILED)
                self.assert_equal(len(received), 1)
                self.assert_equal(received[0]["task_id"], task_id)
                self.assert_true(received[0]["error"])
            finally:
                pool.shutdown(timeout=5.0)

    def _test_background_worker_pool_publishes_task_failed_on_exception(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:

            class _RaisingWorkflowEngine:
                def run(self, workflow_id: str):
                    raise RuntimeError("provider defect")

            bus = EventBus()
            received = []
            bus.subscribe("background_worker.task_failed", lambda **kw: received.append(kw))

            pool = BackgroundWorkerPool(
                workflow_engine=_RaisingWorkflowEngine(), worker_count=1, event_bus=bus
            )
            try:
                task_id = pool.submit("whatever")
                ok = _wait_until(lambda: pool.get_task(task_id).status == TaskStatus.FAILED)
                self.assert_true(ok, "task never reached FAILED")
                self.assert_equal(len(received), 1)
                self.assert_equal(received[0]["task_id"], task_id)
            finally:
                pool.shutdown(timeout=5.0)

    def _test_background_worker_pool_task_state_unaffected_by_event_bus(self) -> None:
        """Regression: task status/result with event_bus wired matches without it."""
        with tempfile.TemporaryDirectory() as tmp:
            engine_a, manager_a, _ = _build_workflow_engine(Path(tmp))
            _register_workflow(manager_a, "bg-parity", "do-parity")
            pool_no_bus = BackgroundWorkerPool(workflow_engine=engine_a, worker_count=1)

            engine_b, manager_b, _ = _build_workflow_engine(Path(tmp))
            _register_workflow(manager_b, "bg-parity", "do-parity")
            pool_with_bus = BackgroundWorkerPool(
                workflow_engine=engine_b, worker_count=1, event_bus=EventBus()
            )
            try:
                id_a = pool_no_bus.submit("bg-parity")
                id_b = pool_with_bus.submit("bg-parity")
                self.assert_true(_wait_until(lambda: pool_no_bus.get_task(id_a).status == TaskStatus.COMPLETED))
                self.assert_true(_wait_until(lambda: pool_with_bus.get_task(id_b).status == TaskStatus.COMPLETED))
                self.assert_equal(
                    pool_no_bus.get_task(id_a).result.success,
                    pool_with_bus.get_task(id_b).result.success,
                )
            finally:
                pool_no_bus.shutdown(timeout=5.0)
                pool_with_bus.shutdown(timeout=5.0)

    # ---------- Hook vs event migration: exactly-once guarantee ----------

    def _test_on_demand_run_triggers_automation_exactly_once_via_event(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine, manager, stub = _build_workflow_engine(Path(tmp))
            _register_workflow(manager, "trig-1", "trigger-req-1")
            _register_workflow(manager, "act-1", "action-req-1")

            bus = EventBus()
            registry = AutomationRuleRegistry()
            automation_engine = AutomationEngine(registry=registry, workflow_engine=engine)
            registry.register(_automation_rule("r1", "trig-1", "act-1"))

            call_count = []

            def counting_notify_run(**kwargs):
                call_count.append(1)
                return automation_engine.notify_run(**kwargs)

            bus.subscribe("workflow.completed", counting_notify_run)

            # Production-shaped wiring: event_bus given, set_automation_hook() NEVER called.
            service = WorkflowEngineService(manager=manager, engine=engine, event_bus=bus)
            outcome = service.run("trig-1")

            self.assert_true(outcome.success)
            self.assert_equal(len(call_count), 1, "notify_run must be triggered exactly once")
            self.assert_equal(
                stub.calls.count("action-req-1"),
                1,
                "the action workflow must run exactly once, not twice",
            )
            rule = registry.get("r1")
            self.assert_true(rule.last_triggered is not None)

    def _test_scheduled_run_triggers_automation_exactly_once_via_event(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine, manager, stub = _build_workflow_engine(Path(tmp))
            _register_workflow(manager, "trig-2", "trigger-req-2")
            _register_workflow(manager, "act-2", "action-req-2")

            bus = EventBus()
            registry = AutomationRuleRegistry()
            automation_engine = AutomationEngine(registry=registry, workflow_engine=engine)
            registry.register(_automation_rule("r2", "trig-2", "act-2"))

            call_count = []

            def counting_notify_run(**kwargs):
                call_count.append(1)
                return automation_engine.notify_run(**kwargs)

            bus.subscribe("workflow.completed", counting_notify_run)

            scheduler_engine = WorkflowSchedulerEngine(
                registry=ScheduledWorkflowRegistry(), workflow_engine=engine, event_bus=bus
            )
            scheduler_engine.register_entry(
                ScheduledWorkflow(
                    id="entry-2",
                    name="entry-2",
                    description="",
                    workflow_id="trig-2",
                    schedule=Schedule(type=ScheduleType.MANUAL),
                )
            )
            scheduler_engine.run_now("entry-2")

            self.assert_equal(len(call_count), 1, "notify_run must be triggered exactly once")
            self.assert_equal(stub.calls.count("action-req-2"), 1)

    def _test_set_automation_hook_still_works_directly(self) -> None:
        """Backward compatibility: the hook API itself is untouched and still functions."""
        with tempfile.TemporaryDirectory() as tmp:
            engine, manager, stub = _build_workflow_engine(Path(tmp))
            _register_workflow(manager, "trig-3", "trigger-req-3")
            _register_workflow(manager, "act-3", "action-req-3")

            registry = AutomationRuleRegistry()
            automation_engine = AutomationEngine(registry=registry, workflow_engine=engine)
            registry.register(_automation_rule("r3", "trig-3", "act-3"))

            service = WorkflowEngineService(manager=manager, engine=engine)  # no event_bus
            service.set_automation_hook(automation_engine.notify_run)
            outcome = service.run("trig-3")

            self.assert_true(outcome.success)
            self.assert_equal(stub.calls.count("action-req-3"), 1)

    def _test_hook_and_event_together_would_double_fire_if_both_wired(self) -> None:
        """Documents exactly why Bootstrap must use only one path, not both.

        This deliberately wires BOTH the hook and the event subscription
        to the same notify_run target (the misconfiguration Bootstrap
        must avoid) and confirms the action workflow does run twice --
        proving the exactly-once tests above are actually meaningful,
        not vacuously true.
        """
        with tempfile.TemporaryDirectory() as tmp:
            engine, manager, stub = _build_workflow_engine(Path(tmp))
            _register_workflow(manager, "trig-4", "trigger-req-4")
            _register_workflow(manager, "act-4", "action-req-4")

            bus = EventBus()
            registry = AutomationRuleRegistry()
            automation_engine = AutomationEngine(registry=registry, workflow_engine=engine)
            registry.register(_automation_rule("r4", "trig-4", "act-4"))

            bus.subscribe("workflow.completed", automation_engine.notify_run)
            service = WorkflowEngineService(manager=manager, engine=engine, event_bus=bus)
            service.set_automation_hook(automation_engine.notify_run)  # the misconfiguration

            service.run("trig-4")

            self.assert_equal(
                stub.calls.count("action-req-4"),
                2,
                "wiring both hook and event to the same target double-fires by design "
                "-- this is exactly what Bootstrap's migration avoids",
            )

    # ---------- Bootstrap: production wiring uses the event, not the hook ----------

    def _test_bootstrap_on_demand_run_triggers_automation_via_event(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(directory)
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.initialize()
                self.assert_true(bootstrap.workflow_engine_service is not None)
                self.assert_true(bootstrap.automation_service is not None)

                engine_service = bootstrap.workflow_engine_service
                automation_service = bootstrap.automation_service

                trigger = WorkflowDefinition(
                    id="ep037-trigger",
                    name="ep037-trigger",
                    description="",
                    enabled=True,
                    steps=(WorkflowRequestStep(name="Step", request="noop"),),
                )
                action = WorkflowDefinition(
                    id="ep037-action",
                    name="ep037-action",
                    description="",
                    enabled=True,
                    steps=(WorkflowRequestStep(name="Step", request="noop"),),
                )
                engine_service._manager.registry.register(trigger)  # noqa: SLF001
                engine_service._manager.registry.register(action)  # noqa: SLF001

                rule_result = automation_service.register(
                    _automation_rule("ep037-rule", "ep037-trigger", "ep037-action")
                )
                self.assert_true(rule_result.success)

                outcome = engine_service.run("ep037-trigger")
                self.assert_true(outcome.success)

                rule = automation_service.get_rule("ep037-rule")
                self.assert_true(rule.last_triggered is not None)
                self.assert_true(rule.last_action_success)

    def _test_bootstrap_production_wiring_does_not_use_hook(self) -> None:
        """The EP-037 migration: Bootstrap no longer calls set_automation_hook()."""
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(directory)
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.initialize()
                self.assert_true(bootstrap.workflow_engine_service is not None)
                self.assert_true(bootstrap.workflow_scheduler_service is not None)

                # noqa: SLF001 -- verifying internal wiring state is the point of this test.
                engine_service = bootstrap.workflow_engine_service
                self.assert_true(
                    engine_service._automation_hook is None,  # noqa: SLF001
                    "Bootstrap must not wire set_automation_hook() for production automation",
                )
                self.assert_true(
                    engine_service._event_bus is not None,  # noqa: SLF001
                    "Bootstrap must wire an EventBus into WorkflowEngineService",
                )
                self.assert_true("workflow.completed" in bootstrap.event_bus.event_names)

    def _test_bootstrap_disabled_automation_never_fires(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(directory, automation_enabled=False)
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.initialize()
                self.assert_true(bootstrap.automation_service is not None)
                self.assert_false(bootstrap.automation_service.status().enabled)
                self.assert_true("workflow.completed" not in bootstrap.event_bus.event_names)

                engine_service = bootstrap.workflow_engine_service
                trigger = WorkflowDefinition(
                    id="ep037-off-trigger",
                    name="ep037-off-trigger",
                    description="",
                    enabled=True,
                    steps=(WorkflowRequestStep(name="Step", request="noop"),),
                )
                engine_service._manager.registry.register(trigger)  # noqa: SLF001
                outcome = engine_service.run("ep037-off-trigger")
                self.assert_true(outcome.success)

    # ---------- STEP 3: background-worker completion -> automation adapter ----------

    @staticmethod
    def _subscribe_background_worker_completion_adapter(
        bus: EventBus, automation_engine: AutomationEngine
    ) -> None:
        """Local copy of Bootstrap's small STEP 3 adapter, for isolated testing.

        Mirrors exactly what src/bootstrap.py wires: re-keys
        `background_worker.task_completed`'s existing `workflow_id` kwarg
        to the `definition_id` kwarg `notify_run()` expects. Never
        subscribed to `background_worker.task_failed`.
        """

        def _on_background_worker_task_completed(**kwargs) -> None:
            automation_engine.notify_run(definition_id=kwargs["workflow_id"], result=kwargs["result"])

        bus.subscribe("background_worker.task_completed", _on_background_worker_task_completed)

    def _test_background_worker_completion_adapter_triggers_automation_exactly_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine, manager, stub = _build_workflow_engine(Path(tmp))
            _register_workflow(manager, "bg-trig-1", "bg-trigger-req-1")
            _register_workflow(manager, "bg-act-1", "bg-action-req-1")

            bus = EventBus()
            registry = AutomationRuleRegistry()
            automation_engine = AutomationEngine(registry=registry, workflow_engine=engine)
            registry.register(_automation_rule("bgr1", "bg-trig-1", "bg-act-1"))
            self._subscribe_background_worker_completion_adapter(bus, automation_engine)

            pool = BackgroundWorkerPool(workflow_engine=engine, worker_count=1, event_bus=bus)
            try:
                task_id = pool.submit("bg-trig-1")
                ok = _wait_until(lambda: pool.get_task(task_id).status == TaskStatus.COMPLETED)
                self.assert_true(ok, "background task never completed")
                self.assert_equal(
                    stub.calls.count("bg-action-req-1"),
                    1,
                    "a background task completion must trigger automation exactly once",
                )
                rule = registry.get("bgr1")
                self.assert_true(rule.last_triggered is not None)
                self.assert_true(rule.last_action_success)
            finally:
                pool.shutdown(timeout=5.0)

    def _test_background_worker_task_failed_never_triggers_automation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine, manager, stub = _build_workflow_engine(
                Path(tmp), failing_requests=frozenset({"bg-trigger-req-2"})
            )
            _register_workflow(manager, "bg-trig-2", "bg-trigger-req-2")
            _register_workflow(manager, "bg-act-2", "bg-action-req-2")

            bus = EventBus()
            registry = AutomationRuleRegistry()
            automation_engine = AutomationEngine(registry=registry, workflow_engine=engine)
            registry.register(_automation_rule("bgr2", "bg-trig-2", "bg-act-2"))
            self._subscribe_background_worker_completion_adapter(bus, automation_engine)

            pool = BackgroundWorkerPool(workflow_engine=engine, worker_count=1, event_bus=bus)
            try:
                task_id = pool.submit("bg-trig-2")
                ok = _wait_until(lambda: pool.get_task(task_id).status == TaskStatus.FAILED)
                self.assert_true(ok, "background task never reached FAILED")
                self.assert_equal(
                    stub.calls.count("bg-action-req-2"),
                    0,
                    "task_failed must never trigger automation (no adapter subscribed to it)",
                )
                rule = registry.get("bgr2")
                self.assert_true(rule.last_triggered is None)
            finally:
                pool.shutdown(timeout=5.0)

    def _test_background_worker_and_workflow_completed_do_not_double_fire(self) -> None:
        """Both subscriptions co-present (real Bootstrap shape); a background-only
        completion must still fire the action exactly once, since Pool never
        publishes "workflow.completed" itself."""
        with tempfile.TemporaryDirectory() as tmp:
            engine, manager, stub = _build_workflow_engine(Path(tmp))
            _register_workflow(manager, "bg-trig-3", "bg-trigger-req-3")
            _register_workflow(manager, "bg-act-3", "bg-action-req-3")

            bus = EventBus()
            registry = AutomationRuleRegistry()
            automation_engine = AutomationEngine(registry=registry, workflow_engine=engine)
            registry.register(_automation_rule("bgr3", "bg-trig-3", "bg-act-3"))

            # Both production subscriptions present at once, exactly like Bootstrap.
            bus.subscribe("workflow.completed", automation_engine.notify_run)
            self._subscribe_background_worker_completion_adapter(bus, automation_engine)

            pool = BackgroundWorkerPool(workflow_engine=engine, worker_count=1, event_bus=bus)
            try:
                task_id = pool.submit("bg-trig-3")
                ok = _wait_until(lambda: pool.get_task(task_id).status == TaskStatus.COMPLETED)
                self.assert_true(ok, "background task never completed")
                self.assert_equal(
                    stub.calls.count("bg-action-req-3"),
                    1,
                    "a background-only completion must not double-fire even with both "
                    "subscriptions present",
                )
            finally:
                pool.shutdown(timeout=5.0)

    def _test_background_worker_pool_and_service_api_unchanged(self) -> None:
        """Regression: BackgroundWorkerPool/Service public API is untouched by STEP 3."""
        with tempfile.TemporaryDirectory() as tmp:
            engine, manager, _ = _build_workflow_engine(Path(tmp))
            _register_workflow(manager, "bg-api", "bg-api-req")
            # No event_bus at all -- exact pre-EP-037 call shape must still work.
            pool = BackgroundWorkerPool(workflow_engine=engine, worker_count=1)
            try:
                task_id = pool.submit("bg-api")
                self.assert_true(_wait_until(lambda: pool.get_task(task_id).status == TaskStatus.COMPLETED))
                self.assert_true(task_id in [t.id for t in pool.list_tasks()])
            finally:
                pool.shutdown(timeout=5.0)

            config = _write_config(Path(tmp), "background_workers:\n  enabled: true\n  worker_count: 1\n")
            service = BackgroundWorkerService(config=config, workflow_engine=engine)
            status = service.status()
            self.assert_true(status.enabled)
            service.shutdown()

    def _test_bootstrap_background_worker_completion_triggers_automation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(directory)
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.initialize()
                self.assert_true(bootstrap.background_worker_service is not None)
                self.assert_true(bootstrap.automation_service is not None)

                engine_service = bootstrap.workflow_engine_service
                trigger = WorkflowDefinition(
                    id="ep037-bg-trigger",
                    name="ep037-bg-trigger",
                    description="",
                    enabled=True,
                    steps=(WorkflowRequestStep(name="Step", request="noop"),),
                )
                action = WorkflowDefinition(
                    id="ep037-bg-action",
                    name="ep037-bg-action",
                    description="",
                    enabled=True,
                    steps=(WorkflowRequestStep(name="Step", request="noop"),),
                )
                engine_service._manager.registry.register(trigger)  # noqa: SLF001
                engine_service._manager.registry.register(action)  # noqa: SLF001

                rule_result = bootstrap.automation_service.register(
                    _automation_rule("ep037-bg-rule", "ep037-bg-trigger", "ep037-bg-action")
                )
                self.assert_true(rule_result.success)

                task_id = bootstrap.background_worker_service.submit("ep037-bg-trigger")
                ok = _wait_until(
                    lambda: bootstrap.background_worker_service.get_task(task_id).status
                    == TaskStatus.COMPLETED,
                    timeout=10.0,
                )
                self.assert_true(ok, "bootstrap-dispatched background task never completed")

                rule = bootstrap.automation_service.get_rule("ep037-bg-rule")
                self.assert_true(rule.last_triggered is not None)
                self.assert_true(rule.last_action_success)

                bootstrap.background_worker_service.shutdown(timeout=5.0)

    def _test_bootstrap_disabled_automation_also_skips_background_worker_adapter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(directory, automation_enabled=False)
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.initialize()
                self.assert_true(bootstrap.background_worker_service is not None)
                self.assert_true(
                    "background_worker.task_completed" not in bootstrap.event_bus.event_names,
                    "the STEP 3 adapter must not be subscribed when automation is disabled",
                )
                bootstrap.background_worker_service.shutdown(timeout=5.0)
