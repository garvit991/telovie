# Telovie

Local `.mkv` library manager and player for Windows 11. PySide6 + QtMultimedia
(FFmpeg backend, bundled with PySide6) + SQLite. No VLC, no external codecs, no
network calls.

## Requirements

- Windows 11
- Python 3.10–3.15 (tested on 3.15.1)
- PySide6 6.12.0

## Setup

```powershell
py -3.15 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Run

```powershell
python run.py
```

or `python -m telovie`.

Data lives in `%LOCALAPPDATA%\Telovie\`:

- `library.db` — SQLite library, playback state, preferences
- `logs\app.log` — rotating log

Override with `TELOVIE_DATA_DIR` (handy for a portable copy or tests).

## Library folder

The app has one permanent drop folder, created on first launch:

```
%USERPROFILE%\Videos\Telovie
```

Extract zips straight into it (subfolders are fine, e.g.
`Telovie\Game of Thrones\Season 2\`). Everything under it is indexed
automatically — no folder picker, no Scan button. New or changed files are
picked up within ~10 seconds; `F5` (or `⋯` → Refresh library) forces a check.
Override the folder with `TELOVIE_LIBRARY_DIR`.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

## Troubleshooting

- **A video opens but has no picture or sound:** Qt uses its bundled FFmpeg
  backend. Some codecs or codec profiles may not be supported by the installed
  PySide6 build; DRM-protected media is not supported. Try a standard H.264 or
  HEVC encode and confirm the file plays in another local player.
- **10-bit or HDR video looks washed out, too dark, or has odd colors:** HDR
  tone mapping and some 10-bit output paths depend on the display and graphics
  drivers. Telovie does not currently provide HDR controls; try an SDR/8-bit
  version if the output is incorrect.
- **A library item is missing:** reconnect the drive or restore the `.mkv` to
  its stored path, then use Reload or press `F5` to refresh the library.
- **Playback or scanning fails:** check `%LOCALAPPDATA%\Telovie\logs\app.log`.
  The log rotates at 1 MB and retains three previous files.

## Phase 0 diagnostic probe

```powershell
.\.venv\Scripts\python.exe tools\spike_probe.py
```

Loads every `.mkv` placed in `sample files\`, prints Qt's track/language report
next to a direct EBML header parse, and writes `tools\probe_report.json`.
Sample media is not included in this repository.

## Notes

- **Backend:** `QT_MEDIA_BACKEND=ffmpeg` is pinned in `run.py` and `telovie/app.py`.
  Media Foundation is deprecated in Qt 6.10+ and cannot switch MKV subtitle tracks.
- **Console noise:** the FFmpeg backend prints stream dumps to stderr while
  loading. Harmless, and invisible in a packaged GUI build.
- **Playback strategy:** resume seeks while paused, then plays. Seeking after
  `play()` makes the UI show `0:00` for a few seconds (verified in Phase 0).
- **Track memory:** per-file audio/caption choices are stored in
  `PlaybackState.AudioTrackIndex` / `SubtitleTrackIndex` and restored on open.
  Manual changes persist immediately; `-1` remembers captions-off. Ordered
  language preferences are only a fallback for files without a saved choice.
- **Preferences:** open Preferences from the library menu or player header to
  edit ordered audio/caption languages and the default volume. Language changes
  take effect on the current video when it has no saved per-file choice.
- **Track shortcuts:** `A` cycles audio tracks; `S` cycles captions, including
  captions-off.
- **Status:** Phases 0–7 are implemented. Verify track switching and resume
  against your MKV samples as described in `SPEC.md`.
