"""Asynchronously extract and cache poster frames for library cards."""

from __future__ import annotations

import hashlib
import logging
from collections import deque
from pathlib import Path

from PySide6.QtCore import QObject, QRect, QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QImage
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer, QVideoFrame, QVideoSink

log = logging.getLogger(__name__)

THUMBNAIL_SIZE = QSize(480, 270)


class ThumbnailService(QObject):
    """Extract one muted video frame at a time without blocking the UI."""

    thumbnailReady = Signal(str, str)

    def __init__(self, cache_dir: Path, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.cache_dir = cache_dir
        self._queue: deque[str] = deque()
        self._queued: set[str] = set()
        self._current: str | None = None
        self._target_position = 0
        self._paused = False
        self._generation = 0
        self._player: QMediaPlayer | None = None
        self._audio: QAudioOutput | None = None
        self._sink: QVideoSink | None = None

        self._timeout = QTimer(self)
        self._timeout.setSingleShot(True)
        self._timeout.setInterval(15_000)
        self._timeout.timeout.connect(self._finish_current)

    def cache_path(self, media_path: str | Path) -> Path | None:
        cached = self._cache_path_for_existing_file(str(media_path))
        if cached is None:
            return None
        return cached if cached.is_file() else None

    def request(self, media_paths: list[str]) -> None:
        for media_path in media_paths:
            path = Path(media_path)
            if not path.is_file() or self.cache_path(path) is not None:
                continue
            key = str(path.resolve()).casefold()
            if key not in self._queued and (
                self._current is None
                or str(Path(self._current).resolve()).casefold() != key
            ):
                self._queued.add(key)
                self._queue.append(str(path))
        self._start_next()

    def pause(self) -> None:
        self._paused = True
        if self._current is not None:
            path = self._current
            self._current = None
            self._timeout.stop()
            self._release_player()
            self._queue.appendleft(path)
            self._queued.add(str(Path(path).resolve()).casefold())

    def resume(self) -> None:
        self._paused = False
        self._start_next()

    def stop(self) -> None:
        self._paused = True
        self._current = None
        self._queue.clear()
        self._queued.clear()
        self._timeout.stop()
        self._release_player()

    def _start_next(self) -> None:
        if self._paused or self._current is not None or not self._queue:
            return
        self._current = self._queue.popleft()
        self._queued.discard(str(Path(self._current).resolve()).casefold())
        self._target_position = 0
        self._generation += 1
        generation = self._generation
        path = self._current

        player = QMediaPlayer(self)
        audio = QAudioOutput(self)
        audio.setMuted(True)
        player.setAudioOutput(audio)
        sink = QVideoSink(self)
        player.setVideoSink(sink)
        sink.videoFrameChanged.connect(
            lambda frame, p=path, g=generation: self._on_frame(p, g, frame)
        )
        player.mediaStatusChanged.connect(
            lambda status, p=path, g=generation: self._on_media_status(p, g, status)
        )
        player.errorOccurred.connect(
            lambda error, message, p=path, g=generation: self._on_error(
                p, g, error, message
            )
        )
        self._player, self._audio, self._sink = player, audio, sink
        self._timeout.start()
        player.setSource(QUrl.fromLocalFile(path))

    def _on_media_status(
        self, path: str, generation: int, status: QMediaPlayer.MediaStatus
    ) -> None:
        if (
            path != self._current
            or generation != self._generation
            or self._player is None
            or status != QMediaPlayer.MediaStatus.LoadedMedia
        ):
            return
        duration = self._player.duration()
        self._target_position = min(10_000, max(1_000, duration // 10))
        self._player.setPosition(self._target_position)
        self._player.play()

    def _on_frame(self, path: str, generation: int, frame: QVideoFrame) -> None:
        if (
            path != self._current
            or generation != self._generation
            or self._player is None
            or self._player.position() < self._target_position
        ):
            return
        frame_time = frame.startTime()
        if frame_time >= 0 and frame_time < self._target_position * 1_000:
            return
        image = frame.toImage()
        if image.isNull():
            return
        self._save_current(path, generation, image)

    def _on_error(
        self, path: str, generation: int, _error, message: str
    ) -> None:
        if path != self._current or generation != self._generation:
            return
        log.debug("Could not extract thumbnail from %s: %s", path, message)
        self._finish_current(path, generation)

    def _save_current(self, path: str, generation: int, image: QImage) -> None:
        if path != self._current or generation != self._generation:
            return
        self._current = None
        self._timeout.stop()
        self._release_player()
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            scaled = image.scaled(
                THUMBNAIL_SIZE,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            x = max(0, (scaled.width() - THUMBNAIL_SIZE.width()) // 2)
            y = max(0, (scaled.height() - THUMBNAIL_SIZE.height()) // 2)
            thumbnail = scaled.copy(
                QRect(x, y, THUMBNAIL_SIZE.width(), THUMBNAIL_SIZE.height())
            ).convertToFormat(QImage.Format.Format_RGB32)
            cached = self._cache_path_for_existing_file(path)
            if cached is None:
                log.debug("Media file disappeared before thumbnail caching: %s", path)
            elif thumbnail.save(str(cached), "JPEG", 85):
                self.thumbnailReady.emit(path, str(cached))
            else:
                log.warning("Could not write thumbnail cache file %s", cached)
        except OSError:
            log.exception("Could not cache thumbnail for %s", path)
        self._start_next()

    def _finish_current(
        self, path: str | None = None, generation: int | None = None
    ) -> None:
        if self._current is None or (
            path is not None
            and (path != self._current or generation != self._generation)
        ):
            return
        self._current = None
        self._timeout.stop()
        self._release_player()
        self._start_next()

    def _release_player(self) -> None:
        player, audio, sink = self._player, self._audio, self._sink
        self._player = None
        self._audio = None
        self._sink = None
        if player is not None:
            player.stop()
            player.setSource(QUrl())
            player.deleteLater()
        if audio is not None:
            audio.deleteLater()
        if sink is not None:
            sink.deleteLater()

    def _cache_path_for_existing_file(self, media_path: str) -> Path | None:
        path = Path(media_path)
        try:
            stat = path.stat()
        except OSError:
            return None
        identity = f"v2|{path.resolve()}|{stat.st_size}|{stat.st_mtime_ns}".casefold()
        key = hashlib.sha256(identity.encode("utf-8")).hexdigest()
        return self.cache_dir / f"{key}.jpg"
