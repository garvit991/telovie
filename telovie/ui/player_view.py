"""Full-window player: video surface, transport bar, fullscreen."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QCursor, QKeySequence, QShortcut
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMenu,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from telovie.mkv.parser import TrackInfo
from telovie.playback.controller import PlayerController
from telovie.ui.controls import IconButton, SeekSlider, VolumeSlider
from telovie.util.languages import display_name
from telovie.util.timefmt import format_ms

BARS_TIMEOUT_MS = 2600


class PlayerView(QWidget):
    backRequested = Signal()
    preferencesRequested = Signal()
    volumeChanged = Signal(int)
    fullscreenChanged = Signal(bool)

    def __init__(
        self, controller: PlayerController, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.controller = controller
        self._duration = 0
        self._scrubbing = False
        self._fullscreen = False
        self._saved_window_state = None
        self._shortcuts: list[QShortcut] = []

        self.setObjectName("PlayerView")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)

        self._bars_timer = QTimer(self)
        self._bars_timer.setSingleShot(True)
        self._bars_timer.timeout.connect(self._maybe_hide_bars)

        self._build_ui()
        self.controller.set_video_output(self.video)
        self._connect_signals()
        self._install_shortcuts()

    # -- construction -----------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.top_bar = QWidget(self)
        self.top_bar.setObjectName("PlayerTop")
        top = QHBoxLayout(self.top_bar)
        top.setContentsMargins(12, 8, 16, 8)
        top.setSpacing(10)

        self.back_button = IconButton("back", "Back to library (Esc)", size=34)
        top.addWidget(self.back_button)

        self.title_label = QLabel()
        self.title_label.setObjectName("PlayerTitle")
        self.title_label.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred
        )
        top.addWidget(self.title_label, 1)
        self.preferences_button = QToolButton(self.top_bar)
        self.preferences_button.setObjectName("TrackMenu")
        self.preferences_button.setText("Preferences")
        self.preferences_button.setCursor(Qt.CursorShape.PointingHandCursor)
        top.addWidget(self.preferences_button)
        root.addWidget(self.top_bar)

        self.video_area = QWidget(self)
        self.video_area.setObjectName("VideoArea")
        video_layout = QVBoxLayout(self.video_area)
        video_layout.setContentsMargins(0, 0, 0, 0)

        self.video = QVideoWidget(self.video_area)
        self.video.setMinimumSize(320, 180)
        self.video.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.video.setMouseTracking(True)
        self.video.installEventFilter(self)
        video_layout.addWidget(self.video)

        self.error_label = QLabel(self.video_area)
        self.error_label.setObjectName("PlayerError")
        self.error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.error_label.setWordWrap(True)
        self.error_label.hide()

        root.addWidget(self.video_area, 1)

        self.bottom_bar = QWidget(self)
        self.bottom_bar.setObjectName("PlayerBar")
        bar = QHBoxLayout(self.bottom_bar)
        bar.setContentsMargins(16, 10, 16, 10)
        bar.setSpacing(10)

        self.play_button = IconButton("play", "Play (Space)", size=38, icon_size=22)
        bar.addWidget(self.play_button)

        self.elapsed = QLabel("0:00")
        self.elapsed.setObjectName("Time")
        self.elapsed.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self.elapsed.setMinimumWidth(46)
        bar.addWidget(self.elapsed)

        self.seek = SeekSlider()
        self.seek.setEnabled(False)
        bar.addWidget(self.seek, 1)

        self.total = QLabel("0:00")
        self.total.setObjectName("Time")
        self.total.setMinimumWidth(46)
        bar.addWidget(self.total)

        bar.addSpacing(6)
        self.volume_button = IconButton("volume", "Mute (M)", size=32, icon_size=19)
        bar.addWidget(self.volume_button)
        self.volume = VolumeSlider()
        bar.addWidget(self.volume)

        self.audio_button = self._track_button("Audio")
        self.audio_menu = QMenu(self.audio_button)
        self.audio_button.setMenu(self.audio_menu)
        bar.addWidget(self.audio_button)

        self.subtitle_button = self._track_button("Captions")
        self.subtitle_menu = QMenu(self.subtitle_button)
        self.subtitle_button.setMenu(self.subtitle_menu)
        bar.addWidget(self.subtitle_button)

        self.fullscreen_button = IconButton(
            "fullscreen", "Fullscreen (F)", size=32, icon_size=18
        )
        bar.addWidget(self.fullscreen_button)

        root.addWidget(self.bottom_bar)

    def _track_button(self, label: str) -> QToolButton:
        button = QToolButton(self)
        button.setObjectName("TrackMenu")
        button.setText(label)
        button.setToolTip(f"Select {label.lower()}")
        button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        return button

    def _connect_signals(self) -> None:
        self.back_button.clicked.connect(self._request_back)
        self.preferences_button.clicked.connect(self.preferencesRequested)
        self.play_button.clicked.connect(self._toggle_playback)
        self.fullscreen_button.clicked.connect(self.toggle_fullscreen)

        self.seek.seekRequested.connect(self._on_seek_requested)
        self.seek.scrubStarted.connect(self._on_scrub_started)
        self.seek.scrubMoved.connect(self._on_scrub_moved)
        self.seek.scrubFinished.connect(self._on_scrub_finished)

        self.volume.valueChanged.connect(self._on_volume_slider)
        self.volume_button.clicked.connect(self.controller.toggle_mute)

        self.controller.positionChanged.connect(self._on_position)
        self.controller.durationChanged.connect(self._on_duration)
        self.controller.bufferedChanged.connect(self.seek.set_buffered)
        self.controller.playbackStateChanged.connect(self._on_playback_state)
        self.controller.mediaStatusChanged.connect(self._on_media_status)
        self.controller.volumeChanged.connect(self._on_volume_changed)
        self.controller.mutedChanged.connect(self._on_muted_changed)
        self.controller.errorOccurred.connect(self._on_error)
        self.controller.tracksChanged.connect(self._rebuild_track_menus)
        self.play_button.setEnabled(False)
        self._rebuild_track_menus()

    def _install_shortcuts(self) -> None:
        bindings = {
            "Space": self._toggle_playback,
            "Left": lambda: self._nudge(-10_000),
            "Right": lambda: self._nudge(10_000),
            "Up": lambda: self._nudge_volume(5),
            "Down": lambda: self._nudge_volume(-5),
            "M": self.controller.toggle_mute,
            "A": self._cycle_audio_track,
            "S": self._cycle_subtitle_track,
            "F": self.toggle_fullscreen,
            "Esc": self._on_escape,
            "Backspace": self._request_back,
        }
        for key, slot in bindings.items():
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            shortcut.activated.connect(slot)
            self._shortcuts.append(shortcut)

    # -- public API -------------------------------------------------------

    def open_media(self, title: str, path: str, duration_ms: int = 0) -> None:
        self.title_label.setText(title)
        self.title_label.setToolTip(path)
        self._duration = max(0, int(duration_ms))
        self.seek.setRange(0, self._duration)
        self.seek.setValue(0)
        self.seek.set_buffered(0)
        self.seek.setEnabled(self._duration > 0)
        self.play_button.setEnabled(True)
        self.elapsed.setText("0:00")
        self.total.setText(format_ms(self._duration))
        self.error_label.hide()
        self._show_bars()
        self.setFocus()
        self.controller.open(path)

    def set_volume(self, value: int) -> None:
        """Apply a volume without treating it as a user edit."""
        self.controller.set_volume(int(value))
        self.volume.blockSignals(True)
        self.volume.setValue(self.controller.volume)
        self.volume.blockSignals(False)
        self._update_volume_icon()

    def stop_and_release(self) -> None:
        self.controller.close()
        self._duration = 0
        self.seek.setRange(0, 0)
        self.seek.setValue(0)
        self.seek.set_buffered(0)
        self.seek.setEnabled(False)
        self.elapsed.setText("0:00")
        self.total.setText("0:00")
        self.play_button.set_kind("play")
        self.play_button.setEnabled(False)
        self.audio_button.setEnabled(False)
        self.subtitle_button.setEnabled(False)
        self.error_label.hide()
        if self._fullscreen:
            self.set_fullscreen(False)

    def toggle_fullscreen(self) -> None:
        self.set_fullscreen(not self._fullscreen)

    def set_fullscreen(self, enabled: bool) -> None:
        if enabled == self._fullscreen:
            return
        self._fullscreen = enabled
        window = self.window()

        if enabled:
            self._saved_window_state = window.windowState()
            window.showFullScreen()
            self.fullscreen_button.set_kind("fullscreen_exit")
            self.fullscreen_button.setToolTip("Exit fullscreen (F)")
            self._show_bars()
            if self.controller.is_playing:
                self._bars_timer.start(BARS_TIMEOUT_MS)
        else:
            window.showNormal()
            if self._saved_window_state == Qt.WindowState.WindowMaximized:
                window.showMaximized()
            self.fullscreen_button.set_kind("fullscreen")
            self.fullscreen_button.setToolTip("Fullscreen (F)")
            self._show_bars()
            self._bars_timer.stop()

        self.fullscreenChanged.emit(enabled)

    @property
    def is_fullscreen(self) -> bool:
        return self._fullscreen

    # -- transport --------------------------------------------------------

    def _toggle_playback(self) -> None:
        controller = self.controller
        if (
            not controller.is_playing
            and self._duration
            and controller.position >= self._duration - 250
        ):
            controller.seek(0)
        controller.toggle()
        self._show_bars()

    def _nudge(self, delta_ms: int) -> None:
        if self._duration <= 0:
            return
        target = max(0, min(self._duration, self.controller.position + delta_ms))
        self.controller.seek(target)
        self.seek.setValue(target)
        self.elapsed.setText(format_ms(target))

    def _nudge_volume(self, delta: int) -> None:
        self.controller.set_volume(self.controller.volume + delta)

    def _cycle_audio_track(self) -> None:
        count = self.controller.audio_track_count
        if count:
            self.controller.select_audio_track(
                (self.controller.active_audio_track + 1) % count
            )

    def _cycle_subtitle_track(self) -> None:
        count = self.controller.subtitle_track_count
        if not count:
            return
        active = self.controller.active_subtitle_track
        self.controller.select_subtitle_track(
            (active + 2) % (count + 1) - 1
        )

    @staticmethod
    def _track_label(track: TrackInfo | None, kind: str, index: int) -> str:
        ordinal = index + 1
        prefix = "Audio" if kind == "audio" else "Caption"
        if track is None:
            return f"{prefix} {ordinal}"
        language = display_name(track.language) or "Unknown language"
        codec = track.codec.strip()
        codec = {
            "A_AC3": "AC-3",
            "A_EAC3": "E-AC-3",
            "A_AAC": "AAC",
            "A_OPUS": "Opus",
            "A_FLAC": "FLAC",
            "A_TRUEHD": "TrueHD",
            "S_TEXT/UTF8": "SRT",
            "S_TEXT/ASS": "ASS",
            "S_TEXT/SSA": "SSA",
            "S_HDMV/PGS": "PGS",
            "S_VOBSUB": "VobSub",
        }.get(codec, codec.removeprefix("A_").removeprefix("S_"))
        label = f"{prefix} {ordinal} · {language}"
        if codec:
            label += f" · {codec}"
        flags = []
        if track.is_default:
            flags.append("Default")
        if track.is_forced:
            flags.append("Forced")
        if flags:
            label += f" · {', '.join(flags)}"
        return label

    def _rebuild_track_menus(self) -> None:
        audio_count = self.controller.audio_track_count
        subtitle_count = self.controller.subtitle_track_count
        audio_metadata = self.controller.audio_track_metadata
        subtitle_metadata = self.controller.subtitle_track_metadata
        if audio_count != len(audio_metadata):
            audio_metadata = ()
        if subtitle_count != len(subtitle_metadata):
            subtitle_metadata = ()

        self.audio_menu.clear()
        self.audio_button.setEnabled(audio_count > 0)
        for index in range(audio_count):
            track = audio_metadata[index] if index < len(audio_metadata) else None
            action = self.audio_menu.addAction(
                self._track_label(track, "audio", index)
            )
            action.setCheckable(True)
            action.setChecked(index == self.controller.active_audio_track)
            action.triggered.connect(
                lambda _checked=False, track_index=index:
                self.controller.select_audio_track(track_index)
            )

        self.subtitle_menu.clear()
        self.subtitle_button.setEnabled(subtitle_count > 0)
        off_action = self.subtitle_menu.addAction("Captions off")
        off_action.setCheckable(True)
        off_action.setChecked(self.controller.active_subtitle_track < 0)
        off_action.triggered.connect(
            lambda _checked=False: self.controller.select_subtitle_track(-1)
        )
        self.subtitle_menu.addSeparator()
        for index in range(subtitle_count):
            track = (
                subtitle_metadata[index]
                if index < len(subtitle_metadata)
                else None
            )
            action = self.subtitle_menu.addAction(
                self._track_label(track, "subtitle", index)
            )
            action.setCheckable(True)
            action.setChecked(index == self.controller.active_subtitle_track)
            action.triggered.connect(
                lambda _checked=False, track_index=index:
                self.controller.select_subtitle_track(track_index)
            )

    def _request_back(self) -> None:
        if self._fullscreen:
            self.set_fullscreen(False)
            return
        self.backRequested.emit()

    def _on_escape(self) -> None:
        if self._fullscreen:
            self.set_fullscreen(False)
        else:
            self._request_back()

    # -- controller slots -------------------------------------------------

    def _on_position(self, position_ms: int) -> None:
        if self._scrubbing:
            return
        self.seek.setValue(int(position_ms))
        self.elapsed.setText(format_ms(position_ms))

    def _on_duration(self, duration_ms: int) -> None:
        if duration_ms > 0:
            self._duration = int(duration_ms)
        self.seek.setRange(0, self._duration)
        self.seek.setEnabled(self._duration > 0)
        self.total.setText(format_ms(self._duration))

    def _on_playback_state(self, state) -> None:
        playing = state == QMediaPlayer.PlaybackState.PlayingState
        self.play_button.set_kind("pause" if playing else "play")
        self.play_button.setToolTip("Pause (Space)" if playing else "Play (Space)")
        if self._fullscreen:
            if playing:
                self._bars_timer.start(BARS_TIMEOUT_MS)
            else:
                self._show_bars()

    def _on_media_status(self, status) -> None:
        if status == QMediaPlayer.MediaStatus.LoadedMedia:
            self.play_button.setEnabled(True)
            self.seek.setEnabled(self._duration > 0)
            self._rebuild_track_menus()
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self.play_button.set_kind("play")
            self.play_button.setToolTip("Play (Space)")
            self.seek.setValue(self._duration)

    def _on_error(self, _error, message: str) -> None:
        self.error_label.setText(
            "Playback failed\n\n"
            f"{message}\n\n"
            "The file may be damaged or use an unsupported codec or DRM format."
        )
        self.error_label.setGeometry(self.video_area.rect().adjusted(40, 40, -40, -40))
        self.error_label.show()
        self.error_label.raise_()
        self.play_button.set_kind("play")
        self.play_button.setEnabled(False)
        self.seek.setEnabled(False)
        self.audio_button.setEnabled(False)
        self.subtitle_button.setEnabled(False)

    def _on_volume_slider(self, value: int) -> None:
        self.controller.set_volume(int(value))

    def _on_volume_changed(self, value: int) -> None:
        self.volume.blockSignals(True)
        self.volume.setValue(int(value))
        self.volume.blockSignals(False)
        self._update_volume_icon()
        self.volumeChanged.emit(int(value))

    def _on_muted_changed(self, _muted: bool) -> None:
        self._update_volume_icon()

    def _update_volume_icon(self) -> None:
        muted = self.controller.muted or self.controller.volume <= 0
        self.volume_button.set_kind("muted" if muted else "volume")
        self.volume_button.setToolTip("Unmute (M)" if muted else "Mute (M)")

    # -- scrubbing --------------------------------------------------------

    def _on_scrub_started(self) -> None:
        self._scrubbing = True

    def _on_scrub_moved(self, value: int) -> None:
        self.elapsed.setText(format_ms(value))

    def _on_scrub_finished(self) -> None:
        self._scrubbing = False

    def _on_seek_requested(self, value: int) -> None:
        self.controller.seek(int(value))
        self.elapsed.setText(format_ms(value))

    # -- fullscreen chrome ------------------------------------------------

    def _show_bars(self) -> None:
        self.top_bar.show()
        self.bottom_bar.show()
        self.unsetCursor()
        self.video.unsetCursor()
        if self._fullscreen and self.controller.is_playing:
            self._bars_timer.start(BARS_TIMEOUT_MS)

    def _hide_bars(self) -> None:
        self.top_bar.hide()
        self.bottom_bar.hide()
        self.setCursor(Qt.CursorShape.BlankCursor)
        self.video.setCursor(Qt.CursorShape.BlankCursor)

    def _maybe_hide_bars(self) -> None:
        if not self._fullscreen or not self.controller.is_playing:
            return
        local = self.mapFromGlobal(QCursor.pos())
        if self.top_bar.geometry().contains(local) or self.bottom_bar.geometry().contains(
            local
        ):
            self._bars_timer.start(BARS_TIMEOUT_MS)
            return
        self._hide_bars()

    # -- events -----------------------------------------------------------

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._fullscreen:
            self._show_bars()
        super().mouseMoveEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.toggle_fullscreen()
        super().mouseDoubleClickEvent(event)

    def eventFilter(self, watched, event) -> bool:  # noqa: N802
        if watched is self.video:
            if event.type() == QEvent.Type.MouseMove and self._fullscreen:
                self._show_bars()
            elif event.type() == QEvent.Type.MouseButtonDblClick:
                self.toggle_fullscreen()
                return True
        return super().eventFilter(watched, event)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if self.error_label.isVisible():
            self.error_label.setGeometry(self.video_area.rect().adjusted(40, 40, -40, -40))
