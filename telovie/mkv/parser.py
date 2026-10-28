"""Read title, duration and track metadata from an MKV header.

Stops at the first Cluster, so only a few kilobytes of each file are touched.
This is the scanner's metadata source and the language oracle for track menus.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from telovie.mkv.ebml import (
    MAX_HEADER_BYTES,
    EbmlError,
    iter_elements,
    read_float,
    read_str,
    read_uint,
)
from telovie.util.languages import normalize_code

ID_SEGMENT = 0x18538067
ID_INFO = 0x1549A966
ID_TRACKS = 0x1654AE6B
ID_CLUSTER = 0x1F43B675
ID_TRACKENTRY = 0xAE

INFO_TIMESTAMP_SCALE = 0x2AD7B1
INFO_DURATION = 0x4489
INFO_TITLE = 0x7BA9
INFO_MUXING_APP = 0x4D80

TRK_NUMBER = 0xD7
TRK_TYPE = 0x83
TRK_CODEC = 0x86
TRK_LANGUAGE = 0x22B59C
TRK_LANGUAGE_IETF = 0x22B59D
TRK_NAME = 0x536E
TRK_DEFAULT = 0x88
TRK_FORCED = 0x55AA

TRACK_TYPES = {1: "video", 2: "audio", 17: "subtitle", 3: "complex", 16: "logo"}


@dataclass(frozen=True)
class TrackInfo:
    number: int
    kind: str  # video | audio | subtitle | ...
    codec: str = ""
    language: str = ""  # canonical 639-2/B, "und" when untagged
    name: str = ""
    is_default: bool = False
    is_forced: bool = False


@dataclass
class MkvInfo:
    title: str = ""
    duration_ms: int = 0
    tracks: list[TrackInfo] = field(default_factory=list)
    muxing_app: str = ""
    error: str | None = None

    @property
    def audio_tracks(self) -> list[TrackInfo]:
        return [track for track in self.tracks if track.kind == "audio"]

    @property
    def subtitle_tracks(self) -> list[TrackInfo]:
        return [track for track in self.tracks if track.kind == "subtitle"]


def display_title(_raw_title: str, stem: str) -> str:
    """Use the filename for library titles; container titles may be uploader tags."""
    return prettify_title(stem)


def prettify_title(title: str) -> str:
    """Turn ``Game.Of.Thrones.S02E05`` into ``Game Of Thrones S02E05``.

    Only when the name has no spaces at all: a real title such as
    ``Dr. Strangelove`` keeps its punctuation.
    """
    if " " in title or "." not in title:
        return title
    cleaned = " ".join(part for part in title.split(".") if part)
    return cleaned or title


def parse_mkv(path: str | Path, *, max_bytes: int = MAX_HEADER_BYTES) -> MkvInfo:
    """Parse the header of an MKV. Never raises: failures land in ``error``."""
    info = MkvInfo()
    try:
        with Path(path).open("rb") as handle:
            data = handle.read(max_bytes)
    except OSError as exc:
        info.error = f"{type(exc).__name__}: {exc}"
        return info

    try:
        for element in iter_elements(data):
            if element.element_id == ID_SEGMENT:
                _parse_segment(element.body, info)
                break
    except EbmlError as exc:
        info.error = str(exc)
    return info


def _parse_segment(segment: bytes, info: MkvInfo) -> None:
    timestamp_scale = 1_000_000  # nanoseconds per tick (Matroska default)
    duration_units = 0.0

    for element in iter_elements(segment):
        if element.element_id == ID_CLUSTER:
            break
        if element.element_id == ID_INFO:
            for child in iter_elements(element.body):
                if child.element_id == INFO_TIMESTAMP_SCALE:
                    timestamp_scale = read_uint(child.body) or 1_000_000
                elif child.element_id == INFO_DURATION:
                    duration_units = read_float(child.body)
                elif child.element_id == INFO_TITLE:
                    info.title = read_str(child.body)
                elif child.element_id == INFO_MUXING_APP:
                    info.muxing_app = read_str(child.body)
        elif element.element_id == ID_TRACKS:
            info.tracks.extend(_parse_tracks(element.body))

    if duration_units > 0:
        info.duration_ms = int(round(duration_units * timestamp_scale / 1_000_000))


def _parse_tracks(tracks_body: bytes) -> list[TrackInfo]:
    tracks: list[TrackInfo] = []
    for element in iter_elements(tracks_body):
        if element.element_id == ID_TRACKENTRY:
            track = _parse_track_entry(element.body)
            if track is not None:
                tracks.append(track)
    return tracks


def _parse_track_entry(entry: bytes) -> TrackInfo | None:
    number = 0
    type_id = 0
    codec = ""
    language = ""
    language_ietf = ""
    name = ""
    is_default = False
    is_forced = False

    for element in iter_elements(entry):
        if element.element_id == TRK_NUMBER:
            number = read_uint(element.body)
        elif element.element_id == TRK_TYPE:
            type_id = read_uint(element.body)
        elif element.element_id == TRK_CODEC:
            codec = read_str(element.body)
        elif element.element_id == TRK_LANGUAGE:
            language = read_str(element.body)
        elif element.element_id == TRK_LANGUAGE_IETF:
            language_ietf = read_str(element.body)
        elif element.element_id == TRK_NAME:
            name = read_str(element.body)
        elif element.element_id == TRK_DEFAULT:
            is_default = bool(read_uint(element.body))
        elif element.element_id == TRK_FORCED:
            is_forced = bool(read_uint(element.body))

    if type_id == 0:
        return None

    canonical = normalize_code(language_ietf or language) or "und"
    return TrackInfo(
        number=number,
        kind=TRACK_TYPES.get(type_id, f"type{type_id}"),
        codec=codec,
        language=canonical,
        name=name,
        is_default=is_default,
        is_forced=is_forced,
    )
