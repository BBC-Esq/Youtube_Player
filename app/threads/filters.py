from PySide6.QtCore import QThread, Signal

from app.core.adblock import refresh_filter_lists


class FilterListThread(QThread):
    completed = Signal(int)

    def run(self):
        try:
            updated = refresh_filter_lists()
        except Exception:
            updated = 0
        self.completed.emit(updated)
