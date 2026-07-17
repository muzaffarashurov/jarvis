from __future__ import annotations

from src.testing.result import TestResult


class TestReport:
    """
    Creates console reports for executed test suites.
    """

    @staticmethod
    def print(result: TestResult) -> None:

        print()
        print("=" * 50)
        print(f" Test Suite : {result.suite}")
        print("=" * 50)

        print(f"Passed : {result.passed}")
        print(f"Failed : {result.failed}")
        print(f"Skipped: {result.skipped}")
        print(f"Time   : {result.duration:.3f} sec")

        if result.errors:

            print()
            print("Errors:")

            for error in result.errors:
                print(f" - {error}")

        print("=" * 50)
        print()

    @staticmethod
    def print_summary(results: list[TestResult]) -> None:

        passed = sum(r.passed for r in results)
        failed = sum(r.failed for r in results)
        skipped = sum(r.skipped for r in results)

        duration = sum(r.duration for r in results)

        print()
        print("=" * 50)
        print(" Test Summary")
        print("=" * 50)

        print(f"Passed : {passed}")
        print(f"Failed : {failed}")
        print(f"Skipped: {skipped}")
        print(f"Time   : {duration:.3f} sec")

        print("=" * 50)
        print()