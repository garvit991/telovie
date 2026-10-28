"""SQLite schema and migration runner.

Version 1 is the only schema so far. Future changes append to MIGRATIONS and
bump SCHEMA_VERSION; `migrate()` applies them in order inside one transaction.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA_VERSION = 1

DDL_V1 = """
CREATE TABLE IF NOT EXISTS MediaLibrary (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    Title         TEXT    NOT NULL,
    FilePath      TEXT    NOT NULL COLLATE NOCASE UNIQUE,
    TotalDuration INTEGER NOT NULL DEFAULT 0,
    FileSize      INTEGER NOT NULL DEFAULT 0,
    FileMTime     REAL    NOT NULL DEFAULT 0,
    IsAvailable   INTEGER NOT NULL DEFAULT 1 CHECK (IsAvailable IN (0, 1)),
    AddedAt       TEXT    NOT NULL DEFAULT (datetime('now')),
    LastSeenAt    TEXT
);

CREATE INDEX IF NOT EXISTS idx_media_title ON MediaLibrary(Title COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS idx_media_available ON MediaLibrary(IsAvailable, Title COLLATE NOCASE);

CREATE TABLE IF NOT EXISTS PlaybackState (
    MediaID           INTEGER PRIMARY KEY
                      REFERENCES MediaLibrary(id) ON DELETE CASCADE,
    LastPosition      INTEGER NOT NULL DEFAULT 0,
    IsCompleted       INTEGER NOT NULL DEFAULT 0 CHECK (IsCompleted IN (0, 1)),
    AudioTrackIndex   INTEGER,
    SubtitleTrackIndex INTEGER,
    PlayCount         INTEGER NOT NULL DEFAULT 0,
    UpdatedAt         TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_playback_completed
    ON PlaybackState(IsCompleted, UpdatedAt DESC);

CREATE TABLE IF NOT EXISTS Preferences (
    id               INTEGER PRIMARY KEY CHECK (id = 1),
    DefaultAudioLang TEXT    NOT NULL DEFAULT 'eng',
    DefaultSubLang   TEXT    NOT NULL DEFAULT '',
    Volume           INTEGER NOT NULL DEFAULT 80 CHECK (Volume BETWEEN 0 AND 100),
    LastLibraryRoot  TEXT,
    ScanRecursive    INTEGER NOT NULL DEFAULT 1 CHECK (ScanRecursive IN (0, 1))
);

INSERT OR IGNORE INTO Preferences (id) VALUES (1);
"""

MIGRATIONS: dict[int, str] = {1: DDL_V1}


def connect(db_path: str | Path) -> sqlite3.Connection:
    """Open a connection with the pragmas the app relies on."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


def migrate(conn: sqlite3.Connection) -> int:
    """Apply pending migrations. Idempotent. Returns the resulting version."""
    version = int(conn.execute("PRAGMA user_version").fetchone()[0])
    if version > SCHEMA_VERSION:
        raise RuntimeError(
            f"Database schema v{version} is newer than this build (v{SCHEMA_VERSION}). "
            "Upgrade Telovie or use a different data directory."
        )
    if version < SCHEMA_VERSION:
        for target in range(version + 1, SCHEMA_VERSION + 1):
            script = MIGRATIONS.get(target)
            if script is None:
                raise RuntimeError(f"Missing migration for schema v{target}")
            conn.executescript(script)
            conn.execute(f"PRAGMA user_version = {target}")
        conn.commit()
    return SCHEMA_VERSION
