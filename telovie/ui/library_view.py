"""Responsive card grid with search, sort, and the empty state."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import (
    QByteArray,
    QEasingCurve,
    QEvent,
    QPoint,
    QPropertyAnimation,
    QRect,
    QSettings,
    QSize,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import QAction, QActionGroup, QCursor, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLayoutItem,
    QLineEdit,
    QMenu,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from telovie.ui.animations import HoverFade
from telovie.ui.media_card import CardData, MediaCard
from telovie.ui.theme import ACCENT

SORT_OPTIONS = (
    ("Title A–Z", "title"),
    ("Recently added", "added"),
    ("Duration", "duration"),
    ("Progress", "progress"),
)


def _folder_icon() -> QIcon:
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="48" height="48"
        viewBox="0 0 48 48">
        <path fill="{ACCENT}" d="M5 11a4 4 0 0 1 4-4h10l4 4h16a4 4 0 0 1 4 4v21a4 4 0 0 1-4 4H9a4 4 0 0 1-4-4z"/>
    </svg>"""
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    pixmap = QPixmap(48, 48)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    return QIcon(pixmap)


class FlowLayout(QLayout):
    """Left-to-right wrapping layout; Qt has no built-in flow layout."""

    def __init__(self, parent: QWidget | None = None, margin: int = 0, spacing: int = 14):
        super().__init__(parent)
        self._items: list[QLayoutItem] = []
        self.setContentsMargins(margin, margin, margin, margin)
        self.setSpacing(spacing)

    def addItem(self, item: QLayoutItem) -> None:  # noqa: N802
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int) -> QLayoutItem | None:  # noqa: N802
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index: int) -> QLayoutItem | None:  # noqa: N802
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self):  # noqa: N802
        return Qt.Orientations()

    def hasHeightForWidth(self) -> bool:  # noqa: N802
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect: QRect) -> None:  # noqa: N802
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self) -> QSize:  # noqa: N802
        return self.minimumSize()

    def minimumSize(self) -> QSize:  # noqa: N802
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        size += QSize(margins.left() + margins.right(), margins.top() + margins.bottom())
        return size

    def _do_layout(self, rect: QRect, test_only: bool) -> int:
        left, top, right, bottom = self.getContentsMargins()
        effective = rect.adjusted(left, top, -right, -bottom)
        x, y = effective.x(), effective.y()
        line_height = 0
        spacing = self.spacing()

        for item in self._items:
            hint = item.sizeHint()
            next_x = x + hint.width() + spacing
            if next_x - spacing > effective.right() and line_height > 0:
                x = effective.x()
                y = y + line_height + spacing
                next_x = x + hint.width() + spacing
                line_height = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x = next_x
            line_height = max(line_height, hint.height())

        return y + line_height - rect.y() + bottom


class FolderCard(QToolButton):
    """Clickable folder tile showing the number of indexed media files inside."""

    opened = Signal(str)

    def __init__(self, path: Path, count: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.path = path
        self.setObjectName("FolderCard")
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self.setIcon(_folder_icon())
        self.setIconSize(QSize(46, 46))
        self.setText(f"{path.name}\n{count} contents")
        self.setFixedSize(236, 132)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName(path.name)
        self.setAccessibleDescription(f"{count} contents")
        self._hover_fade = HoverFade(self)
        self._pending_open = False
        self._click_animation = QPropertyAnimation(self, b"iconSize", self)
        self._click_animation.setDuration(180)
        self._click_animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self._click_animation.setKeyValueAt(0.45, QSize(42, 42))
        self._click_animation.setEndValue(QSize(46, 46))
        self._click_animation.finished.connect(self._finish_open)
        self.clicked.connect(self._animate_open)

    def _animate_open(self) -> None:
        if self._click_animation.state() == QPropertyAnimation.State.Running:
            return
        self._pending_open = True
        self._click_animation.setStartValue(self.iconSize())
        self._click_animation.start()

    def _finish_open(self) -> None:
        if self._pending_open:
            self._pending_open = False
            self.opened.emit(str(self.path))


class LibraryView(QWidget):
    playRequested = Signal(int)
    startOverRequested = Signal(int)
    revealRequested = Signal(int)
    removeRequested = Signal(int)
    deleteRequested = Signal(int)
    openFolderRequested = Signal()
    refreshRequested = Signal()
    preferencesRequested = Signal()
    filtersChanged = Signal(str, str)

    def __init__(self, library_dir: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.library_dir = library_dir
        self.setObjectName("LibraryView")
        self._settings = QSettings("Telovie", "Telovie")
        self._build_ui()

        self._stats_close_timer = QTimer(self)
        self._stats_close_timer.setSingleShot(True)
        self._stats_close_timer.setInterval(180)
        self._stats_close_timer.timeout.connect(self._close_stats_if_pointer_left)

        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(200)
        self._search_timer.timeout.connect(self._emit_filters)

    # -- construction -----------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        top = QWidget(self)
        top.setObjectName("TopBar")
        top_layout = QGridLayout(top)
        top_layout.setContentsMargins(20, 14, 20, 12)
        top_layout.setHorizontalSpacing(10)
        top_layout.setVerticalSpacing(0)
        top_layout.setColumnMinimumWidth(0, 120)
        top_layout.setColumnStretch(0, 1)
        top_layout.setColumnMinimumWidth(2, 120)
        top_layout.setColumnStretch(2, 1)

        title = QLabel("TELOVIE")
        title.setObjectName("AppTitle")
        top_layout.addWidget(title, 0, 0, Qt.AlignmentFlag.AlignLeft)

        search_box = QFrame(top)
        search_box.setObjectName("SearchBox")
        search_layout = QHBoxLayout(search_box)
        search_layout.setContentsMargins(10, 2, 4, 2)
        search_layout.setSpacing(2)
        self.search = QLineEdit(search_box)
        self.search.setObjectName("Search")
        self.search.setPlaceholderText("Search titles…")
        self.search.setClearButtonEnabled(True)
        search_layout.addWidget(self.search, 1)

        self.sort_menu_button = QToolButton(search_box)
        self.sort_menu_button.setObjectName("SortMenu")
        self.sort_menu_button.setText("↕")
        self.sort_menu_button.setToolTip("Sort library")
        self.sort_menu_button.setAccessibleName("Sort library")
        self.sort_menu_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.sort_menu_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        search_layout.addWidget(self.sort_menu_button)

        sort_menu = QMenu(self.sort_menu_button)
        sort_group = QActionGroup(sort_menu)
        sort_group.setExclusive(True)
        self._sort_actions: dict[str, QAction] = {}
        for label, key in SORT_OPTIONS:
            action = sort_menu.addAction(label)
            action.setCheckable(True)
            sort_group.addAction(action)
            self._sort_actions[key] = action
            action.triggered.connect(
                lambda _checked=False, sort_key=key: self._on_sort_selected(sort_key)
            )
        saved = str(self._settings.value("library/sort", "title"))
        if saved not in self._sort_actions:
            saved = "title"
        self._sort_actions[saved].setChecked(True)
        self.sort_menu_button.setMenu(sort_menu)
        self._update_sort_button_label(saved)
        search_box.setMinimumWidth(240)
        search_box.setMaximumWidth(340)
        top_layout.addWidget(search_box, 0, 1, Qt.AlignmentFlag.AlignHCenter)

        # Folder actions live behind this so the bar stays quiet.
        self.overflow = QToolButton()
        self.overflow.setObjectName("Overflow")
        self.overflow.setText("\u22ef")
        self.overflow.setToolTip("More")
        self.overflow.setCursor(Qt.CursorShape.PointingHandCursor)
        self.overflow.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.overflow.setFixedSize(38, 34)
        self._overflow_hover = HoverFade(self.overflow, idle_opacity=0.94)
        menu = QMenu(self.overflow)
        self.open_action = menu.addAction("Open library folder")
        self.refresh_action = menu.addAction("Refresh library\tF5")
        menu.addSeparator()
        self.preferences_action = menu.addAction("Preferences")
        self.overflow.setMenu(menu)
        top_layout.addWidget(self.overflow, 0, 2, Qt.AlignmentFlag.AlignRight)

        root.addWidget(top)

        content = QHBoxLayout()
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(0)
        self.stack = QStackedWidget(self)
        self.stack.setObjectName("LibraryStack")

        self.empty = QWidget(self)
        self.empty.setObjectName("EmptyPane")
        empty_layout = QVBoxLayout(self.empty)
        empty_layout.setContentsMargins(40, 40, 40, 40)
        empty_layout.setSpacing(10)
        empty_layout.addStretch(1)
        self.empty_title = QLabel("Your library is empty")
        self.empty_title.setObjectName("EmptyTitle")
        self.empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(self.empty_title)
        self.empty_hint = QLabel()
        self.empty_hint.setObjectName("EmptyHint")
        self.empty_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_hint.setWordWrap(True)
        self.empty_hint.setMaximumWidth(520)
        self.empty_hint.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        empty_layout.addWidget(self.empty_hint)
        empty_row = QHBoxLayout()
        empty_row.addStretch(1)
        self.empty_open = QPushButton("Open library folder")
        self.empty_open.setObjectName("Primary")
        self._empty_open_hover = HoverFade(self.empty_open, idle_opacity=0.94)
        empty_row.addWidget(self.empty_open)
        empty_row.addStretch(1)
        empty_layout.addLayout(empty_row)
        empty_layout.addStretch(1)
        self._update_empty_state(searching=False)

        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.viewport().setAutoFillBackground(False)

        self.container = QWidget()
        self.container.setObjectName("GridCanvas")
        self.container.setAutoFillBackground(False)
        self.container_layout = QVBoxLayout(self.container)
        self.container_layout.setContentsMargins(20, 18, 20, 20)
        self.container_layout.setSpacing(22)

        self.home_page = QWidget(self.container)
        home_layout = QVBoxLayout(self.home_page)
        home_layout.setContentsMargins(0, 0, 0, 0)
        home_layout.setSpacing(22)
        self.continue_title = QLabel("Continue Watching")
        self.continue_title.setObjectName("SectionTitle")
        home_layout.addWidget(self.continue_title)
        self.continue_flow = FlowLayout(margin=0, spacing=14)
        home_layout.addLayout(self.continue_flow)
        self.continue_empty = QLabel("Nothing to continue right now")
        self.continue_empty.setObjectName("SectionHint")
        home_layout.addWidget(self.continue_empty)
        self.collection_title = QLabel("Collection")
        self.collection_title.setObjectName("SectionTitle")
        home_layout.addWidget(self.collection_title)
        self.collection_flow = FlowLayout(margin=0, spacing=14)
        home_layout.addLayout(self.collection_flow)
        self.collection_empty = QLabel("No folders in your collection yet")
        self.collection_empty.setObjectName("SectionHint")
        home_layout.addWidget(self.collection_empty)
        self.container_layout.addWidget(self.home_page)

        self.browse_page = QWidget(self.container)
        browse_layout = QVBoxLayout(self.browse_page)
        browse_layout.setContentsMargins(0, 0, 0, 0)
        browse_layout.setSpacing(14)
        nav = QHBoxLayout()
        self.back_button = QPushButton("← Back")
        self.back_button.setObjectName("FolderBack")
        self.home_button = QPushButton("Home")
        self.home_button.setObjectName("FolderBack")
        self._back_hover = HoverFade(self.back_button, idle_opacity=0.94)
        self._home_hover = HoverFade(self.home_button, idle_opacity=0.94)
        self.breadcrumb = QLabel("Collection")
        self.breadcrumb.setObjectName("Breadcrumb")
        nav.addWidget(self.back_button)
        nav.addWidget(self.home_button)
        nav.addWidget(self.breadcrumb, 1)
        browse_layout.addLayout(nav)
        self.folder_flow = FlowLayout(margin=0, spacing=14)
        browse_layout.addLayout(self.folder_flow)
        self.container_layout.addWidget(self.browse_page)
        self.container_layout.addStretch(1)

        self._all_cards: list[CardData] = []
        self._continue_cards: list[tuple[CardData, bool]] = []
        self._current_folder: Path | None = None
        self.scroll.setWidget(self.container)

        self.stack.addWidget(self.empty)
        self.stack.addWidget(self.scroll)

        self.stats_sidebar = QWidget(self)
        self.stats_sidebar.setObjectName("StatsSidebar")
        self.stats_sidebar.setFixedWidth(190)
        stats_layout = QVBoxLayout(self.stats_sidebar)
        stats_layout.setContentsMargins(14, 24, 14, 24)
        stats_layout.setSpacing(16)
        stats_title = QLabel("WATCH TIME")
        stats_title.setObjectName("StatsTitle")
        stats_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        stats_layout.addWidget(stats_title)
        watch_ring = QFrame(self.stats_sidebar)
        watch_ring.setObjectName("WatchRing")
        watch_ring.setFixedSize(132, 132)
        ring_layout = QVBoxLayout(watch_ring)
        ring_layout.setContentsMargins(10, 10, 10, 10)
        self.watch_stat = QLabel("0 hours watched", watch_ring)
        self.watch_stat.setObjectName("WatchStat")
        self.watch_stat.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.watch_stat.setWordWrap(True)
        self.watch_stat.setToolTip(
            "Completed media duration plus time spent watching in Telovie"
        )
        ring_layout.addWidget(self.watch_stat)
        stats_layout.addWidget(watch_ring, 0, Qt.AlignmentFlag.AlignHCenter)
        stats_layout.addStretch(1)

        content.addWidget(self.stack, 1)
        root.addLayout(content, 1)

        self.stats_edge = QWidget(self)
        self.stats_edge.setObjectName("StatsEdge")
        self.stats_edge.setToolTip("Hover to show watch time")
        self.stats_edge.setCursor(Qt.CursorShape.PointingHandCursor)
        self.stats_edge.installEventFilter(self)
        self.stats_sidebar.installEventFilter(self)
        self.stats_sidebar.hide()
        self._position_stats_sidebar()
        self.stats_edge.raise_()

        # signals
        self.search.textChanged.connect(self._on_search_changed)
        self.search.returnPressed.connect(self._emit_filters)
        self.open_action.triggered.connect(self.openFolderRequested)
        self.refresh_action.triggered.connect(self.refreshRequested)
        self.preferences_action.triggered.connect(self.preferencesRequested)
        self.empty_open.clicked.connect(self.openFolderRequested)
        self.back_button.clicked.connect(self._go_back)
        self.home_button.clicked.connect(self._go_home)

    # -- data -------------------------------------------------------------

    def current_filters(self) -> tuple[str, str]:
        checked = next(
            key for key, action in self._sort_actions.items() if action.isChecked()
        )
        return self.search.text().strip(), checked

    def set_watched_time(self, total_ms: int) -> None:
        hours = max(0, int(total_ms)) // 3_600_000
        self.watch_stat.setText(
            f"{hours:,} {'hour' if hours == 1 else 'hours'} watched"
        )

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._position_stats_sidebar()

    def eventFilter(self, watched, event) -> bool:  # noqa: N802
        if watched in (self.stats_edge, self.stats_sidebar):
            if event.type() == QEvent.Type.Enter:
                self._stats_close_timer.stop()
                if watched is self.stats_edge:
                    self._position_stats_sidebar()
                    self.stats_sidebar.show()
                    self.stats_sidebar.raise_()
                    self.stats_edge.raise_()
            elif event.type() == QEvent.Type.Leave:
                self._stats_close_timer.start()
        return super().eventFilter(watched, event)

    def _position_stats_sidebar(self) -> None:
        if not hasattr(self, "stats_sidebar") or not hasattr(self, "stats_edge"):
            return
        top = self.findChild(QWidget, "TopBar")
        top_height = top.height() if top is not None else 0
        self.stats_sidebar.setGeometry(
            max(0, self.width() - self.stats_sidebar.width()),
            top_height,
            self.stats_sidebar.width(),
            max(0, self.height() - top_height),
        )
        self.stats_edge.setGeometry(
            max(0, self.width() - 6),
            top_height,
            min(6, self.width()),
            max(0, self.height() - top_height),
        )

    def _close_stats_if_pointer_left(self) -> None:
        pointer = QCursor.pos()
        for widget in (self.stats_edge, self.stats_sidebar):
            if widget.isVisible() and widget.rect().contains(widget.mapFromGlobal(pointer)):
                return
        self.stats_sidebar.hide()
        self.stats_edge.raise_()

    def set_library_items(
        self,
        cards: list[CardData],
        continue_cards: list[tuple[CardData, bool]],
    ) -> None:
        self._all_cards = cards
        self._continue_cards = continue_cards
        if self._current_folder is not None:
            try:
                self._current_folder.relative_to(self.library_dir)
            except ValueError:
                self._current_folder = None
        self._render_content()

    def set_items(self, cards: list[CardData]) -> None:
        """Compatibility wrapper for callers that only have a flat card list."""
        self.set_library_items(cards, [])

    def set_thumbnail(self, file_path: str, thumbnail_path: str) -> None:
        self._all_cards = [
            replace(card, thumbnail_path=thumbnail_path)
            if card.file_path == file_path
            else card
            for card in self._all_cards
        ]
        self._continue_cards = [
            (
                replace(card, thumbnail_path=thumbnail_path)
                if card.file_path == file_path
                else card,
                recommended,
            )
            for card, recommended in self._continue_cards
        ]
        for flow in (self.continue_flow, self.collection_flow, self.folder_flow):
            for index in range(flow.count()):
                widget = flow.itemAt(index).widget()
                if isinstance(widget, MediaCard) and widget.data.file_path == file_path:
                    widget.set_thumbnail(thumbnail_path)

    def _clear_flow(self, flow: FlowLayout) -> None:
        while flow.count():
            item = flow.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget is not None:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()

    def _filtered_cards(self) -> list[CardData]:
        query = self.search.text().strip().casefold()
        return [
            card
            for card in self._all_cards
            if not query
            or query in card.title.casefold()
            or query in card.file_path.casefold()
        ]

    def _add_media_card(self, flow: FlowLayout, card_data: CardData) -> None:
        card = MediaCard(card_data, self.container)
        card.playRequested.connect(self.playRequested)
        card.startOverRequested.connect(self.startOverRequested)
        card.revealRequested.connect(self.revealRequested)
        card.removeRequested.connect(self.removeRequested)
        card.deleteRequested.connect(self.deleteRequested)
        flow.addWidget(card)

    def _render_content(self) -> None:
        self._clear_flow(self.continue_flow)
        self._clear_flow(self.collection_flow)
        self._clear_flow(self.folder_flow)
        if not self._all_cards:
            self._update_empty_state(searching=False)
            self.stack.setCurrentWidget(self.empty)
            return

        filtered = self._filtered_cards()
        if self.search.text().strip() and not filtered:
            self._update_empty_state(searching=True)
            self.stack.setCurrentWidget(self.empty)
            return

        if self._current_folder is None:
            self.stack.setCurrentWidget(self.scroll)
            self.home_page.show()
            self.browse_page.hide()
            visible_paths = {card.file_path for card in filtered}
            for card_data, recommended in self._continue_cards:
                if card_data.file_path not in visible_paths:
                    continue
                if recommended:
                    card_data = replace(card_data, recommended=True)
                self._add_media_card(self.continue_flow, card_data)

            folders = self._child_folders(self.library_dir)
            query = self.search.text().strip().casefold()
            for folder, count in folders:
                descendants = [
                    card for card in filtered if self._is_descendant(card.file_path, folder)
                ]
                if query and query not in folder.name.casefold() and not descendants:
                    continue
                self._add_folder_card(self.collection_flow, folder, count)
            root_files = [
                card
                for card in filtered
                if Path(card.file_path).parent == self.library_dir
            ]
            for card_data in root_files:
                self._add_media_card(self.collection_flow, card_data)
            self.continue_title.setVisible(True)
            self.continue_empty.setVisible(self.continue_flow.count() == 0)
            self.collection_title.setVisible(True)
            self.collection_empty.setVisible(self.collection_flow.count() == 0)
            return

        self.stack.setCurrentWidget(self.scroll)
        self.home_page.hide()
        self.browse_page.show()
        self.breadcrumb.setText(
            "Collection / " + self._current_folder.relative_to(self.library_dir).as_posix()
        )
        self.back_button.setVisible(self._current_folder != self.library_dir)
        self.folder_flow.setEnabled(True)
        for folder, count in self._child_folders(self._current_folder):
            descendants = [
                card for card in filtered if self._is_descendant(card.file_path, folder)
            ]
            query = self.search.text().strip().casefold()
            if query and query not in folder.name.casefold() and not descendants:
                continue
            self._add_folder_card(self.folder_flow, folder, count)
        for card_data in filtered:
            if Path(card_data.file_path).parent == self._current_folder:
                self._add_media_card(self.folder_flow, card_data)

    def _child_folders(self, parent: Path) -> list[tuple[Path, int]]:
        counts: dict[Path, int] = {}
        for card in self._all_cards:
            path = Path(card.file_path)
            try:
                relative = path.relative_to(parent)
            except ValueError:
                continue
            if len(relative.parts) > 1:
                child = parent / relative.parts[0]
                counts[child] = counts.get(child, 0) + 1
        return sorted(counts.items(), key=lambda item: item[0].name.casefold())

    @staticmethod
    def _is_descendant(file_path: str, folder: Path) -> bool:
        try:
            Path(file_path).relative_to(folder)
            return True
        except ValueError:
            return False

    def _add_folder_card(self, flow: FlowLayout, folder: Path, count: int) -> None:
        card = FolderCard(folder, count, self.container)
        card.opened.connect(self._open_folder_path)
        flow.addWidget(card)

    def _open_folder_path(self, folder_path: str) -> None:
        self._current_folder = Path(folder_path)
        self._render_content()

    def _go_back(self) -> None:
        if self._current_folder is None:
            return
        if self._current_folder == self.library_dir:
            self._go_home()
        else:
            self._current_folder = self._current_folder.parent
            self._render_content()

    def _go_home(self) -> None:
        self._current_folder = None
        self._render_content()

    def focus_search(self) -> None:
        self.search.setFocus()
        self.search.selectAll()

    def focus_library(self) -> None:
        """Land on the first card, or the search box when the grid is empty."""
        item = self.continue_flow.itemAt(0)
        widget = item.widget() if item is not None else None
        if widget is not None:
            widget.setFocus()
        else:
            self.search.setFocus()

    # -- internals --------------------------------------------------------

    def _update_empty_state(self, *, searching: bool) -> None:
        if searching:
            self.empty_title.setText("No matches")
            self.empty_hint.setText(
                f"Nothing matches “{self.search.text().strip()}”. Try a shorter search."
            )
            self.empty_open.setVisible(False)
        else:
            self.empty_title.setText("Your library is empty")
            self.empty_hint.setText(
                "Drop MKV, MP4, MOV, or WebM files into your library folder, or extract a show "
                "folder into it. Subfolders are fine — everything underneath "
                "is indexed automatically."
            )
            self.empty_open.setVisible(True)

    def _on_search_changed(self, _text: str) -> None:
        self._search_timer.start()

    def _on_sort_selected(self, key: str) -> None:
        self._settings.setValue("library/sort", key)
        self._update_sort_button_label(key)
        self._emit_filters()

    def _update_sort_button_label(self, key: str) -> None:
        label = next(label for label, option_key in SORT_OPTIONS if option_key == key)
        self.sort_menu_button.setToolTip(f"Sort by {label}")

    def _emit_filters(self) -> None:
        self._search_timer.stop()
        self.filtersChanged.emit(*self.current_filters())
