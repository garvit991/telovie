"""Data access layer. Every SQL statement in the app lives in this package."""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from telovie.config import MIN_RESUME_POSITION_MS
from telovie.db.schema import connect, migrate
from telovie.util.languages import format_language_list, parse_language_list


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _like_pattern(value: str) -> str:
    return f"%{_escape_like(value)}%"


@dataclass(frozen=True)
class MediaUpsert:
    title: str
    file_path: str
    total_duration: int = 0
    file_size: int = 0
    file_mtime: float = 0.0


@dataclass(frozen=True)
class Preferences:
    default_audio_langs: str
    default_sub_langs: str
    volume: int
    last_library_root: str | None
    scan_recursive: bool

    @property
    def audio_langs(self) -> list[str]:
        return parse_language_list(self.default_audio_langs)

    @property
    def sub_langs(self) -> list[str]:
        return parse_language_list(self.default_sub_langs)


class LibraryRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def count(self) -> int:
        return int(self.conn.execute("SELECT COUNT(*) FROM MediaLibrary").fetchone()[0])

    def get(self, media_id: int) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM MediaLibrary WHERE id = ?", (media_id,)
        ).fetchone()

    def find_by_path(self, file_path: str) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM MediaLibrary WHERE FilePath = ?", (file_path,)
        ).fetchone()

    def upsert_many(self, items: Iterable[MediaUpsert]) -> int:
        rows = [
            (
                item.title,
                item.file_path,
                int(item.total_duration),
                int(item.file_size),
                float(item.file_mtime),
            )
            for item in items
        ]
        if not rows:
            return 0
        with self.conn:
            self.conn.executemany(
                """
                INSERT INTO MediaLibrary
                    (Title, FilePath, TotalDuration, FileSize, FileMTime,
                     IsAvailable, LastSeenAt)
                VALUES (?, ?, ?, ?, ?, 1, datetime('now'))
                ON CONFLICT(FilePath) DO UPDATE SET
                    Title         = excluded.Title,
                    TotalDuration = excluded.TotalDuration,
                    FileSize      = excluded.FileSize,
                    FileMTime     = excluded.FileMTime,
                    IsAvailable   = 1,
                    LastSeenAt    = datetime('now')
                """,
                rows,
            )
        return len(rows)

    def file_stamps(self) -> dict[str, tuple[int, float]]:
        """normcase(path) -> (size, mtime) for the incremental scanner."""
        return {
            os.path.normcase(row["FilePath"]): (
                int(row["FileSize"]),
                float(row["FileMTime"]),
            )
            for row in self.conn.execute(
                "SELECT FilePath, FileSize, FileMTime FROM MediaLibrary"
            )
        }

    def mark_missing(self, root: str | Path, seen_paths: Iterable[str]) -> int:
        """Flag rows under `root` that were not seen in the latest scan.

        Rows are never deleted, so playback progress survives an unplugged drive.
        Seen rows are also re-enabled here, which covers files that were flagged
        missing earlier but came back with an unchanged size/mtime (and therefore
        were skipped by the incremental parser).
        """
        seen = list(seen_paths)
        prefix = _escape_like(str(root).rstrip("\\/") + os.sep) + "%"
        with self.conn:
            self.conn.execute(
                "CREATE TEMP TABLE IF NOT EXISTS _seen_paths(path TEXT PRIMARY KEY)"
            )
            self.conn.execute("DELETE FROM _seen_paths")
            self.conn.executemany(
                "INSERT OR IGNORE INTO _seen_paths(path) VALUES (?)",
                [(path,) for path in seen],
            )
            self.conn.execute(
                """
                UPDATE MediaLibrary
                   SET IsAvailable = 1
                 WHERE IsAvailable = 0
                   AND FilePath IN (SELECT path FROM _seen_paths)
                """
            )
            cursor = self.conn.execute(
                """
                UPDATE MediaLibrary
                   SET IsAvailable = 0
                 WHERE IsAvailable = 1
                   AND FilePath LIKE ? ESCAPE '\\'
                   AND FilePath NOT IN (SELECT path FROM _seen_paths)
                """,
                (prefix,),
            )
            return cursor.rowcount

    def list_for_grid(self, search: str = "", sort: str = "title") -> list[sqlite3.Row]:
        orders = {
            "title": "m.Title COLLATE NOCASE ASC, m.id ASC",
            "added": "m.AddedAt DESC, m.id DESC",
            "duration": "m.TotalDuration DESC, m.Title COLLATE NOCASE ASC",
            "progress": "Progress DESC, m.Title COLLATE NOCASE ASC",
        }
        order = orders.get(sort, orders["title"])
        query = f"""
            SELECT m.id, m.Title, m.FilePath, m.TotalDuration, m.FileSize,
                   m.FileMTime, m.IsAvailable, m.AddedAt, m.LastSeenAt,
                   COALESCE(p.LastPosition, 0)  AS LastPosition,
                   COALESCE(p.IsCompleted, 0)   AS IsCompleted,
                   p.AudioTrackIndex            AS AudioTrackIndex,
                   p.SubtitleTrackIndex         AS SubtitleTrackIndex,
                   CASE WHEN m.TotalDuration > 0
                        THEN MIN(1.0, CAST(COALESCE(p.LastPosition, 0) AS REAL)
                                      / m.TotalDuration)
                        ELSE 0.0 END            AS Progress
              FROM MediaLibrary m
              LEFT JOIN PlaybackState p ON p.MediaID = m.id
             WHERE (:q = ''
                    OR m.Title LIKE :like ESCAPE '\\'
                    OR m.FilePath LIKE :like ESCAPE '\\')
             ORDER BY {order}
        """
        return list(
            self.conn.execute(
                query, {"q": search.strip(), "like": _like_pattern(search.strip())}
            )
        )

    def remove(self, media_id: int) -> bool:
        with self.conn:
            cursor = self.conn.execute(
                "DELETE FROM MediaLibrary WHERE id = ?", (media_id,)
            )
        return cursor.rowcount > 0


class PlaybackRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def ensure(self, media_id: int) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT OR IGNORE INTO PlaybackState (MediaID) VALUES (?)", (media_id,)
            )

    def get(self, media_id: int) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM PlaybackState WHERE MediaID = ?", (media_id,)
        ).fetchone()

    def save_position(
        self, media_id: int, position_ms: int, *, completed: bool | None = None
    ) -> None:
        self.ensure(media_id)
        position = max(0, int(position_ms))
        with self.conn:
            if completed is None:
                self.conn.execute(
                    """
                    UPDATE PlaybackState
                       SET LastPosition = ?, UpdatedAt = datetime('now')
                     WHERE MediaID = ?
                    """,
                    (position, media_id),
                )
            else:
                self.conn.execute(
                    """
                    UPDATE PlaybackState
                       SET LastPosition = ?, IsCompleted = ?,
                           UpdatedAt = datetime('now')
                     WHERE MediaID = ?
                    """,
                    (position, int(bool(completed)), media_id),
                )

    def mark_completed(self, media_id: int) -> None:
        """Completed means: badge on, next open starts at zero."""
        self.ensure(media_id)
        with self.conn:
            self.conn.execute(
                """
                UPDATE PlaybackState
                   SET LastPosition = 0, IsCompleted = 1,
                       UpdatedAt = datetime('now')
                 WHERE MediaID = ?
                """,
                (media_id,),
            )

    def mark_in_progress(self, media_id: int) -> None:
        self.ensure(media_id)
        with self.conn:
            self.conn.execute(
                """
                UPDATE PlaybackState
                   SET IsCompleted = 0, UpdatedAt = datetime('now')
                 WHERE MediaID = ?
                """,
                (media_id,),
            )

    def increment_play_count(self, media_id: int) -> None:
        self.ensure(media_id)
        with self.conn:
            self.conn.execute(
                """
                UPDATE PlaybackState
                   SET PlayCount = PlayCount + 1, UpdatedAt = datetime('now')
                 WHERE MediaID = ?
                """,
                (media_id,),
            )

    def set_audio_track(self, media_id: int, index: int | None) -> None:
        self.ensure(media_id)
        with self.conn:
            self.conn.execute(
                """
                UPDATE PlaybackState
                   SET AudioTrackIndex = ?, UpdatedAt = datetime('now')
                 WHERE MediaID = ?
                """,
                (index, media_id),
            )

    def set_subtitle_track(self, media_id: int, index: int | None) -> None:
        """index = -1 means captions off; None clears the saved choice."""
        if index is not None and index < -1:
            raise ValueError(f"invalid subtitle track index: {index}")
        self.ensure(media_id)
        with self.conn:
            self.conn.execute(
                """
                UPDATE PlaybackState
                   SET SubtitleTrackIndex = ?, UpdatedAt = datetime('now')
                 WHERE MediaID = ?
                """,
                (index, media_id),
            )

    def continue_watching(self, limit: int = 20) -> list[sqlite3.Row]:
        return list(
            self.conn.execute(
                """
                SELECT m.id, m.Title, m.FilePath, m.TotalDuration,
                       p.LastPosition, p.IsCompleted, p.UpdatedAt
                  FROM PlaybackState p
                  JOIN MediaLibrary m ON m.id = p.MediaID
                 WHERE p.IsCompleted = 0
                   AND p.LastPosition >= ?
                   AND m.IsAvailable = 1
                 ORDER BY p.UpdatedAt DESC
                 LIMIT ?
                """,
                (MIN_RESUME_POSITION_MS, int(limit)),
            )
        )


class PreferencesRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def get(self) -> Preferences:
        row = self.conn.execute("SELECT * FROM Preferences WHERE id = 1").fetchone()
        if row is None:
            with self.conn:
                self.conn.execute("INSERT OR IGNORE INTO Preferences (id) VALUES (1)")
            row = self.conn.execute(
                "SELECT * FROM Preferences WHERE id = 1"
            ).fetchone()
        return Preferences(
            default_audio_langs=row["DefaultAudioLang"],
            default_sub_langs=row["DefaultSubLang"],
            volume=int(row["Volume"]),
            last_library_root=row["LastLibraryRoot"],
            scan_recursive=bool(row["ScanRecursive"]),
        )

    def update(
        self,
        *,
        default_audio_langs: str | list[str] | None = None,
        default_sub_langs: str | list[str] | None = None,
        volume: int | None = None,
        last_library_root: str | Path | None = None,
        clear_library_root: bool = False,
        scan_recursive: bool | None = None,
    ) -> Preferences:
        current = self.get()
        audio = (
            format_language_list(default_audio_langs)
            if default_audio_langs is not None
            else current.default_audio_langs
        )
        subs = (
            format_language_list(default_sub_langs)
            if default_sub_langs is not None
            else current.default_sub_langs
        )
        new_volume = current.volume if volume is None else max(0, min(100, int(volume)))
        if clear_library_root:
            root: str | None = None
        elif last_library_root is not None:
            root = str(last_library_root)
        else:
            root = current.last_library_root
        recursive = current.scan_recursive if scan_recursive is None else bool(scan_recursive)

        with self.conn:
            self.conn.execute(
                """
                UPDATE Preferences
                   SET DefaultAudioLang = ?, DefaultSubLang = ?, Volume = ?,
                       LastLibraryRoot = ?, ScanRecursive = ?
                 WHERE id = 1
                """,
                (audio, subs, new_volume, root, int(recursive)),
            )
        return self.get()


class Database:
    """Owns the connection and exposes the repositories."""

    def __init__(self, db_path: str | Path) -> None:
        self.path = Path(db_path)
        self.conn = connect(self.path)
        migrate(self.conn)
        self.library = LibraryRepository(self.conn)
        self.playback = PlaybackRepository(self.conn)
        self.prefs = PreferencesRepository(self.conn)

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "Database":
        return self

    def __exit__(self, *_exc_info) -> None:
        self.close()
