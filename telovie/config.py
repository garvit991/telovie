"""Application paths and constants.

No Qt imports here: config must be importable by tests and tools.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

APP_NAME = "Telovie"
ORG_NAME = "Telovie"
LIBRARY_DIR_NAME = "Telovie"

DEFAULT_AUDIO_LANGS = "eng"
DEFAULT_SUB_LANGS = ""
DEFAULT_VOLUME = 80

MKV_SUFFIX = ".mkv"

# Resume / completion thresholds (milliseconds unless noted)
PROGRESS_SAVE_INTERVAL_MS = 5_000
MIN_RESUME_POSITION_MS = 10_000
COMPLETION_RATIO = 0.95


def _default_data_dir() -> Path:
    override = os.environ.get("TELOVIE_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    if base:
        return Path(base) / APP_NAME
    return Path.home() / f".{APP_NAME.lower()}"


def _default_library_dir() -> Path:
    """The permanent drop folder. One place, no picker."""
    override = os.environ.get("TELOVIE_LIBRARY_DIR")
    if override:
        return Path(override).expanduser().resolve()
    return Path.home() / "Videos" / LIBRARY_DIR_NAME


@dataclass(frozen=True)
class AppPaths:
    data_dir: Path
    db_path: Path
    log_dir: Path
    library_dir: Path

    @classmethod
    def resolve(cls) -> "AppPaths":
        data = _default_data_dir()
        return cls(
            data_dir=data,
            db_path=data / "library.db",
            log_dir=data / "logs",
            library_dir=_default_library_dir(),
        )

    def ensure(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.library_dir.mkdir(parents=True, exist_ok=True)
