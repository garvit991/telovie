"""Responsive card grid with search, sort, and the empty state."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QPoint, QRect, QSettings, QSize, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLayoutItem,
    QLineEdit,
    QMenu,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QStyle,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from telovie.ui.media_card import CardData, MediaCard
from telovie.ui.theme import BG

SORT_OPTIONS = (
    ("Title A–Z", "title"),
    ("Recently added", "added"),
    ("Duration", "duration"),
    ("Progress", "progress"),
)


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
        self.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon))
        self.setIconSize(QSize(46, 46))
        self.setText(f"{path.name}\n{count} contents")
        self.setFixedSize(236, 132)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName(path.name)
        self.setAccessibleDescription(f"{count} contents")
        self.clicked.connect(lambda: self.opened.emit(str(path)))


class LibraryView(QWidget):
    playRequested = Signal(int)
    startOverRequested = Signal(int)
    revealRequested = Signal(int)
    removeRequested = Signal(int)
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
        top_layout = QHBoxLayout(top)
        top_layout.setContentsMargins(20, 14, 20, 12)
        top_layout.setSpacing(10)

        title = QLabel("TELOVIE")
        title.setObjectName("AppTitle")
        top_layout.addWidget(title)
        top_layout.addStretch(1)

        self.search = QLineEdit()
        self.search.setObjectName("Search")
        self.search.setPlaceholderText("Search titles…")
        self.search.setClearButtonEnabled(True)
        self.search.setMinimumWidth(240)
        self.search.setMaximumWidth(340)
        top_layout.addWidget(self.search)

        self.sort = QComboBox()
        for label, key in SORT_OPTIONS:
            self.sort.addItem(label, key)
        saved = str(self._settings.value("library/sort", "title"))
        index = self.sort.findData(saved)
        if index >= 0:
            self.sort.setCurrentIndex(index)
        top_layout.addWidget(self.sort)

        # Folder actions live behind this so the bar stays quiet.
        self.overflow = QToolButton()
        self.overflow.setObjectName("Overflow")
        self.overflow.setText("\u22ef")
        self.overflow.setToolTip("More")
        self.overflow.setCursor(Qt.CursorShape.PointingHandCursor)
        self.overflow.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.overflow.setFixedSize(38, 34)
        menu = QMenu(self.overflow)
        self.open_action = menu.addAction("Open library folder")
        self.refresh_action = menu.addAction("Refresh library\tF5")
        menu.addSeparator()
        self.preferences_action = menu.addAction("Preferences")
        self.overflow.setMenu(menu)
        top_layout.addWidget(self.overflow)

        root.addWidget(top)

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
        self.scroll.viewport().setStyleSheet(f"background: {BG};")

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
        root.addWidget(self.stack, 1)

        # signals
        self.search.textChanged.connect(self._on_search_changed)
        self.search.returnPressed.connect(self._emit_filters)
        self.sort.currentIndexChanged.connect(self._on_sort_changed)
        self.open_action.triggered.connect(self.openFolderRequested)
        self.refresh_action.triggered.connect(self.refreshRequested)
        self.preferences_action.triggered.connect(self.preferencesRequested)
        self.empty_open.clicked.connect(self.openFolderRequested)
        self.back_button.clicked.connect(self._go_back)
        self.home_button.clicked.connect(self._go_home)

    # -- data -------------------------------------------------------------

    def current_filters(self) -> tuple[str, str]:
        return self.search.text().strip(), str(self.sort.currentData())

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
                "Drop .mkv files into your library folder, or extract a show "
                "folder into it. Subfolders are fine — everything underneath "
                "is indexed automatically."
            )
            self.empty_open.setVisible(True)

    def _on_search_changed(self, _text: str) -> None:
        self._search_timer.start()

    def _on_sort_changed(self, _index: int) -> None:
        self._settings.setValue("library/sort", str(self.sort.currentData()))
        self._emit_filters()

    def _emit_filters(self) -> None:
        self._search_timer.stop()
        self.filtersChanged.emit(*self.current_filters())
