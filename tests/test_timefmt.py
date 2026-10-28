from __future__ import annotations

from telovie.util.timefmt import clamp_position, format_ms, format_remaining


def test_format_ms():
    assert format_ms(0) == "0:00"
    assert format_ms(65_000) == "1:05"
    assert format_ms(3_723_000) == "1:02:03"
    assert format_ms(None) == "0:00"
    assert format_ms(-5) == "0:00"


def test_format_remaining():
    assert format_remaining(60_000, 3_600_000) == "-59:00"
    assert format_remaining(3_700_000, 3_600_000) == "-0:00"


def test_clamp_position():
    assert clamp_position(500, 1000) == 500
    assert clamp_position(2000, 1000) == 1000
    assert clamp_position(-10, 1000) == 0
    assert clamp_position(500, 0) == 500  # unknown duration
