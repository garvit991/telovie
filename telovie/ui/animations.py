"""Small hover transitions shared by interactive widgets."""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QEvent, QObject, QPropertyAnimation
from PySide6.QtWidgets import QGraphicsOpacityEffect, QWidget


class HoverFade(QObject):
    """Gently brighten a widget while it is hovered."""

    def __init__(
        self, widget: QWidget, idle_opacity: float = 0.88, duration_ms: int = 160
    ) -> None:
        super().__init__(widget)
        self._idle_opacity = idle_opacity
        self._effect = QGraphicsOpacityEffect(widget)
        self._effect.setOpacity(idle_opacity)
        widget.setGraphicsEffect(self._effect)

        self._animation = QPropertyAnimation(self._effect, b"opacity", self)
        self._animation.setDuration(duration_ms)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        widget.installEventFilter(self)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if event.type() in (QEvent.Type.Enter, QEvent.Type.Leave):
            self._animation.stop()
            self._animation.setStartValue(self._effect.opacity())
            self._animation.setEndValue(
                1.0 if event.type() == QEvent.Type.Enter else self._idle_opacity
            )
            self._animation.start()
        return super().eventFilter(watched, event)
