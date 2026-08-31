"""Real engineering tests for EP-056 STEP 2 - Capability Registry.

Single combined test suite (NAME = "EP056"), following the same
precedent EP-043 through EP-055 already established.

Per `EP056_DESIGN.md` Section 7/17/Owner Decision D3, this module makes
no AI-provider call and has no resource/rate limit to test -- every
gate/argument-shape test here runs against fake `PluginService`/
`module_names` collaborators. Per Owner Decision D6, `capability
inject`'s Prompt Engine integration is tested against a real, unmodified
`PromptManager` (not a fake), mirroring EP-055's own real,
non-fake, temporary-directory-backed template tests rather than
mocking the one genuine integration surface this module has.

Covers:
    - Argument-shape validation (`capability list` rejects any
      argument; `capability inject` rejects missing text) -- rejected
      before any downstream call.
    - The `capability_registry.enabled` safety gate: every action is
      rejected while disabled, with zero downstream calls to
      `PluginService`/`module_names`/`PromptManager`; the action
      reaches its dependencies once enabled.
    - `capability list` positive-path: exact composed summary text
      against fake `PluginService`/`module_names` collaborators,
      including the empty-state case (zero running plugins, zero
      registered namespaces).
    - `capability inject` positive-path: a real, unmodified
      `PromptManager` is used, and the assembled `Prompt.rendered`
      text is asserted to contain both the composed Capability
      Context summary and the given user prompt text.
    - `capability inject` error translation: a real
      `PromptValidationError` (raised by the real `PromptManager` for
      an empty resulting prompt) is translated into a failed
      `CommandResult`, never an uncaught exception.
    - `CommandRouter` dispatch equivalence.
    - `Bootstrap` wiring: `capability_registry.enabled` defaults to
      false when entirely absent from config; the 'capability'
      namespace is registered with `CommandRouter` regardless of the
      flag's value; actions report the disabled message until the
      flag is set to true; other modules (including the pre-existing
      'plugin', 'reflect', and 'prompt' namespaces) are unaffected.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from src.bootstrap import Bootstrap
from src.core.ai.prompt_manager import PromptManager
from src.core.command_router import CommandRouter
from src.core.config import Config
from src.core.plugins.plugin import Plugin, PluginStatus
from src.skills.capability_registry.skill import HELP_TEXT, CapabilityRegistryModule
from src.testing.base_test import BaseTest
from src.testing.registry import TestRegistry
from tests.EP045.test_web_dashboard import (
    _MINIMAL_BOOTSTRAP_CONFIG_YAML,
    _ChdirGuard,
    _api_section,
)


# ---------- Fakes ----------


@dataclass
class _FakePluginService:
    """Deterministic, test-only stand-in for `PluginService`.

    Exposes only `running_plugins()`, matching the one method
    `CapabilityRegistryModule` actually calls.
    """

    plugins: list[Plugin]
    running_plugins_call_count: int = field(default=0, init=False)

    def running_plugins(self) -> list[Plugin]:
        self.running_plugins_call_count += 1
        return self.plugins


@dataclass
class _FakeModuleNames:
    """Deterministic, test-only stand-in for `CommandRouter.module_names`."""

    names: list[str]
    call_count: int = field(default=0, init=False)

    def __call__(self) -> list[str]:
        self.call_count += 1
        return self.names


def _config_with(overrides: dict) -> Config:
    """Build a Config whose in-memory data is exactly `overrides`."""
    config = Config(config_path=Path("unused.yaml"))
    config._data = overrides
    return config


def _capability_registry_config(*, enabled: bool = True) -> Config:
    """Build a Config with a 'capability_registry:' section for CapabilityRegistryModule tests."""
    return _config_with({"capability_registry": {"enabled": enabled}})


def _real_prompt_manager(*, max_prompt_size: int | None = None) -> PromptManager:
    """Build a real, minimal, unmodified PromptManager for the D6 integration test.

    Args:
        max_prompt_size: Optional override for 'prompt.max_prompt_size',
            used only to deliberately trigger a real
            `PromptValidationError` in
            `_test_inject_error_translated_to_failed_command_result`.
    """
    data: dict = {}
    if max_prompt_size is not None:
        data["prompt"] = {"max_prompt_size": max_prompt_size}
    return PromptManager(config=_config_with(data))


def _make_plugin(
    plugin_id: str,
    *,
    name: str = "Test Plugin",
    description: str = "A test plugin.",
    capabilities: tuple[str, ...] = (),
    status: PluginStatus = PluginStatus.RUNNING,
) -> Plugin:
    """Build a real `Plugin` object -- pure data, no side effects, safe to construct directly."""
    return Plugin(
        id=plugin_id,
        name=name,
        version="1.0.0",
        description=description,
        author="Test Author",
        capabilities=capabilities,
        status=status,
    )


def _write_capability_registry_bootstrap_config(directory: Path, capability_registry_section: str) -> None:
    """Write a minimal bootstrap config.yaml (EP-045's fixture) plus a 'capability_registry:' block."""
    config_dir = directory / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    base_yaml = _MINIMAL_BOOTSTRAP_CONFIG_YAML.format(
        api_section=_api_section(enabled=False, web_dashboard_dir=None)
    )
    (config_dir / "config.yaml").write_text(base_yaml + "\n" + capability_registry_section, encoding="utf-8")


@TestRegistry.register
class CapabilityRegistryTest(BaseTest):
    NAME = "EP056"

    def run(self):
        # ---------- Argument-shape validation ----------
        self._test_list_rejects_arguments()
        self._test_inject_rejects_no_arguments()

        # ---------- capability_registry.enabled gate ----------
        self._test_disabled_rejects_list_with_zero_downstream_calls()
        self._test_disabled_rejects_inject_with_zero_downstream_calls()
        self._test_enabled_true_allows_list_to_reach_dependencies()

        # ---------- capability list positive path ----------
        self._test_list_composes_plugin_and_namespace_summary()
        self._test_list_empty_state_reports_none_without_raising()

        # ---------- capability inject positive path (real PromptManager -- Owner Decision D6) ----------
        self._test_inject_returns_rendered_prompt_containing_summary_and_text()
        self._test_inject_error_translated_to_failed_command_result()

        # ---------- HELP / unknown action ----------
        self._test_help_lists_commands()
        self._test_unknown_action_returns_failure()

        # ---------- CommandRouter integration ----------
        self._test_command_router_dispatch_matches_direct_execute()

        # ---------- Bootstrap wiring ----------
        self._test_bootstrap_config_defaults_capability_registry_disabled()
        self._test_bootstrap_registers_capability_namespace_even_when_disabled()
        self._test_bootstrap_capability_actions_report_disabled_message()
        self._test_bootstrap_other_modules_unaffected_when_capability_registry_absent()

        # ---------- Real, enabled Bootstrap -> CommandRouter -> CapabilityRegistryModule
        # integration (Owner Decision D8, EP-056 STEP 4 -- proves
        # Finding 1's fix and prevents this exact wiring bug from
        # returning) ----------
        self._test_bootstrap_enabled_capability_list_succeeds_end_to_end()
        self._test_bootstrap_enabled_capability_inject_succeeds_end_to_end()
        self._test_bootstrap_enabled_capability_list_includes_later_registered_namespaces()

        return self.result

    # ---------- Shared helper ----------

    def _build_module(
        self,
        *,
        config: Config | None = None,
        plugins: list[Plugin] | None = None,
        names: list[str] | None = None,
        prompt_manager: PromptManager | None = None,
    ) -> tuple[CapabilityRegistryModule, _FakePluginService, _FakeModuleNames]:
        if config is None:
            config = _capability_registry_config()
        plugin_service = _FakePluginService(plugins=plugins if plugins is not None else [])
        module_names = _FakeModuleNames(names=names if names is not None else [])
        module = CapabilityRegistryModule(
            config=config,
            plugin_service=plugin_service,
            module_names=module_names,
            prompt_manager=prompt_manager if prompt_manager is not None else _real_prompt_manager(),
        )
        return module, plugin_service, module_names

    # ---------- Argument-shape validation ----------

    def _test_list_rejects_arguments(self) -> None:
        module, plugin_service, module_names = self._build_module()
        result = module.execute("list", ["unexpected"])
        self.assert_false(result.success)
        self.assert_equal(plugin_service.running_plugins_call_count, 0)
        self.assert_equal(module_names.call_count, 0)

    def _test_inject_rejects_no_arguments(self) -> None:
        module, plugin_service, module_names = self._build_module()
        result = module.execute("inject", [])
        self.assert_false(result.success)
        self.assert_equal(plugin_service.running_plugins_call_count, 0)
        self.assert_equal(module_names.call_count, 0)

    # ---------- capability_registry.enabled gate ----------

    def _test_disabled_rejects_list_with_zero_downstream_calls(self) -> None:
        module, plugin_service, module_names = self._build_module(config=_capability_registry_config(enabled=False))
        result = module.execute("list", [])
        self.assert_false(result.success)
        self.assert_true("disabled" in result.message.lower())
        self.assert_equal(plugin_service.running_plugins_call_count, 0)
        self.assert_equal(module_names.call_count, 0)

    def _test_disabled_rejects_inject_with_zero_downstream_calls(self) -> None:
        module, plugin_service, module_names = self._build_module(config=_capability_registry_config(enabled=False))
        result = module.execute("inject", ["hello"])
        self.assert_false(result.success)
        self.assert_true("disabled" in result.message.lower())
        self.assert_equal(plugin_service.running_plugins_call_count, 0)
        self.assert_equal(module_names.call_count, 0)

    def _test_enabled_true_allows_list_to_reach_dependencies(self) -> None:
        module, plugin_service, module_names = self._build_module(config=_capability_registry_config(enabled=True))
        result = module.execute("list", [])
        self.assert_true(result.success)
        self.assert_equal(plugin_service.running_plugins_call_count, 1)
        self.assert_equal(module_names.call_count, 1)

    # ---------- capability list positive path ----------

    def _test_list_composes_plugin_and_namespace_summary(self) -> None:
        plugins = [
            _make_plugin("invoice_automation", name="Invoice Automation", description="Automates invoices.",
                         capabilities=("invoice.automation",)),
            _make_plugin("no_tags_plugin", name="No Tags", description="Has no declared tags.", capabilities=()),
        ]
        module, _, _ = self._build_module(plugins=plugins, names=["desktop", "reflect"])
        result = module.execute("list", [])
        self.assert_true(result.success)
        self.assert_true("invoice_automation" in result.message)
        self.assert_true("Invoice Automation" in result.message)
        self.assert_true("Automates invoices." in result.message)
        self.assert_true("invoice.automation" in result.message)
        self.assert_true("no_tags_plugin" in result.message)
        self.assert_true("(none declared)" in result.message)
        self.assert_true("desktop" in result.message)
        self.assert_true("reflect" in result.message)

    def _test_list_empty_state_reports_none_without_raising(self) -> None:
        module, _, _ = self._build_module(plugins=[], names=[])
        result = module.execute("list", [])
        self.assert_true(result.success)
        self.assert_true("(none currently running)" in result.message)
        self.assert_true("(none)" in result.message)

    # ---------- capability inject positive path (real PromptManager) ----------

    def _test_inject_returns_rendered_prompt_containing_summary_and_text(self) -> None:
        plugins = [_make_plugin("demo_plugin", name="Demo", description="Demo plugin.", capabilities=("demo.tag",))]
        module, _, _ = self._build_module(plugins=plugins, names=["prompt"])
        result = module.execute("inject", ["please", "help", "me"])
        self.assert_true(result.success)
        self.assert_true("please help me" in result.message)
        self.assert_true("demo_plugin" in result.message)
        self.assert_true("demo.tag" in result.message)
        self.assert_true("prompt" in result.message)

    def _test_inject_error_translated_to_failed_command_result(self) -> None:
        """A real PromptValidationError (prompt exceeds max_prompt_size) must be caught, never raised."""
        plugins = [
            _make_plugin(
                "verbose_plugin",
                name="Verbose Plugin",
                description="A plugin with a deliberately long description used only to "
                "push the assembled prompt over a tiny, test-only 'prompt.max_prompt_size'.",
                capabilities=("verbose.tag.one", "verbose.tag.two"),
            )
        ]
        tiny_prompt_manager = _real_prompt_manager(max_prompt_size=10)
        module, _, _ = self._build_module(plugins=plugins, names=["desktop"], prompt_manager=tiny_prompt_manager)
        result = module.execute("inject", ["a", "reasonably", "long", "request", "for", "testing"])
        self.assert_false(result.success)
        self.assert_true("capability inject failed" in result.message.lower())
        self.assert_true("max" in result.message.lower())

    # ---------- HELP / unknown action ----------

    def _test_help_lists_commands(self) -> None:
        module, _, _ = self._build_module()
        result = module.execute("help", [])
        self.assert_true(result.success)
        self.assert_true("capability list" in result.message)
        self.assert_equal(result.message, HELP_TEXT)

    def _test_unknown_action_returns_failure(self) -> None:
        module, _, _ = self._build_module()
        result = module.execute("save", [])
        self.assert_false(result.success)

    # ---------- CommandRouter integration ----------

    def _test_command_router_dispatch_matches_direct_execute(self) -> None:
        module, _, _ = self._build_module()
        router = CommandRouter()
        router.register(module)
        direct = module.execute("help", [])
        dispatched = router.dispatch("capability help")
        self.assert_equal(direct.success, dispatched.success)
        self.assert_equal(direct.message, dispatched.message)

    # ---------- Bootstrap wiring ----------

    def _test_bootstrap_config_defaults_capability_registry_disabled(self) -> None:
        config = _config_with({})
        self.assert_false(
            bool(config.get("capability_registry.enabled", False)),
            "'capability_registry.enabled' must default to false when entirely absent from config",
        )

    def _test_bootstrap_registers_capability_namespace_even_when_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            directory = Path(tmp_dir)
            _write_capability_registry_bootstrap_config(directory, capability_registry_section="")
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                try:
                    bootstrap.initialize()
                    self.assert_true(
                        "capability" in bootstrap.command_router.module_names,
                        "'capability' namespace must be registered even when "
                        "'capability_registry.enabled' is absent/false",
                    )
                finally:
                    bootstrap.shutdown()

    def _test_bootstrap_capability_actions_report_disabled_message(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            directory = Path(tmp_dir)
            _write_capability_registry_bootstrap_config(directory, capability_registry_section="")
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                try:
                    bootstrap.initialize()
                    result = bootstrap.command_router.dispatch("capability list")
                    self.assert_false(result.success)
                    self.assert_true("disabled" in result.message.lower())
                finally:
                    bootstrap.shutdown()

    def _test_bootstrap_other_modules_unaffected_when_capability_registry_absent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            directory = Path(tmp_dir)
            _write_capability_registry_bootstrap_config(directory, capability_registry_section="")
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                try:
                    bootstrap.initialize()
                    other = bootstrap.command_router.dispatch("system version")
                    self.assert_true(other.success, "Other modules must be unaffected by EP-056 wiring")
                    plugin_result = bootstrap.command_router.dispatch("plugin help")
                    self.assert_true(
                        plugin_result.success,
                        "The pre-existing 'plugin' namespace (EP-010) must be unaffected by EP-056 wiring",
                    )
                    reflect_result = bootstrap.command_router.dispatch("reflect help")
                    self.assert_true(
                        reflect_result.success,
                        "The pre-existing 'reflect' namespace (EP-054) must be unaffected by EP-056 wiring",
                    )
                    prompt_result = bootstrap.command_router.dispatch("prompt help")
                    self.assert_true(
                        prompt_result.success,
                        "The pre-existing 'prompt' namespace (EP-055) must be unaffected by EP-056 wiring",
                    )
                finally:
                    bootstrap.shutdown()

    # ---------- Real, enabled Bootstrap -> CommandRouter -> CapabilityRegistryModule
    # integration (Owner Decision D8, EP-056 STEP 4) ----------
    #
    # These three tests deliberately exercise the REAL, fully-wired
    # Bootstrap with 'capability_registry.enabled: true' -- not a fake
    # ProviderManager/PluginService/module_names collaborator -- because
    # that is precisely the combination the STEP 3 audit found no
    # existing test exercised (EP056_ARCHITECTURE_AUDIT.md Finding 1):
    # a fake `module_names` callable, however faithfully it implements
    # CapabilityRegistryModule's own documented contract, cannot
    # reproduce a defect that lives entirely in what `bootstrap.py`
    # actually wires up. Only a real `CommandRouter.module_names`
    # (a `@property`) flowing through the real Bootstrap construction
    # path can prove the fix holds.

    def _test_bootstrap_enabled_capability_list_succeeds_end_to_end(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            directory = Path(tmp_dir)
            _write_capability_registry_bootstrap_config(
                directory, capability_registry_section="capability_registry:\n  enabled: true\n"
            )
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                try:
                    bootstrap.initialize()
                    result = bootstrap.command_router.dispatch("capability list")
                    self.assert_true(
                        result.success,
                        "'capability list' must succeed through the real, enabled Bootstrap wiring "
                        "(EP056_ARCHITECTURE_AUDIT.md Finding 1 -- must not raise TypeError: "
                        "'list' object is not callable)",
                    )
                    self.assert_true("Capability Registry (EP-056):" in result.message)
                    self.assert_true("Built-in commands:" in result.message)
                finally:
                    bootstrap.shutdown()

    def _test_bootstrap_enabled_capability_inject_succeeds_end_to_end(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            directory = Path(tmp_dir)
            _write_capability_registry_bootstrap_config(
                directory, capability_registry_section="capability_registry:\n  enabled: true\n"
            )
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                try:
                    bootstrap.initialize()
                    result = bootstrap.command_router.dispatch("capability inject please help me plan my day")
                    self.assert_true(
                        result.success,
                        "'capability inject' must succeed through the real, enabled Bootstrap wiring "
                        "(EP056_ARCHITECTURE_AUDIT.md Finding 1 -- must not raise TypeError: "
                        "'list' object is not callable)",
                    )
                    self.assert_true("please help me plan my day" in result.message)
                    self.assert_true("Capability Registry (EP-056):" in result.message)
                finally:
                    bootstrap.shutdown()

    def _test_bootstrap_enabled_capability_list_includes_later_registered_namespaces(self) -> None:
        """Regression guard: `module_names` must be evaluated live, at dispatch time, not at
        CapabilityRegistryModule construction time.

        `scheduler`/`telegram`/`test` are all registered *after*
        `capability` in `src/bootstrap.py`. If `module_names` were ever
        captured as a snapshot at construction time again (e.g. a
        regression that replaces the `lambda: router.module_names` fix
        with `list(router.module_names)` at the registration call site,
        which would be callable-free and therefore also fail differently,
        or otherwise re-introduces eager evaluation), this test fails by
        showing the summary is stale/incomplete -- catching not just a
        crash, but a silent staleness regression a crash-only test would
        miss.
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            directory = Path(tmp_dir)
            _write_capability_registry_bootstrap_config(
                directory, capability_registry_section="capability_registry:\n  enabled: true\n"
            )
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                try:
                    bootstrap.initialize()
                    result = bootstrap.command_router.dispatch("capability list")
                    self.assert_true(result.success)
                    for later_namespace in ("scheduler", "telegram", "test"):
                        self.assert_true(
                            later_namespace in result.message,
                            f"'{later_namespace}' (registered after 'capability' in bootstrap.py) "
                            "must appear in the live-evaluated summary",
                        )
                    self.assert_true(
                        "capability" in result.message,
                        "'capability' should also see itself in the live summary (harmless self-inclusion)",
                    )
                finally:
                    bootstrap.shutdown()
