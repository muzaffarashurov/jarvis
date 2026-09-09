"""EP-068 test suite: CommandRouter Dispatch-Level Sensitive Argument
Log Redaction.

**Revision 2** (following the STEP 3 FAIL / EP068-B1 BLOCKER recorded
immutably in `docs/architecture/audits/EP068_ARCHITECTURE_AUDIT.md`
and the resulting design revision in `EP068_DESIGN.md`). This suite
is *extended*, not replaced, per that audit's own EP068-L1
recommendation ("the suite be extended, not replaced") -- every
Revision 1 test below remains, with only the log-wording assertions
updated to match the revised, narrower log format (`action` and
`str(exc)` are no longer part of either changed log line).

Covers, per `EP068_DESIGN.md` (Revision 2) Section 9:
    1. Successful dispatch: a distinctive sentinel argument does not
       reach the log via `CommandRouter.dispatch()`'s success-path log
       line; the log line now contains only `module_name` (D2/D3
       revised -- `action` is no longer logged at all).
    2. Module-exception dispatch: the same sentinel does not reach the
       log via the exception-path log line, while the returned
       `CommandResult.message` is confirmed *unchanged* -- it still
       echoes the full raw input, exactly as before this EP (D4) --
       proving this is a logging-only fix, not a response-content
       redaction.
    3. Ordinary, non-sensitive commands still dispatch exactly as
       before, including a bare module-only command with no action.
    4. EP-065's malformed-quoting branch (`except ValueError`) is
       confirmed byte-for-byte unaffected (D6): unchanged message,
       unchanged log wording, no raw input in either.
    5. The pre-existing "Unknown module: ..." branch is confirmed
       unaffected (D5) -- and, per D12/EP068-M1, deliberately left
       out of this EP's own two log statements' scope.
    6. Logging severity (`ERROR` for the exception path, `INFO` for
       the success path) is unchanged -- only message content changed.
    7. **(Revision 2, new)** A sentinel placed in the *action* position
       (not `arguments`) -- the exact shape that caused EP068-B1 --
       does not reach either log line, on both the success and
       exception variants, including a direct reproduction against the
       real, registered `TestModule`.
    8. **(Revision 2, new)** A sentinel embedded inside a module's own
       exception *message* text does not reach the exception log line;
       only the exception's class name (`type(exc).__name__`) appears
       in its place.
    9. **(Revision 2, new)** A sentinel placed in the *module-name*
       position (unregistered module) reaches only the pre-existing,
       out-of-scope "Unknown module" log line -- never either of
       `dispatch()`'s own two EP-068 log statements -- proving D12/
       EP068-M1 remains correctly deferred and unaffected.

Self-contained per this repository's own per-EP test convention (no
import from `tests/EP061/` through `tests/EP067/`) -- the local
fixtures below are independent, EP-068-owned copies of the kind of
real `CommandModule` stubs `tests/EP065/test_command_router_malformed_input.py`
already uses for the same real `CommandRouter`. The real, registered
`TestModule` (`src/modules/test_module.py`) is also used directly for
the literal EP068-B1 reproduction (test 7), matching the shape the
independent audit used.
"""

from __future__ import annotations

from loguru import logger

from src.core.command_router import CommandResult, CommandRouter
from src.testing.base_test import BaseTest
from src.testing.registry import TestRegistry

# `TestModule` (src/modules/test_module.py) is imported lazily, inside
# the test method that needs it (test 7 below), rather than at module
# scope here. `src/modules/test_module.py` itself imports *this* file
# (for EP068 test registration, per the established convention) before
# its own `TestModule` class is defined -- a module-level import here
# would therefore be a circular import. By the time any test actually
# *runs*, `src.modules.test_module` has already finished importing, so
# a local, in-function import is safe.

# ================= Local fixtures (independent of other tests/EP0XX/) =================


class _RecordingModule:
    """Minimal, real `CommandModule` implementation -- records every call."""

    def __init__(self, name: str = "stub") -> None:
        self._name = name
        self.calls: list[tuple[str, list[str]]] = []

    @property
    def name(self) -> str:
        return self._name

    def execute(self, action: str, arguments: list[str]) -> CommandResult:
        self.calls.append((action, arguments))
        return CommandResult(success=True, message=f"executed:{action}")


class _RaisingModule:
    """A `CommandModule` whose `execute()` always raises.

    The exception message is deliberately generic and never echoes
    `arguments` -- a module's own exception message is that module's
    own responsibility (`EP068_DESIGN.md` D3), not something this EP
    changes or relies on. This lets the test isolate exactly what
    `CommandRouter.dispatch()` itself adds to the log.
    """

    def __init__(self, name: str = "boom") -> None:
        self._name = name
        self.calls: list[tuple[str, list[str]]] = []

    @property
    def name(self) -> str:
        return self._name

    def execute(self, action: str, arguments: list[str]) -> CommandResult:
        self.calls.append((action, arguments))
        raise RuntimeError("simulated module defect")


def _capture_logs() -> tuple[list[str], int]:
    """Attach a fresh loguru sink capturing formatted messages.

    Returns the list that will be appended to, and the sink id (to be
    removed with `logger.remove(sink_id)` when the caller is done).
    """
    lines: list[str] = []
    sink_id = logger.add(lambda message: lines.append(message.record["message"]), level="DEBUG")
    return lines, sink_id


@TestRegistry.register
class CommandRouterLogRedactionTest(BaseTest):
    """EP-068 regression suite (`NAME = "EP068"`)."""

    NAME = "EP068"

    def run(self):
        self._test_success_path_redacts_sensitive_argument()
        self._test_exception_path_redacts_sensitive_argument_but_preserves_returned_message()
        self._test_ordinary_command_dispatches_normally()
        self._test_module_only_command_has_no_trailing_space_artifact()
        self._test_malformed_quoting_path_unchanged()
        self._test_unknown_module_path_unchanged()
        self._test_logging_severity_unchanged()
        self._test_safe_metadata_still_logged_for_non_sensitive_command()
        self._test_action_position_sentinel_redacted_success_path()
        self._test_action_position_sentinel_redacted_exception_path()
        self._test_ep068_b1_literal_reproduction_via_real_test_module()
        self._test_exception_message_text_never_logged()
        self._test_module_name_position_sentinel_only_reaches_unknown_module_line()
        return self.result

    # ---------- 1. Successful dispatch ----------

    def _test_success_path_redacts_sensitive_argument(self) -> None:
        sentinel = "EP068_SECRET_SENTINEL_9f1c3a7d"
        router = CommandRouter()
        module = _RecordingModule("stub")
        router.register(module)

        lines, sink_id = _capture_logs()
        try:
            result = router.dispatch(f"stub speak {sentinel}")
        finally:
            logger.remove(sink_id)

        self.assert_true(result.success, "expected the stub command to succeed")
        self.assert_equal(result.message, "executed:speak")
        self.assert_equal(module.calls, [("speak", [sentinel])])

        joined = "\n".join(lines)
        self.assert_false(
            sentinel in joined,
            "the sensitive sentinel argument must never appear in any log line",
        )
        self.assert_true(
            any(line == "Command executed: stub" for line in lines),
            "expected the redacted 'Command executed: <module_name>' log line "
            "(Revision 2: action is no longer logged at all)",
        )
        self.assert_false(
            any("speak" in line for line in lines),
            "the action token must never appear in the success log either, "
            "per the Revision 2 security invariant",
        )

    # ---------- 2. Module exception path ----------

    def _test_exception_path_redacts_sensitive_argument_but_preserves_returned_message(
        self,
    ) -> None:
        sentinel = "EP068_SECRET_SENTINEL_4b2e9f10"
        router = CommandRouter()
        module = _RaisingModule("boom")
        router.register(module)

        raw_input = f"boom detonate {sentinel}"
        lines, sink_id = _capture_logs()
        try:
            result = router.dispatch(raw_input)
        finally:
            logger.remove(sink_id)

        # D4: the returned CommandResult.message is completely
        # unchanged by this EP -- it still echoes the full raw input,
        # exactly as before. This is a logging-only fix.
        self.assert_false(result.success)
        self.assert_equal(
            result.message,
            f"Internal error while executing '{raw_input.strip()}'.",
        )
        self.assert_true(sentinel in result.message)

        joined = "\n".join(lines)
        self.assert_false(
            sentinel in joined,
            "the sensitive sentinel argument must never appear in any log line, "
            "even though it is present in the returned CommandResult.message",
        )
        self.assert_true(
            any(line == "Error executing 'boom': RuntimeError" for line in lines),
            "expected the redacted 'Error executing '<module_name>': "
            "<ExceptionTypeName>' log line (Revision 2: action and str(exc) "
            f"are no longer logged); actual lines: {lines!r}",
        )
        self.assert_false(
            any("detonate" in line for line in lines),
            "the action token must never appear in the exception log either, "
            "per the Revision 2 security invariant",
        )
        self.assert_false(
            any("simulated module defect" in line for line in lines),
            "the module's own exception message text must no longer be logged "
            "(Revision 2: only the exception's type name is logged, since a "
            "module's exception message can itself embed unvalidated, "
            "user-controlled action content -- see EP068-B1)",
        )

    # ---------- 3. Ordinary command behavior ----------

    def _test_ordinary_command_dispatches_normally(self) -> None:
        router = CommandRouter()
        module = _RecordingModule("stub")
        router.register(module)

        result = router.dispatch("stub status")
        self.assert_true(result.success)
        self.assert_equal(result.message, "executed:status")
        self.assert_equal(module.calls, [("status", [])])

    def _test_module_only_command_has_no_trailing_space_artifact(self) -> None:
        router = CommandRouter()
        module = _RecordingModule("stub")
        router.register(module)

        lines, sink_id = _capture_logs()
        try:
            result = router.dispatch("stub")
        finally:
            logger.remove(sink_id)

        self.assert_true(result.success)
        self.assert_equal(module.calls, [("", [])])
        self.assert_true(
            any(line == "Command executed: stub" for line in lines),
            "expected no trailing space when 'action' is empty "
            f"(actual lines: {lines!r})",
        )

    # ---------- 4. EP-065 malformed-quoting path unchanged ----------

    def _test_malformed_quoting_path_unchanged(self) -> None:
        router = CommandRouter()
        lines, sink_id = _capture_logs()
        try:
            result = router.dispatch('system status "oops')
        finally:
            logger.remove(sink_id)

        self.assert_false(result.success)
        self.assert_true(result.message.startswith("Invalid command syntax:"))
        self.assert_false(
            '"oops' in result.message,
            "the malformed-quoting message must still never echo raw input (D6)",
        )
        joined = "\n".join(lines)
        self.assert_true(
            any("Failed to parse command input:" in line for line in lines),
            "expected EP-065's own unchanged log line to still fire",
        )
        self.assert_false(
            "oops" in joined,
            "the malformed-quoting log line must still never echo raw input (D6)",
        )

    # ---------- 5. Unknown module path unchanged ----------

    def _test_unknown_module_path_unchanged(self) -> None:
        router = CommandRouter()
        lines, sink_id = _capture_logs()
        try:
            result = router.dispatch("totally_unregistered_module some args")
        finally:
            logger.remove(sink_id)

        self.assert_false(result.success)
        self.assert_true("Unknown module: totally_unregistered_module" in result.message)
        self.assert_true(
            any(
                line == "Unknown module: totally_unregistered_module"
                for line in lines
            ),
            "expected the pre-existing 'Unknown module: <name>' log line, unchanged (D5)",
        )

    # ---------- 6. Logging severity unchanged ----------

    def _test_logging_severity_unchanged(self) -> None:
        router = CommandRouter()
        router.register(_RecordingModule("stub"))
        router.register(_RaisingModule("boom"))

        records: list[tuple[str, str]] = []
        sink_id = logger.add(
            lambda message: records.append(
                (message.record["level"].name, message.record["message"])
            ),
            level="DEBUG",
        )
        try:
            router.dispatch("stub status")
            router.dispatch("boom detonate")
        finally:
            logger.remove(sink_id)

        success_levels = [
            level for level, msg in records if msg.startswith("Command executed:")
        ]
        error_levels = [
            level for level, msg in records if msg.startswith("Error executing")
        ]
        self.assert_true(success_levels and all(lvl == "INFO" for lvl in success_levels))
        self.assert_true(error_levels and all(lvl == "ERROR" for lvl in error_levels))

    # ---------- Safe metadata still logged ----------

    def _test_safe_metadata_still_logged_for_non_sensitive_command(self) -> None:
        router = CommandRouter()
        router.register(_RecordingModule("stub"))

        lines, sink_id = _capture_logs()
        try:
            router.dispatch("stub status")
        finally:
            logger.remove(sink_id)

        # Revision 2: module_name alone remains visible (it is gated by
        # the registered-module lookup, D2 revised); action is no
        # longer logged at all, even for an entirely non-sensitive,
        # harmless command (D8 revised) -- CommandRouter has no way to
        # distinguish a harmless action from a sensitive one, so it now
        # excludes action uniformly.
        self.assert_true(
            any(line == "Command executed: stub" for line in lines),
            f"expected module_name to remain visible in the log "
            f"even for an entirely non-sensitive command; actual lines: {lines!r}",
        )
        self.assert_false(
            any("status" in line for line in lines),
            "action must no longer appear in the log, even when harmless (D8 revised)",
        )

    # ---------- 7. (Revision 2) Sentinel in action position ----------

    def _test_action_position_sentinel_redacted_success_path(self) -> None:
        """The exact success-path shape from the audit's follow-up probe:
        a two-token command (module + one free-text token, no separate
        `arguments`) where the sentinel lands in `action`, not
        `arguments`. This must not appear in the success log line.
        """
        sentinel = "EP068B1_ACTION_SUCCESS_7c4d1e2a"
        router = CommandRouter()
        module = _RecordingModule("stub2")
        router.register(module)

        lines, sink_id = _capture_logs()
        try:
            result = router.dispatch(f"stub2 {sentinel}")
        finally:
            logger.remove(sink_id)

        self.assert_true(result.success)
        self.assert_equal(module.calls, [(sentinel.lower(), [])])

        joined = "\n".join(lines)
        self.assert_false(
            sentinel in joined or sentinel.lower() in joined,
            "a sentinel in the action position must never reach the "
            "success-path log line (EP068-B1 regression)",
        )
        self.assert_true(
            any(line == "Command executed: stub2" for line in lines),
            f"expected only 'Command executed: <module_name>'; actual lines: {lines!r}",
        )

    def _test_action_position_sentinel_redacted_exception_path(self) -> None:
        """Same shape, but the module raises using the action token
        (mirroring `TestModule`'s real behavior) -- the shape that
        produced EP068-B1 on the exception path.
        """

        class _RaisesUsingAction:
            def __init__(self) -> None:
                self._name = "stub3"

            @property
            def name(self) -> str:
                return self._name

            def execute(self, action: str, arguments: list[str]) -> CommandResult:
                raise ValueError(f"Unknown thing: {action.upper()}")

        sentinel = "EP068B1_ACTION_EXCEPTION_9a3f7b21"
        router = CommandRouter()
        router.register(_RaisesUsingAction())

        lines, sink_id = _capture_logs()
        try:
            result = router.dispatch(f"stub3 {sentinel}")
        finally:
            logger.remove(sink_id)

        self.assert_false(result.success)
        # D4 (unchanged): the returned message still echoes raw input.
        self.assert_true(sentinel in result.message)

        joined = "\n".join(lines)
        self.assert_false(
            sentinel in joined or sentinel.lower() in joined or sentinel.upper() in joined,
            "a sentinel in the action position must never reach the "
            "exception-path log line, whether via 'action' or via the "
            "module's own exception message text (EP068-B1 regression)",
        )
        self.assert_true(
            any(line == "Error executing 'stub3': ValueError" for line in lines),
            f"expected only 'Error executing '<module_name>': <ExceptionTypeName>'; "
            f"actual lines: {lines!r}",
        )

    def _test_ep068_b1_literal_reproduction_via_real_test_module(self) -> None:
        """The literal EP068-B1 reproduction from the STEP 3 audit
        (Section 9, Probe F), against the real, currently-registered
        `TestModule` -- not a stand-in. Proves the exact previously-
        exploited path is now closed.

        Audit reproduction:
            dispatch("test AuditRealLeakViaTestModule2026XYZ")
            -> log contained the sentinel twice (via `action` and via
               `str(exc)`).
        """
        from src.modules.test_module import TestModule  # local import, see header note

        sentinel = "AuditEP068B1_e91f4c6d2a"
        router = CommandRouter()
        router.register(TestModule())

        lines, sink_id = _capture_logs()
        try:
            result = router.dispatch(f"test {sentinel}")
        finally:
            logger.remove(sink_id)

        self.assert_false(result.success)
        # D4 (unchanged): the returned message still echoes raw input.
        self.assert_true(sentinel in result.message)

        joined = "\n".join(lines)
        self.assert_false(
            sentinel in joined or sentinel.lower() in joined or sentinel.upper() in joined,
            "EP068-B1 regression: the sentinel must not reach the log via "
            "the real TestModule, in any casing, via either 'action' or "
            "the exception's own message text",
        )
        self.assert_true(
            any(line == "Error executing 'test': ValueError" for line in lines),
            f"expected only 'Error executing 'test': ValueError'; actual lines: {lines!r}",
        )

    # ---------- 8. (Revision 2) Exception message leak ----------

    def _test_exception_message_text_never_logged(self) -> None:
        """A sentinel embedded in an exception's own *message* text
        (not merely in `action`) must not reach the log -- only
        `type(exc).__name__` may appear in its place.
        """

        class _RaisesWithSentinelInMessage:
            def __init__(self) -> None:
                self._name = "leaky"

            @property
            def name(self) -> str:
                return self._name

            def execute(self, action: str, arguments: list[str]) -> CommandResult:
                raise KeyError(f"failure involving {_SENTINEL}")

        _SENTINEL = "EP068_EXC_MESSAGE_SENTINEL_2d8a4f11"

        router = CommandRouter()
        router.register(_RaisesWithSentinelInMessage())

        lines, sink_id = _capture_logs()
        try:
            result = router.dispatch("leaky go")
        finally:
            logger.remove(sink_id)

        self.assert_false(result.success)
        joined = "\n".join(lines)
        self.assert_false(
            _SENTINEL in joined,
            "the sensitive sentinel embedded in an exception's own message "
            "text must never reach the log",
        )
        self.assert_false(
            "failure involving" in joined,
            "no part of the exception's own message text may reach the log",
        )
        self.assert_true(
            any("Error executing 'leaky': KeyError" in line for line in lines),
            f"expected the exception's class name in place of its message; "
            f"actual lines: {lines!r}",
        )

    # ---------- 9. (Revision 2) Module-name-position sentinel: out of scope ----------

    def _test_module_name_position_sentinel_only_reaches_unknown_module_line(self) -> None:
        """A sentinel supplied as the (unregistered) module name reaches
        only the pre-existing, out-of-scope 'Unknown module' log line --
        never either of `dispatch()`'s own two EP-068 log statements.
        This proves D12/EP068-M1 remains correctly deferred and that
        this revision neither fixes nor worsens it.
        """
        sentinel = "EP068_MODULE_POSITION_SENTINEL_ab12cd34"
        router = CommandRouter()

        lines, sink_id = _capture_logs()
        try:
            result = router.dispatch(f"{sentinel} some args here")
        finally:
            logger.remove(sink_id)

        self.assert_false(result.success)
        self.assert_true(f"Unknown module: {sentinel}" in result.message)

        # It DOES reach the pre-existing "Unknown module" line -- that
        # is EP068-M1, explicitly deferred, not this EP's concern.
        self.assert_true(
            any(line == f"Unknown module: {sentinel}" for line in lines),
            "expected the pre-existing 'Unknown module: <name>' log line, "
            "unchanged (D5) -- this is EP068-M1, deliberately deferred",
        )
        # It must NOT reach either of EP-068's own two statements.
        self.assert_false(
            any(line.startswith("Command executed:") for line in lines),
            "a module-name-position sentinel must never trigger EP-068's "
            "own success-path log line",
        )
        self.assert_false(
            any(line.startswith("Error executing") for line in lines),
            "a module-name-position sentinel must never trigger EP-068's "
            "own exception-path log line",
        )
