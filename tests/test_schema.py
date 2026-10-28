from __future__ import annotations

import sqlite3

import pytest

from telovie.db.schema import SCHEMA_VERSION, connect, migrate


def test_migrate_creates_schema(tmp_path):
    conn = connect(tmp_path / "fresh.db")
    try:
        assert migrate(conn) == SCHEMA_VERSION
        assert migrate(conn) == SCHEMA_VERSION  # idempotent

        version = conn.execute("PRAGMA user_version").fetchone()[0]
        assert version == SCHEMA_VERSION

        tables = {
            row["name"]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert {"MediaLibrary", "PlaybackState", "Preferences"} <= tables

        playback_cols = {
            row["name"] for row in conn.execute("PRAGMA table_info(PlaybackState)")
        }
        assert {"MediaID", "LastPosition", "IsCompleted", "AudioTrackIndex",
                "SubtitleTrackIndex"} <= playback_cols

        prefs = conn.execute("SELECT * FROM Preferences").fetchone()
        assert prefs["id"] == 1
        assert prefs["DefaultAudioLang"] == "eng"
        assert prefs["DefaultSubLang"] == ""
        assert prefs["Volume"] == 80

        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    finally:
        conn.close()


def test_unique_path_is_case_insensitive(tmp_path):
    conn = connect(tmp_path / "case.db")
    try:
        migrate(conn)
        conn.execute(
            "INSERT INTO MediaLibrary (Title, FilePath) VALUES ('A', 'C:/Media/File.mkv')"
        )
        conn.commit()
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO MediaLibrary (Title, FilePath) VALUES ('B', 'c:/media/file.mkv')"
            )
    finally:
        conn.close()
