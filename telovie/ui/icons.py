"""Vector icons painted at runtime, so the app ships no image assets.

Each function paints into ``rect`` using ``color``. They are deliberately small
and geometric to match the flat dark theme.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPolygonF


def _pen(color: QColor, width: float = 1.6) -> QPen:
    pen = QPen(color, width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return pen


def draw_play(painter: QPainter, rect: QRectF, color: QColor) -> None:
    left = rect.left() + rect.width() * 0.32
    top = rect.top() + rect.height() * 0.22
    bottom = rect.bottom() - rect.height() * 0.22
    tip = rect.left() + rect.width() * 0.74

    path = QPainterPath()
    path.moveTo(left, top)
    path.lineTo(tip, rect.center().y())
    path.lineTo(left, bottom)
    path.closeSubpath()

    painter.setBrush(color)
    painter.setPen(_pen(color, 2.0))
    painter.drawPath(path)


def draw_pause(painter: QPainter, rect: QRectF, color: QColor) -> None:
    bar_width = rect.width() * 0.14
    bar_height = rect.height() * 0.58
    top = rect.center().y() - bar_height / 2
    left = rect.left() + rect.width() * 0.31
    right = rect.left() + rect.width() * 0.55

    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(color)
    radius = bar_width / 2
    painter.drawRoundedRect(QRectF(left, top, bar_width, bar_height), radius, radius)
    painter.drawRoundedRect(QRectF(right, top, bar_width, bar_height), radius, radius)


def draw_volume(
    painter: QPainter, rect: QRectF, color: QColor, *, muted: bool = False
) -> None:
    width, height = rect.width(), rect.height()
    center_y = rect.center().y()
    left = rect.left() + width * 0.08

    body = QPainterPath()
    body.moveTo(left, center_y - height * 0.10)
    body.lineTo(left + width * 0.17, center_y - height * 0.10)
    body.lineTo(left + width * 0.38, center_y - height * 0.32)
    body.lineTo(left + width * 0.38, center_y + height * 0.32)
    body.lineTo(left + width * 0.17, center_y + height * 0.10)
    body.lineTo(left, center_y + height * 0.10)
    body.closeSubpath()

    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(color)
    painter.drawPath(body)

    painter.setBrush(Qt.BrushStyle.NoBrush)
    if muted:
        painter.setPen(_pen(color, 1.7))
        painter.drawLine(
            QPointF(left + width * 0.52, center_y - height * 0.17),
            QPointF(left + width * 0.84, center_y + height * 0.17),
        )
        painter.drawLine(
            QPointF(left + width * 0.84, center_y - height * 0.17),
            QPointF(left + width * 0.52, center_y + height * 0.17),
        )
        return

    painter.setPen(_pen(color, 1.4))
    painter.drawArc(
        QRectF(left + width * 0.30, center_y - height * 0.22, width * 0.30, height * 0.44),
        -50 * 16,
        100 * 16,
    )
    painter.drawArc(
        QRectF(left + width * 0.30, center_y - height * 0.36, width * 0.52, height * 0.72),
        -50 * 16,
        100 * 16,
    )


def draw_fullscreen(
    painter: QPainter, rect: QRectF, color: QColor, *, exiting: bool = False
) -> None:
    painter.setPen(_pen(color, 1.8))
    painter.setBrush(Qt.BrushStyle.NoBrush)

    left = rect.left() + rect.width() * 0.14
    right = rect.right() - rect.width() * 0.14
    top = rect.top() + rect.height() * 0.14
    bottom = rect.bottom() - rect.height() * 0.14
    arm = rect.width() * 0.22
    inset = rect.width() * 0.20 if exiting else 0.0

    corners = [
        (left, top, 1, 1),
        (right, top, -1, 1),
        (left, bottom, 1, -1),
        (right, bottom, -1, -1),
    ]
    for x, y, dx, dy in corners:
        if exiting:
            # brackets point inward
            painter.drawPolyline(
                QPolygonF(
                    [
                        QPointF(x + dx * arm, y + dy * arm),
                        QPointF(x + dx * inset, y + dy * inset),
                        QPointF(x + dx * (arm + inset), y + dy * inset),
                    ]
                )
            )
        else:
            painter.drawPolyline(
                QPolygonF(
                    [
                        QPointF(x, y + dy * arm),
                        QPointF(x, y),
                        QPointF(x + dx * arm, y),
                    ]
                )
            )


def draw_back(painter: QPainter, rect: QRectF, color: QColor) -> None:
    painter.setPen(_pen(color, 2.0))
    painter.setBrush(Qt.BrushStyle.NoBrush)

    center_y = rect.center().y()
    left = rect.left() + rect.width() * 0.22
    right = rect.left() + rect.width() * 0.74
    painter.drawLine(QPointF(right, center_y), QPointF(left, center_y))
    painter.drawLine(
        QPointF(left, center_y),
        QPointF(left + rect.width() * 0.20, center_y - rect.height() * 0.20),
    )
    painter.drawLine(
        QPointF(left, center_y),
        QPointF(left + rect.width() * 0.20, center_y + rect.height() * 0.20),
    )


DRAWERS = {
    "play": draw_play,
    "pause": draw_pause,
    "volume": draw_volume,
    "muted": lambda painter, rect, color: draw_volume(
        painter, rect, color, muted=True
    ),
    "fullscreen": draw_fullscreen,
    "fullscreen_exit": lambda painter, rect, color: draw_fullscreen(
        painter, rect, color, exiting=True
    ),
    "back": draw_back,
}


def paint_icon(
    painter: QPainter, kind: str, rect: QRectF, color: QColor
) -> None:
    DRAWERS[kind](painter, rect, color)
