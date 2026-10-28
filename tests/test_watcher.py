from __future__ import annotations

import time
from pathlib import Path

import pytest
from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer

from telovie.library.watcher import LibraryWatcher


@pytest.fixture(scope="module")
def qapp():
    app = QCoreApplication.instance() or QCoreApplication([])
    yield app


def _touch(path: Path, content: bytes = b"x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _wait_for_signal(signal, timeout_ms: int = 4_000) -> bool:
    """Run the Qt event loop until `signal` fires or the timeout expires."""
    loop = QEventLoop()
    seen = {"hit": False}

    def on_signal(*_args) -> None:
        seen["hit"] = True
        loop.quit()

    signal.connect(on_signal)
    timer = QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(loop.quit)
    timer.start(timeout_ms)
    try:
        loop.exec()
    finally:
        signal.disconnect(on_signal)
        timer.stop()
    return seen["hit"]


def test_watcher_ignores_a_static_folder(qapp, tmp_path: Path):
    _touch(tmp_path / "Show" / "e01.mkv")
    watcher = LibraryWatcher(tmp_path, interval_ms=30)
    watcher.start()
    try:
        assert not _wait_for_signal(watcher.changed, timeout_ms=400)
    finally:
        watcher.stop()


def test_watcher_detects_a_new_file_after_it_settles(qapp, tmp_path: Path):
    watcher = LibraryWatcher(tmp_path, interval_ms=30)
    watcher.start()
    try:
        _touch(tmp_path / "Show" / "e01.mkv", b"a" * 8)
        assert _wait_for_signal(watcher.changed)
    finally:
        watcher.stop()


def test_watcher_waits_for_a_file_to_stop_growing(qapp, tmp_path: Path):
    watcher = LibraryWatcher(tmp_path, interval_ms=30)
    watcher.start()
    target = tmp_path / "Show" / "e01.mkv"
    try:
        # a half-extracted file keeps changing size; the first change must not
        # fire on its own, only the stable snapshot after it
        _touch(target, b"a" * 4)
        time.sleep(0.05)
        _touch(target, b"a" * 32)
        assert _wait_for_signal(watcher.changed)
        assert watcher._last[str(target)][0] == 32
    finally:
        watcher.stop()


def test_watcher_detects_a_removed_file(qapp, tmp_path: Path):
    target = tmp_path / "Show" / "e01.mkv"
    _touch(target)
    watcher = LibraryWatcher(tmp_path, interval_ms=30)
    watcher.start()
    try:
        target.unlink()
        assert _wait_for_signal(watcher.changed)
    finally:
        watcher.stop()


def test_sync_resets_the_baseline(qapp, tmp_path: Path):
    watcher = LibraryWatcher(tmp_path, interval_ms=30)
    watcher.start()
    try:
        _touch(tmp_path / "e01.mkv")
        # a scan finishing right after the drop must not cause a second refresh
        watcher.sync()
        assert not _wait_for_signal(watcher.changed, timeout_ms=400)
    finally:
        watcher.stop()
