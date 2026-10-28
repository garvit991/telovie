"""Player controls: a scrub slider with buffered tint, and painted icon buttons."""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QAbstractButton, QSlider, QStyle

from telovie.ui.icons import paint_icon
from telovie.ui.theme import ACCENT, BORDER, DIM, SURFACE_ALT, TEXT

TRACK_HEIGHT = 4.0
HANDLE_RADIUS = 6.0
HANDLE_RADIUS_HOVER = 7.0


class SeekSlider(QSlider):
    """Click anywhere to seek, drag to scrub, release to commit.

    ``seekRequested`` is emitted once, on release, so dragging does not spam
    the media backend with seeks. While the user drags, the view freezes the
    elapsed label using ``scrubMoved``.
    """

    seekRequested = Signal(int)
    scrubMoved = Signal(int)
    scrubStarted = Signal()
    scrubFinished = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(Qt.Orientation.Horizontal, parent)
        self.setRange(0, 0)
        self.setSingleStep(5_000)
        self.setPageStep(30_000)
        self.setFixedHeight(24)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._dragging = False
        self._hover = False
        self._buffered = 0
        self.setMouseTracking(True)

    # -- state -----------------------------------------------------------

    def set_buffered(self, position_ms: int) -> None:
        position_ms = max(0, int(position_ms))
        if position_ms != self._buffered:
            self._buffered = position_ms
            self.update()

    @property
    def buffered(self) -> int:
        return self._buffered

    # -- geometry --------------------------------------------------------

    def _track_rect(self) -> QRectF:
        margin = HANDLE_RADIUS_HOVER + 2
        return QRectF(
            margin,
            (self.height() - TRACK_HEIGHT) / 2,
            max(1.0, self.width() - margin * 2),
            TRACK_HEIGHT,
        )

    def _value_at(self, x: float) -> int:
        track = self._track_rect()
        ratio = (x - track.left()) / track.width()
        ratio = min(1.0, max(0.0, ratio))
        return int(round(self.minimum() + ratio * (self.maximum() - self.minimum())))

    def _x_for_value(self, value: int) -> float:
        track = self._track_rect()
        span = self.maximum() - self.minimum()
        ratio = 0.0 if span <= 0 else (value - self.minimum()) / span
        return track.left() + min(1.0, max(0.0, ratio)) * track.width()

    # -- painting --------------------------------------------------------

    def paintEvent(self, _event) -> None:  # noqa: N802 - Qt naming
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        track = self._track_rect()
        radius = TRACK_HEIGHT / 2

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(BORDER))
        painter.drawRoundedRect(track, radius, radius)

        span = self.maximum() - self.minimum()
        if span > 0 and self._buffered > 0:
            buffered_ratio = min(1.0, max(0.0, (self._buffered - self.minimum()) / span))
            if buffered_ratio > 0:
                painter.setBrush(QColor("#3a4150"))
                painter.drawRoundedRect(
                    QRectF(track.left(), track.top(), track.width() * buffered_ratio, track.height()),
                    radius,
                    radius,
                )

        value_ratio = 0.0 if span <= 0 else (self.value() - self.minimum()) / span
        if value_ratio > 0:
            painter.setBrush(QColor(ACCENT))
            painter.drawRoundedRect(
                QRectF(track.left(), track.top(), track.width() * value_ratio, track.height()),
                radius,
                radius,
            )

        if self.isEnabled():
            radius = HANDLE_RADIUS_HOVER if (self._hover or self._dragging) else HANDLE_RADIUS
            center = QPoint(int(self._x_for_value(self.value())), int(track.center().y()))
            painter.setBrush(QColor(TEXT))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(center, int(radius), int(radius))

    # -- interaction -----------------------------------------------------

    def enterEvent(self, event) -> None:  # noqa: N802
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self.isEnabled():
            self._dragging = True
            self.scrubStarted.emit()
            self.setValue(self._value_at(event.position().x()))
            self.scrubMoved.emit(self.value())
            self.update()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._dragging:
            self.setValue(self._value_at(event.position().x()))
            self.scrubMoved.emit(self.value())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self._dragging and event.button() == Qt.MouseButton.LeftButton:
            self._dragging = False
            value = self._value_at(event.position().x())
            self.setValue(value)
            self.update()
            self.scrubFinished.emit()
            self.seekRequested.emit(value)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            super().keyPressEvent(event)
            self.seekRequested.emit(self.value())
            return
        super().keyPressEvent(event)

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(320, 24)


class IconButton(QAbstractButton):
    """A flat, square button that paints a vector icon."""

    def __init__(
        self,
        kind: str,
        tooltip: str = "",
        *,
        size: int = 34,
        icon_size: int = 20,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._kind = kind
        self._icon_size = icon_size
        self._hover = False
        self.setFixedSize(size, size)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        if tooltip:
            self.setToolTip(tooltip)
            self.setAccessibleName(tooltip)

    def set_kind(self, kind: str) -> None:
        if kind != self._kind:
            self._kind = kind
            self.update()

    @property
    def kind(self) -> str:
        return self._kind

    def enterEvent(self, event) -> None:  # noqa: N802
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if self._hover and self.isEnabled():
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(SURFACE_ALT))
            painter.drawRoundedRect(QRectF(self.rect()), 8, 8)

        color = QColor(TEXT if self.isEnabled() else DIM)
        inset = (self.width() - self._icon_size) / 2
        rect = QRectF(inset, inset, self._icon_size, self._icon_size)
        paint_icon(painter, self._kind, rect, color)


class VolumeSlider(QSlider):
    """Thin 0-100 slider; the groove/handle are styled in the app stylesheet."""

    def __init__(self, parent=None) -> None:
        super().__init__(Qt.Orientation.Horizontal, parent)
        self.setObjectName("Volume")
        self.setRange(0, 100)
        self.setFixedWidth(96)
        self.setFixedHeight(24)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def wheelEvent(self, event) -> None:  # noqa: N802
        event.ignore()

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(96, 24)
