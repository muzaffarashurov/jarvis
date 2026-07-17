"""Real engineering tests for EP001 – Foundation.

Validates Bootstrap construction and internal state, Config loading
(against the real project config file, without hardcoding domain
values), Logger availability, the real ASCII banner rendering, and
exception-free application initialization.
"""

from __future__ import annotations

import contextlib
import io
import traceback
from pathlib import Path

import yaml

from src.bootstrap import Bootstrap, PROJECT_ROOT
from src.core.config import Config, ConfigError
from src.core.logger import Logger
from src.testing.base_test import BaseTest
from src.testing.registry import TestRegistry
from src.utils.constants import APP_NAME, APP_VERSION


@TestRegistry.register
class FoundationTest(BaseTest):
    """Real tests covering the Foundation layer (EP001)."""

    NAME = "EP001"

    def run(self):
        """Execute all Foundation checks and return the aggregated result."""
        self._test_bootstrap_creation_and_initial_state()
        self._test_configuration_loads()
        self._test_logger_exists()
        self._test_banner_actually_renders()
        self._test_version_string_not_empty()
        self._test_initialization_does_not_throw()
        return self.result

    def _test_bootstrap_creation_and_initial_state(self) -> None:
        """Bootstrap can be created and its real pre-run() state is correct.

        Before run() executes, Bootstrap must expose a live EventBus but
        must NOT yet have a config, orchestrator, command_router or shell –
        those are only populated once run() completes. Checking this real
        state is stronger than a bare not-None check on the instance.
        """
        bootstrap = Bootstrap()
        self.assert_not_none(bootstrap, "Bootstrap instance should not be None")

        self.assert_not_none(
            bootstrap.event_bus, "Bootstrap should expose an initialized EventBus"
        )
        self.assert_true(
            bootstrap.config is None, "config should be None before run() is called"
        )
        self.assert_true(
            bootstrap.orchestrator is None,
            "orchestrator should be None before run() is called",
        )
        self.assert_true(
            bootstrap.command_router is None,
            "command_router should be None before run() is called",
        )
        self.assert_true(
            bootstrap.shell is None, "shell should be None before run() is called"
        )

    def _test_configuration_loads(self) -> None:
        """Configuration loads correctly from the real config.yaml file.

        Values are not hardcoded (e.g. asserting app.name == "JARVIS"),
        since that would break the moment the project is renamed. Instead
        we verify the loader's real behaviour: it must produce a non-empty
        mapping whose content matches what is actually on disk, and
        `app.name` must resolve to a real, non-empty string.
        """
        config_path = PROJECT_ROOT / "config" / "config.yaml"
        config = Config(config_path)

        try:
            config.load()
        except ConfigError as exc:
            self.assert_true(False, f"Configuration failed to load: {exc}")
            return

        self.assert_true(
            isinstance(config.data, dict) and len(config.data) > 0,
            "Loaded configuration data should be a non-empty mapping",
        )

        with config_path.open("r", encoding="utf-8") as handle:
            raw_yaml = yaml.safe_load(handle)
        self.assert_equal(
            config.data,
            raw_yaml,
            "Config.load() should faithfully reproduce the on-disk YAML content",
        )

        app_name = config.get("app.name")
        self.assert_true(
            isinstance(app_name, str) and app_name.strip() != "",
            "app.name should resolve to a non-empty string, whatever its value is",
        )

    def _test_logger_exists(self) -> None:
        """Logger object exists and exposes standard logging methods."""
        raw_logger = Logger.get_logger()
        self.assert_not_none(raw_logger, "Logger.get_logger() should not return None")
        for method_name in ("info", "debug", "warning", "error"):
            self.assert_true(
                hasattr(raw_logger, method_name) and callable(getattr(raw_logger, method_name)),
                f"Logger should expose a callable '{method_name}' method",
            )

    def _test_banner_actually_renders(self) -> None:
        """The banner is actually built and printed, not just named.

        Jarvis has no separate Banner class; the real rendering logic
        lives in Bootstrap._render_ascii_logo() and Bootstrap._print_banner().
        We call both directly and inspect their real output instead of
        only checking that the underlying constants are non-empty strings.
        """
        logo = Bootstrap._render_ascii_logo(APP_NAME)
        self.assert_true(
            isinstance(logo, str) and len(logo.strip()) > 0,
            "Rendered ASCII logo should be a non-empty string",
        )
        self.assert_true(
            logo.count("\n") > 0, "Rendered ASCII logo should span multiple lines"
        )

        bootstrap = Bootstrap()
        captured = io.StringIO()
        with contextlib.redirect_stdout(captured):
            bootstrap._print_banner()
        printed = captured.getvalue()

        self.assert_true(len(printed.strip()) > 0, "Banner printing should produce output")
        self.assert_true(
            APP_VERSION in printed, "Printed banner should include the real version string"
        )

    def _test_version_string_not_empty(self) -> None:
        """Version string is not empty."""
        self.assert_true(
            isinstance(APP_VERSION, str) and len(APP_VERSION.strip()) > 0,
            "APP_VERSION should be a non-empty string",
        )

    def _test_initialization_does_not_throw(self) -> None:
        """Application initialization (Bootstrap construction) does not throw.

        Any unexpected exception is captured (with its traceback attached
        to the failure message) rather than left to propagate, because the
        test runner has no per-suite isolation: an uncaught exception here
        would abort `test all` for EP002/EP003 as well, not just EP001.
        """
        try:
            Bootstrap(project_root=Path(PROJECT_ROOT))
        except Exception:  # noqa: BLE001 - deliberately captured, see docstring
            self.assert_true(
                False, f"Bootstrap initialization raised:\n{traceback.format_exc()}"
            )
        else:
            self.assert_true(True, "Bootstrap initialization completed without exceptions")
