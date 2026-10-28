from __future__ import annotations

import os
from pathlib import Path

import pytest

from telovie.db import Database, MediaUpsert


@pytest.fixture()
def db(tmp_path: Path):
    database = Database(tmp_path / "library.db")
    yield database
    database.close()


def add(db: Database, name: str, duration: int = 3_000_000) -> str:
    path = str(Path("C:/Media") / f"{name}.mkv")
    db.library.upsert_many([MediaUpsert(name, path, duration)])
    return path


def test_upsert_and_case_insensitive_dedupe(db: Database):
    add(db, "Alpha")
    add(db, "Beta")
    assert db.library.count() == 2

    db.library.upsert_many([MediaUpsert("Alpha remuxed", str(Path("c:/media/alpha.mkv")), 9)])
    assert db.library.count() == 2
    row = db.library.find_by_path(str(Path("C:/Media/Alpha.mkv")))
    assert row["Title"] == "Alpha remuxed"
    assert row["TotalDuration"] == 9


def test_grid_search_and_sort(db: Database):
    add(db, "Zulu", 100)
    add(db, "Alpha", 300)
    add(db, "Mike", 200)

    titles = [row["Title"] for row in db.library.list_for_grid(sort="title")]
    assert titles == ["Alpha", "Mike", "Zulu"]

    by_duration = [row["Title"] for row in db.library.list_for_grid(sort="duration")]
    assert by_duration == ["Alpha", "Mike", "Zulu"]

    matches = db.library.list_for_grid(search="mik")
    assert [row["Title"] for row in matches] == ["Mike"]

    # path search, case-insensitive
    matches = db.library.list_for_grid(search="alpha.mkv")
    assert [row["Title"] for row in matches] == ["Alpha"]

    # LIKE wildcards in user input must not widen the search
    assert db.library.list_for_grid(search="%") == []


def test_mark_missing_flags_absent_files(db: Database):
    root = Path("C:/Media")
    path_a = add(db, "A")
    path_b = add(db, "B")

    assert db.library.mark_missing(root, [path_a]) == 1
    assert db.library.find_by_path(path_a)["IsAvailable"] == 1
    assert db.library.find_by_path(path_b)["IsAvailable"] == 0

    # seeing the file again clears the flag, even without a re-parse
    assert db.library.mark_missing(root, [path_a, path_b]) == 0
    assert db.library.find_by_path(path_b)["IsAvailable"] == 1

    # re-seeing the file via an upsert also clears it
    db.library.mark_missing(root, [path_a])
    db.library.upsert_many([MediaUpsert("B", path_b, 1)])
    assert db.library.find_by_path(path_b)["IsAvailable"] == 1

    # files outside the scanned root are untouched
    outside = str(Path("D:/Other") / "Elsewhere.mkv")
    db.library.upsert_many([MediaUpsert("Elsewhere", outside)])
    db.library.mark_missing(root, [])
    assert db.library.find_by_path(outside)["IsAvailable"] == 1


def test_file_stamps_keyed_by_normcase(db: Database):
    path = str(Path("C:/Media") / "Stamp.mkv")
    db.library.upsert_many([MediaUpsert("Stamp", path, 1, 123, 456.0)])
    stamps = db.library.file_stamps()
    key = os.path.normcase(path)
    assert key in stamps
    assert stamps[key] == (123, 456.0)


def test_progress_completion_and_play_count(db: Database):
    path = add(db, "Episode")
    media_id = db.library.find_by_path(path)["id"]

    db.playback.save_position(media_id, 120_000)
    state = db.playback.get(media_id)
    assert state["LastPosition"] == 120_000
    assert state["IsCompleted"] == 0

    db.playback.mark_completed(media_id)
    state = db.playback.get(media_id)
    assert state["LastPosition"] == 0
    assert state["IsCompleted"] == 1

    db.playback.mark_in_progress(media_id)
    assert db.playback.get(media_id)["IsCompleted"] == 0

    db.playback.increment_play_count(media_id)
    db.playback.increment_play_count(media_id)
    assert db.playback.get(media_id)["PlayCount"] == 2

    db.playback.save_position(media_id, -50)
    assert db.playback.get(media_id)["LastPosition"] == 0


def test_track_memory_roundtrip(db: Database):
    path = add(db, "Tracks")
    media_id = db.library.find_by_path(path)["id"]

    db.playback.set_audio_track(media_id, 1)
    db.playback.set_subtitle_track(media_id, -1)
    state = db.playback.get(media_id)
    assert state["AudioTrackIndex"] == 1
    assert state["SubtitleTrackIndex"] == -1

    # clearing a choice must not disturb the other track type
    db.playback.set_audio_track(media_id, 0)
    state = db.playback.get(media_id)
    assert state["AudioTrackIndex"] == 0
    assert state["SubtitleTrackIndex"] == -1

    db.playback.set_subtitle_track(media_id, None)
    assert db.playback.get(media_id)["SubtitleTrackIndex"] is None

    with pytest.raises(ValueError):
        db.playback.set_subtitle_track(media_id, -2)


def test_delete_cascades_to_playback(db: Database):
    path = add(db, "Gone")
    media_id = db.library.find_by_path(path)["id"]
    db.playback.save_position(media_id, 5000)

    assert db.library.remove(media_id) is True
    assert db.library.get(media_id) is None
    assert db.playback.get(media_id) is None
    assert db.library.remove(media_id) is False


def test_preferences_defaults_and_normalisation(db: Database):
    prefs = db.prefs.get()
    assert prefs.default_audio_langs == "eng"
    assert prefs.default_sub_langs == ""
    assert prefs.volume == 80
    assert prefs.last_library_root is None
    assert prefs.scan_recursive is True
    assert prefs.audio_langs == ["eng"]

    updated = db.prefs.update(
        default_audio_langs="EN, hi, en",
        default_sub_langs="eng, spa",
        volume=150,
        last_library_root=Path("C:/Media"),
    )
    assert updated.default_audio_langs == "eng,hin"
    assert updated.default_sub_langs == "eng,spa"
    assert updated.volume == 100
    assert updated.last_library_root == str(Path("C:/Media"))
    assert updated.sub_langs == ["eng", "spa"]

    cleared = db.prefs.update(clear_library_root=True, volume=-5)
    assert cleared.last_library_root is None
    assert cleared.volume == 0


def test_preferences_persist_across_reopen(tmp_path: Path):
    db = Database(tmp_path / "persist.db")
    db.prefs.update(default_audio_langs="hin,eng", default_sub_langs="eng", volume=55)
    db.close()

    reopened = Database(tmp_path / "persist.db")
    try:
        prefs = reopened.prefs.get()
        assert prefs.default_audio_langs == "hin,eng"
        assert prefs.default_sub_langs == "eng"
        assert prefs.volume == 55
    finally:
        reopened.close()


def test_continue_watching(db: Database):
    root = Path("C:/Media")
    path_a = add(db, "A")
    path_b = add(db, "B")
    path_c = add(db, "C")
    id_a = db.library.find_by_path(path_a)["id"]
    id_b = db.library.find_by_path(path_b)["id"]
    id_c = db.library.find_by_path(path_c)["id"]

    db.playback.save_position(id_a, 120_000)
    db.playback.save_position(id_b, 9_000)     # below the resume threshold
    db.playback.save_position(id_c, 200_000)
    db.playback.mark_completed(id_c)

    rows = db.playback.continue_watching()
    assert [row["id"] for row in rows] == [id_a]

    db.library.mark_missing(root, [])
    assert db.playback.continue_watching() == []
