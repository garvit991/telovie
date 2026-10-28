"""Visual tokens and the application stylesheet."""

from __future__ import annotations

from PySide6.QtGui import QColor

BG = "#0f1115"
SURFACE = "#12151b"
SURFACE_ALT = "#1b1f27"
BORDER = "#2a2f3a"
BORDER_HOVER = "#3a4150"
TEXT = "#e6edf3"
MUTED = "#8b949e"
DIM = "#57606a"
ACCENT = "#4c9aff"
ACCENT_STRONG = "#2563eb"
OK = "#3fb950"
WARN = "#d29922"
DANGER = "#f85149"

APP_QSS = f"""
QMainWindow {{ background: {BG}; }}
QWidget#LibraryView, QWidget#LibraryStack, QWidget#GridCanvas,
QWidget#EmptyPane {{ background: {BG}; }}
QScrollArea, QScrollArea > QWidget > QWidget {{ background: {BG}; border: none; }}
QWidget {{ color: {TEXT};
           font-family: "Segoe UI Variable Text", "Segoe UI"; font-size: 13px; }}

QWidget#TopBar {{ background: {SURFACE}; border-bottom: 1px solid #232833; }}
QLabel#AppTitle {{ font-family: "Century Gothic", "Trebuchet MS", "Segoe UI";
                   font-size: 23px; font-weight: 600; color: {TEXT}; }}
QLabel#SectionTitle {{ font-family: "Segoe UI Variable Display", "Segoe UI";
                       font-size: 19px; font-weight: 600; }}
QLabel#SectionHint {{ color: {MUTED}; font-size: 12px; }}
QLabel#Breadcrumb {{ color: {MUTED}; font-size: 12px; }}
QLabel#EmptyTitle {{ font-family: "Segoe UI Variable Display", "Segoe UI";
                     font-size: 20px; font-weight: 600; }}
QLabel#EmptyHint {{ color: {MUTED}; font-size: 12px; }}

QToolButton#FolderCard {{ background: {SURFACE}; border: 1px solid {BORDER};
                          border-radius: 10px; padding: 10px; text-align: center;
                          font-weight: 600; }}
QToolButton#FolderCard:hover {{ background: {SURFACE_ALT};
                                border-color: {BORDER_HOVER}; }}
QPushButton#FolderBack {{ padding: 6px 10px; }}

QToolButton#Overflow {{ background: {SURFACE_ALT}; border: 1px solid {BORDER};
                        border-radius: 8px; color: {MUTED}; font-size: 17px; }}
QToolButton#Overflow:hover {{ background: #222833; border-color: {BORDER_HOVER};
                              color: {TEXT}; }}
QToolButton#Overflow:pressed {{ background: #161a21; }}
QToolButton#Overflow::menu-indicator {{ image: none; width: 0; }}
QToolButton#TrackMenu {{ background: {SURFACE_ALT}; border: 1px solid {BORDER};
                        border-radius: 8px; padding: 6px 9px; }}
QToolButton#TrackMenu:hover {{ background: #222833; border-color: {BORDER_HOVER}; }}
QToolButton#TrackMenu:focus {{ border-color: {ACCENT}; }}

QLineEdit#Search {{ background: {SURFACE_ALT}; border: 1px solid {BORDER};
                    border-radius: 8px; padding: 7px 10px;
                    selection-background-color: {ACCENT_STRONG}; }}
QLineEdit#Search:focus {{ border-color: {ACCENT}; }}

QComboBox {{ background: {SURFACE_ALT}; border: 1px solid {BORDER};
             border-radius: 8px; padding: 6px 10px; min-width: 132px; }}
QComboBox:hover {{ border-color: {BORDER_HOVER}; }}
QComboBox::drop-down {{ border: none; width: 18px; }}
QComboBox QAbstractItemView {{ background: {SURFACE_ALT}; border: 1px solid {BORDER};
                               selection-background-color: #24344d; outline: none; }}

QPushButton {{ background: {SURFACE_ALT}; border: 1px solid {BORDER};
               border-radius: 8px; padding: 7px 12px; }}
QPushButton:hover {{ background: #222833; border-color: {BORDER_HOVER}; }}
QPushButton:pressed {{ background: #161a21; }}
QPushButton#Primary {{ background: {ACCENT_STRONG}; border-color: {ACCENT_STRONG};
                       color: white; font-weight: 600; }}
QPushButton#Primary:hover {{ background: #3b82f6; }}

QScrollArea {{ border: none; background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {BORDER}; border-radius: 4px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {BORDER_HOVER}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}

QStatusBar {{ background: {SURFACE}; border-top: 1px solid #232833; color: {MUTED}; }}
QStatusBar::item {{ border: none; }}

QMenu {{ background: {SURFACE_ALT}; border: 1px solid {BORDER}; padding: 4px; }}
QMenu::item {{ padding: 6px 18px; border-radius: 5px; }}
QMenu::item:selected {{ background: #24344d; }}
QMenu::item:disabled {{ color: {DIM}; }}
QMenu::separator {{ height: 1px; background: {BORDER}; margin: 4px 8px; }}

QToolTip {{ background: {SURFACE_ALT}; color: {TEXT}; border: 1px solid {BORDER};
            padding: 4px; }}

QWidget#PlayerView {{ background: {BG}; }}
QWidget#VideoArea {{ background: #000000; }}
QWidget#PlayerTop {{ background: {SURFACE}; border-bottom: 1px solid #232833; }}
QWidget#PlayerBar {{ background: {SURFACE}; border-top: 1px solid #232833; }}
QLabel#PlayerTitle {{ font-size: 15px; font-weight: 600; }}
QLabel#Time {{ color: {MUTED}; font-size: 11px; }}
QLabel#PlayerError {{ color: {DANGER}; font-size: 14px; }}

QSlider#Volume::groove:horizontal {{ height: 4px; background: {BORDER};
                                     border-radius: 2px; }}
QSlider#Volume::sub-page:horizontal {{ background: {ACCENT}; border-radius: 2px; }}
QSlider#Volume::handle:horizontal {{ background: {TEXT}; width: 12px; height: 12px;
                                     margin: -4px 0; border-radius: 6px; }}
QSlider#Volume::handle:horizontal:hover {{ background: #ffffff; }}

QLabel#Toast {{ background: #1e2430; border: 1px solid #2f3a4c; border-radius: 8px;
                padding: 8px 14px; color: {TEXT}; }}
"""


def gradient_colors(seed: str) -> tuple[QColor, QColor]:
    """Stable, muted two-stop gradient derived from the title."""
    value = 0
    for char in seed:
        value = (value * 31 + ord(char)) & 0xFFFFFFFF
    hue = (value % 360) / 360.0
    top = QColor.fromHsvF(hue, 0.52, 0.44)
    bottom = QColor.fromHsvF((hue + 0.07) % 1.0, 0.68, 0.20)
    return top, bottom
