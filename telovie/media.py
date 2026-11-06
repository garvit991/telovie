"""Container-aware metadata parser dispatch for supported video files."""

from __future__ import annotations

from pathlib import Path

from telovie.config import ISOBMFF_SUFFIXES
from telovie.isobmff import IsobmffInfo, parse_isobmff
from telovie.mkv.parser import MkvInfo, parse_mkv


MediaInfo = MkvInfo | IsobmffInfo


def parse_media(path: str | Path) -> MediaInfo:
    """Parse metadata using EBML for Matroska/WebM and atoms for MP4/MOV."""
    suffix = Path(path).suffix.casefold()
    if suffix in ISOBMFF_SUFFIXES:
        return parse_isobmff(path)
    return parse_mkv(path)
