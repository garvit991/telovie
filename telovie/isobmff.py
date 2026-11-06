"""Read basic title, duration, and track metadata from MP4/MOV atoms."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

from telovie.mkv.parser import TrackInfo
from telovie.util.languages import normalize_code

MAX_ATOMS = 200_000
MAX_METADATA_BYTES = 64 * 1024
CONTAINER_ATOMS = {b"moov", b"udta", b"meta", b"ilst"}


class IsobmffError(ValueError):
    """Raised when an ISO Base Media File Format atom is malformed."""


@dataclass(frozen=True)
class _Atom:
    kind: bytes
    start: int
    payload_start: int
    end: int


@dataclass
class IsobmffInfo:
    title: str = ""
    duration_ms: int = 0
    tracks: list[TrackInfo] = field(default_factory=list)
    error: str | None = None

    @property
    def audio_tracks(self) -> list[TrackInfo]:
        return [track for track in self.tracks if track.kind == "audio"]

    @property
    def subtitle_tracks(self) -> list[TrackInfo]:
        return [track for track in self.tracks if track.kind == "subtitle"]


class _AtomReader:
    def __init__(self) -> None:
        self.count = 0

    def iter_atoms(self, handle, start: int, end: int) -> Iterator[_Atom]:
        position = start
        while position < end:
            self.count += 1
            if self.count > MAX_ATOMS:
                raise IsobmffError("too many atoms")
            if end - position < 8:
                raise IsobmffError("truncated atom header")

            handle.seek(position)
            header = handle.read(8)
            size = int.from_bytes(header[:4], "big")
            kind = header[4:]
            header_size = 8
            if size == 1:
                extended = handle.read(8)
                if len(extended) != 8:
                    raise IsobmffError("truncated extended atom header")
                size = int.from_bytes(extended, "big")
                header_size += 8
            elif size == 0:
                size = end - position

            if kind == b"uuid":
                header_size += 16
            if size < header_size:
                raise IsobmffError("atom size is smaller than its header")
            atom_end = position + size
            if atom_end > end:
                raise IsobmffError("atom extends past its parent")

            yield _Atom(kind, position, position + header_size, atom_end)
            position = atom_end


def parse_isobmff(path: str | Path) -> IsobmffInfo:
    """Parse metadata without reading media payloads; failures are returned."""
    info = IsobmffInfo()
    try:
        with Path(path).open("rb") as handle:
            file_size = Path(path).stat().st_size
            reader = _AtomReader()
            moov = next(
                (
                    atom
                    for atom in reader.iter_atoms(handle, 0, file_size)
                    if atom.kind == b"moov"
                ),
                None,
            )
            if moov is None:
                info.error = "moov atom not found"
                return info

            for atom in reader.iter_atoms(handle, moov.payload_start, moov.end):
                if atom.kind == b"mvhd":
                    info.duration_ms = _duration_ms(handle, atom)
                elif atom.kind == b"trak":
                    track = _parse_track(handle, reader, atom)
                    if track is not None:
                        info.tracks.append(track)
                elif atom.kind == b"udta":
                    info.title = _title_in_udta(handle, reader, atom)
    except OSError as exc:
        info.error = f"{type(exc).__name__}: {exc}"
    except IsobmffError as exc:
        info.error = str(exc)
    return info


def _read(handle, start: int, size: int, *, limit: int = MAX_METADATA_BYTES) -> bytes:
    if size < 0 or size > limit:
        raise IsobmffError("metadata atom exceeds the read limit")
    handle.seek(start)
    data = handle.read(size)
    if len(data) != size:
        raise IsobmffError("truncated metadata atom")
    return data


def _duration_ms(handle, atom: _Atom) -> int:
    payload = _read(handle, atom.payload_start, atom.end - atom.payload_start, limit=64)
    if len(payload) < 20:
        return 0
    version = payload[0]
    if version == 0:
        timescale = int.from_bytes(payload[12:16], "big")
        duration = int.from_bytes(payload[16:20], "big")
    elif version == 1 and len(payload) >= 32:
        timescale = int.from_bytes(payload[20:24], "big")
        duration = int.from_bytes(payload[24:32], "big")
    else:
        return 0
    if not timescale or duration == (1 << (32 if version == 0 else 64)) - 1:
        return 0
    return int(round(duration * 1000 / timescale))


def _title_in_udta(handle, reader: _AtomReader, atom: _Atom) -> str:
    for child in reader.iter_atoms(handle, atom.payload_start, atom.end):
        if child.kind == b"meta":
            # The meta atom starts with a FullBox version/flags field.
            if child.end - child.payload_start < 4:
                continue
            for meta_child in reader.iter_atoms(
                handle, child.payload_start + 4, child.end
            ):
                if meta_child.kind == b"ilst":
                    for item in reader.iter_atoms(
                        handle, meta_child.payload_start, meta_child.end
                    ):
                        if item.kind == b"\xa9nam":
                            title = _title_from_item(handle, reader, item)
                            if title:
                                return title
    return ""


def _title_from_item(handle, reader: _AtomReader, item: _Atom) -> str:
    for child in reader.iter_atoms(handle, item.payload_start, item.end):
        if child.kind == b"data":
            payload = _read(
                handle,
                child.payload_start,
                child.end - child.payload_start,
            )
            return payload[8:].decode("utf-8", errors="replace").rstrip("\x00").strip()
    return ""


def _parse_track(handle, reader: _AtomReader, atom: _Atom) -> TrackInfo | None:
    tkhd = None
    mdia = None
    for child in reader.iter_atoms(handle, atom.payload_start, atom.end):
        if child.kind == b"tkhd":
            tkhd = child
        elif child.kind == b"mdia":
            mdia = child
    if tkhd is None or mdia is None:
        return None

    header = _read(handle, tkhd.payload_start, tkhd.end - tkhd.payload_start, limit=64)
    if len(header) < 16:
        return None
    version = header[0]
    track_offset = 20 if version == 1 else 12
    if len(header) < track_offset + 4:
        return None
    number = int.from_bytes(header[track_offset : track_offset + 4], "big")
    flags = int.from_bytes(header[:4], "big") & 0xFFFFFF

    handler = ""
    language = "und"
    codec = ""
    for child in reader.iter_atoms(handle, mdia.payload_start, mdia.end):
        if child.kind == b"hdlr":
            payload = _read(
                handle, child.payload_start, child.end - child.payload_start, limit=64
            )
            if len(payload) >= 12:
                handler = payload[8:12].decode("ascii", errors="replace")
        elif child.kind == b"mdhd":
            language = _track_language(handle, child)
        elif child.kind == b"minf":
            codec = _codec_from_minf(handle, reader, child)

    kinds = {
        "vide": "video",
        "soun": "audio",
        "text": "subtitle",
        "sbtl": "subtitle",
        "subt": "subtitle",
        "clcp": "subtitle",
    }
    kind = kinds.get(handler)
    if kind is None:
        return None
    return TrackInfo(
        number=number,
        kind=kind,
        codec=codec,
        language=language,
        is_default=bool(flags & 1),
    )


def _track_language(handle, atom: _Atom) -> str:
    payload = _read(handle, atom.payload_start, atom.end - atom.payload_start, limit=64)
    version = payload[0] if payload else 0
    offset = 32 if version == 1 else 20
    if len(payload) < offset + 2:
        return "und"
    packed = int.from_bytes(payload[offset : offset + 2], "big") & 0x7FFF
    code = "".join(chr(((packed >> shift) & 0x1F) + 0x60) for shift in (10, 5, 0))
    return normalize_code(code) or "und"


def _codec_from_minf(handle, reader: _AtomReader, atom: _Atom) -> str:
    for child in reader.iter_atoms(handle, atom.payload_start, atom.end):
        if child.kind != b"stbl":
            continue
        for table_child in reader.iter_atoms(
            handle, child.payload_start, child.end
        ):
            if table_child.kind != b"stsd":
                continue
            header = _read(
                handle,
                table_child.payload_start,
                min(8, table_child.end - table_child.payload_start),
                limit=8,
            )
            if len(header) < 8 or int.from_bytes(header[4:8], "big") == 0:
                return ""
            sample_start = table_child.payload_start + 8
            sample_header = _read(handle, sample_start, 8, limit=8)
            sample_size = int.from_bytes(sample_header[:4], "big")
            if sample_size < 8 or sample_start + sample_size > table_child.end:
                raise IsobmffError("invalid sample entry in stsd")
            return sample_header[4:8].decode("ascii", errors="replace")
    return ""
