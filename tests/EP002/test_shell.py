"""Real engineering tests for EP002 – Interactive Shell / CommandRouter.

Validates CommandRouter registration, dispatch, and case-insensitive
module lookup using real CommandRouter and CommandResult objects.
"""

from __future__ import annotations

from src.core.command_router import CommandResult, CommandRouter
from src.testing.base_test import BaseTest
from src.testing.registry import TestRegistry


class _StubModule:
    """Minimal real CommandModule implementation used to exercise CommandRouter."""

    def __init__(self, name: str = "stub") -> None:
        self._name = name
        self.calls: list[tuple[str, list[str]]] = []

    @property
    def name(self) -> str:
        return self._name

    def execute(self, action: str, arguments: list[str]) -> CommandResult:
        self.calls.append((action, arguments))
        return CommandResult(success=True, message=f"executed:{action}")


@TestRegistry.register
class ShellTest(BaseTest):
    """Real tests covering CommandRouter behaviour (EP002)."""

    NAME = "EP002"

    def run(self):
        """Execute all CommandRouter checks and return the aggregated result."""
        self._test_router_creation()
        self._test_empty_router_has_zero_modules()
        self._test_register_module_increases_count()
        self._test_duplicate_registration_raises()
        self._test_unknown_module_returns_unsuccessful_result()
        self._test_blank_input_returns_unsuccessful_result()
        self._test_module_lookup_is_case_insensitive()
        self._test_dispatch_trims_surrounding_and_internal_whitespace()
        return self.result

    def _test_router_creation(self) -> None:
        """CommandRouter can be created."""
        router = CommandRouter()
        self.assert_not_none(router, "CommandRouter instance should not be None")

    def _test_empty_router_has_zero_modules(self) -> None:
        """A freshly created router contains zero registered modules."""
        router = CommandRouter()
        self.assert_equal(
            len(router.module_names), 0, "A new CommandRouter should have no modules"
        )

    def _test_register_module_increases_count(self) -> None:
        """Registering a module increases the module count by one."""
        router = CommandRouter()
        before = len(router.module_names)
        router.register(_StubModule("alpha"))
        after = len(router.module_names)
        self.assert_equal(after, before + 1, "Module count should increase by exactly one")
        self.assert_true(
            "alpha" in router.module_names, "Registered module name should be present"
        )

    def _test_duplicate_registration_raises(self) -> None:
        """Registering two modules with the same namespace raises ValueError."""
        router = CommandRouter()
        router.register(_StubModule("beta"))

        try:
            router.register(_StubModule("beta"))
        except ValueError:
            self.assert_true(True, "Duplicate registration correctly raised ValueError")
        else:
            self.assert_true(False, "Duplicate registration should have raised ValueError")

    def _test_unknown_module_returns_unsuccessful_result(self) -> None:
        """Dispatching to an unregistered module returns an unsuccessful CommandResult."""
        router = CommandRouter()
        result = router.dispatch("nosuchmodule help")
        self.assert_true(
            isinstance(result, CommandResult), "Dispatch should return a CommandResult"
        )
        self.assert_false(result.success, "Unknown module dispatch should not succeed")

    def _test_blank_input_returns_unsuccessful_result(self) -> None:
        """Dispatching blank input returns an unsuccessful CommandResult."""
        router = CommandRouter()
        result = router.dispatch("")
        self.assert_true(
            isinstance(result, CommandResult), "Dispatch should return a CommandResult"
        )
        self.assert_false(result.success, "Blank input should not succeed")

        whitespace_result = router.dispatch("   ")
        self.assert_false(whitespace_result.success, "Whitespace-only input should not succeed")

    def _test_module_lookup_is_case_insensitive(self) -> None:
        """Module lookup during dispatch is case insensitive."""
        router = CommandRouter()
        module = _StubModule("gamma")
        router.register(module)

        lower_result = router.dispatch("gamma status")
        upper_result = router.dispatch("GAMMA status")
        mixed_result = router.dispatch("GaMmA status")

        self.assert_true(lower_result.success, "Lowercase module name should dispatch")
        self.assert_true(upper_result.success, "Uppercase module name should dispatch")
        self.assert_true(mixed_result.success, "Mixed-case module name should dispatch")
        self.assert_equal(len(module.calls), 3, "Module.execute should be called three times")

    def _test_dispatch_trims_surrounding_and_internal_whitespace(self) -> None:
        """Dispatch tolerates leading/trailing spaces and repeated spacing.

        Whitespace handling is a frequent source of real bugs in command
        parsers, so it is exercised explicitly here rather than assumed.
        """
        router = CommandRouter()
        module = _StubModule("gamma")
        router.register(module)

        variants = [
            "gamma",
            "gamma ",
            "gamma      status",
            " gamma",
            " gamma ",
            "  gamma   status  ",
        ]
        for raw_input in variants:
            result = router.dispatch(raw_input)
            self.assert_true(
                result.success,
                f"dispatch({raw_input!r}) should succeed once whitespace is trimmed",
            )
        self.assert_equal(
            len(module.calls),
            len(variants),
            "Module.execute should be called once per whitespace variant",
        )
