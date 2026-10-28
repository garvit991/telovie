"""Library card: painted placeholder art, title, duration, progress."""

from __future__ import annotations

import re
from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import QMenu, QWidget

from telovie.ui.theme import (
    ACCENT,
    BORDER,
    DIM,
    MUTED,
    OK,
    TEXT,
    gradient_colors,
)
from telovie.util.timefmt import format_ms

CARD_WIDTH = 236
CARD_HEIGHT = 192
ART_HEIGHT = 132
RADIUS = 10


@dataclass(frozen=True)
class CardData:
    media_id: int
    title: str
    duration_ms: int
    size_bytes: int
    progress: float
    completed: bool
    available: bool
    file_path: str
    recommended: bool = False


def _initials(title: str) -> str:
    words = [w for w in re.split(r"[\s._\-]+", title) if w]
    if not words:
        return "?"
    if len(words) == 1:
        return words[0][:2].upper()
    return (words[0][0] + words[1][0]).upper()


class MediaCard(QWidget):
    playRequested = Signal(int)
    startOverRequested = Signal(int)
    revealRequested = Signal(int)
    removeRequested = Signal(int)

    def __init__(self, data: CardData, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.data = data
        self._hover = False
        self.setFixedSize(CARD_WIDTH, CARD_HEIGHT)
        self.setCursor(
            Qt.CursorShape.PointingHandCursor
            if data.available
            else Qt.CursorShape.ForbiddenCursor
        )
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setToolTip(f"{data.title}\n{data.file_path}")
        self.setAccessibleName(data.title)
        self.setAccessibleDescription(
            "Unavailable" if not data.available else "Video"
        )

    # -- painting ---------------------------------------------------------

    def paintEvent(self, _event) -> None:  # noqa: N802 - Qt naming
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if not self.data.available:
            painter.setOpacity(0.45)

        art = QRectF(0, 0, CARD_WIDTH, ART_HEIGHT)
        path = QPainterPath()
        path.addRoundedRect(art, RADIUS, RADIUS)

        painter.save()
        painter.setClipPath(path)

        top, bottom = gradient_colors(self.data.title)
        gradient = QLinearGradient(art.topLeft(), art.bottomRight())
        gradient.setColorAt(0.0, top)
        gradient.setColorAt(1.0, bottom)
        painter.fillRect(art, gradient)

        painter.setPen(QColor(255, 255, 255, 30))
        painter.setFont(QFont("Segoe UI Variable Display", 44, QFont.Weight.Bold))
        painter.drawText(art, Qt.AlignmentFlag.AlignCenter, _initials(self.data.title))

        self._draw_duration_chip(painter, art)
        if not self.data.available:
            self._draw_badge(painter, art, "MISSING", DIM)
        elif self.data.recommended:
            self._draw_badge(painter, art, "NEXT UP", ACCENT)
        elif self.data.completed:
            self._draw_badge(painter, art, "WATCHED", OK)

        painter.restore()

        self._draw_progress(painter)

        border = ACCENT if self._hover and self.data.available else BORDER
        pen = QPen(QColor(border))
        pen.setWidthF(1.6 if self._hover and self.data.available else 1.0)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(art.adjusted(0.5, 0.5, -0.5, -0.5), RADIUS, RADIUS)

        self._draw_text(painter)

        if self.hasFocus():
            focus_pen = QPen(QColor(ACCENT))
            focus_pen.setWidthF(1.4)
            focus_pen.setStyle(Qt.PenStyle.DotLine)
            painter.setPen(focus_pen)
            painter.drawRoundedRect(
                QRectF(1.5, 1.5, CARD_WIDTH - 3, CARD_HEIGHT - 3), RADIUS, RADIUS
            )

    def _draw_duration_chip(self, painter: QPainter, art: QRectF) -> None:
        text = format_ms(self.data.duration_ms) if self.data.duration_ms else "—"
        font = QFont("Segoe UI Variable Text", 8, QFont.Weight.DemiBold)
        painter.setFont(font)
        metrics = QFontMetrics(font)
        width = metrics.horizontalAdvance(text) + 12
        rect = QRectF(art.right() - width - 8, art.bottom() - 26, width, 18)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 155))
        painter.drawRoundedRect(rect, 4, 4)
        painter.setPen(QColor(255, 255, 255, 225))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)

    def _draw_badge(
        self, painter: QPainter, art: QRectF, text: str, color: str
    ) -> None:
        font = QFont("Segoe UI Variable Text", 7, QFont.Weight.Bold)
        painter.setFont(font)
        metrics = QFontMetrics(font)
        width = metrics.horizontalAdvance(text) + 14
        rect = QRectF(art.right() - width - 8, 8, width, 17)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(color))
        painter.drawRoundedRect(rect, 4, 4)
        painter.setPen(QColor("#0b0e12"))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)

    def _draw_progress(self, painter: QPainter) -> None:
        if self.data.progress <= 0 or not self.data.available:
            return
        height = 4.0
        y = ART_HEIGHT - height
        painter.fillRect(QRectF(0, y, CARD_WIDTH, height), QColor(0, 0, 0, 100))
        filled = CARD_WIDTH * min(1.0, max(0.0, self.data.progress))
        color = OK if self.data.completed else ACCENT
        painter.fillRect(QRectF(0, y, filled, height), QColor(color))

    def _draw_text(self, painter: QPainter) -> None:
        title_font = QFont("Segoe UI Variable Text", 10, QFont.Weight.DemiBold)
        painter.setFont(title_font)
        painter.setPen(QColor(TEXT if self.data.available else MUTED))
        title_rect = QRectF(2, ART_HEIGHT + 8, CARD_WIDTH - 4, 20)
        title = QFontMetrics(title_font).elidedText(
            self.data.title,
            Qt.TextElideMode.ElideRight,
            int(title_rect.width()),
        )
        painter.drawText(
            title_rect,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            title,
        )

        meta_font = QFont("Segoe UI Variable Text", 8)
        painter.setFont(meta_font)
        painter.setPen(QColor(MUTED if self.data.available else DIM))
        if not self.data.available:
            meta = "File missing — rescan or move it back"
        elif self.data.progress > 0 and not self.data.completed:
            meta = f"{int(self.data.progress * 100)}% watched"
        elif self.data.completed:
            meta = "finished"
        else:
            meta = ""
        painter.drawText(
            QRectF(2, ART_HEIGHT + 30, CARD_WIDTH - 4, 18),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            meta,
        )

    # -- interaction ------------------------------------------------------

    def enterEvent(self, event) -> None:  # noqa: N802
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if (
            event.button() == Qt.MouseButton.LeftButton
            and self.rect().contains(event.position().toPoint())
            and self.data.available
        ):
            self.playRequested.emit(self.data.media_id)
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            if self.data.available:
                self.playRequested.emit(self.data.media_id)
            return
        super().keyPressEvent(event)

    def contextMenuEvent(self, event) -> None:  # noqa: N802
        menu = QMenu(self)
        play = menu.addAction("Play")
        play.setEnabled(self.data.available)
        start_over = menu.addAction("Start over")
        start_over.setEnabled(self.data.available)
        menu.addSeparator()
        reveal = menu.addAction("Show in Explorer")
        remove = menu.addAction("Remove from library")

        chosen = menu.exec(event.globalPos())
        if chosen is play:
            self.playRequested.emit(self.data.media_id)
        elif chosen is start_over:
            self.startOverRequested.emit(self.data.media_id)
        elif chosen is reveal:
            self.revealRequested.emit(self.data.media_id)
        elif chosen is remove:
            self.removeRequested.emit(self.data.media_id)

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(CARD_WIDTH, CARD_HEIGHT)
