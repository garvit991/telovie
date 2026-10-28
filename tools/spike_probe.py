"""Phase 0 diagnostic probe — throwaway code, not part of the app.

Answers the questions that decide the architecture:

  1. Does the FFmpeg backend load these MKVs, and what does Qt report?
  2. Are per-track languages real ISO codes, or QLocale::Undetermined?
  3. Do Qt's track indices line up with the MKV TrackNumber order?
  4. Does setActiveAudioTrack / setActiveSubtitleTrack take effect?
  5. Does a seek issued while paused stick, and does playback advance?

Run:  .venv\\Scripts\\python.exe tools\\spike_probe.py
Out:  console report + tools/probe_report.json
"""

from __future__ import annotations

import json
import os
import struct
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_MEDIA_BACKEND", "ffmpeg")

from PySide6.QtCore import QEventLoop, QLocale, QTimer, QUrl  # noqa: E402
from PySide6.QtMultimedia import (  # noqa: E402
    QAudioOutput,
    QMediaMetaData,
    QMediaPlayer,
)
from PySide6.QtWidgets import QApplication  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "sample files"

# --------------------------------------------------------------------------- #
# Minimal EBML reader (header only, stops at the first Cluster)
# --------------------------------------------------------------------------- #

ID_EBML = 0x1A45DFA3
ID_SEGMENT = 0x18538067
ID_INFO = 0x1549A966
ID_TRACKS = 0x1654AE6B
ID_CLUSTER = 0x1F43B675
ID_TRACKENTRY = 0xAE

INFO_TIMESTAMP_SCALE = 0x2AD7B1
INFO_DURATION = 0x4489
INFO_TITLE = 0x7BA9
INFO_MUXING_APP = 0x4D80
INFO_WRITING_APP = 0x5741

TRK_NUMBER = 0xD7
TRK_TYPE = 0x83
TRK_CODEC = 0x86
TRK_LANGUAGE = 0x22B59C
TRK_LANGUAGE_IETF = 0x22B59D
TRK_NAME = 0x536E
TRK_DEFAULT = 0x88
TRK_FORCED = 0x55AA
TRK_DEFAULT_DURATION = 0x23E383

TRACK_TYPES = {1: "video", 2: "audio", 17: "subtitle", 3: "complex", 16: "logo"}

HEADER_CAP = 8 * 1024 * 1024


def read_vint(buf: bytes, pos: int, keep_marker: bool) -> tuple[int, int]:
    """Read an EBML variable-length integer. Returns (value, next_pos)."""
    if pos >= len(buf):
        raise ValueError("vint past end of buffer")
    first = buf[pos]
    if first == 0:
        raise ValueError("invalid vint leader 0x00")
    mask = 0x80
    length = 1
    while length <= 8 and not (first & mask):
        mask >>= 1
        length += 1
    if length > 8 or pos + length > len(buf):
        raise ValueError("truncated vint")
    value = first if keep_marker else first & (mask - 1)
    for i in range(1, length):
        value = (value << 8) | buf[pos + i]
    return value, pos + length


def vint_is_unknown(value: int, length: int) -> bool:
    return value == (1 << (7 * length)) - 1


def read_uint(buf: bytes) -> int:
    return int.from_bytes(buf, "big") if buf else 0


def read_float(buf: bytes) -> float:
    if len(buf) == 4:
        return struct.unpack(">f", buf)[0]
    if len(buf) == 8:
        return struct.unpack(">d", buf)[0]
    return 0.0


def read_str(buf: bytes) -> str:
    return buf.decode("utf-8", errors="replace").rstrip("\x00").strip()


def parse_info(buf: bytes) -> dict:
    info: dict = {"timestamp_scale": 1_000_000}
    pos = 0
    while pos < len(buf):
        try:
            eid, pos = read_vint(buf, pos, True)
            size, pos = read_vint(buf, pos, False)
        except ValueError:
            break
        body = buf[pos : pos + size]
        if eid == INFO_TIMESTAMP_SCALE:
            info["timestamp_scale"] = read_uint(body) or 1_000_000
        elif eid == INFO_DURATION:
            info["duration_units"] = read_float(body)
        elif eid == INFO_TITLE:
            info["title"] = read_str(body)
        elif eid == INFO_MUXING_APP:
            info["muxing_app"] = read_str(body)
        elif eid == INFO_WRITING_APP:
            info["writing_app"] = read_str(body)
        pos += size
    units = info.get("duration_units")
    if units:
        info["duration_ms"] = round(units * info["timestamp_scale"] / 1_000_000)
    return info


def parse_track_entry(buf: bytes) -> dict:
    track: dict = {"default": False, "forced": False}
    pos = 0
    while pos < len(buf):
        try:
            eid, pos = read_vint(buf, pos, True)
            size, pos = read_vint(buf, pos, False)
        except ValueError:
            break
        body = buf[pos : pos + size]
        if eid == TRK_NUMBER:
            track["number"] = read_uint(body)
        elif eid == TRK_TYPE:
            track["type_id"] = read_uint(body)
            track["type"] = TRACK_TYPES.get(track["type_id"], str(track["type_id"]))
        elif eid == TRK_CODEC:
            track["codec"] = read_str(body)
        elif eid == TRK_LANGUAGE:
            track["language"] = read_str(body)
        elif eid == TRK_LANGUAGE_IETF:
            track["language_ietf"] = read_str(body)
        elif eid == TRK_NAME:
            track["name"] = read_str(body)
        elif eid == TRK_DEFAULT:
            track["default"] = bool(read_uint(body))
        elif eid == TRK_FORCED:
            track["forced"] = bool(read_uint(body))
        elif eid == TRK_DEFAULT_DURATION:
            track["default_duration_ns"] = read_uint(body)
        pos += size
    return track


def parse_tracks(buf: bytes) -> list[dict]:
    tracks: list[dict] = []
    pos = 0
    while pos < len(buf):
        try:
            eid, pos = read_vint(buf, pos, True)
            size, pos = read_vint(buf, pos, False)
        except ValueError:
            break
        if eid == ID_TRACKENTRY:
            tracks.append(parse_track_entry(buf[pos : pos + size]))
        pos += size
    return tracks


def parse_mkv_header(path: Path, cap: int = HEADER_CAP) -> dict:
    with path.open("rb") as handle:
        data = handle.read(cap)

    result: dict = {"bytes_read": len(data), "tracks": []}
    pos = 0
    try:
        eid, pos = read_vint(data, pos, True)
        if eid != ID_EBML:
            raise ValueError("not an EBML file")
        size, pos = read_vint(data, pos, False)
        pos += size

        eid, pos = read_vint(data, pos, True)
        if eid != ID_SEGMENT:
            raise ValueError("no Segment element")
        size, next_pos = read_vint(data, pos, False)
        size_len = next_pos - pos
        pos = next_pos
        seg_end = len(data) if vint_is_unknown(size, size_len) else min(len(data), pos + size)

        while pos < seg_end:
            try:
                eid, body_pos = read_vint(data, pos, True)
                size, body_start = read_vint(data, body_pos, False)
                size_len = body_start - body_pos
            except ValueError:
                break
            if vint_is_unknown(size, size_len):
                body_end = seg_end
            else:
                body_end = body_start + size
            if eid == ID_CLUSTER:
                result["stopped_at_cluster"] = True
                break
            if body_end > len(data):
                result["truncated"] = True
                break
            chunk = data[body_start:body_end]
            if eid == ID_INFO:
                result.update(parse_info(chunk))
            elif eid == ID_TRACKS:
                result["tracks"] = parse_tracks(chunk)
            pos = body_end
    except Exception as exc:  # noqa: BLE001 - diagnostic tool
        result["parse_error"] = f"{type(exc).__name__}: {exc}"
    return result


# --------------------------------------------------------------------------- #
# Qt probe
# --------------------------------------------------------------------------- #


def settle(ms: int) -> None:
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def enum_name(value) -> str:
    return getattr(value, "name", str(value))


def describe_language(raw) -> dict:
    info = {"raw": repr(raw), "type": type(raw).__name__}
    lang = None
    if isinstance(raw, QLocale.Language):
        lang = raw
    elif isinstance(raw, int):
        try:
            lang = QLocale.Language(raw)
        except ValueError:
            return info
    if lang is None:
        return info
    info["enum"] = enum_name(lang)
    try:
        info["locale"] = QLocale(lang).name()
    except Exception:  # noqa: BLE001
        pass
    for attr in ("languageToCode",):
        fn = getattr(QLocale, attr, None)
        if fn is not None:
            try:
                info["code"] = fn(lang)
            except Exception as exc:  # noqa: BLE001
                info["code_error"] = f"{type(exc).__name__}: {exc}"
    return info


def metadata_dict(md: QMediaMetaData) -> dict:
    out: dict = {}
    try:
        keys = md.keys()
    except Exception:  # noqa: BLE001
        return {"error": "keys() unavailable"}
    for key in keys:
        name = enum_name(key)
        entry: dict = {}
        try:
            entry["value"] = repr(md.value(key))
        except Exception:  # noqa: BLE001
            pass
        try:
            entry["string"] = md.stringValue(key)
        except Exception:  # noqa: BLE001
            pass
        out[name] = entry
    return out


def track_list(tracks, kind: str) -> list[dict]:
    rows = []
    for index, md in enumerate(tracks):
        row = {"index": index, "kind": kind}
        for key, label in (
            (QMediaMetaData.Key.Title, "title"),
            (QMediaMetaData.Key.Language, "language"),
            (QMediaMetaData.Key.AudioBitRate, "audio_bitrate"),
            (QMediaMetaData.Key.VideoBitRate, "video_bitrate"),
        ):
            try:
                value = md.value(key)
            except Exception:  # noqa: BLE001
                continue
            if value in (None, ""):
                continue
            row[label] = describe_language(value) if label == "language" else repr(value)
        try:
            row["string"] = md.stringValue(QMediaMetaData.Key.Title)
        except Exception:  # noqa: BLE001
            pass
        rows.append(row)
    return rows


def wait_for_status(player: QMediaPlayer, statuses: set, timeout_ms: int) -> bool:
    loop = QEventLoop()
    state = {"ok": False}

    def check(*_args) -> None:
        if player.mediaStatus() in statuses:
            state["ok"] = True
            loop.quit()

    player.mediaStatusChanged.connect(check)
    timer = QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(loop.quit)
    timer.start(timeout_ms)
    check()
    if not state["ok"]:
        loop.exec()
    timer.stop()
    try:
        player.mediaStatusChanged.disconnect(check)
    except Exception:  # noqa: BLE001
        pass
    return state["ok"]


def probe_file(app: QApplication, path: Path) -> dict:
    result: dict = {"file": path.name, "size_mb": round(path.stat().st_size / 1048576, 1)}
    result["ebml"] = parse_mkv_header(path)

    player = QMediaPlayer()
    audio_out = QAudioOutput()
    audio_out.setVolume(0.0)  # silent probe
    player.setAudioOutput(audio_out)

    events: list[str] = []
    player.mediaStatusChanged.connect(lambda s: events.append(f"status:{enum_name(s)}"))
    player.errorOccurred.connect(
        lambda err, msg: events.append(f"error:{enum_name(err)}:{msg}")
    )

    started = time.perf_counter()
    player.setSource(QUrl.fromLocalFile(str(path)))
    loaded = wait_for_status(
        player,
        {
            QMediaPlayer.MediaStatus.LoadedMedia,
            QMediaPlayer.MediaStatus.BufferedMedia,
            QMediaPlayer.MediaStatus.InvalidMedia,
        },
        30_000,
    )
    result["load_ok"] = loaded
    result["load_ms"] = round((time.perf_counter() - started) * 1000)
    settle(400)  # let track lists populate

    result["status"] = enum_name(player.mediaStatus())
    result["error_string"] = player.errorString()
    result["duration_ms"] = player.duration()
    result["seekable"] = player.isSeekable()
    result["has_audio"] = player.hasAudio()
    result["has_video"] = player.hasVideo()
    result["qt_audio_tracks"] = track_list(player.audioTracks(), "audio")
    result["qt_subtitle_tracks"] = track_list(player.subtitleTracks(), "subtitle")
    result["qt_video_tracks"] = track_list(player.videoTracks(), "video")
    result["active_audio_default"] = player.activeAudioTrack()
    result["active_subtitle_default"] = player.activeSubtitleTrack()
    result["metadata"] = metadata_dict(player.metaData())

    # --- switch audio to the last track ---
    audio_count = len(result["qt_audio_tracks"])
    if audio_count > 1:
        player.setActiveAudioTrack(audio_count - 1)
        settle(300)
        result["audio_switch_requested"] = audio_count - 1
        result["active_audio_after_switch"] = player.activeAudioTrack()

    # --- enable first subtitle track ---
    sub_count = len(result["qt_subtitle_tracks"])
    if sub_count:
        player.setActiveSubtitleTrack(0)
        settle(300)
        result["subtitle_switch_requested"] = 0
        result["active_subtitle_after_switch"] = player.activeSubtitleTrack()

    # --- seek while paused ---
    player.setPosition(60_000)
    settle(800)
    result["position_after_paused_seek"] = player.position()

    # --- play briefly ---
    player.play()
    settle(2_500)
    result["position_after_play"] = player.position()
    result["playback_state"] = enum_name(player.playbackState())
    result["active_audio_during_play"] = player.activeAudioTrack()
    result["active_subtitle_during_play"] = player.activeSubtitleTrack()
    result["error_string_after_play"] = player.errorString()

    player.stop()
    player.setSource(QUrl())
    settle(150)
    player.deleteLater()
    audio_out.deleteLater()
    app.processEvents()
    settle(300)

    result["events"] = events[-12:]
    return result


# --------------------------------------------------------------------------- #
# Report
# --------------------------------------------------------------------------- #


def fmt_lang(entry) -> str:
    if not isinstance(entry, dict):
        return str(entry)
    code = entry.get("code") or entry.get("locale") or entry.get("enum") or "?"
    raw = entry.get("raw", "")
    return f"{code} (raw={raw}, {entry.get('type', '')})"


def print_report(results: list[dict]) -> None:
    for res in results:
        print("=" * 78)
        print(f"{res['file']}  ({res['size_mb']} MB)")
        print("=" * 78)
        ebml = res["ebml"]
        print(f"EBML     title={ebml.get('title')!r}")
        print(
            f"         duration={ebml.get('duration_ms')} ms  "
            f"muxer={ebml.get('muxing_app')!r}  tracks={len(ebml.get('tracks', []))}"
        )
        for t in ebml.get("tracks", []):
            print(
                f"         #{t.get('number')} {t.get('type'):8} "
                f"lang={t.get('language')!r}/{t.get('language_ietf')!r} "
                f"name={t.get('name')!r} codec={t.get('codec')!r} "
                f"default={t.get('default')} forced={t.get('forced')}"
            )
        if ebml.get("parse_error"):
            print(f"         PARSE ERROR: {ebml['parse_error']}")

        print(
            f"Qt       loaded={res['load_ok']} in {res['load_ms']} ms  "
            f"status={res['status']}  duration={res['duration_ms']} ms  "
            f"seekable={res['seekable']} audio={res['has_audio']} video={res['has_video']}"
        )
        if res["error_string"]:
            print(f"         errorString={res['error_string']!r}")

        for kind in ("qt_audio_tracks", "qt_subtitle_tracks", "qt_video_tracks"):
            rows = res[kind]
            print(f"         {kind}: {len(rows)}")
            for row in rows:
                lang = row.get("language")
                lang_txt = fmt_lang(lang) if lang else "-"
                print(
                    f"           [{row['index']}] lang={lang_txt} "
                    f"title={row.get('string')!r}"
                )

        print(
            f"         active audio: default={res['active_audio_default']} "
            f"after switch={res.get('active_audio_after_switch')} "
            f"during play={res.get('active_audio_during_play')}"
        )
        print(
            f"         active subs : default={res['active_subtitle_default']} "
            f"after switch={res.get('active_subtitle_after_switch')} "
            f"during play={res.get('active_subtitle_during_play')}"
        )
        print(
            f"         seek(60s) paused -> {res.get('position_after_paused_seek')} ms; "
            f"after 2.5s play -> {res.get('position_after_play')} ms; "
            f"state={res.get('playback_state')}"
        )

        ebml_tracks = ebml.get("tracks", [])
        ebml_audio = [t for t in ebml_tracks if t.get("type") == "audio"]
        ebml_subs = [t for t in ebml_tracks if t.get("type") == "subtitle"]
        print(
            f"         parity: audio ebml={len(ebml_audio)} qt={len(res['qt_audio_tracks'])} | "
            f"subs ebml={len(ebml_subs)} qt={len(res['qt_subtitle_tracks'])}"
        )
        for i, t in enumerate(ebml_audio):
            qt_lang = res["qt_audio_tracks"][i].get("language") if i < len(res["qt_audio_tracks"]) else None
            print(
                f"           audio[{i}] ebml={t.get('language')!r} "
                f"-> qt={fmt_lang(qt_lang) if qt_lang else 'missing'}"
            )
        print()

    print("=" * 78)
    print("VERDICT")
    print("=" * 78)
    for res in results:
        langs = [
            row.get("language", {}).get("code")
            for row in res["qt_audio_tracks"] + res["qt_subtitle_tracks"]
            if isinstance(row.get("language"), dict)
        ]
        usable = [code for code in langs if code and code not in ("", "und", "Undetermined")]
        print(
            f"{res['file'][:52]:52} load={'Y' if res['load_ok'] else 'N'} "
            f"langs={len(usable)}/{len(langs)} usable  "
            f"audio_switch={'Y' if res.get('active_audio_after_switch') not in (None, res['active_audio_default']) or len(res['qt_audio_tracks']) < 2 else 'N'}  "
            f"seek={'Y' if (res.get('position_after_play') or 0) > 55_000 else 'N'}"
        )


def main() -> int:
    paths = [Path(arg) for arg in sys.argv[1:]]
    if not paths:
        paths = sorted(SAMPLES.glob("*.mkv"))
    if not paths:
        print(f"No .mkv files found in {SAMPLES}", file=sys.stderr)
        return 2

    app = QApplication.instance() or QApplication(sys.argv[:1])
    results = []
    for path in paths:
        print(f"\n>>> probing {path.name} ...")
        results.append(probe_file(app, path))

    print_report(results)

    out = ROOT / "tools" / "probe_report.json"
    out.write_text(
        json.dumps(
            {
                "backend": os.environ.get("QT_MEDIA_BACKEND"),
                "qt": __import__("PySide6.QtCore", fromlist=["qVersion"]).qVersion(),
                "files": results,
            },
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )
    print(f"\nJSON report: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
