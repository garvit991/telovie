from __future__ import annotations

from dataclasses import dataclass, field

from telovie.mkv.parser import TrackInfo

__all__ = ["MediaItem", "ScanSummary", "TrackInfo"]


@dataclass(frozen=True)
class MediaItem:
    """A row produced by the scanner and written to MediaLibrary."""

    title: str
    file_path: str
    duration_ms: int = 0
    file_size: int = 0
    file_mtime: float = 0.0


@dataclass
class ScanSummary:
    total: int = 0
    parsed: int = 0
    unchanged: int = 0
    errors: int = 0
    missing: int = 0
    cancelled: bool = False
    seen: list[str] = field(default_factory=list)

    @property
    def indexed(self) -> int:
        return self.parsed

    def describe(self) -> str:
        if self.cancelled:
            return "Scan cancelled"
        parts = [f"{self.total} file{'s' if self.total != 1 else ''}"]
        if self.parsed:
            parts.append(f"{self.parsed} new or changed")
        if self.unchanged:
            parts.append(f"{self.unchanged} unchanged")
        if self.missing:
            parts.append(f"{self.missing} missing")
        if self.errors:
            parts.append(f"{self.errors} unreadable")
        return " · ".join(parts)
