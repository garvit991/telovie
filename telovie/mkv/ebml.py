"""Minimal read-only EBML primitives (Matroska's container format).

Only what the scanner needs: variable-length integers, element iteration, and
scalar decoding. Everything is bounded so a corrupt file cannot make us read
gigabytes or loop forever.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator

MAX_HEADER_BYTES = 4 * 1024 * 1024
MAX_ELEMENTS = 200_000


class EbmlError(ValueError):
    """Raised when a buffer is not valid EBML."""


@dataclass(frozen=True)
class Element:
    element_id: int
    body: bytes


def read_vint(
    data: bytes, pos: int, *, keep_marker: bool
) -> tuple[int, int, int]:
    """Read an EBML variable-length integer.

    Returns ``(value, next_pos, length)``. ``keep_marker`` keeps the length
    marker bit, which is how element IDs are stored (0x1A45DFA3); sizes drop it.
    """
    if pos < 0 or pos >= len(data):
        raise EbmlError("vint past end of buffer")
    first = data[pos]
    if first == 0:
        raise EbmlError("invalid vint leader 0x00")

    mask = 0x80
    length = 1
    while length <= 8 and not (first & mask):
        mask >>= 1
        length += 1
    if length > 8:
        raise EbmlError("invalid vint length")
    if pos + length > len(data):
        raise EbmlError("truncated vint")

    value = first if keep_marker else first & (mask - 1)
    for offset in range(1, length):
        value = (value << 8) | data[pos + offset]
    return value, pos + length, length


def vint_is_unknown(value: int, length: int) -> bool:
    """True for the all-ones size, used by streaming/unknown-length segments."""
    return value == (1 << (7 * length)) - 1


def iter_elements(
    data: bytes, start: int = 0, end: int | None = None
) -> Iterator[Element]:
    """Yield top-level elements in ``data[start:end]``.

    An element with unknown size swallows the rest of the buffer and ends
    iteration, because its children cannot be located reliably.
    """
    limit = len(data) if end is None else min(end, len(data))
    pos = start
    seen = 0
    while pos < limit:
        seen += 1
        if seen > MAX_ELEMENTS:
            raise EbmlError("too many elements")

        element_id, after_id, _ = read_vint(data, pos, keep_marker=True)
        size, body_start, size_len = read_vint(data, after_id, keep_marker=False)
        if body_start > limit:
            raise EbmlError("element header past end of buffer")

        if vint_is_unknown(size, size_len):
            body_end = limit
            unknown = True
        else:
            body_end = body_start + size
            unknown = False

        # The buffer is capped (e.g. a 1.1 GB Segment), so a declared body may
        # extend past what we read. Clamp and stop: everything we need (Info,
        # Tracks) appears before the first Cluster.
        truncated = body_end > limit
        if truncated:
            body_end = limit

        yield Element(element_id, data[body_start:body_end])
        if unknown or truncated:
            return
        pos = body_end


def read_uint(body: bytes) -> int:
    return int.from_bytes(body, "big") if body else 0


def read_float(body: bytes) -> float:
    import struct

    if len(body) == 4:
        return struct.unpack(">f", body)[0]
    if len(body) == 8:
        return struct.unpack(">d", body)[0]
    return 0.0


def read_str(body: bytes) -> str:
    return body.decode("utf-8", errors="replace").rstrip("\x00").strip()
