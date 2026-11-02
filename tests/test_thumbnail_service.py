from __future__ import annotations

import hashlib
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtMultimedia import QVideoFrame  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from telovie.ui.thumbnail_service import ThumbnailService  # noqa: E402


def test_stale_frame_from_previous_file_is_ignored(tmp_path: Path):
    app = QApplication.instance() or QApplication([])
    first = tmp_path / "first.mkv"
    second = tmp_path / "second.mkv"
    first.touch()
    second.touch()
    service = ThumbnailService(tmp_path / "cache")
    service._current = str(second)
    service._generation = 2

    service._on_frame(str(first), 1, QVideoFrame())

    assert service._current == str(second)
    service.stop()
    app.processEvents()


def test_old_cached_thumbnails_are_not_reused(tmp_path: Path):
    app = QApplication.instance() or QApplication([])
    media = tmp_path / "episode.mkv"
    media.write_bytes(b"video")
    cache_dir = tmp_path / "cache"
    service = ThumbnailService(cache_dir)
    stat = media.stat()
    legacy_identity = (
        f"{media.resolve()}|{stat.st_size}|{stat.st_mtime_ns}".casefold()
    )
    legacy_key = hashlib.sha256(legacy_identity.encode("utf-8")).hexdigest()
    cache_dir.mkdir()
    (cache_dir / f"{legacy_key}.jpg").write_bytes(b"old thumbnail")

    assert service.cache_path(media) is None
    service.stop()
    app.processEvents()
