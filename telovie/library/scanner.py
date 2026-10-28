"""Background indexing of the fixed library folder.

The worker only touches the filesystem and the MKV header parser. Every SQLite
write happens on the GUI thread via the ``batch`` signal.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from telovie.library.models import MediaItem, ScanSummary
from telovie.mkv.parser import display_title, parse_mkv

log = logging.getLogger(__name__)

SKIP_DIRS = {"system volume information", "$recycle.bin", "__pycache__"}
BATCH_SIZE = 40


def collect_mkv_files(root: str | Path) -> list[Path]:
    """Every .mkv under ``root`` (recursive, case-insensitive, stable order)."""
    root_path = Path(root)
    if not root_path.is_dir():
        return []
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root_path):
        dirnames[:] = sorted(
            name
            for name in dirnames
            if not name.startswith(".") and name.lower() not in SKIP_DIRS
        )
        for name in sorted(filenames):
            if name.lower().endswith(".mkv"):
                found.append(Path(dirpath) / name)
    return found


class ScanWorker(QThread):
    progress = Signal(int, int, str)  # done, total, current filename
    batch = Signal(list)  # list[MediaItem]
    finished_scan = Signal(object)  # ScanSummary
    failed = Signal(str)

    def __init__(
        self,
        root: str | Path,
        known_stamps: dict[str, tuple[int, float]] | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.root = Path(root)
        self.known = dict(known_stamps or {})

    def run(self) -> None:  # noqa: D401 - QThread entry point
        try:
            files = collect_mkv_files(self.root)
        except OSError as exc:
            log.exception("Could not walk the library folder")
            self.failed.emit(str(exc))
            return

        summary = ScanSummary(total=len(files))
        pending: list[MediaItem] = []

        for index, path in enumerate(files, start=1):
            if self.isInterruptionRequested():
                summary.cancelled = True
                break

            summary.seen.append(str(path))
            try:
                stat = path.stat()
            except OSError as exc:
                summary.errors += 1
                log.warning("Skipping %s: %s", path, exc)
                continue

            key = os.path.normcase(str(path))
            if self.known.get(key) == (stat.st_size, stat.st_mtime):
                summary.unchanged += 1
            else:
                info = parse_mkv(path)
                if info.error:
                    summary.errors += 1
                    log.warning("Header parse failed for %s: %s", path, info.error)
                pending.append(
                    MediaItem(
                        title=display_title(info.title, path.stem),
                        file_path=str(path),
                        duration_ms=info.duration_ms,
                        file_size=stat.st_size,
                        file_mtime=stat.st_mtime,
                    )
                )
                summary.parsed += 1
                if len(pending) >= BATCH_SIZE:
                    self.batch.emit(pending)
                    pending = []

            if index % 5 == 0 or index == summary.total:
                self.progress.emit(index, summary.total, path.name)

        if pending:
            self.batch.emit(pending)

        self.finished_scan.emit(summary)
