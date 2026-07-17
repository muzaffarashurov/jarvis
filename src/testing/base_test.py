from __future__ import annotations

from abc import ABC, abstractmethod

from src.testing.result import TestResult


class BaseTest(ABC):
    """
    Base class for every Jarvis test suite.
    """

    NAME = "Unnamed"

    def __init__(self) -> None:
        self.result = TestResult(self.NAME)

    @abstractmethod
    def run(self) -> TestResult:
        """
        Execute test suite.
        """
        raise NotImplementedError

    # ---------- Assertions ----------

    def assert_true(self, value: bool, message: str = "") -> None:
        if value:
            self.result.add_pass()
        else:
            self.result.add_fail(message or "Expected True")

    def assert_false(self, value: bool, message: str = "") -> None:
        self.assert_true(not value, message or "Expected False")

    def assert_equal(self, left, right, message: str = "") -> None:
        if left == right:
            self.result.add_pass()
        else:
            self.result.add_fail(
                message or f"{left!r} != {right!r}"
            )

    def assert_not_none(self, value, message: str = "") -> None:
        if value is not None:
            self.result.add_pass()
        else:
            self.result.add_fail(message or "Value is None")

    def skip(self) -> None:
        self.result.add_skip()