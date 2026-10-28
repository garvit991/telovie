"""Episode ordering helpers used for next-episode recommendations."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

EPISODE_PATTERN = re.compile(r"(?:^|[ ._-])S(\d{1,3})[ ._-]*E(\d{1,4})(?:\b|[ ._-])", re.I)
EPISODE_ONLY_PATTERN = re.compile(r"^(?:E|Episode[ ._-]*)?(\d{1,4})(?:\b|[ ._-])", re.I)
SEASON_PATTERN = re.compile(r"(?:^|[ ._-])Season[ ._-]*(\d{1,3})(?:\b|[ ._-])", re.I)


def episode_order(file_path: str | Path) -> tuple[int, int] | None:
    """Return a sortable (season, episode) for common show/season file names."""
    path = Path(file_path)
    match = EPISODE_PATTERN.search(path.stem)
    if match:
        return int(match.group(1)), int(match.group(2))

    season = None
    for part in reversed(path.parts[:-1]):
        season_match = SEASON_PATTERN.search(part)
        if season_match:
            season = int(season_match.group(1))
            break
    episode_match = EPISODE_ONLY_PATTERN.search(path.stem)
    if season is not None and episode_match:
        return season, int(episode_match.group(1))
    return None


def _series_key(file_path: str | Path, library_root: str | Path) -> str | None:
    path = Path(file_path)
    try:
        relative = path.relative_to(Path(library_root))
    except ValueError:
        relative = path

    if len(relative.parts) > 1:
        return relative.parts[0].casefold()

    match = EPISODE_PATTERN.search(path.stem)
    if match:
        name = path.stem[: match.start()].rstrip(" ._-")
        return name.casefold() or None
    return None


def next_episode_recommendations(
    rows: Iterable[object],
    library_root: str | Path,
    active_ids: set[int],
) -> list[object]:
    """Suggest the first unwatched episode after each show's latest completion."""
    rows = list(rows)
    episodes: dict[str, list[tuple[tuple[int, int], object]]] = {}
    completed: dict[str, tuple[int, int]] = {}

    for row in rows:
        if not bool(row["IsAvailable"]):
            continue
        order = episode_order(row["FilePath"])
        series = _series_key(row["FilePath"], library_root)
        if order is None or series is None:
            continue
        episodes.setdefault(series, []).append((order, row))
        if bool(row["IsCompleted"]):
            completed[series] = max(completed.get(series, order), order)

    recommendations: list[object] = []
    for series, last_completed in completed.items():
        if any(
            _series_key(row["FilePath"], library_root) == series
            for row in rows
            if int(row["id"]) in active_ids
        ):
            continue
        candidates = sorted(episodes[series], key=lambda item: (item[0], item[1]["FilePath"]))
        for order, row in candidates:
            if order <= last_completed or bool(row["IsCompleted"]):
                continue
            recommendations.append(row)
            break
    return recommendations
