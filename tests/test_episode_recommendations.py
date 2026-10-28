from __future__ import annotations

from pathlib import Path

from telovie.library.episodes import episode_order, next_episode_recommendations


def _row(media_id: int, path: Path, *, completed: bool = False) -> dict:
    return {
        "id": media_id,
        "FilePath": str(path),
        "IsCompleted": int(completed),
        "IsAvailable": 1,
    }


def test_episode_order_reads_season_and_episode_from_filename(tmp_path: Path):
    assert episode_order(tmp_path / "Show" / "S02E05.mkv") == (2, 5)
    assert episode_order(tmp_path / "Show" / "Season 3" / "06 - Finale.mkv") == (3, 6)
    assert episode_order(tmp_path / "Show" / "feature.mkv") is None


def test_completed_episode_recommends_next_unwatched_episode(tmp_path: Path):
    show = tmp_path / "Show"
    first = _row(1, show / "Season 1" / "S01E01.mkv", completed=True)
    second = _row(2, show / "Season 1" / "S01E02.mkv")
    third = _row(3, show / "Season 1" / "S01E03.mkv")

    recommended = next_episode_recommendations(
        [first, second, third], tmp_path, set()
    )

    assert [row["id"] for row in recommended] == [2]


def test_active_episode_suppresses_duplicate_next_episode_suggestion(tmp_path: Path):
    show = tmp_path / "Show"
    first = _row(1, show / "Season 1" / "S01E01.mkv", completed=True)
    second = _row(2, show / "Season 1" / "S01E02.mkv")

    recommended = next_episode_recommendations(
        [first, second], tmp_path, {2}
    )

    assert recommended == []
