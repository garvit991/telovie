"""Main window: owns the grid, the scanner lifecycle and the watcher."""

from __future__ import annotations

import logging
import time
from pathlib import Path

from PySide6.QtCore import QEvent, QSettings, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QLabel,
    QMainWindow,
    QMessageBox,
    QStackedWidget,
    QStatusBar,
)

from telovie.config import APP_NAME, AppPaths
from telovie.db import Database, MediaUpsert
from telovie.library.episodes import next_episode_recommendations
from telovie.library.models import ScanSummary
from telovie.library.scanner import ScanWorker
from telovie.library.watcher import LibraryWatcher
from telovie.mkv.parser import display_title, parse_mkv
from telovie.playback.controller import PlayerController
from telovie.ui.library_view import LibraryView
from telovie.ui.media_card import CardData
from telovie.ui.player_view import PlayerView
from telovie.ui.preferences_dialog import PreferencesDialog
from telovie.ui.theme import APP_QSS
from telovie.ui.toast import Toast
from telovie.util.timefmt import format_ms

log = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    def __init__(self, paths: AppPaths, db: Database) -> None:
        super().__init__()
        self.paths = paths
        self.db = db
        self._settings = QSettings("Telovie", "Telovie")
        self._scanner: ScanWorker | None = None
        self._scan_queued = False
        self._last_scan_at = 0.0
        self._current_media_id: int | None = None
        self._handling_playback_error = False

        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(900, 600)
        self.resize(1200, 780)
        self.setStyleSheet(APP_QSS)

        self.view = LibraryView(paths.library_dir, self)
        self.player = PlayerView(PlayerController(self), self)
        self.stack = QStackedWidget(self)
        self.stack.addWidget(self.view)
        self.stack.addWidget(self.player)
        self.setCentralWidget(self.stack)

        self._toast = Toast(self)

        status = QStatusBar(self)
        self.setStatusBar(status)
        self._status = QLabel("Ready")
        self._count = QLabel("")
        status.addWidget(self._status, 1)
        status.addPermanentWidget(self._count)

        self._volume_timer = QTimer(self)
        self._volume_timer.setSingleShot(True)
        self._volume_timer.setInterval(500)
        self._volume_timer.timeout.connect(self._save_volume)
        self._pending_volume = self.db.prefs.get().volume
        self.player.set_volume(self._pending_volume)

        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(350)
        self._refresh_timer.timeout.connect(self.refresh_grid)

        self._watcher = LibraryWatcher(paths.library_dir, parent=self)
        self._watcher.changed.connect(self._on_folder_changed)

        self.view.playRequested.connect(self._on_play_requested)
        self.view.startOverRequested.connect(self._on_start_over)
        self.view.revealRequested.connect(self._on_reveal)
        self.view.removeRequested.connect(self._on_remove)
        self.view.openFolderRequested.connect(self._open_folder)
        self.view.refreshRequested.connect(self.start_scan)
        self.view.preferencesRequested.connect(self._open_preferences)
        self.view.filtersChanged.connect(lambda *_: self.refresh_grid())

        self.player.controller.resumeRequested.connect(self._on_resume_requested)
        self.player.controller.errorOccurred.connect(self._on_playback_error)
        self.player.backRequested.connect(self._on_player_back)
        self.player.preferencesRequested.connect(self._open_preferences)
        self.player.volumeChanged.connect(self._on_volume_changed)
        self.player.fullscreenChanged.connect(self._on_fullscreen_changed)

        self._search_shortcut = QShortcut(QKeySequence("Ctrl+F"), self)
        self._search_shortcut.activated.connect(self.view.focus_search)
        self._refresh_shortcut = QShortcut(QKeySequence("F5"), self)
        self._refresh_shortcut.activated.connect(self.start_scan)

        geometry = self._settings.value("window/geometry")
        if geometry:
            self.restoreGeometry(geometry)

        QTimer.singleShot(0, self._startup)

    # -- lifecycle --------------------------------------------------------

    def _startup(self) -> None:
        self.refresh_grid()
        self._watcher.start()
        self.start_scan()

    def closeEvent(self, event) -> None:  # noqa: N802
        self._watcher.stop()
        self._volume_timer.stop()
        self._save_volume()
        # release the media file handle before the window goes away
        self.player.controller.close()
        if self._scanner is not None and self._scanner.isRunning():
            self._scanner.requestInterruption()
            self._scanner.wait(2_000)
        self._settings.setValue("window/geometry", self.saveGeometry())
        super().closeEvent(event)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._toast.parent_resized()

    def changeEvent(self, event) -> None:  # noqa: N802
        if event.type() == QEvent.Type.ActivationChange and self.isActiveWindow():
            if time.monotonic() - self._last_scan_at > 15:
                self.start_scan()
        super().changeEvent(event)

    # -- scanning ---------------------------------------------------------

    def start_scan(self, force: bool = False) -> None:
        if self._scanner is not None and self._scanner.isRunning():
            self._scan_queued = True
            return

        stamps = {} if force else self.db.library.file_stamps()
        worker = ScanWorker(self.paths.library_dir, stamps, self)
        worker.progress.connect(self._on_progress)
        worker.batch.connect(self._on_batch)
        worker.finished_scan.connect(self._on_finished)
        worker.failed.connect(self._on_failed)
        # delete only once the thread has actually stopped
        worker.finished.connect(worker.deleteLater)

        self._scanner = worker
        self._last_scan_at = time.monotonic()
        self._set_status("Indexing library…")
        worker.start()

    def _on_progress(self, done: int, total: int, name: str) -> None:
        if total:
            short = name if len(name) <= 58 else f"{name[:55]}…"
            self._set_status(f"Indexing {done} of {total} · {short}")

    def _on_batch(self, items: list) -> None:
        upserts = [
            MediaUpsert(
                title=item.title,
                file_path=item.file_path,
                total_duration=item.duration_ms,
                file_size=item.file_size,
                file_mtime=item.file_mtime,
            )
            for item in items
        ]
        if upserts:
            self.db.library.upsert_many(upserts)
            self._refresh_timer.start()

    def _on_finished(self, summary: ScanSummary) -> None:
        if not summary.cancelled:
            summary.missing = self.db.library.mark_missing(
                self.paths.library_dir, summary.seen
            )
        self._watcher.sync()

        self._scanner = None

        self.refresh_grid()
        message = summary.describe()
        self._set_status(message)
        if summary.parsed or summary.missing or summary.errors:
            self._toast.show_message(message)
        if summary.total == 0:
            self._set_status(
                "Library is empty — drop .mkv files into the library folder"
            )

        if self._scan_queued:
            self._scan_queued = False
            QTimer.singleShot(300, self.start_scan)

    def _on_failed(self, message: str) -> None:
        log.error("Scan failed: %s", message)
        self._set_status(f"Scan failed: {message}")
        self._scanner = None

    def _on_folder_changed(self) -> None:
        log.info("Library folder changed; re-indexing")
        self.start_scan()

    # -- grid -------------------------------------------------------------

    def refresh_grid(self) -> None:
        search, sort = self.view.current_filters()
        rows = self.db.library.list_for_grid(search, sort)
        all_rows = self.db.library.list_for_grid("", sort)
        cards = [
            CardData(
                media_id=row["id"],
                title=display_title("", Path(row["FilePath"]).stem),
                duration_ms=row["TotalDuration"],
                size_bytes=row["FileSize"],
                progress=float(row["Progress"]),
                completed=bool(row["IsCompleted"]),
                available=bool(row["IsAvailable"]),
                file_path=row["FilePath"],
            )
            for row in all_rows
        ]
        cards_by_id = {card.media_id: card for card in cards}
        active_rows = self.db.playback.continue_watching()
        active_ids = {int(row["id"]) for row in active_rows}
        continue_cards = [
            (cards_by_id[int(row["id"])], False)
            for row in active_rows
            if int(row["id"]) in cards_by_id
        ]
        continue_cards.extend(
            (cards_by_id[int(row["id"])], True)
            for row in next_episode_recommendations(
                all_rows, self.paths.library_dir, active_ids
            )
            if int(row["id"]) in cards_by_id
        )
        self.view.set_library_items(cards, continue_cards)

        total = self.db.library.count()
        if search:
            self._count.setText(f"{len(rows)} of {total} titles")
        else:
            self._count.setText(f"{total} title{'s' if total != 1 else ''}")

    def _set_status(self, text: str) -> None:
        self._status.setText(text)

    # -- card actions -----------------------------------------------------

    def _on_play_requested(self, media_id: int) -> None:
        row = self.db.library.get(media_id)
        if row is None:
            return
        if not Path(row["FilePath"]).is_file():
            self._show_missing_file_prompt(media_id)
            return
        if not row["IsAvailable"]:
            self.start_scan()
        self._current_media_id = int(media_id)
        self._handling_playback_error = False
        self.stack.setCurrentWidget(self.player)
        self.statusBar().setVisible(False)
        self._search_shortcut.setEnabled(False)
        self._refresh_shortcut.setEnabled(False)
        self.setWindowTitle(f"{APP_NAME} — {row['Title']}")
        self.player.controller.set_progress_store(self.db.playback, int(media_id))
        preferences = self.db.prefs.get()
        media_info = parse_mkv(row["FilePath"])
        if media_info.error:
            log.warning(
                "Could not read track metadata for %s: %s",
                row["FilePath"],
                media_info.error,
            )
        self.player.controller.set_track_metadata(
            media_info.audio_tracks,
            media_info.subtitle_tracks,
            preferences.audio_langs,
            preferences.sub_langs,
        )
        self.player.open_media(
            row["Title"], row["FilePath"], int(row["TotalDuration"])
        )

    def _on_player_back(self) -> None:
        self.player.stop_and_release()
        self._current_media_id = None
        self._handling_playback_error = False
        self.stack.setCurrentWidget(self.view)
        self.statusBar().setVisible(True)
        self._search_shortcut.setEnabled(True)
        self._refresh_shortcut.setEnabled(True)
        self.setWindowTitle(APP_NAME)
        self.refresh_grid()
        self.view.focus_library()

    # -- volume -----------------------------------------------------------

    def _on_resume_requested(self, position_ms: int) -> None:
        self._toast.show_message(f"Resumed from {format_ms(position_ms)}")

    def _on_playback_error(self, error, message: str) -> None:
        if self._handling_playback_error:
            return
        self._handling_playback_error = True
        media_id = self._current_media_id
        row = self.db.library.get(media_id) if media_id is not None else None
        if row is not None and not Path(row["FilePath"]).is_file():
            self._show_missing_file_prompt(media_id)
            return

        error_name = getattr(error, "name", str(error))
        log.error(
            "Playback could not start for media %s (%s): %s",
            media_id,
            error_name,
            message,
        )
        detail = (
            "Telovie could not decode this file. It may be damaged, use an "
            "unsupported codec, or require DRM that the player does not support."
        )
        if message:
            detail += f"\n\nPlayer error ({error_name}): {message}"
        QMessageBox.critical(self, "Playback failed", detail)
        self._on_player_back()

    def _show_missing_file_prompt(self, media_id: int) -> None:
        row = self.db.library.get(media_id)
        if row is None:
            self._set_status("This item is no longer in the library.")
            return

        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("File moved or unavailable")
        box.setText(
            f"Could not find “{row['Title']}” at its stored location.\n\n"
            "Reconnect the drive or restore the file, then choose Reload. "
            "Choose Remove to forget this item from the library."
        )
        reload_button = box.addButton("Reload", QMessageBox.ButtonRole.AcceptRole)
        remove_button = box.addButton("Remove", QMessageBox.ButtonRole.DestructiveRole)
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.setDefaultButton(reload_button)
        box.exec()

        if box.clickedButton() is reload_button:
            file_path = Path(row["FilePath"])
            if file_path.is_file():
                self._on_player_back()
                self._on_play_requested(media_id)
            else:
                self._on_player_back()
                self.start_scan(force=True)
                self._toast.show_message(
                    "File is still unavailable. Restore it and refresh the library."
                )
        elif box.clickedButton() is remove_button:
            self._on_player_back()
            self.db.library.remove(media_id)
            self.refresh_grid()
            self._toast.show_message("Removed from library.")

    def _open_preferences(self) -> None:
        dialog = PreferencesDialog(self.db.prefs.get(), self)
        if dialog.exec() != PreferencesDialog.DialogCode.Accepted:
            return
        updated = self.db.prefs.update(**dialog.values())
        self.player.set_volume(updated.volume)
        self.player.controller.update_track_preferences(
            updated.audio_langs, updated.sub_langs
        )
        self._toast.show_message("Preferences saved.")

    def _on_volume_changed(self, value: int) -> None:
        self._pending_volume = int(value)
        self._volume_timer.start()

    def _save_volume(self) -> None:
        try:
            self.db.prefs.update(volume=self._pending_volume)
        except Exception:  # noqa: BLE001 - never lose playback over a pref write
            log.exception("Could not save the volume preference")

    def _on_fullscreen_changed(self, enabled: bool) -> None:
        # the status bar would sit under the video in fullscreen
        self.statusBar().setVisible(not enabled and self.stack.currentWidget() is self.view)

    def _on_start_over(self, media_id: int) -> None:
        self.db.playback.save_position(media_id, 0, completed=False)
        self.refresh_grid()
        self._toast.show_message("Progress cleared.")

    def _on_reveal(self, media_id: int) -> None:
        row = self.db.library.get(media_id)
        if row is None:
            return
        folder = Path(row["FilePath"]).parent
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def _on_remove(self, media_id: int) -> None:
        row = self.db.library.get(media_id)
        if row is None:
            return
        answer = QMessageBox.question(
            self,
            "Remove from library",
            f"Remove “{row['Title']}” from the library?\n\n"
            "The file stays on disk; the next scan will find it again.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.db.library.remove(media_id)
            self.refresh_grid()
            self._toast.show_message("Removed from library.")

    def _open_folder(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.paths.library_dir)))
