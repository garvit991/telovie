from __future__ import annotations

from telovie.mkv.parser import TrackInfo
from telovie.playback.tracks import choose_track


TRACKS = [
    TrackInfo(number=1, kind="audio", language="jpn", codec="A_AAC"),
    TrackInfo(number=2, kind="audio", language="eng", codec="A_AC3"),
    TrackInfo(number=3, kind="audio", language="und", codec="A_AAC"),
]


def test_saved_choice_takes_priority_over_language():
    choice = choose_track(TRACKS, 0, ["eng"])
    assert (choice.index, choice.source) == (0, "saved")


def test_stale_saved_choice_falls_back_to_first_preferred_language():
    choice = choose_track(TRACKS, 9, ["en", "jpn"])
    assert (choice.index, choice.source) == (1, "language eng")


def test_undetermined_language_never_matches():
    choice = choose_track(TRACKS, None, ["und"])
    assert choice.index is None


def test_subtitles_preserve_explicit_off_choice():
    captions = [TrackInfo(number=4, kind="subtitle", language="eng")]
    choice = choose_track(captions, -1, ["eng"], subtitles=True)
    assert (choice.index, choice.source) == (-1, "saved")


def test_unmatched_preferred_subtitle_language_turns_captions_off():
    captions = [TrackInfo(number=4, kind="subtitle", language="spa")]
    choice = choose_track(captions, None, ["eng"], subtitles=True)
    assert (choice.index, choice.source) == (-1, "no language match")


def test_no_subtitle_preference_leaves_container_default():
    captions = [TrackInfo(number=4, kind="subtitle", language="spa")]
    choice = choose_track(captions, None, [], subtitles=True)
    assert (choice.index, choice.source) == (None, "container default")
