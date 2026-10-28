from __future__ import annotations

from pathlib import Path

from telovie.library.models import ScanSummary
from telovie.library.scanner import collect_mkv_files


def _touch(path: Path, content: bytes = b"x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def test_collect_is_recursive_and_case_insensitive(tmp_path: Path):
    _touch(tmp_path / "Show A" / "Season 1" / "e01.mkv")
    _touch(tmp_path / "Show A" / "Season 1" / "e02.MKV")
    _touch(tmp_path / "Show B" / "movie.mkv")
    _touch(tmp_path / "Show B" / "notes.txt")
    _touch(tmp_path / "Show B" / "poster.jpg")

    found = collect_mkv_files(tmp_path)
    names = sorted(path.name for path in found)
    assert names == ["e01.mkv", "e02.MKV", "movie.mkv"]


def test_collect_skips_system_and_hidden_folders(tmp_path: Path):
    _touch(tmp_path / "ok.mkv")
    _touch(tmp_path / ".hidden" / "secret.mkv")
    _touch(tmp_path / "System Volume Information" / "x.mkv")
    _touch(tmp_path / "$RECYCLE.BIN" / "y.mkv")

    found = collect_mkv_files(tmp_path)
    assert [path.name for path in found] == ["ok.mkv"]


def test_collect_missing_root_returns_empty(tmp_path: Path):
    assert collect_mkv_files(tmp_path / "does-not-exist") == []


def test_collect_handles_spaces_and_unicode(tmp_path: Path):
    _touch(tmp_path / "Game of Thrones" / "S02E05 — The Ghost.mkv")
    found = collect_mkv_files(tmp_path)
    assert len(found) == 1
    assert "S02E05" in found[0].name


def test_scan_summary_description():
    summary = ScanSummary(total=10, parsed=3, unchanged=6, errors=1, missing=2)
    text = summary.describe()
    assert "10 files" in text
    assert "3 new or changed" in text
    assert "6 unchanged" in text
    assert "2 missing" in text
    assert "1 unreadable" in text

    assert ScanSummary(total=1, cancelled=True).describe() == "Scan cancelled"
