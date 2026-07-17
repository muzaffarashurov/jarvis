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

        suite_class = TestRegistry.get(suite_name)

        if suite_class is None:
            raise ValueError(f"Unknown test suite: {suite_name}")

        logger.info(f"Running test suite: {suite_name}")

        suite = suite_class()

        started = time.perf_counter()

        result = suite.run()

        result.duration = time.perf_counter() - started

        TestReport.print(result)

        return result

    def run_all(self) -> list[TestResult]:

        results: list[TestResult] = []

        logger.info("Running all test suites.")

        for suite_class in TestRegistry.all():

            suite = suite_class()

            started = time.perf_counter()

            result = suite.run()

            result.duration = time.perf_counter() - started

            results.append(result)

        TestReport.print_summary(results)

        return results