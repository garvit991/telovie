r"""Scale check: synthesize N tiny MKVs, index them, time the grid.

    .\.venv\Scripts\python.exe tools\smoke_scale.py --count 240
"""

from __future__ import annotations

import argparse
import os
import shutil
import struct
import sys
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


def _el(element_id: int, payload: bytes) -> bytes:
    eid = element_id.to_bytes((element_id.bit_length() + 7) // 8, "big")
    size = len(payload)
    length = 1
    while size >= (1 << (7 * length)) - 1:
        length += 1
    return eid + ((1 << (7 * length)) | size).to_bytes(length, "big") + payload


def _uint(value: int) -> bytes:
    return value.to_bytes((value.bit_length() + 7) // 8 or 1, "big")


def build_mkv(title: str, duration_ms: int) -> bytes:
    info = _el(
        0x1549A966,
        _el(0x2AD7B1, _uint(1_000_000))
        + _el(0x4489, struct.pack(">d", float(duration_ms)))
        + _el(0x7BA9, title.encode()),
    )
    tracks = _el(
        0x1654AE6B,
        _el(0xAE, _el(0xD7, _uint(1)) + _el(0x83, _uint(1)) + _el(0x86, b"V_MPEG4/ISO/AVC"))
        + _el(
            0xAE,
            _el(0xD7, _uint(2))
            + _el(0x83, _uint(2))
            + _el(0x86, b"A_AC3")
            + _el(0x22B59C, b"hin")
            + _el(0x22B59D, b"hi"),
        ),
    )
    segment = _el(0x18538067, info + tracks + _el(0x1F43B675, b"\x00" * 64))
    return _el(0x1A45DFA3, b"") + segment


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=240)
    parser.add_argument("--out", default="tools/scale.png")
    args = parser.parse_args()

    library = Path(os.environ.get("TELOVIE_LIBRARY_DIR", "") or ROOT / ".scale-lib")
    data = Path(os.environ.get("TELOVIE_DATA_DIR", "") or ROOT / ".scale-data")
    for folder in (library, data):
        shutil.rmtree(folder, ignore_errors=True)
        folder.mkdir(parents=True)
    os.environ["TELOVIE_LIBRARY_DIR"] = str(library)
    os.environ["TELOVIE_DATA_DIR"] = str(data)

    shows = ["Game of Thrones", "The Wire", "Severance", "Dark", "Chernobyl"]
    for index in range(args.count):
        show = shows[index % len(shows)]
        # 5 shows x 4 seasons x 12 episodes = 240 distinct names
        season = 1 + (index // (len(shows) * 12)) % 4
        episode = (index // len(shows)) % 12 + 1
        folder = library / show / f"Season {season:02d}"
        folder.mkdir(parents=True, exist_ok=True)
        name = f"{show.replace(' ', '.')}.S{season:02d}E{episode:02d}.1080p.mkv"
        (folder / name).write_bytes(build_mkv(name[:-4], 2_400_000 + index * 1000))

    paths = AppPaths.resolve()
    paths.ensure()
    configure_logging(paths.log_dir)
    print(f"library: {paths.library_dir} ({args.count} files)")

    app = QApplication(sys.argv[:1])
    app.setStyle("Fusion")
    db = Database(paths.db_path)
    window = MainWindow(paths, db)
    window.resize(1400, 900)
    window.show()

    started = time.monotonic()
    result = {"done": False}

    def tick() -> None:
        if window._scanner is not None or db.library.count() < args.count:
            if time.monotonic() - started > 120:
                print("FAIL: scan did not finish", file=sys.stderr)
                app.exit(1)
            return
        if result["done"]:
            return
        result["done"] = True

        scan_seconds = time.monotonic() - started
        t0 = time.perf_counter()
        window.refresh_grid()
        rebuild_ms = (time.perf_counter() - t0) * 1000
        app.processEvents()

        cards = window.view.flow.count()
        print(f"scan: {scan_seconds:.2f}s for {args.count} files")
        print(f"grid rebuild: {rebuild_ms:.0f}ms for {cards} cards")

        bar = window.view.scroll.verticalScrollBar()
        bar.setValue(bar.maximum())
        app.processEvents()

        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        window.grab().save(str(out), "PNG")
        print(f"screenshot: {out}")

        window._watcher.stop()
        db.close()
        app.exit(0)

    timer = QTimer()
    timer.timeout.connect(tick)
    timer.start(200)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
