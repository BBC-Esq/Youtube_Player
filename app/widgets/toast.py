from PySide6.QtWidgets import QLabel, QWidget, QGraphicsOpacityEffect
from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve


class Toast(QLabel):
    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAlignment(Qt.AlignCenter)
        self.setWordWrap(True)
        self.setMinimumWidth(240)
        self.setMaximumWidth(520)
        self.hide()

        self._opacity_effect = QGraphicsOpacityEffect(self)
        self._opacity_effect.setOpacity(1.0)
        self.setGraphicsEffect(self._opacity_effect)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._start_fade_out)

        self._fade = QPropertyAnimation(self._opacity_effect, b"opacity", self)
        self._fade.setDuration(300)
        self._fade.setEasingCurve(QEasingCurve.InOutQuad)
        self._fade.finished.connect(self._on_fade_finished)
        self._fading_out = False

    def _style_for(self, level: str) -> str:
        colors = {
            "success": ("#1f6f33", "#2e8b57"),
            "error": ("#7a1f1f", "#a83232"),
            "info": ("#2a4a6b", "#3b6ea8"),
        }
        bg, border = colors.get(level, colors["info"])
        return (
            f"background-color: {bg};"
            "color: white;"
            f"border: 1px solid {border};"
            "border-radius: 6px;"
            "padding: 8px 14px;"
            "font-size: 12px;"
            "font-weight: 500;"
        )

    def show_message(self, text: str, level: str = "info", duration_ms: int = 4000):
        self._timer.stop()
        self._fade.stop()
        self._fading_out = False
        self.setStyleSheet(self._style_for(level))
        self.setText(text)
        self.adjustSize()
        self._reposition()
        self._opacity_effect.setOpacity(1.0)
        self.show()
        self.raise_()
        self._timer.start(duration_ms)

    def _reposition(self):
        parent = self.parentWidget()
        if parent is None:
            return
        margin = 18
        x = parent.width() - self.width() - margin
        y = parent.height() - self.height() - margin
        self.move(max(0, x), max(0, y))

    def reposition(self):
        if self.isVisible():
            self._reposition()

    def _start_fade_out(self):
        self._fading_out = True
        self._fade.stop()
        self._fade.setStartValue(1.0)
        self._fade.setEndValue(0.0)
        self._fade.start()

    def _on_fade_finished(self):
        if self._fading_out:
            self.hide()
            self._opacity_effect.setOpacity(1.0)
            self._fading_out = False
