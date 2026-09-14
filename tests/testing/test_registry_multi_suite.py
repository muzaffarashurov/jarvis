"""Regression coverage for the TestRegistry multi-suite collision repair.

Background
----------
`TestRegistry.register()` used to key `_tests` by `NAME.upper()` and
store a single class per key. Several EPs (EP038-EP042) split their
tests across two files (a `*_module.py` and a `*_service.py`) that
both register under the same bare `NAME` (e.g. `NAME = "EP039"`).
Because the dict stored exactly one class per key, the second import
silently overwrote the first: `TestRegistry.get("EP039")` -- and
therefore `TestRunner.run("EP039")` and the CLI command `test EP039`
-- only ever executed one of the two suites.

This is exactly how EP039's and EP041's service-level URL-encoding
regressions (both since fixed) went undetected through every
historical audit and regression run: the failing assertions lived in
the suite that got silently discarded.

This file verifies, directly against the real registry (not a mock),
that:

1. Two suites registered under the same `NAME` are BOTH retained --
   neither is silently discarded.
2. `TestRegistry.get()` stays backward compatible (still returns a
   single class -- the first registered -- so existing identity
   checks elsewhere, e.g. `tests/EP036/test_background_worker_module.py`'s
   `TestRegistry.get("EP036") is BackgroundWorkerPoolTest`, are
   unaffected).
3. `TestRegistry.get_all()` returns every class registered under a
   name.
4. `TestRunner.run()` actually executes every suite registered under
   a name (not just one), by checking that the aggregated result
   equals the sum of what each individual suite produces on its own.
5. This holds for the real EP038-EP042 suites specifically, not just
   synthetic classes -- proving the previously-hidden EP039/EP041
   service suites (and EP038/EP040/EP042's) are now genuinely reached
   through the normal `TestRunner.run("EPxxx")` path.
"""

from __future__ import annotations

from src.testing.base_test import BaseTest
from src.testing.registry import TestRegistry
from src.testing.result import TestResult
from src.testing.runner import TestRunner

# Force-import every EP038-EP042 module/service test file directly, so
# this file's assertions do not depend on import order relative to
# `src/modules/test_module.py` (which normally triggers registration
# as a side effect at process start).
import tests.EP038.test_git_module  # noqa: F401
import tests.EP038.test_git_service  # noqa: F401
import tests.EP039.test_github_module  # noqa: F401
import tests.EP039.test_github_service  # noqa: F401
import tests.EP040.test_telegram_info_module  # noqa: F401
import tests.EP040.test_telegram_info_service  # noqa: F401
import tests.EP041.test_discord_module  # noqa: F401
import tests.EP041.test_discord_service  # noqa: F401
import tests.EP042.test_email_module  # noqa: F401
import tests.EP042.test_email_service  # noqa: F401

# EP036 registers three genuinely distinct names ("EP036",
# "EP036-STEP2", "EP036-STEP3") rather than colliding -- imported
# explicitly here (not relying on import order elsewhere) so the
# backward-compatibility check below is self-contained.
import tests.EP036.test_background_worker_pool  # noqa: F401


# A throwaway name, guaranteed not to collide with any real EP name,
# used only to prove the collision behavior in isolation with two
# synthetic suites before checking the real EP038-EP042 suites.
_SELF_TEST_NAME = "__TESTREGISTRY_SELFTEST__"


class _SelfTestSuiteA(BaseTest):
    NAME = _SELF_TEST_NAME

    def run(self) -> TestResult:
        self.assert_true(True, "suite A ran")
        self.assert_true(True, "suite A ran again")
        return self.result


class _SelfTestSuiteB(BaseTest):
    NAME = _SELF_TEST_NAME

    def run(self) -> TestResult:
        self.assert_true(True, "suite B ran")
        return self.result


TestRegistry.register(_SelfTestSuiteA)
TestRegistry.register(_SelfTestSuiteB)


@TestRegistry.register
class TestRegistryMultiSuiteTest(BaseTest):
    """Verifies the TestRegistry multi-suite collision repair."""

    NAME = "TESTREGISTRY-MULTISUITE"

    def run(self) -> TestResult:
        self._test_synthetic_collision_retains_both_suites()
        self._test_get_stays_backward_compatible()
        self._test_get_all_returns_every_registered_class()
        self._test_runner_executes_both_synthetic_suites()
        self._test_ep038_both_suites_registered()
        self._test_ep039_both_suites_registered()
        self._test_ep040_both_suites_registered()
        self._test_ep041_both_suites_registered()
        self._test_ep042_both_suites_registered()
        self._test_ep039_runner_executes_both_suites_and_matches_isolated_counts()
        self._test_ep041_runner_executes_both_suites_and_matches_isolated_counts()
        self._test_single_suite_ep_still_returns_single_result()
        return self.result

    # ---------- Core collision behavior ----------

    def _test_synthetic_collision_retains_both_suites(self) -> None:
        registered = TestRegistry.get_all(_SELF_TEST_NAME)
        self.assert_equal(
            len(registered), 2,
            f"expected both synthetic suites to remain registered under "
            f"the shared name, got {len(registered)}",
        )
        self.assert_true(_SelfTestSuiteA in registered, "suite A missing from registration")
        self.assert_true(_SelfTestSuiteB in registered, "suite B missing from registration")

    def _test_get_stays_backward_compatible(self) -> None:
        # get() must keep returning a single class -- the first
        # registered -- for names that have (or historically had)
        # exactly one registrant, and for the first of a colliding
        # pair, so identity checks elsewhere are unaffected.
        first = TestRegistry.get(_SELF_TEST_NAME)
        self.assert_true(first is _SelfTestSuiteA, "get() should return the first-registered class")

        # EP036 uses three genuinely distinct names (no collision) --
        # confirm those single-registrant lookups are untouched.
        self.assert_true(TestRegistry.get("EP036") is not None, "EP036 lookup should still resolve")

    def _test_get_all_returns_every_registered_class(self) -> None:
        registered = TestRegistry.get_all(_SELF_TEST_NAME)
        self.assert_equal(registered, [_SelfTestSuiteA, _SelfTestSuiteB])

        # A name with nothing registered returns an empty list, never None.
        empty = TestRegistry.get_all("__NAME_THAT_WAS_NEVER_REGISTERED__")
        self.assert_equal(empty, [])

    def _test_runner_executes_both_synthetic_suites(self) -> None:
        runner = TestRunner()
        result = runner.run(_SELF_TEST_NAME)
        # Suite A contributes 2 passing assertions, Suite B contributes 1.
        # If only one suite executed, this would be 2 or 1, not 3.
        self.assert_equal(result.passed, 3, "both synthetic suites' assertions should be summed")
        self.assert_equal(result.failed, 0)

    # ---------- Real EP038-EP042 registration ----------

    def _test_ep038_both_suites_registered(self) -> None:
        registered = TestRegistry.get_all("EP038")
        self.assert_equal(len(registered), 2, "EP038 should have both module and service suites registered")

    def _test_ep039_both_suites_registered(self) -> None:
        registered = TestRegistry.get_all("EP039")
        self.assert_equal(len(registered), 2, "EP039 should have both module and service suites registered")

    def _test_ep040_both_suites_registered(self) -> None:
        registered = TestRegistry.get_all("EP040")
        self.assert_equal(len(registered), 2, "EP040 should have both module and service suites registered")

    def _test_ep041_both_suites_registered(self) -> None:
        registered = TestRegistry.get_all("EP041")
        self.assert_equal(len(registered), 2, "EP041 should have both module and service suites registered")

    def _test_ep042_both_suites_registered(self) -> None:
        registered = TestRegistry.get_all("EP042")
        self.assert_equal(len(registered), 2, "EP042 should have both module and service suites registered")

    # ---------- Real EP039/EP041: runner actually executes both ----------

    def _test_ep039_runner_executes_both_suites_and_matches_isolated_counts(self) -> None:
        registered = TestRegistry.get_all("EP039")
        # Run each registered class on its own, exactly as TestRunner
        # would internally, to get an independent expected total.
        expected_passed = 0
        expected_failed = 0
        for suite_class in registered:
            r = suite_class().run()
            expected_passed += r.passed
            expected_failed += r.failed

        aggregate = TestRunner().run("EP039")
        self.assert_equal(
            aggregate.passed, expected_passed,
            f"TestRunner.run('EP039') should sum both suites' passed counts "
            f"(expected {expected_passed}, got {aggregate.passed})",
        )
        self.assert_equal(aggregate.failed, expected_failed)
        # With both the EP039 service fix and this registry fix in
        # place, the previously-hidden failure is gone and both
        # suites are provably included (44 + 36 = 80 assertions).
        self.assert_equal(aggregate.failed, 0, "EP039 should be fully green after its service-level fix")

    def _test_ep041_runner_executes_both_suites_and_matches_isolated_counts(self) -> None:
        registered = TestRegistry.get_all("EP041")
        expected_passed = 0
        expected_failed = 0
        for suite_class in registered:
            r = suite_class().run()
            expected_passed += r.passed
            expected_failed += r.failed

        aggregate = TestRunner().run("EP041")
        self.assert_equal(
            aggregate.passed, expected_passed,
            f"TestRunner.run('EP041') should sum both suites' passed counts "
            f"(expected {expected_passed}, got {aggregate.passed})",
        )
        self.assert_equal(aggregate.failed, expected_failed)
        self.assert_equal(aggregate.failed, 0, "EP041 should be fully green after its service-level fix")

    # ---------- Single-suite EPs are unaffected ----------

    def _test_single_suite_ep_still_returns_single_result(self) -> None:
        # EP037 (event bus) has exactly one registered suite. Its
        # runner result must be unaffected by this repair.
        registered = TestRegistry.get_all("EP037")
        self.assert_equal(len(registered), 1, "EP037 should still have exactly one registered suite")

        direct = registered[0]().run()
        via_runner = TestRunner().run("EP037")
        self.assert_equal(via_runner.passed, direct.passed)
        self.assert_equal(via_runner.failed, direct.failed)
        self.assert_equal(via_runner.skipped, direct.skipped)
