"""Cheap polling watcher for the library folder.

QFileSystemWatcher does not recurse reliably and chokes on big trees, so we
compare (size, mtime) snapshots every few seconds instead. Two identical
snapshots are required before emitting, which keeps a half-extracted zip from
being indexed and stops scan/refresh loops.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal

from telovie.library.scanner import collect_mkv_files

DEFAULT_INTERVAL_MS = 3_000


class LibraryWatcher(QObject):
    changed = Signal()

    def __init__(
        self, root: str | Path, interval_ms: int = DEFAULT_INTERVAL_MS, parent=None
    ) -> None:
        super().__init__(parent)
        self.root = Path(root)
        self._timer = QTimer(self)
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self._poll)
        self._last: dict[str, tuple[int, float]] = {}
        self._pending: dict[str, tuple[int, float]] | None = None

    def start(self) -> None:
        self._last = self._snapshot()
        self._pending = None
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    def sync(self) -> None:
        """Reset the baseline after a scan so we do not re-trigger for it."""
        self._last = self._snapshot()
        self._pending = None

    def _snapshot(self) -> dict[str, tuple[int, float]]:
        snapshot: dict[str, tuple[int, float]] = {}
        try:
            files = collect_mkv_files(self.root)
        except OSError:
            return snapshot
        for path in files:
            try:
                stat = path.stat()
            except OSError:
                continue
            snapshot[str(path)] = (stat.st_size, stat.st_mtime)
        return snapshot

    def _poll(self) -> None:
        snapshot = self._snapshot()
        if snapshot == self._last:
            self._pending = None
            return
        if self._pending is not None and snapshot == self._pending:
            self._last = snapshot
            self._pending = None
            self.changed.emit()
        else:
            self._pending = snapshot
