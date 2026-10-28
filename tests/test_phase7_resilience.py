from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtMultimedia import QMediaPlayer  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from telovie.config import AppPaths  # noqa: E402
from telovie.db import Database, MediaUpsert  # noqa: E402
from telovie.library.models import ScanSummary  # noqa: E402
from telovie.playback.controller import PlayerController  # noqa: E402
from telovie.ui.main_window import MainWindow  # noqa: E402
from telovie.ui.player_view import PlayerView  # noqa: E402


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _window(tmp_path: Path) -> tuple[MainWindow, Database]:
    _app()
    paths = AppPaths(
        data_dir=tmp_path / "data",
        db_path=tmp_path / "data" / "library.db",
        log_dir=tmp_path / "data" / "logs",
        library_dir=tmp_path / "library",
    )
    paths.ensure()
    database = Database(paths.db_path)
    return MainWindow(paths, database), database


def test_controller_surfaces_media_error_type_and_message():
    _app()
    controller = PlayerController()
    errors: list[tuple[object, str]] = []
    controller.errorOccurred.connect(lambda error, message: errors.append((error, message)))

    controller._on_error(QMediaPlayer.Error.FormatError, "bad media")

    assert errors == [(QMediaPlayer.Error.FormatError, "bad media")]
    controller.close()


def test_player_disables_playback_controls_after_media_error():
    _app()
    controller = PlayerController()
    view = PlayerView(controller)
    view.play_button.setEnabled(True)
    view.seek.setEnabled(True)
    view.audio_button.setEnabled(True)
    view.subtitle_button.setEnabled(True)

    view._on_error(QMediaPlayer.Error.FormatError, "unsupported stream")

    assert view.error_label.text().startswith("Playback failed")
    assert not view.play_button.isEnabled()
    assert not view.seek.isEnabled()
    assert not view.audio_button.isEnabled()
    assert not view.subtitle_button.isEnabled()
    view.close()
    controller.close()


def test_missing_playback_file_offers_recovery(tmp_path: Path, monkeypatch):
    window, database = _window(tmp_path)
    try:
        missing_path = tmp_path / "library" / "gone.mkv"
        database.library.upsert_many([MediaUpsert("Gone", str(missing_path))])
        media_id = int(database.library.find_by_path(str(missing_path))["id"])
        prompted: list[int] = []
        monkeypatch.setattr(
            window, "_show_missing_file_prompt", lambda value: prompted.append(value)
        )

        window._on_play_requested(media_id)

        assert prompted == [media_id]
        assert window._current_media_id is None
    finally:
        window.close()
        database.close()


def test_unreadable_scan_summary_is_toasted(tmp_path: Path):
    window, database = _window(tmp_path)
    try:
        missing_path = window.paths.library_dir / "gone.mkv"
        database.library.upsert_many([MediaUpsert("Gone", str(missing_path))])
        window._on_finished(ScanSummary(total=1, missing=1, errors=1))

        assert "missing" in window._toast.text()
        assert "unreadable" in window._toast.text()
    finally:
        window.close()
        database.close()


def test_decode_error_is_reported_and_returns_to_library(tmp_path: Path, monkeypatch):
    window, database = _window(tmp_path)
    try:
        dialogs: list[tuple[str, str]] = []
        returned: list[bool] = []
        monkeypatch.setattr(
            QMessageBox,
            "critical",
            lambda _parent, title, text: dialogs.append((title, text)),
        )
        monkeypatch.setattr(window, "_on_player_back", lambda: returned.append(True))

        window._on_playback_error(QMediaPlayer.Error.FormatError, "invalid stream")

        assert len(dialogs) == 1
        assert "damaged" in dialogs[0][1]
        assert "DRM" in dialogs[0][1]
        assert returned == [True]
    finally:
        window.close()
        database.close()
