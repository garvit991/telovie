"""Telovie entry point.

Pins the Qt multimedia backend before any Qt import so playback behaviour is
deterministic across machines. The FFmpeg backend ships inside PySide6.
"""

from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_MEDIA_BACKEND", "ffmpeg")

from telovie.app import main  # noqa: E402  (import after env pin)

if __name__ == "__main__":
    sys.exit(main())
