r"""Phase 4 acceptance check: playback, controls, and file-handle release.

    .\.venv\Scripts\python.exe tools\smoke_player.py
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_MEDIA_BACKEND", "ffmpeg")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from telovie.app import configure_logging  # noqa: E402
from telovie.config import AppPaths  # noqa: E402
from telovie.db import Database  # noqa: E402
from telovie.ui.main_window import MainWindow  # noqa: E402

FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {name}{'  ' + detail if detail else ''}")
    if not ok:
        FAILURES.append(name)


def wait_until(app: QApplication, predicate, timeout: float = 10.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(0.05)
    return False


def rename_probe(path: Path, attempts: int = 40) -> bool:
    """True when nothing holds the file open (Windows locks open media)."""
    probe = path.with_name(path.name + ".locktest")
    for _ in range(attempts):
        try:
            path.rename(probe)
            probe.rename(path)
            return True
        except OSError:
            time.sleep(0.05)
    return False


def main() -> int:
    paths = AppPaths.resolve()
    paths.ensure()
    configure_logging(paths.log_dir)

    app = QApplication(sys.argv[:1])
    app.setStyle("Fusion")
    db = Database(paths.db_path)
    window = MainWindow(paths, db)
    window.resize(1200, 780)
    window.move(-4000, -4000)
    window.show()

    # index the sample folder (or whatever TELOVIE_LIBRARY_DIR points at)
    if not wait_until(app, lambda: window._scanner is None and db.library.count() > 0, 60):
        print("FAIL  library did not index")
        return 1
    window._watcher.stop()

    row = db.library.list_for_grid("", "title")[0]
    media_path = Path(row["FilePath"])
    print(f"playing: {row['Title']}")
    print(f"duration in DB: {row['TotalDuration']} ms")

    window.player.set_volume(0)  # keep the room quiet while probing
    window._on_play_requested(row["id"])

    loaded = wait_until(app, lambda: window.player.controller.duration > 0, 15)
    check("media loads", loaded)
    check("video widget visible", window.player.video.isVisible())

    playing = wait_until(app, lambda: window.player.controller.is_playing, 10)
    check("playback starts", playing)

    advanced = wait_until(
        app, lambda: window.player.controller.position > 500, 6.0
    )
    position = window.player.controller.position
    check("position advances", advanced, f"{position} ms")
    check(
        "duration matches the container",
        abs(window.player.controller.duration - row["TotalDuration"]) < 1500,
        f"{window.player.controller.duration} ms",
    )
    check(
        "seek bar is enabled with a real range",
        window.player.seek.isEnabled() and window.player.seek.maximum() > 0,
        f"max={window.player.seek.maximum()}",
    )
    check("play button shows pause", window.player.play_button.kind == "pause")

    target = int(window.player.controller.duration * 0.6)
    window.player.seek.seekRequested.emit(target)
    time.sleep(0.6)
    app.processEvents()
    check(
        "seek lands near the target",
        abs(window.player.controller.position - target) < 2500,
        f"{window.player.controller.position} vs {target}",
    )

    window.player.controller.pause()
    time.sleep(0.3)
    app.processEvents()
    check("pause updates the button", window.player.play_button.kind == "play")

    window.player.set_volume(45)
    time.sleep(0.9)
    app.processEvents()
    check("volume is persisted", db.prefs.get().volume == 45, f"{db.prefs.get().volume}")

    window.player.controller.toggle_mute()
    app.processEvents()
    check("mute updates the icon", window.player.volume_button.kind == "muted")
    window.player.controller.toggle_mute()
    app.processEvents()
    check("unmute updates the icon", window.player.volume_button.kind == "volume")

    window.player.controller.play()
    time.sleep(0.6)
    app.processEvents()

    out = ROOT / "tools" / "player.png"
    window.grab().save(str(out), "PNG")
    print(f"screenshot: {out}")

    # back to the grid, then confirm the handle is gone
    window.player.backRequested.emit()
    app.processEvents()
    check("back returns to the library", window.stack.currentWidget() is window.view)
    check("file handle released after close", rename_probe(media_path))

    # 20 open/close cycles must not leak handles or players
    controller = window.player.controller
    for _ in range(20):
        window.player.open_media("cycle", str(media_path), 0)
        wait_until(app, lambda: controller.duration > 0, 3)
        window.player.stop_and_release()
        app.processEvents()
    check("file handle released after 20 cycles", rename_probe(media_path))
    check("still using one player", controller.source_path is None)

    window._watcher.stop()
    db.close()
    print()
    print("FAILURES:", FAILURES if FAILURES else "none")
    return 0 if not FAILURES else 1


if __name__ == "__main__":
    sys.exit(main())
