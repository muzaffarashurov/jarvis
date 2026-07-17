from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class TestResult:
    """
    Stores execution result of a single test suite.
    """

    suite: str

    passed: int = 0
    failed: int = 0
    skipped: int = 0

    duration: float = 0.0

    errors: List[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return self.passed + self.failed + self.skipped

    @property
    def success(self) -> bool:
        return self.failed == 0

    def add_pass(self) -> None:
        self.passed += 1

    def add_fail(self, message: str) -> None:
        self.failed += 1
        self.errors.append(message)

    def add_skip(self) -> None:
        self.skipped += 1