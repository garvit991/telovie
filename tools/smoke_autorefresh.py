r"""End-to-end auto-refresh check.

Copies one sample into the library, starts the app, then drops a second file in
while it runs. The grid must pick it up with no button press.

    $env:TELOVIE_LIBRARY_DIR = "$env:TEMP\telovie-watch"
    $env:TELOVIE_DATA_DIR = "$env:TEMP\telovie-watch-data"
    .\.venv\Scripts\python.exe tools\smoke_autorefresh.py
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_MEDIA_BACKEND", "ffmpeg")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from telovie.app import configure_logging  # noqa: E402
from telovie.config import AppPaths  # noqa: E402
from telovie.db import Database  # noqa: E402
from telovie.ui.main_window import MainWindow  # noqa: E402

SAMPLES = sorted((ROOT / "sample files").glob("*.mkv"))
DEADLINE_SECONDS = 40.0


def main() -> int:
    if len(SAMPLES) < 2:
        print("need two sample MKVs", file=sys.stderr)
        return 2

    library = Path(os.environ.get("TELOVIE_LIBRARY_DIR", "") or tempfile.mkdtemp())
    data = Path(os.environ.get("TELOVIE_DATA_DIR", "") or tempfile.mkdtemp())
    if library.exists():
        shutil.rmtree(library, ignore_errors=True)
    if data.exists():
        shutil.rmtree(data, ignore_errors=True)
    library.mkdir(parents=True)
    data.mkdir(parents=True)
    os.environ["TELOVIE_LIBRARY_DIR"] = str(library)
    os.environ["TELOVIE_DATA_DIR"] = str(data)

    paths = AppPaths.resolve()
    paths.ensure()
    configure_logging(paths.log_dir)
    print(f"library: {paths.library_dir}")

    shutil.copy2(SAMPLES[0], library / SAMPLES[0].name)

    app = QApplication(sys.argv[:1])
    app.setStyle("Fusion")
    db = Database(paths.db_path)
    window = MainWindow(paths, db)
    window.resize(1000, 700)
    window.show()

    started = time.monotonic()
    state = {"phase": "first", "drop_at": 0.0, "second_name": SAMPLES[1].name}

    def tick() -> None:
        count = db.library.count()
        elapsed = time.monotonic() - started

        if state["phase"] == "first" and count >= 1 and window._scanner is None:
            state["phase"] = "second"
            shutil.copy2(SAMPLES[1], library / state["second_name"])
            state["drop_at"] = time.monotonic()
            print(f"first file indexed in {elapsed:.1f}s — dropped the second")
            return

        if state["phase"] == "second" and count >= 2:
            took = time.monotonic() - state["drop_at"]
            print(f"second file indexed {took:.1f}s after the drop")
            print("PASS" if took < 15 else "FAIL: too slow")
            finish(0 if took < 15 else 1)
            return

        if elapsed > DEADLINE_SECONDS:
            print(f"FAIL: only {count} row(s) after {elapsed:.0f}s", file=sys.stderr)
            finish(1)

    def finish(code: int) -> None:
        for row in db.library.list_for_grid("", "title"):
            print(f"  {row['Title']!r} available={row['IsAvailable']}")
        window._watcher.stop()
        db.close()
        app.exit(code)

    timer = QTimer()
    timer.timeout.connect(tick)
    timer.start(400)

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
