"""Pure rule functions for progress tracking, completion, and resume.

These functions encapsulate the business logic defined in SPEC.md section 6.2
and have no Qt or database dependencies, making them fast and straightforward
to unit-test.
"""

from __future__ import annotations

from dataclasses import dataclass

from telovie.config import (
    COMPLETION_RATIO,
    MIN_RESUME_POSITION_MS,
)


@dataclass(frozen=True)
class ProgressDecision:
    """Outcome of evaluating current playback progress."""

    should_save: bool
    position_ms: int
    is_completed: bool


def should_resume(
    last_position_ms: int,
    duration_ms: int,
    is_completed: bool,
    *,
    min_resume_ms: int = MIN_RESUME_POSITION_MS,
    completion_ratio: float = COMPLETION_RATIO,
) -> bool:
    """Determine whether opening this media should trigger an auto-resume seek.

    Rules:
    - If is_completed is True -> start at 0 (do not resume).
    - If last_position_ms < 10s (min_resume_ms) -> start at 0.
    - If duration > 0 and last_position_ms >= 95% (completion_ratio * duration) -> start at 0.
    - Otherwise (10s <= last_position < 95% and not completed) -> resume.
    """
    if is_completed:
        return False
    if last_position_ms < min_resume_ms:
        return False
    if duration_ms > 0 and last_position_ms >= int(duration_ms * completion_ratio):
        return False
    return True


def evaluate_progress(
    position_ms: int,
    duration_ms: int,
    last_saved_position_ms: int = 0,
    *,
    end_of_media: bool = False,
    is_completed: bool = False,
    min_resume_ms: int = MIN_RESUME_POSITION_MS,
    completion_ratio: float = COMPLETION_RATIO,
    min_change_ms: int = 1_000,
) -> ProgressDecision:
    """Evaluate whether and how to persist playback progress.

    Rules from SPEC 6.2:
    - Writes are clamped to [0, duration] (if duration > 0).
    - Position < 10 s is NOT persisted as a resume point (prevents accidental open from erasing progress),
      EXCEPT if completing or already completed / replay transitions:
      specifically:
        * If EndOfMedia reached OR (duration > 0 and position >= 95%):
            IsCompleted=1, LastPosition=0, should_save=True.
        * If position < 10s and not completed:
            should_save=False (do not overwrite prior progress / accidental open).
            (Note: if item was previously completed and replay is under 10s, it stays completed;
             once replay passes 10s, it flips back to in-progress with is_completed=False).
        * If position >= 10s:
            Clamped to duration. If previously completed, is_completed flips to False.
            Skipped if unchanged by < 1s (abs(clamped - last_saved_position_ms) < min_change_ms),
            UNLESS completed state changed.
    """
    # 1. Check completion triggers (EndOfMedia or >= 95% when duration > 0)
    # If duration == 0, never auto-complete by percentage; only on EndOfMedia.
    hit_completion = end_of_media or (
        duration_ms > 0 and position_ms >= int(duration_ms * completion_ratio)
    )

    if hit_completion:
        # Upon completion: IsCompleted=1, LastPosition=0
        # Should save if not already in this state or position was not 0
        already_saved_as_completed = is_completed and last_saved_position_ms == 0
        return ProgressDecision(
            should_save=not already_saved_as_completed,
            position_ms=0,
            is_completed=True,
        )

    # Clamp position
    clamped_pos = max(0, int(position_ms))
    if duration_ms > 0:
        clamped_pos = min(clamped_pos, int(duration_ms))

    # 2. Position < 10s:
    # "Position < 10 s: not persisted as a resume point (prevents an accidental open from erasing progress)"
    # "a completed item flips back to in-progress once replay passes 10 s"
    if clamped_pos < min_resume_ms:
        return ProgressDecision(
            should_save=False,
            position_ms=clamped_pos,
            is_completed=is_completed,
        )

    # 3. Position >= 10s:
    # A completed item flips back to in-progress (is_completed=False)
    new_completed = False
    state_changed = is_completed != new_completed

    # Check if position changed by at least 1s (1000ms) or if completion status changed
    pos_changed = abs(clamped_pos - last_saved_position_ms) >= min_change_ms

    if state_changed or pos_changed:
        return ProgressDecision(
            should_save=True,
            position_ms=clamped_pos,
            is_completed=new_completed,
        )

    return ProgressDecision(
        should_save=False,
        position_ms=clamped_pos,
        is_completed=new_completed,
    )
