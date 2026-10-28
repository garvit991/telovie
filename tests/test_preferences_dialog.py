from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from telovie.ui.preferences_dialog import LanguageListEditor


def test_language_editor_adds_valid_codes_and_reorders():
    app = QApplication.instance() or QApplication([])
    editor = LanguageListEditor(["eng", "hin"])
    editor.language_combo.setEditText("French (fre)")
    editor._add_selected()
    assert editor.codes() == ["eng", "hin", "fre"]

    editor.languages.setCurrentRow(2)
    editor._move(-1)
    assert editor.codes() == ["eng", "fre", "hin"]
    editor._remove_selected()
    assert editor.codes() == ["eng", "hin"]
    editor.close()
