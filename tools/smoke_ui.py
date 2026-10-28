r"""Headless UI smoke test: index a folder, render the grid to PNG.

Usage (PowerShell):
    $env:QT_QPA_PLATFORM = "offscreen"
    $env:TELOVIE_LIBRARY_DIR = "...\sample files"
    $env:TELOVIE_DATA_DIR = "...\temp\telovie-smoke"
    .\.venv\Scripts\python.exe tools\smoke_ui.py --out tools\smoke.png
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

# The platform must be chosen before Qt is imported. "windows" gives real fonts;
# "offscreen" is only useful for pure smoke runs (all text renders as boxes).
if "--offscreen" in sys.argv:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_MEDIA_BACKEND", "ffmpeg")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QPoint, QTimer  # noqa: E402
from PySide6.QtGui import QPainter  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from telovie.app import configure_logging  # noqa: E402
from telovie.config import AppPaths  # noqa: E402
from telovie.db import Database  # noqa: E402
from telovie.ui.main_window import MainWindow  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="tools/smoke.png")
    parser.add_argument("--width", type=int, default=1200)
    parser.add_argument("--height", type=int, default=780)
    parser.add_argument("--search", default="")
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument(
        "--offscreen",
        action="store_true",
        help="run without a window (no fonts, text renders as boxes)",
    )
    parser.add_argument(
        "--simulate-missing",
        action="store_true",
        help="flag the first row as unavailable before grabbing",
    )
    parser.add_argument(
        "--open-menu",
        action="store_true",
        help="also capture the overflow menu",
    )
    args = parser.parse_args()

    paths = AppPaths.resolve()
    paths.ensure()
    configure_logging(paths.log_dir)
    print(f"library: {paths.library_dir}")
    print(f"data:    {paths.data_dir}")

    app = QApplication(sys.argv[:1])
    app.setStyle("Fusion")
    db = Database(paths.db_path)
    window = MainWindow(paths, db)
    window.resize(args.width, args.height)
    if os.environ.get("QT_QPA_PLATFORM") != "offscreen":
        window.move(-4000, -4000)  # keep the smoke window off the desktop
    window.show()

    state = {"started": time.monotonic(), "done": False}

    def poll() -> None:
        if window._scanner is not None or state["done"]:
            return
        state["done"] = True
        QTimer.singleShot(600, capture)

    def capture() -> None:
        if state.get("captured"):
            return
        state["captured"] = True
        if args.simulate_missing:
            rows = db.library.list_for_grid("", "title")
            if rows:
                seen = [row["FilePath"] for row in rows[1:]]
                db.library.mark_missing(paths.library_dir, seen)
                window.refresh_grid()
                app.processEvents()
        if args.search:
            window.view.search.setText(args.search)
            app.processEvents()
            window.refresh_grid()
            app.processEvents()
        rows = db.library.list_for_grid("", "title")
        print(f"indexed rows: {len(rows)}")
        for row in rows[:10]:
            print(
                f"  #{row['id']} {row['Title']!r} "
                f"{row['TotalDuration']}ms "
                f"{row['FileSize'] / 1024 / 1024:.1f}MB "
                f"available={row['IsAvailable']}"
            )
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        pixmap = window.grab()

        if args.open_menu:
            button = window.view.overflow
            menu = button.menu()
            menu.popup(button.mapToGlobal(QPoint(0, button.height() + 4)))
            app.processEvents()
            menu_pixmap = menu.grab()
            menu_out = out.with_name(f"{out.stem}-menu{out.suffix}")
            menu_pixmap.save(str(menu_out), "PNG")
            print(f"menu screenshot: {menu_out}")
            # paint the popup into the window shot so one image shows both
            origin = button.mapTo(window, QPoint(0, button.height() + 4))
            x = min(origin.x(), window.width() - menu_pixmap.width() - 8)
            painter = QPainter(pixmap)
            painter.drawPixmap(QPoint(max(8, x), origin.y()), menu_pixmap)
            painter.end()
            menu.close()

        pixmap.save(str(out), "PNG")
        print(f"screenshot: {out} ({pixmap.width()}x{pixmap.height()})")
        print(f"status: {window._status.text()}")
        print(f"count label: {window._count.text()}")
        window._watcher.stop()
        db.close()
        app.quit()

    def watchdog() -> None:
        if not state["done"]:
            print("TIMEOUT waiting for the scan", file=sys.stderr)
            capture()

    timer = QTimer()
    timer.timeout.connect(poll)
    timer.start(150)
    QTimer.singleShot(int(args.timeout * 1000), watchdog)

    code = app.exec()
    return code


if __name__ == "__main__":
    sys.exit(main())
