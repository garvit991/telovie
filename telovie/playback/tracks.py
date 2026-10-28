"""Pure track-selection rules shared by playback and tests."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from telovie.mkv.parser import TrackInfo
from telovie.util.languages import normalize_code


@dataclass(frozen=True)
class TrackChoice:
    index: int | None
    source: str


def choose_track(
    tracks: Sequence[TrackInfo],
    saved_index: int | None,
    preferred_languages: Sequence[str],
    *,
    subtitles: bool = False,
) -> TrackChoice:
    """Resolve saved choice, then preferred language, then container default.

    ``index=None`` means keep Qt's container-selected track. Subtitle ``-1``
    explicitly means captions off.
    """
    if saved_index is not None:
        if subtitles and saved_index == -1:
            return TrackChoice(-1, "saved")
        if 0 <= saved_index < len(tracks):
            return TrackChoice(saved_index, "saved")

    preferences = [
        normalize_code(code)
        for code in preferred_languages
        if normalize_code(code) and normalize_code(code) != "und"
    ]
    for language in preferences:
        for index, track in enumerate(tracks):
            code = normalize_code(track.language)
            if code and code != "und" and code == language:
                return TrackChoice(index, f"language {language}")

    if subtitles and preferences:
        return TrackChoice(-1, "no language match")
    return TrackChoice(None, "container default")
