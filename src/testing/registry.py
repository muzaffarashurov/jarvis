from __future__ import annotations

from typing import Dict, List, Type

from src.testing.base_test import BaseTest


class TestRegistry:
    """
    Global registry of all available test suites.
    """

    _tests: Dict[str, Type[BaseTest]] = {}

    @classmethod
    def register(cls, test_class):
       cls._tests[test_class.NAME.upper()] = test_class
       return test_class

    @classmethod
    def get(cls, name: str) -> Type[BaseTest] | None:
        return cls._tests.get(name.upper())

    @classmethod
    def names(cls) -> List[str]:
        return sorted(cls._tests.keys())

    @classmethod
    def all(cls) -> List[Type[BaseTest]]:
        return [
            cls._tests[name]
            for name in sorted(cls._tests.keys())
        ]