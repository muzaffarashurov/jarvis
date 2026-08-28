"""Real engineering tests for EP-052 STEP 2 - File Automation.

Single combined test suite (NAME = "EP052"), following the same
precedent EP-043/EP-045/EP-046/EP-047/EP-048/EP-049/EP-050 already
established: this sidesteps the pre-existing `TestRegistry`
NAME-collision technical debt (docs/BACKLOG.md) entirely rather than
triggering it.

Two backend tiers are exercised, mirroring EP052_DESIGN.md Section 16:

    - `_FakeFileBackend` (below): a deterministic, in-memory,
      test-only stand-in implementing `FileBackend`'s full protocol,
      following `_FakeComputerUseBackend`/`_FakeBrowserBackend`'s own
      convention -- used for `FileModule` argument-shape/gate/
      path-safety/dispatch tests that do not need to observe real
      filesystem behavior.
    - `LocalFileBackend` itself, exercised directly against a real,
      disposable `tempfile.TemporaryDirectory()` -- unlike
      `WindowsComputerUseBackend`/`PlaywrightBrowserBackend`,
      `LocalFileBackend`'s real implementation needs no special
      hardware/display/network access (EP052_DESIGN.md Section 16),
      so its *real* filesystem behavior (CRUD correctness, overwrite
      refusal, non-recursive delete, UTF-8 handling) is verified here
      in the same default, fully-automated suite -- never against the
      developer's home directory, the repository root, or any path
      outside each test's own temporary sandbox.

Covers:
    - `FileBackend` protocol conformance (the fake satisfies the same
      structural interface the real backend does).
    - `FileModule` argument-shape validation (wrong argument count) --
      rejected before any backend call.
    - The `file.enabled` safety gate: every action is rejected, with
      zero backend calls, while disabled; every action reaches the
      backend once enabled.
    - The path-safety model (Owner Decisions D4/D5): empty
      `allowed_roots` blocks everything; a path outside every
      configured root is refused; path traversal (`../..`) is
      defeated by resolve-before-compare; a `denied_paths` entry
      inside an otherwise-allowed root is refused.
    - The `file.allow_destructive` gate (Owner Decision D3): `move`
      and `delete` are refused while false and succeed once true;
      overwriting `write`/`copy` follows the same rule; non-
      destructive actions (`write`/`copy` to a new path, `mkdir`,
      every read-only action) are never blocked by this flag.
    - Full CRUD behavioral coverage against a real, temporary
      filesystem: CREATE (`write` new file, `copy`, `mkdir`), READ
      (`list`, `exists`, `stat`, `read`), UPDATE (`write` existing
      file with explicit overwrite, `move`), DELETE (`delete` a file,
      an empty directory, and refusal on a non-empty directory --
      Owner Decision D8).
    - UTF-8 read/write round-tripping and a clean, non-crashing
      failure for non-UTF-8 content (Owner Decision D6).
    - Missing-path, invalid-path, and backend-error translation into
      a failed `CommandResult`, never propagated raw.
    - `CommandRouter` string-dispatch ("file <action> ...") produces
      results identical to direct `FileModule.execute()` calls.
    - `Bootstrap` wiring: 'file.enabled' defaults to false when
      entirely absent from config; the 'file' namespace is registered
      with `CommandRouter` regardless of the flag's value; actions
      report the disabled message until the flag is set to true.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path

from src.bootstrap import Bootstrap
from src.core.command_router import CommandRouter
from src.core.config import Config
from src.skills.files.backend import FileBackend, FileBackendError, FileEntry
from src.skills.files.local_backend import LocalFileBackend
from src.skills.files.skill import FileModule
from src.testing.base_test import BaseTest
from src.testing.registry import TestRegistry
from tests.EP045.test_web_dashboard import (
    _MINIMAL_BOOTSTRAP_CONFIG_YAML,
    _ChdirGuard,
    _api_section,
)


@dataclass
class _RecordedCall:
    """One recorded `FileBackend` method invocation."""

    method: str
    args: tuple
    kwargs: dict


class _FakeFileBackend:
    """Deterministic, in-memory, test-only `FileBackend` (EP052_DESIGN.md Section 16).

    Records every call it receives (`self.calls`) so tests can assert
    exactly what `FileModule` passed through, without touching any
    real filesystem. Backed by a plain in-memory dict of
    `path -> content-or-None` (`None` marks a directory). `raise_on`
    (a set of method names) makes the fake raise `FileBackendError`
    for specific methods, to exercise `FileModule`'s failure-
    translation path deterministically.
    """

    def __init__(
        self,
        files: dict[str, str] | None = None,
        directories: frozenset[str] = frozenset(),
        raise_on: frozenset[str] = frozenset(),
        raise_message: str = "simulated backend failure",
    ) -> None:
        self.calls: list[_RecordedCall] = []
        self._files: dict[str, str] = dict(files or {})
        self._directories: set[str] = set(directories)
        self._raise_on = raise_on
        self._raise_message = raise_message

    def _record(self, method: str, *args, **kwargs) -> None:
        self.calls.append(_RecordedCall(method=method, args=args, kwargs=kwargs))
        if method in self._raise_on:
            raise FileBackendError(self._raise_message)

    def list(self, path: Path) -> list[FileEntry]:
        self._record("list", path)
        key = str(path)
        entries: list[FileEntry] = []
        for candidate in sorted(set(self._files) | self._directories):
            parent = str(Path(candidate).parent)
            if parent == key and candidate != key:
                is_dir = candidate in self._directories
                entries.append(
                    FileEntry(
                        name=Path(candidate).name,
                        path=candidate,
                        is_dir=is_dir,
                        is_file=not is_dir,
                        size=len(self._files.get(candidate, "")),
                        modified=0.0,
                    )
                )
        return entries

    def exists(self, path: Path) -> bool:
        self._record("exists", path)
        key = str(path)
        return key in self._files or key in self._directories

    def stat(self, path: Path) -> FileEntry:
        self._record("stat", path)
        key = str(path)
        is_dir = key in self._directories
        return FileEntry(
            name=path.name,
            path=key,
            is_dir=is_dir,
            is_file=not is_dir,
            size=len(self._files.get(key, "")),
            modified=0.0,
        )

    def read(self, path: Path) -> str:
        self._record("read", path)
        return self._files[str(path)]

    def write(self, path: Path, content: str) -> None:
        self._record("write", path, content)
        self._files[str(path)] = content

    def copy(self, src: Path, dst: Path) -> None:
        self._record("copy", src, dst)
        self._files[str(dst)] = self._files[str(src)]

    def move(self, src: Path, dst: Path) -> None:
        self._record("move", src, dst)
        if str(src) in self._files:
            self._files[str(dst)] = self._files.pop(str(src))
        else:
            self._directories.discard(str(src))
            self._directories.add(str(dst))

    def mkdir(self, path: Path) -> None:
        self._record("mkdir", path)
        self._directories.add(str(path))

    def delete(self, path: Path) -> None:
        self._record("delete", path)
        key = str(path)
        if key in self._files:
            del self._files[key]
        elif key in self._directories:
            self._directories.discard(key)


def _config_with(overrides: dict) -> Config:
    """Build a Config whose in-memory data is exactly `overrides`."""
    config = Config(config_path=Path("unused.yaml"))
    config._data = overrides
    return config


def _file_config(
    *,
    enabled: bool = True,
    allow_destructive: bool = False,
    allowed_roots: list[str] | None = None,
    denied_paths: list[str] | None = None,
) -> Config:
    """Build a Config with a single 'file:' section for FileModule tests."""
    return _config_with(
        {
            "file": {
                "enabled": enabled,
                "allow_destructive": allow_destructive,
                "allowed_roots": allowed_roots if allowed_roots is not None else [],
                "denied_paths": denied_paths if denied_paths is not None else [],
            }
        }
    )


def _write_file_bootstrap_config(directory: Path, file_section: str) -> None:
    """Write a minimal bootstrap config.yaml (EP-045's fixture) plus a 'file:' block."""
    config_dir = directory / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    base_yaml = _MINIMAL_BOOTSTRAP_CONFIG_YAML.format(
        api_section=_api_section(enabled=False, web_dashboard_dir=None)
    )
    (config_dir / "config.yaml").write_text(base_yaml + "\n" + file_section, encoding="utf-8")


@TestRegistry.register
class FileTest(BaseTest):
    NAME = "EP052"

    def run(self):
        # ---------- Protocol conformance ----------
        self._test_fake_backend_satisfies_protocol()
        self._test_local_backend_satisfies_protocol()

        # ---------- Argument-shape validation ----------
        self._test_list_rejects_wrong_argument_count()
        self._test_write_rejects_too_few_arguments()
        self._test_copy_rejects_wrong_argument_count()
        self._test_move_rejects_wrong_argument_count()

        # ---------- file.enabled gate ----------
        self._test_disabled_rejects_every_action_with_zero_backend_calls()
        self._test_no_backend_available_rejects_with_zero_backend_calls()
        self._test_enabled_true_allows_dispatch_to_reach_path_safety()

        # ---------- Path safety (D4/D5) ----------
        self._test_empty_allowed_roots_blocks_everything()
        self._test_path_outside_allowed_root_rejected()
        self._test_path_traversal_rejected()
        self._test_path_inside_allowed_root_accepted()
        self._test_denied_path_inside_allowed_root_rejected()
        self._test_absolute_path_outside_allowed_root_rejected()

        # ---------- file.allow_destructive gate (D3) ----------
        self._test_move_rejected_without_destructive_permission()
        self._test_move_succeeds_with_destructive_permission()
        self._test_delete_rejected_without_destructive_permission()
        self._test_delete_succeeds_with_destructive_permission()
        self._test_write_overwrite_rejected_without_destructive_permission()
        self._test_write_overwrite_succeeds_with_destructive_permission()
        self._test_write_new_file_never_requires_destructive_permission()
        self._test_copy_new_destination_never_requires_destructive_permission()
        self._test_mkdir_never_requires_destructive_permission()
        self._test_destructive_permission_does_not_bypass_path_safety()

        # ---------- CREATE (real filesystem) ----------
        self._test_write_new_file_creates_file_on_disk()
        self._test_copy_creates_new_file_on_disk()
        self._test_mkdir_creates_directory_on_disk()
        self._test_mkdir_rejects_already_existing_directory()

        # ---------- READ (real filesystem) ----------
        self._test_list_returns_directory_entries()
        self._test_list_rejects_non_directory()
        self._test_exists_true_and_false()
        self._test_stat_returns_metadata()
        self._test_read_returns_utf8_content()
        self._test_read_rejects_missing_file()
        self._test_read_rejects_non_utf8_content()

        # ---------- UPDATE (real filesystem) ----------
        self._test_write_existing_file_without_overwrite_is_refused()
        self._test_write_existing_file_with_overwrite_updates_content()
        self._test_move_renames_file_on_disk()
        self._test_move_rejects_existing_destination()

        # ---------- DELETE (real filesystem) ----------
        self._test_delete_removes_file_on_disk()
        self._test_delete_removes_empty_directory_on_disk()
        self._test_delete_rejects_non_empty_directory()
        self._test_delete_rejects_missing_path()

        # ---------- copy overwrite semantics ----------
        self._test_copy_existing_destination_without_overwrite_is_refused()
        self._test_copy_existing_destination_with_overwrite_replaces_content()

        # ---------- HELP / unknown action ----------
        self._test_help_lists_commands()
        self._test_unknown_action_returns_failure()

        # ---------- Backend failure translation ----------
        self._test_backend_failure_translated_to_failed_result()

        # ---------- Invalid path handling ----------
        self._test_invalid_path_produces_clean_failure()

        # ---------- CommandRouter integration ----------
        self._test_command_router_dispatch_matches_direct_execute()
        self._test_command_router_unaffected_by_other_modules()

        # ---------- Bootstrap wiring ----------
        self._test_bootstrap_config_defaults_file_disabled()
        self._test_bootstrap_registers_file_namespace_even_when_disabled()
        self._test_bootstrap_file_actions_report_disabled_message()
        self._test_bootstrap_other_modules_unaffected_when_file_absent()

        return self.result

    # ---------- Protocol conformance ----------

    def _test_fake_backend_satisfies_protocol(self) -> None:
        fake = _FakeFileBackend()
        self.assert_true(isinstance(fake, FileBackend), "_FakeFileBackend must satisfy the FileBackend Protocol")

    def _test_local_backend_satisfies_protocol(self) -> None:
        backend = LocalFileBackend()
        self.assert_true(isinstance(backend, FileBackend), "LocalFileBackend must satisfy the FileBackend Protocol")

    # ---------- Argument-shape validation ----------

    def _test_list_rejects_wrong_argument_count(self) -> None:
        fake = _FakeFileBackend()
        module = FileModule(config=_file_config(allowed_roots=["/tmp"]), backend=fake)
        result = module.execute("list", [])
        self.assert_false(result.success)
        self.assert_equal(len(fake.calls), 0, "no backend call before shape validation passes")

    def _test_write_rejects_too_few_arguments(self) -> None:
        fake = _FakeFileBackend()
        module = FileModule(config=_file_config(allowed_roots=["/tmp"]), backend=fake)
        result = module.execute("write", ["/tmp/only-path"])
        self.assert_false(result.success)
        self.assert_equal(len(fake.calls), 0)

    def _test_copy_rejects_wrong_argument_count(self) -> None:
        fake = _FakeFileBackend()
        module = FileModule(config=_file_config(allowed_roots=["/tmp"]), backend=fake)
        result = module.execute("copy", ["/tmp/only-src"])
        self.assert_false(result.success)
        self.assert_equal(len(fake.calls), 0)

    def _test_move_rejects_wrong_argument_count(self) -> None:
        fake = _FakeFileBackend()
        module = FileModule(config=_file_config(allowed_roots=["/tmp"]), backend=fake)
        result = module.execute("move", ["/tmp/only-src"])
        self.assert_false(result.success)
        self.assert_equal(len(fake.calls), 0)

    # ---------- file.enabled gate ----------

    def _test_disabled_rejects_every_action_with_zero_backend_calls(self) -> None:
        fake = _FakeFileBackend(files={"/tmp/root/a.txt": "hi"}, directories=frozenset({"/tmp/root"}))
        module = FileModule(config=_file_config(enabled=False, allowed_roots=["/tmp/root"]), backend=fake)
        for action, args in [
            ("list", ["/tmp/root"]),
            ("exists", ["/tmp/root/a.txt"]),
            ("stat", ["/tmp/root/a.txt"]),
            ("read", ["/tmp/root/a.txt"]),
            ("write", ["/tmp/root/b.txt", "hi"]),
            ("copy", ["/tmp/root/a.txt", "/tmp/root/c.txt"]),
            ("move", ["/tmp/root/a.txt", "/tmp/root/d.txt"]),
            ("mkdir", ["/tmp/root/newdir"]),
            ("delete", ["/tmp/root/a.txt"]),
        ]:
            result = module.execute(action, args)
            self.assert_false(result.success, f"'{action}' must be rejected while disabled")
            self.assert_true("disabled" in result.message.lower(), f"'{action}' message must mention disabled")
        self.assert_equal(len(fake.calls), 0, "zero backend calls must occur while file.enabled is false")

    def _test_no_backend_available_rejects_with_zero_backend_calls(self) -> None:
        module = FileModule(config=_file_config(enabled=True, allowed_roots=["/tmp"]), backend=None)
        result = module.execute("list", ["/tmp"])
        self.assert_false(result.success)
        self.assert_true("no backend" in result.message.lower() or "unavailable" in result.message.lower() or "backend" in result.message.lower())

    def _test_enabled_true_allows_dispatch_to_reach_path_safety(self) -> None:
        fake = _FakeFileBackend()
        module = FileModule(config=_file_config(enabled=True, allowed_roots=[]), backend=fake)
        result = module.execute("list", ["/tmp/somewhere"])
        # Empty allowed_roots -> refused at path-safety stage, zero backend calls,
        # but the *gate* itself (enabled + backend availability) must have passed
        # (i.e. failure message is about the workspace, not "disabled").
        self.assert_false(result.success)
        self.assert_false("disabled" in result.message.lower())
        self.assert_equal(len(fake.calls), 0)

    # ---------- Path safety (D4/D5) ----------

    def _test_empty_allowed_roots_blocks_everything(self) -> None:
        fake = _FakeFileBackend()
        module = FileModule(config=_file_config(allowed_roots=[]), backend=fake)
        result = module.execute("exists", ["/tmp/anything"])
        self.assert_false(result.success)
        self.assert_true("allowed_roots" in result.message or "allowed workspace" in result.message.lower())
        self.assert_equal(len(fake.calls), 0)

    def _test_path_outside_allowed_root_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as allowed_dir, tempfile.TemporaryDirectory() as outside_dir:
            fake = _FakeFileBackend()
            module = FileModule(config=_file_config(allowed_roots=[allowed_dir]), backend=fake)
            result = module.execute("exists", [str(Path(outside_dir) / "x.txt")])
            self.assert_false(result.success)
            self.assert_equal(len(fake.calls), 0)

    def _test_path_traversal_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as allowed_dir:
            allowed_path = Path(allowed_dir)
            subdir = allowed_path / "sub"
            subdir.mkdir()
            fake = _FakeFileBackend()
            module = FileModule(config=_file_config(allowed_roots=[str(subdir)]), backend=fake)
            traversal = str(subdir / ".." / ".." / "etc" / "passwd")
            result = module.execute("read", [traversal])
            self.assert_false(result.success, "path traversal ('../..') must be refused")
            self.assert_equal(len(fake.calls), 0)

    def _test_path_inside_allowed_root_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as allowed_dir:
            target = Path(allowed_dir) / "inside.txt"
            target.write_text("hello", encoding="utf-8")
            fake = _FakeFileBackend()
            module = FileModule(config=_file_config(allowed_roots=[allowed_dir]), backend=fake)
            result = module.execute("exists", [str(target)])
            self.assert_true(result.success)
            self.assert_equal(len(fake.calls), 1, "path inside an allowed root must reach the backend")

    def _test_denied_path_inside_allowed_root_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as allowed_dir:
            allowed_path = Path(allowed_dir)
            denied_subdir = allowed_path / ".env-dir"
            denied_subdir.mkdir()
            target = denied_subdir / "secret.txt"
            target.write_text("secret", encoding="utf-8")
            fake = _FakeFileBackend()
            module = FileModule(
                config=_file_config(allowed_roots=[allowed_dir], denied_paths=[str(denied_subdir)]),
                backend=fake,
            )
            result = module.execute("read", [str(target)])
            self.assert_false(result.success, "a path inside a denied_paths entry must be refused even though it is inside an allowed root")
            self.assert_equal(len(fake.calls), 0)

    def _test_absolute_path_outside_allowed_root_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as allowed_dir:
            fake = _FakeFileBackend()
            module = FileModule(config=_file_config(allowed_roots=[allowed_dir]), backend=fake)
            result = module.execute("read", ["/etc/passwd"])
            self.assert_false(result.success)
            self.assert_equal(len(fake.calls), 0)

    # ---------- file.allow_destructive gate (D3) ----------

    def _test_move_rejected_without_destructive_permission(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            src = Path(root) / "a.txt"
            src.write_text("hi", encoding="utf-8")
            dst = Path(root) / "b.txt"
            module = FileModule(config=_file_config(allowed_roots=[root], allow_destructive=False), backend=LocalFileBackend())
            result = module.execute("move", [str(src), str(dst)])
            self.assert_false(result.success)
            self.assert_true("allow_destructive" in result.message)
            self.assert_true(src.exists(), "source must remain untouched when destructive permission is refused")
            self.assert_false(dst.exists())

    def _test_move_succeeds_with_destructive_permission(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            src = Path(root) / "a.txt"
            src.write_text("hi", encoding="utf-8")
            dst = Path(root) / "b.txt"
            module = FileModule(config=_file_config(allowed_roots=[root], allow_destructive=True), backend=LocalFileBackend())
            result = module.execute("move", [str(src), str(dst)])
            self.assert_true(result.success)
            self.assert_false(src.exists())
            self.assert_true(dst.exists())
            self.assert_equal(dst.read_text(encoding="utf-8"), "hi")

    def _test_delete_rejected_without_destructive_permission(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            target = Path(root) / "a.txt"
            target.write_text("hi", encoding="utf-8")
            module = FileModule(config=_file_config(allowed_roots=[root], allow_destructive=False), backend=LocalFileBackend())
            result = module.execute("delete", [str(target)])
            self.assert_false(result.success)
            self.assert_true(target.exists(), "file must remain when destructive permission is refused")

    def _test_delete_succeeds_with_destructive_permission(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            target = Path(root) / "a.txt"
            target.write_text("hi", encoding="utf-8")
            module = FileModule(config=_file_config(allowed_roots=[root], allow_destructive=True), backend=LocalFileBackend())
            result = module.execute("delete", [str(target)])
            self.assert_true(result.success)
            self.assert_false(target.exists())

    def _test_write_overwrite_rejected_without_destructive_permission(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            target = Path(root) / "a.txt"
            target.write_text("original", encoding="utf-8")
            module = FileModule(config=_file_config(allowed_roots=[root], allow_destructive=False), backend=LocalFileBackend())
            result = module.execute("write", ["--overwrite", str(target), "new", "content"])
            self.assert_false(result.success)
            self.assert_equal(target.read_text(encoding="utf-8"), "original", "content must remain unchanged")

    def _test_write_overwrite_succeeds_with_destructive_permission(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            target = Path(root) / "a.txt"
            target.write_text("original", encoding="utf-8")
            module = FileModule(config=_file_config(allowed_roots=[root], allow_destructive=True), backend=LocalFileBackend())
            result = module.execute("write", ["--overwrite", str(target), "new", "content"])
            self.assert_true(result.success)
            self.assert_equal(target.read_text(encoding="utf-8"), "new content")

    def _test_write_new_file_never_requires_destructive_permission(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            target = Path(root) / "brand-new.txt"
            module = FileModule(config=_file_config(allowed_roots=[root], allow_destructive=False), backend=LocalFileBackend())
            result = module.execute("write", [str(target), "hello"])
            self.assert_true(result.success, "creating a new file must not require file.allow_destructive")
            self.assert_true(target.exists())

    def _test_copy_new_destination_never_requires_destructive_permission(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            src = Path(root) / "src.txt"
            src.write_text("hi", encoding="utf-8")
            dst = Path(root) / "dst.txt"
            module = FileModule(config=_file_config(allowed_roots=[root], allow_destructive=False), backend=LocalFileBackend())
            result = module.execute("copy", [str(src), str(dst)])
            self.assert_true(result.success)
            self.assert_true(dst.exists())

    def _test_mkdir_never_requires_destructive_permission(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            target = Path(root) / "newdir"
            module = FileModule(config=_file_config(allowed_roots=[root], allow_destructive=False), backend=LocalFileBackend())
            result = module.execute("mkdir", [str(target)])
            self.assert_true(result.success)
            self.assert_true(target.is_dir())

    def _test_destructive_permission_does_not_bypass_path_safety(self) -> None:
        with tempfile.TemporaryDirectory() as allowed_dir, tempfile.TemporaryDirectory() as outside_dir:
            outside_target = Path(outside_dir) / "victim.txt"
            outside_target.write_text("do not touch", encoding="utf-8")
            module = FileModule(
                config=_file_config(allowed_roots=[allowed_dir], allow_destructive=True),
                backend=LocalFileBackend(),
            )
            result = module.execute("delete", [str(outside_target)])
            self.assert_false(result.success, "file.allow_destructive=true must never bypass the allowed_roots check")
            self.assert_true(outside_target.exists(), "a path outside allowed_roots must survive even with destructive permission granted")

    # ---------- CREATE (real filesystem) ----------

    def _test_write_new_file_creates_file_on_disk(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            target = Path(root) / "created.txt"
            module = self._enabled_local_module(root)
            result = module.execute("write", [str(target), "hello", "world"])
            self.assert_true(result.success)
            self.assert_true("created" in result.message.lower())
            self.assert_true(target.exists())
            self.assert_equal(target.read_text(encoding="utf-8"), "hello world")

    def _test_copy_creates_new_file_on_disk(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            src = Path(root) / "src.txt"
            src.write_text("copy-me", encoding="utf-8")
            dst = Path(root) / "dst.txt"
            module = self._enabled_local_module(root)
            result = module.execute("copy", [str(src), str(dst)])
            self.assert_true(result.success)
            self.assert_true(dst.exists())
            self.assert_equal(dst.read_text(encoding="utf-8"), "copy-me")
            self.assert_true(src.exists(), "copy must not remove the source")

    def _test_mkdir_creates_directory_on_disk(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            target = Path(root) / "newdir"
            module = self._enabled_local_module(root)
            result = module.execute("mkdir", [str(target)])
            self.assert_true(result.success)
            self.assert_true(target.is_dir())

    def _test_mkdir_rejects_already_existing_directory(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            target = Path(root) / "existing"
            target.mkdir()
            module = self._enabled_local_module(root)
            result = module.execute("mkdir", [str(target)])
            self.assert_false(result.success)

    # ---------- READ (real filesystem) ----------

    def _test_list_returns_directory_entries(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            (Path(root) / "a.txt").write_text("a", encoding="utf-8")
            (Path(root) / "b.txt").write_text("bb", encoding="utf-8")
            (Path(root) / "subdir").mkdir()
            module = self._enabled_local_module(root)
            result = module.execute("list", [root])
            self.assert_true(result.success)
            self.assert_true("a.txt" in result.message)
            self.assert_true("b.txt" in result.message)
            self.assert_true("subdir" in result.message)

    def _test_list_rejects_non_directory(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            target = Path(root) / "file.txt"
            target.write_text("hi", encoding="utf-8")
            module = self._enabled_local_module(root)
            result = module.execute("list", [str(target)])
            self.assert_false(result.success)

    def _test_exists_true_and_false(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            present = Path(root) / "present.txt"
            present.write_text("hi", encoding="utf-8")
            missing = Path(root) / "missing.txt"
            module = self._enabled_local_module(root)
            self.assert_equal(module.execute("exists", [str(present)]).message, "true")
            self.assert_equal(module.execute("exists", [str(missing)]).message, "false")

    def _test_stat_returns_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            target = Path(root) / "sized.txt"
            target.write_text("12345", encoding="utf-8")
            module = self._enabled_local_module(root)
            result = module.execute("stat", [str(target)])
            self.assert_true(result.success)
            self.assert_true("5 bytes" in result.message)
            self.assert_true("file" in result.message)

    def _test_read_returns_utf8_content(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            target = Path(root) / "unicode.txt"
            target.write_text("héllo wörld 日本語", encoding="utf-8")
            module = self._enabled_local_module(root)
            result = module.execute("read", [str(target)])
            self.assert_true(result.success)
            self.assert_equal(result.message, "héllo wörld 日本語")

    def _test_read_rejects_missing_file(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            missing = Path(root) / "nope.txt"
            module = self._enabled_local_module(root)
            result = module.execute("read", [str(missing)])
            self.assert_false(result.success)

    def _test_read_rejects_non_utf8_content(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            target = Path(root) / "binary.dat"
            target.write_bytes(b"\xff\xfe\x00\x01not-utf8\x80")
            module = self._enabled_local_module(root)
            result = module.execute("read", [str(target)])
            self.assert_false(result.success, "non-UTF-8 content must be a clean failure, not a crash")

    # ---------- UPDATE (real filesystem) ----------

    def _test_write_existing_file_without_overwrite_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            target = Path(root) / "existing.txt"
            target.write_text("original", encoding="utf-8")
            module = self._enabled_local_module(root, allow_destructive=True)
            result = module.execute("write", [str(target), "new", "text"])
            self.assert_false(result.success, "write on an existing file without --overwrite must be refused (D7)")
            self.assert_equal(target.read_text(encoding="utf-8"), "original")

    def _test_write_existing_file_with_overwrite_updates_content(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            target = Path(root) / "existing.txt"
            target.write_text("original", encoding="utf-8")
            module = self._enabled_local_module(root, allow_destructive=True)
            result = module.execute("write", ["--overwrite", str(target), "updated", "text"])
            self.assert_true(result.success)
            self.assert_true("updated" in result.message.lower())
            self.assert_equal(target.read_text(encoding="utf-8"), "updated text")

    def _test_move_renames_file_on_disk(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            src = Path(root) / "old-name.txt"
            src.write_text("content", encoding="utf-8")
            dst = Path(root) / "new-name.txt"
            module = self._enabled_local_module(root, allow_destructive=True)
            result = module.execute("move", [str(src), str(dst)])
            self.assert_true(result.success)
            self.assert_false(src.exists())
            self.assert_true(dst.exists())
            self.assert_equal(dst.read_text(encoding="utf-8"), "content")

    def _test_move_rejects_existing_destination(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            src = Path(root) / "src.txt"
            src.write_text("src", encoding="utf-8")
            dst = Path(root) / "dst.txt"
            dst.write_text("dst", encoding="utf-8")
            module = self._enabled_local_module(root, allow_destructive=True)
            result = module.execute("move", [str(src), str(dst)])
            self.assert_false(result.success, "move must not overwrite an existing destination in v1")
            self.assert_true(src.exists())
            self.assert_equal(dst.read_text(encoding="utf-8"), "dst")

    # ---------- DELETE (real filesystem) ----------

    def _test_delete_removes_file_on_disk(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            target = Path(root) / "to-delete.txt"
            target.write_text("bye", encoding="utf-8")
            module = self._enabled_local_module(root, allow_destructive=True)
            result = module.execute("delete", [str(target)])
            self.assert_true(result.success)
            self.assert_false(target.exists())

    def _test_delete_removes_empty_directory_on_disk(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            target = Path(root) / "empty-dir"
            target.mkdir()
            module = self._enabled_local_module(root, allow_destructive=True)
            result = module.execute("delete", [str(target)])
            self.assert_true(result.success)
            self.assert_false(target.exists())

    def _test_delete_rejects_non_empty_directory(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            target = Path(root) / "non-empty-dir"
            target.mkdir()
            (target / "child.txt").write_text("hi", encoding="utf-8")
            module = self._enabled_local_module(root, allow_destructive=True)
            result = module.execute("delete", [str(target)])
            self.assert_false(result.success, "recursive delete of a non-empty directory must be refused (D8)")
            self.assert_true(target.exists())
            self.assert_true((target / "child.txt").exists())

    def _test_delete_rejects_missing_path(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            missing = Path(root) / "nope.txt"
            module = self._enabled_local_module(root, allow_destructive=True)
            result = module.execute("delete", [str(missing)])
            self.assert_false(result.success)

    # ---------- copy overwrite semantics ----------

    def _test_copy_existing_destination_without_overwrite_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            src = Path(root) / "src.txt"
            src.write_text("new-content", encoding="utf-8")
            dst = Path(root) / "dst.txt"
            dst.write_text("old-content", encoding="utf-8")
            module = self._enabled_local_module(root, allow_destructive=True)
            result = module.execute("copy", [str(src), str(dst)])
            self.assert_false(result.success)
            self.assert_equal(dst.read_text(encoding="utf-8"), "old-content")

    def _test_copy_existing_destination_with_overwrite_replaces_content(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            src = Path(root) / "src.txt"
            src.write_text("new-content", encoding="utf-8")
            dst = Path(root) / "dst.txt"
            dst.write_text("old-content", encoding="utf-8")
            module = self._enabled_local_module(root, allow_destructive=True)
            result = module.execute("copy", ["--overwrite", str(src), str(dst)])
            self.assert_true(result.success)
            self.assert_equal(dst.read_text(encoding="utf-8"), "new-content")

    # ---------- HELP / unknown action ----------

    def _test_help_lists_commands(self) -> None:
        fake = _FakeFileBackend()
        module = FileModule(config=_file_config(enabled=False), backend=fake)
        result = module.execute("help", [])
        self.assert_true(result.success)
        self.assert_true("file list" in result.message)
        self.assert_true("file delete" in result.message)

    def _test_unknown_action_returns_failure(self) -> None:
        fake = _FakeFileBackend()
        module = FileModule(config=_file_config(allowed_roots=["/tmp"]), backend=fake)
        result = module.execute("not-a-real-action", [])
        self.assert_false(result.success)

    # ---------- Backend failure translation ----------

    def _test_backend_failure_translated_to_failed_result(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            target = Path(root) / "a.txt"
            target.write_text("hi", encoding="utf-8")
            fake = _FakeFileBackend(
                files={str(target): "hi"},
                raise_on=frozenset({"exists"}),
                raise_message="simulated disk failure",
            )
            module = FileModule(config=_file_config(allowed_roots=[root]), backend=fake)
            result = module.execute("write", [str(target), "irrelevant"])
            self.assert_false(result.success)
            self.assert_true("simulated disk failure" in result.message)

    # ---------- Invalid path handling ----------

    def _test_invalid_path_produces_clean_failure(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            fake = _FakeFileBackend()
            module = FileModule(config=_file_config(allowed_roots=[root]), backend=fake)
            # A NUL byte is invalid in a filesystem path on every
            # supported platform and makes Path.resolve()/OS calls
            # raise -- must be translated cleanly, never crash.
            result = module.execute("read", ["bad\x00path"])
            self.assert_false(result.success)

    # ---------- CommandRouter integration ----------

    def _test_command_router_dispatch_matches_direct_execute(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            target = Path(root) / "dispatch-test.txt"
            target.write_text("hi", encoding="utf-8")
            module = self._enabled_local_module(root)
            router = CommandRouter()
            router.register(module)

            direct = module.execute("read", [str(target)])
            dispatched = router.dispatch(f"file read {target}")

            self.assert_equal(direct.success, dispatched.success)
            self.assert_equal(direct.message, dispatched.message)

    def _test_command_router_unaffected_by_other_modules(self) -> None:
        fake = _FakeFileBackend()
        module = FileModule(config=_file_config(allowed_roots=["/tmp"]), backend=fake)
        router = CommandRouter()
        router.register(module)

        result = router.dispatch("unknownmodule somecommand")
        self.assert_false(result.success)

    # ---------- Bootstrap wiring ----------

    def _test_bootstrap_config_defaults_file_disabled(self) -> None:
        config = _config_with({})
        self.assert_false(
            bool(config.get("file.enabled", False)),
            "'file.enabled' must default to false when entirely absent from config",
        )

    def _test_bootstrap_registers_file_namespace_even_when_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            directory = Path(tmp_dir)
            _write_file_bootstrap_config(directory, file_section="")
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                try:
                    bootstrap.initialize()
                    self.assert_true(
                        "file" in bootstrap.command_router.module_names,
                        "'file' namespace must be registered even when 'file.enabled' is absent/false",
                    )
                finally:
                    bootstrap.shutdown()

    def _test_bootstrap_file_actions_report_disabled_message(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            directory = Path(tmp_dir)
            _write_file_bootstrap_config(directory, file_section="")
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                try:
                    bootstrap.initialize()
                    result = bootstrap.command_router.dispatch("file list /tmp")
                    self.assert_false(result.success)
                    self.assert_true("disabled" in result.message.lower())
                finally:
                    bootstrap.shutdown()

    def _test_bootstrap_other_modules_unaffected_when_file_absent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            directory = Path(tmp_dir)
            _write_file_bootstrap_config(directory, file_section="")
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                try:
                    bootstrap.initialize()
                    other = bootstrap.command_router.dispatch("system version")
                    self.assert_true(other.success, "Other modules must be unaffected by EP-052 wiring")
                finally:
                    bootstrap.shutdown()

    # ---------- Shared helpers ----------

    def _enabled_local_module(self, root: str, allow_destructive: bool = False) -> FileModule:
        """Build a FileModule wired to a real LocalFileBackend, rooted at `root`."""
        return FileModule(
            config=_file_config(enabled=True, allow_destructive=allow_destructive, allowed_roots=[root]),
            backend=LocalFileBackend(),
        )
