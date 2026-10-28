"""Render 'Telovie' in candidate fonts so we can pick a wordmark face."""

from __future__ import annotations

import sys

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QImage, QPainter
from PySide6.QtWidgets import QApplication

CANDIDATES = [
    "Segoe UI Variable Display",
    "Segoe UI",
    "Trebuchet MS",
    "Century Gothic",
    "Candara",
    "Corbel",
    "Gabriola",
    "Ink Free",
    "Segoe Script",
    "Georgia",
    "Sitka Display",
    "Comic Sans MS",
    "Verdana",
    "Calibri",
]

app = QApplication(sys.argv[:1])
families = set(QFontDatabase.families())
installed = [name for name in CANDIDATES if name in families]
print("installed:", installed)
missing = [name for name in CANDIDATES if name not in families]
print("missing:", missing)

row = 78
image = QImage(760, row * len(installed) + 20, QImage.Format.Format_ARGB32)
image.fill(QColor("#0f1115"))
painter = QPainter(image)
painter.setRenderHint(QPainter.RenderHint.Antialiasing)
painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

for index, family in enumerate(installed):
    y = 10 + index * row
    font = QFont(family, 26, QFont.Weight.DemiBold)
    painter.setFont(font)
    painter.setPen(QColor("#e6edf3"))
    painter.drawText(QRectF(20, y, 400, 48), Qt.AlignmentFlag.AlignVCenter, "Telovie")
    painter.setFont(QFont("Segoe UI", 9))
    painter.setPen(QColor("#8b949e"))
    painter.drawText(
        QRectF(430, y, 320, 48),
        Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
        family,
    )

painter.end()
image.save(sys.argv[1] if len(sys.argv) > 1 else "tools/fonts.png", "PNG")
print("wrote", sys.argv[1] if len(sys.argv) > 1 else "tools/fonts.png")
