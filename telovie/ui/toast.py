"""Small non-blocking message shown near the bottom of the window."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QLabel, QWidget


class Toast(QLabel):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("Toast")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.hide()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)

    def show_message(self, text: str, duration_ms: int = 2600) -> None:
        self.setText(text)
        self.adjustSize()
        self._reposition()
        self.show()
        self.raise_()
        self._timer.start(duration_ms)

    def _reposition(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        x = max(8, (parent.width() - self.width()) // 2)
        y = max(8, parent.height() - self.height() - 48)
        self.move(x, y)

    def parent_resized(self) -> None:
        if self.isVisible():
            self._reposition()
