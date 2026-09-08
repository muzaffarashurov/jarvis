"""EP-066 test suite: MemoryPersistence auto-save loop exception containment.

Covers, per `EP066_DESIGN.md` Section 13:
    A. Normal auto-save still occurs.
    B. An unexpected (non-OSError) exception from `save()` does not
       escape the auto-save thread.
    C. The loop survives one failure and performs a later successful
       save (proves continuation, not merely that the exception was
       logged).
    D. The pre-existing `OSError` handling inside `save()` itself is
       unchanged.
    E. `shutdown()` still works correctly after the loop has already
       survived an exception.
    F. The failure is actually recorded via the real logging pipeline.
    G. No memory content is leaked into the log for a genuine,
       reachable non-OSError failure (a non-JSON-serializable stored
       value).
    H. Repeated unexpected failures do not terminate the loop.

Self-contained per this repository's own per-EP test convention (no
import from `tests/EP061/`, `tests/EP062/`, `tests/EP063/`,
`tests/EP064/`, or `tests/EP065/`) -- local builder functions below
are deliberately near-identical to (but independent copies of) the
ones `tests/EP064/test_memory_persistence_shutdown.py` already uses
for the same kind of real objects.
"""

from __future__ import annotations

import os
import tempfile
import threading
import time
from pathlib import Path

from loguru import logger

from src.core.config import Config
from src.core.memory.context import MemoryEntry
from src.core.memory.memory_persistence import MemoryPersistence
from src.core.memory.memory_store import MemoryStore
from src.testing.base_test import BaseTest
from src.testing.registry import TestRegistry

# ================= Local builders (independent of tests/EP064/) =================


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
    built-in default via `Config.get`'s `default` argument.
    """
    config_path = directory / "config.yaml"
    config_path.write_text(memory_settings, encoding="utf-8")
    return Config(config_path).load()


def _memory_config_yaml(
    persistent: bool = True,
    auto_save: bool = True,
    auto_save_interval: float = 3600,
) -> str:
    """Build a minimal 'memory.*'-only config.yaml body."""
    return (
        "memory:\n"
        f"  enabled: true\n"
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
    persistence_cls: type[MemoryPersistence] = MemoryPersistence,
) -> MemoryPersistence:
    """Build a real, minimal MemoryPersistence (does not start it)."""
    config = _write_config(
        tmp_path,
        _memory_config_yaml(
            persistent=persistent, auto_save=auto_save, auto_save_interval=auto_save_interval
        ),
    )
    store = MemoryStore()
    return persistence_cls(config=config, store=store)


class _FlakySaveMemoryPersistence(MemoryPersistence):
    """A MemoryPersistence whose `save()` raises a controlled, non-OSError
    exception for its first `fail_times` calls, then delegates to the
    real `save()` implementation.

    Deliberately intercepts exactly the call the auto-save loop makes
    (mirrors `tests/EP064/`'s own `_SlowSaveMemoryPersistence` pattern
    of subclassing to control `save()`'s behavior deterministically,
    rather than a mock).
    """

    def __init__(self, config: Config, store: MemoryStore, fail_times: int) -> None:
        super().__init__(config=config, store=store)
        self._fail_times = fail_times
        self.call_count = 0
        self.success_count = 0
        self.first_success = threading.Event()
        self._count_lock = threading.Lock()

    def save(self) -> tuple[bool, str]:
        with self._count_lock:
            self.call_count += 1
            current_call = self.call_count
        if current_call <= self._fail_times:
            raise RuntimeError(f"deliberate unexpected failure #{current_call}")
        result = super().save()
        with self._count_lock:
            self.success_count += 1
        self.first_success.set()
        return result


class _DirectoryClashMemoryPersistence(MemoryPersistence):
    """A MemoryPersistence whose `storage_path()` points at a directory,
    so `save()`'s own `target.open("w", ...)` raises a real, genuine
    `OSError` subclass (`IsADirectoryError`) -- used to prove the
    pre-existing `OSError` handling inside `save()` is unchanged by
    this EP.
    """

    def __init__(self, config: Config, store: MemoryStore, clash_path: Path) -> None:
        super().__init__(config=config, store=store)
        self._clash_path = clash_path

    def storage_path(self) -> Path:
        return self._clash_path


def _capture_logs() -> tuple[list[str], int]:
    """Attach a fresh loguru sink capturing formatted messages.

    Returns the list that will be appended to, and the sink id (to be
    removed with `logger.remove(sink_id)` when the caller is done).
    """
    lines: list[str] = []
    sink_id = logger.add(lambda message: lines.append(message.record["message"]), level="DEBUG")
    return lines, sink_id


def _wait_until(predicate, timeout: float = 5.0, interval: float = 0.01) -> bool:
    """Poll `predicate()` until it is truthy or `timeout` elapses."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


@TestRegistry.register
class MemoryPersistenceAutoSaveResilienceTest(BaseTest):
    """EP-066: MemoryPersistence auto-save loop exception containment."""

    NAME = "EP066"

    def run(self):
        self._test_normal_auto_save_still_occurs()
        self._test_unexpected_exception_does_not_escape_the_thread()
        self._test_loop_recovers_and_saves_after_one_failure()
        self._test_existing_oserror_handling_in_save_is_unchanged()
        self._test_shutdown_works_after_a_survived_exception()
        self._test_unexpected_failure_is_logged_at_error_level()
        self._test_non_serializable_value_does_not_leak_into_logs()
        self._test_repeated_unexpected_failures_do_not_kill_the_loop()
        return self.result

    # ---------- A. Normal auto-save ----------

    def _test_normal_auto_save_still_occurs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with _ChdirGuard(Path(tmp)):
                persistence = _build_real_memory_persistence(
                    Path(tmp), persistent=True, auto_save=True, auto_save_interval=0.02
                )
                persistence.start()
                try:
                    self.assert_true(persistence.is_running())
                    ok = _wait_until(lambda: persistence.storage_path().exists(), timeout=5.0)
                    self.assert_true(ok, "expected storage file to be written by auto-save")
                finally:
                    persistence.shutdown()

    # ---------- B. Unexpected exception containment ----------

    def _test_unexpected_exception_does_not_escape_the_thread(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with _ChdirGuard(Path(tmp)):
                persistence = _build_real_memory_persistence(
                    Path(tmp),
                    persistent=True,
                    auto_save=True,
                    auto_save_interval=0.02,
                    persistence_cls=lambda config, store: _FlakySaveMemoryPersistence(
                        config=config, store=store, fail_times=1
                    ),
                )
                persistence.start()
                try:
                    ok = _wait_until(lambda: persistence.call_count >= 1, timeout=5.0)
                    self.assert_true(ok, "auto-save loop never called save()")
                    # Give the loop a moment past the failing call: the thread
                    # must still be alive (no exception escaped it).
                    time.sleep(0.1)
                    self.assert_true(
                        persistence.is_running(),
                        "auto-save thread died after an unexpected save() exception",
                    )
                finally:
                    persistence.shutdown()

    # ---------- C. Recovery after one failure ----------

    def _test_loop_recovers_and_saves_after_one_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with _ChdirGuard(Path(tmp)):
                persistence = _build_real_memory_persistence(
                    Path(tmp),
                    persistent=True,
                    auto_save=True,
                    auto_save_interval=0.02,
                    persistence_cls=lambda config, store: _FlakySaveMemoryPersistence(
                        config=config, store=store, fail_times=1
                    ),
                )
                persistence.start()
                try:
                    ok = persistence.first_success.wait(timeout=5.0)
                    self.assert_true(
                        ok, "loop never reached a successful save() after the first failure"
                    )
                    self.assert_true(persistence.success_count >= 1)
                    self.assert_true(
                        persistence.call_count > 1,
                        "expected save() to be called again after the first failure",
                    )
                    self.assert_true(persistence.is_running())
                finally:
                    persistence.shutdown()

    # ---------- D. Existing OSError semantics unchanged ----------

    def _test_existing_oserror_handling_in_save_is_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with _ChdirGuard(Path(tmp)):
                # A directory at the storage path makes open(..., "w") raise
                # a genuine IsADirectoryError (an OSError subclass), exactly
                # the pre-existing failure class save() already handles.
                clash_dir = Path(tmp) / "clash_is_a_directory"
                clash_dir.mkdir(parents=True, exist_ok=True)

                config = _write_config(
                    Path(tmp),
                    _memory_config_yaml(persistent=True, auto_save=True, auto_save_interval=0.02),
                )
                store = MemoryStore()
                persistence = _DirectoryClashMemoryPersistence(
                    config=config, store=store, clash_path=clash_dir
                )

                lines, sink_id = _capture_logs()
                try:
                    persistence.start()
                    ok = _wait_until(
                        lambda: any("Memory auto-save failed:" in line for line in lines),
                        timeout=5.0,
                    )
                    self.assert_true(
                        ok, "expected the pre-existing 'Memory auto-save failed:' message"
                    )
                    self.assert_false(
                        any(
                            "Memory auto-save loop encountered an unexpected error" in line
                            for line in lines
                        ),
                        "an OSError must still take save()'s own existing path, not the new one",
                    )
                    self.assert_true(
                        persistence.is_running(),
                        "the pre-existing OSError path must still keep the loop alive",
                    )
                finally:
                    logger.remove(sink_id)
                    persistence.shutdown()

    # ---------- E. Shutdown behavior after a survived exception ----------

    def _test_shutdown_works_after_a_survived_exception(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with _ChdirGuard(Path(tmp)):
                persistence = _build_real_memory_persistence(
                    Path(tmp),
                    persistent=True,
                    auto_save=True,
                    auto_save_interval=0.02,
                    persistence_cls=lambda config, store: _FlakySaveMemoryPersistence(
                        config=config, store=store, fail_times=3
                    ),
                )
                persistence.start()
                ok = _wait_until(lambda: persistence.call_count >= 1, timeout=5.0)
                self.assert_true(ok, "auto-save loop never called save()")

                result = persistence.shutdown(timeout=5.0)
                self.assert_true(result, "shutdown() did not report success")
                self.assert_false(
                    persistence.is_running(), "auto-save thread still alive after shutdown()"
                )
                # Idempotent, exactly as before this EP.
                self.assert_true(persistence.shutdown())

    # ---------- F. Logging ----------

    def _test_unexpected_failure_is_logged_at_error_level(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with _ChdirGuard(Path(tmp)):
                persistence = _build_real_memory_persistence(
                    Path(tmp),
                    persistent=True,
                    auto_save=True,
                    auto_save_interval=0.02,
                    persistence_cls=lambda config, store: _FlakySaveMemoryPersistence(
                        config=config, store=store, fail_times=1
                    ),
                )

                captured_levels: list[str] = []
                captured_messages: list[str] = []

                def _sink(message) -> None:
                    captured_levels.append(message.record["level"].name)
                    captured_messages.append(message.record["message"])

                sink_id = logger.add(_sink, level="DEBUG")
                try:
                    persistence.start()
                    ok = _wait_until(
                        lambda: any(
                            "Memory auto-save loop encountered an unexpected error" in msg
                            for msg in captured_messages
                        ),
                        timeout=5.0,
                    )
                    self.assert_true(ok, "expected the new unexpected-error message to be logged")
                    matching_index = next(
                        i
                        for i, msg in enumerate(captured_messages)
                        if "Memory auto-save loop encountered an unexpected error" in msg
                    )
                    self.assert_equal(captured_levels[matching_index], "ERROR")
                finally:
                    logger.remove(sink_id)
                    persistence.shutdown()

    # ---------- G. No sensitive-data leakage ----------

    def _test_non_serializable_value_does_not_leak_into_logs(self) -> None:
        """A genuinely reachable (not synthetic) failure: a MemoryEntry
        whose value is not JSON-serializable (e.g. a `set`, which a
        future internal caller could store directly via `MemoryStore.set()`,
        bypassing the CLI's string-only `memory set`) makes `json.dump()`
        raise `TypeError` from inside `save()`. This exercises the real
        underlying gap this EP fixes, not just a hand-raised exception,
        and confirms the sensitive stored value itself never appears in
        the log -- only the exception's own type-name message does.
        """
        with tempfile.TemporaryDirectory() as tmp:
            with _ChdirGuard(Path(tmp)):
                persistence = _build_real_memory_persistence(
                    Path(tmp), persistent=True, auto_save=True, auto_save_interval=0.02
                )
                sensitive_marker = "XYZZY-EP066-SENSITIVE-MARKER-13572468"
                entry = MemoryEntry(
                    key="unserializable",
                    value={sensitive_marker, "other-secret-value"},
                    namespace="test",
                    persistent=True,
                )
                persistence._store.set(entry)  # noqa: SLF001 - direct store access for the test setup

                lines, sink_id = _capture_logs()
                try:
                    persistence.start()
                    ok = _wait_until(
                        lambda: any(
                            "Memory auto-save loop encountered an unexpected error" in line
                            for line in lines
                        ),
                        timeout=5.0,
                    )
                    self.assert_true(
                        ok, "expected the non-serializable value to trigger the new guard"
                    )
                    self.assert_false(
                        any(sensitive_marker in line for line in lines),
                        "the stored value must not leak into the log",
                    )
                    self.assert_true(
                        persistence.is_running(),
                        "the loop must survive a real, non-OSError save() failure",
                    )
                finally:
                    logger.remove(sink_id)
                    persistence.shutdown()

    # ---------- H. Repeated failures ----------

    def _test_repeated_unexpected_failures_do_not_kill_the_loop(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with _ChdirGuard(Path(tmp)):
                fail_times = 5
                persistence = _build_real_memory_persistence(
                    Path(tmp),
                    persistent=True,
                    auto_save=True,
                    auto_save_interval=0.01,
                    persistence_cls=lambda config, store: _FlakySaveMemoryPersistence(
                        config=config, store=store, fail_times=fail_times
                    ),
                )
                persistence.start()
                try:
                    ok = _wait_until(
                        lambda: persistence.call_count >= fail_times, timeout=5.0
                    )
                    self.assert_true(
                        ok, f"expected at least {fail_times} save() calls within the timeout"
                    )
                    self.assert_true(
                        persistence.is_running(),
                        "the auto-save thread must survive several consecutive failures",
                    )
                finally:
                    persistence.shutdown(timeout=5.0)
                self.assert_false(persistence.is_running())
