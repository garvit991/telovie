"""Unit tests for pure resume and progress rules."""

from __future__ import annotations

import pytest

from telovie.playback.resume import evaluate_progress, should_resume


class TestShouldResume:
    def test_resume_normal_in_progress(self):
        # 12 minutes in a 60-minute video
        duration = 60 * 60 * 1000  # 3600_000 ms
        pos = 12 * 60 * 1000  # 720_000 ms
        assert should_resume(pos, duration, is_completed=False) is True

    def test_no_resume_under_10s(self):
        duration = 60 * 60 * 1000
        assert should_resume(0, duration, is_completed=False) is False
        assert should_resume(5_000, duration, is_completed=False) is False
        assert should_resume(9_999, duration, is_completed=False) is False

    def test_resume_at_10s_boundary(self):
        duration = 60 * 60 * 1000
        assert should_resume(10_000, duration, is_completed=False) is True

    def test_no_resume_when_completed(self):
        duration = 60 * 60 * 1000
        # Even if last position was somehow > 10s, if is_completed is True, don't resume
        assert should_resume(100_000, duration, is_completed=True) is False

    def test_no_resume_at_or_above_95_percent(self):
        duration = 100_000
        # 95% = 95_000
        assert should_resume(94_999, duration, is_completed=False) is True
        assert should_resume(95_000, duration, is_completed=False) is False
        assert should_resume(96_000, duration, is_completed=False) is False

    def test_resume_when_duration_unknown(self):
        # When duration is 0, we cannot calculate 95%, so any pos >= 10s resumes
        assert should_resume(15_000, 0, is_completed=False) is True
        assert should_resume(5_000, 0, is_completed=False) is False


class TestEvaluateProgress:
    def test_under_10s_not_persisted(self):
        # Position < 10 s is not persisted as resume point
        duration = 100_000
        dec = evaluate_progress(5_000, duration, last_saved_position_ms=0)
        assert dec.should_save is False
        assert dec.position_ms == 5_000
        assert dec.is_completed is False

        # Even if previous saved position was 50_000, opening and stopping at 3s doesn't overwrite!
        dec = evaluate_progress(3_000, duration, last_saved_position_ms=50_000)
        assert dec.should_save is False

    def test_persisted_at_10s_and_above(self):
        duration = 100_000
        dec = evaluate_progress(10_000, duration, last_saved_position_ms=0)
        assert dec.should_save is True
        assert dec.position_ms == 10_000
        assert dec.is_completed is False

    def test_skip_if_unchanged_by_less_than_1s(self):
        duration = 100_000
        # Moved only 500ms since last save
        dec = evaluate_progress(15_500, duration, last_saved_position_ms=15_000)
        assert dec.should_save is False

        # Moved 1000ms
        dec = evaluate_progress(16_000, duration, last_saved_position_ms=15_000)
        assert dec.should_save is True
        assert dec.position_ms == 16_000

    def test_completion_at_95_percent(self):
        duration = 100_000
        # 95% = 95_000
        dec = evaluate_progress(95_000, duration, last_saved_position_ms=90_000)
        assert dec.should_save is True
        assert dec.position_ms == 0
        assert dec.is_completed is True

        # Above 95%
        dec = evaluate_progress(96_000, duration, last_saved_position_ms=90_000)
        assert dec.should_save is True
        assert dec.position_ms == 0
        assert dec.is_completed is True

    def test_completion_on_end_of_media(self):
        # Even if duration is unknown (0) or position is small, end_of_media completes
        dec = evaluate_progress(0, 0, last_saved_position_ms=0, end_of_media=True)
        assert dec.should_save is True
        assert dec.position_ms == 0
        assert dec.is_completed is True

    def test_unknown_duration_does_not_complete_by_percentage(self):
        # duration == 0 -> never auto-complete by percentage
        dec = evaluate_progress(100_000, 0, last_saved_position_ms=0, end_of_media=False)
        assert dec.should_save is True
        assert dec.position_ms == 100_000
        assert dec.is_completed is False

    def test_completed_item_flips_to_in_progress_after_10s(self):
        duration = 100_000
        # Previously completed, replay is at 5s -> should NOT save / flip yet
        dec = evaluate_progress(5_000, duration, last_saved_position_ms=0, is_completed=True)
        assert dec.should_save is False
        assert dec.is_completed is True

        # Replay passes 10s -> flips back to in-progress!
        dec = evaluate_progress(10_500, duration, last_saved_position_ms=0, is_completed=True)
        assert dec.should_save is True
        assert dec.position_ms == 10_500
        assert dec.is_completed is False

    def test_position_clamped_to_duration(self):
        duration = 100_000
        # If position is reported as 105_000 (overshoot) but not EndOfMedia,
        # note: 105_000 >= 95%, so it triggers completion!
        dec = evaluate_progress(105_000, duration, last_saved_position_ms=0)
        assert dec.is_completed is True
        assert dec.position_ms == 0
