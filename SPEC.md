# Telovie — Local MKV Library & Player

**Status:** Draft for approval · **Target OS:** Windows 11 · **Last updated:** 2026-10-28

A single-user desktop app that indexes a folder of `.mkv` files, presents a Continue Watching home section and a nested show/season collection browser, plays files in-app with the Qt multimedia stack, remembers where you stopped, and auto-selects your preferred audio/subtitle languages.

---

## 1. Locked decisions (from interview)

| # | Decision | Choice |
|---|---|---|
| D1 | Media backend | **Qt FFmpeg backend** (PySide6 default on Windows). Not Media Foundation. |
| D2 | Language preference | **Ordered fallback list**, e.g. `jpn,eng` — first available match wins. |
| D3 | Resume behavior | **Silent auto-seek** + brief non-blocking "Resumed from 12:34" toast. |
| D4 | Library cards | **Placeholder cards** (no thumbnail extraction). Gradient + monogram + duration + progress. |
| D5 | Library root | **Fixed folder** `%USERPROFILE%\Videos\Telovie`, auto-created. No folder picker. Recursive scan on startup, automatic refresh when files settle, plus a manual refresh (F5, or the ⋯ menu). |
| D6 | Library layout | **Continue Watching + Collection** home sections — browse collection folders in the same nested show/season structure as storage. |
| D7 | Track memory | **Per-file memory is primary.** Whatever audio/caption track you last chose for a video is restored next time ("Audio 2", "Caption 1"). Language preferences are only a fallback for never-played files. |

### Why not Media Foundation

Qt 6.10 deprecated the Windows Media Foundation backend; it is slated for removal in the next major Qt. The FFmpeg backend is the default on Windows, ships **inside the PySide6 wheel** (no VLC, no separate FFmpeg install, no PATH dependency), and is the only backend with usable `setActiveAudioTrack()` / `setActiveSubtitleTrack()` support for MKV. `QT_MEDIA_BACKEND` will be pinned to `ffmpeg` at startup so behavior is deterministic.

---

## 2. Environment facts (verified)

- Workspace is empty; nothing to preserve.
- Python **3.15.1** (default) and 3.11 available. PySide6 **6.12.0** supports `>=3.10,<3.16` → use 3.15.1 in a project-local venv.
- No `ffprobe` / `ffmpeg` / `mkvmerge` / `mpv` on PATH. All metadata must come from Qt or our own MKV header reader.
- App data will live in `%LOCALAPPDATA%\Telovie\` (`library.db`, `logs\`). Overridable via `TELOVIE_DATA_DIR`.

### 2.1 Phase 0 probe results (verified against your two samples)

Both files: 1080p H.264, **Hindi AC-3 + English HE-AAC**, English/Spanish SRT subs, ~54 min, ~1.14 GB.

| Check | Result |
|---|---|
| FFmpeg backend loads | Yes, **13–29 ms** to `LoadedMedia` |
| Duration parity (EBML vs Qt) | Exact: `3,250,347 ms` and `3,239,552 ms` |
| Track counts (EBML vs Qt) | Exact: audio `2/2`, subs `5/5` and `4/4` |
| Language reporting | **Reliable**: `hi`, `en`, `es` (not `Undetermined`) |
| Track index order | **Matches MKV `TrackNumber` order** for both types |
| `setActiveAudioTrack()` | Works before and during playback, keeps playing |
| `setActiveSubtitleTrack()` | Works; `-1` disables; subs default to off in these files |
| Seek while paused, then play | Works; ~1.5 s to first frame after a seek |
| Seek **after** play starts | Rejected — UI shows `0` for ~3 s, then jumps |
| FFmpeg noise | Backend dumps stream info to stderr; suppressed for GUI builds |

Consequences baked into the plan: scan with our EBML reader (no decoder spin-up, gives exact track metadata for the menus), resume by seeking **while paused** right after `LoadedMedia`, and persist track choices per file. The language-matching fallback stays, but it is no longer on the critical path.


---

## 3. Architecture

### 3.1 Layer map

```
run.py / __main__.py
   └── telovie.app ................ QApplication, logging, theme, backend pin
        └── ui.main_window ........ QStackedWidget: Library ⇄ Player
             ├── ui.library_view .. home sections, nested collection browser, search, sort, rescan
             ├── ui.player_view ... QVideoWidget + control bar
             └── ui.preferences_dialog
   ├── playback.controller ....... QMediaPlayer wrapper, 5 s save timer, resume
   ├── playback.tracks ........... language normalization + track matching
   ├── library.scanner ........... QThread worker: walk + parse, emits batches
   ├── mkv.parser ................ EBML/MKV header reader (title, duration, tracks)
   └── db.repository ............. SQLite access (main thread only)
```

**Threading rule:** `QMediaPlayer`, `QVideoWidget`, and every SQLite write run on the GUI thread. The scanner thread performs **only** file I/O + EBML parsing and emits plain dataclasses; the GUI thread persists them. One SQLite connection, WAL mode, `foreign_keys=ON`.

### 3.2 Metadata strategy (important)

Qt exposes per-track info via `QMediaPlayer.audioTracks()` / `subtitleTracks()` as `QMediaMetaData` entries, but `Language` is a `QLocale::Language` **enum**, not an ISO string — it can collapse to `Undetermined` or lose regional variants. It is also only populated after `mediaStatus == LoadedMedia`, which is too slow for scanning hundreds of files.

Therefore:

1. **Scan time** — our own read-only EBML parser reads `Segment/Info/Title`, `Segment/Info/Duration × TimestampScale`, and each `TrackEntry` (`TrackNumber`, `TrackType`, `Language`, `Name`, `CodecID`, `FlagDefault`, `FlagForced`). Bounded read: stop at the first `Cluster`, hard cap 8 MB. This gives instant scans and exact ISO 639-2 tags.
2. **Play time** — Qt's track lists drive `setActiveAudioTrack()` / `setActiveSubtitleTrack()`; our parsed track list is the **language oracle** used to resolve the right Qt index, matched by ordinal position within each track type and cross-checked against Qt's own language when Qt reports one.
3. **Fallback** — if the EBML parse fails (corrupt/truncated file), we fall back to Qt's `QMediaMetaData` at load time, and to filename-as-title with unknown duration. Nothing crashes; the card still opens.

Phase 0 validates this mapping against real files before any UI is built.

### 3.3 Playback pipeline

`QMediaPlayer` → `QAudioOutput` (volume 0–1, persisted) → `QVideoWidget`. Controls sit in a bar **below** the video (not an overlay) for the MVP; fullscreen hides the bar and reveals it on mouse movement. Seek slider shows `bufferedTimeRange` as a secondary tint.

---

## 4. Project structure (exact files)

`P#` = phase that creates the file.

```
Telovie/
├─ SPEC.md                          now      this document
├─ README.md                        P0       setup, run, troubleshooting
├─ requirements.txt                 P0       PySide6==6.12.0, pytest
├─ pyproject.toml                   P0       metadata + pytest config
├─ .gitignore                       P0       .venv, __pycache__, *.db, build/
├─ run.py                           P0       entry point; pins QT_MEDIA_BACKEND=ffmpeg
├─ tools/
│  └─ spike_probe.py                P0       throwaway diagnostic (tracks/language/seek probe)
├─ telovie/
│  ├─ __init__.py                   P0       __version__
│  ├─ __main__.py                   P0       python -m telovie
│  ├─ app.py                        P1       bootstrap, logging, theme, MainWindow wiring
│  ├─ config.py                     P1       AppPaths, defaults, env overrides
│  ├─ db/
│  │  ├─ __init__.py                P1
│  │  ├─ schema.py                  P1       DDL + PRAGMA user_version migrations
│  │  └─ repository.py              P1       LibraryRepo, PlaybackRepo, PrefsRepo
│  ├─ mkv/
│  │  ├─ __init__.py                P2
│  │  ├─ ebml.py                    P2       vint/element reader with size caps
│  │  └─ parser.py                  P2       title, duration, TrackInfo list
│  ├─ library/
│  │  ├─ __init__.py                P2
│  │  ├─ models.py                  P2       MediaItem, ScanSummary dataclasses
│  │  ├─ scanner.py                 P2       QThread: recursive walk, parse, emit batches
│  │  └─ watcher.py                 P2       poll size/mtime, debounce, emit changed
│  ├─ playback/
│  │  ├─ __init__.py                P4
│  │  ├─ controller.py              P4/P5    QMediaPlayer wrapper, timers, save, resume
│  │  └─ tracks.py                  P6       language normalization + matching
│  ├─ ui/
│  │  ├─ __init__.py                P3
│  │  ├─ theme.py                   P3       dark QSS tokens, palette
│  │  ├─ main_window.py             P3       stacked shell, top bar, rescan
│  │  ├─ library_view.py            P3       home sections, folder browser, filtering, sorting
│  │  ├─ media_card.py              P3       placeholder card widget
│  │  ├─ player_view.py             P4       video surface, back, track menus
│  │  ├─ controls.py                P4       play/pause, seek, time, volume
│  │  ├─ toast.py                   P5       "Resumed from …" overlay
│  │  └─ preferences_dialog.py      P6       language lists, volume
│  └─ util/
│     ├─ __init__.py                P1
│     ├─ languages.py               P1       ISO 639-1/2 ↔ QLocale, display names
│     └─ timefmt.py                 P1       ms → H:MM:SS
├─ tests/
│  ├─ test_schema.py                P1
│  ├─ test_repository.py            P1
│  ├─ test_languages.py             P1
│  ├─ test_ebml_parser.py           P2       synthetic byte fixtures, no media needed
│  ├─ test_scanner.py               P2
│  ├─ test_resume_rules.py          P5       pure rule functions
│  └─ test_track_match.py           P6
└─ packaging/
   ├─ telovie.spec                  P8       PyInstaller one-folder
   └─ build.ps1                     P8
```

No file is created before its phase is approved.

---

## 5. Database schema

Single-row preferences table, matching the requested column names, extended with the few settings the UI needs. Migrations via `PRAGMA user_version` (current = **1**).

```sql
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE MediaLibrary (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    Title         TEXT    NOT NULL,
    FilePath      TEXT    NOT NULL COLLATE NOCASE UNIQUE,
    TotalDuration INTEGER NOT NULL DEFAULT 0,   -- milliseconds
    FileSize      INTEGER NOT NULL DEFAULT 0,   -- bytes
    FileMTime     REAL    NOT NULL DEFAULT 0,   -- epoch seconds
    IsAvailable   INTEGER NOT NULL DEFAULT 1 CHECK (IsAvailable IN (0,1)),
    AddedAt       TEXT    NOT NULL DEFAULT (datetime('now')),
    LastSeenAt    TEXT
);

CREATE INDEX idx_media_title ON MediaLibrary(Title COLLATE NOCASE);

CREATE TABLE PlaybackState (
    MediaID           INTEGER PRIMARY KEY
                      REFERENCES MediaLibrary(id) ON DELETE CASCADE,
    LastPosition      INTEGER NOT NULL DEFAULT 0,    -- milliseconds
    IsCompleted       INTEGER NOT NULL DEFAULT 0 CHECK (IsCompleted IN (0,1)),
    AudioTrackIndex   INTEGER,                       -- NULL = no per-file choice
    SubtitleTrackIndex INTEGER,                      -- NULL = no choice, -1 = off
    PlayCount         INTEGER NOT NULL DEFAULT 0,
    UpdatedAt         TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_playback_completed ON PlaybackState(IsCompleted, UpdatedAt DESC);

CREATE TABLE Preferences (
    id               INTEGER PRIMARY KEY CHECK (id = 1),
    DefaultAudioLang TEXT    NOT NULL DEFAULT 'eng',  -- ordered CSV: "jpn,eng"
    DefaultSubLang   TEXT    NOT NULL DEFAULT '',     -- empty = subtitles off
    Volume           INTEGER NOT NULL DEFAULT 80 CHECK (Volume BETWEEN 0 AND 100),
    LastLibraryRoot  TEXT,
    ScanRecursive    INTEGER NOT NULL DEFAULT 1
);

INSERT OR IGNORE INTO Preferences (id) VALUES (1);
```

**Notes**

- `FilePath` is stored absolute, `os.path.normcase`d, unique per path. Renames are handled as delete+insert (new row, fresh progress) — no inode tracking in v1.
- Language lists are stored **ISO 639-2/B** lowercase (`eng`, `jpn`, `ger`) because that is what MKV carries; input in 639-1 (`en`) is normalized on save via `util/languages.py`.
- A grid query joins `MediaLibrary` ⟕ `PlaybackState` and derives `progress = LastPosition / TotalDuration` and a `status` (unwatched / in-progress / completed / unavailable).
- `PlaybackState.AudioTrackIndex` / `SubtitleTrackIndex` hold the **per-file track memory** (D7). They store Qt's track *index* within its type, written the moment you switch tracks. On open, a saved index is restored only if it still exists (`index < track_count`); otherwise the file's tracks changed and we fall back to preferences. `-1` in `SubtitleTrackIndex` means "captions off", which is a real choice and must be preserved.
- Window geometry and theme live in `QSettings` (registry), not the DB — they are UI state, not library data.

---

## 6. Behavioral specification

### 6.1 Scan

1. Root is **fixed**: `%USERPROFILE%\Videos\Telovie` (override with `TELOVIE_LIBRARY_DIR`), created on first launch. No folder picker, no root preference.
2. Recursive walk with `os.scandir`, `followlinks=False`, skipping `System Volume Information`, `$RECYCLE.BIN`, and dotfolders.
3. Accept files whose suffix is `.mkv` (case-insensitive). Everything else ignored.
4. Per file: `stat` → if `(size, mtime)` unchanged and row exists, skip parsing entirely.
5. Parse header → title (MKV `Info/Title`, else filename stem), duration, track list.
6. Upsert in batches of 100; unseen rows **under the scanned root** become `IsAvailable=0` (never deleted, so progress survives a detached drive).
7. No modal progress dialog: a status label shows "Indexing 412 / 1,203" and the grid fills as batches arrive. A `QTimer` polls file size/mtime every 3 s; after two stable snapshots (~6 s) it triggers an incremental scan, so extracting a zip updates the grid without a button press. Window focus also triggers a check.
8. Errors per file are logged and counted, never fatal. Summary toast: "Added 12, updated 3, unavailable 2".

### 6.2 Progress & resume (precise rules)

| Situation | Behavior |
|---|---|
| Playing | `QTimer` every **5,000 ms** → read `position()`, persist |
| Pause / stop / seek settle / source change / window close | persist immediately |
| Position < 10 s | **not** persisted as a resume point (prevents an accidental open from erasing progress) |
| `duration > 0` and `position ≥ 95%` | `IsCompleted=1`, `LastPosition=0` |
| `EndOfMedia` reached | same as above, even if duration is unknown |
| Opening: `IsCompleted=0`, `10 s ≤ LastPosition < 95%` | seek there + toast "Resumed from 12:34" |
| Opening: `LastPosition < 10 s` or `IsCompleted=1` | start at 0; a completed item flips back to in-progress once replay passes 10 s |
| `duration == 0` (unknown) | never auto-complete by percentage; only on `EndOfMedia` |

Writes are clamped to `[0, duration]`, skipped when unchanged by <1 s, and wrapped in one transaction per save. `PlayCount` increments on `LoadedMedia`.

Seeking is applied when `mediaStatus == LoadedMedia`; if the backend reports position 0 afterwards, one retry occurs on the first `positionChanged` (known FFmpeg backend quirk).

### 6.3 Track selection & memory

At `LoadedMedia`, audio and subtitles are resolved independently; first hit wins:

1. **Per-file memory (primary, D7).** `PlaybackState.AudioTrackIndex` / `SubtitleTrackIndex`, written on every manual switch. Restore only if `0 ≤ index < len(tracks)`; `SubtitleTrackIndex = -1` means captions off. A stale index (file re-muxed) falls through instead of guessing.
2. **Language preference (fallback).** Walk `DefaultAudioLang` / `DefaultSubLang` in order (e.g. `hin,eng`) and take the first track whose language matches after normalization (`hi` ↔ `hin`, `ger`/`fre`/`chi` aliases, `und` never matches).
3. **Container default.** Leave Qt's `activeAudioTrack` as loaded. For subtitles, if the preference list is non-empty and nothing matched, force `-1` (off) rather than surfacing an arbitrary Spanish track.

Rules:

- Menus are built from our EBML track list (exact language, codec, flags) and labeled `Audio 1 · Hindi · AC-3`, `Caption 2 · English · SRT`. The index is always shown because these files put `MoviesMod.org` on every track — track titles carry no information.
- Selecting a track applies immediately and **persists that index in the same action**; "Captions off" persists `-1`. This is the "keep it equipped" behavior.
- Restored choices are logged: `tracks: audio 1 (saved) | subs 0 (language eng)`.
- Menus rebuild on `audioTracksChanged` / `subtitleTracksChanged` without clobbering a choice made in the current session.
- Phase 0 verified Qt index order equals MKV `TrackNumber` order on both samples, so persisted indices survive restarts. The count check protects against re-muxed files.

### 6.4 UI

**Library (default view).** Top bar: app name, search field (debounced 200 ms, matches title or path), sort combo (Title A–Z · Recently added · Duration · Progress), and a ⋯ overflow menu holding "Open library folder" and "Refresh library" (F5). The home view has a Continue Watching section for resumable episodes and the next available episode after a completed episode, followed by Collection folders. Folder cards show the number of indexed media contents and open the next directory level, preserving the storage hierarchy (show → season → episodes). Episode cards retain the title-derived gradient, monogram, duration chip, progress bar, and "Watched" badge. Right-click episode card → Play, Start over, Reveal in Explorer, Remove from library. Unavailable files are dimmed with a warning badge and cannot be played.

**Player.** Back arrow + title, black letterboxed video area, control bar: play/pause, elapsed / total, seek slider (with buffered tint), volume slider + mute, audio menu, subtitle menu, fullscreen. Shortcuts: `Space` play/pause, `←/→` ∓10 s, `↑/↓` volume, `M` mute, `F` fullscreen, `Esc` leave fullscreen, `A`/`S` cycle audio/subtitles, `Ctrl+O` choose folder.

**Preferences.** Audio language list and subtitle language list (comma-separated, validated against a bundled ISO list with autocomplete, reorderable), default volume. Save → applied to the next playback; changing the subtitle list also re-applies on the currently loaded video.

**Look & feel.** Custom dark QSS (near-black `#121417` base, `#1b1f24` surfaces, one accent `#4c9aff`), Segoe UI Variable, 8 px radii, no native chrome fights. All controls keyboard-focusable with visible focus rings.

---

## 7. Phased implementation plan

Each phase ends with a **stop-and-report**: I summarize files added, show how to verify, and wait for your go-ahead. No phase starts early.

### Phase 0 — Environment, spike, feasibility gate — ✅ complete (§2.1)
**Goal:** prove the risky assumptions before building.
**Files:** `requirements.txt`, `pyproject.toml`, `.gitignore`, `README.md`, `run.py`, `telovie/__init__.py`, `telovie/__main__.py`, `tools/spike_probe.py`.
**Steps:**
1. Create `.venv` on Python 3.15.1, install PySide6 6.12.0 + pytest, freeze versions.
2. Pin `QT_MEDIA_BACKEND=ffmpeg`; log `QMediaDevices`/backend availability at startup.
3. Probe 3+ of your real MKV files: does `audioTracks()`/`subtitleTracks()` populate? Are languages real ISO codes or `Undetermined`? Does `setActiveAudioTrack` switch audibly? Does `setActiveSubtitleTrack` render? Does seek-after-`LoadedMedia` stick?
4. Dump EBML `TrackEntry` languages from the same files and compare ordinal mapping with Qt.
**Acceptance:** a written findings table for each file; a clear go/no-go on Qt-index ↔ MKV-track mapping; any fallback decision recorded in this SPEC.
**Gate:** if Qt cannot switch tracks on your files, we stop and revisit the approach (e.g. manual-only track menu) **before** UI work.

### Phase 1 — Skeleton, config, database — ✅ complete
**Files:** `telovie/app.py`, `config.py`, `db/*`, `util/*`, `tests/test_schema.py`, `test_repository.py`, `test_languages.py`.
**Steps:** paths/logging bootstrap; schema + `user_version` migration runner; repositories (`upsert_many`, `mark_unavailable`, `list_for_grid`, `get_state`, `save_progress`, `set_completed`, `get_prefs`, `save_prefs`); ISO language normalization with alias table; ms→time formatting; window shows an empty library shell.
**Acceptance:** fresh DB is created and migrated idempotently; all Phase 1 tests pass; no SQL outside `db/`.

### Phase 2 — MKV parser + auto-indexing — ✅ complete
**Files:** `mkv/ebml.py`, `mkv/parser.py`, `library/models.py`, `library/scanner.py`, `library/watcher.py`, `tests/test_ebml_parser.py`, `test_scanner.py`.
**Steps:** vint reader with element-size caps and recursion depth limit; parse title/duration/tracks; stop at first `Cluster`; malformed input returns partial data. `ScanWorker(QThread)` walks the fixed root, skips unchanged files via `(size, mtime)`, emits `progress(done,total,path)`, `batch(list[MediaItem])`, `finished_scan(summary)`, `failed(reason)`; GUI thread persists batches. `LibraryWatcher` polls every 3 s and fires after two stable snapshots so a half-extracted zip is not indexed.
**Acceptance:** 200-file folder scans in <5 s (warm cache) on local SSD; a truncated MKV yields a usable row instead of a crash; parser unit tests run on synthetic bytes with no media files; dropping a new `.mkv` into the folder updates the grid within ~10 s without pressing anything.

### Phase 3 — Library grid — ✅ complete
**Files:** `ui/theme.py`, `ui/main_window.py`, `ui/library_view.py`, `ui/media_card.py`.
**Steps:** shell with top bar and status line; `QScrollArea` + flow layout (no dependency); card painting with cached gradient per title hash; filter/sort via repository query; empty state pointing at the library folder with an Open button; scan progress in the status line; context menu (Play / Start over / Reveal / Remove).
**Acceptance:** 500 cards scroll at 60 fps; search narrows in <100 ms; sort persists across restart; unavailable rows are visibly disabled; the empty state explains the drop folder and offers an Open button.

### Phase 4 — Player shell & controls
**Files:** `playback/controller.py` (load/unload, volume, state signals), `ui/player_view.py`, `ui/controls.py`, `telovie/playback/__init__.py`, `telovie/ui/__init__.py`.
**Steps:** open from card → `PlayerView`; `QVideoWidget` + `QAudioOutput`; play/pause, slider scrubbing with drag-vs-click semantics, buffered tint, elapsed/total labels, volume + mute with icon states, fullscreen, keyboard shortcuts, back returns to grid and releases the source.
**Acceptance:** MKV with HEVC/H.264 + AC3/EAC3/AAC plays with audio; scrub is smooth; leaving the player releases the file handle (verified with `handle.exe` or a rename test); no leaked players after 20 open/close cycles.

### Phase 5 — Progress tracking & auto-resume
**Files:** `playback/controller.py` (extend), `ui/toast.py`, `tests/test_resume_rules.py`.
**Steps:** extract resume/complete rules into pure functions and test them; 5 s timer plus save-on-event hooks; completion at 95 %/`EndOfMedia`; resume by seeking **while paused immediately after `LoadedMedia`, then calling `play()`** (Phase 0: seek-after-play shows 0 for ~3 s); toast; grid progress bars refresh on return; window `closeEvent` flushes state; crash-safety (≤5 s loss).
**Acceptance:** close at 12:00, reopen → resumes at 12:00 with no flash of 0:00; watch to 96 % → card shows Watched and next open starts at 0; quick open/close under 10 s does not erase progress; killing the process mid-play loses ≤5 s.

### Phase 6 — Smart audio & subtitle selection + per-file memory — implementation complete
**Files:** `playback/tracks.py`, `playback/controller.py`, `ui/player_view.py`, `ui/preferences_dialog.py`, `ui/main_window.py`, `ui/library_view.py`, `ui/theme.py`, `tests/test_track_match.py`, `tests/test_preferences_dialog.py`, `tests/test_library_view.py`.
**Steps:** implement §6.3 (saved index → language fallback → container default); build both menus from parsed MKV tracks with `Audio N · <language> · <codec>` labels; write the chosen index to `PlaybackState` on every switch; validate saved indices against the live track count; preferences dialog with ordered lists, validation, autocomplete; log each decision.
**Acceptance:** headless unit tests cover saved-choice priority, stale-index fallback, ISO aliases, subtitle-off, unmatched preference behavior, and preference ordering. Manual confirmation against the sample MKVs remains necessary for audible/rendered switching and persistence across app restarts.

### Phase 7 — Polish & resilience
**Files:** touch-ups across `ui/`, `config.py`.
**Steps:** error surfaces for missing/corrupt/DRM-less files; "file moved" prompt offering Reload or Remove; geometry/volume restore; scan summary toast; consistent disabled states; `README` troubleshooting (codec support, 10-bit/HDR note, log location); log rotation.
**Status:** implementation complete. Geometry/volume persistence and 1 MB × 3 log rotation were already present.
**Acceptance:** unplugging the drive mid-session leaves the app usable; corrupt file shows a clear message and returns to the grid; all error paths log without tracebacks reaching the user. Headless regression tests cover controller error reporting and disabled player controls; unplug/reconnect and real-codec behavior still require manual testing against local media.

### Phase 8 — Packaging (optional, on request)
**Files:** `packaging/telovie.spec`, `packaging/build.ps1`.
**Steps:** PyInstaller one-folder build; confirm Qt multimedia plugins and FFmpeg DLLs are bundled; smoke-test on a clean Windows profile; document the build command.
**Acceptance:** `Telovie.exe` launches on a machine without Python and plays an MKV with subtitles.

---

## 8. Testing strategy

- **pytest, headless:** schema/migrations, repository CRUD, language normalization, EBML parsing on synthetic fixtures, resume rules, track matching. These are the majority of tests and need no media.
- **Manual checklist per phase** (written into `README.md`): the acceptance criteria above, run against 3 sample files you provide (single-audio, dual-audio JPN/ENG, multi-subtitle).
- **Offscreen smoke test:** `QT_QPA_PLATFORM=offscreen` import + window construction, so CI-style checks catch broken signals.
- **No GUI automation** in v1 — not worth the maintenance for a single-user app.

---

## 9. Risks & mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Qt reports `Undetermined` track languages | Auto-selection fails silently | EBML parser is the language oracle; Phase 0 gate; visible "not matched" hint; manual menus always work |
| Qt track index ≠ MKV `TrackNumber` order | Wrong track selected | Match by ordinal per track type, verified in Phase 0; never guess when counts disagree |
| MF backend deprecation | Future breakage | Pin FFmpeg backend; zero MF-specific code |
| ASS/SSA styling not honored | Subtitles look plain | Document as a Qt FFmpeg-backend limitation; no libass in v1 |
| 10-bit/HDR MKV color shift | Visual defect | Document; test a sample; note GPU/driver dependency |
| Huge/network libraries | Slow scan | Header-only reads, stat-based skip, cancel, batch writes |
| Crash during playback | ≤5 s progress loss | 5 s timer + save-on-pause/close |

---

## 10. Out of scope for v1

Transcoding, casting, streaming, thumbnail extraction (deferred per D4), external `.srt`/`.ass` sidecar loading, multi-root libraries, metadata scraping (TMDB/TVDB), TV season/episode grouping, subtitle styling editor, Linux/macOS builds.

---

## 11. Assumptions to confirm at approval

1. **Fixed library root.** `%USERPROFILE%\Videos\Telovie`, created automatically; override only via `TELOVIE_LIBRARY_DIR` (used for tests). Files outside it are never indexed.
2. **MKV only.** `.mp4`/`.avi` are ignored, not indexed.
3. **`Preferences` stays a single-row typed table** (your column names) rather than a key/value store — adding a setting later needs a migration. Say the word and I'll switch to key/value.
4. **Per-file memory beats language preferences.** A saved track index always wins; language matching only runs for files you have never manually adjusted. If neither applies, subtitles stay off rather than showing the container's default subtitle.
5. **Replaying a completed item** resets it to in-progress only after 10 s of playback, so the "Watched" badge isn't lost by a mis-click.
6. **App name/paths:** "Telovie", `%LOCALAPPDATA%\Telovie\library.db`.
7. **Python 3.15.1** with PySide6 6.12.0 in a project venv (fallback: 3.11 if a wheel issue appears).
8. **Track memory is per file, not global.** Indices are meaningless across different muxes, so there is no "last used everywhere" default; new files use the language preferences instead.

---

## 12. Approval checklist

- [ ] Backend = FFmpeg, MF explicitly ruled out
- [ ] Schema in §5 accepted (incl. single-row `Preferences`)
- [ ] Resume/completion thresholds in §6.2 accepted
- [ ] Track-matching rules in §6.3 accepted (esp. subtitle-off-on-no-match)
- [ ] Phase order and file list in §4/§7 accepted
- [ ] Assumptions in §11 confirmed or corrected
- [ ] Phase 0 is the only thing I build next

**Reply "approved"** (plus any corrections) and I'll start Phase 0: venv, pinned dependencies, and the diagnostic probe against your MKV samples.
