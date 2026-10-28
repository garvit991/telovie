from __future__ import annotations

import struct
from pathlib import Path

import pytest

from telovie.mkv.parser import display_title, parse_mkv, prettify_title

SAMPLES = Path(__file__).resolve().parent.parent / "sample files"


def _id(element_id: int) -> bytes:
    return element_id.to_bytes((element_id.bit_length() + 7) // 8, "big")


def _size(value: int) -> bytes:
    length = 1
    while value >= (1 << (7 * length)) - 1:
        length += 1
    return ((1 << (7 * length)) | value).to_bytes(length, "big")


def _el(element_id: int, payload: bytes) -> bytes:
    return _id(element_id) + _size(len(payload)) + payload


def _uint(value: int) -> bytes:
    if value == 0:
        return b"\x00"
    return value.to_bytes((value.bit_length() + 7) // 8, "big")


def _track(
    number: int,
    type_id: int,
    codec: str,
    *,
    language: str | None = None,
    ietf: str | None = None,
    name: str = "",
    default: bool = False,
) -> bytes:
    children = [
        _el(0xD7, _uint(number)),
        _el(0x83, _uint(type_id)),
        _el(0x86, codec.encode()),
    ]
    if language:
        children.append(_el(0x22B59C, language.encode()))
    if ietf:
        children.append(_el(0x22B59D, ietf.encode()))
    if name:
        children.append(_el(0x536E, name.encode()))
    if default:
        children.append(_el(0x88, _uint(1)))
    return _el(0xAE, b"".join(children))


def build_mkv(
    *,
    title: str = "Synthetic",
    duration_units: float = 1_234_500.0,
    tracks: list[bytes] | None = None,
    unknown_segment_size: bool = False,
) -> bytes:
    info = _el(
        0x1549A966,
        b"".join(
            [
                _el(0x2AD7B1, _uint(1_000_000)),
                _el(0x4489, struct.pack(">d", duration_units)),
                _el(0x7BA9, title.encode()),
                _el(0x4D80, b"libebml test"),
            ]
        ),
    )
    tracks_element = _el(0x1654AE6B, b"".join(tracks or []))
    cluster = _el(0x1F43B675, b"\x00" * 64)
    segment_body = info + tracks_element + cluster
    if unknown_segment_size:
        segment = _id(0x18538067) + b"\x01" + b"\xff" * 7 + segment_body
    else:
        segment = _el(0x18538067, segment_body)
    return _el(0x1A45DFA3, b"") + segment


def test_parse_title_duration_and_tracks(tmp_path: Path):
    data = build_mkv(
        title="The Test Episode",
        duration_units=1_234_500.0,
        tracks=[
            _track(1, 1, "V_MPEG4/ISO/AVC"),
            _track(2, 2, "A_AC3", language="hin", ietf="hi", name="Hindi", default=True),
            _track(3, 2, "A_AAC", ietf="en"),
            _track(4, 17, "S_TEXT/UTF8", language="eng", ietf="en"),
        ],
    )
    path = tmp_path / "episode.mkv"
    path.write_bytes(data)

    info = parse_mkv(path)
    assert info.error is None
    assert info.title == "The Test Episode"
    assert info.duration_ms == 1_234_500
    assert info.muxing_app == "libebml test"
    assert [t.kind for t in info.tracks] == ["video", "audio", "audio", "subtitle"]
    assert [t.language for t in info.audio_tracks] == ["hin", "eng"]
    assert info.subtitle_tracks[0].language == "eng"
    assert info.audio_tracks[0].is_default is True


def test_unknown_segment_size_is_handled(tmp_path: Path):
    path = tmp_path / "streamed.mkv"
    path.write_bytes(build_mkv(unknown_segment_size=True))
    info = parse_mkv(path)
    assert info.error is None
    assert info.duration_ms == 1_234_500


def test_truncated_file_reports_error_without_raising(tmp_path: Path):
    path = tmp_path / "broken.mkv"
    path.write_bytes(b"\x1a\x45\xdf\xa3")  # EBML id, no size
    info = parse_mkv(path)
    assert info.error is not None
    assert info.duration_ms == 0
    assert info.tracks == []


def test_missing_file_reports_error(tmp_path: Path):
    info = parse_mkv(tmp_path / "nope.mkv")
    assert info.error is not None


def test_display_title():
    assert display_title("", "Some.File") == "Some File"
    assert display_title("Some.File", "Some.File") == "Some File"
    assert display_title("Some.File.mkv", "Some.File") == "Some File"
    assert display_title("movieverse.co", "The.Mentalist.S01E01") == (
        "The Mentalist S01E01"
    )
    assert display_title("Game.Of.Thrones.S02E05", "Dr. Strangelove") == (
        "Dr. Strangelove"
    )


def test_prettify_title():
    assert prettify_title("Show.S01E01.1080p") == "Show S01E01 1080p"
    assert prettify_title("Show S01E01") == "Show S01E01"
    assert prettify_title("...") == "..."
    assert prettify_title("") == ""


@pytest.mark.skipif(not SAMPLES.is_dir(), reason="sample files not present")
def test_real_samples_parse():
    files = sorted(SAMPLES.glob("*.mkv"))
    assert files, "expected at least one sample"
    for path in files:
        info = parse_mkv(path)
        assert info.error is None
        assert info.duration_ms > 50 * 60 * 1000
        assert len(info.audio_tracks) >= 2
        assert len(info.subtitle_tracks) >= 4
        languages = {track.language for track in info.audio_tracks}
        assert {"hin", "eng"} <= languages
        assert info.title  # container title present
