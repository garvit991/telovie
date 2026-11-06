from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtCore import QEvent  # noqa: E402
from PySide6.QtGui import QImage  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QFrame,
    QGraphicsOpacityEffect,
    QLabel,
    QToolButton,
    QWidget,
)

from telovie.ui.library_view import LibraryView  # noqa: E402
from telovie.ui.theme import ACCENT  # noqa: E402
from telovie.ui.media_card import (
    CardData,
    MediaCard,
    _wrapped_title_lines,
)  # noqa: E402


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
    view.set_watched_time(142 * 3_600_000)
    assert view.watch_stat.text() == "142 hours watched"
    assert view.stats_sidebar.isAncestorOf(view.watch_stat)


def test_sort_filters_are_embedded_in_search_menu(view: LibraryView):
    menu = view.sort_menu_button.menu()
    assert menu is not None
    assert [action.text() for action in menu.actions()] == [
        "Title A–Z",
        "Recently added",
        "Duration",
        "Progress",
    ]

    changed: list[tuple[str, str]] = []
    view.filtersChanged.connect(lambda search, sort: changed.append((search, sort)))
    view._sort_actions["duration"].trigger()

    assert view.current_filters() == ("", "duration")
    assert changed == [("", "duration")]


def test_search_field_is_centered_in_top_bar(view: LibraryView, qapp):
    view.resize(1200, 700)
    view.show()
    qapp.processEvents()
    top_bar = view.findChild(QWidget, "TopBar")
    search_box = view.findChild(QFrame, "SearchBox")
    assert top_bar is not None
    assert search_box is not None
    assert abs(search_box.geometry().center().x() - top_bar.width() // 2) <= 1


def test_stats_sidebar_opens_at_right_edge_and_closes_when_pointer_leaves(
    view: LibraryView, qapp
):
    view.resize(1200, 700)
    view.show()
    qapp.processEvents()
    assert view.stats_sidebar.isHidden()

    QTest.mouseMove(view, view.rect().center())
    qapp.sendEvent(view.stats_edge, QEvent(QEvent.Type.Enter))
    assert view.stats_sidebar.isVisible()

    QTest.mouseMove(view.stats_sidebar, view.stats_sidebar.rect().center())
    QTest.qWait(240)
    assert view.stats_sidebar.isVisible()

    QTest.mouseMove(view, view.rect().center())
    qapp.sendEvent(view.stats_sidebar, QEvent(QEvent.Type.Leave))
    QTest.qWait(240)
    assert view.stats_sidebar.isHidden()


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
    QTest.qWait(220)
    season_folder = view.container.findChild(QToolButton, "FolderCard")
    assert season_folder is not None
    assert season_folder.text() == "Season 1\n2 contents"

    season_folder.click()
    QTest.qWait(220)
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
    icon = folder_card.icon().pixmap(48, 48).toImage()
    assert icon.pixelColor(24, 24).name().lower() == ACCENT


def test_media_titles_wrap_to_two_lines_and_elide_the_remainder(qapp):
    from PySide6.QtGui import QFont, QFontMetrics

    metrics = QFontMetrics(QFont("Segoe UI Variable Text", 10))
    lines = _wrapped_title_lines(
        "A Very Long Episode Title With More Words Than Can Fit", metrics, 110
    )

    assert len(lines) == 2
    assert lines[-1].endswith("…")
    assert all(metrics.horizontalAdvance(line) <= 110 for line in lines)
    long_word = _wrapped_title_lines("A" * 100, metrics, 110)
    assert metrics.horizontalAdvance(long_word[0]) <= 110


def test_media_card_exposes_animated_hover_progress(qapp):
    card = MediaCard(CardData(1, "Episode", 1_000_000, 10, 0, False, True, ""))

    assert card.metaObject().indexOfProperty("hoverProgress") >= 0
    card.setProperty("hoverProgress", 0.5)
    assert card.property("hoverProgress") == 0.5

    card.deleteLater()


def test_media_card_waits_for_click_animation_before_play(qapp):
    card = MediaCard(CardData(9, "Episode", 1_000_000, 10, 0, False, True, ""))
    played: list[int] = []
    card.playRequested.connect(played.append)

    card._activate()
    assert played == []
    QTest.qWait(220)
    assert played == [9]

    card.deleteLater()


def test_media_card_paints_placeholder_before_thumbnail_arrives(qapp):
    card = MediaCard(CardData(1, "Episode", 1_000_000, 10, 0, False, True, ""))
    image = QImage(card.size(), QImage.Format.Format_ARGB32)
    image.fill(0)

    card.render(image)

    assert image.pixelColor(10, 10).alpha() > 0
    card.deleteLater()
