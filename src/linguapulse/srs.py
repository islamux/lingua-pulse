"""Spaced repetition grading and interval computation."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone, tzinfo

from . import models

GRADES = ("again", "hard", "good", "easy")
DEFAULT_EASE = 2.5
MIN_EASE = 1.3
MAX_EASE = 2.8
MAX_INTERVAL_DAYS = 365.0
RELEARN_MINUTES = 10
GRACE_MINUTES = 15


def new_state(card_id: str, moment: datetime | None = None) -> models.CardState:
    """Create the initial scheduling state of a card."""
    moment = moment or models.now_utc()
    return models.CardState(
        card_id=card_id,
        due=models.iso(moment),
        interval_days=0.0,
        ease=DEFAULT_EASE,
        reps=0,
        lapses=0,
        notifiable=True,
    )


def apply_grade(
    state: models.CardState,
    grade: str,
    moment: datetime | None = None,
    zone: tzinfo | None = None,
) -> models.CardState:
    """Return the state of a card after it was graded."""
    if grade not in GRADES:
        raise ValueError(f"unknown grade: {grade!r}")
    moment = moment or models.now_utc()
    zone = zone or models.local_zone()

    ease = state.ease
    reps = state.reps
    lapses = state.lapses
    interval = state.interval_days
    notifiable = True

    if grade == "again":
        interval = RELEARN_MINUTES / 1440.0
        ease = max(MIN_EASE, ease - 0.20)
        reps = 0
        lapses += 1
        notifiable = False
    elif grade == "hard":
        interval = max(1.0, interval * 1.2) if reps > 0 else 1.0
        ease = max(MIN_EASE, ease - 0.15)
        reps += 1
    elif grade == "good":
        if reps == 0:
            interval = 1.0
        elif reps == 1:
            interval = 6.0
        else:
            interval = interval * ease
        reps += 1
    else:  # easy
        if reps == 0:
            interval = 3.0
        elif reps == 1:
            interval = 8.0
        else:
            interval = interval * ease * 1.3
        ease = min(MAX_EASE, ease + 0.15)
        reps += 1

    interval = min(interval, MAX_INTERVAL_DAYS)
    if grade == "again":
        due = (moment + timedelta(minutes=RELEARN_MINUTES)).astimezone(timezone.utc)
    else:
        due = models.add_wall_clock(moment, interval, zone)

    return models.CardState(
        card_id=state.card_id,
        due=models.iso(due),
        interval_days=interval,
        ease=ease,
        reps=reps,
        lapses=lapses,
        last_graded_at=models.iso(moment),
        handled_due=None,
        notifiable=notifiable,
    )
