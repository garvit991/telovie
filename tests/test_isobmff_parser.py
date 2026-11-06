from __future__ import annotations

from pathlib import Path

from telovie.isobmff import parse_isobmff
from telovie.media import parse_media


def _atom(kind: bytes, payload: bytes) -> bytes:
    return (len(payload) + 8).to_bytes(4, "big") + kind + payload


def _container(kind: bytes, *children: bytes) -> bytes:
    return _atom(kind, b"".join(children))


def _track(track_id: int, handler: bytes, codec: bytes, language: str = "eng") -> bytes:
    flags = (1).to_bytes(4, "big")
    tkhd = _atom(
        b"tkhd",
        flags
        + b"\x00" * 8
        + track_id.to_bytes(4, "big")
        + b"\x00" * 8,
    )
    packed_language = sum(
        (ord(char) - 0x60) << shift
        for char, shift in zip(language, (10, 5, 0))
    )
    mdhd = _atom(
        b"mdhd",
        b"\x00" * 20 + packed_language.to_bytes(2, "big") + b"\x00\x00",
    )
    hdlr = _atom(b"hdlr", b"\x00" * 4 + b"\x00" * 4 + handler + b"\x00" * 12)
    sample_entry = _atom(codec, b"")
    stsd = _atom(b"stsd", b"\x00" * 4 + (1).to_bytes(4, "big") + sample_entry)
    media_info = _container(b"minf", _container(b"stbl", stsd))
    return _container(b"trak", tkhd, _container(b"mdia", mdhd, hdlr, media_info))


def _movie(title: str = "Atom title") -> bytes:
    mvhd = _atom(
        b"mvhd",
        b"\x00" * 12 + (1000).to_bytes(4, "big") + (92_500).to_bytes(4, "big"),
    )
    data = _atom(b"data", b"\x00" * 8 + title.encode("utf-8"))
    title_item = _atom(b"\xa9nam", data)
    ilst = _container(b"ilst", title_item)
    meta = _atom(b"meta", b"\x00" * 4 + ilst)
    udta = _container(b"udta", meta)
    moov = _container(
        b"moov",
        mvhd,
        _track(1, b"vide", b"avc1"),
        _track(2, b"soun", b"mp4a"),
        _track(3, b"sbtl", b"tx3g"),
        udta,
    )
    # A media-data atom verifies that the parser skips payloads instead of reading them.
    return _atom(b"ftyp", b"isom\x00\x00\x00\x00isom") + moov + _atom(b"mdat", b"x" * 4096)


def test_parse_mp4_title_duration_and_tracks(tmp_path: Path):
    path = tmp_path / "sample.mp4"
    path.write_bytes(_movie())

    info = parse_isobmff(path)

    assert info.error is None
    assert info.title == "Atom title"
    assert info.duration_ms == 92_500
    assert [(track.kind, track.codec) for track in info.tracks] == [
        ("video", "avc1"),
        ("audio", "mp4a"),
        ("subtitle", "tx3g"),
    ]
    assert info.audio_tracks[0].language == "eng"
    assert info.audio_tracks[0].is_default
    assert parse_media(path).duration_ms == 92_500


def test_parse_mov_and_report_malformed_atoms(tmp_path: Path):
    path = tmp_path / "sample.MOV"
    path.write_bytes(_movie())
    assert parse_media(path).title == "Atom title"

    path.write_bytes(b"\x00\x00\x00\x20moov")
    info = parse_isobmff(path)
    assert info.error is not None
    assert info.duration_ms == 0
    assert info.tracks == []
