"""Visual tokens and the application stylesheet."""

from __future__ import annotations

import logging
import sys

from PySide6.QtGui import QColor

log = logging.getLogger(__name__)

BG = "rgba(13, 16, 22, 80)"
SURFACE = "rgba(18, 21, 27, 40)"
OPAQUE_BG = "#0f1115"
OPAQUE_SURFACE = "#12151b"
GLASS_BG = BG if sys.platform == "win32" else OPAQUE_BG
GLASS_SURFACE = SURFACE if sys.platform == "win32" else OPAQUE_SURFACE
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
QMainWindow {{ background: transparent; }}
QStackedWidget#CentralStack {{ background: {GLASS_BG}; }}
QWidget#LibraryView, QWidget#LibraryStack, QWidget#GridCanvas,
QWidget#EmptyPane {{ background: transparent; }}
QWidget#StatsSidebar {{ background: {GLASS_SURFACE}; border-left: 1px solid #232833; }}
QWidget#StatsEdge {{ background: {BORDER}; }}
QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; border: none; }}
QWidget {{ color: {TEXT};
           font-family: "Segoe UI Variable Text", "Segoe UI"; font-size: 13px; }}

QWidget#TopBar {{ background: {GLASS_SURFACE}; border-bottom: 1px solid #232833; }}
QLabel#AppTitle {{ font-family: "Century Gothic", "Trebuchet MS", "Segoe UI";
                   font-size: 23px; font-weight: 600; color: {TEXT}; }}
QLabel#SectionTitle {{ font-family: "Segoe UI Variable Display", "Segoe UI";
                       font-size: 19px; font-weight: 600; }}
QLabel#SectionHint {{ color: {MUTED}; font-size: 12px; }}
QLabel#Breadcrumb {{ color: {MUTED}; font-size: 12px; }}
QLabel#StatsTitle {{ color: {DIM}; font-size: 10px; font-weight: 700;
                     letter-spacing: 1px; }}
QFrame#WatchRing {{ background: {OPAQUE_SURFACE}; border: 2px solid {ACCENT};
                    border-radius: 66px; }}
QLabel#WatchStat {{ color: {TEXT}; font-size: 14px; font-weight: 600; }}
QLabel#EmptyTitle {{ font-family: "Segoe UI Variable Display", "Segoe UI";
                     font-size: 20px; font-weight: 600; }}
QLabel#EmptyHint {{ color: {MUTED}; font-size: 12px; }}

QToolButton#FolderCard {{ background: {OPAQUE_SURFACE}; border: 1px solid {BORDER};
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
QToolButton#EpisodeNavigation {{ background: {SURFACE_ALT}; border: 1px solid {BORDER};
                                border-radius: 8px; padding: 6px 9px; }}
QToolButton#EpisodeNavigation:hover {{ background: #222833; border-color: {BORDER_HOVER}; }}
QToolButton#EpisodeNavigation:disabled {{ color: {DIM}; background: transparent;
                                          border-color: transparent; }}

QFrame#SearchBox {{ background: {SURFACE_ALT}; border: 1px solid {BORDER};
                    border-radius: 9px; }}
QLineEdit#Search {{ background: transparent; border: none; padding: 7px 2px;
                    selection-background-color: {ACCENT_STRONG}; }}
QToolButton#SortMenu {{ background: transparent; border: none; border-radius: 6px;
                        color: {MUTED}; font-size: 18px; padding: 0 5px; }}
QToolButton#SortMenu:hover {{ background: #222833; color: {TEXT}; }}
QToolButton#SortMenu::menu-indicator {{ image: none; width: 0; }}

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

QStatusBar {{ background: {GLASS_BG}; border-top: 1px solid #232833; color: {MUTED}; }}
QStatusBar::item {{ border: none; }}

QMenu {{ background: {SURFACE_ALT}; border: 1px solid {BORDER}; padding: 4px; }}
QMenu::item {{ padding: 6px 18px; border-radius: 5px; }}
QMenu::item:selected {{ background: #24344d; }}
QMenu::item:disabled {{ color: {DIM}; }}
QMenu::separator {{ height: 1px; background: {BORDER}; margin: 4px 8px; }}

QToolTip {{ background: {SURFACE_ALT}; color: {TEXT}; border: 1px solid {BORDER};
            padding: 4px; }}

QWidget#PlayerView {{ background: transparent; }}
QWidget#VideoArea {{ background: #000000; }}
QWidget#PlayerTop {{ background: {GLASS_SURFACE}; border-bottom: 1px solid #232833; }}
QWidget#PlayerBar {{ background: {GLASS_SURFACE}; border-top: 1px solid #232833; }}
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


def enable_acrylic_backdrop(window_id: int) -> bool:
    """Request the Windows acrylic system backdrop for the top-level window.

    The system backdrop only paints the window frame by default, which is why
    acrylic normally shows up in the title bar only. Extending the frame into
    the client area turns the whole window into a sheet of glass, so the
    backdrop is visible behind the transparent application background too.
    """
    if sys.platform != "win32":
        return False

    import ctypes
    from ctypes import wintypes

    class _Margins(ctypes.Structure):
        _fields_ = [
            ("cxLeftWidth", ctypes.c_int),
            ("cxRightWidth", ctypes.c_int),
            ("cyTopHeight", ctypes.c_int),
            ("cyBottomHeight", ctypes.c_int),
        ]

    dwmapi = ctypes.windll.dwmapi  # type: ignore[attr-defined]
    dwm_set_window_attribute = dwmapi.DwmSetWindowAttribute
    dwm_set_window_attribute.argtypes = (
        wintypes.HWND,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
    )
    dwm_set_window_attribute.restype = ctypes.c_long

    dwm_extend_frame = dwmapi.DwmExtendFrameIntoClientArea
    dwm_extend_frame.argtypes = (wintypes.HWND, ctypes.POINTER(_Margins))
    dwm_extend_frame.restype = ctypes.c_long

    DWMWA_USE_IMMERSIVE_DARK_MODE = 20
    DWMWA_SYSTEMBACKDROP_TYPE = 38
    dark_mode = ctypes.c_int(1)
    dark_mode_result = dwm_set_window_attribute(
        wintypes.HWND(window_id),
        DWMWA_USE_IMMERSIVE_DARK_MODE,
        ctypes.byref(dark_mode),
        ctypes.sizeof(dark_mode),
    )
    if dark_mode_result != 0:
        log.warning(
            "Windows did not enable dark mode for the acrylic backdrop (HRESULT 0x%08X)",
            dark_mode_result & 0xFFFFFFFF,
        )

    backdrop_type = ctypes.c_int(3)  # DWMSBT_TRANSIENTWINDOW
    result = dwm_set_window_attribute(
        wintypes.HWND(window_id),
        DWMWA_SYSTEMBACKDROP_TYPE,
        ctypes.byref(backdrop_type),
        ctypes.sizeof(backdrop_type),
    )
    if result != 0:
        log.warning(
            "Windows did not enable the acrylic system backdrop (HRESULT 0x%08X)",
            result & 0xFFFFFFFF,
        )
        return False

    # A negative margin extends the frame over the entire client area. Without
    # it the backdrop is painted behind the frame only, which is why acrylic
    # normally appears in the title bar and nowhere else.
    margins = _Margins(-1, -1, -1, -1)
    extend_result = dwm_extend_frame(
        wintypes.HWND(window_id), ctypes.byref(margins)
    )
    if extend_result != 0:
        log.warning(
            "Windows did not extend the window frame for the acrylic backdrop "
            "(HRESULT 0x%08X)",
            extend_result & 0xFFFFFFFF,
        )
        return False
    return True
