"""ApiWorker: runs one JarvisApiClient call on a background QThread.

Implements EP044_DESIGN.md Section 15/30's threading model: the Qt
event loop (UI thread) must never be blocked by network I/O. Each
worker owns exactly one call, runs it on a ``QThread``, and reports
the outcome back to the UI thread via Qt's queued-connection signal
mechanism -- callers never receive a direct cross-thread call into
Qt widgets, only signals.

Reused by ``MainWindowViewModel`` for all three API calls (health,
status, execute command), so the threading logic is written once
rather than duplicated per call site.
"""

from __future__ import annotations

from typing import Callable, Generic, TypeVar

from PySide6.QtCore import QObject, QThread, Signal

from desktop.api.client_errors import ApiClientError

__all__ = ["ApiWorker"]

_T = TypeVar("_T")


class _WorkerSignals(QObject):
    """Signals emitted by a worker's underlying QThread.

    Kept as a separate QObject (rather than defined directly on
    ApiWorker) because ApiWorker itself does not need to inherit from
    QObject; only the object whose signals cross the thread boundary
    does.
    """

    succeeded = Signal(object)
    failed = Signal(object)


class ApiWorker(QThread, Generic[_T]):
    """Runs a single zero-argument callable on a background thread.

    Emits exactly one of ``succeeded(result)`` or ``failed(error)``
    when the callable returns or raises. Both signals use Qt's default
    queued connection when connected to a slot living on the UI
    thread, so UI-side slots always run on the UI thread even though
    the callable itself runs on this worker thread.
    """

    def __init__(self, call: Callable[[], _T], parent: QObject | None = None) -> None:
        """Initialize the worker.

        Args:
            call: A zero-argument callable to run on this thread, e.g.
                ``lambda: api_client.check_health()``. Must raise only
                ``ApiClientError`` subclasses on failure -- any other
                exception is still caught and reported via ``failed``
                (EP044_DESIGN.md Section 18, "Unexpected client
                error"), but is re-wrapped so callers only ever handle
                ``ApiClientError``.
            parent: Optional Qt parent object.
        """
        super().__init__(parent)
        self._call = call
        self.signals = _WorkerSignals()

    @property
    def succeeded(self) -> Signal:
        """Emitted with the callable's return value on success."""
        return self.signals.succeeded

    @property
    def failed(self) -> Signal:
        """Emitted with an ``ApiClientError`` on failure."""
        return self.signals.failed

    def run(self) -> None:
        """Execute the wrapped callable and emit the outcome.

        Never lets an exception propagate out of the worker thread
        uncaught -- every failure, including one not already an
        ``ApiClientError``, is caught and reported through the
        ``failed`` signal (EP044_DESIGN.md Section 30, "Ensure worker
        failures are propagated safely").
        """
        try:
            result = self._call()
        except ApiClientError as exc:
            self.signals.failed.emit(exc)
        except Exception as exc:  # noqa: BLE001 - last-resort boundary; see docstring
            self.signals.failed.emit(ApiClientError(str(exc)))
        else:
            self.signals.succeeded.emit(result)
