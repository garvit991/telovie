from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel, QToolButton  # noqa: E402

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
