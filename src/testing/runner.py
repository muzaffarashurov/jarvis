from __future__ import annotations

import time

from loguru import logger

from src.testing.registry import TestRegistry
from src.testing.report import TestReport
from src.testing.result import TestResult


class TestRunner:
    """
    Executes registered Jarvis test suites.
    """

    def list(self) -> list[str]:
        return TestRegistry.names()

    def run(self, suite_name: str) -> TestResult:

        suite_classes = TestRegistry.get_all(suite_name)

        if not suite_classes:
            raise ValueError(f"Unknown test suite: {suite_name}")

        logger.info(
            f"Running test suite: {suite_name} "
            f"({len(suite_classes)} suite class(es) registered under this name)"
        )

        aggregate = TestResult(suite=suite_name)

        for suite_class in suite_classes:

            logger.info(
                f"  -> executing {suite_class.__module__}.{suite_class.__qualname__} "
                f"(registered as {suite_name})"
            )

            suite = suite_class()

            started = time.perf_counter()

            result = suite.run()

            result.duration = time.perf_counter() - started

            TestReport.print(result)

            aggregate.passed += result.passed
            aggregate.failed += result.failed
            aggregate.skipped += result.skipped
            aggregate.duration += result.duration
            aggregate.errors.extend(result.errors)

        if len(suite_classes) > 1:
            # More than one suite shares this name: print an explicit
            # combined total in addition to each suite's own report
            # above, so it is visible that every one of them ran.
            print(f"Combined total for {suite_name} ({len(suite_classes)} suites):")
            TestReport.print(aggregate)

        return aggregate

    def run_all(self) -> list[TestResult]:

        results: list[TestResult] = []

        logger.info("Running all test suites.")

        for suite_class in TestRegistry.all():

            suite_name = suite_class.NAME

            print(f"Running {suite_name}")

            suite = suite_class()

            started = time.perf_counter()

            result = suite.run()

            result.duration = time.perf_counter() - started

            print(f"Finished {suite_name} (elapsed {result.duration:.3f} sec)")

            results.append(result)

        TestReport.print_summary(results)

        return results