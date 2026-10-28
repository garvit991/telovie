"""Preferences for preferred audio and subtitle languages."""

from __future__ import annotations

import re

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from telovie.db.repository import Preferences
from telovie.util.languages import display_name, language_choices, normalize_code


class LanguageListEditor(QWidget):
    def __init__(self, codes: list[str], parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.languages = QListWidget(self)
        self.languages.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        for code in codes:
            self._add_code(code)
        layout.addWidget(self.languages)

        row = QHBoxLayout()
        self.language_combo = QComboBox(self)
        self.language_combo.setEditable(True)
        self.language_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.language_combo.setPlaceholderText("Search languages…")
        for code, name in language_choices():
            self.language_combo.addItem(f"{name} ({code})", code)
        self.language_combo.completer().setCaseSensitivity(
            Qt.CaseSensitivity.CaseInsensitive
        )
        row.addWidget(self.language_combo, 1)

        self.add_button = QPushButton("Add", self)
        self.add_button.clicked.connect(self._add_selected)
        row.addWidget(self.add_button)
        layout.addLayout(row)

        controls = QHBoxLayout()
        self.up_button = QPushButton("Move up", self)
        self.down_button = QPushButton("Move down", self)
        self.remove_button = QPushButton("Remove", self)
        self.up_button.clicked.connect(lambda: self._move(-1))
        self.down_button.clicked.connect(lambda: self._move(1))
        self.remove_button.clicked.connect(self._remove_selected)
        controls.addWidget(self.up_button)
        controls.addWidget(self.down_button)
        controls.addStretch(1)
        controls.addWidget(self.remove_button)
        layout.addLayout(controls)

    def codes(self) -> list[str]:
        return [
            str(self.languages.item(index).data(Qt.ItemDataRole.UserRole))
            for index in range(self.languages.count())
        ]

    def _add_code(self, code: str) -> None:
        normalized = normalize_code(code)
        if not normalized or normalized == "und" or normalized in self.codes():
            return
        item = QListWidgetItem(
            f"{display_name(normalized)} ({normalized})", self.languages
        )
        item.setData(Qt.ItemDataRole.UserRole, normalized)

    def _add_selected(self) -> None:
        text = self.language_combo.currentText().strip()
        match = re.search(r"\(([A-Za-z-]+)\)\s*$", text)
        code = match.group(1) if match else text
        known = {value for value, _name in language_choices()}
        normalized = normalize_code(code)
        if normalized not in known:
            QMessageBox.warning(
                self, "Unknown language", "Choose a language from the suggestions."
            )
            return
        if normalized in self.codes():
            return
        self._add_code(normalized)
        self.language_combo.setEditText("")

    def _move(self, offset: int) -> None:
        row = self.languages.currentRow()
        target = row + offset
        if row < 0 or not 0 <= target < self.languages.count():
            return
        item = self.languages.takeItem(row)
        self.languages.insertItem(target, item)
        self.languages.setCurrentRow(target)

    def _remove_selected(self) -> None:
        row = self.languages.currentRow()
        if row >= 0:
            self.languages.takeItem(row)


class PreferencesDialog(QDialog):
    def __init__(self, preferences: Preferences, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Telovie preferences")
        self.setModal(True)
        self.resize(560, 560)

        layout = QVBoxLayout(self)
        hint = QLabel(
            "Preferred languages are tried in order when a file has no saved "
            "track choice.", self
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        groups = QHBoxLayout()
        self.audio_editor = LanguageListEditor(
            preferences.audio_langs, self
        )
        self.subtitle_editor = LanguageListEditor(
            preferences.sub_langs, self
        )
        audio_group = QGroupBox("Audio language order", self)
        audio_layout = QVBoxLayout(audio_group)
        audio_layout.addWidget(self.audio_editor)
        subtitle_group = QGroupBox("Caption language order", self)
        subtitle_layout = QVBoxLayout(subtitle_group)
        subtitle_layout.addWidget(self.subtitle_editor)
        groups.addWidget(audio_group)
        groups.addWidget(subtitle_group)
        layout.addLayout(groups, 1)

        form = QFormLayout()
        self.volume_slider = QSlider(Qt.Orientation.Horizontal, self)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(preferences.volume)
        self.volume_slider.setAccessibleName("Default volume")
        form.addRow("Default volume", self.volume_slider)
        layout.addLayout(form)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

    def values(self) -> dict[str, object]:
        return {
            "default_audio_langs": self.audio_editor.codes(),
            "default_sub_langs": self.subtitle_editor.codes(),
            "volume": self.volume_slider.value(),
        }
