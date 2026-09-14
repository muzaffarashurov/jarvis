from __future__ import annotations

from typing import Dict, List, Type

from src.testing.base_test import BaseTest


class TestRegistry:
    """
    Global registry of all available test suites.

    Multi-suite-per-name note (TestRegistry multi-suite collision repair):
    More than one test class may register under the same `NAME` (for
    example, EP039's `test_github_module.py` and
    `test_github_service.py` both register as `NAME = "EP039"`).
    `_tests` therefore maps each uppercased name to a *list* of every
    class registered under it, in registration order, rather than to a
    single class. Registering a second class under a name that is
    already in use no longer silently discards the first one -- both
    remain reachable via `get_all()`, and both are executed when
    `TestRunner` runs that name or runs everything via `all()`.

    `get()` is kept backward compatible: it returns the first class
    registered under a name (or `None` if nothing is registered),
    exactly as it always has for every name that only ever had one
    registrant (which is the overwhelming majority of names, including
    every name checked by identity elsewhere, e.g.
    `tests/EP036/test_background_worker_module.py`'s
    `TestRegistry.get("EP036") is BackgroundWorkerPoolTest`).
    """

    _tests: Dict[str, List[Type[BaseTest]]] = {}

    @classmethod
    def register(cls, test_class):
        key = test_class.NAME.upper()
        registered = cls._tests.setdefault(key, [])
        if test_class not in registered:
            registered.append(test_class)
        return test_class

    @classmethod
    def get(cls, name: str) -> Type[BaseTest] | None:
        registered = cls._tests.get(name.upper())
        return registered[0] if registered else None

    @classmethod
    def get_all(cls, name: str) -> List[Type[BaseTest]]:
        """Return every suite class registered under `name`, in
        registration order. Returns an empty list if nothing is
        registered under that name (never `None`), so callers can
        always safely iterate the result.
        """
        return list(cls._tests.get(name.upper(), []))

    @classmethod
    def names(cls) -> List[str]:
        return sorted(cls._tests.keys())

    @classmethod
    def all(cls) -> List[Type[BaseTest]]:
        """Return every registered suite class across every name, in
        deterministic (name, then registration) order. This includes
        *all* classes registered under a shared name -- previously
        this flattened to only the last-registered class per name,
        which meant `run_all()` silently skipped collided suites in
        exactly the same way single-name lookups via `get()` did.
        """
        result: List[Type[BaseTest]] = []
        for name in sorted(cls._tests.keys()):
            result.extend(cls._tests[name])
        return result