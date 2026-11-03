"""Tasks return Python data only. Qt widgets and Matplotlib never run here."""
from PySide6.QtCore import QThread, Signal


class TaskThread(QThread):
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, task, parent=None):
        super().__init__(parent)
        self.task = task

    def run(self):
        try:
            result = self.task()
        except Exception as exc:
            self.failed.emit(f'{type(exc).__name__}: {exc}')
        else:
            self.succeeded.emit(result)
