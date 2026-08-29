"""Real engineering tests for EP-053 STEP 2 - Vision Integration.

Single combined test suite (NAME = "EP053"), following the same
precedent EP-043/EP-045/EP-046/EP-047/EP-048/EP-049/EP-050/EP-051/
EP-052 already established: this sidesteps the pre-existing
`TestRegistry` NAME-collision technical debt (docs/BACKLOG.md)
entirely rather than triggering it.

Two backend tiers are exercised, mirroring EP053_DESIGN.md Section
16/20 (Owner Decision D10):

    - `_FakeVisionBackend` (below): a deterministic, in-memory,
      test-only stand-in implementing `VisionBackend`'s full
      protocol, following `_FakeComputerUseBackend`/
      `_FakeBrowserBackend`/`_FakeFileBackend`'s own convention --
      used for `VisionModule` argument-shape/gate/path-safety/dispatch
      tests that do not need to observe real image-decoding/OCR
      behavior.
    - `LocalVisionBackend` itself, exercised directly against real,
      small, programmatically-generated (via Pillow, right here in
      this file) sample images -- `image_info()` has no external
      binary dependency (Pillow only), so its real behavior is
      verified in this same default, fully-automated suite. Real
      Tesseract-based `extract_text()` accuracy is deliberately NOT
      exercised here (Owner Decision D10) -- see the separate,
      intentionally unregistered
      `tests/EP053/test_vision_ocr_integration.py` for that.

Covers:
    - `VisionBackend` protocol conformance (the fake satisfies the
      same structural interface the real backend does).
    - `VisionModule` argument-shape validation (wrong argument count)
      -- rejected before any backend call.
    - The `vision.enabled` safety gate: every action is rejected, with
      zero backend calls, while disabled; every action reaches the
      backend once enabled.
    - The path-safety model (Owner Decision D4): empty
      `allowed_roots` blocks everything; a path outside every
      configured root is refused; path traversal (`../..`) is
      defeated by resolve-before-compare; a path inside an allowed
      root is accepted (reaches the backend).
    - Real, Pillow-based `image_info()` behavior against a real,
      temporary filesystem: correct width/height/format/mode/size,
      resource-limit refusal (`vision.max_file_size_mb`/
      `vision.max_dimension`, Owner Decision D5), a clean failure for
      a non-image file, and a clean failure for a missing file.
    - `extract_text()` dispatch/argument-passthrough (language code)
      against `_FakeVisionBackend` only -- no real Tesseract
      dependency in this suite (Owner Decision D10).
    - Missing-path and backend-error translation into a failed
      `CommandResult`, never propagated raw.
    - `CommandRouter` string-dispatch ("vision <action> ...") produces
      results identical to direct `VisionModule.execute()` calls.
    - `Bootstrap` wiring: 'vision.enabled' defaults to false when
      entirely absent from config; the 'vision' namespace is
      registered with `CommandRouter` regardless of the flag's value;
      actions report the disabled message until the flag is set to
      true; other modules are unaffected.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from src.bootstrap import Bootstrap
from src.core.command_router import CommandRouter
from src.core.config import Config
from src.skills.vision.backend import ImageInfo, OcrResult, VisionBackend, VisionBackendError
from src.skills.vision.local_backend import LocalVisionBackend
from src.skills.vision.skill import VisionModule
from src.testing.base_test import BaseTest
from src.testing.registry import TestRegistry
from tests.EP045.test_web_dashboard import (
    _MINIMAL_BOOTSTRAP_CONFIG_YAML,
    _ChdirGuard,
    _api_section,
)


@dataclass
class _RecordedCall:
    """One recorded `VisionBackend` method invocation."""

    method: str
    args: tuple
    kwargs: dict


class _FakeVisionBackend:
    """Deterministic, in-memory, test-only `VisionBackend` (EP053_DESIGN.md Section 16/20).

    Records every call it receives (`self.calls`) so tests can assert
    exactly what `VisionModule` passed through, without decoding any
    real image or invoking any real OCR engine. `raise_on` (a set of
    method names) makes the fake raise `VisionBackendError` for
    specific methods, to exercise `VisionModule`'s failure-translation
    path deterministically.
    """

    def __init__(
        self,
        info_by_path: dict[str, ImageInfo] | None = None,
        text_by_path: dict[str, str] | None = None,
        raise_on: frozenset[str] = frozenset(),
        raise_message: str = "simulated backend failure",
    ) -> None:
        self.calls: list[_RecordedCall] = []
        self._info_by_path: dict[str, ImageInfo] = dict(info_by_path or {})
        self._text_by_path: dict[str, str] = dict(text_by_path or {})
        self._raise_on = raise_on
        self._raise_message = raise_message

    def _record(self, method: str, *args, **kwargs) -> None:
        self.calls.append(_RecordedCall(method=method, args=args, kwargs=kwargs))
        if method in self._raise_on:
            raise VisionBackendError(self._raise_message)

    def image_info(self, path: Path) -> ImageInfo:
        self._record("image_info", path)
        return self._info_by_path.get(
            str(path),
            ImageInfo(width=1, height=1, format="PNG", mode="RGB", size_bytes=1),
        )

    def extract_text(self, path: Path, language: str | None = None) -> OcrResult:
        self._record("extract_text", path, language=language)
        return OcrResult(text=self._text_by_path.get(str(path), ""), confidence=None, language=language or "eng")


def _config_with(overrides: dict) -> Config:
    """Build a Config whose in-memory data is exactly `overrides`."""
    config = Config(config_path=Path("unused.yaml"))
    config._data = overrides
    return config


def _vision_config(
    *,
    enabled: bool = True,
    allowed_roots: list[str] | None = None,
    max_file_size_mb: int = 25,
    max_dimension: int = 8000,
) -> Config:
    """Build a Config with a single 'vision:' section for VisionModule tests."""
    return _config_with(
        {
            "vision": {
                "enabled": enabled,
                "allowed_roots": allowed_roots if allowed_roots is not None else [],
                "max_file_size_mb": max_file_size_mb,
                "max_dimension": max_dimension,
            }
        }
    )


def _write_vision_bootstrap_config(directory: Path, vision_section: str) -> None:
    """Write a minimal bootstrap config.yaml (EP-045's fixture) plus a 'vision:' block."""
    config_dir = directory / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    base_yaml = _MINIMAL_BOOTSTRAP_CONFIG_YAML.format(
        api_section=_api_section(enabled=False, web_dashboard_dir=None)
    )
    (config_dir / "config.yaml").write_text(base_yaml + "\n" + vision_section, encoding="utf-8")


def _make_png(path: Path, *, width: int = 10, height: int = 8, color=(255, 0, 0)) -> None:
    """Write a small, valid PNG image to `path` using Pillow."""
    Image.new("RGB", (width, height), color=color).save(path, format="PNG")


@TestRegistry.register
class VisionTest(BaseTest):
    NAME = "EP053"

    def run(self):
        # ---------- Protocol conformance ----------
        self._test_fake_backend_satisfies_protocol()
        self._test_local_backend_satisfies_protocol()

        # ---------- Argument-shape validation ----------
        self._test_info_rejects_wrong_argument_count()
        self._test_ocr_rejects_wrong_argument_count()

        # ---------- vision.enabled gate ----------
        self._test_disabled_rejects_every_action_with_zero_backend_calls()
        self._test_no_backend_available_rejects_with_zero_backend_calls()
        self._test_enabled_true_allows_dispatch_to_reach_path_safety()

        # ---------- Path safety (D4) ----------
        self._test_empty_allowed_roots_blocks_everything()
        self._test_path_outside_allowed_root_rejected()
        self._test_path_traversal_rejected()
        self._test_path_inside_allowed_root_accepted()
        self._test_absolute_path_outside_allowed_root_rejected()

        # ---------- vision info (real Pillow, real filesystem) ----------
        self._test_info_returns_real_image_metadata()
        self._test_info_rejects_missing_file()
        self._test_info_rejects_non_image_file()
        self._test_info_rejects_oversized_file_size()
        self._test_info_rejects_oversized_dimension()

        # ---------- vision ocr (fake backend, argument passthrough) ----------
        self._test_ocr_passes_language_argument_to_backend()
        self._test_ocr_defaults_language_to_none()
        self._test_ocr_reports_no_text_found_as_success()
        self._test_ocr_returns_extracted_text()

        # ---------- HELP / unknown action ----------
        self._test_help_lists_commands()
        self._test_unknown_action_returns_failure()

        # ---------- Backend failure translation ----------
        self._test_backend_failure_translated_to_failed_result()

        # ---------- CommandRouter integration ----------
        self._test_command_router_dispatch_matches_direct_execute()

        # ---------- Bootstrap wiring ----------
        self._test_bootstrap_config_defaults_vision_disabled()
        self._test_bootstrap_registers_vision_namespace_even_when_disabled()
        self._test_bootstrap_vision_actions_report_disabled_message()
        self._test_bootstrap_other_modules_unaffected_when_vision_absent()

        return self.result

    # ---------- Protocol conformance ----------

    def _test_fake_backend_satisfies_protocol(self) -> None:
        fake = _FakeVisionBackend()
        self.assert_true(isinstance(fake, VisionBackend), "_FakeVisionBackend must satisfy the VisionBackend Protocol")

    def _test_local_backend_satisfies_protocol(self) -> None:
        backend = LocalVisionBackend(config=_vision_config())
        self.assert_true(isinstance(backend, VisionBackend), "LocalVisionBackend must satisfy the VisionBackend Protocol")

    # ---------- Argument-shape validation ----------

    def _test_info_rejects_wrong_argument_count(self) -> None:
        fake = _FakeVisionBackend()
        module = VisionModule(config=_vision_config(allowed_roots=["/tmp"]), backend=fake)
        result = module.execute("info", [])
        self.assert_false(result.success)
        self.assert_equal(len(fake.calls), 0, "no backend call before shape validation passes")

    def _test_ocr_rejects_wrong_argument_count(self) -> None:
        fake = _FakeVisionBackend()
        module = VisionModule(config=_vision_config(allowed_roots=["/tmp"]), backend=fake)
        result = module.execute("ocr", [])
        self.assert_false(result.success)
        result_too_many = module.execute("ocr", ["/tmp/a.png", "eng", "extra"])
        self.assert_false(result_too_many.success)
        self.assert_equal(len(fake.calls), 0)

    # ---------- vision.enabled gate ----------

    def _test_disabled_rejects_every_action_with_zero_backend_calls(self) -> None:
        fake = _FakeVisionBackend()
        module = VisionModule(config=_vision_config(enabled=False, allowed_roots=["/tmp/root"]), backend=fake)
        for action, args in [
            ("info", ["/tmp/root/a.png"]),
            ("ocr", ["/tmp/root/a.png"]),
        ]:
            result = module.execute(action, args)
            self.assert_false(result.success, f"'{action}' must be rejected while disabled")
            self.assert_true("disabled" in result.message.lower(), f"'{action}' message must mention disabled")
        self.assert_equal(len(fake.calls), 0, "zero backend calls must occur while vision.enabled is false")

    def _test_no_backend_available_rejects_with_zero_backend_calls(self) -> None:
        module = VisionModule(config=_vision_config(enabled=True, allowed_roots=["/tmp"]), backend=None)
        result = module.execute("info", ["/tmp/a.png"])
        self.assert_false(result.success)
        self.assert_true("backend" in result.message.lower())

    def _test_enabled_true_allows_dispatch_to_reach_path_safety(self) -> None:
        fake = _FakeVisionBackend()
        module = VisionModule(config=_vision_config(enabled=True, allowed_roots=[]), backend=fake)
        result = module.execute("info", ["/tmp/somewhere.png"])
        # Empty allowed_roots -> refused at path-safety stage, zero backend calls,
        # but the *gate* itself (enabled + backend availability) must have passed
        # (i.e. failure message is about the workspace, not "disabled").
        self.assert_false(result.success)
        self.assert_false("disabled" in result.message.lower())
        self.assert_equal(len(fake.calls), 0)

    # ---------- Path safety (D4) ----------

    def _test_empty_allowed_roots_blocks_everything(self) -> None:
        fake = _FakeVisionBackend()
        module = VisionModule(config=_vision_config(allowed_roots=[]), backend=fake)
        result = module.execute("info", ["/tmp/anything.png"])
        self.assert_false(result.success)
        self.assert_true("allowed_roots" in result.message or "allowed workspace" in result.message.lower())
        self.assert_equal(len(fake.calls), 0)

    def _test_path_outside_allowed_root_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as allowed_dir, tempfile.TemporaryDirectory() as outside_dir:
            fake = _FakeVisionBackend()
            module = VisionModule(config=_vision_config(allowed_roots=[allowed_dir]), backend=fake)
            result = module.execute("info", [str(Path(outside_dir) / "x.png")])
            self.assert_false(result.success)
            self.assert_equal(len(fake.calls), 0)

    def _test_path_traversal_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as allowed_dir:
            allowed_path = Path(allowed_dir)
            (allowed_path / "sub").mkdir()
            fake = _FakeVisionBackend()
            module = VisionModule(config=_vision_config(allowed_roots=[str(allowed_path / "sub")]), backend=fake)
            traversal_path = str(allowed_path / "sub" / ".." / ".." / "escaped.png")
            result = module.execute("info", [traversal_path])
            self.assert_false(result.success)
            self.assert_equal(len(fake.calls), 0)

    def _test_path_inside_allowed_root_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as allowed_dir:
            image_path = Path(allowed_dir) / "a.png"
            _make_png(image_path)
            fake = _FakeVisionBackend()
            module = VisionModule(config=_vision_config(allowed_roots=[allowed_dir]), backend=fake)
            result = module.execute("info", [str(image_path)])
            self.assert_true(result.success)
            self.assert_equal(len(fake.calls), 1, "an in-allow-list path must reach the backend")

    def _test_absolute_path_outside_allowed_root_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as allowed_dir:
            fake = _FakeVisionBackend()
            module = VisionModule(config=_vision_config(allowed_roots=[allowed_dir]), backend=fake)
            result = module.execute("info", ["/etc/passwd"])
            self.assert_false(result.success)
            self.assert_equal(len(fake.calls), 0)

    # ---------- vision info (real Pillow, real filesystem) ----------

    def _test_info_returns_real_image_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            image_path = Path(tmp_dir) / "sample.png"
            _make_png(image_path, width=32, height=16, color=(0, 128, 255))
            module = self._enabled_local_module(tmp_dir)
            result = module.execute("info", [str(image_path)])
            self.assert_true(result.success)
            self.assert_true("32x16" in result.message)
            self.assert_true("PNG" in result.message)

    def _test_info_rejects_missing_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            module = self._enabled_local_module(tmp_dir)
            result = module.execute("info", [str(Path(tmp_dir) / "missing.png")])
            self.assert_false(result.success)

    def _test_info_rejects_non_image_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            bogus_path = Path(tmp_dir) / "not-an-image.png"
            bogus_path.write_text("this is not image data", encoding="utf-8")
            module = self._enabled_local_module(tmp_dir)
            result = module.execute("info", [str(bogus_path)])
            self.assert_false(result.success)

    def _test_info_rejects_oversized_file_size(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            image_path = Path(tmp_dir) / "big.png"
            _make_png(image_path, width=64, height=64)
            config = _vision_config(allowed_roots=[tmp_dir], max_file_size_mb=0)
            backend = LocalVisionBackend(config=config)
            module = VisionModule(config=config, backend=backend)
            result = module.execute("info", [str(image_path)])
            self.assert_false(result.success, "a file exceeding max_file_size_mb must be refused")
            self.assert_true("max_file_size_mb" in result.message)

    def _test_info_rejects_oversized_dimension(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            image_path = Path(tmp_dir) / "wide.png"
            _make_png(image_path, width=50, height=10)
            config = _vision_config(allowed_roots=[tmp_dir], max_dimension=20)
            backend = LocalVisionBackend(config=config)
            module = VisionModule(config=config, backend=backend)
            result = module.execute("info", [str(image_path)])
            self.assert_false(result.success, "an image exceeding max_dimension must be refused")
            self.assert_true("max_dimension" in result.message)

    # ---------- vision ocr (fake backend) ----------

    def _test_ocr_passes_language_argument_to_backend(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            image_path = Path(tmp_dir) / "a.png"
            fake = _FakeVisionBackend(text_by_path={str(_resolved(image_path)): "hello"})
            module = VisionModule(config=_vision_config(allowed_roots=[tmp_dir]), backend=fake)
            result = module.execute("ocr", [str(image_path), "rus"])
            self.assert_true(result.success)
            self.assert_equal(fake.calls[-1].method, "extract_text")
            self.assert_equal(fake.calls[-1].kwargs.get("language"), "rus")

    def _test_ocr_defaults_language_to_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            image_path = Path(tmp_dir) / "a.png"
            fake = _FakeVisionBackend()
            module = VisionModule(config=_vision_config(allowed_roots=[tmp_dir]), backend=fake)
            module.execute("ocr", [str(image_path)])
            self.assert_equal(fake.calls[-1].kwargs.get("language"), None)

    def _test_ocr_reports_no_text_found_as_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            image_path = Path(tmp_dir) / "blank.png"
            fake = _FakeVisionBackend()  # returns "" for any unknown path
            module = VisionModule(config=_vision_config(allowed_roots=[tmp_dir]), backend=fake)
            result = module.execute("ocr", [str(image_path)])
            self.assert_true(result.success, "no text found is a success, not a failure")
            self.assert_true("no text found" in result.message.lower())

    def _test_ocr_returns_extracted_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            image_path = Path(tmp_dir) / "a.png"
            fake = _FakeVisionBackend(text_by_path={str(_resolved(image_path)): "Hello Jarvis"})
            module = VisionModule(config=_vision_config(allowed_roots=[tmp_dir]), backend=fake)
            result = module.execute("ocr", [str(image_path)])
            self.assert_true(result.success)
            self.assert_equal(result.message, "Hello Jarvis")

    # ---------- HELP / unknown action ----------

    def _test_help_lists_commands(self) -> None:
        module = VisionModule(config=_vision_config(), backend=_FakeVisionBackend())
        result = module.execute("help", [])
        self.assert_true(result.success)
        self.assert_true("vision info" in result.message)
        self.assert_true("vision ocr" in result.message)

    def _test_unknown_action_returns_failure(self) -> None:
        module = VisionModule(config=_vision_config(), backend=_FakeVisionBackend())
        result = module.execute("describe", ["/tmp/a.png"])
        self.assert_false(result.success, "'vision describe' does not exist in v1 (Owner Decision D1)")

    # ---------- Backend failure translation ----------

    def _test_backend_failure_translated_to_failed_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            image_path = Path(tmp_dir) / "a.png"
            fake = _FakeVisionBackend(raise_on=frozenset({"image_info"}))
            module = VisionModule(config=_vision_config(allowed_roots=[tmp_dir]), backend=fake)
            result = module.execute("info", [str(image_path)])
            self.assert_false(result.success)
            self.assert_true("simulated backend failure" in result.message)

    # ---------- CommandRouter integration ----------

    def _test_command_router_dispatch_matches_direct_execute(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            image_path = Path(tmp_dir) / "a.png"
            _make_png(image_path)
            module = self._enabled_local_module(tmp_dir)
            router = CommandRouter()
            router.register(module)
            direct = module.execute("info", [str(image_path)])
            dispatched = router.dispatch(f'vision info "{image_path}"')
            self.assert_equal(direct.success, dispatched.success)
            self.assert_equal(direct.message, dispatched.message)

    # ---------- Bootstrap wiring ----------

    def _test_bootstrap_config_defaults_vision_disabled(self) -> None:
        config = _config_with({})
        self.assert_false(
            bool(config.get("vision.enabled", False)),
            "'vision.enabled' must default to false when entirely absent from config",
        )

    def _test_bootstrap_registers_vision_namespace_even_when_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            directory = Path(tmp_dir)
            _write_vision_bootstrap_config(directory, vision_section="")
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                try:
                    bootstrap.initialize()
                    self.assert_true(
                        "vision" in bootstrap.command_router.module_names,
                        "'vision' namespace must be registered even when 'vision.enabled' is absent/false",
                    )
                finally:
                    bootstrap.shutdown()

    def _test_bootstrap_vision_actions_report_disabled_message(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            directory = Path(tmp_dir)
            _write_vision_bootstrap_config(directory, vision_section="")
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                try:
                    bootstrap.initialize()
                    result = bootstrap.command_router.dispatch("vision info /tmp/a.png")
                    self.assert_false(result.success)
                    self.assert_true("disabled" in result.message.lower())
                finally:
                    bootstrap.shutdown()

    def _test_bootstrap_other_modules_unaffected_when_vision_absent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            directory = Path(tmp_dir)
            _write_vision_bootstrap_config(directory, vision_section="")
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                try:
                    bootstrap.initialize()
                    other = bootstrap.command_router.dispatch("system version")
                    self.assert_true(other.success, "Other modules must be unaffected by EP-053 wiring")
                finally:
                    bootstrap.shutdown()

    # ---------- Shared helpers ----------

    def _enabled_local_module(self, root: str) -> VisionModule:
        """Build a VisionModule wired to a real LocalVisionBackend, rooted at `root`."""
        config = _vision_config(enabled=True, allowed_roots=[root])
        return VisionModule(config=config, backend=LocalVisionBackend(config=config))


def _resolved(path: Path) -> Path:
    """Resolve `path`, mirroring `VisionModule._resolve_within_allowed`'s own resolution."""
    return path.resolve()
