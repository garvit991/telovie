"""Application bootstrap: logging, paths, database, main window."""

from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

os.environ.setdefault("QT_MEDIA_BACKEND", "ffmpeg")

from PySide6.QtCore import qVersion  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from telovie import __version__  # noqa: E402
from telovie.config import APP_NAME, ORG_NAME, AppPaths  # noqa: E402
from telovie.db import Database  # noqa: E402
from telovie.ui.main_window import MainWindow  # noqa: E402

log = logging.getLogger(__name__)
_CONFIGURED = False


def configure_logging(log_dir: Path) -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    log_dir.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    root.setLevel(logging.INFO)

    formatter = logging.Formatter(
        "%(asctime)s %(levelname)-7s %(name)s: %(message)s", "%H:%M:%S"
    )
    file_handler = RotatingFileHandler(
        log_dir / "app.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    root.addHandler(console)
    _CONFIGURED = True


def main() -> int:
    paths = AppPaths.resolve()
    paths.ensure()
    configure_logging(paths.log_dir)
    log.info(
        "%s %s starting · Qt %s · backend %s · library %s",
        APP_NAME,
        __version__,
        qVersion(),
        os.environ.get("QT_MEDIA_BACKEND", "default"),
        paths.library_dir,
    )

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(ORG_NAME)
    app.setApplicationVersion(__version__)
    app.setStyle("Fusion")

    try:
        db = Database(paths.db_path)
    except Exception as exc:  # noqa: BLE001 - surface a readable failure
        log.exception("Could not open the library database")
        QMessageBox.critical(
            None,
            APP_NAME,
            f"Could not open the library database:\n\n{paths.db_path}\n\n{exc}",
        )
        return 1

    log.info("Database ready: %s (%d titles)", paths.db_path, db.library.count())

    window = MainWindow(paths, db)
    window.show()
    app.aboutToQuit.connect(db.close)
    return app.exec()
