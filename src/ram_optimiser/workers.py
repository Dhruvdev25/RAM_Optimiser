"""Small QThreadPool task wrapper for blocking system reads and actions."""

from __future__ import annotations

from PySide6.QtCore import QObject, QRunnable, Signal


class WorkerSignals(QObject):
    result = Signal(object)
    error = Signal(str)
    finished = Signal()


class Worker(QRunnable):
    def __init__(self, function, *args, **kwargs):
        super().__init__()
        self.function = function
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()
        self.setAutoDelete(True)

    def run(self):
        try:
            self.signals.result.emit(self.function(*self.args, **self.kwargs))
        except Exception as exc:  # surfaced in the GUI instead of killing a worker
            self.signals.error.emit(str(exc))
        finally:
            self.signals.finished.emit()
