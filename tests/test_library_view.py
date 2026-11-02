from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtGui import QImage  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel, QToolButton  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QGraphicsOpacityEffect,
    QLabel,
    QToolButton,
)

from telovie.ui.library_view import LibraryView  # noqa: E402
from telovie.ui.media_card import CardData, MediaCard  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def view(qapp, tmp_path: Path) -> LibraryView:
    widget = LibraryView(tmp_path)
    yield widget
    widget.deleteLater()


def test_top_bar_shows_no_folder_path(view: LibraryView):
    assert view.findChild(QLabel, "LibraryPath") is None
    assert not hasattr(view, "path_label")


def test_empty_state_names_no_absolute_path(view: LibraryView, tmp_path: Path):
    text = view.empty_hint.text()
    assert str(tmp_path) not in text
    assert "library folder" in text.lower()


def test_folder_actions_live_behind_the_overflow_menu(view: LibraryView):
    menu = view.overflow.menu()
    assert menu is not None
    assert [action.text() for action in menu.actions()] == [
        "Open library folder",
        "Refresh library\tF5",
        "",
        "Preferences",
    ]


def test_overflow_actions_emit_the_view_signals(view: LibraryView):
    opened: list[str] = []
    refreshed: list[str] = []
    preferences: list[str] = []
    view.openFolderRequested.connect(lambda: opened.append("open"))
    view.refreshRequested.connect(lambda: refreshed.append("refresh"))
    view.preferencesRequested.connect(lambda: preferences.append("preferences"))

    view.open_action.trigger()
    view.refresh_action.trigger()
    view.preferences_action.trigger()

    assert opened == ["open"]
    assert refreshed == ["refresh"]
    assert preferences == ["preferences"]


def test_homepage_sections_and_nested_collection_navigation(view: LibraryView, tmp_path: Path):
    episode = tmp_path / "Example Show" / "Season 1" / "S01E01.mkv"
    next_episode = tmp_path / "Example Show" / "Season 1" / "S01E02.mkv"
    cards = [
        CardData(1, "Episode 1", 1_000_000, 10, 0.4, False, True, str(episode)),
        CardData(2, "Episode 2", 1_000_000, 10, 0.0, False, True, str(next_episode)),
    ]

    view.set_library_items(cards, [(cards[0], True)])

    assert view.findChild(QLabel, "AppTitle").text() == "TELOVIE"
    assert view.continue_title.text() == "Continue Watching"
    assert view.collection_title.text() == "Collection"
    continue_card = view.continue_flow.itemAt(0).widget()
    assert isinstance(continue_card, MediaCard)
    assert continue_card.data.recommended
    show_folder = view.container.findChild(QToolButton, "FolderCard")
    assert show_folder is not None
    assert show_folder.text() == "Example Show\n2 contents"

    show_folder.click()
    season_folder = view.container.findChild(QToolButton, "FolderCard")
    assert season_folder is not None
    assert season_folder.text() == "Season 1\n2 contents"

    season_folder.click()
    assert view.folder_flow.count() == 2


def test_thumbnail_updates_visible_card_and_is_kept_for_rerender(
    view: LibraryView, tmp_path: Path
):
    media_path = tmp_path / "episode.mkv"
    card_data = CardData(1, "Episode", 1_000_000, 10, 0, False, True, str(media_path))
    view.set_items([card_data])
    thumbnail_path = tmp_path / "thumbnail.jpg"
    thumbnail = QImage(8, 8, QImage.Format.Format_RGB32)
    thumbnail.fill(0xFF336699)
    assert thumbnail.save(str(thumbnail_path), "JPEG")

    view.set_thumbnail(str(media_path), str(thumbnail_path))

    card = view.collection_flow.itemAt(0).widget()
    assert isinstance(card, MediaCard)
    assert card.data.thumbnail_path == str(thumbnail_path)
    assert not card._thumbnail.isNull()

    view.set_items(view._all_cards)
    rerendered = view.collection_flow.itemAt(0).widget()
    assert isinstance(rerendered, MediaCard)
    assert not rerendered._thumbnail.isNull()


def test_folder_navigation_has_a_hover_transition(view: LibraryView, tmp_path: Path):
    episode = tmp_path / "Example Show" / "Season 1" / "S01E01.mkv"
    card = CardData(1, "Episode 1", 1_000_000, 10, 0, False, True, str(episode))
    view.set_library_items([card], [])

    folder_card = view.container.findChild(QToolButton, "FolderCard")
    assert folder_card is not None
    assert isinstance(folder_card.graphicsEffect(), QGraphicsOpacityEffect)


def test_media_card_exposes_animated_hover_progress(qapp):
    card = MediaCard(CardData(1, "Episode", 1_000_000, 10, 0, False, True, ""))

    assert card.metaObject().indexOfProperty("hoverProgress") >= 0
    card.setProperty("hoverProgress", 0.5)
    assert card.property("hoverProgress") == 0.5

    card.deleteLater()
