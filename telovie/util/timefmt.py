"""Time formatting helpers (milliseconds <-> display strings)."""

from __future__ import annotations


def format_ms(ms: int | None) -> str:
    """Format milliseconds as M:SS, or H:MM:SS past one hour."""
    if ms is None or ms < 0:
        ms = 0
    total_seconds = int(ms // 1000)
    hours, rem = divmod(total_seconds, 3600)
    minutes, seconds = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


def format_remaining(position_ms: int, duration_ms: int) -> str:
    """Format the remaining time as -M:SS."""
    remaining = max(0, int(duration_ms) - int(position_ms))
    return f"-{format_ms(remaining)}"


def clamp_position(position_ms: int, duration_ms: int) -> int:
    """Clamp a position into [0, duration] (duration 0 means unknown)."""
    position = max(0, int(position_ms))
    if duration_ms and duration_ms > 0:
        return min(position, int(duration_ms))
    return position
