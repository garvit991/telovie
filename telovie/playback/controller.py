"""One QMediaPlayer, one QAudioOutput, and a small signal surface.

Everything here runs on the GUI thread. The scanner never touches it. Phase 5
adds position saving and resume on top of ``loaded``; Phase 6 adds track memory.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QObject, QTimer, QUrl, Signal
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer

from telovie.config import PROGRESS_SAVE_INTERVAL_MS
from telovie.mkv.parser import TrackInfo
from telovie.playback.resume import evaluate_progress, should_resume
from telovie.playback.tracks import choose_track

__all__ = ["PlayerController"]

log = logging.getLogger(__name__)


class PlayerController(QObject):
    """Thin wrapper that keeps media state in one place for the views."""

    positionChanged = Signal(int)
    durationChanged = Signal(int)
    bufferedChanged = Signal(int)
    playbackStateChanged = Signal(object)
    mediaStatusChanged = Signal(object)
    volumeChanged = Signal(int)
    mutedChanged = Signal(bool)
    errorOccurred = Signal(object, str)
    loaded = Signal()  # first LoadedMedia for the current source
    resumeRequested = Signal(int)
    tracksChanged = Signal()

    def __init__(
        self, parent: QObject | None = None, *, playback_repo=None
    ) -> None:
        super().__init__(parent)
        self._player = QMediaPlayer(self)
        self._audio = QAudioOutput(self)
        self._player.setAudioOutput(self._audio)

        self._volume = 80
        self._muted = False
        self._loaded_source = False
        self._source_path: str | None = None
        self._current_media_id: int | None = None
        self._playback_repo = playback_repo
        self._last_position_ms = 0
        self._last_saved_position_ms = 0
        self._is_completed = False
        self._pending_autoplay = True
        self._resume_position_ms = 0
        self._audio_tracks: list[TrackInfo] = []
        self._subtitle_tracks: list[TrackInfo] = []
        self._audio_languages: list[str] = []
        self._subtitle_languages: list[str] = []

        self._player.positionChanged.connect(self._on_position)
        self._player.durationChanged.connect(self._on_duration)
        self._player.playbackStateChanged.connect(self._on_playback_state)
        self._player.mediaStatusChanged.connect(self._on_media_status)
        self._player.errorOccurred.connect(self._on_error)
        self._player.tracksChanged.connect(self._on_tracks_changed)

        # Qt 6.12 has bufferedTimeRange() but no change signal, so poll it while
        # playing. 500 ms is plenty for a tint on a 4 px groove.
        self._buffer_timer = QTimer(self)
        self._buffer_timer.setInterval(500)
        self._buffer_timer.timeout.connect(self._poll_buffer)
        self._last_buffered = 0

        self._save_timer = QTimer(self)
        self._save_timer.setInterval(PROGRESS_SAVE_INTERVAL_MS)
        self._save_timer.setSingleShot(False)
        self._save_timer.timeout.connect(self._flush_timer_position)

        self._audio.setVolume(self._volume / 100.0)

    # -- source ----------------------------------------------------------

    def set_progress_store(self, playback_repo, media_id: int | None = None) -> None:
        if self._current_media_id is not None and self._current_media_id != media_id:
            self._persist_position(force=True)
        self._playback_repo = playback_repo
        if media_id is not None:
            self._current_media_id = int(media_id)
            self._last_saved_position_ms = self._load_last_position_ms()
            self._is_completed = self._load_is_completed()

    def set_track_metadata(
        self,
        audio_tracks: list[TrackInfo],
        subtitle_tracks: list[TrackInfo],
        audio_languages: list[str],
        subtitle_languages: list[str],
    ) -> None:
        self._audio_tracks = list(audio_tracks)
        self._subtitle_tracks = list(subtitle_tracks)
        self._audio_languages = list(audio_languages)
        self._subtitle_languages = list(subtitle_languages)
        self.tracksChanged.emit()

    def update_track_preferences(
        self, audio_languages: list[str], subtitle_languages: list[str]
    ) -> None:
        self._audio_languages = list(audio_languages)
        self._subtitle_languages = list(subtitle_languages)
        if self._loaded_source:
            self._apply_track_selection()

    @property
    def audio_track_count(self) -> int:
        return len(self._player.audioTracks())

    @property
    def subtitle_track_count(self) -> int:
        return len(self._player.subtitleTracks())

    @property
    def audio_track_metadata(self) -> tuple[TrackInfo, ...]:
        return tuple(self._audio_tracks)

    @property
    def subtitle_track_metadata(self) -> tuple[TrackInfo, ...]:
        return tuple(self._subtitle_tracks)

    @property
    def active_audio_track(self) -> int:
        return int(self._player.activeAudioTrack())

    @property
    def active_subtitle_track(self) -> int:
        return int(self._player.activeSubtitleTrack())

    def select_audio_track(self, index: int) -> None:
        if not 0 <= index < self.audio_track_count:
            raise ValueError(f"audio track index out of range: {index}")
        self._player.setActiveAudioTrack(index)
        if self._playback_repo is not None and self._current_media_id is not None:
            self._playback_repo.set_audio_track(self._current_media_id, index)
        log.info("tracks: audio %d (manual)", index + 1)
        self.tracksChanged.emit()

    def select_subtitle_track(self, index: int) -> None:
        if index != -1 and not 0 <= index < self.subtitle_track_count:
            raise ValueError(f"subtitle track index out of range: {index}")
        self._player.setActiveSubtitleTrack(index)
        if self._playback_repo is not None and self._current_media_id is not None:
            self._playback_repo.set_subtitle_track(self._current_media_id, index)
        log.info(
            "tracks: subs %s (manual)", "off" if index == -1 else index + 1
        )
        self.tracksChanged.emit()

    def _load_last_position_ms(self) -> int:
        if self._playback_repo is None or self._current_media_id is None:
            return 0
        state = self._playback_repo.get(self._current_media_id)
        if state is None:
            return 0
        return int(state["LastPosition"])

    def _load_is_completed(self) -> bool:
        if self._playback_repo is None or self._current_media_id is None:
            return False
        state = self._playback_repo.get(self._current_media_id)
        if state is None:
            return False
        return bool(state["IsCompleted"])

    def open(self, path: str, *, autoplay: bool = True) -> None:
        self._source_path = path
        self._loaded_source = False
        self._pending_autoplay = bool(autoplay)
        self._last_position_ms = 0
        self._resume_position_ms = 0
        self._save_timer.stop()
        media_id = self._current_media_id
        self._current_media_id = None
        try:
            self._player.stop()
            self._player.setSource(QUrl.fromLocalFile(path))
        finally:
            self._current_media_id = media_id

    def close(self) -> None:
        """Stop and drop the source so Windows releases the file handle."""
        self._persist_position(force=True)
        self._save_timer.stop()
        self._player.stop()
        self._player.setSource(QUrl())
        self._loaded_source = False
        self._source_path = None
        self._last_position_ms = 0
        self._last_saved_position_ms = 0
        self._is_completed = False
        self._resume_position_ms = 0
        self._current_media_id = None

    @property
    def source_path(self) -> str | None:
        return self._source_path

    def set_video_output(self, target) -> None:
        """Bind the video target (e.g. QVideoWidget or QVideoSink)."""
        self._player.setVideoOutput(target)

    # -- transport -------------------------------------------------------

    def play(self) -> None:
        self._player.play()

    def pause(self) -> None:
        self._player.pause()

    def toggle(self) -> None:
        if self.is_playing:
            self.pause()
        else:
            self.play()

    def seek(self, position_ms: int) -> None:
        target = max(0, int(position_ms))
        self._last_position_ms = target
        self._player.setPosition(target)
        self._persist_position(force=True)

    def stop(self) -> None:
        self._persist_position(force=True)
        self._player.stop()

    @property
    def is_playing(self) -> bool:
        return (
            self._player.playbackState()
            == QMediaPlayer.PlaybackState.PlayingState
        )

    @property
    def playback_state(self) -> QMediaPlayer.PlaybackState:
        return self._player.playbackState()

    @property
    def media_status(self) -> QMediaPlayer.MediaStatus:
        return self._player.mediaStatus()

    @property
    def position(self) -> int:
        return int(self._player.position())

    @property
    def duration(self) -> int:
        return int(self._player.duration())

    # -- audio -----------------------------------------------------------

    @property
    def volume(self) -> int:
        return self._volume

    def set_volume(self, value: int) -> None:
        volume = max(0, min(100, int(value)))
        if volume == self._volume:
            return
        self._volume = volume
        self._audio.setVolume(volume / 100.0)
        if volume > 0 and self._muted:
            self.set_muted(False)
        self.volumeChanged.emit(volume)

    @property
    def muted(self) -> bool:
        return self._muted

    def set_muted(self, muted: bool) -> None:
        muted = bool(muted)
        if muted == self._muted:
            return
        self._muted = muted
        self._audio.setMuted(muted)
        self.mutedChanged.emit(muted)

    def toggle_mute(self) -> None:
        self.set_muted(not self._muted)

    # -- slots -----------------------------------------------------------

    def _on_position(self, position: int) -> None:
        self._last_position_ms = int(position)
        if not self._save_timer.isActive():
            self._save_timer.start(PROGRESS_SAVE_INTERVAL_MS)
        self.positionChanged.emit(int(position))

    def _on_duration(self, duration: int) -> None:
        self.durationChanged.emit(int(duration))

    def _on_playback_state(self, state) -> None:
        self.playbackStateChanged.emit(state)
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self._poll_buffer()
            self._buffer_timer.start()
            self._save_timer.start(PROGRESS_SAVE_INTERVAL_MS)
        else:
            self._buffer_timer.stop()
            self._persist_position(force=True)
            self._save_timer.stop()

    def _poll_buffer(self) -> None:
        try:
            latest = int(self._player.bufferedTimeRange().latestTime())
        except (AttributeError, TypeError):
            latest = 0
        if latest != self._last_buffered:
            self._last_buffered = latest
            self.bufferedChanged.emit(latest)

    def _on_media_status(self, status: QMediaPlayer.MediaStatus) -> None:
        self.mediaStatusChanged.emit(status)
        if status == QMediaPlayer.MediaStatus.LoadedMedia and not self._loaded_source:
            self._loaded_source = True
            if self._playback_repo is not None and self._current_media_id is not None:
                self._playback_repo.increment_play_count(self._current_media_id)
            self.loaded.emit()
            self._apply_track_selection()
            self._apply_resume_if_needed()
        elif status == QMediaPlayer.MediaStatus.EndOfMedia:
            self._persist_position(force=True, end_of_media=True)

    def _on_tracks_changed(self) -> None:
        self.tracksChanged.emit()
        if self._loaded_source and self.media_status == QMediaPlayer.MediaStatus.LoadedMedia:
            self._apply_track_selection()

    def _saved_track_choices(self) -> tuple[int | None, int | None]:
        if self._playback_repo is None or self._current_media_id is None:
            return None, None
        state = self._playback_repo.get(self._current_media_id)
        if state is None:
            return None, None
        audio = state["AudioTrackIndex"]
        subtitles = state["SubtitleTrackIndex"]
        return (
            None if audio is None else int(audio),
            None if subtitles is None else int(subtitles),
        )

    def _apply_track_selection(self) -> None:
        audio_count = self.audio_track_count
        subtitle_count = self.subtitle_track_count
        if audio_count != len(self._audio_tracks):
            log.warning(
                "tracks: audio metadata count %d does not match Qt count %d; "
                "leaving container selection",
                len(self._audio_tracks),
                audio_count,
            )
        if subtitle_count != len(self._subtitle_tracks):
            log.warning(
                "tracks: subtitle metadata count %d does not match Qt count %d; "
                "leaving container selection",
                len(self._subtitle_tracks),
                subtitle_count,
            )

        saved_audio, saved_subtitle = self._saved_track_choices()
        audio_metadata_matches = audio_count == len(self._audio_tracks)
        subtitle_metadata_matches = subtitle_count == len(self._subtitle_tracks)
        audio_choice = (
            choose_track(self._audio_tracks, saved_audio, self._audio_languages)
            if audio_metadata_matches
            else None
        )
        subtitle_choice = (
            choose_track(
                self._subtitle_tracks,
                saved_subtitle,
                self._subtitle_languages,
                subtitles=True,
            )
            if subtitle_metadata_matches
            else None
        )
        decisions: list[str] = []
        if (
            audio_choice is not None
            and audio_choice.index is not None
            and 0 <= audio_choice.index < audio_count
        ):
            self._player.setActiveAudioTrack(audio_choice.index)
            decisions.append(f"audio {audio_choice.index + 1} ({audio_choice.source})")
        else:
            decisions.append(f"audio {self.active_audio_track} (container default)")

        if subtitle_choice is not None and subtitle_choice.index == -1:
            self._player.setActiveSubtitleTrack(-1)
            decisions.append(f"subs off ({subtitle_choice.source})")
        elif (
            subtitle_choice is not None
            and subtitle_choice.index is not None
            and 0 <= subtitle_choice.index < subtitle_count
        ):
            self._player.setActiveSubtitleTrack(subtitle_choice.index)
            decisions.append(f"subs {subtitle_choice.index + 1} ({subtitle_choice.source})")
        else:
            decisions.append(f"subs {self.active_subtitle_track} (container default)")
        log.info("tracks: %s | %s", *decisions)
        self.tracksChanged.emit()

    def _apply_resume_if_needed(self) -> None:
        if self._playback_repo is None or self._current_media_id is None:
            if self._pending_autoplay:
                self.play()
            return

        state = self._playback_repo.get(self._current_media_id)
        if state is None:
            if self._pending_autoplay:
                self.play()
            return

        last_position_ms = int(state["LastPosition"])
        is_completed = bool(state["IsCompleted"])
        if should_resume(last_position_ms, self.duration, is_completed):
            self._resume_position_ms = last_position_ms
            self.resumeRequested.emit(last_position_ms)
            self._last_position_ms = last_position_ms
            self._last_saved_position_ms = last_position_ms
            self._is_completed = is_completed
            self._player.pause()
            self.seek(last_position_ms)
            if self._pending_autoplay:
                self.play()
            return

        if self._pending_autoplay:
            self.play()

    def _persist_position(self, *, force: bool = False, end_of_media: bool = False) -> None:
        if self._playback_repo is None or self._current_media_id is None:
            return

        position_ms = int(self._last_position_ms)
        if position_ms == 0 and not force and not end_of_media:
            return

        decision = evaluate_progress(
            position_ms,
            self.duration,
            last_saved_position_ms=self._last_saved_position_ms,
            end_of_media=end_of_media,
            is_completed=self._is_completed,
        )
        if not decision.should_save:
            return

        self._playback_repo.save_position(
            self._current_media_id,
            int(decision.position_ms),
            completed=decision.is_completed,
        )
        self._last_saved_position_ms = int(decision.position_ms)
        self._is_completed = bool(decision.is_completed)

    def _flush_timer_position(self) -> None:
        self._persist_position(force=False)

    def _on_error(self, error: QMediaPlayer.Error, message: str) -> None:
        if error == QMediaPlayer.Error.NoError:
            return
        detail = message or "The file could not be played."
        log.error("Media playback failed (%s): %s", error.name, detail)
        self.errorOccurred.emit(error, detail)
