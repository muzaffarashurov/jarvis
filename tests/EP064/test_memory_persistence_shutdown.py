"""EP-064 test suite: MemoryPersistence.shutdown() and its wiring.

Covers, per `EP064_DESIGN.md` Section 12:
    1. `MemoryPersistence.shutdown()` in isolation.
    2. `MemoryService.shutdown()`/`MemoryStatus.auto_save_running`.
    3. `RuntimeService.shutdown()`'s widened (REST -> Scheduler ->
       Workflow Scheduler -> Memory Persistence -> Background Workers)
       behavior.
    4. Real `Bootstrap` end-to-end wiring, including final-save
       compatibility with `main.py`'s post-shutdown explicit save.
    5. Public-surface guards (`MemoryPersistence`, `MemoryService`,
       `MemoryModule`, `RuntimeModule`).

Self-contained per this repository's own per-EP test convention (no
import from `tests/EP061/`, `tests/EP062/`, or `tests/EP063/`) -- local
builder functions below are deliberately near-identical to (but
independent copies of) the ones those suites already use for the same
kind of real objects.
"""

from __future__ import annotations

import inspect
import os
import tempfile
import threading
import time
import types
from pathlib import Path

from src.bootstrap import Bootstrap
from src.core.config import Config
from src.core.memory.memory_persistence import MemoryPersistence
from src.core.memory.memory_store import MemoryStore
from src.modules.memory_module import MemoryModule
from src.modules.runtime_module import RuntimeModule
from src.services.memory_service import MemoryService, MemoryStatus
from src.services.runtime_service import RuntimeService, RuntimeShutdownReport
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


def _write_config(directory: Path, memory_settings: str) -> Config:
    """Write a minimal, self-contained config.yaml and load it.

    Only 'memory.*' keys are set; every other key resolves to its own
    built-in default via `Config.get`'s `default` argument, exactly as
    it would for an operator who never configured it (matches
    `tests/EP023/test_memory_manager.py`'s own `_write_config` shape).
    """
    config_path = directory / "config.yaml"
    config_path.write_text(memory_settings, encoding="utf-8")
    return Config(config_path).load()


def _memory_config_yaml(
    enabled: bool = True,
    persistent: bool = True,
    auto_save: bool = True,
    auto_save_interval: float = 3600,
) -> str:
    """Build a minimal 'memory.*'-only config.yaml body.

    `auto_save_interval` defaults to a large value (3600s) so no
    auto-save tick ever actually fires during a test unless a test
    explicitly overrides it to exercise the loop's `save()` path.
    """
    return (
        "memory:\n"
        f"  enabled: {str(enabled).lower()}\n"
        f"  persistent: {str(persistent).lower()}\n"
        f"  auto_save: {str(auto_save).lower()}\n"
        f"  auto_save_interval: {auto_save_interval}\n"
        '  default_provider: "memory"\n'
    )


def _build_real_memory_persistence(
    tmp_path: Path,
    persistent: bool = True,
    auto_save: bool = True,
    auto_save_interval: float = 3600,
) -> MemoryPersistence:
    """Build a real, minimal MemoryPersistence (does not start it)."""
    config = _write_config(
        tmp_path,
        _memory_config_yaml(
            persistent=persistent, auto_save=auto_save, auto_save_interval=auto_save_interval
        ),
    )
    store = MemoryStore()
    return MemoryPersistence(config=config, store=store)


def _build_real_memory_service(
    tmp_path: Path,
    enabled: bool = True,
    persistent: bool = True,
    auto_save: bool = True,
    auto_save_interval: float = 3600,
) -> MemoryService:
    """Build a real, minimal, enabled MemoryService (auto-starts per config)."""
    config = _write_config(
        tmp_path,
        _memory_config_yaml(
            enabled=enabled,
            persistent=persistent,
            auto_save=auto_save,
            auto_save_interval=auto_save_interval,
        ),
    )
    store = MemoryStore()
    return MemoryService(config=config, store=store)


class _SlowSaveMemoryPersistence(MemoryPersistence):
    """A MemoryPersistence whose `save()` blocks until released.

    Used to deterministically exercise `shutdown()`'s `timeout`
    argument against a controlled blocking operation, rather than an
    arbitrary sleep or a flaky timing assumption -- the auto-save
    loop's own `save()` call is what `shutdown()`'s join races
    against, so this subclass intercepts exactly that call.
    """

    def __init__(self, config: Config, store: MemoryStore) -> None:
        super().__init__(config=config, store=store)
        self.save_started = threading.Event()
        self.release_save = threading.Event()

    def save(self) -> tuple[bool, str]:
        self.save_started.set()
        self.release_save.wait()
        return super().save()


class _OrderRecordingRest:
    """Minimal duck-typed fake matching the surface `RuntimeService`
    reads/calls for the REST API Server (`is_running`, `host`, `port`,
    `stop()`), recording call order deterministically."""

    def __init__(self, order_log: list[str]) -> None:
        self._log = order_log
        self._running = True

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def host(self) -> str:
        return "127.0.0.1"

    @property
    def port(self) -> int:
        return 0

    def stop(self) -> None:
        self._log.append("rest_api")
        self._running = False


class _OrderRecordingSubsystem:
    """Minimal duck-typed fake matching the `status()`/`shutdown()`
    surface `RuntimeService` reads/calls for Scheduler, Workflow
    Scheduler, Memory Persistence (via `MemoryService`), and
    Background Worker Service, recording call order deterministically.

    `running_attr` selects which attribute name `status()`'s return
    object exposes: "running" for Scheduler/Workflow Scheduler/
    Background Workers, "auto_save_running" for Memory -- matching
    exactly what `RuntimeService.shutdown()` reads for each subsystem.
    """

    def __init__(self, name: str, order_log: list[str], running_attr: str = "running") -> None:
        self._name = name
        self._log = order_log
        self._running_attr = running_attr
        self._running = True

    def status(self) -> types.SimpleNamespace:
        return types.SimpleNamespace(**{self._running_attr: self._running})

    def shutdown(self, wait: bool = True, timeout: float | None = None) -> bool:
        self._log.append(self._name)
        self._running = False
        return True


_FULL_BOOTSTRAP_CONFIG_YAML = (
    "app:\n"
    '  name: "JARVIS-TEST"\n'
    '  tagline: "Test"\n'
    '  version: "0.0.0-test"\n\n'
    "logging:\n"
    '  level: "INFO"\n'
    "  retention_days: 1\n"
    "  console_enabled: false\n\n"
    "paths:\n"
    '  logs: "logs"\n'
    '  data_input: "data/input"\n'
    '  data_output: "data/output"\n'
    '  data_cache: "data/cache"\n'
    '  data_database: "data/database"\n'
    '  knowledge: "knowledge"\n'
    '  prompts: "prompts"\n\n'
    "{memory_section}"
    "knowledge:\n"
    "  enabled: true\n"
    '  default_provider: "local"\n\n'
    "long_term_memory:\n"
    "  enabled: true\n"
    '  default_provider: "knowledge"\n\n'
    "orchestrator:\n"
    "  skills_enabled: []\n\n"
    "invoice:\n"
    '  script: ""\n\n'
    "fast_response:\n"
    '  workbook: ""\n'
    '  worksheet: ""\n'
    '  backup_folder: ""\n\n'
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
    "  tick_interval: 3600\n\n"
    "plugins:\n"
    "  enabled: true\n"
    "  auto_load: false\n"
    "  auto_discovery: false\n"
    '  plugin_directory: "plugins"\n\n'
    "telegram:\n"
    "  enabled: false\n"
    "  auto_start: false\n"
    '  token: ""\n'
    "  allowed_chat_ids: []\n"
    "  polling_interval: 2\n\n"
    "ai:\n"
    "  enabled: true\n"
    '  default_provider: "none"\n'
    "  timeout: 120\n"
    "  retry_count: 2\n"
    "  max_context_messages: 20\n\n"
    "conversation:\n"
    "  enabled: true\n"
    "  auto_save: false\n"
    "  max_messages: 100\n"
    "  max_conversations: 100\n"
    '  storage_file: "data/database/conversations.json"\n'
    '  truncate_strategy: "oldest"\n\n'
    "prompt:\n"
    "  enabled: true\n"
    '  system_prompt: ""\n'
    "  append_datetime: false\n"
    "  append_provider_name: false\n"
    "  append_os_information: false\n"
    "  append_working_directory: false\n"
    "  max_prompt_size: 32000\n"
    "  reserved_system_prompt: 2000\n"
    "  reserved_conversation_history: 8000\n"
    "  reserved_user_prompt: 2000\n"
    "  reserved_provider_overhead: 1000\n\n"
    "context:\n"
    "  enabled: true\n"
    "  auto_load: true\n"
    "  include_environment: false\n"
    "  include_working_directory: false\n"
    "  include_project_files: false\n"
    "  smart_selection: true\n\n"
    "indexing:\n"
    '  storage_backend: "memory"\n'
    '  storage_file: "data/database/project_index.json"\n\n'
    "providers:\n"
    "  claude:\n"
    "    enabled: false\n"
    '    api_key: ""\n'
    "  openai:\n"
    "    enabled: false\n"
    '    api_key: ""\n'
    "  gemini:\n"
    "    enabled: false\n"
    '    api_key: ""\n'
    "  ollama:\n"
    "    enabled: false\n"
    '    endpoint: ""\n'
    "  lmstudio:\n"
    "    enabled: false\n"
    '    endpoint: ""\n\n'
    "embedding:\n"
    "  enabled: true\n"
    '  default_provider: "local"\n'
    "  batch_size: 16\n"
    "  providers:\n"
    "    local:\n"
    "      enabled: true\n"
    '      model: "local-hash-v1"\n'
    "      dimension: 16\n"
    "    cloud:\n"
    "      enabled: false\n"
    '      api_key: ""\n'
    '      model: "text-embedding-cloud-v1"\n'
    "      dimension: 1536\n\n"
    "rag:\n"
    "  enabled: true\n"
    "  top_k: 5\n"
    "  max_context_characters: 4000\n\n"
    "semantic:\n"
    "  enabled: true\n"
    '  default_provider: "semantic"\n'
    "  top_k: 5\n"
    "  similarity_threshold: 0.0\n\n"
    "context_compression:\n"
    "  enabled: true\n"
    '  default_provider: "compression"\n'
    "  max_context_characters: 12000\n"
    "  max_chunks: 20\n"
    "  deduplicate: true\n\n"
    "agent:\n"
    "  enabled: true\n"
    '  default_agent: "jarvis"\n'
    '  startup_mode: "idle"\n\n'
    "planning:\n"
    "  enabled: true\n"
    '  default_provider: "planning"\n'
    "  max_steps: 10\n\n"
    "plan_execution:\n"
    "  enabled: true\n"
    '  default_provider: "plan_execution"\n'
    "  stop_on_failure: true\n\n"
    "tool:\n"
    "  enabled: true\n"
    '  default_provider: "tool_engine"\n\n'
    "collaboration:\n"
    "  enabled: true\n"
    '  default_provider: "collaboration"\n\n'
    "workflow_engine:\n"
    "  enabled: true\n"
    '  default_provider: "workflow_engine"\n'
    "  stop_on_failure: true\n\n"
    "workflow_scheduler:\n"
    "  enabled: true\n"
    "  auto_start: false\n"
    "  tick_interval: 5\n\n"
    "automation:\n"
    "  enabled: true\n\n"
    "git:\n"
    "  enabled: false\n\n"
    "github:\n"
    "  enabled: false\n\n"
    "telegram_info:\n"
    "  enabled: false\n\n"
    "discord:\n"
    "  enabled: false\n\n"
    "email:\n"
    "  enabled: false\n\n"
    "api:\n"
    "  enabled: false\n"
    '  host: "127.0.0.1"\n'
    "  port: 0\n"
)


def _write_full_bootstrap_config(
    directory: Path,
    memory_section: str = (
        "memory:\n"
        "  enabled: true\n"
        "  persistent: false\n"
        "  auto_save: false\n"
        "  max_entries: 10000\n"
        "  default_ttl: null\n"
        '  default_provider: "memory"\n\n'
    ),
) -> None:
    """Write config/config.yaml (a full, offline-safe config) under `directory`."""
    config_dir = directory / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "config.yaml").write_text(
        _FULL_BOOTSTRAP_CONFIG_YAML.format(memory_section=memory_section),
        encoding="utf-8",
    )


_MEMORY_AUTO_SAVE_SECTION = (
    "memory:\n"
    "  enabled: true\n"
    "  persistent: true\n"
    "  auto_save: true\n"
    "  auto_save_interval: 3600\n"
    "  max_entries: 10000\n"
    "  default_ttl: null\n"
    '  default_provider: "memory"\n\n'
)


@TestRegistry.register
class MemoryPersistenceShutdownTest(BaseTest):
    NAME = "EP064"

    def run(self):
        # ---------- MemoryPersistence.shutdown() in isolation ----------
        self._test_shutdown_never_started_returns_true_immediately()
        self._test_shutdown_when_not_persistent_returns_true_immediately()
        self._test_shutdown_when_auto_save_disabled_returns_true_immediately()
        self._test_auto_save_loop_starts_when_persistent_and_auto_save_enabled()
        self._test_shutdown_stops_a_running_auto_save_loop()
        self._test_shutdown_is_idempotent()
        self._test_concurrent_shutdown_calls_are_race_safe()
        self._test_shutdown_no_wait_returns_promptly()
        self._test_manual_save_still_works_after_shutdown()
        self._test_default_shutdown_timeout_is_five_seconds()
        self._test_shutdown_times_out_while_save_is_blocked()
        self._test_shutdown_converges_true_after_blocked_save_releases()
        self._test_shutdown_does_not_hold_lock_during_join()

        # ---------- MemoryService / MemoryStatus ----------
        self._test_memory_service_shutdown_passthrough()
        self._test_memory_status_auto_save_running_reflects_actual_thread_state()
        self._test_memory_operations_still_work_after_shutdown()

        # ---------- RuntimeService.shutdown() widened behavior ----------
        self._test_runtime_status_reports_inactive_memory_persistence_by_default()
        self._test_runtime_status_reports_active_memory_persistence()
        self._test_runtime_shutdown_all_none_unchanged_defaults()
        self._test_runtime_shutdown_stops_real_memory_persistence()
        self._test_runtime_shutdown_orders_rest_scheduler_workflow_scheduler_memory_background_workers()
        self._test_runtime_shutdown_idempotent_with_memory_persistence()

        # ---------- Real Bootstrap end-to-end ----------
        self._test_bootstrap_initialize_starts_memory_auto_save_loop()
        self._test_bootstrap_shutdown_stops_memory_auto_save_loop()
        self._test_bootstrap_shutdown_preserves_memory_service_identity()
        self._test_bootstrap_shutdown_twice_does_not_raise_or_hang()
        self._test_bootstrap_shutdown_without_initialize_does_not_raise()
        self._test_final_save_still_works_after_bootstrap_shutdown()

        # ---------- Public-surface guards ----------
        self._test_memory_persistence_public_surface_is_previous_plus_shutdown()
        self._test_memory_service_public_surface_is_previous_plus_shutdown()
        self._test_memory_module_cli_actions_unchanged()
        self._test_runtime_module_cli_actions_unchanged()
        self._test_runtime_module_status_displays_memory_auto_save()

        return self.result

    # ================= MemoryPersistence.shutdown() in isolation =================

    def _test_shutdown_never_started_returns_true_immediately(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            persistence = _build_real_memory_persistence(Path(tmp))
            self.assert_false(persistence.is_running())
            result = persistence.shutdown()
            self.assert_true(result)
            self.assert_false(persistence.is_running())

    def _test_shutdown_when_not_persistent_returns_true_immediately(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            persistence = _build_real_memory_persistence(Path(tmp), persistent=False)
            persistence.start()
            self.assert_false(persistence.is_running())
            self.assert_true(persistence.shutdown())

    def _test_shutdown_when_auto_save_disabled_returns_true_immediately(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            persistence = _build_real_memory_persistence(
                Path(tmp), persistent=True, auto_save=False
            )
            persistence.start()
            self.assert_false(persistence.is_running())
            self.assert_true(persistence.shutdown())

    def _test_auto_save_loop_starts_when_persistent_and_auto_save_enabled(self) -> None:
        """Baseline coverage: no prior test file exercised this at all
        (`EP064_DESIGN.md` Section 2.8) -- establishing it here before
        testing `shutdown()` avoids `shutdown()` being the only tested
        behavior of a previously wholly-untested subsystem."""
        with tempfile.TemporaryDirectory() as tmp:
            persistence = _build_real_memory_persistence(
                Path(tmp), persistent=True, auto_save=True
            )
            persistence.start()
            self.assert_true(persistence.is_running())
            persistence.shutdown()

    def _test_shutdown_stops_a_running_auto_save_loop(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            persistence = _build_real_memory_persistence(
                Path(tmp), persistent=True, auto_save=True
            )
            persistence.start()
            self.assert_true(persistence.is_running())
            result = persistence.shutdown()
            self.assert_true(result)
            self.assert_false(persistence.is_running())

    def _test_shutdown_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            persistence = _build_real_memory_persistence(
                Path(tmp), persistent=True, auto_save=True
            )
            persistence.start()
            first = persistence.shutdown()
            second = persistence.shutdown()
            self.assert_true(first)
            self.assert_true(second)
            self.assert_false(persistence.is_running())

    def _test_concurrent_shutdown_calls_are_race_safe(self) -> None:
        """Two threads calling shutdown() at once must not deadlock,
        must not raise, and must converge to the correct stopped
        state. Mirrors `tests/EP061/test_scheduler_shutdown.py`'s own
        `_test_concurrent_shutdown_calls_are_race_safe`, retargeted at
        `MemoryPersistence` (deliberately included here, unlike
        EP-063's own audit-disclosed Finding F1 gap for
        `WorkflowSchedulerService`, since the pattern is already
        established and cheap to reuse for a new subsystem)."""
        with tempfile.TemporaryDirectory() as tmp:
            persistence = _build_real_memory_persistence(
                Path(tmp), persistent=True, auto_save=True
            )
            persistence.start()
            self.assert_true(persistence.is_running())

            results: list[bool] = []
            errors: list[BaseException] = []
            results_lock = threading.Lock()

            def _call_shutdown() -> None:
                try:
                    outcome = persistence.shutdown()
                    with results_lock:
                        results.append(outcome)
                except BaseException as exc:  # noqa: BLE001
                    with results_lock:
                        errors.append(exc)

            threads = [threading.Thread(target=_call_shutdown) for _ in range(2)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=10.0)

            self.assert_true(
                all(not thread.is_alive() for thread in threads),
                "a concurrent shutdown() call did not finish within 10s (deadlock?)",
            )
            self.assert_equal(errors, [], f"concurrent shutdown() raised: {errors!r}")
            self.assert_equal(len(results), 2)
            self.assert_true(all(results), f"expected both calls to report True, got {results!r}")
            self.assert_false(persistence.is_running())
            self.assert_true(persistence.shutdown())

    def _test_shutdown_no_wait_returns_promptly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            persistence = _build_real_memory_persistence(
                Path(tmp), persistent=True, auto_save=True
            )
            persistence.start()
            started = time.monotonic()
            persistence.shutdown(wait=False)
            elapsed = time.monotonic() - started
            self.assert_true(elapsed < 1.0, f"wait=False took {elapsed:.3f}s, expected near-instant")
            time.sleep(0.2)
            self.assert_false(persistence.is_running())

    def _test_manual_save_still_works_after_shutdown(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            persistence = _build_real_memory_persistence(
                Path(tmp), persistent=True, auto_save=True
            )
            persistence.start()
            persistence.shutdown()
            self.assert_false(persistence.is_running())
            try:
                success, _message = persistence.save()
                self.assert_true(success)
            except Exception as exc:  # noqa: BLE001
                self.assert_true(False, f"save() after shutdown() raised: {exc!r}")

    def _test_default_shutdown_timeout_is_five_seconds(self) -> None:
        self.assert_equal(MemoryPersistence._DEFAULT_SHUTDOWN_TIMEOUT, 5.0)  # noqa: SLF001

    def _test_shutdown_times_out_while_save_is_blocked(self) -> None:
        """Controlled-blocking timeout test (no arbitrary sleeps for
        the core assertion): `save()` is intercepted so `shutdown()`'s
        join genuinely has something to time out on, rather than
        relying on flaky real-world timing."""
        with tempfile.TemporaryDirectory() as tmp:
            config = _write_config(
                Path(tmp),
                _memory_config_yaml(persistent=True, auto_save=True, auto_save_interval=0.01),
            )
            store = MemoryStore()
            persistence = _SlowSaveMemoryPersistence(config=config, store=store)
            persistence.start()
            self.assert_true(
                persistence.save_started.wait(timeout=5.0),
                "auto-save loop never entered save() within 5s",
            )
            try:
                result = persistence.shutdown(timeout=0.2)
                self.assert_false(result, "expected shutdown() to time out while save() is blocked")
                self.assert_true(persistence.is_running())
            finally:
                persistence.release_save.set()
                persistence.shutdown(timeout=5.0)

    def _test_shutdown_converges_true_after_blocked_save_releases(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _write_config(
                Path(tmp),
                _memory_config_yaml(persistent=True, auto_save=True, auto_save_interval=0.01),
            )
            store = MemoryStore()
            persistence = _SlowSaveMemoryPersistence(config=config, store=store)
            persistence.start()
            self.assert_true(persistence.save_started.wait(timeout=5.0))
            persistence.release_save.set()
            result = persistence.shutdown(timeout=5.0)
            self.assert_true(result)
            self.assert_false(persistence.is_running())

    def _test_shutdown_does_not_hold_lock_during_join(self) -> None:
        """Regression guard: `shutdown()` must not hold `_save_lock`
        across `thread.join()` -- a concurrent `is_running()` call must
        not be blocked by an in-progress `shutdown()`."""
        with tempfile.TemporaryDirectory() as tmp:
            persistence = _build_real_memory_persistence(
                Path(tmp), persistent=True, auto_save=True
            )
            persistence.start()
            persistence.shutdown()
            acquired = persistence._save_lock.acquire(timeout=1.0)  # noqa: SLF001
            self.assert_true(acquired, "_save_lock still held after shutdown() returned")
            if acquired:
                persistence._save_lock.release()  # noqa: SLF001

    # ================= MemoryService / MemoryStatus =================

    def _test_memory_service_shutdown_passthrough(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = _build_real_memory_service(
                Path(tmp), persistent=True, auto_save=True
            )
            self.assert_true(service.status().auto_save_running)
            result = service.shutdown()
            self.assert_true(result)
            self.assert_false(service.status().auto_save_running)

    def _test_memory_status_auto_save_running_reflects_actual_thread_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = _build_real_memory_service(
                Path(tmp), persistent=True, auto_save=True
            )
            status_before: MemoryStatus = service.status()
            self.assert_true(status_before.auto_save)
            self.assert_true(status_before.auto_save_running)
            service.shutdown()
            status_after: MemoryStatus = service.status()
            # Config-flag field is unchanged; only the running-thread
            # field reflects the shutdown.
            self.assert_true(status_after.auto_save)
            self.assert_false(status_after.auto_save_running)

    def _test_memory_operations_still_work_after_shutdown(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = _build_real_memory_service(
                Path(tmp), persistent=True, auto_save=True
            )
            service.shutdown()
            result = service.set("k", "v")
            self.assert_true(result.success)
            get_result = service.get("k")
            self.assert_not_none(get_result)
            status = service.status()
            self.assert_equal(status.total_entries, 1)

    # ================= RuntimeService.shutdown() widened behavior =================

    def _test_runtime_status_reports_inactive_memory_persistence_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = _build_real_memory_service(
                Path(tmp), persistent=True, auto_save=False
            )
            runtime = RuntimeService(
                started_at=time.monotonic(),
                rest_api_server=None,
                background_worker_service=None,
                shell=None,
                memory_service=service,
            )
            status = runtime.status()
            self.assert_false(status.memory_persistence_active)
            self.assert_equal(status.memory_persistence_entries_saved, 0)

    def _test_runtime_status_reports_active_memory_persistence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = _build_real_memory_service(
                Path(tmp), persistent=True, auto_save=True
            )
            service.set("k", "v", persistent=True)
            runtime = RuntimeService(
                started_at=time.monotonic(),
                rest_api_server=None,
                background_worker_service=None,
                shell=None,
                memory_service=service,
            )
            status = runtime.status()
            self.assert_true(status.memory_persistence_active)
            self.assert_equal(status.memory_persistence_entries_saved, 1)
            service.shutdown()

    def _test_runtime_shutdown_all_none_unchanged_defaults(self) -> None:
        service = RuntimeService(
            started_at=time.monotonic(),
            rest_api_server=None,
            background_worker_service=None,
            shell=None,
        )
        report = service.shutdown()
        self.assert_true(isinstance(report, RuntimeShutdownReport))
        self.assert_false(report.memory_persistence_was_active)
        self.assert_true(report.memory_persistence_stopped)
        # Pre-existing fields remain exactly as EP-060/061/063 left them.
        self.assert_false(report.rest_api_was_active)
        self.assert_true(report.rest_api_stopped)
        self.assert_false(report.background_workers_was_active)
        self.assert_true(report.background_workers_stopped)
        self.assert_false(report.scheduler_was_active)
        self.assert_true(report.scheduler_stopped)
        self.assert_false(report.workflow_scheduler_was_active)
        self.assert_true(report.workflow_scheduler_stopped)

    def _test_runtime_shutdown_stops_real_memory_persistence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            memory_service = _build_real_memory_service(
                Path(tmp), persistent=True, auto_save=True
            )
            self.assert_true(memory_service.status().auto_save_running)
            runtime = RuntimeService(
                started_at=time.monotonic(),
                rest_api_server=None,
                background_worker_service=None,
                shell=None,
                memory_service=memory_service,
            )
            report = runtime.shutdown()
            self.assert_true(report.memory_persistence_was_active)
            self.assert_true(report.memory_persistence_stopped)
            self.assert_false(memory_service.status().auto_save_running)

    def _test_runtime_shutdown_orders_rest_scheduler_workflow_scheduler_memory_background_workers(
        self,
    ) -> None:
        order_log: list[str] = []
        proxy_rest = _OrderRecordingRest(order_log)
        proxy_scheduler = _OrderRecordingSubsystem("scheduler", order_log)
        proxy_workflow_scheduler = _OrderRecordingSubsystem("workflow_scheduler", order_log)
        proxy_memory = _OrderRecordingSubsystem(
            "memory_persistence", order_log, running_attr="auto_save_running"
        )
        proxy_bg = _OrderRecordingSubsystem("background_workers", order_log)

        runtime = RuntimeService(
            started_at=time.monotonic(),
            rest_api_server=proxy_rest,  # type: ignore[arg-type]
            background_worker_service=proxy_bg,  # type: ignore[arg-type]
            shell=None,
            scheduler_service=proxy_scheduler,  # type: ignore[arg-type]
            workflow_scheduler_service=proxy_workflow_scheduler,  # type: ignore[arg-type]
            memory_service=proxy_memory,  # type: ignore[arg-type]
        )
        runtime.shutdown()
        self.assert_equal(
            order_log,
            ["rest_api", "scheduler", "workflow_scheduler", "memory_persistence", "background_workers"],
        )

    def _test_runtime_shutdown_idempotent_with_memory_persistence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            memory_service = _build_real_memory_service(
                Path(tmp), persistent=True, auto_save=True
            )
            runtime = RuntimeService(
                started_at=time.monotonic(),
                rest_api_server=None,
                background_worker_service=None,
                shell=None,
                memory_service=memory_service,
            )
            first = runtime.shutdown()
            second = runtime.shutdown()
            self.assert_true(first.memory_persistence_stopped)
            self.assert_true(second.memory_persistence_stopped)
            self.assert_false(memory_service.status().auto_save_running)

    # ================= Real Bootstrap end-to-end =================

    def _test_bootstrap_initialize_starts_memory_auto_save_loop(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(directory, memory_section=_MEMORY_AUTO_SAVE_SECTION)
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.initialize()
                try:
                    self.assert_true(bootstrap.memory_service is not None)
                    self.assert_true(bootstrap.memory_service.status().auto_save_running)
                finally:
                    bootstrap.shutdown()

    def _test_bootstrap_shutdown_stops_memory_auto_save_loop(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(directory, memory_section=_MEMORY_AUTO_SAVE_SECTION)
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.initialize()
                self.assert_true(bootstrap.memory_service.status().auto_save_running)
                bootstrap.shutdown()
                self.assert_false(bootstrap.memory_service.status().auto_save_running)

    def _test_bootstrap_shutdown_preserves_memory_service_identity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(directory, memory_section=_MEMORY_AUTO_SAVE_SECTION)
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.initialize()
                memory_service = bootstrap.memory_service
                self.assert_true(memory_service is not None)
                bootstrap.shutdown()
                # Owner Decision D8: reference stays alive, unlike
                # `_rest_api_server`/`_background_worker_service`.
                self.assert_true(bootstrap.memory_service is not None)
                self.assert_true(bootstrap.memory_service is memory_service)

    def _test_bootstrap_shutdown_twice_does_not_raise_or_hang(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(directory, memory_section=_MEMORY_AUTO_SAVE_SECTION)
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.initialize()
                try:
                    bootstrap.shutdown()
                    bootstrap.shutdown()
                    self.assert_true(True)
                except Exception as exc:  # noqa: BLE001
                    self.assert_true(False, f"second shutdown() raised: {exc!r}")

    def _test_bootstrap_shutdown_without_initialize_does_not_raise(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(directory)
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                try:
                    bootstrap.shutdown()
                    self.assert_true(True)
                except Exception as exc:  # noqa: BLE001
                    self.assert_true(False, f"shutdown() without initialize() raised: {exc!r}")

    def _test_final_save_still_works_after_bootstrap_shutdown(self) -> None:
        """Mirrors `main.py`'s `_save_memory_on_shutdown()`, which runs
        *after* `bootstrap.shutdown()` and needs a non-`None`,
        still-usable `bootstrap.memory_service` to call its final
        explicit `save()` (Owner Decision D8's compatibility argument,
        `EP064_DESIGN.md` Section 14)."""
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(directory, memory_section=_MEMORY_AUTO_SAVE_SECTION)
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.initialize()
                bootstrap.shutdown()
                self.assert_true(bootstrap.memory_service is not None)
                result = bootstrap.memory_service.save()
                self.assert_true(result.success, f"final save() after shutdown failed: {result.message}")

    # ================= Public-surface guards =================

    def _test_memory_persistence_public_surface_is_previous_plus_shutdown(self) -> None:
        public_methods = {
            name
            for name, _ in inspect.getmembers(MemoryPersistence, predicate=inspect.isfunction)
            if not name.startswith("_")
        }
        expected = {
            "start",
            "is_persistent",
            "is_auto_save",
            "auto_save_interval",
            "storage_path",
            "load",
            "save",
            "is_running",
            "diagnostics",
            "shutdown",
        }
        self.assert_equal(public_methods, expected)

    def _test_memory_service_public_surface_is_previous_plus_shutdown(self) -> None:
        public_methods = {
            name
            for name, _ in inspect.getmembers(MemoryService, predicate=inspect.isfunction)
            if not name.startswith("_")
        }
        expected = {
            "set",
            "get",
            "delete",
            "clear",
            "list_entries",
            "status",
            "doctor",
            "export",
            "import_",
            "save",
            "providers_status",
            "current_provider",
            "use_provider",
            "register_provider",
            "shutdown",
        }
        self.assert_equal(public_methods, expected)

    def _test_memory_module_cli_actions_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = _build_real_memory_service(Path(tmp), persistent=False, auto_save=False)
            module = MemoryModule(service)
            self.assert_equal(
                set(module._actions.keys()),  # noqa: SLF001
                {
                    "status",
                    "doctor",
                    "get",
                    "set",
                    "delete",
                    "clear",
                    "list",
                    "export",
                    "import",
                    "providers",
                    "use",
                    "help",
                },
            )
            for forbidden in ("start", "stop", "shutdown"):
                self.assert_true(forbidden not in module._actions)  # noqa: SLF001

    def _test_runtime_module_cli_actions_unchanged(self) -> None:
        service = RuntimeService(
            started_at=time.monotonic(),
            rest_api_server=None,
            background_worker_service=None,
            shell=None,
        )
        module = RuntimeModule(service)
        self.assert_equal(set(module._actions.keys()), {"status", "help"})  # noqa: SLF001
        for forbidden in ("start", "stop", "restart", "reconfigure", "register", "shutdown"):
            self.assert_true(forbidden not in module._actions)  # noqa: SLF001

    def _test_runtime_module_status_displays_memory_auto_save(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            memory_service = _build_real_memory_service(
                Path(tmp), persistent=True, auto_save=True
            )
            runtime = RuntimeService(
                started_at=time.monotonic(),
                rest_api_server=None,
                background_worker_service=None,
                shell=None,
                memory_service=memory_service,
            )
            module = RuntimeModule(runtime)
            result = module.execute("status", [])
            self.assert_true(result.success)
            self.assert_true("Memory Auto-Save : ACTIVE" in result.message)
            self.assert_true("Memory entries pending auto-save" in result.message)
            memory_service.shutdown()
